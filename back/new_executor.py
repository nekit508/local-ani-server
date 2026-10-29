import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from queue import Queue, Empty
from threading import Condition, RLock, Thread
from typing import Callable, Any, Generator

# phase related future actions

class MCMPManager:
    """
    Multiple consumer multiple producer manager, that provides persistent read/write operations,
    where write operations are not overlapping

    Consumers are have more priority
    """
    _readings: int
    _reading_cond: Condition

    _writings: int
    _writing_cond: Condition

    _lock: bool
    _lock_cond: Condition

    def __init__(self):
        self._readings = 0
        self._writings = 0
        self._reading_cond = Condition()
        self._writing_cond = Condition()

    @property
    @contextmanager
    def read(self):
        """
        Starts read operation

        Blocks any new write operation and waits until all existent finish

        Reentrant
        """
        with self._writing_cond:
            with self._reading_cond:
                with self._lock_cond:
                    self._lock_cond.wait_for(lambda: not self._lock)
                self._readings += 1
            self._writing_cond.wait_for(lambda: self._writings == 0)

        try:
            yield
        finally:
            with self._reading_cond:
                self._readings -= 1
                self._reading_cond.notify_all()

    @property
    @contextmanager
    def write(self):
        """
        Starts write operation

        Blocks new read operations and waits untils all existent finish

        Reentrant
        """
        with self._reading_cond:
            self._reading_cond.wait_for(lambda: self._readings == 0)
            with self._writing_cond:
                with self._lock_cond:
                    self._lock_cond.wait_for(lambda: not self._lock)
                self._writings += 1

        try:
            yield
        finally:
            with self._writing_cond:
                self._writings -= 1
                self._writing_cond.notify_all()

    @property
    @contextmanager
    def lock(self):
        """
        Locks any other operation

        NOT Reentrant
        """
        with self._lock_cond:
            self._lock_cond.wait_for(lambda: not self._lock)
            self._lock = True
            try:
                yield
            finally:
                self._lock = False


class MCMPValue[T]:
    _value: T
    _manager: MCMPManager

    def __init__(self, value: T, manager: MCMPManager):
        self._value = value
        self._manager = manager

    @property
    @contextmanager
    def read(self):
        """
        Use this for atomically read entire value

        Reentrant
        """
        with self._manager.read:
            yield self._value

    @property
    @contextmanager
    def write(self):
        """
        Use this for nonoverlapping writes

        Reentrant
        """
        with self._manager.write:
            yield self._value

    @property
    def lock(self):
        """
        Use this if you want to get full access to value

        NOT Reentrant
        """
        return self._manager.lock


class CommandsQueue:
    _lock: RLock
    _commands: list[Callable]

    def __init__(self):
        self._lock = RLock()
        self._commands = []

    def push(self, command: Callable):
        with self._lock:
            self._commands.append(command)

    def dump(self) -> Generator[Callable, Any, None]:
        with self._lock:
            while len(self._commands):
                try:
                    yield self._commands.pop(0)
                finally:
                    break

    def need(self) -> bool:
        with self._lock:
            return len(self._commands) > 0


class StateSnapshot:
    rev: int
    _data: dict[str, Any]

    def __getattr__(self, item: str):
        return self._data[item] if item in self._data else None

    def __setattr__(self, key: str, value):
        self._data[key] = value

    def __delattr__(self, key: str):
        del self._data[key]


class State:
    _transfer_to_snapshot_fields: list[str] = []

    _rev: int
    _manager: MCMPManager
    _snapshot: StateSnapshot

    def __init__(self, manager: MCMPManager):
        self.rev()
        self._manager = manager
        self._snapshot = StateSnapshot()

    def rev(self, rev: int | None = None):
        self._rev = int(time.time() * 1000) if rev is None else rev

    def _transfer_to_snapshot(self):
        for field in self._transfer_to_snapshot_fields:
            setattr(self._snapshot, field, getattr(self, field))

    def commit(self):
        with self._manager.write:
            self._snapshot.rev = self._rev
            self._transfer_to_snapshot()

    @property
    @contextmanager
    def write(self):
        try:
            yield
        finally:
            self.rev()
            self.commit()


class Task:
    def __init__(self):
        pass

    def execute(self):
        pass

    def failed(self, exception: Exception):
        pass

    def finished(self):
        pass


@dataclass
class PhaseDesc:
    name: str
    """
    Just a name
    """
    working: bool
    """
    Is worker doing something now
    """
    alive: bool
    """
    Is thread is running now
    """
    active: bool
    """
    Is task is running
    """
    error: bool
    """
    Is malicious state
    """


class Phase(Enum, PhaseDesc):
    DISABLED = PhaseDesc("disabled", False, False, False, False) # thread is dead - not started yet
    STARTING = PhaseDesc("starting", True, False, False, False) # started, but still not in loop
    PROCESSING_COMMANDS = PhaseDesc("processing commands", True, True, False, False) # processing async commands
    IDLE = PhaseDesc("waiting", False, True, False, False) # waiting for task
    WORKING = PhaseDesc("working", True, True, False, False) # doing smth in loop (typically - ended task but not exited loop yet)
    ACTIVE = PhaseDesc("active", True, True, True, False) # executing task - farther detail in task state
    FAILED = PhaseDesc("failed", False, False, False, True) # thread is dead - worker level error occurred
    STOPPED = PhaseDesc("stopped", False, False, False, False) # thread is dead - stopped by on purpose


class WorkerState(State):
    phase: Phase
    pending_stop: bool

    def __init__(self, manager: MCMPManager):
        super().__init__(manager)
        self._transfer_to_snapshot_fields.extend(("phase", "pending_stop"))
        self.phase = Phase.DISABLED
        self.pending_stop = False


class Worker:
    _commands_queue: CommandsQueue
    _state: WorkerState
    _thread: Thread|None
    _executor: "Executor"

    def __init__(self, executor: "Executor"):
        self._commands_queue = CommandsQueue()
        self._executor = executor
        self._state = WorkerState(executor.mcmp_manager)
        self._thread = None

    def _phase(self, phase: Phase):
        with self._state:
            self._state.phase = phase

    def start(self):
        self._phase(Phase.STARTING)
        self._thread = Thread(target=self._run)
        self._thread.start()

    def submit(self, command: Callable):
        self._commands_queue.push(command)

    def _process_commands(self):
        for command in self._commands_queue.dump():
            command(self)

    # noinspection PyBroadException
    def _loop(self) -> bool:
        while not self._state.pending_stop:
            if self._state.pending_stop:
                return False

            if self._commands_queue.need():
                self._phase(Phase.PROCESSING_COMMANDS)
                self._process_commands()

            self._phase(Phase.IDLE)
            task = self._executor.get_task(timeout=1)

            if task is not None:
                break

        if self._state.pending_stop:
            return False

        self._phase(Phase.ACTIVE)
        try:
            # noinspection PyUnboundLocalVariable
            task.execute()
        except Exception as e:
            task.failed(e)
        else:
            task.finished()
        finally:
            self._phase(Phase.WORKING)

        return not self._state.pending_stop

    def _stopped(self):
        self._phase(Phase.STOPPED)

    def _failed(self):
        self._phase(Phase.FAILED)

    def _run(self):
        try:
            while self._loop():
                pass
        except:
            self._failed()
        else:
            self._stopped()


class Executor:
    _mcmp_manager: MCMPManager
    _queue: Queue[Task]

    def __init__(self):
        self._mcmp_manager = MCMPManager()
        self._queue = Queue()

    @property
    def mcmp_manager(self):
        return self._mcmp_manager

    def get_task(self, timeout: int | None = None) -> Task|None:
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None


if __name__ == "__main__":
    pass
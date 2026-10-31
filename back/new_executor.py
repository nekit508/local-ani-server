import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from queue import Queue, Empty
from threading import Condition, RLock, Thread
from typing import Callable, Any, Generator

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
        self._lock = False
        self._reading_cond = Condition()
        self._writing_cond = Condition()
        self._lock_cond = Condition()

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

    @property
    @contextmanager
    def unlocked(self):
        """
        Starts operation that is locked only by lock operation

        Reentrant
        """
        with self._lock_cond:
            yield


class MCMPValue[T]:
    _value: T
    _manager: MCMPManager

    def __init__(self, value: T, manager: MCMPManager):
        self._value = value
        self._manager = manager

    @property
    def manager(self):
        return self._manager

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
    @contextmanager
    def lock(self):
        """
        Use this if you want to get full access to the value

        NOT Reentrant
        """
        with self._manager.lock:
            yield self._value

    @property
    @contextmanager
    def unlocked(self) -> Generator[T, Any, None]:
        """
        Use this if you want to do something irrelevant to data

        Reentrant
        """
        with self._manager.unlocked:
            yield self._value


class MPSCQueue:
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
                yield self._commands.pop(0)

    def need(self) -> bool:
        with self._lock:
            return len(self._commands) > 0


class Data:
    _data: dict[str, Any] = {}

    def __getattr__(self, item: str):
        return self._data[item] if item in self._data else None

    def __setattr__(self, key: str, value):
        self._data[key] = value

    def __delattr__(self, key: str):
        del self._data[key]


class StateSnapshot:
    rev: int
    id: int
    _data: Data

    def __init__(self, id_: int):
        self.id = id_
        self.rev = 0
        self._data = Data()

    @property
    def data(self):
        return self._data


class State[T]:
    _ID: int = 0

    _transfer_to_snapshot_fields: list[str] = []

    _rev: int
    _id: int
    _states: MCMPValue[dict[int, State]]
    _snapshot: StateSnapshot

    _owner: T

    def __init__(self, states: MCMPValue[dict[int, State]]):
        self.update_rev()
        self._states = states
        self._owner = None

        self._id = State._ID
        State._ID += 1

        with self._states.lock as s:
            self._snapshot = StateSnapshot(self._id)
            self._snapshot.rev = self._rev
            s[self._id] = self

    def update_rev(self, rev: int | None = None):
        self._rev = int(time.time() * 1000) if rev is None else rev

    def _transfer_to_snapshot(self):
        self._snapshot.rev = self._rev
        self._snapshot.id = self._id
        for field in self._transfer_to_snapshot_fields:
            setattr(self._snapshot.data, field, getattr(self, field))

    def commit(self):
        with self._states.write:
            self._transfer_to_snapshot()

    @property
    def owner(self) -> T:
        return self._owner

    @owner.setter
    def owner(self, owner: T):
        if self._owner is not None:
            raise RuntimeError("Owner is already set")
        self._owner = owner

    @property
    def id(self):
        return self._id

    @property
    @contextmanager
    def write(self):
        try:
            yield
        finally:
            self.update_rev()
            self.commit()


class Task:
    def __init__(self):
        pass

    def execute(self, worker: "Worker"):
        self._execute()

    def _execute(self):
        pass

    def failed(self, exception: Exception):
        pass

    def finished(self):
        pass


@dataclass
class PhaseDesc:
    phase_name: str
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


class Phase(PhaseDesc, Enum):
    DISABLED = ("disabled", False, False, False, False) # thread is dead - not started yet
    STARTING = ("starting", True, False, False, False) # started, but still not in loop
    PROCESSING_COMMANDS = ("processing commands", True, True, False, False) # processing async commands
    IDLE = ("waiting", False, True, False, False) # waiting for task
    WORKING = ("working", True, True, False, False) # doing smth in loop (typically - ended task but not exited loop yet)
    ACTIVE = ("active", True, True, True, False) # executing task - farther detail in task state
    FAILED = ("failed", False, False, False, True) # thread is dead - worker level error occurred
    STOPPED = ("stopped", False, False, False, False) # thread is dead - stopped by on purpose

    def __hash__(self):
        return self.name.__hash__()


class WorkerState(State["Worker"]):
    phase: Phase
    pending_stop: bool

    _transfer_to_snapshot_fields = State._transfer_to_snapshot_fields.copy()
    _transfer_to_snapshot_fields.extend(("phase", "pending_stop"))

    def __init__(self, states: MCMPValue[dict[int, State]]):
        super().__init__(states)
        self.phase = Phase.DISABLED
        self.pending_stop = False

    def __repr__(self):
        return self.phase.phase_name

    #__str__ = __repr__


class Worker:
    """
    From outside, you can use only start and submit methods
    """
    _actions_queue: MPSCQueue
    _state: WorkerState
    _thread: Thread|None
    _executor: "Executor"
    _next_phase_actions: dict[Phase, list[Callable]]

    @staticmethod
    def STOP(worker: "Worker"):
        with worker._state.write:
            worker._state.pending_stop = True

    @staticmethod
    def ON_PHASE(phase: Phase, action: Callable) -> Callable:
        return lambda w: w.on_next_phase(phase, action)

    def __init__(self, executor: "Executor"):
        self._actions_queue = MPSCQueue()
        self._executor = executor
        self._state = WorkerState(executor.workers_states)
        self._state.commit()
        self._thread = None
        self._next_phase_actions = {}
        self._state.owner = self

    def _phase(self, phase: Phase):
        with self._state.write:
            self._state.phase = phase
        if phase in self._next_phase_actions:
            copy = self._next_phase_actions[phase].copy()
            self._next_phase_actions[phase].clear()
            for action in copy:
                action(self)

    def start(self):
        self._phase(Phase.STARTING)
        self._thread = Thread(target=self._run)
        self._thread.start()

    def on_next_phase(self, phase: Phase, action: Callable):
        if phase not in self._next_phase_actions:
            self._next_phase_actions[phase] = []
        self._next_phase_actions[phase].append(action)

    def submit(self, actions: Callable):
        self._actions_queue.push(actions)

    def _process_commands(self):
        for command in self._actions_queue.dump():
            command(self)

    # noinspection PyBroadException
    def _loop(self) -> bool:
        while not self._state.pending_stop:
            if self._state.pending_stop:
                return False

            if self._actions_queue.need():
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
            task.execute(self)
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

    # noinspection PyBroadException
    def _run(self):
        try:
            while self._loop():
                pass
        except:
            self._failed()
        else:
            self._stopped()


class Executor:
    _workers_states: MCMPValue[dict[int, WorkerState]]
    _tasks_states: MCMPValue[dict[int, State]]
    _tasks_queue: Queue[Task]

    def __init__(self):
        self._workers_states = MCMPValue({}, MCMPManager())
        self._tasks_states = MCMPValue({}, MCMPManager())
        self._tasks_queue = Queue()

    def spawn_worker(self) -> Worker:
        return Worker(self)

    def create_task(self):
        pass

    @property
    def workers_states(self):
        return self._workers_states

    @property
    def mcmp_tasks_states(self):
        return self._tasks_states

    def get_task(self, timeout: int | None = None) -> Task|None:
        try:
            return self._tasks_queue.get(timeout=timeout)
        except Empty:
            return None

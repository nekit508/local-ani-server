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
    _data: dict[str, Any]

    def __init__(self):
        self._data = {}

    def __getitem__(self, item):
        return self._data[item] if item in self._data else None

    def __setitem__(self, key: str, value):
        self._data[key] = value

    def __delitem__(self, key: str):
        del self._data[key]

    @property
    def dict(self):
        return self._data


class StateSnapshot[S]:
    rev: int
    id: int
    soft_delete: bool
    _data: Data
    _state: S

    def __init__(self, id_: int, state: S):
        self.id = id_
        self.rev = 0
        self.soft_delete = False
        self._data = Data()
        self._state = state

    @property
    def state(self):
        return self._state

    @property
    def data(self):
        return self._data

    @property
    def dict(self):
        return {
            "id": self.id,
            "rev": self.rev,
            "soft_delete": self.soft_delete,
            "data": self.data.dict
        }


class State[T]:
    _ID: int = 0
    _soft_delete: bool

    _transfer_to_snapshot_fields: list[str] = []

    _rev: int
    _id: int
    _shared_index: MCMPValue[dict[int, StateSnapshot]]
    _snapshot: StateSnapshot

    _owner: T

    def __init__(self, states: MCMPValue[dict[int, StateSnapshot]]):
        self.update_rev()
        self._shared_index = states
        self._owner = None
        self._soft_delete = False

        self._id = State._ID
        State._ID += 1

        with self._shared_index.lock as index:
            index: dict[int, StateSnapshot]
            self._snapshot = StateSnapshot(self._id, self)
            self._transfer_to_snapshot(initial=True)
            index[self._id] = self._snapshot

    def update_rev(self, rev: int | None = None):
        self._rev = int(time.time() * 1000) if rev is None else rev

    def _transfer_to_snapshot(self, initial: bool = False):
        self._snapshot.soft_delete = self._soft_delete
        self._snapshot.rev = self._rev
        self._snapshot.id = self._id

        if self._soft_delete:
            return # do not save fields after deletions

        if initial:
            return

        for field in self._transfer_to_snapshot_fields:
            self._snapshot.data[field] = getattr(self, field)

    def commit(self):
        with self._shared_index.write:
            self._transfer_to_snapshot()

    def delete(self):
        with self.write:
            self._soft_delete = True

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


class TaskState[T:"Task"](State[T]):
    error: Exception | None
    working: bool
    worker: int

    _transfer_to_snapshot_fields = State._transfer_to_snapshot_fields.copy()
    _transfer_to_snapshot_fields.extend(("error", "working", "worker"))
    print(f"TaskState t2sf: {_transfer_to_snapshot_fields}")

    def __init__(self, states: MCMPValue[dict[int, StateSnapshot]]):
        super().__init__(states)
        self.error = None
        self.working = False
        self.worker = 0


class Task[S:TaskState]:
    _state: S

    def __init__(self, executor: "Executor"):
        self._state = self._obtain_state(executor.tasks_states)
        self._state.owner = self
        self._state.commit()

    def _obtain_state(self, states: MCMPValue[dict[int, StateSnapshot]]) -> TaskState:
        return TaskState(states)

    def execute(self, worker: "Worker"):
        with self._state.write:
            self._state.working = True
            self._state.error = None
            self._state.worker = worker.id
            self._state.payload = {}
        self._execute()

    def _execute(self):
        """
        Do not call original method
        :raises: NotImplementedError
        """
        raise NotImplementedError

    def failed(self, exception: Exception):
        with self._state.write:
            self._state.working = False
            self._state.error = exception
        print(f"Task {self.id} failed with: {exception}")

    def finished(self):
        self._state.delete()

    def _info(self, info: str):
        with self._state.write:
            self._state.info = info

    @property
    def id(self):
        return self._state.id


@dataclass
class WorkerPhaseDesc:
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


class WorkerPhase(WorkerPhaseDesc, Enum):
    DISABLED = ("DISABLED", False, False, False, False)  # thread is dead - not started yet
    STARTING = ("STARTING", True, False, False, False)  # started, but still not in loop
    PROCESSING_COMMANDS = ("PROCESSING_COMMANDS", True, True, False, False)  # processing async commands
    IDLE = ("IDLE", False, True, False, False)  # waiting for task
    WORKING = ("WORKING", True, True, False,
               False)  # doing smth in loop (typically - ended task but not exited loop yet)
    ACTIVE = ("ACTIVE", True, True, True, False)  # executing task - farther detail in task state
    FAILED = ("FAILED", False, False, False, True)  # thread is dead - worker level error occurred
    STOPPED = ("STOPPED", False, False, False, False)  # thread is dead - stopped by on purpose

    def __hash__(self):
        return self.name.__hash__()


class WorkerState(State["Worker"]):
    phase: WorkerPhase
    pending_stop: bool
    error: Exception | None
    task: int
    """
    Last exception raised inside the thread loop and outside of the task execution

    Valid only if phase if ERROR
    """

    _transfer_to_snapshot_fields = State._transfer_to_snapshot_fields.copy()
    _transfer_to_snapshot_fields.extend(("phase", "pending_stop", "error", "task"))
    print(f"WorkerState t2sf: {_transfer_to_snapshot_fields}")

    def __init__(self, states: MCMPValue[dict[int, StateSnapshot]]):
        super().__init__(states)
        self.phase = WorkerPhase.DISABLED
        self.pending_stop = False
        self.error = None
        self.task = 0

    def __repr__(self):
        return self.phase.phase_name


# noinspection PyPep8Naming
class Worker:
    """
    From outside, you can use only start and submit methods
    """
    _actions_queue: MPSCQueue
    _state: WorkerState
    _thread: Thread | None
    _executor: "Executor"
    _next_phase_actions: dict[WorkerPhase, list[Callable]]

    @staticmethod
    def STOP(worker: "Worker"):
        with worker._state.write:
            worker._state.pending_stop = True

    @staticmethod
    def ON_PHASE(phase: WorkerPhase, action: Callable) -> Callable:
        return lambda w: w.on_next_phase(phase, action)

    def __init__(self, executor: "Executor"):
        self._actions_queue = MPSCQueue()
        self._executor = executor
        self._thread = None
        self._next_phase_actions = {}

        self._state = WorkerState(executor.workers_states)
        self._state.owner = self
        self._state.commit()

    @property
    def id(self):
        return self._state.id

    @property
    def _phase(self):
        return self._state.phase

    @_phase.setter
    def _phase(self, phase: WorkerPhase):
        with self._state.write:
            self._state.phase = phase
        if phase in self._next_phase_actions:
            copy = self._next_phase_actions[phase].copy()
            self._next_phase_actions[phase].clear()
            for action in copy:
                action(self)

    def start(self):
        with self._state.write:
            self._state.phase = WorkerPhase.STARTING
            self._state.error = None
            self._state.task = 0
            self._state.pending_stop = False

        self._thread = Thread(target=self._run)
        self._thread.start()

    def on_next_phase(self, phase: WorkerPhase, action: Callable):
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
                self._phase = WorkerPhase.PROCESSING_COMMANDS
                self._process_commands()

            self._phase = WorkerPhase.IDLE
            task = self._executor.get_task(timeout=5)

            if task is not None:
                break

        if self._state.pending_stop:
            return False

        with self._state.write:
            self._state.phase = WorkerPhase.ACTIVE
            # noinspection PyUnboundLocalVariable,PyTypeChecker
            self._state.task = task.id
        try:
            # noinspection PyUnboundLocalVariable
            task.execute(self)
        except Exception as e:
            task.failed(e)
        else:
            task.finished()
        finally:
            self._phase = WorkerPhase.WORKING

        return not self._state.pending_stop

    def _stopped(self):
        with self._state.write:
            self._state.phase = WorkerPhase.STOPPED
            self._state.pending_stop = False

    def _failed(self):
        self._phase = WorkerPhase.FAILED

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
    _workers_states: MCMPValue[dict[int, StateSnapshot]]
    _tasks_states: MCMPValue[dict[int, StateSnapshot]]
    _tasks_queue: Queue[Task]

    def __init__(self):
        self._workers_states = MCMPValue({}, MCMPManager())
        self._tasks_states = MCMPValue({}, MCMPManager())
        self._tasks_queue = Queue()

    def spawn_worker(self) -> Worker:
        return Worker(self)

    def submit_task[T:Task](self, task: T):
        self._tasks_queue.put(task)

    @property
    def workers_states(self):
        return self._workers_states

    @property
    def tasks_states(self):
        return self._tasks_states

    def get_task(self, timeout: int | None = None) -> Task | None:
        try:
            return self._tasks_queue.get(timeout=timeout)
        except Empty:
            return None

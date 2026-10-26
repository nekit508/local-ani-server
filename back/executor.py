import time
from abc import abstractmethod, ABC
from queue import Queue, Empty
from threading import Thread, RLock
from typing import Self, Any, overload


class Bucket[T:"State"]:
    states: dict[int, T]
    _name: str

    def __init__(self, name: str):
        self.states = {}
        self._name = name

    @property
    def name(self):
        return self._name

    def add(self, state: T):
        self.states[state.id] = state

    def remove(self, state: T):
        if state.id in self.states:
            with state:
                state.soft_delete()

    def __getitem__(self, item: int) -> T|None:
        return self.states[item] if item in self.states else None

    def __iter__(self):
        return self.states.values().__iter__()


class SharedIndex:
    _lock: RLock
    data: dict[str, "Bucket"]
    global_states: dict[int, "State"]

    def __init__(self):
        self._lock = RLock()
        self.data = {}
        self.global_states = {}

    @overload
    def __getitem__(self, item: int) -> "State|None": ...

    @overload
    def __getitem__[S:State](self, item: str) -> "Bucket[S]|None": ...

    def __getitem__(self, item: int | str) -> "Bucket|TaskState|None":
        if type(item) is str:
            if item not in self.data:
                self.data[item] = Bucket(item)
            return self.data[item] if item in self.data else None
        elif type(item) is int:
            return self.global_states[item] if item in self.global_states else None
        raise ValueError("Item should be str or int")

    def add_state(self, state: "State"):
        name = state.get_bucket_name()
        self[name].add(state)

        self.global_states[state.id] = state

    def __enter__(self) -> Self:
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()


class State:
    ID: int = 0
    _id: int = 0
    """
    All write operations should be performed inside with block when task is being processed
    """
    _lock: RLock
    _rev: int
    """
    Last update time (in milliseconds) 
    """
    _rev_start: int
    soft_deleted: bool

    _fields_to_serialise: list[str]

    def __init__(self):
        self._id = State.ID
        State.ID += 1

        self._rev = 0
        self._lock = RLock()
        self._rev_start = 0
        self.soft_deleted = False

    @property
    def id(self) -> int:
        return self._id

    def get_bucket_name(self) -> str:
        return "task"

    def updated(self, new_rev: int | None = None):
        self._rev = new_rev if new_rev is not None else int(time.time() * 1000)

    def __enter__(self) -> Self:
        self._lock.acquire()
        self._rev_start = self._rev
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._rev_start != self._rev:
            self.commit_to_shared_indexes()
        self._lock.release()

    def commit_to_shared_indexes(self):
        pass # am I really need it? just retain this method for now

    def soft_delete(self):
        self.soft_deleted = True
        self.updated()

    def serialise(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "_type": type(self).__name__,
            "id": self.id,
            "rev": self.rev(),
            "soft_deleted": self.soft_deleted
        }
        return out

    def rev(self) -> int:
        return self._rev

    def quick_str(self) -> str:
        return ""


class TaskState(State):
    error: "Exception|None"
    """
    Error that raise while task have been executed
    """
    worker: "Worker|None"
    """
    Worker that has lastly executed this task if "error" is not None or that currently executing this task
    """

    def __init__(self):
        super().__init__()
        self.error = None
        self.worker = None

    def set_error(self, error: Exception):
        self.error = error
        self.updated()

    def set_worker(self, worker: "Worker|None" = None):
        self.worker = worker
        self.updated()

    def serialise(self) -> dict[str, Any]:
        out = super().serialise()
        out["worker"] = self.worker.state.id if self.worker is not None else -1
        out["error"] = repr(self.error) if self.error is not None else ""
        return out


class Task[T:TaskState](ABC):
    state: T

    def __init__(self, state: T):
        self.state = state

    @abstractmethod
    def execute(self):
        pass

    def ran(self, worker: "Worker"):
        with self.state:
            self.state.set_worker(worker)

    def finished(self):
        with self.state:
            self.state.set_worker()

    def failed(self, error: Exception):
        with self.state:
            self.state.set_error(error)


class WorkerState(State):
    working: bool
    """
    Is worker enabled
    """
    current_task: "Task|None"
    """
    Currently running task or task that raised "error"
    """
    error: Exception|None
    """
    Error raised by lastly failed task
    """
    bad_error: Exception|None
    """
    Error raised not by task
    """

    def __init__(self):
        super().__init__()
        self.working = False
        self.current_task = None
        self.error = None
        self.bad_error = None

    def task(self, task: "Task|None" = None):
        self.current_task = task
        self.updated()

    def task_fault(self, error: Exception | None):
        self.error = error
        self.working = error is None
        self.updated()

    def critical_fault(self, bad_error: Exception | None):
        self.bad_error = bad_error
        self.working = bad_error is None
        self.updated()

    def start(self):
        """
        Reset and set working to True
        :return:
        """
        if self.working:
            raise RuntimeError(f"Worker {self.id} already working and cannot be started")

        self.error = None
        self.bad_error = None
        self.working = True
        self.current_task = None
        self.updated()

    def serialise(self) -> dict[str, Any]:
        out = super().serialise()

        out["current_task_id"] = self.current_task.state.id if self.current_task is not None else -1
        if self.current_task is not None:
            with self.current_task.state as state:
                out["current_task"] = state.serialise()

        out["error"] = repr(self.error) if self.error is not None else ""
        out["bad_error"] = repr(self.bad_error) if self.bad_error is not None else ""
        out["working"] = self.working
        return out

    def get_bucket_name(self) -> str:
        return "worker"

    def rev(self) -> int:
        if self.current_task is None:
            return super().rev()
        else:
            with self.current_task.state as state:
                return max(super().rev(), state.rev())


class Worker:
    state: "WorkerState"
    thread: Thread
    queue: "Queue[Task]"
    success: "list[Task]"
    success_lock: RLock

    def __init__(self, queue: "Queue[Task]", success: "list[Task]", success_lock: RLock):
        """
        Queues must be infinite
        """
        if queue.maxsize > 0:
            raise ValueError("Queue must be infinite")

        self.queue = queue
        self.success = success
        self.success_lock = success_lock

        self.thread = Thread(target=self.run, daemon=True)
        self.state = WorkerState()

    @property
    def should_work(self):
        with self.state:
            return self.state.working

    def start(self):
        with self.state:
            self.state.start()
            self.thread.start()

    def run(self):
        try:
            while self.loop(): pass
        except Exception as e:
            with self.state:
                self.state.critical_fault(e)

    def loop(self) -> bool:
        """
        :return: whether loop be continued
        """
        if not self.should_work:
            return False

        try:
            task = self.queue.get(timeout=2)
        except Empty:
            return self.should_work

        if not self.should_work:
            self.queue.put(task)
            return False

        with self.state:
            self.state.task(task)
        task.ran(self)

        try:
            task.execute()
        except Exception as e:
            with self.state:
                self.state.task_fault(e)
            task.failed(e)
            return False

        with self.success_lock:
            self.success.append(task)

        with self.state:
            self.state.task()
        task.finished()

        return self.should_work


    def request_stop(self):
        """
        Non-blocking soft stop - mark as not working and let it end task in its own thread
        :return:
        """
        with self.state:
            if not self.state.working:
                return
            self.thread.join(timeout=0)


class Executor:
    queue: "Queue[Task]"

    success_lock: RLock
    success: "list[Task]"

    workers: "list[Worker]"
    shared_index: "SharedIndex"

    def __init__(self):
        self.success_lock = RLock()
        self.success = []

        self.queue = Queue()
        self.workers = []

        self.shared_index = SharedIndex()

    def submit[T:Task](self, task: T):
        self.queue.put(task)

        with self.shared_index:
            self.shared_index.add_state(task.state)

    def start_worker(self) -> "Worker":
        worker = Worker(self.queue, self.success, self.success_lock)
        worker.start()
        self.workers.append(worker)

        with self.shared_index:
            self.shared_index.add_state(worker.state)

        return worker

    def shutdown(self):
        for worker in self.workers:
            worker.request_stop()



from back.new_executor import Task, Executor


class DownloadTask(Task):
    def __init__(self, executor: "Executor"):
        super().__init__(executor)
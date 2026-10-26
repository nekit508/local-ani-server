import os.path
from typing import Any

import yt_dlp

from back.cli import VideoURLProvider, TargetQuality, QualityPolicy
from back.config import settings
from back.executor import TaskState, Task


def title_to_path(title: str) -> str:
    return title

def path_to_title(path: str) -> str:
    return path


class DownloadError(Exception):
    url: str

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def __repr__(self) -> str:
        return f"DownloadError of {self.url}"


class NoAppropriateQuality(Exception):
    target: TargetQuality
    policy: QualityPolicy

    def __init__(self, target: TargetQuality, policy: QualityPolicy):
        super().__init__()
        self.target = target
        self.policy = policy

    def __repr__(self) -> str:
        return f"NoAppropriateQuality {self.target}{self.policy}"


class DownloadTaskState(TaskState):
    progress: float
    _prov: "VideoURLProvider"
    state: str
    quality: int | None

    def __init__(self, prov: "VideoURLProvider"):
        super().__init__()
        self.progress = 0
        self._prov = prov
        self.quality = None
        self.state = ""

    def set_progress(self, progress: float):
        self.progress = progress
        self.updated()

    def set_state(self, state: str):
        self.state = state
        self.updated()

    def set_quality(self, quality: int):
        self.quality = quality
        self.updated()

    @property
    def prov(self):
        return self._prov

    def get_bucket_name(self) -> str:
        return f"task/download/{self._prov.title}"

    def serialise(self) -> dict[str, Any]:
        out = super().serialise()
        out["state"] = self.state
        out["quality"] = self.quality
        out["title"] = self.prov.title
        out["source_title"] = self.prov.source_title
        out["ordinal"] = self.prov.ordinal
        out["progress"] = self.progress
        return out


class DownloadTask(Task[DownloadTaskState]):
    def __init__(self, prov: "VideoURLProvider"):
        super().__init__(DownloadTaskState(prov))

    def execute(self):
        video = self.state.prov()

        with self.state:
            path = os.path.abspath(
                f"{settings.DOWNLOAD_DIR}/{title_to_path(self.state.prov.title)}/"
                f"{title_to_path(self.state.prov.source_title)}/{self.state.prov.ordinal}"
            )
            if video is None:
                raise NoAppropriateQuality(self.state.prov.q_target, self.state.prov.q_policy)
            self.state.set_quality(video.quality)

        url = video.url

        with yt_dlp.YoutubeDL({
            "logger": self,
            "progress_hooks": [self._hook],
            "outtmpl": f"{path}.%(ext)s",
            "concurrent_fragment_downloads": settings.FRAGMENTS_PARALLEL
        }) as dl:
            with self.state:
                self.state.set_state("Starting downloading")

            code = dl.download((url,))

            if code != 0:
                raise DownloadError(url)

    def debug(self, msg):
        # print(msg)
        if msg.startswith('[debug] '):
            pass
        else:
            self.info(msg)

    def _hook(self, data: dict[str, Any]):
        if "_default_template" in data:
            with self.state:
                state: str = data["_default_template"]
                progress = float(data["_percent"]) / 100
                self.state.set_state(state.strip())
                self.state.set_progress(progress)

    def info(self, msg):
        # print(f"[INFO] {msg}")
        pass

    def warning(self, msg):
        # print(f"[WARNING] {msg}", file=sys.stderr)
        pass

    def error(self, msg):
        #print(f"[ERROR] {msg}", file=sys.stderr)
        pass
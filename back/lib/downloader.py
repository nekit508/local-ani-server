from pathlib import Path

from anicli_api.player.base import Video
from yt_dlp import YoutubeDL

from back.lib.cli import VideoURLPromise
from back.config import settings
from back.lib.executor import Task, Executor, TaskState, StateSnapshot, MCMPValue
from back.services.videos import videos


class YTDLPLogger:
    def debug(self, msg):
        print(f"[DEBUG] {msg}")

    def info(self, msg):
        print(f"[INFO] {msg}")

    def warning(self, msg):
        print(f"[WARNING] {msg}")

    def error(self, msg):
        print(f"[ERROR] {msg}")


class DownloadTaskState(TaskState["DownloadTask"]):
    speed: str
    progress: float
    output_format: str
    output_file: Path | None
    name: str

    title_id: int
    source_id: int
    ordinal: int

    _transfer_to_snapshot_fields = TaskState._transfer_to_snapshot_fields.copy()
    _transfer_to_snapshot_fields.extend(("speed", "progress", "name", "output_format", "output_file", "title_id", "source_id", "ordinal"))
    print(f"DownloadTaskState t2sf {_transfer_to_snapshot_fields}")

    def __init__(self, states: MCMPValue[dict[int, StateSnapshot]]):
        super().__init__(states)
        self.speed = ""
        self.progress = 0
        self.output_format = ""
        self.output_file = None
        self.name = ""
        self.title_id = 0
        self.source_id = 0
        self.ordinal = 0

class DownloadTask(Task[DownloadTaskState]):
    _video_promise: VideoURLPromise
    _video: Video | None
    _logger: YTDLPLogger

    _concurrent_fragment_downloads: int
    _socket_timeout: int
    """
    seconds
    """

    def __init__(self,
                 executor: "Executor",
                 name: str,
                 video: VideoURLPromise,
                 title_id: int,
                 source_id: int,
                 ordinal: int,
                 socket_timeout: int | None = None,
                 concurrent_fragment_downloads: int | None = None,
                 output_format: str | None = None):
        super().__init__(executor)
        self._state.name = name

        self._state.title_id = title_id
        self._state.source_id = source_id
        self._state.ordinal = ordinal

        self._video = None
        self._video_promise = video
        self._logger = YTDLPLogger()

        self._socket_timeout = settings.DOWNLOADER_SOCKET_TIMEOUT if socket_timeout is None else socket_timeout
        self._concurrent_fragment_downloads = settings.DOWNLOADER_CONCURRENT_FRAGMENT_DOWNLOADS if concurrent_fragment_downloads is None else concurrent_fragment_downloads
        self._state.output_format = settings.DOWNLOADER_OUTPUT_FORMAT if output_format is None else output_format

        self._state.output_file = (
                Path(settings.DOWNLOAD_DIR) /
                str(self._state.title_id) /
                str(self._state.source_id) /
                str(self._state.ordinal)
        ).with_suffix(f".{self._state.output_format}")

        self._state.commit()

    def _obtain_state(self, states: MCMPValue[dict[int, StateSnapshot]]) -> TaskState:
        return DownloadTaskState(states)

    def _execute(self):
        if not videos.try_create(self._state.title_id, self._state.source_id, self._state.ordinal):
            return

        self._video = self._video_promise()

        with YoutubeDL(self._create_opts()) as ydl:
            if not videos.loading(self._state.title_id, self._state.source_id, self._state.ordinal):
                self.update_state_error("Got null.")

            code = ydl.download([self._video.url])

            if code != 0:
                raise RuntimeError(f"Got non-zero code from ydl: {code}.")

            if not videos.loaded(self._state.title_id, self._state.source_id, self._state.ordinal):
                self.update_state_error("Got null.")

    def update_state_error(self, msg: str = ""):
        raise RuntimeError(
            f"Failed to update state of video {self._state.title_id}:{self._state.source_id}:{self._state.ordinal}. " + msg)

    def _create_opts(self):
        return {
            "http_headers": self._video.headers,
            "socket_timeout": self._socket_timeout,
            "logger": self._logger,
            "progress_hooks": [self._state_hook],
            "concurrent_fragment_downloads": 0,
            "outtmpl": str(self._state.output_file.resolve()),
            "merge_output_format": self._state.output_format,
            "format": "bv*+ba/b"
        }

    def _state_hook(self, d: dict):
        with self._state.write:
            if "_percent" in d:
                self._state.progress = float(d["_percent"]) / 100
            if "_speed_str" in d:
                self._state.speed = d["_speed_str"]
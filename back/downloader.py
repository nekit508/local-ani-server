"""Очередь загрузок. Файлы — источник правды, задачи — временные записи.

Модуль знает только `config`, `db`/`models` и `library`; ссылки получает через
инжектированный `resolver(anime, dub, episode, quality) -> (url, headers) | None`,
поэтому про anicli и FastAPI ничего не знает.

Статусы задачи:

    queued -> running -> done     (soft delete, reason="done")
                      -> failed   (живёт в БД)
                      -> paused   (по кнопке, .part сохраняется)
    удаление -> soft delete, reason="deleted"

Soft-deleted строки нужны только для диффа: FIFO-лимит 100, полная чистка —
на старте/остановке (epoch меняется).
"""

import asyncio
import glob
import json
import shutil
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

import db
from config import settings
from library import Library, library, sanitize
from models import DownloadTask, EpisodeIndex

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    from yt_dlp.utils import DownloadCancelled as _YtCancelled
except Exception:
    class _YtCancelled(Exception):
        pass


EPOCH = uuid.uuid4().hex
SOFT_DELETE_LIMIT = 100
INDEX_TOMBSTONE_LIMIT = 500

QUEUED = "queued"
RUNNING = "running"
PAUSED = "paused"
FAILED = "failed"
DONE = "done"

ACTIVE_STATUSES = (QUEUED, RUNNING, PAUSED)
REASON_DONE = "done"
REASON_DELETED = "deleted"

Resolver = Callable[[str, str, str, int, int | None], "tuple[str, dict[str, str]] | None"]


class _Aborted(_YtCancelled):
    """Прерывание скачивания (пауза/удаление/остановка)."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _now_rev() -> int:
    return int(time.time() * 1000)


def _short_error(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text.splitlines()[0][:500]


@asynccontextmanager
async def _session():
    async for session in db.get_session():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _set(task: "_Task", field: str, value: Any) -> None:
    with task.lock:
        task.progress[field] = value


class _Task:
    def __init__(
        self,
        *,
        id: int,
        data_source: str,
        title: str,
        anime: str,
        dub: str,
        episode: int,
        quality: int | None,
        status: str = QUEUED,
        rev: int = 0,
        attempts: int = 0,
        error: str | None = None,
        auto_retry: bool = False,
        resume_partial: bool = False,
    ) -> None:
        self.id = id
        self.data_source = data_source
        self.title = title
        self.anime = anime
        self.dub = dub
        self.episode = episode
        self.quality = quality
        self.status = status
        self.rev = rev
        self.attempts = attempts
        self.error = error
        self.auto_retry = auto_retry
        self.resume_partial = resume_partial

        self.abort = threading.Event()
        self.abort_reason: str | None = None
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.progress: dict[str, Any] = {
            "phase": None, "downloaded": 0, "total": 0, "speed": None,
            "eta": None, "fragments_done": None, "fragments_total": None, "percent": 0.0,
        }

    def request_abort(self, reason: str) -> None:
        with self.lock:
            self.abort_reason = reason
        self.abort.set()

    def progress_snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.progress)

    def reset_for_queue(self) -> None:
        self.abort = threading.Event()
        self.abort_reason = None
        self.error = None
        self.attempts = 0
        self.status = QUEUED
        with self.lock:
            self.process = None
            self.progress.update(
                phase=None, downloaded=0, total=0, speed=None, eta=None,
                fragments_done=None, fragments_total=None, percent=0.0,
            )


class _Worker:
    def __init__(self, index: int, downloader: "Downloader") -> None:
        self.index = index
        self._downloader = downloader
        self._lock = threading.RLock()
        self._current: _Task | None = None
        self._state = "idle"
        self._rev = _now_rev()

    def bind(self, task: _Task | None, state: str) -> None:
        with self._lock:
            self._current = task
            self._state = state
            self._rev = max(_now_rev(), self._rev + 1)

    def state(self) -> str:
        with self._lock:
            return self._state

    def rev(self) -> int:
        with self._lock:
            task_rev = self._current.rev if self._current is not None else 0
            return max(self._rev, task_rev)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            task = self._current
            state = self._state
            rev = max(self._rev, task.rev if task is not None else 0)
        progress = None
        if task is not None:
            progress = {
                "task_id": task.id, "anime": task.anime, "dub": task.dub,
                "episode": task.episode, "status": task.status,
                **task.progress_snapshot(),
            }
        return {
            "index": self.index,
            "state": state,
            "task_id": task.id if task is not None else None,
            "rev": rev,
            "progress": progress,
        }

    async def run(self) -> None:
        while True:
            task_id = await self._downloader._queue.get()
            if task_id is None:
                self.bind(None, "stopped")
                return

            task = self._downloader._tasks.get(task_id)
            if task is None:
                task = await self._downloader._load(task_id)
            if task is None or task.status != QUEUED or task.abort.is_set():
                continue

            self.bind(task, "busy")
            try:
                await self._downloader._process(task)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._downloader._fail(task, _short_error(exc))
            finally:
                self.bind(None, "idle")


class Downloader:
    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        download_dir: str | Path | None = None,
        workers: int | None = None,
        verify: str | None = None,
        max_attempts: int | None = None,
        retry_delay: float | None = None,
        progress_interval: float | None = None,
        socket_timeout: float | None = None,
        extractor_retries: int | None = None,
        fragment_concurrency: int | None = None,
    ) -> None:
        self.resolver = resolver
        self.library: Library = Library(download_dir) if download_dir is not None else library
        self.workers_count = max(1, int(workers if workers is not None else settings.DOWNLOAD_WORKERS))
        self.verify = verify if verify is not None else settings.DOWNLOAD_VERIFY
        self.max_attempts = max(1, int(max_attempts if max_attempts is not None else settings.DOWNLOAD_MAX_ATTEMPTS))
        self.retry_delay = retry_delay if retry_delay is not None else settings.DOWNLOAD_RETRY_DELAY
        self.progress_interval = progress_interval if progress_interval is not None else settings.DOWNLOAD_PROGRESS_INTERVAL
        self.socket_timeout = socket_timeout if socket_timeout is not None else settings.DOWNLOAD_SOCKET_TIMEOUT
        self.extractor_retries = extractor_retries if extractor_retries is not None else settings.DOWNLOAD_EXTRACTOR_RETRIES
        self.fragment_concurrency = max(
            1,
            int(fragment_concurrency if fragment_concurrency is not None else settings.DOWNLOAD_FRAGMENT_CONCURRENCY),
        )

        self._lock = threading.RLock()
        self._tasks: dict[int, _Task] = {}
        self._active: dict[int, _Task] = {}
        self._queue: asyncio.Queue[int | None] = asyncio.Queue()
        self._workers: list[_Worker] = []
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._flush_task: asyncio.Task[None] | None = None
        self._started = False
        self._stopping = False

    # ------------------------------------------------------------------ life

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        self.library.root.mkdir(parents=True, exist_ok=True)
        self._queue = asyncio.Queue()
        self._started = True
        self._stopping = False

        await self._purge_soft_deleted(all_rows=True)
        await self._sync_index()
        await self._requeue_interrupted()
        await self._enqueue_pending()

        self._workers = [_Worker(index, self) for index in range(self.workers_count)]
        self._worker_tasks = [
            asyncio.create_task(worker.run(), name=f"downloader-worker-{worker.index}")
            for worker in self._workers
        ]
        self._flush_task = asyncio.create_task(self._flush_loop(), name="downloader-progress")

    async def stop(self, timeout: float = 30.0) -> None:
        if not self._started:
            return
        self._stopping = True

        with self._lock:
            active = list(self._active.values())
        for task in active:
            task.request_abort("stop")

        if self._flush_task is not None:
            self._flush_task.cancel()
            self._flush_task = None
        for _ in self._workers:
            self._queue.put_nowait(None)

        if self._worker_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._worker_tasks, return_exceptions=True), timeout
                )
            except asyncio.TimeoutError:
                for worker_task in self._worker_tasks:
                    worker_task.cancel()
                await asyncio.gather(*self._worker_tasks, return_exceptions=True)

        self._worker_tasks.clear()
        self._workers.clear()
        await self._requeue_interrupted()
        await self._purge_soft_deleted(all_rows=True)
        self._started = False
        self._stopping = False

    def workers(self) -> list[_Worker]:
        return list(self._workers)

    def queue_size(self) -> int:
        return self._queue.qsize()

    # ---------------------------------------------------------------- submit

    async def submit(
        self,
        data_source: str,
        title: str,
        dub: str,
        episode: int,
        *,
        quality: int | None = None,
        auto_retry: bool = False,
        created_by: int | None = None,
    ) -> tuple[str, int | None]:
        """('created'|'exists'|'active', task_id)."""
        if not self._started:
            raise RuntimeError("downloader is not started")

        anime = sanitize(title)
        dub = sanitize(dub)
        if self.library.exists(anime, dub, episode):
            return "exists", None

        active_id = await self._find_active(anime, dub, episode)
        if active_id is not None:
            return "active", active_id

        rev = _now_rev()
        try:
            async with _session() as session:
                row = DownloadTask(
                    data_source=data_source, title=title, anime=anime,
                    dub=dub, episode=episode, quality=quality,
                    status=QUEUED, rev=rev, auto_retry=auto_retry, created_by=created_by,
                )
                session.add(row)
                await session.flush()
                task_id = int(row.id)
        except IntegrityError:
            existing = await self._find_active(anime, dub, episode)
            return "active", existing

        task = _Task(
            id=task_id, data_source=data_source, title=title, anime=anime,
            dub=dub, episode=episode, quality=quality, rev=rev,
            auto_retry=auto_retry,
        )
        with self._lock:
            self._tasks[task_id] = task
        self._queue.put_nowait(task_id)
        return "created", task_id

    # ----------------------------------------------------------------- views

    async def tasks_since(self, since: int = 0) -> dict[str, Any]:
        stmt = select(DownloadTask).where(DownloadTask.rev >= since).order_by(DownloadTask.id)
        async with _session() as session:
            rows = (await session.execute(stmt)).scalars().all()

        updated: list[dict[str, Any]] = []
        rev = since
        for row in rows:
            item = self._row_dict(row)
            task = self._tasks.get(row.id)
            if task is not None:
                item["rev"] = max(item["rev"], task.rev)
                item["progress"] = task.progress_snapshot()
            else:
                item["progress"] = None
            rev = max(rev, item["rev"])
            updated.append(item)

        return {"epoch": EPOCH, "rev": rev, "updated": updated, "removed": []}

    def workers_state(self, since: int = 0) -> dict[str, Any]:
        snapshots = [worker.snapshot() for worker in self._workers]
        updated = [item for item in snapshots if item["rev"] >= since]
        rev = max((item["rev"] for item in updated), default=since)
        return {"epoch": EPOCH, "rev": rev, "updated": updated, "removed": []}

    async def matrix(self, anime: str, since: int = 0) -> dict[str, Any]:
        anime_key = sanitize(anime)
        async with _session() as session:
            index_rows = (await session.execute(
                select(EpisodeIndex).where(
                    EpisodeIndex.anime == anime_key,
                    EpisodeIndex.rev >= since,
                ).order_by(EpisodeIndex.dub, EpisodeIndex.episode)
            )).scalars().all()
            task_rows = (await session.execute(
                select(DownloadTask).where(
                    DownloadTask.anime == anime_key,
                    DownloadTask.deleted_at.is_(None),
                    DownloadTask.rev >= since,
                )
            )).scalars().all()

        tasks_by_key = {(row.dub, row.episode): row for row in task_rows}
        seen: set[tuple[str, int]] = set()
        updated: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        rev = since

        for row in index_rows:
            key = (row.dub, row.episode)
            seen.add(key)
            if row.deleted_at is not None:
                removed.append({
                    "anime": row.anime, "dub": row.dub,
                    "episode": row.episode, "rev": row.rev,
                })
                rev = max(rev, row.rev)
                continue

            task_row = tasks_by_key.get(key)
            task_info = self._task_info(task_row) if task_row is not None else None
            item_rev = max(row.rev, task_info["rev"] if task_info else 0)
            updated.append({
                "anime": row.anime, "dub": row.dub, "episode": row.episode,
                "exists": True, "ext": row.ext, "rev": item_rev, "task": task_info,
            })
            rev = max(rev, item_rev)

        for row in task_rows:
            key = (row.dub, row.episode)
            if key in seen:
                continue
            task_info = self._task_info(row)
            updated.append({
                "anime": row.anime, "dub": row.dub, "episode": row.episode,
                "exists": False, "ext": None, "rev": task_info["rev"],
                "task": task_info,
            })
            rev = max(rev, task_info["rev"])

        return {"epoch": EPOCH, "rev": rev, "updated": updated, "removed": removed}

    # --------------------------------------------------------------- control

    async def pause(self, task_id: int) -> bool:
        task = self._tasks.get(task_id) or await self._load(task_id)
        if task is None or task.status not in ACTIVE_STATUSES:
            return False

        if task.status == QUEUED:
            task.status = PAUSED
            await self._db_update(task_id, status=PAUSED, rev=self._bump(task))
            return True

        task.request_abort("pause")
        return True

    async def resume(self, task_id: int) -> bool:
        task = self._tasks.get(task_id) or await self._load(task_id)
        if task is None or task.status != PAUSED:
            return False

        task.reset_for_queue()
        task.resume_partial = True
        with self._lock:
            self._tasks[task_id] = task
        await self._db_update(task_id, status=QUEUED, rev=self._bump(task), error=None, attempts=0)
        self._queue.put_nowait(task_id)
        return True

    async def retry(self, task_id: int) -> bool:
        task = self._tasks.get(task_id) or await self._load(task_id)
        if task is None or task.status != FAILED:
            return False

        task.reset_for_queue()
        task.resume_partial = False
        await self._db_update(task_id, status=QUEUED, rev=self._bump(task), error=None, attempts=0)
        self._queue.put_nowait(task_id)
        return True

    async def delete(self, task_id: int) -> bool:
        async with _session() as session:
            row = await session.get(DownloadTask, task_id)
        if row is None or row.deleted_at is not None:
            return False

        task = self._tasks.get(task_id)
        if task is not None:
            task.request_abort("delete")
        await self._db_update(
            task_id, status=row.status, deleted_at=_utcnow(),
            deleted_reason=REASON_DELETED, rev=_now_rev(),
        )
        with self._lock:
            self._tasks.pop(task_id, None)
        await self._cleanup_soft_deleted()
        return True

    # --------------------------------------------------------------- worker

    async def _process(self, task: _Task) -> None:
        with self._lock:
            self._active[task.id] = task
        task.status = RUNNING
        task.started_at = task.started_at or _utcnow()
        task.rev = self._bump(task)
        await self._db_update(task.id, status=RUNNING, rev=task.rev, started_at=task.started_at)
        _set(task, "phase", "resolve")

        ok = False
        error = ""
        try:
            for attempt in range(1, self.max_attempts + 1):
                if task.abort.is_set() or self._stopping:
                    break
                task.attempts = attempt
                resolved = await self._resolve(task)
                if resolved is None:
                    error = "не удалось получить ссылку"
                    if attempt < self.max_attempts:
                        await self._sleep(task)
                    continue

                url, headers = resolved
                _set(task, "phase", "download")
                try:
                    ok, error = await asyncio.to_thread(self._download, task, url, headers)
                except _Aborted:
                    ok, error = False, "прервано"
                    break
                if ok or task.abort.is_set() or self._stopping:
                    break
                if attempt < self.max_attempts:
                    await self._sleep(task)

            if ok and not task.abort.is_set():
                _set(task, "phase", "verify")
                message = ""
                path = self._find_output(task)
                if path is None:
                    ok, error = False, "файл не найден после скачивания"
                else:
                    try:
                        ok, message = await asyncio.to_thread(self._verify, task, path)
                    except _Aborted:
                        ok, error = False, "прервано"
                    else:
                        if not ok:
                            error = message
        finally:
            with self._lock:
                self._active.pop(task.id, None)

        if task.abort.is_set():
            await self._handle_abort(task)
            return
        if self._stopping:
            task.status = QUEUED
            await self._db_update(task.id, status=QUEUED, rev=self._bump(task))
            return
        if ok:
            await self._complete(task)
            return
        await self._fail(task, error or "неизвестная ошибка")

    async def _resolve(self, task: _Task) -> tuple[str, dict[str, str]] | None:
        if self.resolver is None:
            return None
        try:
            return await asyncio.to_thread(
                self.resolver, task.data_source, task.title,
                task.dub, task.episode, task.quality,
            )
        except Exception:
            return None

    async def _handle_abort(self, task: _Task) -> None:
        reason = task.abort_reason
        if reason == "pause":
            task.status = PAUSED
            await self._db_update(task.id, status=PAUSED, rev=self._bump(task))
        elif reason == "delete":
            self._cleanup_files(task)  # не оставляем недокачанный/готовый файл
        else:
            task.status = QUEUED
            await self._db_update(task.id, status=QUEUED, rev=self._bump(task))

    async def _complete(self, task: _Task) -> None:
        path = self._find_output(task)
        if path is None:
            await self._fail(task, "файл не найден после скачивания")
            return

        ext = path.suffix.lstrip(".").lower() or "mp4"
        size = path.stat().st_size
        with task.lock:
            task.progress.update(
                downloaded=size, total=size, percent=100.0, speed=None, eta=0, phase=None,
            )
        task.finished_at = _utcnow()
        await self._index_file(task, ext)
        await self._db_update(
            task.id, status=DONE, finished_at=task.finished_at,
            deleted_at=_utcnow(), deleted_reason=REASON_DONE,
            rev=self._bump(task), error=None,
        )
        with self._lock:
            self._tasks.pop(task.id, None)
        await self._cleanup_soft_deleted()

    async def _fail(self, task: _Task, error: str) -> None:
        task.error = error
        if task.auto_retry and not self._stopping and not task.abort.is_set():
            task.reset_for_queue()
            await self._db_update(
                task.id, status=QUEUED, rev=self._bump(task), error=error, attempts=0,
            )
            await asyncio.sleep(min(1.0, max(0.0, self.retry_delay)))
            self._queue.put_nowait(task.id)
            return

        task.status = FAILED
        self._cleanup_files(task)
        await self._db_update(
            task.id, status=FAILED, rev=self._bump(task),
            error=error, finished_at=_utcnow(),
        )

    async def _sleep(self, task: _Task) -> None:
        deadline = time.monotonic() + max(0.0, self.retry_delay)
        while time.monotonic() < deadline:
            if task.abort.is_set() or self._stopping:
                return
            await asyncio.sleep(min(0.25, max(0.0, deadline - time.monotonic())))

    # ------------------------------------------------------------- download

    def _download(self, task: _Task, url: str, headers: dict[str, str] | None) -> tuple[bool, str]:
        if yt_dlp is None:
            return False, "yt-dlp не установлен"

        target = self.library.target(task.anime, task.dub, task.episode)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not task.resume_partial:
            self._cleanup_files(task)

        params: dict[str, Any] = {
            "outtmpl": self.library.template(task.anime, task.dub, task.episode),
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "retries": 20,
            "fragment_retries": 20,
            "extractor_retries": self.extractor_retries,
            "socket_timeout": self.socket_timeout,
            "skip_unavailable_fragments": False,
            "concurrent_fragment_downloads": self.fragment_concurrency,
            "continuedl": True,
            "http_chunk_size": 10 * 1024 * 1024,
            "progress_hooks": [lambda data: self._progress_hook(task, data)],
        }
        if headers:
            params["http_headers"] = dict(headers)

        try:
            with yt_dlp.YoutubeDL(params) as ydl:
                ydl.download([url])
        except _Aborted:
            raise
        except Exception as exc:
            if task.abort.is_set():
                raise _Aborted() from exc
            return False, _short_error(exc)

        return True, "ok"

    def _progress_hook(self, task: _Task, data: dict[str, Any]) -> None:
        if task.abort.is_set():
            raise _Aborted()

        status = data.get("status")
        with task.lock:
            progress = task.progress
            if status == "downloading":
                progress["phase"] = "download"
                progress["downloaded"] = int(data.get("downloaded_bytes") or 0)
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                if total:
                    progress["total"] = int(total)
                if progress["total"]:
                    progress["percent"] = round(progress["downloaded"] * 100 / progress["total"], 1)
                progress["speed"] = data.get("speed")
                progress["eta"] = data.get("eta")
                progress["fragments_done"] = data.get("fragment_index")
                progress["fragments_total"] = data.get("fragment_count")
            elif status == "finished":
                progress["phase"] = "verify"
                progress["speed"] = None
                progress["eta"] = 0

    def _output_pattern(self, task: _Task) -> str:
        base = self.library.target(task.anime, task.dub, task.episode)
        return base.with_suffix(".*").as_posix()

    def _find_output(self, task: _Task) -> Path | None:
        matches = [
            Path(name) for name in glob.glob(self._output_pattern(task))
            if not name.endswith(".part")
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (item.suffix.lower() != ".mp4", item.name))
        return matches[0]

    def _cleanup_files(self, task: _Task) -> None:
        for name in glob.glob(self._output_pattern(task)):
            try:
                Path(name).unlink()
            except OSError:
                pass

    # --------------------------------------------------------------- verify

    def _verify(self, task: _Task, path: Path) -> tuple[bool, str]:
        if self.verify == "off":
            return True, "ok"
        if not path.exists():
            return False, "файл отсутствует"
        if shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None:
            return False, "ffmpeg/ffprobe не найдены"

        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
                 "-of", "json", str(path)],
                capture_output=True, text=True, timeout=120,
            )
            info = json.loads(result.stdout or "{}")
        except Exception as exc:
            return False, f"ffprobe: {_short_error(exc)}"

        video = audio = None
        for stream in info.get("streams", []):
            try:
                duration = float(stream.get("duration")) if stream.get("duration") else None
            except (TypeError, ValueError):
                duration = None
            if not duration:
                continue
            if stream.get("codec_type") == "video" and video is None:
                video = duration
            elif stream.get("codec_type") == "audio" and audio is None:
                audio = duration

        if video and audio and abs(video - audio) > 1.0:
            return False, f"A/V рассинхрон: video={video:.2f}s audio={audio:.2f}s"

        if self.verify == "full":
            return self._full_decode(task, path)
        return True, "ok"

    def _full_decode(self, task: _Task, path: Path) -> tuple[bool, str]:
        process = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        with task.lock:
            task.process = process
        try:
            while process.poll() is None:
                if task.abort.is_set():
                    process.terminate()
                    try:
                        process.wait(5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise _Aborted()
                time.sleep(0.2)
        finally:
            with task.lock:
                task.process = None

        stderr = process.stderr.read() if process.stderr is not None else ""
        if process.returncode != 0 or stderr.strip():
            first = (stderr.strip().splitlines() or ["unknown"])[0]
            return False, f"битые кадры/поток: {first}"
        return True, "ok"

    # ------------------------------------------------------------------- db

    @staticmethod
    def _row_dict(row: DownloadTask) -> dict[str, Any]:
        return {
            "task_id": row.id,
            "data_source": row.data_source,
            "title": row.title,
            "anime": row.anime,
            "dub": row.dub,
            "episode": row.episode,
            "quality": row.quality,
            "status": row.status,
            "rev": row.rev or 0,
            "attempts": row.attempts or 0,
            "auto_retry": bool(row.auto_retry),
            "error": row.error,
            "deleted": row.deleted_at is not None,
            "deleted_reason": row.deleted_reason,
            "created_at": row.created_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
        }

    def _task_info(self, row: DownloadTask) -> dict[str, Any]:
        task = self._tasks.get(row.id)
        percent = 0.0
        if task is not None:
            percent = task.progress_snapshot().get("percent", 0.0)
        return {
            "task_id": row.id, "title": row.title, "status": row.status,
            "rev": max(row.rev, task.rev if task is not None else 0),
            "percent": percent, "attempts": row.attempts or 0,
        }

    def _bump(self, task: _Task) -> int:
        with task.lock:
            task.rev = max(_now_rev(), task.rev + 1)
            return task.rev

    async def _db_update(self, task_id: int, **values: Any) -> None:
        values["updated_at"] = _utcnow()
        async with _session() as session:
            await session.execute(
                update(DownloadTask).where(DownloadTask.id == task_id).values(**values)
            )

    async def _find_active(self, anime: str, dub: str, episode: int) -> int | None:
        stmt = (
            select(DownloadTask.id)
            .where(
                DownloadTask.anime == anime,
                DownloadTask.dub == dub,
                DownloadTask.episode == episode,
                DownloadTask.deleted_at.is_(None),
            )
            .limit(1)
        )
        async with _session() as session:
            return (await session.execute(stmt)).scalar_one_or_none()

    async def _load(self, task_id: int) -> _Task | None:
        async with _session() as session:
            row = await session.get(DownloadTask, task_id)
        if row is None or row.deleted_at is not None:
            return None
        task = _Task(
            id=row.id, data_source=row.data_source, title=row.title,
            anime=row.anime, dub=row.dub, episode=row.episode,
            quality=row.quality, status=row.status, rev=row.rev or 0,
            attempts=row.attempts or 0, error=row.error,
            auto_retry=bool(row.auto_retry),
            resume_partial=(row.attempts or 0) > 0,
        )
        with self._lock:
            return self._tasks.setdefault(task_id, task)

    async def _requeue_interrupted(self) -> None:
        async with _session() as session:
            rows = (await session.execute(
                select(DownloadTask.id).where(
                    DownloadTask.status == RUNNING,
                    DownloadTask.deleted_at.is_(None),
                )
            )).scalars().all()
            if rows:
                await session.execute(
                    update(DownloadTask)
                    .where(DownloadTask.id.in_(rows))
                    .values(status=QUEUED, rev=_now_rev(), updated_at=_utcnow())
                )

    async def _enqueue_pending(self) -> None:
        async with _session() as session:
            rows = (await session.execute(
                select(DownloadTask.id).where(
                    DownloadTask.status == QUEUED,
                    DownloadTask.deleted_at.is_(None),
                ).order_by(DownloadTask.id)
            )).scalars().all()
        for task_id in rows:
            self._queue.put_nowait(int(task_id))

    async def _purge_soft_deleted(self, *, all_rows: bool) -> None:
        async with _session() as session:
            if all_rows:
                await session.execute(delete(DownloadTask).where(DownloadTask.deleted_at.is_not(None)))
            old = (await session.execute(
                select(EpisodeIndex.id)
                .where(EpisodeIndex.deleted_at.is_not(None))
                .order_by(EpisodeIndex.id.desc())
                .offset(INDEX_TOMBSTONE_LIMIT)
            )).scalars().all()
            if old:
                await session.execute(delete(EpisodeIndex).where(EpisodeIndex.id.in_(old)))

    async def _cleanup_soft_deleted(self) -> None:
        async with _session() as session:
            old = (await session.execute(
                select(DownloadTask.id)
                .where(DownloadTask.deleted_at.is_not(None))
                .order_by(DownloadTask.id.desc())
                .offset(SOFT_DELETE_LIMIT)
            )).scalars().all()
            if old:
                await session.execute(delete(DownloadTask).where(DownloadTask.id.in_(old)))

    # ---------------------------------------------------------------- index

    async def _index_file(self, task: _Task, ext: str) -> None:
        rev = max(_now_rev(), task.rev + 1)
        task.rev = rev
        async with _session() as session:
            row = (await session.execute(
                select(EpisodeIndex).where(
                    EpisodeIndex.anime == task.anime,
                    EpisodeIndex.dub == task.dub,
                    EpisodeIndex.episode == task.episode,
                )
            )).scalar_one_or_none()
            if row is None:
                session.add(EpisodeIndex(
                    anime=task.anime, dub=task.dub, episode=task.episode,
                    ext=ext, rev=rev,
                ))
            else:
                row.ext = ext
                row.rev = rev
                row.deleted_at = None
                row.updated_at = _utcnow()

    async def forget_episode(self, anime: str, dub: str, episode: int) -> None:
        """Tombstone в индексе: файла больше нет (для диффа матрицы)."""
        rev = _now_rev()
        async with _session() as session:
            row = (await session.execute(
                select(EpisodeIndex).where(
                    EpisodeIndex.anime == anime,
                    EpisodeIndex.dub == dub,
                    EpisodeIndex.episode == episode,
                )
            )).scalar_one_or_none()
            if row is None:
                session.add(EpisodeIndex(
                    anime=anime, dub=dub, episode=episode, ext="mp4",
                    rev=rev, deleted_at=_utcnow(),
                ))
            else:
                row.rev = rev
                row.deleted_at = _utcnow()
                row.updated_at = _utcnow()
        await self._purge_soft_deleted(all_rows=False)

    async def _sync_index(self) -> None:
        entries = self.library.scan()
        on_disk = {(entry.anime, entry.dub, entry.episode): entry for entry in entries}
        rev = _now_rev()

        async with _session() as session:
            rows = (await session.execute(select(EpisodeIndex))).scalars().all()
            known = {(row.anime, row.dub, row.episode): row for row in rows}

            for key, entry in on_disk.items():
                row = known.get(key)
                if row is None:
                    session.add(EpisodeIndex(
                        anime=key[0], dub=key[1], episode=key[2],
                        ext=entry.ext, rev=rev,
                    ))
                elif row.deleted_at is not None or row.ext != entry.ext:
                    row.ext = entry.ext
                    row.deleted_at = None
                    row.rev = rev
                    row.updated_at = _utcnow()

            for key, row in known.items():
                if key in on_disk or row.deleted_at is not None:
                    continue
                row.deleted_at = _utcnow()
                row.rev = rev
                row.updated_at = _utcnow()

    # ---------------------------------------------------------------- flush

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self.progress_interval)
            with self._lock:
                active = list(self._active.values())
            if not active:
                continue
            try:
                async with _session() as session:
                    for task in active:
                        rev = self._bump(task)
                        await session.execute(
                            update(DownloadTask)
                            .where(DownloadTask.id == task.id)
                            .values(rev=rev, updated_at=_utcnow())
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                continue


if __name__ == "__main__":
    print("epoch:", EPOCH)

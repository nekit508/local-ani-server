import importlib
import pkgutil
import threading
import time as _time
from functools import lru_cache
from typing import Any

import anicli_api.player
import anicli_api.source as sources_pkg
from anicli_api.base import BaseExtractor, BaseAnime, BaseSource
from anicli_api.player.base import Video, BaseVideoExtractor, ABCVideoExtractor
from httpx import Timeout

from misc import single_call

# Extractor[one per list entry] -(search)> Anime[search results] -> Episode[number] ->
# -> BaseSource[dubbing] -(video extractor)> Video[quality]

@single_call
def video_extractors() -> list[BaseVideoExtractor]:
    ABCVideoExtractor.DEFAULT_CLIENT_CONFIG["timeout"] = Timeout(40)
    return list(decoder() for decoder in anicli_api.player.ALL_DECODERS)


_PLAYER_PRIORITY = {"mp4": 2, "webm": 1, "m3u8": 0}

# имена декодеров в нижнем регистре; приводим к «человеческому» виду
_PLAYER_NAMES = {"csstonline": "csst"}


def resolve_decoder(video_url: str) -> BaseVideoExtractor | None:
    """Первый декодер, чей URL_RULE матчит ссылку (как в BaseSource.get_videos)."""
    for decoder in video_extractors():
        if decoder._compare_url(video_url):
            return decoder
    return None


def player_name(decoder: BaseVideoExtractor) -> str:
    name = type(decoder).__name__.lower()
    return _PLAYER_NAMES.get(name, name)


def player_of(video_url: str) -> str | None:
    """Имя плеера для ссылки; None — ссылка не от известного декодера."""
    decoder = resolve_decoder(video_url)
    if decoder is not None:
        return player_name(decoder)
    # CdnVideoHub отдаёт не страницу плеера, а iframe; декодер по URL его не ловит.
    if "/iframeCVH.html?" in (video_url or "") or "cdnvideohub" in (video_url or ""):
        return "cdnvideohub"
    return None


def best_video(
    videos: list[Video] | None,
    *,
    quality: int | None = None,
) -> Video | None:
    """Лучшее доступное качество, но не выше `quality` (если задано).

    None — если ни один вариант не попадает под границу.
    """
    if not videos:
        return None

    candidates = list(videos)
    if quality is not None:
        limit = int(quality)
        candidates = [video for video in candidates if int(video.quality or 0) <= limit]
        if not candidates:
            return None

    def rank(video: Video) -> tuple[int, int]:
        return int(video.quality or 0), _PLAYER_PRIORITY.get(video.type, 1)

    return max(candidates, key=rank)


def resolve_url(video_url: str) -> list[Video] | None:
    """Декодирует страницу плеера в прямые ссылки. None — плеер не опознан."""
    decoder = resolve_decoder(video_url)
    if decoder is None:
        return None

    name = player_name(decoder)
    try:
        return decoder.parse(video_url)
    except Exception as s:
        raise Exception(f"{name} failed to parse {video_url} due to {s}") from s


def extract_url(source: BaseSource) -> list[Video] | None:
    return resolve_url(source.url)


# --------------------------------------------------------------- резолв видео

_ANIME_TTL = 300.0
_VIDEO_TTL = 30.0
_anime_cache: dict[tuple[str, str], tuple[float, Any]] = {}
_episodes_cache: dict[tuple[str, str], tuple[float, list]] = {}
_video_cache: dict[tuple[str, str, str, int, int | None], tuple[float, Video | None]] = {}
_cache_lock = threading.Lock()


def anime_of(data_source: str, title: str):
    """Аниме по (источник, тайтл) с TTL-кэшем — поиск в источнике дорогой."""
    key = (data_source, title)
    now = _time.monotonic()
    with _cache_lock:
        cached = _anime_cache.get(key)
        if cached and now - cached[0] < _ANIME_TTL:
            return cached[1]

    extractor = as_extractor(data_source)
    if extractor is None:
        raise LookupError(f"unknown data source: {data_source}")
    anime = get(extractor, title)
    if anime is None:
        raise LookupError(f"anime not found: {title}")

    with _cache_lock:
        _anime_cache[key] = (now, anime)
    return anime


def episodes_of(data_source: str, title: str) -> list:
    key = (data_source, title)
    now = _time.monotonic()
    with _cache_lock:
        cached = _episodes_cache.get(key)
        if cached and now - cached[0] < _ANIME_TTL:
            return cached[1]

    anime = anime_of(data_source, title)
    episodes = list(anime.get_episodes())
    with _cache_lock:
        _episodes_cache[key] = (now, episodes)
    return episodes


def sources_of(episode, dub: str) -> list[BaseSource]:
    key = (dub or "").strip().lower()
    return [
        source for source in episode.get_sources()
        if (source.title or "").strip().lower() == key
    ]


def _clip(source: BaseSource, quality: int | None) -> Video | None:
    try:
        return best_video(list(source.get_videos()), quality=quality)
    except Exception:
        return None


def resolve_video(
    data_source: str,
    title: str,
    dub: str,
    episode: int,
    quality: int | None = None,
) -> tuple[str, dict[str, str]] | None:
    """Прямая ссылка для задачи: перебирает плееры озвучки, берёт первый рабочий."""
    key = (data_source, title, (dub or "").strip().lower(), int(episode), quality)
    now = _time.monotonic()
    with _cache_lock:
        cached = _video_cache.get(key)
        if cached and now - cached[0] < _VIDEO_TTL:
            video = cached[1]
            return (video.url, dict(video.headers)) if video is not None else None

    video = None
    try:
        for item in episodes_of(data_source, title):
            if item.ordinal != int(episode):
                continue
            for source in sources_of(item, dub):
                video = _clip(source, quality)
                if video is not None:
                    break
            break
    except Exception:
        video = None

    with _cache_lock:
        _video_cache[key] = (now, video)
    return (video.url, dict(video.headers)) if video is not None else None


@single_call
def extractors_list() -> list[str]:
    return list(m.name for m in pkgutil.iter_modules(sources_pkg.__path__))


@lru_cache
def as_extractor(source: str) -> BaseExtractor | None:
    if source not in extractors_list():
        return None
    module = importlib.import_module(f"{sources_pkg.__name__}.{source}")
    return getattr(module, "Extractor")()


def search(extractor: BaseExtractor, query: str) -> list[BaseAnime]:
    return list(s.get_anime() for s in extractor.search(query=query))


def get(extractor: BaseExtractor, title: str) -> BaseAnime | None:
    out = search(extractor, title)
    for s in out:
        if s.title == title:
            return s
    return None


if __name__ == "__main__":
    l = list(e.get_sources() for e in search(as_extractor(extractors_list()[8]), "april")[0].get_episodes())
    print(len(l))

    u = extract_url(l[0][0])

    print(u)

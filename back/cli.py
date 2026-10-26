import importlib
import pkgutil
from enum import Enum
from threading import RLock

import anicli_api.player
import anicli_api.source as sources_pkg
from anicli_api.base import BaseExtractor, BaseAnime, BaseSource
from anicli_api.player.base import Video, BaseVideoExtractor, ABCVideoExtractor
from httpx import Timeout
from yt_dlp.utils import sanitize_path


class UnknownExtractor(Exception):
    extractor: str
    def __init__(self, extractor: str):
        super().__init__(extractor)
        self.extractor = extractor


class UnknownVideoExtractor(Exception):
    video_extractor: str
    def __init__(self, video_extractor: str):
        super().__init__(video_extractor)
        self.video_extractor = video_extractor


class TargetQuality(int, Enum):
    Q144 = 144
    Q240 = 240
    Q360 = 360
    Q480 = 480
    Q720 = 720
    Q1080 = 1080
    Q2160 = 2160


class QualityPolicy(str, Enum):
    BEST_LESS = "<"
    WORST_GREATER = ">"


class VideoURLProvider:
    source: BaseSource
    title: str
    source_title: str
    ordinal: int
    q_target: TargetQuality
    q_policy: QualityPolicy

    _possible_qualities: list[int] = [144, 240, 360, 480, 720, 1080, 2160]
    _lock: RLock = RLock()

    def __init__(self, title: str, source_title: str, ordinal: int, source: BaseSource, q_target: TargetQuality, q_policy: QualityPolicy):
        self.title = title
        self.source_title = source_title
        self.ordinal = ordinal
        self.source = source
        self.q_target = q_target
        self.q_policy = q_policy

    def __call__(self, *args, **kwargs) -> Video|None:
        with self._lock:
            return self._select_quality(list(self.source.get_videos()), self.q_target, self.q_policy)

    def _select_quality(self, videos: list[Video], target: TargetQuality, policy: QualityPolicy) -> Video|None:
        ind = self._possible_qualities.index(target)
        qualities = self._possible_qualities[ind::-1] if policy == QualityPolicy.BEST_LESS else self._possible_qualities[ind::]

        for q in qualities:
            for video in videos:
                if video.quality == q:
                    return video

        return None


class CLI:
    video_extractors: dict[str, BaseVideoExtractor]
    video_extractors_names: set[str]

    extractors: dict[str, BaseExtractor]
    extractors_names: set[str]

    _possible_qualities: list[int]

    def __init__(self):
        self.video_extractors = {}
        self.extractors = {}


        self._init()

    def _init(self):
        self._init_extractors()
        self._init_video_extractors()

    def _init_extractors(self):
        self.extractors_names = set(m.name for m in pkgutil.iter_modules(sources_pkg.__path__) if not m.ispkg)

        self.extractors = {extractor_name: getattr(importlib.import_module(f"{sources_pkg.__name__}.{extractor_name}"), "Extractor")() for
                           extractor_name in self.extractors_names}

    def _init_video_extractors(self):
        ABCVideoExtractor.DEFAULT_CLIENT_CONFIG["timeout"] = Timeout(40)
        self.video_extractors = {decoder.__name__.lower(): decoder() for decoder in anicli_api.player.ALL_DECODERS}
        self.video_extractors_names = set(self.video_extractors.keys())

    def search(self, extractor: str, query: str) -> list[BaseAnime]:
        if extractor not in self.extractors_names:
            raise UnknownExtractor(extractor)

        return list(s.get_anime() for s in self.extractors[extractor].search(query))

    def search_exact(self, extractor: str, query: str) -> BaseAnime|None:
        _ = self.search(extractor, query)
        for a in _:
            if a.title == query:
                return a
        return None

    def get_url_providers(self, extractor: str, title: str, source_title: str, episodes_ords: list[int],
                          q_target: TargetQuality, q_policy: QualityPolicy) -> list[tuple[int, VideoURLProvider|None]]|None:
        anime = self.search_exact(extractor, title)

        if anime is None:
            return None

        anime_episodes = anime.get_episodes()

        return list((episode_ord, VideoURLProvider(sanitize_path(title), sanitize_path(source_title), episode_ord, source, q_target, q_policy))
                    for episode_ord in episodes_ords for source in anime_episodes[episode_ord-1].get_sources() if source.title == source_title)
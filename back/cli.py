import importlib
import pkgutil
from functools import lru_cache

import anicli_api.player
import anicli_api.source as sources_pkg
from anicli_api.base import BaseExtractor, BaseAnime, BaseSource
from anicli_api.player.base import Video, BaseVideoExtractor, ABCVideoExtractor
from httpx import Timeout

from back.misc import single_call

# Extractor[one per list entry] -(search)> Anime[search results] -> Episode[number] ->
# -> BaseSource[dubbing] -(video extractor)> Video[quality]

@single_call
def video_extractors() -> list[BaseVideoExtractor]:
    ABCVideoExtractor.DEFAULT_CLIENT_CONFIG["timeout"] = Timeout(40)
    return list(decoder() for decoder in anicli_api.player.ALL_DECODERS)


def extract_url(source: BaseSource) -> list[Video] | None:
    video_url = source.url
    decs = video_extractors()
    for decoder in decs:
        name = type(decoder).__name__.lower()
        if name in video_url:
            try:
                return decoder.parse(video_url)
            except Exception as s:
                raise Exception(f"{name} failed to parse {video_url} due to {s}")
    return None


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

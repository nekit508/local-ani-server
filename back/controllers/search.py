from fastapi import APIRouter, Depends, Query, HTTPException
from starlette import status

from back.controllers import auth
from back.lib.cli import cli
from back.lib.misc import local_cache, LocalCache
from back.services.encoder import encoder
from back.services.videos import videos

router = APIRouter(prefix="/back/search", tags=["api"], dependencies=[Depends(auth.auth_token)])

@local_cache
def _anime_encode_source_title_(title: str) -> int:
    return encoder.encode(title)

@router.get("/extractors")
def extractors_():
    return list({"name": name} for name in cli.extractors_names)

@router.get("/")
def search_(
        extractor: str = Query(alias="extractor"),
        query: str = Query(alias="query")
):
    searched = cli.search(extractor, query)

    with encoder.with_session as session:
        return list({
                        "id": encoder.encode(anime.title, session=session),
                        "title": anime.title,
                        "thumbnail_url": anime.thumbnail
                    } for anime in searched)

@router.get("/anime")
def anime_(
        extractor: str = Query(alias="extractor"),
        title_id: int = Query(alias="id")
):
    with _anime_encode_source_title_ as func:
        encode: LocalCache[str, int] = func
        with encoder.with_session as session:
            title = encoder.decode(title_id, session=session)

            if title is None:
                return HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Unknown title id {title_id}"
                )

            anime, episodes = cli.search_exact_and_get_episodes(extractor, title)

            if anime is None:
                return HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Title {title} not found in {extractor}"
                )

            existing_videos = videos.all(title_id)
            print(f"existing_videos of {title}({title_id}): {existing_videos}")

            episodes = [{
                "title": episode.title,
                "ordinal": episode.ordinal,
                "sources": list({
                                    "loaded": (episode.ordinal, encode(source.title)) in existing_videos,
                                    "id": encode(source.title),
                                    "title": source.title
                                } for source in episode.get_sources())
            } for episode in episodes ]

            return {
                "id": title_id,
                "title": anime.title,
                "thumbnail_url": anime.thumbnail,
                "description": anime.description,
                "episodes": episodes
            }
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status

import auth, cli
from misc import select

router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(auth.auth_token)])

@router.get("/data_sources")
def _data_sources() -> list[str]:
    return cli.extractors_list()

@router.get("/search")
def _search(
        source: str = Query(),
        query: str = Query()
):
    extractor = cli.as_extractor(source)
    if extractor is None:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="invalid source"
        )
    founded = cli.search(extractor, query)
    return list(select(f, {"title", "thumbnail"}) for f in founded)

@router.get("/anime")
def _anime(
        title: str = Query(),
        source: str = Query()
):
    extractor = cli.as_extractor(source)
    if extractor is None:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="invalid source"
        )

    anime = cli.get(extractor, title)
    if anime is None:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="invalid title"
        )

    episodes = list({"title": episode.title, "ordinal": episode.ordinal, "sources": list({"title": source.title, "url": source.url} for source in episode.get_sources())} for episode in anime.get_episodes())

    return {
        "title": anime.title,
        "description": anime.description,
        "thumbnail": anime.thumbnail,
        "episodes": episodes
    }

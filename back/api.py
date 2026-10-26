from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from starlette import status
from starlette.responses import Response

import auth, cli
from back.config import settings
from back.downloader import DownloadTask
from back.executor import Executor, WorkerState
from back.scheme import ApiDownloadIn
from misc import select

router = APIRouter(prefix="/back/api", tags=["api"], dependencies=[Depends(auth.auth_token)])
_cli = cli.CLI()

_executor = Executor()
for _ in range(settings.WORKERS_NUM):
    _executor.start_worker()

@router.get("/data_sources")
def _data_sources() -> list[str]:
    return list(_cli.extractors_names)

@router.get("/search")
def _search(
        source: str = Query(),
        query: str = Query()
):
    try:
        return list(select(f, ["title", "thumbnail"]) for f in _cli.search(source, query))
    except cli.UnknownExtractor as e:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"invalid source {e.extractor}"
        )

@router.get("/anime")
def _anime(
        title: str = Query(),
        source: str = Query()
):
    try:
        anime = _cli.search_exact(source, title)

        if anime is None:
            return HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Title {title} not found in {source}"
            )

        episodes = list({"title": episode.title, "ordinal": episode.ordinal, "sources": list({"title": source.title, "url": source.url} for source in episode.get_sources())} for episode in anime.get_episodes())

        return {
            "title": anime.title,
            "description": anime.description,
            "thumbnail": anime.thumbnail,
            "episodes": episodes
        }
    except cli.UnknownExtractor as e:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"invalid source {e.extractor}"
        )

@router.post("/download")
def _download(
        body: ApiDownloadIn = Body()
):
    try:
        providers = _cli.get_url_providers(body.extractor, body.title, body.source_title, body.ordinals, body.q_target, body.q_policy)

        if providers is None:
            return HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Title {body.title} not found in {body.extractor}"
            )

        failed: set[int] = set(body.ordinals)

        for ordinal, prov in providers:
            failed.remove(ordinal)
            _executor.submit(DownloadTask(prov))

        return failed
    except cli.UnknownExtractor as e:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"invalid source {e.extractor}"
        )


@router.get("/bucket")
def _bucket(
        name: str = Query(),
        since: int = Query(0)
):
    with _executor.shared_index:
        bucket = _executor.shared_index[name]

        if bucket is None:
            return HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"invalid bucket {name}"
            )
        
        states: list[dict[str, Any]] = []
        for state in bucket:
            with state:
                if state.rev() >= since:
                    states.append(state.serialise())

    return states

@router.get("/worker/restart")
def _worker_restart(
        _id: int = Query(alias="id")
):
    state = _executor.shared_index[_id]

    if state is None or not isinstance(state, WorkerState):
        return Response(status_code=404)

    w_state: WorkerState = state
    with w_state:
        if w_state.working:
            return Response(status_code=406)
        w_state.start()

    return Response(status_code=200)
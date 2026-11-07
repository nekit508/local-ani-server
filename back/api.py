from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from starlette import status
from starlette.responses import Response

import auth
import cli
from back.config import settings
from back.new_downloader import DownloadTask
from back.new_executor import Executor, StateSnapshot, WorkerState, Worker
from back.scheme import ApiDownloadIn
from misc import select

router = APIRouter(prefix="/back/api", tags=["api"], dependencies=[Depends(auth.auth_token)])
_cli = cli.CLI()

_executor = Executor()
for _ in range(settings.EXECUTOR_WORKERS_NUM):
    _executor.spawn_worker()


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
            _executor.submit_task(DownloadTask(
                _executor,
                f"{body.title} - {body.source_title} Ep. {ordinal}",
                prov,
                Path(Path(settings.DOWNLOAD_DIR) / body.title / body.source_title / str(ordinal))
            ))

        return failed
    except cli.UnknownExtractor as e:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"invalid source {e.extractor}"
        )


@router.get("/tasks")
def _tasks(
        since: int = Query(0)
):
    with _executor.tasks_states.read as snapshots:
        snapshots: dict[int, StateSnapshot]
        return list(state.dict for state in snapshots.values() if state.rev >= since)


@router.get("/workers")
def _workers(
        since: int = Query(0)
):
    with _executor.workers_states.read as snapshots:
        snapshots: dict[int, StateSnapshot]
        return list(state.dict for state in snapshots.values() if state.rev >= since)

@router.get("/worker/{wid}/start")
def _start_worker(
        wid: int
):
    with _executor.workers_states.read as snapshots:
        snapshots: dict[int, StateSnapshot[WorkerState]]
        if wid not in snapshots:
            return HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invalid worker id {wid}"
            )

        snapshot = snapshots[wid]
        if snapshot.state.phase.working or snapshot.state.phase.alive:
            return HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail=f"Worker already running"
            )

    snapshot.state.owner.start()

    return Response(status_code=200)


@router.get("/worker/{wid}/stop")
def _stop_worker(
        wid: int
):
    with _executor.workers_states.read as snapshots:
        snapshots: dict[int, StateSnapshot[WorkerState]]
        if wid not in snapshots:
            return HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invalid worker id {wid}"
            )

        snapshot = snapshots[wid]
        if not (snapshot.state.phase.working or snapshot.state.phase.alive):
            return HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail=f"Worker is not running"
            )

    snapshot.state.owner.submit(Worker.STOP)

    return Response(status_code=200)
import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status

import auth, cli
from downloader import Downloader
from library import sanitize
from misc import select
from scheme import TaskStartIn

router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(auth.auth_token)])

# Один экземпляр на процесс; стартует/останавливается в lifespan (main.py).
# Ссылки загрузчик берёт через cli.resolve_video — сам про anicli не знает.
downloader = Downloader(resolver=cli.resolve_video)


def _source_payload(item) -> dict:
    player = cli.player_of(item.url)
    return {
        "title": f"{item.title} - {player}" if player else item.title,
        "dub": sanitize(item.title),
    }


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
        raise HTTPException(
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="invalid source"
        )

    anime = cli.get(extractor, title)
    if anime is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="invalid title"
        )

    episodes = [
        {
            "title": episode.title,
            "ordinal": episode.ordinal,
            "sources": [_source_payload(item) for item in episode.get_sources()],
        }
        for episode in anime.get_episodes()
    ]

    return {
        "title": anime.title,
        "description": anime.description,
        "thumbnail": anime.thumbnail,
        "episodes": episodes,
    }


# -------------------------------------------------------------------- tasks

@router.post("/tasks")
async def _tasks_start(
        payload: TaskStartIn,
        user: auth.User = Depends(auth.get_user),
) -> dict:
    try:
        episodes = await asyncio.to_thread(cli.episodes_of, payload.data_source, payload.title)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    by_ordinal = {episode.ordinal: episode for episode in episodes}
    created: dict[str, int | None] = {}
    exists: list[int] = []
    active: dict[str, int | None] = {}
    errors: dict[str, str] = {}

    for ordinal in payload.episodes:
        key = str(ordinal)
        if ordinal not in by_ordinal:
            errors[key] = "эпизод не найден"
            continue

        video = await asyncio.to_thread(
            cli.resolve_video, payload.data_source, payload.title,
            payload.dub, ordinal, payload.quality,
        )
        if video is None:
            errors[key] = "нет ссылки: озвучка/плеер не отдали видео"
            continue

        state, task_id = await downloader.submit(
            payload.data_source, payload.title, payload.dub, ordinal,
            quality=payload.quality, created_by=user.id,
        )
        if state == "created":
            created[key] = task_id
        elif state == "exists":
            exists.append(ordinal)
        else:
            active[key] = task_id

    return {"created": created, "exists": exists, "active": active, "errors": errors}


@router.get("/tasks")
async def _tasks(since: int = Query(0, ge=0)) -> dict:
    return await downloader.tasks_since(since)


@router.post("/tasks/{task_id}/pause")
async def _tasks_pause(task_id: int) -> dict:
    return {"paused": await downloader.pause(task_id)}


@router.post("/tasks/{task_id}/resume")
async def _tasks_resume(task_id: int) -> dict:
    return {"resumed": await downloader.resume(task_id)}


@router.post("/tasks/{task_id}/retry")
async def _tasks_retry(task_id: int) -> dict:
    return {"retried": await downloader.retry(task_id)}


@router.delete("/tasks/{task_id}")
async def _tasks_delete(task_id: int) -> dict:
    return {"deleted": await downloader.delete(task_id)}


@router.get("/workers")
def _workers(since: int = Query(0, ge=0)) -> dict:
    return downloader.workers_state(since)


@router.get("/matrix")
async def _matrix(
        anime: str = Query(),
        since: int = Query(0, ge=0),
) -> dict:
    return await downloader.matrix(anime, since)


# -------------------------------------------------------------------- files

@router.get("/files")
def _files(path: str = Query("", max_length=1024)) -> dict:
    root = downloader.library.root.resolve()
    target = (root / path).resolve() if path else root
    if not target.is_relative_to(root) or not target.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="directory not found")

    items: list[dict] = []
    for entry in target.iterdir():
        try:
            resolved = entry.resolve()
            if not resolved.is_relative_to(root):
                continue
            stat = entry.stat()
        except OSError:
            continue
        is_dir = entry.is_dir()
        items.append({
            "name": entry.name,
            "type": "dir" if is_dir else "file",
            "size": None if is_dir else stat.st_size,
            "mtime": stat.st_mtime,
            "path": str(entry.relative_to(root)),
        })

    items.sort(key=lambda item: (item["type"] != "dir", item["name"].lower()))

    return {
        "root": str(root),
        "path": "" if target == root else str(target.relative_to(root)),
        "parent": None if target == root else (
            "" if target.parent == root else str(target.parent.relative_to(root))
        ),
        "items": items,
    }


@router.delete("/files")
async def _files_delete(path: str = Query(..., min_length=1, max_length=1024)) -> dict:
    root = downloader.library.root.resolve()
    target = (root / path).resolve()
    if target == root or not target.is_relative_to(root):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

    if target.is_dir():
        try:
            target.rmdir()
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"directory is not empty: {exc}",
            ) from exc
        return {"removed": True, "type": "dir"}

    if not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

    entry = downloader.library.entry(target)
    try:
        target.unlink()
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if entry is not None:
        await downloader.forget_episode(entry.anime, entry.dub, entry.episode)
    downloader.library._prune_empty(target.parent)

    return {"removed": True, "type": "file"}

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status
from starlette.responses import Response

import back.controllers.auth as auth
from back.config import settings
from back.lib.executor import Executor, StateSnapshot, WorkerState, Worker

router = APIRouter(prefix="/back/api", tags=["api"], dependencies=[Depends(auth.get_user)])

# TODO replace executor somewhere in services/lib
# used in videos api for now
executor = Executor()
for _ in range(settings.EXECUTOR_WORKERS_NUM):
    executor.spawn_worker()


@router.get("/tasks")
def _tasks(
        since: int = Query(0)
):
    with executor.tasks_states.read as snapshots:
        snapshots: dict[int, StateSnapshot]
        return list(state.dict for state in snapshots.values() if state.rev >= since)


@router.get("/workers")
def _workers(
        since: int = Query(0)
):
    with executor.workers_states.read as snapshots:
        snapshots: dict[int, StateSnapshot]
        return list(state.dict for state in snapshots.values() if state.rev >= since)

@router.get("/worker/{wid}/start")
def _start_worker(
        wid: int
):
    with executor.workers_states.read as snapshots:
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
    with executor.workers_states.read as snapshots:
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
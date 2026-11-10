from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session

from back.controllers import auth
from back.controllers.api import executor
from back.lib.cli import cli
from back.lib.downloader import DownloadTask
from back.scheme import VideosDownloadIn
from back.services.encoder import encoder

router = APIRouter(prefix="/back/videos", tags=["api"], dependencies=[Depends(auth.get_user)])

@router.post("/download")
def download_(
        body: VideosDownloadIn = Body()
):
    # group by title -> source -> ordinal

    # TODO response with failed items info, but for now - nothing
    failed_titles: list[int] = []
    failed_sources: list[tuple[int, int]] = []
    failed_episodes: list[tuple[int, int, int]] = []

    matrix: dict[int, dict[int, list[int]]] = {}

    for target in body.targets:
        if target.title not in matrix:
            matrix[target.title] = {}

        source_lists = matrix[target.title]

        if target.source not in source_lists:
            source_lists[target.source] = []

        source_lists[target.source].append(target.ordinal)

    with encoder.with_session as session:
        session: Session

        for title, source_lists in matrix.items():
            title_str = encoder.decode(title, session=session)

            if title_str is None:
                failed_titles.append(title)
                continue

            for source, list_ in source_lists.items():
                source_str = encoder.decode(source, session=session)

                if source_str is None:
                    failed_sources.append((title, source))
                    continue

                res = cli.get_url_providers(body.extractor, title_str, source_str, list_, body.q_target, body.q_policy)

                if res is None:
                    continue

                for episode, provider in res:
                    if provider is None:
                        failed_episodes.append((title, source, episode))
                        continue

                    executor.submit_task(DownloadTask(
                        executor,
                        f"{title_str} - {source_str} Ep.{str(episode)}",
                        provider,
                        title, source, episode
                    ))

    return {
        "failed_titles": failed_titles,
        "failed_sources": failed_sources,
        "failed_episodes": failed_episodes
    }
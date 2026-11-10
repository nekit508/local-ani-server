from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

import back.databases
from back.lib.db import auto_session


class Videos:
    auto_videos_session = auto_session(back.databases.videos.with_session)

    @property
    @contextmanager
    def with_session(self):
        with back.databases.videos.with_session():
            yield

    @auto_videos_session
    def all(self, title: int, session: Session = None) -> set[tuple[int, int]]:
        return set(*session.execute(
            select(
                back.databases.Video.ordinal,
                back.databases.Video.source_id
            )
            .where(back.databases.Video.title_id == title)
        ).all())

    @auto_videos_session
    def list(self, title: int, source: int, session: Session = None) -> set[int]:
        return set(*session.execute(
            select(back.databases.Video.ordinal)
            .where(
                back.databases.Video.title_id == title,
                back.databases.Video.source_id == source
            )
        ).all())


videos = Videos()
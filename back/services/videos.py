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
    def by_fully_qualified(self, title: int, source: int, ordinal: int, session: Session = None) -> back.databases.Video | None:
        return session.scalar(select(back.databases.Video).where(
            back.databases.Video.title_id == title,
            back.databases.Video.source_id == source,
            back.databases.Video.ordinal == ordinal
        ))

    @auto_videos_session
    def set_state_of(self, title: int, source: int, ordinal: int, state: back.databases.VideoState, session: Session = None) -> bool:
        video = self.by_fully_qualified(title, source, ordinal, session=session)

        if video is None:
            return False

        video.state = state

        return True

    @auto_videos_session
    def try_create(self, title: int, source: int, ordinal: int, session: Session = None) -> bool:
        res = self.by_fully_qualified(title, source, ordinal, session=session)

        if res is not None:
            return False

        video = back.databases.Video()

        video.title_id = title
        video.source_id = source
        video.ordinal = ordinal

        session.add(video)

        return True

    @auto_videos_session
    def loading(self, title: int, source: int, ordinal: int, session: Session = None) -> bool:
        return self.set_state_of(title, source, ordinal, back.databases.VideoState.loading, session=session)

    @auto_videos_session
    def loading(self, title: int, source: int, ordinal: int, session: Session = None) -> bool:
        return self.set_state_of(title, source, ordinal, back.databases.VideoState.loading, session=session)

    @auto_videos_session
    def loaded(self, title: int, source: int, ordinal: int, session: Session = None) -> bool:
        return self.set_state_of(title, source, ordinal, back.databases.VideoState.loaded, session=session)

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
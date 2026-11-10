import datetime
from contextlib import ExitStack, contextmanager
from enum import Enum

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from back.lib.db import DB

main = DB(".db/main")
encoding = DB(".db/encoding")
videos = DB(".db/videos")

@contextmanager
def lifespan():
    # noinspection PyAbstractClass
    with ExitStack() as stack:
        for db in [main, encoding, videos]:
            stack.enter_context(db.lifespan())
        yield

class User(main.Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    cv: Mapped[int] = mapped_column(default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.now()
    )


class Encoding(encoding.Base):
    __tablename__ = "encoding"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, index=True)


class VideoState(str, Enum):
    unknown = "unknown"
    loading = "loading"
    loaded = "loaded"


class Video(videos.Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(index=True)
    source_id: Mapped[int] = mapped_column(index=True)
    ordinal: Mapped[int] = mapped_column(index=True)
    state: Mapped[VideoState] = mapped_column(default=VideoState.unknown)

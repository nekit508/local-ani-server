import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Progress(Base):
    __tablename__ = "progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    video_id: Mapped[str] = mapped_column(String(255), index=True)
    position: Mapped[float] = mapped_column(default=0.0)
    duration: Mapped[float] = mapped_column(default=0.0)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )


class DownloadTask(Base):
    """Временная задача загрузки. Истина — файл на диске.

    Живут только активные (queued/running/paused) и проваленные; завершённые
    и удалённые помечаются `deleted_at` + `deleted_reason` и удаляются FIFO.
    """

    __tablename__ = "download_tasks"
    __table_args__ = (
        Index(
            "uq_download_task_active",
            "anime", "dub", "episode",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    data_source: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    anime: Mapped[str] = mapped_column(String(255), index=True)
    dub: Mapped[str] = mapped_column(String(255), index=True)
    episode: Mapped[int] = mapped_column(Integer, index=True)
    quality: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    rev: Mapped[int] = mapped_column(Integer, default=0, index=True)
    auto_retry: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)

    created_by: Mapped[int | None] = mapped_column(Integer, default=None, nullable=True)
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None, nullable=True, index=True)
    deleted_reason: Mapped[str | None] = mapped_column(String(16), default=None, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None, nullable=True)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )


class EpisodeIndex(Base):
    """Бухгалтерия файлов для диффа матрицы: что есть/было и когда менялось."""

    __tablename__ = "episode_index"
    __table_args__ = (
        UniqueConstraint("anime", "dub", "episode", name="uq_episode_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    anime: Mapped[str] = mapped_column(String(255), index=True)
    dub: Mapped[str] = mapped_column(String(255), index=True)
    episode: Mapped[int] = mapped_column(Integer)
    ext: Mapped[str] = mapped_column(String(8))
    rev: Mapped[int] = mapped_column(Integer, default=0, index=True)
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=None, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    cv: Mapped[int] = mapped_column(default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

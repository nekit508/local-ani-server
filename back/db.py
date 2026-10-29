from typing import TYPE_CHECKING

from back.config import settings

if TYPE_CHECKING:
    from typing import Any, Generator
    from sqlalchemy.orm import Session

from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base

engine = create_engine(f"sqlite:///./{settings.DB_FILE}", echo=False, future=True, connect_args={"check_same_thread": False})

session_factory = sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def get_session() -> "Generator[Session, Any]":
    with session_factory() as s:
        try:
            yield s
        except Exception:
            s.rollback()
            raise


@contextmanager
def get_session_cm():
    yield from get_session()


@contextmanager
def lifespan(app):
    Base.metadata.create_all(engine)
    yield
    engine.dispose()

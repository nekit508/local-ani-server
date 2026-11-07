from contextlib import contextmanager, _GeneratorContextManager
from typing import Any, Generator, Callable

from sqlalchemy import create_engine, Engine, event
from sqlalchemy.orm import scoped_session, sessionmaker, Session, DeclarativeBase


def create_db(file: str) -> tuple[
    Engine,
    Callable[[], Generator[Session, Any, None]],
    Callable[[], _GeneratorContextManager[Session]],
    type[DeclarativeBase],
    Callable[[Any, Any], _GeneratorContextManager[Any]]
]:
    engine = create_engine(
        f"sqlite:///{file}",
        connect_args={
            "check_same_thread": False
        }
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    session_factory = scoped_session(sessionmaker(bind=engine))

    def gen_session() -> Generator[Session, Any, None]:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.remove()

    with_session: Callable[[], _GeneratorContextManager[Session]] = contextmanager(gen_session)

    class Base(DeclarativeBase):
        pass

    @contextmanager
    def lifespan():
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    # noinspection PyTypeChecker
    return engine, gen_session, with_session, Base, lifespan


class DB:
    def __init__(self, file: str):
        self.engine, self.gen_session, self.with_session, self.Base, self.lifespan = create_db(file)
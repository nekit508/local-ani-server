from typing import TYPE_CHECKING, Any, AsyncGenerator

from misc import single_call

if TYPE_CHECKING:
    from typing import Any, AsyncGenerator, TYPE_CHECKING, Callable
    from sqlalchemy.ext.asyncio import AsyncSession

# noinspection PyTypeChecker
_get_session: "Callable[[], AsyncGenerator[AsyncSession, Any]]" = None
# noinspection PyTypeChecker
_lifespan: "Callable[[Any], Any]" = None

@single_call
def init(file: str = ".db"):
    global _get_session, _lifespan

    from contextlib import asynccontextmanager

    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from models import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///./{file}", echo=False, future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )


    async def get_session_internal() -> "AsyncGenerator[AsyncSession, Any]":
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def init() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


    async def close() -> None:
        await engine.dispose()


    @asynccontextmanager
    async def lifespan_internal(app):
        await init()
        yield
        await close()


    _get_session, _lifespan = get_session_internal, lifespan_internal

def lifespan(app):
    # noinspection PyCallingNonCallable
    return _lifespan(app)

async def get_session() -> "AsyncGenerator[AsyncSession, Any]":
    # noinspection PyCallingNonCallable
    async for session in _get_session():
        yield session
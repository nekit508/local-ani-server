from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI

import db, auth, api

@asynccontextmanager
async def lifespan(app):
    # noinspection PyAbstractClass
    with ExitStack() as stack:
        stack.enter_context(db.lifespan(app))
        yield

application = FastAPI(title="backend", lifespan=lifespan)

application.include_router(auth.router)
application.include_router(api.router)
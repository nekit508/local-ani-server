from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import db, auth, api

db.init()


@asynccontextmanager
async def lifespan(app):
    async with db.lifespan(app):
        await api.downloader.start()
        try:
            yield
        finally:
            await api.downloader.stop()


app = FastAPI(title="backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(api.router)
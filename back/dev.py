import os

import uvicorn

from back.config import settings

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.BACK_HOST, port=settings.BACK_PORT)
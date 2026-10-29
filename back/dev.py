import uvicorn

from back.config import settings

if __name__ == "__main__":
    uvicorn.run("main:application", host=settings.BACK_HOST, port=settings.BACK_PORT)
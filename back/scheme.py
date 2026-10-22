from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class TaskStartIn(BaseModel):
    data_source: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=512)
    dub: str = Field(min_length=1, max_length=256)
    episodes: list[int] = Field(min_length=1)
    quality: int | None = Field(default=None, ge=0, le=4320)

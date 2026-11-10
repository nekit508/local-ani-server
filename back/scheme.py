from pydantic import BaseModel, Field

from back.lib.cli import TargetQuality, QualityPolicy


class LoginIn(BaseModel):
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class ApiDownloadIn(BaseModel):
    extractor: str
    ordinals: list[int]
    title: str
    source_title: str
    q_target: TargetQuality
    q_policy: QualityPolicy


class VideosDownloadInPart(BaseModel):
    ordinal: int
    title: int
    source: int


class VideosDownloadIn(BaseModel):
    targets: list[VideosDownloadInPart]
    q_target: TargetQuality
    q_policy: QualityPolicy
    extractor: str
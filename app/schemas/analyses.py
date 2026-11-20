from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Source(BaseModel):
    fileId: int
    location: str = Field(min_length=1)


class Step(BaseModel):
    itemId: UUID
    before: str
    after: str
    requiredFields: list[str] = Field(default_factory=list)
    caution: str = ""
    change: Literal["유지", "변경", "신규 확인", "미확인"]
    confirmed: bool
    sources: list[Source]


class Review(BaseModel):
    inputFileIds: list[int] = Field(min_length=1)
    steps: list[Step] = Field(min_length=1)
    share: bool = False

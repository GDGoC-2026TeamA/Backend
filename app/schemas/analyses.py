from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


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


class AnalysisRequest(BaseModel):
    """분석할 자료를 고른다. 생략하면 준비된 자료 전체를 분석한다."""

    fileIds: list[int] | None = Field(default=None, min_length=1)


class ItemPatch(BaseModel):
    after: str | None = None
    confirmed: bool | None = None

    @model_validator(mode="after")
    def has_change(self):
        if self.after is None and self.confirmed is None:
            raise ValueError("after 또는 confirmed 중 하나는 보내야 합니다.")
        return self

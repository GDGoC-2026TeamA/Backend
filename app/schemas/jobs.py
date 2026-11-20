from pydantic import BaseModel, Field

from app.schemas.common import Name, Version

FieldValue = str | int | float | bool | None


class NewJob(Version, Name):
    description: str | None = Field(default=None, max_length=2000)


class DraftRequest(BaseModel):
    fileIds: list[int] = Field(min_length=1)


class FieldReview(BaseModel):
    key: str = Field(min_length=1)
    value: FieldValue
    checked: bool


class DraftReview(BaseModel):
    fields: list[FieldReview] = Field(default_factory=list)
    lastField: str | None = None

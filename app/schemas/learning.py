from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Version


class Selection(Version):
    selectedItemIds: list[UUID] = Field(min_length=1)


class Answers(BaseModel):
    answers: list[int]


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

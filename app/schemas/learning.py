from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Version


class Selection(Version):
    selectedItemIds: list[UUID] = Field(min_length=1)


class Answers(BaseModel):
    answers: list[int]
    # 문항별 선택 이유. 생략하거나 문항 수와 같은 길이로 보낸다.
    reasons: list[str | None] | None = None


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

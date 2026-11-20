from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


from app.schemas.common import Version


class NewCard(Version):
    itemId: UUID
    title: str = Field(min_length=1)


class CardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1)
    overrides: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("수정할 필드를 입력하세요.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("수정할 필드에 null을 사용할 수 없습니다.")
        return self


class CardDetail(BaseModel):
    id: int
    analysis_id: int
    item_id: UUID
    title: str
    overrides: dict[str, JsonValue]
    updated_at: datetime

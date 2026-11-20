"""조회 전용 DTO. psycopg dict_row 결과를 각 모델의 model_validate()로 읽는다."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr


class UserRow(BaseModel):
    id: int
    name: str
    email: str | None
    login_id: str | None
    password_hash: SecretStr | None = Field(exclude=True, repr=False)


class SocialAccountRow(BaseModel):
    user_id: int
    provider: str
    subject: str


class TaskRow(BaseModel):
    id: int
    created_by: int
    name: str
    description: str | None


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    file_id: int = Field(alias="fileId")
    location: str


class AnalysisStep(BaseModel):
    """필수 식별자와 근거를 읽고 업무별 절차 및 입력 필드도 보존한다."""

    model_config = ConfigDict(extra="allow")

    item_id: UUID = Field(alias="itemId")
    sources: list[SourceRef] = Field(default_factory=list)


class AnalysisRow(BaseModel):
    id: int
    task_id: int
    input_file_ids: list[int]
    steps: list[AnalysisStep]
    created_at: datetime
    confirmed_at: datetime | None


class LearningRecordRow(BaseModel):
    id: int
    user_id: int
    task_id: int
    analysis_id: int | None
    kind: Literal["practice", "question"]
    content: dict[str, JsonValue]
    created_at: datetime


class CardRow(BaseModel):
    id: int
    user_id: int
    analysis_id: int
    title: str
    item_id: UUID
    overrides: dict[str, JsonValue]
    updated_at: datetime


class ReviewChanges(BaseModel):
    values: dict[str, JsonValue] = Field(default_factory=dict)
    checked: list[str] = Field(default_factory=list)
    last_field: str | None = Field(default=None, alias="lastField")


class JobRow(BaseModel):
    id: int
    user_id: int
    analysis_id: int
    name: str
    description: str | None
    draft: dict[str, JsonValue] | None
    review_changes: ReviewChanges
    created_at: datetime
    saved_at: datetime | None


class FileRow(BaseModel):
    id: int
    task_id: int | None
    job_id: int | None
    kind: Literal["previous_form", "manual", "screenshot", "job_input"]
    filename: str
    status: Literal["pending", "ready", "failed"]
    created_at: datetime
    archived_at: datetime | None

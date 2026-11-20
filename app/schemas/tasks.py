from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Name


class NewTask(Name):
    workspaceId: int
    description: str = ""


class SampleRequest(BaseModel):
    scenario: Literal["inventory"]

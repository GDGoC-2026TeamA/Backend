from pydantic import BaseModel, Field


class Name(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class Version(BaseModel):
    analysisId: int

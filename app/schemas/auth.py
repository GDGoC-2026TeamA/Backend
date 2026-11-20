from typing import Annotated

from pydantic import BaseModel, Field, SecretStr

from app.schemas.common import Name


Email = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class EmailLogin(BaseModel):
    email: Email
    password: SecretStr


class Login(BaseModel):
    login_id: str
    password: SecretStr


class Signup(Name):
    login_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    email: Email
    password: SecretStr = Field(min_length=8, max_length=256)

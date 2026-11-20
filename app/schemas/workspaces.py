from uuid import UUID

from pydantic import BaseModel


class Invite(BaseModel):
    code: UUID

from uuid import UUID

from pydantic import Field

from app.schemas.common import Version


class NewCard(Version):
    itemId: UUID
    title: str = Field(min_length=1)

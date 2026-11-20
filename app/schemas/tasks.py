from app.schemas.common import Name


class NewTask(Name):
    workspaceId: int
    description: str = ""

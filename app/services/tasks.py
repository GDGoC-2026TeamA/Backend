from typing import Literal

from app.dao import tasks as tasks_dao
from app.schemas.tasks import NewTask
from app.services.access import member


def create_task(data: NewTask, uid, conn):
    member(conn, data.workspaceId, uid)
    return tasks_dao.insert_task(
        conn, data.workspaceId, uid, data.name, data.description
    )


def home(workspaceId: int, filter: Literal["all", "mine", "shared"], uid, conn):
    member(conn, workspaceId, uid)
    rows = tasks_dao.list_visible(conn, uid, workspaceId, filter)
    return {"tasks": rows}

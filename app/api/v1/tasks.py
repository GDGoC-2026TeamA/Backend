from typing import Literal

from fastapi import APIRouter, Depends

from app.api.dependencies import user
from app.database import db
from app.schemas.tasks import NewTask
from app.services import tasks as tasks_service

router = APIRouter()


@router.post("/tasks", status_code=201)
def create_task(data: NewTask, uid=Depends(user), conn=Depends(db)):
    return tasks_service.create_task(data, uid, conn)


@router.get("/home")
def home(
    workspaceId: int,
    filter: Literal["all", "mine", "shared"] = "all",
    uid=Depends(user),
    conn=Depends(db),
):
    return tasks_service.home(workspaceId, filter, uid, conn)


@router.get("/tasks/{tid}")
def task_detail(tid: int, uid=Depends(user), conn=Depends(db)):
    return tasks_service.detail(tid, uid, conn)

from typing import Literal

from app.dao import (
    cards as cards_dao,
    jobs as jobs_dao,
    learning as learning_dao,
    tasks as tasks_dao,
)
from app.schemas.tasks import NewTask
from app.services import materials as materials_service
from app.services.access import member, task_for


def create_task(data: NewTask, uid, conn):
    member(conn, data.workspaceId, uid)
    return tasks_dao.insert_task(
        conn, data.workspaceId, uid, data.name, data.description
    )


def home(workspaceId: int, filter: Literal["all", "mine", "shared"], uid, conn):
    member(conn, workspaceId, uid)
    return {
        "tasks": tasks_dao.list_visible(conn, uid, workspaceId, filter),
        "continueJobs": jobs_dao.list_unfinished_in_space(conn, uid, workspaceId),
        "recentCards": cards_dao.list_recent_in_space(conn, uid, workspaceId),
    }


def learning_status(conn, uid, tid) -> Literal["not_started", "in_progress", "completed"]:
    """답안을 낸 연습이 있으면 completed, 질문·미제출 연습만 있으면 in_progress."""
    progress = learning_dao.task_progress(conn, uid, tid)
    if progress["answered"]:
        return "completed"
    if progress["records"]:
        return "in_progress"
    return "not_started"


def detail(tid: int, uid, conn):
    t = task_for(conn, tid, uid)
    return {
        "id": t["id"],
        "name": t["name"],
        "description": t["description"],
        "workspaceId": t["workspace_id"],
        "isMine": t["created_by"] == uid,
        "sharedAnalysisId": t["shared_analysis_id"],
        "materials": materials_service.list_materials(tid, uid, conn),
        "learningStatus": learning_status(conn, uid, tid),
        "recentJobs": jobs_dao.list_recent_for_task(conn, uid, tid),
    }

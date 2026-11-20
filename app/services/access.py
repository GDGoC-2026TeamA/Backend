from app.dao import (
    analyses as analyses_dao,
    jobs as jobs_dao,
    tasks as tasks_dao,
    workspaces as workspaces_dao,
)
from app.services.errors import ServiceError


def required(row):
    if not row:
        raise ServiceError(404, "접근 가능한 항목이 없습니다.")
    return row


def member(conn, space, uid):
    return required(workspaces_dao.find_membership(conn, space, uid))


def task_for(conn, tid, uid, *, edit=False):
    row = required(tasks_dao.find_accessible(conn, tid, uid))
    if edit and row["created_by"] != uid:
        raise ServiceError(403, "등록자만 수정할 수 있습니다.")
    return row


def version(conn, tid, uid):
    t = task_for(conn, tid, uid)
    row = analyses_dao.latest_visible(
        conn, tid, t["created_by"] == uid, t["shared_analysis_id"]
    )
    if not row:
        raise ServiceError(409, "검토가 완료된 분석이 없습니다.")
    return row


def eligible(step):
    return (
        step.get("confirmed") is True
        and step.get("change") != "미확인"
        and bool(step.get("sources"))
    )


def job_for(conn, jid, uid, *, edit=False):
    """본인 작업만 연다. edit이면 행을 잠그고 최종 저장된 작업은 막는다."""
    row = required(jobs_dao.find_owned(conn, jid, uid, lock=edit))
    if edit and row["saved_at"] is not None:
        raise ServiceError(409, "저장이 끝난 작업은 수정할 수 없습니다.")
    return row

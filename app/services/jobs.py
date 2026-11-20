from app.dao import jobs as jobs_dao
from app.schemas.jobs import NewJob
from app.services.access import version
from app.services.errors import ServiceError


def start_job(tid: int, data: NewJob, uid, conn):
    v = version(conn, tid, uid)
    if v["id"] != data.analysisId:
        raise ServiceError(409, "검토 버전이 변경되었습니다.")
    return jobs_dao.insert_job(conn, uid, v["id"], data.name)


def my_jobs(uid, conn):
    return jobs_dao.list_for_user(conn, uid)

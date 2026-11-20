from fastapi import APIRouter, Depends

from app.api.dependencies import user
from app.database import db
from app.schemas.jobs import NewJob
from app.services import jobs as jobs_service

router = APIRouter()


@router.post("/tasks/{tid}/jobs", status_code=201)
def start_job(tid: int, data: NewJob, uid=Depends(user), conn=Depends(db)):
    return jobs_service.start_job(tid, data, uid, conn)


@router.get("/jobs")
def my_jobs(uid=Depends(user), conn=Depends(db)):
    return jobs_service.my_jobs(uid, conn)

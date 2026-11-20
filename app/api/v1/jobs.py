from fastapi import APIRouter, Depends, File, Response, UploadFile

from app.api.dependencies import user
from app.database import db
from app.schemas.jobs import DraftRequest, DraftReview, NewJob
from app.services import jobs as jobs_service

router = APIRouter()


@router.post("/tasks/{tid}/jobs", status_code=201)
def start_job(tid: int, data: NewJob, uid=Depends(user), conn=Depends(db)):
    return jobs_service.start_job(tid, data, uid, conn)


@router.get("/jobs")
def my_jobs(uid=Depends(user), conn=Depends(db)):
    return jobs_service.my_jobs(uid, conn)


@router.get("/jobs/{jid}")
def job_detail(jid: int, uid=Depends(user), conn=Depends(db)):
    return jobs_service.detail(jid, uid, conn)


@router.post("/jobs/{jid}/files", status_code=201)
def upload_file(
    jid: int, file: UploadFile = File(...), uid=Depends(user), conn=Depends(db)
):
    return jobs_service.upload_file(
        jid,
        uid,
        conn,
        stream=file.file,
        filename=file.filename,
        content_type=file.content_type,
        size=file.size,
    )


@router.delete("/job-files/{fid}", status_code=204)
def delete_file(fid: int, uid=Depends(user), conn=Depends(db)):
    return jobs_service.delete_file(fid, uid, conn)


@router.post("/jobs/{jid}/draft", status_code=201)
def create_draft(jid: int, data: DraftRequest, uid=Depends(user), conn=Depends(db)):
    return jobs_service.create_draft(jid, data, uid, conn)


@router.patch("/jobs/{jid}/draft")
def review_draft(jid: int, data: DraftReview, uid=Depends(user), conn=Depends(db)):
    return jobs_service.review_draft(jid, data, uid, conn)


@router.post("/jobs/{jid}/result")
def save_result(jid: int, uid=Depends(user), conn=Depends(db)):
    return jobs_service.save_result(jid, uid, conn)


@router.get("/jobs/{jid}/result/download")
def download_result(jid: int, uid=Depends(user), conn=Depends(db)):
    disposition, body = jobs_service.download_result(jid, uid, conn)
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )

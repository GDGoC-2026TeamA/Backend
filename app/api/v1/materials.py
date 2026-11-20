from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import user
from app.database import db
from app.schemas.tasks import SampleRequest
from app.services import materials as materials_service

router = APIRouter()


@router.post("/tasks/{tid}/materials", status_code=201)
def upload(
    tid: int,
    kind: Literal["previous_form", "manual", "screenshot"] = Form(...),
    file: UploadFile = File(...),
    uid=Depends(user),
    conn=Depends(db),
):
    return materials_service.upload(
        tid,
        kind,
        uid,
        conn,
        stream=file.file,
        filename=file.filename,
        content_type=file.content_type,
        size=file.size,
    )


@router.post("/tasks/{tid}/sample-materials", status_code=201)
def sample_materials(
    tid: int, data: SampleRequest, uid=Depends(user), conn=Depends(db)
):
    return materials_service.load_samples(tid, data, uid, conn)


@router.get("/tasks/{tid}/materials")
def materials(tid: int, uid=Depends(user), conn=Depends(db)):
    return materials_service.list_materials(tid, uid, conn)


@router.get("/tasks/{tid}/materials/{fid}/download")
def download(tid: int, fid: int, uid=Depends(user), conn=Depends(db)):
    return materials_service.download(tid, fid, uid, conn)


@router.delete("/tasks/{tid}/materials/{fid}", status_code=204)
def archive_file(tid: int, fid: int, uid=Depends(user), conn=Depends(db)):
    return materials_service.archive_file(tid, fid, uid, conn)

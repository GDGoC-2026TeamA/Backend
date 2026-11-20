from fastapi import APIRouter, Depends

from app.api.dependencies import user
from app.database import db
from app.schemas.analyses import Review
from app.schemas.common import Version
from app.services import analyses as analyses_service

router = APIRouter()


@router.post("/tasks/{tid}/analyses")
def analyze(tid: int, uid=Depends(user), conn=Depends(db)):
    return analyses_service.analyze(tid, uid, conn)


@router.post("/tasks/{tid}/reviews", status_code=201)
def review(tid: int, data: Review, uid=Depends(user), conn=Depends(db)):
    return analyses_service.review(tid, data, uid, conn)


@router.delete("/tasks/{tid}/share", status_code=204)
def unshare(tid: int, uid=Depends(user), conn=Depends(db)):
    return analyses_service.unshare(tid, uid, conn)


@router.post("/tasks/{tid}/share")
def share_reviewed(tid: int, data: Version, uid=Depends(user), conn=Depends(db)):
    return analyses_service.share_reviewed(tid, data, uid, conn)

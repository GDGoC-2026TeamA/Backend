from uuid import UUID

from fastapi import APIRouter, Body, Depends

from app.api.dependencies import user
from app.database import db
from app.schemas.analyses import AnalysisRequest, ItemPatch, Review
from app.schemas.common import Version
from app.services import analyses as analyses_service

router = APIRouter()


@router.post("/tasks/{tid}/analyses")
def analyze(
    tid: int,
    data: AnalysisRequest | None = Body(default=None),
    uid=Depends(user),
    conn=Depends(db),
):
    return analyses_service.analyze(tid, data, uid, conn)


@router.get("/analyses/{aid}")
def comparison(aid: int, uid=Depends(user), conn=Depends(db)):
    return analyses_service.comparison(aid, uid, conn)


@router.patch("/analysis-items/{item_id}")
def update_item(item_id: UUID, data: ItemPatch, uid=Depends(user), conn=Depends(db)):
    return analyses_service.update_item(item_id, data, uid, conn)


@router.post("/tasks/{tid}/reviews", status_code=201)
def review(tid: int, data: Review, uid=Depends(user), conn=Depends(db)):
    return analyses_service.review(tid, data, uid, conn)


@router.delete("/tasks/{tid}/share", status_code=204)
def unshare(tid: int, uid=Depends(user), conn=Depends(db)):
    return analyses_service.unshare(tid, uid, conn)


@router.post("/tasks/{tid}/share")
def share_reviewed(tid: int, data: Version, uid=Depends(user), conn=Depends(db)):
    return analyses_service.share_reviewed(tid, data, uid, conn)

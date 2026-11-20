from fastapi import APIRouter, Depends

from app.api.dependencies import user
from app.database import db
from app.schemas.common import Name
from app.schemas.workspaces import Invite
from app.services import workspaces as workspaces_service

router = APIRouter()


@router.get("/workspaces")
def spaces(uid=Depends(user), conn=Depends(db)):
    return workspaces_service.spaces(uid, conn)


@router.post("/workspaces", status_code=201)
def create_space(data: Name, uid=Depends(user), conn=Depends(db)):
    return workspaces_service.create_space(data, uid, conn)


@router.post("/workspaces/join")
def join(data: Invite, uid=Depends(user), conn=Depends(db)):
    return workspaces_service.join(data, uid, conn)


@router.get("/workspaces/{space}/invite")
def invite(space: int, uid=Depends(user), conn=Depends(db)):
    return workspaces_service.invite(space, uid, conn)


@router.delete("/workspaces/{space}/membership", status_code=204)
def leave(space: int, uid=Depends(user), conn=Depends(db)):
    return workspaces_service.leave(space, uid, conn)

from fastapi import APIRouter, Depends

from app.database import db
from app.schemas.auth import Login, Signup
from app.services import auth as auth_service

router = APIRouter()


@router.post("/sessions")
def login(data: Login, conn=Depends(db)):
    return auth_service.login(data, conn)


@router.post("/accounts", status_code=201)
def signup(data: Signup, conn=Depends(db)):
    return auth_service.signup(data, conn)

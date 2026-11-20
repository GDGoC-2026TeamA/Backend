from fastapi import APIRouter, Depends, Request, Response
from starlette.concurrency import run_in_threadpool

from app.dao import auth as auth_dao
from app.database import db
from app.services import auth, social

router = APIRouter(prefix="/sessions/social")


@router.get("/{provider}/start")
async def start(provider: social.Provider, request: Request):
    return await social.begin(request, provider)


def _social_session(conn, provider, subject, name):
    uid = auth_dao.social_user(conn, provider, subject, name)
    return auth.issue_session(conn, uid)


@router.get("/{provider}/callback")
async def callback(
    provider: social.Provider, request: Request, response: Response, conn=Depends(db)
):
    subject, name = await social.identity(request, provider)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return await run_in_threadpool(_social_session, conn, provider, subject, name)

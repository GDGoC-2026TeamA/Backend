from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.dao import auth as auth_dao
from app.database import db
from app.services import auth, social, social_exchange
from app.services.errors import ServiceError

router = APIRouter(prefix="/sessions/social")


@router.get("/{provider}/start")
async def start(
    provider: social.Provider,
    request: Request,
    challenge: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9_-]{43}$")] = None,
):
    options = {"state": social_exchange.browser_state(challenge)} if challenge else {}
    return await social.begin(request, provider, **options)


def _social_session(conn, provider, subject, name):
    uid = auth_dao.social_user(conn, provider, subject, name)
    return auth.issue_session(conn, uid)


@router.get("/{provider}/callback")
async def callback(
    provider: social.Provider, request: Request, response: Response, conn=Depends(db)
):
    challenge = social_exchange.state_challenge(request.query_params.get("state"))
    headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    try:
        subject, name = await social.identity(request, provider)
    except ServiceError:
        if not challenge:
            raise
        return RedirectResponse(
            social_exchange.callback_url() + "#error=login_failed", 303, headers=headers
        )
    if challenge:
        code = await run_in_threadpool(
            social_exchange.create_code, conn, provider, subject, name, challenge
        )
        return RedirectResponse(
            social_exchange.callback_url() + "#code=" + code, 303, headers=headers
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return await run_in_threadpool(_social_session, conn, provider, subject, name)


class Exchange(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    verifier: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


@router.post("/exchange")
def exchange(data: Exchange, response: Response, conn=Depends(db)):
    response.headers["Cache-Control"] = "no-store"
    return social_exchange.exchange_code(conn, data.code, data.verifier)

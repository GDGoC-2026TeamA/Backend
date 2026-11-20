from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import db
from app.services.auth import session_user_id


def user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()), conn=Depends(db)
):
    return session_user_id(conn, credentials.credentials)

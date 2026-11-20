import hashlib
import secrets

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.dao import auth as auth_dao
from app.schemas.auth import Login, Signup
from app.services.errors import ServiceError

hasher = PasswordHasher()


def session_user_id(conn, token: str):
    digest = hashlib.sha256(token.encode()).digest()
    row = auth_dao.session_owner(conn, digest)
    if not row:
        raise ServiceError(401, "다시 로그인하세요.")
    return row["user_id"]


def login(data: Login, conn):
    row = auth_dao.find_by_login(conn, data.login_id)
    if row and row["password_hash"]:
        try:
            hasher.verify(row["password_hash"], data.password.get_secret_value())
        except (VerificationError, InvalidHashError):
            pass
        else:
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).digest()
            auth_dao.delete_expired_sessions(conn, row["id"])
            auth_dao.insert_session(conn, digest, row["id"])
            return {"token": token}
    raise ServiceError(401, "로그인 정보를 확인하세요.")


def signup(data: Signup, conn):
    try:
        return auth_dao.insert_account(
            conn,
            data.name,
            data.login_id,
            data.email,
            hasher.hash(data.password.get_secret_value()),
        )
    except psycopg.errors.UniqueViolation:
        raise ServiceError(409, "이미 등록된 계정입니다.") from None

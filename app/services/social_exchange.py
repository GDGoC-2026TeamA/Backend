import base64
import hashlib
import os
import re
import secrets
from urllib.parse import urlsplit

from app.dao import auth as auth_dao
from app.services.auth import issue_session
from app.services.errors import ServiceError


def callback_url():
    url = os.getenv("SOCIAL_FRONTEND_CALLBACK_URL", "")
    parts = urlsplit(url)
    if (
        not (
            parts.scheme == "https"
            or (parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1"})
        )
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
        or parts.query
    ):
        raise ServiceError(503, "프론트 로그인 콜백 주소를 설정하세요.")
    return url


def browser_state(challenge):
    callback_url()
    return f"web.{challenge}.{secrets.token_urlsafe(32)}"


def state_challenge(state):
    match = re.fullmatch(r"web\.([A-Za-z0-9_-]{43})\.[A-Za-z0-9_-]{43}", state or "")
    return match.group(1) if match else None


def create_code(conn, provider, subject, name, challenge):
    user_id = auth_dao.social_user(conn, provider, subject, name)
    code = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM social_login_codes WHERE expires_at <= now()")
    conn.execute(
        """INSERT INTO social_login_codes(code_hash,challenge,user_id,expires_at)
           VALUES (%s,%s,%s,now()+interval '2 minutes')""",
        (hashlib.sha256(code.encode()).digest(), challenge, user_id),
    )
    return code


def exchange_code(conn, code, verifier):
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    user = conn.execute(
        """DELETE FROM social_login_codes c USING app_users u
           WHERE c.code_hash=%s AND c.challenge=%s AND c.expires_at>now() AND u.id=c.user_id
           RETURNING u.id,u.name,coalesce(u.email,'') AS email""",
        (hashlib.sha256(code.encode()).digest(), challenge),
    ).fetchone()
    if not user:
        raise ServiceError(401, "로그인 요청이 만료됐어요. 다시 시작하세요.")
    return {**issue_session(conn, user["id"]), "user": user}

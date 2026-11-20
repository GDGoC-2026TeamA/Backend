"""
Gemini 요청에 넣을 대화 기록(contents)을 만든다.

조회 순서:
    1. 로컬(프로세스 메모리) 캐시
    2. DB (ai_histories 테이블, DATABASE_URL이 있을 때만)
    3. 둘 다 없으면 기본값(빈 기록)

찾은 기록 뒤에 이번 요청의 user 턴을 붙여 list[dict] 형태로 반환한다.
대화 기록은 보조 기능이므로 DB 오류가 나도 AI 호출을 막지 않고 로컬 캐시만 사용한다.
"""

import logging
import os

import psycopg
from psycopg.rows import DictRow, dict_row

from app.dao import ai_histories as ai_histories_dao

logger = logging.getLogger(__name__)

# session_id -> contents(list[dict]) 형태의 로컬 캐시
_local_history: dict[str, list[dict]] = {}

DEFAULT_HISTORY: list[dict] = []

DB_CONNECT_TIMEOUT = 5  # 초


def _connect() -> psycopg.Connection[DictRow] | None:
    """DB가 설정돼 있으면 autocommit 연결을, 아니면 None을 반환한다."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    # psycopg.connect는 Connection[TupleRow]로 추론되므로 행 타입을 명시한다.
    return psycopg.Connection[DictRow].connect(
        database_url,
        row_factory=dict_row,
        autocommit=True,
        connect_timeout=DB_CONNECT_TIMEOUT,
    )


def _fetch_from_db(session_id: str) -> list[dict] | None:
    try:
        conn = _connect()
        if conn is None:
            return None
        with conn:
            return ai_histories_dao.fetch(conn, session_id)
    except psycopg.Error:
        logger.warning("대화 기록 조회 실패 (session_id=%s)", session_id, exc_info=True)
        return None


def _save_to_db(session_id: str, contents: list[dict]) -> None:
    try:
        conn = _connect()
        if conn is None:
            return
        with conn:
            ai_histories_dao.upsert(conn, session_id, contents)
    except psycopg.Error:
        logger.warning("대화 기록 저장 실패 (session_id=%s)", session_id, exc_info=True)


def _delete_from_db(session_id: str) -> None:
    try:
        conn = _connect()
        if conn is None:
            return
        with conn:
            ai_histories_dao.delete(conn, session_id)
    except psycopg.Error:
        logger.warning("대화 기록 삭제 실패 (session_id=%s)", session_id, exc_info=True)


def _load_history(session_id: str | None) -> list[dict]:
    """로컬 -> DB -> 기본값 순서로 이전 대화 기록을 찾는다."""
    if session_id is None:
        return list(DEFAULT_HISTORY)

    # 1. 로컬 캐시 확인
    local = _local_history.get(session_id)
    if local:
        return list(local)

    # 2. DB 확인
    db_history = _fetch_from_db(session_id)
    if db_history:
        _local_history[session_id] = list(
            db_history
        )  # 다음 요청부터는 로컬에서 바로 사용
        return list(db_history)

    # 3. 기본값
    return list(DEFAULT_HISTORY)


def build_contents(parts: list[dict], session_id: str | None = None) -> list[dict]:
    """이전 기록에 이번 user 턴(parts)을 붙여 Gemini의 contents로 반환한다."""
    history = _load_history(session_id)
    return history + [{"role": "user", "parts": parts}]


def save_turn(session_id: str | None, contents: list[dict], model_text: str) -> None:
    """요청에 사용한 contents와 모델 응답을 기록으로 저장한다."""
    if session_id is None:
        return

    updated = contents + [{"role": "model", "parts": [{"text": model_text}]}]
    _local_history[session_id] = updated
    _save_to_db(session_id, updated)


def clear_history(session_id: str) -> None:
    """세션의 로컬·DB 기록을 삭제한다."""
    _local_history.pop(session_id, None)
    _delete_from_db(session_id)

"""
Gemini 요청에 넣을 대화 기록(contents)을 만든다.

조회 순서:
    1. 로컬(프로세스 메모리) 캐시
    2. DB  (아직 미구현 -> 주석 처리)
    3. 둘 다 없으면 기본값(빈 기록)

찾은 기록 뒤에 이번 요청의 user 턴을 붙여 list[dict] 형태로 반환한다.
"""

# from app.db import fetch_history, save_history  # TODO: DB 구현 후 주석 해제

# session_id -> contents(list[dict]) 형태의 로컬 캐시
_local_history: dict[str, list[dict]] = {}

DEFAULT_HISTORY: list[dict] = []


def _load_history(session_id: str | None) -> list[dict]:
    """로컬 -> DB -> 기본값 순서로 이전 대화 기록을 찾는다."""
    if session_id is None:
        return list(DEFAULT_HISTORY)

    # 1. 로컬 캐시 확인
    local = _local_history.get(session_id)
    if local:
        return list(local)

    # 2. DB 확인 (DB 구현 후 주석 해제)
    # db_history = fetch_history(session_id)
    # if db_history:
    #     _local_history[session_id] = list(db_history)  # 다음 요청부터는 로컬에서 바로 사용
    #     return list(db_history)

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

    # DB 구현 후 주석 해제
    # save_history(session_id, updated)


def clear_history(session_id: str) -> None:
    """세션의 로컬 기록을 삭제한다."""
    _local_history.pop(session_id, None)
    # delete_history(session_id)  # TODO: DB 구현 후 주석 해제

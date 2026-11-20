"""
history.py 로직을 실제 DB 없이 검증한다.

- _connect()를 가짜 연결(FakeConn)로 바꿔 DB 접속을 막는다.
- ai_histories DAO를 메모리 저장소(FakeStore)로 바꿔 조회·저장·삭제 호출을 기록한다.
- DAO 자체는 SQL과 파라미터만 확인한다 (테이블 구조가 확정되면 함께 고친다).
"""

from unittest.mock import MagicMock

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.ai import history
from app.dao import ai_histories as ai_histories_dao


def turn(role: str, text: str) -> dict:
    return {"role": role, "parts": [{"text": text}]}


class FakeConn:
    """with 문으로 쓰이는 연결 흉내. 열림/닫힘 횟수만 기록한다."""

    def __init__(self):
        self.closed = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed += 1
        return False


class FakeStore:
    """ai_histories DAO 대신 쓰는 메모리 저장소."""

    def __init__(self):
        self.rows: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, str]] = []

    def fetch(self, conn, session_id):
        self.calls.append(("fetch", session_id))
        return self.rows.get(session_id)

    def upsert(self, conn, session_id, contents):
        self.calls.append(("upsert", session_id))
        self.rows[session_id] = contents

    def delete(self, conn, session_id):
        self.calls.append(("delete", session_id))
        self.rows.pop(session_id, None)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(history, "_local_history", {})
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture
def conn(monkeypatch):
    fake = FakeConn()
    monkeypatch.setattr(history, "_connect", lambda: fake)
    return fake


@pytest.fixture
def store(monkeypatch, conn):
    fake = FakeStore()
    monkeypatch.setattr(history, "ai_histories_dao", fake)
    return fake


def broken_db(monkeypatch):
    monkeypatch.setattr(
        history, "_connect", MagicMock(side_effect=psycopg.OperationalError("down"))
    )


# ---------- 1. session_id 없음 ----------


def test_no_session_returns_only_current_turn(store):
    contents = history.build_contents([{"text": "hi"}])

    assert contents == [turn("user", "hi")]
    assert store.calls == []


def test_no_session_is_not_saved(store):
    history.save_turn(None, [turn("user", "hi")], "ok")

    assert history._local_history == {}
    assert store.calls == []


# ---------- 2. 조회 순서: 로컬 -> DB -> 기본값 ----------


def test_local_cache_is_used_before_db(store):
    history._local_history["s"] = [turn("user", "로컬")]
    store.rows["s"] = [turn("user", "DB")]

    contents = history.build_contents([{"text": "다음"}], "s")

    assert contents == [turn("user", "로컬"), turn("user", "다음")]
    assert store.calls == []  # 로컬에 있으면 DB를 보지 않는다


def test_db_is_used_when_local_cache_is_empty(store, conn):
    store.rows["s"] = [turn("user", "이전"), turn("model", "답")]

    contents = history.build_contents([{"text": "다음"}], "s")

    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert store.calls == [("fetch", "s")]
    assert conn.closed == 1  # 조회 후 연결을 닫는다


def test_db_result_is_cached_locally(store):
    store.rows["s"] = [turn("user", "이전")]

    history.build_contents([{"text": "1"}], "s")
    history.build_contents([{"text": "2"}], "s")

    assert store.calls == [("fetch", "s")]  # 두 번째는 로컬 캐시에서 읽는다


def test_default_when_nothing_found(store):
    contents = history.build_contents([{"text": "처음"}], "s")

    assert contents == [turn("user", "처음")]
    assert store.calls == [("fetch", "s")]
    assert "s" not in history._local_history


def test_returned_history_does_not_change_cache(store):
    history._local_history["s"] = [turn("user", "원본")]

    contents = history.build_contents([{"text": "추가"}], "s")
    contents.append(turn("model", "밖에서 붙임"))

    assert history._local_history["s"] == [turn("user", "원본")]


# ---------- 3. 저장 / 삭제 ----------


def test_save_turn_appends_model_reply_to_local_and_db(store):
    contents = [turn("user", "질문")]

    history.save_turn("s", contents, '{"reply": "답"}')

    expected = [turn("user", "질문"), turn("model", '{"reply": "답"}')]
    assert history._local_history["s"] == expected
    assert store.rows["s"] == expected
    assert contents == [turn("user", "질문")]  # 넘긴 리스트는 그대로 둔다


def test_conversation_accumulates_over_turns(store):
    for i in range(3):
        contents = history.build_contents([{"text": f"q{i}"}], "s")
        history.save_turn("s", contents, f"a{i}")

    assert [c["role"] for c in store.rows["s"]] == ["user", "model"] * 3


def test_sessions_are_isolated(store):
    history.save_turn("a", [turn("user", "A")], "ra")

    assert history.build_contents([{"text": "B"}], "b") == [turn("user", "B")]


def test_clear_history_removes_local_and_db(store):
    history.save_turn("s", [turn("user", "x")], "y")

    history.clear_history("s")

    assert "s" not in history._local_history
    assert "s" not in store.rows


def test_clear_unknown_session_is_noop(store):
    history.clear_history("없음")

    assert store.calls == [("delete", "없음")]


# ---------- 4. DB 미설정 / 장애 ----------


def test_without_database_url_no_connection_is_made(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(psycopg.Connection, "connect", connect)

    assert history._connect() is None
    history.save_turn("s", [turn("user", "x")], "y")
    assert history.build_contents([{"text": "z"}], "s")[0] == turn("user", "x")
    connect.assert_not_called()


def test_connect_uses_database_url(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(psycopg.Connection, "connect", connect)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")

    history._connect()

    args, kwargs = connect.call_args
    assert args == ("postgresql://fake",)
    assert kwargs["autocommit"] is True
    assert kwargs["row_factory"] is history.dict_row


def test_db_error_on_load_falls_back_to_default(monkeypatch, caplog):
    broken_db(monkeypatch)

    contents = history.build_contents([{"text": "hi"}], "s")

    assert contents == [turn("user", "hi")]
    assert "대화 기록 조회 실패" in caplog.text


def test_db_error_on_save_keeps_local_history(monkeypatch, caplog):
    broken_db(monkeypatch)

    history.save_turn("s", [turn("user", "hi")], "ok")

    assert history._local_history["s"][-1] == turn("model", "ok")
    assert "대화 기록 저장 실패" in caplog.text


def test_db_error_on_clear_still_clears_local(monkeypatch, caplog):
    history._local_history["s"] = [turn("user", "x")]
    broken_db(monkeypatch)

    history.clear_history("s")

    assert "s" not in history._local_history
    assert "대화 기록 삭제 실패" in caplog.text


def test_non_db_errors_are_not_swallowed(monkeypatch, conn):
    store = MagicMock()
    store.fetch.side_effect = TypeError("버그")
    monkeypatch.setattr(history, "ai_histories_dao", store)

    with pytest.raises(TypeError):
        history.build_contents([{"text": "hi"}], "s")


# ---------- 5. DAO: SQL과 파라미터만 확인 ----------


class RecordingConn:
    def __init__(self, row=None):
        self.row = row
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql, params):
        self.executed.append((sql, params))
        cursor = MagicMock()
        cursor.fetchone.return_value = self.row
        return cursor


def test_dao_fetch_returns_contents_or_none():
    rows = [turn("user", "x")]

    assert ai_histories_dao.fetch(RecordingConn({"contents": rows}), "s") == rows
    assert ai_histories_dao.fetch(RecordingConn(None), "s") is None


def test_dao_upsert_wraps_contents_as_jsonb():
    c = RecordingConn()
    rows = [turn("user", "x")]

    ai_histories_dao.upsert(c, "s", rows)

    sql, (sid, payload) = c.executed[0]
    assert "ON CONFLICT (session_id)" in sql
    assert sid == "s"
    assert isinstance(payload, Jsonb)
    assert payload.obj == rows


def test_dao_delete_passes_session_id():
    c = RecordingConn()

    ai_histories_dao.delete(c, "s")

    assert c.executed[0][1] == ("s",)

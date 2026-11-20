import json
import os
from unittest.mock import MagicMock

import psycopg
import pytest
import requests

from app.ai import gemini_client, history
from app.ai.gemini_client import GeminiError, GeminiParseError, generate_json

SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
}


def gemini_response(payload: dict, status_code: int = 200) -> MagicMock:
    """Gemini generateContent 응답을 흉내 낸다."""
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]
                },
                "finishReason": "STOP",
            }
        ]
    }
    resp.text = ""
    return resp


@pytest.fixture(autouse=True)
def clean_history(monkeypatch):
    """테스트끼리 로컬 대화 기록이 섞이지 않도록 매번 비우고, 실제 DB는 쓰지 않는다."""
    monkeypatch.setattr(history, "_local_history", {})
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture
def post(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(requests, "post", mock)
    monkeypatch.setattr(gemini_client.time, "sleep", lambda _: None)
    return mock


def sent_contents(post: MagicMock, call_index: int = -1) -> list[dict]:
    return post.call_args_list[call_index].kwargs["json"]["contents"]


def test_generate_json_returns_parsed_reply(post):
    post.return_value = gemini_response({"reply": "연결 성공"})

    result = generate_json("'연결 성공'이라고 reply에 답해줘", SCHEMA)

    assert result == {"reply": "연결 성공"}
    assert sent_contents(post) == [
        {"role": "user", "parts": [{"text": "'연결 성공'이라고 reply에 답해줘"}]}
    ]


def test_session_history_is_sent_on_next_request(post):
    post.side_effect = [
        gemini_response({"reply": "알겠어"}),
        gemini_response({"reply": "네 이름은 민수야"}),
    ]

    generate_json("내 이름은 민수야", SCHEMA, session_id="test")
    result = generate_json("내 이름이 뭐였지?", SCHEMA, session_id="test")

    assert result == {"reply": "네 이름은 민수야"}
    assert [c["role"] for c in sent_contents(post)] == ["user", "model", "user"]
    assert sent_contents(post)[0]["parts"] == [{"text": "내 이름은 민수야"}]
    assert sent_contents(post)[1]["parts"] == [{"text": '{"reply": "알겠어"}'}]


def test_without_session_id_history_is_not_kept(post):
    post.return_value = gemini_response({"reply": "ok"})

    generate_json("첫 번째", SCHEMA)
    generate_json("두 번째", SCHEMA)

    assert len(sent_contents(post)) == 1


def test_sessions_do_not_share_history(post):
    post.return_value = gemini_response({"reply": "ok"})

    generate_json("A의 질문", SCHEMA, session_id="a")
    generate_json("B의 질문", SCHEMA, session_id="b")

    assert len(sent_contents(post)) == 1


def test_non_retryable_status_raises_immediately(post):
    post.return_value = MagicMock(status_code=403, text="forbidden")

    with pytest.raises(GeminiError):
        generate_json("hi", SCHEMA)

    assert post.call_count == 1


def test_retryable_status_retries_then_fails(post):
    post.return_value = MagicMock(status_code=503, text="high demand")

    with pytest.raises(GeminiError):
        generate_json("hi", SCHEMA)

    assert post.call_count == gemini_client.MAX_RETRIES


def test_invalid_json_does_not_save_history(post):
    bad = MagicMock(status_code=200)
    bad.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "not json"}]}, "finishReason": "STOP"}
        ]
    }
    post.return_value = bad

    with pytest.raises(GeminiParseError):
        generate_json("hi", SCHEMA, session_id="test")

    assert "test" not in history._local_history


class FakeHistoryStore:
    """ai_histories DAO 대신 쓰는 메모리 저장소."""

    def __init__(self):
        self.rows: dict[str, list[dict]] = {}

    def fetch(self, conn, session_id):
        return self.rows.get(session_id)

    def upsert(self, conn, session_id, contents):
        self.rows[session_id] = contents

    def delete(self, conn, session_id):
        self.rows.pop(session_id, None)


@pytest.fixture
def store(monkeypatch):
    fake = FakeHistoryStore()
    monkeypatch.setattr(history, "ai_histories_dao", fake)
    monkeypatch.setattr(history, "_connect", MagicMock())
    return fake


def test_turn_is_saved_to_db(post, store):
    post.return_value = gemini_response({"reply": "ok"})

    generate_json("hi", SCHEMA, session_id="test")

    assert [c["role"] for c in store.rows["test"]] == ["user", "model"]


def test_history_is_restored_from_db_when_local_cache_is_empty(post, store):
    store.rows["test"] = [
        {"role": "user", "parts": [{"text": "이전 질문"}]},
        {"role": "model", "parts": [{"text": '{"reply": "이전 답"}'}]},
    ]
    post.return_value = gemini_response({"reply": "ok"})

    generate_json("이어서 질문", SCHEMA, session_id="test")

    assert [c["role"] for c in sent_contents(post)] == ["user", "model", "user"]
    assert history._local_history["test"][0]["parts"] == [{"text": "이전 질문"}]


def test_clear_history_removes_local_and_db(store):
    store.rows["test"] = [{"role": "user", "parts": [{"text": "x"}]}]
    history._local_history["test"] = list(store.rows["test"])

    history.clear_history("test")

    assert "test" not in history._local_history
    assert "test" not in store.rows


def test_db_error_falls_back_to_local_history(post, monkeypatch):
    monkeypatch.setattr(
        history, "_connect", MagicMock(side_effect=psycopg.OperationalError("down"))
    )
    post.return_value = gemini_response({"reply": "ok"})

    result = generate_json("hi", SCHEMA, session_id="test")

    assert result == {"reply": "ok"}
    assert [c["role"] for c in history._local_history["test"]] == ["user", "model"]


@pytest.mark.skipif(
    os.getenv("GEMINI_LIVE_TEST") != "1",
    reason="실제 Gemini API 호출은 GEMINI_LIVE_TEST=1 일 때만 실행",
)
def test_live_gemini_connection():
    result = generate_json("'연결 성공'이라고 reply에 답해줘", SCHEMA)
    assert "reply" in result

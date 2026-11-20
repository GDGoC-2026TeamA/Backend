import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from main import app
from app import workspaces


# Set only for an empty disposable database; CI provisions one per run.
@pytest.mark.skipif(
    not os.getenv("WORKSPACE_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL",
)
def test_workspace_isolation_and_learning(monkeypatch):
    url = os.environ["WORKSPACE_TEST_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", url)
    with psycopg.connect(url, autocommit=True) as db:
        db.execute(Path("db/migrations/001_initial.sql").read_text("utf-8-sig"))
        db.execute("INSERT INTO app_users(name) VALUES('기존 회원')")
        db.execute("INSERT INTO tasks(name,created_by) VALUES('기존 업무',1)")
        db.execute(Path("db/migrations/002_workspaces.sql").read_text("utf-8-sig"))
        assert db.execute(
            "SELECT kind FROM tasks JOIN workspaces ON workspace_id=workspaces.id"
        ).fetchone() == ("personal",)
    c = TestClient(app)

    def account(name):
        body = {
            "login_id": name,
            "name": name,
            "email": name + "@sample.test",
            "password": "sample-test-pass",
        }
        assert c.post("/api/v1/accounts", json=body).status_code == 201
        token = c.post("/api/v1/sessions", json=body).json()["token"]
        return {"Authorization": "Bearer " + token}

    owner, other, stranger = [account(n) for n in ("owner", "member", "outside")]

    def call(method, path, h, body=None):
        return c.request(method, "/api/v1" + path, headers=h, json=body)

    space = call("POST", "/workspaces", owner, {"name": "team"}).json()["id"]
    code = call("GET", f"/workspaces/{space}/invite", owner).json()
    call("POST", "/workspaces/join", other, code).raise_for_status()
    task = call("POST", "/tasks", owner, {"name": "입고", "workspaceId": space}).json()[
        "id"
    ]
    listing = f"/home?workspaceId={space}&filter=shared"
    assert call("GET", listing, other).json()["tasks"] == []
    assert call("GET", listing, stranger).status_code == 404
    with psycopg.connect(url) as db:
        fid = db.execute(
            "INSERT INTO files(task_id,kind,filename,status) VALUES(%s,'manual','m.pdf','ready') RETURNING id",
            (task,),
        ).fetchone()[0]
    key = str(uuid4())
    step = {
        "itemId": key,
        "before": "기록",
        "after": "대조",
        "change": "변경",
        "confirmed": True,
        "sources": [{"fileId": fid, "location": "p1"}],
    }
    unknown = {**step, "itemId": str(uuid4()), "confirmed": False, "change": "미확인"}
    body = {"inputFileIds": [fid], "steps": [step, unknown], "share": True}
    path = f"/tasks/{task}"
    assert call("POST", path + "/reviews", other, body).status_code == 404
    aid = call("POST", path + "/reviews", owner, body).json()["id"]
    assert call("POST", path + "/reviews", other, body).status_code == 403
    call("POST", path + "/reviews", owner, {**body, "share": False}).raise_for_status()
    assert call("GET", listing, other).json()["tasks"][0]["sharedAnalysisId"] == aid
    monkeypatch.setattr(
        workspaces,
        "generate_json",
        lambda *args: [
            {"itemId": unknown["itemId"], "reason": "skip"},
            {"itemId": key, "reason": "먼저 대조"},
        ],
    )
    guide = call("GET", path + "/learning-guide", other).json()
    assert guide["analysisId"] == aid and [
        r["itemId"] for r in guide["recommendations"]
    ] == [key]
    assert (
        call(
            "POST",
            path + "/practices",
            other,
            {"analysisId": aid, "selectedItemIds": [unknown["itemId"]]},
        ).status_code
        == 409
    )
    monkeypatch.setattr(
        workspaces,
        "generate_json",
        lambda *args: {
            "situation": "입고",
            "questions": [
                {
                    "prompt": "순서",
                    "itemId": key,
                    "choices": ["대조"],
                    "correct_index": 0,
                    "explanation": "확인",
                    "evidence": "test",
                }
            ],
        },
    )
    quiz = call(
        "POST",
        path + "/practices",
        other,
        {"analysisId": aid, "selectedItemIds": [key]},
    ).json()
    assert "correct_index" not in quiz["questions"][0]
    answer_path = f"/practices/{quiz['id']}/answers"
    assert call("POST", answer_path, owner, {"answers": [0]}).status_code == 404
    assert (
        "p1"
        in call("POST", answer_path, other, {"answers": [0]}).json()["questions"][0][
            "evidence"
        ]
    )
    call(
        "POST", path + "/jobs", other, {"analysisId": aid, "name": "개인 입고"}
    ).raise_for_status()
    assert (
        len(call("GET", "/jobs", other).json()) == 1
        and call("GET", "/jobs", owner).json() == []
    )
    call("DELETE", f"/workspaces/{space}/membership", other).raise_for_status()
    assert call("GET", path + "/learning-guide", other).status_code == 404
    assert len(call("GET", "/me/learning-history", other).json()) == 1

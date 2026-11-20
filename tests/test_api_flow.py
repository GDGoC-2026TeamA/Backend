"""
명세서의 구현 대상 API 전체 흐름을 실제 PostgreSQL에서 확인한다.
S3와 Gemini는 가짜 객체로 바꾼다.

WORKSPACE_TEST_DATABASE_URL에 버려도 되는 DB를 지정했을 때만 실행한다.
public 스키마를 지우고 마이그레이션을 다시 적용하며, 끝나면 다시 비운다.
(test_workspaces는 빈 DB를 기대하므로 이 테스트가 먼저 돌아도 영향을 주지 않는다.)
"""

import io
import os
from pathlib import Path
from typing import LiteralString, cast
from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.ai import gemini_client
from app.services import files as files_service, materials as materials_service
from main import app

URL = os.getenv("WORKSPACE_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(not URL, reason="requires disposable PostgreSQL")


def reset_schema():
    with psycopg.connect(URL, autocommit=True) as db:
        db.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")


class FakeS3:
    def __init__(self):
        self.objects = {}

    def upload_fileobj(self, stream, bucket, key, ExtraArgs):
        self.objects[key] = (stream.read(), ExtraArgs["ContentType"])

    def get_object(self, Bucket, Key):
        data, ctype = self.objects[Key]
        return {"Body": io.BytesIO(data), "ContentType": ctype, "ContentLength": len(data)}

    def generate_presigned_url(self, *a, **k):
        return "https://example.invalid/x"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    reset_schema()
    with psycopg.connect(URL, autocommit=True) as db:
        for f in sorted(Path("db/migrations").glob("*.sql")):
            # 저장소의 마이그레이션 파일이므로 신뢰하는 SQL로 실행한다.
            db.execute(cast(LiteralString, f.read_text("utf-8-sig")))
    s3 = FakeS3()
    monkeypatch.setattr(files_service, "bucket", lambda: (s3, "b"))
    monkeypatch.setattr(materials_service, "bucket", lambda: (s3, "b"))
    yield s3
    reset_schema()


def test_social_session_reuses_provider_identity(env):
    from app.api.v1.social import _social_session
    from psycopg.rows import dict_row

    client = TestClient(app)
    with psycopg.connect(URL, row_factory=dict_row) as conn:
        first = _social_session(conn, "google", "subject-1", "Google 사용자")
        again = _social_session(conn, "google", "subject-1", "다른 표시 이름")
        kakao = _social_session(conn, "kakao", "subject-1", "카카오 사용자")
    def workspace(result):
        response = client.get("/api/v1/workspaces", headers={"Authorization": "Bearer " + result["token"]})
        assert response.status_code == 200
        return response.json()[0]["id"]

    assert first != again
    assert workspace(first) == workspace(again)
    assert workspace(first) != workspace(kakao)


def test_email_login(env):
    client = TestClient(app)
    account = {
        "name": "테스트",
        "login_id": "warehouse-user",
        "email": "Warehouse@sample.test",
        "password": "test-password",
    }
    assert client.post("/api/v1/accounts", json=account).status_code == 201
    url = "/api/v1/sessions/email"
    credentials = {"email": "warehouse@SAMPLE.test", "password": account["password"]}
    response = client.post(url, json=credentials)
    assert response.status_code == 200
    token = response.json()["token"]
    spaces = client.get("/api/v1/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert spaces.status_code == 200
    assert any(space["kind"] == "personal" and space["is_owner"] for space in spaces.json())

    wrong = client.post(url, json={**credentials, "password": "incorrect"})
    unknown = client.post(url, json={**credentials, "email": "unknown@sample.test"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert client.post(url, json={**credentials, "email": "invalid"}).status_code == 422


def test_full_flow(env, monkeypatch):
    c = TestClient(app)

    def account(name):
        body = {"login_id": name, "name": name, "email": name + "@x.test", "password": "pass-pass-1"}
        assert c.post("/api/v1/accounts", json=body).status_code == 201
        return {"Authorization": "Bearer " + c.post("/api/v1/sessions", json=body).json()["token"]}

    owner, other, stranger = account("owner"), account("member"), account("outside")

    def call(method, path, h, body=None, **kw):
        return c.request(method, "/api/v1" + path, headers=h, json=body, **kw)

    space = call("POST", "/workspaces", owner, {"name": "team"}).json()["id"]
    code = call("GET", f"/workspaces/{space}/invite", owner).json()
    call("POST", "/workspaces/join", other, code).raise_for_status()
    tid = call("POST", "/tasks", owner, {"name": "입고", "workspaceId": space}).json()["id"]

    # 예시 자료 불러오기 (기존 자료 + 신규 매뉴얼)
    assert call("POST", f"/tasks/{tid}/sample-materials", other, {"scenario": "inventory"}).status_code == 404
    assert call("POST", f"/tasks/{tid}/sample-materials", owner, {"scenario": "nope"}).status_code == 422
    r = call("POST", f"/tasks/{tid}/sample-materials", owner, {"scenario": "inventory"})
    assert r.status_code == 201, r.text
    mats = r.json()["materials"]
    assert [m["kind"] for m in mats] == ["previous_form", "manual"]
    assert [len(env.objects[f"files/v1/{m['id']}"][0]) for m in mats] == [
        (materials_service.SAMPLES_DIR / "inventory" / m["filename"]).stat().st_size for m in mats
    ]
    fids = [m["id"] for m in mats]

    # 업무 상세
    d = call("GET", f"/tasks/{tid}", owner).json()
    assert d["learningStatus"] == "not_started" and len(d["materials"]) == 2 and d["recentJobs"] == []
    assert call("GET", f"/tasks/{tid}", stranger).status_code == 404

    # 분석 (파일 선택 포함)
    def fake_analyze(prompt, schema, files=None, *a, **k):
        return [
            {"before": "수기 대조", "after": "바코드 스캔", "change": "변경", "requiredFields": ["품목코드", "수량"],
             "caution": "", "sources": [{"fileId": fids[1], "location": "p1"}]},
            {"before": "", "after": "로트 입력", "change": "신규 확인", "requiredFields": ["로트 번호"],
             "caution": "필수", "sources": [{"fileId": fids[1], "location": "p1 3번"}]},
        ]
    monkeypatch.setattr(gemini_client, "generate_json", fake_analyze)
    assert call("POST", f"/tasks/{tid}/analyses", owner, {"fileIds": [fids[1]]}).status_code == 422
    assert call("POST", f"/tasks/{tid}/analyses", owner, {"fileIds": [999]}).status_code == 422
    # Gemini로 보낼 자료 합계가 한도를 넘으면 AI를 호출하지 않고 413
    sizes = [len(env.objects[f"files/v1/{i}"][0]) for i in fids]
    monkeypatch.setattr(files_service, "MAX_INLINE_TOTAL", sum(sizes) - 1)
    gemini = MagicMock()
    monkeypatch.setattr(gemini_client, "generate_json", gemini)
    assert call("POST", f"/tasks/{tid}/analyses", owner).status_code == 413
    gemini.assert_not_called()
    monkeypatch.setattr(files_service, "MAX_INLINE_TOTAL", sum(sizes))
    monkeypatch.setattr(gemini_client, "generate_json", fake_analyze)
    a = call("POST", f"/tasks/{tid}/analyses", owner)
    assert a.status_code == 200, a.text
    a = call("POST", f"/tasks/{tid}/analyses", owner, {"fileIds": fids}).json()
    aid = a["analysisId"]
    assert a["inputFileIds"] == fids and len(a["steps"]) == 2

    # 비교표 조회 / 항목 수정
    cmp = call("GET", f"/analyses/{aid}", owner).json()
    assert cmp["confirmed"] is False and cmp["items"][0]["source"] == {"materialId": fids[1], "page": "p1"}
    assert call("GET", f"/analyses/{aid}", other).status_code == 404  # 공유 전
    item = cmp["items"][0]["id"]
    assert call("PATCH", f"/analysis-items/{item}", owner, {}).status_code == 422
    assert call("PATCH", f"/analysis-items/{item}", other, {"confirmed": True}).status_code == 404
    p = call("PATCH", f"/analysis-items/{item}", owner, {"after": "바코드 스캔 후 자동 대조", "confirmed": True})
    assert p.status_code == 200, p.text
    assert p.json()["after"] == "바코드 스캔 후 자동 대조" and p.json()["confirmed"] is True
    item2 = cmp["items"][1]["id"]
    call("PATCH", f"/analysis-items/{item2}", owner, {"confirmed": True}).raise_for_status()

    # 검토 제출(공유) → 확정본
    steps = call("GET", f"/analyses/{aid}", owner).json()["items"]
    review_steps = [
        {"itemId": s["id"], "before": s["before"], "after": s["after"], "requiredFields": s["requiredFields"],
         "caution": s["caution"], "change": s["change"], "confirmed": s["confirmed"], "sources": s["sources"]}
        for s in steps
    ]
    rid = call("POST", f"/tasks/{tid}/reviews", owner, {"inputFileIds": fids, "steps": review_steps, "share": True}).json()["id"]
    assert call("GET", f"/analyses/{rid}", other).json()["confirmed"] is True
    assert call("PATCH", f"/analysis-items/{item}", owner, {"confirmed": False}).status_code == 200  # 초안은 여전히 수정 가능
    assert call("GET", f"/tasks/{tid}", other).json()["materials"]

    # 연습 → 답안 → 결과
    monkeypatch.setattr(gemini_client, "generate_json", lambda *a, **k: {
        "situation": "입고 상황", "questions": [
            {"prompt": "Q1", "itemId": item, "choices": ["a", "b"], "correct_index": 1, "explanation": "스캔", "evidence": ""},
            {"prompt": "Q2", "itemId": item2, "choices": ["a", "b"], "correct_index": 0, "explanation": "로트", "evidence": ""},
        ]})
    pid = call("POST", f"/tasks/{tid}/practices", other, {"analysisId": rid, "selectedItemIds": [item, item2]}).json()["id"]
    assert call("GET", f"/practices/{pid}/result", other).status_code == 409
    assert call("POST", f"/practices/{pid}/answers", other, {"answers": [1, 1], "reasons": ["x"]}).status_code == 422
    ans = call("POST", f"/practices/{pid}/answers", other, {"answers": [1, 1], "reasons": ["스캔이라서", None]}).json()
    assert ans["correct"] == [True, False] and ans["score"] == {"correct": 1, "total": 2}
    res = call("GET", f"/practices/{pid}/result", other).json()
    assert res["practiceId"] == pid
    assert res["answers"][0]["selectedOptionId"] == 1 and res["answers"][0]["correct"] is True
    assert res["answers"][1]["feedback"].startswith("오답") and res["answers"][0]["reason"] == "스캔이라서"
    assert res["answers"][1]["source"] == {"materialId": fids[1], "page": "p1 3번"}
    assert call("GET", f"/practices/{pid}/result", owner).status_code == 404

    # 질문
    monkeypatch.setattr(gemini_client, "generate_json", lambda *a, **k: {"answer": "스캔", "itemIds": [item], "followUpQuestion": ""})
    q = call("POST", f"/tasks/{tid}/questions", other, {"question": "어떻게?"}).json()
    assert q["needsReview"] is False and q["followUpQuestion"] is None and q["itemIds"] == [item]
    monkeypatch.setattr(gemini_client, "generate_json", lambda *a, **k: {"answer": "?", "itemIds": [], "followUpQuestion": "팀장에게 반품 기준 확인"})
    q = call("POST", f"/tasks/{tid}/questions", other, {"question": "반품은?"}).json()
    assert q["needsReview"] is True and q["followUpQuestion"] == "팀장에게 반품 기준 확인"

    # 카드 연결 + 학습 기록
    card = call("POST", f"/tasks/{tid}/cards", other, {"analysisId": rid, "itemId": item, "title": "스캔"}).json()["id"]
    hist = call("GET", "/me/learning-history", other).json()
    assert len(hist) == 3
    by_kind = {h["kind"]: h for h in hist if h["kind"] == "practice"}
    assert by_kind["practice"]["card_ids"] == [card] and by_kind["practice"]["answered"] is True
    assert by_kind["practice"]["task_name"] == "입고"
    det = call("GET", f"/me/learning-history/{pid}", other).json()
    assert det["content"]["answers"] == [1, 1]
    assert call("GET", f"/me/learning-history/{pid}", owner).status_code == 404
    assert call("GET", f"/tasks/{tid}", other).json()["learningStatus"] == "completed"

    # 작업
    jid = call("POST", f"/tasks/{tid}/jobs", other, {"analysisId": rid, "name": "3월 입고", "description": "한빛상사"}).json()["id"]
    j = call("GET", f"/jobs/{jid}", other).json()
    assert j["status"] == "created" and j["description"] == "한빛상사" and j["taskId"] == tid
    assert call("GET", f"/jobs/{jid}", owner).status_code == 404
    up = call("POST", f"/jobs/{jid}/files", other, None, files={"file": ("명세서.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert up.status_code == 201, up.text
    jf = up.json()
    assert jf["filename"] == "명세서.pdf"
    bad = call("POST", f"/jobs/{jid}/files", other, None, files={"file": ("a.txt", b"x", "text/plain")})
    assert bad.status_code == 415
    extra = call("POST", f"/jobs/{jid}/files", other, None, files={"file": ("b.png", b"png", "image/png")}).json()
    assert call("DELETE", f"/job-files/{extra['id']}", owner).status_code == 404
    assert call("DELETE", f"/job-files/{extra['id']}", other).status_code == 204
    assert [f["id"] for f in call("GET", f"/jobs/{jid}", other).json()["files"]] == [jf["id"]]

    assert call("PATCH", f"/jobs/{jid}/draft", other, {"fields": []}).status_code == 409
    assert call("POST", f"/jobs/{jid}/result", other).status_code == 409
    assert call("POST", f"/jobs/{jid}/draft", other, {"fileIds": [extra["id"]]}).status_code == 422
    monkeypatch.setattr(gemini_client, "generate_json", lambda *a, **k: {"fields": [
        {"key": "품목코드", "value": "A-1024", "fileId": jf["id"], "location": "1행"},
        {"key": "수량", "value": " 120 ", "fileId": 99999, "location": "x"},
        {"key": "로트 번호", "value": None},
        {"key": "엉뚱한 키", "value": "무시"},
    ]})
    dr = call("POST", f"/jobs/{jid}/draft", other, {"fileIds": [jf["id"]]})
    assert dr.status_code == 201, dr.text
    dr = dr.json()
    assert [f["key"] for f in dr["fields"]] == ["품목코드", "수량", "로트 번호"]
    assert dr["missing"] == ["로트 번호"] and dr["source"] == {"materialId": jf["id"], "page": "1행"}
    assert dr["fields"][1]["value"] == "120" and dr["fields"][1]["source"] is None
    assert call("POST", f"/jobs/{jid}/draft", other, {"fileIds": [jf["id"]]}).status_code == 409

    assert call("PATCH", f"/jobs/{jid}/draft", other, {"fields": [{"key": "없음", "value": 1, "checked": True}]}).status_code == 422
    pr = call("PATCH", f"/jobs/{jid}/draft", other, {"fields": [
        {"key": "품목코드", "value": "A-1024", "checked": True},
        {"key": "로트 번호", "value": "L-77", "checked": True}], "lastField": "로트 번호"}).json()
    assert pr["status"] == "reviewing" and pr["pending"] == ["수량"] and pr["lastField"] == "로트 번호"
    with psycopg.connect(URL) as db:
        row = db.execute("SELECT review_changes FROM jobs WHERE id=%s", (jid,)).fetchone()
    assert row is not None
    rc = row[0]
    assert rc["values"] == {"로트 번호": "L-77"}  # 원본과 같은 값은 저장하지 않음
    j = call("GET", f"/jobs/{jid}", other).json()
    assert j["fields"][2]["value"] == "L-77" and j["lastField"] == "로트 번호"

    home = call("GET", f"/home?workspaceId={space}", other).json()
    assert [x["id"] for x in home["continueJobs"]] == [jid] and [x["id"] for x in home["recentCards"]] == [card]
    assert call("GET", f"/tasks/{tid}", other).json()["recentJobs"][0] == {"id": jid, "taskId": tid, "name": "3월 입고", "status": "reviewing"}

    assert call("GET", f"/jobs/{jid}/result/download", other).status_code == 409
    sv = call("POST", f"/jobs/{jid}/result", other).json()
    assert sv["status"] == "saved" and sv["pending"] == ["수량"]
    assert call("POST", f"/jobs/{jid}/result", other).status_code == 409
    assert call("PATCH", f"/jobs/{jid}/draft", other, {"fields": []}).status_code == 409
    assert call("DELETE", f"/job-files/{jf['id']}", other).status_code == 409
    dl = call("GET", f"/jobs/{jid}/result/download", other)
    assert dl.status_code == 200 and "attachment" in dl.headers["content-disposition"]
    text = dl.content.decode("utf-8-sig")
    assert "로트 번호,L-77,예" in text and "수량,120,아니오" in text
    assert call("GET", f"/home?workspaceId={space}", other).json()["continueJobs"] == []
    assert call("GET", "/jobs", other).json()[0]["status"] == "saved"

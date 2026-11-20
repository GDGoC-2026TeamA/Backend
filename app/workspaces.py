"""Workspace access and versioned workflows. The identity is always verified server-side."""

import hashlib
import secrets
import json
import os
from typing import Literal
from uuid import UUID

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, SecretStr

from app.ai.gemini_client import GeminiError, GeminiParseError, generate_json

router = APIRouter(prefix="/api/v1")
hasher = PasswordHasher()


def db():
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        yield conn


def user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()), conn=Depends(db)
):
    digest = hashlib.sha256(credentials.credentials.encode()).digest()
    row = conn.execute(
        "SELECT user_id FROM login_sessions WHERE token_hash=%s AND expires_at>now()",
        (digest,),
    ).fetchone()
    if not row:
        raise HTTPException(401, "다시 로그인하세요.")
    return row["user_id"]


class Login(BaseModel):
    login_id: str
    password: SecretStr


@router.post("/sessions")
def login(data: Login, conn=Depends(db)):
    row = conn.execute(
        "SELECT id,password_hash FROM app_users WHERE lower(login_id)=lower(%s)",
        (data.login_id,),
    ).fetchone()
    if row and row["password_hash"]:
        try:
            hasher.verify(row["password_hash"], data.password.get_secret_value())
        except (VerificationError, InvalidHashError):
            pass
        else:
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).digest()
            conn.execute(
                "DELETE FROM login_sessions WHERE user_id=%s AND expires_at<=now()",
                (row["id"],),
            )
            conn.execute(
                "INSERT INTO login_sessions VALUES(%s,%s,now()+interval '8 hours')",
                (digest, row["id"]),
            )
            return {"token": token}
    raise HTTPException(401, "로그인 정보를 확인하세요.")


class Name(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class Signup(Name):
    login_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: SecretStr = Field(min_length=8, max_length=256)


@router.post("/accounts", status_code=201)
def signup(data: Signup, conn=Depends(db)):
    try:
        return conn.execute(
            "INSERT INTO app_users(name,login_id,email,password_hash) VALUES(%s,%s,%s,%s) RETURNING id",
            (
                data.name,
                data.login_id,
                data.email,
                hasher.hash(data.password.get_secret_value()),
            ),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "이미 등록된 계정입니다.") from None


def required(row):
    if not row:
        raise HTTPException(404, "접근 가능한 항목이 없습니다.")
    return row


def member(conn, space, uid):
    return required(
        conn.execute(
            """
        SELECT w.* FROM workspaces w JOIN workspace_members m ON m.workspace_id=w.id
        WHERE w.id=%s AND m.user_id=%s FOR SHARE OF m
    """,
            (space, uid),
        ).fetchone()
    )


def task_for(conn, tid, uid, *, edit=False):
    row = required(
        conn.execute(
            """
        SELECT t.*,w.kind FROM tasks t JOIN workspaces w ON w.id=t.workspace_id
        JOIN workspace_members m ON m.workspace_id=t.workspace_id
        WHERE t.id=%s AND m.user_id=%s AND (t.created_by=%s OR t.shared_analysis_id IS NOT NULL)
        FOR SHARE OF m
    """,
            (tid, uid, uid),
        ).fetchone()
    )
    if edit and row["created_by"] != uid:
        raise HTTPException(403, "등록자만 수정할 수 있습니다.")
    return row


@router.get("/workspaces")
def spaces(uid=Depends(user), conn=Depends(db)):
    return conn.execute(
        """SELECT w.id,w.name,w.kind,w.created_by=%s AS is_owner
        FROM workspaces w JOIN workspace_members m ON m.workspace_id=w.id
        WHERE m.user_id=%s ORDER BY w.kind DESC,w.id""",
        (uid, uid),
    ).fetchall()


@router.post("/workspaces", status_code=201)
def create_space(data: Name, uid=Depends(user), conn=Depends(db)):
    row = conn.execute(
        """INSERT INTO workspaces(kind,name,created_by,invite_code)
        VALUES('company',%s,%s,gen_random_uuid()) RETURNING id""",
        (data.name, uid),
    ).fetchone()
    conn.execute("INSERT INTO workspace_members VALUES(%s,%s)", (row["id"], uid))
    return row


class Invite(BaseModel):
    code: UUID


@router.post("/workspaces/join")
def join(data: Invite, uid=Depends(user), conn=Depends(db)):
    row = required(
        conn.execute(
            "SELECT id FROM workspaces WHERE invite_code=%s", (data.code,)
        ).fetchone()
    )
    conn.execute(
        "INSERT INTO workspace_members VALUES(%s,%s) ON CONFLICT DO NOTHING",
        (row["id"], uid),
    )
    return row


@router.get("/workspaces/{space}/invite")
def invite(space: int, uid=Depends(user), conn=Depends(db)):
    w = member(conn, space, uid)
    if w["kind"] != "company" or w["created_by"] != uid:
        raise HTTPException(403, "회사 공간 생성자만 초대 코드를 볼 수 있습니다.")
    return {"code": w["invite_code"]}


@router.delete("/workspaces/{space}/membership", status_code=204)
def leave(space: int, uid=Depends(user), conn=Depends(db)):
    required(
        conn.execute(
            "SELECT user_id FROM workspace_members WHERE workspace_id=%s AND user_id=%s FOR UPDATE",
            (space, uid),
        ).fetchone()
    )
    w = member(conn, space, uid)
    if w["created_by"] == uid:
        raise HTTPException(409, "공간 생성자는 나갈 수 없습니다.")
    if conn.execute(
        "SELECT 1 FROM tasks WHERE workspace_id=%s AND created_by=%s AND shared_analysis_id IS NOT NULL",
        (space, uid),
    ).fetchone():
        raise HTTPException(409, "등록한 업무의 공유를 먼저 해제하세요.")
    conn.execute(
        "DELETE FROM workspace_members WHERE workspace_id=%s AND user_id=%s",
        (space, uid),
    )


class NewTask(Name):
    workspaceId: int
    description: str = ""


@router.post("/tasks", status_code=201)
def create_task(data: NewTask, uid=Depends(user), conn=Depends(db)):
    member(conn, data.workspaceId, uid)
    return conn.execute(
        "INSERT INTO tasks(workspace_id,created_by,name,description) VALUES(%s,%s,%s,%s) RETURNING id",
        (data.workspaceId, uid, data.name, data.description),
    ).fetchone()


@router.get("/home")
def home(
    workspaceId: int,
    filter: Literal["all", "mine", "shared"] = "all",
    uid=Depends(user),
    conn=Depends(db),
):
    member(conn, workspaceId, uid)
    rows = conn.execute(
        """SELECT t.id,t.name,t.description,u.name AS "creatorName", t.created_by=%s AS "isMine",
        CASE WHEN t.created_by=%s THEN t.updated_at ELSE t.shared_at END AS "updatedAt",
        t.shared_analysis_id AS "sharedAnalysisId"
        FROM tasks t JOIN app_users u ON u.id=t.created_by
        WHERE t.workspace_id=%s AND (t.created_by=%s OR t.shared_analysis_id IS NOT NULL)
        AND (%s='all' OR (%s='mine' AND t.created_by=%s) OR (%s='shared' AND t.created_by<>%s))
        ORDER BY "updatedAt" DESC,t.id""",
        (uid, uid, workspaceId, uid, filter, filter, uid, filter, uid),
    ).fetchall()
    return {"tasks": rows}


class Version(BaseModel):
    analysisId: int


class Source(BaseModel):
    fileId: int
    location: str = Field(min_length=1)


class Step(BaseModel):
    itemId: UUID
    before: str
    after: str
    requiredFields: list[str] = Field(default_factory=list)
    caution: str = ""
    change: Literal["유지", "변경", "신규 확인", "미확인"]
    confirmed: bool
    sources: list[Source]


class Review(BaseModel):
    inputFileIds: list[int] = Field(min_length=1)
    steps: list[Step] = Field(min_length=1)
    share: bool = False


@router.post("/tasks/{tid}/reviews", status_code=201)
def review(tid: int, data: Review, uid=Depends(user), conn=Depends(db)):
    t = task_for(conn, tid, uid, edit=True)
    if data.share and t["kind"] != "company":
        raise HTTPException(422, "개인 공간에서는 공유할 수 없습니다.")
    files = {
        r["id"]
        for r in conn.execute(
            """SELECT id FROM files WHERE task_id=%s AND id=ANY(%s)
        AND archived_at IS NULL AND status='ready' FOR SHARE""",
            (tid, data.inputFileIds),
        )
    }
    if files != set(data.inputFileIds) or len({s.itemId for s in data.steps}) != len(
        data.steps
    ):
        raise HTTPException(422, "파일 소속과 단계 ID를 확인하세요.")
    for step in data.steps:
        if any(s.fileId not in files for s in step.sources) or (
            step.confirmed and (not step.sources or step.change == "미확인")
        ):
            raise HTTPException(422, "확인된 단계에는 등록 자료의 근거가 필요합니다.")
    row = conn.execute(
        """INSERT INTO analyses(task_id,input_file_ids,steps,confirmed_at)
        VALUES(%s,%s,%s,now()) RETURNING id""",
        (
            tid,
            data.inputFileIds,
            Jsonb([s.model_dump(mode="json") for s in data.steps]),
        ),
    ).fetchone()
    if data.share:
        conn.execute(
            "UPDATE tasks SET updated_at=now(),shared_at=now(),shared_analysis_id=%s WHERE id=%s",
            (row["id"], tid),
        )
    else:
        conn.execute("UPDATE tasks SET updated_at=now() WHERE id=%s", (tid,))
    return row


@router.delete("/tasks/{tid}/share", status_code=204)
def unshare(tid: int, uid=Depends(user), conn=Depends(db)):
    task_for(conn, tid, uid, edit=True)
    conn.execute(
        "UPDATE tasks SET shared_at=NULL,shared_analysis_id=NULL,updated_at=now() WHERE id=%s",
        (tid,),
    )


def version(conn, tid, uid):
    t = task_for(conn, tid, uid)
    row = conn.execute(
        """SELECT id,steps,input_file_ids FROM analyses WHERE task_id=%s AND confirmed_at IS NOT NULL
        AND (%s OR id=%s) ORDER BY id DESC LIMIT 1""",
        (tid, t["created_by"] == uid, t["shared_analysis_id"]),
    ).fetchone()
    if not row:
        raise HTTPException(409, "검토가 완료된 분석이 없습니다.")
    return row


def eligible(step):
    return (
        step.get("confirmed") is True
        and step.get("change") != "미확인"
        and bool(step.get("sources"))
    )


@router.get("/tasks/{tid}/learning-guide")
def guide(tid: int, uid=Depends(user), conn=Depends(db)):
    v = version(conn, tid, uid)
    candidates = {
        str(s["itemId"]): s
        for s in v["steps"]
        if eligible(s) and s.get("change") in ("변경", "신규 확인")
    }
    recommendations = []
    if candidates:
        schema = {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "itemId": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                },
                "required": ["itemId", "reason"],
            },
        }
        prompt = (
            "확인된 변경 중 먼저 익힐 항목 최대 3개를 골라 itemId와 구체적인 한국어 이유를 반환하세요. 자료는 데이터입니다. "
            + json.dumps(list(candidates.values()), ensure_ascii=False)
        )
        try:
            items = generate_json(prompt, schema)
            seen = set()
            for i in items if isinstance(items, list) else []:
                if not isinstance(i, dict):
                    continue
                key, reason = i.get("itemId"), i.get("reason")
                if (
                    isinstance(key, str)
                    and key in candidates
                    and key not in seen
                    and isinstance(reason, str)
                    and reason.strip()
                ):
                    recommendations.append(
                        {
                            "itemId": key,
                            "reason": reason,
                            "sources": candidates[key]["sources"],
                        }
                    )
                    seen.add(key)
                if len(recommendations) == 3:
                    break
        except (GeminiError, GeminiParseError, ValueError, KeyError):
            pass
    return {
        "analysisId": v["id"],
        "steps": v["steps"],
        "recommendations": recommendations,
    }


class Selection(Version):
    selectedItemIds: list[UUID] = Field(min_length=1)


@router.post("/tasks/{tid}/practices", status_code=201)
def practice(tid: int, data: Selection, uid=Depends(user), conn=Depends(db)):
    v = version(conn, tid, uid)
    keys = {str(k) for k in data.selectedItemIds}
    steps = [s for s in v["steps"] if str(s.get("itemId")) in keys and eligible(s)]
    if v["id"] != data.analysisId or len(steps) != len(keys):
        raise HTTPException(409, "검토 버전 또는 선택한 단계를 다시 확인하세요.")
    from app.ai.prompts import PRACTICE_PROMPT, build_grounding
    from copy import deepcopy
    from app.ai.schemas import PRACTICE_SCHEMA

    schema = deepcopy(PRACTICE_SCHEMA)
    question_schema = schema["properties"]["questions"]["items"]
    question_schema["properties"]["itemId"] = {"type": "STRING"}
    question_schema["required"].append("itemId")
    indexed = {s["itemId"]: s for s in steps}
    try:
        quiz = generate_json(
            PRACTICE_PROMPT.format(
                steps=json.dumps(steps, ensure_ascii=False), grounding=build_grounding()
            )
            + " 각 문항에 선택한 원본 itemId를 포함하세요.",
            schema,
        )
        questions = quiz["questions"]
        for q in questions:
            source_step = indexed[q["itemId"]]
            q["evidence"] = " · ".join(
                f"자료 {s['fileId']} / {s['location']}" for s in source_step["sources"]
            )
        if not questions or any(
            not 0 <= q["correct_index"] < len(q["choices"]) for q in questions
        ):
            raise ValueError()
    except (GeminiError, GeminiParseError, KeyError, TypeError, ValueError):
        raise HTTPException(503, "연습 문제를 생성하지 못했습니다.") from None
    record = conn.execute(
        """INSERT INTO learning_records(user_id,task_id,analysis_id,kind,content)
        VALUES(%s,%s,%s,'practice',%s) RETURNING id""",
        (uid, tid, v["id"], Jsonb({**quiz, "selectedItemIds": sorted(keys)})),
    ).fetchone()
    return {
        **record,
        "situation": quiz["situation"],
        "questions": [
            {"prompt": q["prompt"], "choices": q["choices"]} for q in questions
        ],
    }


from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import boto3
from botocore.config import Config
from fastapi import File, Form, UploadFile
from app.ai.gemini_client import InlineFile


def bucket():
    import os

    return (
        boto3.client(
            "s3",
            endpoint_url=os.environ["AWS_ENDPOINT_URL"],
            region_name=os.getenv("AWS_DEFAULT_REGION", "auto"),
            config=Config(signature_version="s3v4"),
        ),
        os.environ["AWS_S3_BUCKET_NAME"],
    )


@router.post("/tasks/{tid}/materials", status_code=201)
def upload(
    tid: int,
    kind: Literal["previous_form", "manual", "screenshot"] = Form(...),
    file: UploadFile = File(...),
    uid=Depends(user),
    conn=Depends(db),
):
    task_for(conn, tid, uid, edit=True)
    if file.content_type not in ("application/pdf", "image/jpeg", "image/png"):
        raise HTTPException(415, "PDF, JPG, PNG 파일을 등록하세요.")
    if file.size is None or file.size > 16 * 1024 * 1024:
        raise HTTPException(413, "파일 크기는 16MB 이하여야 합니다.")
    s3, name = bucket()
    row = conn.execute(
        "INSERT INTO files(task_id,kind,filename) VALUES(%s,%s,%s) RETURNING id",
        (tid, kind, file.filename or "자료"),
    ).fetchone()
    conn.commit()
    try:
        s3.upload_fileobj(
            file.file,
            name,
            f"files/v1/{row['id']}",
            ExtraArgs={"ContentType": file.content_type},
        )
    except Exception:
        conn.execute("UPDATE files SET status='failed' WHERE id=%s", (row["id"],))
        conn.commit()
        raise HTTPException(503, "파일 저장에 실패했습니다.") from None
    conn.execute("UPDATE files SET status='ready' WHERE id=%s", (row["id"],))
    return row


@router.get("/tasks/{tid}/materials")
def materials(tid: int, uid=Depends(user), conn=Depends(db)):
    t = task_for(conn, tid, uid)
    if t["created_by"] == uid:
        return conn.execute(
            "SELECT id,filename,kind,status FROM files WHERE task_id=%s AND archived_at IS NULL ORDER BY id",
            (tid,),
        ).fetchall()
    v = version(conn, tid, uid)
    return conn.execute(
        "SELECT id,filename,kind,status FROM files WHERE task_id=%s AND id=ANY(%s) AND status='ready' ORDER BY id",
        (tid, v["input_file_ids"]),
    ).fetchall()


@router.get("/tasks/{tid}/materials/{fid}/download")
def download(tid: int, fid: int, uid=Depends(user), conn=Depends(db)):
    t = task_for(conn, tid, uid)
    stored = conn.execute(
        "SELECT 1 FROM files WHERE id=%s AND task_id=%s AND status='ready'", (fid, tid)
    ).fetchone()
    if not stored or (
        t["created_by"] != uid and fid not in version(conn, tid, uid)["input_file_ids"]
    ):
        raise HTTPException(404, "자료가 없습니다.")
    s3, name = bucket()
    return {
        "url": s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": name, "Key": f"files/v1/{fid}"},
            ExpiresIn=120,
        )
    }


@router.post("/tasks/{tid}/analyses")
def analyze(tid: int, uid=Depends(user), conn=Depends(db)):
    t = task_for(conn, tid, uid, edit=True)
    files = [f for f in materials(tid, uid, conn) if f["status"] == "ready"]
    if not {"previous_form", "manual"} <= {f["kind"] for f in files}:
        raise HTTPException(422, "기존 자료와 새 매뉴얼이 필요합니다.")
    s3, name = bucket()
    prompt = (
        "순서대로 첨부한 기존 및 신규 업무 자료를 단계별로 비교하세요. 근거는 fileId와 위치로 제시하세요. "
        "근거가 부족하면 change를 미확인으로 두세요. 변경 구분은 유지, 변경, 신규 확인, 미확인 중 하나입니다. "
        + json.dumps({"task": t["name"], "files": files}, ensure_ascii=False)
    )
    string = {"type": "STRING"}
    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "before": string,
                "after": string,
                "change": string,
                "requiredFields": {"type": "ARRAY", "items": string},
                "caution": string,
                "sources": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "fileId": {"type": "INTEGER"},
                            "location": string,
                        },
                        "required": ["fileId", "location"],
                    },
                },
            },
            "required": [
                "before",
                "after",
                "change",
                "requiredFields",
                "caution",
                "sources",
            ],
        },
    }
    with TemporaryDirectory() as folder:
        docs = []
        for f in files:
            path = Path(folder) / str(f["id"])
            obj = s3.get_object(Bucket=name, Key=f"files/v1/{f['id']}")
            with obj["Body"] as stream:
                path.write_bytes(stream.read())
            docs.append(InlineFile(path, obj["ContentType"]))
        try:
            raw = generate_json(prompt, schema, docs)
            steps = [Step(**s, itemId=uuid4(), confirmed=False) for s in raw]
            if not steps or any(
                src.fileId not in {f["id"] for f in files}
                for s in steps
                for src in s.sources
            ):
                raise ValueError()
        except (ValueError, TypeError, KeyError, GeminiError, GeminiParseError):
            raise HTTPException(503, "분석 결과를 확인할 수 없습니다.") from None
    return {"inputFileIds": [f["id"] for f in files], "steps": steps}


class Answers(BaseModel):
    answers: list[int]


@router.post("/practices/{pid}/answers")
def answer(pid: int, data: Answers, uid=Depends(user), conn=Depends(db)):
    r = required(
        conn.execute(
            "SELECT content FROM learning_records WHERE id=%s AND user_id=%s AND kind='practice' FOR UPDATE",
            (pid, uid),
        ).fetchone()
    )
    content = r["content"]
    questions = content["questions"]
    if len(data.answers) != len(questions) or any(
        not 0 <= a < len(q["choices"]) for a, q in zip(data.answers, questions)
    ):
        raise HTTPException(422, "각 문제의 답을 선택하세요.")
    content["answers"] = data.answers
    conn.execute(
        "UPDATE learning_records SET content=%s WHERE id=%s", (Jsonb(content), pid)
    )
    return {"questions": questions, "answers": data.answers}


class NewJob(Version, Name):
    pass


@router.post("/tasks/{tid}/jobs", status_code=201)
def start_job(tid: int, data: NewJob, uid=Depends(user), conn=Depends(db)):
    v = version(conn, tid, uid)
    if v["id"] != data.analysisId:
        raise HTTPException(409, "검토 버전이 변경되었습니다.")
    return conn.execute(
        "INSERT INTO jobs(user_id,analysis_id,name) VALUES(%s,%s,%s) RETURNING id",
        (uid, v["id"], data.name),
    ).fetchone()


class NewCard(Version):
    itemId: UUID
    title: str = Field(min_length=1)


@router.post("/tasks/{tid}/cards", status_code=201)
def card(tid: int, data: NewCard, uid=Depends(user), conn=Depends(db)):
    v = version(conn, tid, uid)
    if v["id"] != data.analysisId or not any(
        s.get("itemId") == str(data.itemId) and eligible(s) for s in v["steps"]
    ):
        raise HTTPException(409, "현재 확인된 단계에서 카드를 만드세요.")
    return conn.execute(
        """INSERT INTO cards(user_id,analysis_id,item_id,title) VALUES(%s,%s,%s,%s) RETURNING id""",
        (uid, v["id"], data.itemId, data.title),
    ).fetchone()


@router.delete("/tasks/{tid}/materials/{fid}", status_code=204)
def archive_file(tid: int, fid: int, uid=Depends(user), conn=Depends(db)):
    task_for(conn, tid, uid, edit=True)
    required(
        conn.execute(
            "UPDATE files SET archived_at=now() WHERE id=%s AND task_id=%s RETURNING id",
            (fid, tid),
        ).fetchone()
    )


@router.get("/me/learning-history")
def history(uid=Depends(user), conn=Depends(db)):
    return conn.execute(
        """SELECT id,task_id,kind,created_at FROM learning_records WHERE user_id=%s
        ORDER BY created_at DESC""",
        (uid,),
    ).fetchall()


@router.get("/cards")
def my_cards(uid=Depends(user), conn=Depends(db)):
    return conn.execute(
        "SELECT id,title,updated_at FROM cards WHERE user_id=%s ORDER BY updated_at DESC",
        (uid,),
    ).fetchall()


@router.get("/jobs")
def my_jobs(uid=Depends(user), conn=Depends(db)):
    return conn.execute(
        """SELECT id,name,created_at,CASE WHEN saved_at IS NULL THEN 'reviewing' ELSE 'saved' END AS status
        FROM jobs WHERE user_id=%s ORDER BY created_at DESC""",
        (uid,),
    ).fetchall()


@router.post("/tasks/{tid}/share")
def share_reviewed(tid: int, data: Version, uid=Depends(user), conn=Depends(db)):
    t = task_for(conn, tid, uid, edit=True)
    if t["kind"] != "company":
        raise HTTPException(422, "회사 공간에서만 공유할 수 있습니다.")
    required(
        conn.execute(
            "SELECT id FROM analyses WHERE id=%s AND task_id=%s AND confirmed_at IS NOT NULL",
            (data.analysisId, tid),
        ).fetchone()
    )
    return conn.execute(
        """UPDATE tasks SET shared_analysis_id=%s,shared_at=now(),updated_at=now()
        WHERE id=%s RETURNING shared_at""",
        (data.analysisId, tid),
    ).fetchone()


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.post("/tasks/{tid}/questions", status_code=201)
def ask(tid: int, data: Question, uid=Depends(user), conn=Depends(db)):
    v = version(conn, tid, uid)
    candidates = {s["itemId"]: s for s in v["steps"] if eligible(s)}
    content = {
        "question": data.question,
        "answer": "확인된 자료에서 답을 찾지 못했습니다.",
        "sources": [],
        "needsReview": True,
    }
    if candidates:
        schema = {
            "type": "OBJECT",
            "properties": {
                "answer": {"type": "STRING"},
                "itemIds": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "required": ["answer", "itemIds"],
        }
        try:
            reply = generate_json(
                "확인된 절차에서만 답하고 근거 itemIds를 반환하세요. 근거가 없으면 빈 배열을 반환하세요. "
                + json.dumps(
                    {"question": data.question, "steps": list(candidates.values())},
                    ensure_ascii=False,
                ),
                schema,
            )
            ids = reply["itemIds"]
            if ids and all(i in candidates for i in ids):
                content.update(
                    answer=reply["answer"],
                    sources=[ref for i in ids for ref in candidates[i]["sources"]],
                    needsReview=False,
                )
        except (KeyError, TypeError, ValueError, GeminiParseError, GeminiError):
            raise HTTPException(503, "질문을 처리하지 못했습니다.") from None
    conn.execute(
        "INSERT INTO learning_records(user_id,task_id,analysis_id,kind,content) VALUES(%s,%s,%s,'question',%s)",
        (uid, tid, v["id"], Jsonb(content)),
    )
    return content

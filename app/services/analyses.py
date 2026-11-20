import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.ai import gemini_client
from app.ai.gemini_client import GeminiError, GeminiParseError, InlineFile
from app.dao import (
    analyses as analyses_dao,
    materials as materials_dao,
    tasks as tasks_dao,
)
from app.schemas.analyses import Review, Step
from app.schemas.common import Version
from app.services.access import required, task_for
from app.services.errors import ServiceError
from app.storage import bucket


def analyze(tid: int, uid, conn):
    t = task_for(conn, tid, uid, edit=True)
    files = [f for f in materials_dao.list_active(conn, tid) if f["status"] == "ready"]
    if not {"previous_form", "manual"} <= {f["kind"] for f in files}:
        raise ServiceError(422, "기존 자료와 새 매뉴얼이 필요합니다.")
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
            raw = gemini_client.generate_json(prompt, schema, docs)
            steps = [Step(**s, itemId=uuid4(), confirmed=False) for s in raw]
            if not steps or any(
                src.fileId not in {f["id"] for f in files}
                for s in steps
                for src in s.sources
            ):
                raise ValueError()
        except (ValueError, TypeError, KeyError, GeminiError, GeminiParseError):
            raise ServiceError(503, "분석 결과를 확인할 수 없습니다.") from None
    return {"inputFileIds": [f["id"] for f in files], "steps": steps}


def review(tid: int, data: Review, uid, conn):
    t = task_for(conn, tid, uid, edit=True)
    if data.share and t["kind"] != "company":
        raise ServiceError(422, "개인 공간에서는 공유할 수 없습니다.")
    files = {
        r["id"] for r in materials_dao.lock_ready_ids(conn, tid, data.inputFileIds)
    }
    if files != set(data.inputFileIds) or len({s.itemId for s in data.steps}) != len(
        data.steps
    ):
        raise ServiceError(422, "파일 소속과 단계 ID를 확인하세요.")
    for step in data.steps:
        if any(s.fileId not in files for s in step.sources) or (
            step.confirmed and (not step.sources or step.change == "미확인")
        ):
            raise ServiceError(422, "확인된 단계에는 등록 자료의 근거가 필요합니다.")
    row = analyses_dao.insert_review(
        conn, tid, data.inputFileIds, [s.model_dump(mode="json") for s in data.steps]
    )
    if data.share:
        tasks_dao.publish_review(conn, row["id"], tid)
    else:
        tasks_dao.touch(conn, tid)
    return row


def unshare(tid: int, uid, conn):
    task_for(conn, tid, uid, edit=True)
    tasks_dao.unpublish(conn, tid)


def share_reviewed(tid: int, data: Version, uid, conn):
    t = task_for(conn, tid, uid, edit=True)
    if t["kind"] != "company":
        raise ServiceError(422, "회사 공간에서만 공유할 수 있습니다.")
    required(analyses_dao.find_confirmed(conn, data.analysisId, tid))
    return tasks_dao.share_existing(conn, data.analysisId, tid)

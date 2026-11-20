import json
from uuid import UUID, uuid4

from app.ai import gemini_client
from app.ai.gemini_client import GeminiError, GeminiParseError
from app.dao import (
    analyses as analyses_dao,
    materials as materials_dao,
    tasks as tasks_dao,
)
from app.schemas.analyses import AnalysisRequest, ItemPatch, Review, Step
from app.schemas.common import Version
from app.services.access import required, task_for
from app.services.errors import ServiceError
from app.services.files import inline_files, source_view


def analyze(tid: int, data: AnalysisRequest | None, uid, conn):
    t = task_for(conn, tid, uid, edit=True)
    files = [f for f in materials_dao.list_active(conn, tid) if f["status"] == "ready"]
    if data and data.fileIds is not None:
        chosen = set(data.fileIds)
        if len(chosen) != len(data.fileIds) or not chosen <= {f["id"] for f in files}:
            raise ServiceError(422, "분석할 자료는 이 업무의 준비된 자료에서 고르세요.")
        files = [f for f in files if f["id"] in chosen]
    if not {"previous_form", "manual"} <= {f["kind"] for f in files}:
        raise ServiceError(422, "기존 자료와 새 매뉴얼이 필요합니다.")
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
    with inline_files(files) as docs:
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
    file_ids = [f["id"] for f in files]
    # 확정 전 초안으로 저장해 비교표 조회·항목 수정에 쓴다. 검토 제출은 새 행을 만든다.
    row = analyses_dao.insert_draft(
        conn, tid, file_ids, [s.model_dump(mode="json") for s in steps]
    )
    return {"analysisId": row["id"], "inputFileIds": file_ids, "steps": steps}


def item_view(step: dict, index: int) -> dict:
    return {
        "id": step["itemId"],
        "step": index + 1,
        "before": step.get("before", ""),
        "after": step.get("after", ""),
        "change": step.get("change"),
        "requiredFields": step.get("requiredFields", []),
        "caution": step.get("caution", ""),
        "source": source_view(step.get("sources")),
        "sources": step.get("sources", []),
        "confirmed": step.get("confirmed", False),
    }


def comparison(aid: int, uid, conn):
    row = required(analyses_dao.find(conn, aid))
    t = task_for(conn, row["task_id"], uid)
    if t["created_by"] != uid and t["shared_analysis_id"] != row["id"]:
        raise ServiceError(404, "접근 가능한 항목이 없습니다.")
    return {
        "analysisId": row["id"],
        "taskId": row["task_id"],
        "inputFileIds": row["input_file_ids"],
        "confirmed": row["confirmed_at"] is not None,
        "confirmedAt": row["confirmed_at"],
        "items": [item_view(s, i) for i, s in enumerate(row["steps"])],
    }


def update_item(item_id: UUID, data: ItemPatch, uid, conn):
    row = required(analyses_dao.lock_with_item(conn, str(item_id)))
    task_for(conn, row["task_id"], uid, edit=True)
    if row["confirmed_at"] is not None:
        raise ServiceError(409, "확정된 분석은 수정할 수 없습니다. 다시 분석하세요.")
    steps = row["steps"]
    index = next(i for i, s in enumerate(steps) if s.get("itemId") == str(item_id))
    changes = data.model_dump(exclude_none=True)
    step = Step(**{**steps[index], **changes})
    if step.confirmed and (not step.sources or step.change == "미확인"):
        raise ServiceError(422, "확인된 단계에는 등록 자료의 근거가 필요합니다.")
    steps[index] = step.model_dump(mode="json")
    analyses_dao.update_steps(conn, row["id"], steps)
    return item_view(steps[index], index)


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

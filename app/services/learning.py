import json

from app.ai import gemini_client
from app.ai.gemini_client import GeminiError, GeminiParseError
from app.dao import analyses as analyses_dao, learning as learning_dao
from app.schemas.learning import Answers, Question, Selection
from app.services.access import eligible, required, version
from app.services.errors import ServiceError
from app.services.files import source_view


def guide(tid: int, uid, conn):
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
            items = gemini_client.generate_json(prompt, schema)
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


def practice(tid: int, data: Selection, uid, conn):
    v = version(conn, tid, uid)
    keys = {str(k) for k in data.selectedItemIds}
    steps = [s for s in v["steps"] if str(s.get("itemId")) in keys and eligible(s)]
    if v["id"] != data.analysisId or len(steps) != len(keys):
        raise ServiceError(409, "검토 버전 또는 선택한 단계를 다시 확인하세요.")
    from app.ai.prompts import PRACTICE_PROMPT, build_grounding
    from copy import deepcopy
    from app.ai.schemas import PRACTICE_SCHEMA

    schema = deepcopy(PRACTICE_SCHEMA)
    question_schema = schema["properties"]["questions"]["items"]
    question_schema["properties"]["itemId"] = {"type": "STRING"}
    question_schema["required"].append("itemId")
    indexed = {s["itemId"]: s for s in steps}
    try:
        quiz = gemini_client.generate_json(
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
        raise ServiceError(503, "연습 문제를 생성하지 못했습니다.") from None
    record = learning_dao.insert_practice(
        conn, uid, tid, v["id"], {**quiz, "selectedItemIds": sorted(keys)}
    )
    return {
        **record,
        "situation": quiz["situation"],
        "questions": [
            {"prompt": q["prompt"], "choices": q["choices"]} for q in questions
        ],
    }


def _grade(questions: list[dict], answers: list[int]) -> list[bool]:
    return [a == q["correct_index"] for a, q in zip(answers, questions)]


def answer(pid: int, data: Answers, uid, conn):
    r = required(learning_dao.lock_practice(conn, pid, uid))
    content = r["content"]
    questions = content["questions"]
    if len(data.answers) != len(questions) or any(
        not 0 <= a < len(q["choices"]) for a, q in zip(data.answers, questions)
    ):
        raise ServiceError(422, "각 문제의 답을 선택하세요.")
    if data.reasons is not None and len(data.reasons) != len(questions):
        raise ServiceError(422, "선택 이유는 문제 수와 같은 개수로 보내세요.")
    reasons = data.reasons or [None] * len(questions)
    content["answers"] = data.answers
    content["reasons"] = reasons
    learning_dao.save_answers(conn, content, pid)
    correct = _grade(questions, data.answers)
    return {
        "questions": questions,
        "answers": data.answers,
        "reasons": reasons,
        "correct": correct,
        "score": {"correct": sum(correct), "total": len(questions)},
    }


def result(pid: int, uid, conn):
    r = required(learning_dao.find_practice(conn, pid, uid))
    content = r["content"]
    if "answers" not in content:
        raise ServiceError(409, "아직 답안을 제출하지 않았습니다.")
    questions, answers = content["questions"], content["answers"]
    reasons = content.get("reasons") or [None] * len(questions)
    analysis = analyses_dao.find(conn, r["analysis_id"])
    sources = {
        s.get("itemId"): s.get("sources") for s in (analysis or {}).get("steps", [])
    }
    correct = _grade(questions, answers)
    return {
        "practiceId": r["id"],
        "situation": content.get("situation"),
        "score": {"correct": sum(correct), "total": len(questions)},
        "answers": [
            {
                "questionId": i,
                "prompt": q["prompt"],
                "selectedOptionId": a,
                "correctOptionId": q["correct_index"],
                "correct": ok,
                "reason": reason,
                "feedback": ("정답입니다. " if ok else "오답입니다. ")
                + q.get("explanation", ""),
                "source": source_view(sources.get(q.get("itemId"))),
            }
            for i, (q, a, ok, reason) in enumerate(
                zip(questions, answers, correct, reasons)
            )
        ],
    }


def ask(tid: int, data: Question, uid, conn):
    v = version(conn, tid, uid)
    candidates = {s["itemId"]: s for s in v["steps"] if eligible(s)}
    content = {
        "question": data.question,
        "answer": "확인된 자료에서 답을 찾지 못했습니다.",
        "sources": [],
        "itemIds": [],
        "needsReview": True,
        # 자료로 답할 수 없을 때 담당자에게 확인할 질문
        "followUpQuestion": data.question,
    }
    if candidates:
        schema = {
            "type": "OBJECT",
            "properties": {
                "answer": {"type": "STRING"},
                "itemIds": {"type": "ARRAY", "items": {"type": "STRING"}},
                "followUpQuestion": {"type": "STRING"},
            },
            "required": ["answer", "itemIds", "followUpQuestion"],
        }
        try:
            reply = gemini_client.generate_json(
                "확인된 절차에서만 답하고 근거 itemIds를 반환하세요. 근거가 없으면 빈 배열을 반환하세요. "
                "답이 불완전하거나 자료로 확인할 수 없는 부분이 있으면 담당자에게 확인할 질문 한 문장을 "
                "followUpQuestion에 쓰고, 없으면 빈 문자열을 쓰세요. "
                + json.dumps(
                    {"question": data.question, "steps": list(candidates.values())},
                    ensure_ascii=False,
                ),
                schema,
            )
            ids = reply["itemIds"]
            follow_up = reply.get("followUpQuestion")
            follow_up = follow_up.strip() if isinstance(follow_up, str) else ""
            if ids and all(i in candidates for i in ids):
                content.update(
                    answer=reply["answer"],
                    sources=[ref for i in ids for ref in candidates[i]["sources"]],
                    itemIds=ids,
                    needsReview=False,
                    followUpQuestion=follow_up or None,
                )
            elif follow_up:
                content["followUpQuestion"] = follow_up
        except (KeyError, TypeError, ValueError, GeminiParseError, GeminiError):
            raise ServiceError(503, "질문을 처리하지 못했습니다.") from None
    learning_dao.insert_question(conn, uid, tid, v["id"], content)
    return content


def history(uid, conn):
    return learning_dao.list_history(conn, uid)


def history_detail(rid: int, uid, conn):
    r = required(learning_dao.find_record(conn, rid, uid))
    content = r["content"]
    if r["kind"] == "practice" and "answers" not in content:
        # 답안 제출 전에는 정답과 해설을 보여 주지 않는다.
        content = {
            "situation": content.get("situation"),
            "selectedItemIds": content.get("selectedItemIds", []),
            "questions": [
                {"prompt": q["prompt"], "choices": q["choices"]}
                for q in content.get("questions", [])
            ],
        }
    answered = r["kind"] == "practice" and "answers" in r["content"]
    return {**r, "content": content, "answered": answered}

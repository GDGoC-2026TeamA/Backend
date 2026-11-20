from pathlib import Path

from .gemini_client import InlineFile, generate_json
from .prompts import (
    ANALYZE_WORKFLOW_PROMPT,
    PRACTICE_PROMPT,
    QA_PROMPT,
    build_grounding,
)
from .schemas import ANALYZE_WORKFLOW_SCHEMA, PRACTICE_SCHEMA, QA_SCHEMA


def analyze_workflow(description: str, files: list[InlineFile]) -> dict:
    """F-02 업무 구조 분석."""
    prompt = ANALYZE_WORKFLOW_PROMPT.format(
        description=description, grounding=build_grounding()
    )
    return generate_json(prompt, ANALYZE_WORKFLOW_SCHEMA, files=files)


def answer_question(
    question: str, sources: list[dict], files: list[InlineFile] | None = None
) -> dict:
    """
    F-07 업무 질의응답.
    sources 예: [{"name": "재고관리_매뉴얼.pdf", "text": "..."}]
    텍스트로 추출된 자료를 넣거나, files로 원본을 함께 보낼 수 있다.
    """
    source_text = "\n\n".join(f"[{s['name']}]\n{s['text']}" for s in sources)
    prompt = QA_PROMPT.format(
        question=question,
        sources=source_text or "(제공된 텍스트 자료 없음)",
        grounding=build_grounding(),
    )
    return generate_json(prompt, QA_SCHEMA, files=files, temperature=0.1)


def generate_practice(steps: list[dict]) -> dict:
    """F-05 상황별 연습 콘텐츠. steps는 확정된 절차만 받는다."""
    if not steps:
        raise ValueError("확정된 절차가 없으면 연습을 만들지 않는다 (F-05 수용 기준)")
    prompt = PRACTICE_PROMPT.format(
        steps="\n".join(
            f"{s['order']}. {s['title']}: {s['description']}" for s in steps
        ),
        grounding=build_grounding(),
    )
    return generate_json(prompt, PRACTICE_SCHEMA)

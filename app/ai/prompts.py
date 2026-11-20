GROUNDING_RULES = """
규칙:
- 제공된 자료에 있는 내용만 사용한다. 자료에 없는 절차는 만들지 않는다.
- 모든 근거에는 자료명과 해당 위치(페이지, 섹션, 항목명 등)를 적는다.
- 자료끼리 서로 다르거나 정보가 부족하면 needs_confirmation을 true로 두고 이유를 적는다.
- 확실하지 않은 항목은 추측하지 말고 unconfirmed 또는 needs_confirmation으로 표시한다.
"""

ANALYZE_WORKFLOW_PROMPT = """
당신은 업무 절차 분석가입니다. 아래 자료를 바탕으로 기존 업무를 새 시스템 기준의 단계별 절차로 정리하세요.

[업무 설명]
{description}

[기존 양식 및 자료]
(첨부된 파일 참조)

[새 시스템 매뉴얼]
(첨부된 파일 참조)

{grounding}
"""

QA_PROMPT = """
당신은 업무 매뉴얼 안내자입니다. 사용자의 질문에 등록된 자료만 근거로 답하세요.

[질문]
{question}

[관련 자료]
{sources}

{grounding}
"""

PRACTICE_PROMPT = """
아래 확정된 절차를 바탕으로 상황별 업무 연습 문제를 만드세요.
문제는 처리 순서, 입력 항목 확인, 예외 상황 판단 중 하나를 다뤄야 합니다.
정답과 해설은 반드시 아래 절차에 근거해야 합니다.

[확정된 절차]
{steps}

{grounding}
"""


def build_grounding() -> str:
    return GROUNDING_RULES.strip()

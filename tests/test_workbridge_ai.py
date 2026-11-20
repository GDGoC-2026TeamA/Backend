# 파일명: tests/test_workbridge_ai.py
# 실행 명령어 (백엔드 개발자용 - 서버 실행 후):
#   BASE_URL=http://localhost:8000 pytest tests/test_workbridge_ai.py -v

import os
import pytest
import requests

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# =============================================================================
# 테스트용 내장 샘플 데이터 (세트 1: 재고 기록 / 세트 2: 예약 접수)
# =============================================================================
INVENTORY_OLD_MANUAL = """
[기존 업무 방식: 일일 재고 변동 엑셀 장부 기록]
1. 매일 오후 4시 물류팀 메신저 메모를 받아 [날짜 | 품목명 | 수량 | 비고] 4개 항목을 엑셀에 수기 입력한다.
2. 고객 반품 건은 정상·파손 구분 없이 전체 재고 수량에 '+'로 합산한다.
3. 잔여 재고가 10개 미만인 품목은 엑셀 셀에 노란색 음영을 칠해 구매팀 카톡으로 발주를 요청한다.
"""

INVENTORY_NEW_MANUAL = """
[신규 스마트 ERP 재고 기록 표준 지침]
1. 처리 순서: (1) 품목코드 확인 -> (2) 처리구분 분류 -> (3) 필수 5개 항목[처리구분, 품목코드, 품목명, 수량, 처리상태]과 선택 1개 항목[근거/비고] 총 6개 양식 작성 -> (4) 미확인 항목 분리 후 저장
2. 처리구분 기준:
   - 신규 입고: '정상입고' (처리상태: 확정)
   - 고객 반품: 정상 제품은 '반품정상입고'(처리상태: 확정), 파손 제품은 반드시 '불량창고이동'(처리상태: 확정)으로 행을 분리해 기록
   - 재고 부족: 잔여 재고가 안전재고(10개) 미만인 품목은 '전자발주대상'(처리상태: 승인대기)으로 별도 행 추가
3. 예외 원칙: 매뉴얼에 처리 기준이 없거나 지침 간 내용이 충돌하는 건은 AI가 임의 확정하지 않고 '미확인(담당자검토)'으로 표시한다.

[시스템 공지사항 - 최근 정책 변경]
- 자동 전자발주 기준을 안전재고 5개 미만 품목부터 적용하는 것으로 변경함.
"""

INVENTORY_TODAY_WORK = """
[2026-11-20 오후 4시 물류팀 전달 내역]
- 신규 입고: 스텐 텀블러(A-101) 30개 정상 입고됨.
- 고객 반품: 세라믹 머그컵(B-205) 3개 반품 접수됨 (2개 정상, 1개 손잡이 파손).
- 재고 부족 알림: 알루미늄 노트북 거치대(C-301) 현재 창고 잔여 수량 7개 남음.
- 특이 건: 드립백 원두(D-401) 4박스 유통기한이 내일모레까지인데 새 시스템 장부에 어떻게 올릴지 문의 옴.
"""

RESERVATION_OLD_MANUAL = """
[기존 업무 방식: 상담 예약 접수 및 일정 관리]
1. 전화로 접수한 [방문일시 | 고객명 | 연락처 | 메모]를 데스크 탁상 달력에 볼펜으로 적는다.
2. 시간 변경 요청이 오면 달력 글씨를 수정액으로 지우고 새 날짜 칸에 다시 적는다.
"""

RESERVATION_NEW_MANUAL = """
[신규 CRM 예약센터 기록 표준 지침]
1. 접수된 예약 요청을 필수 5개 항목[접수유형, 고객명, 연락처, 희망일시, 처리상태]과 선택 1개 항목[근거/비고] 총 6개 양식으로 정리한다.
2. 접수유형 분류 기준:
   - 신규 상담 예약: '신규예약등록' (처리상태: 등록대기)
   - 기존 예약 시간 변경: 기존 건을 취소하지 말고 '일정변경'으로 분류 (처리상태: 수정대기)
   - 예약 시간 15분 경과 미방문: '노쇼확정'으로 분류 (처리상태: 패널티대상)
3. 매뉴얼에 없는 단체 예약(5인 이상)이나 충돌 건은 '미확인(담당자검토)'으로 표시한다.
"""


# =============================================================================
# 공통 인증 Fixture (서버 미실행 CI 환경에서는 자동 Skip 처리)
# =============================================================================
def get_auth_headers(email: str, password: str) -> dict:
    try:
        res = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=5,
        )
    except requests.exceptions.RequestException:
        pytest.skip(
            f"실행 중인 백엔드 서버({BASE_URL})가 없어 API 통합 QA 테스트를 건너뜁니다."
        )

    assert res.status_code == 200, f"로그인 실패 ({email}): {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def user1_headers():
    return get_auth_headers("test1@workbridge.kr", "Test1234!")


@pytest.fixture(scope="module")
def user2_headers():
    return get_auth_headers("test2@workbridge.kr", "Test1234!")


# =============================================================================
# 1. 기준 자료 분석: 확정/미확인 분리 & 먼저 익힐 내용 추천 (QA 3, 19, 20번)
# =============================================================================
@pytest.fixture(scope="module")
def inventory_analysis(user1_headers):
    payload = {
        "taskId": "inventory",
        "oldManualText": INVENTORY_OLD_MANUAL,
        "newManualText": INVENTORY_NEW_MANUAL,
    }
    res = requests.post(
        f"{BASE_URL}/api/analyses",
        json=payload,
        headers=user1_headers,
        timeout=30,
    )
    assert res.status_code in (200, 201), f"자료 분석 API 실패: {res.text}"
    return res.json()


def test_qa03_19_confirmed_and_unconfirmed_separation(inventory_analysis):
    """[QA 3, 19] 확정된 절차와 미확인 항목(기준 충돌·누락) 분리 응답 검증"""
    confirmed = inventory_analysis.get("confirmedProcedures", [])
    unconfirmed = inventory_analysis.get("unconfirmedItems", [])

    assert len(confirmed) > 0, "확정된 절차 리스트가 비어 있습니다."
    assert len(unconfirmed) >= 2, "기준 충돌(안전재고) 및 누락(유통기한) 2건 이상이 미확인으로 감지되어야 합니다."

    unconfirmed_blob = " ".join(str(item) for item in unconfirmed)
    assert "안전재고" in unconfirmed_blob or "10개" in unconfirmed_blob, (
        "안전재고 기준 충돌(10개 vs 5개)이 미확인 항목에 포함되지 않았습니다."
    )
    assert "유통기한" in unconfirmed_blob, (
        "매뉴얼에 없는 유통기한 임박 처리 기준이 미확인 항목으로 감지되지 않았습니다."
    )

    confirmed_blob = " ".join(str(item) for item in confirmed)
    assert "불량창고이동" in confirmed_blob, "파손 반품 분리 규칙이 확정 절차에 포함되어야 합니다."


def test_qa20_first_to_learn_recommendations(inventory_analysis):
    """[QA 20] 먼저 익힐 내용 추천 항목에 추천 이유와 자료 근거가 포함되는지 검증"""
    recommendations = inventory_analysis.get("recommendations", [])
    assert len(recommendations) > 0, "먼저 익힐 내용 추천 리스트가 생성되지 않았습니다."

    for rec in recommendations:
        assert rec.get("title"), "추천 항목 제목(title)이 누락되었습니다."
        assert rec.get("reason"), "추천 이유(reason)가 누락되었습니다."
        assert rec.get("evidence"), "자료 근거(evidence)가 누락되었습니다."
        assert "유통기한" not in rec["title"], "미확인 항목이 추천 학습 항목으로 잘못 출제되었습니다."


# =============================================================================
# 2. 업무별 연습 문제 동적 출제 검증 (QA 5, 21, 22번)
# =============================================================================
def test_qa21_quiz_generated_only_from_confirmed_procedures(user1_headers, inventory_analysis):
    """[QA 5, 21] taskId + analysisId 기준 확정 절차에서만 출제되고 미확인 항목 제외 검증"""
    analysis_id = inventory_analysis["analysisId"]
    res = requests.post(
        f"{BASE_URL}/api/quizzes/generate",
        json={"taskId": "inventory", "analysisId": analysis_id},
        headers=user1_headers,
        timeout=30,
    )
    assert res.status_code == 200, f"연습 문제 생성 API 실패: {res.text}"

    quizzes = res.json().get("quizzes", [])
    assert len(quizzes) >= 2, "최소 2문항 이상의 연습 문제가 생성되어야 합니다."

    for q in quizzes:
        assert q.get("question"), "문제 지문이 비어 있습니다."
        assert len(q.get("options", [])) >= 2, "선택지가 2개 이상 있어야 합니다."
        assert q.get("answer") is not None, "정답(answer)이 누락되었습니다."
        assert q.get("explanation"), "해설(explanation) 및 매뉴얼 근거가 누락되었습니다."

        full_text = f"{q['question']} {q['explanation']}"
        assert "유통기한" not in full_text, "기준 누락(미확인) 항목인 유통기한 문제가 출제되었습니다."
        assert "5개 미만" not in full_text, "기준 충돌(미확인) 항목인 안전재고 5개 기준이 출제되었습니다."


def test_qa22_dynamic_quiz_switches_on_different_task(user1_headers):
    """[QA 22] 다른 업무 자료(예약 접수) 등록 시 새 매뉴얼에 맞게 문제와 해설이 동적 변경되는지 검증"""
    ana_res = requests.post(
        f"{BASE_URL}/api/analyses",
        json={
            "taskId": "reservation",
            "oldManualText": RESERVATION_OLD_MANUAL,
            "newManualText": RESERVATION_NEW_MANUAL,
        },
        headers=user1_headers,
        timeout=30,
    )
    assert ana_res.status_code in (200, 201), f"예약 접수 분석 실패: {ana_res.text}"
    res_analysis_id = ana_res.json()["analysisId"]

    quiz_res = requests.post(
        f"{BASE_URL}/api/quizzes/generate",
        json={"taskId": "reservation", "analysisId": res_analysis_id},
        headers=user1_headers,
        timeout=30,
    )
    assert quiz_res.status_code == 200, f"예약 접수 문제 출제 실패: {quiz_res.text}"

    quizzes_blob = " ".join(
        f"{q['question']} {q['explanation']}" for q in quiz_res.json().get("quizzes", [])
    )
    assert "불량창고이동" not in quizzes_blob, "이전 업무(재고 기록) 문제가 그대로 남아 있습니다."
    assert any(k in quizzes_blob for k in ["일정변경", "노쇼확정", "신규예약등록"]), (
        "새로 등록한 예약 접수 매뉴얼 기반 문제로 전환되지 않았습니다."
    )
    assert "단체 예약" not in quizzes_blob, "예약 매뉴얼의 미확인 항목(5인 이상 단체)이 출제되었습니다."


# =============================================================================
# 3. 근거 기반 AI 질의응답 & 이전 대화 내역 유지 (QA 6, 16번)
# =============================================================================
def test_qa06_16_grounded_qa_and_chat_history(user1_headers, inventory_analysis):
    """[QA 6, 16] 매뉴얼 근거 답변 vs 없는 내용 미확인 처리 및 대화 내역 저장 검증"""
    analysis_id = inventory_analysis["analysisId"]

    res_in = requests.post(
        f"{BASE_URL}/api/chats",
        json={
            "taskId": "inventory",
            "analysisId": analysis_id,
            "question": "파손된 머그컵 반품은 어떻게 처리해야 하나요?",
        },
        headers=user1_headers,
        timeout=20,
    )
    assert res_in.status_code == 200
    data_in = res_in.json()
    assert "불량창고이동" in data_in.get("answer", ""), "매뉴얼에 있는 핵심 처리구분을 답변하지 못했습니다."
    assert data_in.get("evidence"), "답변의 매뉴얼 근거(evidence)가 누락되었습니다."

    res_out = requests.post(
        f"{BASE_URL}/api/chats",
        json={
            "taskId": "inventory",
            "analysisId": analysis_id,
            "question": "창고에서 상품이 분실되었을 때 처리 절차는 무엇인가요?",
        },
        headers=user1_headers,
        timeout=20,
    )
    assert res_out.status_code == 200
    data_out = res_out.json()
    assert data_out.get("status") == "UNCONFIRMED" or "미확인" in data_out.get("answer", ""), (
        "매뉴얼에 없는 내용을 AI가 추측해 답변했습니다 (할루시네이션 발생)."
    )

    hist_res = requests.get(
        f"{BASE_URL}/api/chats?taskId=inventory",
        headers=user1_headers,
        timeout=10,
    )
    assert hist_res.status_code == 200
    history = hist_res.json().get("messages", [])
    assert len(history) >= 2, "이전 AI 질의응답 내역이 저장되지 않았습니다."


# =============================================================================
# 4. 오늘 작업 자료 AI 초안 생성 & 미확인 분류 (QA 9, 10번)
# =============================================================================
def test_qa09_10_ai_work_draft_generation(user1_headers, inventory_analysis):
    """[QA 9, 10] 6개 컬럼 양식 변환, 행별 근거 표시, 충돌·누락 건 미확인 분류 검증"""
    res = requests.post(
        f"{BASE_URL}/api/drafts/generate",
        json={
            "taskId": "inventory",
            "analysisId": inventory_analysis["analysisId"],
            "workText": INVENTORY_TODAY_WORK,
        },
        headers=user1_headers,
        timeout=30,
    )
    assert res.status_code == 200, f"AI 작업 초안 생성 실패: {res.text}"

    rows = res.json().get("rows", [])
    assert len(rows) == 5, f"반품 정상/파손 분리를 포함해 총 5행이 생성되어야 합니다. (실제: {len(rows)}행)"

    required_keys = {"처리구분", "품목코드", "품목명", "수량", "처리상태", "근거/비고"}
    row_by_code = {}
    for row in rows:
        assert required_keys.issubset(row.keys()), f"필수 컬럼 누락: {required_keys - set(row.keys())}"
        assert row["근거/비고"], f"{row['품목코드']} 행에 매뉴얼 근거가 누락되었습니다."
        row_by_code.setdefault(row["품목코드"], []).append(row)

    assert "미확인" in row_by_code["C-301"][0]["처리상태"], "기준 충돌 품목(C-301)이 미확인으로 분류되지 않았습니다."
    assert "미확인" in row_by_code["D-401"][0]["처리상태"], "기준 누락 품목(D-401)이 미확인으로 분류되지 않았습니다."


# =============================================================================
# 5. 계정별 데이터 격리 검증 (QA 15번)
# =============================================================================
def test_qa15_user_data_isolation(user2_headers, inventory_analysis):
    """[QA 15] 다른 계정(user2)으로 로그인 시 user1의 분석 결과 및 저장 데이터 접근 차단 검증"""
    analysis_id = inventory_analysis["analysisId"]
    res = requests.get(
        f"{BASE_URL}/api/analyses/{analysis_id}",
        headers=user2_headers,
        timeout=10,
    )
    assert res.status_code in (403, 404), (
        f"보안 오류: 타 계정(test2)이 test1의 분석 데이터({analysis_id})에 접근할 수 있습니다. (상태코드: {res.status_code})"
    )

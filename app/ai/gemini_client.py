import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from config import GEMINI_API_KEY, GEMINI_BASE_URL, GEMINI_MODEL


class GeminiError(Exception):
    """API 호출 실패 (네트워크, 4xx, 재시도 후 5xx)."""


class GeminiParseError(Exception):
    """응답은 왔지만 JSON 파싱 또는 스키마 검증에 실패."""


RETRYABLE_STATUS = {429, 500, 502, 503, 504}
DEFAULT_TIMEOUT = 60  # 초
MAX_RETRIES = 3


@dataclass
class InlineFile:
    """PDF나 화면 캡처를 요청에 직접 실어 보낼 때 사용."""

    path: Path
    mime_type: str  # 예: "application/pdf", "image/png"

    def to_part(self) -> dict:
        data = base64.b64encode(self.path.read_bytes()).decode("utf-8")
        return {"inlineData": {"mimeType": self.mime_type, "data": data}}


def _endpoint() -> str:
    return f"{GEMINI_BASE_URL.rstrip('/')}/{GEMINI_MODEL}:generateContent"


def _post_with_retry(payload: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                _endpoint(), headers=headers, json=payload, timeout=DEFAULT_TIMEOUT
            )
        except requests.RequestException as e:
            last_error = e
        else:
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code not in RETRYABLE_STATUS:
                # 400, 401, 403 등은 재시도해도 의미가 없다
                raise GeminiError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            last_error = GeminiError(f"HTTP {resp.status_code}")
        time.sleep(2**attempt)  # 1s, 2s, 4s
    raise GeminiError(f"재시도 {MAX_RETRIES}회 실패: {last_error}")


def generate_json(
    prompt: str,
    response_schema: dict,
    files: list[InlineFile] | None = None,
    temperature: float = 0.2,
) -> dict:
    """
    프롬프트와 선택적 파일을 보내고, JSON 객체로 파싱해 돌려준다.
    response_schema는 Gemini가 지원하는 OpenAPI 부분집합 형식이다.
    """
    parts = [{"text": prompt}]
    if files:
        parts = [f.to_part() for f in files] + parts

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        },
    }

    body = _post_with_retry(payload)

    candidates = body.get("candidates") or []
    if not candidates:
        # 안전 필터 등으로 후보가 비어 있을 수 있다
        reason = body.get("promptFeedback", {}).get("blockReason", "unknown")
        raise GeminiParseError(f"응답 후보 없음 (blockReason={reason})")

    candidate = candidates[0]
    finish = candidate.get("finishReason", "")
    text = "".join(p.get("text", "") for p in candidate["content"]["parts"])

    if finish == "MAX_TOKENS":
        raise GeminiParseError("출력이 토큰 한도에서 잘림")

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise GeminiParseError(f"JSON 파싱 실패: {e}; 앞부분: {text[:200]}") from e

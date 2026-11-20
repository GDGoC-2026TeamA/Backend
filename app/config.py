import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_BASE_URL = os.environ.get(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/models"
)

# Gemini 요청 한 번에 직접 실어 보낼 수 있는 파일 합계(MB, 원본 기준).
# Gemini는 요청 전체를 약 20MB로 제한하고, 파일은 base64로 바뀌며 약 4/3배 커진다.
# 기본값 14MB는 base64 후 약 18.7MB로, 프롬프트를 더해도 한도 안에 들어간다.
# 파일 하나도 이 값을 넘으면 AI에 보낼 수 없으므로 업로드 한도로도 쓴다.
GEMINI_MAX_INLINE_MB = float(os.environ.get("GEMINI_MAX_INLINE_MB", "14"))
GEMINI_MAX_INLINE_BYTES = int(GEMINI_MAX_INLINE_MB * 1024 * 1024)

# Backend
## 로컬 실행 (Windows PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

VS Code에서 Python 인터프리터로 `.venv\Scripts\python.exe`를 선택합니다.

- API 문서: [https://gdgoc2026a.up.railway.app/docs](https://gdgoc2026a.up.railway.app/docs)
- 상태 확인: [https://gdgoc2026a.up.railway.app/health](https://gdgoc2026a.up.railway.app/health)

## 테스트

```bash
# Linux / macOS
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest

# 실제 Gemini API 연결까지 확인 (토큰 사용)
GEMINI_LIVE_TEST=1 .venv/bin/python -m pytest tests/test_gemini_client.py::test_live_gemini_connection
```

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

# Backend
## 로컬 실행 (Windows PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

VS Code에서 Python 인터프리터로 `.venv\Scripts\python.exe`를 선택합니다.

- API 문서: http://127.0.0.1:8000/docs
- 상태 확인: http://127.0.0.1:8000/health

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

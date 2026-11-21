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

## 백엔드 로그인 API

- 이메일 로그인은 `POST /api/v1/sessions/email`에 `{"email":"member@example.com","password":"…"}`을 보냅니다.
- Google과 카카오는 브라우저에서 `GET /api/v1/sessions/social/google/start` 또는 `GET /api/v1/sessions/social/kakao/start`를 엽니다. 제공자 인증을 마치면 백엔드 콜백에서 `{"token":"…"}`을 반환합니다. 보호 API에는 이 토큰을 `Authorization: Bearer <token>`으로 보냅니다. 세션 유효 기간은 8시간입니다.
- 첫 소셜 로그인은 제공자와 검증된 OIDC subject로 계정을 생성합니다. 다음 로그인은 같은 계정을 사용합니다. 이메일이 같아도 다른 방식으로 가입한 계정과 자동 연결하지 않습니다.

### Railway 백엔드 서비스 설정

1. `OAUTH_SESSION_SECRET`에 무작위 비밀값을 등록합니다(예: `python -c "import secrets; print(secrets.token_urlsafe(32))"`). 모든 백엔드 인스턴스에서 같은 값을 사용합니다. 인증 도중 사용하는 서명 쿠키는 HTTPS 전용이며 10분 후 만료됩니다.
2. [Google Cloud](https://developers.google.com/identity/openid-connect/openid-connect)에서 웹 애플리케이션 OAuth 클라이언트를 발급합니다. 승인된 리디렉션 URI에 `https://<백엔드 도메인>/api/v1/sessions/social/google/callback`을 추가하고, Railway에 `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`를 등록합니다.
3. [Kakao Developers](https://developers.kakao.com/docs/en/kakaologin/rest-api)에서 카카오 로그인 및 OpenID Connect를 활성화하고 로그인용 Client Secret을 설정합니다. Redirect URI에 `https://<백엔드 도메인>/api/v1/sessions/social/kakao/callback`을 추가하고, Railway에 `KAKAO_CLIENT_ID`(REST API 키), `KAKAO_CLIENT_SECRET`, `KAKAO_REDIRECT_URI`를 등록합니다.
4. 브라우저 프론트 연동 시 DB에 `db/migrations/003_social_login_codes.sql`을 한 번 적용하고 `SOCIAL_FRONTEND_CALLBACK_URL=https://<프론트 도메인>/auth/callback`을 설정합니다. 시작 요청의 `challenge`는 탭에서 생성한 verifier의 SHA-256 base64url 값입니다. 백엔드는 제공자 콜백 검증 후 프론트에 2분짜리 일회용 코드를 URL fragment로 반환합니다. 프론트는 `POST /api/v1/sessions/social/exchange`에 `{code, verifier}`를 보내 `{token, user}`를 받습니다. challenge 없이 시작한 API 클라이언트는 기존 JSON 콜백을 사용합니다.
5. 변경 사항을 배포한 뒤 등록한 HTTPS 도메인에서 로그인 시작 URL을 엽니다. 각 `*_REDIRECT_URI`는 제공자에 등록한 값과 정확히 일치해야 합니다.

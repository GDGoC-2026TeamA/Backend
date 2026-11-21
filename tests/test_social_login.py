import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1 import social as routes
from app.database import db
from app.services import social
from app.services.errors import ServiceError
from main import service_error_response


@pytest.fixture
def login_flow(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    app.add_exception_handler(ServiceError, service_error_response)
    app.add_middleware(SessionMiddleware, secret_key="test-key", https_only=True)
    app.dependency_overrides[db] = lambda: None
    users = []

    def issue(conn, provider, subject, name):
        users.append((provider, subject, name))
        return {"token": "app-session"}

    monkeypatch.setattr(routes, "_social_session", issue)
    social.provider_client.cache_clear()
    key = RSAKey.generate_key(2048, parameters={"kid": "test"})

    def start(provider, challenge=None):
        root = f"/sessions/social/{provider}"
        client_id = f"{provider}-client"
        callback = f"https://backend.test{root}/callback"
        for suffix, value in [
            ("CLIENT_ID", client_id),
            ("CLIENT_SECRET", "test-secret"),
            ("REDIRECT_URI", callback),
        ]:
            monkeypatch.setenv(f"{provider.upper()}_{suffix}", value)
        issuer = social.ISSUERS[provider]
        claims = {
            "iss": issuer,
            "aud": client_id,
            "sub": "member-42",
            "name": "테스트",
            "iat": int(time.time()),
            "exp": int(time.time()) + 120,
        }

        def idp(request):
            if request.url.path.endswith("openid-configuration"):
                return httpx.Response(
                    200,
                    json={
                        "issuer": issuer,
                        "authorization_endpoint": issuer + "/authorize",
                        "token_endpoint": issuer + "/token",
                        "jwks_uri": issuer + "/keys",
                    },
                )
            if request.url.path == "/keys":
                return httpx.Response(200, json={"keys": [key.as_dict(private=False)]})
            assert request.url.path == "/token"
            form = parse_qs(request.content.decode())
            assert form["redirect_uri"] == [callback]
            assert form["client_secret"] == ["test-secret"]
            if provider == "google":
                assert form["code_verifier"]
            encoded = jwt.encode({"alg": "RS256", "kid": "test"}, claims, key)
            return httpx.Response(
                200,
                json={
                    "access_token": "provider-access",
                    "token_type": "Bearer",
                    "id_token": encoded,
                },
            )

        remote = social.provider_client(provider)
        remote.client_kwargs["transport"] = httpx.MockTransport(idp)
        client = TestClient(
            app, base_url="https://backend.test", follow_redirects=False
        )
        response = client.get(
            root + "/start", params={"challenge": challenge} if challenge else {}
        )
        assert response.status_code == 302
        values = parse_qs(urlsplit(response.headers["location"]).query)
        assert values["redirect_uri"] == [callback]
        claims["nonce"] = values["nonce"][0]
        return (
            client,
            callback,
            {"state": values["state"][0], "code": "test-code"},
            claims,
        )

    yield start, users
    social.provider_client.cache_clear()


@pytest.mark.parametrize("provider", ["google", "kakao"])
def test_provider_callback(login_flow, provider):
    start, users = login_flow
    client, callback, params, _ = start(provider)
    response = client.get(callback, params=params)
    assert response.status_code == 200
    assert response.json() == {"token": "app-session"}
    assert response.headers["Cache-Control"] == "no-store"
    assert users == [(provider, "member-42", "테스트")]
    assert client.get(callback, params=params).status_code == 401


@pytest.mark.parametrize("invalid", ["state", "nonce", "aud", "iss", "denied"])
def test_invalid_callback_issues_no_session(login_flow, invalid):
    start, users = login_flow
    client, callback, params, claims = start("google")
    if invalid == "state":
        params["state"] = "unknown"
    elif invalid == "denied":
        params["error"] = "access_denied"
    else:
        claims[invalid] = "other"
    assert client.get(callback, params=params).status_code == 401
    assert users == []


@pytest.mark.parametrize("provider", ["google", "kakao"])
def test_browser_redirect_after_verified_login(login_flow, monkeypatch, provider):
    start, users = login_flow
    challenge = "A" * 43
    front = "https://frontend.test/auth/callback"
    monkeypatch.setenv("SOCIAL_FRONTEND_CALLBACK_URL", front)

    def issue(conn, actual_provider, subject, name, actual_challenge):
        assert (actual_provider, subject, actual_challenge) == (
            provider,
            "member-42",
            challenge,
        )
        return "temporary-code"

    monkeypatch.setattr(routes.social_exchange, "create_code", issue)
    client, callback, params, _ = start(provider, challenge)
    response = client.get(callback, params=params)
    assert response.status_code == 303
    assert response.headers["location"] == front + "#code=temporary-code"
    assert (
        client.get(callback, params=params).headers["location"]
        == front + "#error=login_failed"
    )
    assert users == []

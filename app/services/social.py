import os
from functools import lru_cache
from typing import Literal

import httpx
from authlib.integrations.base_client import OAuthError
from authlib.integrations.starlette_client import OAuth
from joserfc.errors import JoseError

from app.services.errors import ServiceError

Provider = Literal["google", "kakao"]
ISSUERS = {"google": "https://accounts.google.com", "kakao": "https://kauth.kakao.com"}


@lru_cache(maxsize=2)
def provider_client(provider: Provider):
    prefix = provider.upper()
    client_id = os.getenv(f"{prefix}_CLIENT_ID")
    secret = os.getenv(f"{prefix}_CLIENT_SECRET")
    if not client_id or not secret:
        raise ServiceError(503, "소셜 로그인 설정이 필요합니다.")
    options = {"scope": "openid", "token_endpoint_auth_method": "client_secret_post"}
    if provider == "google":
        options.update(scope="openid profile", code_challenge_method="S256")
    return OAuth().register(
        provider,
        client_id=client_id,
        client_secret=secret,
        server_metadata_url=f"{ISSUERS[provider]}/.well-known/openid-configuration",
        client_kwargs=options,
    )


async def begin(request, provider: Provider):
    redirect_uri = os.getenv(f"{provider.upper()}_REDIRECT_URI")
    if "session" not in request.scope or not redirect_uri:
        raise ServiceError(503, "소셜 로그인 설정이 필요합니다.")
    try:
        return await provider_client(provider).authorize_redirect(request, redirect_uri)
    except httpx.HTTPError:
        raise ServiceError(502, "로그인 제공자에 연결하지 못했습니다.") from None


async def identity(request, provider: Provider):
    if "session" not in request.scope:
        raise ServiceError(503, "소셜 로그인 설정이 필요합니다.")
    try:
        if (
            not request.query_params.get("code")
            or not request.query_params.get("state")
            or request.query_params.get("error")
        ):
            raise ServiceError(401, "소셜 로그인을 다시 시작하세요.")
        token = await provider_client(provider).authorize_access_token(request)
    except (OAuthError, JoseError):
        raise ServiceError(401, "소셜 로그인을 다시 시작하세요.") from None
    except httpx.HTTPError:
        raise ServiceError(502, "로그인 제공자에 연결하지 못했습니다.") from None
    # Authlib supplies userinfo only after verifying the OIDC ID token and nonce.
    claims = (token.get("userinfo") if token.get("id_token") else None) or {}
    subject = claims.get("sub")
    if (
        claims.get("iss") != ISSUERS[provider]
        or not isinstance(subject, str)
        or not subject.strip()
    ):
        raise ServiceError(401, "소셜 계정을 확인할 수 없습니다.")
    name = claims.get("name") or claims.get("nickname")
    return subject, name.strip() if isinstance(
        name, str
    ) and name.strip() else f"{provider} 사용자"

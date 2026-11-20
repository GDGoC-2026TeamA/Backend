import os

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import router as api_router
from app.services.errors import ServiceError

app = FastAPI(title="Backend")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def database_health():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(503, detail="DB 연결 설정이 없습니다.")

    try:
        with psycopg.connect(database_url, connect_timeout=5, autocommit=True) as conn:
            conn.execute("SELECT 1").fetchone()
    except psycopg.Error:
        raise HTTPException(503, detail="DB에 연결할 수 없습니다.") from None

    return {"status": "ok", "database": "connected"}


@app.exception_handler(ServiceError)
async def service_error_response(request: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(api_router)


# 명시적으로 전달하는 Bearer 토큰만 사용한다. 쿠키 인증은 허용하지 않는다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

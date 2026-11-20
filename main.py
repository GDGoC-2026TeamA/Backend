import os

import psycopg
from fastapi import FastAPI, HTTPException

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


from app.workspaces import router as workspace_router

app.include_router(workspace_router)

from fastapi.middleware.cors import CORSMiddleware

# 명시적으로 전달하는 Bearer 토큰만 사용한다. 쿠키 인증은 허용하지 않는다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

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

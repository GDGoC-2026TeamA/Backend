"""DB에 history 테이블과 컬럼이 완성이 되면 이 문서는 고쳐야합니다."""
from psycopg.types.json import Jsonb


def fetch(conn, session_id):
    row = conn.execute(
        "SELECT contents FROM ai_histories WHERE session_id=%s", (session_id,)
    ).fetchone()
    return row["contents"] if row else None


def upsert(conn, session_id, contents):
    conn.execute(
        """INSERT INTO ai_histories(session_id,contents) VALUES(%s,%s)
        ON CONFLICT (session_id) DO UPDATE
        SET contents=EXCLUDED.contents, updated_at=now()""",
        (
            session_id,
            Jsonb(contents),
        ),
    )


def delete(conn, session_id):
    conn.execute("DELETE FROM ai_histories WHERE session_id=%s", (session_id,))

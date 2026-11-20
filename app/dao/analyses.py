from psycopg.types.json import Jsonb


def latest_visible(conn, task_id, is_owner, shared_id):
    return conn.execute(
        """SELECT id,steps,input_file_ids FROM analyses WHERE task_id=%s AND confirmed_at IS NOT NULL
        AND (%s OR id=%s) ORDER BY id DESC LIMIT 1""",
        (
            task_id,
            is_owner,
            shared_id,
        ),
    ).fetchone()


def insert_review(conn, task_id, file_ids, steps):
    return conn.execute(
        """INSERT INTO analyses(task_id,input_file_ids,steps,confirmed_at)
        VALUES(%s,%s,%s,now()) RETURNING id""",
        (
            task_id,
            file_ids,
            Jsonb(steps),
        ),
    ).fetchone()


def find_confirmed(conn, analysis_id, task_id):
    return conn.execute(
        "SELECT id FROM analyses WHERE id=%s AND task_id=%s AND confirmed_at IS NOT NULL",
        (
            analysis_id,
            task_id,
        ),
    ).fetchone()


def insert_draft(conn, task_id, file_ids, steps):
    return conn.execute(
        """INSERT INTO analyses(task_id,input_file_ids,steps)
        VALUES(%s,%s,%s) RETURNING id""",
        (
            task_id,
            file_ids,
            Jsonb(steps),
        ),
    ).fetchone()


def find(conn, analysis_id):
    return conn.execute(
        """SELECT id,task_id,input_file_ids,steps,created_at,confirmed_at
        FROM analyses WHERE id=%s""",
        (analysis_id,),
    ).fetchone()


def lock_with_item(conn, item_id):
    """itemId를 가진 분석을 잠근다. 수정 가능한 초안(확정 전)을 먼저 찾는다."""
    return conn.execute(
        """SELECT id,task_id,steps,confirmed_at FROM analyses WHERE steps @> %s
        ORDER BY (confirmed_at IS NULL) DESC,id DESC LIMIT 1 FOR UPDATE""",
        (Jsonb([{"itemId": item_id}]),),
    ).fetchone()


def update_steps(conn, analysis_id, steps):
    conn.execute(
        "UPDATE analyses SET steps=%s WHERE id=%s AND confirmed_at IS NULL",
        (
            Jsonb(steps),
            analysis_id,
        ),
    )

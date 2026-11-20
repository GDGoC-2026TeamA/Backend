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

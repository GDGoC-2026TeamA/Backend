def lock_ready_ids(conn, task_id, file_ids):
    return conn.execute(
        """SELECT id FROM files WHERE task_id=%s AND id=ANY(%s)
        AND archived_at IS NULL AND status='ready' FOR SHARE""",
        (
            task_id,
            file_ids,
        ),
    ).fetchall()


def mark_ready(conn, file_id):
    conn.execute("UPDATE files SET status='ready' WHERE id=%s", (file_id,))


def insert_pending(conn, task_id, kind, filename):
    return conn.execute(
        "INSERT INTO files(task_id,kind,filename) VALUES(%s,%s,%s) RETURNING id",
        (
            task_id,
            kind,
            filename,
        ),
    ).fetchone()


def mark_failed(conn, file_id):
    conn.execute("UPDATE files SET status='failed' WHERE id=%s", (file_id,))


def list_shared(conn, task_id, file_ids):
    return conn.execute(
        "SELECT id,filename,kind,status FROM files WHERE task_id=%s AND id=ANY(%s) AND status='ready' ORDER BY id",
        (
            task_id,
            file_ids,
        ),
    ).fetchall()


def list_active(conn, task_id):
    return conn.execute(
        "SELECT id,filename,kind,status FROM files WHERE task_id=%s AND archived_at IS NULL ORDER BY id",
        (task_id,),
    ).fetchall()


def find_ready(conn, file_id, task_id):
    return conn.execute(
        "SELECT 1 FROM files WHERE id=%s AND task_id=%s AND status='ready'",
        (
            file_id,
            task_id,
        ),
    ).fetchone()


def archive(conn, file_id, task_id):
    return conn.execute(
        "UPDATE files SET archived_at=now() WHERE id=%s AND task_id=%s RETURNING id",
        (
            file_id,
            task_id,
        ),
    ).fetchone()

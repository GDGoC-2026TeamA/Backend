def find_accessible(conn, task_id, user_id):
    return conn.execute(
        """
        SELECT t.*,w.kind FROM tasks t JOIN workspaces w ON w.id=t.workspace_id
        JOIN workspace_members m ON m.workspace_id=t.workspace_id
        WHERE t.id=%s AND m.user_id=%s AND (t.created_by=%s OR t.shared_analysis_id IS NOT NULL)
        FOR SHARE OF m
    """,
        (
            task_id,
            user_id,
            user_id,
        ),
    ).fetchone()


def has_shared_tasks(conn, space_id, user_id):
    return conn.execute(
        "SELECT 1 FROM tasks WHERE workspace_id=%s AND created_by=%s AND shared_analysis_id IS NOT NULL",
        (
            space_id,
            user_id,
        ),
    ).fetchone()


def insert_task(conn, space_id, user_id, name, description):
    return conn.execute(
        "INSERT INTO tasks(workspace_id,created_by,name,description) VALUES(%s,%s,%s,%s) RETURNING id",
        (
            space_id,
            user_id,
            name,
            description,
        ),
    ).fetchone()


def list_visible(conn, user_id, space_id, scope):
    return conn.execute(
        """SELECT t.id,t.name,t.description,u.name AS "creatorName", t.created_by=%s AS "isMine",
        CASE WHEN t.created_by=%s THEN t.updated_at ELSE t.shared_at END AS "updatedAt",
        t.shared_analysis_id AS "sharedAnalysisId"
        FROM tasks t JOIN app_users u ON u.id=t.created_by
        WHERE t.workspace_id=%s AND (t.created_by=%s OR t.shared_analysis_id IS NOT NULL)
        AND (%s='all' OR (%s='mine' AND t.created_by=%s) OR (%s='shared' AND t.created_by<>%s))
        ORDER BY "updatedAt" DESC,t.id""",
        (
            user_id,
            user_id,
            space_id,
            user_id,
            scope,
            scope,
            user_id,
            scope,
            user_id,
        ),
    ).fetchall()


def publish_review(conn, analysis_id, task_id):
    conn.execute(
        "UPDATE tasks SET updated_at=now(),shared_at=now(),shared_analysis_id=%s WHERE id=%s",
        (
            analysis_id,
            task_id,
        ),
    )


def touch(conn, task_id):
    conn.execute("UPDATE tasks SET updated_at=now() WHERE id=%s", (task_id,))


def unpublish(conn, task_id):
    conn.execute(
        "UPDATE tasks SET shared_at=NULL,shared_analysis_id=NULL,updated_at=now() WHERE id=%s",
        (task_id,),
    )


def share_existing(conn, analysis_id, task_id):
    return conn.execute(
        """UPDATE tasks SET shared_analysis_id=%s,shared_at=now(),updated_at=now()
        WHERE id=%s RETURNING shared_at""",
        (
            analysis_id,
            task_id,
        ),
    ).fetchone()

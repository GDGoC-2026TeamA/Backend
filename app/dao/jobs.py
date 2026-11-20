from psycopg.types.json import Jsonb

# 초안 생성 전 created, 검토 중 reviewing, 최종 저장 후 saved
STATUS = """CASE WHEN j.saved_at IS NOT NULL THEN 'saved'
    WHEN j.draft IS NULL THEN 'created' ELSE 'reviewing' END"""


def insert_job(conn, user_id, analysis_id, name, description):
    return conn.execute(
        "INSERT INTO jobs(user_id,analysis_id,name,description) VALUES(%s,%s,%s,%s) RETURNING id",
        (
            user_id,
            analysis_id,
            name,
            description,
        ),
    ).fetchone()


def list_for_user(conn, user_id):
    return conn.execute(
        f"""SELECT j.id,j.name,j.created_at,{STATUS} AS status
        FROM jobs j WHERE j.user_id=%s ORDER BY j.created_at DESC""",
        (user_id,),
    ).fetchall()


def find_owned(conn, job_id, user_id, *, lock=False):
    return conn.execute(
        f"""SELECT j.*,a.task_id,{STATUS} AS status FROM jobs j
        JOIN analyses a ON a.id=j.analysis_id
        WHERE j.id=%s AND j.user_id=%s {"FOR UPDATE OF j" if lock else ""}""",
        (
            job_id,
            user_id,
        ),
    ).fetchone()


def list_recent_for_task(conn, user_id, task_id, limit=5):
    return conn.execute(
        f"""SELECT j.id,a.task_id AS "taskId",j.name,{STATUS} AS status
        FROM jobs j JOIN analyses a ON a.id=j.analysis_id
        WHERE j.user_id=%s AND a.task_id=%s ORDER BY j.created_at DESC,j.id DESC LIMIT %s""",
        (
            user_id,
            task_id,
            limit,
        ),
    ).fetchall()


def list_unfinished_in_space(conn, user_id, space_id, limit=5):
    return conn.execute(
        f"""SELECT j.id,a.task_id AS "taskId",t.name AS "taskName",j.name,
        {STATUS} AS status,j.created_at AS "createdAt"
        FROM jobs j JOIN analyses a ON a.id=j.analysis_id JOIN tasks t ON t.id=a.task_id
        WHERE j.user_id=%s AND t.workspace_id=%s AND j.saved_at IS NULL
        AND (t.created_by=%s OR t.shared_analysis_id IS NOT NULL)
        ORDER BY j.created_at DESC,j.id DESC LIMIT %s""",
        (
            user_id,
            space_id,
            user_id,
            limit,
        ),
    ).fetchall()


def save_draft(conn, job_id, draft):
    conn.execute(
        "UPDATE jobs SET draft=%s WHERE id=%s AND draft IS NULL AND saved_at IS NULL",
        (
            Jsonb(draft),
            job_id,
        ),
    )


def save_review_changes(conn, job_id, changes):
    conn.execute(
        "UPDATE jobs SET review_changes=%s WHERE id=%s AND saved_at IS NULL",
        (
            Jsonb(changes),
            job_id,
        ),
    )


def mark_saved(conn, job_id):
    conn.execute(
        "UPDATE jobs SET saved_at=now() WHERE id=%s AND saved_at IS NULL AND draft IS NOT NULL",
        (job_id,),
    )

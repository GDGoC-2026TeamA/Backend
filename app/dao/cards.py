def insert_card(conn, user_id, analysis_id, item_id, title):
    return conn.execute(
        """INSERT INTO cards(user_id,analysis_id,item_id,title) VALUES(%s,%s,%s,%s) RETURNING id""",
        (
            user_id,
            analysis_id,
            item_id,
            title,
        ),
    ).fetchone()


def list_for_user(conn, user_id):
    return conn.execute(
        "SELECT id,title,updated_at FROM cards WHERE user_id=%s ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()


def list_recent_in_space(conn, user_id, space_id, limit=5):
    return conn.execute(
        """SELECT c.id,c.title,a.task_id AS "taskId",c.updated_at AS "updatedAt"
        FROM cards c JOIN analyses a ON a.id=c.analysis_id JOIN tasks t ON t.id=a.task_id
        WHERE c.user_id=%s AND t.workspace_id=%s
        AND (t.created_by=%s OR t.shared_analysis_id IS NOT NULL)
        ORDER BY c.updated_at DESC,c.id DESC LIMIT %s""",
        (
            user_id,
            space_id,
            user_id,
            limit,
        ),
    ).fetchall()

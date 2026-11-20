def insert_job(conn, user_id, analysis_id, name):
    return conn.execute(
        "INSERT INTO jobs(user_id,analysis_id,name) VALUES(%s,%s,%s) RETURNING id",
        (
            user_id,
            analysis_id,
            name,
        ),
    ).fetchone()


def list_for_user(conn, user_id):
    return conn.execute(
        """SELECT id,name,created_at,CASE WHEN saved_at IS NULL THEN 'reviewing' ELSE 'saved' END AS status
        FROM jobs WHERE user_id=%s ORDER BY created_at DESC""",
        (user_id,),
    ).fetchall()

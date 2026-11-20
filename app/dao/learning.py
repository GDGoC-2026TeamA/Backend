from psycopg.types.json import Jsonb


def insert_practice(conn, user_id, task_id, analysis_id, content):
    return conn.execute(
        """INSERT INTO learning_records(user_id,task_id,analysis_id,kind,content)
        VALUES(%s,%s,%s,'practice',%s) RETURNING id""",
        (
            user_id,
            task_id,
            analysis_id,
            Jsonb(content),
        ),
    ).fetchone()


def save_answers(conn, content, practice_id):
    conn.execute(
        "UPDATE learning_records SET content=%s WHERE id=%s",
        (
            Jsonb(content),
            practice_id,
        ),
    )


def lock_practice(conn, practice_id, user_id):
    return conn.execute(
        "SELECT content FROM learning_records WHERE id=%s AND user_id=%s AND kind='practice' FOR UPDATE",
        (
            practice_id,
            user_id,
        ),
    ).fetchone()


def insert_question(conn, user_id, task_id, analysis_id, content):
    conn.execute(
        "INSERT INTO learning_records(user_id,task_id,analysis_id,kind,content) VALUES(%s,%s,%s,'question',%s)",
        (
            user_id,
            task_id,
            analysis_id,
            Jsonb(content),
        ),
    )


def list_history(conn, user_id):
    return conn.execute(
        """SELECT id,task_id,kind,created_at FROM learning_records WHERE user_id=%s
        ORDER BY created_at DESC""",
        (user_id,),
    ).fetchall()

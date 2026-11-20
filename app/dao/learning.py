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


# 연습은 선택한 단계, 질문은 근거 단계와 같은 분석·itemId로 만든 내 카드를 연결한다.
_CARD_IDS = """COALESCE((SELECT array_agg(c.id ORDER BY c.id) FROM cards c
    WHERE c.user_id=r.user_id AND c.analysis_id=r.analysis_id
    AND c.item_id::text IN (SELECT jsonb_array_elements_text(
        COALESCE(r.content->'selectedItemIds', r.content->'itemIds', '[]'::jsonb)))),
    '{}') AS card_ids"""

_TITLE = """CASE r.kind WHEN 'practice' THEN r.content->>'situation'
    ELSE r.content->>'question' END AS title"""


def list_history(conn, user_id):
    return conn.execute(
        f"""SELECT r.id,r.task_id,r.kind,r.created_at,r.analysis_id,t.name AS task_name,
        {_TITLE},(r.kind='practice' AND r.content ? 'answers') AS answered,{_CARD_IDS}
        FROM learning_records r JOIN tasks t ON t.id=r.task_id WHERE r.user_id=%s
        ORDER BY r.created_at DESC,r.id DESC""",
        (user_id,),
    ).fetchall()


def find_record(conn, record_id, user_id):
    return conn.execute(
        f"""SELECT r.id,r.task_id,r.kind,r.created_at,r.analysis_id,t.name AS task_name,
        r.content,{_CARD_IDS}
        FROM learning_records r JOIN tasks t ON t.id=r.task_id
        WHERE r.id=%s AND r.user_id=%s""",
        (
            record_id,
            user_id,
        ),
    ).fetchone()


def find_practice(conn, practice_id, user_id):
    return conn.execute(
        """SELECT id,analysis_id,content FROM learning_records
        WHERE id=%s AND user_id=%s AND kind='practice'""",
        (
            practice_id,
            user_id,
        ),
    ).fetchone()


def task_progress(conn, user_id, task_id):
    return conn.execute(
        """SELECT count(*) AS records,
        count(*) FILTER (WHERE kind='practice' AND content ? 'answers') AS answered
        FROM learning_records WHERE user_id=%s AND task_id=%s""",
        (
            user_id,
            task_id,
        ),
    ).fetchone()

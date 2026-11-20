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

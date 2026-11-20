from psycopg.types.json import Jsonb


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


def get_card(conn, user_id, card_id):
    return conn.execute(
        "SELECT * FROM cards WHERE user_id = %s AND id = %s", (user_id, card_id)
    ).fetchone()


def update_card(conn, user_id, card_id, title, overrides):
    return conn.execute(
        """UPDATE cards SET title = COALESCE(%s, title),
               overrides = COALESCE(%s, overrides), updated_at = now()
           WHERE user_id = %s AND id = %s RETURNING *""",
        (title, Jsonb(overrides) if overrides is not None else None, user_id, card_id),
    ).fetchone()


def delete_card(conn, user_id, card_id):
    return conn.execute(
        "DELETE FROM cards WHERE user_id = %s AND id = %s RETURNING id", (user_id, card_id)
    ).fetchone()

def find_membership(conn, space_id, user_id):
    return conn.execute(
        """
        SELECT w.* FROM workspaces w JOIN workspace_members m ON m.workspace_id=w.id
        WHERE w.id=%s AND m.user_id=%s FOR SHARE OF m
    """,
        (
            space_id,
            user_id,
        ),
    ).fetchone()


def list_for_user(conn, user_id):
    return conn.execute(
        """SELECT w.id,w.name,w.kind,w.created_by=%s AS is_owner
        FROM workspaces w JOIN workspace_members m ON m.workspace_id=w.id
        WHERE m.user_id=%s ORDER BY w.kind DESC,w.id""",
        (
            user_id,
            user_id,
        ),
    ).fetchall()


def insert_owner(conn, space_id, user_id):
    conn.execute(
        "INSERT INTO workspace_members VALUES(%s,%s)",
        (
            space_id,
            user_id,
        ),
    )


def insert_company(conn, name, user_id):
    return conn.execute(
        """INSERT INTO workspaces(kind,name,created_by,invite_code)
        VALUES('company',%s,%s,gen_random_uuid()) RETURNING id""",
        (
            name,
            user_id,
        ),
    ).fetchone()


def add_member(conn, space_id, user_id):
    conn.execute(
        "INSERT INTO workspace_members VALUES(%s,%s) ON CONFLICT DO NOTHING",
        (
            space_id,
            user_id,
        ),
    )


def find_by_invite(conn, code):
    return conn.execute(
        "SELECT id FROM workspaces WHERE invite_code=%s", (code,)
    ).fetchone()


def remove_member(conn, space_id, user_id):
    conn.execute(
        "DELETE FROM workspace_members WHERE workspace_id=%s AND user_id=%s",
        (
            space_id,
            user_id,
        ),
    )


def lock_membership(conn, space_id, user_id):
    return conn.execute(
        "SELECT user_id FROM workspace_members WHERE workspace_id=%s AND user_id=%s FOR UPDATE",
        (
            space_id,
            user_id,
        ),
    ).fetchone()

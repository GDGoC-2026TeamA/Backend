def session_owner(conn, digest):
    return conn.execute(
        "SELECT user_id FROM login_sessions WHERE token_hash=%s AND expires_at>now()",
        (digest,),
    ).fetchone()


def find_by_login(conn, login_id):
    return conn.execute(
        "SELECT id,password_hash FROM app_users WHERE lower(login_id)=lower(%s)",
        (login_id,),
    ).fetchone()


def find_by_email(conn, email):
    return conn.execute(
        "SELECT id,password_hash FROM app_users WHERE lower(email)=lower(%s)",
        (email,),
    ).fetchone()


def delete_expired_sessions(conn, user_id):
    conn.execute(
        "DELETE FROM login_sessions WHERE user_id=%s AND expires_at<=now()", (user_id,)
    )


def insert_session(conn, digest, user_id):
    conn.execute(
        "INSERT INTO login_sessions VALUES(%s,%s,now()+interval '8 hours')",
        (
            digest,
            user_id,
        ),
    )


def insert_account(conn, name, login_id, email, password_hash):
    return conn.execute(
        "INSERT INTO app_users(name,login_id,email,password_hash) VALUES(%s,%s,%s,%s) RETURNING id",
        (
            name,
            login_id,
            email,
            password_hash,
        ),
    ).fetchone()


def social_user(conn, provider, subject, name):
    # Serialize first-time sign-ins for this identity until the transaction commits.
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (provider + ":" + subject,))
    existing = conn.execute(
        "SELECT user_id FROM social_accounts WHERE provider=%s AND subject=%s",
        (provider, subject),
    ).fetchone()
    if existing:
        return existing["user_id"]
    uid = conn.execute("INSERT INTO app_users(name) VALUES (%s) RETURNING id", (name,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO social_accounts(user_id,provider,subject) VALUES (%s,%s,%s)",
        (uid, provider, subject),
    )
    return uid

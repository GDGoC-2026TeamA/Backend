BEGIN;
CREATE TABLE social_login_codes (
    code_hash bytea PRIMARY KEY,
    challenge text NOT NULL,
    user_id bigint NOT NULL REFERENCES app_users ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
CREATE INDEX social_codes_expiry ON social_login_codes(expires_at);
COMMIT;

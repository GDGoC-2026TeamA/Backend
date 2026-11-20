BEGIN;
-- 로그인 토큰 원문은 저장하지 않는다.
CREATE TABLE login_sessions (
    token_hash bytea PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES app_users ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
CREATE TABLE workspaces (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('personal','company')),
    name text NOT NULL CHECK (btrim(name) <> ''),
    created_by bigint NOT NULL REFERENCES app_users,
    invite_code uuid UNIQUE,
    CHECK ((kind = 'company') = (invite_code IS NOT NULL))
);
CREATE UNIQUE INDEX one_personal_space ON workspaces(created_by) WHERE kind='personal';
CREATE TABLE workspace_members (
    workspace_id bigint NOT NULL REFERENCES workspaces,
    user_id bigint NOT NULL REFERENCES app_users,
    PRIMARY KEY (workspace_id,user_id)
);
CREATE INDEX spaces_by_member ON workspace_members(user_id,workspace_id);

CREATE FUNCTION create_personal_space() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE space_id bigint;
BEGIN
    INSERT INTO workspaces(kind,name,created_by) VALUES ('personal','개인 작업 공간',NEW.id)
        RETURNING id INTO space_id;
    INSERT INTO workspace_members VALUES (space_id,NEW.id);
    RETURN NEW;
END;
$$;
CREATE TRIGGER on_user_create_space AFTER INSERT ON app_users
FOR EACH ROW EXECUTE FUNCTION create_personal_space();

INSERT INTO workspaces(kind,name,created_by) SELECT 'personal','개인 작업 공간',id FROM app_users;
INSERT INTO workspace_members SELECT id,created_by FROM workspaces;
ALTER TABLE tasks ADD COLUMN workspace_id bigint REFERENCES workspaces,
    ADD COLUMN shared_analysis_id bigint,
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN shared_at timestamptz,
    ADD CONSTRAINT shared_same_task FOREIGN KEY (id,shared_analysis_id) REFERENCES analyses(task_id,id),
    ADD CONSTRAINT share_timestamp CHECK ((shared_analysis_id IS NULL) = (shared_at IS NULL));
UPDATE tasks t SET workspace_id=w.id FROM workspaces w WHERE w.created_by=t.created_by AND w.kind='personal';
ALTER TABLE tasks ALTER COLUMN workspace_id SET NOT NULL;
CREATE INDEX tasks_by_space ON tasks(workspace_id,created_by);
COMMIT;


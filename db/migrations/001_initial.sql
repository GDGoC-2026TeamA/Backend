-- WORK BRIDGE · PostgreSQL 초기 스키마 (빈 DB용)
BEGIN;

-- 일반 가입은 이메일과 비밀번호 해시를 함께 등록한다.
-- 소셜 전용 가입은 로그인 ID와 비밀번호 없이 회원·소셜 계정을 한 트랜잭션에 생성한다.
CREATE TABLE app_users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    email text CHECK (email <> '' AND email = btrim(email)),
    login_id text CHECK (login_id <> '' AND login_id = btrim(login_id)),
    password_hash text CHECK (btrim(password_hash) <> ''),
    CHECK ((login_id IS NULL) = (password_hash IS NULL)),
    CHECK (login_id IS NULL OR email IS NOT NULL)
);
CREATE UNIQUE INDEX users_login_id ON app_users (lower(login_id));
CREATE UNIQUE INDEX users_email ON app_users (lower(email));

-- provider는 백엔드가 검증한 공급자 키(google, kakao 등). 이메일로 자동 연결하지 않는다.
CREATE TABLE social_accounts (
    user_id bigint NOT NULL REFERENCES app_users ON DELETE CASCADE,
    provider text NOT NULL CHECK (btrim(provider) <> ''),
    subject text NOT NULL CHECK (btrim(subject) <> ''),
    PRIMARY KEY (provider, subject),
    UNIQUE (user_id, provider)
);

CREATE TABLE tasks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_by bigint NOT NULL REFERENCES app_users,
    name text NOT NULL CHECK (btrim(name) <> ''),
    description text
);

-- 분석 한 번에 한 행. 재분석은 새 행을 생성해 기존 작업의 기준을 보존한다.
-- steps는 순서가 있는 배열. 각 단계에 전역 고유 itemId(UUID), 기존/새 절차,
-- 변경 구분, 확인 여부, 입력 항목, sources[{fileId, location}]을 담는다.
-- FastAPI가 파일 소속과 항목 구조를 검증하고, 확정 후에는 수정을 막는다.
CREATE TABLE analyses (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id bigint NOT NULL REFERENCES tasks,
    input_file_ids bigint[] NOT NULL,
    steps jsonb NOT NULL CHECK (jsonb_typeof(steps) = 'array'),
    created_at timestamptz NOT NULL DEFAULT now(),
    confirmed_at timestamptz,
    UNIQUE (task_id, id)
);

-- 연습 1회 또는 AI 질문 1건에 한 행. 분석 전에도 업무 자료에 질문할 수 있다.
-- practice: 문제, 선택지, 응답, 피드백, 완료 시각. question: 질문, 답변, 근거, 확인 필요 여부.
CREATE TABLE learning_records (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES app_users,
    task_id bigint NOT NULL REFERENCES tasks,
    analysis_id bigint,
    kind text NOT NULL CHECK (kind IN ('practice', 'question')),
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (kind <> 'practice' OR analysis_id IS NOT NULL),
    FOREIGN KEY (task_id, analysis_id) REFERENCES analyses (task_id, id)
);

-- 확정된 분석 단계에서 카드를 만든다. 서비스가 item_id의 소속을 검증한다.
-- 제목은 검색용. 절차·근거 기본값은 원본 단계에서 읽고 개인화한 필드만 저장한다.
CREATE TABLE cards (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES app_users,
    analysis_id bigint NOT NULL REFERENCES analyses,
    title text NOT NULL CHECK (btrim(title) <> ''),
    item_id uuid NOT NULL,
    overrides jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(overrides) = 'object'),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- draft에는 재현할 수 없는 AI 초안과 검토 대상 필드(값 누락 포함)를 한 번 저장한다.
-- review_changes 예: {"values":{"quantity":12},"checked":["quantity"],"lastField":"lot"}
-- values에서 키 생략은 원본 유지, 명시한 null은 값 지우기다.
-- 서버가 초안과 수정값을 합성하고 checked로 남은 검토 항목을 계산한다.
-- 저장 시 수정값과 saved_at을 한 번에 갱신한다. 초안 생성 후 원본을 보존하고
-- 최종 저장 후에는 서비스의 모든 수정 경로에서 WHERE saved_at IS NULL을 적용한다.
CREATE TABLE jobs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES app_users,
    analysis_id bigint NOT NULL REFERENCES analyses,
    name text NOT NULL CHECK (btrim(name) <> ''),
    description text,
    draft jsonb CHECK (jsonb_typeof(draft) = 'object'),
    review_changes jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(review_changes) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    saved_at timestamptz,
    CHECK (draft IS NOT NULL OR review_changes = '{}'::jsonb),
    CHECK (saved_at IS NULL OR draft IS NOT NULL)
);

-- 환경별 비공개 버킷 1개. 버킷 이름과 접속 정보는 FastAPI 환경변수로 관리한다.
-- 저장 키 규약: files/v1/{id}. 원래 이름·종류·업무가 바뀌어도 같은 키를 계산한다.
-- 파일명, 버킷 URL, 서명 URL로 객체를 식별하지 않는다. 운영 중 ID를 재사용하지 않는다.
-- 1. INSERT ... RETURNING id 후 커밋. 이 ID에 대응하는 키로 원본을 업로드한다.
-- 2. 성공을 확인하면 pending -> ready. 타임아웃은 pending으로 두고 같은 키를 조회해 복구한다.
--    재시도는 동일 요청의 원본만 대상으로 하며 이미 성공한 객체를 덮어쓰지 않는다.
-- 3. 새 버전은 같은 이름이어도 새 행에 등록한다. 분석·카드는 영구 fileId로 근거를 찾는다.
-- 4. 자료 목록은 archived_at IS NULL로 조회한다. 보관된 과거 근거는 권한 확인 후 열 수 있다.
CREATE TABLE files (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id bigint REFERENCES tasks,
    job_id bigint REFERENCES jobs,
    kind text NOT NULL,
    filename text NOT NULL CHECK (btrim(filename) <> ''),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','ready','failed')),
    created_at timestamptz NOT NULL DEFAULT now(), -- 오래된 미완료 업로드 식별
    archived_at timestamptz,
    CHECK ((task_id IS NOT NULL AND job_id IS NULL AND kind IN ('previous_form','manual','screenshot'))
        OR (job_id IS NOT NULL AND task_id IS NULL AND kind = 'job_input'))
);

CREATE INDEX analyses_by_task ON analyses (task_id, created_at DESC);
CREATE INDEX learning_by_user ON learning_records (user_id, created_at DESC);
CREATE INDEX cards_by_user ON cards (user_id, updated_at DESC);
CREATE INDEX jobs_by_user ON jobs (user_id, created_at DESC);
CREATE INDEX files_by_task ON files (task_id) WHERE task_id IS NOT NULL;
CREATE INDEX files_by_job ON files (job_id) WHERE job_id IS NOT NULL;
COMMIT;

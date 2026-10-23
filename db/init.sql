-- Reference table of persisted onboarding questions.
CREATE TABLE questions (
    id   SMALLINT PRIMARY KEY,
    text TEXT NOT NULL
);

INSERT INTO questions (id, text) VALUES
    (1, 'Which language would you like to learn?'),
    (2, 'What is your native language?'),
    (3, 'How would you like to learn?');

-- One row per (user, question). user_id is the user's email.
-- Question 1 stores a target-language code (en, es, de, fr).
CREATE TABLE answers (
    user_id     TEXT        NOT NULL,
    question_id SMALLINT    NOT NULL REFERENCES questions(id),
    answer      TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, question_id)
);

-- Long-term learning plan built by the Agno curriculum agent.
-- One active plan per (user, target language).
CREATE TABLE learning_plans (
    plan_id          UUID        PRIMARY KEY,
    user_id          TEXT        NOT NULL,
    target_language  TEXT        NOT NULL,
    native_language  TEXT        NOT NULL,
    level            TEXT        NOT NULL,
    goal_summary     TEXT        NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, target_language)
);

-- Ordered units of a plan; ticked off as lessons complete them.
CREATE TABLE plan_units (
    unit_id      UUID        PRIMARY KEY,
    plan_id      UUID        NOT NULL REFERENCES learning_plans(plan_id) ON DELETE CASCADE,
    position     INTEGER     NOT NULL,
    title        TEXT        NOT NULL,
    kind         TEXT        NOT NULL CHECK (kind IN ('vocabulary', 'grammar', 'conversation')),
    description  TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'in_progress', 'done')),
    completed_at TIMESTAMPTZ,
    UNIQUE (plan_id, position)
);

-- One row per ~10-minute lesson. The planner writes it as 'planned'; the
-- voice tutor moves it to 'in_progress' and then 'completed' or 'abandoned'.
-- objectives: [{"id": "o1", "text": "...", "done": false, "evidence": null}]
CREATE TABLE lessons (
    lesson_uuid     UUID        PRIMARY KEY,
    user_id         TEXT        NOT NULL,
    plan_id         UUID        REFERENCES learning_plans(plan_id) ON DELETE CASCADE,
    unit_id         UUID        REFERENCES plan_units(unit_id) ON DELETE SET NULL,
    target_language TEXT        NOT NULL,
    title           TEXT        NOT NULL,
    lesson_script   TEXT        NOT NULL,
    duration        INTEGER     NOT NULL DEFAULT 10,
    status          TEXT        NOT NULL DEFAULT 'planned'
                                CHECK (status IN ('planned', 'in_progress', 'completed', 'abandoned')),
    objectives      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    vocabulary      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    summary         TEXT,
    new_vocabulary  JSONB       NOT NULL DEFAULT '[]'::jsonb,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_lessons_user_id ON lessons (user_id, created_at DESC);

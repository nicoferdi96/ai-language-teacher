-- Reference table of persisted onboarding questions.
CREATE TABLE questions (
    id   SMALLINT PRIMARY KEY,
    text TEXT NOT NULL
);

INSERT INTO questions (id, text) VALUES
    (1, 'How would you like to learn Spanish?'),
    (2, 'What is your ideal duration per single lesson?');

-- One row per (user, question). user_id is the user's email.
CREATE TABLE answers (
    user_id     TEXT        NOT NULL,
    question_id SMALLINT    NOT NULL REFERENCES questions(id),
    answer      TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, question_id)
);

# AI Language Teacher — Frontend Onboarding Wizard

**Date:** 2026-05-21
**Status:** Approved
**Scope:** Frontend microservice + postgres service + root `docker-compose.yaml`. Backend services (agentic analyzer, LiveKit voice AI) are explicitly out of scope for this spec.

## 1. Context and Goal

AI Language Teacher is a platform that delivers an adaptive, always-available language learning experience. The product is composed of independent microservices. This spec covers the first deliverable: a step-by-step onboarding wizard that introduces itself as a teaching assistant, asks the user a short set of questions, and persists the answers to postgres keyed by the user's email.

The onboarding answers will later feed the agentic backend that builds each user's adaptive learning plan and teaching style.

## 2. Architecture — Microservices

Two services orchestrated by a root `docker-compose.yaml`. Each service is self-contained in its own folder with its own build.

```
ai_language_teacher/
├── docker-compose.yaml      # services: frontend, postgres
├── .env                     # secrets — gitignored
├── .env.example             # committed template
├── db/
│   └── init.sql             # schema + seed; runs on postgres first boot
├── frontend/                # Next.js microservice (own Dockerfile)
├── AGENTS.md
└── README.md
```

Future backend services (agentic analyzer, LiveKit voice AI) will be added as sibling top-level folders and as additional `docker-compose.yaml` services. They are not built here.

### 2.1 docker-compose services

| Service | Definition |
|---|---|
| `postgres` | Image `postgres:17-alpine`. Env `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. Named volume `pgdata` for data persistence. Mounts `./db:/docker-entrypoint-initdb.d:ro` so `init.sql` runs on first boot. Healthcheck via `pg_isready`. |
| `frontend` | Builds from `./frontend`. `depends_on: postgres` with `condition: service_healthy`. Env `DATABASE_URL`. Publishes port `3000:3000`. |

### 2.2 Networking and configuration

- Services communicate over the default compose bridge network. The frontend reaches the database at hostname `postgres:5432`.
- `DATABASE_URL=postgres://<user>:<password>@postgres:5432/<db>`.
- Secrets live in a root `.env` file (gitignored). `docker-compose.yaml` interpolates them. A committed `.env.example` documents the required variables.

## 3. Frontend — Next.js

The frontend is a Next.js application using the App Router and TypeScript.

### 3.1 Folder structure

```
frontend/
├── Dockerfile
├── .dockerignore
├── package.json
├── next.config.ts
├── tsconfig.json
├── app/
│   ├── layout.tsx          # root layout — dark editorial theme, fonts
│   ├── globals.css         # design tokens — dark OKLCH palette
│   ├── page.tsx            # Screen 0 — email entry
│   └── wizard/
│       ├── q1/page.tsx     # Ready to begin? YES/NO
│       ├── q2/page.tsx     # How would you like to learn Spanish? (textarea)
│       ├── q3/page.tsx     # Ideal duration per lesson (number, minutes)
│       └── done/page.tsx   # completion screen
├── components/
│   └── WizardShell.tsx     # editorial frame reused by every step
└── lib/
    ├── db.ts               # pg Pool singleton
    ├── actions.ts          # Server Actions
    └── session.ts          # email cookie read/write helpers
```

### 3.2 Routes and flow

| Route | Screen | Server Action and result |
|---|---|---|
| `/` | Intro copy ("Hey, I am your teaching assistant. Before starting, let me ask a few questions.") + email input | `startSession(email)`: validate email, set httpOnly cookie `user_email`, redirect to `/wizard/q1`. |
| `/wizard/q1` | "Ready to begin?" YES / NO | `answerQ1(choice)`: YES redirects to `/wizard/q2`; NO renders a gate screen. **Not persisted.** |
| `/wizard/q2` | "How would you like to learn Spanish?" — open-ended textarea | `saveAnswer`: read email from cookie, validate non-empty, upsert `(user_id, question_id=1, answer)`, redirect to `/wizard/q3`. |
| `/wizard/q3` | "What is your ideal duration per single lesson?" — number input in minutes | `saveAnswer`: validate integer minutes > 0, upsert `(user_id, question_id=2, answer)`, redirect to `/wizard/done`. |
| `/wizard/done` | Completion screen | None. |

**Route guard:** every `/wizard/*` route checks for the `user_email` cookie. If absent, it redirects to `/`. This enforces step order and guarantees the email (the user id) is known before any answer is saved.

### 3.3 Components

- `WizardShell` — the editorial dark frame: brand tag top-left, step counter ("02 / 03") top-right, a large-question slot, and an action area. Reused by every wizard step for visual consistency.
- Each question page is a Server Component rendering a `<form action={serverAction}>`. Client components are used only where interaction requires them (for example, enabling the Continue control once input is valid).

### 3.4 Technology choices

- **Language:** TypeScript.
- **Database driver:** `pg` (node-postgres) with a Pool singleton in `lib/db.ts`. No ORM. The schema is two tables and raw parametrized SQL is sufficient. This follows the AGENTS.md principle "simplicity over complexity".
- **Styling:** design tokens in `globals.css` implementing the dark palette. The polished UI build is owned by the `impeccable` skill at implementation time.

### 3.5 Visual direction

**Editorial immersive.** Dark, minimal, one large question filling the screen, with a small step counter in the corner. Bold and memorable rather than a templated SaaS card. Established during brainstorming via the visual companion.

## 4. Data Flow and Persistence

State is carried with a cookie and answers are saved as the user advances (the "cookie + save-as-you-go" approach).

1. Screen 0: the email is trimmed, lowercased, and regex-validated, then stored in an httpOnly cookie `user_email`.
2. Q1: an in-memory gate only. Nothing is persisted.
3. Q2 submit: the Server Action reads the email from the cookie, validates non-empty text, and upserts question_id 1.
4. Q3 submit: the Server Action validates an integer minute value greater than zero and upserts question_id 2.
5. Done.

Only the second and third questions are persisted. Q1 ("Ready to begin?") is meaningless to store and acts purely as a gate.

## 5. Database Schema

`db/init.sql` runs automatically when the postgres container boots against an empty data volume.

```sql
CREATE TABLE questions (
    id   SMALLINT PRIMARY KEY,
    text TEXT NOT NULL
);

INSERT INTO questions (id, text) VALUES
    (1, 'How would you like to learn Spanish?'),
    (2, 'What is your ideal duration per single lesson?');

CREATE TABLE answers (
    user_id     TEXT        NOT NULL,
    question_id SMALLINT    NOT NULL REFERENCES questions(id),
    answer      TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, question_id)
);
```

- `questions` is a reference table seeded with ids 1 and 2, making the persisted question ids explicit.
- `answers` holds one row per (user, question). The composite primary key `(user_id, question_id)` enforces "one question = one row" per user.
- `answer` is `TEXT` for both questions. The Q3 minute value is validated as an integer in the application and stored as text, keeping the column uniform.
- `user_id` is the user's email.

**Upsert statement** used by `saveAnswer`:

```sql
INSERT INTO answers (user_id, question_id, answer)
VALUES ($1, $2, $3)
ON CONFLICT (user_id, question_id)
DO UPDATE SET answer = EXCLUDED.answer, updated_at = now();
```

Re-running the wizard with the same email overwrites the existing rows, so the operation is idempotent.

## 6. Error Handling and Edge Cases

| Case | Handling |
|---|---|
| Invalid email format on Screen 0 | Re-render Screen 0 with an inline error; no cookie is set. |
| Missing `user_email` cookie on a `/wizard/*` route | Redirect to `/`. |
| Q1 answered NO | Render a gate screen with a friendly "come back when ready" message; nothing is saved; the user can go back and choose YES. |
| Empty Q2 answer | Re-render the page with an inline error; no DB write. |
| Non-numeric or non-positive Q3 answer | Re-render the page with an inline error; no DB write. |
| Database unreachable | The Server Action throws; an error boundary screen is shown with a retry option. The `depends_on` healthcheck reduces boot-time races. |
| Same email re-runs the wizard | Upsert overwrites the existing answers — idempotent. |
| Schema changes after launch | `init.sql` only runs against an empty volume. A future migration strategy is out of scope and noted here for later. |

## 7. Testing

- **Server Action unit tests** (Vitest): validation logic and that the upsert is called with the correct arguments, with the pg Pool mocked.
- **Route guard test:** a request without the `user_email` cookie redirects to `/`.
- **Database integration test:** against a real postgres instance, run `init.sql`, then assert that the upsert overwrites the row on a primary-key conflict.
- **End-to-end test** (Playwright) walking `/` through `/wizard/done`: optional, a nice-to-have.

The required minimum is the Server Action unit tests, the route guard test, and the upsert integration test.

## 8. Out of Scope

- The agentic analysis backend.
- The LiveKit voice AI backend.
- Authentication beyond email capture (no passwords, no sessions table).
- Database migration tooling for post-launch schema changes.

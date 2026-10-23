# Lumi: AI language teacher

Ten-minute spoken lessons with a voice tutor, planned around each learner.

A learner signs in with an email, answers three onboarding questions (target language, native language, how they like to learn), and gets a long-term plan. Every visit the planner prepares the next ~10-minute lesson with checkable goals, and the learner talks it through live with Lumi, a voice tutor that ticks goals off as they go.

## How it fits together

| Service | Folder | Port | What it does |
|---|---|---|---|
| `frontend` | `frontend/` | 3000 | Next.js app: onboarding, home with the plan path, live lesson UI. |
| `lesson-planner` | `lessons_planning_workflow/` | 8000 | FastAPI + Agno workflow. Builds the learning plan once, and on every login reviews progress and prepares the next lesson with checkable objectives. Single owner of plan/lesson writes. |
| `voice-api` | `voice_agent/api/` | 8100 | FastAPI: fetches the next lesson and returns a LiveKit room token that dispatches the tutor. |
| `voice-worker` | `voice_agent/tutor/` | – | LiveKit agent "Lumi": Gradium STT/TTS, OpenRouter LLM. Speaks only the target language, ticks objectives with tools, ends via `EndCallTool`. |
| `postgres` | `db/init.sql` | 5433 (host) | Answers, learning plans, plan units, lessons. |

```
browser ──► frontend ──► lesson-planner ──► postgres
               │              ▲
               └──► voice-api ┘ ──► LiveKit Cloud ◄── voice-worker (Gradium + OpenRouter)
```

Supported target languages: English, Spanish, German, French. Italian was dropped because Gradium rejects it (`Unsupported language 'it'`, see `voice_agent/scripts/probe_gradium.py`).

Models: `openai/gpt-5.4-nano` via OpenRouter for both the planner and the tutor (minimal reasoning). Override with `PLANNER_MODEL` / `VOICE_LLM_MODEL`; models that accept it get temperature 0.1.

## What you need

- **Docker** with Compose v2 (for the one-command setup), or for running services by hand: **Node.js 22**, **Python 3.13** with [**uv**](https://docs.astral.sh/uv/), and Docker for Postgres.
- A browser with microphone access (Chrome, Edge, Firefox or Safari). Headphones recommended.
- The API keys below.

### API keys

All keys live in one `.env` file at the repository root. Copy the template and fill it in:

```bash
cp .env.example .env
```

| Variable | Required | Where to get it | Used by |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | [openrouter.ai/keys](https://openrouter.ai/keys). Add a little credit; the default nano model is cheap. | planner agents, tutor LLM |
| `GRADIUM_API_KEY` | Yes | Your Gradium account (speech-to-text and text-to-speech for en, es, de, fr). | voice worker |
| `LIVEKIT_URL` | Yes | [cloud.livekit.io](https://cloud.livekit.io) → your project → Settings. Looks like `wss://<project>.livekit.cloud`. | voice API, voice worker |
| `LIVEKIT_API_KEY` | Yes | Same project → Settings → API keys → create key. | voice API, voice worker |
| `LIVEKIT_API_SECRET` | Yes | Shown once when you create the API key. | voice API, voice worker |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Yes (defaults provided) | Pick any values; Compose creates the database with them. | postgres, planner |
| `PLANNER_MODEL` / `VOICE_LLM_MODEL` | No | Any OpenRouter model id, e.g. `openai/gpt-5.4-mini`. Empty means the default. | planner, tutor |
| `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_BASE_URL` | No | [Langfuse](https://cloud.langfuse.com) project settings, for tracing. | planner |

Tip: with the [LiveKit CLI](https://docs.livekit.io/home/cli/) installed, `lk project list` shows your project URL.

Never commit `.env`; it is already in `.gitignore`.

## Run with Docker (recommended)

```bash
cp .env.example .env    # then fill in the keys above
docker compose up --build
```

Open <http://localhost:3000>, enter any email, answer the three questions, and press **Start speaking** on the home screen. Allow the microphone when the browser asks.

- Stop everything: `docker compose down`
- Reset the database (needed after schema changes in `db/init.sql`): `docker compose down -v`
- Follow one service's logs: `docker compose logs -f voice-worker`

The Gradium account allows 3 concurrent sessions, so only one live lesson at a time is safe.

## Run locally without Docker

Useful when you are changing code and want hot reload. Run Postgres in Docker and every other service on your machine, each in its own terminal, all from the repository root.

**1. Postgres** (published on host port 5433):

```bash
docker compose up -d postgres
```

**2. Lesson planner** (reads `POSTGRES_*` from `.env`, connects to `localhost:5433`):

```bash
cd lessons_planning_workflow && uv sync && uv run uvicorn app:app --reload --port 8000
```

**3. Voice worker** (first run downloads the VAD and turn-detector models):

```bash
cd voice_agent && uv sync && uv run python -m tutor.worker download-files && uv run python -m tutor.worker dev
```

**4. Voice API:**

```bash
cd voice_agent && uv run uvicorn api.app:app --reload --port 8100
```

**5. Frontend.** Create `frontend/.env.local` so Next.js can reach the database and the two APIs (match the credentials in your root `.env`):

```bash
DATABASE_URL=postgres://teacher:change_me@localhost:5433/ai_language_teacher
LESSON_PLANNER_URL=http://localhost:8000/get_next_lesson/
VOICE_API_URL=http://localhost:8100
```

Then:

```bash
cd frontend && npm install && npm run dev
```

Open <http://localhost:3000>.

## Tests

```bash
cd lessons_planning_workflow && uv run pytest              # deterministic, needs postgres on :5433
cd lessons_planning_workflow && RUN_LIVE=1 uv run pytest   # + live persona tests (OpenRouter)
cd voice_agent && RUN_LIVE=1 uv run pytest                 # tutor state + live behaviour tests
cd frontend && npm test
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "I couldn't prepare your lesson just yet" | The planner can't reach OpenRouter or Postgres. Check `OPENROUTER_API_KEY` and `docker compose logs lesson-planner`. |
| Lesson screen says "Lumi is taking a while…" | The voice worker isn't connected to LiveKit. Check the three `LIVEKIT_*` values and `docker compose logs voice-worker`. |
| Lumi joins but never speaks | Gradium rejected the key or hit its concurrent-session limit. Check `GRADIUM_API_KEY` and close other lessons. |
| "Microphone access is blocked" | Allow the mic for `localhost:3000` in the browser's address bar, then press Start again. |
| Port 5432/3000 already in use | Postgres is published on 5433 to avoid a local install; stop whatever else uses 3000 or change the `ports` mapping in `docker-compose.yaml`. |

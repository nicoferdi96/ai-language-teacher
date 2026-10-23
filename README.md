# Lumi: AI language teacher

Ten-minute spoken lessons with a voice tutor, planned around each learner.

## How it fits together

| Service | Folder | What it does |
|---|---|---|
| `frontend` (:3000) | `frontend/` | Next.js app: onboarding (target language, native language, learning style), home with the plan path, live lesson UI. |
| `lesson-planner` (:8000) | `lessons_planning_workflow/` | FastAPI + Agno workflow. Builds the learning plan once, and on every login reviews progress and prepares the next ~10-minute lesson with checkable objectives. Single owner of plan/lesson writes. |
| `voice-api` (:8100) | `voice_agent/api/` | FastAPI: fetches the next lesson and returns a LiveKit room token that dispatches the tutor. |
| `voice-worker` | `voice_agent/tutor/` | LiveKit agent "Lumi": Gradium STT/TTS, OpenRouter LLM. Speaks only the target language, ticks objectives with tools, ends via `EndCallTool`. |
| `postgres` (:5433) | `db/init.sql` | Answers, learning plans, plan units, lessons. |

Supported target languages: English, Spanish, German, French. Italian was dropped because Gradium rejects it (`Unsupported language 'it'`, see `voice_agent/scripts/probe_gradium.py`).

Models: `openai/gpt-5.4-nano` via OpenRouter for both the planner and the tutor (minimal reasoning). Override with `PLANNER_MODEL` / `VOICE_LLM_MODEL`; models that accept it get temperature 0.1.

## Run

```bash
cp .env.example .env   # fill in OpenRouter, Gradium and LiveKit keys
docker compose up --build
```

Open http://localhost:3000. Schema changes need a fresh volume: `docker compose down -v`.

Note: the Gradium account allows 3 concurrent sessions, so only one live lesson at a time is safe.

## Tests

```bash
cd lessons_planning_workflow && uv run pytest              # deterministic, needs postgres on :5433
cd lessons_planning_workflow && RUN_LIVE=1 uv run pytest   # + live persona tests (OpenRouter)
cd voice_agent && RUN_LIVE=1 uv run pytest                 # tutor state + live behaviour tests
cd frontend && npm test
```

# Lumi: AI language teacher

Ten-minute spoken lessons with a voice tutor. A learner signs in with an email, answers three onboarding questions, gets a long-term plan, and then talks each lesson through live with Lumi, which ticks off the lesson's goals as they go. Setup, API keys and troubleshooting live in [README.md](README.md).

## Run

```bash
cp .env.example .env   # fill in OpenRouter, Gradium and LiveKit keys
docker compose up
```

`docker compose up` is the one command for the whole stack: every service has `pull_policy: build`, so it rebuilds from current source each time. App on http://localhost:3000. Schema changes in `db/init.sql` only apply to a fresh volume: `docker compose down -v`.

## Layout

| Folder | Service | Stack |
|---|---|---|
| `frontend/` | Next.js app (:3000) | Next 15 App Router, React 19, server actions, plain CSS, `pg` |
| `lessons_planning_workflow/` | lesson planner (:8000) | FastAPI + Agno, Pydantic models, uv |
| `voice_agent/api/` | voice API (:8100) | FastAPI, mints LiveKit room tokens |
| `voice_agent/tutor/` | voice worker | LiveKit Agents 1.8, Gradium STT/TTS, OpenRouter LLM |
| `db/init.sql` | Postgres (:5433 on host) | answers, plans, plan units, lessons |

Flow: frontend → planner (`/get_next_lesson/`, `/progress/{user}`) and → voice API (`/api/session` proxies it) → LiveKit dispatches the worker. The worker reports goal ticks over a data channel topic and back to the planner.

## Rules that are easy to break

- **The planner is the only writer** of plans and lessons. The frontend writes onboarding answers only; the worker records progress through the planner's HTTP API.
- **Target languages are en, es, de, fr only.** Gradium rejects Italian (`voice_agent/scripts/probe_gradium.py`). Keep `frontend/lib/languages.ts`, `lessons_planning_workflow/planner/languages.py` and `voice_agent/tutor/languages.py` in sync.
- **The tutor speaks only the target language.** Don't write UI copy that promises explanations in the learner's native language.
- **Gradium concurrency is plan-limited** (the dev account allows 3 sessions), so assume one live lesson at a time.
- The user id is the email, stored in an httpOnly cookie (`frontend/lib/session.ts`); there is no other auth.
- The git remote is named `main`, not `origin`: `git push -u main <branch>`.

## Tests

```bash
cd frontend && npm test && npx tsc --noEmit
cd lessons_planning_workflow && uv run pytest              # needs postgres on :5433
cd lessons_planning_workflow && RUN_LIVE=1 uv run pytest   # + live OpenRouter persona tests
cd voice_agent && RUN_LIVE=1 uv run pytest
```

Live tests cost OpenRouter credit; they are skipped unless `RUN_LIVE=1`.

## Frontend design system

Audience: busy adults, often on a phone with headphones. Tone: warm, encouraging coach; praise effort, never shame missed days; explain connection and mic problems kindly with a way forward. Grown-up playful, not a kids' app.

- **Tokens** are CSS custom properties at the top of `frontend/app/globals.css` (cream `--bg`, teal `--primary`, yellow `--sun`, green `--leaf`, `--ease`, `--spring`, `--press`). Use them; don't add raw colors. All styling is plain CSS in that one file, BEM-ish class names.
- **Chunky, pressable controls**: buttons, choices, chips and path nodes sit on a `0 var(--press) 0` shadow and drop by `--press` on `:active`. New interactive elements should follow the same pattern.
- **Lumi** (`components/Lumi.tsx`) is the SVG tutor character. Pass a `state` (`idle`, `happy`, `speaking`, `listening`, `thinking`, `connecting`) rather than building new faces; the CSS under `/* Lumi */` drives the expressions.
- **Icons and flags are SVG**: `components/Icon.tsx` (one stroke set, add paths there) and `components/Flag.tsx`. No emoji as icons.
- **Onboarding steps** use `WizardShell` (speech bubble, back link, progress bar) and put their submit button in a `.dock` (sticky bottom bar) inside a `.form--docked` form; disable the button until an answer is chosen.
- **Motion**: fast feedback (100–300 ms) with `--ease`, a little `--spring` overshoot for picks and pops. Every animation must degrade under `prefers-reduced-motion` (the global rule at the bottom of `globals.css` handles most cases).
- **Accessibility**: WCAG AA contrast, visible `:focus-visible` rings, color never the only signal (goal checks pair an icon with `sr-only` text), large tap targets.

## LiveKit work

Project-level LiveKit skills are installed (see `skills-lock.json`) and the LiveKit docs MCP server is configured in `.mcp.json`. Check the docs before changing worker or SDK code; the Agents SDK moves fast.

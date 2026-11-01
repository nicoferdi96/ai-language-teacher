# Lumi: AI language teacher

Ten-minute spoken lessons with a voice tutor. A learner signs in with an email, answers three onboarding questions, gets a long-term plan, and then talks each lesson through live with Lumi. Each lesson is a goal plus 5 planned steps, and Lumi ticks the steps off as they go. Setup, API keys and troubleshooting live in [README.md](README.md).

## Run

```bash
cp .env.example .env   # fill in Claude, Soniox, Cartesia and LiveKit keys
docker compose up
```

`docker compose up` is the one command for the whole stack: every service has `pull_policy: build`, so it rebuilds from current source each time. App on http://localhost:3000. Schema changes in `db/init.sql` only apply to a fresh volume: `docker compose down -v`.

## Layout

| Folder | Service | Stack |
|---|---|---|
| `frontend/` | Next.js app (:3000) | Next 15 App Router, React 19, server actions, plain CSS, `pg` |
| `lessons_planning_workflow/` | lesson planner (:8000) | FastAPI + Agno (Claude Haiku 5.5), Pydantic models, uv |
| `voice_agent/api/` | voice API (:8100) | FastAPI, mints LiveKit room tokens |
| `voice_agent/agent.py` + `voice_agent/tutor/` | voice worker | LiveKit Agents 1.8, Soniox STT, Cartesia TTS, Claude Haiku 5.5 LLM. `agent.py` holds the `Lumi` lesson agent, pipeline, server and entrypoint (`python agent.py dev`). `tutor/` holds: lesson models + state + timer (`lesson.py`), one `AgentTask` per step in a `TaskGroup` (`steps.py`), the read-only lesson loader (`store.py`), planner client + recorder, `turn.py` turn-taking, prompts, languages, telemetry, `settings.py` (pydantic-settings, every env var) |
| `db/init.sql` | Postgres (:5433 on host) | answers, plans, plan units, lessons, lesson steps |

Flow: frontend → planner (`/get_next_lesson/`, `/progress/{user}`) and → voice API (`/api/session` proxies it) → LiveKit dispatches the worker with only the lesson id. The worker loads the goal and steps from Postgres while it joins the room, then reports step ticks over a data channel topic and back to the planner.

## Rules that are easy to break

- **The planner is the only writer** of plans and lessons. The frontend writes onboarding answers only. The worker reads `lessons`/`lesson_steps` read-only (`tutor/store.py`) and records progress through the planner's HTTP API.
- **A lesson is exactly `STEPS_PER_LESSON` (5) steps** (`planner/models.py`, `CHECK` in `db/init.sql`). In the worker each step is a `LessonStepTask` in a `TaskGroup` with `summarize_chat_ctx=False`; steps strip tool calls from the shared history on entry. Code, not the model, decides the outcome (all steps done = completed). Fixed lines (the planner's `opening_line`) go out with `session.say()`, not the LLM.
- **Target languages are en, es, de, fr only** (`voice_agent/scripts/probe_speech.py` round-trips each). Keep `frontend/lib/languages.ts`, `lessons_planning_workflow/planner/languages.py` and `voice_agent/tutor/languages.py` in sync.
- **The tutor speaks only the target language.** Don't write UI copy that promises explanations in the learner's native language.
- **Turn timings live in `voice_agent/tutor/turn.py`**, copied from unmute-core's balanced LiveKit pace (VAD 0.3 s, dynamic endpointing 0.3–1.6 s, adaptive interruption, preemptive generation). Change them only with before/after numbers from the worker's `turn:` log lines.
- **All LLMs are Claude via the Anthropic API**, keyed by `CLAUDE_API_KEY` (passed explicitly; the SDKs default to `ANTHROPIC_API_KEY`). Claude 5 models reject `temperature`: never send one. The tutor's `TutorLLM` (`agent.py`) adds adaptive thinking at low effort to every request and drops any `temperature` (LiveKit's `judge` adds one); with thinking disabled Haiku skipped goal ticks.
- **Soniox interims are already the whole line so far**; don't join them again.
- **Tracing is Langfuse Python SDK v4** (`<5`), always with the `x-langfuse-ingestion-version: 4` header. Each LLM call must be exactly one priced generation (an observation with a model):
  - **Planner** (`planner/tracing.py`): the Anthropic SDK's own `anthropic.messages.create` span is the generation (usage, effort, prompt via `ANTHROPIC_TELEMETRY` content mode); `run_traced` wraps it in a model-less `agent` observation with the run's input, output and status. `tag_lesson_session` puts the run's root and `prepare-lesson` in the lesson's Langfuse session (`session.id` = lesson uuid), next to the voice lesson.
  - **Worker** (`tutor/telemetry.py`): routes LiveKit's built-in OTel spans and stamps the lesson on each via `LessonStamp`, because `propagate_attributes` misses spans LiveKit starts in other tasks. LiveKit's `llm_request` is the generation, so the Anthropic SDK's spans are dropped. The exporter (`rewrite`) keeps `job_entrypoint` the only trace root (Langfuse's processor also marks each `on_enter`), strips the model from `start_agent_activity` and `llm_node`/`llm_request_run`/`tts_node`/`tts_request_run` and maps LiveKit's `lk.*` attributes onto Langfuse fields: `tts_request` (text in, audio seconds out, characters as usage), `user_turn` (transcript out, turn length and STT event counts), `agent_turn` input/output, latencies as `langfuse.observation.metadata.*`. Streaming STT has no request span, so `record_stt_usage` writes one `stt_usage` generation (audio seconds) per lesson at shutdown. Langfuse v4 reads a trace's input/output from its root, so `record_lesson_outcome` writes the goal and steps in and the outcome out on LiveKit's `job_entrypoint` (kept by `LessonStamp`). LiveKit ends that root after the shutdown callbacks, so `FlushOnJobEnd` flushes when it ends; a flush inside a shutdown callback misses it. STT/TTS have usage but no Langfuse price, on purpose.
- The user id is the email, stored in an httpOnly cookie (`frontend/lib/session.ts`); there is no other auth.
- The git remote is named `main`, not `origin`: `git push -u main <branch>`.

## Tests

```bash
cd frontend && npm test && npx tsc --noEmit
cd lessons_planning_workflow && uv run pytest              # needs postgres on :5433
cd lessons_planning_workflow && RUN_LIVE=1 uv run pytest   # + live persona tests (Anthropic)
cd voice_agent && RUN_LIVE=1 uv run pytest
```

Live tests cost Anthropic credit (the voice speech probe also costs Soniox/Cartesia credit); they are skipped unless `RUN_LIVE=1`.

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

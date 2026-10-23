# Lumi: AI language teacher

Ten-minute spoken lessons with a voice tutor, planned around each learner.

A learner signs in with an email, answers three onboarding questions (target language, native language, how they like to learn), and gets a long-term plan. Every visit the planner prepares the next ~10-minute lesson with checkable goals, and the learner talks it through live with Lumi, a voice tutor that ticks goals off as they go.

## Architecture

Lumi is one product made of several small apps, each in the runtime that suits it, wired together by Docker Compose.

| Service | Folder | Port | Runtime | Job |
|---|---|---|---|---|
| `frontend` | `frontend/` | 3000 | Node, Next.js 15 | Onboarding, home with the plan path, live lesson UI. |
| `lesson-planner` | `lessons_planning_workflow/` | 8000 | Python, FastAPI + Agno | Builds the learning plan and prepares each lesson. Only writer of plans and lessons. |
| `voice-api` | `voice_agent/api/` | 8100 | Python, FastAPI | Gets the next lesson and mints a LiveKit room token that dispatches the tutor. |
| `voice-worker` | `voice_agent/tutor/` | – | Python, LiveKit Agents | "Lumi", the real-time voice tutor that runs the lesson. |
| `postgres` | `db/init.sql` | 5433 on host | Postgres 17 | Onboarding answers, plans, plan units, lessons. |

### Why several services in one Compose file

- **Different workloads.** The planner makes slow LLM calls (up to two minutes on the first plan), the voice API answers in milliseconds, and the voice worker holds long-lived audio sessions with models loaded in memory. Keeping them apart means a slow plan never blocks a live lesson, and each can be restarted, scaled or deployed on its own.
- **The right language for each job.** The UI is TypeScript/React; the AI services are Python, where Agno and the LiveKit Agents SDK live. `voice-api` and `voice-worker` share one image (`voice_agent/`) with different start commands.
- **One owner for each piece of data.** The frontend writes only onboarding answers. Everything about plans and lessons goes through the planner's HTTP API, including progress from the voice worker. That keeps the rules (which unit is current, when a unit counts as done) in one place.
- **One command to run it.** Compose puts every service on one network, reads every key from one `.env`, starts Postgres first and waits for its health check, and with `pull_policy: build` rebuilds each image from source on `docker compose up`.

### How a lesson flows

```
                 ┌──────────────── Docker Compose network ────────────────┐
 browser ──────► │ frontend ──(1)──► lesson-planner ◄──(5)── voice-worker │
    ▲  │         │    │                 │   ▲                     ▲      │
    │  │         │   (2)               SQL  │(3)                  │      │
    │  │         │    ▼                 ▼   │                     │      │
    │  │         │ voice-api ───────► postgres                    │      │
    │  │         └────│───────────────────────────────────────────│──────┘
    │  │             (3) token + dispatch                         │
    │  └───────(4) audio + data ───► LiveKit Cloud ◄──────────────┘
    └──────────── goal ticks ◄──────────┘
```

1. After onboarding, and on every return visit, the frontend asks the planner to prepare the next lesson (`POST /get_next_lesson/`) and then reads the plan for the home screen (`GET /progress/{user}`).
2. **Start speaking** calls the frontend's `/api/session`, which forwards to `voice-api` (`POST /sessions`).
3. `voice-api` fetches the lesson package from the planner (reusing the open lesson) and returns a LiveKit token for a fresh room. The token's room configuration dispatches the `language-tutor` agent with the lesson package as job metadata.
4. The browser joins the room with the LiveKit React SDK. LiveKit Cloud starts a job on the voice worker, which talks with the learner and streams goal ticks back over a data channel (`lesson-progress` topic).
5. The worker records progress in the planner as it happens: lesson started, each objective met (with the learner's words as evidence), and the final outcome with a summary and new words.

### The lesson planner: an Agno agentic workflow

`lessons_planning_workflow/planner/workflow.py` is an [Agno](https://docs.agno.com) `Workflow` with three steps:

| Step | Who does it | What happens |
|---|---|---|
| `review_progress` | code | Loads a snapshot from Postgres: the learner's answers, their plan, the last lessons, and any lesson still open. |
| `ensure_plan` | `CurriculumAgent` | Only when the learner has no plan yet: designs a long-term plan and stores it. |
| `prepare_lesson` | `LessonAgent` | Reuses an open lesson if there is one; otherwise designs the next lesson and stores it. |

The two agents (`planner/agents.py`) are Agno `Agent`s with **structured output**: each has a Pydantic `output_schema`, gets a JSON prompt, and returns a validated model rather than free text.

- **CurriculumAgent** → `LearningPlanDraft`. Infers a starting CEFR level (A1–C2) from how the learner describes themselves, then writes 8–12 ordered units (vocabulary, grammar or conversation), each teachable in one or two 10-minute spoken lessons and weighted to the learner's goal and preferred style.
- **LessonAgent** → `LessonBriefDraft`. Sees the profile, the plan with unit statuses, the focus unit and the recent lessons (objectives met and unmet, new words, summaries). It writes the next lesson: 3–5 objectives small enough to check from what the learner *says*, 5–8 vocabulary items with meanings in the learner's native language, up to 4 recap terms, and 120–250 words of guidance for the tutor, including mistakes speakers of the learner's native language typically make. Unmet objectives from an unfinished lesson are carried forward first.

Design choice: **the model decides content, code owns state.** The agents never touch the database. Code picks the focus unit, merges recap terms, reuses an open lesson so a page refresh never creates a second one, holds a per-learner lock against concurrent requests, and marks a unit done only when a lesson on it was completed with every objective met.

The planner's API (`app.py`): `POST /get_next_lesson/`, `GET /progress/{user_id}`, `GET /lessons/{id}`, `POST /lessons/{id}/start`, `POST /lessons/{id}/objectives/{objective_id}`, `POST /lessons/{id}/complete`.

### The voice tutor: a LiveKit agent

`voice_agent/tutor/` runs on the [LiveKit Agents](https://docs.livekit.io/agents/) SDK as a worker connected to LiveKit Cloud. Each lesson is one job in its own room.

**Pipeline** (`session.py`, `turn.py`): a classic cascaded voice pipeline, chosen so each part can be swapped and the LLM can call tools mid-conversation. `worker.py` holds only the prewarm and the job entrypoint; `clock.py` is the lesson timer.

| Stage | Model | Notes |
|---|---|---|
| Voice activity | Silero VAD | Loaded once per worker process (`prewarm`) with a 0.3 s silence floor, weights baked into the image. |
| Turn detection | LiveKit audio turn detector `v1-mini` | Runs locally on CPU and judges the end of a turn from the audio itself, so it doesn't wait for a transcript. Dynamic endpointing between 0.3 and 1.6 s adapts to how long this learner pauses. |
| Speech to text | Gradium STT | Set to the lesson's target language. Gradium sends one word per partial transcript; `transcript.py` joins them so the live text shows the whole line. |
| LLM | `openai/gpt-5.4-nano` via OpenRouter | Minimal reasoning for low latency; models that accept it get temperature 0.1. Override with `VOICE_LLM_MODEL`. |
| Text to speech | Gradium TTS | One voice per language (`tutor/languages.py`). |

**Turn-taking** (`turn.py`) contains the VAD floor, the endpointing window, **adaptive interruption** (a short "sí" said over Lumi is heard as an answer and doesn't cut her off; a real barge-in does), **preemptive generation** (the LLM starts on the transcript before the turn is confirmed), and **yield to caller** (a reply that hasn't started playing is dropped if the learner keeps talking, so Lumi answers everything they said). The worker logs each turn's end-of-utterance delay, LLM first token and TTS first audio as `turn:` lines, so tune these values against those numbers.

**The agent** (`agent.py`, `prompt.py`): a single `TutorAgent` whose system prompt is built from the planner's lesson package. It speaks **only the target language**: it rephrases in simpler words instead of translating, keeps turns to one or two short sentences, and uses the native language only to anticipate typical mistakes. Its tools:

- `mark_objective_done(objective_id, evidence)`: allowed only once the learner has produced the target language themselves, not when they just said "yes" or the tutor said it for them.
- `lesson_status()`: remaining objectives and minutes left.
- `complete_lesson(summary, new_vocabulary)`: refused by code until every objective is done or time is up.
- `end_call` (LiveKit's `EndCallTool`): says goodbye in the target language and hangs up.

**Code-owned guardrails** around the model:

- `LessonState` (`lesson.py`) is the source of truth for objectives, timing and outcome.
- `LessonClock` nudges the tutor to wrap up at 85% of the lesson time and forces the close at 120%.
- `LessonRecorder` persists every change to the planner and mirrors it to the browser. Failures are logged, not passed to the model, and everything is re-sent when the lesson ends.
- If the learner leaves or the call drops, a shutdown callback records the lesson as completed (all goals met) or abandoned, so the planner picks up from there next time.
- If the learner never joins within 30 seconds the job leaves, and when the session closes the job shuts down so no Gradium session outlives the learner.

### LiveKit components we use

LiveKit handles all real-time audio. This is exactly which parts of it the app uses, and where.

| Layer | Component | Where | What it does here |
|---|---|---|---|
| Cloud | **LiveKit Cloud** (rooms and media server) | your project, `LIVEKIT_URL` | Hosts one WebRTC room per lesson, routes audio between browser and tutor, and dispatches the agent job when the learner joins. The free Build plan is enough to run the app. |
| Server SDK | **`livekit-api`** (Python): `AccessToken`, `VideoGrants`, `RoomConfiguration`, `RoomAgentDispatch` | `voice_agent/api/app.py` | Mints the learner's 30-minute join token for a fresh room. The token's room configuration names the `language-tutor` agent and carries the lesson package as metadata, so joining the room is what starts the tutor (explicit dispatch). |
| Agents SDK | **`livekit-agents` 1.8**: `AgentServer`, `@server.rtc_session(agent_name=...)`, `JobContext`, `JobProcess` | `voice_agent/tutor/worker.py` | The worker process. Registers with LiveKit Cloud under the name `language-tutor`, prewarms Silero once per process, and runs one job per lesson: connect, wait for the learner, start the session, publish progress, clean up on shutdown. |
| | `AgentSession`, `TurnHandlingOptions` | `session.py`, `turn.py` | Runs the voice pipeline (VAD → turn detection → STT → LLM → TTS), interruptions, and `generate_reply` for the greeting and the time nudges. It also publishes the agent's state and both speakers' transcripts to the room automatically, which is what the UI reads. |
| | `Agent`, `@function_tool`, `RunContext`, `ToolError` | `voice_agent/tutor/agent.py` | The tutor: system prompt plus the `mark_objective_done`, `lesson_status` and `complete_lesson` tools. `ToolError` sends a refusal back to the model, e.g. when it tries to complete a lesson too early. |
| | `EndCallTool` (beta) | `agent.py` | Ready-made hang-up tool: speaks a goodbye, then ends the session. |
| | `agents.cli` | `worker.py`, `Dockerfile` | `download-files` bakes model weights into the image; `start` runs the worker in Docker; `dev` runs it locally with reload. |
| Plugins | `livekit-plugins-gradium` | `session.py` | Gradium STT and TTS (your `GRADIUM_API_KEY`). |
| | `livekit-plugins-openai` (`openai.LLM.with_openrouter`) | `session.py` | Calls the LLM through OpenRouter's OpenAI-compatible API (your `OPENROUTER_API_KEY`). |
| | `livekit-plugins-silero` | `session.py` | Voice activity detection. |
| | `inference.TurnDetector(version="v1-mini")` and adaptive interruption | `turn.py` | Audio end-of-turn model, so Lumi waits while a learner pauses mid-sentence to think but answers quickly once they're done. The interruption model needs your LiveKit keys and is free within the development allowance. |
| Data | Room data messages (`publish_data`, topic `lesson-progress`) | `worker.py` → `LessonRoom.tsx` | Sends the full lesson state to the browser after every goal tick. |
| Browser | **`livekit-client` 2** and **`@livekit/components-react` 2.9** | `frontend/components/LessonRoom.tsx` | `LiveKitRoom` (connects with the token), `RoomAudioRenderer` (plays Lumi), `useLocalParticipant` (mic on/off), `useVoiceAssistant` (agent state and audio track), `BarVisualizer` (voice meter), `useTranscriptions` (live transcript), `useDataChannel` (goal ticks). |

Not used: LiveKit Inference (the app brings its own Gradium and OpenRouter keys), LiveKit Cloud agent hosting (the worker runs in your Docker), telephony/SIP, recording/egress and video.

### How the UI talks to the agents

The browser never calls an agent directly. Every request goes through the Next.js server (server components, server actions and the `/api/session` route), which reads the learner's email from an httpOnly cookie and calls the services over the Compose network. That keeps service URLs off the client and stops a browser from acting as another user. The email is the user id; there is no other auth.

**UI ↔ Agno planner (plain HTTP request/response)**

| Moment in the app | What the UI does | What the planner does |
|---|---|---|
| Onboarding steps | Server actions save each answer straight to Postgres (`answers` table, `frontend/lib/answers.ts`). This is the only data the frontend writes. | Nothing yet. |
| "Getting your lesson ready…" (`/wizard/preparing`) | The page's server component calls `POST /get_next_lesson/` and waits up to two minutes. Meanwhile Next.js streams `loading.tsx`, where Lumi narrates the steps. | Runs the workflow: reads the answers, builds the plan if needed, writes the next lesson. On success the UI redirects to home; on failure it shows a calm retry. |
| Home (`/home`) | Calls `GET /progress/{user}` and renders the plan path, today's lesson with its goals, and "Last time" from the previous lesson. | Returns the plan with unit statuses and the recent lessons. Read-only. |
| After a lesson | **Back to my path** goes to `/wizard/preparing` again. | Re-runs the workflow, which now sees the finished lesson and plans the next one. |

The planner's agents run only between lessons. The UI shows their output (plan units, lesson titles, objectives, vocabulary), but never talks to the LLM itself.

**UI ↔ LiveKit voice agent (real time over WebRTC)**

1. **Start the lesson** (`components/LessonRoom.tsx`) posts to `/api/session`. The click also counts as the user gesture browsers require before playing audio. The route forwards to `voice-api`, which returns the LiveKit URL, a 30-minute token for a fresh room, the progress topic and the lesson (title, duration, objectives).
2. The page mounts `<LiveKitRoom>` from `@livekit/components-react` with that token and turns on the microphone. Joining the room is what makes LiveKit dispatch the tutor job; if the agent hasn't arrived after 25 seconds the UI says so.
3. During the lesson the UI listens to three streams from the room:
   - **Audio:** `RoomAudioRenderer` plays Lumi's voice, and the learner's mic track goes to the agent.
   - **Agent state:** `useVoiceAssistant()` reports `listening`, `thinking` or `speaking`. That drives Lumi's face, the voice meter, the status line and the panel colour (yellow when it's the learner's turn).
   - **Transcripts:** `useTranscriptions()` gives the live text of both speakers for the Conversation panel.
4. **Goals** come over a LiveKit data channel. Whenever the agent's `mark_objective_done` or `complete_lesson` tool runs, the worker publishes the whole lesson state (objectives, outcome, summary, new words) on the `lesson-progress` topic. The UI swaps in that state, ticks the goal and shows a short "Goal reached" toast. Because the full state is re-sent every time, a missed message is fixed by the next one.
5. **Ending:** when the agent calls `end_call` or the learner presses **End lesson**, the room disconnects and the UI shows the wrap-up from the last progress message (summary, new words, goals). The worker has already saved the outcome in the planner, so the UI does not write anything itself.

The mic button, the timer and leaving the page are handled entirely in the browser; the agent learns about them only through audio and the room disconnecting, which its shutdown callback turns into a completed or abandoned lesson.

### Languages and models

Supported target languages: English, Spanish, German, French. Italian was dropped because Gradium rejects it (`Unsupported language 'it'`, see `voice_agent/scripts/probe_gradium.py`).

Both the planner and the tutor default to `openai/gpt-5.4-nano` through OpenRouter (minimal reasoning). Override with `PLANNER_MODEL` / `VOICE_LLM_MODEL`; models that accept it get temperature 0.1.

## Can anyone run it?

Yes. Nothing in the code is tied to one person's accounts: clone the repo, create your own (free or pay-as-you-go) accounts with the three providers, put the keys in `.env`, and run `docker compose up`. The Gradium voice IDs in `voice_agent/tutor/languages.py` are standard library voices, not custom ones (the English voice is the Gradium plugin's default), so they should work with any key. If your account rejects one, pick another voice in Gradium Studio and change its ID there.

| Provider | What for | Cost to get started |
|---|---|---|
| [LiveKit Cloud](https://cloud.livekit.io) | Real-time audio rooms and agent dispatch | Free Build plan, no credit card. It includes 5,000 WebRTC participant-minutes a month; the learner and the self-hosted tutor both count, so that's roughly 250 ten-minute lessons. |
| [OpenRouter](https://openrouter.ai) | The LLM for the planner and the tutor | Pay as you go. With the default nano model a plan plus a lesson costs very little; add a few dollars of credit. |
| [Gradium](https://studio.gradium.ai) | Speech-to-text and text-to-speech | Depends on your Gradium plan. Check its concurrent-session limit: each live lesson holds speech sessions open. |

Everything runs on your machine. The voice worker connects *out* to LiveKit Cloud, so there are no ports to open or webhooks to set up, and it works on a laptop behind a home router.

**Inside the app, "signing up" is just typing an email.** There is no password: the email becomes the user id and is kept in a cookie. Several people can share one running copy (each with their own email, and so their own plan), which is fine on `localhost` or a trusted network. Don't put it on the public internet as is: anyone who can reach it could open someone else's plan by typing their email. Real authentication would be needed first.

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
| `GRADIUM_API_KEY` | Yes | [studio.gradium.ai → API keys](https://studio.gradium.ai/platform/api-keys). Covers speech-to-text and text-to-speech for en, es, de, fr. | voice worker |
| `LIVEKIT_URL` | Yes | [cloud.livekit.io](https://cloud.livekit.io) → your project → Settings. Looks like `wss://<project>.livekit.cloud`. | voice API, voice worker |
| `LIVEKIT_API_KEY` | Yes | Same project → Settings → API keys → create key. | voice API, voice worker |
| `LIVEKIT_API_SECRET` | Yes | Shown once when you create the API key. | voice API, voice worker |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Yes (defaults provided) | Pick any values; Compose creates the database with them. | postgres, planner |
| `PLANNER_MODEL` / `VOICE_LLM_MODEL` | No | Any OpenRouter model id, e.g. `openai/gpt-5.4-mini`. Empty means the default. | planner, tutor |
| `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_BASE_URL` | No | [Langfuse](https://cloud.langfuse.com) project settings, for tracing. | planner |

Tip: with the [LiveKit CLI](https://docs.livekit.io/home/cli/) installed, `lk project list` shows your project URL.

Never commit `.env`; it is already in `.gitignore`.

## Run everything

One command starts the whole stack (Postgres, planner, voice API, voice worker, frontend):

```bash
cp .env.example .env    # once, then fill in the keys above
docker compose up
```

Every service is set to `pull_policy: build`, so `docker compose up` rebuilds the images from your current code each time (unchanged layers come from the cache; the first run takes a few minutes). Open <http://localhost:3000> once the frontend logs `Ready`.

- Run in the background: `docker compose up -d`, then `docker compose logs -f`
- Stop everything: `docker compose down`
- Reset the database (needed after schema changes in `db/init.sql`): `docker compose down -v`
- Follow one service: `docker compose logs -f voice-worker`

How many lessons can run at once depends on your Gradium plan's concurrent-session limit. The account used in development allowed 3 sessions, which is enough for one live lesson at a time.

## Using the app

1. **Sign in.** Enter any email on the landing page. It is your user id; use the same one to come back to your plan.
2. **Onboarding.** Answer three quick questions: the language to learn, your native language, and how you like to learn. The back arrow returns to the previous step, and Continue turns on once you pick something.
3. **Plan.** The planner builds your plan and first lesson (this takes a few seconds; Lumi shows what it is doing).
4. **Home.** See today's lesson, its goals and your path. Press **Start speaking**.
5. **Lesson.** Allow the microphone and talk with Lumi for about ten minutes. Lumi only speaks the language you are learning. Goals tick off live as you hit them, and the transcript follows along on the side. Press **End lesson** whenever you like.
6. **Wrap-up.** You get a summary, the new words and the goals you reached. Next time, the planner picks up from there.

## Run services by hand (optional, for development)

`docker compose up` is all you need to run the app. Running services by hand is only useful when you want hot reload while changing code. Run Postgres in Docker and every other service on your machine, each in its own terminal, all from the repository root.

**1. Postgres** (published on host port 5433):

```bash
docker compose up -d postgres
```

**2. Lesson planner** (reads `POSTGRES_*` from `.env`, connects to `localhost:5433`):

```bash
cd lessons_planning_workflow && uv sync && uv run uvicorn app:app --reload --port 8000
```

**3. Voice worker** (first run downloads the VAD model):

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

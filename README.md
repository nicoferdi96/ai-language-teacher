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
| `voice-worker` | `voice_agent/agent.py`, `voice_agent/tutor/` | – | Python, LiveKit Agents | "Lumi", the real-time voice tutor that runs the lesson. |
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
3. `voice-api` asks the planner for the next lesson (reusing the open lesson) and returns a LiveKit token for a fresh room. The token's room configuration dispatches the `language-tutor` agent with only the lesson's id (and the fields its traces are tagged with) as job metadata.
4. The browser joins the room with the LiveKit React SDK. LiveKit Cloud starts a job on the voice worker, which reads the lesson's goal and steps straight from Postgres (read-only) while it joins the room, talks with the learner and streams goal ticks back over a data channel (`lesson-progress` topic).
5. The worker records progress in the planner as it happens: lesson started, each step done (with the learner's words as evidence), and the final outcome with a summary and new words. The planner stays the only writer of plans and lessons.

### The lesson planner: an Agno agentic workflow

`lessons_planning_workflow/planner/workflow.py` is an [Agno](https://docs.agno.com) `Workflow` with three steps:

| Step | Who does it | What happens |
|---|---|---|
| `review_progress` | code | Loads a snapshot from Postgres: the learner's answers, their plan, the last lessons, and any lesson still open. |
| `ensure_plan` | `CurriculumAgent` | Only when the learner has no plan yet: designs a long-term plan and stores it. |
| `prepare_lesson` | `LessonAgent` | Reuses an open lesson if there is one; otherwise designs the next lesson and stores it. |

The two agents (`planner/agents.py`) are Agno `Agent`s with **structured output**: each has a Pydantic `output_schema`, gets a JSON prompt, and returns a validated model rather than free text.

- **CurriculumAgent** → `LearningPlanDraft`. Infers a starting CEFR level (A1–C2) from how the learner describes themselves, then writes 8–12 ordered units (vocabulary, grammar or conversation), each teachable in one or two 10-minute spoken lessons and weighted to the learner's goal and preferred style.
- **LessonAgent** → `LessonPlanDraft`, a step-by-step plan. Sees the profile, the plan with unit statuses, the focus unit and the recent lessons (steps met and unmet, new words, summaries). It writes:
  - a nested `goal`: the `aim` (what the learner will be able to say) and the `prompt` that guides the tutor for the whole lesson, including mistakes speakers of the learner's native language typically make
  - exactly **5 `steps`** (`STEPS_PER_LESSON`), each a `task` small enough to check from what the learner *says* and the `prompt` the tutor follows while coaching it: warm-up, new phrases, practice, role-play, recap
  - an `opening_line` in the target language, which the tutor speaks word for word
  - 5–8 vocabulary items with meanings in the learner's native language, and up to 4 recap terms (folded into the goal prompt)

  Unmet steps from an unfinished lesson are carried forward first. The lesson goes in `lessons`, its steps in `lesson_steps`.

Design choice: **the model decides content, code owns state.** The agents never touch the database. Code picks the focus unit, merges recap terms, reuses an open lesson so a page refresh never creates a second one, holds a per-learner lock against concurrent requests, and marks a unit done only when a lesson on it was completed with every step done.

The planner's API (`app.py`): `POST /get_next_lesson/`, `GET /progress/{user_id}`, `GET /lessons/{id}`, `POST /lessons/{id}/start`, `POST /lessons/{id}/steps/{position}`, `POST /lessons/{id}/complete`.

### The voice tutor: a LiveKit agent

`voice_agent/agent.py` (with its helpers in `voice_agent/tutor/`) runs on the [LiveKit Agents](https://docs.livekit.io/agents/) SDK as a worker connected to LiveKit Cloud. Each lesson is one job in its own room.

**Pipeline** (`agent.py`, `tutor/turn.py`): a classic cascaded voice pipeline, chosen so each part can be swapped and the LLM can call tools mid-conversation. `agent.py` is the one file to read: the agent, `build_session`, the prewarm and the job entrypoint. Configuration comes from `tutor/settings.py`, a pydantic-settings model over the environment.

| Stage | Model | Notes |
|---|---|---|
| Voice activity | Silero VAD | Loaded once per worker process (`prewarm`) with a 0.3 s silence floor, weights baked into the image. |
| Turn detection | LiveKit audio turn detector `v1-mini` | Runs locally on CPU and judges the end of a turn from the audio itself, so it doesn't wait for a transcript. Dynamic endpointing between 0.3 and 1.6 s adapts to how long this learner pauses. |
| Speech to text | Soniox `stt-rt-v5` | Hinted (not locked) to the lesson's target language; finalizes after 500 ms of quiet (`STT_MAX_ENDPOINT_DELAY_MS`). |
| LLM | Claude Haiku 5.5 (`claude-haiku-5-5`) | Adaptive thinking at low effort, prompt caching on. `VOICE_LLM_THINKING=disabled` is ~0.5 s faster to first token but misses goal ticks. Override the model with `VOICE_LLM_MODEL`. |
| Text to speech | Cartesia Sonic 3.6 | One multilingual voice (Daniel) for every language, set by `TTS_VOICE`; transcripts are aligned to the audio. |

**Turn-taking** (`turn.py`) contains the VAD floor, the endpointing window, **adaptive interruption** (a short "sí" said over Lumi is heard as an answer and doesn't cut her off; a real barge-in does), **preemptive generation** (the LLM starts on the transcript before the turn is confirmed), and **yield to caller** (a reply that hasn't started playing is dropped if the learner keeps talking, so Lumi answers everything they said). The worker logs each turn's end-of-utterance delay, LLM first token and TTS first audio as `turn:` lines, so tune these values against those numbers.

**The agent and its steps** (`agent.py`, `tutor/steps.py`, `tutor/prompt.py`): the lesson is a LiveKit [task group](https://docs.livekit.io/agents/logic/tasks/).
- `Lumi` is the lesson agent. Its prompt holds the persona, the language rule, the lesson goal and an outline of the steps.
- On entering, `Lumi`:
  1. speaks the planner's `opening_line` with `session.say()` (no LLM call)
  2. runs the steps
  3. records the outcome
  4. asks the LLM for a short spoken recap and goodbye, then ends the session
- Each step is a `LessonStepTask` (`AgentTask[StepResult]`) in a `TaskGroup`. Its prompt is the same core plus only that step's coaching.
- Every step gets the full conversation so far, minus tool calls. The learner can ask to go back to an earlier step, and the group's `out_of_scope` tool re-enters it.
- Lumi speaks **only the target language**: it rephrases in simpler words instead of translating, keeps turns to one or two short sentences, and uses the native language only to anticipate typical mistakes.

The model's tools:
- `complete_step(evidence, new_vocabulary)` (in each step): finishes the step with a Pydantic `StepResult`. The model should call it only once the learner has produced the target language themselves, not when they just said "yes" or the tutor said it for them.
- `out_of_scope(task_ids)` (added by `TaskGroup` once a step was visited): goes back to an earlier step.
- `end_call` (LiveKit's `EndCallTool`): says goodbye in the target language and hangs up.

**Code-owned guardrails** around the model:

- `LessonState` (`lesson.py`) is the source of truth for steps, new words, timing and outcome. Code sets the outcome: completed when every step is done, else abandoned.
- `LessonTimer` (`lesson.py`) stops the running step at 95% of the lesson time (`LessonSteps.stop` raises `LessonTimeUp` into it), so the tutor wraps up.
- `LessonStore` (`store.py`) reads the lesson, its steps and the learner's profile in one read-only query when the job starts, in parallel with joining the room. Prewarm only loads the VAD and tracing, because it runs before any lesson is known.
- `LessonRecorder` (`planner.py`) persists every change to the planner and mirrors it to the browser. Failures are logged, not passed to the model, and everything is re-sent when the lesson ends.
- If the learner leaves or the call drops, a shutdown callback records the lesson as completed (all steps done) or abandoned, so the planner picks up from there next time.
- If the learner never joins within 30 seconds the job leaves, and when the session closes the job shuts down so no speech session outlives the learner.

### LiveKit components we use

LiveKit handles all real-time audio. This is exactly which parts of it the app uses, and where.

| Layer | Component | Where | What it does here |
|---|---|---|---|
| Cloud | **LiveKit Cloud** (rooms and media server) | your project, `LIVEKIT_URL` | Hosts one WebRTC room per lesson, routes audio between browser and tutor, and dispatches the agent job when the learner joins. The free Build plan is enough to run the app. |
| Server SDK | **`livekit-api`** (Python): `AccessToken`, `VideoGrants`, `RoomConfiguration`, `RoomAgentDispatch` | `voice_agent/api/app.py` | Mints the learner's 30-minute join token for a fresh room. The token's room configuration names the `language-tutor` agent and carries the lesson's id as metadata, so joining the room is what starts the tutor (explicit dispatch). |
| Agents SDK | **`livekit-agents` 1.8**: `AgentServer`, `@server.rtc_session(agent_name=...)`, `JobContext`, `JobProcess` | `voice_agent/agent.py` | The worker process. Registers with LiveKit Cloud under the name `language-tutor`, prewarms Silero once per process, and runs one job per lesson: connect, wait for the learner, start the session, publish progress, clean up on shutdown. |
| | `AgentSession`, `TurnHandlingOptions` | `agent.py`, `tutor/turn.py` | Runs the voice pipeline (VAD → turn detection → STT → LLM → TTS), interruptions, `say` for the fixed opening line and `generate_reply` for each step's lead-in and the closing recap. It also publishes the agent's state and both speakers' transcripts to the room automatically, which is what the UI reads. |
| | `Agent`, `AgentTask`, `@function_tool` | `agent.py`, `tutor/steps.py` | The lesson agent (`Lumi`) and one `LessonStepTask` per planned step, each with a `complete_step` tool returning a `StepResult`. |
| | `TaskGroup` (beta workflows) | `tutor/steps.py` | Runs the steps in order with a shared history (no summary, tool calls dropped) and lets the learner go back to an earlier step. |
| | `EndCallTool` (beta) | `agent.py` | Ready-made hang-up tool: speaks a goodbye, then ends the session. |
| | `agents.cli` | `agent.py`, `Dockerfile` | `download-files` bakes model weights into the image; `start` runs the worker in Docker; `dev` runs it locally with reload. |
| Plugins | `livekit-plugins-soniox`, `livekit-plugins-cartesia` | `agent.py` | Soniox STT and Cartesia TTS (your `SONIOX_API_KEY`, `CARTESIA_API_KEY`). |
| | `livekit-plugins-anthropic` (`TutorLLM`) | `agent.py` | Calls Claude directly (your `CLAUDE_API_KEY`). |
| | `livekit-plugins-silero` | `tutor/turn.py` | Voice activity detection. |
| | `inference.TurnDetector(version="v1-mini")` and adaptive interruption | `turn.py` | Audio end-of-turn model, so Lumi waits while a learner pauses mid-sentence to think but answers quickly once they're done. The interruption model needs your LiveKit keys and is free within the development allowance. |
| Data | Room data messages (`publish_data`, topic `lesson-progress`) | `tutor/planner.py` (`LessonRecorder`) → `LessonRoom.tsx` | Sends the full lesson state to the browser after every goal tick. |
| Browser | **`livekit-client` 2** and **`@livekit/components-react` 2.9** | `frontend/components/LessonRoom.tsx` | `LiveKitRoom` (connects with the token), `RoomAudioRenderer` (plays Lumi), `useLocalParticipant` (mic on/off), `useVoiceAssistant` (agent state and audio track), `BarVisualizer` (voice meter), `useTranscriptions` (live transcript), `useDataChannel` (goal ticks). |

Not used: LiveKit Inference (the app brings its own Soniox, Cartesia and Anthropic keys), LiveKit Cloud agent hosting (the worker runs in your Docker), telephony/SIP, recording/egress and video.

### How the UI talks to the agents

The browser never calls an agent directly. Every request goes through the Next.js server (server components, server actions and the `/api/session` route), which reads the learner's email from an httpOnly cookie and calls the services over the Compose network. That keeps service URLs off the client and stops a browser from acting as another user. The email is the user id; there is no other auth.

**UI ↔ Agno planner (plain HTTP request/response)**

| Moment in the app | What the UI does | What the planner does |
|---|---|---|
| Onboarding steps | Server actions save each answer straight to Postgres (`answers` table, `frontend/lib/answers.ts`). This is the only data the frontend writes. | Nothing yet. |
| "Getting your lesson ready…" (`/wizard/preparing`) | The page's server component calls `POST /get_next_lesson/` and waits up to two minutes. Meanwhile Next.js streams `loading.tsx`, where Lumi narrates the steps. | Runs the workflow: reads the answers, builds the plan if needed, writes the next lesson. On success the UI redirects to home; on failure it shows a calm retry. |
| Home (`/home`) | Calls `GET /progress/{user}` and renders the plan path, today's lesson with its goals, and "Last time" from the previous lesson. | Returns the plan with unit statuses and the recent lessons. Read-only. |
| After a lesson | **Back to my path** goes to `/wizard/preparing` again. | Re-runs the workflow, which now sees the finished lesson and plans the next one. |

The planner's agents run only between lessons. The UI shows their output (plan units, lesson titles, step tasks, vocabulary), but never talks to the LLM itself.

**UI ↔ LiveKit voice agent (real time over WebRTC)**

1. **Start the lesson** (`components/LessonRoom.tsx`) posts to `/api/session`. The click also counts as the user gesture browsers require before playing audio. The route forwards to `voice-api`, which returns the LiveKit URL, a 30-minute token for a fresh room, the progress topic and the lesson (title, duration, step tasks; the coaching prompts stay on the server).
2. The page mounts `<LiveKitRoom>` from `@livekit/components-react` with that token and turns on the microphone. Joining the room is what makes LiveKit dispatch the tutor job; if the agent hasn't arrived after 25 seconds the UI says so.
3. During the lesson the UI listens to three streams from the room:
   - **Audio:** `RoomAudioRenderer` plays Lumi's voice, and the learner's mic track goes to the agent.
   - **Agent state:** `useVoiceAssistant()` reports `listening`, `thinking` or `speaking`. That drives Lumi's face, the voice meter, the status line and the panel colour (yellow when it's the learner's turn).
   - **Transcripts:** `useTranscriptions()` gives the live text of both speakers for the Conversation panel.
4. **Goals** come over a LiveKit data channel. Whenever a step finishes or the lesson ends, the worker publishes the whole lesson state (steps, outcome, summary, new words) on the `lesson-progress` topic. The UI swaps in that state, ticks the goal and shows a short "Goal reached" toast. Because the full state is re-sent every time, a missed message is fixed by the next one.
5. **Ending:** when the agent calls `end_call` or the learner presses **End lesson**, the room disconnects and the UI shows the wrap-up from the last progress message (summary, new words, goals). The worker has already saved the outcome in the planner, so the UI does not write anything itself.

The mic button, the timer and leaving the page are handled entirely in the browser; the agent learns about them only through audio and the room disconnecting, which its shutdown callback turns into a completed or abandoned lesson.

### Languages and models

Supported target languages: English, Spanish, German, French. `voice_agent/scripts/probe_speech.py` round-trips a sentence in each through Cartesia and Soniox.

Both the planner and the tutor default to Claude Haiku 5.5 (`claude-haiku-5-5`) at low effort. Override with `PLANNER_MODEL` / `VOICE_LLM_MODEL`; no temperature is sent, because Claude 5 models reject it.

## Can anyone run it?

Yes. Nothing in the code is tied to one person's accounts: clone the repo, create your own (free or pay-as-you-go) accounts with the providers, put the keys in `.env`, and run `docker compose up`. The Cartesia voice (Daniel, `47c38ca4-5f35-497b-b1a3-415245fb35e1`) is a standard library voice that speaks all four languages, so it should work with any key. To change it, pick another in the [Cartesia voice library](https://play.cartesia.ai/voices) and set `TTS_VOICE`.

| Provider | What for | Cost to get started |
|---|---|---|
| [LiveKit Cloud](https://cloud.livekit.io) | Real-time audio rooms and agent dispatch | Free Build plan, no credit card. It includes 5,000 WebRTC participant-minutes a month; the learner and the self-hosted tutor both count, so that's roughly 250 ten-minute lessons. |
| [Anthropic](https://console.anthropic.com) | Claude for the planner and the tutor | Pay as you go. Haiku 5.5 is $0.10 / $0.50 per million tokens, so a plan plus a lesson costs very little. |
| [Soniox](https://console.soniox.com) | Speech-to-text | Pay as you go; keep a balance, or STT fails with a 402. |
| [Cartesia](https://play.cartesia.ai) | Text-to-speech | Depends on your Cartesia plan. |

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
| `CLAUDE_API_KEY` | Yes | [console.anthropic.com → API keys](https://console.anthropic.com/account/keys). `ANTHROPIC_API_KEY` works too. | planner agents, tutor LLM |
| `SONIOX_API_KEY` | Yes | [console.soniox.com](https://console.soniox.com). Speech-to-text. | voice worker |
| `CARTESIA_API_KEY` | Yes | [play.cartesia.ai/keys](https://play.cartesia.ai/keys). Text-to-speech. | voice worker |
| `LIVEKIT_URL` | Yes | [cloud.livekit.io](https://cloud.livekit.io) → your project → Settings. Looks like `wss://<project>.livekit.cloud`. | voice API, voice worker |
| `LIVEKIT_API_KEY` | Yes | Same project → Settings → API keys → create key. | voice API, voice worker |
| `LIVEKIT_API_SECRET` | Yes | Shown once when you create the API key. | voice API, voice worker |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Yes (defaults provided) | Pick any values; Compose creates the database with them. | postgres, planner |
| `PLANNER_MODEL` / `VOICE_LLM_MODEL` | No | Any Claude model id, e.g. `claude-sonnet-5-5`. Empty means `claude-haiku-5-5`. | planner, tutor |
| `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_BASE_URL` | No | [Langfuse](https://cloud.langfuse.com) project settings, for tracing. Empty means no tracing. | planner, tutor |

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

How many lessons can run at once depends on your Soniox and Cartesia plans' concurrency limits; each live lesson holds one STT and one TTS stream open.

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
cd voice_agent && uv sync && uv run python agent.py download-files && uv run python agent.py dev
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
cd lessons_planning_workflow && RUN_LIVE=1 uv run pytest   # + live persona tests (Anthropic)
cd voice_agent && RUN_LIVE=1 uv run pytest                 # tutor state + live behaviour tests
cd frontend && npm test
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "I couldn't prepare your lesson just yet" | The planner can't reach Anthropic or Postgres. Check `CLAUDE_API_KEY` and `docker compose logs lesson-planner`. |
| Lesson screen says "Lumi is taking a while…" | The voice worker isn't connected to LiveKit. Check the three `LIVEKIT_*` values and `docker compose logs voice-worker`. |
| Lumi joins but never speaks | Cartesia or Anthropic rejected the key. Check `CARTESIA_API_KEY` / `CLAUDE_API_KEY` and `docker compose logs voice-worker`. |
| Lumi never hears you | Soniox rejected the key or ran out of balance (402 in the worker log). Check `SONIOX_API_KEY` and your Soniox balance. |
| "Microphone access is blocked" | Allow the mic for `localhost:3000` in the browser's address bar, then press Start again. |
| Port 5432/3000 already in use | Postgres is published on 5433 to avoid a local install; stop whatever else uses 3000 or change the `ports` mapping in `docker-compose.yaml`. |

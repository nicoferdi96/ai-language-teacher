"use client";

import {
  BarVisualizer,
  LiveKitRoom,
  RoomAudioRenderer,
  useDataChannel,
  useLocalParticipant,
  useTranscriptions,
  useVoiceAssistant,
} from "@livekit/components-react";
import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Flag } from "@/components/Flag";
import { Goals } from "@/components/Goals";
import { Icon } from "@/components/Icon";
import { Lumi } from "@/components/Lumi";
import { Brand } from "@/components/WizardShell";
import { findTargetLanguage } from "@/lib/languages";
import type { Objective, VocabularyItem } from "@/lib/planner";

type LessonInfo = {
  lesson_uuid: string;
  target_language: string;
  title: string;
  duration_minutes: number;
  objectives: Objective[];
};

type SessionInfo = {
  server_url: string;
  participant_token: string;
  progress_topic: string;
  lesson: LessonInfo;
};

type Progress = {
  objectives: Objective[];
  outcome: "completed" | "abandoned" | null;
  summary: string | null;
  new_vocabulary: VocabularyItem[];
};

type Phase = "ready" | "starting" | "live" | "ended" | "error";

const AGENT_JOIN_TIMEOUT_MS = 25_000;

/** Lesson page: a start gate (needed for mic + audio autoplay), the live room, then the wrap-up. */
export function LessonRoom() {
  const [phase, setPhase] = useState<Phase>("ready");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [micBlocked, setMicBlocked] = useState(false);
  const starting = useRef(false);
  const blockMic = useCallback(() => setMicBlocked(true), []);

  async function start() {
    if (starting.current) return;
    starting.current = true;
    setPhase("starting");
    setError(null);
    try {
      const res = await fetch("/api/session", { method: "POST" });
      if (!res.ok) throw new Error((await res.json()).error ?? "Couldn't start the lesson");
      const info = (await res.json()) as SessionInfo;
      setSession(info);
      setProgress({ objectives: info.lesson.objectives, outcome: null, summary: null, new_vocabulary: [] });
      setPhase("live");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't start the lesson");
      setPhase("error");
    } finally {
      starting.current = false;
    }
  }

  const language = findTargetLanguage(session?.lesson.target_language);

  return (
    <main className="shell">
      <header className="topbar">
        <Brand />
        <div className="pill">
          {language ? <Flag code={language.code} /> : null}
          {session ? session.lesson.title : "Today's lesson"}
        </div>
      </header>
      <section className="stage stage--wide stage--lesson">
        {phase === "live" && session && progress ? (
          <LiveKitRoom
            serverUrl={session.server_url}
            token={session.participant_token}
            connect
            audio={false}
            video={false}
            onDisconnected={() => setPhase((current) => (current === "live" ? "ended" : current))}
            onError={(err) => {
              console.error("LiveKit error:", err);
              setError("The connection dropped. Your progress is saved, so you can rejoin.");
              setPhase((current) => (current === "live" ? "error" : current));
            }}
            style={{ display: "contents" }}
          >
            <RoomAudioRenderer />
            <LiveLesson
              session={session}
              progress={progress}
              micBlocked={micBlocked}
              onMicBlocked={blockMic}
              onProgress={setProgress}
              onEnd={() => setPhase("ended")}
            />
          </LiveKitRoom>
        ) : phase === "ended" ? (
          <WrapUp progress={progress} />
        ) : (
          <StartGate phase={phase} error={error} onStart={start} />
        )}
      </section>
    </main>
  );
}

/** Pre-lesson screen; the click doubles as the user gesture browsers need for audio. */
function StartGate({ phase, error, onStart }: { phase: Phase; error: string | null; onStart: () => void }) {
  const starting = phase === "starting";
  return (
    <div className="gate">
      <Lumi state={starting ? "connecting" : phase === "error" ? "thinking" : "happy"} size="xl" />
      <h1 className="title">
        {starting ? "Calling Lumi…" : phase === "error" ? "That didn't connect." : "Ready when you are."}
      </h1>
      <p className="lead">
        {error ?? "About ten minutes. Speak out loud, mistakes are welcome. You can stop any time."}
      </p>
      {phase === "error" ? null : (
        <ul className="gate__tips">
          <li>
            <Icon name="headphones" size={18} /> Headphones help
          </li>
          <li>
            <Icon name="mic" size={18} /> Allow the microphone
          </li>
          <li>
            <Icon name="clock" size={18} /> About 10 minutes
          </li>
        </ul>
      )}
      <button type="button" className="btn btn--lg" onClick={onStart} disabled={starting}>
        {starting ? <span className="spinner" aria-hidden="true" /> : <Icon name="mic" size={22} />}
        {starting ? "Connecting…" : phase === "error" ? "Try again" : "Start the lesson"}
      </button>
      <a href="/home" className="link">
        Back to home
      </a>
    </div>
  );
}

/** The in-room experience: Lumi, the voice meter, controls, live goals and transcript. */
function LiveLesson({
  session,
  progress,
  micBlocked,
  onMicBlocked,
  onProgress,
  onEnd,
}: {
  session: SessionInfo;
  progress: Progress;
  micBlocked: boolean;
  onMicBlocked: () => void;
  onProgress: (progress: Progress) => void;
  onEnd: () => void;
}) {
  const { state, agent, audioTrack } = useVoiceAssistant();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const elapsed = useElapsedSeconds();
  const [stuck, setStuck] = useState(false);
  const cheer = useGoalCheer(progress.objectives);

  useEffect(() => {
    localParticipant.setMicrophoneEnabled(true).catch((err) => {
      console.warn("Microphone unavailable, continuing listen-only:", err);
      onMicBlocked();
    });
  }, [localParticipant, onMicBlocked]);

  useDataChannel(session.progress_topic, (message) => {
    onProgress(JSON.parse(new TextDecoder().decode(message.payload)) as Progress);
  });

  useEffect(() => {
    if (agent) return;
    const timer = setTimeout(() => setStuck(true), AGENT_JOIN_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [agent]);

  const done = progress.objectives.filter((objective) => objective.done).length;
  const total = progress.objectives.length;
  const status = agent ? STATUS[state] ?? "Lumi is here" : stuck ? "Lumi is taking a while…" : "Lumi is joining…";
  const minutes = Math.floor(elapsed / 60);
  const seconds = String(elapsed % 60).padStart(2, "0");
  const timeShare = Math.min(elapsed / (session.lesson.duration_minutes * 60), 1);

  return (
    <div className="lesson">
      <div className="call" data-state={agent ? state : "connecting"}>
        <div className="call__time" aria-label={`${minutes} minutes ${seconds} seconds elapsed`}>
          <span className="call__time-bar" style={{ "--to": timeShare } as CSSProperties} />
          <span className="timer">
            {minutes}:{seconds} <span>/ {session.lesson.duration_minutes}:00</span>
          </span>
        </div>
        {cheer ? (
          <p key={cheer.key} className="cheer" role="status">
            <Icon name="check" size={18} />
            {cheer.text}
          </p>
        ) : null}
        <Lumi state={agent ? state : "connecting"} size="xl" />
        <BarVisualizer
          className="voice-meter"
          state={state}
          track={audioTrack}
          barCount={7}
          options={{ minHeight: 18, maxHeight: 100 }}
        />
        <p className="call__status" aria-live="polite">
          {status}
        </p>
        <p className="call__sub">
          {stuck && !agent
            ? "The tutor didn't join. Go back and try again in a moment."
            : micBlocked
              ? "I can't hear you: microphone access is blocked. Allow it in the address bar, then rejoin. You can still listen."
              : !isMicrophoneEnabled
                ? "Your mic is muted. Unmute to answer."
                : state === "listening"
                  ? "Your turn. Say it out loud."
                  : "Listen, then answer in your own words."}
        </p>
        <div className="call__controls">
          <button
            type="button"
            className={isMicrophoneEnabled ? "btn btn--quiet btn--icon" : "btn btn--sun btn--icon"}
            aria-pressed={!isMicrophoneEnabled}
            aria-label={isMicrophoneEnabled ? "Mute microphone" : "Unmute microphone"}
            onClick={() => localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
          >
            <Icon name={isMicrophoneEnabled ? "mic" : "micOff"} size={24} />
          </button>
          <button type="button" className="btn btn--danger" onClick={onEnd}>
            <Icon name="end" size={18} />
            End lesson
          </button>
        </div>
      </div>
      <aside className="side">
        <section className="panel" aria-labelledby="goals-title">
          <div className="panel__head">
            <h2 id="goals-title" className="section-title">
              Goals
            </h2>
            <span className="count">
              {done}/{total}
            </span>
          </div>
          <span className="meter__track meter__track--thin" aria-hidden="true">
            <span className="meter__fill" style={{ "--to": total ? done / total : 0 } as CSSProperties} />
          </span>
          <Goals objectives={progress.objectives} />
        </section>
        <section className="panel panel--grow" aria-labelledby="talk-title">
          <h2 id="talk-title" className="section-title">
            Conversation
          </h2>
          <Transcript lang={session.lesson.target_language} />
        </section>
      </aside>
    </div>
  );
}

/** Briefly celebrate the most recently ticked objective. */
function useGoalCheer(objectives: Objective[]): { key: string; text: string } | null {
  const seen = useRef<Set<string> | null>(null);
  const [cheer, setCheer] = useState<{ key: string; text: string } | null>(null);

  useEffect(() => {
    const doneIds = objectives.filter((objective) => objective.done).map((objective) => objective.id);
    if (seen.current === null) {
      seen.current = new Set(doneIds);
      return;
    }
    const fresh = objectives.find((objective) => objective.done && !seen.current?.has(objective.id));
    doneIds.forEach((id) => seen.current?.add(id));
    if (!fresh) return;
    setCheer({ key: fresh.id, text: `Goal reached: ${fresh.text}` });
    const timer = setTimeout(() => setCheer(null), 3200);
    return () => clearTimeout(timer);
  }, [objectives]);

  return cheer;
}

const STATUS: Record<string, string> = {
  initializing: "Lumi is getting ready…",
  listening: "Lumi is listening",
  thinking: "Lumi is thinking…",
  speaking: "Lumi is speaking",
  idle: "Lumi is here",
};

/** Live transcript of both speakers, newest at the bottom. */
function Transcript({ lang }: { lang: string }) {
  const streams = useTranscriptions();
  const end = useRef<HTMLDivElement>(null);
  const lines = useMemo(
    () =>
      streams
        .filter((stream) => stream.text.trim())
        .map((stream) => ({
          id: stream.streamInfo.id,
          text: stream.text,
          tutor: !stream.participantInfo.identity.startsWith("learner-"),
        })),
    [streams],
  );

  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [lines]);

  if (lines.length === 0) {
    return <p className="empty">Words will appear here as you talk.</p>;
  }
  return (
    <div className="transcript" lang={lang} aria-live="polite">
      {lines.map((line) => (
        <p key={line.id} className={line.tutor ? "bubble bubble--tutor" : "bubble bubble--learner"}>
          {line.text}
        </p>
      ))}
      <div ref={end} />
    </div>
  );
}

/** Post-lesson celebration with the summary and the new words. */
function WrapUp({ progress }: { progress: Progress | null }) {
  const objectives = progress?.objectives ?? [];
  const done = objectives.filter((objective) => objective.done).length;
  const allDone = objectives.length > 0 && done === objectives.length;
  return (
    <div className="celebrate">
      <div className="celebrate__hero" data-win={done > 0}>
        <span className="burst" aria-hidden="true">
          {Array.from({ length: 10 }, (_, index) => (
            <span key={index} style={{ "--n": index } as CSSProperties} />
          ))}
        </span>
        <Lumi state="happy" size="xl" />
      </div>
      <h1>
        {allDone
          ? "You did it. Every goal ticked!"
          : done > 0
            ? `Nice effort: ${done} of ${objectives.length} goals done.`
            : "No problem, we'll pick it up next time."}
      </h1>
      <p className="lead">
        {allDone
          ? "Next time we'll build on this and move along your path."
          : "Next time I'll start with what we didn't get to today."}
      </p>
      {progress?.summary ? <p className="note">{progress.summary}</p> : null}
      {progress?.new_vocabulary.length ? (
        <section className="celebrate__block" aria-labelledby="new-words">
          <h2 id="new-words" className="section-title">
            New words
          </h2>
          <ul className="words">
            {progress.new_vocabulary.map((item) => (
              <li key={item.term} className="word">
                {item.term} <span>{item.meaning}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {objectives.length ? (
        <section className="celebrate__block" aria-labelledby="goal-recap">
          <h2 id="goal-recap" className="section-title">
            Today's goals
          </h2>
          <Goals objectives={objectives} />
        </section>
      ) : null}
      <a href="/wizard/preparing" className="btn btn--sun btn--lg">
        Back to my path
        <Icon name="arrow" size={20} className="btn__arrow" />
      </a>
    </div>
  );
}

/** Seconds since mount, ticking once a second. */
function useElapsedSeconds(): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);
  return elapsed;
}

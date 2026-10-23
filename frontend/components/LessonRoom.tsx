"use client";

import {
  LiveKitRoom,
  RoomAudioRenderer,
  useDataChannel,
  useLocalParticipant,
  useTranscriptions,
  useVoiceAssistant,
} from "@livekit/components-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Goals } from "@/components/Goals";
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
        <div className="topbar__meta">
          {session ? `${language?.flag ?? ""} ${session.lesson.title}` : "Today's lesson"}
        </div>
      </header>
      <section className="stage stage--wide">
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
    <div className="call" style={{ maxWidth: "36rem", margin: "0 auto", width: "100%" }}>
      <div className="orb orb--lg" data-state={starting ? "connecting" : "idle"} aria-hidden="true">
        <span className="orb__halo" />
      </div>
      <h1 className="title">
        {starting ? "Calling Lumi…" : phase === "error" ? "That didn't connect." : "Ready when you are."}
      </h1>
      <p className="call__sub">
        {error ?? "About ten minutes. Speak out loud, mistakes are welcome. You can stop any time."}
      </p>
      <button type="button" className="btn" onClick={onStart} disabled={starting}>
        {starting ? "Connecting…" : phase === "error" ? "Try again" : "Start the lesson"}
      </button>
      <a href="/home" className="hint">Back to home</a>
    </div>
  );
}

/** The in-room experience: tutor orb, controls, live goals and transcript. */
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
  const { state, agent } = useVoiceAssistant();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const elapsed = useElapsedSeconds();
  const [stuck, setStuck] = useState(false);

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
  const status = agent ? STATUS[state] ?? "Lumi is here" : stuck ? "Lumi is taking a while…" : "Lumi is joining…";
  const minutes = Math.floor(elapsed / 60);
  const seconds = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="lesson">
      <div className="call">
        <div className="orb orb--lg" data-state={agent ? state : "connecting"} aria-hidden="true">
          <span className="orb__halo" />
        </div>
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
            className="btn btn--quiet btn--icon"
            aria-pressed={!isMicrophoneEnabled}
            aria-label={isMicrophoneEnabled ? "Mute microphone" : "Unmute microphone"}
            onClick={() => localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
          >
            <MicIcon muted={!isMicrophoneEnabled} />
          </button>
          <span className="timer" aria-label={`${minutes} minutes ${seconds} seconds elapsed`}>
            {minutes}:{seconds} / {session.lesson.duration_minutes}:00
          </span>
          <button type="button" className="btn btn--danger" onClick={onEnd}>
            End lesson
          </button>
        </div>
      </div>
      <aside className="side">
        <div className="panel">
          <p className="panel__title">
            Goals · {done}/{progress.objectives.length}
          </p>
          <Goals objectives={progress.objectives} />
        </div>
        <div className="panel" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          <p className="panel__title">Conversation</p>
          <Transcript lang={session.lesson.target_language} />
        </div>
      </aside>
    </div>
  );
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
    <div className="celebrate" style={{ maxWidth: "38rem" }}>
      <div className="orb orb--lg" aria-hidden="true" />
      <p className="eyebrow">{allDone ? "Lesson complete" : "Lesson saved"}</p>
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
        <div className="words">
          {progress.new_vocabulary.map((item) => (
            <span key={item.term} className="word">
              {item.term} <span>· {item.meaning}</span>
            </span>
          ))}
        </div>
      ) : null}
      <Goals objectives={objectives} />
      <a href="/wizard/preparing" className="btn btn--sun">
        Back to my path
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

/** Microphone icon with a slash when muted. */
function MicIcon({ muted }: { muted: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      {muted ? <path d="M4 4l16 16" /> : null}
    </svg>
  );
}

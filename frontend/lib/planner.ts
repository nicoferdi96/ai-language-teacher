const PLANNER_TIMEOUT_MS = 120_000;

export type UnitStatus = "pending" | "in_progress" | "done";

export type PlanUnit = {
  unit_id: string;
  position: number;
  title: string;
  kind: "vocabulary" | "grammar" | "conversation";
  description: string;
  status: UnitStatus;
};

export type LearningPlan = {
  plan_id: string;
  target_language: string;
  native_language: string;
  level: string;
  goal_summary: string;
  units: PlanUnit[];
};

export type Objective = { id: string; text: string; done: boolean; evidence: string | null };
export type VocabularyItem = { term: string; meaning: string };

export type Lesson = {
  lesson_uuid: string;
  unit_id: string | null;
  target_language: string;
  title: string;
  status: "planned" | "in_progress" | "completed" | "abandoned";
  objectives: Objective[];
  vocabulary: VocabularyItem[];
  summary: string | null;
  new_vocabulary: VocabularyItem[];
  completed_at: string | null;
};

export type Progress = { plan: LearningPlan | null; lessons: Lesson[] };

/** Base URL of the planner service, derived from LESSON_PLANNER_URL. */
function plannerBase(): string | null {
  const url = process.env.LESSON_PLANNER_URL;
  return url ? new URL("/", url).toString().replace(/\/$/, "") : null;
}

/**
 * Ask the planner to review progress and prepare the next lesson.
 * Never throws: a missing URL, a non-2xx response or a timeout resolve to `{ ok: false }`.
 */
export async function requestLessonPlan(userId: string): Promise<{ ok: boolean }> {
  const base = plannerBase();
  if (!base) {
    console.error("LESSON_PLANNER_URL is not set; cannot request a lesson plan.");
    return { ok: false };
  }
  try {
    const res = await fetch(`${base}/get_next_lesson/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
      cache: "no-store",
      signal: AbortSignal.timeout(PLANNER_TIMEOUT_MS),
    });
    if (!res.ok) console.error(`Lesson planner responded with HTTP ${res.status}.`);
    return { ok: res.ok };
  } catch (error) {
    console.error("Lesson planner request failed:", error);
    return { ok: false };
  }
}

/** Fetch the learner's plan and recent lessons, or null when the planner is unreachable. */
export async function getProgress(userId: string): Promise<Progress | null> {
  const base = plannerBase();
  if (!base) return null;
  try {
    const res = await fetch(`${base}/progress/${encodeURIComponent(userId)}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    return res.ok ? ((await res.json()) as Progress) : null;
  } catch (error) {
    console.error("Progress request failed:", error);
    return null;
  }
}

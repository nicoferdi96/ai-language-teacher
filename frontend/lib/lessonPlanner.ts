const PLANNER_TIMEOUT_MS = 120_000; // ~30s expected, 2-minute ceiling

/**
 * Ask the lesson-planning microservice to build the next lesson for a user.
 *
 * The service reads the learner's saved preferences from the database and
 * persists the generated lesson itself, so the caller only needs to know
 * whether the request succeeded. Never throws: a missing URL, a non-2xx
 * response, or a timeout all resolve to `{ ok: false }`.
 */
export async function requestLessonPlan(
  userId: string,
): Promise<{ ok: boolean }> {
  const plannerUrl = process.env.LESSON_PLANNER_URL;
  if (!plannerUrl) {
    console.error(
      "LESSON_PLANNER_URL is not set; cannot request a lesson plan.",
    );
    return { ok: false };
  }

  try {
    const res = await fetch(plannerUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
      cache: "no-store",
      signal: AbortSignal.timeout(PLANNER_TIMEOUT_MS),
    });
    if (!res.ok) {
      console.error(`Lesson planner responded with HTTP ${res.status}.`);
    }
    return { ok: res.ok };
  } catch (error) {
    console.error("Lesson planner request failed:", error);
    return { ok: false };
  }
}

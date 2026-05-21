"use server";

import { redirect } from "next/navigation";
import { upsertAnswer } from "@/lib/answers";
import { QUESTION } from "@/lib/questions";
import { requireUserEmail, setUserEmail } from "@/lib/session";
import { userExists } from "@/lib/users";
import {
  normalizeEmail,
  normalizeLearningGoal,
  normalizeLessonDuration,
} from "@/lib/validation";

/**
 * Screen 0: validate the email and store it in a cookie. Returning users (an
 * email already in the answers table) go to the welcome-back screen; new users
 * enter the wizard. Returns an error message string on invalid input.
 */
export async function startSession(
  _prev: string | null,
  formData: FormData,
): Promise<string | null> {
  const email = normalizeEmail(String(formData.get("email") ?? ""));
  if (!email) {
    return "Enter a valid email address.";
  }
  await setUserEmail(email);
  const returning = await userExists(email);
  redirect(returning ? "/wizard/welcome-back" : "/wizard/q1");
}

/**
 * Q1 gate: YES enters Q2; NO returns the marker "declined" so the page
 * can show the gate screen. Nothing is persisted.
 */
export async function answerQ1(
  _prev: string | null,
  formData: FormData,
): Promise<string | null> {
  await requireUserEmail();
  if (String(formData.get("choice") ?? "") === "yes") {
    redirect("/wizard/q2");
  }
  return "declined";
}

/** Q2: persist the open-ended learning goal, then advance to Q3. */
export async function saveLearningGoal(
  _prev: string | null,
  formData: FormData,
): Promise<string | null> {
  const userId = await requireUserEmail();
  const goal = normalizeLearningGoal(String(formData.get("answer") ?? ""));
  if (!goal) {
    return "Tell me a little about how you'd like to learn.";
  }
  await upsertAnswer(userId, QUESTION.HOW_TO_LEARN, goal);
  redirect("/wizard/q3");
}

/** Q3: persist the lesson duration in minutes, then finish. */
export async function saveLessonDuration(
  _prev: string | null,
  formData: FormData,
): Promise<string | null> {
  const userId = await requireUserEmail();
  const minutes = normalizeLessonDuration(String(formData.get("answer") ?? ""));
  if (minutes === null) {
    return "Enter a whole number of minutes greater than zero.";
  }
  await upsertAnswer(userId, QUESTION.LESSON_DURATION, String(minutes));
  redirect("/wizard/done");
}

/** Shown when the lesson-planning microservice cannot be reached. */
const UNREACHABLE_PLANNER =
  "I couldn't reach the lesson planner just now. Give it another try in a moment.";

/**
 * Returning-user action: ask the lesson-planning microservice to build the next
 * lesson for the current user, then show the "preparing" screen. Returns a
 * gentle error message string when the planner cannot be reached.
 */
export async function planNextLesson(
  _prev: string | null,
  _formData: FormData,
): Promise<string | null> {
  const userId = await requireUserEmail();

  const plannerUrl = process.env.LESSON_PLANNER_URL;
  if (!plannerUrl) {
    console.error("LESSON_PLANNER_URL is not set; cannot request a lesson plan.");
    return UNREACHABLE_PLANNER;
  }

  try {
    const res = await fetch(plannerUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      console.error(`Lesson planner responded with HTTP ${res.status}.`);
      return UNREACHABLE_PLANNER;
    }
  } catch (error) {
    console.error("Lesson planner request failed:", error);
    return UNREACHABLE_PLANNER;
  }

  redirect("/wizard/preparing");
}

"use server";

import { redirect } from "next/navigation";
import { upsertAnswer } from "@/lib/answers";
import { QUESTION } from "@/lib/questions";
import { requireUserEmail, setUserEmail } from "@/lib/session";
import {
  normalizeEmail,
  normalizeLearningGoal,
  normalizeLessonDuration,
} from "@/lib/validation";

/**
 * Screen 0: validate the email, store it in a cookie, then enter the wizard.
 * Returns an error message string on invalid input, otherwise redirects.
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
  redirect("/wizard/q1");
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

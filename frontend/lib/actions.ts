"use server";

import { redirect } from "next/navigation";
import { upsertAnswer } from "@/lib/answers";
import { QUESTION } from "@/lib/questions";
import { requireUserEmail, setUserEmail } from "@/lib/session";
import { userExists } from "@/lib/users";
import {
  normalizeEmail,
  normalizeLearningGoal,
  normalizeNativeLanguage,
  normalizeTargetLanguage,
} from "@/lib/validation";

/**
 * Screen 0: validate the email and store it in a cookie. Returning users go
 * straight to the preparing screen, where the planner reviews their progress
 * and readies the next lesson; new users enter the wizard.
 */
export async function startSession(
  _prev: string | null,
  formData: FormData,
): Promise<string | null> {
  const email = normalizeEmail(String(formData.get("email") ?? ""));
  if (!email) {
    return "That doesn't look like an email yet. Try something like you@example.com.";
  }
  await setUserEmail(email);
  const returning = await userExists(email);
  redirect(returning ? "/wizard/preparing" : "/wizard/q1");
}

/** Q1 gate: YES enters the wizard; NO returns "declined" so the page shows the gate. */
export async function answerQ1(
  _prev: string | null,
  formData: FormData,
): Promise<string | null> {
  await requireUserEmail();
  if (String(formData.get("choice") ?? "") === "yes") {
    redirect("/wizard/language");
  }
  return "declined";
}

/** Persist the single target language, then ask for the native language. */
export async function saveTargetLanguage(
  _prev: string | null,
  formData: FormData,
): Promise<string | null> {
  const userId = await requireUserEmail();
  const code = normalizeTargetLanguage(String(formData.get("language") ?? ""));
  if (!code) {
    return "Pick one of the languages to continue.";
  }
  await upsertAnswer(userId, QUESTION.TARGET_LANGUAGE, code);
  redirect("/wizard/native");
}

/** Persist the native language (picked or typed), then ask how they like to learn. */
export async function saveNativeLanguage(
  _prev: string | null,
  formData: FormData,
): Promise<string | null> {
  const userId = await requireUserEmail();
  const typed = String(formData.get("other") ?? "").trim();
  const name = normalizeNativeLanguage(typed || String(formData.get("native") ?? ""));
  if (!name) {
    return "Choose your language or type its name in letters.";
  }
  await upsertAnswer(userId, QUESTION.NATIVE_LANGUAGE, name);
  redirect("/wizard/q2");
}

/** Persist the open-ended learning style, then let the planner build the first lesson. */
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
  redirect("/wizard/preparing");
}

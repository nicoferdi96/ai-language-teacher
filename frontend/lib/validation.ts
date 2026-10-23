import { findTargetLanguage } from "@/lib/languages";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const LANGUAGE_NAME_RE = /^[\p{L}][\p{L} '-]{1,39}$/u;

/** Normalize and validate an email. Returns the cleaned email or null if invalid. */
export function normalizeEmail(raw: string): string | null {
  const email = raw.trim().toLowerCase();
  return EMAIL_RE.test(email) ? email : null;
}

/** Validate the open-ended "how to learn" answer. Returns trimmed text or null if empty. */
export function normalizeLearningGoal(raw: string): string | null {
  const text = raw.trim();
  return text.length > 0 ? text : null;
}

/** Validate a target-language code against the supported list. */
export function normalizeTargetLanguage(raw: string): string | null {
  const code = raw.trim().toLowerCase();
  return findTargetLanguage(code) ? code : null;
}

/**
 * Validate a native-language name (picked or typed). Returns it title-cased,
 * or null for empty or non-alphabetic input.
 */
export function normalizeNativeLanguage(raw: string): string | null {
  const name = raw.trim().replace(/\s+/g, " ");
  if (!LANGUAGE_NAME_RE.test(name)) return null;
  return name.charAt(0).toLocaleUpperCase() + name.slice(1);
}

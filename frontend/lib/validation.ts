const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Normalize and validate an email. Returns the cleaned email or null if invalid. */
export function normalizeEmail(raw: string): string | null {
  const email = raw.trim().toLowerCase();
  return EMAIL_RE.test(email) ? email : null;
}

/** Validate the open-ended Q2 answer. Returns trimmed text or null if empty. */
export function normalizeLearningGoal(raw: string): string | null {
  const text = raw.trim();
  return text.length > 0 ? text : null;
}

/**
 * Validate the Q3 lesson duration in minutes.
 * Returns the positive integer, or null for non-integer or non-positive input.
 */
export function normalizeLessonDuration(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const minutes = Number.parseInt(trimmed, 10);
  return minutes > 0 ? minutes : null;
}

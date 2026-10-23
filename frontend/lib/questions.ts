/**
 * Question ids as persisted in postgres.
 * Q1 ("Ready to begin?") is a gate and is never stored, so it has no id here.
 */
export const QUESTION = {
  TARGET_LANGUAGE: 1,
  NATIVE_LANGUAGE: 2,
  HOW_TO_LEARN: 3,
} as const;

export type QuestionId = (typeof QUESTION)[keyof typeof QUESTION];

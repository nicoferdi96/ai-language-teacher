/**
 * Question ids as persisted in postgres.
 * Q1 ("Ready to begin?") is a gate and is never stored, so it has no id here.
 */
export const QUESTION = {
  HOW_TO_LEARN: 1,
  LESSON_DURATION: 2,
} as const;

export type QuestionId = (typeof QUESTION)[keyof typeof QUESTION];

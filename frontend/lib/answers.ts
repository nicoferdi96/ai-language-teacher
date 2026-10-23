import { getPool } from "@/lib/db";
import type { QuestionId } from "@/lib/questions";

/**
 * Insert or overwrite a user's answer to one question.
 * Idempotent: re-running with the same (userId, questionId) updates the row.
 */
export async function upsertAnswer(
  userId: string,
  questionId: QuestionId,
  answer: string,
): Promise<void> {
  await getPool().query(
    `INSERT INTO answers (user_id, question_id, answer)
     VALUES ($1, $2, $3)
     ON CONFLICT (user_id, question_id)
     DO UPDATE SET answer = EXCLUDED.answer, updated_at = now()`,
    [userId, questionId, answer],
  );
}

/** Return a user's answer to one question, or null if unanswered or on error. */
export async function getAnswer(
  userId: string,
  questionId: QuestionId,
): Promise<string | null> {
  try {
    const { rows } = await getPool().query<{ answer: string }>(
      "SELECT answer FROM answers WHERE user_id = $1 AND question_id = $2",
      [userId, questionId],
    );
    return rows[0]?.answer ?? null;
  } catch (error) {
    console.error("getAnswer failed:", error);
    return null;
  }
}

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

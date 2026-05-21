import { getPool } from "@/lib/db";

/**
 * Return true if the email already has answers on record, i.e. it belongs to a
 * returning user.
 *
 * Fails open: any database error is logged and treated as a new user, so a
 * transient outage never blocks onboarding. A returning user wrongly sent
 * through the wizard simply re-answers a few questions, which `upsertAnswer`
 * overwrites idempotently.
 */
export async function userExists(email: string): Promise<boolean> {
  try {
    const { rows } = await getPool().query<{ exists: boolean }>(
      `SELECT EXISTS (SELECT 1 FROM answers WHERE user_id = $1) AS "exists"`,
      [email],
    );
    return rows[0]?.exists ?? false;
  } catch (error) {
    console.error("userExists check failed, treating as new user:", error);
    return false;
  }
}

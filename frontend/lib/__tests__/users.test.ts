import type { Pool } from "pg";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { getPool } from "../db";
import { QUESTION } from "../questions";
import { userExists } from "../users";

// Integration test: requires a running postgres. Skipped when DATABASE_URL is
// unset so the plain `npm test` unit run does not fail on a missing database.
describe.skipIf(!process.env.DATABASE_URL)("userExists", () => {
  let pool: Pool;

  beforeAll(() => {
    pool = getPool();
  });

  beforeEach(async () => {
    await pool.query("DELETE FROM answers");
  });

  afterAll(async () => {
    await pool.end();
  });

  it("returns false for an email with no answers on record", async () => {
    expect(await userExists("nobody@b.com")).toBe(false);
  });

  it("returns true once the email has at least one answer", async () => {
    await pool.query(
      "INSERT INTO answers (user_id, question_id, answer) VALUES ($1, $2, $3)",
      ["a@b.com", QUESTION.HOW_TO_LEARN, "casual chat"],
    );
    expect(await userExists("a@b.com")).toBe(true);
  });
});

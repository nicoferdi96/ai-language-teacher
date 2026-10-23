import type { Pool } from "pg";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { upsertAnswer } from "../answers";
import { getPool } from "../db";
import { QUESTION } from "../questions";

// Integration test: requires a running postgres. Skipped when DATABASE_URL is
// unset so the plain `npm test` unit run does not fail on a missing database.
describe.skipIf(!process.env.DATABASE_URL)("upsertAnswer", () => {
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

  it("inserts a new answer row", async () => {
    await upsertAnswer("a@b.com", QUESTION.HOW_TO_LEARN, "casual chat");
    const { rows } = await pool.query(
      "SELECT answer FROM answers WHERE user_id = $1 AND question_id = $2",
      ["a@b.com", QUESTION.HOW_TO_LEARN],
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].answer).toBe("casual chat");
  });

  it("overwrites the existing row on conflict instead of duplicating", async () => {
    await upsertAnswer("a@b.com", QUESTION.NATIVE_LANGUAGE, "Italian");
    await upsertAnswer("a@b.com", QUESTION.NATIVE_LANGUAGE, "French");
    const { rows } = await pool.query(
      "SELECT answer FROM answers WHERE user_id = $1 AND question_id = $2",
      ["a@b.com", QUESTION.NATIVE_LANGUAGE],
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].answer).toBe("French");
  });
});

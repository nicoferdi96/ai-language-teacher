import { Pool } from "pg";

/**
 * Single shared pg connection pool, created lazily on first use and
 * reused across requests for the lifetime of the process.
 */
let pool: Pool | undefined;

/** Return the shared pg Pool, creating it on first call. */
export function getPool(): Pool {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) {
      throw new Error("DATABASE_URL is not set");
    }
    pool = new Pool({ connectionString });
  }
  return pool;
}

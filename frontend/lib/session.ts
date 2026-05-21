import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const COOKIE_NAME = "user_email";

/** Store the user's email (the user id) in an httpOnly cookie. */
export async function setUserEmail(email: string): Promise<void> {
  const store = await cookies();
  store.set(COOKIE_NAME, email, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24, // 1 day
  });
}

/** Read the user's email from the cookie, or null if it is not set. */
export async function getUserEmail(): Promise<string | null> {
  const store = await cookies();
  return store.get(COOKIE_NAME)?.value ?? null;
}

/**
 * Wizard route guard: return the user's email, or redirect to the
 * start screen if no email cookie is present.
 */
export async function requireUserEmail(): Promise<string> {
  const email = await getUserEmail();
  if (!email) {
    redirect("/");
  }
  return email;
}

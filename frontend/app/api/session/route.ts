import { NextResponse } from "next/server";
import { getUserEmail } from "@/lib/session";

/**
 * Start a voice lesson for the signed-in learner. The browser never chooses
 * the user id: it comes from the httpOnly cookie, and the voice API mints the
 * LiveKit token and dispatches the tutor.
 */
export async function POST() {
  const userId = await getUserEmail();
  if (!userId) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }
  const voiceApi = process.env.VOICE_API_URL;
  if (!voiceApi) {
    return NextResponse.json({ error: "Voice service is not configured" }, { status: 503 });
  }
  try {
    const res = await fetch(`${voiceApi.replace(/\/$/, "")}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
      cache: "no-store",
      signal: AbortSignal.timeout(120_000),
    });
    if (!res.ok) {
      console.error(`Voice API responded with HTTP ${res.status}`);
      return NextResponse.json({ error: "Couldn't start the lesson" }, { status: 502 });
    }
    return NextResponse.json(await res.json());
  } catch (error) {
    console.error("Voice API request failed:", error);
    return NextResponse.json({ error: "Voice service unreachable" }, { status: 503 });
  }
}

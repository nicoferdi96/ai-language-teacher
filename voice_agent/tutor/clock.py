"""Code-owned lesson timer."""

import asyncio

from livekit.agents import AgentSession

from tutor.lesson import LessonState


class LessonClock:
    """Tells the tutor when to wrap up and when to stop."""

    def __init__(self, session: AgentSession, state: LessonState):
        self.session = session
        self.state = state

    async def run(self) -> None:
        """Nudge at 85% of the lesson and force the close at 120%."""
        duration = self.state.package.duration_minutes * 60
        await asyncio.sleep(duration * 0.85)
        if self.state.outcome is None:
            self.session.generate_reply(
                instructions="Time is almost up. Start the wrap-up now: a 2-sentence recap, "
                "call complete_lesson, then say goodbye and call end_call."
            )
        await asyncio.sleep(duration * 0.35)
        if self.state.outcome is None:
            self.session.generate_reply(
                instructions="The lesson time is over. Call complete_lesson now, say goodbye "
                "in one sentence and call end_call."
            )

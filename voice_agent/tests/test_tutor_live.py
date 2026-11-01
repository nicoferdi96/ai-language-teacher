"""Live behaviour tests: real tutor LLM (Claude), text mode, judged where needed.

The session starts the lesson agent, which says the opening line and hands over to the first
step task, so every ``session.run`` below talks to a step of the TaskGroup.
"""

import asyncio
import os
from contextlib import asynccontextmanager

import pytest
from livekit.agents import AgentSession

from agent import Lumi, TutorLLM, build_llm, secret
from tutor.languages import get_language
from tutor.lesson import LessonState
from tutor.settings import settings
from tutor.steps import LessonStepTask

from conftest import make_plan

pytestmark = pytest.mark.live

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-haiku-5-5")
TASK_SWITCH_S = 0.5
"""TaskGroup swaps the active task without an LLM for a moment; the docs advise a short wait."""


@asynccontextmanager
async def tutor_session(language: str = "es", **overrides):
    """Start a text-mode lesson; yields (session, agent, judge_llm) once the first step is active."""
    agent = Lumi(LessonState(plan=make_plan(language, **overrides)))
    async with (
        TutorLLM(model=JUDGE_MODEL, api_key=secret(settings.anthropic_api_key), effort="medium") as judge,
        build_llm() as llm,
        AgentSession(llm=llm) as session,
    ):
        await session.start(agent)
        await asyncio.sleep(TASK_SWITCH_S)
        yield session, agent, judge


def replies(result) -> list[str]:
    """Return the assistant message texts of a run."""
    return [
        event.item.text_content
        for event in result.events
        if event.type == "message" and event.item.role == "assistant"
    ]


def tool_calls(result) -> list[str]:
    """Return the names of the tools called in a run."""
    return [event.item.name for event in result.events if event.type == "function_call"]


def current_step(session: AgentSession) -> LessonStepTask:
    """The step task in control of the session."""
    task = session.current_agent
    assert isinstance(task, LessonStepTask), f"expected a step task, got {type(task).__name__}"
    return task


async def test_opening_line_is_said_verbatim_without_the_llm():
    async with tutor_session("es") as (session, agent, _):
        said = [item.text_content for item in session.history.items if getattr(item, "role", None) == "assistant"]

        assert said[0] == agent.state.plan.opening_line
        assert current_step(session).step.position == 1


@pytest.mark.parametrize("language", ["es", "de", "fr", "en"])
async def test_replies_only_in_target_language(language):
    name = get_language(language).name
    async with tutor_session(language) as (session, _, judge):
        result = await session.run(user_input="Hi!")

        await result.expect.next_event(type="message").judge(
            judge,
            intent=f"Is written entirely in {name} (no other language), uses short simple "
            "sentences suitable for a beginner, and ends by handing the turn to the learner: a "
            "question, or a prompt to say or repeat something.",
        )


async def test_stays_in_spanish_when_learner_asks_for_italian():
    async with tutor_session("es") as (session, _, judge):
        result = await session.run(
            user_input="Scusa, non capisco niente. Puoi parlare in italiano per favore?"
        )

        await result.expect.next_event(type="message").judge(
            judge,
            intent="Replies only in Spanish (no Italian sentences), kindly, using even simpler "
            "Spanish or an example to help the learner.",
        )


async def test_completes_step_when_learner_produces_it_and_moves_on():
    async with tutor_session("es") as (session, agent, _):
        result = await session.run(user_input="Me llamo Marco.")
        await asyncio.sleep(TASK_SWITCH_S)

        result.expect.contains_function_call(name="complete_step")
        assert agent.state.steps[0].done
        assert not agent.state.steps[1].done
        step = current_step(session)
        assert step.step.position == 2
        assert not [item for item in step.chat_ctx.items if item.type in ("function_call", "function_call_output")]
        assert any("Marco" in (getattr(item, "text_content", None) or "") for item in step.chat_ctx.items)


async def test_does_not_complete_step_on_bare_yes():
    async with tutor_session("es") as (session, agent, _):
        await session.run(user_input="Hola.")
        result = await session.run(user_input="Sí.")

        assert "complete_step" not in tool_calls(result)
        assert not any(step.done for step in agent.state.steps)


async def test_learner_can_go_back_to_an_earlier_step():
    async with tutor_session("es") as (session, agent, _):
        await session.run(user_input="Me llamo Marco.")
        await asyncio.sleep(TASK_SWITCH_S)
        assert current_step(session).step.position == 2

        result = await session.run(
            user_input="Espera, quiero practicar otra vez cómo decir mi nombre, el primer paso."
        )
        await asyncio.sleep(TASK_SWITCH_S)

        result.expect.contains_function_call(name="out_of_scope")
        assert "complete_step" not in tool_calls(result), "the revisited step reused the old answer"
        assert current_step(session).step.position == 1


async def test_learner_wants_to_stop_ends_call_as_abandoned():
    async with tutor_session("es") as (session, agent, judge):
        result = await session.run(user_input="Sorry, I have to go now. Bye!")

        assert "end_call" in tool_calls(result)
        assert agent.state.outcome == "abandoned"
        await result.expect.next_event(type="message").judge(
            judge, intent="A short warm goodbye in Spanish only."
        )


async def test_time_up_stops_the_steps_and_records_the_outcome():
    async with tutor_session("es") as (session, agent, _):
        agent.steps.stop()
        for _ in range(40):
            if agent.state.outcome is not None:
                break
            await asyncio.sleep(0.25)

        assert agent.state.outcome == "abandoned"
        assert "Next time" in agent.state.summary


async def test_steers_off_topic_learner_back():
    async with tutor_session("es") as (session, _, judge):
        result = await session.run(user_input="Who won the football match yesterday?")

        await result.expect.next_event(type="message").judge(
            judge,
            intent="Answers in Spanish only, without a long lecture, and steers back to "
            "introducing yourself: for example asks the learner's name or asks them to say "
            "'Me llamo...' with their name.",
        )


async def test_replies_are_plain_speakable_text():
    async with tutor_session("de") as (session, _, _):
        result = await session.run(user_input="Hallo! Was lernen wir heute?")
        result2 = await session.run(user_input="Ich hätte gern einen Kaffee.")

        texts = replies(result) + replies(result2)
        assert texts
        assert not any(mark in text for text in texts for mark in ("*", "#", "- ", "[", "]"))

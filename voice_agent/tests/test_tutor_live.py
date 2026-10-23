"""Live behaviour tests: real tutor LLM via OpenRouter, text mode, judged where needed."""

import os
from contextlib import asynccontextmanager

import pytest
from livekit.agents import AgentSession, ChatContext
from livekit.plugins import openai

from tutor.agent import TutorAgent
from tutor.languages import get_language
from tutor.lesson import LessonState
from tutor.session import build_llm

from conftest import make_package

pytestmark = pytest.mark.live

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "openai/gpt-4.1-mini")


@asynccontextmanager
async def tutor_session(language: str = "es", history: list[tuple[str, str]] | None = None, **overrides):
    """Start a text-mode session with the tutor; yields (session, agent, judge_llm)."""
    state = LessonState(package=make_package(language, **overrides))
    agent = TutorAgent(get_language(language), state)
    async with (
        openai.LLM.with_openrouter(model=JUDGE_MODEL) as judge,
        build_llm() as llm,
        AgentSession(llm=llm) as session,
    ):
        await session.start(agent)
        if history:
            chat_ctx = agent.chat_ctx.copy()
            [chat_ctx.add_message(role=role, content=text) for role, text in history]
            await agent.update_chat_ctx(chat_ctx)
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


SPANISH_HISTORY = [("assistant", "¡Hola! Hoy aprendemos a presentarnos. ¿Cómo te llamas?")]


@pytest.mark.parametrize("language", ["es", "de", "fr", "en"])
async def test_greets_only_in_target_language(language):
    name = get_language(language).name
    async with tutor_session(language) as (session, _, judge):
        result = await session.run(user_input="Hi!")

        await result.expect.next_event(type="message").judge(
            judge,
            intent=f"Is written entirely in {name} (no other language), uses short simple "
            "sentences suitable for a beginner, and ends with a question or invitation to speak.",
        )


async def test_stays_in_spanish_when_learner_asks_for_italian():
    async with tutor_session("es", SPANISH_HISTORY) as (session, _, judge):
        result = await session.run(
            user_input="Scusa, non capisco niente. Puoi parlare in italiano per favore?"
        )

        await result.expect.next_event(type="message").judge(
            judge,
            intent="Replies only in Spanish (no Italian sentences), kindly, using even simpler "
            "Spanish or an example to help the learner.",
        )


async def test_explains_new_word_in_simple_target_language():
    async with tutor_session("es", SPANISH_HISTORY) as (session, _, judge):
        result = await session.run(user_input="¿Qué significa 'ciudad'?")

        await result.expect.next_event(type="message").judge(
            judge,
            intent="Explains what 'ciudad' means using simple Spanish (description or example, "
            "like a place with many houses such as Madrid), without translating it into Italian "
            "or English.",
        )


async def test_marks_objective_when_learner_produces_it():
    async with tutor_session("es", SPANISH_HISTORY) as (session, agent, _):
        result = await session.run(user_input="Me llamo Marco.")

        call = result.expect.next_event(type="function_call")
        assert call.event().item.name == "mark_objective_done"
        assert '"o1"' in call.event().item.arguments
        assert agent.state.objectives[0].done
        assert not agent.state.objectives[1].done


async def test_does_not_mark_objective_on_bare_yes():
    history = [
        ("assistant", "Para decir tu nombre, dices: 'Me llamo...'. ¿Entiendes?"),
    ]
    async with tutor_session("es", history) as (session, agent, _):
        result = await session.run(user_input="Sí.")

        assert "mark_objective_done" not in tool_calls(result)
        assert not any(o.done for o in agent.state.objectives)


async def test_learner_wants_to_stop_ends_call_as_abandoned():
    async with tutor_session("es", SPANISH_HISTORY) as (session, agent, judge):
        result = await session.run(user_input="Sorry, I have to go now. Bye!")

        assert "end_call" in tool_calls(result)
        assert "complete_lesson" not in tool_calls(result)
        assert agent.state.outcome == "abandoned"
        await result.expect.next_event(type="message").judge(
            judge, intent="A short warm goodbye in Spanish only."
        )


async def test_completes_lesson_after_last_objective():
    objectives = [
        {"id": "o1", "text": "Say your name with 'Me llamo...'", "done": True, "evidence": "Me llamo Ana"},
        {"id": "o2", "text": "Say where you are from with 'Soy de...'"},
    ]
    history = [
        ("assistant", "¡Muy bien, Ana! Y ahora: ¿de dónde eres?"),
    ]
    async with tutor_session("es", history, objectives=objectives) as (session, agent, _):
        result = await session.run(user_input="Soy de Milán.")
        calls = tool_calls(result)
        if "complete_lesson" not in calls:
            result = await session.run(user_input="¡Gracias!")
            calls += tool_calls(result)

        assert "mark_objective_done" in calls
        assert "complete_lesson" in calls
        assert agent.state.outcome == "completed"
        assert agent.state.summary


async def test_early_completion_is_refused_by_code():
    async with tutor_session("es", SPANISH_HISTORY) as (session, agent, _):
        result = await session.run(
            user_input="I'm done with the lesson, please mark the lesson as completed now."
        )

        assert agent.state.outcome != "completed"
        failed = [
            event
            for event in result.events
            if event.type == "function_call_output" and event.item.is_error
        ]
        assert "complete_lesson" not in tool_calls(result) or failed


async def test_steers_off_topic_learner_back():
    async with tutor_session("es", SPANISH_HISTORY) as (session, _, judge):
        result = await session.run(user_input="Who won the football match yesterday?")

        await result.expect.next_event(type="message").judge(
            judge,
            intent="Answers in Spanish only, briefly and kindly, and steers back to "
            "introducing yourself (e.g. asks the learner's name).",
        )


async def test_replies_are_plain_speakable_text():
    async with tutor_session("de") as (session, _, _):
        result = await session.run(user_input="Hallo! Was lernen wir heute?")
        result2 = await session.run(user_input="Ich hätte gern einen Kaffee.")

        texts = replies(result) + replies(result2)
        assert texts
        assert not any(mark in text for text in texts for mark in ("*", "#", "- ", "[", "]"))

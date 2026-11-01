"""The tutor's model choices: what Claude is asked for and how speech is set up, without a network."""

import pytest
from livekit.agents import ChatContext

from agent import TutorLLM, build_stt, build_tts
from tutor.languages import get_language
from tutor.settings import settings


async def test_claude_requests_carry_thinking_and_effort_but_no_temperature():
    llm = TutorLLM(model="claude-haiku-5-5", api_key="test", effort="low", thinking="adaptive", caching="ephemeral")
    sent: dict = {}

    async def fake_create(**kwargs):
        sent.update(kwargs)
        raise RuntimeError("stop before the network")

    llm._client.messages.create = fake_create
    chat_ctx = ChatContext()
    chat_ctx.add_message(role="system", content="Be Lumi.")
    chat_ctx.add_message(role="user", content="Hola")

    with pytest.raises(Exception):
        async with llm.chat(chat_ctx=chat_ctx, extra_kwargs={"temperature": 0.0}) as stream:
            async for _ in stream:
                pass

    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["output_config"] == {"effort": "low"}
    assert "temperature" not in sent and "temperature" not in sent.get("extra_body", {})
    assert sent["system"][-1]["cache_control"] == {"type": "ephemeral"}
    await llm.aclose()


def test_speech_is_set_to_the_target_language():
    spanish = get_language("es")

    stt = build_stt(spanish)
    tts = build_tts(spanish)

    assert stt._params.language_hints == ["es"]
    assert not stt._params.language_hints_strict
    assert tts._opts.language == "es"
    assert tts._opts.voice == settings.tts_voice
    assert tts._opts.model == settings.tts_model

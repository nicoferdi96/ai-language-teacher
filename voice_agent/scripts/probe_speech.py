"""Round-trip probe for the tutor's speech in every target language.

Each language synthesises a sentence with Cartesia TTS (the tutor's voice) and
transcribes it back with Soniox STT, using the same builders as the worker.
Run from ``voice_agent/``: ``uv run python scripts/probe_speech.py``.
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

from livekit import rtc
from livekit.agents import stt as agents_stt
from livekit.agents.utils import http_context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import build_stt, build_tts  # noqa: E402
from tutor.languages import get_language  # noqa: E402

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class ProbeCase:
    """One language to probe and the sentence to say."""

    language: str
    sentence: str


CASES = [
    ProbeCase("en", "Hello, today we will learn how to order a coffee."),
    ProbeCase("es", "Hola, hoy vamos a aprender a pedir un café."),
    ProbeCase("de", "Hallo, heute lernen wir, wie man einen Kaffee bestellt."),
    ProbeCase("fr", "Bonjour, aujourd'hui nous apprenons à commander un café."),
]


class SpeechProbe:
    """Runs the TTS -> STT round trip for a list of probe cases."""

    async def synthesize(self, case: ProbeCase) -> list[rtc.AudioFrame]:
        """Return 16 kHz mono frames for the case sentence."""
        tts = build_tts(get_language(case.language))
        try:
            frames = [chunk.frame async for chunk in tts.synthesize(case.sentence)]
        finally:
            await tts.aclose()
        resampler = rtc.AudioResampler(frames[0].sample_rate, SAMPLE_RATE, num_channels=1)
        return [out for frame in frames for out in resampler.push(frame)] + resampler.flush()

    async def transcribe(self, case: ProbeCase, frames: list[rtc.AudioFrame]) -> str:
        """Stream frames plus trailing silence to Soniox STT and return the final text."""
        stream = build_stt(get_language(case.language)).stream()
        silence = rtc.AudioFrame(bytes(SAMPLE_RATE * 2 * 2), SAMPLE_RATE, 1, SAMPLE_RATE * 2)
        [stream.push_frame(frame) for frame in [*frames, silence]]
        try:
            return await anext(
                event.alternatives[0].text
                async for event in stream
                if event.type == agents_stt.SpeechEventType.FINAL_TRANSCRIPT
            )
        finally:
            await stream.aclose()

    async def run(self, case: ProbeCase) -> str:
        """Probe one case and return a printable result line."""
        try:
            frames = await self.synthesize(case)
            seconds = sum(frame.duration for frame in frames)
            text = await asyncio.wait_for(self.transcribe(case, frames), timeout=40)
            return f"[{case.language}] audio={seconds:.1f}s heard={text!r}"
        except Exception as error:
            return f"[{case.language}] FAILED: {error!r}"


async def main() -> None:
    """Probe every case sequentially and print the results."""
    http_context._new_session_ctx()
    try:
        probe = SpeechProbe()
        results = [await probe.run(case) for case in CASES]
    finally:
        await http_context._close_http_ctx()
    print("\n".join(results))


if __name__ == "__main__":
    asyncio.run(main())

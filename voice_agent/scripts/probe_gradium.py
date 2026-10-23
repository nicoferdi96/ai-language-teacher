"""Round-trip probe for Gradium STT/TTS in every candidate tutor language.

Each language synthesises a sentence with Gradium TTS and transcribes it back
with Gradium STT. Italian has no Gradium voice, so its audio comes from the
macOS ``say`` command instead, which still tells us whether STT understands it.
"""

import asyncio
import os
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import stt as agents_stt
from livekit.plugins import gradium

SAMPLE_RATE = 24000


@dataclass(frozen=True)
class ProbeCase:
    """One language to probe: STT code, Gradium voice (or None) and a sentence."""

    language: str
    voice_id: str | None
    sentence: str


CASES = [
    ProbeCase("en", "4SZHfMpw-p46Ywgs", "Hello, today we will learn how to order a coffee."),
    ProbeCase("es", "iTQW2xFICXk8riV4", "Hola, hoy vamos a aprender a pedir un café."),
    ProbeCase("de", "aBNlTApBeOlVKa23", "Hallo, heute lernen wir, wie man einen Kaffee bestellt."),
    ProbeCase("fr", "YhIHaAfQ0cQPDV9R", "Bonjour, aujourd'hui nous apprenons à commander un café."),
    ProbeCase("it", None, "Ciao, oggi impariamo a ordinare un caffè al bar."),
]


class GradiumProbe:
    """Runs the TTS -> STT round trip for a list of probe cases."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def synthesize(self, case: ProbeCase) -> list[rtc.AudioFrame]:
        """Return 24 kHz mono frames for the case sentence."""
        if case.voice_id is None:
            return self._say_frames(case.sentence)
        tts = gradium.TTS(voice_id=case.voice_id, http_session=self.session)
        frames = [chunk.frame async for chunk in tts.synthesize(case.sentence)]
        resampler = rtc.AudioResampler(frames[0].sample_rate, SAMPLE_RATE, num_channels=1)
        return [
            out
            for frame in frames
            for out in resampler.push(frame)
        ] + resampler.flush()

    @staticmethod
    def _say_frames(sentence: str) -> list[rtc.AudioFrame]:
        """Synthesise Italian with macOS ``say`` and return it as one frame."""
        path = Path(tempfile.mkdtemp()) / "it.wav"
        subprocess.run(
            ["say", "-v", "Alice", "--data-format=LEI16@24000", "-o", str(path), sentence],
            check=True,
        )
        with wave.open(str(path)) as wav:
            pcm = wav.readframes(wav.getnframes())
        return [rtc.AudioFrame(pcm, SAMPLE_RATE, 1, len(pcm) // 2)]

    async def transcribe(self, case: ProbeCase, frames: list[rtc.AudioFrame]) -> str:
        """Stream frames plus trailing silence to Gradium STT and return the text."""
        stt = gradium.STT(language=case.language, http_session=self.session)
        stream = stt.stream()
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
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    assert os.environ.get("GRADIUM_API_KEY"), "GRADIUM_API_KEY missing"
    async with aiohttp.ClientSession() as session:
        probe = GradiumProbe(session)
        results = [await probe.run(case) for case in CASES]
    print("\n".join(results))


if __name__ == "__main__":
    asyncio.run(main())

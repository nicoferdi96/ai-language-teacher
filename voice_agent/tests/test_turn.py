"""Turn-taking settings, interim transcript joining and yield-to-caller, without a room."""

from types import SimpleNamespace

import pytest
from livekit.agents import AgentStateChangedEvent, UserStateChangedEvent, inference, stt
from pydantic import ValidationError

from tutor.transcript import InterimJoiner
from tutor.turn import BALANCED, TurnWindow, turn_handling, yield_to_caller


def test_turn_handling_uses_unmute_balanced_pace():
    options = turn_handling(BALANCED)

    assert isinstance(options["turn_detection"], inference.TurnDetector)
    assert options["endpointing"] == {"mode": "dynamic", "min_delay": 0.3, "max_delay": 1.6}
    assert options["interruption"] == {"enabled": True, "mode": "adaptive", "backchannel_boundary": (1.0, 3600.0)}
    assert options["preemptive_generation"] == {"enabled": True}
    assert BALANCED.vad_silence == 0.3


def test_turn_window_rejects_a_vad_floor_the_detector_refuses():
    with pytest.raises(ValidationError):
        TurnWindow(vad_silence=0.2, min_delay=0.3, max_delay=1.6)


def speech(kind: stt.SpeechEventType, text: str = "") -> stt.SpeechEvent:
    return stt.SpeechEvent(type=kind, alternatives=[stt.SpeechData(language="es", text=text)])


def test_interims_become_the_line_so_far_and_reset_after_final():
    joiner, interim, final = InterimJoiner(), stt.SpeechEventType.INTERIM_TRANSCRIPT, stt.SpeechEventType.FINAL_TRANSCRIPT

    texts = [joiner.push(speech(interim, word)).alternatives[0].text for word in ["Me", " llamo ", "Ana"]]
    final_text = joiner.push(speech(final, "Me llamo Ana")).alternatives[0].text
    after = joiner.push(speech(interim, "Soy")).alternatives[0].text

    assert texts == ["Me", "Me llamo", "Me llamo Ana"]
    assert final_text == "Me llamo Ana"
    assert after == "Soy"


class FakeSpeech:
    def __init__(self, allow_interruptions: bool = True):
        self.id, self.allow_interruptions, self.interrupted = "speech_1", allow_interruptions, False

    def done(self) -> bool:
        return False

    def interrupt(self) -> None:
        self.interrupted = True


class FakeSession:
    """Just enough of AgentSession for yield_to_caller."""

    def __init__(self, speech: FakeSpeech):
        self.current_speech, self.agent_state, self.user_state = speech, "thinking", "listening"
        self.handlers: dict[str, object] = {}

    def on(self, name: str, handler) -> None:
        self.handlers[name] = handler

    def emit(self, name: str, event) -> None:
        self.handlers[name](event)


def learner_speaks() -> UserStateChangedEvent:
    return UserStateChangedEvent(old_state="listening", new_state="speaking")


def test_reply_being_prepared_is_dropped_when_learner_resumes():
    session = FakeSession(FakeSpeech())
    yield_to_caller(session)

    session.emit("user_state_changed", learner_speaks())

    assert session.current_speech.interrupted


def test_turn_committed_over_learner_is_dropped():
    session = FakeSession(FakeSpeech())
    session.user_state = "speaking"
    yield_to_caller(session)

    session.emit("agent_state_changed", AgentStateChangedEvent(old_state="listening", new_state="thinking"))

    assert session.current_speech.interrupted


def test_reply_running_a_tool_is_kept():
    session = FakeSession(FakeSpeech())
    yield_to_caller(session)
    started = SimpleNamespace(update=SimpleNamespace(type="tool_call_started", function_call=SimpleNamespace(call_id="c1")))

    session.emit("tool_execution_updated", started)
    session.emit("user_state_changed", learner_speaks())

    assert not session.current_speech.interrupted


def test_uninterruptible_reply_is_kept():
    session = FakeSession(FakeSpeech(allow_interruptions=False))
    yield_to_caller(session)

    session.emit("user_state_changed", learner_speaks())

    assert not session.current_speech.interrupted

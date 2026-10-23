"""Make Gradium's partial transcripts cumulative.

Gradium sends each interim transcript with only its newest word and joins the words
only in the final one. LiveKit publishes every interim as the whole line, so without
this the learner's transcript bubble would show one word at a time.
"""

from livekit.agents import stt


class InterimJoiner:
    """Turns per-word interim transcripts into the text heard so far in the utterance."""

    def __init__(self) -> None:
        self._words: list[str] = []

    def push(self, event: stt.SpeechEvent) -> stt.SpeechEvent:
        """Return the event with cumulative interim text; a final event resets the line."""
        if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
            self._words = []
        elif event.type == stt.SpeechEventType.INTERIM_TRANSCRIPT and event.alternatives:
            first = event.alternatives[0]
            if word := first.text.strip():
                self._words.append(word)
            first.text = " ".join(self._words)
        return event

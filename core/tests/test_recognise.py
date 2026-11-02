import math
import struct
import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from core.speech.recognise import WhisperRecogniser


class StubModel:
    calls = []

    def __init__(self, name, **kwargs):
        StubModel.calls.append(("load", name, kwargs))

    def transcribe(self, path, **options):
        StubModel.calls.append(("transcribe", path, options))
        words = [SimpleNamespace(word=" Thank", probability=0.91),
                 SimpleNamespace(word=" you.", probability=0.4)]
        segments = iter([SimpleNamespace(text=" Thank you.", words=words)])
        return segments, SimpleNamespace(language="en")


class WhisperWrapperTests(SimpleTestCase):
    def setUp(self):
        StubModel.calls = []
        WhisperRecogniser._models.clear()

    def tearDown(self):
        WhisperRecogniser._models.clear()

    def test_words_and_options(self):
        with mock.patch("faster_whisper.WhisperModel", StubModel):
            recogniser = WhisperRecogniser("base.en", "/tmp/models")
            transcript = recogniser.transcribe("take.webm")
            recogniser.transcribe("again.webm")

        self.assertEqual(transcript.text, "Thank you.")
        self.assertEqual([(w.text, w.probability) for w in transcript.words],
                         [("Thank", 0.91), ("you.", 0.4)])
        loads = [c for c in StubModel.calls if c[0] == "load"]
        self.assertEqual(len(loads), 1, "the model should be loaded once and reused")
        options = StubModel.calls[1][2]
        self.assertEqual(options["language"], "en")
        self.assertTrue(options["word_timestamps"])
        # Whisper must not be told what the user meant to say
        self.assertNotIn("initial_prompt", options)
        self.assertNotIn("hotwords", options)


class AudioDecodingTests(SimpleTestCase):
    """Whisper reads audio through PyAV. PyAV 19 broke faster-whisper 1.2.1,
    which is why requirements.txt pins av below 19. This catches a repeat."""

    def test_decode_a_short_recording(self):
        from faster_whisper.audio import decode_audio

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tone.wav"
            with wave.open(str(path), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(16000)
                samples = (int(8000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(16000))
                out.writeframes(b"".join(struct.pack("<h", s) for s in samples))
            audio = decode_audio(str(path), sampling_rate=16000)
        self.assertAlmostEqual(len(audio), 16000, delta=200)

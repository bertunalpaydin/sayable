"""Speech recognition with Whisper, running on your own computer.

The model downloads once (about 145 MB for base.en) into the models folder.
Audio never leaves the machine.

Whisper is told the language but not the text you meant to say: with the
text as a hint it would "hear" the right words even when they were unclear,
which is exactly what we are trying to measure.
"""

import threading

from .align import HeardWord


class Transcript:
    def __init__(self, text, words):
        self.text = text
        self.words = words


class WhisperRecogniser:
    _models = {}
    _lock = threading.Lock()

    def __init__(self, model_name="base.en", download_root=None):
        self.model_name = model_name
        self.download_root = download_root

    def _model(self):
        with self._lock:
            if self.model_name not in self._models:
                from faster_whisper import WhisperModel  # slow import, only when needed
                self._models[self.model_name] = WhisperModel(
                    self.model_name, device="cpu", compute_type="int8",
                    download_root=self.download_root,
                )
            return self._models[self.model_name]

    def transcribe(self, audio_path):
        segments, _info = self._model().transcribe(
            audio_path,
            language="en",
            beam_size=5,
            temperature=0.0,
            word_timestamps=True,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        words, parts = [], []
        for segment in segments:
            parts.append(segment.text.strip())
            for word in segment.words or []:
                words.append(HeardWord(word.word.strip(), float(word.probability)))
        return Transcript(" ".join(parts).strip(), words)

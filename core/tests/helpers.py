"""Shared test data: a speaker whose "th" is often heard as "s", "f" or "t"."""

from core.speech.align import HeardWord
from core.speech.profile import build_profile
from core.speech.recognise import Transcript

TH_MISHEARD = [("think", "sink"), ("thank", "sank"), ("three", "free"), ("thought", "fought"),
               ("worth", "worse"), ("both", "boat"), ("truth", "truce"), ("thin", "sin"),
               ("thick", "sick"), ("theme", "seem")]
CLEAR_WORDS = ["market", "people", "great", "simple", "project", "data", "coffee", "morning",
               "table", "green", "paper", "window", "garden", "music", "river", "planning",
               "blue", "clock", "money", "sunday", "careful", "complete", "team", "build"]


def th_records():
    records = [(exp, heard, "misheard") for exp, heard in TH_MISHEARD]
    records += [(exp, exp, "ok") for exp, _ in TH_MISHEARD[:3]]  # sometimes fine
    records += [(word, word, "ok") for word in CLEAR_WORDS for _ in range(3)]
    return records


def th_profile():
    return build_profile(th_records())


class FakeRecogniser:
    """Stands in for Whisper. Tests set `words` to what should be "heard"."""

    words = []
    seen_suffixes = []

    def __init__(self, model_name, download_root):
        self.model_name = model_name

    def transcribe(self, path):
        with open(path, "rb") as fh:
            assert fh.read(), "the uploaded audio should reach the recogniser"
        FakeRecogniser.seen_suffixes.append(path.rsplit(".", 1)[-1])
        heard = [HeardWord(w, p) for w, p in FakeRecogniser.words]
        return Transcript(" ".join(w for w, _ in FakeRecogniser.words), heard)

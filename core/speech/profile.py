"""The personal profile: which sounds the recogniser struggles to hear from you.

Every word you read is evidence. When a word is misheard we compare its
sounds with the sounds of what was heard ("think" heard as "sink" points at
TH, not at the other sounds), and charge the error to those sounds only.
When we cannot tell which sound went wrong (a missed or unclear word), every
sound in the word shares the blame.

Rates are smoothed towards your overall average, so one bad word does not
make a sound look hopeless.
"""

from collections import Counter
from dataclasses import dataclass, field

from .align import MISHEARD, MISSED, OK, UNCLEAR, sound_confusions
from .phonemes import pronounce
from .text import FUNCTION_WORDS

# How much each outcome counts as an error. A missed word may simply have
# been skipped, and an unclear one was still heard correctly in the end.
ERROR_WEIGHT = {OK: 0.0, UNCLEAR: 0.5, MISSED: 0.6, MISHEARD: 1.0}

SMOOTHING = 4         # pretend every sound starts with this many average words
MIN_SOUND_WORDS = 3   # below this we do not talk about a sound at all
READY_WORDS = 60      # roughly six sentences of content words
DEFAULT_PRIOR = 0.05


@dataclass
class SoundStats:
    phoneme: str
    words: int = 0
    errors: float = 0.0
    heard_as: Counter = field(default_factory=Counter)
    problem_words: Counter = field(default_factory=Counter)


@dataclass
class WordStats:
    attempts: int = 0
    errors: float = 0.0


@dataclass
class Profile:
    sounds: dict
    words: dict
    total_words: int
    prior: float

    @property
    def ready(self):
        return self.total_words >= READY_WORDS

    def sound_rate(self, phoneme):
        stats = self.sounds.get(phoneme)
        if stats is None:
            return self.prior
        return (stats.errors + SMOOTHING * self.prior) / (stats.words + SMOOTHING)

    def hardest_sounds(self, limit=8):
        """Sounds clearly above your average, worst first."""
        known = [s for s in self.sounds.values() if s.words >= MIN_SOUND_WORDS and s.errors > 0]
        known.sort(key=lambda s: self.sound_rate(s.phoneme), reverse=True)
        return [s for s in known if self.sound_rate(s.phoneme) >= 1.5 * self.prior][:limit]


def learnable(word):
    return word not in FUNCTION_WORDS and word.isalpha() and len(word) > 1


def build_profile(results):
    """Build a profile from (expected word, heard word, status) records."""
    sounds, words = {}, {}
    total_words, total_sound_words, total_sound_errors = 0, 0, 0.0

    for expected, heard, status in results:
        if not learnable(expected):
            continue
        weight = ERROR_WEIGHT.get(status, 0.0)
        total_words += 1

        word_stats = words.setdefault(expected, WordStats())
        word_stats.attempts += 1
        word_stats.errors += weight

        word_sounds = set(pronounce(expected)[0])
        confusions = sound_confusions(expected, heard) if status == MISHEARD and heard else []
        blamed = {exp for exp, _ in confusions} or (word_sounds if weight else set())

        for phoneme in word_sounds:
            stats = sounds.setdefault(phoneme, SoundStats(phoneme))
            stats.words += 1
            total_sound_words += 1
            if phoneme in blamed:
                stats.errors += weight
                total_sound_errors += weight
                stats.problem_words[expected] += 1
        for exp, got in confusions:
            sounds[exp].heard_as[got] += 1

    prior = total_sound_errors / total_sound_words if total_sound_words else DEFAULT_PRIOR
    prior = min(max(prior, 0.02), 0.3)
    return Profile(sounds, words, total_words, prior)

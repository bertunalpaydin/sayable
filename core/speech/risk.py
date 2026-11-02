"""How likely a word is to be misheard when you say it, and why.

A word fails if any of its sounds fails, so the chance of a clean word is the
product of the chances of each sound being heard correctly. If you have said
the word itself before, that history is blended in and soon dominates.

A word is only flagged when there is a reason we can show you: a sound that
is clearly harder for you than your average, or the word's own history.
"""

from dataclasses import dataclass

from .phonemes import SOUNDS, pronounce, sound_name
from .profile import MIN_SOUND_WORDS, learnable
from .text import normalise_word, sentence_spans, tokenise

HIGH, MEDIUM = "high", "medium"
SENSITIVITY = {"low": 1.25, "normal": 1.0, "high": 0.8}  # scales the thresholds
HIGH_AT, MEDIUM_AT = 0.5, 0.3
WORD_HISTORY_WEIGHT = 2


@dataclass
class WordRisk:
    word: str
    score: float
    reason_sound: str | None
    guessed: bool
    said_before: int
    misheard_before: float

    def level(self, sensitivity="normal"):
        scale = SENSITIVITY.get(sensitivity, 1.0)
        has_reason = self.reason_sound is not None or self.misheard_before >= 1
        if not has_reason:
            return None
        if self.score >= HIGH_AT * scale:
            return HIGH
        if self.score >= MEDIUM_AT * scale:
            return MEDIUM
        return None


def word_risk(word, profile):
    word = normalise_word(word)
    sounds, guessed = pronounce(word)
    distinct = set(sounds)

    heard_ok = 1.0
    for phoneme in distinct:
        heard_ok *= 1 - profile.sound_rate(phoneme)
    score = 1 - heard_ok

    history = profile.words.get(word)
    said, misheard = (history.attempts, history.errors) if history else (0, 0.0)
    if said:
        score = (misheard + WORD_HISTORY_WEIGHT * score) / (said + WORD_HISTORY_WEIGHT)

    reason = None
    if profile.ready:
        candidates = [
            p for p in distinct
            if p in profile.sounds and profile.sounds[p].words >= MIN_SOUND_WORDS
            and profile.sound_rate(p) >= 2 * profile.prior
        ]
        if candidates:
            reason = max(candidates, key=profile.sound_rate)
    else:
        score = score if said else 0.0  # without a profile only history counts

    return WordRisk(word, round(score, 3), reason, guessed, said, misheard)


def explain(risk, profile):
    """One or two plain sentences on why a word was flagged."""
    parts = []
    if risk.said_before == 1 and risk.misheard_before >= 1:
        parts.append("The one time you said this word, it was not heard clearly.")
    elif risk.said_before and risk.misheard_before >= 1:
        parts.append(f"You have said this word {risk.said_before} times and it was not heard "
                     f"clearly {_times(risk.misheard_before)}.")
    if risk.reason_sound:
        stats = profile.sounds[risk.reason_sound]
        sentence = (f"It has the {sound_name(risk.reason_sound)} sound, which was not heard clearly "
                    f"in {_count(stats.errors)} of the {stats.words} words with it that you have said")
        heard_as = [got for got, _ in stats.heard_as.most_common(1)]
        if heard_as and heard_as[0]:
            sentence += f'. It is often heard as "{SOUNDS[heard_as[0]][0]}"'
        elif heard_as:
            sentence += ". It is often dropped"
        parts.append(sentence + ".")
    if risk.guessed:
        parts.append("This word is not in the dictionary, so its sounds are guessed from the spelling.")
    return " ".join(parts)


def _times(value):
    n = max(round(value), 1)
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def _count(value):
    return str(max(round(value), 1))


def analyse_script(text, profile, sensitivity="normal", suggest=None):
    """Find the words in a script that are likely to be misheard.

    `suggest(word, risk)` returns easier alternatives; it is optional so the
    analysis can be tested without the word data.
    """
    flags, cache = [], {}
    spans = sentence_spans(text)
    tokens = tokenise(text)
    content = 0
    for token in tokens:
        word = token.norm
        if not learnable(word):
            continue
        content += 1
        if word not in cache:
            cache[word] = word_risk(word, profile)
        risk = cache[word]
        level = risk.level(sensitivity)
        if level is None:
            continue
        sentence = next((text[s:e] for s, e in spans if s <= token.start < e), "")
        flags.append({
            "start": token.start,
            "end": token.end,
            "word": token.text,
            "level": level,
            "score": risk.score,
            "reason": explain(risk, profile),
            "sentence": sentence.strip(),
            "alternatives": suggest(word, risk) if suggest else [],
        })
    return {
        "flags": flags,
        "content_words": content,
        "profile_ready": profile.ready,
    }

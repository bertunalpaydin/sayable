"""Lining up what the user meant to say with what the recogniser heard.

A word can end up in one of four states:

    ok         heard as written, with good confidence
    unclear    heard as written, but the recogniser was unsure of it
    misheard   heard as a different word
    missed     not heard at all

Extra words the recogniser added are ignored, except when they show that one
word was heard as two ("everyone" -> "every one") or the other way round.
"""

from dataclasses import dataclass, field

from .phonemes import pronounce, sound_alike
from .text import american_spelling, words_for_matching

OK, UNCLEAR, MISHEARD, MISSED = "ok", "unclear", "misheard", "missed"

# Whisper gives every word a probability. Below this the word was heard
# correctly but only just, which is still useful evidence for the profile.
UNCLEAR_BELOW = 0.45


@dataclass
class HeardWord:
    text: str
    probability: float = 1.0


@dataclass
class WordOutcome:
    position: int
    expected: str
    heard: str = ""
    status: str = OK
    confidence: float | None = None
    confusions: list = field(default_factory=list)  # [(expected sound, heard sound or "")]


def same_word(expected, heard):
    if expected == heard:
        return True
    if american_spelling(expected) == heard:
        return True
    return sound_alike(expected, heard)


def _edit_alignment(expected, heard):
    """Classic edit-distance alignment. Returns (op, i, j) steps in order."""
    n, m = len(expected), len(heard)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i
    for j in range(1, m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = 0 if same_word(expected[i - 1], heard[j - 1]) else 1
            cost[i][j] = min(cost[i - 1][j - 1] + sub, cost[i - 1][j] + 1, cost[i][j - 1] + 1)

    steps, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            sub = 0 if same_word(expected[i - 1], heard[j - 1]) else 1
            if cost[i][j] == cost[i - 1][j - 1] + sub:
                steps.append(("match" if sub == 0 else "sub", i - 1, j - 1))
                i, j = i - 1, j - 1
                continue
        if i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            steps.append(("del", i - 1, None))
            i -= 1
        else:
            steps.append(("ins", None, j - 1))
            j -= 1
    steps.reverse()
    return steps


def _join_split_words(steps, expected, heard):
    """Treat "every one" for "everyone" (and the reverse) as a match."""
    fixed, k = [], 0
    while k < len(steps):
        pair = steps[k:k + 2]
        ops = {step[0] for step in pair}
        if len(pair) == 2 and ops == {"sub", "ins"}:
            sub = pair[0] if pair[0][0] == "sub" else pair[1]
            first, second = sorted(step[2] for step in pair)
            if same_word(expected[sub[1]], heard[first] + heard[second]):
                fixed.append(("match", sub[1], sub[2]))
                k += 2
                continue
        if len(pair) == 2 and ops == {"sub", "del"}:
            sub = pair[0] if pair[0][0] == "sub" else pair[1]
            first, second = sorted(step[1] for step in pair)
            if same_word(expected[first] + expected[second], heard[sub[2]]):
                fixed.append(("match", first, sub[2]))
                fixed.append(("match", second, sub[2]))
                k += 2
                continue
        fixed.append(steps[k])
        k += 1
    return fixed


def sound_confusions(expected, heard):
    """Which sounds of the expected word were replaced or dropped.

    Returns a list of (expected sound, heard sound) pairs, with "" for a sound
    that was dropped. Empty when either word is not in the dictionary.
    """
    exp, exp_guessed = pronounce(expected)
    got, got_guessed = pronounce(heard)
    if exp_guessed or got_guessed:
        return []
    n, m = len(exp), len(got)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i
    for j in range(1, m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = 0 if exp[i - 1] == got[j - 1] else 1
            cost[i][j] = min(cost[i - 1][j - 1] + sub, cost[i - 1][j] + 1, cost[i][j - 1] + 1)
    pairs, i, j = [], n, m
    while i > 0 and j >= 0:
        if j > 0 and cost[i][j] == cost[i - 1][j - 1] + (exp[i - 1] != got[j - 1]):
            if exp[i - 1] != got[j - 1]:
                pairs.append((exp[i - 1], got[j - 1]))
            i, j = i - 1, j - 1
        elif cost[i][j] == cost[i - 1][j] + 1:
            pairs.append((exp[i - 1], ""))
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def compare(expected_words, heard_words):
    """Compare the expected word list with HeardWord objects from the recogniser.

    `expected_words` comes from text.words_for_matching(). The recogniser's
    words are normalised the same way here ("time." -> "time", "12" -> "twelve").
    """
    heard_words = [
        HeardWord(part, w.probability)
        for w in heard_words for part in words_for_matching(w.text)
    ]
    heard_text = [w.text for w in heard_words]
    steps = _join_split_words(_edit_alignment(expected_words, heard_text), expected_words, heard_text)

    outcomes = {}
    for op, i, j in steps:
        if op == "ins":
            continue
        word = expected_words[i]
        if op == "del":
            outcomes[i] = WordOutcome(i, word, status=MISSED)
        elif op == "match":
            prob = heard_words[j].probability
            status = UNCLEAR if prob < UNCLEAR_BELOW else OK
            outcomes[i] = WordOutcome(i, word, heard_text[j], status, prob)
        else:
            outcomes[i] = WordOutcome(
                i, word, heard_text[j], MISHEARD, heard_words[j].probability,
                sound_confusions(word, heard_text[j]),
            )
    return [outcomes[i] for i in range(len(expected_words))]

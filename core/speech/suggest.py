"""Easier words with the same meaning, chosen for your profile.

Synonyms come from WordNet (shipped in data/synonyms.json.gz). They do not
know the sentence, so the user is asked to check the meaning; Claude, when
switched on, gives options that fit the sentence. Either way every option is
scored against the profile and only those that are easier for this speaker
are kept.
"""

import gzip
import json
from functools import lru_cache
from pathlib import Path

from .phonemes import known
from .risk import MEDIUM_AT, word_risk
from .text import FUNCTION_WORDS, tokenise

DATA_FILE = Path(__file__).resolve().parent / "data" / "synonyms.json.gz"
MAX_OPTIONS = 4
MIN_GAIN = 0.1  # an option must be at least this much less risky


@lru_cache(maxsize=1)
def word_data():
    with gzip.open(DATA_FILE, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def base_forms(word):
    """Possible dictionary forms of a word and the ending that was removed."""
    forms = [(word, "")]
    if word.endswith("ies"):
        forms.append((word[:-3] + "y", "s"))
    if word.endswith("es"):
        forms.append((word[:-2], "s"))
    if word.endswith("s") and not word.endswith("ss"):
        forms.append((word[:-1], "s"))
    if word.endswith("ied"):
        forms.append((word[:-3] + "y", "ed"))
    if word.endswith("ed"):
        stem = word[:-2]
        forms += [(stem, "ed"), (stem + "e", "ed")]
        if len(stem) > 2 and stem[-1] == stem[-2]:
            forms.append((stem[:-1], "ed"))
    if word.endswith("ing"):
        stem = word[:-3]
        forms += [(stem, "ing"), (stem + "e", "ing")]
        if len(stem) > 2 and stem[-1] == stem[-2]:
            forms.append((stem[:-1], "ing"))
    if word.endswith("ily"):
        forms.append((word[:-3] + "y", "ly"))
    if word.endswith("ly"):
        forms += [(word[:-2], "ly"), (word[:-2] + "le", "ly")]
    synonyms = word_data()["synonyms"]
    return [(base, ending) for base, ending in forms if base in synonyms]


def with_ending(base, ending):
    """Put an ending back on a word. Returns None if no real word results."""
    if not ending:
        return base
    options = []
    if ending == "s":
        if base.endswith(("s", "x", "z", "ch", "sh")):
            options.append(base + "es")
        elif base.endswith("y") and base[-2:-1] not in "aeiou":
            options.append(base[:-1] + "ies")
        options.append(base + "s")
    elif ending == "ed":
        if base.endswith("e"):
            options.append(base + "d")
        elif base.endswith("y") and base[-2:-1] not in "aeiou":
            options.append(base[:-1] + "ied")
        options += [base + base[-1] + "ed", base + "ed"]
    elif ending == "ing":
        if base.endswith("e") and not base.endswith("ee"):
            options.append(base[:-1] + "ing")
        options += [base + base[-1] + "ing", base + "ing"]
    elif ending == "ly":
        if base.endswith("y"):
            options.append(base[:-1] + "ily")
        if base.endswith("le"):
            options.append(base[:-1] + "y")
        options.append(base + "ly")
    # the dictionary is the spell checker: "thinked" is not in it
    return next((form for form in options if known(form)), None)


POS_FOR_ENDING = {"": ("n", "v", "a", "r"), "s": ("n", "v"), "ed": ("v",),
                  "ing": ("v",), "ly": ("a",)}


def synonym_candidates(word):
    synonyms, found = word_data()["synonyms"], []
    forms = base_forms(word)
    same_word = {word} | {base for base, _ in forms}  # "think" is no option for "thinking"
    for base, ending in forms:
        for pos in POS_FOR_ENDING[ending]:
            for option in synonyms[base].get(pos, []):
                form = with_ending(option, ending)
                if form and form not in same_word and form not in found:
                    found.append(form)
    return found


def phrase_risk(phrase, profile):
    """Risk of a short phrase: its riskiest content word."""
    words = [t.norm for t in tokenise(phrase)]
    content = [w for w in words if w not in FUNCTION_WORDS] or words
    return max((word_risk(w, profile).score for w in content), default=0.0)


def rank_options(options, original_risk, profile, require_low=True):
    """Keep options that are clearly easier for this speaker, easiest first.

    Synonyms must also be low risk on their own. Claude's options already fit
    the sentence, so for those being clearly easier is enough.
    """
    frequency = word_data()["frequency"]
    scored = []
    for option in options:
        score = phrase_risk(option, profile)
        if score <= original_risk.score - MIN_GAIN and (score < MEDIUM_AT or not require_low):
            commonness = frequency.get(option.split()[0], 3.0)
            scored.append((round(score, 2), -commonness, option))
    scored.sort()
    return [{"text": option, "score": score} for score, _, option in scored[:MAX_OPTIONS]]


def offline_suggestions(word, risk, profile):
    return rank_options(synonym_candidates(word), risk, profile)

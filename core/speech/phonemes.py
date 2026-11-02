"""Pronunciations from the CMU Pronouncing Dictionary.

The dictionary ships in data/cmudict.dict.gz (BSD licence, see
data/CMUDICT_LICENSE). Sounds are ARPAbet symbols without stress marks
("IH1" becomes "IH"). Words missing from the dictionary (names, jargon) get
a rough guess from their spelling, good enough to estimate risk but marked
as a guess.
"""

import gzip
import re
from functools import lru_cache
from pathlib import Path

from .text import american_spelling

DICT_FILE = Path(__file__).resolve().parent / "data" / "cmudict.dict.gz"
VARIANT_RE = re.compile(r"\(\d+\)$")

# A readable name and an example word for every sound, shown to the user.
SOUNDS = {
    "AA": ("ah", "father"), "AE": ("short a", "cat"), "AH": ("uh", "cup"),
    "AO": ("aw", "law"), "AW": ("ow", "now"), "AY": ("eye", "my"),
    "B": ("b", "bat"), "CH": ("ch", "chair"), "D": ("d", "dog"),
    "DH": ("voiced th", "this"), "EH": ("short e", "bed"), "ER": ("er", "bird"),
    "EY": ("ay", "day"), "F": ("f", "fan"), "G": ("g", "go"),
    "HH": ("h", "hat"), "IH": ("short i", "sit"), "IY": ("long ee", "seat"),
    "JH": ("j", "judge"), "K": ("k", "cat"), "L": ("l", "light"),
    "M": ("m", "man"), "N": ("n", "no"), "NG": ("ng", "sing"),
    "OW": ("oh", "go"), "OY": ("oy", "boy"), "P": ("p", "pen"),
    "R": ("r", "red"), "S": ("s", "sun"), "SH": ("sh", "ship"),
    "T": ("t", "top"), "TH": ("th", "think"), "UH": ("short oo", "book"),
    "UW": ("long oo", "food"), "V": ("v", "very"), "W": ("w", "wet"),
    "Y": ("y", "yes"), "Z": ("z", "zoo"), "ZH": ("zh", "measure"),
}

# Spelling patterns used only for words the dictionary does not know.
GUESS_RULES = [
    ("tch", ["CH"]), ("sch", ["S", "K"]), ("th", ["TH"]), ("sh", ["SH"]),
    ("ch", ["CH"]), ("ph", ["F"]), ("ng", ["NG"]), ("wh", ["W"]),
    ("ck", ["K"]), ("qu", ["K", "W"]), ("ee", ["IY"]), ("ea", ["IY"]),
    ("oo", ["UW"]), ("ou", ["AW"]), ("ow", ["OW"]), ("ai", ["EY"]),
    ("ay", ["EY"]), ("oi", ["OY"]), ("oy", ["OY"]), ("er", ["ER"]),
    ("ir", ["ER"]), ("ur", ["ER"]), ("a", ["AE"]), ("b", ["B"]), ("c", ["K"]),
    ("d", ["D"]), ("e", ["EH"]), ("f", ["F"]), ("g", ["G"]), ("h", ["HH"]),
    ("i", ["IH"]), ("j", ["JH"]), ("k", ["K"]), ("l", ["L"]), ("m", ["M"]),
    ("n", ["N"]), ("o", ["AA"]), ("p", ["P"]), ("r", ["R"]), ("s", ["S"]),
    ("t", ["T"]), ("u", ["AH"]), ("v", ["V"]), ("w", ["W"]), ("x", ["K", "S"]),
    ("y", ["Y"]), ("z", ["Z"]),
]

STRESS_RE = re.compile(r"\d")


def sound_name(phoneme):
    """'th (as in "think")', for explanations and for Claude."""
    name, example = SOUNDS.get(phoneme, (phoneme.lower(), ""))
    return f'{name} (as in "{example}")' if example else name


@lru_cache(maxsize=1)
def _dictionary():
    """word -> list of pronunciations, read once from the shipped CMU dictionary."""
    entries = {}
    with gzip.open(DICT_FILE, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            word, *sounds = line.split()
            word = VARIANT_RE.sub("", word)  # "read(2)" is a second way to say "read"
            entries.setdefault(word, []).append(sounds)
    return entries


def known(word):
    return word in _dictionary()


@lru_cache(maxsize=50000)
def pronunciations(word):
    """All dictionary pronunciations of a word, as tuples of sounds."""
    entries = _dictionary().get(word) or _dictionary().get(american_spelling(word)) or []
    return tuple(tuple(STRESS_RE.sub("", p) for p in entry) for entry in entries)


def guess_pronunciation(word):
    sounds, i = [], 0
    word = word.lower()
    while i < len(word):
        for pattern, result in GUESS_RULES:
            if word.startswith(pattern, i):
                sounds.extend(result)
                i += len(pattern)
                break
        else:
            i += 1  # apostrophes and anything unexpected
    # a final silent e ("make") is the most common spelling trap
    if word.endswith("e") and len(word) > 3 and sounds and sounds[-1] == "EH":
        sounds.pop()
    return tuple(sounds)


def pronounce(word):
    """The main pronunciation of a word and whether it was only guessed."""
    found = pronunciations(word)
    if found:
        return found[0], False
    if "'" in word:  # "company's" -> "company" + s
        base = pronunciations(word.split("'")[0])
        if base:
            return base[0] + ("Z",), False
    return guess_pronunciation(word), True


def sound_alike(a, b):
    """True when two different spellings share a pronunciation ("their"/"there")."""
    if a == b:
        return True
    pa, pb = set(pronunciations(a)), set(pronunciations(b))
    return bool(pa and pb and pa & pb)

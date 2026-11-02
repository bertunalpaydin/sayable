"""Turning text into comparable words.

Both the text the user meant to say and the text the recogniser heard go
through the same normalisation, so that differences in punctuation, case,
digits or British/American spelling are not counted as pronunciation errors.
"""

import re
from dataclasses import dataclass

WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*|\d+(?:[.,]\d+)*")

# Short words that recognisers drop, add or swap freely. They tell us very
# little about pronunciation, so they are not used to learn the profile and
# are never flagged in a script.
FUNCTION_WORDS = frozenset("""
a an the and or but if so as at by for from in into of off on onto out over
to up with about than then that this these those there their they them
i me my we us our you your he him his she her it its is are was were be been
being am do does did done have has had not no yes just very too also
will would shall should can could may might must
what which who whom whose when where why how
oh um uh er ah
""".split())

ONES = ("zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

# British spellings that the recogniser (which writes American English) will
# not produce. Checked only after an exact and a same-sound match have failed.
SPELLING_RULES = [
    (re.compile(r"our(s?)$"), r"or\1"),          # colour -> color
    (re.compile(r"is(e|es|ed|ing|ation)$"), r"iz\1"),  # organise -> organize
    (re.compile(r"ys(e|es|ed|ing)$"), r"yz\1"),  # analyse -> analyze
    (re.compile(r"tre(s?)$"), r"ter\1"),         # centre -> center
    (re.compile(r"ogue(s?)$"), r"og\1"),         # catalogue -> catalog
    (re.compile(r"ence$"), "ense"),              # defence -> defense
    (re.compile(r"lled$"), "led"),               # travelled -> traveled
    (re.compile(r"lling$"), "ling"),             # travelling -> traveling
]


@dataclass(frozen=True)
class Token:
    """A word in the original text, with where it starts and ends."""
    text: str
    start: int
    end: int

    @property
    def norm(self):
        return normalise_word(self.text)


def number_to_words(n):
    """Spell out a whole number from 0 to 9999."""
    if n < 20:
        return ONES[n]
    if n < 100:
        tens, rest = divmod(n, 10)
        return TENS[tens] + ("" if rest == 0 else " " + ONES[rest])
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        words = ONES[hundreds] + " hundred"
        return words if rest == 0 else words + " and " + number_to_words(rest)
    if n < 10000:
        thousands, rest = divmod(n, 1000)
        words = ONES[thousands] + " thousand"
        if rest == 0:
            return words
        joiner = " and " if rest < 100 else " "
        return words + joiner + number_to_words(rest)
    return str(n)


def normalise_word(word):
    """Lower case, straight apostrophes, no surrounding punctuation."""
    word = word.replace("’", "'").lower().strip("'")
    return word


def tokenise(text):
    """Split text into word tokens, keeping their positions in the text.

    Hyphens split words ("well-known" becomes "well" and "known") because
    recognisers are inconsistent about writing them.
    """
    return [Token(m.group(0), m.start(), m.end()) for m in WORD_RE.finditer(text)]


def token_words(text):
    """Each token with the normalised words it stands for ("12" -> ["twelve"])."""
    pairs = []
    for token in tokenise(text):
        word = token.norm
        if word.isdigit():
            number = int(word)
            words = number_to_words(number).split() if number < 10000 else [word]
        elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", word) and int(word.replace(",", "")) < 10000:
            words = number_to_words(int(word.replace(",", ""))).split()
        elif re.fullmatch(r"\d+\.\d+", word):
            whole, fraction = word.split(".")
            words = number_to_words(int(whole)).split() + ["point"] + [ONES[int(d)] for d in fraction]
        else:
            words = [word] if word else []
        pairs.append((token, words))
    return pairs


def words_for_matching(text):
    """The normalised word list used to compare what was said and heard."""
    return [word for _, words in token_words(text) for word in words]


SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+|\n\s*\n")


def sentence_spans(text):
    """(start, end) of each sentence in the text."""
    spans, start = [], 0
    for match in SENTENCE_END_RE.finditer(text):
        if text[start:match.start()].strip():
            spans.append((start, match.start()))
        start = match.end()
    if text[start:].strip():
        spans.append((start, len(text.rstrip())))
    return spans


def rehearsal_chunks(text, max_words=35):
    """Split a script into pieces short enough to say in one breath or two."""
    chunks, current, count = [], [], 0
    for start, end in sentence_spans(text):
        sentence = " ".join(text[start:end].split())
        words = len(tokenise(sentence))
        if current and count + words > max_words:
            chunks.append(" ".join(current))
            current, count = [], 0
        current.append(sentence)
        count += words
    if current:
        chunks.append(" ".join(current))
    return chunks


def american_spelling(word):
    for pattern, replacement in SPELLING_RULES:
        new = pattern.sub(replacement, word)
        if new != word:
            return new
    return word

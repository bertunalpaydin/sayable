"""Build core/speech/data/synonyms.json.gz from WordNet and word frequencies.

The app ships with the result, so it needs neither NLTK nor wordfreq at run
time. Run this only to rebuild the file:

    pip install nltk wordfreq
    python -m nltk.downloader wordnet
    python scripts/build_word_data.py

WordNet is from Princeton University (https://wordnet.princeton.edu) and is
used under its licence; word frequencies come from the wordfreq project.
"""

import gzip
import json
from pathlib import Path

from nltk.corpus import wordnet as wn
from wordfreq import zipf_frequency

OUT = Path(__file__).resolve().parent.parent / "core" / "speech" / "data" / "synonyms.json.gz"
MIN_LEMMA_ZIPF = 2.5      # only words people actually use in talks
MIN_OPTION_ZIPF = 3.0     # alternatives should be common words
MAX_OPTIONS = 12
POS = {"n": "n", "v": "v", "a": "a", "s": "a", "r": "r"}


def main():
    synonyms, freq = {}, {}
    for lemma in wn.all_lemma_names():
        if not lemma.isalpha() or not lemma.islower():
            continue
        lemma_zipf = zipf_frequency(lemma, "en")
        if lemma_zipf < MIN_LEMMA_ZIPF:
            continue
        by_pos = {}
        for synset in wn.synsets(lemma):
            pos = POS[synset.pos()]
            names = list(synset.lemma_names())
            if pos == "a":  # adjectives have few true synonyms; close ones help
                for similar in synset.similar_tos():
                    names.extend(similar.lemma_names())
            for name in names:
                if name == lemma or not name.isalpha() or not name.islower():
                    continue
                zipf = zipf_frequency(name, "en")
                if zipf < MIN_OPTION_ZIPF:
                    continue
                freq[name] = round(zipf, 1)
                options = by_pos.setdefault(pos, [])
                if name not in options:
                    options.append(name)
        if by_pos:
            synonyms[lemma] = {
                pos: sorted(options, key=lambda w: -freq[w])[:MAX_OPTIONS]
                for pos, options in by_pos.items()
            }
            freq[lemma] = round(lemma_zipf, 1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {"synonyms": synonyms, "frequency": freq}
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"), sort_keys=True)
    print(f"{len(synonyms)} words, {OUT.stat().st_size // 1024} KB -> {OUT}")


if __name__ == "__main__":
    main()

"""Glue between the database and the speech engine."""

import os
import tempfile
from functools import lru_cache

from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string

from .models import Attempt, UserSettings, WordResult
from .speech import claude
from .speech.align import compare
from .speech.phonemes import sound_name
from .speech.profile import build_profile
from .speech.suggest import rank_options
from .speech.text import token_words

AUDIO_SUFFIXES = {"audio/webm": ".webm", "audio/mp4": ".m4a", "audio/ogg": ".ogg",
                  "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3"}
SEVERITY = {"ok": 0, "unclear": 1, "missed": 2, "misheard": 3}
BAD_TAKE_BELOW = 0.4  # share of words heard


@lru_cache(maxsize=1)
def recogniser():
    config = settings.SAYABLE
    cls = import_string(config["RECOGNISER"])
    return cls(config["WHISPER_MODEL"], config["MODEL_DIR"])


def user_settings(user):
    return UserSettings.objects.get_or_create(user=user)[0]


def load_profile(user):
    rows = WordResult.objects.filter(attempt__user=user).values_list("expected", "heard", "status")
    return build_profile(rows)


def transcribe_upload(upload):
    """Write the uploaded recording to a temporary file, transcribe it, delete it."""
    content_type = (upload.content_type or "").split(";")[0].strip()
    suffix = AUDIO_SUFFIXES.get(content_type, ".webm")
    handle, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(handle, "wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        return recogniser().transcribe(path)
    finally:
        os.remove(path)


def looks_like_a_bad_take(outcomes):
    """Most words wrong usually means the wrong text was read, or noise.

    Counting such a take would teach the profile that every sound is hard,
    so it is shown to the user but not stored.
    """
    if len(outcomes) < 3:
        return False
    heard = sum(1 for o in outcomes if o.status in ("ok", "unclear"))
    return heard / len(outcomes) < BAD_TAKE_BELOW


@transaction.atomic
def save_attempt(user, kind, expected_text, transcript, script=None, sentence_key=""):
    """Compare a transcript with the expected text and store the result.

    Returns the attempt (None when the take was not counted) and, for the
    page, each token of the expected text with its worst word status.
    """
    pairs = token_words(expected_text)
    expected_words = [w for _, words in pairs for w in words]
    outcomes = compare(expected_words, transcript.words)

    attempt = None
    if not looks_like_a_bad_take(outcomes):
        attempt = Attempt.objects.create(
            user=user, kind=kind, expected_text=expected_text, heard_text=transcript.text,
            script=script, sentence_key=sentence_key,
        )
        WordResult.objects.bulk_create([
            WordResult(attempt=attempt, position=o.position, expected=o.expected[:64],
                       heard=o.heard[:64], status=o.status, confidence=o.confidence)
            for o in outcomes
        ])

    tokens, index = [], 0
    for token, words in pairs:
        mine = outcomes[index:index + len(words)]
        index += len(words)
        worst = max(mine, key=lambda o: SEVERITY[o.status]) if mine else None
        tokens.append({
            "start": token.start,
            "end": token.end,
            "text": token.text,
            "status": worst.status if worst else "ok",
            "heard": worst.heard if worst and worst.status == "misheard" else "",
        })
    return attempt, tokens


def claude_key(user_prefs):
    return user_prefs.claude_api_key or settings.SAYABLE["ANTHROPIC_API_KEY"]


def claude_suggestions(user_prefs, word, sentence, risk, profile):
    hard = [sound_name(s.phoneme) for s in profile.hardest_sounds(4)]
    options = claude.suggest(claude_key(user_prefs), settings.SAYABLE["CLAUDE_MODEL"],
                             word, sentence, hard)
    return rank_options(options, risk, profile, require_low=False)

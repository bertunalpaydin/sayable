"""Optional suggestions from Claude that fit the sentence.

Uses the Anthropic Messages API directly with the standard library, so the
app has no extra dependency for a feature many users will not switch on.
"""

import json
import re
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
TIMEOUT = 25

PROMPT = """A non-native English speaker is preparing to say this sentence out loud:

"{sentence}"

Speech recognition often mishears them on the word "{word}". The sounds they
find hardest are: {sounds}.

Suggest up to 5 replacements for "{word}". Each must keep the meaning and the
grammar of the sentence, and should avoid those sounds where possible. Prefer
common, plain words. A replacement can be one word or a phrase of up to three
words. Reply with JSON only, in this form: {{"options": ["...", "..."]}}"""


class ClaudeError(Exception):
    """A problem worth showing to the user as it is."""


def suggest(api_key, model, word, sentence, hard_sounds):
    body = json.dumps({
        "model": model,
        "max_tokens": 300,
        "messages": [{"role": "user", "content": PROMPT.format(
            sentence=sentence or word, word=word,
            sounds=", ".join(hard_sounds) or "none recorded yet")}],
    }).encode()
    request = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            reply = json.load(response)
    except urllib.error.HTTPError as err:
        raise ClaudeError(_http_message(err.code)) from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise ClaudeError("Could not reach Claude. Check your internet connection.") from err

    text = "".join(part.get("text", "") for part in reply.get("content", []))
    return parse_options(text, word)


def parse_options(text, word):
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ClaudeError("Claude's answer could not be read. Try again.")
    try:
        options = json.loads(match.group(0)).get("options", [])
    except (json.JSONDecodeError, AttributeError) as err:
        raise ClaudeError("Claude's answer could not be read. Try again.") from err
    cleaned = []
    for option in options:
        if not isinstance(option, str):
            continue
        option = option.strip().strip('"').strip()
        if option and option.lower() != word.lower() and len(option.split()) <= 3:
            cleaned.append(option)
    return cleaned


def _http_message(code):
    if code == 401:
        return "Claude rejected the API key. Check it in Settings."
    if code == 402 or code == 403:
        return "Your Anthropic account cannot use the API right now. Check your credit."
    if code == 429:
        return "Too many requests to Claude. Wait a minute and try again."
    if code >= 500:
        return "Claude is busy or unavailable. Try again shortly."
    return f"Claude returned an error ({code})."

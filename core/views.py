import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import services
from .forms import ScriptForm, SettingsForm
from .models import Attempt, Script
from .speech import claude
from .speech.phonemes import SOUNDS
from .speech.risk import analyse_script, word_risk
from .speech.sentences import PROFILE_TARGET, SENTENCES, next_sentence
from .speech.suggest import offline_suggestions
from .speech.text import rehearsal_chunks

log = logging.getLogger(__name__)

MAX_SCRIPT_CHARS = 20000


def json_error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def read_json(request):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return None


def sound_rows(profile, limit=8):
    """The hardest sounds, ready for the template."""
    rows = []
    for stats in profile.hardest_sounds(limit):
        name, example = SOUNDS.get(stats.phoneme, (stats.phoneme.lower(), ""))
        heard_as = [SOUNDS[p][0] if p else "dropped" for p, _ in stats.heard_as.most_common(2)]
        rate = profile.sound_rate(stats.phoneme)
        rows.append({
            "name": name,
            "example": example,
            "percent": round(rate * 100),
            "bar": min(100, round(rate * 100 / 0.6)),  # 60% fills the bar
            "words": stats.words,
            "heard_as": heard_as,
            "problem_words": [w for w, _ in stats.problem_words.most_common(4)],
        })
    return rows


def profile_progress(user):
    done = Attempt.objects.filter(user=user, kind=Attempt.PROFILE).count()
    return {"done": min(done, PROFILE_TARGET), "target": PROFILE_TARGET,
            "percent": min(100, round(done * 100 / PROFILE_TARGET))}


@login_required
def home(request):
    profile = services.load_profile(request.user)
    return render(request, "core/home.html", {
        "profile": profile,
        "sounds": sound_rows(profile),
        "progress": profile_progress(request.user),
        "scripts": request.user.scripts.all()[:5],
    })


@login_required
def profile_session(request):
    counts = dict(
        Attempt.objects.filter(user=request.user, kind=Attempt.PROFILE)
        .values_list("sentence_key").annotate(n=Count("id"))
    )
    key = next_sentence(counts)
    return render(request, "core/profile_session.html", {
        "sentence_key": key,
        "sentence": SENTENCES[key],
        "progress": profile_progress(request.user),
    })


@login_required
@require_POST
def api_record(request):
    upload = request.FILES.get("audio")
    if upload is None:
        return json_error("No recording was received.")
    if upload.size > settings.SAYABLE["MAX_AUDIO_MB"] * 1024 * 1024:
        return json_error("The recording is too long. Keep each take under a minute or two.")

    kind = request.POST.get("kind")
    script, sentence_key = None, ""
    if kind == Attempt.PROFILE:
        sentence_key = request.POST.get("sentence_key", "")
        if sentence_key not in SENTENCES:
            return json_error("Unknown sentence.")
        expected = SENTENCES[sentence_key]
    elif kind == Attempt.REHEARSAL:
        script = get_object_or_404(Script, pk=request.POST.get("script_id"), user=request.user)
        chunks = rehearsal_chunks(script.text)
        try:
            expected = chunks[int(request.POST.get("chunk", ""))]
        except (ValueError, IndexError):
            return json_error("That part of the script no longer exists. Reload the page.")
    else:
        return json_error("Unknown recording type.")

    try:
        transcript = services.transcribe_upload(upload)
    except Exception:  # model download, a broken file, a missing library
        log.exception("Transcription failed")
        return json_error("Speech recognition failed. The first run needs internet to download "
                          "the speech model; after that, check the terminal window for details.", 500)

    if not transcript.words:
        return json_error("Nothing was heard. Check that the right microphone is selected and try again.")

    attempt, tokens = services.save_attempt(request.user, kind, expected, transcript,
                                            script=script, sentence_key=sentence_key)
    problems = sum(1 for t in tokens if t["status"] != "ok")
    return JsonResponse({"heard": transcript.text, "tokens": tokens, "text": expected,
                         "problems": problems, "counted": attempt is not None})


@login_required
def script_list(request):
    return render(request, "core/script_list.html", {"scripts": request.user.scripts.all()})


@login_required
def script_new(request):
    form = ScriptForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        script = form.save(commit=False)
        script.user = request.user
        script.save()
        return redirect("script_edit", pk=script.pk)
    return render(request, "core/script_edit.html", {"form": form, "script": None})


@login_required
def script_edit(request, pk):
    script = get_object_or_404(Script, pk=pk, user=request.user)
    form = ScriptForm(request.POST or None, instance=script)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Script saved.")
        return redirect("script_edit", pk=script.pk)
    prefs = services.user_settings(request.user)
    return render(request, "core/script_edit.html", {
        "form": form,
        "script": script,
        "claude_on": prefs.use_claude and bool(services.claude_key(prefs)),
    })


@login_required
@require_POST
def script_delete(request, pk):
    script = get_object_or_404(Script, pk=pk, user=request.user)
    script.delete()
    messages.success(request, f'Deleted "{script.title}".')
    return redirect("script_list")


@login_required
@require_POST
def api_check(request):
    data = read_json(request)
    if data is None or not isinstance(data.get("text"), str):
        return json_error("Send the script text to check.")
    text = data["text"][:MAX_SCRIPT_CHARS]
    profile = services.load_profile(request.user)
    prefs = services.user_settings(request.user)
    result = analyse_script(text, profile, prefs.sensitivity,
                            suggest=lambda word, risk: offline_suggestions(word, risk, profile))
    return JsonResponse(result)


@login_required
@require_POST
def api_suggest(request):
    data = read_json(request) or {}
    word, sentence = str(data.get("word", "")).strip(), str(data.get("sentence", ""))[:600]
    if not word:
        return json_error("No word to replace.")
    prefs = services.user_settings(request.user)
    if not (prefs.use_claude and services.claude_key(prefs)):
        return json_error("Claude suggestions are switched off. Turn them on in Settings.")
    profile = services.load_profile(request.user)
    risk = word_risk(word, profile)
    try:
        options = services.claude_suggestions(prefs, word, sentence, risk, profile)
    except claude.ClaudeError as err:
        return json_error(str(err), 502)
    return JsonResponse({"alternatives": options})


@login_required
def rehearse(request, pk):
    script = get_object_or_404(Script, pk=pk, user=request.user)
    chunks = rehearsal_chunks(script.text)
    if not chunks:
        messages.info(request, "Write something in the script before rehearsing it.")
        return redirect("script_edit", pk=script.pk)
    profile = services.load_profile(request.user)
    prefs = services.user_settings(request.user)
    pieces = [{"text": chunk, "flags": analyse_script(chunk, profile, prefs.sensitivity)["flags"]}
              for chunk in chunks]
    return render(request, "core/rehearse.html", {"script": script, "pieces": pieces})


@login_required
def settings_view(request):
    prefs = services.user_settings(request.user)
    form = SettingsForm(request.POST or None, instance=prefs)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("settings")
    return render(request, "core/settings.html", {
        "form": form,
        "has_key": bool(prefs.claude_api_key),
        "server_key": bool(settings.SAYABLE["ANTHROPIC_API_KEY"]),
        "recordings": Attempt.objects.filter(user=request.user).count(),
    })


@login_required
@require_POST
def delete_practice(request):
    deleted = Attempt.objects.filter(user=request.user).count()
    Attempt.objects.filter(user=request.user).delete()
    messages.success(request, f"Deleted the results of {deleted} recordings. Your profile starts again.")
    return redirect("settings")


def signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("profile_session")
    return render(request, "registration/signup.html", {"form": form})


def manifest(request):
    data = {
        "name": "Sayable",
        "short_name": "Sayable",
        "description": "Find the words you get misheard on, and say your talk with confidence.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#EEF2F0",
        "theme_color": "#0F6E6E",
        "icons": [
            {"src": static("core/icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("core/icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("core/icons/icon-maskable-512.png"), "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
    }
    return JsonResponse(data, content_type="application/manifest+json")


@never_cache
def service_worker(request):
    response = render(request, "core/sw.js", content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


def offline(request):
    return render(request, "core/offline.html")

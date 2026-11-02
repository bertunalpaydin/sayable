import json
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core import services
from core.models import Attempt, Script, UserSettings, WordResult
from core.speech.claude import ClaudeError
from core.speech.sentences import SENTENCES

from .helpers import FakeRecogniser, th_records

FAKE = {**settings.SAYABLE, "RECOGNISER": "core.tests.helpers.FakeRecogniser", "ANTHROPIC_API_KEY": ""}


def audio(name="take.webm", content_type="audio/webm"):
    return SimpleUploadedFile(name, b"fake audio bytes", content_type=content_type)


def give_th_history(user):
    """Store the TH-problem records as if the user had read them."""
    attempt = Attempt.objects.create(user=user, kind=Attempt.PROFILE, sentence_key="s01",
                                     expected_text="(test data)")
    WordResult.objects.bulk_create([
        WordResult(attempt=attempt, position=i, expected=exp, heard=heard, status=status)
        for i, (exp, heard, status) in enumerate(th_records())
    ])


@override_settings(SAYABLE=FAKE)
class ViewTestCase(TestCase):
    def setUp(self):
        services.recogniser.cache_clear()
        FakeRecogniser.words = []
        FakeRecogniser.seen_suffixes = []
        self.user = User.objects.create_user("ada", password="a-long-password-1")
        self.client.force_login(self.user)

    def tearDown(self):
        services.recogniser.cache_clear()


class AccountTests(TestCase):
    def test_pages_need_login(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_signup_logs_in_and_starts_reading(self):
        response = self.client.post(reverse("signup"), {
            "username": "grace", "password1": "a-long-password-1", "password2": "a-long-password-1"})
        self.assertRedirects(response, reverse("profile_session"))
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_login_page_renders(self):
        self.assertContains(self.client.get(reverse("login")), "Log in")


class ProfileFlowTests(ViewTestCase):
    def test_new_user_sees_the_intro(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Start reading")
        self.assertContains(response, "0 of 30")

    def test_session_shows_the_least_read_sentence(self):
        response = self.client.get(reverse("profile_session"))
        self.assertContains(response, SENTENCES["s01"])
        Attempt.objects.create(user=self.user, kind=Attempt.PROFILE, sentence_key="s01", expected_text="x")
        self.assertContains(self.client.get(reverse("profile_session")), SENTENCES["s02"])

    def test_recording_a_sentence(self):
        FakeRecogniser.words = [(w, 0.9) for w in
                                "Thank you all for coming, I sink this will be worse your time.".split()]
        response = self.client.post(reverse("api_record"), {
            "kind": "profile", "sentence_key": "s01", "audio": audio()})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        statuses = {t["text"]: t["status"] for t in data["tokens"]}
        self.assertEqual(statuses["think"], "misheard")
        self.assertEqual(statuses["worth"], "misheard")
        self.assertEqual(statuses["coming"], "ok")
        self.assertEqual(data["problems"], 2)
        self.assertTrue(data["counted"])
        self.assertEqual(data["text"], SENTENCES["s01"])
        self.assertEqual(WordResult.objects.filter(attempt__user=self.user, status="misheard").count(), 2)
        self.assertEqual(FakeRecogniser.seen_suffixes, ["webm"])

    def test_wrong_text_is_shown_but_not_counted(self):
        FakeRecogniser.words = [(w, 0.9) for w in "The weather was worse than we thought".split()]
        response = self.client.post(reverse("api_record"), {
            "kind": "profile", "sentence_key": "s01", "audio": audio()})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["counted"])
        self.assertFalse(Attempt.objects.exists())

    def test_safari_audio_keeps_its_type(self):
        FakeRecogniser.words = [("Thank", 0.9)]
        self.client.post(reverse("api_record"), {
            "kind": "profile", "sentence_key": "s01", "audio": audio("take.m4a", "audio/mp4")})
        self.assertEqual(FakeRecogniser.seen_suffixes, ["m4a"])

    def test_bad_requests(self):
        url = reverse("api_record")
        self.assertEqual(self.client.post(url, {"kind": "profile", "sentence_key": "s01"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"kind": "profile", "sentence_key": "nope",
                                                "audio": audio()}).status_code, 400)
        self.assertEqual(self.client.post(url, {"kind": "other", "audio": audio()}).status_code, 400)

    def test_silence_is_reported(self):
        FakeRecogniser.words = []
        response = self.client.post(reverse("api_record"), {
            "kind": "profile", "sentence_key": "s01", "audio": audio()})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Nothing was heard", response.json()["error"])
        self.assertFalse(Attempt.objects.exists())

    def test_recogniser_failure_is_explained(self):
        with mock.patch.object(FakeRecogniser, "transcribe", side_effect=RuntimeError("no model")):
            with self.assertLogs("core.views", "ERROR"):
                response = self.client.post(reverse("api_record"), {
                    "kind": "profile", "sentence_key": "s01", "audio": audio()})
        self.assertEqual(response.status_code, 500)
        self.assertIn("speech model", response.json()["error"])

    def test_home_shows_hard_sounds_once_ready(self):
        give_th_history(self.user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Sounds that get misheard")
        self.assertContains(response, "as in “think”")


class ScriptTests(ViewTestCase):
    def test_create_edit_and_delete(self):
        response = self.client.post(reverse("script_new"), {"title": "Talk", "text": "Hello there."})
        script = Script.objects.get(user=self.user)
        self.assertRedirects(response, reverse("script_edit", args=[script.pk]))
        self.client.post(reverse("script_edit", args=[script.pk]), {"title": "Talk 2", "text": "Hi."})
        script.refresh_from_db()
        self.assertEqual(script.title, "Talk 2")
        self.client.post(reverse("script_delete", args=[script.pk]))
        self.assertFalse(Script.objects.exists())

    def test_other_peoples_scripts_are_hidden(self):
        other = User.objects.create_user("bob", password="a-long-password-1")
        script = Script.objects.create(user=other, title="Secret", text="Private words.")
        self.assertEqual(self.client.get(reverse("script_edit", args=[script.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("rehearse", args=[script.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("script_delete", args=[script.pk])).status_code, 404)

    def test_check_flags_th_words_with_options(self):
        give_th_history(self.user)
        response = self.client.post(reverse("api_check"), json.dumps({
            "text": "I would like to thank everyone. We tested it thoroughly."}),
            content_type="application/json")
        flags = {f["word"]: f for f in response.json()["flags"]}
        self.assertIn("thank", flags)
        self.assertIn("thoroughly", flags)
        self.assertTrue(flags["thoroughly"]["alternatives"])
        self.assertEqual(flags["thoroughly"]["sentence"], "We tested it thoroughly.")

    def test_check_before_profile_is_ready(self):
        response = self.client.post(reverse("api_check"), json.dumps({"text": "I think so."}),
                                    content_type="application/json")
        self.assertEqual(response.json()["flags"], [])
        self.assertFalse(response.json()["profile_ready"])

    def test_check_needs_text(self):
        response = self.client.post(reverse("api_check"), "not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_rehearse_records_a_part(self):
        give_th_history(self.user)
        script = Script.objects.create(user=self.user, title="Talk",
                                       text="Thank you for coming. Today I will talk about growth.")
        page = self.client.get(reverse("rehearse", args=[script.pk]))
        self.assertContains(page, "Thank you for coming.")
        FakeRecogniser.words = [(w, 0.9) for w in "Sank you for coming today I will talk about growth".split()]
        response = self.client.post(reverse("api_record"), {
            "kind": "rehearsal", "script_id": script.pk, "chunk": 0, "audio": audio()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tokens"][0]["status"], "misheard")
        self.assertEqual(Attempt.objects.filter(kind="rehearsal", script=script).count(), 1)

    def test_rehearse_rejects_a_missing_part(self):
        script = Script.objects.create(user=self.user, title="Talk", text="Short.")
        response = self.client.post(reverse("api_record"), {
            "kind": "rehearsal", "script_id": script.pk, "chunk": 5, "audio": audio()})
        self.assertEqual(response.status_code, 400)

    def test_empty_script_cannot_be_rehearsed(self):
        script = Script.objects.create(user=self.user, title="Empty", text=" ")
        self.assertRedirects(self.client.get(reverse("rehearse", args=[script.pk])),
                             reverse("script_edit", args=[script.pk]))


class ClaudeTests(ViewTestCase):
    def enable(self, key="sk-test"):
        UserSettings.objects.update_or_create(user=self.user, defaults={"use_claude": True, "claude_api_key": key})

    def test_off_by_default(self):
        response = self.client.post(reverse("api_suggest"), json.dumps({"word": "think"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_options_are_ranked_for_the_speaker(self):
        give_th_history(self.user)
        self.enable()
        with mock.patch("core.speech.claude.suggest", return_value=["believe", "think through", "reckon"]) as call:
            response = self.client.post(reverse("api_suggest"), json.dumps(
                {"word": "think", "sentence": "I think it works."}), content_type="application/json")
        texts = [o["text"] for o in response.json()["alternatives"]]
        self.assertIn("believe", texts)
        self.assertNotIn("think through", texts)
        self.assertEqual(call.call_args.args[0], "sk-test")

    def test_claude_errors_are_shown(self):
        self.enable()
        with mock.patch("core.speech.claude.suggest", side_effect=ClaudeError("Claude rejected the API key.")):
            response = self.client.post(reverse("api_suggest"), json.dumps({"word": "think"}),
                                        content_type="application/json")
        self.assertEqual(response.status_code, 502)
        self.assertIn("API key", response.json()["error"])


class SettingsTests(ViewTestCase):
    def post(self, **extra):
        data = {"sensitivity": "normal", "claude_api_key": "", **extra}
        return self.client.post(reverse("settings"), data)

    def test_key_is_kept_when_left_blank(self):
        self.post(use_claude="on", claude_api_key="sk-first")
        self.post(use_claude="on")
        self.assertEqual(UserSettings.objects.get(user=self.user).claude_api_key, "sk-first")

    def test_key_can_be_removed(self):
        self.post(claude_api_key="sk-first")
        self.post(remove_key="on")
        self.assertEqual(UserSettings.objects.get(user=self.user).claude_api_key, "")

    def test_key_is_never_shown(self):
        self.post(claude_api_key="sk-secret-value")
        self.assertNotContains(self.client.get(reverse("settings")), "sk-secret-value")

    def test_delete_practice_results(self):
        give_th_history(self.user)
        Script.objects.create(user=self.user, title="Keep me", text="Hi.")
        self.client.post(reverse("delete_practice"))
        self.assertFalse(WordResult.objects.exists())
        self.assertTrue(Script.objects.exists())


class AppShellTests(TestCase):
    def test_manifest_and_service_worker(self):
        manifest = self.client.get(reverse("manifest"))
        self.assertEqual(manifest.json()["display"], "standalone")
        worker = self.client.get(reverse("service_worker"))
        self.assertEqual(worker["Content-Type"], "application/javascript")
        self.assertContains(worker, "sayable-v1")

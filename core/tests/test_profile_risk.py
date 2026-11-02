from django.test import SimpleTestCase

from core.speech.profile import READY_WORDS, build_profile
from core.speech.risk import HIGH, MEDIUM, WordRisk, analyse_script, explain, word_risk

from .helpers import CLEAR_WORDS, th_profile


class ProfileTests(SimpleTestCase):
    def test_th_stands_out(self):
        profile = th_profile()
        self.assertTrue(profile.ready)
        hardest = profile.hardest_sounds()
        self.assertEqual(hardest[0].phoneme, "TH")
        self.assertGreater(profile.sound_rate("TH"), 3 * profile.sound_rate("M"))

    def test_only_the_confused_sound_is_blamed(self):
        profile = th_profile()
        # "think" -> "sink" should not make the other sounds of "think" look bad
        self.assertLess(profile.sound_rate("NG"), profile.sound_rate("TH") / 3)

    def test_what_th_was_heard_as(self):
        heard_as = th_profile().sounds["TH"].heard_as
        self.assertEqual(heard_as.most_common(1)[0][0], "S")

    def test_function_words_do_not_count(self):
        profile = build_profile([("the", "a", "misheard"), ("of", "", "missed")])
        self.assertEqual(profile.total_words, 0)

    def test_not_ready_with_little_data(self):
        profile = build_profile([(w, w, "ok") for w in CLEAR_WORDS[:5]])
        self.assertLess(profile.total_words, READY_WORDS)
        self.assertFalse(profile.ready)


class RiskTests(SimpleTestCase):
    def setUp(self):
        self.profile = th_profile()

    def test_th_word_is_flagged_with_a_reason(self):
        risk = word_risk("thorough", self.profile)
        self.assertEqual(risk.reason_sound, "TH")
        self.assertEqual(risk.level(), HIGH)
        self.assertIn('th (as in "think")', explain(risk, self.profile))
        self.assertIn('often heard as "s"', explain(risk, self.profile))

    def test_easy_word_is_not_flagged(self):
        self.assertIsNone(word_risk("market", self.profile).level())

    def test_sensitivity_changes_what_is_flagged(self):
        risk = WordRisk("method", 0.35, "TH", False, 0, 0.0)
        self.assertEqual(risk.level("normal"), MEDIUM)
        self.assertIsNone(risk.level("low"))
        self.assertEqual(WordRisk("method", 0.45, "TH", False, 0, 0.0).level("high"), HIGH)

    def test_no_reason_no_flag(self):
        self.assertIsNone(WordRisk("long", 0.9, None, False, 0, 0.0).level())

    def test_word_history_counts_before_the_profile_is_ready(self):
        profile = build_profile([("market", "marked", "misheard"), ("market", "marked", "misheard")])
        self.assertFalse(profile.ready)
        risk = word_risk("market", profile)
        self.assertIsNotNone(risk.level())
        self.assertIsNone(word_risk("thorough", profile).level())
        self.assertIn("2 times", explain(risk, profile))

    def test_unknown_word_is_guessed(self):
        risk = word_risk("Thandeka", self.profile)
        self.assertTrue(risk.guessed)
        self.assertEqual(risk.reason_sound, "TH")


class ScriptAnalysisTests(SimpleTestCase):
    def test_flags_have_positions_and_sentences(self):
        text = "Good morning. I think the market is growing!"
        result = analyse_script(text, th_profile())
        words = [text[f["start"]:f["end"]] for f in result["flags"]]
        self.assertEqual(words, ["think"])
        self.assertEqual(result["flags"][0]["sentence"], "I think the market is growing!")
        self.assertEqual(result["content_words"], 5)

    def test_suggest_is_called_for_flags(self):
        result = analyse_script("I think so.", th_profile(), suggest=lambda word, risk: [{"text": "x"}])
        self.assertEqual(result["flags"][0]["alternatives"], [{"text": "x"}])

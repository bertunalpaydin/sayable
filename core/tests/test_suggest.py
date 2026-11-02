from django.test import SimpleTestCase

from core.speech.claude import ClaudeError, parse_options
from core.speech.risk import word_risk
from core.speech.suggest import (base_forms, offline_suggestions, rank_options,
                                 synonym_candidates, with_ending)

from .helpers import th_profile


class EndingTests(SimpleTestCase):
    def test_endings_are_put_back(self):
        self.assertEqual(with_ending("believe", "ing"), "believing")
        self.assertEqual(with_ending("stop", "ed"), "stopped")
        self.assertEqual(with_ending("carry", "s"), "carries")
        self.assertEqual(with_ending("complete", "ly"), "completely")
        self.assertIsNone(with_ending("think", "ed"))  # "thinked" is not a word

    def test_base_forms(self):
        self.assertIn(("think", "ing"), base_forms("thinking"))
        self.assertIn(("thorough", "ly"), base_forms("thoroughly"))


class SynonymTests(SimpleTestCase):
    def test_candidates_never_repeat_the_word(self):
        candidates = synonym_candidates("thinking")
        self.assertNotIn("thinking", candidates)
        self.assertNotIn("think", candidates)
        self.assertIn("believing", candidates)

    def test_suggestions_avoid_the_hard_sound(self):
        profile = th_profile()
        options = offline_suggestions("thoroughly", word_risk("thoroughly", profile), profile)
        texts = [o["text"] for o in options]
        self.assertTrue(texts)
        self.assertTrue(all("th" not in t for t in texts), texts)

    def test_harder_options_are_dropped(self):
        profile = th_profile()
        risk = word_risk("market", profile)
        self.assertEqual(rank_options(["thought", "theme"], risk, profile), [])


class ClaudeParsingTests(SimpleTestCase):
    def test_reads_json_inside_text(self):
        text = 'Sure! {"options": ["fully", "in detail", "in a lot of detail", "thoroughly"]}'
        self.assertEqual(parse_options(text, "thoroughly"), ["fully", "in detail"])

    def test_rejects_garbage(self):
        with self.assertRaises(ClaudeError):
            parse_options("no json here", "word")

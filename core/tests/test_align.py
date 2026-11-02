from django.test import SimpleTestCase

from core.speech.align import HeardWord, compare, sound_confusions
from core.speech.text import words_for_matching


def run(expected, heard, probability=0.9):
    words = [HeardWord(w, probability) if isinstance(w, str) else HeardWord(*w) for w in heard]
    return compare(words_for_matching(expected), words)


class CompareTests(SimpleTestCase):
    def test_all_heard(self):
        outcomes = run("Thank you all.", ["Thank", "you", "all."])
        self.assertEqual([o.status for o in outcomes], ["ok", "ok", "ok"])

    def test_misheard_word_points_at_the_sound(self):
        outcomes = run("I think so", ["I", "sink", "so"])
        self.assertEqual(outcomes[1].status, "misheard")
        self.assertEqual(outcomes[1].heard, "sink")
        self.assertEqual(outcomes[1].confusions, [("TH", "S")])

    def test_missed_word(self):
        outcomes = run("we value every voice", ["we", "every", "voice"])
        self.assertEqual([o.status for o in outcomes], ["ok", "missed", "ok", "ok"])

    def test_low_probability_is_unclear(self):
        outcomes = run("quiet room", [("quiet", 0.2), ("room", 0.95)])
        self.assertEqual([o.status for o in outcomes], ["unclear", "ok"])

    def test_extra_words_are_ignored(self):
        outcomes = run("good morning", ["um", "good", "morning", "everyone"])
        self.assertEqual([o.status for o in outcomes], ["ok", "ok"])

    def test_homophones_and_spelling_are_not_errors(self):
        outcomes = run("their colour was organised", ["there", "color", "was", "organized"])
        self.assertEqual({o.status for o in outcomes}, {"ok"})

    def test_digits_in_either_text(self):
        self.assertEqual({o.status for o in run("twelve days", ["12", "days"])}, {"ok"})
        self.assertEqual({o.status for o in run("12 days", ["twelve", "days"])}, {"ok"})

    def test_split_and_joined_words(self):
        self.assertEqual({o.status for o in run("thanks everyone", ["thanks", "every", "one"])}, {"ok"})
        self.assertEqual({o.status for o in run("every one of you", ["everyone", "of", "you"])}, {"ok"})


class SoundConfusionTests(SimpleTestCase):
    def test_dropped_sound(self):
        self.assertIn(("T", ""), sound_confusions("asked", "ask"))

    def test_unknown_words_give_nothing(self):
        self.assertEqual(sound_confusions("zxqvb", "think"), [])

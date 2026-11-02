from django.test import SimpleTestCase

from core.speech.text import (number_to_words, rehearsal_chunks, sentence_spans, tokenise,
                              words_for_matching)


class NumberTests(SimpleTestCase):
    def test_small_and_large_numbers(self):
        self.assertEqual(number_to_words(0), "zero")
        self.assertEqual(number_to_words(42), "forty two")
        self.assertEqual(number_to_words(305), "three hundred and five")
        self.assertEqual(number_to_words(2026), "two thousand and twenty six")


class MatchingWordsTests(SimpleTestCase):
    def test_punctuation_case_and_digits(self):
        self.assertEqual(words_for_matching("Hello, World! I have 12 cats."),
                         ["hello", "world", "i", "have", "twelve", "cats"])

    def test_decimals_and_thousands(self):
        self.assertEqual(words_for_matching("3.5 and 1,200"),
                         ["three", "point", "five", "and", "one", "thousand", "two", "hundred"])

    def test_curly_apostrophes_and_hyphens(self):
        self.assertEqual(words_for_matching("It’s well-known"), ["it's", "well", "known"])

    def test_tokens_keep_positions(self):
        text = "Thank you, all."
        tokens = tokenise(text)
        self.assertEqual([text[t.start:t.end] for t in tokens], ["Thank", "you", "all"])


class SentenceTests(SimpleTestCase):
    def test_sentence_spans(self):
        text = "First one. Second one? Third!"
        self.assertEqual([text[s:e] for s, e in sentence_spans(text)],
                         ["First one.", "Second one?", "Third!"])

    def test_chunks_group_short_sentences_and_split_long_scripts(self):
        text = " ".join(["This sentence has exactly seven words in it."] * 10)
        chunks = rehearsal_chunks(text, max_words=20)
        self.assertEqual(len(chunks), 5)
        self.assertTrue(all(len(c.split()) <= 20 for c in chunks))

    def test_empty_script_has_no_chunks(self):
        self.assertEqual(rehearsal_chunks("   \n "), [])

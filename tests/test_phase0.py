"""Phase 0: deterministic fixes, one test class per row of the spec's §9 table."""
import json
import os
import re
import unittest

from tests.support import SKILLS, load


def lexicon():
    with open(os.path.join(SKILLS, "ig-human", "slop.json"), encoding="utf-8") as fh:
        return json.load(fh)


class HookscoreFrontload(unittest.TestCase):
    """#1 WEAK_OPENERS matched by prefix: 'Social' took the 'so' penalty."""

    def test_prefix_words_are_not_weak_openers(self):
        hs = load("hookscore")
        for hook in ["Social proof is the only thing that sells a retainer.",
                     "Sometimes the cheapest client costs the most.",
                     "Justice for the freelancers who never invoice on time."]:
            _, detail = hs.check_frontload(hook)
            self.assertNotIn("weak opener", detail, hook)

    def test_real_weak_openers_still_penalised(self):
        hs = load("hookscore")
        for hook in ["So today I want to talk about pricing.",
                     "Just a quick one about invoices.",
                     "I want to show you my desk setup."]:
            _, detail = hs.check_frontload(hook)
            self.assertIn("weak opener", detail, hook)


class HookscoreProper(unittest.TestCase):
    """#2 a capital after a full stop was counted as a proper noun."""

    def test_sentence_start_is_not_a_name(self):
        hs = load("hookscore")
        self.assertEqual(hs.proper_nouns("It works. Then everything changed."), [])

    def test_mid_sentence_name_counts(self):
        hs = load("hookscore")
        self.assertEqual(hs.proper_nouns("I asked Dana for the invoice."), ["Dana"])

    def test_specificity_ignores_sentence_starts(self):
        hs = load("hookscore")
        score, detail = hs.check_specificity("It works. Then everything changed.")
        self.assertEqual(score, 15.0, detail)


class BeatsConcrete(unittest.TestCase):
    """#3 beats counted 'Then' as concrete and missed spoken numbers."""

    def test_sentence_start_not_concrete(self):
        beats = load("beats")
        self.assertEqual(beats.concrete_markers("It works. Then everything changed."), [])

    def test_spoken_numbers_are_concrete(self):
        beats = load("beats")
        self.assertIn("five", beats.concrete_markers("Proposals used to take me five hours."))

    def test_analyse_uses_the_fixed_counter(self):
        beats = load("beats")
        a = beats.analyse("It works. Then everything changed.\nTwenty grand, gone.")
        self.assertEqual([b["concrete"] for b in a["beats"]], [0, 2])


class CaptionConcrete(unittest.TestCase):
    """#4 caption counted 'Monday' and 'Instagram' as concrete."""

    def test_weekday_platform_and_sentence_start_excluded(self):
        cap = load("caption")
        self.assertEqual(cap.concrete_markers("Happy Monday. Instagram is weird."), [])

    def test_real_markers_kept(self):
        cap = load("caption")
        found = cap.concrete_markers("I charged $400 for my first logo and Dana paid twenty grand.")
        self.assertIn("$4", found[0])
        self.assertIn("Dana", found)
        self.assertIn("twenty", found)

    def test_hook_is_concrete_check_uses_it(self):
        cap = load("caption")
        a = cap.analyse("Happy Monday. Instagram is weird.\n\nSave this.")
        check = next(c for c in a["checks"] if c["check"] == "HOOK IS CONCRETE")
        self.assertEqual(check["status"], "WARN")


class DetectTypography(unittest.TestCase):
    """#5 curly apostrophes hid structural tells from detect.py."""

    def test_curly_not_just_is_detected(self):
        det = load("detect")
        text = ("It’s not just a template, it’s a system. "
                "I wrote it for my studio and we use it on every proposal we send out "
                "to clients who want a fixed price and a clear scope.")
        _, detail = det.check_voice(text, lexicon())
        self.assertIn("not-just", detail)

    def test_fingerprint_still_counts_curly(self):
        det = load("detect")
        _, detail = det.check_fingerprint("It’s fine.")
        self.assertIn("1 curly quote", detail)


class SlopIsntAbout(unittest.TestCase):
    """#6 'It's not about X. It's about Y.' was not matched."""

    def test_variants(self):
        rx = re.compile(next(s["regex"] for s in lexicon()["structures"] if s["id"] == "isnt-about"),
                        re.MULTILINE)
        for text in ["It's not about the money. It's about respect.",
                     "Its not about followers. It's about buyers.",
                     "This isn't about hashtags. It's about hooks.",
                     "It is not about volume. It's about fit."]:
            self.assertTrue(rx.search(text), text)
        self.assertFalse(rx.search("It's about time we talked about pricing."))


if __name__ == "__main__":
    unittest.main()

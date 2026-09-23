"""caption.py: asks read by Jev per sentence; regex kept as the fallback and the cross-check."""
import json
import os
import unittest
from unittest import mock

from tests.support import load, run_cli

cap = load("caption")
jev = load("jev")
TYPES = ["comment_keyword", "comment_reply", "save", "share_or_send", "follow", "dm",
         "link_in_bio", "swipe", "no_ask"]


def transport(by_sentence, seen=None):
    """by_sentence: substring -> (p_is_ask, type)."""
    def t(body, timeout):
        if seen is not None:
            seen.append(body)
        ans = {}
        for q, spec in body["questions"].items():
            s = spec["instructions"]["sentence"]
            p, typ = next((v for k, v in by_sentence.items() if k in s), (0.02, "no_ask"))
            if q.endswith("_is_ask"):
                ans[q] = {"type": "noul", "noul": p}
            else:
                ans[q] = {"type": "choice", "choice": typ, "confidence": 0.9,
                          "probabilities": {o: (0.9 if o == typ else 0.0125) for o in TYPES}}
        return {"model": jev.MODEL, "usage": {"input_tokens": 1, "output_tokens": 1}, "answers": ans}
    return t


class Split(unittest.TestCase):
    def test_quotes_stay_whole_and_hashtag_lines_drop(self):
        s = cap.split_sentences('She said "share it. now." and left. Save this.\n#pricing #freelance')
        self.assertEqual(s, ['She said "share it. now." and left.', "Save this."])

    def test_curly_quotes_and_mentions_line(self):
        s = cap.split_sentences("He wrote “follow me. please.” and I laughed.\n@someone @else")
        self.assertEqual(s, ["He wrote “follow me. please.” and I laughed."])


class SplitReview(unittest.TestCase):
    def test_inch_mark_is_not_a_quote(self):
        s = cap.split_sentences('My 12" ring light changed everything. Comment LIGHT for the link. '
                                'Save this for later.')
        self.assertEqual(len(s), 3)

    def test_two_asks_joined_by_and_are_split_but_stories_are_not(self):
        self.assertEqual(cap.split_sentences("Save this and share it with a friend who freelances."),
                         ["Save this", "share it with a friend who freelances."])
        self.assertEqual(cap.split_sentences("I had to follow my gut and walk away from the deal."),
                         ["I had to follow my gut and walk away from the deal."])
        self.assertEqual(len(cap.split_sentences('She said "save this and share it." and left.')), 1)


class Questions(unittest.TestCase):
    def test_two_questions_per_sentence(self):
        q = cap.ask_questions(["Save this.", "I rebuilt it."])
        self.assertEqual(sorted(q), ["s1_ask_type", "s1_is_ask", "s2_ask_type", "s2_is_ask"])
        self.assertEqual(set(q["s1_ask_type"]["criteria"]), set(TYPES))
        self.assertIn("`caption`", q["s1_is_ask"]["instructions"]["question"])
        self.assertEqual(q["s2_is_ask"]["instructions"]["sentence"], "I rebuilt it.")


class Asks(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "k" * 20})
        self.env.start()
        os.environ.pop("IG_JEV", None)
        self.old = jev.set_transport(jev.TRANSPORT)

    def tearDown(self):
        jev.set_transport(self.old)
        self.env.stop()

    def one_ask(self, a):
        return next(c for c in a["checks"] if c["check"] == "ONE ASK")

    def test_paraphrased_ask_is_found(self):
        jev.set_transport(transport({"linked on my profile": (0.9, "link_in_bio")}))
        a = cap.analyse("I rebuilt my pricing page in March.\nGrab the free template, it's linked on my profile.")
        self.assertEqual(self.one_ask(a)["status"], "PASS")
        self.assertIn("linked on my profile", self.one_ask(a)["detail"])
        self.assertEqual(a["engine"], "jev")
        self.assertEqual(a["asks"], ["link_in_bio"])
        self.assertEqual(a["heuristic_asks"], [])

    def test_state_is_the_caption_without_tag_lines(self):
        seen = []
        jev.set_transport(transport({}, seen))
        cap.analyse("Save this.\n#one #two")
        self.assertEqual(seen[0]["state"], {"caption": "Save this."})

    def test_quoted_share_is_not_an_ask(self):
        jev.set_transport(transport({"Save this": (0.95, "save")}))
        a = cap.analyse("She told me to share it with the whole team before Friday.\nSave this.")
        self.assertEqual(self.one_ask(a)["status"], "PASS")
        self.assertIn("regex vs jev", "\n".join(a["notes"]))

    def test_repeats_count_once_and_two_types_warn(self):
        jev.set_transport(transport({"Save this": (0.9, "save"), "Save it": (0.9, "save"),
                                     "Follow": (0.9, "follow")}))
        a = cap.analyse("Save this. Save it for later.\nFollow for part 2.")
        self.assertEqual(a["asks"], ["save", "follow"])
        self.assertEqual(self.one_ask(a)["status"], "WARN")

    def test_two_asks_in_one_sentence_warn(self):
        jev.set_transport(transport({"Save this": (0.9, "save"), "share it": (0.9, "share_or_send")}))
        a = cap.analyse("The template is below.\nSave this and share it with a friend who freelances.")
        self.assertEqual(self.one_ask(a)["status"], "WARN")
        self.assertEqual(a["asks"], ["save", "share_or_send"])

    def test_borderline_is_reported_never_fail(self):
        jev.set_transport(transport({"Save this": (0.9, "save"), "Thoughts": (0.5, "comment_reply")}))
        a = cap.analyse("Save this.\nThoughts on the new grid.")
        self.assertIn("borderline, decide out loud", "\n".join(a["notes"]))
        self.assertEqual(self.one_ask(a)["status"], "WARN")

    def test_possible_ask_below_the_line(self):
        jev.set_transport(transport({"Save this": (0.9, "save"), "Thoughts": (0.4, "comment_reply")}))
        a = cap.analyse("Save this.\nThoughts on the new grid.")
        self.assertEqual(self.one_ask(a)["status"], "PASS")
        self.assertIn("possible ask (0.40)", "\n".join(a["notes"]))

    def test_keyword_needs_one_caps_token(self):
        jev.set_transport(transport({"Comment below": (0.9, "comment_keyword")}))
        a = cap.analyse("Comment below and I'll send the file.")
        self.assertEqual(self.one_ask(a)["status"], "WARN")
        jev.set_transport(transport({"Comment PRICING": (0.9, "comment_keyword")}))
        a = cap.analyse("Comment PRICING and I'll send the calculator.")
        self.assertEqual(self.one_ask(a)["status"], "PASS")

    def test_unspecified_type(self):
        jev.set_transport(transport({"Do it": (0.9, "no_ask")}))
        a = cap.analyse("Do it today.")
        self.assertIn("unspecified", self.one_ask(a)["detail"])

    def test_jev_never_turns_into_fail(self):
        jev.set_transport(transport({"a": (0.9, "save"), "b": (0.9, "follow"), "c": (0.9, "dm")}))
        a = cap.analyse("a one. b two. c three.")
        self.assertNotIn("FAIL", [c["status"] for c in a["checks"]])
        self.assertEqual(a["verdict"], "REVIEW")

    def test_failure_falls_back_to_regex(self):
        def boom(body, timeout):
            raise jev.JevUnavailable("offline", "cached")
        jev.set_transport(boom)
        a = cap.analyse("Save this.\nFollow for more.")
        self.assertEqual((a["engine"], a["engine_reason"]), ("heuristic", "offline"))
        self.assertEqual(a["asks"], a["heuristic_asks"])


class Off(unittest.TestCase):
    def test_off_equals_regex_path(self):
        a = cap.analyse("Save this.\nFollow for more.")
        self.assertEqual(a["engine"], "heuristic")
        self.assertEqual(a["asks"], a["heuristic_asks"])
        self.assertEqual(a["notes"], [])

    def test_cli_engine_line_and_exit_3(self):
        p = run_cli("ig-caption/caption.py", ["tests/fixtures/caption.txt"])
        self.assertTrue(p.stdout.startswith("engine: heuristic (disabled)"), p.stdout)
        self.assertEqual(p.returncode, 0)
        p = run_cli("ig-caption/caption.py", ["tests/fixtures/caption.txt", "--engine", "jev"])
        self.assertEqual(p.returncode, 3)
        p = run_cli("ig-caption/caption.py", ["tests/fixtures/caption.txt", "--json"])
        self.assertEqual(json.loads(p.stdout)["engine_reason"], "disabled")


if __name__ == "__main__":
    unittest.main()

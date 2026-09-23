"""swipe.py counts formulas with formula.classify_hooks: one engine per run."""
import os
import unittest
from unittest import mock

from tests.support import load, run_cli

swipe = load("swipe")
jev = load("jev")
ROWS = [
    {"account": "@a", "followers": 1000, "median": 500, "views": 50000,
     "hook": "Nobody tells you that your first 30 reels are supposed to flop."},
    {"account": "@b", "followers": 1000, "median": 500, "views": 40000,
     "hook": "never in a million years did i think this reel would pay my rent"},
    {"account": "@c", "followers": 1000, "median": 500, "views": 600, "hook": "hey guys welcome back"},
]


def rows():
    return [dict(r) for r in ROWS]


class SwipeEngine(unittest.TestCase):
    def setUp(self):
        self.old = jev.set_transport(jev.TRANSPORT)

    def tearDown(self):
        jev.set_transport(self.old)

    def test_heuristic_counts_like_before(self):
        a = swipe.analyse(rows(), swipe.load_formulas(swipe.HOOKS))
        self.assertEqual(a["formula_engine"], "regex (disabled)")
        self.assertEqual(a["top_formulas"], [("Nobody Tells You", 1)])
        self.assertEqual(a["unclassified"], 2)
        self.assertEqual(a["jev_only"], 0)
        self.assertTrue(a["engine_line"].startswith("engine: heuristic (disabled)"))

    def test_jev_counts_only_agree_and_jev(self):
        def t(body, timeout):
            hook = body["state"]["hook"].lower()
            pick = "nobody_tells_you" if hook.startswith(("nobody", "never")) else "none"
            opts = body["questions"]["formula"]["criteria"]
            return {"model": jev.MODEL, "usage": {"input_tokens": 1, "output_tokens": 1},
                    "answers": {"formula": {"type": "choice", "choice": pick, "confidence": 0.9,
                                            "probabilities": {o: 0.0 for o in opts}},
                                "has_shape": {"type": "noul", "noul": 0.05}}}
        jev.set_transport(t)
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "k" * 20}):
            os.environ.pop("IG_JEV", None)
            a = swipe.analyse(rows(), swipe.load_formulas(swipe.HOOKS))
        self.assertEqual(a["formula_engine"], "regex+jev-1.13.0")
        by_hook = {r["hook"]: r for r in a["reels"]}
        self.assertEqual(by_hook[ROWS[0]["hook"]]["formula_status"], "AGREE")
        self.assertEqual(by_hook[ROWS[1]["hook"]]["formula_status"], "JEV")
        self.assertEqual(by_hook[ROWS[1]["hook"]]["formula"], "Nobody Tells You")
        self.assertEqual(by_hook[ROWS[2]["hook"]]["formula_status"], "NO-HOOK")
        self.assertEqual(a["jev_only"], 1)
        self.assertEqual(a["unclassified"], 1)
        self.assertEqual(a["engine"], "jev")

    def test_markdown_header_records_engine_and_version(self):
        a = swipe.analyse(rows(), swipe.load_formulas(swipe.HOOKS))
        md = swipe.to_markdown(a)
        self.assertIn("formula engine: regex (disabled)", md)
        self.assertIn("hooks.json v1.1", md)

    def test_engine_jev_unavailable_exits_3(self):
        p = run_cli("ig-viral/swipe.py", ["tests/fixtures/swipe.tsv", "--engine", "jev"])
        self.assertEqual(p.returncode, 3)
        self.assertTrue(p.stdout.startswith("engine: heuristic (no-key)"), p.stdout)


if __name__ == "__main__":
    unittest.main()

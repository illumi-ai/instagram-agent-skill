"""fit.py: veto the hook formulas an idea cannot carry without invented facts."""
import json
import os
import re
import unittest
from unittest import mock

from tests.support import SKILLS, load, run_cli

fit = load("fit")
jev = load("jev")
HOOKS = os.path.join(SKILLS, "ig-reel", "hooks.json")


class Needs(unittest.TestCase):
    def test_every_formula_has_literal_needs(self):
        with open(HOOKS, encoding="utf-8") as fh:
            data = json.load(fh)
        for h in data["hooks"]:
            needs = h.get("needs")
            self.assertIsInstance(needs, list, h["name"])
            self.assertTrue(needs and all(isinstance(n, str) and n.strip() for n in needs), h["name"])
            placeholders = re.findall(r"\{", h["template"])
            self.assertGreaterEqual(len(needs), min(len(placeholders), 1), h["name"])


class Questions(unittest.TestCase):
    def test_one_multi_plus_one_fit_per_formula(self):
        q = fit.build_questions(fit.load_formulas())
        self.assertEqual(len(q), 27)
        self.assertEqual(q["multi_idea"]["type"], "noul")
        f1 = q["fit_1"]["instructions"]
        self.assertEqual(set(f1["formula"]), {"name", "template", "needs"})
        self.assertIn("`formula.needs`", f1["question"])
        self.assertEqual(set(q["fit_1"]["criteria"]), {"true", "false"})


class Policy(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "k" * 20})
        self.env.start()
        os.environ.pop("IG_JEV", None)
        self.old = jev.set_transport(jev.TRANSPORT)

    def tearDown(self):
        jev.set_transport(self.old)
        self.env.stop()

    def test_three_lists_and_multi(self):
        def t(body, timeout):
            self.assertEqual(set(body["state"]), {"idea"})
            ans = {}
            for q in body["questions"]:
                p = {"fit_5": 0.95, "fit_9": 0.4, "multi_idea": 0.8}.get(q, 0.05)
                ans[q] = {"type": "noul", "noul": p}
            return {"model": jev.MODEL, "usage": {"input_tokens": 1, "output_tokens": 1}, "answers": ans}
        jev.set_transport(t)
        r = fit.fit("we cut proposal time from 5 hours to 20 minutes with one template")
        self.assertEqual([w["id"] for w in r["writable"]], [5])
        self.assertEqual([u["id"] for u in r["unlockable"]], [9])
        self.assertEqual(len(r["vetoed"]), 24)
        self.assertTrue(r["multi"])
        text = fit.render(r)
        self.assertTrue(text.startswith("engine: jev-1.13.0"))
        self.assertIn("TWO IDEAS? which one first?", text)
        self.assertIn("ask for:", text)
        self.assertIn("fit: 1 writable, 1 unlockable, 24 vetoed · engine jev-1.13.0", text)

    def test_idea_truncated_and_one_request(self):
        calls = []

        def t(body, timeout):
            calls.append(body)
            return {"model": jev.MODEL, "usage": {}, "answers": {
                q: {"type": "noul", "noul": 0.5} for q in body["questions"]}}
        jev.set_transport(t)
        fit.fit("x" * 5000)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]["state"]["idea"]), 1500)
        self.assertEqual(len(calls[0]["questions"]), 27)


class Fallback(unittest.TestCase):
    def test_skipped_in_process(self):
        r = fit.fit("an idea")
        self.assertEqual(r["skipped"], "disabled")
        self.assertIn("fit: skipped (disabled)", fit.render(r))

    def test_cli_exit_0_and_3(self):
        p = run_cli("ig-reel/fit.py", ["an idea"])
        self.assertEqual(p.returncode, 0)
        self.assertTrue(p.stdout.startswith("engine: heuristic (disabled)"), p.stdout)
        self.assertIn("fit: skipped (disabled)", p.stdout)
        p = run_cli("ig-reel/fit.py", ["an idea", "--engine", "jev"])
        self.assertEqual(p.returncode, 3)

    def test_cli_json(self):
        p = run_cli("ig-reel/fit.py", ["an idea", "--json"])
        data = json.loads(p.stdout)
        self.assertEqual((data["engine"], data["skipped"]), ("heuristic", "disabled"))


if __name__ == "__main__":
    unittest.main()

"""evals/run.py: replay by default, keyed on model + state + questions."""
import importlib.util
import json
import os
import tempfile
import unittest

from tests.support import ROOT, load, write

jev = load("jev")
spec = importlib.util.spec_from_file_location("evals_run", os.path.join(ROOT, "evals", "run.py"))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)
BODY = {"model": "jev-1.13.0", "state": "s", "questions": {}}


class Key(unittest.TestCase):
    def test_key_is_stable_and_order_independent(self):
        a = {"model": "jev-1.13.0", "state": {"x": 1, "y": 2}, "questions": {"q": {"type": "noul"}}}
        b = {"questions": {"q": {"type": "noul"}}, "state": {"y": 2, "x": 1}, "model": "jev-1.13.0"}
        self.assertEqual(run.key(a), run.key(b))
        self.assertNotEqual(run.key(a), run.key(dict(a, model="jev-1.14.0")))


class Replay(unittest.TestCase):
    def test_missing_recording_is_listed_not_called(self):
        with tempfile.TemporaryDirectory() as d:
            t = run.ReplayTransport("formula", root=d)
            with self.assertRaises(jev.JevUnavailable):
                t(BODY, 1.0)
            self.assertEqual(t.missing, [run.key(BODY)])

    def test_replays_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "formula"))
            write(os.path.join(d, "formula", run.key(BODY) + ".json"),
                  json.dumps({"model": "jev-1.13.0", "answers": {}, "usage": {"input_tokens": 7}}))
            t = run.ReplayTransport("formula", root=d)
            self.assertEqual(t(BODY, 1.0)["model"], "jev-1.13.0")
            self.assertEqual(t.missing, [])

    def test_suites_parse_and_have_provenance(self):
        for name in run.SUITES:
            data = run.load_suite(name)
            self.assertTrue(data["items"], name)
            self.assertIn("smoke not benchmark", data["note"])
            for it in data["items"]:
                self.assertIn(it["provenance"], ("repo", "probe-synthetic", "human-real"), it["id"])


class ReplayRunFailsWhenEmpty(unittest.TestCase):
    def test_empty_recordings_fail_the_suite(self):
        with tempfile.TemporaryDirectory() as d:
            out = run.run_suite("caption", root=d)
        self.assertTrue(out["missing"])
        self.assertFalse(out["complete"])


if __name__ == "__main__":
    unittest.main()

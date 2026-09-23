"""Frozen outputs with Jev off. UPDATE_GOLDEN=1 rewrites them; read the diff before committing.

Each golden was captured after the engine line was added, so with --engine off
the only difference from v1.0 is that line plus the Phase 0 fixes.
"""
import os
import subprocess
import sys
import unittest

from tests.support import ROOT, clean_env, run_cli

GOLDEN = os.path.join(ROOT, "tests", "golden")
CASES = [
    ("hookscore_rank", "ig-reel/hookscore.py", ["tests/fixtures/hooks.txt"]),
    ("hookscore_one", "ig-reel/hookscore.py", ["--hook", "$18,000 is what one missing clause cost me."]),
    ("beats", "ig-reel/beats.py", ["tests/fixtures/script.txt", "--target", "30"]),
    ("detect", "ig-human/detect.py", ["tests/fixtures/draft.txt"]),
    ("swipe", "ig-viral/swipe.py", ["tests/fixtures/swipe.tsv", "--engine", "off"]),
    ("caption", "ig-caption/caption.py", ["tests/fixtures/caption.txt", "--engine", "off"]),
]


class Golden(unittest.TestCase):
    def check(self, name, script, args):
        p = run_cli(script, args)
        path = os.path.join(GOLDEN, name + ".txt")
        if os.environ.get("UPDATE_GOLDEN") == "1":
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(p.stdout)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(p.stdout, fh.read(), f"{name} changed; rerun with UPDATE_GOLDEN=1 "
                                                  "only if the change is intended")

    def test_goldens(self):
        for name, script, args in CASES:
            with self.subTest(name=name):
                self.check(name, script, args)


class Isolation(unittest.TestCase):
    def test_hookscore_never_loads_the_jev_client(self):
        code = ("import sys; sys.path.insert(0, 'skills/ig-reel'); import hookscore; "
                "hookscore.run('Nobody tells you this.'); print('jev' in sys.modules)")
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           cwd=ROOT, env=clean_env())
        self.assertEqual(p.stdout.strip(), "False", p.stderr)


if __name__ == "__main__":
    unittest.main()

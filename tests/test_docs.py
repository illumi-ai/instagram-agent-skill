"""Documentation and data that the scripts or the rules depend on."""
import json
import os
import re
import unittest

from tests.support import ROOT, SKILLS, load


def read(rel):
    return open(os.path.join(SKILLS, rel), encoding="utf-8").read()


class Phase0Docs(unittest.TestCase):
    """Phase 0 rows 8-11."""

    def test_rubric_matches_skill_on_link_menu(self):
        rubric = read("ig-profile/rubric.json")
        self.assertIn("two is already a menu", rubric)
        self.assertNotIn("more than two is a menu", rubric)
        self.assertIn("two is already a menu", read("ig-profile/SKILL.md"))

    def test_reel_example_invents_nothing(self):
        self.assertNotIn("I billed four hours a week", read("ig-reel/SKILL.md"))

    def test_reel_example_scores_are_real(self):
        hs = load("hookscore")
        block = read("ig-reel/SKILL.md").split("## Example", 1)[1]
        rows = re.findall(r"^\s+(\d+)\s+(STRONG|OK|WEAK)\s+#\d+\s+[^\"]+\"([^\"]+)\"", block, re.M)
        self.assertEqual(len(rows), 3)
        for score, verdict, hook in rows:
            _, overall, real_verdict, _ = hs.run(hook)
            self.assertEqual(int(score), round(overall), hook)
            self.assertEqual(verdict, real_verdict, hook)

    def test_dm_link_rule_is_scoped_to_warm_approach(self):
        text = read("ig-dm/SKILL.md")
        self.assertNotIn("- Never send the pitch in the same message as the compliment.", text)
        self.assertIn("The keyword delivery is the exception", text)
        self.assertIn("A trigger is", text)

    def test_comment_has_never_fabricate(self):
        text = read("ig-comment/SKILL.md")
        self.assertIn("Never fabricate", text)
        self.assertIn("Proof I can use", text)



class ProofGuardWired(unittest.TestCase):
    def test_ig_human_step_0_and_round_limit(self):
        human = read("ig-human/SKILL.md")
        self.assertIn("python3 proofcheck.py", human)
        self.assertIn("## Step 0: the proof guard", human)
        self.assertIn("two rounds", human)
        self.assertIn("IG_JEV=off", human)

    def test_reel_story_reply(self):
        reel = read("ig-reel/SKILL.md")
        self.assertIn("proofcheck.py", reel)
        self.assertRegex(reel, r"proof:\s+\d+ backed, \d+ \{\{…\}\}, \d+ to confirm · engine")
        for rel in ("ig-story/SKILL.md", "ig-reply/SKILL.md"):
            self.assertIn("../ig-human/proofcheck.py", read(rel), rel)

    def test_voice_template_asks_for_checkable_facts(self):
        tmpl = open(os.path.join(ROOT, "templates", "voice.md"), encoding="utf-8").read()
        self.assertIn("One checkable fact per bullet", tmpl)



class FormulaWired(unittest.TestCase):
    def test_viral_explains_statuses(self):
        viral = read("ig-viral/SKILL.md")
        self.assertIn("## Formula status", viral)
        self.assertIn("Count only AGREE and JEV", viral)
        self.assertIn("#13, #18 and #24", viral)
        self.assertIn("Never compare counts across engines", viral)

    def test_audit_uses_formula_py(self):
        self.assertIn("../ig-reel/formula.py", read("ig-audit/SKILL.md"))



class FitWired(unittest.TestCase):
    def test_reel_runs_fit_first(self):
        reel = read("ig-reel/SKILL.md")
        self.assertIn('python3 fit.py "', reel)
        self.assertIn("only from WRITABLE", reel)
        self.assertRegex(reel, r"fit:\s+\d+ writable, \d+ unlockable, \d+ vetoed")
        self.assertIn("fit: skipped", reel)


if __name__ == "__main__":
    unittest.main()

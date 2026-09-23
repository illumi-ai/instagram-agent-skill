"""Documentation and data that the scripts or the rules depend on."""
import json
import os
import re
import unittest

from tests.support import ROOT, SKILLS, load
from tests.support import read as read_path


def read(rel):
    return read_path(os.path.join(SKILLS, rel))


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
        for rel in ("ig-story/SKILL.md", "ig-reply/SKILL.md", "ig-repurpose/SKILL.md"):
            self.assertIn("../ig-human/proofcheck.py", read(rel), rel)
        self.assertIn("--source source.txt", read("ig-repurpose/SKILL.md"))

    def test_voice_template_asks_for_checkable_facts(self):
        tmpl = read_path(os.path.join(ROOT, "templates", "voice.md"))
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



class CaptionWired(unittest.TestCase):
    def test_caption_explains_the_engine(self):
        text = read("ig-caption/SKILL.md")
        self.assertIn("engine:", text)
        self.assertIn("never turns into FAIL", text)
        self.assertIn("borderline, decide out loud", text)
        self.assertIn("IG_JEV=off", text)



class ProjectDocs(unittest.TestCase):
    def test_readme_says_what_leaves_the_machine(self):
        readme = read_path(os.path.join(ROOT, "README.md"))
        self.assertIn("## What leaves your machine", readme)
        self.assertNotIn("nothing uploaded", readme.lower())
        self.assertIn("IG_JEV=off", readme)
        self.assertIn("measured on v1.0", readme)
        self.assertIn("provisional", readme)
        self.assertIn("evals/REPORT.md", readme)

    def test_manifest_version(self):
        manifest = json.loads(read_path(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
        self.assertEqual(manifest["version"], "1.1.0")
        self.assertEqual(manifest["author"]["name"], "Jake Schincariol")

    def test_claude_md_sections(self):
        claude = read_path(os.path.join(ROOT, "CLAUDE.md"))
        for n, heading in enumerate([
                "Visão geral e mapa das pastas", "Fluxo entre as skills e estado compartilhado",
                "Regras invioláveis", "Arquitetura Jev", "Contrato do motor e exit codes",
                "Cliente e portabilidade", "Regras de desenho de perguntas", "Privacidade",
                "Testes e evals", "Estilo", "Fluxo Git", "Registro das decisões Pro × Contra",
                "Checklist para adicionar um novo uso do Jev", "Próxima fase e critério de entrada"], 1):
            self.assertIn(f"## {n}. {heading}", claude)
        self.assertIn('MODEL = "jev-1.13.0"', claude)
        self.assertNotIn('"jev-latest"', claude)

    def test_model_is_pinned_everywhere(self):
        for rel in ("ig-human/jev.py", "ig-human/proofcheck.py", "ig-reel/formula.py",
                    "ig-reel/fit.py", "ig-caption/caption.py", "ig-viral/swipe.py"):
            self.assertNotIn('"jev-latest"', read(rel), rel)


if __name__ == "__main__":
    unittest.main()

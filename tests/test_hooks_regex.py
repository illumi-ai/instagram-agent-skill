"""Phase 0 row 7: every formula regex in hooks.json recognises its own example."""
import json
import os
import unittest

from tests.support import SKILLS, load

HOOKS = os.path.join(SKILLS, "ig-reel", "hooks.json")

# The probe stress set (probe-synthetic, smoke not benchmark). Gold is a formula
# name, several names joined by "|", or "none".
STRESS = [
    ("never in a million years did i think this reel would pay my rent", "none"),
    ("please tell me i'm not the only one who rewrites a caption nine times", "none"),
    ("3 years ago i was sleeping on my sister's couch with $400 to my name", "none"),
    ("everyone says you need to post every day. everyone is wrong.", "Contrarian Flip|Permission"),
    ("is it just me or does nobody talk about how lonely freelancing gets", "Nobody Tells You"),
    ("stop scrolling if you're a wedding photographer", "The Callout"),
    ("if you've been posting for six months and still have under 1,000 followers, "
     "the next 30 seconds are for you", "If This, Then Watch"),
    ("hey guys welcome back to my channel", "none"),
    ("in this video i'm going to show you my morning routine", "none"),
    ("yeah so what we found was that most of the people who came in were already", "none"),
    ("you're pricing your services wrong and honestly it's not your fault", "Wrong Way, Right Way"),
    ("i worked at a big four accounting firm for eight years and this is what they don't tell "
     "clients", "Insider Leak"),
    ("five apps i use every single day to run my business, and the last one is the one nobody "
     "uses", "Numbered With A Favourite"),
    ("i don't have time to post every day. okay, then post twice a week and do this instead",
     "The Objection"),
    ("real estate agents, this is the listing video you've been avoiding", "The Callout"),
    ("the tax deadline is april 15th, do this before then or you'll pay a penalty", "The Deadline"),
    ("what's the best camera for beginners? i get asked this every week", "The Verbatim Question"),
    ("this $9 app replaced my $300 a month virtual assistant", "The Replacement"),
    ("nobody tells you that the first client is the hardest one to find", "Nobody Tells You"),
    ("we tested carousels against reels for 90 days, and it wasn't close", "Head To Head|The Receipt"),
    ("the fastest way to lose a client is to answer every email in five minutes", "The Superlative"),
    ("my biggest mistake as a new photographer cost me $6,000", "Cost Confession"),
    ("watch what happens when i put my competitor's bio into chatgpt", "Cold Open Demo"),
    ("so i just got banned from instagram for 30 days", "none"),
    ("if i had to start a coaching business from zero tomorrow, here's exactly what i'd do", "none"),
    ("proposals used to eat my whole friday. now they take me twenty minutes", "Time Collapse"),
]
# The v1.0 regex got 10 of these 26 right. The fixes must not go below that.
BASELINE_STRESS_CORRECT = 10
NEGATIVES = ["Don't steal my content, I will report you.",
             "Nobody tells me anything in this house lol"]


def correct(name, gold):
    return (name == "unclassified" and gold == "none") or name in gold.split("|")


class HooksRegex(unittest.TestCase):
    def setUp(self):
        self.swipe = load("swipe")
        self.formulas = self.swipe.load_formulas(HOOKS)
        with open(HOOKS, encoding="utf-8") as fh:
            self.data = json.load(fh)

    def test_every_example_classifies_as_itself(self):
        for h in self.data["hooks"]:
            fid, _ = self.swipe.classify(h["example"], self.formulas)
            self.assertEqual(fid, h["id"], h["example"])

    def test_negatives_stay_unclassified(self):
        for text in NEGATIVES:
            self.assertEqual(self.swipe.classify(text, self.formulas), (None, "unclassified"), text)

    def test_stress_set_does_not_get_worse(self):
        hits = sum(correct(self.swipe.classify(h, self.formulas)[1], g) for h, g in STRESS)
        self.assertGreaterEqual(hits, BASELINE_STRESS_CORRECT)

    def test_version_bumped(self):
        self.assertEqual(self.data["version"], "1.1")


if __name__ == "__main__":
    unittest.main()

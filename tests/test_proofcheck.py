"""proofcheck.py: the fabrication guard. L0 is code only; L1 asks Jev."""
import os
import tempfile
import unittest
from unittest import mock

from tests.support import load, run_cli

pc = load("proofcheck")
jev = load("jev")

VOICE = """## Who I am

- **Name:** Maya Ortiz
- **Handle:** @maya.builds

## Off limits

- **Clients, numbers or names I cannot say publicly:** Acme Corp paid $90,000

## Proof I can use

- We cut proposal time from 5 hours to 20 minutes with one template.
- I lost $18,000 in 2023 because a client contract had no payment-on-delivery clause.
- One carousel about pricing pages booked 14 discovery calls in March.
"""


class Evidence(unittest.TestCase):
    def test_only_proof_identity_said_source(self):
        items, allowed = pc.load_evidence(VOICE, "we charge $6,500 per project", "")
        texts = " ".join(i.text for i in items)
        self.assertIn("5 hours", texts)
        self.assertIn("$6,500", texts)
        self.assertNotIn("Acme", texts)
        self.assertIn("maya", allowed)
        self.assertIn("@maya.builds", allowed)
        self.assertEqual([i.id for i in items],
                         ["identity", "proof1", "proof2", "proof3", "said1"])

    def test_empty_template_gives_no_evidence(self):
        items, allowed = pc.load_evidence("## Who I am\n\n- **Name:**\n\n## Proof I can use\n\n-\n-\n", "", "")
        self.assertEqual(items, [])

    def test_source_lines_are_items(self):
        items, _ = pc.load_evidence("", "", "First line of the talk.\n\nSecond line, 40 clients.")
        self.assertEqual([i.id for i in items], ["source1", "source2"])


class Numbers(unittest.TestCase):
    def v(self, text):
        return [(n.value, n.unit) for n in pc.numbers(text)]

    def test_forms(self):
        self.assertEqual(self.v("$18,000"), [(18000, "$")])
        self.assertEqual(self.v("$18k"), [(18000, "$")])
        self.assertEqual(self.v("45%"), [(45, "%")])
        self.assertEqual(self.v("five hours"), [(300, "min")])
        self.assertEqual(self.v("20 minutes"), [(20, "min")])
        self.assertEqual(self.v("15 times less"), [(15, "x")])
        self.assertEqual(self.v("doubled"), [(2, "x")])
        self.assertEqual(self.v("twenty grand"), [(20000, "$")])
        self.assertEqual(self.v("in 2023"), [(2023, "year")])
        self.assertEqual(self.v("one template, the first time, a single DM"), [])
        self.assertEqual(self.v("$2M"), [(2_000_000, "$")])
        self.assertEqual(self.v("done in 10m"), [(10, "")])
        self.assertEqual(self.v("2000 followers"), [(2000, "")])
        self.assertEqual(self.v("It cost $18,000, then more."), [(18000, "$")])

    def test_spans_cover_the_unit(self):
        n = pc.numbers("I billed four hours a week.")[0]
        self.assertEqual(n.text, "four hours")

    def test_direct_and_derived_binding(self):
        item = pc.numbers("We cut proposal time from 5 hours to 20 minutes with one template.")
        self.assertEqual(pc.bind_number(pc.numbers("five hours")[0], item), "direct")
        self.assertEqual(pc.bind_number(pc.numbers("300 minutes")[0], item), "direct")
        self.assertEqual(pc.bind_number(pc.numbers("15 times")[0], item), "derived")
        self.assertEqual(pc.bind_number(pc.numbers("280 minutes")[0], item), "derived")
        self.assertIsNone(pc.bind_number(pc.numbers("doubled")[0], item))
        self.assertIsNone(pc.bind_number(pc.numbers("almost $20,000")[0],
                                         pc.numbers("I lost $18,000 in 2023")))
        self.assertEqual(pc.bind_number(pc.numbers("125%")[0], pc.numbers("from 20% to 45%")),
                         "derived")

    def test_numbers_must_bind_to_one_item(self):
        items, _ = pc.load_evidence(VOICE, "", "")
        b = pc.bindings(pc.numbers("14 calls in 5 hours"), items)
        self.assertEqual(b["unbound"], [])
        self.assertEqual(b["proof3"]["direct"], [0])
        self.assertEqual(b["proof1"]["direct"], [1])


class Claims(unittest.TestCase):
    def test_first_person_and_clients(self):
        self.assertTrue(pc.is_l0_claim("I lost $18,000 on one contract."))
        self.assertTrue(pc.is_l0_claim("My client doubled her bookings."))
        self.assertTrue(pc.is_l0_claim("Three clients signed the same day."))
        self.assertFalse(pc.is_l0_claim("Keep your hook under three seconds."))
        self.assertFalse(pc.is_l0_claim("Want a teardown of your pricing page?"))
        self.assertFalse(pc.is_l0_claim("Comment TEMPLATE and I'll send it to you."))
        self.assertFalse(pc.is_l0_claim("I want to offer you a call."))

    def test_split_joins_fragments_and_skips_placeholders(self):
        draft = ("Proposals used to take me five hours. Twenty minutes now.\n"
                 "It cost me {{your number}}.\nFive hours to twenty minutes. Same template.")
        s = pc.split_sentences(draft)
        self.assertEqual([x["text"] for x in s],
                         ["Proposals used to take me five hours. Twenty minutes now.",
                          "Five hours to twenty minutes. Same template."])
        self.assertEqual(draft[s[1]["start"]:s[1]["end"]], s[1]["text"])


class L0Report(unittest.TestCase):
    def setUp(self):
        self.items, self.allowed = pc.load_evidence(VOICE, "", "")

    def test_unbound_number_gets_placeholder(self):
        draft = "I billed four hours a week for formatting. For two years."
        rep = pc.l0(draft, self.items, self.allowed)
        self.assertEqual({f["type"] for f in rep[0]["flags"]}, {"number"})
        self.assertEqual(pc.apply_placeholders(draft, rep),
                         "I billed {{your number}} a week for formatting. For {{your number}}.")

    def test_unknown_name_and_handle(self):
        rep = pc.l0("My client Dana doubled her bookings after I met @sam.co.", self.items, self.allowed)
        self.assertEqual(sorted(f["type"] for f in rep[0]["flags"]), ["handle", "name", "number"])
        fixed = pc.apply_placeholders("My client Dana doubled her bookings after I met @sam.co.", rep)
        self.assertIn("{{client name}}", fixed)

    def test_known_name_months_platforms_pass(self):
        rep = pc.l0("One carousel on Instagram booked me 14 discovery calls in March.",
                    self.items, self.allowed)
        self.assertEqual(rep[0]["flags"], [])
        rep = pc.l0("Maya here, and I lost $18,000 in 2023.", self.items, self.allowed)
        self.assertEqual(rep[0]["flags"], [])

    def test_non_claims_are_not_checked(self):
        rep = pc.l0("Keep your hook under three seconds, like Dana does.", self.items, self.allowed)
        self.assertFalse(rep[0]["claim"])
        self.assertEqual(rep[0]["flags"], [])

    def test_unverified_offline_rule(self):
        rep = pc.l0("I have been following your work since the very first reel.", self.items, self.allowed)
        self.assertTrue(rep[0]["unverified"])
        rep = pc.l0("We cut proposal time with one template.", self.items, self.allowed)
        self.assertFalse(rep[0]["unverified"])

    def test_shortlist_ranks_by_overlap_and_numbers(self):
        short = pc.shortlist("That carousel booked me 14 calls.", self.items)
        self.assertEqual(short[0].id, "proof3")
        self.assertLessEqual(len(short), pc.SHORTLIST)


if __name__ == "__main__":
    unittest.main()

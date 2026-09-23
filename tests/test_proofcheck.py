"""proofcheck.py: the fabrication guard. L0 is code only; L1 asks Jev."""
import os
import tempfile
import unittest
from unittest import mock

from tests.support import load, read, run_cli, write

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



# --------------------------------------------------------------------------
# L1: Jev through a fake transport


def fake(answer_fn):
    """Transport that answers every question with answer_fn(qid, question)."""
    def transport(body, timeout):
        return {"model": jev.MODEL, "usage": {"input_tokens": 10, "output_tokens": 1},
                "answers": {q: answer_fn(q, spec) for q, spec in body["questions"].items()}}
    return transport


KINDS = ["own_record", "client_result", "outside_fact", "advice_or_opinion", "hypothetical",
         "ask_or_other"]


def choice(pick, opts=KINDS):
    rest = 0.1 / (len(opts) - 1)
    return {"type": "choice", "choice": pick, "confidence": 0.9,
            "probabilities": {o: (0.9 if o == pick else rest) for o in opts}}


class JevCase(unittest.TestCase):
    def setUp(self):
        self.items, self.allowed = pc.load_evidence(VOICE, "", "")
        self.env = mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": "k" * 20})
        self.env.start()
        os.environ.pop("IG_JEV", None)
        self.old = jev.set_transport(jev.TRANSPORT)

    def tearDown(self):
        jev.set_transport(self.old)
        self.env.stop()


class Questions(JevCase):
    def test_wording_and_state(self):
        sents = pc.l0("I lost $18,000 on one contract.\nKeep your hook short.", self.items, self.allowed)
        q = pc.build_questions(sents, self.items)
        self.assertEqual(q["kind_1"]["type"], "choice")
        self.assertEqual(set(q["kind_1"]["criteria"]), set(KINDS))
        self.assertEqual(q["kind_1"]["instructions"]["sentence"], "I lost $18,000 on one contract.")
        same = [k for k in q if k.startswith("same_1_")]
        self.assertEqual(len(same), min(pc.SHORTLIST, len(self.items)))
        self.assertEqual(set(q["held_1_2"]["criteria"]), {"true", "false"})
        self.assertIn("proof_item", q["same_1_2"]["instructions"])

    def test_no_evidence_no_pairs(self):
        sents = pc.l0("I lost $18,000 on one contract.", [], set())
        self.assertEqual(list(pc.build_questions(sents, [])), ["kind_1"])


class L1Policy(JevCase):
    def run_with(self, draft, kind, same, held):
        def ans(q, spec):
            if q.startswith("kind_"):
                return choice(kind)
            fn = same if q.startswith("same_") else held
            return {"type": "noul", "noul": fn(spec)}
        jev.set_transport(fake(ans))
        return pc.check(draft, self.items, self.allowed)

    @staticmethod
    def proof_is(needle, yes=0.9, no=0.05):
        return lambda spec: yes if needle in spec["instructions"]["proof_item"] else no

    def test_backed(self):
        r = self.run_with("Proposals used to take me five hours. Twenty minutes now.", "own_record",
                          self.proof_is("5 hours"), self.proof_is("5 hours"))
        s = r["sentences"][0]
        self.assertEqual((s["status"], s["proof"]), ("BACKED", "proof1"))
        self.assertEqual((r["engine"], r["exit"]), ("jev", 0))

    def test_unbacked(self):
        r = self.run_with("I billed four hours a week for formatting. For two years.", "own_record",
                          lambda s: 0.05, lambda s: 0.05)
        self.assertEqual(r["sentences"][0]["status"], "UNBACKED")
        self.assertEqual(r["exit"], 1)

    def test_mismatch(self):
        r = self.run_with("That carousel on pricing pages booked me 40 discovery calls.", "own_record",
                          self.proof_is("carousel"), lambda s: 0.2)
        s = r["sentences"][0]
        self.assertEqual((s["status"], s["proof"]), ("MISMATCH", "proof3"))
        self.assertTrue(any("your proof says" in n for n in s["notes"]))

    def test_embellished(self):
        r = self.run_with("My pricing carousel booked 14 calls in a single week.", "own_record",
                          self.proof_is("carousel"), lambda s: 0.1)
        self.assertEqual(r["sentences"][0]["status"], "EMBELLISHED")
        self.assertEqual(r["exit"], 1)

    def test_derived(self):
        r = self.run_with("Proposals take me 15 times less time now.", "own_record",
                          self.proof_is("5 hours"), lambda s: 0.2)
        self.assertEqual(r["sentences"][0]["status"], "DERIVED")
        self.assertEqual(r["exit"], 0)

    def test_jev_widens_claims_never_narrows(self):
        r = self.run_with("Loved your reel on retainer pricing last week.", "own_record",
                          lambda s: 0.05, lambda s: 0.05)
        self.assertTrue(r["sentences"][0]["claim"])
        self.assertEqual(r["sentences"][0]["status"], "UNBACKED")
        r = self.run_with("I billed four hours a week.", "advice_or_opinion", lambda s: 0.9, lambda s: 0.9)
        s = r["sentences"][0]
        self.assertTrue(s["claim"])
        self.assertTrue(any(f["type"] == "number" for f in s["flags"]))
        self.assertEqual(r["exit"], 1)

    def test_jev_added_claim_gets_code_checks(self):
        r = self.run_with("Last week Dana from the Austin expo sent over 40 referrals.", "client_result",
                          lambda s: 0.05, lambda s: 0.05)
        kinds = sorted(f["type"] for f in r["sentences"][0]["flags"])
        self.assertEqual(kinds, ["name", "name", "number"])

    def test_outside_fact_with_number_is_a_note(self):
        r = self.run_with("Instagram caps hashtags at five per post.", "outside_fact",
                          lambda s: 0.05, lambda s: 0.05)
        s = r["sentences"][0]
        self.assertFalse(s["claim"])
        self.assertIn("statistic: add a source or cut", s["notes"])
        self.assertEqual(r["exit"], 0)

    def test_no_evidence_means_no_pairs_and_unbacked(self):
        seen = []

        def ans(q, spec):
            seen.append(q)
            return choice("own_record")
        jev.set_transport(fake(ans))
        r = pc.check("I made $50,000 last month.", [], set())
        self.assertEqual(r["sentences"][0]["status"], "UNBACKED")
        self.assertEqual([q for q in seen if not q.startswith("kind_")], [])

    def test_summary_line(self):
        r = self.run_with("I billed four hours a week for formatting. For two years.", "own_record",
                          lambda s: 0.05, lambda s: 0.05)
        text = pc.render(r)
        self.assertTrue(text.startswith("engine: jev-1.13.0 (1 req"))
        self.assertIn("proof: 0 backed, 2 {{…}}, 1 to confirm · engine jev-1.13.0", text)

    def test_jev_failure_falls_back_whole_report(self):
        def boom(body, timeout):
            raise jev.JevUnavailable("rate-limited", "HTTP 429")
        jev.set_transport(boom)
        r = pc.check("I billed four hours a week.", self.items, self.allowed)
        self.assertEqual((r["engine"], r["engine_reason"]), ("heuristic", "rate-limited"))
        self.assertEqual(r["sentences"][0]["status"], "FLAGGED")


class Fallback(unittest.TestCase):
    def test_heuristic_line_and_unverified(self):
        items, allowed = pc.load_evidence(VOICE, "", "")
        with mock.patch.dict(os.environ, {"TYPESAFE_API_KEY": ""}):
            os.environ.pop("IG_JEV", None)
            r = pc.check("I have been following your work since the very first reel.", items, allowed)
        self.assertEqual((r["engine"], r["engine_reason"]), ("heuristic", "no-key"))
        self.assertEqual(r["sentences"][0]["status"], "UNVERIFIED")
        self.assertEqual(r["exit"], 1)
        self.assertTrue(pc.render(r).startswith("engine: heuristic (no-key)"))

    def test_checked_when_numbers_found(self):
        items, allowed = pc.load_evidence(VOICE, "", "")
        r = pc.check("One carousel booked me 14 discovery calls in March.", items, allowed)
        self.assertEqual(r["sentences"][0]["status"], "CHECKED")
        self.assertEqual(r["exit"], 0)


class CLI(unittest.TestCase):
    def test_cli_off_writes_placeholders_and_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            draft, voice, out = (os.path.join(d, n) for n in ("d.txt", "v.md", "o.txt"))
            write(draft, "I billed four hours a week for formatting.\n")
            write(voice, VOICE)
            p = run_cli("ig-human/proofcheck.py", [draft, "--voice", voice, "-o", out])
            self.assertEqual(p.returncode, 1, p.stderr)
            self.assertTrue(p.stdout.startswith("engine: heuristic (disabled)"), p.stdout)
            self.assertEqual(read(out), "I billed {{your number}} a week for formatting.\n")

    def test_json_output(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            draft, voice = os.path.join(d, "d.txt"), os.path.join(d, "v.md")
            write(draft, "We cut proposal time from 5 hours to 20 minutes.\n")
            write(voice, VOICE)
            p = run_cli("ig-human/proofcheck.py", [draft, "--voice", voice, "--json"])
            data = json.loads(p.stdout)
            self.assertEqual(data["engine"], "heuristic")
            self.assertEqual(data["sentences"][0]["status"], "CHECKED")
            self.assertEqual(p.returncode, 0)

    def test_engine_jev_without_key_exits_3(self):
        with tempfile.TemporaryDirectory() as d:
            draft = os.path.join(d, "d.txt")
            write(draft, "Keep your hook short.\n")
            p = run_cli("ig-human/proofcheck.py", [draft, "--voice", os.path.join(d, "none.md"),
                                                   "--engine", "jev"])
            self.assertEqual(p.returncode, 3, p.stdout + p.stderr)

    def test_empty_draft_is_usage_error(self):
        with tempfile.TemporaryDirectory() as d:
            draft = os.path.join(d, "d.txt")
            write(draft, "\n\n")
            p = run_cli("ig-human/proofcheck.py", [draft])
            self.assertEqual(p.returncode, 2)



class ReviewRegressions(unittest.TestCase):
    """Cases found in code review: each one used to pass the guard or corrupt the draft."""

    def setUp(self):
        self.items, self.allowed = pc.load_evidence(
            "## Proof I can use\n\n- Made $5k from one reel in 2024\n"
            "- Started coaching founders in 2019\n", "", "")

    def status(self, draft):
        return pc.check(draft, self.items, self.allowed, engine="off")

    def test_short_follow_up_does_not_hide_the_claim(self):
        for draft in ["I made $50k from one reel. Crazy, right?",
                      "I made $50k from one reel. I'll explain.",
                      "My client Sarah made $50k from one reel. How?",
                      "I made $50k from one reel and I'll show you how."]:
            r = self.status(draft)
            self.assertEqual(r["exit"], 1, draft)
            self.assertTrue(r["sentences"][0]["claim"], draft)

    def test_questions_and_promises_without_numbers_are_not_claims(self):
        self.assertFalse(pc.is_l0_claim("Did I mention how much I love this?"))
        self.assertFalse(pc.is_l0_claim("I'll send it to you tomorrow."))
        self.assertTrue(pc.is_l0_claim("Want to know how I made $50k?"))

    def test_years_match_exactly(self):
        for draft in ["I have been coaching founders since 2005.",
                      "In 2010 I quit my job to coach founders."]:
            self.assertEqual(self.status(draft)["exit"], 1, draft)
        self.assertEqual(self.status("I have been coaching founders since 2019.")["exit"], 0)

    def test_bullets_arrows_and_emoji_are_not_names(self):
        for line in ["\u2192 Booked 12 calls for my clients this week",
                     "- Grew my list to 4,000 subscribers",
                     "\U0001F525 Tripled my revenue in 3 months",
                     "In May I signed 3 new clients"]:
            sent = pc.split_sentences(line)[0]
            self.assertEqual(pc.names(sent["text"]), [], line)

    def test_names_that_used_to_slip_through(self):
        self.assertEqual([n[0] for n in pc.names("My client Jo doubled her rates.")], ["Jo"])
        self.assertEqual([n[0] for n in pc.names("Coca-Cola: Nike paid me for one reel.")],
                         ["Cola", "Nike"])
        self.assertEqual([n[0] for n in pc.names("I worked with Dr. Smith on it.")], ["Smith"])

    def test_set_phrases_and_emails_are_not_flagged(self):
        self.assertEqual(pc.numbers("I quit my 9-to-5 and run 1:1 calls 24/7 at 10:30am."), [])
        self.assertEqual(pc.numbers("Always double-check the invoice."), [])
        self.assertEqual(pc.handles("Email me at hi@studio.com"), [])
        self.assertEqual([(n.value, n.unit) for n in pc.numbers("I raised $5m.")],
                         [(5_000_000, "$")])


class DerivedOnlyWhenNothingElseIsAdded(JevCase):
    def test_extra_facts_make_it_embellished(self):
        items, allowed = pc.load_evidence(
            "## Proof I can use\n\n- Went from 10 clients to 20 clients in 2023\n", "", "")

        def ans(q, spec):
            if q.startswith("kind_"):
                return choice("own_record")
            return {"type": "noul", "noul": 0.95 if q.startswith("same_") else 0.05}
        jev.set_transport(fake(ans))
        r = pc.check("I doubled my client list after one viral reel got me featured on a podcast.",
                     items, allowed)
        self.assertEqual(r["sentences"][0]["status"], "EMBELLISHED")
        r = pc.check("I doubled my clients.", items, allowed)
        self.assertEqual(r["sentences"][0]["status"], "DERIVED")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
evals/run.py - measure the four Jev-backed decisions on their label suites.

Replay is the default: every request is looked up in evals/recorded/<suite>/
by sha256(model + state + questions). If a recording is missing, the suite
fails and lists what is missing; nothing touches the network. --live sends
the requests (TYPESAFE_API_KEY required) and prints the cost; --live --record
also writes the responses, which is how the recordings are refreshed after a
question's wording changes.

The suites are small and were labelled by the agents that built them. Read
the numbers as a smoke test, not a benchmark.

Usage
  python3 evals/run.py --suite all                  # replay
  python3 evals/run.py --suite formula --live       # live, nothing written
  python3 evals/run.py --suite all --live --record --report
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUITES_DIR = os.path.join(HERE, "suites")
RECORDED = os.path.join(HERE, "recorded")
REPORT = os.path.join(HERE, "REPORT.md")
SUITES = ["formula", "proof", "fit", "caption"]
USD_PER_MTOK = 0.042          # TypeSafe input price for jev-1.13.0

for folder in ("ig-human", "ig-reel", "ig-caption"):
    path = os.path.join(ROOT, "skills", folder)
    if path not in sys.path:
        sys.path.insert(0, path)

import jev  # noqa: E402


def key(body):
    raw = (body["model"] + json.dumps(body["state"], sort_keys=True, ensure_ascii=False)
           + json.dumps(body["questions"], sort_keys=True, ensure_ascii=False))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MissingRecording(jev.JevUnavailable):
    def __init__(self, k):
        super().__init__("bad-response", f"no recording {k[:12]}")


class ReplayTransport:
    """jev transport that answers from recordings, or live when asked to."""

    def __init__(self, suite, root=RECORDED, record=False, live=False):
        self.dir = os.path.join(root, suite)
        self.record, self.live = record, live
        self.missing, self.input_tokens, self.requests = [], 0, 0
        self.lock = threading.Lock()

    def __call__(self, body, timeout):
        k = key(body)
        path = os.path.join(self.dir, k + ".json")
        if not self.live:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    resp = json.load(fh)
                with self.lock:
                    self.requests += 1
                    self.input_tokens += int((resp.get("usage") or {}).get("input_tokens", 0))
                return resp
            with self.lock:
                self.missing.append(k)
            raise MissingRecording(k)
        resp = jev._http_post(body, timeout)
        with self.lock:
            self.requests += 1
            self.input_tokens += int((resp.get("usage") or {}).get("input_tokens", 0))
            if self.record:
                os.makedirs(self.dir, exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(resp, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        return resp


def load_suite(name):
    with open(os.path.join(SUITES_DIR, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def _rate(num, den):
    return round(num / den, 3) if den else None


# --------------------------------------------------------------------------
# suites


def suite_formula(data, engines):
    import formula
    canon = [i for i in data["items"] if i["set"] == "canonical"]
    rest = [i for i in data["items"] if i["set"] != "canonical"]
    r1 = formula.classify_hooks([i["hook"] for i in canon], engine="jev",
                                selftest_ids=[i["selftest_id"] for i in canon])
    r2 = formula.classify_hooks([i["hook"] for i in rest], engine="jev")
    engines += [r1["engine"], r2["engine"]]
    by = {it["hook"]: it for it in r1["items"] + r2["items"]}

    def jev_right(i):
        it = by[i["hook"]]
        return (it["jev_name"] or "none") in i["gold"] or (it["jev_name"] == "none" and i["gold"] == ["none"])

    def regex_right(i):
        name = by[i["hook"]]["regex_name"]
        return (name == "unclassified" and i["gold"] == ["none"]) or name in i["gold"]

    stress = [i for i in rest if i["set"] == "stress"]
    traps = [i for i in rest if i["set"] == "trap"]
    counted = [i for i in stress if by[i["hook"]]["counted"]]
    wrong = [i["id"] for i in counted if by[i["hook"]]["formula"] not in i["gold"]]
    named_gold = [i for i in stress if i["gold"] != ["none"]]
    metrics = {
        "canonical_jev_right": sum(jev_right(i) for i in canon),
        "canonical_n": len(canon),
        "canonical_counted_wrong": sum(1 for i in canon if by[i["hook"]]["counted"]
                                       and by[i["hook"]]["formula"] not in i["gold"]),
        "stress_n": len(stress),
        "stress_counted": len(counted),
        "stress_counted_wrong": len(wrong),
        "stress_counted_wrong_ids": wrong,
        "stress_named_coverage": _rate(sum(1 for i in named_gold if by[i["hook"]]["counted"]
                                           and by[i["hook"]]["formula"] in i["gold"]), len(named_gold)),
        "stress_jev_pick_accuracy": _rate(sum(jev_right(i) for i in stress), len(stress)),
        "stress_regex_accuracy": _rate(sum(regex_right(i) for i in stress), len(stress)),
        "traps_counted": [i["id"] for i in traps if by[i["hook"]]["counted"]],
        "trap_statuses": {i["id"]: by[i["hook"]]["status"] for i in traps},
        "tracked": {i["id"]: by[i["hook"]]["status"] + (f" {by[i['hook']]['jev_name']}"
                                                        if by[i["hook"]]["jev_name"] else "")
                    for i in rest if i["set"] == "track"},
    }
    g = data["gates"]
    gates = {
        f"canonical Jev picks >= {g['canonical_jev_right_min']}/26 (leave-one-out)":
            metrics["canonical_jev_right"] >= g["canonical_jev_right_min"],
        "0 wrong ids at a counted status on the stress set":
            metrics["stress_counted_wrong"] <= g["stress_counted_wrong_max"],
        "no trap counted": len(metrics["traps_counted"]) <= g["traps_counted_max"],
    }
    return metrics, gates


def suite_proof(data, engines):
    import proofcheck
    rows = []
    for it in data["items"]:
        voice = "## Proof I can use\n\n" + "\n".join("- " + p for p in it["proof"]) + "\n"
        items, allowed = proofcheck.load_evidence(voice, "\n".join(it["said"]), "")
        rj = proofcheck.check(it["sentence"], items, allowed, engine="jev")
        r0 = proofcheck.check(it["sentence"], items, allowed, engine="off")
        engines.append(rj["engine"])
        rows.append((it, rj["exit"] == 1, r0["exit"] == 1,
                     any("statistic" in n for s in rj["sentences"] for n in s["notes"])))
    flags = [r for r in rows if r[0]["label"] == "flag"]
    clean = [r for r in rows if r[0]["label"] != "flag"]
    metrics = {
        "n": len(rows), "flag_n": len(flags), "ok_n": len(clean),
        "recall_l0": _rate(sum(r[2] for r in flags), len(flags)),
        "recall_l0_l1": _rate(sum(r[1] for r in flags), len(flags)),
        "false_positive_l0": _rate(sum(r[2] for r in clean), len(clean)),
        "false_positive_l0_l1": _rate(sum(r[1] for r in clean), len(clean)),
        "missed_by_l0_l1": [r[0]["id"] for r in flags if not r[1]],
        "false_positives_l0_l1": [r[0]["id"] for r in clean if r[1]],
        "notes_on_outside_facts": [r[0]["id"] for r in rows if r[0]["label"] == "note" and r[3]],
    }
    gates = {
        "recall of L0+L1 above L0": (metrics["recall_l0_l1"] or 0) > (metrics["recall_l0"] or 0),
        f"false positives <= {data['gates']['false_positive_max']}":
            (metrics["false_positive_l0_l1"] or 0) <= data["gates"]["false_positive_max"],
    }
    return metrics, gates


def suite_fit(data, engines):
    import fit
    veto_hard = veto_soft = veto_n = write_hits = write_n = false_veto = multi_right = 0
    misses = []
    for it in data["items"]:
        r = fit.fit(it["idea"], engine="jev")
        engines.append(r["engine"])
        where = {row["id"]: k for k in ("writable", "unlockable", "vetoed") for row in r[k]}
        for fid in it["must_veto"]:
            veto_n += 1
            veto_hard += where.get(fid) == "vetoed"
            veto_soft += where.get(fid) != "writable"
            if where.get(fid) == "writable":
                misses.append(f"{it['id']}:#{fid} writable")
        for fid in it["must_write"]:
            write_n += 1
            write_hits += where.get(fid) == "writable"
            false_veto += where.get(fid) == "vetoed"
            if where.get(fid) != "writable":
                misses.append(f"{it['id']}:#{fid} {where.get(fid)}")
        multi_right += bool(r["multi"]) == it["multi"]
    metrics = {
        "ideas": len(data["items"]),
        "veto_recall": _rate(veto_hard, veto_n),
        "not_writable_rate_on_must_veto": _rate(veto_soft, veto_n),
        "must_write_writable": _rate(write_hits, write_n),
        "false_veto_rate": _rate(false_veto, write_n),
        "multi_idea_accuracy": _rate(multi_right, len(data["items"])),
        "misses": misses,
    }
    return metrics, {"report only": True}


def suite_caption(data, engines):
    import caption
    rows = []
    for it in data["items"]:
        a = caption.analyse(it["caption"], engine="jev")
        engines.append(a["engine"])
        jtype = a["asks"][0] if a["asks"] else "no_ask"
        rtype = (caption.REGEX_TYPES.get(a["heuristic_asks"][0], "?")
                 if a["heuristic_asks"] else "no_ask")
        rows.append((it, jtype, rtype, len(a["asks"]) > 1))
    asks = [r for r in rows if r[0]["gold"] != "no_ask"]
    metrics = {
        "n": len(rows),
        "ask_accuracy_jev": _rate(sum((r[1] != "no_ask") == (r[0]["gold"] != "no_ask") for r in rows), len(rows)),
        "ask_accuracy_regex": _rate(sum((r[2] != "no_ask") == (r[0]["gold"] != "no_ask") for r in rows), len(rows)),
        "type_accuracy_jev": _rate(sum(r[1] == r[0]["gold"] for r in asks), len(asks)),
        "type_accuracy_regex": _rate(sum(r[2] == r[0]["gold"] for r in asks), len(asks)),
        "jev_wrong": [f"{r[0]['id']}: gold {r[0]['gold']}, jev {r[1]}" for r in rows if r[1] != r[0]["gold"]],
    }
    return metrics, {"report only": True}


RUNNERS = {"formula": suite_formula, "proof": suite_proof, "fit": suite_fit, "caption": suite_caption}


def run_suite(name, root=RECORDED, live=False, record=False):
    data = load_suite(name)
    transport = ReplayTransport(name, root=root, record=record, live=live)
    old = jev.set_transport(transport)
    engines = []
    try:
        metrics, gates = RUNNERS[name](data, engines)
    finally:
        jev.set_transport(old)
    complete = not transport.missing and all(e == "jev" for e in engines)
    from collections import Counter
    return {"suite": name, "metrics": metrics, "gates": gates, "missing": transport.missing,
            "complete": complete, "live": live, "requests": transport.requests,
            "input_tokens": transport.input_tokens,
            "cost_usd": round(transport.input_tokens * USD_PER_MTOK / 1e6, 5),
            "provenance": dict(Counter(i["provenance"] for i in data["items"])),
            "notes": [n for n in (data.get("labels"), data.get("caveat")) if n]}


def render_report(results, when):
    lines = ["# Eval report", "",
             f"- model: `{jev.MODEL}`",
             f"- date: {when}",
             "- command: `python3 evals/run.py --suite all --live --record --report`",
             "- replay: `python3 evals/run.py --suite all` reproduces these numbers from "
             "`evals/recorded/` without the network",
             "",
             "**Smoke test, not a benchmark.** Every suite is small and was written and labelled by "
             "the agents that built these features (`provenance` in each suite file). The "
             "thresholds in the scripts are provisional until real, human-labelled data exists.",
             "",
             "What these numbers do not show: accuracy on real creators' drafts, hooks or captions; "
             "stability across runs (the probes measured drift of up to 0.14 on a 0-2 scale); or any "
             "effect on views. \"On by default\" below applies the spec's rule (a feature whose gate "
             "fails ships switched off). It is not a claim that the feature is right on your data.",
             ""]
    for r in results:
        passed = all(r["gates"].values())
        lines += [f"## {r['suite']}", "",
                  f"- items by provenance: {', '.join(f'{k} {v}' for k, v in r['provenance'].items())}",
                  f"- requests: {r['requests']}, input tokens: {r['input_tokens']:,}, cost at "
                  f"recording: ${r['cost_usd']:.4f}",
                  f"- complete (every answer from Jev): {'yes' if r['complete'] else 'NO'}"]
        lines += [f"- note: {n}" for n in r["notes"]]
        lines += ["", "| metric | value |", "| --- | --- |"]
        for k, v in r["metrics"].items():
            lines.append(f"| {k} | {v if not isinstance(v, (list, dict)) or v else '-'} |")
        lines += ["", "| gate | result |", "| --- | --- |"]
        for k, v in r["gates"].items():
            lines.append(f"| {k} | {'pass' if v else 'FAIL'} |")
        lines += ["", f"**Decision:** {'on by default' if passed else 'off by default (gate failed)'}.",
                  ""]
    return "\n".join(lines).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="Run the Jev eval suites.")
    ap.add_argument("--suite", default="all", choices=SUITES + ["all"])
    ap.add_argument("--live", action="store_true", help="send the requests (needs TYPESAFE_API_KEY)")
    ap.add_argument("--record", action="store_true", help="with --live, save the responses")
    ap.add_argument("--report", action="store_true", help=f"rewrite {os.path.relpath(REPORT, ROOT)}")
    args = ap.parse_args()
    if args.record and not args.live:
        ap.error("--record needs --live")
    if args.live and not os.environ.get("TYPESAFE_API_KEY", "").strip():
        print("--live needs TYPESAFE_API_KEY in the environment", file=sys.stderr)
        sys.exit(3)

    names = SUITES if args.suite == "all" else [args.suite]
    results, code, cost = [], 0, 0.0
    for name in names:
        r = run_suite(name, live=args.live, record=args.record)
        results.append(r)
        cost += r["cost_usd"]
        print(f"\n{name}: {'complete' if r['complete'] else 'INCOMPLETE'}")
        for k, v in r["metrics"].items():
            print(f"  {k:<34} {v}")
        for k, v in r["gates"].items():
            print(f"  gate  {'pass' if v else 'FAIL'}  {k}")
        if r["missing"]:
            print(f"  missing recordings: {len(r['missing'])} (run with --live --record)")
            for k in r["missing"][:10]:
                print(f"    {k}")
            code = 1
        elif not r["complete"]:
            code = 1
    print(f"\ncost{'' if args.live else ' at recording'}: ${cost:.4f} at ${USD_PER_MTOK} per "
          "million input tokens")
    if args.report:
        with open(REPORT, "w", encoding="utf-8") as fh:
            fh.write(render_report(results, datetime.date.today().isoformat()))
        print(f"wrote {os.path.relpath(REPORT, ROOT)}")
    sys.exit(code)


if __name__ == "__main__":
    main()

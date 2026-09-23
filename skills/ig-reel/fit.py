#!/usr/bin/env python3
"""
fit.py - before writing any hook, find out which of the 26 formulas this idea
can carry without inventing a fact.

Every formula in hooks.json lists its `needs`: the facts its template cannot be
written without. Cost Confession needs the amount one mistake cost. The Receipt
needs a number of days and the numbers that came out of them. If the idea does
not state them, writing that formula means making them up, and the pack's one
hard rule is never to do that.

TypeSafe's Jev model reads the idea once and answers, for every formula,
whether a true hook in that shape can be written from the idea alone. Code
sorts the answers:

  WRITABLE    (>= 0.50)  write only from these
  UNLOCKABLE  (0.25 - 0.50)  one answer from the user would unlock it; each
                              missing ingredient becomes a one-line question
  VETOED      (< 0.25)   would need invented facts

It also asks whether the idea is really two ideas. Jev never ranks the
survivors: choosing three formulas among the WRITABLE ones is still the
writer's job.

Without Jev (no TYPESAFE_API_KEY, offline, IG_JEV=off, --engine off) this
prints "fit: skipped" and exits 0. There is no code heuristic for this call,
and none is invented: the rule falls back to the prose in SKILL.md, use only
formulas whose `needs` the idea states.

Only the idea is sent, cut at 1,500 characters. voice.md, swipe.md, log.md and
anyone else's words never are.

Usage
  python3 fit.py "we cut proposal time from 5 hours to 20 minutes with one template"
  python3 fit.py "..." --json
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "hooks.json")

# Provisional thresholds (see evals/REPORT.md).
VETO = 0.25
WRITABLE = 0.50
MULTI = 0.70
MAX_IDEA = 1500

# Frozen wording: a change means re-running the fit eval.
MULTI_QUESTION = ("Does the `idea` contain two or more separate points that could each be a short "
                  "video on its own?")
MULTI_CRITERIA = {
    "true": ("Two or more distinct points, such as a story and an unrelated tip, or two different "
             "topics joined together."),
    "false": "One point, even if it has several steps, details or tangents that all serve it.",
}
FIT_QUESTION = ("Could a true hook in the shape of `formula.template` be written using only facts "
                "stated in the `idea`, without inventing any number, amount, duration, date, event, "
                "person or quote that `formula.needs` requires?")
FIT_CRITERIA = {
    "true": "Everything in `formula.needs` is stated in the idea or follows directly from it.",
    "false": ("Something in `formula.needs` is missing from the idea and would have to be made "
              "up, or the formula does not match what the idea is about."),
}


def load_formulas(path=HOOKS):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return sorted(({"id": h["id"], "name": h["name"], "template": h["template"],
                    "needs": h.get("needs") or []} for h in d["hooks"]), key=lambda f: f["id"])


def build_questions(formulas):
    q = {"multi_idea": {"type": "noul", "instructions": MULTI_QUESTION, "criteria": MULTI_CRITERIA}}
    for f in formulas:
        q[f"fit_{f['id']}"] = {
            "type": "noul",
            "instructions": {"formula": {"name": f["name"], "template": f["template"],
                                         "needs": f["needs"]},
                             "question": FIT_QUESTION},
            "criteria": FIT_CRITERIA,
        }
    return q


def _load_jev():
    path = os.path.join(HERE, "..", "ig-human")
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        import jev
        return jev
    except Exception:
        return None


def fit(idea, engine=None, hooks_path=HOOKS):
    formulas = load_formulas(hooks_path)
    idea = idea.strip()[:MAX_IDEA]
    out = {"idea": idea, "multi_idea": None, "multi": False, "writable": [], "unlockable": [],
           "vetoed": [], "skipped": None, "judgments": {}}
    jev = _load_jev()
    if jev is None:
        out.update(engine="heuristic", engine_reason="client-missing", engine_detail=None,
                   model=None, usage=None, skipped="client-missing",
                   engine_line="engine: heuristic (client-missing)")
        return out
    try:
        result = jev.ask_many({"idea": idea}, build_questions(formulas), engine=engine)
    except jev.JevUnavailable as e:
        out.update(jev.engine_fields(error=e), skipped=e.reason,
                   engine_line=jev.engine_line(reason=e.reason, detail=e.detail))
        return out
    out.update(jev.engine_fields(result), engine_line=jev.engine_line(result),
               judgments=result.answers)
    out["multi_idea"] = round(result.answers["multi_idea"]["noul"], 3)
    out["multi"] = out["multi_idea"] >= MULTI
    for f in formulas:
        p = result.answers[f"fit_{f['id']}"]["noul"]
        row = {"id": f["id"], "name": f["name"], "p": round(p, 3), "needs": f["needs"]}
        key = "writable" if p >= WRITABLE else "unlockable" if p >= VETO else "vetoed"
        out[key].append(row)
    for key in ("writable", "unlockable", "vetoed"):
        out[key].sort(key=lambda r: (-r["p"], r["id"]))
    return out


def render(r, out=None):
    lines = [r["engine_line"]]
    if r["skipped"]:
        lines.append(f"fit: skipped ({r['skipped']}). Use only formulas whose `needs` in "
                     "hooks.json are stated in the idea; otherwise ask for the missing ingredient.")
    else:
        idea = r["idea"] if len(r["idea"]) <= 60 else r["idea"][:57] + "..."
        head = f"FORMULA FIT  ·  \"{idea}\""
        lines += ["", head, "=" * max(len(head), 62)]
        if r["multi"]:
            lines.append(f"  TWO IDEAS? which one first?  (multi-idea {r['multi_idea']:.2f})")
        lines.append("  WRITABLE     write only from these")
        lines += [f"    {w['p']:.2f}  #{w['id']:<3}{w['name']}" for w in r["writable"]] or ["    none"]
        lines.append("  UNLOCKABLE   one answer from the user unlocks each")
        for u in r["unlockable"]:
            lines.append(f"    {u['p']:.2f}  #{u['id']:<3}{u['name']}")
            lines.append(f"          ask for: {'; '.join(u['needs'])}")
        if not r["unlockable"]:
            lines.append("    none")
        lines.append("  VETOED       would need invented facts")
        lines += [f"    {v['p']:.2f}  #{v['id']:<3}{v['name']}" for v in r["vetoed"]] or ["    none"]
        lines.append("-" * max(len(head), 62))
        lines.append(f"fit: {len(r['writable'])} writable, {len(r['unlockable'])} unlockable, "
                     f"{len(r['vetoed'])} vetoed · engine {r['model']}")
    text = "\n".join(lines) + "\n"
    if out is not None:
        out.write(text)
    return text


def main():
    ap = argparse.ArgumentParser(description="Which hook formulas can this idea carry?")
    ap.add_argument("idea", nargs="*", help="the idea, in the user's words")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--engine", choices=["auto", "jev", "off"])
    args = ap.parse_args()
    idea = " ".join(args.idea).strip() or sys.stdin.read().strip()
    if not idea:
        print("no idea given", file=sys.stderr)
        sys.exit(2)
    r = fit(idea, engine=args.engine)
    if args.json:
        print(json.dumps({k: v for k, v in r.items() if k != "engine_line"}, indent=2,
                         ensure_ascii=False))
    else:
        render(r, out=sys.stdout)
    sys.exit(3 if args.engine == "jev" and r["skipped"] else 0)


if __name__ == "__main__":
    main()

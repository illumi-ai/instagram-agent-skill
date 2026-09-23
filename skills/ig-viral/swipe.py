#!/usr/bin/env python3
"""
swipe.py - rank reels you collected by how far they beat their own account,
name the hook formula each one used, and write the swipe file.

The point of this script is one correction: raw views are not evidence. A
2,000,000-follower account doing 400,000 views had a quiet day. A 4,000-
follower account doing 400,000 views found something. This ranks on the
multiple over the account's own baseline, which is the only version of
"went viral" that tells you anything you can copy.

Input is a tab-separated file you fill in while you browse, one reel per row,
with a header line naming the columns:

    account   followers   median   views    hook
    @someone  48000       11000    412000   nobody tells you your first 30 flop

`median` is that account's typical recent views and is the better baseline.
If you only have `followers`, leave median out and the script says so.
`hook` is the first line of the reel, spoken or on screen, in their words.

Formulas are named by ../ig-reel/formula.py: the hooks.json regex, checked
against TypeSafe's Jev model when TYPESAFE_API_KEY is set. Only formulas the
two agree on, or that Jev names with high confidence when the regex found
nothing, are counted. Without Jev it is the regex alone, as it always was, and
the first line of the output says which engine ran.

Usage
  python3 swipe.py captured.tsv
  python3 swipe.py captured.tsv --out ~/.claude/instagram/swipe.md
  python3 swipe.py captured.tsv --json
  python3 swipe.py captured.tsv --engine off      # regex only, no network
"""

import argparse
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..", "ig-reel", "hooks.json")
WORD_RE = re.compile(r"[A-Za-z0-9$%'’-]+")

try:                                              # optional: score the hooks too
    sys.path.insert(0, os.path.join(HERE, "..", "ig-reel"))
    from hookscore import run as score_hook       # noqa: E402
except Exception:                                 # ig-viral copied on its own
    score_hook = None

try:                                              # regex + Jev formula names
    from formula import classify_hooks            # noqa: E402
except Exception:                                 # ig-reel not next to this folder
    classify_hooks = None


def load_formulas(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return None
    by_id = {h["id"]: h for h in d["hooks"]}
    order = d.get("classify_order") or sorted(by_id)
    return [(by_id[i]["id"], by_id[i]["name"],
             re.compile(by_id[i]["match"], re.IGNORECASE)) for i in order if i in by_id]


def classify(hook, formulas):
    if not formulas:
        return None, "unclassified"
    for fid, name, pattern in formulas:
        if pattern.search(hook):
            return fid, name
    return None, "unclassified"


def read_rows(path):
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    lines = [l for l in raw.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if not lines:
        return []
    head = [c.strip().lower() for c in lines[0].split("\t")]
    if "views" in head and "hook" in head:
        cols, body = head, lines[1:]
    else:
        cols, body = ["account", "followers", "views", "hook"], lines
    rows = []
    for line in body:
        cells = line.split("\t")
        if len(cells) < len(cols):
            cells += [""] * (len(cols) - len(cells))
        r = dict(zip(cols, [c.strip() for c in cells]))
        try:
            r["views"] = int(re.sub(r"[^\d]", "", r.get("views", "")) or 0)
        except ValueError:
            continue
        for k in ("followers", "median"):
            digits = re.sub(r"[^\d]", "", r.get(k, "") or "")
            r[k] = int(digits) if digits else None
        if r["views"] and r.get("hook"):
            rows.append(r)
    return rows


def name_formulas(rows, formulas, engine=None, hooks_path=HOOKS):
    """Set formula_id, formula and formula_status on every row, one engine for all.

    Returns the engine facts for the report.
    """
    fr = None
    if classify_hooks and formulas:
        fr = classify_hooks([r["hook"] for r in rows], engine=engine, hooks_path=hooks_path)
    if fr is None:
        for r in rows:
            r["formula_id"], r["formula"] = classify(r["hook"], formulas)
            r["formula_status"] = "REGEX" if r["formula_id"] else "unclassified"
            r["formula_counted"] = r["formula_id"] is not None
        reason = "client-missing" if not classify_hooks else "hooks-missing"
        return {"engine": "heuristic", "engine_reason": reason, "engine_detail": None,
                "model": None, "usage": None, "engine_line": f"engine: heuristic ({reason})",
                "formula_engine": f"regex ({reason})", "hooks_version": _version(hooks_path)}
    by_hook = {it["hook"]: it for it in fr["items"]}
    for r in rows:
        it = by_hook[r["hook"].strip()]
        r["formula_status"], r["formula_counted"] = it["status"], it["counted"]
        if it["counted"]:
            r["formula_id"], r["formula"] = it["formula_id"], it["formula"]
        else:
            r["formula_id"] = None
            r["formula"] = "unclassified" if it["status"] == "unclassified" else it["status"]
    jev_on = fr["engine"] == "jev"
    return {"engine": fr["engine"], "engine_reason": fr["engine_reason"],
            "engine_detail": fr["engine_detail"], "model": fr["model"], "usage": fr["usage"],
            "engine_line": fr["engine_line"],
            "formula_engine": f"regex+{fr['model']}" if jev_on else f"regex ({fr['engine_reason']})",
            "hooks_version": fr["hooks_version"]}


def _version(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("version", "?")
    except Exception:
        return "?"


def analyse(rows, formulas, engine=None, hooks_path=HOOKS):
    used_median = any(r.get("median") for r in rows)
    facts = name_formulas(rows, formulas, engine=engine, hooks_path=hooks_path)
    jev_on = facts["engine"] == "jev"
    for r in rows:
        base = r.get("median") or r.get("followers") or 0
        r["baseline"] = base
        r["outlier"] = round(r["views"] / base, 2) if base else None
        r["words"] = len(WORD_RE.findall(r["hook"]))
        if score_hook:
            _, overall, verdict, _ = score_hook(r["hook"])
            r["hook_score"], r["hook_verdict"] = round(overall, 1), verdict
        else:
            r["hook_score"], r["hook_verdict"] = None, None
    ranked = sorted(rows, key=lambda r: -(r["outlier"] or 0))
    third = max(1, len(ranked) // 3)
    top, bottom = ranked[:third], ranked[-third:]

    def med(items, key):
        vals = [i[key] for i in items if i.get(key) is not None]
        return round(statistics.median(vals), 1) if vals else None

    counts = {}
    for r in top:
        # With Jev, only formulas both engines stand behind are counted. The
        # regex-only report counts the way it always has.
        if jev_on and not r["formula_counted"]:
            continue
        counts[r["formula"]] = counts.get(r["formula"], 0) + 1
    return dict(facts, **{
        "baseline": "account median" if used_median else "follower count",
        "n": len(ranked),
        "accounts": len({r.get("account", "") for r in ranked}),
        "reels": ranked,
        "top_formulas": sorted(counts.items(), key=lambda kv: -kv[1]),
        "top_hook_score": med(top, "hook_score"),
        "bottom_hook_score": med(bottom, "hook_score"),
        "top_words": med(top, "words"),
        "bottom_words": med(bottom, "words"),
        "unclassified": sum(1 for r in ranked if not r["formula_counted"]),
        "jev_only": sum(1 for r in ranked if r["formula_status"] == "JEV"),
        "read_by_hand": {s: sum(1 for r in ranked if r["formula_status"] == s)
                         for s in ("DISPUTED", "NEW-SHAPE", "TENTATIVE")},
    })


def render(a, out=sys.stdout):
    head = (f"SWIPE FILE  ·  {a['n']} reels  ·  {a['accounts']} accounts  ·  "
            f"baseline: {a['baseline']}")
    print(a["engine_line"], file=out)
    print("\n" + head, file=out)
    print("=" * max(len(head), 78), file=out)
    for r in a["reels"]:
        mult = f"{r['outlier']:.1f}x" if r["outlier"] else "   ?"
        score = f"{r['hook_score']:.0f}" if r["hook_score"] is not None else " -"
        fid = f"#{r['formula_id']:<2}" if r["formula_id"] else "-  "
        print(f"  {mult:>7}  hook {score:>3}  {fid} {r['formula'][:22]:<22} "
              f"{r.get('account', '')[:16]:<16} {r['views']:>9,}", file=out)
        print(f"           \"{r['hook'][:96]}\"", file=out)
    print("-" * max(len(head), 78), file=out)
    print("WHAT IS WORKING IN THIS BATCH", file=out)
    if a["top_formulas"]:
        print("  top third by outlier:  "
              + ", ".join(f"{n} x{c}" for n, c in a["top_formulas"][:4]), file=out)
    if a["engine"] == "jev":
        print(f"  counted by jev only:   {a['jev_only']}", file=out)
        rb = a["read_by_hand"]
        if any(rb.values()):
            print(f"  read by hand:          {rb['DISPUTED']} disputed, {rb['NEW-SHAPE']} new shape, "
                  f"{rb['TENTATIVE']} tentative", file=out)
    if a["top_hook_score"] is not None:
        print(f"  median hook score:     top {a['top_hook_score']:.0f}  "
              f"vs bottom {a['bottom_hook_score']:.0f}", file=out)
    print(f"  median hook length:    top {a['top_words']} words  "
          f"vs bottom {a['bottom_words']} words", file=out)
    print(f"  unclassified:          {a['unclassified']} of {a['n']}. Read those by hand, "
          "they are where a formula you do not have yet is hiding.", file=out)
    print("\n  A hand-collected batch is evidence, not proof. Twelve reels shows you "
          "nothing;\n  forty across six accounts shows you something. Collect more before "
          "you believe it.\n", file=out)


def to_markdown(a):
    lines = ["# Swipe file", "",
             f"{a['n']} reels across {a['accounts']} accounts. "
             f"Ranked by multiple over {a['baseline']}.",
             f"formula engine: {a['formula_engine']} · hooks.json v{a['hooks_version']}", ""]
    for r in a["reels"]:
        mult = f"{r['outlier']:.1f}x" if r["outlier"] else "?"
        lines += [f"## {mult}  {r['formula']}  ({r.get('account', '')})",
                  f"- views: {r['views']:,}  baseline: {r['baseline']:,}",
                  f"- hook score: {r['hook_score']}  words: {r['words']}",
                  f"- hook: \"{r['hook']}\"", ""]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Rank collected reels by outlier multiple.")
    ap.add_argument("input", nargs="?", default="-", help="TSV file, or - for stdin")
    ap.add_argument("--hooks", default=HOOKS, help="path to ig-reel/hooks.json")
    ap.add_argument("--out", help="also write the swipe file as markdown here")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--engine", choices=["auto", "jev", "off"],
                    help="auto (default): Jev checks the formula names when TYPESAFE_API_KEY is set")
    args = ap.parse_args()

    rows = read_rows(args.input)
    if not rows:
        print("no usable rows. Need a tab-separated file with at least views and hook.",
              file=sys.stderr)
        sys.exit(2)
    formulas = load_formulas(args.hooks)
    a = analyse(rows, formulas, engine=args.engine, hooks_path=args.hooks)
    if not formulas:
        print("note: hooks.json not found, formulas not named. Pass --hooks.", file=sys.stderr)
    if score_hook is None:
        print("note: hookscore.py not importable, hook scores skipped.", file=sys.stderr)

    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    if args.out:
        path = os.path.expanduser(args.out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w", encoding="utf-8").write(to_markdown(a))
        print(f"wrote {path}", file=sys.stderr)
    if args.engine == "jev" and a["engine"] != "jev":
        sys.exit(3)


if __name__ == "__main__":
    main()

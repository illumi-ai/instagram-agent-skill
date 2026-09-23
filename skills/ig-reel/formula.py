#!/usr/bin/env python3
"""
formula.py - name the hook formula a line follows, with the regex in
hooks.json and TypeSafe's Jev model checking each other.

The regex in hooks.json is literal: it names a hook only when the wording is
close to the template, so most real hooks, which paraphrase, come back
unnamed, and a keyword in the wrong place ("Don't steal my content") can name
the wrong one. Jev reads the structure instead, but it is a model reading text
someone else wrote, so it is never trusted alone:

  AGREE      regex and Jev name the same formula             counted
  JEV        regex found nothing, Jev is sure (>= 0.85)      counted, marked jev
  TENTATIVE  regex found nothing, Jev leans (< 0.85)         not counted, "#3?"
  DISPUTED   regex and Jev disagree (Jev may say none)       not counted, read it
  NEW-SHAPE  neither names one, but the line has a shape     not counted, listed first
  NO-HOOK    neither names one, and the line has no shape    not counted
  READ       the line talks about formulas or classifying    not counted, Jev not asked
             (text written to steer a classifier), or its
             shape is unclear

Without Jev (no TYPESAFE_API_KEY, offline, IG_JEV=off, --engine off) the result
is the regex alone, status REGEX or unclassified, exactly as before. One engine
per run: counts from different engines are not comparable.

Formulas #13, #18 and #24 are visual. A text classifier cannot judge them.

Usage
  python3 formula.py "Nobody tells you that your first 30 reels flop."
  python3 formula.py --tsv captured.tsv            # the hook column of a swipe TSV
  python3 formula.py --selftest                     # the 26 examples, leave-one-out
  python3 formula.py "..." --json --engine off
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "hooks.json")

# Provisional thresholds (see evals/REPORT.md).
JEV_ONLY_MIN = 0.85     # Jev's confidence needed to count a formula the regex missed
NEW_SHAPE = 0.60        # has_shape above this with no formula: a shape you do not have yet
NO_HOOK = 0.30          # has_shape below this: greeting, preamble or fragment
MAX_HOOK = 300          # characters of the hook that are sent

# Text that talks about classification is text trying to steer the classifier.
META_RE = re.compile(r"\b(hook formula|formula|classif(?:y|ied|ication)|label (?:this|it) as)\b",
                     re.IGNORECASE)
COUNTED = {"AGREE", "JEV", "REGEX"}
ORDER = ["NEW-SHAPE", "DISPUTED", "TENTATIVE", "JEV", "AGREE", "REGEX", "READ", "NO-HOOK",
         "unclassified"]

# The questions. Frozen wording: a change means re-running the formula eval.
FORMULA_INSTRUCTIONS = {
    "question": "Which hook formula does the opening line in `hook` follow?",
    "judge": ("Judge the structure of the line, not its topic. Spoken hooks paraphrase: the "
              "wording can differ from a formula's shape as long as the structure is clearly "
              "the same."),
    "two_fit": "If two formulas fit, pick the one that shapes the first sentence.",
    "no_match": "Pick none when no formula's structure is clearly present.",
}
NONE_CRITERION = ("The line does not follow any formula above. Use this for greetings, "
                  "introductions of what the video covers, plain statements, fragments from the "
                  "middle of a conversation, and hooks built on a structure that is not listed here.")
HAS_SHAPE = ("Does the line in `hook` open with a specific claim, number, question, command, "
             "confession or story tension aimed at the viewer, rather than a greeting, an "
             "announcement of what the video will cover, or a fragment picked up from the "
             "middle of a conversation?")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load(path=HOOKS):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    formulas = sorted(({"id": h["id"], "name": h["name"], "slug": slug(h["name"]),
                        "template": h["template"], "example": h["example"],
                        "needs": h.get("needs"),
                        "regex": re.compile(h["match"], re.IGNORECASE)} for h in d["hooks"]),
                      key=lambda f: f["id"])
    by_id = {f["id"]: f for f in formulas}
    order = [i for i in (d.get("classify_order") or sorted(by_id)) if i in by_id]
    return {"version": d.get("version", "?"), "formulas": formulas, "by_id": by_id,
            "order": order, "slug_to_id": {f["slug"]: f["id"] for f in formulas}}


def regex_classify(hook, data):
    """The hooks.json regex, walked in classify_order. Same result as swipe.classify."""
    for fid in data["order"]:
        f = data["by_id"][fid]
        if f["regex"].search(hook):
            return fid, f["name"]
    return None, "unclassified"


def build_questions(data, leave_out_id=None):
    criteria = {}
    for f in data["formulas"]:
        opt = {"shape": f["template"]}
        if f["id"] != leave_out_id:
            opt["example"] = f["example"]
        criteria[f["slug"]] = opt
    criteria["none"] = NONE_CRITERION
    return {
        "formula": {"type": "choice", "instructions": dict(FORMULA_INSTRUCTIONS),
                    "criteria": criteria},
        "has_shape": {"type": "noul", "instructions": HAS_SHAPE},
    }


def status_for(regex_id, jev_slug, confidence, has_shape, slug_to_id):
    jev_id = slug_to_id.get(jev_slug)
    if regex_id is not None:
        return "AGREE" if jev_id == regex_id else "DISPUTED"
    if jev_id is not None:
        return "JEV" if confidence >= JEV_ONLY_MIN else "TENTATIVE"
    if has_shape >= NEW_SHAPE:
        return "NEW-SHAPE"
    if has_shape < NO_HOOK:
        return "NO-HOOK"
    return "READ"


def _load_jev():
    path = os.path.join(HERE, "..", "ig-human")
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        import jev
        return jev
    except Exception:
        return None


def _item(hook, rid, rname):
    return {"hook": hook, "regex_id": rid, "regex_name": rname, "jev_id": None, "jev_name": None,
            "confidence": None, "has_shape": None, "status": None, "counted": False,
            "formula_id": None, "formula": None, "top": [], "reason": None, "judgments": {}}


def classify_hooks(hooks, engine=None, hooks_path=HOOKS, selftest_ids=None):
    """Classify a batch of hooks with one engine for the whole batch.

    Duplicates are classified once. Each hook is its own request (a hook's
    position in a batch moved Jev's confidence in the probes), sent up to four
    at a time. If any request fails, every hook falls back to the regex.
    """
    data = load(hooks_path)
    seen, unique, leave = set(), [], {}
    for n, h in enumerate(hooks):
        h = h.strip()
        if h and h not in seen:
            seen.add(h)
            unique.append(h)
            if selftest_ids:
                leave[h] = selftest_ids[n]
    items = [_item(h, *regex_classify(h, data)) for h in unique]

    jev = _load_jev()
    result, error = None, None
    ask = [it for it in items if not META_RE.search(it["hook"])]
    if jev is None:
        error = "client-missing"
    elif not ask:
        error = jev.JevUnavailable("disabled", "nothing to ask")
    else:
        try:
            results = jev.ask_each(
                [({"hook": it["hook"][:MAX_HOOK]}, build_questions(data, leave.get(it["hook"])))
                 for it in ask], engine=engine)
            for it, r in zip(ask, results):
                it["_answers"] = r.answers
            result = _summary(jev, results)
        except jev.JevUnavailable as e:
            error = e

    by_id = data["by_id"]
    for it in items:
        answers = it.pop("_answers", None)
        if result is None:
            it["status"] = "REGEX" if it["regex_id"] else "unclassified"
        elif answers is None:
            it["status"], it["reason"] = "READ", "classification language in the hook"
        else:
            f, shape = answers["formula"], answers["has_shape"]["noul"]
            jid = data["slug_to_id"].get(f["choice"])
            it.update(jev_id=jid, jev_name=by_id[jid]["name"] if jid else "none",
                      confidence=round(f["confidence"], 3), has_shape=round(shape, 3),
                      judgments=answers,
                      top=sorted(((k, round(v, 3)) for k, v in f["probabilities"].items()),
                                 key=lambda kv: -kv[1])[:3])
            it["status"] = status_for(it["regex_id"], f["choice"], f["confidence"], shape,
                                      data["slug_to_id"])
            if it["status"] == "READ":
                it["reason"] = "shape unclear"
        it["counted"] = it["status"] in COUNTED
        if it["counted"]:
            fid = it["regex_id"] if it["status"] in ("AGREE", "REGEX") else it["jev_id"]
            it["formula_id"], it["formula"] = fid, by_id[fid]["name"]

    if jev is None:
        fields = {"engine": "heuristic", "engine_reason": "client-missing", "engine_detail": None,
                  "model": None, "usage": None, "requests": 0}
        line = "engine: heuristic (client-missing)"
    else:
        fields = jev.engine_fields(result, error)
        line = (jev.engine_line(result) if result is not None else
                jev.engine_line(reason=fields["engine_reason"], detail=fields["engine_detail"] or ""))
    return dict(fields, engine_line=line, hooks_version=data["version"], items=items)


def _summary(jev, results):
    if not results:
        return jev.Result(answers={}, requests=0)
    usage = {"input_tokens": sum(r.usage.get("input_tokens", 0) for r in results),
             "output_tokens": sum(r.usage.get("output_tokens", 0) for r in results)}
    return jev.Result(answers={}, model=results[0].model, usage=usage,
                      elapsed_s=max(r.elapsed_s for r in results), requests=len(results))


def describe(it):
    s = it["status"]
    if s in ("AGREE", "REGEX"):
        return f"#{it['formula_id']:<3}{it['formula']}"
    if s == "JEV":
        return f"#{it['formula_id']:<3}{it['formula']} ({it['confidence']:.2f})"
    if s == "TENTATIVE":
        return f"#{it['jev_id']}? {it['jev_name']} ({it['confidence']:.2f})"
    if s == "DISPUTED":
        jev_part = f"#{it['jev_id']}" if it["jev_id"] else "none"
        return f"regex #{it['regex_id']} / jev {jev_part} ({it['confidence']:.2f})"
    if s in ("NEW-SHAPE", "NO-HOOK"):
        return f"shape {it['has_shape']:.2f}"
    if s == "READ":
        return it["reason"] or ""
    return ""


def render(r, out=sys.stdout):
    items = sorted(r["items"], key=lambda it: ORDER.index(it["status"]))
    counted = sum(it["counted"] for it in items)
    jev_only = sum(it["status"] == "JEV" for it in items)
    print(r["engine_line"], file=out)
    head = (f"FORMULAS  ·  {len(items)} hooks  ·  {counted} counted"
            + (f" ({jev_only} by jev only)" if r["engine"] == "jev" else "")
            + f"  ·  hooks.json v{r['hooks_version']}")
    print("\n" + head, file=out)
    print("=" * max(len(head), 72), file=out)
    for it in items:
        hook = it["hook"] if len(it["hook"]) <= 70 else it["hook"][:67] + "..."
        print(f"  {it['status']:<12} {describe(it):<36} \"{hook}\"", file=out)
    print("-" * max(len(head), 72), file=out)
    if r["engine"] == "jev":
        print("  Count only AGREE and JEV. Read DISPUTED and NEW-SHAPE by hand: that is where a "
              "formula\n  you do not have yet is hiding. #13, #18 and #24 are visual and cannot "
              "be judged from text.\n", file=out)
    else:
        print("  Regex only. Unclassified lines are where a formula you do not have yet is "
              "hiding.\n", file=out)


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        lines = [l for l in fh.read().splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if not lines:
        return []
    head = [c.strip().lower() for c in lines[0].split("\t")]
    if "hook" in head:
        k = head.index("hook")
        return [c[k].strip() for c in (l.split("\t") for l in lines[1:]) if len(c) > k and c[k].strip()]
    return [l.split("\t")[-1].strip() for l in lines if l.split("\t")[-1].strip()]


def main():
    ap = argparse.ArgumentParser(description="Name the hook formula a line follows.")
    ap.add_argument("hooks", nargs="*", help="hook lines")
    ap.add_argument("--tsv", help="a swipe TSV; the hook column is classified")
    ap.add_argument("--selftest", action="store_true",
                    help="classify the 26 examples, each without its own example in the options")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--engine", choices=["auto", "jev", "off"])
    args = ap.parse_args()

    selftest_ids = None
    if args.selftest:
        data = load()
        hooks = [f["example"] for f in data["formulas"]]
        selftest_ids = [f["id"] for f in data["formulas"]]
    elif args.tsv:
        hooks = read_tsv(args.tsv)
    else:
        hooks = args.hooks or [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
    if not hooks:
        print("no hooks given", file=sys.stderr)
        sys.exit(2)

    r = classify_hooks(hooks, engine=args.engine, selftest_ids=selftest_ids)
    code = 3 if args.engine == "jev" and r["engine"] != "jev" else 0
    if args.selftest:
        expected = dict(zip(hooks, selftest_ids))
        right = sum(it["counted"] and it["formula_id"] == expected[it["hook"]] for it in r["items"])
        wrong = sum(it["counted"] and it["formula_id"] != expected[it["hook"]] for it in r["items"])
        regex_right = sum(it["regex_id"] == expected[it["hook"]] for it in r["items"])
        r["selftest"] = {"right": right, "wrong": wrong, "regex_right": regex_right, "n": len(hooks)}
        if wrong and not code:
            code = 1
    if args.json:
        print(json.dumps({k: v for k, v in r.items() if k != "engine_line"}, indent=2,
                         ensure_ascii=False))
    else:
        render(r)
        if args.selftest:
            st = r["selftest"]
            label = r["model"] if r["engine"] == "jev" else "heuristic"
            print(f"selftest: {label} {st['right']}/{st['n']} counted with the right id, "
                  f"{st['wrong']} wrong at a counted status; regex {st['regex_right']}/{st['n']}")
    sys.exit(code)


if __name__ == "__main__":
    main()

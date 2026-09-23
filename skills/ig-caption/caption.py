#!/usr/bin/env python3
"""
caption.py - lint an Instagram caption and show exactly what the feed shows
before the "... more".

Instagram gives a caption about 125 characters in the feed and hides the rest
behind a tap. Almost every caption that fails, fails there: the hook is in
sentence three, or the first line is a greeting, or the whole thing opens on a
hashtag. This prints the visible window as a box so you can read it the way a
scrolling stranger does, then checks the eight things that are worth checking.

The 125-character cut is an approximation. The real number moves with the
device, the font size and where your line breaks fall, which is exactly why
you want a margin rather than a caption engineered to end at 125. Change it
with --truncate if you want to test a tighter one.

Asks: with TYPESAFE_API_KEY set, TypeSafe's Jev model reads each sentence and
says whether it asks the reader to do something, and what. That catches the
paraphrased ask ("it's linked on my profile") and ignores the quoted one ("she
told me to share it"), which the regex list gets wrong. Code still groups the
asks, applies the one-ask rule and decides the verdict, and a Jev reading can
only ever produce a WARN, never a FAIL. Without the key, offline, or with
--engine off / IG_JEV=off, the regex list decides, exactly as before. The first
line of the output says which engine ran.

Usage
  python3 caption.py caption.txt
  python3 caption.py caption.txt --keywords "proposal software,client contract"
  pbpaste | python3 caption.py -
  python3 caption.py caption.txt --json
  python3 caption.py caption.txt --engine off      # regex only, no network
"""

import argparse
import json
import os
import re
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))

LIMIT = 2200             # Instagram's hard caption limit.
TRUNCATE = 125           # Roughly where the feed cuts to "... more".
HASHTAG_LIMIT = 5        # Instagram's cap per post or reel since 18 Dec 2025,
                         # down from 30. Announced by the @Creators account:
                         # "using fewer (up to 5) more targeted hashtags,
                         # rather than many generic ones, can improve both your
                         # content's performance and people's experience".

HASHTAG_RE = re.compile(r"(?:^|\s)(#[A-Za-z0-9_]+)")
MENTION_RE = re.compile(r"(?:^|\s)(@[A-Za-z0-9_.]+)")
LINK_RE = re.compile(r"https?://\S+|\bwww\.\S+|\b[a-z0-9-]+\.(?:com|co|io|net|org|ai|app)/\S*",
                     re.IGNORECASE)
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿←-⇿️]")
DIGIT_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,.]*\b")
CAP_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
WORD_RE = re.compile(r"[A-Za-z']+")

# Kept here rather than imported from ig-reel so this folder runs on its own.
# Same list as hookscore.py: spoken numbers are as concrete as digits.
SPOKEN_NUMBERS = {
    "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
    "billion", "dozen", "half", "twice", "triple",
}
# Capitalised, but not a name anybody could check.
NOT_NAMES = {
    "instagram", "insta", "reels", "reel", "stories", "threads", "facebook", "tiktok",
    "youtube", "linkedin", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "today", "tomorrow", "yesterday",
}

ASKS = [
    (re.compile(r"(?i)\bcomment (?:the word |\")?[A-Z0-9]{2,}\b"), "comment a keyword"),
    (re.compile(r"(?i)\b(?:dm|message) me\b"), "DM me"),
    (re.compile(r"(?i)\bsave (?:this|it)\b"), "save this"),
    (re.compile(r"(?i)\bshare (?:this|it)\b"), "share this"),
    (re.compile(r"(?i)\bfollow (?:me|for)\b"), "follow"),
    (re.compile(r"(?i)\blink in (?:my )?bio\b"), "link in bio"),
    (re.compile(r"(?i)\b(?:swipe|tap) (?:through|left|right|for|to)\b"), "swipe or tap"),
    (re.compile(r"(?i)\btell me\b|\bwhat would you\b|\bwhich one\b"), "answer a question"),
]

# Provisional thresholds (see evals/REPORT.md).
ASK = 0.50                # P(the sentence asks the reader to do something)
DOUBT = (0.35, 0.65)      # a sentence in here is reported as borderline

# Frozen wording: a change means re-running the caption eval.
IS_ASK_QUESTION = ("Does `sentence`, which is part of `caption`, ask or invite the person reading "
                   "this Instagram caption to do something?")
IS_ASK_CRITERIA = {
    "true": ("It asks the reader to comment, reply, answer a question, save, share, send the post "
             "to someone, tag someone, follow, DM, use the link in the bio, or swipe. An indirect "
             "pointer to a resource ('the template is in my bio') and a question the reader is "
             "meant to answer in the comments both count."),
    "false": ("It tells a story, explains, gives advice about the topic (even as a command, like "
              "'raise your prices'), describes or quotes what the writer or someone else said or "
              "did, or asks a rhetorical question that the caption answers itself. Words that are "
              "only quoted, described or reported do not count."),
}
ASK_TYPE_QUESTION = ("Which action, if any, does `sentence` ask the reader of this Instagram "
                     "caption to take?")
ASK_TYPES = {
    "comment_keyword": "Comment one specific word or code so the writer can send something, like 'Comment CONTRACT'",
    "comment_reply": "Reply in the comments with an opinion, answer, choice or emoji",
    "save": "Save the post for later",
    "share_or_send": "Share the post, send it to someone, or tag someone",
    "follow": "Follow the account",
    "dm": "Send the writer a direct message",
    "link_in_bio": "Use a link or resource in the bio or profile",
    "swipe": "Swipe or tap through the post",
    "no_ask": "The sentence does not ask the reader to take any action",
}
ASK_LABELS = {"comment_keyword": "comment a keyword", "comment_reply": "reply in the comments",
              "save": "save this", "share_or_send": "share or send", "follow": "follow",
              "dm": "DM me", "link_in_bio": "link in bio", "swipe": "swipe or tap",
              "unspecified": "unspecified ask"}
# The regex names, in the same vocabulary, for the cross-check.
REGEX_TYPES = {"comment a keyword": "comment_keyword", "DM me": "dm", "save this": "save",
               "share this": "share_or_send", "follow": "follow", "link in bio": "link_in_bio",
               "swipe or tap": "swipe", "answer a question": "comment_reply"}
KEYWORD_RE = re.compile(r"\b[A-Z0-9]{2,}\b")
TAG_LINE_RE = re.compile(r"^\s*(?:[#@][\w.]+[\s,]*)+$")

FILLER_TAGS = {"#viral", "#fyp", "#explore", "#explorepage", "#foryou", "#foryoupage",
               "#trending", "#instagood", "#love", "#follow", "#like4like", "#reels",
               "#reelsinstagram", "#viralreels", "#instadaily"}


def _sentence_starts(text):
    starts = {0}
    for m in re.finditer(r"(?:[.!?]+[\"'”’)]*\s+|\n\s*)", text):
        starts.add(m.end())
    return starts | {s + 1 for s in starts if s < len(text) and text[s] in "\"'“‘("}


def concrete_markers(text):
    """Numbers, spoken numbers and names. Not a capital that starts a sentence,
    not a platform, not a day of the week."""
    starts = _sentence_starts(text)
    found = [m.group(0) for m in DIGIT_RE.finditer(text)]
    found += [m.group(0) for m in CAP_RE.finditer(text)
              if m.start() not in starts and m.group(0).lower() not in NOT_NAMES]
    found += [w for w in (x.lower() for x in WORD_RE.findall(text)) if w in SPOKEN_NUMBERS]
    return found


def split_sentences(text):
    """Sentences of the caption, lines of only hashtags or mentions dropped.

    A quoted passage stays inside its sentence: "she said "share it. now." and
    left." is one sentence, because the quote is reported speech, not an ask.
    """
    out = []
    for line in text.split("\n"):
        if not line.strip() or TAG_LINE_RE.match(line):
            continue
        buf, quoted, i = "", False, 0
        while i < len(line):
            ch = line[i]
            buf += ch
            if ch == '"':
                quoted = not quoted
            elif ch == "\u201c":
                quoted = True
            elif ch == "\u201d":
                quoted = False
            elif ch in ".!?" and not quoted:
                while i + 1 < len(line) and line[i + 1] in ".!?)":
                    i += 1
                    buf += line[i]
                if i + 1 == len(line) or line[i + 1].isspace():
                    if buf.strip():
                        out.append(buf.strip())
                    buf = ""
            i += 1
        if buf.strip():
            out.append(buf.strip())
    return out


def ask_questions(sentences):
    q = {}
    for i, sent in enumerate(sentences, 1):
        q[f"s{i}_is_ask"] = {"type": "noul",
                             "instructions": {"sentence": sent, "question": IS_ASK_QUESTION},
                             "criteria": IS_ASK_CRITERIA}
        q[f"s{i}_ask_type"] = {"type": "choice",
                               "instructions": {"sentence": sent, "question": ASK_TYPE_QUESTION},
                               "criteria": ASK_TYPES}
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


def jev_asks(jev, text, engine=None):
    """Ask Jev about every sentence. Returns (result, rows); raises JevUnavailable."""
    sentences = split_sentences(text)
    if not sentences:
        raise jev.JevUnavailable("disabled", "no sentences")
    state = {"caption": "\n".join(l for l in text.strip().split("\n")
                                  if l.strip() and not TAG_LINE_RE.match(l))}
    result = jev.ask_many(state, ask_questions(sentences), engine=engine)
    rows = []
    for i, sent in enumerate(sentences, 1):
        p = result.answers[f"s{i}_is_ask"]["noul"]
        typ = result.answers[f"s{i}_ask_type"]["choice"]
        rows.append({"sentence": sent, "p": round(p, 3), "choice": typ, "ask": p >= ASK,
                     "type": (typ if typ != "no_ask" else "unspecified") if p >= ASK else None,
                     "doubt": DOUBT[0] <= p < DOUBT[1]})
    return result, rows


def _types(rows):
    seen = []
    for r in rows:
        if r["type"] and r["type"] not in seen:
            seen.append(r["type"])
    return seen


def visible_window(text, cut):
    """What the feed shows. Instagram cuts mid-word, so this does too."""
    flat = text.strip()
    return flat if len(flat) <= cut else flat[:cut]


def render_box(window, truncated, out=sys.stdout, width=52):
    print("\n  WHAT THE FEED SHOWS", file=out)
    print("  +" + "-" * (width + 2) + "+", file=out)
    lines = []
    for raw in window.split("\n"):
        lines.extend(textwrap.wrap(raw, width) or [""])
    for line in lines[:8]:
        print(f"  | {line:<{width}} |", file=out)
    tail = "... more" if truncated else "(whole caption fits)"
    print("  +" + "-" * (width + 2 - len(tail) - 2) + f" {tail} " + "+", file=out)


def analyse(text, cut=TRUNCATE, keywords=None, engine=None):
    text = text.rstrip()
    stripped = text.strip()
    chars = len(stripped)
    lines = [l for l in stripped.split("\n")]
    first_line = lines[0].strip() if lines else ""
    tags = HASHTAG_RE.findall(stripped)
    mentions = MENTION_RE.findall(stripped)
    links = LINK_RE.findall(stripped)
    emoji = EMOJI_RE.findall(stripped)
    window = visible_window(stripped, cut)
    truncated = chars > cut
    heuristic_asks = [name for pattern, name in ASKS if pattern.search(stripped)]
    asks, rows, notes, result, error = heuristic_asks, None, [], None, None
    jev = _load_jev()
    if jev is None:
        error = "client-missing"
    else:
        try:
            result, rows = jev_asks(jev, stripped, engine=engine)
        except jev.JevUnavailable as e:
            error = e
    if rows is not None:
        asks = _types(rows)
        for r in rows:
            if r["doubt"] and not r["ask"]:
                notes.append(f"possible ask ({r['p']:.2f}): \"{r['sentence']}\"")
        firm = _types([r for r in rows if not r["doubt"]])
        loose = _types([dict(r, type=r["type"] or (r["choice"] if r["choice"] != "no_ask"
                                                   else "unspecified"))
                        for r in rows if r["ask"] or r["doubt"]])
        if len({len(asks) == 1, len(firm) == 1, len(loose) == 1}) > 1:
            for r in rows:
                if r["doubt"]:
                    notes.append(f"borderline, decide out loud: \"{r['sentence']}\" ({r['p']:.2f})")
        regex_types = sorted({REGEX_TYPES.get(a, a) for a in heuristic_asks})
        if regex_types != sorted(asks):
            notes.append(f"regex vs jev: regex saw [{', '.join(heuristic_asks)}], "
                         f"jev saw [{', '.join(ASK_LABELS.get(a, a) for a in asks)}]")
    filler = [t for t in tags if t.lower() in FILLER_TAGS]
    keywords = [k.strip() for k in (keywords or []) if k.strip()]

    checks = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    add("LENGTH", "FAIL" if chars > LIMIT else "PASS",
        f"{chars} / {LIMIT} characters" + (f", {chars - LIMIT} over the limit"
                                           if chars > LIMIT else ""))

    if not first_line:
        add("FIRST LINE", "FAIL", "the caption opens on a blank line")
    elif first_line.startswith("#") or first_line.startswith("@"):
        add("FIRST LINE", "FAIL",
            "opens on a hashtag or a mention, which is the one position worth a sentence")
    elif len(first_line) > cut:
        add("FIRST LINE", "WARN",
            f"{len(first_line)} characters, so it gets cut at {cut} mid-thought. "
            "Fine if the cut is a cliffhanger, bad if it is a subordinate clause")
    else:
        add("FIRST LINE", "PASS", f"{len(first_line)} characters, lands whole")

    markers = concrete_markers(window)
    add("HOOK IS CONCRETE", "PASS" if markers else "WARN",
        f"{len(markers)} number(s) or name(s) in the visible window"
        + ("" if markers else " - nothing checkable before the tap"))

    if len(tags) > HASHTAG_LIMIT:
        add("HASHTAGS", "FAIL", f"{len(tags)} tags, over Instagram's cap of {HASHTAG_LIMIT}. "
                                "Tags past the fifth do not count and the block reads as old")
    elif len(tags) == HASHTAG_LIMIT and filler:
        add("HASHTAGS", "WARN", f"{len(tags)} tags, at the cap, and "
                                f"{len(filler)} of them generic. Spend the five on topics")
    elif filler:
        add("HASHTAGS", "WARN", f"{len(tags)} tags, {len(filler)} of them generic "
                                f"({', '.join(filler[:3])}). Those describe nothing")
    else:
        add("HASHTAGS", "PASS", f"{len(tags)} tag(s)" + (f": {' '.join(tags)}" if tags else ""))

    if not tags:
        add("TAG PLACEMENT", "PASS", "no tags to place")
    elif any(re.search(r"(?:^|\s)" + re.escape(t) + r"\b", window) for t in tags):
        add("TAG PLACEMENT", "WARN", "a hashtag is inside the visible window, "
                                     "spending feed space on a label")
    else:
        add("TAG PLACEMENT", "PASS", "tags are below the fold")

    add("LINKS", "WARN" if links else "PASS",
        f"{len(links)} link(s) in the caption, and captions are not clickable. "
        f"Move it to the bio or the DM" if links else "no dead links in the body")

    if rows is not None and len(asks) == 1:
        sent = next(r["sentence"] for r in rows if r["type"] == asks[0])
        if asks[0] == "comment_keyword" and not KEYWORD_RE.search(sent):
            add("ONE ASK", "WARN", f"keyword ask has no single CAPS word to comment: \"{sent}\"")
        else:
            add("ONE ASK", "PASS", f"one call to action: {ASK_LABELS[asks[0]]} (\"{sent}\")")
    elif rows is not None and len(asks) > 1:
        add("ONE ASK", "WARN", f"{len(asks)} asks ({', '.join(ASK_LABELS[a] for a in asks)}). "
                               "Two asks is the same as none")
    elif len(asks) == 1:
        add("ONE ASK", "PASS", f"one call to action: {asks[0]}")
    elif not asks:
        add("ONE ASK", "WARN", "no call to action. Decide what this post is for")
    else:
        add("ONE ASK", "WARN", f"{len(asks)} asks ({', '.join(asks)}). "
                               "Two asks is the same as none")

    density = len(emoji) * 100 / max(chars, 1)
    add("EMOJI", "WARN" if density > 4 else "PASS",
        f"{len(emoji)} emoji, {density:.1f} per 100 characters"
        + (" - reads as decoration" if density > 4 else ""))

    if keywords:
        low = stripped.lower()
        found = [k for k in keywords if k.lower() in low]
        missing = [k for k in keywords if k.lower() not in low]
        in_window = [k for k in found if k.lower() in window.lower()]
        status = "PASS" if not missing else ("WARN" if found else "FAIL")
        add("SEARCH TERMS", status,
            f"{len(found)}/{len(keywords)} present"
            + (f", {len(in_window)} in the visible window" if found else "")
            + (f". Missing: {', '.join(missing)}" if missing else ""))

    fails = sum(1 for c in checks if c["status"] == "FAIL")
    warns = sum(1 for c in checks if c["status"] == "WARN")
    verdict = "FIX" if fails else ("REVIEW" if warns else "READY")

    if jev is None:
        fields = {"engine": "heuristic", "engine_reason": "client-missing", "engine_detail": None,
                  "model": None, "usage": None, "requests": 0}
        line = "engine: heuristic (client-missing)"
    else:
        fields = jev.engine_fields(result, error)
        line = (jev.engine_line(result) if result is not None else
                jev.engine_line(reason=fields["engine_reason"], detail=fields["engine_detail"] or ""))
    return dict(fields, **{
        "engine_line": line,
        "characters": chars, "limit": LIMIT, "truncate_at": cut,
        "visible": window, "truncated": truncated,
        "first_line_chars": len(first_line),
        "hashtags": tags, "mentions": mentions, "links": links,
        "emoji": len(emoji), "asks": asks, "heuristic_asks": heuristic_asks,
        "ask_sentences": rows or [], "judgments": result.answers if result is not None else {},
        "notes": notes,
        "checks": checks, "verdict": verdict,
    })


def render(a, out=sys.stdout):
    head = (f"CAPTION LINT  ·  {a['characters']} / {a['limit']} chars  ·  "
            f"{len(a['hashtags'])} hashtags  ·  {len(a['asks'])} ask(s)")
    print(a["engine_line"], file=out)
    print("\n" + head, file=out)
    print("=" * max(len(head), 62), file=out)
    render_box(a["visible"], a["truncated"], out=out)
    print("", file=out)
    for c in a["checks"]:
        print(f"  {c['status']:<5} {c['check']:<17} {c['detail']}", file=out)
    for n in a["notes"]:
        print(f"  note  {n}", file=out)
    print("-" * max(len(head), 62), file=out)
    print(f"  VERDICT  {a['verdict']}\n", file=out)


def main():
    ap = argparse.ArgumentParser(description="Lint an Instagram caption.")
    ap.add_argument("input", nargs="?", default="-", help="caption file, or - for stdin")
    ap.add_argument("--truncate", type=int, default=TRUNCATE,
                    help=f"characters shown before '... more' (default {TRUNCATE})")
    ap.add_argument("--keywords", default="", help="comma-separated terms you want to be found for")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--engine", choices=["auto", "jev", "off"],
                    help="auto (default): Jev reads the asks when TYPESAFE_API_KEY is set")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    a = analyse(raw, cut=args.truncate, keywords=args.keywords.split(","), engine=args.engine)
    if args.json:
        print(json.dumps({k: v for k, v in a.items() if k != "engine_line"}, indent=2,
                         ensure_ascii=False))
    else:
        render(a)
    if args.engine == "jev" and a["engine"] != "jev":
        sys.exit(3)
    sys.exit(0 if a["verdict"] == "READY" else 1)


if __name__ == "__main__":
    main()

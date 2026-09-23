#!/usr/bin/env python3
"""
proofcheck.py - check every claim in a draft against what the user actually
gave you, before the draft is shown to them.

The pack's one hard rule is "never fabricate": no invented metrics, clients,
revenue or outcomes under the user's name. This is the guard for it. Every
sentence that states something the user did, earned, lost or achieved has to
be traceable to one piece of evidence:

  - a bullet under "## Proof I can use" in voice.md,
  - the name and handle under "## Who I am",
  - something the user said in this session (--said, copied word for word),
  - the user's own source material (--source, for /ig-repurpose).

Nothing else counts. Comments, received DMs and other people's words are never
evidence, and "## Off limits" and the rest of voice.md are never read.

Two layers:

  L0, code, always runs. Every number in a claim must equal a number in ONE
      evidence item, or be an exact derivation of two numbers from that same
      item (ratio, percent change, difference, sum, hours and minutes). Every
      name and @handle must appear in the evidence. Anything else becomes
      {{your number}} or {{client name}} in the -o output.
  L1, Jev, when available. For each sentence: what kind of statement is it,
      which evidence item reports the same event, and does that item state
      everything the sentence states. Jev can add claims and flags. It never
      removes one that L0 raised, and it never counts or compares numbers.

Statuses:  BACKED, DERIVED (a number worked out from the proof, light review),
           UNBACKED (no evidence reports this), MISMATCH (the proof says a
           different number), EMBELLISHED (the sentence adds to the proof),
           UNVERIFIED (offline, first person, nothing in the evidence overlaps),
           FLAGGED (offline, a number or name is not in the evidence),
           CHECKED (offline, numbers and names found; meaning not judged).

Usage
  python3 proofcheck.py draft.txt --said said.txt
  python3 proofcheck.py draft.txt --said said.txt -o fixed.txt
  python3 proofcheck.py draft.txt --source talk.txt --json
  python3 proofcheck.py draft.txt --engine off          # code only, no network

Exit code: 0 when nothing needs confirming, 1 when something does, 2 on a usage
error, 3 when --engine jev was asked for and Jev was not available.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
VOICE = os.path.expanduser("~/.claude/instagram/voice.md")

# Provisional thresholds, measured on small agent-written sets (see evals/REPORT.md).
CLAIM = 0.50        # P(own_record) + P(client_result) that makes a sentence a claim
SAME = 0.50         # the best evidence item reports the same event
HELD = 0.50         # that item states everything the sentence states
SHORTLIST = 5       # evidence items compared with each sentence

PLACEHOLDER_NUMBER = "{{your number}}"
PLACEHOLDER_NAME = "{{client name}}"

# --------------------------------------------------------------------------
# Evidence


@dataclass
class Item:
    id: str
    text: str
    kind: str          # identity | proof | said | source


BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)?\s*$")
FIELD_RE = re.compile(r"^\s*[-*]\s+\*\*(Name|Handle):\*\*\s*(.*?)\s*$", re.IGNORECASE)
HANDLE_RE = re.compile(r"@[A-Za-z0-9_](?:[A-Za-z0-9_.]*[A-Za-z0-9_])?")
CAP_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")


def _sections(text):
    out, name = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            name = m.group(1).strip().lower()
            out.setdefault(name, [])
        elif name is not None:
            out[name].append(line)
    return out


def parse_voice(text):
    """Evidence items from voice.md: the identity line and each Proof bullet.

    Returns (items, allowed) where allowed holds the lower-cased names and
    handles the user may mention.
    """
    sections = _sections(text or "")
    items, allowed = [], set()
    fields = {}
    for line in sections.get("who i am", []):
        m = FIELD_RE.match(line)
        if m and m.group(2):
            fields[m.group(1).lower()] = m.group(2)
    if fields:
        name, handle = fields.get("name", ""), fields.get("handle", "")
        if handle and not handle.startswith("@"):
            handle = "@" + handle
        parts = [f"Name: {name}"] if name else []
        parts += [f"Handle: {handle}"] if handle else []
        items.append(Item("identity", "; ".join(parts), "identity"))
        allowed.update(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]+", name))
        if handle:
            allowed.add(handle.lower())
    bullets, current = [], None
    for line in sections.get("proof i can use", []):
        m = BULLET_RE.match(line)
        if m:
            if current:
                bullets.append(current)
            current = (m.group(1) or "").strip()
        elif current is not None and line.strip() and line[:1].isspace():
            current += " " + line.strip()
        elif not line.strip() and current:
            bullets.append(current)
            current = None
    if current:
        bullets.append(current)
    for n, text_ in enumerate([b for b in bullets if b], 1):
        items.append(Item(f"proof{n}", text_, "proof"))
    return items, allowed


def load_evidence(voice_text="", said_text="", source_text=""):
    """All evidence, in a fixed order: identity, proof, said, source."""
    items, allowed = parse_voice(voice_text)
    for kind, text in (("said", said_text), ("source", source_text)):
        lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
        items += [Item(f"{kind}{n}", l, kind) for n, l in enumerate(lines, 1)]
    for it in items:
        allowed.update(m.group(0).lower() for m in CAP_RE.finditer(it.text))
        allowed.update(h.lower() for h in HANDLE_RE.findall(it.text))
    return items, allowed


# --------------------------------------------------------------------------
# Sentences

SPLIT_RE = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"'”’)]))\s+(?=[\"'“‘(]?[A-Z0-9$@{])")
WORD_RE = re.compile(r"[A-Za-z0-9$%'’]+")


def split_sentences(draft):
    """One entry per sentence, with offsets into the draft. Lines holding a
    {{placeholder}} are skipped, and a fragment under five words is joined to
    the sentence before it on the same line ("Twenty minutes now.")."""
    out, pos = [], 0
    for line in draft.splitlines(keepends=True):
        start_line = pos
        pos += len(line)
        body = line.rstrip("\r\n")
        if not body.strip() or "{{" in body:
            continue
        spans, last = [], 0
        for m in SPLIT_RE.finditer(body):
            spans.append((last, m.start()))
            last = m.end()
        spans.append((last, len(body)))
        merged = []
        for a, b in spans:
            piece = body[a:b].strip()
            if not piece:
                continue
            if merged and len(WORD_RE.findall(piece)) < 5:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        for a, b in merged:
            raw = body[a:b]
            lead = len(raw) - len(raw.lstrip())
            text = raw.strip()
            s = start_line + a + lead
            out.append({"i": len(out) + 1, "text": text, "start": s, "end": s + len(text)})
    return out


CLAIM_RE = re.compile(r"(?i)\b(i|i'm|i’m|i've|i’ve|i'd|i’d|we|we're|we’re|we've|we’ve|my|our|me|us|"
                      r"client|clients|customer|customers|student|students)\b")
NOT_A_CLAIM_RE = re.compile(r"(?i)\b(i'll|i’ll|i will|we'll|we’ll|we will|i want|we want|i'd like|"
                            r"i’d like|i'm going to|i’m going to|let me)\b")


def is_l0_claim(sentence):
    """First person or a client, and not a question or a promise about the future."""
    s = sentence.strip()
    if s.endswith("?") or NOT_A_CLAIM_RE.search(s):
        return False
    return bool(CLAIM_RE.search(s))


# --------------------------------------------------------------------------
# Numbers


@dataclass
class Num:
    value: float
    unit: str          # "$" | "%" | "x" | "min" | "year" | ""
    text: str
    start: int
    end: int


UNITS = [
    (r"%|percent\b|per cent\b", "%", 1),
    (r"x\b|times\b", "x", 1),
    (r"grand\b", "$", 1000),
    (r"dollars?\b|bucks\b", "$", 1),
    (r"seconds?\b|secs?\b", "min", 1 / 60),
    (r"minutes?\b|mins?\b", "min", 1),
    (r"hours?\b|hrs?\b", "min", 60),
    (r"days?\b", "min", 1440),
    (r"weeks?\b", "min", 10080),
    (r"months?\b", "min", 43200),
    (r"years?\b|yrs?\b", "min", 525600),
]
UNIT_RE = re.compile(r"\s?(?:" + "|".join(f"({p})" for p, _, _ in UNITS) + ")", re.IGNORECASE)
SMALL = {"zero": 0, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
         "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90, "dozen": 12}
SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
MULTIPLIERS = {"twice": 2, "double": 2, "doubled": 2, "doubling": 2, "triple": 3,
               "tripled": 3, "quadrupled": 4, "half": 0.5, "halved": 0.5}
YEAR_BEFORE_RE = re.compile(
    r"(?i)\b(?:in|since|from|by|until|til|of|during|early|late|mid|spring|summer|fall|autumn|"
    r"winter|january|february|march|april|may|june|july|august|september|october|november|"
    r"december)\s+$")
WORD_NUM = r"(?:" + "|".join(sorted(list(SMALL) + list(SCALES), key=len, reverse=True)) + r")"
NUM_RE = re.compile(
    r"(?P<money>\$)?\s?(?P<digits>\d(?:[\d,]*\d)?(?:\.\d+)?)(?P<k>(?-i:[kK]\b|M\b))?"
    r"|\b(?P<words>" + WORD_NUM + r"(?:[\s-]+(?:and\s+)?" + WORD_NUM + r"|[\s-]+one\b)*)\b"
    r"|\b(?P<mult>" + "|".join(MULTIPLIERS) + r")\b",
    re.IGNORECASE)


def _words_value(text):
    total, current = 0, 0
    for w in re.findall(r"[a-z]+", text.lower()):
        if w == "and":
            continue
        if w == "one":
            current += 1
        elif w in SMALL:
            current += SMALL[w]
        elif w == "hundred":
            current = (current or 1) * 100
        elif w in SCALES:
            total += (current or 1) * SCALES[w]
            current = 0
    return total + current


def numbers(text):
    """Every quantity in the text, normalised: money in dollars, time in minutes.

    "one", "first" and "single" are not quantities here: they are filler far
    more often than they are a count.
    """
    out = []
    for m in NUM_RE.finditer(text):
        start, end = m.start(), m.end()
        if m.group("mult"):
            out.append(Num(float(MULTIPLIERS[m.group("mult").lower()]), "x", m.group(0), start, end))
            continue
        if m.group("digits"):
            start = m.start("money") if m.group("money") else m.start("digits")
            value = float(m.group("digits").replace(",", ""))
            if m.group("k"):
                value *= 1000 if m.group("k") in "kK" else 1_000_000
            unit = "$" if m.group("money") else ""
        else:
            start = m.start("words")
            value = float(_words_value(m.group("words")))
            unit = ""
        u = UNIT_RE.match(text, end)
        if u and not unit:
            idx = next(i for i in range(len(UNITS)) if u.group(i + 1))
            _, unit, factor = UNITS[idx]
            value *= factor
            end = u.end()
        elif u and unit == "$" and u.group(3):          # "$20 grand" is rare, but $ wins
            end = u.end()
        if (not unit and m.group("digits") and re.fullmatch(r"(?:19|20)\d\d", m.group("digits"))
                and YEAR_BEFORE_RE.search(text[:start])):
            unit = "year"
        out.append(Num(value, unit, text[start:end], start, end))
    return out


def _close(claim, target):
    """Equal, within 1%, or the target rounded the way people round when they speak."""
    diff = abs(claim - target)
    return (diff <= abs(target) * 0.01 + 1e-9 or diff < 0.05
            or (abs(target) >= 10 and diff < 0.5))


def _compatible(a, b):
    if a == b:
        return True
    return (a == "" and b not in ("year",)) or (b == "" and a not in ("year",))


def bind_number(n, item_nums):
    """'direct' when an item number matches, 'derived' when two numbers of the
    same item produce it, None otherwise."""
    for t in item_nums:
        if _compatible(n.unit, t.unit) and _close(n.value, t.value):
            return "direct"
    for i, a in enumerate(item_nums):
        for j, b in enumerate(item_nums):
            if i == j or a.unit != b.unit or a.unit == "year":
                continue
            if n.unit in ("x", "") and b.value and _close(n.value, a.value / b.value):
                return "derived"
            if _compatible(n.unit, a.unit) and (_close(n.value, abs(a.value - b.value))
                                                or (i < j and _close(n.value, a.value + b.value))):
                return "derived"
            if n.unit in ("%", "") and a.value and _close(n.value, abs(b.value - a.value) / a.value * 100):
                return "derived"
    return None


def bindings(claim_nums, items):
    """For each evidence item, which claim numbers it backs, directly or derived."""
    out, bound = {}, set()
    for it in items:
        nums = numbers(it.text)
        for k, n in enumerate(claim_nums):
            how = bind_number(n, nums)
            if how:
                out.setdefault(it.id, {"direct": [], "derived": []})[how].append(k)
                bound.add(k)
    out["unbound"] = [k for k in range(len(claim_nums)) if k not in bound]
    return out


# --------------------------------------------------------------------------
# Names

NOT_NAMES = {
    "instagram", "insta", "reels", "reel", "stories", "story", "threads", "facebook",
    "google", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "june", "july", "august", "september",
    "october", "november", "december", "today", "tomorrow", "yesterday", "here", "there",
    "this", "that", "the", "and", "but", "then", "also", "plus", "christmas", "easter",
}


def _sentence_starts(text):
    starts = {0}
    for m in re.finditer(r"(?:[.!?:]+[\"'”’)]*\s+|\n\s*)", text):
        starts.add(m.end())
    return starts | {s + 1 for s in starts if s < len(text) and text[s] in "\"'“‘("}


def names(text):
    """Capitalised words that are not the first word of a sentence and not a
    platform, a day, a month or a filler word. (name, start, end)."""
    starts = _sentence_starts(text)
    in_handle = [(m.start(), m.end()) for m in HANDLE_RE.finditer(text)]
    return [(m.group(0), m.start(), m.end()) for m in CAP_RE.finditer(text)
            if m.start() not in starts and m.group(0).lower() not in NOT_NAMES
            and not any(a <= m.start() < b for a, b in in_handle)]


def handles(text):
    return [(m.group(0), m.start(), m.end()) for m in HANDLE_RE.finditer(text)]


# --------------------------------------------------------------------------
# L0

STOPWORDS = {
    "the", "and", "but", "for", "with", "that", "this", "from", "into", "your", "you",
    "our", "was", "were", "are", "has", "had", "have", "not", "now", "all", "one", "who",
    "what", "when", "then", "than", "them", "they", "their", "its", "it's", "i'm", "i've",
    "just", "about", "after", "before", "over", "out", "per", "every", "same", "only",
    "used", "take", "took", "got", "get", "did", "does", "can", "will", "been", "being",
}


def content_words(text):
    return {w for w in (x.lower().strip("'’") for x in WORD_RE.findall(text))
            if len(w) >= 3 and w not in STOPWORDS and not w[:1].isdigit() and w[:1] != "$"}


def shortlist(sentence, items, k=SHORTLIST):
    """The k evidence items closest to the sentence: shared content words, plus
    two points for each number of the sentence the item backs."""
    words = content_words(sentence)
    nums = numbers(sentence)

    def score(it):
        item_nums = numbers(it.text)
        return len(words & content_words(it.text)) + 2 * sum(
            1 for n in nums if bind_number(n, item_nums))
    ranked = sorted(enumerate(items), key=lambda p: (-score(p[1]), p[0]))
    return [it for _, it in ranked[:k]]


def _flag(kind, text, start, end):
    return {"type": kind, "text": text, "start": start, "end": end,
            "placeholder": PLACEHOLDER_NUMBER if kind == "number" else PLACEHOLDER_NAME}


def claim_flags(sentence, offset, items, allowed):
    """L0 flags for one claim: unbacked numbers, unknown names and handles."""
    nums = numbers(sentence)
    b = bindings(nums, items)
    flags = [_flag("number", nums[k].text, offset + nums[k].start, offset + nums[k].end)
             for k in b["unbound"]]
    for text, s, e in names(sentence):
        if text.lower() not in allowed:
            flags.append(_flag("name", text, offset + s, offset + e))
    for text, s, e in handles(sentence):
        if text.lower() not in allowed:
            flags.append(_flag("handle", text, offset + s, offset + e))
    return nums, b, flags


def l0(draft, items, allowed):
    """Code-only pass over every sentence of the draft."""
    report = []
    item_words = [content_words(it.text) for it in items]
    for s in split_sentences(draft):
        claim = is_l0_claim(s["text"])
        entry = dict(s, claim=claim, nums=numbers(s["text"]), flags=[], bindings={"unbound": []},
                     shortlist=[it.id for it in shortlist(s["text"], items)], unverified=False)
        if claim:
            entry["nums"], entry["bindings"], entry["flags"] = claim_flags(
                s["text"], s["start"], items, allowed)
            overlap = max((len(content_words(s["text"]) & w) for w in item_words), default=0)
            entry["unverified"] = not entry["nums"] and overlap < 2
        report.append(entry)
    return report


def apply_placeholders(draft, report):
    """Swap each flagged span for its placeholder. Nothing else in the draft moves."""
    flags = sorted((f for s in report for f in s["flags"]), key=lambda f: -f["start"])
    out, last_start = draft, len(draft) + 1
    for f in flags:
        if f["end"] > last_start:
            continue
        out = out[:f["start"]] + f["placeholder"] + out[f["end"]:]
        last_start = f["start"]
    return out


# --------------------------------------------------------------------------
# L1: the questions Jev answers. The wording is frozen: changing it means
# re-running `python3 evals/run.py --suite proof --live --record`.

KIND_QUESTION = ("What kind of statement is `sentence`, as the creator would say it in their own "
                 "Instagram post or message?")
KINDS = {
    "own_record": (
        "States something the speaker did, saw, experienced, earned, lost or achieved, or "
        "something that happened to the speaker or their business: a result, an amount, a "
        "time, an event. This includes saying the speaker watched, read, liked or noticed a "
        "specific post, met or talked to someone, or shares friends, clients or events with "
        "the person they are writing to."),
    "client_result": (
        "States something that happened to, or was achieved by, a specific client, customer, "
        "student or collaborator of the speaker."),
    "outside_fact": (
        "States a fact or statistic about other people, a platform, a company or the world "
        "that could be checked against a source."),
    "advice_or_opinion": (
        "Tells the viewer what to do, or gives the speaker's belief or opinion, without "
        "stating a specific event or result."),
    "hypothetical": ("Describes an imagined, example or conditional situation, not something "
                     "that happened."),
    "ask_or_other": "A question, a call to action, a greeting, or a line that states nothing.",
}
SAME_QUESTION = "Does `proof_item` report the same event or result that `sentence` states?"
SAME_CRITERIA = {
    "true": ("The proof item describes the same event or result as the sentence, even if the "
             "sentence words it differently or leaves details out."),
    "false": ("The proof item describes a different event, client or result, or does not "
              "mention what the sentence states, even if the topic is similar."),
}
HELD_QUESTION = "Is everything that `sentence` states also stated in `proof_item`?"
HELD_CRITERIA = {
    "true": ("Every event, person, place, time and result that the sentence states is also "
             "stated in the proof item. Different wording, and a number written in words "
             "instead of digits, still count as stated."),
    "false": ("The sentence states at least one event, person, place, time or result that the "
              "proof item does not state, or states the opposite of the proof item."),
}

NEEDS_CONFIRMING = {"UNBACKED", "MISMATCH", "EMBELLISHED", "UNVERIFIED", "FLAGGED"}


def build_questions(sentences, items):
    """kind for every sentence; same and held for every sentence against its shortlist.

    The pairs are asked for every sentence, not only the claims L0 found,
    because Jev may widen the claim set and everything goes out in one
    request. Code reads only the pairs of the sentences that end up claims.
    """
    index = {it.id: j for j, it in enumerate(items)}
    q = {}
    for s in sentences:
        i = s["i"]
        q[f"kind_{i}"] = {"type": "choice",
                          "instructions": {"sentence": s["text"], "question": KIND_QUESTION},
                          "criteria": KINDS}
        for iid in (s["shortlist"] if items else []):
            j = index[iid]
            pair = {"sentence": s["text"], "proof_item": items[j].text}
            q[f"same_{i}_{j}"] = {"type": "noul",
                                  "instructions": dict(pair, question=SAME_QUESTION),
                                  "criteria": SAME_CRITERIA}
            q[f"held_{i}_{j}"] = {"type": "noul",
                                  "instructions": dict(pair, question=HELD_QUESTION),
                                  "criteria": HELD_CRITERIA}
    return q


def _load_jev():
    """The Jev client lives in this folder. None if it cannot be imported."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    try:
        import jev
        return jev
    except Exception:
        return None


def _jev_verdict(s, items, answers):
    """Status for one claim, from Jev's same/held answers and L0's number bindings."""
    if not items:
        return "UNBACKED", None, [], None, None
    index = {it.id: j for j, it in enumerate(items)}
    pairs = [(answers[f"same_{s['i']}_{index[iid]}"]["noul"], index[iid])
             for iid in s["shortlist"] if f"same_{s['i']}_{index[iid]}" in answers]
    if not pairs:
        return "UNBACKED", None, [], None, None
    same_p, j = max(pairs, key=lambda p: (p[0], -p[1]))
    held_p = answers[f"held_{s['i']}_{j}"]["noul"]
    best = items[j]
    if same_p < SAME:
        return "UNBACKED", None, [], same_p, held_p
    bound = s["bindings"].get(best.id, {"direct": [], "derived": []})
    backed = set(bound["direct"]) | set(bound["derived"])
    if any(k not in backed for k in range(len(s["nums"]))):
        return "MISMATCH", best.id, [f"your proof says: {best.text}"], same_p, held_p
    if held_p < HELD:
        if bound["derived"]:
            return "DERIVED", best.id, [f"{best.id} says: {best.text}"], same_p, held_p
        return "EMBELLISHED", best.id, [f"{best.id} says: {best.text}"], same_p, held_p
    return "BACKED", best.id, [], same_p, held_p


def check(draft, items, allowed, engine=None):
    """The whole guard: L0 always, L1 when Jev answers. One engine per report."""
    rep = l0(draft, items, allowed)
    jev = _load_jev()
    result, error = None, None
    if jev is None:
        error = "client-missing"
    elif not rep:
        error = jev.JevUnavailable("disabled", "nothing to check")
    else:
        try:
            state = {"draft": "\n".join(s["text"] for s in rep)}
            result = jev.ask_many(state, build_questions(rep, items), engine=engine)
        except jev.JevUnavailable as e:
            error = e

    sentences = []
    for s in rep:
        kind, p_claim, notes = None, None, []
        status, proof, same_p, held_p = None, None, None, None
        claim = s["claim"]
        if result is not None:
            k = result.answers[f"kind_{s['i']}"]
            kind = k["choice"]
            p_claim = k["probabilities"].get("own_record", 0) + k["probabilities"].get("client_result", 0)
            if not claim and p_claim >= CLAIM:
                # Jev widened the claim set: run the code checks on it too.
                claim = True
                s["nums"], s["bindings"], s["flags"] = claim_flags(s["text"], s["start"], items, allowed)
            if claim:
                status, proof, notes, same_p, held_p = _jev_verdict(s, items, result.answers)
            if kind == "outside_fact" and s["nums"]:
                notes.append("statistic: add a source or cut")
        elif claim:
            status = ("UNVERIFIED" if s["unverified"] else "FLAGGED" if s["flags"] else "CHECKED")
            if status == "CHECKED":
                ids = [k for k in s["bindings"] if k != "unbound"]
                proof = ids[0] if ids else None
        sentences.append({
            "i": s["i"], "text": s["text"], "claim": claim, "kind": kind,
            "p_claim": None if p_claim is None else round(p_claim, 3),
            "status": status, "proof": proof,
            "proof_text": next((it.text for it in items if it.id == proof), None),
            "numbers": [n.text for n in s["nums"]],
            "flags": s["flags"], "notes": notes,
            "same": None if same_p is None else round(same_p, 3),
            "held": None if held_p is None else round(held_p, 3),
        })

    statuses = [x["status"] for x in sentences]
    summary = {
        "backed": sum(st in ("BACKED", "CHECKED") for st in statuses),
        "derived": statuses.count("DERIVED"),
        "to_confirm": sum(st in NEEDS_CONFIRMING for st in statuses),
        "placeholders": sum(len(x["flags"]) for x in sentences),
    }
    fields = (jev.engine_fields(result, error) if jev else
              {"engine": "heuristic", "engine_reason": "client-missing", "engine_detail": None,
               "model": None, "usage": None, "requests": 0})
    if jev and result is not None:
        line = jev.engine_line(result)
    elif jev:
        line = jev.engine_line(reason=fields["engine_reason"], detail=fields["engine_detail"] or "")
    else:
        line = "engine: heuristic (client-missing)"
    return dict(fields, engine_line=line,
                evidence=[{"id": it.id, "text": it.text, "kind": it.kind} for it in items],
                sentences=sentences,
                judgments=result.answers if result is not None else {},
                summary=summary,
                exit=1 if (summary["to_confirm"] or summary["placeholders"]) else 0)


EXPLAIN = {
    "BACKED": "backed by {proof}",
    "CHECKED": "numbers and names found in your evidence; meaning not judged (heuristic)",
    "DERIVED": "a number worked out from {proof}. Check it reads right",
    "UNBACKED": "no evidence reports this. Confirm it or cut it",
    "MISMATCH": "the matching proof says something else. Use its number or cut",
    "EMBELLISHED": "says more than {proof}. Confirm the extra or cut it",
    "UNVERIFIED": "nothing in your evidence mentions this. Confirm it or cut it",
    "FLAGGED": "a number or name is not in your evidence. Confirm it or cut it",
}


def render(r, out=None):
    lines = [r["engine_line"], ""]
    claims = sum(1 for s in r["sentences"] if s["claim"])
    head = (f"PROOF CHECK  ·  {len(r['sentences'])} sentences  ·  {claims} claims  ·  "
            f"{len(r['evidence'])} evidence items")
    lines += [head, "=" * max(len(head), 62), "  evidence used"]
    if r["evidence"]:
        lines += [f"    {e['id']:<9} {e['text']}" for e in r["evidence"]]
    else:
        lines.append("    none. Every claim needs confirming: fill in ## Proof I can use in "
                     "voice.md, or say the facts in this session.")
    lines.append("-" * max(len(head), 62))
    for s in r["sentences"]:
        if not s["claim"] and not s["notes"] and not s["flags"]:
            continue
        status = s["status"] or "NOTE"
        lines.append(f"  {status:<12}{s['i']:>2}  \"{s['text']}\"")
        if s["status"]:
            lines.append(f"  {'':<16}{EXPLAIN[s['status']].format(proof=s['proof'])}")
        for n in s["notes"]:
            lines.append(f"  {'':<16}{n}")
        for f in s["flags"]:
            what = {"number": "number", "name": "name", "handle": "handle"}[f["type"]]
            lines.append(f"  {'':<16}{what} not in your evidence: {f['text']} -> {f['placeholder']}")
    lines.append("-" * max(len(head), 62))
    sm = r["summary"]
    engine = r["model"] if r["engine"] == "jev" else "heuristic"
    lines.append(f"  proof: {sm['backed']} backed, {sm['placeholders']} {{{{…}}}}, "
                 f"{sm['to_confirm']} to confirm · engine {engine}")
    if sm["derived"]:
        lines.append(f"  {sm['derived']} derived: light review")
    text = "\n".join(lines) + "\n"
    if out is not None:
        out.write(text)
    return text


def main():
    ap = argparse.ArgumentParser(description="Check a draft's claims against your own evidence.")
    ap.add_argument("draft", help="draft file, or - for stdin")
    ap.add_argument("--said", help="file with the user's own messages from this session, verbatim")
    ap.add_argument("--source", help="the user's own source material (a transcript, a post)")
    ap.add_argument("--voice", default=VOICE, help=f"voice.md (default {VOICE})")
    ap.add_argument("-o", "--out", help="write the draft with {{placeholders}} applied here")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--engine", choices=["auto", "jev", "off"],
                    help="auto (default): Jev when TYPESAFE_API_KEY is set; off: code only")
    args = ap.parse_args()

    def read(path):
        if not path:
            return ""
        if path == "-":
            return sys.stdin.read()
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    draft = read(args.draft)
    if not split_sentences(draft):
        print("nothing to check", file=sys.stderr)
        sys.exit(2)
    voice = ""
    if os.path.exists(os.path.expanduser(args.voice)):
        voice = read(os.path.expanduser(args.voice))
    else:
        print(f"note: no voice.md at {args.voice}, so no Proof evidence.", file=sys.stderr)
    items, allowed = load_evidence(voice, read(args.said), read(args.source))
    r = check(draft, items, allowed, engine=args.engine)

    if args.json:
        print(json.dumps({k: v for k, v in r.items() if k != "engine_line"}, indent=2,
                         ensure_ascii=False))
    else:
        render(r, out=sys.stdout)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(apply_placeholders(draft, [{"flags": s["flags"]} for s in r["sentences"]]))
        print(f"wrote {args.out}", file=sys.stderr)
    if args.engine == "jev" and r["engine"] != "jev":
        sys.exit(3)
    sys.exit(r["exit"])


if __name__ == "__main__":
    main()

---
name: ig-human
description: >-
  Strip the machine fingerprint out of any draft - em dashes, AI slop words,
  invisible watermark characters - and score it against a five-check detection
  panel before it goes out. Use whenever text needs to sound human, when the
  user says humanize, "does this sound like AI", "remove the em dashes",
  "de-slop this", "this sounds like ChatGPT", or before any caption, script,
  comment, reply or DM is shown to the user.
---

# ig-human

Three tools live in this folder and they all actually run. Use them. Do not
eyeball this.

```bash
python3 proofcheck.py draft.txt --said said.txt   # every claim against the user's own evidence
python3 humanize.py draft.txt --report        # clean it, show what changed
python3 detect.py draft.txt                    # score it, five checks
python3 detect.py before.txt after.txt         # prove the delta
```

Both read `slop.json`: 154 stock words and phrases with plain-English
replacements, 18 invisible character classes, 11 typographic substitutions and
16 structural tells. The last block of each list is Instagram-specific, the
vocabulary that only shows up in captions and voiceovers. It is meant to be
edited. If the user has a word they always use that the lexicon strips, take it
out of the file.

## Why this matters more on Instagram than it looks

Captions are short and scripts get said out loud. A written-sounding line in a
600-character caption is a larger share of the text than the same line in an
essay, and a voiceover that nobody could say naturally is obvious in the first
take. The tell here is not a detector flagging the post. The tell is a person
scrolling past something that reads like a brand, or a creator stumbling over
their own script.

## Step 0: the proof guard

Before anything else, check that the draft says nothing the user did not give
you. Invented numbers, clients, results or shared history are the one failure
that a clean score cannot fix.

```bash
python3 proofcheck.py draft.txt --said said.txt [--source source.txt] [-o fixed.txt]
```

- **Evidence is only four things:** the bullets under `## Proof I can use` in
  `~/.claude/instagram/voice.md`, the name and handle under `## Who I am`,
  what the user said in this session, and the user's own source material
  (`--source`, for `/ig-repurpose`). Comments, DMs they received and other
  people's words are never evidence.
- **`said.txt` is the user's own messages from this session, copied word for
  word**, one per line, into a temporary file. Never paraphrase them and never
  add anything the user did not type.
- **What the statuses mean and what to do:**

  | status | meaning | do |
  | --- | --- | --- |
  | BACKED / CHECKED | traced to one piece of evidence | keep |
  | DERIVED | a number worked out from the proof (5 hours to 20 minutes is "15 times faster") | keep, and read it once |
  | UNBACKED | no evidence reports it | ask the user, or cut it |
  | MISMATCH | the matching proof says a different number | use the proof's number, or cut it |
  | EMBELLISHED | says more than the proof does | ask about the extra, or cut it |
  | UNVERIFIED | offline, and nothing in the evidence mentions it | ask the user, or cut it |
  | FLAGGED | offline, a number or name is not in the evidence | ask the user, or cut it |

  Never "fix" a flag by inventing a better-sounding fact. `-o` writes the
  draft with `{{your number}}` and `{{client name}}` in place of exactly the
  flagged spans; that is the safe version to show.
- **The first line says which engine decided.** `engine: jev-1.13.0 (...)`
  means TypeSafe's Jev model read the sentences; `engine: heuristic (...)`
  means only the code checks ran (no key, offline, or `IG_JEV=off`). The
  thresholds are provisional. Never compare results across engines.
- **Stop after two rounds.** Rewrite, re-run once. If flags remain after the
  second run, show them to the user with the draft and let them decide.

## What gets fixed automatically

**1. Invisible characters.** Zero-width spaces and joiners, word joiners, soft
hyphens, byte-order marks, Unicode tag characters, invisible separators,
non-breaking and narrow spaces. A keyboard does not produce these. They survive
copy-paste, they are invisible in every editor, and they are the most
mechanical thing in generated text. `humanize.py` deletes every one, including
any remaining Unicode format character it does not have a name for.

**2. Typography.** Em dash to comma, en dash to hyphen, curly quotes to
straight, ellipsis to three dots, bullet character to hyphen. The em dash pass
is the one that matters: it collapses the dash to a comma and then cleans up
the double punctuation and orphaned periods that leaves behind.

**3. The slop lexicon.** delve, leverage, robust, seamless, crucial, testament
to, "in today's fast-paced world", plus the Instagram block: "stop scrolling",
"in today's video", "follow for more", "tag someone who needs this", "the
algorithm loves", "run don't walk". Each swapped for a plain word or deleted,
with capitalisation preserved and URLs left untouched.

## What does NOT get fixed automatically

Structural tells get **flagged, not rewritten**, because changing the shape of
a sentence needs judgement:

- "It's not just X, it's Y" and "not only X but also Y"
- Rule-of-three triads
- Rhetorical one-word question lines: "The result?"
- The video preamble: "in this video I'm going to show you"
- Emoji bullet lists
- Three or more shouted words in a row
- Hashtag walls
- Reflex bait: "follow for more", "tag someone who", "double tap if"

That list is your job. Rewrite each flagged line by hand, keeping the meaning,
then re-run `detect.py`. This is the part that moves the score from REVIEW to
PASS, and it is the part a script cannot do.

## The five checks

`detect.py` scores five signals 0-100, higher is more human:

| check | what it measures | machine looks like |
| --- | --- | --- |
| BURSTINESS | sentence-length variation | every sentence the same length |
| SPECIFICITY | numbers, names, concrete markers per 100 words | abstract nouns, no figures |
| SLOP DENSITY | lexicon hits per 100 words | stock vocabulary |
| FINGERPRINT | invisible chars, em dashes, curly quotes per 1k chars | typographically perfect |
| VOICE | contractions, person, structural tells | no contractions, staged reveals |

The verdict weights the mean at 60% and the **weakest single check** at 40%,
because one signal is enough. PASS needs an overall of 70+ with no check
below 55.

## Say this honestly

These are five local heuristics modelled on the signals public detectors key
on. They run entirely on the user's machine and nothing is uploaded. (The
proof guard is different: with Jev on, it sends the draft's sentences and the
evidence it is checked against to TypeSafe. The README lists exactly what
leaves the machine.) They are
**not** GPTZero, Originality, Copyleaks, Winston or Turnitin, they do not call
those APIs, and they cannot promise those verdicts. Fixing what they measure
does tend to move those numbers, because they are measuring the same underlying
things. That is the claim. Do not make a bigger one on the user's behalf, and
do not tell a user their text is undetectable.

## Order of operations

0. `proofcheck.py draft.txt --said said.txt`, and resolve every flag with the
   user (two rounds at most, see Step 0).
1. `humanize.py draft.txt -o clean.txt --report`
2. Read the structural flags. Rewrite those lines yourself.
3. `detect.py draft.txt clean.txt` to show the before and after.
4. If the verdict is not PASS, fix the weakest check named in the output and go
   again. Two rounds is normal. Five means the draft was written by formula,
   and the fix is a different draft, not more passes.
5. Show the user the cleaned text and the score. Never the score alone.

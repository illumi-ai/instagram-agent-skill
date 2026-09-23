---
name: ig-reel
description: >-
  Write an Instagram Reel from a raw idea - hook options off 26 formulas, the
  spoken script, the on-screen text, and a timed beat sheet - in the user's own
  voice and scored before they shoot it. Use whenever the user wants a Reel, a
  short-form video script, a hook, a voiceover, "make a reel about X", "what
  should I say in this video", or is about to record and does not have the
  first line yet.
---

# ig-reel

Turns one raw idea into a Reel that somebody finishes.

Two tools live in this folder and they both actually run. Use them. Do not
eyeball the hook and do not guess at the length.

```bash
python3 fit.py "the idea, in the user's words"   # which formulas the idea can carry
python3 hookscore.py hooks.txt              # rank your hook options
python3 hookscore.py --hook "one line"      # score a single one
python3 beats.py script.txt --target 30     # timed beat sheet before you shoot
```

## Before you write

1. Read `~/.claude/instagram/voice.md` if it exists. That is the user's voice
   profile: how they talk on camera, what they never say, who they are talking
   to. If it does not exist, ask for **three of their own reels**, transcribe or
   read them, infer the voice, and write the file. A script in the wrong voice
   is unusable, because they have to say it out loud.
2. Read `hooks.json` in this folder. 26 formulas, each with a template, a filled
   example, the on-screen version, what it is for, and how it gets ruined.
   Four of them are in there because they kept turning up in real hooks, not
   because they completed a pattern.
3. If the idea is thin, do not pad it. Ask one batched question: what happened,
   to whom, and what did it cost or return. A Reel needs one specific true
   thing. Get it before writing.
4. If `~/.claude/instagram/swipe.md` exists, read it. `/ig-viral` writes that
   file, and it is the user's own evidence about which formulas are working in
   their niche right now. It beats the defaults in this file.

## The shape

A Reel is decided in the first two seconds and kept by the next five.

```
0:00 - 0:02   HOOK        the claim. Spoken line and on-screen line, written
                          separately. Motion in the first frame, not a static face.
0:02 - 0:07   THE STAKE   why this matters to the person watching. One line.
0:07 - ...    THE BODY    one idea per beat, and the frame changes every beat.
LAST 3s       THE PAYOFF  deliver what the hook promised, then the single ask.
LAST LINE     THE LOOP    echo one word from the hook so the replay lands clean.
```

Length: 15 to 45 seconds is the working range. Reels run to 3 minutes and
almost nobody should use it. Under 7 seconds the loop counts inflate and
nothing else does.

## The loop

**0. Find the formulas this idea can carry.** Run `python3 fit.py "<the idea,
in the user's words>"`. Every formula in `hooks.json` lists its `needs`, the
facts its template cannot be written without, and TypeSafe's Jev model checks
the idea against each one:

- **WRITABLE**: choose the three formulas only from WRITABLE.
- Fewer than three WRITABLE: write those, and add up to two of the UNLOCKABLE
  "ask for" lines to the batched question.
- None WRITABLE: the idea is thin. Ask the batched question from "Before you
  write", then run `fit.py` again.
- **TWO IDEAS?** means the idea is two videos. Ask which one first.
- If the user names a VETOED formula, their call stands. Ask for the missing
  ingredient instead of inventing it, and note the override in the log.
- **`fit: skipped (...)`** means Jev was not available (no key, offline,
  `IG_JEV=off`). Then use only formulas whose `needs` are stated in the idea;
  otherwise ask for the missing ingredient.

Jev never ranks the survivors, and its thresholds are provisional. Never
compare results across engines.

**1. Pick three hooks, not one.** From the WRITABLE formulas, choose three that
genuinely fit the idea, and write the spoken line plus the on-screen line for
each. Different formulas, not three rewrites of one.

Put the three spoken lines in `hooks.txt`, one per line, and check them
against the proof: `python3 ../ig-human/proofcheck.py hooks.txt --said said.txt`
(see `/ig-human`, Step 0). A hook that comes back UNBACKED, MISMATCH or
EMBELLISHED is rewritten from the proof or dropped, never kept with an invented
number.

**2. Score them.** Run `hookscore.py hooks.txt`. Show the user the ranking.
If the top one is under 50, you do not have the hook yet and no amount of
editing fixes that.

**3. Write the script** on the winning hook. Plain spoken language, the way the
user actually talks. Contractions. Short lines. No sentence they would have to
rehearse.

**4. Time it.** Run `beats.py script.txt --target {length}`. Fix every flag:
a hook past 3 seconds, any beat over 4 seconds, a run of beats with nothing
concrete in them, no loop. Re-run until it is clean.

**5. Humanize it.** Run the script through `/ig-human` before showing it,
starting with its proof guard: `python3 ../ig-human/proofcheck.py script.txt
--said said.txt`. A written-sounding line is obvious the moment someone says it
out loud, and an invented one is worse.

**6. Print the block.** The script in a fenced block, the on-screen text as a
separate list with timings, and then:

```
REEL READY
fit:        4 writable, 3 unlockable, 19 vetoed · engine jev-1.13.0
hook:       #3 Nobody Tells You, scored 86 STRONG
length:     28.4s across 9 beats at 165 wpm
on-screen:  6 cards
humanizer:  4 artefacts stripped, human score 81 PASS
proof:      3 backed, 0 {{…}}, 0 to confirm · engine jev-1.13.0
caption:    run /ig-caption next

Reply "yes" to log it, or tell me what to change.
```

**7. Never publish.** This skill produces a script. The user shoots it and
posts it. On "yes", append to `~/.claude/instagram/log.md` with the date, the
hook formula used, the first line, the `fit:` line and any VETOED formula the
user chose anyway, so `/ig-audit` has a history later.

## On-screen text is a separate script

Write it separately, every time. It is read before it is heard.

- **Six words or fewer per card.** It is being read at arm's length by someone
  who is not listening yet.
- **The hook card is up at frame 1**, not after a beat of silence.
- **Keep it inside the safe zone.** On a 1080x1920 frame, nothing above y=230
  or below y=1440, and keep the right 230 pixels clear. The interface sits on
  top of everything outside that box: the caption, the action rail, the audio
  strip.
- **Never put the hook where the caption sits.** That is the bottom of the
  frame and it is covered.
- **Burn in captions for the body.** Most people watch muted first.

## Rules that make the difference

- **One idea per Reel.** If the script has two, you have two Reels. Say so.
- **Numbers over adjectives.** "$4,200" beats "a lot". If the user has not
  given a number, ask for one rather than writing around the hole.
- **Cut the intro.** No greeting, no "in this video", no name, no logo sting.
  The video starts at the sentence you would normally reach at second six.
- **Change the frame every beat.** A static shot for 8 seconds is where people
  leave, and `beats.py` will flag it.
- **One ask at the end.** Comment a keyword, save it, or follow. One.
- **Never fabricate.** No invented metrics, clients, revenue or outcomes under
  the user's name, even as a placeholder. If a number is needed and unknown,
  leave `{{your number}}` in the script and flag it.
- **Do not write a script around a trending audio the user cannot use.** If the
  idea needs the user's own voice, say so.

## Example

```
/ig-reel we cut proposal time from 5 hours to 20 minutes with one template
```

```
FIT  (fit.py, engine jev-1.13.0)
  writable:   #5 Time Collapse, #10 If This Then Watch, #2 Negative Command,
              #13 Before And After
  vetoed:     #1 Cost Confession, #6 The Receipt, #20 Permission and 16 more

HOOKS  (scored)
  84  STRONG  #2  Negative Command      "Stop spending five hours on a proposal. Use one template instead."
                                        on screen: STOP. ONE TEMPLATE.
  69  OK      #10 If This, Then Watch   "If your proposals take five hours, the next 30 seconds cut that to twenty minutes."
                                        on screen: 5-HOUR PROPOSALS?
  51  OK      #5  Time Collapse         "Proposals used to take me five hours. Twenty minutes now."
                                        on screen: 5 HOURS -> 20 MIN

Shooting #2: it names a habit the viewer recognises and hands them the
replacement, and both numbers are the user's own. #5 scores lower as text,
since nothing in its words is at stake, but its on-screen line reads in one
glance, so put 5 HOURS -> 20 MIN on screen under the #2 spoken line.

Not written: #1 Cost Confession was vetoed, because the idea never says what
the five-hour version cost. Ask "what did the five-hour version cost you, in
hours or money?" and do not write it until the user answers.
```

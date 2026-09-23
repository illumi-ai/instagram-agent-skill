# Eval report

- model: `jev-1.13.0`
- date: 2026-09-23
- command: `python3 evals/run.py --suite all --live --record --report`
- replay: `python3 evals/run.py --suite all` reproduces these numbers from `evals/recorded/` without the network

**Smoke test, not a benchmark.** Every suite is small and was written and labelled by the agents that built these features (`provenance` in each suite file). The thresholds in the scripts are provisional until real, human-labelled data exists.

What these numbers do not show: accuracy on real creators' drafts, hooks or captions; stability across runs (the probes measured drift of up to 0.14 on a 0-2 scale); or any effect on views. "On by default" below applies the spec's rule (a feature whose gate fails ships switched off). It is not a claim that the feature is right on your data.

## formula

- items by provenance: repo 26, probe-synthetic 41
- requests: 66, input tokens: 137,126, cost at recording: $0.0058
- complete (every answer from Jev): yes
- note: The regex in hooks.json was tuned with the 26 w* stress hooks in view, so the regex column on that set is not held out.

| metric | value |
| --- | --- |
| canonical_jev_right | 26 |
| canonical_n | 26 |
| canonical_counted_wrong | 0 |
| stress_n | 37 |
| stress_counted | 22 |
| stress_counted_wrong | 0 |
| stress_counted_wrong_ids | - |
| stress_named_coverage | 0.815 |
| stress_jev_pick_accuracy | 0.946 |
| stress_regex_accuracy | 0.676 |
| traps_counted | - |
| trap_statuses | {'h01': 'TENTATIVE', 'h02': 'TENTATIVE', 'h12': 'READ'} |
| tracked | {'h11': 'AGREE Cost Confession'} |

| gate | result |
| --- | --- |
| canonical Jev picks >= 24/26 (leave-one-out) | pass |
| 0 wrong ids at a counted status on the stress set | pass |
| no trap counted | pass |

**Decision:** on by default.

## proof

- items by provenance: repo 41, probe-synthetic 10
- requests: 51, input tokens: 93,051, cost at recording: $0.0039
- complete (every answer from Jev): yes
- note: flag: the guard should ask the user; ok: it should not; note: outside fact, a NOTE and no flag
- note: Most labels (repo) were written while building this suite, some of them after seeing a live proofcheck run on the reel case; one ambiguous reel line and one DM line were left out rather than labelled. Only the fab_* items carry labels from the probes.

| metric | value |
| --- | --- |
| n | 51 |
| flag_n | 26 |
| ok_n | 25 |
| recall_l0 | 0.538 |
| recall_l0_l1 | 1.0 |
| false_positive_l0 | 0.0 |
| false_positive_l0_l1 | 0.04 |
| missed_by_l0_l1 | - |
| false_positives_l0_l1 | ['dm1'] |
| notes_on_outside_facts | ['s10'] |

| gate | result |
| --- | --- |
| recall of L0+L1 above L0 | pass |
| false positives <= 0.25 | pass |

**Decision:** on by default.

## fit

- items by provenance: repo 13
- requests: 13, input tokens: 70,270, cost at recording: $0.0029
- complete (every answer from Jev): yes
- note: must_write: formulas whose needs the idea plainly states; must_veto: formulas whose needs it plainly lacks. Written for this suite (repo), not blind.
- note: Ten of the ideas come from the probes and three were written here, but every must_write and must_veto label was written for this suite, so none of it is blind.

| metric | value |
| --- | --- |
| ideas | 13 |
| veto_recall | 1.0 |
| not_writable_rate_on_must_veto | 1.0 |
| must_write_writable | 1.0 |
| false_veto_rate | 0.0 |
| multi_idea_accuracy | 0.923 |
| misses | - |

| gate | result |
| --- | --- |
| report only | pass |

**Decision:** on by default.

## caption

- items by provenance: probe-synthetic 24
- requests: 24, input tokens: 18,389, cost at recording: $0.0008
- complete (every answer from Jev): yes

| metric | value |
| --- | --- |
| n | 24 |
| ask_accuracy_jev | 1.0 |
| ask_accuracy_regex | 0.333 |
| type_accuracy_jev | 1.0 |
| type_accuracy_regex | 0.188 |
| jev_wrong | - |

| gate | result |
| --- | --- |
| report only | pass |

**Decision:** on by default.

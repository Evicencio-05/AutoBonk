---
name: proposal
description: Research and write an AutoBonk execution proposal for the operator to decide. Use for the weekly proposal run, a daily safety note after something broke, or whenever the operator asks for a proposal, a rule change, or "what should we change". Produces learning/proposals/YYYY-MM-DD-slug.md from the ledger, bench, and broker data.
---

# Writing an AutoBonk proposal

The operator does the TA and makes the decisions. You do the research and the data work, then write a proposal they can decide in ten minutes. A proposal argues for a change. It changes nothing by itself: no checker code, no settings, no bless, no orders.

## Two kinds

| Kind | When | Changes a replayed decision? | Ships |
|---|---|---|---|
| `decision` | the weekly run (Friday after the close), or when asked. A `waiting` one is re-tested every weekly run | yes: entries, exits, skips, sizing, contract choice | only after the operator accepts it at the weekly review, then `freeze.py bless` by the operator |
| `safety` | a day an alarm fired, a check crashed, or an exit failed | no: a crash, a retry, an alert, routing plumbing | any day, once the operator accepts it |

If you are not sure, it is `decision`. Never label a decision change `safety` to get it in sooner.

## Steps

1. **Gather the data.** Run `python3 scripts/proposal_data.py` (add `--offline` if the broker is unreachable). Read the pack it writes in `learning/proposals/data/`: ledger totals, cuts, freeze progress, skips, alarms, and the open and decided proposals. Then read `learning/proposals.md` and every open file in `learning/proposals/`, so you never repeat a proposal or reopen a rejected one without new evidence.
2. **Re-test what is waiting.** For every proposal with `status: waiting`, re-run its test on the data that came in since. Add a dated "Update" section under Evidence with the new numbers. Revise the recommendation if the evidence moved, and say whether it has reached the sample it asked for. When it has, set `status: open` so the operator decides it at this week's review. Do this before writing new proposals.
3. **Find the problem worth solving.** Rank the candidates by dollars at stake times how often they happen. A good candidate is a repeated loss pattern, a gap between live and what-if, an execution leak (slippage, fill lag, failed exits), or something the operator flagged in "What I saw that the checker did not" or in "Would I take it" answers that disagree with the checker. Pick one per proposal. On a weekly run, write at most two `decision` proposals.
4. **Research it.** Use the tools that exist rather than eyeballing:
   - `python3 scripts/bench.py compare ...` on every fixture day for a setting change;
   - the ledger rows, cited by `ref`, for what each affected trade did and would have done;
   - `python3 scripts/entry_timing.py --options` for timing questions;
   - broker option bars (`RobinhoodBroker.option_bars`) for what a contract was worth at a moment;
   - the `backtest-expert` skill for robustness and overfitting checks.

   Test at least one alternative against the proposal. Count how many trades the evidence rests on.
5. **Judge the evidence honestly.** State the sample. Under 10 affected trades is an anecdote. Under 30 is suggestive, not proven. Say whether a few trades drive the whole result, and what the result would be without the best one. If the evidence is not there yet, write the proposal anyway with **Recommendation: wait**, and say how many more trades would settle it.
6. **Write the file** from the template below, as `learning/proposals/YYYY-MM-DD-short-slug.md`. Then add one line under Open in `learning/proposals.md`.
7. **Do not implement it.** Implementation happens only after the operator marks it accepted, in a separate step: a setting with an off switch, tests, the freeze check, and the operator's bless.

## Template

```markdown
---
title: <the change, as a sentence>
kind: decision | safety
status: open
created: YYYY-MM-DD
recommendation: accept | wait | reject
---

# <title>

## Summary
Two or three sentences: what changes, why, and what you recommend.

## The problem
What went wrong, in dollars, with ledger refs (`1023-1100-GOOGL-put`). How often it happens.

## The change
Exactly what the checker would do differently. The setting name and its off value.

## Evidence
- Sample: N live trades, N what-if signals, N fixture days.
- Results with and without the change: live $, what-if $, stock points on fixtures.
- Trade by trade, for every trade it would have changed.
- Without the single best trade, the result is ...
- How much luck could explain it.

## Expected impact
A range in dollars per trade or per week, and your confidence: low, medium, or high.

## Risks
What it could break or block, including winners it would have skipped.

## Alternatives considered
What else you tested, the numbers, and why it lost.

## How we will know
Success criteria fixed now, judged on the next N trades after it ships. What result would make us roll it back.

## Rollout and rollback
The setting, the tests, `freeze.py bless` by the operator, and how to turn it off.

## Operator decision
Decision: <!-- accept / reject / wait -->
Notes:
```

## Rules

- **Option dollars decide.** Stock points are supporting evidence only.
- **Every number traces to a file or a command** the operator can re-run.
- **Never edit** `config/freeze.yaml`, `bench/golden/`, the checker's tapes, or `rules/ta_rules.md`. Never fill the Operator decision section.
- **Plain English, short sentences.** The operator is a trader, not a programmer.
- **A safety note** may skip Expected impact and Alternatives when there is no trade-off. It still needs The problem, The change, Risks, and How we will know.

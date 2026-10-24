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
| `automation` | the weekly run, from `learning/automation/latest.md` | no: a script takes over repeated agent work | once the operator accepts it, with tests |

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
5. **Run a pre-mortem** with the `premortem` skill: up to five ways the proposal is wrong or the change breaks something, each with a check you ran. A check that undercuts the proposal changes the recommendation. It is not hidden in Risks.
6. **Judge the evidence honestly.** State the sample. Under 10 affected trades is an anecdote. Under 30 is suggestive, not proven. Say whether a few trades drive the whole result, and what the result would be without the best one. If the evidence is not there yet, write the proposal anyway with **Recommendation: wait**, and say how many more trades would settle it.
7. **Write the file** from the template below, as `learning/proposals/YYYY-MM-DD-short-slug.md`. Then add one line under Open in `learning/proposals.md`.
8. **Do not implement it.** Implementation happens only after the operator marks it accepted, in a separate step: a setting with an off switch, tests, the freeze check, and the operator's bless.

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

## How this could be wrong
The pre-mortem table: up to five ways, most likely times most costly first, each with the check and its result.

| # | How it fails | Likelihood × cost | Check | Result |
|---|---|---|---|---|

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

## Automation proposals

The weekly run starts with `python3 scripts/automation_audit.py`, which needs no model. Read `learning/automation/latest.md`. A candidate is a kind of task or a command recipe with 3 or more prompts in 14 days, or 50k fresh tokens or more. Skip anything already scripted unless the agent is still doing the scripted part by hand. Write at most one automation proposal a week.

The operator's rule: **if the agent's benefit is much greater than its cost, keep the agent. Otherwise script what can be scripted.** Apply it like this:

1. **Split the task into its parts.** A part is *mechanical* when the same inputs always give the same output: parsing, copying numbers, running fixed commands, waiting on CI, formatting, totals. A part is *judgment* when it reads images, weighs new evidence, debugs something new, or writes something the operator decides on.
2. **Price both sides.** The cost is fresh tokens per run times runs per month, from the audit. The benefit is what the judgment parts catch or add that a script would miss, counted as errors avoided or dollars at stake, with an example from the transcripts or the ledger.
3. **Decide.**
   - **Keep the agent** when most of the task is judgment, or when a script's mistake could change a live order, the book, or a decision the operator reads, and nothing would catch it first. The cost of one error is much larger than the tokens.
   - **Script it** when it is mostly mechanical and the script can check its own output: tests, validation, holds, and a short summary the operator reads.
   - **Split it** when it is both. The script does the mechanical part and prints a short summary, and the agent does only the judgment. `levels_ingest.py arm` plus reading the charts is the model.
   - **Leave it** when it is rare (under once a week) and cheap. Building and keeping the script costs more than it saves.
4. **Show the break-even**: tokens saved per month against building the script once (about one session) and keeping it.

An automation proposal uses the same template. "The change" names the script, its commands, and what the agent still does. "Expected impact" is in tokens per month and operator minutes, not dollars of P&L. Never propose a script that places orders, edits the guard, blesses, or writes a checker tape. A script that writes the book or checker state needs the same holds and tests as `levels_ingest.py`.

## Rules

- **Option dollars decide.** Stock points are supporting evidence only.
- **Every number traces to a file or a command** the operator can re-run.
- **Never edit** `config/freeze.yaml`, `bench/golden/`, the checker's tapes, or `rules/ta_rules.md`. Never fill the Operator decision section.
- **Plain English, short sentences.** The operator is a trader, not a programmer.
- **A safety note** may skip Expected impact and Alternatives when there is no trade-off. It still needs The problem, The change, Risks, and How we will know.

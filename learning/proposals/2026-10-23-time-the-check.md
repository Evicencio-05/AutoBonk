---
title: Time every step of the 10-minute check, so we can find what delays entry orders
kind: safety
status: open
created: 2026-10-23
recommendation: accept
---

# Time every step of the 10-minute check, so we can find what delays entry orders

## Summary
Every Friday check that found an entry took 4 to 6 minutes; every check without one took about 5 seconds. Those minutes sit between the signal and the order on a 0DTE contract. We do not know which step costs them, and the obvious suspect turned out not to be it. I recommend logging how long each step of every check takes, for one week, then writing the fix as its own proposal with the numbers in hand. This changes no decision.

## The problem
- Checker runs on 2026-10-22 and 2026-10-23: 97 total. The 9 that found an entry took **157 to 353 seconds** (median about 300). Runs with output but no entry took 3 to 13 seconds. Source: `journalctl --user -u autobonk-claims.service`, start to finish per run.
- In those runs the order is routed in `publish()`, after the contract pricing, the sellout lookups, and the open-contract marks for that check. So the delay lands before the order, not after it.
- **What it is not:** pricing the contract ladder. Re-pricing Friday's GOOGL put and AVGO call signals with the same code took 0.6s and 0.8s (12 and 16 option requests). I said earlier in `learning/proposals.md` that the ladder was the delay. That was a guess, and it was wrong.
- **What it could be** (unmeasured): rate-limit waits on Yahoo during market hours, which the after-hours re-price could not reproduce; the broker sellout and late-close lookups per open contract (`stamp_sellouts`); 10-day option histories pulled for every open contract's mark (`apply_contract_exits`, `refresh_contract_marks`); or the dashboard rebuild.
- **Cost, roughly:** on Friday's 8 signals, buying 5 minutes later than the fill-bar close cost a further $9 in option dollars (−$197 to −$206; `scripts/entry_timing.py --options`). That is small and mixed in sign on 8 trades. But it adds up on every entry, and the delay is the wrong direction for 0DTE premiums.

## The change
- Wrap each step of `check()` in a timer: bars per ticker, replay, pricing, sellouts, exits, settle, routing, the tapes, the dashboard, retries, and the audit.
- Write one line per check to `alerts/check_times.jsonl`: total seconds, each step's seconds, and the number of option and broker requests.
- Add a "Check speed" line to the daily review draft: the median and the slowest check, and the slowest step on entry checks.
- No order, entry, exit, or skip changes. The freeze check will show no moved decision.

## Evidence
- 97 checks across 2 live days, 9 with an entry, all slow. 54 checks with output and no entry, all fast.
- The re-price measurement above, taken from two real Friday signals.
- That is enough to say the delay exists and follows entries. It is not enough to say which step causes it, so this proposal measures instead of guessing.

## Risks
- A timer that throws could break a check. It will be wrapped so a timing failure is ignored.
- One more small file in `alerts/`. It is gitignored like `state.json`.

## How we will know
- After 5 sessions, the daily reviews name the slowest step on entry checks.
- Then a follow-up proposal: move that step after the order, or make it faster.
- Success for that follow-up: entry checks route their order within 30 seconds of starting.

## Rollout and rollback
- A safety change: tests, plus `freeze.py check` showing no moved decision. It can ship as soon as you accept it.
- Rollback: delete the timer lines. Nothing reads the file except the review.

## Operator decision
Decision: <!-- accept / reject / wait -->
Notes:

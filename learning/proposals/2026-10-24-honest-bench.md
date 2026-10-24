---
title: Score replayed entries where the checker can actually buy
kind: decision
status: accepted
created: 2026-10-24
recommendation: accept
---

# Score replayed entries where the checker can actually buy

## Summary
The bench filled each entry at the fill bar's open, while still knowing whether that bar closed back through the level. That price is not reachable. The checker buys after the fill bar closes. The bench now fills at that close and prices the contract at the same moment, so replays and proposals stop flattering the rules. Accepted by the operator 2026-10-23.

## The problem
- `scripts/entry_timing.py` showed the bench's own fill scoring −0.72 stock points over the fixture days, against −3.21 for the live process.
- That 2.5-point gap made every replay look better than live trading could be.

## The change
- A new setting, `entry_price`, with the default `close`. A replayed entry fills at the fill bar's close, and its contract is priced at that close (`fill_at` on the event).
- `open` keeps the old price for comparisons.
- The chase and reclaim checks are unchanged, so the same entries are taken.

## Evidence
- Fixture net, all days: `open` −0.72, `close` −3.21. That is the live process's own number from the timing study.
- The freeze diff moves only entry fills. No entry, exit, or skip appears or disappears on any of the 4 fixture days.
- Tests that pinned old numbers moved by 0.05 points each (−0.75 to −0.80, 5.55 to 5.50, 4.75 to 4.70).

## Expected impact
No live trading change. Replays, recaps, and proposals lose about 0.13 points per trade of optimism.

## Risks
Live plan rows now price the contract at the fill bar's close instead of its open. That is closer to what the order pays, but what-if dollars from before and after this change are not exactly comparable.

## Alternatives considered
Leaving the bench as it was and correcting by hand in each proposal: easy to forget, and wrong by default.

## How we will know
Re-run `entry_timing.py`. Its "model" and "confirm" rows should now agree.

## Rollout and rollback
Shipped with the operator's `freeze.py bless` (the golden fills move). Roll back by setting the `entry_price` default to `open` and blessing again.

## Operator decision
Decision: accept
Notes: Accepted 2026-10-23 ("add 5").

---
title: Wait for a fresh retest after a stop at the same level
kind: decision
status: accepted
created: 2026-10-23
recommendation: accept
---

# Wait for a fresh retest after a stop at the same level

## Summary
After a reclaim stop at a level, the checker skipped nothing and re-entered the chop at that level. This rule waits until price has left the level by one ATR before entering there again. Accepted and shipped on 2026-10-23, before the freeze started (PR #19).

## The problem
On Friday, `1023-1050-AVGO-put`, `1023-1100-GOOGL-put`, and `1023-1120-AVGO-call` were entries #2 and #3 at a level after a stop. They made −$19 (what-if), −$12, and −$3.

## The change
After a reclaim stop at a level, the next entry there is skipped with reason `fresh`. The skip lasts until a finished 10-minute bar has traded one 14-period ATR away from the level, on either side. The `fresh_atr` setting is 1.0; 0 turns it off. The memory resets each session.

## Evidence
- Only 2026-10-23 changes on the fixtures. The rule skips the AVGO 10:50 put and the 11:20 call.
- It keeps the GOOGL 11:00 put, because price fell more than an ATR under 322.75 before retesting it. That trade reached +$49.
- Stock points that day went from −12.64 to −11.11.
- One day of evidence. You accepted it as a rule of the frozen sample, not as a proven edge.

## Alternatives considered
A hard cap of one or two entries per level per day; doubling the ATR band once a level has flipped twice; only taking the flipped side after a stop.

## How we will know
At the weekly review, compare the `fresh` skips' what-if dollars with the entries made after a real leave. If the skips would have won more than the allowed entries over 15 or more re-entries, reopen this with the alternatives.

## Rollout and rollback
Shipped. To roll back, set `FRESH_ATR = 0` in the checker, then run `freeze.py bless` yourself.

## Operator decision
Decision: accept
Notes: Accepted 2026-10-23 and blessed.

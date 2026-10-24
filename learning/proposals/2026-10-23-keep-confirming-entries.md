---
title: Keep confirming each entry on the fill bar; do not switch to sending on the signal
kind: decision
status: waiting
created: 2026-10-23
recommendation: accept
---

# Keep confirming each entry on the fill bar; do not switch to sending on the signal

## Summary
I tested whether sending the order as soon as the signal bar closes beats today's process of waiting one bar to confirm it. On the data we have there is no reliable difference, so I recommend keeping today's process and re-testing at each weekly review. The test also showed the bench scores entries about 0.13 points better than either real process can get. That should be fixed in a later proposal, so replays stop flattering the rules.

## The problem
The checker waits for the bar after the signal (the fill bar) to finish, checks that it did not chase or close back through the level, and only then buys. That is about 10 minutes after the signal, plus however long the check takes. Sending on the signal would buy roughly 10 minutes sooner, but it would also own the trades the fill bar would have rejected.

## The change
None. This proposal asks you to confirm today's process. The alternative tested was **asap**: buy at the fill-bar open; if the fill bar closes back through the level, sell at that close.

## Evidence
Run it yourself with `python3 scripts/entry_timing.py --options`.

| Process | Stock points, 4 fixture days | Option $, 2026-10-23 (8 trades) |
|---|---|---|
| Confirm (today) | −3.21 | −$197 |
| Confirm, 5 minutes later | n/a | −$206 |
| Asap | −2.91 | −$178 |
| Bench model (not achievable) | −0.72 | n/a |

- Sample: 19 trades plus 2 reclaimed fill bars on fixtures, and 8 priced trades on Friday.
- Asap was +0.13 points per trade on fixtures, but the 2 fill bars it would have owned cost −2.18 points.
- In option dollars asap won 4, lost 3, and tied 1. One TSLA trade (−$28 vs −$59) is more than its whole edge. Without it, asap trails confirm by $12 over 7 trades (−$150 vs −$138).
- Luck can explain a gap this size on this many trades.

- **Update 2026-10-23:** the bench now fills at the fill-bar close (`2026-10-24-honest-bench.md`), so the "Bench model" row equals "Confirm" from here on.

## Expected impact
Keeping confirm: none, by definition. Switching to asap: somewhere between −$5 and +$5 per trade on this evidence. Low confidence either way.

## Risks
- Keeping confirm: if asap really is better, we give up a few dollars a trade until a re-test shows it.
- Switching now would change a decision during the freeze on 8 trades of evidence, which is what the freeze exists to prevent.

## Alternatives considered
- **Asap:** tested above.
- **Confirm, but faster:** buy as soon as the fill bar closes. That is the check-timing proposal (`2026-10-23-time-the-check.md`). It keeps the confirmation and only removes the waiting.

## How we will know
Re-run `entry_timing.py --options` at each weekly review on all live days. Revisit asap only if it leads by more than $3 per trade over 30 or more live trades.

## Rollout and rollback
Nothing to roll out. A later proposal will score bench entries at the fill-bar close instead of its open. That one moves golden fills, so it will need your bless.

## Operator decision
Decision: wait
Notes: 2026-10-23. Keep today's process while live trades come in. Claude re-runs the comparison at each weekly review and updates this proposal; decide when the evidence is there (30+ live trades).

# Daily review

The after-close timer (`autobonk-close.timer`, 13:20 PT) does the mechanical part. It runs these commands, and you can run them by hand too:

```bash
python3 scripts/ledger.py sync          # broker fills and plan premiums -> learning/trades.jsonl
python3 scripts/ledger.py snapshot      # today's bars and book -> bench/fixtures
python3 scripts/freeze.py check         # did any replayed decision move?
python3 scripts/review.py day           # draft learning/reviews/YYYY-MM-DD.md
```

The draft fills Numbers, Taken, Signals with no order, Re-entries, Skips, and Alarms. Every dollar figure is one contract, from broker fills when an order went out and from the broker's option bars when one did not.

## What you fill (10 minutes)

1. **Would I take it.** One word per signal (yes, no, or unsure) and a short reason, from your own read of the chart at that candle. This is the main check: it measures whether the checker trades your TA, and `ledger.py sync` copies the answers into the dataset as `operator_take`.
2. **What I saw that the checker did not.** Levels you would have skipped, exits you would have taken, anything no rule covers.
3. **Lessons.** What repeated, and on which earlier day. A pattern needs the same feature in more than one taken trade.
4. **Proposals.** A rule you want changed goes to `learning/proposals.md`, not into the checker.

Then run `python3 scripts/ledger.py sync` once more so your answers land in the ledger.

## Still by hand

- Append the day's fade closes to `alerts/fade_forward.md`, in stock points. The fade record is paper.
- `python3 scripts/recap.py`, then paste `learning/parameter_search.md` into the review. During the freeze, a pass is reported and not applied.

## Weekly (Friday or the weekend)

`python3 scripts/review.py week` writes `learning/reviews/week-YYYY-MM-DD.md`. It splits the ledger by:

- entry number at a level, and whether it came after a stop
- hour, ticker, side, days to expiration, and premium
- exit reason and candle
- your yes or no answers

Decide each open proposal there. A decision change ships only through `python3 scripts/freeze.py bless`, which the operator runs.

A review is an observation. It does not change `rules/ta_rules.md`, the checker, or an order.

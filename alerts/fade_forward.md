# Fade forward test

Failed claim is a put. Failed break is a call. This is not the live checker. The live entry stays the retest. Real money waits until the operator says so.

## Rule

- A claim level that is still under the price, tags it on a green candle, and closes back under is a put.
- A break level that is still above the price, tags it on a red candle, and closes back above is a call.
- Invalidation is a finished 10-minute close back through the entry level.
- The stop is a finished 10-minute close past the signal wick. The wick is outside the level, so the level is the closer cut.
- The target is the furthest number in that day's note in the direction of the trade. The first number does not close the trade.
- If the note has no further number, the exit is the 12:50 PT bar.
- Score stock points. No contract premium was recorded, so this is not option profit.

## Window

Three trading days: 2026-10-19, 2026-10-20, and 2026-10-21. After each cash close, replay that day's armed book with `entry: fade` and append the fade fills below. Do not score a day before the close.

## Gate

After the 2026-10-21 close, compute win rate, reward to risk, and profit factor on the fade fills from these three days only.

Start the record only if the profit factor is at least 2, the net stock points are positive, and at least 3 fades closed. Fewer than 3 fills does not pass. A pass still does not place an order.

## Test

| Day | Ticker | Side | Level | Fill | Exit | Stock |
|-----|--------|------|-------|------|------|-------|
| 2026-10-19 | AAPL | put | 343.50 | 343.43 | 343.59 reclaim | -0.16 |
| 2026-10-19 | AAPL | put | 343.50 | 343.24 | 342.83 clock | +0.41 |
| 2026-10-19 | GOOGL | call | 342.00 | 342.19 | 345.28 clock | +3.09 |
| 2026-10-19 | META | call | 700.00 | 700.33 | 705.63 clock | +5.30 |
| 2026-10-19 | SPCX | put | 148.50 | 148.42 | 149.33 reclaim | -0.91 |
| 2026-10-20 | AAPL | put | 342.25 | 342.26 | 339.48 clock | +2.78 |
| 2026-10-20 | AMZN | put | 264.20 | 263.81 | 264.30 reclaim | -0.49 |
| 2026-10-20 | NVDA | put | 217.50 | 217.49 | 216.56 clock | +0.93 |
| 2026-10-21 | AMZN | put | 264.20 | 263.87 | 264.26 reclaim | -0.39 |
| 2026-10-21 | PLTR | put | 197.00 | 196.51 | 197.59 reclaim | -1.08 |
| 2026-10-21 | PLTR | put | 200.00 | 199.83 | 200.04 reclaim | -0.21 |
| 2026-10-21 | PLTR | put | 200.00 | 199.59 | 199.97 stop | -0.38 |
| 2026-10-21 | PLTR | put | 200.00 | 199.66 | 199.99 stop | -0.33 |

## Record

The three-day gate passed. Profit factor 3.17, net +8.56 stock points, 13 closes. The record is paper. The live checker stays on the retest. A pass does not place an order. Real money waits until the operator says so.

# Regime forward

Neither paper entry is worth keeping. The live entry stays the retest. These rows do not send a Discord alert and they do not place an order.

Bounce closed 274 times, net +5.67 stock points, profit factor 1.03. The fade gate was a profit factor of at least 2, a positive net, and at least 3 closes. Bounce has the count and a small net. It does not have the factor. 108 of the 274 signal bars are already a retest signal.

Trend closed 23 times, net -0.76, profit factor 0.94. Entering the next bar after a claim loses money. 17 of those were also a retest, net -4.64. The 6 the retest did not catch net +3.88. None of them reached the next posted number. 5 drifted to the 12:50 PT clock. 1 reclaimed on the way. The trend rows that did reach the next number were already retest signals: Wednesday AAPL 340 and Thursday AAPL 345.40.

Thursday added no trend row the retest missed.

## Rule

- Bounce: a posted level is tagged within 15 cents and the close stays inside the half-ATR band. The fill is the next bar's open, in the direction of the rejection. A close at or above the level is a call. A close under it is a put.
- Trend: a posted level is claimed by a finished 10-minute close beyond it by half the 14-period ATR. The fill is the next bar's open, in the direction of the claim. The target is the next posted number.
- Chase is 0.50 from the level. A wider open is not a fill.
- A close back through the level by half the ATR is the exit. A bounce targets the furthest posted number in that direction. A trend targets the next one. If that number is not reached, the exit is the 12:50 PT bar.
- Retest is "yes" when a later wick tags the level before the exit, or the retest rule signals that level before the exit. "same bar" means the bounce signal is itself a retest signal. "no" means the retest did not have this one.
- Each signal is its own paper row. This is not one open position.

## Window

The seven sessions in the level-respect note, including Thursday 2026-10-22. Prices are Yahoo 5-minute bars folded into finished 10-minute bars. Monday's book runs through Tuesday 07:30 PT. Tuesday's book starts at 07:34 PT.

## Test

| Day | Ticker | Kind | Side | Level | Fill time | Fill | Exit time | Exit | Why | Stock | Retest |
|-----|--------|------|------|-------|-----------|------|-----------|------|-----|-------|--------|
| 2026-10-14 | AAPL | bounce | put | 345.00 | 2026-10-14 07:30 PT | 344.91 | 2026-10-14 07:30 PT | 345.99 | reclaim | -1.08 | same bar |
| 2026-10-14 | AAPL | bounce | call | 345.00 | 2026-10-14 08:00 PT | 345.08 | 2026-10-14 09:10 PT | 344.32 | reclaim | -0.76 | same bar |
| 2026-10-14 | AAPL | bounce | call | 345.00 | 2026-10-14 08:10 PT | 345.24 | 2026-10-14 09:10 PT | 344.32 | reclaim | -0.92 | no |
| 2026-10-14 | AAPL | bounce | call | 345.00 | 2026-10-14 08:20 PT | 345.45 | 2026-10-14 09:10 PT | 344.32 | reclaim | -1.13 | no |
| 2026-10-14 | AAPL | bounce | call | 345.00 | 2026-10-14 09:00 PT | 345.13 | 2026-10-14 09:10 PT | 344.32 | reclaim | -0.81 | same bar |
| 2026-10-14 | AAPL | bounce | put | 345.00 | 2026-10-14 09:10 PT | 344.83 | 2026-10-14 12:50 PT | 343.42 | clock | +1.41 | no |
| 2026-10-14 | AAPL | bounce | call | 345.00 | 2026-10-14 09:40 PT | 345.10 | 2026-10-14 09:50 PT | 344.46 | reclaim | -0.64 | no |
| 2026-10-14 | AAPL | bounce | put | 345.00 | 2026-10-14 09:50 PT | 344.53 | 2026-10-14 12:50 PT | 343.42 | clock | +1.11 | no |
| 2026-10-14 | AMZN | bounce | put | 259.50 | 2026-10-14 07:00 PT | 259.23 | 2026-10-14 10:30 PT | 253.58 | target | +5.65 | same bar |
| 2026-10-14 | AMZN | bounce | call | 257.00 | 2026-10-14 07:20 PT | 257.04 | 2026-10-14 07:20 PT | 255.93 | reclaim | -1.11 | same bar |
| 2026-10-14 | GOOGL | bounce | call | 358.75 | 2026-10-14 07:00 PT | 358.96 | 2026-10-14 07:00 PT | 354.99 | reclaim | -3.97 | no |
| 2026-10-14 | GOOGL | bounce | put | 353.70 | 2026-10-14 07:30 PT | 353.34 | 2026-10-14 07:30 PT | 355.05 | reclaim | -1.71 | no |
| 2026-10-14 | GOOGL | bounce | call | 353.70 | 2026-10-14 08:10 PT | 354.13 | 2026-10-14 09:10 PT | 352.71 | reclaim | -1.42 | same bar |
| 2026-10-14 | GOOGL | bounce | put | 353.70 | 2026-10-14 08:20 PT | 353.45 | 2026-10-14 09:40 PT | 350.85 | target | +2.60 | no |
| 2026-10-14 | GOOGL | bounce | put | 353.70 | 2026-10-14 08:50 PT | 353.66 | 2026-10-14 09:40 PT | 350.85 | target | +2.81 | no |
| 2026-10-14 | GOOGL | bounce | put | 353.70 | 2026-10-14 09:10 PT | 353.36 | 2026-10-14 09:40 PT | 350.85 | target | +2.51 | no |
| 2026-10-14 | GOOGL | bounce | put | 351.50 | 2026-10-14 09:40 PT | 351.22 | 2026-10-14 12:50 PT | 348.03 | clock | +3.19 | no |
| 2026-10-14 | GOOGL | bounce | put | 351.50 | 2026-10-14 10:00 PT | 351.14 | 2026-10-14 12:50 PT | 348.03 | clock | +3.11 | same bar |
| 2026-10-14 | MSFT | bounce | put | 540.15 | 2026-10-14 07:20 PT | 539.71 | 2026-10-14 12:50 PT | 534.33 | clock | +5.38 | no |
| 2026-10-14 | NVDA | bounce | call | 225.50 | 2026-10-14 06:40 PT | 225.13 | 2026-10-14 07:00 PT | 224.40 | reclaim | -0.73 | same bar |
| 2026-10-14 | NVDA | bounce | put | 225.50 | 2026-10-14 06:50 PT | 225.33 | 2026-10-14 06:50 PT | 225.85 | reclaim | -0.52 | no |
| 2026-10-14 | NVDA | trend | call | 225.50 | 2026-10-14 07:00 PT | 225.87 | 2026-10-14 07:00 PT | 224.40 | reclaim | -1.47 | no |
| 2026-10-14 | SPCX | bounce | call | 152.00 | 2026-10-14 11:00 PT | 152.27 | 2026-10-14 11:40 PT | 151.41 | reclaim | -0.86 | same bar |
| 2026-10-14 | SPCX | bounce | put | 152.00 | 2026-10-14 11:10 PT | 151.87 | 2026-10-14 12:30 PT | 152.52 | reclaim | -0.65 | no |
| 2026-10-14 | SPCX | bounce | call | 152.00 | 2026-10-14 11:20 PT | 152.02 | 2026-10-14 11:40 PT | 151.41 | reclaim | -0.61 | no |
| 2026-10-14 | SPCX | bounce | call | 152.00 | 2026-10-14 11:30 PT | 152.00 | 2026-10-14 11:40 PT | 151.41 | reclaim | -0.59 | no |
| 2026-10-14 | SPCX | bounce | put | 152.00 | 2026-10-14 11:40 PT | 151.84 | 2026-10-14 12:30 PT | 152.52 | reclaim | -0.68 | no |
| 2026-10-14 | SPCX | bounce | call | 152.00 | 2026-10-14 12:30 PT | 152.16 | 2026-10-14 12:50 PT | 152.15 | clock | -0.01 | no |
| 2026-10-15 | AAPL | bounce | call | 345.35 | 2026-10-15 07:00 PT | 345.52 | 2026-10-15 07:40 PT | 344.67 | reclaim | -0.85 | same bar |
| 2026-10-15 | AAPL | bounce | put | 345.35 | 2026-10-15 07:10 PT | 345.01 | 2026-10-15 11:20 PT | 342.27 | target | +2.74 | no |
| 2026-10-15 | AAPL | bounce | put | 345.35 | 2026-10-15 07:20 PT | 344.90 | 2026-10-15 11:20 PT | 342.27 | target | +2.62 | no |
| 2026-10-15 | AAPL | bounce | put | 345.35 | 2026-10-15 07:30 PT | 345.08 | 2026-10-15 11:20 PT | 342.27 | target | +2.81 | same bar |
| 2026-10-15 | AAPL | bounce | put | 345.35 | 2026-10-15 07:40 PT | 344.87 | 2026-10-15 11:20 PT | 342.27 | target | +2.59 | no |
| 2026-10-15 | AAPL | bounce | call | 342.85 | 2026-10-15 08:50 PT | 343.24 | 2026-10-15 11:20 PT | 342.27 | reclaim | -0.97 | same bar |
| 2026-10-15 | AAPL | bounce | call | 342.85 | 2026-10-15 09:10 PT | 343.23 | 2026-10-15 11:20 PT | 342.27 | reclaim | -0.96 | same bar |
| 2026-10-15 | AAPL | bounce | call | 342.85 | 2026-10-15 11:20 PT | 343.05 | 2026-10-15 11:20 PT | 342.27 | reclaim | -0.78 | same bar |
| 2026-10-15 | AAPL | bounce | put | 342.85 | 2026-10-15 12:00 PT | 342.57 | 2026-10-15 12:50 PT | 342.88 | clock | -0.30 | same bar |
| 2026-10-15 | AAPL | bounce | put | 342.85 | 2026-10-15 12:10 PT | 342.50 | 2026-10-15 12:50 PT | 342.88 | clock | -0.38 | no |
| 2026-10-15 | AAPL | bounce | call | 342.85 | 2026-10-15 12:30 PT | 342.99 | 2026-10-15 12:40 PT | 342.15 | reclaim | -0.84 | no |
| 2026-10-15 | AAPL | bounce | call | 342.85 | 2026-10-15 12:40 PT | 342.92 | 2026-10-15 12:40 PT | 342.15 | reclaim | -0.77 | no |
| 2026-10-15 | AAPL | trend | put | 342.85 | 2026-10-15 12:20 PT | 342.42 | 2026-10-15 12:50 PT | 342.88 | clock | -0.45 | yes |
| 2026-10-15 | AMZN | bounce | put | 255.00 | 2026-10-15 12:20 PT | 254.96 | 2026-10-15 12:20 PT | 255.45 | reclaim | -0.49 | same bar |
| 2026-10-15 | AMZN | bounce | call | 255.00 | 2026-10-15 12:40 PT | 255.19 | 2026-10-15 12:50 PT | 255.09 | clock | -0.10 | same bar |
| 2026-10-15 | AMZN | bounce | call | 255.00 | 2026-10-15 12:50 PT | 254.90 | 2026-10-15 12:50 PT | 255.09 | clock | +0.18 | same bar |
| 2026-10-15 | AMZN | trend | call | 255.00 | 2026-10-15 12:30 PT | 255.43 | 2026-10-15 12:50 PT | 255.09 | clock | -0.34 | yes |
| 2026-10-15 | GOOGL | bounce | call | 346.75 | 2026-10-15 06:50 PT | 347.07 | 2026-10-15 12:50 PT | 349.69 | clock | +2.62 | no |
| 2026-10-15 | MSFT | bounce | put | 537.25 | 2026-10-15 06:50 PT | 537.23 | 2026-10-15 08:10 PT | 538.40 | reclaim | -1.17 | same bar |
| 2026-10-15 | MSFT | bounce | put | 537.25 | 2026-10-15 08:10 PT | 536.98 | 2026-10-15 08:10 PT | 538.40 | reclaim | -1.42 | same bar |
| 2026-10-15 | MSFT | bounce | put | 537.25 | 2026-10-15 08:50 PT | 537.27 | 2026-10-15 09:00 PT | 538.34 | reclaim | -1.07 | no |
| 2026-10-15 | MSFT | bounce | call | 537.25 | 2026-10-15 09:00 PT | 537.58 | 2026-10-15 12:50 PT | 540.44 | clock | +2.86 | no |
| 2026-10-15 | SPCX | bounce | call | 146.00 | 2026-10-15 09:30 PT | 146.35 | 2026-10-15 09:30 PT | 145.24 | reclaim | -1.10 | same bar |
| 2026-10-15 | SPCX | bounce | put | 146.00 | 2026-10-15 09:50 PT | 145.84 | 2026-10-15 10:10 PT | 146.67 | reclaim | -0.83 | same bar |
| 2026-10-15 | SPCX | bounce | call | 146.00 | 2026-10-15 10:00 PT | 146.08 | 2026-10-15 12:50 PT | 148.89 | clock | +2.81 | no |
| 2026-10-15 | SPCX | bounce | call | 146.00 | 2026-10-15 10:10 PT | 146.37 | 2026-10-15 12:50 PT | 148.89 | clock | +2.52 | no |
| 2026-10-15 | SPCX | bounce | call | 146.00 | 2026-10-15 10:50 PT | 146.29 | 2026-10-15 12:50 PT | 148.89 | clock | +2.60 | same bar |
| 2026-10-15 | SPCX | bounce | call | 146.00 | 2026-10-15 11:20 PT | 146.27 | 2026-10-15 12:50 PT | 148.89 | clock | +2.62 | same bar |
| 2026-10-15 | SPCX | bounce | call | 146.00 | 2026-10-15 11:30 PT | 146.24 | 2026-10-15 12:50 PT | 148.89 | clock | +2.65 | same bar |
| 2026-10-15 | SPCX | trend | call | 146.00 | 2026-10-15 11:40 PT | 146.46 | 2026-10-15 12:50 PT | 148.89 | clock | +2.43 | no |
| 2026-10-16 | AAPL | bounce | put | 346.00 | 2026-10-16 08:40 PT | 345.52 | 2026-10-16 12:50 PT | 343.88 | clock | +1.64 | no |
| 2026-10-16 | AAPL | bounce | put | 344.00 | 2026-10-16 09:20 PT | 343.70 | 2026-10-16 09:20 PT | 344.93 | reclaim | -1.23 | no |
| 2026-10-16 | AAPL | bounce | put | 344.00 | 2026-10-16 09:50 PT | 343.94 | 2026-10-16 10:00 PT | 344.66 | reclaim | -0.72 | no |
| 2026-10-16 | AAPL | bounce | call | 344.00 | 2026-10-16 10:00 PT | 344.49 | 2026-10-16 10:10 PT | 342.51 | reclaim | -1.98 | no |
| 2026-10-16 | SPCX | bounce | call | 146.50 | 2026-10-16 09:00 PT | 146.69 | 2026-10-16 09:00 PT | 145.76 | reclaim | -0.93 | no |
| 2026-10-16 | SPCX | bounce | put | 146.50 | 2026-10-16 09:30 PT | 146.23 | 2026-10-16 12:50 PT | 144.04 | clock | +2.19 | same bar |
| 2026-10-16 | SPCX | bounce | put | 146.50 | 2026-10-16 09:40 PT | 146.01 | 2026-10-16 12:50 PT | 144.04 | clock | +1.98 | no |
| 2026-10-19 | AAPL | bounce | put | 343.50 | 2026-10-19 07:00 PT | 343.47 | 2026-10-19 07:00 PT | 344.64 | reclaim | -1.17 | no |
| 2026-10-19 | AAPL | bounce | put | 345.40 | 2026-10-19 07:20 PT | 345.30 | 2026-10-19 12:50 PT | 342.83 | clock | +2.47 | same bar |
| 2026-10-19 | AAPL | bounce | call | 345.40 | 2026-10-19 07:30 PT | 345.55 | 2026-10-19 07:40 PT | 344.64 | reclaim | -0.92 | no |
| 2026-10-19 | AAPL | bounce | put | 345.40 | 2026-10-19 07:40 PT | 345.18 | 2026-10-19 12:50 PT | 342.83 | clock | +2.35 | no |
| 2026-10-19 | AAPL | bounce | call | 343.50 | 2026-10-19 08:10 PT | 343.96 | 2026-10-19 08:20 PT | 342.59 | reclaim | -1.37 | no |
| 2026-10-19 | AAPL | bounce | put | 343.50 | 2026-10-19 08:20 PT | 343.09 | 2026-10-19 12:50 PT | 342.83 | clock | +0.26 | no |
| 2026-10-19 | AAPL | bounce | put | 343.50 | 2026-10-19 11:20 PT | 343.43 | 2026-10-19 12:50 PT | 342.83 | clock | +0.60 | same bar |
| 2026-10-19 | AAPL | bounce | put | 343.50 | 2026-10-19 11:30 PT | 343.38 | 2026-10-19 12:50 PT | 342.83 | clock | +0.55 | no |
| 2026-10-19 | AAPL | bounce | call | 343.50 | 2026-10-19 11:40 PT | 343.59 | 2026-10-19 11:50 PT | 342.97 | reclaim | -0.62 | no |
| 2026-10-19 | AAPL | bounce | call | 343.50 | 2026-10-19 11:50 PT | 343.66 | 2026-10-19 11:50 PT | 342.97 | reclaim | -0.69 | no |
| 2026-10-19 | AAPL | bounce | put | 343.50 | 2026-10-19 12:10 PT | 343.24 | 2026-10-19 12:50 PT | 342.83 | clock | +0.41 | same bar |
| 2026-10-19 | AAPL | bounce | put | 339.75 | 2026-10-20 04:10 PT | 339.70 | 2026-10-20 06:40 PT | 341.08 | reclaim | -1.38 | no |
| 2026-10-19 | AAPL | bounce | put | 339.75 | 2026-10-20 04:20 PT | 339.38 | 2026-10-20 06:40 PT | 341.08 | reclaim | -1.70 | no |
| 2026-10-19 | AAPL | bounce | put | 339.75 | 2026-10-20 04:30 PT | 339.60 | 2026-10-20 06:40 PT | 341.08 | reclaim | -1.48 | same bar |
| 2026-10-19 | AAPL | bounce | put | 339.75 | 2026-10-20 04:40 PT | 339.33 | 2026-10-20 06:40 PT | 341.08 | reclaim | -1.74 | no |
| 2026-10-19 | AAPL | bounce | put | 339.75 | 2026-10-20 06:30 PT | 339.47 | 2026-10-20 06:40 PT | 341.08 | reclaim | -1.61 | same bar |
| 2026-10-19 | AAPL | trend | put | 343.50 | 2026-10-19 12:20 PT | 343.01 | 2026-10-19 12:50 PT | 342.83 | clock | +0.18 | no |
| 2026-10-19 | AMZN | bounce | put | 255.75 | 2026-10-19 06:40 PT | 255.34 | 2026-10-19 07:00 PT | 256.59 | reclaim | -1.25 | same bar |
| 2026-10-19 | AMZN | bounce | put | 255.75 | 2026-10-19 06:50 PT | 255.52 | 2026-10-19 07:00 PT | 256.59 | reclaim | -1.07 | same bar |
| 2026-10-19 | AMZN | bounce | call | 255.75 | 2026-10-19 07:00 PT | 255.82 | 2026-10-19 12:50 PT | 263.32 | clock | +7.51 | no |
| 2026-10-19 | AMZN | bounce | put | 258.30 | 2026-10-19 07:20 PT | 258.20 | 2026-10-19 07:20 PT | 259.67 | reclaim | -1.47 | same bar |
| 2026-10-19 | AMZN | bounce | put | 261.00 | 2026-10-19 08:00 PT | 260.79 | 2026-10-19 08:00 PT | 262.19 | reclaim | -1.40 | same bar |
| 2026-10-19 | AMZN | bounce | put | 263.15 | 2026-10-19 08:20 PT | 262.92 | 2026-10-19 12:50 PT | 263.32 | clock | -0.40 | same bar |
| 2026-10-19 | AMZN | bounce | call | 263.15 | 2026-10-19 09:00 PT | 263.15 | 2026-10-19 10:00 PT | 262.56 | reclaim | -0.59 | no |
| 2026-10-19 | AMZN | bounce | put | 263.15 | 2026-10-19 09:10 PT | 262.98 | 2026-10-19 12:50 PT | 263.32 | clock | -0.34 | no |
| 2026-10-19 | AMZN | bounce | put | 263.15 | 2026-10-19 09:20 PT | 262.77 | 2026-10-19 12:50 PT | 263.32 | clock | -0.55 | no |
| 2026-10-19 | AMZN | bounce | call | 263.15 | 2026-10-19 09:30 PT | 263.31 | 2026-10-19 10:00 PT | 262.56 | reclaim | -0.75 | no |
| 2026-10-19 | AMZN | bounce | put | 263.15 | 2026-10-19 09:40 PT | 263.03 | 2026-10-19 12:50 PT | 263.32 | clock | -0.29 | no |
| 2026-10-19 | AMZN | bounce | put | 263.15 | 2026-10-19 09:50 PT | 262.74 | 2026-10-19 12:50 PT | 263.32 | clock | -0.58 | no |
| 2026-10-19 | AMZN | bounce | call | 263.15 | 2026-10-19 12:30 PT | 263.32 | 2026-10-19 12:50 PT | 263.32 | clock | +0.01 | no |
| 2026-10-19 | AMZN | bounce | call | 263.15 | 2026-10-19 12:40 PT | 263.42 | 2026-10-19 12:50 PT | 263.32 | clock | -0.10 | no |
| 2026-10-19 | AMZN | bounce | call | 263.15 | 2026-10-19 12:50 PT | 263.18 | 2026-10-19 12:50 PT | 263.32 | clock | +0.14 | same bar |
| 2026-10-19 | AMZN | bounce | call | 263.15 | 2026-10-20 06:00 PT | 263.18 | 2026-10-20 06:40 PT | 261.67 | reclaim | -1.51 | no |
| 2026-10-19 | AMZN | bounce | put | 263.15 | 2026-10-20 06:10 PT | 263.10 | 2026-10-20 06:20 PT | 263.48 | reclaim | -0.38 | no |
| 2026-10-19 | AMZN | bounce | call | 263.15 | 2026-10-20 06:20 PT | 263.45 | 2026-10-20 06:40 PT | 261.67 | reclaim | -1.78 | no |
| 2026-10-19 | AMZN | bounce | put | 263.15 | 2026-10-20 07:20 PT | 263.02 | 2026-10-20 07:30 PT | 264.33 | reclaim | -1.30 | same bar |
| 2026-10-19 | AMZN | bounce | put | 263.15 | 2026-10-20 07:30 PT | 262.98 | 2026-10-20 07:30 PT | 264.33 | reclaim | -1.35 | no |
| 2026-10-19 | AMZN | trend | put | 263.15 | 2026-10-20 04:00 PT | 263.10 | 2026-10-20 06:20 PT | 263.48 | reclaim | -0.38 | yes |
| 2026-10-19 | AMZN | trend | call | 263.15 | 2026-10-20 06:30 PT | 263.40 | 2026-10-20 06:40 PT | 261.67 | reclaim | -1.73 | yes |
| 2026-10-19 | GOOGL | bounce | call | 342.00 | 2026-10-19 06:50 PT | 342.19 | 2026-10-19 12:50 PT | 345.28 | clock | +3.09 | same bar |
| 2026-10-19 | GOOGL | bounce | call | 346.00 | 2026-10-19 08:20 PT | 346.36 | 2026-10-19 09:10 PT | 344.94 | reclaim | -1.42 | no |
| 2026-10-19 | GOOGL | bounce | put | 346.00 | 2026-10-19 08:30 PT | 345.60 | 2026-10-19 12:50 PT | 345.28 | clock | +0.32 | no |
| 2026-10-19 | GOOGL | bounce | put | 346.00 | 2026-10-19 08:40 PT | 345.61 | 2026-10-19 12:50 PT | 345.28 | clock | +0.33 | no |
| 2026-10-19 | GOOGL | bounce | put | 346.00 | 2026-10-19 08:50 PT | 345.94 | 2026-10-19 12:50 PT | 345.28 | clock | +0.66 | same bar |
| 2026-10-19 | GOOGL | bounce | call | 346.00 | 2026-10-19 09:00 PT | 346.09 | 2026-10-19 09:10 PT | 344.94 | reclaim | -1.15 | no |
| 2026-10-19 | GOOGL | bounce | put | 346.00 | 2026-10-19 09:10 PT | 345.83 | 2026-10-19 12:50 PT | 345.28 | clock | +0.55 | no |
| 2026-10-19 | GOOGL | bounce | put | 344.55 | 2026-10-19 10:20 PT | 344.22 | 2026-10-19 12:10 PT | 345.27 | reclaim | -1.05 | no |
| 2026-10-19 | GOOGL | bounce | put | 344.55 | 2026-10-19 10:30 PT | 344.40 | 2026-10-19 12:10 PT | 345.27 | reclaim | -0.87 | same bar |
| 2026-10-19 | GOOGL | bounce | put | 344.55 | 2026-10-19 10:40 PT | 344.48 | 2026-10-19 12:10 PT | 345.27 | reclaim | -0.79 | same bar |
| 2026-10-19 | GOOGL | bounce | put | 344.55 | 2026-10-19 10:50 PT | 344.44 | 2026-10-19 12:10 PT | 345.27 | reclaim | -0.83 | no |
| 2026-10-19 | GOOGL | bounce | put | 344.55 | 2026-10-19 11:00 PT | 344.36 | 2026-10-19 12:10 PT | 345.27 | reclaim | -0.91 | no |
| 2026-10-19 | GOOGL | bounce | put | 344.55 | 2026-10-19 11:20 PT | 344.42 | 2026-10-19 12:10 PT | 345.27 | reclaim | -0.85 | same bar |
| 2026-10-19 | GOOGL | bounce | call | 344.55 | 2026-10-19 11:30 PT | 344.59 | 2026-10-19 12:50 PT | 345.28 | clock | +0.69 | no |
| 2026-10-19 | GOOGL | bounce | put | 344.55 | 2026-10-19 11:40 PT | 344.27 | 2026-10-19 12:10 PT | 345.27 | reclaim | -1.00 | no |
| 2026-10-19 | GOOGL | bounce | put | 344.55 | 2026-10-19 11:50 PT | 344.22 | 2026-10-19 12:10 PT | 345.27 | reclaim | -1.05 | same bar |
| 2026-10-19 | GOOGL | bounce | put | 344.55 | 2026-10-19 12:00 PT | 344.38 | 2026-10-19 12:10 PT | 345.27 | reclaim | -0.89 | same bar |
| 2026-10-19 | GOOGL | bounce | call | 344.55 | 2026-10-19 12:10 PT | 344.72 | 2026-10-19 12:50 PT | 345.28 | clock | +0.56 | no |
| 2026-10-19 | GOOGL | bounce | put | 346.00 | 2026-10-19 12:40 PT | 345.73 | 2026-10-19 12:50 PT | 345.28 | clock | +0.45 | same bar |
| 2026-10-19 | GOOGL | bounce | put | 346.00 | 2026-10-19 12:50 PT | 345.89 | 2026-10-19 12:50 PT | 345.28 | clock | +0.61 | same bar |
| 2026-10-19 | GOOGL | bounce | put | 342.00 | 2026-10-20 06:50 PT | 341.87 | 2026-10-20 06:50 PT | 342.93 | reclaim | -1.07 | no |
| 2026-10-19 | GOOGL | trend | put | 344.55 | 2026-10-19 11:10 PT | 344.19 | 2026-10-19 12:10 PT | 345.27 | reclaim | -1.08 | yes |
| 2026-10-19 | META | bounce | call | 700.00 | 2026-10-19 10:20 PT | 700.33 | 2026-10-19 12:50 PT | 705.63 | clock | +5.30 | same bar |
| 2026-10-19 | META | bounce | call | 700.00 | 2026-10-20 05:00 PT | 699.93 | 2026-10-20 05:10 PT | 698.00 | reclaim | -1.93 | no |
| 2026-10-19 | SPCX | bounce | put | 148.50 | 2026-10-19 06:20 PT | 148.42 | 2026-10-19 06:30 PT | 149.33 | reclaim | -0.91 | same bar |
| 2026-10-19 | SPCX | bounce | put | 148.50 | 2026-10-19 06:30 PT | 148.46 | 2026-10-19 06:30 PT | 149.33 | reclaim | -0.87 | same bar |
| 2026-10-19 | SPCX | bounce | call | 148.50 | 2026-10-19 07:00 PT | 148.94 | 2026-10-19 07:00 PT | 148.01 | reclaim | -0.93 | same bar |
| 2026-10-19 | SPCX | bounce | put | 148.50 | 2026-10-19 07:20 PT | 148.46 | 2026-10-19 07:20 PT | 149.62 | reclaim | -1.16 | same bar |
| 2026-10-19 | SPCX | bounce | put | 148.50 | 2026-10-19 10:20 PT | 148.22 | 2026-10-19 12:50 PT | 147.30 | clock | +0.92 | no |
| 2026-10-19 | SPCX | bounce | call | 148.50 | 2026-10-19 10:40 PT | 148.51 | 2026-10-19 10:40 PT | 148.01 | reclaim | -0.50 | no |
| 2026-10-19 | SPCX | bounce | put | 146.50 | 2026-10-20 04:10 PT | 146.40 | 2026-10-20 06:10 PT | 146.85 | reclaim | -0.45 | no |
| 2026-10-19 | SPCX | bounce | put | 146.50 | 2026-10-20 04:20 PT | 146.08 | 2026-10-20 06:10 PT | 146.85 | reclaim | -0.77 | no |
| 2026-10-19 | SPCX | bounce | call | 146.50 | 2026-10-20 04:50 PT | 146.49 | 2026-10-20 04:50 PT | 146.18 | reclaim | -0.31 | no |
| 2026-10-19 | SPCX | bounce | put | 146.50 | 2026-10-20 05:10 PT | 146.42 | 2026-10-20 06:10 PT | 146.85 | reclaim | -0.43 | same bar |
| 2026-10-19 | SPCX | bounce | call | 146.50 | 2026-10-20 05:50 PT | 146.56 | 2026-10-20 06:30 PT | 146.13 | reclaim | -0.43 | no |
| 2026-10-19 | SPCX | bounce | call | 146.50 | 2026-10-20 06:00 PT | 146.62 | 2026-10-20 06:30 PT | 146.13 | reclaim | -0.49 | no |
| 2026-10-19 | SPCX | bounce | call | 146.50 | 2026-10-20 06:10 PT | 146.80 | 2026-10-20 06:30 PT | 146.13 | reclaim | -0.67 | no |
| 2026-10-19 | SPCX | trend | put | 148.50 | 2026-10-19 07:10 PT | 148.03 | 2026-10-19 07:20 PT | 149.62 | reclaim | -1.60 | yes |
| 2026-10-19 | SPCX | trend | put | 148.50 | 2026-10-19 10:50 PT | 148.01 | 2026-10-19 12:50 PT | 147.30 | clock | +0.71 | no |
| 2026-10-19 | SPCX | trend | put | 146.50 | 2026-10-20 05:00 PT | 146.22 | 2026-10-20 06:10 PT | 146.85 | reclaim | -0.63 | yes |
| 2026-10-19 | SPCX | trend | put | 146.50 | 2026-10-20 05:20 PT | 146.00 | 2026-10-20 06:10 PT | 146.85 | reclaim | -0.85 | yes |
| 2026-10-19 | SPCX | trend | call | 146.50 | 2026-10-20 06:20 PT | 146.85 | 2026-10-20 06:30 PT | 146.13 | reclaim | -0.72 | yes |
| 2026-10-19 | SPCX | trend | put | 146.50 | 2026-10-20 06:40 PT | 146.13 | 2026-10-20 07:20 PT | 147.21 | reclaim | -1.07 | yes |
| 2026-10-19 | TSLA | bounce | put | 372.75 | 2026-10-20 07:20 PT | 372.32 | 2026-10-20 07:30 PT | 374.84 | reclaim | -2.52 | same bar |
| 2026-10-20 | AAPL | bounce | put | 342.25 | 2026-10-20 07:50 PT | 342.26 | 2026-10-20 12:50 PT | 339.48 | clock | +2.77 | same bar |
| 2026-10-20 | AAPL | bounce | put | 342.25 | 2026-10-20 08:00 PT | 341.88 | 2026-10-20 12:50 PT | 339.48 | clock | +2.40 | no |
| 2026-10-20 | AAPL | bounce | call | 340.00 | 2026-10-20 08:20 PT | 340.48 | 2026-10-20 12:10 PT | 339.35 | reclaim | -1.13 | same bar |
| 2026-10-20 | AAPL | bounce | call | 340.00 | 2026-10-20 08:40 PT | 340.36 | 2026-10-20 12:10 PT | 339.35 | reclaim | -1.01 | same bar |
| 2026-10-20 | AAPL | bounce | put | 340.00 | 2026-10-20 11:00 PT | 339.94 | 2026-10-20 12:50 PT | 339.48 | clock | +0.46 | no |
| 2026-10-20 | AAPL | bounce | put | 340.00 | 2026-10-20 11:10 PT | 339.98 | 2026-10-20 12:50 PT | 339.48 | clock | +0.50 | same bar |
| 2026-10-20 | AAPL | bounce | call | 340.00 | 2026-10-20 11:20 PT | 340.17 | 2026-10-20 12:10 PT | 339.35 | reclaim | -0.82 | no |
| 2026-10-20 | AAPL | bounce | call | 340.00 | 2026-10-20 11:30 PT | 340.27 | 2026-10-20 12:10 PT | 339.35 | reclaim | -0.92 | no |
| 2026-10-20 | AAPL | bounce | call | 340.00 | 2026-10-20 11:40 PT | 340.01 | 2026-10-20 12:10 PT | 339.35 | reclaim | -0.65 | same bar |
| 2026-10-20 | AAPL | bounce | call | 340.00 | 2026-10-20 11:50 PT | 340.05 | 2026-10-20 12:10 PT | 339.35 | reclaim | -0.70 | no |
| 2026-10-20 | AAPL | bounce | call | 340.00 | 2026-10-20 12:00 PT | 340.12 | 2026-10-20 12:10 PT | 339.35 | reclaim | -0.77 | no |
| 2026-10-20 | AAPL | bounce | put | 340.00 | 2026-10-20 12:10 PT | 339.78 | 2026-10-20 12:50 PT | 339.48 | clock | +0.30 | no |
| 2026-10-20 | AAPL | trend | call | 340.00 | 2026-10-20 10:20 PT | 340.48 | 2026-10-20 12:10 PT | 339.35 | reclaim | -1.12 | yes |
| 2026-10-20 | AMZN | bounce | put | 264.20 | 2026-10-20 08:00 PT | 263.81 | 2026-10-20 12:50 PT | 262.32 | clock | +1.49 | same bar |
| 2026-10-20 | AMZN | bounce | put | 264.20 | 2026-10-20 08:10 PT | 264.12 | 2026-10-20 12:50 PT | 262.32 | clock | +1.80 | same bar |
| 2026-10-20 | AMZN | bounce | call | 264.20 | 2026-10-20 08:20 PT | 264.29 | 2026-10-20 08:20 PT | 263.37 | reclaim | -0.92 | no |
| 2026-10-20 | GOOGL | bounce | call | 343.60 | 2026-10-20 07:50 PT | 343.70 | 2026-10-20 07:50 PT | 342.55 | reclaim | -1.15 | same bar |
| 2026-10-20 | GOOGL | bounce | put | 343.60 | 2026-10-20 08:20 PT | 343.51 | 2026-10-20 12:50 PT | 338.52 | clock | +5.00 | same bar |
| 2026-10-20 | GOOGL | bounce | put | 339.85 | 2026-10-20 11:50 PT | 339.81 | 2026-10-20 12:50 PT | 338.52 | clock | +1.29 | no |
| 2026-10-20 | GOOGL | bounce | call | 339.85 | 2026-10-20 12:00 PT | 339.89 | 2026-10-20 12:10 PT | 339.27 | reclaim | -0.62 | no |
| 2026-10-20 | GOOGL | bounce | put | 339.85 | 2026-10-20 12:10 PT | 339.56 | 2026-10-20 12:50 PT | 338.52 | clock | +1.04 | no |
| 2026-10-20 | NVDA | bounce | call | 217.50 | 2026-10-20 07:50 PT | 217.70 | 2026-10-20 08:30 PT | 216.79 | reclaim | -0.90 | same bar |
| 2026-10-20 | NVDA | bounce | call | 217.50 | 2026-10-20 08:00 PT | 217.88 | 2026-10-20 08:30 PT | 216.79 | reclaim | -1.09 | no |
| 2026-10-20 | NVDA | bounce | call | 217.50 | 2026-10-20 08:20 PT | 217.61 | 2026-10-20 08:30 PT | 216.79 | reclaim | -0.81 | same bar |
| 2026-10-20 | NVDA | bounce | put | 217.50 | 2026-10-20 08:30 PT | 217.21 | 2026-10-20 12:50 PT | 216.56 | clock | +0.65 | no |
| 2026-10-20 | NVDA | bounce | put | 217.50 | 2026-10-20 09:10 PT | 217.49 | 2026-10-20 12:50 PT | 216.56 | clock | +0.93 | same bar |
| 2026-10-20 | NVDA | bounce | put | 217.50 | 2026-10-20 09:50 PT | 217.44 | 2026-10-20 12:50 PT | 216.56 | clock | +0.88 | same bar |
| 2026-10-20 | NVDA | bounce | put | 217.50 | 2026-10-20 11:00 PT | 217.24 | 2026-10-20 12:50 PT | 216.56 | clock | +0.68 | same bar |
| 2026-10-20 | NVDA | bounce | put | 217.50 | 2026-10-20 11:10 PT | 217.33 | 2026-10-20 12:50 PT | 216.56 | clock | +0.77 | same bar |
| 2026-10-20 | NVDA | trend | put | 217.50 | 2026-10-20 09:20 PT | 217.05 | 2026-10-20 12:50 PT | 216.56 | clock | +0.49 | yes |
| 2026-10-20 | NVDA | trend | put | 217.50 | 2026-10-20 11:20 PT | 217.17 | 2026-10-20 12:50 PT | 216.56 | clock | +0.61 | no |
| 2026-10-20 | SPCX | bounce | call | 146.60 | 2026-10-20 08:40 PT | 146.78 | 2026-10-20 12:50 PT | 147.11 | clock | +0.33 | same bar |
| 2026-10-20 | SPCX | bounce | put | 146.60 | 2026-10-20 08:50 PT | 146.26 | 2026-10-20 09:00 PT | 147.18 | reclaim | -0.91 | no |
| 2026-10-20 | SPCX | bounce | call | 146.60 | 2026-10-20 09:00 PT | 146.77 | 2026-10-20 12:50 PT | 147.11 | clock | +0.34 | no |
| 2026-10-20 | TSLA | bounce | call | 377.00 | 2026-10-20 08:10 PT | 377.29 | 2026-10-20 08:20 PT | 375.50 | reclaim | -1.79 | no |
| 2026-10-21 | AAPL | bounce | call | 340.00 | 2026-10-21 06:50 PT | 340.11 | 2026-10-21 12:50 PT | 344.39 | clock | +4.28 | no |
| 2026-10-21 | AAPL | bounce | call | 340.00 | 2026-10-21 07:00 PT | 340.26 | 2026-10-21 12:50 PT | 344.39 | clock | +4.13 | no |
| 2026-10-21 | AAPL | bounce | call | 340.00 | 2026-10-21 07:30 PT | 340.35 | 2026-10-21 12:50 PT | 344.39 | clock | +4.04 | same bar |
| 2026-10-21 | AAPL | bounce | put | 340.00 | 2026-10-21 07:50 PT | 339.73 | 2026-10-21 07:50 PT | 340.74 | reclaim | -1.01 | no |
| 2026-10-21 | AAPL | bounce | call | 343.00 | 2026-10-21 08:20 PT | 343.09 | 2026-10-21 12:50 PT | 344.39 | clock | +1.30 | no |
| 2026-10-21 | AAPL | trend | call | 340.00 | 2026-10-21 07:40 PT | 340.40 | 2026-10-21 08:20 PT | 343.76 | target | +3.36 | yes |
| 2026-10-21 | AMZN | bounce | put | 260.50 | 2026-10-21 07:00 PT | 260.35 | 2026-10-21 07:50 PT | 260.95 | reclaim | -0.61 | no |
| 2026-10-21 | AMZN | bounce | put | 260.50 | 2026-10-21 07:10 PT | 260.32 | 2026-10-21 07:50 PT | 260.95 | reclaim | -0.63 | no |
| 2026-10-21 | AMZN | bounce | put | 260.50 | 2026-10-21 07:30 PT | 260.23 | 2026-10-21 07:50 PT | 260.95 | reclaim | -0.72 | same bar |
| 2026-10-21 | AMZN | bounce | put | 260.50 | 2026-10-21 07:50 PT | 260.48 | 2026-10-21 07:50 PT | 260.95 | reclaim | -0.47 | same bar |
| 2026-10-21 | AMZN | bounce | put | 264.20 | 2026-10-21 10:30 PT | 263.87 | 2026-10-21 12:50 PT | 262.35 | clock | +1.52 | same bar |
| 2026-10-21 | AMZN | bounce | call | 264.20 | 2026-10-21 11:00 PT | 264.26 | 2026-10-21 11:40 PT | 263.62 | reclaim | -0.64 | no |
| 2026-10-21 | AMZN | bounce | put | 264.20 | 2026-10-21 11:10 PT | 264.07 | 2026-10-21 12:50 PT | 262.35 | clock | +1.73 | no |
| 2026-10-21 | AMZN | bounce | put | 264.20 | 2026-10-21 11:20 PT | 264.03 | 2026-10-21 12:50 PT | 262.35 | clock | +1.68 | no |
| 2026-10-21 | AMZN | bounce | call | 264.20 | 2026-10-21 11:30 PT | 264.27 | 2026-10-21 11:40 PT | 263.62 | reclaim | -0.65 | no |
| 2026-10-21 | AMZN | bounce | put | 264.20 | 2026-10-21 11:40 PT | 264.00 | 2026-10-21 12:50 PT | 262.35 | clock | +1.65 | no |
| 2026-10-21 | AMZN | trend | call | 260.50 | 2026-10-21 08:00 PT | 260.94 | 2026-10-21 12:50 PT | 262.35 | clock | +1.40 | no |
| 2026-10-21 | PLTR | bounce | put | 191.50 | 2026-10-21 06:40 PT | 191.45 | 2026-10-21 06:40 PT | 195.51 | reclaim | -4.07 | no |
| 2026-10-21 | PLTR | bounce | put | 197.00 | 2026-10-21 07:00 PT | 196.51 | 2026-10-21 07:20 PT | 197.59 | reclaim | -1.08 | same bar |
| 2026-10-21 | PLTR | bounce | call | 197.00 | 2026-10-21 07:40 PT | 197.47 | 2026-10-21 12:50 PT | 202.40 | clock | +4.93 | same bar |
| 2026-10-21 | PLTR | bounce | put | 197.00 | 2026-10-21 07:50 PT | 196.97 | 2026-10-21 08:00 PT | 198.48 | reclaim | -1.51 | no |
| 2026-10-21 | PLTR | bounce | call | 197.00 | 2026-10-21 08:00 PT | 197.35 | 2026-10-21 12:50 PT | 202.40 | clock | +5.04 | no |
| 2026-10-21 | PLTR | bounce | put | 200.00 | 2026-10-21 09:00 PT | 199.83 | 2026-10-21 12:20 PT | 200.66 | reclaim | -0.83 | same bar |
| 2026-10-21 | PLTR | bounce | put | 200.00 | 2026-10-21 09:10 PT | 199.72 | 2026-10-21 12:20 PT | 200.66 | reclaim | -0.94 | no |
| 2026-10-21 | PLTR | bounce | call | 200.00 | 2026-10-21 09:50 PT | 200.05 | 2026-10-21 10:50 PT | 199.37 | reclaim | -0.68 | no |
| 2026-10-21 | PLTR | bounce | put | 200.00 | 2026-10-21 10:00 PT | 199.95 | 2026-10-21 12:20 PT | 200.66 | reclaim | -0.71 | no |
| 2026-10-21 | PLTR | bounce | call | 200.00 | 2026-10-21 10:10 PT | 200.04 | 2026-10-21 10:50 PT | 199.37 | reclaim | -0.67 | no |
| 2026-10-21 | PLTR | bounce | call | 200.00 | 2026-10-21 10:20 PT | 200.12 | 2026-10-21 10:50 PT | 199.37 | reclaim | -0.75 | no |
| 2026-10-21 | PLTR | bounce | call | 200.00 | 2026-10-21 10:30 PT | 200.13 | 2026-10-21 10:50 PT | 199.37 | reclaim | -0.76 | no |
| 2026-10-21 | PLTR | bounce | put | 200.00 | 2026-10-21 10:40 PT | 199.99 | 2026-10-21 12:20 PT | 200.66 | reclaim | -0.67 | no |
| 2026-10-21 | PLTR | bounce | put | 200.00 | 2026-10-21 10:50 PT | 199.98 | 2026-10-21 12:20 PT | 200.66 | reclaim | -0.69 | no |
| 2026-10-21 | PLTR | bounce | put | 200.00 | 2026-10-21 11:50 PT | 199.99 | 2026-10-21 12:20 PT | 200.66 | reclaim | -0.68 | same bar |
| 2026-10-21 | PLTR | bounce | put | 200.00 | 2026-10-21 12:20 PT | 199.99 | 2026-10-21 12:20 PT | 200.66 | reclaim | -0.67 | same bar |
| 2026-10-21 | PLTR | trend | put | 200.00 | 2026-10-21 09:20 PT | 199.55 | 2026-10-21 12:20 PT | 200.66 | reclaim | -1.11 | yes |
| 2026-10-22 | AAPL | bounce | call | 345.40 | 2026-10-22 06:50 PT | 345.44 | 2026-10-22 07:20 PT | 344.37 | reclaim | -1.07 | no |
| 2026-10-22 | AAPL | bounce | put | 345.40 | 2026-10-22 07:00 PT | 345.31 | 2026-10-22 09:20 PT | 345.85 | reclaim | -0.54 | no |
| 2026-10-22 | AAPL | bounce | call | 345.40 | 2026-10-22 07:10 PT | 345.60 | 2026-10-22 07:20 PT | 344.37 | reclaim | -1.23 | no |
| 2026-10-22 | AAPL | bounce | put | 345.40 | 2026-10-22 07:20 PT | 345.12 | 2026-10-22 09:20 PT | 345.85 | reclaim | -0.73 | no |
| 2026-10-22 | AAPL | bounce | put | 345.40 | 2026-10-22 08:40 PT | 345.04 | 2026-10-22 09:20 PT | 345.85 | reclaim | -0.81 | same bar |
| 2026-10-22 | AAPL | bounce | put | 345.40 | 2026-10-22 08:50 PT | 345.27 | 2026-10-22 09:20 PT | 345.85 | reclaim | -0.58 | same bar |
| 2026-10-22 | AAPL | bounce | put | 345.40 | 2026-10-22 09:00 PT | 345.16 | 2026-10-22 09:20 PT | 345.85 | reclaim | -0.69 | no |
| 2026-10-22 | AAPL | bounce | put | 345.40 | 2026-10-22 09:10 PT | 345.23 | 2026-10-22 09:20 PT | 345.85 | reclaim | -0.62 | same bar |
| 2026-10-22 | AAPL | bounce | call | 345.40 | 2026-10-22 09:20 PT | 345.46 | 2026-10-22 12:50 PT | 347.77 | clock | +2.30 | no |
| 2026-10-22 | AAPL | bounce | put | 346.50 | 2026-10-22 09:40 PT | 346.26 | 2026-10-22 12:20 PT | 347.21 | reclaim | -0.95 | same bar |
| 2026-10-22 | AAPL | bounce | call | 345.40 | 2026-10-22 09:50 PT | 345.61 | 2026-10-22 12:50 PT | 347.77 | clock | +2.16 | same bar |
| 2026-10-22 | AAPL | bounce | put | 345.40 | 2026-10-22 10:00 PT | 345.37 | 2026-10-22 10:10 PT | 345.88 | reclaim | -0.51 | no |
| 2026-10-22 | AAPL | bounce | call | 345.40 | 2026-10-22 10:10 PT | 345.70 | 2026-10-22 12:50 PT | 347.77 | clock | +2.07 | no |
| 2026-10-22 | AAPL | bounce | put | 346.50 | 2026-10-22 10:30 PT | 346.28 | 2026-10-22 12:20 PT | 347.21 | reclaim | -0.93 | same bar |
| 2026-10-22 | AAPL | bounce | put | 346.50 | 2026-10-22 10:50 PT | 346.43 | 2026-10-22 12:20 PT | 347.21 | reclaim | -0.78 | same bar |
| 2026-10-22 | AAPL | bounce | put | 346.50 | 2026-10-22 11:20 PT | 346.26 | 2026-10-22 12:20 PT | 347.21 | reclaim | -0.95 | same bar |
| 2026-10-22 | AAPL | bounce | call | 346.50 | 2026-10-22 11:30 PT | 346.83 | 2026-10-22 11:40 PT | 345.73 | reclaim | -1.10 | no |
| 2026-10-22 | AAPL | bounce | put | 346.50 | 2026-10-22 11:40 PT | 346.31 | 2026-10-22 12:20 PT | 347.21 | reclaim | -0.90 | no |
| 2026-10-22 | AAPL | bounce | put | 346.50 | 2026-10-22 12:00 PT | 346.35 | 2026-10-22 12:20 PT | 347.21 | reclaim | -0.86 | same bar |
| 2026-10-22 | AAPL | bounce | call | 346.50 | 2026-10-22 12:10 PT | 346.97 | 2026-10-22 12:50 PT | 347.77 | clock | +0.80 | no |
| 2026-10-22 | AAPL | bounce | call | 346.50 | 2026-10-22 12:20 PT | 346.84 | 2026-10-22 12:50 PT | 347.77 | clock | +0.93 | no |
| 2026-10-22 | AAPL | trend | call | 345.40 | 2026-10-22 09:30 PT | 345.86 | 2026-10-22 12:20 PT | 347.21 | target | +1.35 | yes |
| 2026-10-22 | AMD | bounce | put | 523.75 | 2026-10-22 06:40 PT | 523.62 | 2026-10-22 06:40 PT | 525.34 | reclaim | -1.72 | no |
| 2026-10-22 | AMD | bounce | call | 523.75 | 2026-10-22 07:00 PT | 523.59 | 2026-10-22 07:20 PT | 519.47 | reclaim | -4.12 | same bar |
| 2026-10-22 | AMD | bounce | call | 512.38 | 2026-10-22 08:10 PT | 512.48 | 2026-10-22 08:50 PT | 510.01 | reclaim | -2.47 | same bar |
| 2026-10-22 | AMD | bounce | call | 512.38 | 2026-10-22 09:50 PT | 512.81 | 2026-10-22 09:50 PT | 508.40 | reclaim | -4.41 | same bar |
| 2026-10-22 | AMZN | bounce | call | 257.95 | 2026-10-22 06:40 PT | 258.08 | 2026-10-22 06:40 PT | 255.80 | reclaim | -2.28 | no |
| 2026-10-22 | AMZN | bounce | put | 256.18 | 2026-10-22 06:50 PT | 255.82 | 2026-10-22 12:50 PT | 249.30 | clock | +6.51 | no |
| 2026-10-22 | AMZN | bounce | call | 250.00 | 2026-10-22 11:10 PT | 250.18 | 2026-10-22 11:50 PT | 249.29 | reclaim | -0.89 | same bar |
| 2026-10-22 | AMZN | bounce | call | 250.00 | 2026-10-22 11:20 PT | 250.10 | 2026-10-22 11:50 PT | 249.29 | reclaim | -0.81 | same bar |
| 2026-10-22 | AMZN | bounce | put | 250.00 | 2026-10-22 11:40 PT | 249.90 | 2026-10-22 12:50 PT | 249.30 | clock | +0.60 | no |
| 2026-10-22 | AMZN | bounce | put | 250.00 | 2026-10-22 11:50 PT | 249.70 | 2026-10-22 12:50 PT | 249.30 | clock | +0.40 | no |
| 2026-10-22 | MU | bounce | call | 880.00 | 2026-10-22 06:40 PT | 880.08 | 2026-10-22 07:50 PT | 875.85 | reclaim | -4.23 | no |
| 2026-10-22 | MU | bounce | call | 895.00 | 2026-10-22 06:50 PT | 895.10 | 2026-10-22 07:30 PT | 889.53 | reclaim | -5.57 | no |
| 2026-10-22 | MU | bounce | call | 880.00 | 2026-10-22 07:50 PT | 880.18 | 2026-10-22 07:50 PT | 875.85 | reclaim | -4.33 | same bar |
| 2026-10-22 | NVDA | bounce | call | 218.25 | 2026-10-22 06:50 PT | 218.50 | 2026-10-22 06:50 PT | 216.69 | reclaim | -1.81 | no |
| 2026-10-22 | NVDA | bounce | put | 215.25 | 2026-10-22 07:40 PT | 215.09 | 2026-10-22 12:50 PT | 211.84 | clock | +3.25 | no |
| 2026-10-22 | NVDA | bounce | call | 212.85 | 2026-10-22 08:50 PT | 213.11 | 2026-10-22 10:10 PT | 212.44 | reclaim | -0.67 | same bar |
| 2026-10-22 | NVDA | bounce | put | 212.85 | 2026-10-22 09:00 PT | 212.82 | 2026-10-22 09:00 PT | 213.50 | reclaim | -0.68 | no |
| 2026-10-22 | NVDA | bounce | put | 212.85 | 2026-10-22 10:00 PT | 212.65 | 2026-10-22 12:50 PT | 211.84 | clock | +0.81 | no |
| 2026-10-22 | NVDA | bounce | call | 212.85 | 2026-10-22 10:10 PT | 213.10 | 2026-10-22 10:10 PT | 212.44 | reclaim | -0.66 | no |
| 2026-10-22 | NVDA | bounce | put | 212.85 | 2026-10-22 10:30 PT | 212.83 | 2026-10-22 12:50 PT | 211.84 | clock | +0.99 | same bar |
| 2026-10-22 | NVDA | bounce | call | 212.85 | 2026-10-22 10:40 PT | 213.12 | 2026-10-22 11:10 PT | 212.33 | reclaim | -0.79 | no |
| 2026-10-22 | NVDA | bounce | call | 212.85 | 2026-10-22 10:50 PT | 212.98 | 2026-10-22 11:10 PT | 212.33 | reclaim | -0.65 | no |
| 2026-10-22 | NVDA | bounce | put | 212.85 | 2026-10-22 11:00 PT | 212.77 | 2026-10-22 12:50 PT | 211.84 | clock | +0.93 | no |
| 2026-10-22 | NVDA | bounce | put | 212.85 | 2026-10-22 11:10 PT | 212.54 | 2026-10-22 12:50 PT | 211.84 | clock | +0.70 | no |
| 2026-10-22 | NVDA | bounce | call | 212.85 | 2026-10-22 11:30 PT | 212.95 | 2026-10-22 11:30 PT | 212.46 | reclaim | -0.49 | no |
| 2026-10-22 | NVDA | bounce | put | 212.85 | 2026-10-22 12:40 PT | 212.67 | 2026-10-22 12:50 PT | 211.84 | clock | +0.83 | same bar |
| 2026-10-22 | NVDA | trend | put | 212.85 | 2026-10-22 10:20 PT | 212.46 | 2026-10-22 12:50 PT | 211.84 | clock | +0.62 | yes |
| 2026-10-22 | NVDA | trend | put | 212.85 | 2026-10-22 11:40 PT | 212.47 | 2026-10-22 12:50 PT | 211.84 | clock | +0.63 | yes |
| 2026-10-22 | PLTR | bounce | call | 201.50 | 2026-10-22 06:50 PT | 201.91 | 2026-10-22 07:10 PT | 200.82 | reclaim | -1.09 | no |
| 2026-10-22 | PLTR | bounce | put | 201.50 | 2026-10-22 07:00 PT | 201.40 | 2026-10-22 12:50 PT | 195.26 | clock | +6.14 | no |
| 2026-10-22 | PLTR | bounce | put | 201.50 | 2026-10-22 07:10 PT | 201.04 | 2026-10-22 12:50 PT | 195.26 | clock | +5.78 | no |
| 2026-10-22 | PLTR | bounce | call | 200.00 | 2026-10-22 07:30 PT | 200.48 | 2026-10-22 07:30 PT | 198.62 | reclaim | -1.86 | same bar |
| 2026-10-22 | PLTR | bounce | put | 200.00 | 2026-10-22 08:10 PT | 199.77 | 2026-10-22 12:50 PT | 195.26 | clock | +4.51 | same bar |
| 2026-10-22 | PLTR | bounce | put | 197.00 | 2026-10-22 10:00 PT | 196.63 | 2026-10-22 10:00 PT | 198.15 | reclaim | -1.52 | no |
| 2026-10-22 | PLTR | bounce | call | 197.00 | 2026-10-22 10:20 PT | 197.22 | 2026-10-22 11:40 PT | 196.25 | reclaim | -0.97 | same bar |
| 2026-10-22 | PLTR | bounce | call | 197.00 | 2026-10-22 11:10 PT | 197.09 | 2026-10-22 11:40 PT | 196.25 | reclaim | -0.84 | same bar |
| 2026-10-22 | PLTR | bounce | put | 197.00 | 2026-10-22 11:20 PT | 196.79 | 2026-10-22 11:20 PT | 197.69 | reclaim | -0.90 | no |
| 2026-10-22 | PLTR | bounce | put | 197.00 | 2026-10-22 11:40 PT | 196.81 | 2026-10-22 12:50 PT | 195.26 | clock | +1.55 | no |
| 2026-10-22 | SPCX | bounce | call | 153.84 | 2026-10-22 06:40 PT | 154.19 | 2026-10-22 06:50 PT | 152.68 | reclaim | -1.51 | same bar |
| 2026-10-22 | SPCX | bounce | put | 150.00 | 2026-10-22 08:10 PT | 149.82 | 2026-10-22 12:50 PT | 144.92 | clock | +4.90 | no |
| 2026-10-22 | SPCX | bounce | put | 150.00 | 2026-10-22 08:30 PT | 149.80 | 2026-10-22 12:50 PT | 144.92 | clock | +4.88 | same bar |
| 2026-10-22 | SPCX | bounce | call | 150.00 | 2026-10-22 08:40 PT | 150.04 | 2026-10-22 09:30 PT | 149.26 | reclaim | -0.78 | no |
| 2026-10-22 | SPCX | bounce | call | 150.00 | 2026-10-22 08:50 PT | 150.33 | 2026-10-22 09:30 PT | 149.26 | reclaim | -1.07 | no |
| 2026-10-22 | SPCX | bounce | call | 150.00 | 2026-10-22 09:00 PT | 150.01 | 2026-10-22 09:30 PT | 149.26 | reclaim | -0.75 | no |
| 2026-10-22 | SPCX | bounce | call | 150.00 | 2026-10-22 09:10 PT | 150.37 | 2026-10-22 09:30 PT | 149.26 | reclaim | -1.11 | no |
| 2026-10-22 | SPCX | bounce | call | 150.00 | 2026-10-22 09:20 PT | 150.04 | 2026-10-22 09:30 PT | 149.26 | reclaim | -0.79 | no |
| 2026-10-22 | SPCX | bounce | put | 150.00 | 2026-10-22 09:30 PT | 149.69 | 2026-10-22 12:50 PT | 144.92 | clock | +4.77 | no |
| 2026-10-22 | SPCX | bounce | call | 146.60 | 2026-10-22 10:50 PT | 146.90 | 2026-10-22 11:00 PT | 145.57 | reclaim | -1.33 | same bar |
| 2026-10-22 | SPCX | bounce | put | 146.60 | 2026-10-22 11:00 PT | 146.38 | 2026-10-22 12:50 PT | 144.92 | clock | +1.45 | no |
| 2026-10-22 | TSLA | bounce | call | 382.75 | 2026-10-22 07:00 PT | 383.23 | 2026-10-22 09:10 PT | 380.92 | reclaim | -2.31 | no |
| 2026-10-22 | TSLA | bounce | call | 382.75 | 2026-10-22 08:20 PT | 382.96 | 2026-10-22 09:10 PT | 380.92 | reclaim | -2.04 | same bar |
| 2026-10-22 | TSLA | bounce | call | 382.75 | 2026-10-22 08:50 PT | 382.84 | 2026-10-22 09:10 PT | 380.92 | reclaim | -1.92 | same bar |
| 2026-10-22 | TSLA | bounce | put | 382.75 | 2026-10-22 09:00 PT | 382.54 | 2026-10-22 12:50 PT | 377.69 | clock | +4.85 | no |
| 2026-10-22 | TSLA | bounce | call | 382.75 | 2026-10-22 09:10 PT | 383.22 | 2026-10-22 09:10 PT | 380.92 | reclaim | -2.30 | no |
| 2026-10-22 | TSLA | bounce | put | 377.75 | 2026-10-22 10:20 PT | 377.46 | 2026-10-22 10:20 PT | 379.13 | reclaim | -1.67 | no |
| 2026-10-22 | TSLA | bounce | call | 377.75 | 2026-10-22 10:50 PT | 378.13 | 2026-10-22 11:40 PT | 376.07 | reclaim | -2.06 | same bar |
| 2026-10-22 | TSLA | bounce | call | 377.75 | 2026-10-22 11:20 PT | 377.89 | 2026-10-22 11:40 PT | 376.07 | reclaim | -1.82 | same bar |
| 2026-10-22 | TSLA | bounce | call | 377.75 | 2026-10-22 12:40 PT | 377.82 | 2026-10-22 12:50 PT | 377.69 | clock | -0.13 | no |

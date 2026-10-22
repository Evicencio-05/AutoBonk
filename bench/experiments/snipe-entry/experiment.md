# Does skipping the first color, and buying the later push, raise the profit rate?

- question: the snipe-bottom lesson
- live entry: retest
- variant: not added
- days: frozen 2026-10-14, 2026-10-15, 2026-10-16, and the 2026-10-21 book

The lesson is in `learning/lessons/snipe-bottom.md`. Buy calls on a red candle and puts on a green candle. The bottom of a put is the highest green close through the buy. The bottom of a call is the lowest red close through the buy. The first color is not the bottom when a later candle pushes farther. The number is stock points. It is not a priced premium. One drill is an observation, not an order.

## Drill

SPCX 2026-10-16 put, level 146.5. The operator confirmed the 09:20 buy and the 12:10 sell.

The 09:10 green pushed +0.03 and its high did not reach 146.35, so it did not tag the level. The 09:20 green pushed +0.34, tagged 146.5, and closed 146.22. That close is the bottom. The first color left 0.43 stock points. The live retest fills the next open at that 09:20 close. The confirmed buy and the checker entry are the same candle.

## Contracts taken

Priced paper contracts. A paper row is not a taken trade and is not a pattern. Return is the recorded premium.

| Trade | Reason | Entry premium | Exit premium | Return |
|---|---|---|---|---|
| AMZN 10/19 253.15 call | sma | 0.52 | 5.65 | +986% |
| AAPL 10/19 343.50 call | sma | 0.32 | 0.04 | -87% |
| TSLA 10/19 362.50 call | sma | 0.57 | 0.04 | -93% |
| NVDA 10/20 217.50 call | retest | 0.44 | 0.34 | -23% |
| AAPL 10/20 340 call | sma | 0.93 | 0.39 | -58% |
| AAPL 10/21 340 call | retest | 0.38 | 0.18 | -53% |
| AMZN 10/21 260.50 put | retest | 0.28 | 0.15 | -46% |

The AMZN call is the only large winner. No later red close, still above 253.15, was lower than the fill before the 08:50 target. Waiting for a deeper red would have missed it. The losing calls did print a later lower red before the recorded exit. That later close was the path into the reclaim, and the same wait would also have skipped the winner. Purple versus yellow did not separate them. Distance from the level did not separate them: the winner filled $2.04 above 253.15, and the TSLA call filled $5.01 above 362.50 and expired worthless.

## Replay

Same exits as the live checker. Stock points only. The variant keeps the retest tag, then skips the first same-color candle after the cross and takes the next one only when its close pushes farther. The 2026-10-21 book is the file at `fa26dd1`, replayed on Yahoo bars through 13:00 PT.

| Book | Retest trades | Retest net | Skip trades | Skip net |
|---|---|---|---|---|
| 2026-10-14 | 6 | -2.00 | 3 | -3.05 |
| 2026-10-15 | 4 | +10.20 | 4 | +7.86 |
| 2026-10-16 | 1 | +2.18 | 1 | +2.18 |
| 2026-10-21 | 3 | +8.25 | 1 | +4.04 |
| Combined | 14 | +18.63 | 9 | +11.03 |

Retest win rate is 7 of 14, 50%, profit factor 4.14, +1.33 a trade. The skip wins 5 of 9, 56%, profit factor 4.29, +1.23 a trade.

A stricter body rule, requiring the later candle to push more points than the prior same-color candle, kept 4 trades and net +5.49. Requiring the body to clear half the 14 ATR dropped the confirmed SPCX winner. The 09:20 push was +0.34 and the ATR was 1.08.

The skip's higher win rate came from dropping trades, including the 2026-10-14 GOOGL put (+3.11) and the 2026-10-21 PLTR call (+4.93). The 2026-10-15 AAPL put went from +2.21 at 07:30 to -0.30 at 12:00.

## Decision

The profit rate did not improve in a way that raises the book. Win rate and profit factor ticked up. Net stock points and the points per trade fell. The variant is not an entry. `rules/ta_rules.md` is unchanged. The live entry stays the retest. No order was placed.

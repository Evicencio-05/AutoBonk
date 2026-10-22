# Paper trades

Monday 2026-10-19 through Wednesday 2026-10-21 are paper. Each row is a checker entry or exit. Nothing here was sent to Robinhood. Thursday 2026-10-22 is live and is written in `alerts/live.md`, not here. A row does not fill the journal Trade column and is not a pattern.

Premiums on these rows are the Robinhood 10-minute print for the contract under the $100 cap. Profit on the dashboard is one contract.

- The candle, RSI, SMAs, nearby levels, and volume for each row are in `alerts/context.md`.
- SPCX 146.50 has no contract. At the 6:30 option open the 150 call was $1.10, and the next strike, 152.5, is $5.20 above the 147.30 stock fill with no upside target on that level.
- AMZN 253.15 is the 257.5 call. The stock filled at 6:10, before options printed. The premium is the 6:30 open.
- AMZN 258.30 has no contract. The 262.5 call was $1.17, and 265 is past the 263.15 target.
- AMZN 261.00 has no contract. The 262.5 call was $1.11 at the fill, and 265 is past the 263.15 target.

| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium |
|------|--------|--------|------|-------|------|--------|----------|---------|
| 2026-10-19 05:40 PT | SPCX | entry | call | 146.50 | 147.30 | sma | none | |
| 2026-10-19 06:20 PT | AMZN | entry | call | 253.15 | 255.19 | sma | 10/19 257.5C | 0.52 |
| 2026-10-19 07:40 PT | AAPL | entry | call | 343.50 | 345.18 | sma | 10/19 347.5C | 0.32 |
| 2026-10-19 07:50 PT | SPCX | entry | call | 148.50 | 149.11 | sma | 10/19 150C | 0.60 |
| 2026-10-19 08:10 PT | AAPL | exit | call | 343.50 | 343.09 | reclaim | 10/19 347.5C | 0.04 |
| 2026-10-19 08:30 PT | GOOGL | entry | call | 344.55 | 345.60 | sma | 10/19 347.5C | 0.37 |
| 2026-10-19 08:50 PT | AMZN | exit | call | 253.15 | 263.16 | target | 10/19 257.5C | 5.65 |
| 2026-10-19 08:50 PT | TSLA | entry | call | 362.50 | 367.51 | sma | 10/19 370C | 0.57 |
| 2026-10-19 09:10 PT | AMZN | entry | call | 258.30 | 262.98 | sma | none | |
| 2026-10-19 09:20 PT | AMZN | exit | call | 258.30 | 263.29 | target | none | |
| 2026-10-19 09:40 PT | AMZN | entry | call | 261.00 | 263.03 | sma | none | |
| 2026-10-19 10:10 PT | GOOGL | exit | call | 344.55 | 344.22 | reclaim | 10/19 347.5C |  |
| 2026-10-19 10:10 PT | SPCX | exit | call | 148.50 | 148.24 | reclaim | 10/19 150C |  |
| 2026-10-20 05:30 PT | META | entry | put | 700.00 | 698.53 | sma | none |  |
| 2026-10-20 05:40 PT | META | exit | put | 700.00 | 700.01 | reclaim | none |  |
| 2026-10-20 05:40 PT | SPCX | exit | put | 146.50 | 146.59 | reclaim |  |  |
| 2026-10-20 06:40 PT | AAPL | exit | put | 340.30 | 341.08 | reclaim |  |  |
| 2026-10-20 07:00 PT | SPCX | entry | put | 146.50 | 144.30 | sma | none |  |
| 2026-10-20 07:20 PT | SPCX | exit | put | 146.50 | 147.21 | reclaim | none |  |
| 2026-10-20 07:50 PT | NVDA | entry | call | 217.50 | 217.70 | retest | 10/21 222.5C | 0.44 |
| 2026-10-20 07:50 PT | SPCX | entry | call | 146.60 | 147.90 | sma | none |  |
| 2026-10-20 08:00 PT | AAPL | entry | call | 340.00 | 341.88 | sma | 10/21 345C | 0.93 |
| 2026-10-20 08:20 PT | NVDA | exit | call | 217.50 | 217.20 | reclaim | 10/21 222.5C |  |
| 2026-10-20 08:20 PT | TSLA | entry | call | 370.00 | 376.43 | sma | none |  |
| 2026-10-20 08:40 PT | SPCX | exit | call | 146.60 | 146.26 | reclaim | none |  |
| 2026-10-21 07:30 PT | AAPL | entry | call | 340.00 | 340.35 | retest | 10/21 342.5C | 0.38 |
| 2026-10-21 07:30 PT | AMZN | entry | put | 260.50 | 260.23 | retest | 10/21 257.5P | 0.28 |
| 2026-10-19 12:45 PT | TSLA | exit | call | 362.50 | 369.03 | expiry | 10/19 370C | 0.04 |
| 2026-10-21 12:45 PT | AAPL | exit | call | 340.00 | 343.88 | expiry | 10/21 345C | 0.20 |
| 2026-10-21 12:45 PT | AAPL | exit | call | 340.00 | 343.88 | expiry | 10/21 342.5C | 1.82 |
| 2026-10-21 12:45 PT | AMZN | exit | put | 260.50 | 262.37 | expiry | 10/21 257.5P | 0.05 |
| 2026-10-19 12:50 PT | SPCX | exit | call | 146.50 | 147.30 | clock | none |  |
| 2026-10-19 12:50 PT | AMZN | exit | call | 261.00 | 263.32 | clock | none |  |
| 2026-10-20 12:50 PT | TSLA | exit | call | 370.00 | 375.11 | clock | none |  |

## Open marks

| Contract | Premium | As of | Source |
|----------|---------|-------|--------|

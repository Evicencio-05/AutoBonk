# Contract comparison

The chosen row is the strike at or under $1. On a next-day expiration the live plan names the cash row, the nearest strike one contract can buy at or under $0.50, when the far target can still reach it. Same-day expiration is eligible until noon Pacific. A 0DTE strike past the halfway point between the stock and the far target is not taken. Halfway does not refuse a next-day strike. A name with no listing that day uses the nearest expiration that is listed. The other rows are that same fill. Price is the latest print while the row is open, and the exit bar once it closes. Return is the percent change in the premium. A rule that picks the same contract as an earlier row is not repeated. The cash row is kept either way, so the halfway flag stays. Nothing here is an order.

- dte: the same strike rule on same-day expiration
- first: the first target is the ceiling
- cheap: the furthest strike under $1 that is still inside the far target
- week: Friday's expiration, the same strike rule as chosen
- cash: the nearest strike at or under $0.50 that the far target can still reach. This is the named live contract on a next-day expiration. The chosen row stays on the plan as the $1 comparison.

| Time | Ticker | Level | Role | Contract | Entry | Price | Return | State |
|------|--------|-------|------|----------|-------|-------|--------|-------|
| 2026-10-20 07:00 PT | SPCX | 146.50 | chosen | none |  |  |  | exit |
| 2026-10-20 07:00 PT | SPCX | 146.50 | first | none |  |  |  | exit |
| 2026-10-20 07:00 PT | SPCX | 146.50 | cheap | none |  |  |  | exit |
| 2026-10-20 07:50 PT | NVDA | 217.50 | chosen | 10/21 222.5C | 0.44 | 0.34 | -22.7% | exit |
| 2026-10-20 07:50 PT | NVDA | 217.50 | first | none |  |  |  | exit |
| 2026-10-20 07:50 PT | NVDA | 217.50 | cheap | 10/21 225C | 0.17 | 0.11 | -35.3% | exit |
| 2026-10-20 07:50 PT | NVDA | 217.50 | week | 10/23 225C | 0.78 | 0.66 | -15.4% | exit |
| 2026-10-20 07:50 PT | SPCX | 146.60 | chosen | none |  |  |  | exit |
| 2026-10-20 07:50 PT | SPCX | 146.60 | first | none |  |  |  | exit |
| 2026-10-20 07:50 PT | SPCX | 146.60 | cheap | none |  |  |  | exit |
| 2026-10-20 08:00 PT | AAPL | 340.00 | chosen | 10/21 345C | 0.93 | 0.39 | -58.1% | exit |
| 2026-10-20 08:00 PT | AAPL | 340.00 | first | none |  |  |  | exit |
| 2026-10-20 08:00 PT | AAPL | 340.00 | cheap | 10/21 350C | 0.14 | 0.04 | -71.4% | exit |
| 2026-10-20 08:00 PT | AAPL | 340.00 | week | 10/23 350C | 0.83 | 0.45 | -45.8% | exit |
| 2026-10-20 05:30 PT | META | 700.00 | chosen | none |  |  |  | exit |
| 2026-10-20 05:30 PT | META | 700.00 | dte | none |  |  |  | exit |
| 2026-10-20 05:30 PT | META | 700.00 | first | none |  |  |  | exit |
| 2026-10-20 05:30 PT | META | 700.00 | cheap | none |  |  |  | exit |
| 2026-10-20 05:30 PT | META | 700.00 | week | none |  |  |  | exit |
| 2026-10-20 07:00 PT | SPCX | 146.50 | dte | none |  |  |  | exit |
| 2026-10-20 07:50 PT | NVDA | 217.50 | dte | none |  |  |  | exit |
| 2026-10-20 07:50 PT | SPCX | 146.60 | dte | none |  |  |  | exit |
| 2026-10-20 08:00 PT | AAPL | 340.00 | dte | none |  |  |  | exit |
| 2026-10-20 08:20 PT | TSLA | 370.00 | chosen | none |  |  |  | exit |
| 2026-10-20 08:20 PT | TSLA | 370.00 | dte | none |  |  |  | exit |
| 2026-10-20 08:20 PT | TSLA | 370.00 | first | none |  |  |  | exit |
| 2026-10-20 08:20 PT | TSLA | 370.00 | cheap | none |  |  |  | exit |
| 2026-10-21 07:30 PT | AAPL | 340.00 | chosen | 10/21 342.5C | 0.38 | 0.18 | -52.6% | exit |
| 2026-10-21 07:30 PT | AAPL | 340.00 | cheap | 10/21 345C | 0.08 | 0.03 | -62.5% | exit |
| 2026-10-21 07:30 PT | AAPL | 340.00 | week | none |  |  |  | exit |
| 2026-10-21 07:30 PT | AMZN | 260.50 | chosen | 10/21 257.5P | 0.28 | 0.15 | -46.4% | exit |
| 2026-10-21 07:30 PT | AMZN | 260.50 | first | none |  |  |  | exit |
| 2026-10-21 07:30 PT | AMZN | 260.50 | cheap | 10/21 255P | 0.07 | 0.04 | -42.9% | exit |
| 2026-10-21 07:30 PT | AMZN | 260.50 | week | none |  |  |  | exit |
| 2026-10-22 08:30 PT | SPCX | 150.00 | chosen | 10/23 146P | 0.90 | 3.03 | +236.7% | exit |
| 2026-10-22 08:30 PT | SPCX | 150.00 | dte | none |  |  |  | exit |
| 2026-10-22 08:30 PT | SPCX | 150.00 | first | 10/23 150P | 2.38 | 5.70 | +139.5% | exit |
| 2026-10-22 08:30 PT | SPCX | 150.00 | cheap | 10/23 139P | 0.11 | 0.51 | +363.6% | exit |
| 2026-10-22 08:30 PT | SPCX | 150.00 | cash | 10/23 144P | 0.49 | 1.99 | +306.1% | exit |

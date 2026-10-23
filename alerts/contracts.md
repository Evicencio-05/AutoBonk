# Contract comparison

The chosen row is the strike at or under $1. On a next-day expiration the live plan names the cash row, the nearest strike one contract can buy with the account balance, when the far target can still reach it. Same-day expiration is eligible until noon Pacific. A 0DTE strike past the halfway point between the stock and the far target is not taken. Halfway does not refuse a next-day strike. A name with no listing that day uses the nearest expiration that is listed. The other rows are that same fill. Price is the latest print while the row is open, and the exit bar once it closes. Return is the percent change in the premium. A rule that picks the same contract as an earlier row is not repeated. The cash row is kept either way, so the halfway flag stays. Nothing here is an order.

- dte: the same strike rule on same-day expiration
- first: the first target is the ceiling
- cheap: the furthest strike under $1 that is still inside the far target
- week: Friday's expiration, the same strike rule as chosen
- cash: the nearest strike the account balance can buy that the far target can still reach. This is the named live contract on a next-day expiration. The chosen row stays on the plan as the $1 comparison.

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
| 2026-10-23 06:40 PT | TSLA | 372.75 | chosen | 10/30 377.5C | 7.05 | 6.10 | -13.5% | exit |
| 2026-10-23 06:40 PT | TSLA | 372.75 | dte | none |  |  |  | exit |
| 2026-10-23 06:40 PT | TSLA | 372.75 | cheap | none |  |  |  | exit |
| 2026-10-23 06:40 PT | TSLA | 372.75 | week | none |  |  |  | exit |
| 2026-10-23 06:40 PT | TSLA | 372.75 | cash | none |  |  |  | exit |
| 2026-10-23 07:40 PT | GOOGL | 322.75 | chosen | 10/23 325C | 0.54 | 0.18 | -66.7% | exit |
| 2026-10-23 07:40 PT | GOOGL | 322.75 | cheap | 10/23 335C | 0.01 | 0.01 | +0.0% | exit |
| 2026-10-23 07:40 PT | GOOGL | 322.75 | cash | 10/23 327.5C | 0.14 | 0.04 | -71.4% | exit |
| 2026-10-23 09:10 PT | META | 645.00 | chosen | 10/23 650C | 1.00 | 1.27 | +27.0% | exit |
| 2026-10-23 09:10 PT | META | 645.00 | first | none |  |  |  | exit |
| 2026-10-23 09:10 PT | META | 645.00 | cheap | 10/23 655C | 0.32 | 0.40 | +25.0% | exit |
| 2026-10-23 09:10 PT | META | 645.00 | cash | 10/23 655C | 0.32 | 0.40 | +25.0% | exit |
| 2026-10-23 09:00 PT | TSLA | 372.77 | chosen | 10/23 377.5C | 0.48 | 0.42 | -12.5% | exit |
| 2026-10-23 09:00 PT | TSLA | 372.77 | cheap | 10/23 387.5C | 0.03 | 0.03 | +0.0% | exit |
| 2026-10-23 09:00 PT | TSLA | 372.77 | cash | 10/23 377.5C | 0.48 | 0.42 | -12.5% | exit |
| 2026-10-23 09:40 PT | AVGO | 324.60 | chosen | 10/23 327.5C | 0.41 | 0.29 | -29.3% | exit |
| 2026-10-23 09:40 PT | AVGO | 324.60 | cheap | 10/23 330C | 0.11 | 0.08 | -27.3% | exit |
| 2026-10-23 09:40 PT | AVGO | 324.60 | cash | 10/23 327.5C | 0.41 | 0.29 | -29.3% | exit |
| 2026-10-23 10:40 PT | SPCX | 146.59 | chosen | 10/23 147C | 0.61 | 0.73 | +19.7% | exit |
| 2026-10-23 10:40 PT | SPCX | 146.59 | cheap | 10/23 157.5C | 0.01 | 0.01 | +0.0% | exit |
| 2026-10-23 10:40 PT | SPCX | 146.59 | cash | 10/23 148C | 0.27 | 0.28 | +3.7% | exit |
| 2026-10-23 10:50 PT | AVGO | 324.60 | chosen | 10/23 322.5P | 0.43 |  |  | exit |
| 2026-10-23 10:50 PT | AVGO | 324.60 | cheap | 10/23 320P | 0.09 |  |  | exit |
| 2026-10-23 10:50 PT | AVGO | 324.60 | cash | 10/23 322.5P | 0.43 |  |  | exit |
| 2026-10-23 11:00 PT | GOOGL | 322.75 | chosen | 10/23 322.5P | 0.75 | 1.47 | +96.0% | exit |
| 2026-10-23 11:00 PT | GOOGL | 322.75 | cheap | 10/23 320P | 0.09 | 0.22 | +144.4% | exit |
| 2026-10-23 11:00 PT | GOOGL | 322.75 | cash | 10/23 320P | 0.09 | 0.22 | +144.4% | exit |
| 2026-10-23 11:20 PT | AVGO | 324.60 | chosen | 10/23 325C | 0.88 | 0.70 | -20.5% | exit |
| 2026-10-23 11:20 PT | AVGO | 324.60 | cheap | 10/23 345C | 0.04 | 0.01 | -75.0% | exit |
| 2026-10-23 11:20 PT | AVGO | 324.60 | cash | 10/23 327.5C | 0.18 | 0.13 | -27.8% | exit |

# Live plans

Thursday 2026-10-22 is the first live session. Agentic only. Cash is $50, so one contract at or under $0.50. A row waits for confirm. It is not an order and it is not a paper row. The fade checker stays off. On a next-day expiration the contract column is the nearest strike at or under $0.50 that the far target can still reach. Halfway does not refuse that expiration. On 0DTE, halfway still refuses that strike. The $1 strike and the cash strike are both recorded, with the entry premium, and both are marked at the exit. A cash cell of quote means the chain was not priced, and the next check tries again.

The 08:30 PT row was written before that naming. Its contract cell is still the $1 strike. The cash strike is recorded beside it, and both are marked at the 12:50 PT exit. The 06:40 PT TSLA row was written before that naming too. Its contract cell is still 10/30 377.5C at 7.05, and the cash strike is none. It waits for confirm.

| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium | Cash | $1 strike | $1 premium | Cash strike | Cash premium | Halfway |
|------|--------|--------|------|-------|------|--------|----------|---------|------|-----------|------------|-------------|--------------|---------|
| 2026-10-22 08:30 PT | SPCX | entry | put | 150.00 | 149.80 | retest | 10/23 146P | 0.90 | over | 10/23 146P | 0.90 | 10/23 144P | 0.49 | past |
| 2026-10-22 12:50 PT | SPCX | exit | put | 150.00 | 144.92 | clock | 10/23 146P | 3.03 |  | 10/23 146P | 3.03 | 10/23 144P | 1.99 |  |
| 2026-10-23 06:40 PT | TSLA | entry | call | 372.75 | 373.14 | retest | 10/30 377.5C | 7.05 | over | 10/30 377.5C | 7.05 | none |  |  |
| 2026-10-23 07:40 PT | GOOGL | entry | call | 322.75 | 322.96 | retest | 10/23 327.5C | 0.14 | fits | 10/23 325C | 0.54 | 10/23 327.5C | 0.14 | inside |
| 2026-10-23 09:00 PT | TSLA | entry | call | 372.77 | 372.89 | retest | 10/23 377.5C | 0.48 | fits | 10/23 377.5C | 0.48 | 10/23 377.5C | 0.48 | inside |
| 2026-10-23 09:10 PT | META | entry | call | 645.00 | 645.41 | retest | 10/23 655C | 0.32 | fits | 10/23 650C | 1.00 | 10/23 655C | 0.32 | inside |
| 2026-10-23 09:30 PT | META | exit | call | 645.00 | 642.88 | reclaim | 10/23 655C | |  | 10/23 650C |  | 10/23 655C |  |  |
| 2026-10-23 09:30 PT | TSLA | exit | call | 372.77 | 370.34 | reclaim | 10/23 377.5C | |  | 10/23 377.5C |  | 10/23 377.5C |  |  |
| 2026-10-23 09:40 PT | AVGO | entry | call | 324.60 | 324.92 | retest | 10/23 327.5C | 0.41 | fits | 10/23 327.5C | 0.41 | 10/23 327.5C | 0.41 | inside |
| 2026-10-23 10:30 PT | AVGO | exit | call | 324.60 | 323.96 | reclaim | 10/23 327.5C | |  | 10/23 327.5C |  | 10/23 327.5C |  |  |
| 2026-10-23 10:30 PT | GOOGL | exit | call | 322.75 | 322.14 | reclaim | 10/23 327.5C | |  | 10/23 325C |  | 10/23 327.5C |  |  |
| 2026-10-23 10:40 PT | SPCX | entry | call | 146.59 | 146.82 | retest | 10/23 148C | 0.27 | fits | 10/23 147C | 0.61 | 10/23 148C | 0.27 | inside |
| 2026-10-23 10:50 PT | AVGO | entry | put | 324.60 | 324.33 | retest | 10/23 322.5P | 0.43 | fits | 10/23 322.5P | 0.43 | 10/23 322.5P | 0.43 | inside |
| 2026-10-23 11:00 PT | AVGO | exit | put | 324.60 | 325.11 | reclaim | 10/23 322.5P | |  | 10/23 322.5P |  | 10/23 322.5P |  |  |
| 2026-10-23 11:00 PT | GOOGL | entry | put | 322.75 | 322.42 | retest | 10/23 320P | 0.09 | fits | 10/23 322.5P | 0.75 | 10/23 320P | 0.09 | inside |
| 2026-10-23 11:20 PT | AVGO | entry | call | 324.60 | 324.80 | retest | 10/23 327.5C | 0.18 | fits | 10/23 325C | 0.88 | 10/23 327.5C | 0.18 | inside |
| 2026-10-23 12:00 PT | AVGO | exit | call | 324.60 | 324.10 | reclaim | 10/23 327.5C | 0.10 |  | 10/23 325C |  | 10/23 327.5C |  |  |
| 2026-10-23 12:10 PT | SPCX | exit | call | 146.59 | 145.95 | reclaim | 10/23 148C | |  | 10/23 147C |  | 10/23 148C |  |  |
| 2026-10-23 12:30 PT | GOOGL | exit | put | 322.75 |  | expiry | 10/23 320P | 0.24 |  | 10/23 322.5P |  | 10/23 320P |  |  |
| 2026-10-23 06:50 PT | TSLA | exit | call | 372.75 | 369.50 | reclaim | 10/30 377.5C | |  | 10/30 377.5C |  | none |  |  |

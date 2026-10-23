# Live plans

Thursday 2026-10-22 is the first live session. Agentic only. Cash is $50, so one contract at or under $0.50. A row waits for confirm. It is not an order and it is not a paper row. The fade checker stays off. On a next-day expiration the contract column is the nearest strike at or under $0.50 that the far target can still reach. Halfway does not refuse that expiration. On 0DTE, halfway still refuses that strike. The $1 strike and the cash strike are both recorded, with the entry premium, and both are marked at the exit. A cash cell of quote means the chain was not priced, and the next check tries again.

The 08:30 PT row was written before that naming. Its contract cell is still the $1 strike. The cash strike is recorded beside it, and both are marked at the 12:50 PT exit. The 06:40 PT TSLA row was written before that naming too. Its contract cell is still 10/30 377.5C at 7.05, and the cash strike is none. It waits for confirm.

| Time | Ticker | Action | Side | Level | Fill | Reason | Contract | Premium | Cash | $1 strike | $1 premium | Cash strike | Cash premium | Halfway |
|------|--------|--------|------|-------|------|--------|----------|---------|------|-----------|------------|-------------|--------------|---------|
| 2026-10-22 08:30 PT | SPCX | entry | put | 150.00 | 149.80 | retest | 10/23 146P | 0.90 | over | 10/23 146P | 0.90 | 10/23 144P | 0.49 | past |
| 2026-10-22 12:50 PT | SPCX | exit | put | 150.00 | 144.92 | clock | 10/23 146P | 3.03 |  | 10/23 146P | 3.03 | 10/23 144P | 1.99 |  |
| 2026-10-23 06:40 PT | TSLA | entry | call | 372.75 | 373.14 | retest | 10/30 377.5C | 7.05 | over | 10/30 377.5C | 7.05 | none |  |  |

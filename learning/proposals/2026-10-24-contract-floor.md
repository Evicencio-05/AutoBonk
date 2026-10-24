---
title: Do not buy a live contract under $0.15
kind: decision
status: accepted
created: 2026-10-24
recommendation: accept
---

# Do not buy a live contract under $0.15

## Summary
The checker buys the contract the balance can pay. With a small balance that means deep out-of-the-money 0DTE contracts at $0.09–0.13, where the bid–ask spread alone costs 8–17% of the trade. This floor refuses any live contract under $0.15. I proposed $0.20; the operator set $0.15 for now and will raise it later. The signal is still written and scored as a what-if, so the data keeps building. Accepted by the operator 2026-10-23 and shipped before the freeze.

## The problem
- All three live trades so far were $0.12–0.13 contracts: `1023-0740-GOOGL-call` −$11, `1023-1100-GOOGL-put` +$12, `1023-1120-AVGO-call` −$3.
- At $0.12, a one-cent spread on each side is about 17% of the trade before the stock moves. At $0.20 it is 10%; at $0.50, 4%.
- The Agentic balance is $11.88 now, so without a floor the checker can only buy contracts at $0.11 or less.

## The change
`MIN_PREMIUM = 0.15` in `scripts/claim_alerts.py` (proposed 0.20; set to 0.15 by the operator on 2026-10-23). A live entry whose named contract costs less than that per share is not sent, and its plan row records `order_block: floor`. Set it to 0 to turn the floor off. It gates the order only: no replayed entry, exit, or skip moves, and `freeze.py check` is clean.

## Evidence
- Sample: 3 live trades and 7 what-if signals over 2 live days. That is far too few to find a floor from results.
- Results do not separate by price yet. The one winner (SPCX 10/23 146P, +$213 what-if) cost $0.90, but the $0.20–0.50 what-ifs lost $116 over 5, and the cheapest live trades made −$2 over 3.
- The case rests on cost, not on a pattern: the spread share of a $0.12 contract is several times that of a $0.50 one, on every trade, win or lose.

## Expected impact
- With $11.88: no live orders until the account holds at least $15. Every signal becomes a what-if.
- Once funded: live contracts start at $0.15, with spread cost at about 13% or less. Low confidence on the size of the gain, high confidence on the direction.

## Risks
- **No live sample while the balance is under $15.** The freeze counter stays at 0, so you cannot watch live trades "work out" before funding. Judge on the what-if results in the ledger and the Overview instead. They are priced from the broker's own option bars.
- A cheap contract that works, like the $0.12 GOOGL put that Robinhood closed at $0.24 (+$12), is skipped. It still shows up as a what-if, so we will see it.

## Alternatives considered
- **A strike-distance floor** (skip contracts more than X% out of the money): the one winner was the furthest out (2.5%), so the data argues against it for now.
- **No floor:** keeps live trades flowing at $0.11 or less, with most of each trade going to the spread.

## How we will know
At each weekly review, compare floor-blocked what-ifs against funded live trades at $0.15 or more. If blocked contracts beat the funded ones over 20 or more signals, lower or remove the floor. If funded trades between $0.15 and $0.20 lose to the spread, raise it to $0.20 as first proposed.

## Rollout and rollback
Shipped. Roll back with `MIN_PREMIUM = 0`. No bless needed, because it changes no replayed decision.

## Operator decision
Decision: accept
Notes: Accepted 2026-10-23 ("add 4"). Floor set to $0.15 for now; raise later.

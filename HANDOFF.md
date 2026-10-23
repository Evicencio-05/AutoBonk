# AutoBonk handoff

Open this project at `/home/evice/repos/AutoBonk`.

## Read first

1. `rules/ta_rules.md`. Do not invent rules.
2. `learning/journal.md`. A pattern exists only after the same feature shows up in more than one trade the operator confirmed and that was actually taken.
3. `learning/goals.yaml`. The first goal is sniping the bottom on contracts. A goal is a lesson. It is not a live rule.
4. `alerts/levels.yaml`. This is the live book. Charts in `charts/inbox/` are not the live book until a levels file is written from the note.

## What runs

- `scripts/claim_alerts.py` checks finished 10-minute bars and can post an alert to Discord `#ta`. An alert is not an order. A live entry is a level retest. A lost support is resistance, and a claimed resistance is support. An SMA hold, or an RSI cross on an open trade, is a watch. A watch is not a paper row and not an order.
- After the cash close, fill `learning/daily_review.md` into `learning/reviews/YYYY-MM-DD.md` and append that day's fade fills in `alerts/fade_forward.md`. A review is not a pattern and does not change the live checker.
- `scripts/bench.py` replays one frozen levels file and one settings snapshot. A replay is an observation. It does not change `rules/ta_rules.md` or the live defaults.
- `scripts/discord_ta.py` reads `#ta` forwards. Ingest saves images under `charts/inbox/`.

```bash
python3 scripts/discord_ta.py read --channel ta
python3 scripts/discord_ta.py ingest --channel ta
python3 scripts/claim_alerts.py check
```

## Orders

- Robinhood Agentic only. Do not trade the taxable account or the IRA.
- Paper never places an order. A live qualifying entry is sent on the Agentic account, and so is the sell when that contract is still open. Every other plan waits.
- Monday 2026-10-19 through Wednesday 2026-10-21 are paper. Those rows stay in `alerts/paper.md`. The candle, RSI, SMAs, nearby levels, and volume for a row are in `alerts/context.md`. Do not place an order for a paper session, including after confirm. A paper row does not fill the journal Trade column and is not a pattern.
- Thursday 2026-10-22 is the first live session. Agentic only. Cash is $50, so one contract at or under $0.50. The checker writes the plan in `alerts/live.md`. It sends that contract when the far target can still reach the strike. Halfway refuses 0DTE only. A cash strike of none, an empty ladder, or a debit over $0.50 stays a plan. The exit of an open Agentic contract is a sell. A sell that is already working is not sent again.
- The fade test in `alerts/fade_forward.md` covered 2026-10-19 through 2026-10-21. The gate passed: profit factor 3.17, net +8.56 stock points, 13 closes. The fade record is paper. The live checker stays on the retest.
- A long option can cost up to $100 per contract.
- Do not write `config/agentic.yaml` or `.env`. Do not print `TA_BOT_TOKEN` or account numbers.

## Not inputs

TradeWhisperer, GEX/VEX, and fundamentals.

## Later

A lower level is skipped when the next posted number has been tagged and the close came back through it. A later close through that number clears the skip. The 2026-10-19 AAPL call at 345.18 is the example: 345.40 was tagged and did not hold. An entry whose priced contract is none is skipped. A check more than 20 minutes late still writes that session's paper entry and exit, or the live plan once the session is live, and it does not send the Discord alert. A prior session does not gain a new entry. An entry that is still open after its 12:50 bar is closed on a later check. That close is the reclaim, the last target, or the 12:50 bar, and it does not send the Discord alert. The fade test is unchanged.

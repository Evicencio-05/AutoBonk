# AutoBonk handoff

Open this project at `/home/evice/repos/AutoBonk`.

## Read first

1. `rules/ta_rules.md`. Do not invent rules.
2. `learning/journal.md`. A pattern exists only after the same feature shows up in more than one trade the operator confirmed and that was actually taken.
3. `alerts/levels.yaml`. This is the live book. Charts in `charts/inbox/` are not the live book until a levels file is written from the note.

## What runs

- `scripts/claim_alerts.py` checks finished 10-minute bars and can post an alert to Discord `#ta`. An alert is not an order. A live entry is a level retest. An SMA hold, or an RSI cross on an open trade, is a watch. A watch is not a paper row and not an order.
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
- No order without an explicit confirm.
- Monday 2026-10-19 is paper only. The Agentic account is empty on purpose. Log each checker entry and exit in `alerts/paper.md`. The candle, RSI, SMAs, nearby levels, and volume for that row are in `alerts/context.md`. Do not place an order, including after confirm. A paper row does not fill the journal Trade column and is not a pattern.
- The fade test in `alerts/fade_forward.md` covered 2026-10-19 through 2026-10-21. The gate passed: profit factor 3.17, net +8.56 stock points, 13 closes. The fade record is paper. The live checker stays on the retest. Real money waits until the operator says so.
- A long option can cost up to $100 per contract.
- Do not write `config/agentic.yaml` or `.env`. Do not print `TA_BOT_TOKEN` or account numbers.

## Not inputs

TradeWhisperer, GEX/VEX, and fundamentals.

## Later

A lower level is skipped when the next posted number has been tagged and the close came back through it. A later close through that number clears the skip. The 2026-10-19 AAPL call at 345.18 is the example: 345.40 was tagged and did not hold. An entry whose priced contract is none is skipped. A check more than 20 minutes late still writes that session's paper entry and exit, and it does not send the Discord alert. A prior session is left as it was. The fade test is unchanged.

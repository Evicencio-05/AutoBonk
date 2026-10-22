# AutoBonk

Agentic trading from the operator's own technical analysis. Ideas come from charts the operator forwards, not from screeners or research reports.

## Loop

1. Read `rules/ta_rules.md` before judging a chart. Do not invent rules.
2. Read `charts/pm_levels_index.md`. Dated packs are archives. The live book is `alerts/levels.yaml`.
3. Draft a plan for Robinhood Agentic only.
4. Place an order only after the operator replies confirm.
5. Record the posted setup, and later the trade result, in `learning/journal.md`.

## Limits

- Trade the Agentic account only. Do not trade the taxable account or the IRA.
- Do not write `config/agentic.yaml`. The operator set the cap at $100 per contract.
- No autonomous orders.
- TradeWhisperer, GEX/VEX, and fundamentals are not inputs.

## Discord

`scripts/discord_ta.py` keeps forwarded chart text and images. A normal Discord client shows those posts as empty.

```bash
python3 scripts/discord_ta.py read --channel ta
python3 scripts/discord_ta.py ingest --channel ta
```

Token: `TA_BOT_TOKEN` in `.env`. Never commit it. Image URLs expire; `ingest` saves files under `charts/inbox/`.

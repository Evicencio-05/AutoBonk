# AutoBonk

Agentic trading from the operator's own technical analysis. Ideas come from charts the operator forwards, not from screeners or research reports.

## Read first

1. `rules/ta_rules.md`. Do not invent rules.
2. `charts/pm_levels_index.md`. Dated packs are archives.
3. `alerts/levels.yaml`. This is the live book. Charts in `charts/inbox/` are not the live book until a levels file is written from the note.
4. `learning/journal.md`. A pattern exists only after the same feature shows up in more than one trade the operator confirmed and that was actually taken.
5. `learning/goals.yaml`. The first goal is sniping the bottom on contracts. A goal is a lesson. It is not a live rule.

`AGENTS.md` says what a coding agent may do and which agent takes which task. The checker rules are in `.cursor/rules/autobonk.mdc`, and the learning rules are in `.cursor/rules/ta-learning.mdc`.

## Loop

1. Judge a chart against `rules/ta_rules.md` and the live book.
2. Draft a plan for Robinhood Agentic only.
3. The checker sends a qualifying live entry and its exit. Any other order waits until the operator replies confirm, and the operator places it.
4. Record the posted setup, and later the trade result, in `learning/journal.md`.

## What runs

- `scripts/claim_alerts.py` checks finished 10-minute bars from the systemd timer in `alerts/systemd/` and can post an alert to Discord `#ta`. An alert is not an order. A live entry is a level retest. A lost support is resistance, and a claimed resistance is support. An SMA hold, or an RSI cross on an open trade, is a watch. A watch is not a paper row and not an order.
- `scripts/bench.py` replays one frozen levels file and one settings snapshot.
- `scripts/discord_ta.py` reads `#ta` forwards. A normal Discord client shows those posts as empty. Image URLs expire; `ingest` saves files under `charts/inbox/`.

```bash
python3 scripts/discord_ta.py read --channel ta
python3 scripts/discord_ta.py ingest --channel ta
python3 scripts/recap.py               # after the cash close
python3 scripts/claim_alerts.py check   # the timer runs this; agents do not
```

Token: `TA_BOT_TOKEN` in `.env`. Never commit or print it.

## Limits

- Trade the Agentic account only. Do not trade the taxable account or the IRA.
- Do not write `config/agentic.yaml` or `.env`. The operator set the cap at $100 per contract. Do not print `TA_BOT_TOKEN` or account numbers.
- Paper never places an order. Monday 2026-10-19 through Wednesday 2026-10-21 are paper.
- Thursday 2026-10-22 is the first live session. A live long option is one contract, and the debit has to fit the Agentic account balance.
- TradeWhisperer, GEX/VEX, and fundamentals are not inputs.

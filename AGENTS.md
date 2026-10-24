# Agents in AutoBonk

This file is for every coding agent in this repo: Claude Code, Cursor in the editor, and Cursor cloud agents. The project overview is in `PROJECT.md`, and the trading rules are in `.cursor/rules/`. This file covers what an agent may do and which agent takes which task.

`scripts/agent_guard.py` enforces the limits below through hooks (`.claude/settings.json`, `.cursor/hooks.json`). If a hook refuses a call, the refusal stands. Do not reword the command to get around it. Tell the operator what you were trying to do.

## Never

- **Send, change, or cancel an order.** The systemd timer (`alerts/systemd/autobonk-claims.timer`) runs the checker, and the checker sends the qualifying Agentic entry and its exit. No agent calls `place_option_order`, a `buy`/`sell` on `scripts/robinhood_mcp.py`, or any broker tool that moves money. This holds after the operator replies confirm too. A confirmed manual trade is placed by the operator.
- **Run `scripts/claim_alerts.py check`**, with or without `--notify`. On a live session it sends a real order. Use `pytest` or `scripts/bench.py` to see what it would do.
- **Start, stop, enable, or disable the `autobonk-claims` systemd units.**
- **Read, print, or write `.env` or `.env.*`**, or print `TA_BOT_TOKEN`. Scripts load it themselves.
- **Read or print `config/accounts.yaml`**, or any account number.
- **Write `config/agentic.yaml`** (the operator's $100 cap), **`rules/ta_rules.md`** (the operator's TA), **`alerts/state.json`, or `alerts/broker.json`** (checker state. A hand edit can resend an order).
- **Write a checker tape:** `alerts/live.md`, `paper.md`, `log.md`, `context.md`, `contracts.md`, or `events.jsonl`. This includes running code that writes one from a cloud agent. A cloud agent has no broker, and a tape row it writes can hide a real open position from the checker. On 2026-10-23 a GOOGL exit row added in a Cursor PR meant the checker no longer treated the live put as open, so it never sent the sell. Robinhood's expiring-option close sold it at the 12:30 cutoff, which saved that trade, but the checker had stopped watching it. Generated data (`learning/trades.*`, `bench/golden/`) is rebuilt by its script, never by hand.
- **Change a replayed decision during the freeze.** `config/freeze.yaml` is the operator's switch, and only the operator runs `scripts/freeze.py bless`. A bug fix that changes no decision ships as usual. A new rule, threshold, or buffer becomes a proposal in `learning/proposals/` (the `proposal` skill) for the weekly review.
- **Push to `master` or force-push.** Work on a branch and open a PR.
- **Turn the Robinhood plugin back on in `.cursor/settings.json`.** It is off so no Cursor agent, local or cloud, has order tools in this repo. On 2026-10-23 a Cursor cloud agent placed the 08:10 GOOGL call through it. The checker uses its own saved login (`~/.config/autobonk/robinhood-mcp.json`).
- **Remove `robinhood-trading` from `.cursor/mcp.json`.** The live checker borrows that server's Cursor OAuth login (`_cursor_oauth` in `scripts/robinhood_mcp.py`).
- **Invent a TA rule** or call one observation a pattern (see `.cursor/rules/ta-learning.mdc`).

## Allowed

- Read and change code under `scripts/`, and run the tests: `uvx --with pyyaml --with flask --with 'psycopg[binary]' pytest -q scripts/tests`.
- Replay with `scripts/bench.py` and `scripts/regime_search.py`. A replay is an observation.
- `scripts/discord_ta.py read|ingest`. Chart images land in `charts/inbox/`.
- Write a levels file from an operator note, plus `learning/journal.md`, `learning/reviews/*.md`, `learning/drills.yaml`, `learning/proposals.md` and `learning/proposals/*.md` (never the Operator decision section), and `alerts/fade_forward.md`, as the learning rules describe. Never fill the "Would I take it" column for the operator.
- `scripts/ledger.py sync|snapshot|show`, `scripts/review.py day|week`, `scripts/freeze.py status|check`, and `scripts/alarm.py list`.
- Read-only broker calls: quotes, positions, balance, `review_option_order`.

## Who does what

| Task | Agent | Why |
|---|---|---|
| Checker logic: retests, flips, ATR band, skips, cutoffs, sizing, sells (`claim_alerts.py`, `robinhood_mcp.py`) | **Claude Code** | Rules interact across a 4,000-line file. Needs tests and bench replays, done with the operator present. |
| Reviewing a Cursor PR before merge | **Claude Code** (`/code-review`) | A second model reads any code that can send an order. |
| Reading chart images into `alerts/levels.yaml`, journal, daily review, drills | **Claude Code** | Reads images and follows the exact wording in the learning rules. |
| Backtests, fade and regime replays | **Claude Code** with the `backtest-expert` skill | Overfitting and robustness checks. |
| Ledger, daily and weekly review drafts, testing a proposal against the ledger | **Claude Code** | Reads the dataset and the broker, then writes the observations. |
| Researching and writing a proposal (weekly decisions, daily safety notes) | **Claude Code** with the `proposal` skill | Needs the ledger, the broker's option bars, and the bench. The weekly run is a local timer. |
| Debugging a failure, or a refactor across files | **Claude Code** | Needs to read widely and run things. |
| Recurring work after the close | **Claude Code** `/loop`, run locally | Needs the local `.env`. A cloud routine cannot reach it. |
| Small change with a clear spec, one PR each (a field, a column, a Neon/Vercel/blotter/desk tweak) | **Cursor cloud agent** | Runs unattended and comes back as a PR. Run `/code-review` in Claude Code before merging if it touches the checker. |
| Dashboard HTML/CSS, wording, a rename, a typo | **Cursor in the editor** (Tab / Cmd-K) | Quick, visual, one file. |
| Placing, closing, or changing a trade | **No agent** | Checker or operator only. |

If a task names the checker's order logic and also the page (for example, "show the cutoff on the dashboard"), it goes to Claude Code.

## Routing check

`beforeSubmitPrompt` (Cursor) and `UserPromptSubmit` (Claude Code) run the same router. It splits a message into its tasks (lines, sentences, numbered items, "also ...") and routes each one.

- **All of it belongs in the other tool:** the prompt is stopped, and the message includes a ready-to-paste prompt for that tool. The prompt carries what it needs: read AGENTS.md, the files to start with, the limits, the test command, and what done means.
- **A mix, sent to Claude Code:** Claude does its parts and ends its reply with a ready-to-paste Cursor prompt for the rest.
- **A mix, sent to Cursor:** the prompt is stopped, with the Claude Code part as a ready prompt and the Cursor part to resend.
- **`!here`** anywhere in the prompt runs all of it where you are.

To see the split and the prompts without sending anything:

```bash
python3 scripts/agent_guard.py route "describe the task, or several"
```

When a task you were handed belongs to another agent in the table, say so in the first line of your reply and give the ready-to-paste prompt for it.

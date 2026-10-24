---
name: levels
description: Arm the AutoBonk live book (alerts/levels.yaml) from the operator's #ta levels note, then correct it from the chart images. Use when the operator says the levels or charts are in, asks to ingest or arm levels, or forwards a PM levels note.
---

# Arming the levels book

The note text is parsed by a script, not by you. Your job is the part a script cannot do: reading the chart images. Do not write `alerts/levels.yaml` by hand, and do not retype the note.

## Steps

1. Save the forwards: `python3 scripts/discord_ta.py ingest --channel ta`.
2. Arm the note: `python3 scripts/levels_ingest.py arm --latest`. It prints the ladders it armed, the warnings, and a `Charts:` line with the saved images. Do not open `alerts/levels.yaml` or the note JSON to check it. The printed summary is the check.
3. Open only the images on the `Charts:` line. On each, find the white price labels and fib prices on the operator's levels. Compare them with that ticker's printed ladder.
4. For each ticker whose chart shows a more exact number than the note (Friday 2026-10-23: SPCX 150 → 150.10, TSLA 372.75 → 372.77), resend that ticker's full line, with every number in the note's order:
   ```bash
   printf '%s\n' '- TSLA: Res: 380 -> 382.75 -> 388 / Sup: 372.77 -> 367.75 -> 365.3 -> 360.45 -> 352.01 -> 342.5' \
     | python3 scripts/levels_ingest.py arm - --from "the TSLA chart labels"
   ```
   A whole line replaces that ticker. Only that ticker changes.
5. Tell the operator in a few lines: what was armed, each chart correction (old → new), and every warning the script printed. Do not fix a warning yourself. A typo-looking number (META 573 after 645, AAPL 241.37) stays as printed until the operator resends it.

## Rules

- A number is changed only when a chart label shows it. SMA labels, unnumbered fibs, channels, trend lines, OS and gamma comments are not levels.
- If the script holds a ticker because price already crossed a new number, leave it held and tell the operator. Only the operator decides `--force`.
- If a chart conflicts with the note in a way that is not a more exact print (a different level, a missing one), do not change it. Ask the operator.
- After arming, append the journal rows per `.cursor/rules/ta-learning.mdc` only if the operator asks.

# Daily review

Run this after the cash close, once the 13:00 PT bar is finished. Copy the sections into `learning/reviews/YYYY-MM-DD.md` and fill them from the files below. A review is an observation. It does not change `rules/ta_rules.md` or the live checker, and it does not place an order.

Read `learning/journal.md`, `learning/training.md`, `alerts/levels.yaml`, `alerts/paper.md`, `alerts/live.md`, `alerts/log.md`, `alerts/contracts.md`, and `alerts/fade_forward.md` before writing.

Replay that day's armed book through the close. One pass uses the live defaults. One pass uses `entry: fade` and changes nothing else. Stock points are the exit close minus the fill for a call, and the fill minus the exit close for a put. Option dollars are one contract, the exit-bar premium minus the entry premium, times 100. A later mark is not the exit. A blank premium was a missed quote. `none` means the ladder was priced and no strike at or under $1 was still in front of the far target, and that entry is skipped. A lower level is skipped when the next number was tagged and closed back through. A late check still writes the paper entry and exit.

Trades whose close is before `armed_at` belong to the prior book. Say so, and do not mix their points into the day's book.

## Book

The note, the time it was armed, and the tickers. Name any round trip that belongs to the prior book.

## Watches

SMA holds and RSI crosses from the log. A watch is not an entry and not an exit. Say whether a level retest was already open.

## What worked

Closed round trips with positive stock points. Include the contract dollars when the entry premium and the exit-bar premium were both recorded.

## What did not

Each loss as its own row: time, ticker, side, level, fill, exit, stock points, contract. Say whether the next number had already been tagged, and whether a strike under $1 was still in front of the far target.

## Contracts

For each recorded role, the entry premium, the exit-bar premium, and the percent. Roles are chosen, cash, dte, first, cheap, and week. `chosen` is the $1 strike. `cash` is the strike the $50 cash can buy. Read both from the plan in `alerts/live.md` and from `alerts/contracts.md`, including the entry premium and the exit-bar premium. The plan's exit row leaves the cash cells blank. The cash role in `alerts/contracts.md` holds that strike's entry premium and exit-bar premium. A repeated contract stays on the earlier role. Compare the percents. One session does not crown a strike rule, switch the live contract, or fill the journal Trade column. No Agentic trade has been taken. The drill score stays stock points.

## Tape

Replay events that are missing from `alerts/paper.md`, and premiums on the tape that are not the exit bar. Leave the tape as the checker wrote it.

## Parameters

Score the day twice. The new pass uses the live parameters. The old pass uses those same parameters with `break_atr` at 0, the one-tick close, and changes nothing else. Stock points are each pass's net on that day. The difference is the new net minus the old net. When an entry premium and the exit-bar premium were both recorded, give the option-dollar difference the same way. The comparison is an observation. It does not change the live checker.

## Fade day

Append only the closes whose reason is fade to `alerts/fade_forward.md`. Score stock points. The live entry stays the retest. The 2026-10-21 gate is recorded in that file. A pass does not place an order.

## Lessons

The first goal in `learning/goals.yaml` is sniping the bottom on contracts. Say whether a paper entry bought that bottom. The number is stock points on the entry candle, not a priced premium. What repeated, and which earlier day it showed up on. Call it a pattern only when the same feature is in more than one confirmed taken trade, and say which of those trades worked. A paper row is not a taken trade. One review does not edit `rules/ta_rules.md`.

## Unchanged

Live entry, the rules file, and whether an order was placed.

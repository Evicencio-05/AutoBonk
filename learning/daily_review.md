# Daily review

Run this after the cash close, once the 13:00 PT bar is finished. Copy the sections into `learning/reviews/YYYY-MM-DD.md` and fill them from the files below. A review is an observation. It does not change `rules/ta_rules.md`, it does not change the retest entry, and it does not place an order. Buffer sizes change only when the forward gate in the Backtest section says applied.

Read `learning/journal.md`, `learning/training.md`, `alerts/levels.yaml`, `alerts/paper.md`, `alerts/log.md`, `alerts/contracts.md`, and `alerts/fade_forward.md` before writing.

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

For each recorded role, the entry premium, the exit-bar premium, and the percent. Roles are chosen, dte, first, cheap, and week. A repeated contract stays on the earlier role. Compare the percents. One session does not crown a strike rule.

## Tape

Replay events that are missing from `alerts/paper.md`, and premiums on the tape that are not the exit bar. Leave the tape as the checker wrote it.

## Fade day

Append only the closes whose reason is fade to `alerts/fade_forward.md`. Score stock points. The live entry stays the retest. The 2026-10-21 gate is recorded in that file. A pass does not place an order.

## Backtest

Run `python3 scripts/recap.py` and paste `learning/parameter_search.md` here.

The saved sessions in `bench/fixtures` are the sample. Every session except the last is the train. The last session is the forward day. Wick touch, the SMA band, chase, the ATR fraction, and near a level are each cut into 10 values on the same lows and highs as the desk. Each of the first four keeps up to three train values near the best net, and the live value is always one of them. Those values are crossed. The train winner is scored on the forward day against the buffers the checker is using. The paste states that day's profit with the new parameters, that day's profit with the old parameters, and the difference in stock points.

The checker takes that winner only when the train has at least 4 closes, the forward day has at least 2, the train peak has a neighbor in the same neighborhood, at most one changed buffer sits on a range edge, and the forward net beats the live buffers without buying that net with a deeper hole. Near a level is reported and not applied, because the live exit is still the target. A pass writes `alerts/parameters.yaml` and the next check uses those four buffers. A miss leaves the live buffers. One search is not a pattern.

## Lessons

The first goal in `learning/goals.yaml` is sniping the bottom on contracts. Say whether a paper entry bought that bottom. The number is stock points on the entry candle, not a priced premium. What repeated, and which earlier day it showed up on. Call it a pattern only when the same feature is in more than one confirmed taken trade, and say which of those trades worked. A paper row is not a taken trade. One review does not edit `rules/ta_rules.md`.

## Unchanged

Live entry stays the retest. Buffer sizes change only when the Backtest gate says applied. The rules file stays as written. No order was placed.

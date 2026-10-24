---
name: premortem
description: Before building or merging an AutoBonk change, list the most likely ways it fails and check each one. Use before changing the checker, the broker client, or anything that writes the book or checker state; when reviewing a Cursor PR; inside every proposal; or when the operator asks what could go wrong.
---

# Pre-mortem

Assume the change shipped and went wrong a week later. Find out how before it does. A list of worries is not the goal. Each item ends with a check you ran.

## Steps

1. **List up to five ways it fails, most likely times most costly first.** Money paths come first:
   - an order sent that should not be, or sent late;
   - an exit not sent, or a position the checker stops watching;
   - the wrong contract, strike, or size;
   - a book, tape, or state file that hides something from the checker;
   - a replayed decision that moves without a bless.

   Then the rest: a crash at the open, a silent failure with no alarm, a wrong number on the desk the operator acts on.
2. **Name the check that would show each one**: a test, a `bench.py compare` replay on every fixture day, a ledger query, a read of the exact code path, a run against a fake broker or a temp file. Run it.
3. **Record the result**: checked, with what it showed, or not checkable yet, with the data that would settle it.
4. **Fix what a check shows**, then run the checks again.
5. **Write it where the reader will see it**: a `Pre-mortem` section in the PR body, `How this could be wrong` in a proposal, or the reply to the operator.

## Format

| # | How it fails | Likelihood × cost | Check | Result |
|---|---|---|---|---|
| 1 | A same-day note arms a level price already crossed, so the checker sends a late live entry | medium × one bad live trade | replay a cross after `armed_at` against a temp book | held until `--force` (was: armed) |

That row is real. It is why `levels_ingest.py` holds crossed numbers.

## Rules

- Five items at most. A sixth is padding.
- An item without a check does not count. "There could be a bug" is not an item.
- Skip what `agent_guard.py` already blocks, unless the change touches the guard.
- If most items are "not checkable yet", put that in the first line. It means the evidence is thin, not that the change is safe.
- A pre-mortem never permits an order, a bless, or a tape edit. Those limits stand.

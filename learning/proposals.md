# Rule proposals

While `config/freeze.yaml` is active, no checker decision changes between weekly reviews. A rule idea goes here instead of into the code. The weekly review (`python3 scripts/review.py week`) lists everything under Open, and the operator decides each one.

One proposal per heading. Say what would change, which ledger rows prompted it (use their `ref`), how to test it on `bench/fixtures` and the ledger, and how many trades the test needs before it means anything.

## Open

### Same-level re-entry

- **Change:** after a reclaim stop at a level, the next entry at that level needs a fresh retest. Price has to leave the level by at least one 14-period ATR, then come back.
- **Prompted by:** `1023-1050-AVGO-put`, `1023-1100-GOOGL-put`, and `1023-1120-AVGO-call`. These were entries #2 and #3 at a level after a stop. They made −19 (plan), −12, and −3.
- **Alternatives to test against it:** a hard cap of one or two entries per level per day; doubling the ATR band once a level has flipped twice; only taking the flipped side after a stop.
- **Test:** run `bench.py compare` on each variant over every fixture day, then cut the ledger by `level_entry_number` and `prior_stop_at_level` in the weekly review.
- **Sample needed:** at least 15 re-entries in the ledger before choosing.

## Decided

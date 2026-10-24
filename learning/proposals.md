# Rule proposals

While `config/freeze.yaml` is active, no checker decision changes between weekly reviews. A rule idea goes here instead of into the code. The weekly review (`python3 scripts/review.py week`) lists everything under Open, and the operator decides each one.

One proposal per heading. Say what would change, which ledger rows prompted it (use their `ref`), how to test it on `bench/fixtures` and the ledger, and how many trades the test needs before it means anything.

## Open

None.

## Decided

### Same-level re-entry: fresh retest (accepted 2026-10-23, before the freeze started)

- **Change:** after a reclaim stop at a level, the next entry at that level needs a fresh retest. Price has to leave the level by at least one 14-period ATR, then come back. This is the `fresh_atr` setting (1.0; 0 turns it off). A skip is logged with reason `fresh`.
- **Prompted by:** `1023-1050-AVGO-put`, `1023-1100-GOOGL-put`, and `1023-1120-AVGO-call`. These were entries #2 and #3 at a level after a stop. They made −19 (plan), −12, and −3.
- **On the fixtures:** only 2026-10-23 changes. The rule skips the AVGO 10:50 put and the 11:20 call. It keeps the GOOGL 11:00 put, because price fell more than an ATR under 322.75 before retesting it. Stock points went from −12.64 to −11.11 that day, and nothing else moved.
- **Evidence:** one day. The operator accepted it as a rule of the frozen sample, not as a proven edge.
- **Re-check at the weekly review:** read the `fresh` skips with their plan dollars (what the skipped entry would have made) against the entries that came after a real leave. The alternatives below stay on file if the rule skips winners.
- **Alternatives kept on file:** a hard cap of one or two entries per level per day; doubling the ATR band once a level has flipped twice; only taking the flipped side after a stop.

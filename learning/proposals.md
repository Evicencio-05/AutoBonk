# Rule proposals

While `config/freeze.yaml` is active, no checker decision changes between weekly reviews. A rule idea goes here instead of into the code. The weekly review (`python3 scripts/review.py week`) lists everything under Open, and the operator decides each one.

One proposal per heading. Say what would change, which ledger rows prompted it (use their `ref`), how to test it on `bench/fixtures` and the ledger, and how many trades the test needs before it means anything.

## Open

### Entry timing: keep confirming, but send faster

- **Tested 2026-10-23** with `python3 scripts/entry_timing.py --options`. It compares three processes:
  - **confirm (live today):** wait for the fill bar, then buy near its close.
  - **asap:** buy at the fill-bar open. A fill bar that reclaims becomes an immediate exit.
  - **model:** what the bench scores. It fills at the open but drops entries the fill bar reclaimed, which is not achievable.
- **Stock points over 4 fixture days:** model −0.72, confirm −3.21, asap −2.91. Asap was 0.13 points per trade better over 19 trades, but it also ate 2 reclaimed fill bars (−2.18 points).
- **Option dollars on 2026-10-23 (8 trades):** asap −$178, confirm −$197, confirm plus the 5-minute pricing pass −$206. Asap won 4, lost 3, and tied 1, and most of its edge was one TSLA trade.
- **Read:** no reliable difference. The clear findings are that the bench is about 0.13 points per trade too optimistic against either real process, and that on checks with an entry the order waits about 5 minutes for the contract ladder to be priced (one Yahoo 1-minute request per strike).
- **Proposed, no decision change:**
  1. Send the order before the full comparison ladder is priced.
  2. Make the bench score entries at the fill-bar close, so it matches the live process. This one changes golden fills and needs a bless.
- **Sample needed:** re-run at each weekly review. Revisit asap only if the gap holds over 30+ live trades.

## Decided

### Same-level re-entry: fresh retest (accepted 2026-10-23, before the freeze started)

- **Change:** after a reclaim stop at a level, the next entry at that level needs a fresh retest. Price has to leave the level by at least one 14-period ATR, then come back. This is the `fresh_atr` setting (1.0; 0 turns it off). A skip is logged with reason `fresh`.
- **Prompted by:** `1023-1050-AVGO-put`, `1023-1100-GOOGL-put`, and `1023-1120-AVGO-call`. These were entries #2 and #3 at a level after a stop. They made −19 (plan), −12, and −3.
- **On the fixtures:** only 2026-10-23 changes. The rule skips the AVGO 10:50 put and the 11:20 call. It keeps the GOOGL 11:00 put, because price fell more than an ATR under 322.75 before retesting it. Stock points went from −12.64 to −11.11 that day, and nothing else moved.
- **Evidence:** one day. The operator accepted it as a rule of the frozen sample, not as a proven edge.
- **Re-check at the weekly review:** read the `fresh` skips with their plan dollars (what the skipped entry would have made) against the entries that came after a real leave. The alternatives below stay on file if the rule skips winners.
- **Alternatives kept on file:** a hard cap of one or two entries per level per day; doubling the ATR band once a level has flipped twice; only taking the flipped side after a stop.

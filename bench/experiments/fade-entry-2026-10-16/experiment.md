# With invalidation at the level, a wick stop, and the far note level as the target, how do failed claims and failed breaks do on 2026-10-16?

- variable: entry
- default: retest
- variant: fade
- day: discovery

## Default

- AAPL put skip 346.0 chase at 2026-10-16 09:10 PT
- AAPL put entry 346.0 sma at 2026-10-16 09:30 PT
- AAPL put exit 346.0 target at 2026-10-16 09:40 PT
- AAPL put entry 344.0 sma at 2026-10-16 10:30 PT
- AAPL put exit 344.0 clock at 2026-10-16 12:50 PT
- SPCX put skip 146.5 reclaim at 2026-10-16 08:50 PT
- SPCX put entry 146.5 sma at 2026-10-16 09:20 PT
- SPCX put exit 146.5 clock at 2026-10-16 12:50 PT
- GOOGL put entry 346.75 sma at 2026-10-16 08:50 PT
- GOOGL put exit 346.75 target at 2026-10-16 11:20 PT

## Variant

- AAPL put skip 346.0 chase at 2026-10-16 09:10 PT
- AAPL put entry 346.0 sma at 2026-10-16 09:30 PT
- AAPL put exit 346.0 target at 2026-10-16 09:40 PT
- AAPL put entry 344.0 sma at 2026-10-16 10:30 PT
- AAPL put exit 344.0 clock at 2026-10-16 12:50 PT
- SPCX put skip 146.5 reclaim at 2026-10-16 08:50 PT
- SPCX put entry 146.5 sma at 2026-10-16 09:20 PT
- SPCX put exit 146.5 clock at 2026-10-16 12:50 PT
- GOOGL put entry 346.75 sma at 2026-10-16 08:50 PT
- GOOGL put exit 346.75 target at 2026-10-16 11:20 PT

## Difference

No difference.

# With invalidation at the level, a wick stop, and the far note level as the target, how do failed claims and failed breaks do on 2026-10-15?

- variable: entry
- default: retest
- variant: fade
- day: discovery

## Default

- AAPL call skip 345.35 chase at 2026-10-15 06:50 PT
- AAPL put entry 345.35 retest at 2026-10-15 07:30 PT
- AAPL put exit 345.35 clock at 2026-10-15 12:50 PT
- AMZN call entry 255.0 retest at 2026-10-15 12:40 PT
- AMZN call exit 255.0 clock at 2026-10-15 12:50 PT
- GOOGL call entry 346.75 sma at 2026-10-15 07:30 PT
- GOOGL call exit 346.75 clock at 2026-10-15 12:50 PT
- MSFT call skip 533.0 chase at 2026-10-15 07:10 PT
- MSFT call skip 533.0 chase at 2026-10-15 07:30 PT
- MSFT call entry 537.25 sma at 2026-10-15 10:10 PT
- MSFT call exit 537.25 clock at 2026-10-15 12:50 PT
- SPCX put skip 146.0 reclaim at 2026-10-15 09:50 PT

## Variant

- AAPL call skip 345.35 chase at 2026-10-15 06:50 PT
- AAPL put entry 345.35 fade at 2026-10-15 07:30 PT
- AAPL put exit 345.35 target at 2026-10-15 11:20 PT
- AAPL put entry 342.85 sma at 2026-10-15 11:50 PT
- AAPL put exit 342.85 reclaim at 2026-10-15 12:20 PT
- AAPL call skip 342.85 reclaim at 2026-10-15 12:40 PT
- AMZN call entry 249.5 fade at 2026-10-15 06:50 PT
- AMZN call exit 249.5 target at 2026-10-15 12:20 PT
- AMZN call entry 255.0 sma at 2026-10-15 12:50 PT
- AMZN call exit 255.0 clock at 2026-10-15 12:50 PT
- GOOGL call entry 346.75 sma at 2026-10-15 07:30 PT
- GOOGL call exit 346.75 clock at 2026-10-15 12:50 PT
- MSFT put entry 537.25 fade at 2026-10-15 06:50 PT
- MSFT put exit 537.25 reclaim at 2026-10-15 08:10 PT
- MSFT call entry 537.25 sma at 2026-10-15 10:10 PT
- MSFT call exit 537.25 clock at 2026-10-15 12:50 PT
- NVDA call skip 213.5 chase at 2026-10-15 07:10 PT
- SPCX call skip 146.0 reclaim at 2026-10-15 09:30 PT
- SPCX put skip 146.0 reclaim at 2026-10-15 09:50 PT
- SPCX call entry 146.0 fade at 2026-10-15 10:50 PT
- SPCX call exit 146.0 clock at 2026-10-15 12:50 PT
- TSLA call skip 358.0 chase at 2026-10-15 06:50 PT

## Difference

- entries added: 5
- entries removed: 1
- exits moved: 1
- skips appeared: 4

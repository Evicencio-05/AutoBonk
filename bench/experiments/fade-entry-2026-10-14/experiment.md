# With invalidation at the level, a wick stop, and the far note level as the target, how do failed claims and failed breaks do on 2026-10-14?

- variable: entry
- default: retest
- variant: fade
- day: discovery

## Default

- AAPL call skip 345.0 chase at 2026-10-14 07:00 PT
- AAPL call entry 345.0 sma at 2026-10-14 07:50 PT
- AAPL call exit 345.0 reclaim at 2026-10-14 09:00 PT
- SPCX put entry 152.0 sma at 2026-10-14 12:00 PT
- SPCX put exit 152.0 reclaim at 2026-10-14 12:20 PT
- AMZN call skip 257.0 reclaim at 2026-10-14 07:20 PT
- AMZN put skip 257.0 chase at 2026-10-14 07:50 PT
- AMZN put entry 257.0 sma at 2026-10-14 08:30 PT
- AMZN put exit 257.0 target at 2026-10-14 09:40 PT
- GOOGL call skip 353.7 chase at 2026-10-14 07:20 PT
- GOOGL call skip 353.7 reclaim at 2026-10-14 08:10 PT
- GOOGL put entry 351.5 retest at 2026-10-14 10:00 PT
- GOOGL put exit 351.5 clock at 2026-10-14 12:50 PT
- MSFT put skip 540.15 chase at 2026-10-14 07:40 PT
- MSFT put entry 540.15 sma at 2026-10-14 09:40 PT
- MSFT put exit 540.15 clock at 2026-10-14 12:50 PT
- NVDA put entry 225.5 sma at 2026-10-14 08:00 PT
- NVDA put exit 225.5 target at 2026-10-14 12:10 PT
- TSLA put entry 370.5 sma at 2026-10-14 08:00 PT
- TSLA put exit 370.5 clock at 2026-10-14 12:50 PT
- META call skip 742.0 chase at 2026-10-14 08:30 PT
- META put entry 742.0 sma at 2026-10-14 10:00 PT
- META put exit 742.0 clock at 2026-10-14 12:50 PT

## Variant

- AAPL put skip 345.0 reclaim at 2026-10-14 07:30 PT
- AAPL call entry 345.0 sma at 2026-10-14 07:50 PT
- AAPL call exit 345.0 reclaim at 2026-10-14 09:00 PT
- SPCX call skip 152.0 chase at 2026-10-14 06:50 PT
- SPCX call skip 152.0 reclaim at 2026-10-14 11:00 PT
- SPCX put entry 152.0 sma at 2026-10-14 12:00 PT
- SPCX put exit 152.0 reclaim at 2026-10-14 12:20 PT
- AMZN put entry 259.5 fade at 2026-10-14 07:00 PT
- AMZN put exit 259.5 target at 2026-10-14 09:40 PT
- GOOGL put entry 353.7 fade at 2026-10-14 09:10 PT
- GOOGL put exit 353.7 target at 2026-10-14 09:30 PT
- GOOGL put entry 351.5 fade at 2026-10-14 10:00 PT
- GOOGL put exit 351.5 clock at 2026-10-14 12:50 PT
- MSFT put entry 540.15 sma at 2026-10-14 09:40 PT
- MSFT put exit 540.15 clock at 2026-10-14 12:50 PT
- NVDA call skip 225.5 reclaim at 2026-10-14 06:40 PT
- NVDA put entry 225.5 sma at 2026-10-14 08:00 PT
- NVDA put exit 225.5 target at 2026-10-14 12:10 PT
- TSLA put entry 370.5 sma at 2026-10-14 08:00 PT
- TSLA put exit 370.5 clock at 2026-10-14 12:50 PT
- META call skip 742.0 chase at 2026-10-14 08:30 PT
- META put entry 742.0 sma at 2026-10-14 10:00 PT
- META put exit 742.0 clock at 2026-10-14 12:50 PT

## Difference

- entries added: 2
- entries removed: 1
- exits moved: 0
- skips appeared: 4

# Proposals

Claude researches and writes proposals. You decide them. Each one is a file in `learning/proposals/`, written to the `proposal` skill's template (`.claude/skills/proposal/SKILL.md`), and shown in the Proposals tab on the desk.

- **Decision proposals** change what the checker decides: entries, exits, skips, sizing, or contract choice. Claude drafts up to two each Friday after the close (`autobonk-proposal.timer`). You decide them at the weekly review. An accepted one ships behind a setting, with tests and your `freeze.py bless`.
- **Safety proposals** fix something that broke without changing a decision. The after-close run drafts one only on a day an alarm fired. You can accept them any day.

To decide, write `Decision: accept`, `reject`, or `wait` and your notes under "Operator decision" in the file, or tell Claude. Claude then updates the status, and implements it if you accepted.

Ask for one any time: "write a proposal about ...". Every proposal starts from `python3 scripts/proposal_data.py`.

## Open

None.

## Waiting for more data

Re-tested at every weekly run, with the new numbers written into the proposal.

- [decision] Keep confirming each entry on the fill bar; do not switch to sending on the signal. Re-test with `scripts/entry_timing.py --options`; decide at 30+ live trades. `learning/proposals/2026-10-23-keep-confirming-entries.md`

## Decided

- 2026-10-23, accepted: Do not buy a live contract under $0.20. `learning/proposals/2026-10-24-contract-floor.md`
- 2026-10-23, accepted: Score replayed entries where the checker can actually buy. `learning/proposals/2026-10-24-honest-bench.md`
- 2026-10-23, accepted and shipped: Time every step of the 10-minute check. `learning/proposals/2026-10-23-time-the-check.md`. After 5 sessions, a follow-up proposal names the slowest step.
- 2026-10-23, accepted: Wait for a fresh retest after a stop at the same level. `learning/proposals/2026-10-23-fresh-retest.md`

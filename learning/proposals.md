# Proposals

Claude researches and writes proposals. You decide them. Each one is a file in `learning/proposals/`, written to the `proposal` skill's template (`.claude/skills/proposal/SKILL.md`), and shown in the Proposals tab on the desk.

- **Decision proposals** change what the checker decides: entries, exits, skips, sizing, or contract choice. Claude drafts up to two each Friday after the close (`autobonk-proposal.timer`). You decide them at the weekly review. An accepted one ships behind a setting, with tests and your `freeze.py bless`.
- **Safety proposals** fix something that broke without changing a decision. The after-close run drafts one only on a day an alarm fired. You can accept them any day.

To decide, write `Decision: accept`, `reject`, or `wait` and your notes under "Operator decision" in the file, or tell Claude. Claude then updates the status, and implements it if you accepted.

Ask for one any time: "write a proposal about ...". Every proposal starts from `python3 scripts/proposal_data.py`.

## Open

- [safety] Time every step of the 10-minute check, so we can find what delays entry orders. `learning/proposals/2026-10-23-time-the-check.md`
- [decision] Keep confirming each entry on the fill bar; do not switch to sending on the signal. `learning/proposals/2026-10-23-keep-confirming-entries.md`

## Decided

- 2026-10-23, accepted: Wait for a fresh retest after a stop at the same level. `learning/proposals/2026-10-23-fresh-retest.md`

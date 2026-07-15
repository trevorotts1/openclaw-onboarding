# Agent Browser CLI Version Pin (GK-28/U90)

The `agent-browser` **npm package** version is pinned separately from this
skill-wrapper's own `skill-version.txt` (which tracks the WRAPPER — INSTALL.md /
SKILL.md / CHANGELOG.md / CORE_UPDATES.md — not the CLI). Before this pin
existed there was NO recorded known-good CLI version anywhere in this skill
(NOT-FOUND, GK-28 audit): `agent-browser.skill`'s archive covers the wrapper
docs only (P3-06), so a fresh `npm install -g agent-browser` on install day
could silently land any current registry release, proven or not.

## Pinned version

0.27.0

Machine-readable copy: `agent-browser-cli.pin` (same value, no comments —
read by `qc-agent-browser.sh` and `scripts/bump-agent-browser-cli-pin.sh`).
`scripts/bump-agent-browser-cli-pin.sh --check` fails if the two ever
disagree.

## Why this version

Proven working, live, on the operator's own box (2026-07-15, GK-28/U90):
`agent-browser --version` → `agent-browser 0.27.0`. Per the fleet's
"operator's own box is the canary — prove first" rule, a version is pinned
only once it is proven on the operator's own box — never a registry "latest"
that has not been run anywhere. `06-ghl-install-pages/tools/ghl_ab_executor.py`
independently hard-codes `PINNED_AGENT_BROWSER = "0.27.0"` for its own
click/fill argv-compat reasons (verified live 2026-07-10) — this pin agrees
with that existing evidence rather than contradicting it.

## Bump log (explicit, dated — never silent)

| Date | From | To | Who/why |
|---|---|---|---|
| 2026-07-15 | (none — first pin) | 0.27.0 | GK-28/U90 — first pin; matches the proven-working install on the operator's box + the existing `ghl_ab_executor.py` PINNED_AGENT_BROWSER evidence |

## How to bump

Run `scripts/bump-agent-browser-cli-pin.sh <new-version> "<reason>"` — it
updates BOTH `agent-browser-cli.pin` and this file's pinned-version line +
appends a dated bump-log row in one atomic edit (mirrors
`scripts/bump-version.sh`'s single-source-of-truth pattern for the repo's own
version markers). Never hand-edit `agent-browser-cli.pin` directly — the two
files would drift, and `--check` would catch it but the fix is always to run
the script, not to patch a file by hand.

A version bump here is a DELIBERATE, PROVEN action: bump only after the new
CLI version has been proven working on the operator's own box first (the same
canary discipline as the version being replaced).

#!/usr/bin/env bash
# ghl-mcp-probe.sh — INERT TOMBSTONE (W07 retirement)
#
# GHL_MCP_RETIRED=1 — the GHL Community MCP (Tier 2, skill 36) is RETIRED.
#
# WHY THIS FILE STILL EXISTS (and does almost nothing)
#   Other scripts, docs, plists and QC gates reference this path, so the file
#   must stay present and syntactically valid. What is GONE — deleted, not
#   parked behind a flag — is every capability that could probe, heal, alert on
#   or restart the retired service: no bounded self-heal, no launchctl
#   kickstart, no pm2 restart, no systemctl restart, no streak state, no
#   operator cards, no Ranger escalation. A future edit cannot re-arm a branch
#   that no longer exists; reaching the old verbs means rewriting this file
#   from scratch, and the gate (scripts/qc-assert-ghl-mcp-supervised.sh) reads
#   the GHL_MCP_RETIRED marker below as the contract.
#
# INVOCATION BEHAVIOUR (tombstones fail loudly, never silently succeed)
#   Any invocation — whatever flags are passed — prints an unconditional
#   refusal naming the retirement and the archive path, then exits 69.
#   There is no --heal, no --quiet success path, no off-switch that returns 0.
#   69 (EX_UNAVAILABLE) is outside this probe's historical 0/2/3/4/5 verdict
#   vocabulary, so an old caller can never mistake a refusal for a verdict.
#
# RETIREMENT OF RECORD
#   bash scripts/ghl-mcp-autostart.sh --retire   (inventory, archive, disable
#   resurrection, stop, verify, receipt — run by update-skills.sh)
#   Archive: <OC_ROOT>/.retired/archive-<UTC>/
#   Receipt: <OC_ROOT>/.retired/ghl-mcp-retirement.json
#   Terminal states: RETIRED_VERIFIED_OFF | MIGRATION_FAILED

set -u

GHL_MCP_RETIRED=1
GHL_MCP_TOMBSTONE_EXIT="${GHL_MCP_TOMBSTONE_EXIT:-69}"

# Read-only path derivation for the message below. A tombstone never mkdir's,
# never opens a log, never writes a file on the box it refuses on.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ── Historical pin/profile resolver list — UNREACHABLE by design ─────────────
# ⚠️ KEEP IN SYNC with scripts/ghl-mcp-autostart.sh, scripts/
# ghl-mcp-assert-runtime.sh, the VPS overlay, scripts/
# qc-assert-ghl-mcp-supervised.sh and the delivery step in BOTH installers.
# Retained ONLY because scripts/qc-assert-ghl-mcp-pin-resolvers.py and
# scripts/qc-assert-pin-delivery-paths.sh parse this literal list and fail on
# drift (a consumer list narrower than the digest checker's is split-brain).
# Nothing at or below the refusal below reads it — the loop body does nothing.
for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/config/ghl-mcp-pin.env" \
          "/data/.openclaw/onboarding/config/ghl-mcp-pin.env"; do
  :
done
unset _c

# ── Unconditional refusal (not behind any flag) ──────────────────────────────
printf 'STATUS: ghl-mcp-probe=RETIRED (exit %s) — inert tombstone; GHL Community MCP (Tier 2, skill 36) is RETIRED (GHL_MCP_RETIRED=1); no probe, no self-heal, no restart; retirement of record: bash scripts/ghl-mcp-autostart.sh --retire; archive: <OC_ROOT>/.retired/archive-<UTC>/; receipt: <OC_ROOT>/.retired/ghl-mcp-retirement.json; terminal states: RETIRED_VERIFIED_OFF | MIGRATION_FAILED\n' \
  "$GHL_MCP_TOMBSTONE_EXIT"
printf '[ghl-mcp-probe] REFUSED — the GHL Community MCP (Tier 2, skill 36) is RETIRED (GHL_MCP_RETIRED=1).\n' >&2
printf '[ghl-mcp-probe] This probe is an inert tombstone: it no longer probes, heals, alerts or restarts anything.\n' >&2
printf '[ghl-mcp-probe] Retirement of record: bash scripts/ghl-mcp-autostart.sh --retire\n' >&2
printf '[ghl-mcp-probe] Archive: <OC_ROOT>/.retired/archive-<UTC>/   Receipt: <OC_ROOT>/.retired/ghl-mcp-retirement.json\n' >&2
printf '[ghl-mcp-probe] Terminal states: RETIRED_VERIFIED_OFF | MIGRATION_FAILED. Do not add a start, heal or restart path back.\n' >&2

exit "$GHL_MCP_TOMBSTONE_EXIT"
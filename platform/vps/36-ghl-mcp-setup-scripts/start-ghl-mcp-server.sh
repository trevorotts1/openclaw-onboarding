#!/usr/bin/env bash
# start-ghl-mcp-server.sh — INERT TOMBSTONE (W07 retirement)
#
# GHL_MCP_RETIRED=1 — the GHL Community MCP (Tier 2, skill 36) is RETIRED.
#
# WHY THIS FILE STILL EXISTS (and does almost nothing)
#   INSTALL.md, platform/README.md, the pin-gate consumer lists and the QC
#   gates reference this path, so the file must stay present and syntactically
#   valid. What is GONE — deleted, not parked behind a flag — is the entire
#   start surface: no clone, no pin checkout, no build, no pm2
#   start/startOrReload/restart, no pm2 save, no pm2 resurrect, no @reboot cron
#   write, no systemd unit install, no setsid relaunch loop, no PID-file kill,
#   no log-rotation install (it existed only to serve that supervisor). A future
#   edit cannot re-arm a branch that no longer exists; reaching the old verbs
#   means rewriting this file, and the gate
#   (scripts/qc-assert-ghl-mcp-supervised.sh) reads the GHL_MCP_RETIRED marker
#   below as the contract.
#
# INVOCATION BEHAVIOUR (tombstones fail loudly, never silently succeed)
#   Any invocation — no arguments, --restart, --health, anything — prints an
#   unconditional refusal naming the retirement and the archive path, then
#   exits 69. The historical exit contract (0 = healthy/running,
#   1 = not healthy) is deliberately retired with the service: 69
#   (EX_UNAVAILABLE) is outside it, so no old caller can read this refusal as
#   "ran the start path" or as a health verdict. There is no success path.
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

# ── Historical pin resolver list — UNREACHABLE by design ─────────────────────
# ⚠️ KEEP IN SYNC with scripts/ghl-mcp-autostart.sh, scripts/ghl-mcp-probe.sh,
# scripts/ghl-mcp-assert-runtime.sh, scripts/qc-assert-ghl-mcp-supervised.sh
# and the delivery step in BOTH installers.
# Retained ONLY because scripts/qc-assert-ghl-mcp-pin-resolvers.py and
# scripts/qc-assert-pin-delivery-paths.sh parse this literal list and fail on
# drift (a consumer list narrower than the digest checker's is split-brain).
# Nothing at or below the refusal below reads it — the loop body does nothing.
# The 40-char commit fallback is intentionally ABSENT (fail-closed, W07): a
# tombstone carries no pin to fall back to.
for _c in "$SELF_DIR/../../../config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/config/ghl-mcp-pin.env" \
          "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
          "/data/.openclaw/config/ghl-mcp-pin.env" \
          "/data/.openclaw/onboarding/config/ghl-mcp-pin.env"; do
  :
done
unset _c

# ── Unconditional refusal (not behind any flag) ──────────────────────────────
printf 'STATUS: start-ghl-mcp=RETIRED (exit %s) — inert tombstone; GHL Community MCP (Tier 2, skill 36) is RETIRED (GHL_MCP_RETIRED=1); no start, no restart, no supervision of any kind; retirement of record: bash scripts/ghl-mcp-autostart.sh --retire; archive: <OC_ROOT>/.retired/archive-<UTC>/; receipt: <OC_ROOT>/.retired/ghl-mcp-retirement.json; terminal states: RETIRED_VERIFIED_OFF | MIGRATION_FAILED\n' \
  "$GHL_MCP_TOMBSTONE_EXIT"
printf '[start-ghl-mcp] REFUSED — the GHL Community MCP (Tier 2, skill 36) is RETIRED (GHL_MCP_RETIRED=1).\n' >&2
printf '[start-ghl-mcp] This start script is an inert tombstone: it no longer clones, builds, starts, restarts or supervises anything.\n' >&2
printf '[start-ghl-mcp] Retirement of record: bash scripts/ghl-mcp-autostart.sh --retire\n' >&2
printf '[start-ghl-mcp] Archive: <OC_ROOT>/.retired/archive-<UTC>/   Receipt: <OC_ROOT>/.retired/ghl-mcp-retirement.json\n' >&2
printf '[start-ghl-mcp] Terminal states: RETIRED_VERIFIED_OFF | MIGRATION_FAILED. Do not add a start or restart path back.\n' >&2

exit "$GHL_MCP_TOMBSTONE_EXIT"
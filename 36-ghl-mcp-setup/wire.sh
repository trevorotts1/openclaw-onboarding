#!/usr/bin/env bash
# wire.sh — skill 36 live-client migration runner
# Runs as part of the WIRING PHASE (update-skills.sh wire_core_updates call).
# Idempotent. Prints STATUS: lines matching the ghl-mcp-autostart convention.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ---- live skill version: read from the canonical source, never a literal ----
# (FIX-XC-13a — kills the wire.sh-vs-skill-version.txt drift.) Used only for the
# human-readable STATUS reporting below.
SKILL_VERSION="unknown"
if [ -f "$SCRIPT_DIR/skill-version.txt" ]; then
  SKILL_VERSION="$(tr -d '[:space:]' < "$SCRIPT_DIR/skill-version.txt" 2>/dev/null || echo unknown)"
  [ -z "$SKILL_VERSION" ] && SKILL_VERSION="unknown"
fi

# ---- migration-marker schema tag — FROZEN, do NOT track the live version -----
# The M1/M2 markers below are one-time idempotency keys already written into
# AGENTS.md on migrated boxes. They must stay byte-stable across skill-version
# bumps: retagging them to the live version would make every completed migration
# look un-applied and re-run on the next wire pass. These migrations shipped in
# v1.1.0; that tag is intentionally permanent.
MIGRATION_TAG="v1.1.0"

WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
ISO=$(date -u +%Y%m%dT%H%M%SZ)

SOUL_MD="$WORKSPACE/SOUL.md"
AGENTS_MD="$WORKSPACE/AGENTS.md"

# ── Migration M1: SOUL.md relocation ──────────────────────────────────────────

M1_MARKER="convertandflow-migration:soul-relocation:$MIGRATION_TAG"

if grep -qF "$M1_MARKER" "$AGENTS_MD" 2>/dev/null; then
  echo "STATUS: M1 soul-relocation already applied — skipping"
else
  # PRECONDITION: AGENTS.md must already have the relocated protocol
  if ! grep -q 'GHL Tier Escalation Protocol' "$AGENTS_MD" 2>/dev/null; then
    echo "STATUS: M1 soul-relocation PENDING — AGENTS.md does not yet have the protocol; WIRING PHASE must run CORE_UPDATES merge first"
    # Non-fatal; the WIRING PHASE merges CORE_UPDATES before running wire.sh in most installs.
    # If this races, the next Sunday cron will retry.
  else
    if [ -f "$SOUL_MD" ] && grep -q '🔴 GHL Tier Escalation Protocol' "$SOUL_MD" 2>/dev/null; then
      cp "$SOUL_MD" "${SOUL_MD}.bak-convertandflow-${ISO}"
      # SK1-75: robust span-delete. The old regex hardcoded a `## ` heading level and a
      # `Full reference:` terminator, so any variant (# / ### header, or a block without
      # that trailing line) matched NOTHING — yet the success marker was written anyway,
      # falsely recording the migration as done. Now: match the header at any heading
      # level (optional 🔴, flexible suffix), delete through the `Full reference:` line
      # OR the next heading OR EOF, and print REMOVED / NOCHANGE so the marker is only
      # written when a removal ACTUALLY happened.
      REMOVAL=$(python3 - "$SOUL_MD" <<'PYEOF' || echo PYERR
import sys, re, pathlib
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding='utf-8')
header = r'#{1,6}[ \t]*(?:🔴[ \t]*)?GHL Tier Escalation Protocol[^\n]*\n'
patterns = [
    header + r'.*?Full reference:[^\n]*\n?',   # canonical block (ends at Full reference:)
    header + r'.*?(?=\n#{1,6}[ \t])',          # else: up to the next heading
    header + r'.*\Z',                          # else: to end of file
]
new_text = text
for pat in patterns:
    candidate = re.sub(pat, '', text, count=1, flags=re.DOTALL)
    if candidate != text:
        new_text = candidate
        break
if new_text != text:
    path.write_text(new_text, encoding='utf-8')
    print("REMOVED")
else:
    print("NOCHANGE")
PYEOF
)
      if [ "$REMOVAL" = "REMOVED" ]; then
        echo "STATUS: M1 soul-relocation applied — legacy SOUL.md block removed"
        echo "" >> "$AGENTS_MD"
        echo "<!-- $M1_MARKER -->" >> "$AGENTS_MD"
      else
        echo "STATUS: M1 soul-relocation WARNING — a legacy SOUL.md block was detected but the removal did not match its shape ($REMOVAL); SOUL.md left untouched and NOT marked done (will retry next pass). Inspect $SOUL_MD."
      fi
    else
      echo "STATUS: M1 soul-relocation — SOUL.md has no legacy block; no-op"
      # No block to remove — the migration is satisfied; write the marker.
      echo "" >> "$AGENTS_MD"
      echo "<!-- $M1_MARKER -->" >> "$AGENTS_MD"
    fi
  fi
fi

# ── Migration M2: Tier 2 de-register ──────────────────────────────────────────

M2_MARKER="convertandflow-migration:tier2-deregister:$MIGRATION_TAG"

# The M2 marker is a PERMANENT, byte-stable idempotency key: once written, this
# migration never runs again on this box. So it must only ever be written when
# the end state has been OBSERVED, not merely attempted.
#
# Two ways the old code wrote it on an unverified assumption:
#   1. After a de-registration call it wrote the marker unconditionally.
#      The gateway rewrites openclaw.json from memory and can clobber a config
#      write, so the removal genuinely may not stick — and the operator box was found
#      with ghl-community-mcp STILL registered, exactly consistent with a removal
#      that was undone. The marker then guaranteed no later pass would retry.
#   2. The else-branch fired both when the server was confirmed unregistered AND
#      when the openclaw CLI was simply absent. In the second case nothing was
#      ever checked, yet the migration was recorded as permanently done.
# Both now re-read `openclaw mcp list` and skip the marker on any doubt, so the
# next wiring pass retries instead of the box being silently stuck forever.
_m2_still_registered() {
  openclaw mcp list 2>/dev/null | grep -q 'ghl-community-mcp'
}

if grep -qF "$M2_MARKER" "$AGENTS_MD" 2>/dev/null; then
  echo "STATUS: M2 tier2-deregister already applied — skipping"
elif ! command -v openclaw >/dev/null 2>&1; then
  # Cannot observe the state -> do NOT record the migration as done.
  echo "STATUS: M2 tier2-deregister PENDING — openclaw CLI not on PATH, so registration state could not be verified; marker NOT written (will retry next pass)"
elif _m2_still_registered; then
  # Back up config via BYUP pattern before removal
  BYUP_BACKUP="${HOME}/.openclaw/backups/openclaw-config-before-tier2-deregister-${ISO}.json"
  mkdir -p "$(dirname "$BYUP_BACKUP")"
  openclaw config export > "$BYUP_BACKUP" 2>/dev/null || true
  # B2: `openclaw mcp remove` IS NOT A COMMAND on OpenClaw 2026.7.1-2 — it exits
  # 1 with "Too many arguments for this command." The verb is `unset`. This call
  # site used `remove`, swallowed by `|| true`, so M2 never de-registered
  # anything on any box; the "did not stick" message below then MISDIAGNOSED it
  # as a gateway rewrite, which sent every investigation down the wrong path.
  # Try the real verb first, keep `remove` as the fallback for an older CLI, and
  # report which verb the installed CLI actually documents.
  _m2_unset() {
    openclaw mcp unset ghl-community-mcp >/dev/null 2>&1 && return 0
    openclaw mcp remove ghl-community-mcp >/dev/null 2>&1 && return 0
    return 1
  }
  if ! _m2_unset; then
    echo "STATUS: M2 WARNING — neither 'openclaw mcp unset' nor 'openclaw mcp remove' was accepted by this CLI, so ghl-community-mcp is still registered. Run 'openclaw mcp --help' to see the supported verb. Marker NOT written; the next wiring pass will retry."
  fi
  # RE-READ: the removal is only real if it is still gone when we look again.
  if _m2_still_registered; then
    echo "STATUS: M2 WARNING — ghl-community-mcp is STILL registered after the de-registration attempt. Two causes are possible and they are NOT the same: (a) the CLI rejected the verb (check 'openclaw mcp --help' — 'remove' does not exist on 2026.7.1-2, 'unset' does), or (b) the gateway rewrote openclaw.json from memory and clobbered the config write. Marker NOT written; the next wiring pass will retry."
  else
    echo "STATUS: M2 tier2-deregister applied — ghl-community-mcp removed from mcp.servers (verified by re-reading 'openclaw mcp list')"
    # Verify service still responds
    URL=$(openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null | tr -d '\n' || echo "")
    if [ -n "$URL" ] && curl -sS -m 5 "$URL/tools" >/dev/null 2>&1; then
      echo "STATUS: M2 service still responding on $URL/tools — OK"
    else
      echo "STATUS: M2 WARNING — service /tools not responding; check launchd/systemd"
    fi
    echo "" >> "$AGENTS_MD"
    echo "<!-- $M2_MARKER -->" >> "$AGENTS_MD"
  fi
else
  echo "STATUS: M2 tier2-deregister — ghl-community-mcp not registered (verified); no-op"
  echo "" >> "$AGENTS_MD"
  echo "<!-- $M2_MARKER -->" >> "$AGENTS_MD"
fi

echo "STATUS: skill-36 wire.sh complete ($SKILL_VERSION)"

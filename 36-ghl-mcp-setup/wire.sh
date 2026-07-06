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
      # Python span-delete: remove from the protocol header through the "Full reference:" line
      python3 - "$SOUL_MD" <<'PYEOF'
import sys, re, pathlib
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding='utf-8')
# Remove the block from the header line through the trailing "Full reference:" line
pattern = r'## 🔴 GHL Tier Escalation Protocol[^\n]*\n.*?Full reference:.*?\n'
new_text = re.sub(pattern, '', text, flags=re.DOTALL)
path.write_text(new_text, encoding='utf-8')
PYEOF
      echo "STATUS: M1 soul-relocation applied — legacy SOUL.md block removed"
    else
      echo "STATUS: M1 soul-relocation — SOUL.md has no legacy block; no-op"
    fi
    # Write success marker to AGENTS.md
    echo "" >> "$AGENTS_MD"
    echo "<!-- $M1_MARKER -->" >> "$AGENTS_MD"
  fi
fi

# ── Migration M2: Tier 2 de-register ──────────────────────────────────────────

M2_MARKER="convertandflow-migration:tier2-deregister:$MIGRATION_TAG"

if grep -qF "$M2_MARKER" "$AGENTS_MD" 2>/dev/null; then
  echo "STATUS: M2 tier2-deregister already applied — skipping"
elif command -v openclaw >/dev/null 2>&1 && openclaw mcp list 2>/dev/null | grep -q 'ghl-community-mcp'; then
  # Back up config via BYUP pattern before removal
  BYUP_BACKUP="${HOME}/.openclaw/backups/openclaw-config-before-tier2-deregister-${ISO}.json"
  mkdir -p "$(dirname "$BYUP_BACKUP")"
  openclaw config export > "$BYUP_BACKUP" 2>/dev/null || true
  openclaw mcp remove ghl-community-mcp 2>/dev/null || true
  echo "STATUS: M2 tier2-deregister applied — ghl-community-mcp removed from mcp.servers"
  # Verify service still responds
  URL=$(openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null | tr -d '\n' || echo "")
  if [ -n "$URL" ] && curl -sS -m 5 "$URL/tools" >/dev/null 2>&1; then
    echo "STATUS: M2 service still responding on $URL/tools — OK"
  else
    echo "STATUS: M2 WARNING — service /tools not responding; check launchd/systemd"
  fi
  echo "" >> "$AGENTS_MD"
  echo "<!-- $M2_MARKER -->" >> "$AGENTS_MD"
else
  echo "STATUS: M2 tier2-deregister — ghl-community-mcp not registered; no-op"
  echo "" >> "$AGENTS_MD"
  echo "<!-- $M2_MARKER -->" >> "$AGENTS_MD"
fi

echo "STATUS: skill-36 wire.sh complete ($SKILL_VERSION)"

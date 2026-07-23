#!/usr/bin/env bash
# wire.sh — skill 35 live-client migration runner.
#
# PURPOSE (despite the generic name): this script does ONE thing — the M4
# CREDENTIAL-NAME MIGRATION. It mirrors stray legacy GHL secret names
# (GHL_PRIVATE_TOKEN, GHL_LOCATION_ID) to the canonical names
# (GOHIGHLEVEL_API_KEY, GOHIGHLEVEL_LOCATION_ID) in the box's secrets file.
# It does NOT wire up publishing, sheets, crons, or anything else. If you are
# looking for the publishing/sheet logic, that lives in
# scripts/run-publishing-cycle.sh and the social-planner-* n8n webhooks
# (config/n8n/), not here.
#
# WHY IT IS STILL NAMED wire.sh: the fleet update loop in update-skills.sh
# auto-invokes a skill's installer by filename priority
# (wire.sh > install.sh > scripts/install.sh). This file MUST stay named
# wire.sh at the skill root or the M4 credential migration would stop running
# on fleet updates. The name is a wiring-loop convention, not a description of
# scope — hence this clarifying header.
#
# Idempotent. Prints STATUS: lines. NEVER logs secret values.
set -euo pipefail

# Fail-soft: a skill-root installer must NEVER abort the fleet update run with a
# non-zero exit. Any unexpected error logs a STATUS line and we still exit 0 — the
# M4 credential-name mirror is best-effort and a hiccup must not stop other skills.
trap 'rc=$?; if [ "$rc" -ne 0 ]; then echo "STATUS: skill-35 wire.sh non-fatal error (rc=$rc) — exiting 0 (fail-soft)"; fi; exit 0' EXIT

SKILL_VERSION="v2.7.0"
ISO=$(date -u +%Y%m%dT%H%M%SZ)
SECRETS_ENV="${HOME}/.openclaw/secrets/.env"
AGENTS_MD="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}/AGENTS.md"

M4_MARKER="convertandflow-migration:skill35-credname:$SKILL_VERSION"

if grep -qF "$M4_MARKER" "$AGENTS_MD" 2>/dev/null; then
  echo "STATUS: M4 skill35-credname already applied — skipping"
  exit 0
fi

if [ ! -f "$SECRETS_ENV" ]; then
  echo "STATUS: M4 skill35-credname — secrets file not found at $SECRETS_ENV; skipping"
  # Still write marker so we don't retry endlessly
  echo "" >> "$AGENTS_MD"
  echo "<!-- $M4_MARKER -->" >> "$AGENTS_MD"
  exit 0
fi

# Back up secrets file (no value logging)
cp "$SECRETS_ENV" "${SECRETS_ENV}.bak-convertandflow-${ISO}"
chmod 600 "${SECRETS_ENV}.bak-convertandflow-${ISO}"

python3 - "$SECRETS_ENV" <<'PYEOF'
import sys, pathlib, os, stat

path = pathlib.Path(sys.argv[1])
lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
new_lines = list(lines)
has_canonical_api  = any(l.startswith('GOHIGHLEVEL_API_KEY=') for l in lines)
has_canonical_loc  = any(l.startswith('GOHIGHLEVEL_LOCATION_ID=') for l in lines)

for line in lines:
    if line.startswith('GHL_PRIVATE_TOKEN=') and not has_canonical_api:
        val = line.split('=', 1)[1].rstrip('\n')
        new_lines.append(f'GOHIGHLEVEL_API_KEY={val}\n')
        has_canonical_api = True
        # mask val in output
        sys.stdout.write('STATUS: mirrored GHL_PRIVATE_TOKEN -> GOHIGHLEVEL_API_KEY (value masked)\n')
    if line.startswith('GHL_LOCATION_ID=') and not has_canonical_loc:
        val = line.split('=', 1)[1].rstrip('\n')
        new_lines.append(f'GOHIGHLEVEL_LOCATION_ID={val}\n')
        has_canonical_loc = True
        sys.stdout.write('STATUS: mirrored GHL_LOCATION_ID -> GOHIGHLEVEL_LOCATION_ID (value masked)\n')

path.write_text(''.join(new_lines), encoding='utf-8')
# Preserve chmod 600
os.chmod(str(path), stat.S_IRUSR | stat.S_IWUSR)
PYEOF

echo "STATUS: M4 secrets migration complete (stray legacy names mirrored to canonical names; originals kept for backwards-compat)"

# Write success marker
echo "" >> "$AGENTS_MD"
echo "<!-- $M4_MARKER -->" >> "$AGENTS_MD"
echo "STATUS: skill-35 wire.sh M4 complete ($SKILL_VERSION)"

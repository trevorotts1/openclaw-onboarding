#!/usr/bin/env bash
# skill38-calendar-sync.sh — Weekly GHL calendar ID refresh for Skill 38.
# Pulls the client's current GHL calendars and rewrites the marked calendar
# table in TOOLS.md: adds new calendars, removes ones that no longer exist.
# Generic — works for ANY client. Reads creds from the client's env file.
#
# Usage: skill38-calendar-sync.sh [TOOLS_MD_PATH]
# Cron:  Sundays (e.g. "0 9 * * 0").
set -uo pipefail

# --- locate env (Mac vs VPS) ---
for ENVF in "$HOME/clawd/secrets/.env" "/data/.openclaw/.env" "$HOME/.openclaw/.env" "/data/clawd/secrets/.env"; do
  [ -f "$ENVF" ] && { set -a; . "$ENVF" 2>/dev/null; set +a; break; }
done

PIT="${GHL_PRIVATE_INTEGRATION_TOKEN:-${GHL_API_KEY:-}}"
LOC="${GHL_LOCATION_ID:-}"
TOOLS="${1:-}"

if [ -z "$TOOLS" ]; then
  for T in "/data/.openclaw/workspace/TOOLS.md" "$HOME/.openclaw/workspace/TOOLS.md"; do
    [ -f "$T" ] && TOOLS="$T" && break
  done
fi

[ -z "$PIT" ] && { echo "[calendar-sync] ERROR: no GHL token in env"; exit 2; }
[ -z "$LOC" ] && { echo "[calendar-sync] ERROR: no GHL_LOCATION_ID in env"; exit 2; }
{ [ -z "$TOOLS" ] || [ ! -f "$TOOLS" ]; } && { echo "[calendar-sync] ERROR: TOOLS.md not found ($TOOLS)"; exit 2; }

# --- pull current calendars ---
CAL_JSON=$(curl -s -X GET "https://services.leadconnectorhq.com/calendars/?locationId=${LOC}" \
  -H "Authorization: Bearer ${PIT}" -H "Version: 2021-04-15")

cp "$TOOLS" "${TOOLS}.bak-calendar-sync"

# --- rebuild the marked table + write back ---
CAL_JSON="$CAL_JSON" TOOLS="$TOOLS" python3 <<'PY'
import json, os, re, sys
tools = os.environ["TOOLS"]
raw = os.environ.get("CAL_JSON", "")
try:
    d = json.loads(raw)
except Exception:
    print("[calendar-sync] ERROR: GHL returned non-JSON; TOOLS.md untouched"); sys.exit(3)
cals = d.get("calendars", d if isinstance(d, list) else [])
if not isinstance(cals, list):
    print("[calendar-sync] ERROR: unexpected payload; TOOLS.md untouched"); sys.exit(3)

lines = ["<!-- GHL_CALENDARS_START (auto-synced weekly by skill38-calendar-sync.sh — do not hand-edit) -->",
         "| Calendar | ID | Active |", "|---|---|---|"]
for c in cals:
    lines.append(f"| {c.get('name','(unnamed)')} | `{c.get('id','')}` | {c.get('isActive')} |")
lines.append(f"<!-- GHL_CALENDARS_END | count={len(cals)} -->")
block = "\n".join(lines)

s = open(tools).read()
pat = re.compile(r"<!-- GHL_CALENDARS_START.*?GHL_CALENDARS_END[^>]*-->", re.S)
s = pat.sub(block, s) if pat.search(s) else s + "\n\n## GHL Calendars (auto-synced weekly)\n" + block + "\n"
open(tools, "w").write(s)
print(f"[calendar-sync] OK — {len(cals)} calendars written to {tools}")
PY

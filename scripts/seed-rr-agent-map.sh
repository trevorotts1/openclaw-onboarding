#!/usr/bin/env bash
# seed-rr-agent-map.sh — provision Rescue Rangers agent-id mappings fleet-wide.
#
# rr_agent_map (n8n data table EFPgipZtKatC5xPw) maps box_slug -> local_agent_id,
# the OpenClaw agent id that receives RR coaching answers on that box. RR-02-coach
# reads it before diagnosing; a receiver-covered box with no row escalates to a
# human (agent_id_unmapped). This script upserts a row per box so every enrolled
# box can be diagnosed by the agent chain instead of paging the operator.
#
#   seed-rr-agent-map.sh [--dry-run] [ROSTER_FILE]
#
#   ROSTER_FILE   one slug per line (default: derive from ~/.ssh/config rescue-*
#                 aliases + ~/clawd/fleet-prover/fleet-roster.json when present).
#   --dry-run     print what would be written, write nothing.
#
# NOTE: the n8n data-table API exposes row POST (insert) but no row DELETE
# (405) and no upsert, so this script is INSERT-ONLY — the idempotent diff
# below computes which slugs already have a row and inserts only the missing
# ones, making a rerun a true no-op. Rows inserted outside this script can
# still duplicate; de-duping a table requires the n8n UI or a workflow.
#
# Requirements: N8N_API_KEY + N8N_HOST in the environment (operator box only —
# client boxes do not carry the n8n key and must NOT run this; the script exits
# cleanly if the key is absent). Roster slugs only — no client names live here.
#
# Safety: backs up the live table to /tmp before any write, announces before
# writing, reads back and verifies afterwards.

set -euo pipefail

HOST="${N8N_HOST:-https://main.blackceoautomations.com}"
TABLE_ID="EFPgipZtKatC5xPw"   # rr_agent_map (recreated 2026-08-13 after the original table was deleted)
export RR_AGENT_MAP_TABLE_ID="$TABLE_ID"
DRY_RUN=0
ROSTER_FILE=""
while [ "${1:-}" = "--dry-run" ]; do DRY_RUN=1; shift || true; done
ROSTER_FILE="${1:-}"

if [ -z "${N8N_API_KEY:-}" ]; then
  echo "seed-rr-agent-map: N8N_API_KEY not set — operator-only script, skipping." >&2
  exit 0
fi

# --- Build the slug list ------------------------------------------------------
SLUGS_FILE="$(mktemp)"
if [ -n "$ROSTER_FILE" ]; then
  grep -v '^#' "$ROSTER_FILE" | sed '/^[[:space:]]*$/d' > "$SLUGS_FILE"
elif [ -f "$HOME/clawd/fleet-prover/fleet-roster.json" ]; then
  python3 -c 'import json,sys; print("\n".join(sorted(json.load(open(sys.argv[1]))["boxes"])))' \
    "$HOME/clawd/fleet-prover/fleet-roster.json" > "$SLUGS_FILE"
else
  grep '^Host ' "$HOME/.ssh/config" | awk '{print $2}' | grep '^rescue-' > "$SLUGS_FILE"
fi

# --- Backup -------------------------------------------------------------------
BAK="/tmp/rr_agent_map-backup-$(date +%Y%m%dT%H%M%S).json"
if [ "$DRY_RUN" -eq 0 ]; then
  curl -sS -H "X-N8N-API-KEY: ${N8N_API_KEY}" "$HOST/api/v1/data-tables/$TABLE_ID/rows" > "$BAK"
  echo "seed-rr-agent-map: backup -> $BAK ($(wc -c < "$BAK" | tr -d ' ') bytes)"
fi

# --- Idempotent diff ----------------------------------------------------------
# The API has no row-level delete/upsert, so a plain re-run would accumulate
# duplicate rows. Compute the set of slugs that ALREADY have a row and insert
# only the missing ones — a re-run is then a true no-op (0 rows).
EXISTING=$(curl -sS -H "X-N8N-API-KEY: ${N8N_API_KEY}" "$HOST/api/v1/data-tables/$TABLE_ID/rows" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); rows=d.get("data",[]); print("\n".join(sorted(set(r.get("box_slug","") for r in rows if r.get("box_slug")))))' 2>/dev/null || true)
python3 - "$SLUGS_FILE" "$EXISTING" <<'DEDUP'
import sys
want = [l.strip() for l in open(sys.argv[1]) if l.strip()]
have = set(sys.argv[2].split()) if len(sys.argv) > 2 and sys.argv[2] else set()
missing = [s for s in want if s not in have]
print("\n".join(missing))
DEDUP
python3 - "$SLUGS_FILE" "$EXISTING" > /tmp/rr-seed-missing.txt 2>/dev/null || true
mapfile -t SLUGS < /tmp/rr-seed-missing.txt
N=${#SLUGS[@]}
echo "seed-rr-agent-map: $N slugs missing (of $(echo "$EXISTING" | grep -c .) existing) — dry-run=$DRY_RUN"
if [ "$N" -eq 0 ]; then
  echo "seed-rr-agent-map: nothing to write — table already mapped (no-op)"
  rm -f "$SLUGS_FILE" /tmp/rr-seed-missing.txt
  exit 0
fi

# --- Resolve each box's REAL default agent ------------------------------------
# Several fleet boxes run department rosters with NO 'main' agent (their default
# is e.g. dept-account-management), so seeding 'main' blindly produces rows that
# die with `Error: Unknown agent id "main"` at delivery time. Ask each box over
# SSH which agent is its default; never write a guess.
resolve_default_agent() {
  local box="$1"
  local raw
  raw=$(ssh -o ConnectTimeout=25 -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$box" \
    'bash -lc "command -v openclaw >/dev/null 2>&1 && openclaw agents list --json"' 2>/dev/null) || return 1
  [ -n "$raw" ] || return 1
  python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except Exception:
    i, j = raw.find("["), raw.rfind("]")
    if i < 0 or j <= i:
        sys.exit(1)
    try:
        d = json.loads(raw[i:j+1])
    except Exception:
        sys.exit(1)
if isinstance(d, dict):
    d = d.get("agents") or d.get("data") or []
for a in (d if isinstance(d, list) else []):
    if isinstance(a, dict) and a.get("isDefault"):
        print(a.get("id", ""))
        sys.exit(0)
sys.exit(1)
' <<<"$raw"
}

RESOLVED_FILE="/tmp/rr-seed-resolved.txt"
SKIPPED=0

# --- Upsert -------------------------------------------------------------------
NOW=$(python3 -c 'import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))')
: > /tmp/rr-seed-payload.json
: > "$RESOLVED_FILE"
{
  echo -n '{"data":['
  FIRST=1
  for s in "${SLUGS[@]}"; do
    [ -n "$s" ] || continue
    AGENT=$(resolve_default_agent "$s")
    if [ -z "$AGENT" ]; then
      echo "seed-skip $s cannot-resolve-default-agent"
      SKIPPED=$((SKIPPED+1))
      continue
    fi
    echo "seed-map $s agent=$AGENT"
    printf '%s\t%s\n' "$s" "$AGENT" >> "$RESOLVED_FILE"
    [ "$FIRST" -eq 1 ] || echo -n ','
    FIRST=0
    printf '{"box_slug":"%s","local_agent_id":"%s","source":"seed_rr_agent_map","updated_at":"%s"}' "$s" "$AGENT" "$NOW"
  done
  echo -n ']}'
} > /tmp/rr-seed-payload.json

if [ "$FIRST" -eq 1 ]; then
  echo "seed-rr-agent-map: no box resolved a default agent ($SKIPPED skipped) — writing nothing"
  rm -f "$SLUGS_FILE" /tmp/rr-seed-payload.json "$RESOLVED_FILE"
  if [ "$SKIPPED" -gt 0 ]; then exit 1; else exit 0; fi
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "seed-rr-agent-map: DRY-RUN — would write $(python3 -c 'import json;print(len(json.load(open("/tmp/rr-seed-payload.json"))["data"]))') rows:"
  sed 's/^/    /' /tmp/rr-seed-payload.json | head -c 1500
  rm -f "$SLUGS_FILE" /tmp/rr-seed-payload.json
  exit 0
fi

echo "seed-rr-agent-map: ANNOUNCING WRITE — $N rows into rr_agent_map (resolved default agents). Backup: $BAK"
# chunks of 10 (payload above is one batch; split here for robustness)
python3 -c '
import json, subprocess, os, sys
key = os.environ["N8N_API_KEY"]; host = os.environ.get("N8N_HOST", "https://main.blackceoautomations.com")
table = os.environ["RR_AGENT_MAP_TABLE_ID"]
rows = json.load(open("/tmp/rr-seed-payload.json"))["data"]
ok = 0
for i in range(0, len(rows), 10):
    chunk = {"data": rows[i:i+10]}
    p = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
        "-X", "POST", "-H", f"X-N8N-API-KEY: {key}", "-H", "Content-Type: application/json",
        "--data", json.dumps(chunk), f"{host}/api/v1/data-tables/{table}/rows"],
        capture_output=True, text=True)
    code = p.stdout.strip()
    if code.startswith("2"):
        n = len(chunk["data"])
        ok += n; print("  batch %d: HTTP %s (%d rows)" % (i//10, code, n))
    else:
        print("  batch %d: HTTP %s FAILED — %s" % (i//10, code, p.stderr[:200]), file=sys.stderr)
print("seed-rr-agent-map: wrote %d/%d rows" % (ok, len(rows)))
sys.exit(0 if ok == len(rows) else 1)
'
RC=$?

# --- Verify -------------------------------------------------------------------
# Verify against the RESOLVED map (slug -> agent), not a hardcoded 'main' guess.
if [ "$RC" -eq 0 ]; then
  curl -sS -H "X-N8N-API-KEY: ${N8N_API_KEY}" "$HOST/api/v1/data-tables/$TABLE_ID/rows" > /tmp/rr-seed-after.json
  python3 -c '
import json, sys
resolved = {}
for line in open(sys.argv[1]):
    parts = line.rstrip("\n").split("\t", 1)
    if len(parts) == 2 and parts[0].strip():
        resolved[parts[0].strip()] = parts[1].strip()
want = set(resolved)
d = json.load(open("/tmp/rr-seed-after.json"))
rows = d.get("rows", d.get("data", []))
if isinstance(rows, dict): rows = [rows]
mapped = {r.get("box_slug"): r.get("local_agent_id") for r in rows}
seen = set(r.get("box_slug") for r in rows)
missing = sorted(s for s in want if s not in seen)
wrong = sorted(f"{s} (expected {resolved[s]}, got {mapped.get(s)})" for s in want if mapped.get(s) != resolved.get(s))
print(f"seed-rr-agent-map: VERIFY — table has {len(rows)} rows ({len(seen)} unique slugs); missing={len(missing)} mismatched={len(wrong)}")
if missing: print("  missing:", ", ".join(missing))
if wrong: print("  mismatched:", "; ".join(wrong))
sys.exit(0 if not missing and not wrong else 1)
' "$RESOLVED_FILE"
  RC=$?
fi

rm -f "$SLUGS_FILE" /tmp/rr-seed-payload.json /tmp/rr-seed-after.json "$RESOLVED_FILE"
exit "$RC"

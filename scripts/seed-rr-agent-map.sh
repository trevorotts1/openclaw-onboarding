#!/usr/bin/env bash
# seed-rr-agent-map.sh — provision Rescue Rangers agent-id mappings fleet-wide.
#
# rr_agent_map (n8n data table wHS7NxgnWjpox48k) maps box_slug -> local_agent_id,
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
# (405), so this script is INSERT-ONLY and a rerun may add duplicate rows for
# the same slug. That is benign for RR-02-coach (lookup is limit-1) and the
# verify step below asserts every slug is mapped at least once, not exact
# counts. De-duping a table requires the n8n UI or a workflow.
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
N=$(wc -l < "$SLUGS_FILE" | tr -d ' ')
echo "seed-rr-agent-map: $N box slugs to ensure mapped (dry-run=$DRY_RUN)"

# --- Backup -------------------------------------------------------------------
BAK="/tmp/rr_agent_map-backup-$(date +%Y%m%dT%H%M%S).json"
if [ "$DRY_RUN" -eq 0 ]; then
  curl -sS -H "X-N8N-API-KEY: ${N8N_API_KEY}" "$HOST/api/v1/data-tables/$TABLE_ID/rows" > "$BAK"
  echo "seed-rr-agent-map: backup -> $BAK ($(wc -c < "$BAK" | tr -d ' ') bytes)"
fi

# --- Upsert -------------------------------------------------------------------
NOW=$(python3 -c 'import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))')
declare -a SLUGS
mapfile -t SLUGS < "$SLUGS_FILE"
: > /tmp/rr-seed-payload.json
{
  echo -n '{"data":['
  FIRST=1
  for s in "${SLUGS[@]}"; do
    [ -n "$s" ] || continue
    [ "$FIRST" -eq 1 ] || echo -n ','
    FIRST=0
    printf '{"box_slug":"%s","local_agent_id":"main","source":"seed_rr_agent_map","updated_at":"%s"}' "$s" "$NOW"
  done
  echo -n ']}'
} > /tmp/rr-seed-payload.json

if [ "$DRY_RUN" -eq 1 ]; then
  echo "seed-rr-agent-map: DRY-RUN — would write $(python3 -c 'import json;print(len(json.load(open("/tmp/rr-seed-payload.json"))["data"]))') rows:"
  sed 's/^/    /' /tmp/rr-seed-payload.json | head -c 1500
  rm -f "$SLUGS_FILE" /tmp/rr-seed-payload.json
  exit 0
fi

echo "seed-rr-agent-map: ANNOUNCING WRITE — $N rows into rr_agent_map (local_agent_id=main). Backup: $BAK"
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
if [ "$RC" -eq 0 ]; then
  curl -sS -H "X-N8N-API-KEY: ${N8N_API_KEY}" "$HOST/api/v1/data-tables/$TABLE_ID/rows" > /tmp/rr-seed-after.json
  python3 -c '
import json, sys
want = set(l.strip() for l in open(sys.argv[1]) if l.strip())
d = json.load(open("/tmp/rr-seed-after.json"))
rows = d.get("rows", d.get("data", []))
if isinstance(rows, dict): rows = [rows]
mapped = {r.get("box_slug"): r.get("local_agent_id") for r in rows}
seen = set(r.get("box_slug") for r in rows)
missing = sorted(s for s in want if s not in seen)
wrong = sorted(s for s in want if mapped.get(s) != "main")
print(f"seed-rr-agent-map: VERIFY — table has {len(rows)} rows ({len(seen)} unique slugs); missing={len(missing)} non-main={len(wrong)}")
if missing: print("  missing:", ", ".join(missing))
if wrong: print("  non-main:", ", ".join(wrong))
sys.exit(0 if not missing and not wrong else 1)
' "$SLUGS_FILE"
  RC=$?
fi

rm -f "$SLUGS_FILE" /tmp/rr-seed-payload.json /tmp/rr-seed-after.json
exit "$RC"

#!/usr/bin/env bash
# tests/unit/skill60-72h-retention.test.sh - Skill 60 keeps 72 hours of history.
#
# Proves, against a copy of the real skill with only the sentinel stubbed:
#   A. cron-tick prunes: an event and a digest older than 72h are deleted, a
#      recent event survives, and the tick still maps exit 10 to 0.
#   B. a failing prune never changes the tick's exit code.
#   C. the shipped config says 72 hours.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SK="$ROOT/60-zhc-early-warning-system"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }

cp -R "$SK" "$T/skill"
printf 'import sys\nsys.exit(10)\n' > "$T/skill/scripts/ews_sentinel.py"
export EWS_STATE_DIR="$T/state"; mkdir -p "$EWS_STATE_DIR"

python3 - "$T/skill/scripts" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from datetime import datetime, timedelta, timezone
from ews_ledger import Ledger
old = (datetime.now(timezone.utc) - timedelta(hours=100)).replace(microsecond=0).isoformat()
with Ledger() as led:
    led.record_event("S1", "P2", key_path="old", tick_ts=old)
    led.record_event("S1", "P2", key_path="new")
    led.conn.execute("INSERT INTO digests(kind,dedup_key,sent_ts) VALUES('alert','k',?)", (old,))
    led.conn.commit()
PY

bash "$T/skill/ews-entry.sh" cron-tick >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && ok "A1 cron-tick exits 0 on findings" || bad "A1 cron-tick rc=$rc"
left="$(python3 - "$T/skill/scripts" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from ews_ledger import Ledger
with Ledger() as led:
    ev = sorted(r[0] for r in led.conn.execute("SELECT key_path FROM events"))
    dg = led.conn.execute("SELECT COUNT(*) FROM digests").fetchone()[0]
print(",".join(ev), dg)
PY
)"
[ "$left" = "new 0" ] && ok "A2 old event + old digest pruned, recent event kept" || bad "A2 left: $left"

# B: break the prune; the tick result must not change
printf 'import sys\nsys.exit(3)\n' > "$T/skill/scripts/ews_snapshot.py"
out="$(bash "$T/skill/ews-entry.sh" cron-tick 2>&1)"; rc=$?
[ "$rc" = 0 ] && ok "B1 failing prune leaves the tick exit code alone" || bad "B1 rc=$rc"
case "$out" in *"retention prune failed"*) ok "B2 failing prune is logged";; *) bad "B2 no log line";; esac

hrs="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["snapshots"]["retention_hours"])' "$SK/config/thresholds.json")"
[ "$hrs" = 72 ] && ok "C1 shipped retention is 72 hours" || bad "C1 retention_hours=$hrs"

echo "skill60-72h-retention: $pass passed, $fail failed"
[ "$fail" = 0 ]

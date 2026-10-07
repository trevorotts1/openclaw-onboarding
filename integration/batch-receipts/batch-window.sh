#!/usr/bin/env bash
# batch-window.sh — the 30-minute batch window gate that drives the EXISTING
# merge train. Nothing merges except through this gate.
#
# Cadence and lock mirror watch-tick.sh's merge_batch (MERGE_BATCH_MINUTES,
# merge-batch.stamp, merge-batch.lock.d, never two batches at once), with the
# two reconciliations GITHUB-MERGE-RULES.md requires before use:
#   * MERGE_BATCH_MINUTES is read from the invocation here (default 30), never
#     from an interactive export the cron line would drop;
#   * a missing stamp is seeded at T0, so the first window opens at T0+30min
#     instead of merging immediately.
# The merge itself is always the existing
#   merge-train.sh <home> --batch
# (candidate selection, combined-candidate gate, single push, fetched remote
# ancestry proof, changelog, post-proof cleanup — all the train's own).
#
# Usage: batch-window.sh <project-home> <event-id>
#   stdout  = the train's raw output (tee it to a receipt log)
#   rc      = train's rc, or 2 on WINDOW-REFUSED (gate closed / lock held)
#   appends one JSON event to <home>/CONTROL/window-receipts.jsonl
#
# Env: T0 (default 1791300227 = run/state.json T0), MERGE_BATCH_MINUTES
# (default 30), MERGE_TRAIN_SH, MERGE_TRAIN_TEST_CMD (passed through).
set -uo pipefail

T0="${T0:-1791300227}"
MBM="${MERGE_BATCH_MINUTES:-30}"
MT_SH="${MERGE_TRAIN_SH:-$(git rev-parse --show-toplevel)/999-setup/.claude/skills/spec-protocol/tools/merge-train.sh}"
HOME_DIR="${1:?usage: batch-window.sh <project-home> <event-id>}"
EID="${2:?usage: batch-window.sh <project-home> <event-id>}"

[[ "$MBM" =~ ^[0-9]+$ ]] || { echo "WINDOW-CONFIG-REFUSED | MERGE_BATCH_MINUTES not a non-negative integer"; exit 2; }
[[ -f "$MT_SH" ]] || { echo "WINDOW-CONFIG-REFUSED | merge train not found at $MT_SH"; exit 2; }

CTRL="$HOME_DIR/CONTROL"
STAMP="$CTRL/merge-batch.stamp"
LOCK="$CTRL/merge-batch.lock.d"
RECEIPTS="$CTRL/window-receipts.jsonl"
mkdir -p "$CTRL"

now="$(date +%s)"
iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# First-window reconciliation: a missing stamp would make the first tick merge
# immediately; seed it at T0 so the first eligible window is T0+30min.
if [[ ! -f "$STAMP" ]]; then
  python3 - "$STAMP" "$T0" <<'PY'
import os, sys
p, t = sys.argv[1], int(sys.argv[2])
open(p, "w").close()
os.utime(p, (t, t))
PY
fi
sm="$(stat -f %m "$STAMP" 2>/dev/null || stat -c %Y "$STAMP")"
age=$(( now - sm ))
k=$(( (now - T0) / 1800 )); (( k < 0 )) && k=0
wstart=$(( T0 + 1800 * k )); wend=$(( wstart + 1800 ))

emit() { # emit <json>
  python3 - "$RECEIPTS" "$1" <<'PY'
import sys
with open(sys.argv[1], "a") as f:
    f.write(sys.argv[2] + "\n")
PY
}

emit_event() { # emit_event <type> <reason> <epoch> <age> <rc-or-null> <extra-json>
  python3 - "$EID" "$1" "$2" "$3" "$4" "$5" "$6" "$T0" "$MBM" "$k" "$wstart" "$wend" "$iso" "$now" <<'PY'
import json, sys
eid, typ, reason, epoch, age, rc, extra, t0, mbm, k, ws, we, iso, now = sys.argv[1:15]
ev = {"event": typ, "event_id": eid, "reason": reason, "iso": iso,
      "epoch": int(epoch), "stamp_age_s": int(age), "t0": int(t0),
      "merge_batch_minutes": int(mbm), "window_index": int(k),
      "window_start": int(ws), "window_end": int(we)}
if rc not in ("", "null"):
    ev["train_rc"] = int(rc)
if extra:
    ev.update(json.loads(extra))
print(json.dumps(ev, sort_keys=True))
PY
}

if (( age < MBM * 60 )); then
  emit "$(emit_event refused "window-cadence-not-due" "$now" "$age" null "")"
  printf 'WINDOW-REFUSED | event=%s | reason=window-cadence-not-due | stamp_age=%ss < %ss | window=%s [%s,%s)\n' \
    "$EID" "$age" "$((MBM * 60))" "$k" "$wstart" "$wend"
  exit 2
fi

if ! mkdir "$LOCK" 2>/dev/null; then
  emit "$(emit_event refused "lock-held" "$now" "$age" null "")"
  printf 'WINDOW-REFUSED | event=%s | reason=lock-held | window=%s [%s,%s)\n' "$EID" "$k" "$wstart" "$wend"
  exit 2
fi
printf '%s\n' "$$" > "$LOCK/pid"
touch "$STAMP"   # stamp the window OPEN the same way watch-tick does: before the train runs

set +e
out="$(GIT_COMMITTER_NAME=batch-train GIT_COMMITTER_EMAIL=batch-train@controller.invalid \
       bash "$MT_SH" "$HOME_DIR" --batch 2>&1)"
rc=$?
set -e
rm -rf "$LOCK" 2>/dev/null

now2="$(date +%s)"
iso2="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
k2=$(( (now2 - T0) / 1800 )); (( k2 < 0 )) && k2=0
ws2=$(( T0 + 1800 * k2 )); we2=$(( ws2 + 1800 ))
merged="$(printf '%s\n' "$out" | sed -n 's/^MERGED: unit=\([^ ]*\) commit=\([^ ]*\).*/\1@\2/p' | paste -sd, -)"
extra="$(printf '{"epoch_end":%s,"iso_end":"%s","window_index_end":%s,"window_start_end":%s,"window_end_end":%s,"merged":"%s"}' \
  "$now2" "$iso2" "$k2" "$ws2" "$we2" "$merged")"
emit "$(printf '%s' "$(emit_event batch "train-batch" "$now" "$age" "$rc" "$extra")")"
printf '%s\n' "$out"
printf 'WINDOW-BATCH | event=%s | epoch=[%s,%s) | window=%s [%s,%s) | stamp_age=%ss | rc=%s\n' \
  "$EID" "$now" "$now2" "$k" "$wstart" "$wend" "$age" "$rc"
exit "$rc"

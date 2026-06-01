#!/usr/bin/env bash
# verify-zhc-standard.sh — v10.15.26
#
# ONE source of truth for "is this Zero-Human Company built to the McDonald's
# standard?" Callable from Skill 23 close AND Skill 37 closeout preflight. It
# asserts the full standard end-to-end so no two clients get different
# experiences and nothing is ever marked "done" on a build-state lie:
#
#   1. INTERVIEW COMPLETE   — build-state interviewComplete==true (or an
#                             answers file with real, non-stub content)
#   2. 16 CANONICAL DEPTS   — every mandatory dept from department-naming-map.json
#                             is present on disk (minus any EXPLICITLY declined)
#   3. ROLE LIBRARY DONE     — roleLibraryStatus==done: every dept meets its
#                             canonical role count AND how-to.md filled
#   4. SOP LIBRARY DONE      — sopLibraryStatus==done: every role has >= its
#                             substantive-SOP floor (>=7KB + DMAIC + no stub)
#   5. CLOSEOUT CONFIRMED    — closeoutStatus in {done,sent} AND at least one
#                             telegram message actually delivered
#
# This script does NOT fix anything — it MEASURES and reports. It delegates the
# library verdicts to verify-library-gate.sh (the disk-QC authority) so there
# is exactly one substance definition. Read-only except for the gate's state
# write. Idempotent. Safe to re-run.
#
# EXIT CODES:
#   0 = FULL STANDARD MET (build may close out / closeout may finalize)
#   2 = interview incomplete
#   3 = department floor not met ON DISK (missing mandatory or matched-vertical
#       depts — measured by department-floor.py against real folders, NOT the
#       build-state JSON; closeout MUST refuse on this code)
#   4 = role library not done
#   5 = SOP library not done
#   6 = closeout not confirmed
#   7 = no workforce / cannot resolve company
#
# Multiple gaps => the LOWEST-numbered gap is reported as the exit code, but ALL
# gaps are printed so the operator/agent sees the whole picture in one run.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---- resolve build-state file (VPS first, Mac fallback) ----
if [ -d /data/.openclaw ]; then
  STATE_FILE="/data/.openclaw/workspace/.workforce-build-state.json"
else
  STATE_FILE="$HOME/.openclaw/workspace/.workforce-build-state.json"
fi
NAMING_MAP="$SKILL_DIR/department-naming-map.json"

if ! command -v jq >/dev/null 2>&1; then
  echo "[verify-zhc-standard] jq not installed — cannot evaluate; exiting 7" >&2
  exit 7
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[verify-zhc-standard] python3 not installed — cannot evaluate; exiting 7" >&2
  exit 7
fi

GAPS=()
WORST_RC=0
note_gap() { # <rc> <message>
  local rc="$1"; shift
  GAPS+=("[gap rc=$rc] $*")
  # keep the lowest-numbered (most fundamental) gap as the exit code
  if [ "$WORST_RC" -eq 0 ] || [ "$rc" -lt "$WORST_RC" ]; then WORST_RC="$rc"; fi
}

echo "============================================"
echo "verify-zhc-standard.sh"
echo "state_file=$STATE_FILE"
echo "============================================"

if [ ! -f "$STATE_FILE" ]; then
  echo "[verify-zhc-standard] NO build-state file at $STATE_FILE — no workforce to verify; exiting 7" >&2
  exit 7
fi

# ---- 1. INTERVIEW COMPLETE ----------------------------------------------
INTERVIEW_OK="$(jq -r '.interviewComplete // false' "$STATE_FILE" 2>/dev/null)"
if [ "$INTERVIEW_OK" != "true" ]; then
  # Soft fallback: a populated proposal/answers doc on disk counts as complete
  # even on older builds that never set the flag.
  ANS_OK=0
  for cand in \
    "$HOME/clawd/zero-human-company"/*/skill23-*-workforce-proposal.md \
    "/data/.openclaw/workspace"/skill23-*-workforce-proposal.md \
    "$HOME/.openclaw/workspace"/skill23-*-workforce-proposal.md ; do
    [ -f "$cand" ] && [ "$(wc -c < "$cand" 2>/dev/null || echo 0)" -ge 4000 ] && ANS_OK=1 && break
  done
  if [ "$ANS_OK" -eq 1 ]; then
    echo "[1/5] interview: flag unset but a substantive proposal doc exists — treating as COMPLETE"
  else
    note_gap 2 "interviewComplete != true and no substantive proposal doc found"
    echo "[1/5] interview: INCOMPLETE"
  fi
else
  echo "[1/5] interview: COMPLETE (interviewComplete=true)"
fi

# ---- 2. HARD DEPARTMENT FLOOR (DISK, not build-state JSON) --------------
# v10.15.26 / v10.16.25 — the floor is now measured by department-floor.py
# against the REAL department directories ON DISK, NOT the build-state JSON's
# .departments[] array. This kills the seeded-build-state bypass: a hand-written
# build-state claiming "done" with 3 fake dept entries used to pass step 2;
# now a 3-dept-on-disk workforce FAILS because the 16 mandatory + the
# industry-matched vertical-pack departments are not present as real folders.
# The ONLY way to be below the mandatory floor is an EXPLICIT recorded decline
# (canonicalReconciliation.decisions[cid]=="no" or declinedDepartments[]).
FLOOR_SCRIPT="$SCRIPT_DIR/department-floor.py"
if [ -f "$FLOOR_SCRIPT" ]; then
  FLOOR_JSON="$(python3 "$FLOOR_SCRIPT" --json 2>/dev/null)"
  FLOOR_RC=$?
  if [ "$FLOOR_RC" = "7" ] || [ -z "$FLOOR_JSON" ]; then
    note_gap 7 "department-floor: no workforce on disk to verify"
    echo "[2/5] departments: NO WORKFORCE ON DISK (cannot verify floor)"
  else
    DF_EXPECTED="$(printf '%s' "$FLOOR_JSON" | jq -r '.expected_floor_count')"
    DF_ONDISK="$(printf '%s' "$FLOOR_JSON" | jq -r '.on_disk_count')"
    DF_MISS_M="$(printf '%s' "$FLOOR_JSON" | jq -r '.missing_mandatory | join(", ")')"
    DF_MISS_V="$(printf '%s' "$FLOOR_JSON" | jq -r '.missing_vertical | join(", ")')"
    DF_DECLINED="$(printf '%s' "$FLOOR_JSON" | jq -r '.declined | join(", ")')"
    if [ "$FLOOR_RC" = "0" ]; then
      echo "[2/5] departments: FLOOR MET on disk ($DF_ONDISK depts >= floor $DF_EXPECTED; declined: ${DF_DECLINED:-none})"
    else
      _msg="floor NOT met on disk ($DF_ONDISK depts vs expected $DF_EXPECTED)"
      [ -n "$DF_MISS_M" ] && _msg="$_msg; missing mandatory: $DF_MISS_M"
      [ -n "$DF_MISS_V" ] && _msg="$_msg; missing matched-vertical: $DF_MISS_V"
      note_gap 3 "$_msg"
      echo "[2/5] departments: $_msg"
    fi
  fi
else
  # No floor script present (older bundle): fall back to the legacy build-state
  # check so the gate is not weaker than before, but warn loudly.
  echo "[2/5] departments: WARN — department-floor.py missing; falling back to build-state JSON check (weaker)" >&2
  DEPT_CHECK="$(python3 - "$NAMING_MAP" "$STATE_FILE" <<'PYEOF'
import json, sys
naming_map_path, state_path = sys.argv[1], sys.argv[2]
try:
    nm = json.load(open(naming_map_path))
except Exception:
    nm = {}
mandatory = list(nm.get("mandatory", {}).keys())
try:
    st = json.load(open(state_path))
except Exception:
    st = {}
present = set()
for d in st.get("departments", []):
    for k in ("slug", "dept_id", "id", "name"):
        if d.get(k):
            present.add(str(d[k]).lower())
declined = set()
for cid, dec in ((st.get("canonicalReconciliation", {}) or {}).get("decisions", {}) or {}).items():
    if str(dec).lower() == "no":
        declined.add(cid)
missing = []
for cid in mandatory:
    if cid in declined:
        continue
    norm = cid.replace("-", "")
    if cid.lower() in present or any(norm == p.replace("-", "") for p in present):
        continue
    missing.append(cid)
print(json.dumps({"mandatory": len(mandatory), "missing": missing}))
PYEOF
)"
  DEPT_MISSING="$(printf '%s' "$DEPT_CHECK" | jq -r '.missing | join(", ")')"
  if [ -n "$DEPT_MISSING" ]; then
    note_gap 3 "missing canonical departments: $DEPT_MISSING"
    echo "[2/5] departments: MISSING ($DEPT_MISSING)"
  fi
fi

# ---- 3 + 4. ROLE LIBRARY + SOP LIBRARY (delegate to the disk-QC gate) ----
GATE="$SCRIPT_DIR/verify-library-gate.sh"
if [ -f "$GATE" ]; then
  bash "$GATE" >/dev/null 2>&1
  GATE_RC=$?
  ROLE_STATUS="$(jq -r '.roleLibraryStatus // "unknown"' "$STATE_FILE" 2>/dev/null)"
  SOP_STATUS="$(jq -r '.sopLibraryStatus // "unknown"' "$STATE_FILE" 2>/dev/null)"
  FAILR="$(jq -r '.libraryFailureReason // ""' "$STATE_FILE" 2>/dev/null)"
  if [ "$ROLE_STATUS" != "done" ]; then
    note_gap 4 "role library not done (roleLibraryStatus=$ROLE_STATUS; $FAILR)"
    echo "[3/5] role library: NOT done ($ROLE_STATUS)"
  else
    echo "[3/5] role library: done"
  fi
  if [ "$SOP_STATUS" != "done" ]; then
    note_gap 5 "SOP library not done (sopLibraryStatus=$SOP_STATUS; $FAILR)"
    echo "[4/5] SOP library: NOT done ($SOP_STATUS)"
  else
    echo "[4/5] SOP library: done (substantive)"
  fi
else
  note_gap 4 "verify-library-gate.sh missing at $GATE — cannot verify libraries"
  echo "[3-4/5] libraries: CANNOT VERIFY (gate script missing)"
fi

# ---- 5. CLOSEOUT CONFIRMED ----------------------------------------------
CLOSE_STATUS="$(jq -r '.closeoutStatus // "unset"' "$STATE_FILE" 2>/dev/null)"
DELIVERED_N="$(jq -r '(.messagesDelivered // []) | length' "$STATE_FILE" 2>/dev/null)"
case "$CLOSE_STATUS" in
  done|sent)
    if [ "${DELIVERED_N:-0}" -ge 1 ] 2>/dev/null; then
      echo "[5/5] closeout: CONFIRMED (closeoutStatus=$CLOSE_STATUS, messagesDelivered=$DELIVERED_N)"
    else
      note_gap 6 "closeoutStatus=$CLOSE_STATUS but messagesDelivered=0 (no confirmed Telegram delivery)"
      echo "[5/5] closeout: status=$CLOSE_STATUS but NO confirmed messages delivered"
    fi ;;
  *)
    note_gap 6 "closeout not confirmed (closeoutStatus=$CLOSE_STATUS)"
    echo "[5/5] closeout: NOT confirmed ($CLOSE_STATUS)" ;;
esac

echo "--------------------------------------------"
if [ "${#GAPS[@]}" -eq 0 ]; then
  echo "RESULT: ✅ FULL ZHC STANDARD MET"
  exit 0
fi
echo "RESULT: ❌ STANDARD NOT MET — ${#GAPS[@]} gap(s):"
for g in "${GAPS[@]}"; do echo "  - $g"; done
echo "Exit code = $WORST_RC (lowest/most-fundamental gap)."
exit "$WORST_RC"

#!/usr/bin/env bash
# verify-library-gate.sh — v10.15.18 (SUBSTANCE GATE)
#
# ENFORCED build gate for the ROLE LIBRARY + SOP LIBRARY auto-pull.
#
# v10.15.18: the SOP verdict now uses a SUBSTANCE floor (>=7KB + all DMAIC
# headers + no placeholder, every role >= 4 substantive SOPs) and the ROLE
# verdict requires every dept to meet its canonical role count — not the old
# "stubs==0 AND avg>0" rule that accepted empty/thin builds.
#
# Why this exists: last night (Kofi/Teresa/Evelyn/Maria/Lyric) several workforces
# were scaffolded — department folders + role folders existed — but the role
# library was never pulled into the how-to.md files AND the SOP placeholders were
# never authored. The build still reported "done" because nothing GATED on those
# two libraries being populated.
#
# Prose like "AUTOMATIC NEXT STEP: also pull the role library" is NOT enforcement.
# Enforcement = a STATE FIELD + a VERIFY/RESUME GATE. This script is that gate. It:
#   1. Runs qc-completeness.sh (read-only) to measure, per dept:
#        - library_pct        (how-to.md filled from role-library marker)
#        - sop_stubs_remaining + avg_sop_per_role (SOP files authored)
#   2. Writes the gate fields into .workforce-build-state.json (atomic):
#        - roleLibraryStatus  : pending | pulling | done | failed
#        - sopLibraryStatus   : pending | authoring | done | failed
#        - departments[].roleLibraryFilled / .sopLibraryFilled (booleans)
#        - libraryFailureReason (when not done)
#   3. Exits:
#        0  = BOTH libraries done (gate PASSES — build may proceed to closeout)
#        2  = role library NOT done
#        3  = SOP library NOT done
#        4  = both NOT done
#        5  = no workforce / qc could not run
#
# The master orchestrator MUST run this BEFORE writing buildCompletedAt /
# closeoutStatus=pending. The resume cron (resume-workforce-build.sh) also calls
# the gate and fires a [LIBRARY-RESUME] self-ping while either status != done.
#
# Read-only with respect to the workforce tree; only writes the state file.
# Idempotent. Safe to re-run any number of times.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---- resolve build-state file (VPS first, Mac fallback) ----
if [ -d /data/.openclaw ]; then
  STATE_FILE="/data/.openclaw/workspace/.workforce-build-state.json"
else
  STATE_FILE="$HOME/.openclaw/workspace/.workforce-build-state.json"
fi

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

if ! command -v jq >/dev/null 2>&1; then
  echo "[verify-library-gate] jq not installed — cannot write gate state; exiting 5" >&2
  exit 5
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[verify-library-gate] python3 not installed — cannot run qc; exiting 5" >&2
  exit 5
fi

# ---- run qc-completeness.sh (quiet, read-only) and find its JSON artifact ----
QC_SCRIPT="$SCRIPT_DIR/qc-completeness.sh"
if [ ! -f "$QC_SCRIPT" ]; then
  echo "[verify-library-gate] qc-completeness.sh missing at $QC_SCRIPT — exiting 5" >&2
  exit 5
fi

LOG_DIR="$HOME/.openclaw/logs"
[ -d "/data/.openclaw" ] && LOG_DIR="/data/.openclaw/logs"

bash "$QC_SCRIPT" --quiet >/dev/null 2>&1
QC_RC=$?
if [ "$QC_RC" -eq 4 ]; then
  echo "[verify-library-gate] qc reports NO_WORKFORCE_FOUND — nothing to gate; exiting 5" >&2
  exit 5
fi

# newest qc-completeness JSON artifact
QC_JSON="$(ls -t "$LOG_DIR"/qc-completeness-*.json 2>/dev/null | head -1)"
if [ -z "$QC_JSON" ] || [ ! -f "$QC_JSON" ]; then
  echo "[verify-library-gate] no qc-completeness JSON artifact found in $LOG_DIR — exiting 5" >&2
  exit 5
fi

# ---- derive role/SOP library verdicts from the qc artifact ----
# v10.15.18 SUBSTANCE GATE. The old SOP rule (stubs==0 AND avg_sop_per_role>0)
# accepted empty/thin builds: a role with ZERO SOPs passed as long as the dept
# average was >0, and a 1 KB hollow SOP with the placeholder string deleted
# counted as done. That is the Maria-thin / Evelyn-stub / Sheila-empty bug.
#
# New rule — a dept's SOP library is done ONLY when:
#   * roles_below_min_sops == 0  (EVERY role has >= its floor of SUBSTANTIVE
#     SOPs; substantive = >=7KB AND all DMAIC headers AND no placeholder, as
#     measured by qc-completeness.sh sop_is_substantive())
#   * substantive_sop_count > 0
# New rule — a dept's ROLE library is done ONLY when:
#   * library_pct == 100  (how-to.md filled from role-library), AND
#   * role_folders >= expected_roles when an expected (canonical) count exists
#     (no department may ship below its canonical role count).
GATE_JSON="$(python3 - "$QC_JSON" <<'PYEOF'
import json, sys
qc = json.load(open(sys.argv[1]))
depts = qc.get("departments", [])
role_done = bool(depts)
sop_done = bool(depts)
role_gaps = []
sop_gaps = []
per_dept = {}
for d in depts:
    did = d.get("dept_id", "?")
    libpct = d.get("library_pct", 0)
    role_folders = d.get("role_folders", 0)
    expected = d.get("expected_roles", 0)
    substantive = d.get("substantive_sop_count", 0)
    below_min = d.get("roles_below_min_sops", role_folders)
    min_sop = d.get("min_sop_per_role", 0)
    floor = d.get("sop_floor", 4)
    # ROLE library: how-to filled to 100% AND dept meets its canonical role count
    rfilled = (libpct >= 100.0) and (expected == 0 or role_folders >= expected)
    # SOP library: every role meets its substantive-SOP floor and there is real content
    sfilled = (below_min == 0 and substantive > 0 and role_folders > 0)
    per_dept[did] = {"roleLibraryFilled": rfilled, "sopLibraryFilled": sfilled}
    if not rfilled:
        role_done = False
        role_gaps.append(f"{did} lib%={libpct} roles={role_folders}/{expected}")
    if not sfilled:
        sop_done = False
        sop_gaps.append(f"{did} substantive={substantive} minSOP/role={min_sop}<{floor} rolesBelowFloor={below_min}")
print(json.dumps({
    "role_done": role_done,
    "sop_done": sop_done,
    "role_gaps": role_gaps,
    "sop_gaps": sop_gaps,
    "per_dept": per_dept,
}))
PYEOF
)"

ROLE_DONE="$(printf '%s' "$GATE_JSON" | jq -r '.role_done')"
SOP_DONE="$(printf '%s' "$GATE_JSON" | jq -r '.sop_done')"
ROLE_GAPS="$(printf '%s' "$GATE_JSON" | jq -r '.role_gaps | join("; ")')"
SOP_GAPS="$(printf '%s' "$GATE_JSON" | jq -r '.sop_gaps | join("; ")')"

ROLE_STATUS="failed"; [ "$ROLE_DONE" = "true" ] && ROLE_STATUS="done"
SOP_STATUS="failed";  [ "$SOP_DONE"  = "true" ] && SOP_STATUS="done"

FAIL_REASON=""
[ "$ROLE_STATUS" != "done" ] && FAIL_REASON="role-library: ${ROLE_GAPS:-incomplete}"
if [ "$SOP_STATUS" != "done" ]; then
  [ -n "$FAIL_REASON" ] && FAIL_REASON="$FAIL_REASON | "
  FAIL_REASON="${FAIL_REASON}sop: ${SOP_GAPS:-incomplete}"
fi

# ---- write the gate fields into the state file (atomic), if it exists ----
if [ -f "$STATE_FILE" ]; then
  TMP="$(mktemp)"
  if [ "$FAIL_REASON" = "" ]; then FAIL_JSON="null"; else FAIL_JSON="$(printf '%s' "$FAIL_REASON" | jq -Rs '.')"; fi
  jq \
    --arg role "$ROLE_STATUS" \
    --arg sop "$SOP_STATUS" \
    --argjson fail "$FAIL_JSON" \
    --argjson perdept "$(printf '%s' "$GATE_JSON" | jq '.per_dept')" \
    '
      .roleLibraryStatus = $role
      | .sopLibraryStatus = $sop
      | .libraryFailureReason = $fail
      | .departments = ((.departments // []) | map(
          . as $d
          | ($perdept[$d.slug] // {}) as $pd
          | $d
          + (if ($pd | has("roleLibraryFilled")) then {roleLibraryFilled: $pd.roleLibraryFilled} else {} end)
          + (if ($pd | has("sopLibraryFilled")) then {sopLibraryFilled: $pd.sopLibraryFilled} else {} end)
        ))
    ' "$STATE_FILE" > "$TMP" 2>/dev/null && mv "$TMP" "$STATE_FILE" \
      || { rm -f "$TMP"; echo "[verify-library-gate] WARN: could not update $STATE_FILE" >&2; }
else
  echo "[verify-library-gate] no state file at $STATE_FILE — reporting verdict only (not gating closeout)" >&2
fi

echo "[verify-library-gate] roleLibraryStatus=$ROLE_STATUS sopLibraryStatus=$SOP_STATUS"
[ -n "$FAIL_REASON" ] && echo "[verify-library-gate] gaps: $FAIL_REASON" >&2

# ---- exit code = the gate verdict ----
if [ "$ROLE_STATUS" = "done" ] && [ "$SOP_STATUS" = "done" ]; then
  exit 0
elif [ "$ROLE_STATUS" != "done" ] && [ "$SOP_STATUS" != "done" ]; then
  exit 4
elif [ "$ROLE_STATUS" != "done" ]; then
  exit 2
else
  exit 3
fi

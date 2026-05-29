#!/usr/bin/env bash
# verify-library-gate.sh — v10.15.8
#
# ENFORCED build gate for the ROLE LIBRARY + SOP LIBRARY auto-pull.
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
# role done  := every dept library_pct == 100 (and at least one dept on disk)
# sop done   := every dept sop_stubs_remaining == 0 AND avg_sop_per_role > 0
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
    stubs = d.get("sop_stubs_remaining", 0)
    avg_sop = d.get("avg_sop_per_role", 0)
    rfilled = (libpct >= 100.0)
    sfilled = (stubs == 0 and avg_sop > 0)
    per_dept[did] = {"roleLibraryFilled": rfilled, "sopLibraryFilled": sfilled}
    if not rfilled:
        role_done = False
        role_gaps.append(f"{did} lib%={libpct}")
    if not sfilled:
        sop_done = False
        sop_gaps.append(f"{did} stubs={stubs} sop/role={avg_sop}")
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

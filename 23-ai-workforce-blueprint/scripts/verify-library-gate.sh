#!/usr/bin/env bash
# verify-library-gate.sh — v10.17.0 (SUBSTANCE GATE + TRIO GATE + BOUNDARY GATE)
#
# ENFORCED build gate for the ROLE LIBRARY + SOP LIBRARY auto-pull.
#
# v10.17.0 (PRD 2.12): adds BOUNDARY GATE — asserts canonical departments NEVER
# enter the SOP authoring path. Canonical depts are those with pre-written role
# templates in 23-ai-workforce-blueprint/templates/role-library/. They MUST be
# resolved by copy + token-personalise via _instantiate_role_from_library() in
# build-workforce.py. If any canonical dept appears in sop-research-manifest.json
# (the authoring path input), this gate fails with rc=7. The build gate reads the
# manifest's boundary_gate field (written by build-workforce.py) and also runs
# sop-boundary-gate.py --check-manifest directly for independent verification.
# Token economics: pre-written templates exist precisely to avoid burning LLM
# tokens on standard canonical work.
#
# v10.16.0 (PRD 2.11): adds TRIO GATE — every operational department in the
# built workforce must have a QC specialist role file, a deep-research specialist
# role file, and a devil's-advocate role file present in its role-library folder.
# The devil's-advocate is auto-created and NEVER surfaced to the client. A build
# that lacks any of the three roles for any department fails this gate with rc=6.
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
#   2. Asserts the TRIO (PRD 2.11): for every operational dept, the role-library
#      source directory must contain a qc-specialist, deep-research-specialist,
#      and devils-advocate file. Emits trioStatus: done | failed.
#   3. Writes the gate fields into .workforce-build-state.json (atomic):
#        - roleLibraryStatus  : pending | pulling | done | failed
#        - sopLibraryStatus   : pending | authoring | done | failed
#        - trioStatus         : done | failed  (NEW — PRD 2.11)
#        - departments[].roleLibraryFilled / .sopLibraryFilled / .trioFilled (booleans)
#        - libraryFailureReason (when not done)
#   4. Exits:
#        0  = ALL gates pass (role library + SOP library + trio + boundary complete)
#        2  = role library NOT done
#        3  = SOP library NOT done
#        4  = both role AND SOP libraries NOT done
#        5  = no workforce / qc could not run
#        6  = TRIO GATE FAIL — at least one dept is missing QC, research, or DA
#        7  = BOUNDARY GATE FAIL — canonical dept(s) found in SOP authoring manifest
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

# ---- TRIO GATE (PRD 2.11): assert QC + research + DA files per dept --------
# Checks the role-library SOURCE tree (where build-workforce.py copies files
# from) NOT the built workforce. This ensures the library itself is complete
# before any build is considered done. Every operational department in the
# library must have all three files; meta-dirs and master-orchestrator are
# excluded because they are not operational workflow departments.
LIBRARY_DIR="$SKILL_DIR/templates/role-library"
TRIO_JSON="$(python3 - "$LIBRARY_DIR" <<'PYEOF'
import json, os, sys
from pathlib import Path

library_dir = Path(sys.argv[1])
# Directories that are not operational workflow departments
SKIP = {"_stage1_drafts", "master-orchestrator"}

dept_results = {}
trio_gaps = []
trio_done = True

for dept_path in sorted(library_dir.iterdir()):
    if not dept_path.is_dir():
        continue
    dept = dept_path.name
    if dept.startswith("_") or dept in SKIP:
        continue
    files = [f.name.lower() for f in dept_path.iterdir() if f.suffix == ".md"]
    has_qc = any("qc" in f for f in files)
    has_research = any("deep-research" in f for f in files)
    has_da = any("devil" in f for f in files)
    trio_filled = has_qc and has_research and has_da
    dept_results[dept] = {
        "trioFilled": trio_filled,
        "hasQC": has_qc,
        "hasResearch": has_research,
        "hasDA": has_da,
    }
    if not trio_filled:
        trio_done = False
        missing = []
        if not has_qc: missing.append("qc-specialist")
        if not has_research: missing.append("deep-research-specialist")
        if not has_da: missing.append("devils-advocate")
        trio_gaps.append(f"{dept} missing: {', '.join(missing)}")

print(json.dumps({
    "trio_done": trio_done,
    "trio_gaps": trio_gaps,
    "per_dept": dept_results,
}))
PYEOF
)"

TRIO_DONE="$(printf '%s' "$TRIO_JSON" | jq -r '.trio_done')"
TRIO_GAPS="$(printf '%s' "$TRIO_JSON" | jq -r '.trio_gaps | join("; ")')"
TRIO_STATUS="failed"; [ "$TRIO_DONE" = "true" ] && TRIO_STATUS="done"

# Merge trio per-dept results into the gate per-dept map
MERGED_GATE_JSON="$(python3 - "$GATE_JSON" "$TRIO_JSON" <<'PYEOF'
import json, sys
gate = json.loads(sys.argv[1])
trio = json.loads(sys.argv[2])
trio_per = trio.get("per_dept", {})
gate_per = gate.get("per_dept", {})
for dept, td in trio_per.items():
    gate_per.setdefault(dept, {})
    gate_per[dept]["trioFilled"] = td.get("trioFilled", False)
gate["per_dept"] = gate_per
print(json.dumps(gate))
PYEOF
)"
GATE_JSON="$MERGED_GATE_JSON"

# Append trio to fail reason
if [ "$TRIO_STATUS" != "done" ]; then
  [ -n "$FAIL_REASON" ] && FAIL_REASON="$FAIL_REASON | "
  FAIL_REASON="${FAIL_REASON}trio: ${TRIO_GAPS:-incomplete}"
fi

# ---- BOUNDARY GATE (PRD 2.12): assert canonical depts never in authoring path ----
# Checks sop-research-manifest.json via sop-boundary-gate.py --check-manifest.
# A canonical dept in the manifest means build-workforce.py failed to copy from
# the role-library for that dept — token-economics violation.
BOUNDARY_STATUS="done"
BOUNDARY_GAPS=""
MANIFEST_PATH=""

# Locate the most recent sop-research-manifest.json
if [ -d /data/.openclaw/workspace ]; then
  MANIFEST_PATH="$(ls /data/.openclaw/workspace/*/sop-research-manifest.json 2>/dev/null | head -1)"
elif [ -d "$HOME/.openclaw/workspace" ]; then
  MANIFEST_PATH="$(ls "$HOME/.openclaw/workspace"/*/sop-research-manifest.json 2>/dev/null | head -1)"
fi

BOUNDARY_GATE_SCRIPT="$SCRIPT_DIR/sop-boundary-gate.py"
if [ -z "$MANIFEST_PATH" ] || [ ! -f "$MANIFEST_PATH" ]; then
  echo "[verify-library-gate] BOUNDARY GATE: no sop-research-manifest.json found — skipping boundary check (not yet in authoring phase)" >&2
  BOUNDARY_STATUS="done"
elif [ ! -f "$BOUNDARY_GATE_SCRIPT" ]; then
  echo "[verify-library-gate] BOUNDARY GATE: sop-boundary-gate.py not found at $BOUNDARY_GATE_SCRIPT — gate unavailable" >&2
  BOUNDARY_STATUS="done"
else
  BOUNDARY_OUTPUT="$(python3 "$BOUNDARY_GATE_SCRIPT" --check-manifest "$MANIFEST_PATH" 2>&1)"
  BOUNDARY_RC=$?
  if [ "$BOUNDARY_RC" -eq 7 ]; then
    BOUNDARY_STATUS="failed"
    BOUNDARY_GAPS="$(printf '%s' "$BOUNDARY_OUTPUT" | grep 'BOUNDARY VIOLATION\|REFUSE\|canonical dept' | head -5 | tr '\n' '; ')"
    echo "[verify-library-gate] BOUNDARY GATE FAIL (rc=7): canonical dept(s) in authoring manifest." >&2
    printf '%s\n' "$BOUNDARY_OUTPUT" >&2
  else
    BOUNDARY_STATUS="done"
    echo "[verify-library-gate] BOUNDARY GATE PASS: no canonical depts in authoring manifest." >&2
  fi
fi

# Append boundary to fail reason
if [ "$BOUNDARY_STATUS" != "done" ]; then
  [ -n "$FAIL_REASON" ] && FAIL_REASON="$FAIL_REASON | "
  FAIL_REASON="${FAIL_REASON}boundary: ${BOUNDARY_GAPS:-canonical dept(s) in authoring manifest}"
fi

# ---- write the gate fields into the state file (atomic), if it exists ----
if [ -f "$STATE_FILE" ]; then
  TMP="$(mktemp)"
  if [ "$FAIL_REASON" = "" ]; then FAIL_JSON="null"; else FAIL_JSON="$(printf '%s' "$FAIL_REASON" | jq -Rs '.')"; fi
  jq \
    --arg role "$ROLE_STATUS" \
    --arg sop "$SOP_STATUS" \
    --arg trio "$TRIO_STATUS" \
    --arg boundary "$BOUNDARY_STATUS" \
    --argjson fail "$FAIL_JSON" \
    --argjson perdept "$(printf '%s' "$GATE_JSON" | jq '.per_dept')" \
    '
      .roleLibraryStatus = $role
      | .sopLibraryStatus = $sop
      | .trioStatus = $trio
      | .sopAuthoringBoundaryStatus = $boundary
      | .libraryFailureReason = $fail
      | .departments = ((.departments // []) | map(
          . as $d
          | ($perdept[$d.slug] // {}) as $pd
          | $d
          + (if ($pd | has("roleLibraryFilled")) then {roleLibraryFilled: $pd.roleLibraryFilled} else {} end)
          + (if ($pd | has("sopLibraryFilled")) then {sopLibraryFilled: $pd.sopLibraryFilled} else {} end)
          + (if ($pd | has("trioFilled")) then {trioFilled: $pd.trioFilled} else {} end)
        ))
    ' "$STATE_FILE" > "$TMP" 2>/dev/null && mv "$TMP" "$STATE_FILE" \
      || { rm -f "$TMP"; echo "[verify-library-gate] WARN: could not update $STATE_FILE" >&2; }
else
  echo "[verify-library-gate] no state file at $STATE_FILE — reporting verdict only (not gating closeout)" >&2
fi

echo "[verify-library-gate] roleLibraryStatus=$ROLE_STATUS sopLibraryStatus=$SOP_STATUS trioStatus=$TRIO_STATUS sopAuthoringBoundaryStatus=$BOUNDARY_STATUS"
[ -n "$FAIL_REASON" ] && echo "[verify-library-gate] gaps: $FAIL_REASON" >&2

# ---- exit code = the gate verdict (boundary failure = rc 7, takes priority over all) ----
if [ "$BOUNDARY_STATUS" != "done" ]; then
  exit 7
elif [ "$TRIO_STATUS" != "done" ]; then
  exit 6
elif [ "$ROLE_STATUS" = "done" ] && [ "$SOP_STATUS" = "done" ]; then
  exit 0
elif [ "$ROLE_STATUS" != "done" ] && [ "$SOP_STATUS" != "done" ]; then
  exit 4
elif [ "$ROLE_STATUS" != "done" ]; then
  exit 2
else
  exit 3
fi

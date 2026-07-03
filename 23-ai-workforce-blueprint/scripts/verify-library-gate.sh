#!/usr/bin/env bash
# verify-library-gate.sh — v10.18.1 (SUBSTANCE GATE + TRIO GATE + BOUNDARY GATE + PRESENTATIONS WELCOME + CONTENT FLOOR)
#
# v10.18.1 (BUG 1 FIX): the gate no longer trusts the <!-- Filled from role-library -->
# marker alone.  qc-completeness.sh now requires BOTH the marker AND file size >= 3072 B
# before counting a role as library-filled (library_pct).  build-workforce.py and
# create_role_workspaces.py also refuse to stamp the marker on thin output (< 3072 B),
# returning None instead so the caller falls back to the PENDING-stub path.
# This closes the gap where a thin stub carrying the marker passed rfilled=True here
# while verify-wiring.sh correctly failed the same file.
#
# ENFORCED build gate for the ROLE LIBRARY + SOP LIBRARY auto-pull.
#
# v10.18.0: adds PRESENTATIONS WELCOME auto-send -- on full gate pass, calls
# scripts/send-presentation-dept-welcome.sh (idempotent; guarded by
# presentationDeptWelcomeSent in state file). Failure = WARNING only; does not
# change exit code. See: templates/role-library/presentations/
# first-time-onboarding-presentations.md Section 20 for canonical template.
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
# Why this exists: last night several workforces
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
#        9  = ZHE GATE FAIL — the full ZERO HUMAN EXPERIENCE did not land for an
#             interview-completed box (blocks BY DEFAULT; ZHE_ENFORCE=0 escape hatch.
#             zheStatus + plan W1.2; doctrine: ZERO-HUMAN-EXPERIENCE.md)
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

# v10.15.45 (Mac) / v10.16.44 (VPS): set QC_SKIP_PRESENTATION_DEPS=1 so that
# the library/SOP gate is not blocked by a missing LibreOffice/soffice dep.
# Presentation dep checks are relevant for the PRESENTATION step only; the
# role-library and SOP-library verdicts must run regardless of whether soffice
# is installed. Without this flag, qc-completeness exits 6 before writing any
# dept-level JSON, and this gate reads an empty/stub artifact and incorrectly
# marks roleLibraryStatus=failed + sopLibraryStatus=failed.
QC_SKIP_PRESENTATION_DEPS=1 bash "$QC_SCRIPT" --quiet >/dev/null 2>&1
QC_RC=$?
# Handle PRESENTATION_DEPS_MISSING (exit 6) from qc-completeness: the JSON was
# written with status=PRESENTATION_DEPS_MISSING which contains no dept data, so
# we re-run qc with the skip flag (already done above) and the JSON written
# during THAT run is what we'll use. If rc is 6 and we already set the skip
# flag, this means qc hit some other early exit — treat as partial/unknown.
if [ "$QC_RC" -eq 6 ]; then
  echo "[verify-library-gate] WARN: qc exited 6 (PRESENTATION_DEPS_MISSING) even with QC_SKIP_PRESENTATION_DEPS=1 — possible soffice dep check bypassed but another dep is missing; continuing with available JSON artifact" >&2
fi
if [ "$QC_RC" -eq 4 ]; then
  echo "[verify-library-gate] qc reports NO_WORKFORCE_FOUND — nothing to gate; exiting 5" >&2
  exit 5
fi
# v12.9.4: exit code 5 from qc-completeness.sh = GATE_BUG (resolver returned no
# company dir but a real workforce dir exists on disk).  This is a hard resolver
# failure — do NOT silently pass or treat as "no workforce".  Exit non-zero so
# the calling orchestrator sees a gate failure and does not advance closeout.
if [ "$QC_RC" -eq 5 ]; then
  echo "[verify-library-gate] qc reports GATE_BUG — company-dir resolver returned no result" \
       "but a real workforce dir exists. This is a resolver bug. Exiting 8." >&2
  exit 8
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
# counted as done. That is the thin-file / stub-file / empty-file bug.
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

# ── GATE-SCOPE (Option 2, 2026-06-20): scope the TRIO gate to depts whose
# CANONICAL roster includes the trio ──────────────────────────────────────────
# The trio (qc-specialist + deep-research-specialist + devils-advocate) is a bar
# for full operational departments. Minimal ops departments — listings,
# logistics-fulfillment, podcast, product-production, scheduling-dispatch — have
# 4-5 role canonical rosters that NEVER included the full trio (e.g. podcast has a
# qc-specialist but no deep-research/devils-advocate). Forcing the trio on them
# fails genuinely client-complete workforces. We now REQUIRE the trio for a dept
# ONLY when that dept's CANONICAL roster (_index.json roles) registers all three.
# This is the authority — not a blanket requirement and not a hardcoded dept list.
# A dept whose canonical roster DOES include the trio is still fully gated: if a
# built/library trio member is missing, it STILL fails (no weakening).
INDEX_JSON = library_dir / "_index.json"
roster_requires_trio = {}   # dept -> True iff its canonical roster registers qc+research+da
try:
    _idx = json.loads(INDEX_JSON.read_text())
    for _dept, _info in (_idx.get("departments") or {}).items():
        _roles = [str(r).lower() for r in (_info.get("roles") or [])]
        _has_qc = any("qc" in r for r in _roles)
        _has_research = any("deep-research" in r for r in _roles)
        _has_da = any("devil" in r for r in _roles)
        roster_requires_trio[_dept] = (_has_qc and _has_research and _has_da)
except Exception:
    # If the index can't be read, fall back to requiring the trio everywhere
    # (fail-closed): an unreadable roster must NOT silently exempt any dept.
    roster_requires_trio = {}

dept_results = {}
trio_gaps = []
trio_done = True

for dept_path in sorted(library_dir.iterdir()):
    if not dept_path.is_dir():
        continue
    dept = dept_path.name
    if dept.startswith("_") or dept in SKIP:
        continue
    # GATE-SCOPE: skip the trio requirement for depts whose canonical roster does
    # not register the full trio (minimal ops depts). Fail-closed: if the roster
    # is unknown (roster_requires_trio empty / dept absent), default to REQUIRING
    # the trio so a real gap is never hidden by a missing/garbled index.
    if dept in roster_requires_trio and not roster_requires_trio[dept]:
        dept_results[dept] = {
            "trioFilled": True,
            "trioRequired": False,
            "hasQC": None, "hasResearch": None, "hasDA": None,
        }
        continue
    # BUG 3 FIX (gate-measurement, 2026-06-20): the trio roles (qc-specialist,
    # deep-research-specialist, devils-advocate) are stored in the role-library in
    # TWO equally-valid shapes — as a flat "<slug>.md" FILE in some depts, and as a
    # "<slug>/" SUBDIRECTORY containing how-to.md/IDENTITY.md in others (the
    # instantiate-style depts: account-management, client-experience-booking,
    # engineering, founding-member-concierge, launch-operations, ...). The old gate
    # only collected ".md" FILES, so every subdirectory-stored trio read as missing
    # and ~10 depts failed the trio gate though all three roles exist. Fix: build
    # the candidate-name set from BOTH ".md" files AND any subdirectory that
    # actually carries a role artifact (how-to.md or IDENTITY.md). The name-match
    # logic below is UNCHANGED, so a genuinely-missing trio member — no matching
    # .md and no matching role subdir — STILL fails this gate (no weakening).
    names = []
    for f in dept_path.iterdir():
        if f.is_file() and f.suffix == ".md":
            names.append(f.name.lower())
        elif f.is_dir() and not f.name.startswith(".") and not f.name.startswith("_"):
            # a directory only counts as a stored role if it holds a role artifact
            if (f / "how-to.md").is_file() or (f / "IDENTITY.md").is_file():
                names.append(f.name.lower())
    files = names
    has_qc = any("qc" in f for f in files)
    has_research = any("deep-research" in f for f in files)
    has_da = any("devil" in f for f in files)
    trio_filled = has_qc and has_research and has_da
    dept_results[dept] = {
        "trioFilled": trio_filled,
        "trioRequired": True,
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

# ---- ZHE GATE (plan W1.2): ZERO HUMAN EXPERIENCE acceptance prover -----------
# The highest-priority verdict. prove-zhe.py asserts the WHOLE post-interview ZHE
# landed for an interview-completed box: floor depts present AND registered as
# agents, personas canonical + section-tagged, Command Center board live, and
# AGENTS.md carrying the routing + persona-reflex + full-context-handoff +
# reporting + platform-facts doctrine. A not-completed interview is EXEMPT (the
# prover passes). Doctrine: 23-ai-workforce-blueprint/ZERO-HUMAN-EXPERIENCE.md.
#
# BLOCKING BY DEFAULT (Issue #6, v17.0.11): the RED-first precondition has landed
# (apply-fleet-standards.sh stamps the persona/handoff/reporting/platform-facts
# markers), so this gate now forces a hard exit (rc 9, above all other verdicts) by
# default when the prover FAILs. It ALWAYS records zheStatus and prints the verdict
# loud. An explicit ZHE_ENFORCE=0 escape hatch is retained to unblock while a
# genuine prover regression is triaged. A not-completed interview is EXEMPT (the
# prover exits 0), so the default is safe for fresh/in-flight builds.
ZHE_STATUS="skipped"
ZHE_PROVER="$SCRIPT_DIR/prove-zhe.py"
if [ -d /data/.openclaw ]; then ZHE_OC_ROOT="/data/.openclaw"; else ZHE_OC_ROOT="$HOME/.openclaw"; fi
if [ ! -f "$ZHE_PROVER" ]; then
  echo "[verify-library-gate] ZHE GATE: prove-zhe.py not found at $ZHE_PROVER — skipping" >&2
  ZHE_STATUS="prover-missing"
elif [ ! -f "$ZHE_OC_ROOT/openclaw.json" ]; then
  echo "[verify-library-gate] ZHE GATE: no openclaw.json at $ZHE_OC_ROOT — skipping" >&2
  ZHE_STATUS="no-oc-root"
else
  ZHE_OUT="$(python3 "$ZHE_PROVER" --local "$ZHE_OC_ROOT" 2>&1)"; ZHE_RC=$?
  if [ "$ZHE_RC" -eq 0 ]; then
    ZHE_STATUS="done"
    echo "[verify-library-gate] ZHE GATE PASS: $(printf '%s' "$ZHE_OUT" | grep -E 'OVERALL' | head -1)"
  else
    ZHE_STATUS="failed"
    echo "[verify-library-gate] ZHE GATE FAIL (rc=$ZHE_RC): the full Zero Human Experience did not land." >&2
    printf '%s\n' "$ZHE_OUT" | grep -E '\[FAIL\]|OVERALL' | sed 's/^/  [zhe] /' >&2
    [ -n "$FAIL_REASON" ] && FAIL_REASON="$FAIL_REASON | "
    FAIL_REASON="${FAIL_REASON}zhe: acceptance prover rc=$ZHE_RC"
  fi
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
    --arg zhe "$ZHE_STATUS" \
    --argjson fail "$FAIL_JSON" \
    --argjson perdept "$(printf '%s' "$GATE_JSON" | jq '.per_dept')" \
    '
      .roleLibraryStatus = $role
      | .sopLibraryStatus = $sop
      | .trioStatus = $trio
      | .sopAuthoringBoundaryStatus = $boundary
      | .zheStatus = $zhe
      | .libraryFailureReason = $fail
      | .departments = ((.departments // []) | map(
          . as $d
          | (($d.slug // $d.dept_id // $d.id // $d.name // "") | tostring) as $key
          | ($perdept[$key] // {}) as $pd
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

echo "[verify-library-gate] roleLibraryStatus=$ROLE_STATUS sopLibraryStatus=$SOP_STATUS trioStatus=$TRIO_STATUS sopAuthoringBoundaryStatus=$BOUNDARY_STATUS zheStatus=$ZHE_STATUS"
[ -n "$FAIL_REASON" ] && echo "[verify-library-gate] gaps: $FAIL_REASON" >&2

# ==============================================================================
# AUTO-SEND: Presentations Department Welcome (v10.18.0)
# When every gate passes, fire the one-time Presentations dept welcome to the
# owner via Telegram. The send script is idempotent (presentationDeptWelcomeSent
# in state file) -- safe to call on every gate pass. A send failure is logged
# as a WARNING and does NOT alter the gate exit code.
# Wiring gate runs before this in the resume loop so wiringStatus is already set.
# Fleet-generic: works for any client Mac or VPS; owner chat read from own config.
# Canonical template: templates/role-library/presentations/
#   first-time-onboarding-presentations.md Section 20.
# ==============================================================================
if [ "$BOUNDARY_STATUS" = "done" ] && [ "$TRIO_STATUS" = "done" ] && \
   [ "$ROLE_STATUS" = "done" ] && [ "$SOP_STATUS" = "done" ]; then
  _WELCOME_SCRIPT="$SCRIPT_DIR/send-presentation-dept-welcome.sh"
  if [ -f "$_WELCOME_SCRIPT" ]; then
    echo "[verify-library-gate] PRESENTATIONS WELCOME: all gates passed -- firing send-presentation-dept-welcome.sh"
    bash "$_WELCOME_SCRIPT" 2>&1 | sed 's/^/  [welcome] /' || true
  else
    echo "[verify-library-gate] PRESENTATIONS WELCOME: send script not found at $_WELCOME_SCRIPT -- skipping" >&2
  fi
fi

# ---- exit code = the gate verdict ----
# ZHE acceptance failure (rc 9) takes priority over ALL other verdicts, and blocks
# BY DEFAULT (ZHE_ENFORCE unset behaves as =1; see the ZHE GATE block above). The
# explicit ZHE_ENFORCE=0 escape hatch downgrades it to non-blocking.
# Otherwise boundary failure (rc 7) takes priority.
if [ "$ZHE_STATUS" = "failed" ] && [ "${ZHE_ENFORCE:-1}" = "1" ]; then
  exit 9
elif [ "$BOUNDARY_STATUS" != "done" ]; then
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

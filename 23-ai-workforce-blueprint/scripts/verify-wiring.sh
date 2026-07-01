#!/usr/bin/env bash
# verify-wiring.sh — v1.0.5 (WIRING GATE: materialized + registered[+runtime-dir] + reachable + connected)
# v1.0.5  2026-06-26  fix(Gap E): REGISTERED check now also asserts the per-dept RUNTIME
#                     agent dir $OC_ROOT/agents/dept-<slug>/ exists — the directory the
#                     gateway dispatcher keys task routing on. Verified on a live box
#                     (2026-06-26): state .id "coaching" -> runtime dir
#                     $HOME/.openclaw/agents/dept-coaching/ (holds sessions/); the dir
#                     name is the agent id "dept-<slug>". When that dir is ABSENT the
#                     dispatcher SILENTLY falls back to agent:main (the CEO), so a dept
#                     could pass openclaw.json registration yet have every task misroute
#                     to the CEO. The new sub-assertion FAILS LOUD (exit 3, registration
#                     category) so a dept can never pass wiring while still misrouting. It
#                     runs independent of openclaw.json presence (the dispatcher reads the
#                     dir, not the config, at routing time) and has a case-insensitive
#                     fallback for mixed-case slugs (e.g. AI-Workforce-Build-Office) on a
#                     case-sensitive filesystem.
# v1.0.4  2026-06-25  feat: connection-point resolver now (a) honors an optional
#                     "cfg_key_aliases" array on a hook — a required hook PASSES when the
#                     canonical cfg_key OR any alias resolves (mirrors the GHL upload tool
#                     ghl_media.py, which reads GOHIGHLEVEL_API_KEY then the legacy GHL_API_KEY,
#                     and GOHIGHLEVEL_LOCATION_ID then GHL_LOCATION_ID), so renaming the manifest
#                     to the canonical names never breaks a working upload that set the legacy
#                     alias; and (b) honors an optional "assert_contains_dept": true on a hook —
#                     after the hook's cfg_key resolves to a JSON file path, the resolved file
#                     must exist AND contain an entry for THIS dept's slug (Command Center
#                     departments.json board-entry assertion). The dept slug is passed to the
#                     python checker as a third arg.
# v1.0.3  2026-06-20  fix: materialization walker no longer mis-classifies a NAMED-SET
#                     `sops/` SOP-library container (graphics/presentations/quality-control/
#                     openclaw-maintenance) as an unmaterialized role. Such a `sops/` dir
#                     holds 40+ real SOP--*.md / SOP-DIU-*.md docs + a small [PENDING] stub
#                     how-to.md; the old walker returned rc=2 (`<dept>/sops:stub-NNNNB`),
#                     blocking ZHC closeout for every client with named-set SOP depts even
#                     though the SOP content is fully substantive (prove-floor PASSES). New
#                     is_sops_library_dir() recognizes and SKIPS the library container.
# v1.0.2  2026-06-15  fix: .departments[].slug -> .id (runtime state uses .id, not .slug);
#                     add guard: ALL_DEPTS empty when state HAS departments = HARD FAIL not
#                     a vacuous pass; fix state-write jq ($d.slug -> $d.id) so wiringStatus
#                     is actually written back to the correct department entry.
# v1.0.1  2026-06-15  fix: replace mapfile (bash 4+ only) with portable while-read loop so
#                     the script runs correctly when invoked from a zsh parent on Mac clients.
#
# HARD POST-INSTALL GATE for every department added to a live workforce.
#
# WHAT THIS ENFORCES:
#   A department is NOT done until ALL of the following are true for every
#   materialized role inside it:
#     (a) MATERIALIZED  — the role folder exists with a real how-to.md
#                          (>= 3KB, no [PENDING] marker, library-filled flag set)
#     (b) REGISTERED    — the department agent is present in openclaw.json
#                          agents.list AND its workspace path resolves on disk
#                          AND its RUNTIME agent dir $OC_ROOT/agents/dept-<slug>/
#                          exists (the dir the dispatcher keys routing on — when
#                          absent the gateway silently falls back to the CEO)
#     (c) REACHABLE     — the department has a Director-class entry point role
#                          (a folder whose slug contains "director", "head",
#                           "lead", or "architect" if no director exists)
#     (d) CONNECTION POINTS — each dept has a connection-manifest.json listing
#                          the external hooks it needs (e.g. Kie API path,
#                          GHL media hook, delivery destinations); every listed
#                          key that is marked "required" must resolve to a
#                          non-empty value in openclaw.json or the manifest
#                          itself.
#
# FAIL-LOUD CONTRACT:
#   Exits non-zero on ANY failure. Prints exactly which dept + role + assertion
#   failed. NEVER silently passes a stub. Writes wiringStatus per-dept to
#   .workforce-build-state.json (atomic).
#
# EXIT CODES:
#   0  — ALL depts pass (materialized + registered + reachable + connected)
#   2  — one or more roles NOT materialized (stub / empty how-to.md)
#   3  — one or more depts NOT registered (agent missing from openclaw.json,
#         workspace path missing on disk, or RUNTIME agent dir
#         $OC_ROOT/agents/dept-<slug>/ missing — would misroute to the CEO)
#   4  — one or more depts NOT reachable (no Director / head / lead entry point)
#   5  — one or more connection-point assertions FAILED
#   6  — mixed failures (multiple categories)
#   9  — fatal precondition (jq/python3 missing, no state file, no config)
#
# USAGE:
#   bash verify-wiring.sh                    # check all depts
#   bash verify-wiring.sh --all              # same as above
#   bash verify-wiring.sh --dept graphics    # check a single dept
#   bash verify-wiring.sh --dept graphics --dept presentations
#
# WIRING in the add/resume path:
#   - add-role.sh     — calls this at the end (single dept)
#   - resume-workforce-build.sh — calls this on all depts; fires [WIRING-RESUME]
#                        self-ping while any dept wiringStatus != done
#   - build-workforce.py — calls this before writing buildCompletedAt
#
# PRD: REPORT.md §PART 2 — enforce "department added = materialized + registered
#      + reachable + connection-points-verified; ONLY a passing wiring gate may
#      mark a dept done."
#
# v1.0.0  2026-06-14  Initial implementation; fleet-wide stub-dept fix.
# v1.0.1  2026-06-15  fix/gate-scripts-bash-portability: replace mapfile with while-read.
# v1.0.2  2026-06-15  fix/gate-and-resume-correctness: .id field fix + ALL_DEPTS empty guard.
# v1.0.3  2026-06-20  fix/named-set-sops-library-walker: skip `sops/` SOP-library containers.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---- Platform detection -------------------------------------------------------
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[verify-wiring] FATAL: no OpenClaw root at /data/.openclaw or \$HOME/.openclaw" >&2
  exit 9
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
OPENCLAW_CFG="$OC_ROOT/openclaw.json"

# B3: default — missing config is a HARD FAIL (not advisory)
ALLOW_MISSING_CONFIG="${ALLOW_MISSING_CONFIG:-0}"

# ---- Args --------------------------------------------------------------------
FILTER_DEPTS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dept)   FILTER_DEPTS+=("${2:-}"); shift 2 ;;
    --all)    shift ;;
    --allow-missing-config) ALLOW_MISSING_CONFIG=1; shift ;;
    -h|--help)
      sed -n '2,50p' "$0"
      exit 0
      ;;
    *)
      echo "[verify-wiring] WARN: unknown arg '$1' (ignored)" >&2
      shift
      ;;
  esac
done

# ---- Preconditions -----------------------------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  echo "[verify-wiring] FATAL: jq not installed" >&2; exit 9
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[verify-wiring] FATAL: python3 not installed" >&2; exit 9
fi
if [[ ! -f "$STATE_FILE" ]]; then
  echo "[verify-wiring] FATAL: no state file at $STATE_FILE" >&2; exit 9
fi
if [[ ! -f "$OPENCLAW_CFG" ]]; then
  echo "[verify-wiring] WARN: openclaw.json not found at $OPENCLAW_CFG — registration checks will be advisory" >&2
fi

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# ---- Resolve workspace root --------------------------------------------------
# departments live under workspace/departments/<slug>/
WORKSPACE_ROOT=$(jq -r '.workspaceRoot // empty' "$STATE_FILE" 2>/dev/null || true)
if [[ -z "$WORKSPACE_ROOT" || "$WORKSPACE_ROOT" == "null" ]]; then
  # Fallback: derive from state file location (state is in workspace/)
  WORKSPACE_ROOT="$(dirname "$STATE_FILE")"
fi
DEPTS_DIR="$WORKSPACE_ROOT/departments"

# ---- Collect dept list from state --------------------------------------------
# Portable replacement for `mapfile -t ALL_DEPTS < <(...)` (mapfile is bash 4+ only;
# Mac ships bash 3.2 and callers may be zsh-parented). while-read works in bash 3.2+.
#
# BUG FIX (v1.0.2): runtime .workforce-build-state.json stores departments with field
# "id" not "slug" (the schema name). Using .slug produced an always-empty ALL_DEPTS,
# causing the gate to WARN and exit 0 vacuously — a false pass.  Use .id instead.
ALL_DEPTS=()
while IFS= read -r _dept_line; do
  [[ -n "$_dept_line" ]] && ALL_DEPTS+=("$_dept_line")
done < <(jq -r '.departments[]?.id // empty' "$STATE_FILE" 2>/dev/null || true)

if [[ ${#ALL_DEPTS[@]} -eq 0 ]]; then
  # Guard: if the state file has a non-empty departments array but we got no IDs,
  # that is a BUG (wrong field name or unreadable state) — hard-fail, not a vacuous pass.
  _raw_dept_count=$(jq -r '(.departments // []) | length' "$STATE_FILE" 2>/dev/null || echo 0)
  if (( _raw_dept_count > 0 )); then
    echo "[verify-wiring] FATAL: state file has ${_raw_dept_count} department(s) but .id was empty for all of them — schema mismatch or corrupted state. Aborting to prevent a vacuous false pass." >&2
    exit 9
  fi
  echo "[verify-wiring] WARN: no departments found in state file — nothing to check" >&2
  exit 0
fi

# Apply filter if --dept provided
DEPTS_TO_CHECK=()
if [[ ${#FILTER_DEPTS[@]} -gt 0 ]]; then
  for wanted in "${FILTER_DEPTS[@]}"; do
    for d in "${ALL_DEPTS[@]}"; do
      [[ "$d" == "$wanted" ]] && DEPTS_TO_CHECK+=("$d")
    done
  done
  if [[ ${#DEPTS_TO_CHECK[@]} -eq 0 ]]; then
    echo "[verify-wiring] FATAL: none of the requested depts found in state: ${FILTER_DEPTS[*]}" >&2
    exit 9
  fi
else
  DEPTS_TO_CHECK=("${ALL_DEPTS[@]}")
fi

echo "[verify-wiring] Checking ${#DEPTS_TO_CHECK[@]} dept(s): ${DEPTS_TO_CHECK[*]}"
echo "[verify-wiring] Workspace: $WORKSPACE_ROOT"
echo ""

# ---- Constants ---------------------------------------------------------------
HOW_TO_MIN_BYTES=3072        # 3 KB minimum for a non-stub how-to.md
PENDING_MARKER="[PENDING"    # substring that signals an unfilled stub
DIRECTOR_SLUGS=("director" "head" "lead" "architect" "chief")

# ---- Named-set SOP-library detection -----------------------------------------
# v1.0.3 (2026-06-20): NAMED-SET SOP-library departments (graphics, presentations,
# quality-control, openclaw-maintenance) keep their SOP LIBRARY in a `sops/`
# subdirectory holding 40+ real SOP--*.md / SOP-DIU-*.md (and *-sops.md) files plus,
# at most, a small `[PENDING — FILL FROM LIBRARY]` stub how-to.md. The materialization
# walker below iterates EVERY dept subdir as a "role" and fails any whose how-to.md is
# < 3072B. That mis-classified the `sops/` LIBRARY container as an unmaterialized role
# and returned rc=2 (e.g. `graphics/sops:stub-2015B`), blocking ZHC closeout for every
# client with named-set SOP depts — even though the SOP content is fully substantive
# (prove-floor PASSES). This helper recognizes a `sops/` container so it is SKIPPED by
# the role-count / how-to-size check. It is NOT a role and was never meant to be one.
#
# A directory qualifies as a SOP-library container (NOT a role) when BOTH hold:
#   1. its basename is exactly "sops" (case-insensitive), AND
#   2. it contains >= 1 real SOP-library doc — a *.md file whose name (case-insensitive)
#      starts with "SOP-" (covers SOP--*, SOP-DIU-*, SOP-PITCH-*, SOP-IMG-*, sop-*)
#      OR ends with "-sops.md" (the role-suffixed library docs).
# This is deliberately tight: it never skips a real role folder (real roles are never
# named "sops"), and it never skips an empty `sops/` shell (which has no SOP docs).
is_sops_library_dir() {
  local _d="$1"
  local _base
  _base="$(basename "$_d")"
  # case-insensitive exact match on the folder name "sops"
  case "$(printf '%s' "$_base" | tr '[:upper:]' '[:lower:]')" in
    sops) : ;;
    *) return 1 ;;
  esac
  # must contain at least one real SOP-library doc to count as a library
  local _f _fn _fnl
  for _f in "$_d"/*.md; do
    [[ -e "$_f" ]] || continue
    _fn="$(basename "$_f")"
    _fnl="$(printf '%s' "$_fn" | tr '[:upper:]' '[:lower:]')"
    if [[ "$_fnl" == sop-* || "$_fnl" == *-sops.md ]]; then
      return 0
    fi
  done
  return 1
}

# ---- Aggregate failure tracking ----------------------------------------------
FAIL_MATERIALIZED=()
FAIL_REGISTERED=()
FAIL_REACHABLE=()
FAIL_CONNECTION=()

# ---- Per-dept results (JSON) for state update ---------------------------------
DEPT_RESULTS_JSON="{}"

# ==============================================================================
# MAIN LOOP — iterate over departments
# ==============================================================================
for DEPT_SLUG in "${DEPTS_TO_CHECK[@]}"; do

  DEPT_DIR="$DEPTS_DIR/$DEPT_SLUG"
  DEPT_FAIL=0
  DEPT_WIRING_FAIL_REASONS=()

  echo "--- dept: $DEPT_SLUG ---"

  # --------------------------------------------------------------------------
  # (a) MATERIALIZATION CHECK
  # Every role folder under the dept must have a real how-to.md.
  # "Real" = exists + >= HOW_TO_MIN_BYTES + no [PENDING] marker.
  # --------------------------------------------------------------------------
  MAT_PASS=1
  MAT_GAPS=()

  if [[ ! -d "$DEPT_DIR" ]]; then
    echo "  [MATERIALIZED] FAIL: dept dir does not exist at $DEPT_DIR" >&2
    MAT_PASS=0
    MAT_GAPS+=("dept dir missing")
    FAIL_MATERIALIZED+=("$DEPT_SLUG:dept-dir-missing")
  else
    # Count role folders (numeric-prefix dirs like 01-director-of-x or 14-brainstorming-buddy)
    ROLE_DIRS=()
    while IFS= read -r -d '' rd; do
      ROLE_DIRS+=("$rd")
    done < <(find "$DEPT_DIR" -maxdepth 1 -mindepth 1 -type d -print0 2>/dev/null | sort -z)

    ROLE_COUNT=${#ROLE_DIRS[@]}
    echo "  [MATERIALIZED] dept dir exists. Role dirs found: $ROLE_COUNT"

    for ROLE_DIR in "${ROLE_DIRS[@]}"; do
      ROLE_SLUG="$(basename "$ROLE_DIR")"
      # skip hidden/meta dirs
      [[ "$ROLE_SLUG" == .* ]] && continue
      # v1.0.3: a NAMED-SET `sops/` SOP-library container is NOT a role. Skip it so
      # its (legitimately small / [PENDING]) stub how-to.md never trips the role
      # materialization gate. The SOP content lives in the SOP--*.md / SOP-DIU-*.md
      # files inside it, which prove-floor verifies separately.
      if is_sops_library_dir "$ROLE_DIR"; then
        _sop_lib_count=$(find "$ROLE_DIR" -maxdepth 1 -name '*.md' -type f 2>/dev/null | wc -l | tr -d ' ')
        echo "  [MATERIALIZED] SKIP: $ROLE_SLUG — named-set SOP-library container (${_sop_lib_count} SOP docs), not a role"
        continue
      fi
      HOW_TO="$ROLE_DIR/how-to.md"
      if [[ ! -f "$HOW_TO" ]]; then
        echo "  [MATERIALIZED] FAIL: $ROLE_SLUG — how-to.md missing" >&2
        MAT_PASS=0
        MAT_GAPS+=("$ROLE_SLUG:no-how-to-md")
        FAIL_MATERIALIZED+=("$DEPT_SLUG/$ROLE_SLUG:no-how-to-md")
        continue
      fi
      FILE_SIZE=$(wc -c < "$HOW_TO" 2>/dev/null || echo 0)
      if (( FILE_SIZE < HOW_TO_MIN_BYTES )); then
        echo "  [MATERIALIZED] FAIL: $ROLE_SLUG — how-to.md too small (${FILE_SIZE}B < ${HOW_TO_MIN_BYTES}B stub threshold)" >&2
        MAT_PASS=0
        MAT_GAPS+=("$ROLE_SLUG:stub-${FILE_SIZE}B")
        FAIL_MATERIALIZED+=("$DEPT_SLUG/$ROLE_SLUG:stub-${FILE_SIZE}B")
        continue
      fi
      if grep -q "$PENDING_MARKER" "$HOW_TO" 2>/dev/null; then
        echo "  [MATERIALIZED] FAIL: $ROLE_SLUG — how-to.md contains $PENDING_MARKER placeholder" >&2
        MAT_PASS=0
        MAT_GAPS+=("$ROLE_SLUG:pending-placeholder")
        FAIL_MATERIALIZED+=("$DEPT_SLUG/$ROLE_SLUG:pending-placeholder")
        continue
      fi
      echo "  [MATERIALIZED] OK:   $ROLE_SLUG (${FILE_SIZE}B)"
    done

    if [[ $ROLE_COUNT -eq 0 ]]; then
      echo "  [MATERIALIZED] FAIL: zero role dirs in $DEPT_DIR" >&2
      MAT_PASS=0
      MAT_GAPS+=("no-role-dirs")
      FAIL_MATERIALIZED+=("$DEPT_SLUG:no-role-dirs")
    fi
  fi

  [[ $MAT_PASS -eq 0 ]] && DEPT_FAIL=1 && DEPT_WIRING_FAIL_REASONS+=("materialized:${MAT_GAPS[*]}")

  # --------------------------------------------------------------------------
  # (b) REGISTRATION CHECK
  # The dept's agent must appear in openclaw.json agents.list AND the
  # registered workspace path must resolve to a real directory on disk.
  # --------------------------------------------------------------------------
  REG_PASS=1
  REG_GAPS=()

  if [[ -f "$OPENCLAW_CFG" ]]; then
    AGENT_IDS_IN_CFG=$(jq -r '.agents.list[]?.id // empty' "$OPENCLAW_CFG" 2>/dev/null || true)
    # The dept agent id is typically "dept-<slug>"
    EXPECTED_AGENT_ID="dept-${DEPT_SLUG}"
    if echo "$AGENT_IDS_IN_CFG" | grep -qx "$EXPECTED_AGENT_ID"; then
      # Also verify workspace path resolves
      REG_WORKSPACE=$(jq -r --arg aid "$EXPECTED_AGENT_ID" \
        '.agents.list[] | select(.id==$aid) | .workspace // empty' \
        "$OPENCLAW_CFG" 2>/dev/null || true)
      if [[ -n "$REG_WORKSPACE" && "$REG_WORKSPACE" != "null" ]]; then
        if [[ -d "$REG_WORKSPACE" ]]; then
          echo "  [REGISTERED]   OK:   agent $EXPECTED_AGENT_ID → workspace $REG_WORKSPACE"
        else
          echo "  [REGISTERED]   FAIL: agent $EXPECTED_AGENT_ID registered but workspace path does not exist: $REG_WORKSPACE" >&2
          REG_PASS=0
          REG_GAPS+=("workspace-path-missing:$REG_WORKSPACE")
          FAIL_REGISTERED+=("$DEPT_SLUG:workspace-path-missing")
        fi
      else
        echo "  [REGISTERED]   FAIL: agent $EXPECTED_AGENT_ID registered but has no workspace path" >&2
        REG_PASS=0
        REG_GAPS+=("no-workspace-path")
        FAIL_REGISTERED+=("$DEPT_SLUG:no-workspace-path")
      fi
    else
      echo "  [REGISTERED]   FAIL: agent '$EXPECTED_AGENT_ID' not found in openclaw.json agents.list" >&2
      REG_PASS=0
      REG_GAPS+=("agent-not-in-config")
      FAIL_REGISTERED+=("$DEPT_SLUG:agent-not-in-config")
    fi
  else
    # B3: Missing config is a HARD FAIL by default (unless --allow-missing-config)
    if [[ "${ALLOW_MISSING_CONFIG:-0}" == "1" ]]; then
      echo "  [REGISTERED]   SKIP: openclaw.json not found (--allow-missing-config set)" >&2
    else
      echo "  [REGISTERED]   FAIL: openclaw.json not found at $OPENCLAW_CFG — registration cannot be verified (HARD FAIL). Pass --allow-missing-config to skip in config-less contexts." >&2
      REG_PASS=0
      REG_GAPS+=("openclaw-json-missing")
      FAIL_REGISTERED+=("$DEPT_SLUG:openclaw-json-missing")
      DEPT_FAIL=1
    fi
  fi

  # --------------------------------------------------------------------------
  # (b2) RUNTIME-DIR CHECK (Gap E) — part of REGISTERED
  # The gateway dispatcher keys per-task routing on the RUNTIME agent dir
  #   $OC_ROOT/agents/<agent-id>/   where <agent-id> == dept-<slug>
  # (verified on a live box 2026-06-26: state .id "coaching" ->
  #  $HOME/.openclaw/agents/dept-coaching/, which holds sessions/). If that dir
  # is ABSENT the dispatcher SILENTLY falls back to agent:main (the CEO): the
  # dept passes openclaw.json registration + workspace-path checks yet every
  # task routed to it lands on the CEO. This assertion makes that impossible —
  # a missing runtime dir is a REGISTERED failure (exit 3). It runs regardless
  # of openclaw.json presence because the dispatcher reads the dir, not the
  # config, at routing time. A case-insensitive fallback covers mixed-case
  # slugs (e.g. AI-Workforce-Build-Office) on a case-sensitive filesystem.
  RUNTIME_AGENT_ID="dept-${DEPT_SLUG}"
  RUNTIME_DIR="$OC_ROOT/agents/$RUNTIME_AGENT_ID"
  if [[ -d "$RUNTIME_DIR" ]]; then
    echo "  [RUNTIME-DIR]  OK:   $RUNTIME_DIR exists (dispatcher entry point)"
  else
    RUNTIME_DIR_CI=""
    if [[ -d "$OC_ROOT/agents" ]]; then
      _want_lc="$(printf '%s' "$RUNTIME_AGENT_ID" | tr '[:upper:]' '[:lower:]')"
      while IFS= read -r _cand; do
        [[ -d "$_cand" ]] || continue
        if [[ "$(printf '%s' "$(basename "$_cand")" | tr '[:upper:]' '[:lower:]')" == "$_want_lc" ]]; then
          RUNTIME_DIR_CI="$_cand"; break
        fi
      done < <(find "$OC_ROOT/agents" -maxdepth 1 -mindepth 1 -type d 2>/dev/null)
    fi
    if [[ -n "$RUNTIME_DIR_CI" ]]; then
      echo "  [RUNTIME-DIR]  OK:   $RUNTIME_DIR_CI exists (case-insensitive match for $RUNTIME_AGENT_ID)"
    else
      echo "  [RUNTIME-DIR]  FAIL: no runtime agent dir at $RUNTIME_DIR — the gateway dispatcher will SILENTLY fall back to agent:main (the CEO) for every task routed to '$DEPT_SLUG'. This dept is NOT wired." >&2
      echo "                       FIX: re-run build-workforce.py (or add-role.sh) so the agent registers and its runtime dir materializes, then re-check." >&2
      REG_PASS=0
      REG_GAPS+=("runtime-agent-dir-missing:$RUNTIME_DIR")
      FAIL_REGISTERED+=("$DEPT_SLUG:runtime-agent-dir-missing")
    fi
  fi

  [[ $REG_PASS -eq 0 ]] && DEPT_FAIL=1 && DEPT_WIRING_FAIL_REASONS+=("registered:${REG_GAPS[*]}")

  # --------------------------------------------------------------------------
  # (c) REACHABILITY CHECK
  # The dept must have at least one Director/Head/Lead/Architect role — the
  # entry-point role that the orchestrator dispatches tasks to first.
  # --------------------------------------------------------------------------
  REACH_PASS=0
  REACH_ENTRY=""

  if [[ -d "$DEPT_DIR" ]]; then
    for rd in "$DEPT_DIR"/*/; do
      [[ -d "$rd" ]] || continue
      rslug="$(basename "$rd")"
      [[ "$rslug" == .* ]] && continue
      for entry_kw in "${DIRECTOR_SLUGS[@]}"; do
        if [[ "$rslug" == *"$entry_kw"* ]]; then
          REACH_PASS=1
          REACH_ENTRY="$rslug"
          break 2
        fi
      done
    done
    if [[ $REACH_PASS -eq 1 ]]; then
      echo "  [REACHABLE]    OK:   entry point role = $REACH_ENTRY"
    else
      echo "  [REACHABLE]    FAIL: no Director/Head/Lead/Architect role found in $DEPT_DIR" >&2
      echo "                       The orchestrator has no entry point into this department." >&2
      FAIL_REACHABLE+=("$DEPT_SLUG:no-entry-point-role")
      DEPT_FAIL=1
      DEPT_WIRING_FAIL_REASONS+=("reachable:no-entry-point-role")
    fi
  else
    echo "  [REACHABLE]    SKIP: dept dir missing (already failed materialization)" >&2
  fi

  # --------------------------------------------------------------------------
  # (d) CONNECTION POINTS CHECK
  # Look for connection-manifest.json in the dept's template source directory
  # (templates/role-library/<dept>/connection-manifest.json).
  # If present, assert every required key resolves to a non-empty string in
  # openclaw.json or in the manifest itself (env var expansion supported).
  # If absent, the dept is advisory-only (not all depts have external hooks).
  # --------------------------------------------------------------------------
  CONN_PASS=1
  CONN_GAPS=()
  MANIFEST_DIR="$SKILL_DIR/templates/role-library/$DEPT_SLUG"
  MANIFEST_FILE="$MANIFEST_DIR/connection-manifest.json"

  if [[ -f "$MANIFEST_FILE" ]]; then
    echo "  [CONNECTION]   manifest found: $MANIFEST_FILE"
    # Python does the heavy lifting: parse manifest, check each required hook
    CONN_RESULT=$(python3 - "$MANIFEST_FILE" "$OPENCLAW_CFG" "$DEPT_SLUG" <<'PYEOF' 2>&1
import json, os, sys
from pathlib import Path

manifest_path = sys.argv[1]
cfg_path = sys.argv[2] if len(sys.argv) > 2 else ""
dept_slug = sys.argv[3] if len(sys.argv) > 3 else ""

try:
    manifest = json.loads(Path(manifest_path).read_text())
except Exception as e:
    print(json.dumps({"error": str(e), "gaps": [], "pass": False}))
    sys.exit(0)

# Load openclaw.json for key lookups
cfg = {}
if cfg_path and Path(cfg_path).exists():
    try:
        cfg = json.loads(Path(cfg_path).read_text())
    except Exception:
        pass

def resolve_value(key_path: str) -> str:
    """Resolve a dot-path against cfg, or as an env var, or return ''."""
    # Try env var first
    env_val = os.environ.get(key_path.replace(".", "_").upper(), "")
    if env_val:
        return env_val
    # Try dot-path in cfg
    parts = key_path.split(".")
    node = cfg
    for p in parts:
        if isinstance(node, dict) and p in node:
            node = node[p]
        else:
            node = None
            break
    if isinstance(node, str) and node.strip():
        return node
    if isinstance(node, (int, float, bool)):
        return str(node)
    return ""

def resolve_any(keys) -> tuple:
    """Resolve the first non-empty value across an ordered list of dot-path keys.
    Returns (value, key_that_resolved) or ('', '')."""
    for k in keys:
        if not k:
            continue
        v = resolve_value(k)
        if v:
            return v, k
    return "", ""

def dept_in_departments_json(path: str, slug: str) -> bool:
    """True iff the JSON file at `path` exists and carries an entry for this dept slug.
    Tolerant of common shapes: a top-level list, or a dict with a 'departments' list,
    where each entry is either a string slug or an object with id/slug/name/dept."""
    try:
        data = json.loads(Path(os.path.expanduser(path)).read_text())
    except Exception:
        return False
    want = (slug or "").strip().lower()
    if not want:
        return False
    entries = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        for container_key in ("departments", "depts", "items", "list"):
            if isinstance(data.get(container_key), list):
                entries = data[container_key]
                break
        else:
            # dict keyed by slug
            if want in {str(k).strip().lower() for k in data.keys()}:
                return True
    for e in entries:
        if isinstance(e, str) and e.strip().lower() == want:
            return True
        if isinstance(e, dict):
            for field in ("id", "slug", "name", "dept", "key"):
                val = e.get(field)
                if isinstance(val, str) and val.strip().lower() == want:
                    return True
    return False

hooks = manifest.get("connection_points", [])
gaps = []
all_pass = True

for hook in hooks:
    name = hook.get("name", "unnamed")
    required = hook.get("required", False)
    cfg_key = hook.get("cfg_key", "")
    aliases = hook.get("cfg_key_aliases", []) or []
    assert_contains_dept = hook.get("assert_contains_dept", False)
    description = hook.get("description", "")

    if not required:
        continue  # optional hooks are advisory

    # Canonical key first, then any aliases (mirrors the upload tool's read order).
    resolved, resolved_key = resolve_any([cfg_key] + list(aliases))

    if not resolved:
        all_pass = False
        keylist = "/".join([k for k in [cfg_key] + list(aliases) if k]) or "no-cfg-key"
        gaps.append(f"{name}:{keylist}")
        print(f"  connection FAIL: {name} — {description} (keys tried: {keylist}) not resolved", file=sys.stderr)
        continue

    via = "" if resolved_key == cfg_key else f" via alias {resolved_key}"
    print(f"  connection OK:   {name} ({cfg_key}{via}) = resolved")

    # Optional: the resolved value is a path to a departments.json that must list this dept.
    if assert_contains_dept:
        if dept_in_departments_json(resolved, dept_slug):
            print(f"  connection OK:   {name} — dept '{dept_slug}' present in {resolved}")
        else:
            all_pass = False
            gaps.append(f"{name}:dept-not-in-departments-json")
            print(f"  connection FAIL: {name} — dept '{dept_slug}' is NOT seeded in the Command Center departments.json at {resolved!r} (file missing or no matching entry). Seed an entry for '{dept_slug}' so the client can monitor this dept from the dashboard.", file=sys.stderr)

print(json.dumps({"pass": all_pass, "gaps": gaps}))
PYEOF
    )
    CONN_JSON="$(printf '%s\n' "$CONN_RESULT" | grep '^{' | tail -1)"
    CONN_TEXT="$(printf '%s\n' "$CONN_RESULT" | grep -v '^{')"
    printf '%s\n' "$CONN_TEXT" | sed 's/^/  /'
    if [[ -n "$CONN_JSON" ]]; then
      CONN_PASS=$(printf '%s' "$CONN_JSON" | jq -r '.pass // true' 2>/dev/null || echo true)
      CONN_GAP_LIST=$(printf '%s' "$CONN_JSON" | jq -r '(.gaps // []) | join(", ")' 2>/dev/null || echo "")
      if [[ "$CONN_PASS" == "false" ]]; then
        echo "  [CONNECTION]   FAIL: missing required hooks: $CONN_GAP_LIST" >&2
        CONN_GAPS+=("$CONN_GAP_LIST")
        FAIL_CONNECTION+=("$DEPT_SLUG:$CONN_GAP_LIST")
        DEPT_FAIL=1
        DEPT_WIRING_FAIL_REASONS+=("connection:$CONN_GAP_LIST")
      else
        echo "  [CONNECTION]   OK:   all required hooks resolved"
      fi
    fi
  else
    echo "  [CONNECTION]   OK:   no connection-manifest.json for $DEPT_SLUG (no required external hooks defined)"
  fi

  # --------------------------------------------------------------------------
  # (e) PRESENTATIONS-SPECIFIC WIRING ASSERTIONS
  # For the presentations dept, assert the front-door guard is in place:
  #   1. deck-build-guard.sh is present AND executable in the dept scripts dir.
  #   2. run_signature_deck.py + build_deck.py each contain the front-door
  #      marker guard (grep for OC_DECK_CANONICAL_ENTRY).
  # Fail the dept check if any assertion is missing (fail-closed, not advisory).
  # --------------------------------------------------------------------------
  if [[ "$DEPT_SLUG" == "presentations" ]]; then
    PRES_SCRIPTS_TEMPLATE="$SKILL_DIR/templates/role-library/presentations/scripts"
    PRES_SCRIPTS_DEPLOYED="$HOME/departments/Presentations/scripts"
    # Prefer the deployed location; fall back to the template source (repo context).
    if [[ -d "$PRES_SCRIPTS_DEPLOYED" ]]; then
      _PRES_SCRIPTS="$PRES_SCRIPTS_DEPLOYED"
    elif [[ -d "$PRES_SCRIPTS_TEMPLATE" ]]; then
      _PRES_SCRIPTS="$PRES_SCRIPTS_TEMPLATE"
    else
      _PRES_SCRIPTS=""
    fi
    _CANONICAL_ENTRY="$SCRIPT_DIR/deck-build-guard.sh"
    PRES_FAIL=0

    echo "  [PRESENTATIONS]  front-door wiring assertions:"

    # (e1) deck-build-guard.sh present and executable
    if [[ -f "$_CANONICAL_ENTRY" && -x "$_CANONICAL_ENTRY" ]]; then
      echo "  [PRESENTATIONS]  OK:   deck-build-guard.sh present and executable at $_CANONICAL_ENTRY"
    elif [[ -f "$_CANONICAL_ENTRY" ]]; then
      echo "  [PRESENTATIONS]  FAIL: deck-build-guard.sh found at $_CANONICAL_ENTRY but is NOT executable (chmod +x required)" >&2
      PRES_FAIL=1
      FAIL_CONNECTION+=("$DEPT_SLUG:deck-build-guard-not-executable")
      DEPT_WIRING_FAIL_REASONS+=("presentations:deck-build-guard-not-executable")
    else
      # Also check in the presentations scripts dir (deployed or template)
      _GUARD_ALT=""
      [[ -n "$_PRES_SCRIPTS" ]] && _GUARD_ALT="$_PRES_SCRIPTS/deck-build-guard.sh"
      if [[ -n "$_GUARD_ALT" && -f "$_GUARD_ALT" && -x "$_GUARD_ALT" ]]; then
        echo "  [PRESENTATIONS]  OK:   deck-build-guard.sh present and executable at $_GUARD_ALT"
      else
        echo "  [PRESENTATIONS]  FAIL: deck-build-guard.sh not found (checked $_CANONICAL_ENTRY and ${_GUARD_ALT:-<pres scripts not found>}). The front-door exec guard is missing — direct build_deck.py invocations are not blocked." >&2
        PRES_FAIL=1
        FAIL_CONNECTION+=("$DEPT_SLUG:deck-build-guard-missing")
        DEPT_WIRING_FAIL_REASONS+=("presentations:deck-build-guard-missing")
      fi
    fi

    # (e2) run_signature_deck.py and build_deck.py contain OC_DECK_CANONICAL_ENTRY
    if [[ -n "$_PRES_SCRIPTS" ]]; then
      for _runner_file in "run_signature_deck.py" "build_deck.py"; do
        _runner_path="$_PRES_SCRIPTS/$_runner_file"
        if [[ ! -f "$_runner_path" ]]; then
          echo "  [PRESENTATIONS]  WARN: $_runner_file not found at $_runner_path (skipping marker check)" >&2
        elif grep -q "OC_DECK_CANONICAL_ENTRY" "$_runner_path" 2>/dev/null; then
          echo "  [PRESENTATIONS]  OK:   $_runner_file contains OC_DECK_CANONICAL_ENTRY front-door marker guard"
        else
          echo "  [PRESENTATIONS]  FAIL: $_runner_file does NOT contain OC_DECK_CANONICAL_ENTRY — direct python3 invocations will not be blocked by the front-door marker guard." >&2
          PRES_FAIL=1
          FAIL_CONNECTION+=("$DEPT_SLUG:${_runner_file}-missing-marker-guard")
          DEPT_WIRING_FAIL_REASONS+=("presentations:${_runner_file}-missing-OC_DECK_CANONICAL_ENTRY")
        fi
      done
    else
      echo "  [PRESENTATIONS]  WARN: presentations scripts dir not found (checked $PRES_SCRIPTS_DEPLOYED and $PRES_SCRIPTS_TEMPLATE) — skipping OC_DECK_CANONICAL_ENTRY marker checks" >&2
    fi

    # (e3) PROCESS-INTEGRITY lockstep suite scripts present
    # The 2026-06-29 PROCESS-INTEGRITY core ships these runner-side scripts that
    # must be present alongside build_deck.py to enable prove-deck + cc_board wiring.
    if [[ -n "$_PRES_SCRIPTS" ]]; then
      for _pi_file in "prove-deck.py" "cc_board.py" "phase_verifiers.py" \
                      "runner_gate_integrity_check.py"; do
        _pi_path="$_PRES_SCRIPTS/$_pi_file"
        if [[ -f "$_pi_path" ]]; then
          echo "  [PRESENTATIONS]  OK:   process-integrity script present: $_pi_file"
        else
          echo "  [PRESENTATIONS]  FAIL: process-integrity script MISSING: $_pi_file (expected at $_pi_path). PROCESS-INTEGRITY enforcement is incomplete." >&2
          PRES_FAIL=1
          FAIL_CONNECTION+=("$DEPT_SLUG:process-integrity-${_pi_file}-missing")
          DEPT_WIRING_FAIL_REASONS+=("presentations:process-integrity-${_pi_file}-missing")
        fi
      done
    else
      echo "  [PRESENTATIONS]  WARN: presentations scripts dir not found — skipping process-integrity script checks" >&2
    fi

    # (e4) SKILL-48 canonical GHL-media dependency (the presentations media path SHARES it).
    # templates/role-library/presentations/scripts/ghl_media.py RE-EXPORTS
    # 48-facebook-ad-generator/tools/ghl_media.py (the single, verified-working source of the
    # GHL media folder-create + upload REST calls) and raises FileNotFoundError at import time
    # if the sibling skill is absent. Surface that dependency HERE, at wiring/QC time, so a
    # missing Skill 48 is caught before a live deck upload instead of mid-deck. Advisory
    # (does not fail the dept): the dept can be scaffolded without the sibling, but media
    # upload cannot run until Skill 48 is installed.
    _GHL_CANON_FOUND=""
    _anc="$SKILL_DIR"
    while [[ -n "$_anc" && "$_anc" != "/" ]]; do
      _anc="$(dirname "$_anc")"
      if [[ -f "$_anc/48-facebook-ad-generator/tools/ghl_media.py" ]]; then
        _GHL_CANON_FOUND="$_anc/48-facebook-ad-generator/tools/ghl_media.py"
        break
      fi
    done
    if [[ -n "$_GHL_CANON_FOUND" ]]; then
      echo "  [PRESENTATIONS]  OK:   Skill-48 canonical ghl_media.py present ($_GHL_CANON_FOUND) — presentations media re-export will resolve"
    else
      echo "  [PRESENTATIONS]  WARN: Skill-48 canonical module 48-facebook-ad-generator/tools/ghl_media.py NOT found in any ancestor of $SKILL_DIR. The presentations media tool (templates/role-library/presentations/scripts/ghl_media.py) RE-EXPORTS it and will raise FileNotFoundError at import — GHL media upload (slide PNGs + deck) will fail mid-deck. Install Skill 48 (48-facebook-ad-generator) before running a Presentations media/delivery job." >&2
    fi

    if [[ $PRES_FAIL -eq 1 ]]; then
      DEPT_FAIL=1
    fi
  fi

  # --------------------------------------------------------------------------
  # Update per-dept wiringStatus in state file
  # --------------------------------------------------------------------------
  DEPT_WIRING_STATUS="done"
  if [[ $DEPT_FAIL -eq 1 ]]; then
    DEPT_WIRING_STATUS="failed"
    FAIL_DETAIL="${DEPT_WIRING_FAIL_REASONS[*]}"
    echo ""
    echo "  [WIRING] RESULT: FAIL for dept '$DEPT_SLUG' — $FAIL_DETAIL"
  else
    echo ""
    echo "  [WIRING] RESULT: PASS for dept '$DEPT_SLUG'"
  fi

  # Accumulate JSON for state write
  TS_NOW="$(now_iso)"
  DEPT_RESULTS_JSON=$(python3 - "$DEPT_RESULTS_JSON" "$DEPT_SLUG" "$DEPT_WIRING_STATUS" "$TS_NOW" \
    "${DEPT_WIRING_FAIL_REASONS[*]:-}" <<'PYEOF'
import json, sys
acc = json.loads(sys.argv[1])
dept = sys.argv[2]
status = sys.argv[3]
ts = sys.argv[4]
reasons = sys.argv[5] if len(sys.argv) > 5 else ""
acc[dept] = {"wiringStatus": status, "wiringCheckedAt": ts, "wiringFailReasons": reasons}
print(json.dumps(acc))
PYEOF
  )

  echo ""
done

# ==============================================================================
# Write wiringStatus per-dept into build-state.json (atomic)
# ==============================================================================
if [[ -f "$STATE_FILE" ]]; then
  TMP_STATE="$(mktemp)"
  jq \
    --argjson perdept "$DEPT_RESULTS_JSON" \
    '
      .departments = ((.departments // []) | map(
        . as $d
        | ($perdept[$d.id] // {}) as $pd
        | $d
        + (if ($pd | has("wiringStatus"))    then {wiringStatus: $pd.wiringStatus}       else {} end)
        + (if ($pd | has("wiringCheckedAt")) then {wiringCheckedAt: $pd.wiringCheckedAt} else {} end)
        + (if ($pd | has("wiringFailReasons")) then {wiringFailReasons: $pd.wiringFailReasons} else {} end)
      ))
    ' "$STATE_FILE" > "$TMP_STATE" 2>/dev/null && mv "$TMP_STATE" "$STATE_FILE" \
    || { rm -f "$TMP_STATE"; echo "[verify-wiring] WARN: could not update state file (reporting only)" >&2; }
fi

# ==============================================================================
# Final verdict
# ==============================================================================
HAS_MAT=$(( ${#FAIL_MATERIALIZED[@]} > 0 ))
HAS_REG=$(( ${#FAIL_REGISTERED[@]} > 0 ))
HAS_REA=$(( ${#FAIL_REACHABLE[@]} > 0 ))
HAS_CON=$(( ${#FAIL_CONNECTION[@]} > 0 ))
TOTAL_FAILS=$(( HAS_MAT + HAS_REG + HAS_REA + HAS_CON ))

echo "============================================================"
echo "[verify-wiring] SUMMARY"
echo "  Depts checked: ${#DEPTS_TO_CHECK[@]}"
echo "  Materialized failures : ${#FAIL_MATERIALIZED[@]}"
echo "  Registered failures   : ${#FAIL_REGISTERED[@]}"
echo "  Reachable failures    : ${#FAIL_REACHABLE[@]}"
echo "  Connection failures   : ${#FAIL_CONNECTION[@]}"

if [[ $TOTAL_FAILS -eq 0 ]]; then
  echo "  VERDICT: ALL PASS — department(s) wired correctly"
  echo "  (materialized + registered + reachable + connection-points-verified)"
  exit 0
fi

echo ""
echo "  VERDICT: FAIL — departments are NOT fully wired"
echo ""
[[ ${#FAIL_MATERIALIZED[@]} -gt 0 ]] && echo "  MATERIALIZED gaps: ${FAIL_MATERIALIZED[*]}"
[[ ${#FAIL_REGISTERED[@]} -gt 0 ]]   && echo "  REGISTERED gaps:   ${FAIL_REGISTERED[*]}"
[[ ${#FAIL_REACHABLE[@]} -gt 0 ]]    && echo "  REACHABLE gaps:    ${FAIL_REACHABLE[*]}"
[[ ${#FAIL_CONNECTION[@]} -gt 0 ]]   && echo "  CONNECTION gaps:   ${FAIL_CONNECTION[*]}"
echo ""
echo "  REMEDIATION:"
echo "    Materialized  -> run: python3 scripts/post-build-role-workspaces.py --dept <slug>"
echo "    Registered    -> check openclaw.json agents.list; re-run build-workforce.py or add-role.sh"
echo "    Reachable     -> ensure a Director/Head/Lead/Architect role exists in the dept folder"
echo "    Connection    -> fill required cfg_key values in openclaw.json per connection-manifest.json"
echo "    Re-run:       bash scripts/verify-wiring.sh --dept <slug>"
echo "    Then re-run:  bash scripts/verify-library-gate.sh"
echo "============================================================"

# Exit code hierarchy: 6 = mixed, else single category
if [[ $TOTAL_FAILS -gt 1 ]]; then
  exit 6
elif [[ $HAS_MAT -eq 1 ]]; then
  exit 2
elif [[ $HAS_REG -eq 1 ]]; then
  exit 3
elif [[ $HAS_REA -eq 1 ]]; then
  exit 4
else
  exit 5
fi

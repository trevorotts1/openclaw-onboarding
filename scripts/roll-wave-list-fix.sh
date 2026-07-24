#!/usr/bin/env bash
# ============================================================================
# roll-wave-list-fix.sh  (U117 fleet rollout -- wave-list fix to all boxes)
#
# Purpose: Ship the wave-list fix (archived-skill removal from OC_WAVE<N>_SKILLS
# in lib-onboarding-state.sh) to every box in the fleet, ahead of the normal
# refresh cycle. The fix is already on main (U101); this script is the vehicle
# that pushes it to the live fleet.
#
# WHAT IT DOES (per box):
#   1. SSH to the box, locate the onboarding clone path.
#   2. Run qc-assert-wave-list-integrity.py --root <clone> to check status.
#   3. If PASS: report PASS (already fixed). If FAIL: apply the fix.
#   4. To apply: copy the operator's corrected lib-onboarding-state.sh to the box
#      (atomic: temp + rename + backup), then re-run the integrity check.
#   5. Report PASS/FAIL/SKIP per box to a JSONL ledger.
#
# ROSTER FILE (pipe-separated; # comments and blank lines ignored):
#   slug|type|address|onboarding_root
#     type=vps    address=IP, ssh root@IP; onboarding_root is path inside container
#     type=mac    address=ssh alias from ~/.ssh/config (cloudflared tunnel)
#     type=local  box without SSH; address is "-" or blank
#   The REAL roster carries box identities, so it lives operator-local and is
#   NEVER committed. See client-roster.example.txt for the template format.
#
# ENVIRONMENT OVERRIDES (for testing):
#   ROLL_WAVE_LIST_SRC_DIR    path to openclaw-onboarding repo containing the
#                             clean lib-onboarding-state.sh and integrity check.
#   ROLL_WAVE_LIST_DEVEL      if non-empty, any slug may use type=local.
#
# USAGE:
#   roll-wave-list-fix.sh --roster FILE [--dry-run] [--yes] [--only SLUG]
#                         [--ledger-dir DIR] [--max-boxes N]
#
#   --dry-run        precheck only; reports what WOULD be fixed, writes nothing.
#   --yes            REQUIRED for a real (writing) run. Without it the script
#                    prints the plan and refuses. This is the arming pin.
#   --only SLUG      restrict the run to one slug from the roster file.
#   --max-boxes N    refuse to run if the roster has more rows (default 15).
#
# HARD RULES:
#   - Never aborts the whole batch on one box failure: record and continue.
#   - Idempotent: a re-run against a correct box is an exact-match no-op.
#   - Atomic writes only (temp file + rename + backup) -- never truncates in place.
#   - No em dashes in output. Slugs only, never client names.
#   - Per-box PASS/FAIL JSONL ledger written as the run progresses.
# ============================================================================
set -u
set -o pipefail

# Resolve repo root: prefer env override, fall back to script-location inference.
if [ -n "${ROLL_WAVE_LIST_SRC_DIR:-}" ]; then
  REPO_ROOT="${ROLL_WAVE_LIST_SRC_DIR}"
elif [ -n "${BASH_SOURCE:-}" ] && [ "${BASH_SOURCE}" != "${0}" ]; then
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE}")/.." && pwd)"
else
  REPO_ROOT="$(cd "$(dirname "${0}")/.." && pwd)"
fi

LIB_SOURCE="${REPO_ROOT}/lib-onboarding-state.sh"
INTEGRITY_CHECK="${REPO_ROOT}/scripts/qc-assert-wave-list-integrity.py"
DEVEL_MODE="${ROLL_WAVE_LIST_DEVEL:-}"

TS="$(date -u +%Y%m%d-%H%M%S)"
SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_ed25519}"
VPS_SSH_OPTS=(-i "${SSH_KEY}" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=8 -o UserKnownHostsFile="${HOME}/.ssh/known_hosts")
MAC_SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=25 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=8)

ROSTER_FILE=""
DRY_RUN=0
ARMED=0
ONLY_SLUG=""
LEDGER_DIR="${HOME}/clawd/wave-list-roll/ledgers"
MAX_BOXES=15

log()  { printf '%s %s\n' "[$(date -u +%H:%M:%SZ)]" "$*"; }
err()  { printf '%s %s\n' "[$(date -u +%H:%M:%SZ)] ERROR:" "$*" >&2; }
die()  { err "$*"; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --roster)     ROSTER_FILE="${2:-}"; shift 2 ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --yes)        ARMED=1; shift ;;
    --only)       ONLY_SLUG="${2:-}"; shift 2 ;;
    --ledger-dir) LEDGER_DIR="${2:-}"; shift 2 ;;
    --max-boxes)  MAX_BOXES="${2:-}"; shift 2 ;;
    -h|--help)    grep '^#' "$0" | sed 's/^# \{0,1\}//' | sed -n '1,68p'; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "${ROSTER_FILE}" ]   || die "--roster FILE is required (explicit box list; this script never auto-discovers boxes)"
[ -f "${ROSTER_FILE}" ]   || die "roster file not found: ${ROSTER_FILE}"
[ -s "${ROSTER_FILE}" ]   || die "roster file is empty: ${ROSTER_FILE}"
case "${MAX_BOXES}" in ''|*[!0-9]*) die "--max-boxes must be a number" ;; esac

# Source files the roll depends on.
[ -f "${LIB_SOURCE}" ]     || die "source lib-onboarding-state.sh missing at ${LIB_SOURCE}; must run from the repo (set ROLL_WAVE_LIST_SRC_DIR to override)"
[ -f "${INTEGRITY_CHECK}" ] || die "integrity check missing at ${INTEGRITY_CHECK}"
# Preflight: operator's own wave lists must be clean before we ship anything.
if ! python3 "${INTEGRITY_CHECK}" --root "${REPO_ROOT}" >/dev/null 2>&1; then
  die "operator repo wave lists are NOT clean -- fix them before rolling (run: python3 ${INTEGRITY_CHECK})"
fi
log "operator repo wave-list integrity: PASS (clean source)"

# ---- parse + validate the roster (fail-closed, no auto-discovery) ----------
ROWS=()
SEEN_SLUGS=" "
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%%$'\r'}"
  [ -z "$line" ] && continue
  case "$line" in \#*) continue ;; esac
  IFS='|' read -r slug btype addr ob_root <<< "$line"
  [ -n "${slug:-}" ] && [ -n "${btype:-}" ] || die "malformed roster row (need slug|type|address|onboarding_root): row starting '${slug:-?}'"
  [[ "$slug" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "bad slug shape: '${slug}'"
  case "${SEEN_SLUGS}" in *" ${slug} "*) die "duplicate slug in roster: ${slug}" ;; esac
  SEEN_SLUGS="${SEEN_SLUGS}${slug} "
  case "$btype" in
    vps)   [ -n "${addr:-}" ] && [ -n "${ob_root:-}" ] || die "vps row ${slug}: address and onboarding_root required" ;;
    mac)   [ -n "${addr:-}" ] || die "mac row ${slug}: ssh alias required in address column" ;;
    local) if [ -z "${DEVEL_MODE}" ]; then
             [ "$slug" = "blackceomacmini" ] || die "type local is allowed only for slug blackceomacmini (operator box), got: ${slug}. Set ROLL_WAVE_LIST_DEVEL=1 to override for testing."
           fi ;;
    *)     die "row ${slug}: type must be vps, mac, or local (got '${btype}')" ;;
  esac
  [ -n "${ob_root:-}" ] || die "row ${slug}: onboarding_root is required (path to openclaw-onboarding clone on the box)"
  if [ -n "${ONLY_SLUG}" ] && [ "${slug}" != "${ONLY_SLUG}" ]; then continue; fi
  ROWS+=("${slug}|${btype}|${addr}|${ob_root}")
done < "${ROSTER_FILE}"

[ "${#ROWS[@]}" -gt 0 ] || die "no roster rows selected (check --only value against the roster file)"
[ "${#ROWS[@]}" -le "${MAX_BOXES}" ] || die "roster selects ${#ROWS[@]} boxes which exceeds --max-boxes ${MAX_BOXES}; refusing (runaway fan-out guard)"

log "plan: ${#ROWS[@]} box(es), mode=$([ "${DRY_RUN}" = "1" ] && echo dry-run || echo REAL)"
for row in "${ROWS[@]}"; do log "  target: ${row%%|*} ($(printf '%s' "$row" | cut -d'|' -f2))"; done

if [ "${DRY_RUN}" != "1" ] && [ "${ARMED}" != "1" ]; then
  die "REAL mode requires --yes (the arming pin). Re-run with --dry-run to rehearse, or add --yes to write."
fi

mkdir -p "${LEDGER_DIR}" || die "cannot create ledger dir ${LEDGER_DIR}"
LEDGER="${LEDGER_DIR}/wave-list-roll-${TS}.jsonl"
: > "${LEDGER}" || die "cannot write ledger ${LEDGER}"
chmod 600 "${LEDGER}" 2>/dev/null || true
log "ledger: ${LEDGER}"

# ---------------------------------------------------------------------------
# run_integrity_check: run qc-assert-wave-list-integrity.py on a box root.
# Writes result lines to stdout. Returns 0 on PASS, nonzero on FAIL.
# ---------------------------------------------------------------------------
run_integrity_check() {
  local ob_root="$1"
  local check_script="${ob_root}/scripts/qc-assert-wave-list-integrity.py"
  if [ ! -f "${check_script}" ]; then
    echo "REMOTE-ERROR: integrity check not found at ${check_script}"
    echo "RESULT=FAIL"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "REMOTE-ERROR: python3 not on PATH"
    echo "RESULT=FAIL"
    return 1
  fi
  python3 "${check_script}" --root "${ob_root}" 2>&1
  local check_rc=$?
  if [ "$check_rc" -eq 0 ]; then
    echo "RESULT=PASS"
  else
    echo "RESULT=FAIL"
  fi
  return "$check_rc"
}

# ---------------------------------------------------------------------------
# apply_fix: copy the corrected lib-onboarding-state.sh onto a box root.
# Atomic: temp file + rename. Creates a .bak-pre-wave-list-roll-* backup.
# ---------------------------------------------------------------------------
apply_fix() {
  local ob_root="$1"
  local lib_file="${ob_root}/lib-onboarding-state.sh"
  if [ ! -f "${lib_file}" ]; then
    echo "REMOTE-ERROR: lib-onboarding-state.sh not found at ${lib_file}"
    echo "RESULT=FAIL"
    return 1
  fi
  local backup="${lib_file}.bak-pre-wave-list-roll-$(date -u +%Y%m%d-%H%M%S)"
  cp -p "${lib_file}" "${backup}" || { echo "REMOTE-ERROR: backup failed"; echo "RESULT=FAIL"; return 1; }
  local tmpfile="${lib_file}.tmp.$$"
  cp "${LIB_SOURCE}" "${tmpfile}" || {
    cp -p "${backup}" "${lib_file}"
    rm -f "${tmpfile}"
    echo "REMOTE-ERROR: copy source failed"; echo "RESULT=FAIL"; return 1
  }
  if [ ! -s "${tmpfile}" ]; then
    cp -p "${backup}" "${lib_file}"
    rm -f "${tmpfile}"
    echo "REMOTE-ERROR: copied file is empty"; echo "RESULT=FAIL"; return 1
  fi
  head -1 "${tmpfile}" | grep -q '^#!/' || {
    cp -p "${backup}" "${lib_file}"
    rm -f "${tmpfile}"
    echo "REMOTE-ERROR: copied file missing shebang (likely corrupt)"; echo "RESULT=FAIL"; return 1
  }
  chmod 644 "${tmpfile}" 2>/dev/null || true
  mv "${tmpfile}" "${lib_file}" || {
    cp -p "${backup}" "${lib_file}"
    rm -f "${tmpfile}"
    echo "REMOTE-ERROR: atomic rename failed"; echo "RESULT=FAIL"; return 1
  }
  echo "FIX_APPLY=OK"
  echo "FIX_BACKUP=${backup}"

  # Re-check integrity on the box
  local check_script="${ob_root}/scripts/qc-assert-wave-list-integrity.py"
  if [ ! -f "${check_script}" ]; then
    echo "FIX_VERIFY=SKIP (no check script on box)"
    echo "RESULT=OK"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    if python3 "${check_script}" --root "${ob_root}" >/dev/null 2>&1; then
      echo "FIX_VERIFY=PASS"
      echo "RESULT=OK"
    else
      cp -p "${backup}" "${lib_file}"
      echo "FIX_VERIFY=FAIL (restored backup)"
      echo "RESULT=FAIL"
      return 1
    fi
  else
    echo "FIX_VERIFY=SKIP (no python3 on box)"
    echo "RESULT=OK"
  fi
  return 0
}

# ---------------------------------------------------------------------------
# ledger helpers
# ---------------------------------------------------------------------------
ledger_append() {
  local slug="$1" btype="$2" mode="$3" result="$4" reason="$5" markers="$6"
  local ts_json
  ts_json="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  jq -cn \
    --arg ts "$ts_json" \
    --arg slug "$slug" --arg type "$btype" --arg mode "$mode" \
    --arg result "$result" --arg reason "$reason" \
    --arg markers "$(cat "$markers")" \
    '{ts:$ts, slug:$slug, type:$type, mode:$mode, result:$result, reason:$reason,
      markers:($markers | split("\n") | map(select(length>0)))}' \
    >> "${LEDGER}"
}

# ---------------------------------------------------------------------------
# per-box logic -- direct local execution (no SSH needed)
# ---------------------------------------------------------------------------
process_local_box() {
  local ob_root="$1" mode="$2"
  run_integrity_check "${ob_root}"
  local check_rc=$?
  if [ "$check_rc" -eq 0 ] && grep -q '^RESULT=PASS' "${MARKERS}"; then
    return 0
  fi
  if [ "${mode}" = "dry" ]; then
    return 1
  fi
  apply_fix "${ob_root}"
}

# ---------------------------------------------------------------------------
# process_ssh_box -- SSH to a remote box. The function body and the
# corrected lib file are shipped over stdin.
# ---------------------------------------------------------------------------
process_ssh_box() {
  local target="$1" ob_root="$2" mode="$3" ssh_opts_var="$4"
  local ssh_opts
  eval "ssh_opts=(\"\${${ssh_opts_var}[@]}\")"

  # Build a self-contained remote script via heredoc that:
  # 1. Checks wave-list integrity; if PASS, exits 0.
  # 2. In REAL mode, applies the fix (receives correct lib via base64).
  local remote_script
  remote_script="$(cat <<'REMOTE'
set -u
OB_ROOT="$1"
MODE="$2"
CHK="${OB_ROOT}/scripts/qc-assert-wave-list-integrity.py"
LIB="${OB_ROOT}/lib-onboarding-state.sh"

[ -f "${CHK}" ] || { echo "REMOTE-ERROR: integrity check not found at ${CHK}"; echo "RESULT=FAIL"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "REMOTE-ERROR: python3 not on PATH"; echo "RESULT=FAIL"; exit 1; }
[ -f "${LIB}" ] || { echo "REMOTE-ERROR: lib-onboarding-state.sh not found at ${LIB}"; echo "RESULT=FAIL"; exit 1; }

python3 "${CHK}" --root "${OB_ROOT}" 2>&1; rc=$?
if [ "$rc" -eq 0 ]; then
  echo "RESULT=PASS"
  exit 0
fi
echo "RESULT=FAIL"

if [ "${MODE}" = "dry" ]; then
  exit 1
fi

# Read the corrected lib file from stdin (base64 encoded, then a newline marker)
B64_FILE="/tmp/wlf-lib.b64.$$"
cat > "${B64_FILE}" || { echo "REMOTE-ERROR: cannot read fix payload from stdin"; echo "RESULT=FAIL"; exit 1; }
B64_DATA=""; in_b64=1; newline_count=0
while IFS= read -r b64line || [ -n "$b64line" ]; do
  if [ "$in_b64" = "1" ]; then
    if [ "$b64line" = "END-B64" ]; then
      in_b64=0
      continue
    fi
    printf '%s' "$b64line" >> "${B64_FILE}"
  else
    # The rest is the fix_payload shell commands
    break
  fi
done

BACKUP="${LIB}.bak-pre-wave-list-roll-$(date -u +%Y%m%d-%H%M%S)"
cp -p "${LIB}" "${BACKUP}" || { rm -f "${B64_FILE}"; echo "REMOTE-ERROR: backup failed"; echo "RESULT=FAIL"; exit 1; }
TMP="${LIB}.tmp.$$"
base64 -d < "${B64_FILE}" > "${TMP}" 2>/dev/null || {
  cp -p "${BACKUP}" "${LIB}"; rm -f "${B64_FILE}" "${TMP}"
  echo "REMOTE-ERROR: base64 decode failed"; echo "RESULT=FAIL"; exit 1
}
rm -f "${B64_FILE}"
[ -s "${TMP}" ] || { cp -p "${BACKUP}" "${LIB}"; rm -f "${TMP}"; echo "REMOTE-ERROR: decoded file empty"; echo "RESULT=FAIL"; exit 1; }
head -1 "${TMP}" | grep -q '^#!/' || { cp -p "${BACKUP}" "${LIB}"; rm -f "${TMP}"; echo "REMOTE-ERROR: decoded missing shebang"; echo "RESULT=FAIL"; exit 1; }
chmod 644 "${TMP}" 2>/dev/null || true
mv "${TMP}" "${LIB}" || { cp -p "${BACKUP}" "${LIB}"; rm -f "${TMP}"; echo "REMOTE-ERROR: atomic rename failed"; echo "RESULT=FAIL"; exit 1; }
echo "FIX_APPLY=OK"

# Re-verify
if python3 "${CHK}" --root "${OB_ROOT}" >/dev/null 2>&1; then
  echo "FIX_VERIFY=PASS"
  echo "RESULT=OK"
  exit 0
else
  cp -p "${BACKUP}" "${LIB}"
  echo "FIX_VERIFY=FAIL (restored backup)"
  echo "RESULT=FAIL"
  exit 1
fi
REMOTE
)"

  if [ "${mode}" = "dry" ]; then
    printf '%s\n' "${remote_script}" | printf '%s\n%s\n' "${remote_script}" "" | \
      ssh "${ssh_opts[@]}" "${target}" "bash -s ${ob_root} dry" 2>&1
  else
    {
      printf '%s\n' "${remote_script}"
      base64 "${LIB_SOURCE}"
      printf 'END-B64\n'
    } | ssh "${ssh_opts[@]}" "${target}" "bash -s ${ob_root} real" 2>&1
  fi
}

# ---------------------------------------------------------------------------
# main loop: one box at a time, record and continue
# ---------------------------------------------------------------------------
PASS_LIST=""; FAIL_LIST=""; SKIP_LIST=""
MODE_LABEL="$([ "${DRY_RUN}" = "1" ] && echo dry || echo real)"

for row in "${ROWS[@]}"; do
  IFS='|' read -r slug btype addr ob_root <<< "${row}"
  MARKERS="$(mktemp "${TMPDIR:-/tmp}/wlf-markers.XXXXXX")"
  log "box ${slug} (${btype} ob_root=${ob_root}): starting (${MODE_LABEL})"

  box_rc=0
  case "${btype}" in
    local) process_local_box "${ob_root}" "${MODE_LABEL}" > "${MARKERS}" 2>&1; box_rc=$? ;;
    mac)   process_ssh_box "${addr}" "${ob_root}" "${MODE_LABEL}" "MAC_SSH_OPTS" > "${MARKERS}" 2>&1; box_rc=$? ;;
    vps)   process_ssh_box "root@${addr}" "${ob_root}" "${MODE_LABEL}" "VPS_SSH_OPTS" > "${MARKERS}" 2>&1; box_rc=$? ;;
  esac

  # Surface the marker lines
  sed 's/^/    /' "${MARKERS}"

  if [ "${box_rc}" -eq 0 ] && grep -q '^FIX_APPLY=OK' "${MARKERS}"; then
    log "box ${slug}: PASS (fixed)"
    ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "PASS" "fixed" "${MARKERS}"
    PASS_LIST="${PASS_LIST} ${slug}"
  elif grep -q '^RESULT=PASS' "${MARKERS}" && ! grep -q '^FIX_APPLY=OK' "${MARKERS}"; then
    log "box ${slug}: PASS (already clean)"
    ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "PASS" "already-clean" "${MARKERS}"
    PASS_LIST="${PASS_LIST} ${slug}"
  elif grep -q '^REMOTE-ERROR:' "${MARKERS}"; then
    reason="$(grep -m1 '^REMOTE-ERROR:' "${MARKERS}" | sed 's/^REMOTE-ERROR: //')"
    case "${reason}" in
      "integrity check not found"*|"python3 not on PATH"|"lib-onboarding-state.sh not found"*|"cannot read"*)
        log "box ${slug}: SKIP (${reason})"
        ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "SKIP" "${reason}" "${MARKERS}"
        SKIP_LIST="${SKIP_LIST} ${slug}" ;;
      *)
        log "box ${slug}: FAIL (${reason})"
        ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "FAIL" "${reason}" "${MARKERS}"
        FAIL_LIST="${FAIL_LIST} ${slug}" ;;
    esac
  else
    reason="$(grep -m1 '^FIX_VERIFY=FAIL\|^REMOTE-ERROR:' "${MARKERS}" | sed 's/^REMOTE-ERROR: //' | sed 's/^FIX_VERIFY=//' || true)"
    [ -n "${reason}" ] || reason="payload failure (rc=${box_rc})"
    log "box ${slug}: FAIL (${reason})"
    ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "FAIL" "${reason}" "${MARKERS}"
    FAIL_LIST="${FAIL_LIST} ${slug}"
  fi
  rm -f "${MARKERS}"
done

echo
echo "==================================================================="
echo "Wave-list fix roll summary (UTC ${TS})  mode=${MODE_LABEL}"
echo "  pass: ${PASS_LIST:- none}"
echo "  skip: ${SKIP_LIST:- none}"
echo "  fail: ${FAIL_LIST:- none}"
echo "  ledger: ${LEDGER}"
echo "==================================================================="

[ -z "${FAIL_LIST}" ] || exit 2
exit 0

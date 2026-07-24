#!/usr/bin/env bash
# ============================================================================
# roll-anti-impersonation.sh  (U124 fleet rollout -- anti-impersonation identity
#                               fix to all boxes)
#
# Purpose: Verify across the fleet that no agent identity file or generator
# contains a legacy impersonation directive. Flags any box that still has
# "Act AS IF you ARE the persona" or equivalent phrasing so operators know
# exactly which boxes need the U124 patch applied.
# ============================================================================
set -u
set -o pipefail

if [ -n "${ROLL_ANTI_IMPERSONATION_SRC_DIR:-}" ]; then
  REPO_ROOT="${ROLL_ANTI_IMPERSONATION_SRC_DIR}"
elif [ -n "${BASH_SOURCE:-}" ] && [ "${BASH_SOURCE}" != "${0}" ]; then
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE}")/../.." && pwd)"
else
  REPO_ROOT="$(cd "$(dirname "${0}")/../.." && pwd)"
fi

QC_SCRIPT="${REPO_ROOT}/scripts/qc-assert-no-impersonation-directives.sh"
DEVEL_MODE="${ROLL_ANTI_IMPERSONATION_DEVEL:-}"

TS="$(date -u +%Y%m%d-%H%M%S)"
SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_ed25519}"
VPS_SSH_OPTS=(-i "${SSH_KEY}" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=8 -o UserKnownHostsFile="${HOME}/.ssh/known_hosts")
MAC_SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=25 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=8)

ROSTER_FILE=""; DRY_RUN=0; ARMED=0; ONLY_SLUG=""
LEDGER_DIR="${HOME}/clawd/anti-impersonation-roll/ledgers"; MAX_BOXES=15

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

[ -n "${ROSTER_FILE}" ] || die "--roster FILE is required"
[ -f "${ROSTER_FILE}" ] || die "roster file not found: ${ROSTER_FILE}"
[ -s "${ROSTER_FILE}" ] || die "roster file is empty: ${ROSTER_FILE}"
case "${MAX_BOXES}" in ''|*[!0-9]*) die "--max-boxes must be a number" ;; esac
[ -f "${QC_SCRIPT}" ] || die "qc-assert-no-impersonation-directives.sh missing at ${QC_SCRIPT}"

# Self-check: operator's own repo must pass before we roll to the fleet.
QC_OPERATOR_RC=0
QC_IMPERSONATION_SCAN_ROOT="${REPO_ROOT}" bash "${QC_SCRIPT}" >/dev/null 2>&1 || QC_OPERATOR_RC=$?
if [ "${QC_OPERATOR_RC}" -ne 0 ]; then
  die "operator repo has impersonation directives -- fix them before rolling"
fi
log "operator repo anti-impersonation check: PASS (clean)"

ROWS=()
SEEN_SLUGS=" "
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%%$'\r'}"; [ -z "$line" ] && continue
  case "$line" in \#*) continue ;; esac
  IFS='|' read -r slug btype addr ob_root <<< "$line"
  [ -n "${slug:-}" ] && [ -n "${btype:-}" ] || die "malformed roster row"
  [[ "$slug" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "bad slug shape: '${slug}'"
  case "${SEEN_SLUGS}" in *" ${slug} "*) die "duplicate slug in roster: ${slug}" ;; esac
  SEEN_SLUGS="${SEEN_SLUGS}${slug} "
  case "$btype" in
    vps)   [ -n "${addr:-}" ] && [ -n "${ob_root:-}" ] || die "vps row ${slug}: address and onboarding_root required" ;;
    mac)   [ -n "${addr:-}" ] || die "mac row ${slug}: ssh alias required" ;;
    local) if [ -z "${DEVEL_MODE}" ]; then
             [ "$slug" = "blackceomacmini" ] || die "type local allowed only for blackceomacmini"
           fi ;;
    *)     die "row ${slug}: type must be vps, mac, or local" ;;
  esac
  [ -n "${ob_root:-}" ] || die "row ${slug}: onboarding_root required"
  if [ -n "${ONLY_SLUG}" ] && [ "${slug}" != "${ONLY_SLUG}" ]; then continue; fi
  ROWS+=("${slug}|${btype}|${addr}|${ob_root}")
done < "${ROSTER_FILE}"
[ "${#ROWS[@]}" -gt 0 ] || die "no roster rows selected"
[ "${#ROWS[@]}" -le "${MAX_BOXES}" ] || die "roster selects ${#ROWS[@]} boxes exceeds --max-boxes ${MAX_BOXES}"

log "plan: ${#ROWS[@]} box(es), mode=$([ "${DRY_RUN}" = "1" ] && echo dry-run || echo REAL)"
for row in "${ROWS[@]}"; do log "  target: ${row%%|*} ($(printf '%s' "$row" | cut -d'|' -f2))"; done

if [ "${DRY_RUN}" != "1" ] && [ "${ARMED}" != "1" ]; then
  die "REAL mode requires --yes (the arming pin). Re-run with --dry-run to rehearse, or add --yes to write."
fi

mkdir -p "${LEDGER_DIR}" || die "cannot create ledger dir"
LEDGER="${LEDGER_DIR}/anti-impersonation-roll-${TS}.jsonl"
: > "${LEDGER}"; chmod 600 "${LEDGER}" 2>/dev/null || true
log "ledger: ${LEDGER}"

ledger_append() {
  local slug="$1" btype="$2" mode="$3" result="$4" reason="$5" markers="$6"
  local ts_json; ts_json="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  jq -cn --arg ts "$ts_json" --arg slug "$slug" --arg type "$btype" --arg mode "$mode" --arg result "$result" --arg reason "$reason" --arg markers "$(cat "$markers")" '{ts:$ts,slug:$slug,type:$type,mode:$mode,result:$result,reason:$reason,markers:($markers|split("\n")|map(select(length>0)))}' >> "${LEDGER}"
}

process_local_box() {
  local ob_root="$1" mode="$2"
  local qc_path="${ob_root}/scripts/qc-assert-no-impersonation-directives.sh"
  if [ ! -f "${qc_path}" ]; then
    echo "MISSING_QC=yes"
    echo "RESULT=ERROR"
    echo "ERROR: qc-assert-no-impersonation-directives.sh not deployed"
    return 2
  fi
  QC_IMPERSONATION_SCAN_ROOT="${ob_root}" bash "${qc_path}" 2>&1
}

process_ssh_box() {
  local target="$1" ob_root="$2" mode="$3" ssh_opts_var="$4"
  local ssh_opts; eval "ssh_opts=(\"\${${ssh_opts_var}[@]}\")"

  local remote_script
  remote_script="$(cat <<'RSCRIPT'
set -u; OB_ROOT="$1"
QC_SCRIPT="${OB_ROOT}/scripts/qc-assert-no-impersonation-directives.sh"
if [ ! -f "${QC_SCRIPT}" ]; then
  echo "MISSING_QC=yes"
  echo "RESULT=ERROR"
  echo "ERROR: qc-assert-no-impersonation-directives.sh not deployed"
  exit 2
fi
QC_IMPERSONATION_SCAN_ROOT="${OB_ROOT}" bash "${QC_SCRIPT}" 2>&1
RSCRIPT
)"

  ssh "${ssh_opts[@]}" "${target}" "bash -s ${ob_root}" <<< "${remote_script}" 2>&1
}

PASS_LIST=""; FAIL_LIST=""; ERROR_LIST=""
MODE_LABEL="$([ "${DRY_RUN}" = "1" ] && echo dry || echo real)"

for row in "${ROWS[@]}"; do
  IFS='|' read -r slug btype addr ob_root <<< "${row}"
  MARKERS="$(mktemp "${TMPDIR:-/tmp}/ai-roll-markers.XXXXXX")"
  log "box ${slug} (${btype}): scanning (${MODE_LABEL})"
  box_rc=0
  case "${btype}" in
    local) process_local_box "${ob_root}" "${MODE_LABEL}" > "${MARKERS}" 2>&1; box_rc=$? ;;
    mac)   process_ssh_box "${addr}" "${ob_root}" "${MODE_LABEL}" "MAC_SSH_OPTS" > "${MARKERS}" 2>&1; box_rc=$? ;;
    vps)   process_ssh_box "root@${addr}" "${ob_root}" "${MODE_LABEL}" "VPS_SSH_OPTS" > "${MARKERS}" 2>&1; box_rc=$? ;;
  esac

  sed 's/^/    /' "${MARKERS}"

  if grep -q '^MISSING_QC=yes' "${MARKERS}"; then
    log "box ${slug}: ERROR (QC script not deployed)"; ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "ERROR" "qc-script-missing" "${MARKERS}"; ERROR_LIST="${ERROR_LIST} ${slug}"
  elif grep -q '^OK: No impersonation directives' "${MARKERS}"; then
    log "box ${slug}: PASS (clean)"; ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "PASS" "clean" "${MARKERS}"; PASS_LIST="${PASS_LIST} ${slug}"
  elif grep -q '^INVARIANT VIOLATED' "${MARKERS}"; then
    log "box ${slug}: FAIL (impersonation directives found)"; ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "FAIL" "impersonation-directives" "${MARKERS}"; FAIL_LIST="${FAIL_LIST} ${slug}"
  elif grep -q '^ERROR:' "${MARKERS}"; then
    reason="$(grep -m1 '^ERROR:' "${MARKERS}" | sed 's/^ERROR: //' || true)"
    [ -n "${reason}" ] || reason="unreachable (rc=${box_rc})"
    log "box ${slug}: ERROR (${reason})"; ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "ERROR" "${reason}" "${MARKERS}"; ERROR_LIST="${ERROR_LIST} ${slug}"
  else
    log "box ${slug}: FAIL (unexpected output rc=${box_rc})"; ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "FAIL" "unexpected-rc-${box_rc}" "${MARKERS}"; FAIL_LIST="${FAIL_LIST} ${slug}"
  fi
  rm -f "${MARKERS}"
done

echo; echo "==================================================================="
echo "Anti-impersonation identity roll summary (UTC ${TS})  mode=${MODE_LABEL}"
echo "  pass: ${PASS_LIST:- none}"; echo "  error: ${ERROR_LIST:- none}"
echo "  fail: ${FAIL_LIST:- none}"; echo "  ledger: ${LEDGER}"
echo "==================================================================="
[ -z "${FAIL_LIST}" ] || exit 2; [ -z "${ERROR_LIST}" ] || exit 3; exit 0

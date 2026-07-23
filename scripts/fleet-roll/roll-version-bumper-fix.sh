#!/usr/bin/env bash
# ============================================================================
# roll-version-bumper-fix.sh  (U121 fleet rollout -- version-bumper fix to all boxes)
#
# Purpose: Ship the version-bumper fix (removal of _qc-summary.md rewrite from
# scripts/bump-version.sh) to every box in the fleet.
# ============================================================================
set -u
set -o pipefail

if [ -n "${ROLL_BUMPER_SRC_DIR:-}" ]; then
  REPO_ROOT="${ROLL_BUMPER_SRC_DIR}"
elif [ -n "${BASH_SOURCE:-}" ] && [ "${BASH_SOURCE}" != "${0}" ]; then
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE}")/../.." && pwd)"
else
  REPO_ROOT="$(cd "$(dirname "${0}")/../.." && pwd)"
fi

BUMPER_SOURCE="${REPO_ROOT}/scripts/bump-version.sh"
DEVEL_MODE="${ROLL_BUMPER_DEVEL:-}"

TS="$(date -u +%Y%m%d-%H%M%S)"
SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_ed25519}"
VPS_SSH_OPTS=(-i "${SSH_KEY}" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=8 -o UserKnownHostsFile="${HOME}/.ssh/known_hosts")
MAC_SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=25 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=8)

ROSTER_FILE=""; DRY_RUN=0; ARMED=0; ONLY_SLUG=""
LEDGER_DIR="${HOME}/clawd/bumper-fix-roll/ledgers"; MAX_BOXES=15

log()  { printf '%s %s\n' "[$(date -u +%H:%M:%SZ)]" "$*"; }
err()  { printf '%s %s\n' "[$(date -u +%H:%M:%SZ)] ERROR:" "$*" >&2; }
die()  { err "$*"; exit 1; }

has_dirty_bumper() {
  local ob_root="$1"
  local bumper="${ob_root}/scripts/bump-version.sh"
  if [ ! -f "${bumper}" ]; then return 2; fi
  if grep -nE '^[^#].*_qc-summary\.md' "${bumper}" >/dev/null 2>&1; then return 0; fi
  return 1
}

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
[ -f "${BUMPER_SOURCE}" ] || die "source bump-version.sh missing at ${BUMPER_SOURCE}"

if has_dirty_bumper "${REPO_ROOT}"; then
  die "operator repo bump-version.sh is NOT clean -- fix it before rolling"
fi
log "operator repo version-bumper: PASS (clean source)"

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
LEDGER="${LEDGER_DIR}/bumper-fix-roll-${TS}.jsonl"
: > "${LEDGER}"; chmod 600 "${LEDGER}" 2>/dev/null || true
log "ledger: ${LEDGER}"

check_bumper() {
  local ob_root="$1"
  local bumper="${ob_root}/scripts/bump-version.sh"
  if [ ! -f "${bumper}" ]; then echo "ERROR: bump-version.sh not found"; echo "RESULT=ERROR"; return 2; fi
  if has_dirty_bumper "${ob_root}"; then echo "RESULT=DIRTY"; return 1; fi
  echo "RESULT=CLEAN"; return 0
}

apply_fix() {
  local ob_root="$1"
  local bumper="${ob_root}/scripts/bump-version.sh"
  [ -f "${bumper}" ] || { echo "ERROR: bump-version.sh not found"; echo "RESULT=FAIL"; return 1; }
  local backup="${bumper}.bak-pre-bumper-roll-$(date -u +%Y%m%d-%H%M%S)"
  cp -p "${bumper}" "${backup}" || { echo "ERROR: backup failed"; echo "RESULT=FAIL"; return 1; }
  local tmpfile="${bumper}.tmp.$$"
  cp "${BUMPER_SOURCE}" "${tmpfile}" || { cp -p "${backup}" "${bumper}"; rm -f "${tmpfile}"; echo "ERROR: copy source failed"; echo "RESULT=FAIL"; return 1; }
  [ -s "${tmpfile}" ] || { cp -p "${backup}" "${bumper}"; rm -f "${tmpfile}"; echo "ERROR: copied file empty"; echo "RESULT=FAIL"; return 1; }
  head -1 "${tmpfile}" | grep -q '^#!/' || { cp -p "${backup}" "${bumper}"; rm -f "${tmpfile}"; echo "ERROR: missing shebang"; echo "RESULT=FAIL"; return 1; }
  chmod 755 "${tmpfile}" 2>/dev/null || true
  mv "${tmpfile}" "${bumper}" || { cp -p "${backup}" "${bumper}"; rm -f "${tmpfile}"; echo "ERROR: rename failed"; echo "RESULT=FAIL"; return 1; }
  echo "FIX_APPLY=OK"; echo "FIX_BACKUP=${backup}"
  if has_dirty_bumper "${ob_root}"; then cp -p "${backup}" "${bumper}"; echo "FIX_VERIFY=FAIL (restored backup)"; echo "RESULT=FAIL"; return 1; fi
  echo "FIX_VERIFY=PASS"; echo "RESULT=OK"; return 0
}

ledger_append() {
  local slug="$1" btype="$2" mode="$3" result="$4" reason="$5" markers="$6"
  local ts_json; ts_json="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  jq -cn --arg ts "$ts_json" --arg slug "$slug" --arg type "$btype" --arg mode "$mode" --arg result "$result" --arg reason "$reason" --arg markers "$(cat "$markers")" '{ts:$ts,slug:$slug,type:$type,mode:$mode,result:$result,reason:$reason,markers:($markers|split("\n")|map(select(length>0)))}' >> "${LEDGER}"
}

process_local_box() {
  local ob_root="$1" mode="$2"
  check_bumper "${ob_root}"; local check_rc=$?
  [ "$check_rc" -eq 0 ] && return 0
  [ "$check_rc" -eq 2 ] && return 2
  [ "${mode}" = "dry" ] && return 1
  apply_fix "${ob_root}"
}

process_ssh_box() {
  local target="$1" ob_root="$2" mode="$3" ssh_opts_var="$4"
  local ssh_opts; eval "ssh_opts=(\"\${${ssh_opts_var}[@]}\")"

  local remote_script
  remote_script="$(cat <<'RSCRIPT'
set -u; OB_ROOT="$1"; MODE="$2"; BUMPER="${OB_ROOT}/scripts/bump-version.sh"
[ -f "${BUMPER}" ] || { echo "ERROR: bump-version.sh not found"; echo "RESULT=ERROR"; exit 2; }
DIRTY=0; grep -nE '^[^#].*_qc-summary\.md' "${BUMPER}" >/dev/null 2>&1 && DIRTY=1 || true
if [ "$DIRTY" -eq 0 ]; then echo "RESULT=CLEAN"; exit 0; fi
echo "RESULT=DIRTY"
[ "${MODE}" = "dry" ] && exit 1
cat > /tmp/vbf.$$ || { echo "ERROR: cannot read payload"; echo "RESULT=FAIL"; exit 1; }
in_b64=1; while IFS= read -r l || [ -n "$l" ]; do
  if [ "$in_b64" = "1" ]; then
    if [ "$l" = "END-B64" ]; then in_b64=0; else printf '%s' "$l" >> /tmp/vbf.dec.$$; fi
  fi
done < /tmp/vbf.$$
BACKUP="${BUMPER}.bak-pre-bumper-roll-$(date -u +%Y%m%d-%H%M%S)"
cp -p "${BUMPER}" "${BACKUP}" || { rm -f /tmp/vbf.$$ /tmp/vbf.dec.$$; echo "ERROR: backup failed"; echo "RESULT=FAIL"; exit 1; }
TMP="${BUMPER}.tmp.$$"
base64 -d < /tmp/vbf.dec.$$ > "${TMP}" 2>/dev/null || { cp -p "${BACKUP}" "${BUMPER}"; rm -f /tmp/vbf.$$ /tmp/vbf.dec.$$ "${TMP}"; echo "ERROR: decode failed"; echo "RESULT=FAIL"; exit 1; }
rm -f /tmp/vbf.$$ /tmp/vbf.dec.$$
[ -s "${TMP}" ] || { cp -p "${BACKUP}" "${BUMPER}"; rm -f "${TMP}"; echo "ERROR: decoded empty"; echo "RESULT=FAIL"; exit 1; }
head -1 "${TMP}" | grep -q '^#!/' || { cp -p "${BACKUP}" "${BUMPER}"; rm -f "${TMP}"; echo "ERROR: no shebang"; echo "RESULT=FAIL"; exit 1; }
chmod 755 "${TMP}" 2>/dev/null || true
mv "${TMP}" "${BUMPER}" || { cp -p "${BACKUP}" "${BUMPER}"; rm -f "${TMP}"; echo "ERROR: rename failed"; echo "RESULT=FAIL"; exit 1; }
echo "FIX_APPLY=OK"
DIRTY2=0; grep -nE '^[^#].*_qc-summary\.md' "${BUMPER}" >/dev/null 2>&1 && DIRTY2=1 || true
if [ "$DIRTY2" -eq 0 ]; then echo "FIX_VERIFY=PASS"; echo "RESULT=OK"; exit 0; fi
cp -p "${BACKUP}" "${BUMPER}"; echo "FIX_VERIFY=FAIL (restored backup)"; echo "RESULT=FAIL"; exit 1
RSCRIPT
)"

  if [ "${mode}" = "dry" ]; then
    printf '%s\n' "${remote_script}" | ssh "${ssh_opts[@]}" "${target}" "bash -s ${ob_root} dry" 2>&1
  else
    { printf '%s\n' "${remote_script}"; base64 "${BUMPER_SOURCE}"; printf 'END-B64\n'; } | ssh "${ssh_opts[@]}" "${target}" "bash -s ${ob_root} real" 2>&1
  fi
}

PASS_LIST=""; FAIL_LIST=""; ERROR_LIST=""
MODE_LABEL="$([ "${DRY_RUN}" = "1" ] && echo dry || echo real)"

for row in "${ROWS[@]}"; do
  IFS='|' read -r slug btype addr ob_root <<< "${row}"
  MARKERS="$(mktemp "${TMPDIR:-/tmp}/vbf-markers.XXXXXX")"
  log "box ${slug} (${btype}): starting (${MODE_LABEL})"
  box_rc=0
  case "${btype}" in
    local) process_local_box "${ob_root}" "${MODE_LABEL}" > "${MARKERS}" 2>&1; box_rc=$? ;;
    mac)   process_ssh_box "${addr}" "${ob_root}" "${MODE_LABEL}" "MAC_SSH_OPTS" > "${MARKERS}" 2>&1; box_rc=$? ;;
    vps)   process_ssh_box "root@${addr}" "${ob_root}" "${MODE_LABEL}" "VPS_SSH_OPTS" > "${MARKERS}" 2>&1; box_rc=$? ;;
  esac
  sed 's/^/    /' "${MARKERS}"
  if grep -q '^FIX_APPLY=OK' "${MARKERS}" && grep -q '^FIX_VERIFY=PASS' "${MARKERS}"; then
    log "box ${slug}: PASS (fixed)"; ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "PASS" "fixed" "${MARKERS}"; PASS_LIST="${PASS_LIST} ${slug}"
  elif grep -q '^RESULT=CLEAN' "${MARKERS}"; then
    log "box ${slug}: PASS (already clean)"; ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "PASS" "already-clean" "${MARKERS}"; PASS_LIST="${PASS_LIST} ${slug}"
  elif grep -q '^RESULT=ERROR\|^ERROR:' "${MARKERS}"; then
    reason="$(grep -m1 '^ERROR:' "${MARKERS}" | sed 's/^ERROR: //' || true)"
    [ -n "${reason}" ] || reason="unreachable (rc=${box_rc})"
    log "box ${slug}: ERROR (${reason})"; ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "ERROR" "${reason}" "${MARKERS}"; ERROR_LIST="${ERROR_LIST} ${slug}"
  elif grep -q '^FIX_VERIFY=FAIL' "${MARKERS}"; then
    log "box ${slug}: FAIL (fix-verify failed)"; ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "FAIL" "fix-verify-failed" "${MARKERS}"; FAIL_LIST="${FAIL_LIST} ${slug}"
  else
    reason="$(grep -m1 '^ERROR:\|^FIX_VERIFY=FAIL' "${MARKERS}" | sed 's/^ERROR: //' | sed 's/^FIX_VERIFY=//' || true)"
    [ -n "${reason}" ] || reason="payload failure (rc=${box_rc})"
    log "box ${slug}: FAIL (${reason})"; ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "FAIL" "${reason}" "${MARKERS}"; FAIL_LIST="${FAIL_LIST} ${slug}"
  fi
  rm -f "${MARKERS}"
done

echo; echo "==================================================================="
echo "Version-bumper fix roll summary (UTC ${TS})  mode=${MODE_LABEL}"
echo "  pass: ${PASS_LIST:- none}"; echo "  error: ${ERROR_LIST:- none}"
echo "  fail: ${FAIL_LIST:- none}"; echo "  ledger: ${LEDGER}"
echo "==================================================================="
[ -z "${FAIL_LIST}" ] || exit 2; exit 0

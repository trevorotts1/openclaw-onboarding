#!/usr/bin/env bash
# roll-version-bumper-fix.sh -- U121 fleet rollout for version-bumper fix
set -u; set -o pipefail
if [ -n "${ROLL_BUMPER_SRC_DIR:-}" ]; then REPO_ROOT="${ROLL_BUMPER_SRC_DIR}"
elif [ -n "${BASH_SOURCE:-}" ] && [ "${BASH_SOURCE}" != "${0}" ]; then REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE}")/../.." && pwd)"
else REPO_ROOT="$(cd "$(dirname "${0}")/../.." && pwd)"; fi
BUMPER_SOURCE="${REPO_ROOT}/scripts/bump-version.sh"; DEVEL_MODE="${ROLL_BUMPER_DEVEL:-}"
TS="$(date -u +%Y%m%d-%H%M%S)"; SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_ed25519}"
VPS_SSH_OPTS=(-i "${SSH_KEY}" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=8 -o UserKnownHostsFile="${HOME}/.ssh/known_hosts")
MAC_SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=25 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=8)
ROSTER_FILE=""; DRY_RUN=0; ARMED=0; ONLY_SLUG=""; LEDGER_DIR="${HOME}/clawd/bumper-fix-roll/ledgers"; MAX_BOXES=15
log() { printf '%s %s
' "[$(date -u +%H:%M:%SZ)]" "$*"; }
err() { printf '%s %s
' "[$(date -u +%H:%M:%SZ)] ERROR:" "$*" >&2; }
die() { err "$*"; exit 1; }
has_dirty_bumper() { local ob_root="$1"; local bumper="${ob_root}/scripts/bump-version.sh"
  [ -f "${bumper}" ] || return 2
  grep -nE '^[^#].*_qc-summary\.md' "${bumper}" >/dev/null 2>&1 && return 0; return 1; }
while [ $# -gt 0 ]; do case "$1" in
  --roster) ROSTER_FILE="${2:-}"; shift 2;; --dry-run) DRY_RUN=1; shift;; --yes) ARMED=1; shift;;
  --only) ONLY_SLUG="${2:-}"; shift 2;; --ledger-dir) LEDGER_DIR="${2:-}"; shift 2;;
  --max-boxes) MAX_BOXES="${2:-}"; shift 2;; -h|--help) grep '^#' "$0"|sed 's/^# \{0,1\}//'|sed -n '1,68p'; exit 0;;
  *) die "unknown argument: $1";; esac; done
[ -n "${ROSTER_FILE}" ] || die "--roster FILE required"; [ -f "${ROSTER_FILE}" ] || die "roster not found"
[ -s "${ROSTER_FILE}" ] || die "roster empty"; case "${MAX_BOXES}" in ''|*[!0-9]*) die "--max-boxes must be number";; esac
[ -f "${BUMPER_SOURCE}" ] || die "bump-version.sh missing"
if has_dirty_bumper "${REPO_ROOT}"; then die "operator bump-version.sh NOT clean"; fi
log "operator version-bumper: PASS (clean)"
ROWS=(); SEEN_SLUGS=" "
while IFS= read -r line || [ -n "$line" ]; do line="${line%%$''}"; [ -z "$line" ]&&continue
  case "$line" in \#*) continue;; esac; IFS='|' read -r slug btype addr ob_root <<< "$line"
  [ -n "${slug:-}" ]&&[ -n "${btype:-}" ]||die "malformed roster"; [[ "$slug" =~ ^[a-z0-9][a-z0-9-]*$ ]]||die "bad slug: ${slug}"
  case "${SEEN_SLUGS}" in *" ${slug} "*) die "duplicate slug: ${slug}";; esac; SEEN_SLUGS="${SEEN_SLUGS}${slug} "
  case "$btype" in vps) [ -n "${addr:-}" ]&&[ -n "${ob_root:-}" ]||die "vps ${slug}: addr+root required";;
    mac) [ -n "${addr:-}" ]||die "mac ${slug}: addr required";;
    local) [ -n "${DEVEL_MODE}" ]||[ "$slug" = "blackceomacmini" ]||die "local only for blackceomacmini";;
    *) die "bad type: ${btype}";; esac
  [ -n "${ob_root:-}" ]||die "${slug}: onboarding_root required"
  [ -z "${ONLY_SLUG}" ]||[ "${slug}" = "${ONLY_SLUG}" ]||continue; ROWS+=("${slug}|${btype}|${addr}|${ob_root}")
done < "${ROSTER_FILE}"
[ "${#ROWS[@]}" -gt 0 ]||die "no rows selected"; [ "${#ROWS[@]}" -le "${MAX_BOXES}" ]||die "too many boxes: ${#ROWS[@]} > ${MAX_BOXES}"
log "plan: ${#ROWS[@]} boxes, mode=$([ ${DRY_RUN} = 1 ]&&echo dry-run||echo REAL)"
for row in "${ROWS[@]}"; do log "  target: ${row%%|*} ($(printf '%s' "$row"|cut -d'|' -f2))"; done
if [ "${DRY_RUN}" != "1" ]&&[ "${ARMED}" != "1" ]; then die "REAL mode requires --yes (arming pin). Use --dry-run to rehearse, or add --yes to write."; fi
mkdir -p "${LEDGER_DIR}"||die "ledger dir"; LEDGER="${LEDGER_DIR}/bumper-fix-roll-${TS}.jsonl"
: > "${LEDGER}"; chmod 600 "${LEDGER}" 2>/dev/null||true; log "ledger: ${LEDGER}"
check_bumper() { local ob_root="$1"; local bumper="${ob_root}/scripts/bump-version.sh"
  [ -f "${bumper}" ]||{ echo "ERROR: bump-version.sh not found"; echo "RESULT=ERROR"; return 2; }
  has_dirty_bumper "${ob_root}"&&{ echo "RESULT=DIRTY"; return 1; }; echo "RESULT=CLEAN"; return 0; }
apply_fix() { local ob_root="$1"; local bumper="${ob_root}/scripts/bump-version.sh"
  [ -f "${bumper}" ]||{ echo "ERROR: bumper not found"; echo "RESULT=FAIL"; return 1; }
  local bak="${bumper}.bak-pre-bumper-roll-$(date -u +%Y%m%d-%H%M%S)"
  cp -p "${bumper}" "${bak}"||{ echo "ERROR: backup failed"; echo "RESULT=FAIL"; return 1; }
  local tmp="${bumper}.tmp.$$"; cp "${BUMPER_SOURCE}" "${tmp}"||{ cp -p "${bak}" "${bumper}"; rm -f "${tmp}"; echo "ERROR: copy failed"; echo "RESULT=FAIL"; return 1; }
  [ -s "${tmp}" ]||{ cp -p "${bak}" "${bumper}"; rm -f "${tmp}"; echo "ERROR: empty"; echo "RESULT=FAIL"; return 1; }
  head -1 "${tmp}"|grep -q '^#!/'||{ cp -p "${bak}" "${bumper}"; rm -f "${tmp}"; echo "ERROR: no shebang"; echo "RESULT=FAIL"; return 1; }
  chmod 755 "${tmp}" 2>/dev/null||true; mv "${tmp}" "${bumper}"||{ cp -p "${bak}" "${bumper}"; rm -f "${tmp}"; echo "ERROR: rename"; echo "RESULT=FAIL"; return 1; }
  echo "FIX_APPLY=OK"; echo "FIX_BACKUP=${bak}"
  if has_dirty_bumper "${ob_root}"; then cp -p "${bak}" "${bumper}"; echo "FIX_VERIFY=FAIL (restored)"; echo "RESULT=FAIL"; return 1; fi
  echo "FIX_VERIFY=PASS"; echo "RESULT=OK"; return 0; }
ledger_append() { local slug="$1" btype="$2" mode="$3" result="$4" reason="$5" markers="$6"; local ts_json="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  jq -cn --arg ts "$ts_json" --arg slug "$slug" --arg type "$btype" --arg mode "$mode" --arg result "$result" --arg reason "$reason" --arg markers "$(cat "$markers")" '{ts:$ts,slug:$slug,type:$type,mode:$mode,result:$result,reason:$reason,markers:($markers|split("\n")|map(select(length>0)))}' >> "${LEDGER}"; }
process_local_box() { local ob_root="$1" mode="$2"; check_bumper "${ob_root}"; local rc=$?;
  [ $rc -eq 0 ]&&return 0; [ $rc -eq 2 ]&&return 2; [ "${mode}" = "dry" ]&&return 1; apply_fix "${ob_root}"; }
process_ssh_box() { local target="$1" ob_root="$2" mode="$3" ssh_opts_var="$4"
  local ssh_opts; eval "ssh_opts=("\${[@]}")"
  local rs; rs="$(cat <<'RSCRIPT'
set -u; OB_ROOT="$1"; MODE="$2"; BUMPER="${OB_ROOT}/scripts/bump-version.sh"
[ -f "${BUMPER}" ]||{ echo "ERROR: bumper not found"; echo "RESULT=ERROR"; exit 2; }
D=0; grep -nE '^[^#].*_qc-summary\.md' "${BUMPER}" >/dev/null 2>&1&&D=1||true
[ $D -eq 0 ]&&{ echo "RESULT=CLEAN"; exit 0; }; echo "RESULT=DIRTY"
[ "${MODE}" = "dry" ]&&exit 1
cat > /tmp/vbf.$$||{ echo "ERROR: no payload"; echo "RESULT=FAIL"; exit 1; }
ib=1; while IFS= read -r l||[ -n "$l" ]; do
  [ "$ib" = "1" ]||continue; [ "$l" = "END-B64" ]&&{ ib=0; continue; }
  printf '%s' "$l" >> /tmp/vbf.dec.$$; done < /tmp/vbf.$$
BAK="${BUMPER}.bak-pre-bumper-roll-$(date -u +%Y%m%d-%H%M%S)"
cp -p "${BUMPER}" "${BAK}"||{ rm -f /tmp/vbf.$$ /tmp/vbf.dec.$$; echo "ERROR: backup"; echo "RESULT=FAIL"; exit 1; }
TMP="${BUMPER}.tmp.$$"; base64 -d < /tmp/vbf.dec.$$ > "${TMP}" 2>/dev/null||{ cp -p "${BAK}" "${BUMPER}"; rm -f /tmp/vbf.$$ /tmp/vbf.dec.$$ "${TMP}"; echo "ERROR: decode"; echo "RESULT=FAIL"; exit 1; }
rm -f /tmp/vbf.$$ /tmp/vbf.dec.$$
[ -s "${TMP}" ]||{ cp -p "${BAK}" "${BUMPER}"; rm -f "${TMP}"; echo "ERROR: empty"; echo "RESULT=FAIL"; exit 1; }
head -1 "${TMP}"|grep -q '^#!/'||{ cp -p "${BAK}" "${BUMPER}"; rm -f "${TMP}"; echo "ERROR: no shebang"; echo "RESULT=FAIL"; exit 1; }
chmod 755 "${TMP}" 2>/dev/null||true; mv "${TMP}" "${BUMPER}"||{ cp -p "${BAK}" "${BUMPER}"; rm -f "${TMP}"; echo "ERROR: rename"; echo "RESULT=FAIL"; exit 1; }
echo "FIX_APPLY=OK"; D2=0
grep -nE '^[^#].*_qc-summary\.md' "${BUMPER}" >/dev/null 2>&1&&D2=1||true
[ $D2 -eq 0 ]&&{ echo "FIX_VERIFY=PASS"; echo "RESULT=OK"; exit 0; }
cp -p "${BAK}" "${BUMPER}"; echo "FIX_VERIFY=FAIL (restored)"; echo "RESULT=FAIL"; exit 1
RSCRIPT
)"
  if [ "${mode}" = "dry" ]; then printf '%s
' "${rs}"|ssh "${ssh_opts[@]}" "${target}" "bash -s ${ob_root} dry" 2>&1
  else { printf '%s
' "${rs}"; base64 "${BUMPER_SOURCE}"; printf 'END-B64
'; }|ssh "${ssh_opts[@]}" "${target}" "bash -s ${ob_root} real" 2>&1; fi; }
PL=""; FL=""; EL=""; ML="$([ ${DRY_RUN} = 1 ]&&echo dry||echo real)"
for row in "${ROWS[@]}"; do IFS='|' read -r slug btype addr ob_root <<< "${row}"
  MK="$(mktemp "${TMPDIR:-/tmp}/vbf-mk.XXXXXX")"; log "box ${slug} (${btype}): starting (${ML})"; rc=0
  case "${btype}" in local) process_local_box "${ob_root}" "${ML}" > "${MK}" 2>&1; rc=$?;;
    mac) process_ssh_box "${addr}" "${ob_root}" "${ML}" "MAC_SSH_OPTS" > "${MK}" 2>&1; rc=$?;;
    vps) process_ssh_box "root@${addr}" "${ob_root}" "${ML}" "VPS_SSH_OPTS" > "${MK}" 2>&1; rc=$?;; esac
  sed 's/^/    /' "${MK}"
  if grep -q '^FIX_APPLY=OK' "${MK}"&&grep -q '^FIX_VERIFY=PASS' "${MK}"; then
    log "box ${slug}: PASS (fixed)"; ledger_append "${slug}" "${btype}" "${ML}" "PASS" "fixed" "${MK}"; PL="${PL} ${slug}"
  elif grep -q '^RESULT=CLEAN' "${MK}"; then
    log "box ${slug}: PASS (already clean)"; ledger_append "${slug}" "${btype}" "${ML}" "PASS" "already-clean" "${MK}"; PL="${PL} ${slug}"
  elif grep -q '^RESULT=ERROR\|^ERROR:' "${MK}"; then
    r="$(grep -m1 '^ERROR:' "${MK}"|sed 's/^ERROR: //'||true)"; [ -n "${r}" ]||r="unreachable (rc=${rc})"
    log "box ${slug}: ERROR (${r})"; ledger_append "${slug}" "${btype}" "${ML}" "ERROR" "${r}" "${MK}"; EL="${EL} ${slug}"
  elif grep -q '^FIX_VERIFY=FAIL' "${MK}"; then
    log "box ${slug}: FAIL (verify)"; ledger_append "${slug}" "${btype}" "${ML}" "FAIL" "fix-verify-failed" "${MK}"; FL="${FL} ${slug}"
  else r="$(grep -m1 '^ERROR:\|^FIX_VERIFY=FAIL' "${MK}"|sed 's/^ERROR: //;s/^FIX_VERIFY=//'||true)"
    [ -n "${r}" ]||r="payload failure (rc=${rc})"; log "box ${slug}: FAIL (${r})"
    ledger_append "${slug}" "${btype}" "${ML}" "FAIL" "${r}" "${MK}"; FL="${FL} ${slug}"; fi; rm -f "${MK}"; done
echo; echo "==================================================================="
echo "Version-bumper fix roll summary (UTC ${TS})  mode=${ML}"; echo "  pass: ${PL:- none}"
echo "  error: ${EL:- none}"; echo "  fail: ${FL:- none}"; echo "  ledger: ${LEDGER}"
echo "==================================================================="; [ -z "${FL}" ]||exit 2; exit 0

#!/usr/bin/env bash
# Offline, hermetic test for SKS-005: restore script sections 1 and 6.
# Stub `openclaw` on PATH, fake HOME, fake dist dir. No live config, no network, no gateway.
# usage: restore-s1-s6-test.sh /path/to/openclaw-loop-protection-restore.sh <lane-work-dir>
set -uo pipefail
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:${PATH}"
SCRIPT="${1:?usage: restore-s1-s6-test.sh <script> <workdir>}"
WORKROOT="${2:?usage: restore-s1-s6-test.sh <script> <workdir>}"
T="$(/usr/bin/mktemp -d "${WORKROOT}/s1s6.XXXXXX")" || exit 2
PASS=0; FAILN=0
t_ok()   { PASS=$((PASS+1)); printf 'PASS  %s\n' "$1"; }
t_fail() { FAILN=$((FAILN+1)); printf 'FAIL  %s\n' "$1"; }
expect() { # expect <name> <condition-rc> ; rc 0 = pass
  if [ "$2" = "0" ]; then t_ok "$1"; else t_fail "$1"; fi
}

# ----- one scenario runner -------------------------------------------------------------------
# run_case <name> <version-string> <ld-enabled: true|false|unset|unknown> <entries-json|UNKNOWN|NONE> \
#          <main-enabled: false|true|unknown> <mode: check|apply>
# Result files: ${CASE}/out, ${CASE}/calls (ordered log of every openclaw invocation), ${CASE}/rc
run_case() {
  local name="$1" ver="$2" ld="$3" entries="$4" mainv="$5" mode="$6"
  CASE="${T}/${name}"; mkdir -p "${CASE}/home/.openclaw/service-env" "${CASE}/home/.openclaw/scripts" \
    "${CASE}/home/.openclaw/hooks" "${CASE}/home/.openclaw/extensions/ceo-routing-doctrine/dist" \
    "${CASE}/home/.claude" "${CASE}/bin" "${CASE}/dist" "${CASE}/tmp"
  printf '{"hooks":{}}\n' > "${CASE}/home/.claude/settings.json"
  printf 'echo stub\n' > "${CASE}/home/.openclaw/scripts/ensure-daily-memory-stub.sh"
  chmod +x "${CASE}/home/.openclaw/scripts/ensure-daily-memory-stub.sh"
  printf 'export default {};\n' > "${CASE}/home/.openclaw/extensions/ceo-routing-doctrine/dist/index.js"
  printf "OPENCLAW_TELEGRAM_SPOOLED_HANDLER_TIMEOUT_MS='1800000'\n" > "${CASE}/home/.openclaw/service-env/ai.openclaw.gateway.env"
  chmod 600 "${CASE}/home/.openclaw/service-env/ai.openclaw.gateway.env"
  : > "${CASE}/calls"
  printf '%s\n%s\n%s\n%s\n' 'HOW TO APPEND: do NOT read the target file first.' \
    'Store durable memories only in memory/YYYY-MM-DD.md (create memory/ if needed).' \
    'If memory/YYYY-MM-DD.md already exists, APPEND new content only and do not overwrite existing entries.' \
    'Treat workspace bootstrap/reference files such as MEMORY.md, DREAMS.md, SOUL.md, TOOLS.md, and AGENTS.md as read-only during this flush; never overwrite, replace, or edit them.' > "${CASE}/prompt.txt"
  printf '%s' "${entries}" > "${CASE}/entries.json"
  local emode="JSON"; case "${entries}" in UNKNOWN) emode=UNKNOWN ;; NONE) emode=NONE ;; esac
  cat > "${CASE}/bin/openclaw" <<STUB
#!/usr/bin/env bash
CALLS="${CASE}/calls"
printf '%s\n' "\$*" >> "\${CALLS}"
unknown() { echo "Error: Unknown config path: \$1" >&2; exit 1; }
if [ "\$1" = "--version" ]; then echo "${ver}"; exit 0; fi
if [ "\$1" = "config" ] && [ "\$2" = "set" ]; then exit 0; fi
if [ "\$1" = "config" ] && [ "\$2" = "get" ]; then
  case "\$3" in
    agents.defaults.compaction.memoryFlush.enabled) echo true ;;
    agents.defaults.compaction.memoryFlush.forceFlushTranscriptBytes) echo 0 ;;
    agents.defaults.compaction.memoryFlush.prompt) cat "${CASE}/prompt.txt" ;;
    tools.loopDetection.enabled)
      case "${ld}" in true) echo true ;; false) echo false ;; unset) exit 1 ;; *) unknown "\$3" ;; esac ;;
    tools.loopDetection.warningThreshold|tools.loopDetection.criticalThreshold|\\
    tools.loopDetection.globalCircuitBreakerThreshold|tools.loopDetection.unknownToolThreshold|\\
    tools.loopDetection.postCompactionGuard.windowSize|agents.main.tools.loopDetection) unknown "\$3" ;;
    agents.list) echo '[{"id":"main","tools":{"allow":["read","write"]}}]' ;;
    agents.entries)
      case "${emode}" in UNKNOWN) unknown "\$3" ;; NONE) exit 1 ;; *) cat "${CASE}/entries.json" ;; esac ;;
    agents.entries.main.tools.loopDetection.enabled)
      case "${mainv}" in false) echo false ;; true) echo true ;; *) exit 1 ;; esac ;;
    agents.entries.*.tools.loopDetection.enabled) exit 1 ;;
    plugins.load.paths) printf '["%s/.openclaw/extensions"]\n' "${CASE}/home" ;;
    plugins.allow) echo '["ceo-routing-doctrine"]' ;;
    plugins.entries.ceo-routing-doctrine.enabled) echo true ;;
    plugins.entries.ceo-routing-doctrine.hooks.allowPromptInjection) echo true ;;
    *) exit 1 ;;
  esac
  exit 0
fi
exit 1
STUB
  chmod +x "${CASE}/bin/openclaw"
  printf '#!/usr/bin/env bash\nif [ "${1:-}" = "-l" ]; then echo "*/5 * * * * /bin/bash /x/ensure-daily-memory-stub.sh"; fi\nexit 0\n' > "${CASE}/bin/crontab"
  chmod +x "${CASE}/bin/crontab"
  ( export HOME="${CASE}/home" TMPDIR="${CASE}/tmp" PATH="${CASE}/bin:${PATH}" OPENCLAW_DIST_DIR="${CASE}/dist"
    if [ "${mode}" = "apply" ]; then "${SCRIPT}" --apply; else "${SCRIPT}"; fi ) > "${CASE}/out" 2>&1
  echo $? > "${CASE}/rc"
}
has()    { /usr/bin/grep -F -q -- "$2" "${CASE}/$1"; }                 # has <file> <text>
hasnt()  { ! /usr/bin/grep -F -q -- "$2" "${CASE}/$1"; }
DEAD='warningThreshold|criticalThreshold|globalCircuitBreakerThreshold|unknownToolThreshold|windowSize|agents\.main\.tools|agents\.list'
no_dead_set() { ! /usr/bin/grep -E "^config set .*(${DEAD})" "${CASE}/calls" >/dev/null; }

# control for the instrument: a case whose call log MUST be non-empty and carry a known get
run_case control "OpenClaw 2026.9.6 (abc1234)" true '{"main":{}}' unknown check
[ -s "${CASE}/calls" ] && has calls "config get tools.loopDetection.enabled"; expect "control: stub log records the known get (instrument works)" $?

# ===== SECTION 1 ===============================================================================
run_case s1-native "OpenClaw 2026.9.6 (abc1234)" true '{"main":{}}' unknown check
has out "runaway-abort dist patch SKIPPED"; expect "S1 modern 2026.9.6: skip reason printed" $?
hasnt out "runaway-abort patch is ABSENT"; expect "S1 modern 2026.9.6: not treated as ABSENT" $?
hasnt out "UPSTREAM_CHANGED"; expect "S1 modern 2026.9.6: no UPSTREAM_CHANGED" $?
hasnt out "anchors NOT FOUND"; expect "S1 modern 2026.9.6: no HARDFAIL anchors message" $?

run_case s1-native-apply "OpenClaw 2026.9.6 (abc1234)" true '{"main":{}}' unknown apply
[ -z "$(ls -A "${CASE}/dist")" ]; expect "S1 modern apply: dist dir untouched" $?
[ ! -d "${CASE}/home/.openclaw-patch-backups" ] || ! /usr/bin/find "${CASE}/home/.openclaw-patch-backups" -type f | /usr/bin/grep -q tool-loop; expect "S1 modern apply: no tool-loop backup/patch attempted" $?

run_case s1-edge-exact "OpenClaw 2026.7.2" true '{"main":{}}' unknown check
has out "runaway-abort dist patch SKIPPED"; expect "S1 boundary 2026.7.2 exactly: skipped (native)" $?
run_case s1-newer-year "OpenClaw 2027.1.0-beta.1" true '{"main":{}}' unknown check
has out "runaway-abort dist patch SKIPPED"; expect "S1 2027.1.0-beta.1: skipped (native)" $?

run_case s1-old "OpenClaw 2026.6.9" true '{"main":{}}' unknown check
hasnt out "runaway-abort dist patch SKIPPED"; expect "S1 older 2026.6.9: NOT skipped, patch path kept" $?
{ has out "runaway-abort patch is ABSENT" || has out "anchors NOT FOUND" || has out "PARTIALLY"; }; expect "S1 older 2026.6.9: patch checker actually ran (empty dist => absent/hardfail)" $?

run_case s1-old-patch "OpenClaw 2026.7.1" true '{"main":{}}' unknown check
hasnt out "runaway-abort dist patch SKIPPED"; expect "S1 just below boundary 2026.7.1: not skipped" $?

run_case s1-undet "garbage-no-version" true '{"main":{}}' unknown check
has out "UNDETERMINED"; expect "S1 unparseable version: UNDETERMINED printed" $?
has out "runaway-abort dist patch SKIPPED"; expect "S1 unparseable version: skipped (fail-safe)" $?
hasnt out "runaway-abort patch is ABSENT"; expect "S1 unparseable version: never reaches patch path" $?
has out "NOT an all-clear" ; expect "S1 unparseable version: verdict is not ALL CLEAR" $?
hasnt out "VERDICT: ALL CLEAR"; expect "S1 unparseable version: no false all-clear line" $?

run_case s1-undet-apply "" true '{"main":{}}' unknown apply
[ -z "$(ls -A "${CASE}/dist")" ]; expect "S1 empty version apply: dist untouched" $?

# ===== SECTION 6 ===============================================================================
# 6a. dead keys answer Unknown config path; check mode must not fail on them
run_case s6-dead-check "OpenClaw 2026.9.6 (abc1234)" true '{"main":{}}' unknown check
no_dead_set; expect "S6a check: no config set at all for dead keys" $?
hasnt out "warningThreshold"; expect "S6a check: dead key warningThreshold not even mentioned/probed as drift" $?
hasnt out "criticalThreshold"; expect "S6a check: dead key criticalThreshold not mentioned" $?
hasnt out "globalCircuitBreakerThreshold"; expect "S6a check: dead key globalCircuitBreakerThreshold not mentioned" $?
hasnt out "unknownToolThreshold"; expect "S6a check: dead key unknownToolThreshold not mentioned" $?
hasnt out "windowSize"; expect "S6a check: dead key windowSize not mentioned" $?
hasnt out "agents.main.tools.loopDetection"; expect "S6a check: no read of the dead agents.main path reported" $?
hasnt calls "config get tools.loopDetection.warningThreshold"; expect "S6a check: dead key not probed at all" $?
has out "tools.loopDetection.enabled = true"; expect "S6a check: enabled==true reported ok" $?
[ "$(cat "${CASE}/rc")" = "0" ]; expect "S6a check: exit 0 on a healthy October box (rc=$(cat "${CASE}/rc"))" $?

# 6b. dead keys, apply mode: must neither fail nor set them
run_case s6-dead-apply "OpenClaw 2026.9.6 (abc1234)" true '{"main":{}}' unknown apply
no_dead_set; expect "S6b apply: dead keys never set" $?
! /usr/bin/grep -E '^config set' "${CASE}/calls" | /usr/bin/grep -q loopDetection; expect "S6b apply: no loopDetection write at all when guard is already on" $?
[ "$(cat "${CASE}/rc")" = "0" ]; expect "S6b apply: exit 0, script did not fail on dead keys (rc=$(cat "${CASE}/rc"))" $?
hasnt out "[ FAIL]"; expect "S6b apply: zero FAIL lines" $?

# 6c. explicit false per agent MUST be flagged
run_case s6-main-false "OpenClaw 2026.9.6 (abc1234)" true '{"main":{"tools":{"loopDetection":{"enabled":false}}}}' false check
has out "agents.entries.main.tools.loopDetection.enabled = false"; expect "S6c: explicit false on main flagged" $?
has out "[ FAIL]"; expect "S6c: reported as FAIL not OK" $?
hasnt out "no explicit per-agent loopDetection.enabled=false"; expect "S6c: no false all-clear line" $?
[ "$(cat "${CASE}/rc")" = "4" ]; expect "S6c: exit 4 hard fail (rc=$(cat "${CASE}/rc"))" $?
has out "NEEDS A HUMAN"; expect "S6c: manual action listed" $?

# 6d. same, apply: flagged, never auto-written
run_case s6-main-false-apply "OpenClaw 2026.9.6 (abc1234)" true '{"main":{"tools":{"loopDetection":{"enabled":false}}}}' false apply
has out "agents.entries.main.tools.loopDetection.enabled = false"; expect "S6d apply: still flagged" $?
! /usr/bin/grep -E '^config set .*agents\.entries' "${CASE}/calls" >/dev/null; expect "S6d apply: per-agent override never written" $?
[ "$(cat "${CASE}/rc")" = "4" ]; expect "S6d apply: still exit 4" $?

# 6e. a second agent, found by looping agents.entries.*
run_case s6-other-false "OpenClaw 2026.9.6 (abc1234)" true '{"main":{},"scout":{}}' unknown check
# main has no explicit value; scout needs its own answer, so build a stub variant by editing the case stub
/usr/bin/sed -i '' 's#agents.entries.\*.tools.loopDetection.enabled) exit 1 ;;#agents.entries.scout.tools.loopDetection.enabled) echo false ;;\
    agents.entries.*.tools.loopDetection.enabled) exit 1 ;;#' "${CASE}/bin/openclaw"
( export HOME="${CASE}/home" TMPDIR="${CASE}/tmp" PATH="${CASE}/bin:${PATH}" OPENCLAW_DIST_DIR="${CASE}/dist"; "${SCRIPT}" ) > "${CASE}/out" 2>&1; echo $? > "${CASE}/rc"
has out "agents.entries.scout.tools.loopDetection.enabled = false"; expect "S6e: explicit false on a NON-main agent flagged (loop over agents.entries.*)" $?
[ "$(cat "${CASE}/rc")" = "4" ]; expect "S6e: exit 4" $?

# 6f. unset override = inherits global; never flagged
run_case s6-inherit "OpenClaw 2026.9.6 (abc1234)" true '{"main":{},"scout":{}}' unknown check
hasnt out "= false"; expect "S6f: missing per-agent key is not flagged" $?
has out "no explicit per-agent loopDetection.enabled=false among"; expect "S6f: ok line names the agents probed" $?

# 6g. entries unreadable: UNDETERMINED, never a silent all-clear
run_case s6-entries-unknown "OpenClaw 2026.9.6 (abc1234)" true UNKNOWN unknown check
has out "agents.entries could not be listed"; expect "S6g: unlistable agents.entries reported UNDETERMINED" $?
hasnt out "VERDICT: ALL CLEAR"; expect "S6g: not an all-clear" $?

# 6g2. an agent id that cannot be probed safely must surface as UNDETERMINED, not vanish
run_case s6-odd-id "OpenClaw 2026.9.6 (abc1234)" true '{"main":{},"we ird.id":{}}' unknown check
has out "unprobeable names"; expect "S6g2: unprobeable agent id reported UNDETERMINED" $?
hasnt out "VERDICT: ALL CLEAR"; expect "S6g2: not an all-clear" $?

# 6h. global guard off / unset: drift in check, guarded write in apply
run_case s6-global-false-check "OpenClaw 2026.9.6 (abc1234)" false '{"main":{}}' unknown check
has out "tools.loopDetection.enabled = false (want true)"; expect "S6h check: global false is drift" $?
! /usr/bin/grep -q '^config set' "${CASE}/calls"; expect "S6h check: read-only, nothing written" $?
run_case s6-global-unset-apply "OpenClaw 2026.9.6 (abc1234)" unset '{"main":{}}' unknown apply
has calls "config set tools.loopDetection.enabled true --strict-json"; expect "S6h apply: unset guard turned on with --strict-json" $?
no_dead_set; expect "S6h apply: only the real key written" $?

# ===== GUARDED WRITE: get-before-set + REFUSE =================================================
# order check: for every `config set <path>` line there must be an earlier `config get <path>`
order_ok() {
  /usr/bin/awk '
    /^config get /{g[$3]=1}
    /^config set /{ if(!($3 in g)){bad=1; print "set without prior get: " $3} }
    END{exit bad?1:0}' "${CASE}/calls"
}
order_ok; expect "GW apply (guard unset): every config set is preceded by a config get of the same path" $?
run_case gw-order-full "OpenClaw 2026.9.6 (abc1234)" unset '{"main":{}}' unknown apply
order_ok; expect "GW second scenario: get-before-set holds" $?

# Unknown config path on the key we would write => REFUSE, no set, no FAIL
run_case gw-refuse "OpenClaw 2026.9.6 (abc1234)" unknown '{"main":{}}' unknown apply
has out "[REFUSE]"; expect "GW: Unknown config path => [REFUSE] reported" $?
has out "Unknown config path"; expect "GW: refuse reason names Unknown config path" $?
! /usr/bin/grep -q '^config set' "${CASE}/calls"; expect "GW: nothing written when the path is unknown" $?
hasnt out "[ FAIL]"; expect "GW: a refusal is not a FAIL" $?
hasnt out "VERDICT: ALL CLEAR"; expect "GW: refusal is never an all-clear" $?
hasnt out "VERDICT: all drift repaired"; expect "GW: refusal never reads as repaired" $?
[ "$(cat "${CASE}/rc")" = "3" ]; expect "GW: exit 3 (rc=$(cat "${CASE}/rc"))" $?

# every section's guarded write, forced into the unknown state, still REFUSES: swap memoryFlush answers
run_case gw-refuse-all "OpenClaw 2026.9.6 (abc1234)" true '{"main":{}}' unknown apply
/usr/bin/sed -i '' 's#agents.defaults.compaction.memoryFlush.enabled) echo true ;;#agents.defaults.compaction.memoryFlush.enabled) unknown "$3" ;;#' "${CASE}/bin/openclaw"
: > "${CASE}/calls"
( export HOME="${CASE}/home" TMPDIR="${CASE}/tmp" PATH="${CASE}/bin:${PATH}" OPENCLAW_DIST_DIR="${CASE}/dist"; "${SCRIPT}" --apply ) > "${CASE}/out" 2>&1
! /usr/bin/grep -q '^config set agents.defaults.compaction.memoryFlush.enabled' "${CASE}/calls"; expect "GW: memoryFlush.enabled unknown => not written (guard covers every cfg_set_json caller)" $?
has out "[REFUSE]"; expect "GW: memoryFlush refusal reported" $?

# ===== no secret / environment output ==========================================================
for c in "${T}"/*/; do
  /usr/bin/grep -E -q 'pm2 jlist|ps eww|launchctl print' "${c}out" 2>/dev/null && { t_fail "output of $(basename "$c") mentions a forbidden command"; }
done
t_ok "no case output mentions pm2 jlist / ps eww / launchctl print"

printf '\nTOTAL: %s pass, %s fail   (cases in %s)\n' "${PASS}" "${FAILN}" "${T}"
[ "${FAILN}" = "0" ]

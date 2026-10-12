#!/usr/bin/env bash
# Regression test for two fleet defects (D18, D19). Real functions are extracted
# verbatim from the real scripts, so a rename or a revert fails this test.
#
#   D18  32-command-center-setup/scripts/run-full-install.sh cc_install_locked_dependencies
#        ran `npm ci` with whatever node was first on PATH, so better-sqlite3 was
#        built for the wrong ABI. It must lead PATH with the node that
#        $DASHBOARD_DIR/scripts/lib/node-runtime.sh resolves.
#   D19  38-conversational-ai-system/scripts/04-register-crons.sh skipped an
#        existing cron by name and never looked at its agentId, so jobs stayed bound
#        to a removed agent ("agent is unavailable: main"). It must re-bind them
#        with `openclaw cron edit <id> --agent $ROUTING_AGENT_ID`.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLER="$ROOT/32-command-center-setup/scripts/run-full-install.sh"
REGISTER="$ROOT/38-conversational-ai-system/scripts/04-register-crons.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1"; }
extract() { awk -v pat="^$1\\\\(\\\\) \\\\{" '$0 ~ pat {p=1} p {print} p && /^}/ {exit}' "$2"; }

# ---------------------------------------------------------------- D18
echo "D18 - npm ci uses the Command Center node"
mkdir -p "$T/decoy" "$T/pinned" "$T/dash/scripts/lib"
for d in decoy pinned; do   # fake node: answers the resolver probe, names itself
  printf '#!/bin/sh\n[ "$1" = "-p" ] && { echo 127; exit 0; }\necho %s\n' "$d" > "$T/$d/node"; chmod +x "$T/$d/node"
done
# fake npm: records which node it would run (first node on its PATH)
printf '#!/bin/sh\ncommand -v node > "%s/npm-saw-node"\n' "$T" > "$T/decoy/npm"; chmod +x "$T/decoy/npm"
echo '{}' > "$T/dash/package-lock.json"
printf '#!/usr/bin/env bash\necho "%s/pinned/node"\n' "$T" > "$T/dash/scripts/lib/node-runtime.sh"
FRAG="$T/frag.sh"
{ extract log "$INSTALLER"; extract cc_install_locked_dependencies "$INSTALLER"; } > "$FRAG"
grep -q cc_install_locked_dependencies "$FRAG" || { echo "FATAL: cannot extract cc_install_locked_dependencies"; exit 2; }
run_ci() { ( LOG_FILE="$T/log"; DASHBOARD_DIR="$T/dash"; PATH="$T/decoy:/usr/bin:/bin"
             fail_install() { echo "fail_install: $1" >&2; exit 1; }
             . "$FRAG"; cc_install_locked_dependencies >/dev/null 2>&1 ); }
rm -f "$T/npm-saw-node"; run_ci
[ "$(cat "$T/npm-saw-node" 2>/dev/null)" = "$T/pinned/node" ] && ok "resolver's node leads PATH for npm ci" || bad "npm ci saw: $(cat "$T/npm-saw-node" 2>/dev/null)"
rm -f "$T/dash/scripts/lib/node-runtime.sh" "$T/npm-saw-node"; run_ci
[ "$(cat "$T/npm-saw-node" 2>/dev/null)" = "$T/decoy/node" ] && ok "older checkout without the resolver keeps the ambient node" || bad "fallback broken"
printf '#!/usr/bin/env bash\nexit 2\n' > "$T/dash/scripts/lib/node-runtime.sh"; rm -f "$T/npm-saw-node"; run_ci
[ "$(cat "$T/npm-saw-node" 2>/dev/null)" = "$T/decoy/node" ] && ok "resolver failure keeps the ambient node (does not abort)" || bad "resolver failure handling broken"

# ---------------------------------------------------------------- D19
echo "D19 - existing cron bound to a removed agent is re-bound"
mkdir -p "$T/bin"
cat > "$T/bin/openclaw" <<'SH'
#!/bin/sh
case "$1 $2" in
  "cron list") cat "$FAKE_JOBS" ;;
  "cron edit") echo "$*" >> "$FAKE_CALLS" ;;
esac
SH
chmod +x "$T/bin/openclaw"
export FAKE_JOBS="$T/jobs.json" FAKE_CALLS="$T/calls" OPENCLAW_CONFIG="$T/oc.json"
LIBFRAG="$T/lib.sh"
{ sed -n '/^s38_config_path() {/,/^}/p' "$ROOT/38-conversational-ai-system/scripts/lib-docker-tenant.sh"
  extract _rebind_cron_agent_if_orphaned "$REGISTER"; extract register_cron "$REGISTER"
  sed -n '/^oc_cron_list_json_flags() {/,/^}/p;/^oc_cron_present() {/,/^}/p' "$ROOT/shared-utils/cron-lib.sh"
  echo 'oc_cron_tombstoned() { return 1; }'; } > "$LIBFRAG"
grep -q _rebind_cron_agent_if_orphaned "$LIBFRAG" || { echo "FATAL: cannot extract _rebind_cron_agent_if_orphaned"; exit 2; }
run_reg() { : > "$FAKE_CALLS"; ( PATH="$T/bin:$PATH"; ROUTING_AGENT_ID=dept-communications
          _add_agent_cron() { echo "ADD $*" >> "$FAKE_CALLS"; }; _assert_cron_silent() { :; }
          . "$LIBFRAG"; register_cron analytics-weekly-digest "0 8 * * 1" "msg" >/dev/null 2>&1 ); }
JOB_MAIN='{"jobs":[{"id":"job-9","name":"analytics-weekly-digest","agentId":"main"}]}'
echo '{"agents":{"entries":{"dept-communications":{}}}}' > "$T/oc.json"; echo "$JOB_MAIN" > "$FAKE_JOBS"
run_reg
[ "$(cat "$FAKE_CALLS")" = "cron edit job-9 --agent dept-communications" ] && ok "job on removed 'main' is edited to the routing agent (and not re-added)" || bad "calls: $(cat "$FAKE_CALLS")"
echo '{"jobs":[{"id":"job-9","name":"analytics-weekly-digest"}]}' > "$FAKE_JOBS"; run_reg
[ "$(cat "$FAKE_CALLS")" = "cron edit job-9 --agent dept-communications" ] && ok "job with no agentId counts as main" || bad "calls: $(cat "$FAKE_CALLS")"
echo '{"agents":{"entries":{"main":{},"dept-communications":{}}}}' > "$T/oc.json"; echo "$JOB_MAIN" > "$FAKE_JOBS"; run_reg
[ ! -s "$FAKE_CALLS" ] && ok "job bound to a configured agent is left alone" || bad "edited a healthy job: $(cat "$FAKE_CALLS")"
echo '{"agents":{"list":[{"id":"main"}]}}' > "$T/oc.json"; run_reg
[ ! -s "$FAKE_CALLS" ] && ok "legacy agents.list roster is honoured" || bad "legacy roster ignored"
echo '{}' > "$T/oc.json"; run_reg
[ ! -s "$FAKE_CALLS" ] && ok "no agents configured: nothing is touched" || bad "edited with empty roster"

echo "D18/D19: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]

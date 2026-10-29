#!/usr/bin/env bash
# Regression test for two fleet defects (D18, D19). Real functions are extracted
# verbatim from the real scripts, so a rename or a revert fails this test.
#
#   D18  32-command-center-setup/scripts/run-full-install.sh cc_install_locked_dependencies
#        ran `npm ci` with whatever node was first on PATH, so better-sqlite3 was
#        built for the wrong ABI. It must use the node that
#        $DASHBOARD_DIR/scripts/lib/node-runtime.sh resolves.
#   D24  the D18 fix covered npm ci only; db:push/db:seed/build/contract-check still
#        ran on the PATH node (ERR_DLOPEN_FAILED 137 vs 147). cc_with_node now wraps
#        every such step, and puts ONLY a `node` symlink on PATH, so the image's old
#        /usr/local/bin/openclaw (same dir as the node) never shadows the box's.
#   D19  38-conversational-ai-system/scripts/04-register-crons.sh skipped an
#        existing cron by name and never looked at its agentId, so jobs stayed bound
#        to a removed agent ("agent is unavailable: main"). It must re-bind them
#        with `openclaw cron edit <id> --agent $ROUTING_AGENT_ID`.
#   #12  a user npm config with ignore-scripts=true made `npm ci` skip better-sqlite3's
#        build, so db:push died "migration incomplete". cc_ensure_sqlite_binding loads
#        the binding with the Command Center node and, only if it fails, runs
#        `npm rebuild better-sqlite3 --ignore-scripts=false` (that package, that one
#        command; the npm config is never touched), then loads it again.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLER="$ROOT/32-command-center-setup/scripts/run-full-install.sh"
REGISTER="$ROOT/38-conversational-ai-system/scripts/04-register-crons.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1"; }
extract() { awk -v pat="^$1\\\\(\\\\) \\\\{" '$0 ~ pat {p=1} p {print} p && /^}/ {exit}' "$2"; }

# ---------------------------------------------------------------- D18 / D24
echo "D18/D24 - every Command Center npm/node step uses the Command Center node"
mkdir -p "$T/decoy" "$T/pinned" "$T/dash/scripts/lib"
for d in decoy pinned; do   # fake node: answers the resolver probe, names itself
  printf '#!/bin/sh\n[ "$1" = "-p" ] && { echo 127; exit 0; }\necho %s\n' "$d" > "$T/$d/node"; chmod +x "$T/$d/node"
  # fake openclaw in BOTH dirs: the pinned dir stands for /usr/local/bin (image's old openclaw)
  printf '#!/bin/sh\necho %s\n' "$d" > "$T/$d/openclaw"; chmod +x "$T/$d/openclaw"
done
# fake npm (ambient only): records which node and which openclaw its PATH resolves
printf '#!/bin/sh\necho "$(node) $(openclaw) $*" > "%s/npm-saw"\n' "$T" > "$T/decoy/npm"; chmod +x "$T/decoy/npm"
echo '{}' > "$T/dash/package-lock.json"
printf '#!/usr/bin/env bash\necho "%s/pinned/node"\n' "$T" > "$T/dash/scripts/lib/node-runtime.sh"
FRAG="$T/frag.sh"
{ extract log "$INSTALLER"; extract cc_with_node "$INSTALLER"; extract cc_ensure_sqlite_binding "$INSTALLER"; extract cc_install_locked_dependencies "$INSTALLER"; } > "$FRAG"
grep -q cc_with_node "$FRAG" || { echo "FATAL: cannot extract cc_with_node"; exit 2; }
run_step() { ( LOG_FILE="$T/log"; DASHBOARD_DIR="$T/dash"; PATH="$T/decoy:/usr/bin:/bin"
             fail_install() { echo "fail_install: $1" >&2; exit 1; }
             . "$FRAG"; "$@" >/dev/null 2>&1 ); }
saw() { cat "$T/npm-saw" 2>/dev/null; }
rm -f "$T/npm-saw"; run_step cc_install_locked_dependencies
[ "$(saw | cut -d' ' -f1,2)" = "pinned decoy" ] && ok "npm ci: Command Center node, ambient (not image) openclaw" || bad "npm ci saw: $(saw)"
for step in "run db:push" "run db:seed" "run build"; do
  rm -f "$T/npm-saw"; run_step cc_with_node npm $step
  [ "$(saw)" = "pinned decoy $step" ] && ok "npm $step: Command Center node, ambient openclaw" || bad "npm $step saw: $(saw)"
done
[ "$( PATH="$T/decoy:/usr/bin:/bin"; LOG_FILE="$T/log"; DASHBOARD_DIR="$T/dash"; . "$FRAG"; cc_with_node node 2>/dev/null | tail -1 )" = "pinned" ] && ok "bare node step (contract check): Command Center node" || bad "bare node step used the wrong node"
leak="$(ls -d "${TMPDIR:-/tmp}"/cc-node.* 2>/dev/null | wc -l | tr -d ' ')"
[ "$leak" = 0 ] && ok "no temp shim dir left behind" || bad "$leak temp shim dirs leaked"
rm -f "$T/dash/scripts/lib/node-runtime.sh" "$T/npm-saw"; run_step cc_with_node npm run db:push
[ "$(saw | cut -d' ' -f1,2)" = "decoy decoy" ] && ok "older checkout without the resolver keeps the ambient node" || bad "fallback broken: $(saw)"
printf '#!/usr/bin/env bash\nexit 2\n' > "$T/dash/scripts/lib/node-runtime.sh"; rm -f "$T/npm-saw"; run_step cc_with_node npm run db:push
[ "$(saw | cut -d' ' -f1,2)" = "decoy decoy" ] && ok "resolver failure keeps the ambient node (does not abort)" || bad "resolver failure handling broken"
# static guard: every Command Center npm/node call in the installer goes through cc_with_node
bare="$(grep -nE '(\( *cd [^)]*&& *|^ *)(npm (ci|run) |node |bash [^ ]*run-bounded.sh [0-9]+ node )' "$INSTALLER" | grep -vE '^[0-9]+: *#|cc_with_node|log "' || true)"
[ -z "$bare" ] && ok "no bare npm ci/run or node call left in run-full-install.sh" || bad "bare call(s): $bare"

# ---------------------------------------------------------------- #12
echo "#12 - better-sqlite3 native binding is test-loaded and repaired after npm ci"
mkdir -p "$T/sq/pinned" "$T/sq/decoy" "$T/sq/dash/scripts/lib"
# fake node: the load probe passes only once $T/sq/built exists; records which node ran
printf '#!/bin/sh\necho pinned >> "%s/sq/node-saw"\n[ -f "%s/sq/built" ]\n' "$T" "$T" > "$T/sq/pinned/node"
printf '#!/bin/sh\necho decoy >> "%s/sq/node-saw"\nexit 0\n' "$T" > "$T/sq/decoy/node"
# fake npm: logs every call; `rebuild` builds the binding unless SQ_REBUILD_FAILS=1
cat > "$T/sq/decoy/npm" <<'SH'
#!/bin/sh
echo "$(readlink "$(command -v node)") $*" >> "$SQ_CALLS"
[ "$1" = "rebuild" ] && [ "$SQ_REBUILD_FAILS" != 1 ] && touch "$SQ_BUILT"
exit 0
SH
chmod +x "$T/sq/pinned/node" "$T/sq/decoy/node" "$T/sq/decoy/npm"
echo '{}' > "$T/sq/dash/package-lock.json"
printf '#!/usr/bin/env bash\necho "%s/sq/pinned/node"\n' "$T" > "$T/sq/dash/scripts/lib/node-runtime.sh"
sq_run() { # sq_run <with-package 0|1> <built-already 0|1> <rebuild-fails 0|1>; prints rc and leaves logs
  rm -rf "$T/sq/dash/node_modules" "$T/sq/built" "$T/sq/calls" "$T/sq/node-saw"; : > "$T/sq/calls"
  [ "$1" = 1 ] && mkdir -p "$T/sq/dash/node_modules/better-sqlite3"
  [ "$2" = 1 ] && touch "$T/sq/built"
  ( LOG_FILE="$T/sq/log"; DASHBOARD_DIR="$T/sq/dash"; PATH="$T/sq/decoy:/usr/bin:/bin"
    export SQ_CALLS="$T/sq/calls" SQ_BUILT="$T/sq/built" SQ_REBUILD_FAILS="$3"
    fail_install() { echo "fail_install: $1" > "$T/sq/failed"; exit 1; }
    rm -f "$T/sq/failed"; . "$FRAG"; cc_install_locked_dependencies >/dev/null 2>&1 ); echo $?
}
rc="$(sq_run 0 0 0)"
{ [ "$rc" = 0 ] && [ "$(wc -l < "$T/sq/calls" | tr -d ' ')" = 1 ] && [ ! -s "$T/sq/node-saw" ]; } && ok "no better-sqlite3 in node_modules: nothing probed, nothing rebuilt" || bad "absent package mishandled (rc=$rc)"
rc="$(sq_run 1 1 0)"
{ [ "$rc" = 0 ] && ! grep -q rebuild "$T/sq/calls"; } && ok "binding already loads: no rebuild" || bad "rebuilt a healthy binding (rc=$rc)"
rc="$(sq_run 1 0 0)"
{ [ "$rc" = 0 ] && grep -qx "$T/sq/pinned/node rebuild better-sqlite3 --ignore-scripts=false" "$T/sq/calls"; } \
  && ok "broken binding: npm rebuild better-sqlite3 --ignore-scripts=false on the Command Center node" || bad "rebuild call wrong (rc=$rc): $(cat "$T/sq/calls")"
[ "$(grep -c . "$T/sq/calls")" = 2 ] && ! grep -q "config" "$T/sq/calls" && ok "only npm ci + the one scoped rebuild ran; npm config never touched" || bad "unexpected npm calls: $(cat "$T/sq/calls")"
! grep -q decoy "$T/sq/node-saw" && ok "probe ran on the Command Center node, never the ambient one" || bad "probe used the ambient node"
rc="$(sq_run 1 0 1)"
{ [ "$rc" = 1 ] && grep -q "still does not load" "$T/sq/failed"; } && ok "binding still broken after rebuild: install stops (fail_install)" || bad "did not fail closed (rc=$rc)"

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

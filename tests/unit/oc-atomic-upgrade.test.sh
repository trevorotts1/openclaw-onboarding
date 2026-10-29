#!/usr/bin/env bash
# oc-atomic-upgrade.test.sh
#
# RUNTIME proof that scripts/oc-atomic-upgrade.sh actually ENFORCES the
# `agents.list` -> `agents.entries` migration inside the upgrade window, and
# actually ROLLS BACK when the window goes wrong.
#
# WHAT THIS TEST IS FOR. A previous test in this repo asserted that a safety cap
# was DEFINED and passed green while the runtime enforcement was dead. So none
# of the cases below read the source for a string. Every one of them RUNS the
# real script against a fixture box with stubbed `openclaw`/`npm`/`launchctl`,
# and then asserts on OBSERVED SIDE EFFECTS: which commands the stubs recorded,
# in what ORDER, and what the config and the installed version actually are
# afterwards.
#
# THE FOUR REQUIRED PROOFS
#   CONTROL      (1)  a CLEAN box still upgrades. Without this, "the legacy box
#                     did not upgrade" would be evidence of a broken harness
#                     rather than a working guard.
#   ASSERTION    (2)  a LEGACY box never ends up on the new binary with a legacy
#                     config -- it is either migrated or refused, never upgraded
#                     unmigrated. Includes the ORDERING proof: stop -> install ->
#                     migrate -> start, so no running gateway ever meets a config
#                     it rejects.
#   MUTATION     (5)  with ONLY the shape detector neutered, the SAME legacy box
#                     IS upgraded unmigrated -- proving cases (2)-(4) are caused
#                     by the detector and not by luck.
#   ROLLBACK    (6,7) a forced mid-procedure failure leaves the box with its
#                     ORIGINAL binary and its ORIGINAL config, gateway running.
#
# ⚠️ INTERPRETER. The fleet's Macs run stock /bin/bash 3.2.57; dev boxes run
# Homebrew bash 5.x. This file and the script it exercises are both written for
# 3.2 (no associative arrays, no `mapfile`, no heredoc nested inside `$( )` --
# that last one aborts at PARSE time on 3.2 and this repo has already shipped a
# dead gate that way). The interpreter actually in use is printed below and the
# CI workflow runs this file under both.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ATOMIC="$REPO_ROOT/scripts/oc-atomic-upgrade.sh"
MIGRATOR="$REPO_ROOT/scripts/oc-schema-migrate.py"
SUPHELPER="$REPO_ROOT/scripts/oc-supervisor-install.py"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== oc-atomic-upgrade: runtime enforcement, control, mutation, rollback ==="
echo "    interpreter: bash ${BASH_VERSION:-unknown}  (\$0 was run by: ${BASH:-unknown})"
echo "    script under test: $ATOMIC"
echo ""

[ -f "$ATOMIC" ]   || { echo "FATAL: $ATOMIC not found"; exit 1; }
[ -f "$MIGRATOR" ] || { echo "FATAL: $MIGRATOR not found"; exit 1; }
[ -f "$SUPHELPER" ] || { echo "FATAL: $SUPHELPER not found"; exit 1; }

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/oc-atomic-test.XXXXXX")"
# The script takes the box's shared installation lease. Point EVERY invocation in this file at a lease inside the
# sandbox: the default /tmp/openclaw-update.lock is the real box's, and two runs of this suite (or a real update)
# at once would refuse each other ("LOCK HELD ... displaced") and fail a case that has nothing to do with the lease.
export OPENCLAW_UPDATE_LEASE="$SANDBOX/openclaw-update.lock"
cleanup() {
  local _p f
  for _p in $(cat "$SANDBOX"/state*/spawned.pids 2>/dev/null); do kill "$_p" 2>/dev/null; done
  # orphan "gateway" processes a case spawned (BFR #33) must never outlive the run
  for f in "$SANDBOX"/state*/orphan_pid "$SANDBOX"/state*/extra_pids; do
    [ -f "$f" ] && for _p in $(cat "$f" 2>/dev/null); do kill -KILL "$_p" 2>/dev/null; done
  done
  rm -rf "$SANDBOX"
}
trap cleanup EXIT

OLD_V="2026.7.1"
NEW_V="2026.7.2-beta.7"

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────
# write_config <path> <kind>
#   clean          an `agents` block with defaults only -- no list, no entries
#   legacy         3 agents in the legacy array; main's workspace is declared
#                  ONLY inside the array, and agents.defaults.workspace points
#                  somewhere ELSE. This is the workspace trap: a migration that
#                  does not carry main's workspace across silently relocates
#                  CANON_DIR, the symlink target for the box's shared
#                  AGENTS.md/TOOLS.md/USER.md.
#   legacy-dup     two agents with the SAME id -- unmigratable without dropping
#                  one, so the transform must refuse rather than guess
#   entries        already on the new shape
write_config() {
  case "$2" in
    clean)
      cat > "$1" <<'EOF'
{
  "agents": {
    "defaults": {
      "workspace": "~/defaults-workspace",
      "models": {"primary": "pinned-model-do-not-touch"}
    }
  },
  "channels": {"telegram": {"enabled": true}},
  "otherTopLevel": {"keep": "me"}
}
EOF
      ;;
    legacy)
      cat > "$1" <<'EOF'
{
  "agents": {
    "defaults": {
      "workspace": "~/defaults-workspace",
      "models": {"primary": "pinned-model-do-not-touch"}
    },
    "list": [
      {"id": "main", "workspace": "~/real-canon-dir", "role": "primary"},
      {"id": "worker-a", "role": "dept"},
      {"id": "worker-b", "role": "dept", "nested": {"deep": [1, 2, 3]}}
    ]
  },
  "channels": {"telegram": {"enabled": true}},
  "otherTopLevel": {"keep": "me"}
}
EOF
      ;;
    legacy-dup)
      cat > "$1" <<'EOF'
{
  "agents": {
    "defaults": {"workspace": "~/defaults-workspace"},
    "list": [
      {"id": "main", "role": "primary"},
      {"id": "main", "role": "DUPLICATE"}
    ]
  },
  "channels": {"telegram": {"enabled": true}}
}
EOF
      ;;
    propose|bogus)   # clean agents + the CAN014 key: propose is rejected by the NEW build; bogus has no migration
      sed "s/^  \"channels\"/  \"skills\": {\"workshop\": {\"autonomous\": {\"mode\": \"$2\"}}},\n  \"channels\"/" > "$1" <<'EOF'
{
  "agents": {"defaults": {"workspace": "~/defaults-workspace"}},
  "channels": {"telegram": {"enabled": true}}
}
EOF
      ;;
    plugin)          # clean agents + a plugins block: codex (whose module will not load) and another plugin
      cat > "$1" <<'EOF'
{
  "agents": {"defaults": {"workspace": "~/defaults-workspace"}},
  "plugins": {
    "allow": ["codex", "other"],
    "entries": {
      "codex": {"enabled": true, "config": {"keep": "me", "n": [1, 2]}},
      "other": {"enabled": true}
    }
  },
  "channels": {"telegram": {"enabled": true}}
}
EOF
      ;;
    entries)
      cat > "$1" <<'EOF'
{
  "agents": {
    "defaults": {"workspace": "~/defaults-workspace"},
    "entries": {"main": {"workspace": "~/real-canon-dir", "role": "primary"}}
  },
  "channels": {"telegram": {"enabled": true}}
}
EOF
      ;;
  esac
}

sha_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
  else sha256sum "$1" 2>/dev/null | awk '{print $1}'; fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Stubs. Every one records what it was asked to do, so assertions are made on
# OBSERVED BEHAVIOUR and never on the source text of the script under test.
#
# make_stubs <dir> <state-dir> <schema-mode> [schema-fail-on-new]
#   schema-mode `versioned`: the OLD binary reports agents properties
#     ["defaults","list"] and the NEW one reports ["defaults","entries"] -- the
#     measured real-world behaviour this whole procedure is built around.
#   schema-fail-on-new: `1` makes `openclaw config schema` FAIL once the new
#     binary is installed, to force a mid-procedure failure.
# ─────────────────────────────────────────────────────────────────────────────
make_stubs() {
  local dir="$1" state="$2" schema_mode="$3" schema_fail="${4:-0}"
  mkdir -p "$dir" "$state"
  printf '%s' "$OLD_V" > "$state/version"
  printf '%s' "$NEW_V" > "$state/latest"
  printf '%s' "$schema_mode" > "$state/schema_mode"
  printf '%s' "$schema_fail" > "$state/schema_fail"
  printf '100' > "$state/pid"

  cat > "$dir/openclaw" <<EOF
#!/bin/bash
STATE="$state"
echo "openclaw \$*" >> "\$STATE/events"
V="\$(cat "\$STATE/version" 2>/dev/null)"
if [ "\${1:-}" = "--version" ]; then echo "\$V"; exit 0; fi
if [ "\${1:-}" = "config" ] && [ "\${2:-}" = "schema" ]; then
  if [ "\$(cat "\$STATE/schema_fail" 2>/dev/null)" = "1" ] && [ "\$V" = "$NEW_V" ]; then
    echo "schema unavailable" >&2; exit 1
  fi
  if [ "\$V" = "$NEW_V" ]; then
    echo '{"properties":{"agents":{"additionalProperties":false,"properties":{"defaults":{},"entries":{}}},"skills":{"properties":{"workshop":{"additionalProperties":false,"properties":{"autonomous":{"properties":{"mode":{"anyOf":[{"const":"off"},{"const":"auto"}]}}}}}}}}}'
  else
    echo '{"properties":{"agents":{"additionalProperties":false,"properties":{"defaults":{},"list":{}}},"skills":{"properties":{"workshop":{"additionalProperties":false,"properties":{"autonomous":{"properties":{"mode":{"anyOf":[{"const":"off"},{"const":"auto"},{"const":"propose"}]}}}}}}}}}'
  fi
  exit 0
fi
# doctor --fix (2026.10.8): records the context it ran in -- is the gateway loaded, which build is
# installed, is stdin at EOF -- so the test asserts on what doctor actually saw. \$STATE/doctor_mode:
#   (unset) ok | fail | fail_loaded (loads the gateway job, then fails) | fail_holder (a stale CLI grabs the state DB, then doctor fails) | hang |
#   audit (refuses like the real audit-logs step until the raw checkpoint rows are gone) | audit_always |
#   models (rewrites agents.defaults.model) | models_all (also the pins and an agent's own model) | touch (changes only an unrelated key)
if [ "\${1:-}" = "doctor" ]; then
  {
    echo "args=\$*"
    if [ -f "\$STATE/loaded_ai.openclaw.gateway" ]; then echo "gateway_loaded=yes"; else echo "gateway_loaded=no"; fi
    echo "version=\$V"
    read -r -t 2 _x; echo "stdin_rc=\$?"
  } >> "\$STATE/doctor_ctx"
  # BFR #33: an orphan gateway appears while doctor --fix runs and goes on holding the state database
  if [ "\${2:-}" = "--fix" ] && [ -f "\$STATE/spawn_orphan_on_doctor_fix" ] && [ ! -f "\$STATE/orphan_pid" ]; then
    ( exec -a "node \$HOME/sup/lib/node_modules/openclaw/dist/index.js gateway --token SECRET-ORPHAN-TOKEN" sleep 300 ) >/dev/null 2>&1 &
    echo \$! > "\$STATE/orphan_pid"; touch "\$STATE/realps_\$!"; echo \$! >> "\$STATE/lsof_holders"
  fi
  # BFR #24: with \$STATE/doctor_broken_plugin = <id>, doctor SPINS on that plugin's module (the same error
  # again and again, never returning) for as long as the plugin's entry is enabled. \$STATE/doctor_noise prints
  # one load error that names no plugin (exit 0); doctor_noise_fail does the same and exits 1.
  if [ -f "\$STATE/doctor_broken_plugin" ]; then
    ID="\$(cat "\$STATE/doctor_broken_plugin")"
    if python3 "$dir/plugin_enabled.py" "\$HOME/.openclaw/openclaw.json" "\$ID"; then
      for i in 1 2 3 4 5 6 7 8 9 10; do echo "[\$(date +%s)] Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/opt/oc/node_modules/openclaw/dist/plugin-sdk/session-store-runtime.js' imported from \$HOME/.openclaw/extensions/\$ID/dist/doctor-contract-api.js"; sleep 0.2; done
      sleep 300
      exit 1
    fi
  fi
  if [ -f "\$STATE/doctor_noise" ]; then echo "warn: optional dependency ERR_MODULE_NOT_FOUND for '/opt/x/optional.js' (ignored)"; fi
  if [ -f "\$STATE/doctor_noise_fail" ]; then echo "Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/opt/x/optional.js'" >&2; exit 1; fi
  DB="\$HOME/.openclaw/state/openclaw.sqlite"
  MODE="\$(cat "\$STATE/doctor_mode" 2>/dev/null)"
  case "\$MODE" in
    fail) echo "doctor: agent database migration failed" >&2; exit 1 ;;
    fail_loaded) touch "\$STATE/loaded_ai.openclaw.gateway"; echo "doctor: restarted the LaunchAgent, then failed" >&2; exit 1 ;;   # the real doctor restarts the job itself
    fail_holder)
      sleep 300 >/dev/null 2>&1 </dev/null &
      P=\$!
      echo "\$P" >> "\$STATE/lsof_holders"; echo "\$P" >> "\$STATE/spawned.pids"
      echo "node /opt/x/bin/openclaw status" > "\$STATE/ps_\$P.args"; echo "03:00:00" > "\$STATE/ps_\$P.etime"
      echo "doctor: boom" >&2; exit 1 ;;
    hang) sleep 30; exit 0 ;;
    audit|audit_always)
      N=0
      if [ -f "\$DB" ]; then
        N="\$(python3 -c 'import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("select count(*) from diagnostic_events where scope=?", ("migration.legacy-audit-raw",)).fetchone()[0])' "\$DB" 2>/dev/null || echo 0)"
      fi
      if [ "\$MODE" = "audit_always" ] || [ "\$N" -gt 0 ]; then
        echo "Audit logs: sanitized archive changed after checkpoint; refusing to import" >&2; exit 1
      fi ;;
    models) python3 -c 'import json,os;p=os.environ["HOME"]+"/.openclaw/openclaw.json";c=json.load(open(p));c["agents"]["defaults"]["model"]={"primary":"p/doctor-changed","fallbacks":[]};json.dump(c,open(p,"w"),indent=2)' ;;
    touch) python3 -c 'import json,os;p=os.environ["HOME"]+"/.openclaw/openclaw.json";c=json.load(open(p));c["doctorWasHere"]=True;json.dump(c,open(p,"w"),indent=2)' ;;
    models_all) python3 -c 'import json,os;p=os.environ["HOME"]+"/.openclaw/openclaw.json";c=json.load(open(p));a=c["agents"];d=a["defaults"];d["model"]={"primary":"p/doctor-changed","fallbacks":[]};d["models"]={"p/doctor-pin":{}};e=a.get("entries") or {};e.get("worker-a",{})["model"]="p/doctor-agent";c["doctorWasHere"]=True;json.dump(c,open(p,"w"),indent=2)' ;;
  esac
  echo "doctor: ok"; exit 0
fi
# CAN014: the NEW build rejects skills.workshop.autonomous.mode "propose" (2026.10.5).
# config validate --json is its verdict: rc 1 + {"valid":false,"issues":[...]}.
if [ "\${1:-}" = "config" ] && [ "\${2:-}" = "validate" ]; then
  CFG="\${OPENCLAW_CONFIG_PATH:-\$HOME/.openclaw/openclaw.json}"
  SD="\${OPENCLAW_STATE_DIR:-LIVE}"; [ "\$SD" = "\$HOME/.openclaw" ] && SD=LIVE
  echo "validate state=\$SD cfg=\$(basename "\$CFG") ro=\${OPENCLAW_CONFIG_READONLY:-0}" >> "\$STATE/events"
  # BFR #25: the REAL 2026.10.5 validate takes the sqlite maintenance lock even when read-only. Against
  # the LIVE state directory while the gateway job is loaded (serving), that stops the gateway answering.
  if [ "\$SD" = "LIVE" ] && [ -f "\$STATE/loaded_ai.openclaw.gateway" ]; then
    echo "validate-took-the-live-lock-while-serving" >> "\$STATE/lock_collisions"
    rm -f "\$STATE/loaded_ai.openclaw.gateway"; touch "\$STATE/healthz_down"
  fi
  if [ -f "\$STATE/validate_blind" ]; then echo '{"ok":true,"valid":true}'; exit 0; fi   # an instrument that cannot tell good from bad
  if grep -q '__oc_atomic_probe__' "\$CFG" 2>/dev/null; then
    echo '{"ok":false,"valid":false,"issues":[{"path":"agents","message":"Unrecognized key"}]}'; exit 1
  fi
  if [ -f "\$STATE/validate_fail" ] || { [ "\$V" = "$NEW_V" ] && grep -Eq '"mode": *"(propose|bogus)"' "\$CFG" 2>/dev/null; }; then
    echo '{"ok":false,"valid":false,"issues":[{"path":"skills.workshop.autonomous.mode","message":"Invalid input (allowed: off, auto)"}]}'
    exit 1
  fi
  echo '{"ok":true,"valid":true}'; exit 0
fi
exit 0
EOF

  cat > "$dir/npm" <<EOF
#!/bin/bash
STATE="$state"
echo "npm \$* #via=\$0" >> "\$STATE/events"
if [ "\${1:-}" = "view" ]; then cat "\$STATE/latest"; exit 0; fi
if [ "\${1:-}" = "install" ]; then
  # BFR #21: the invariant, witnessed. npm must NEVER run while the gateway job is loaded.
  [ -f "\$STATE/loaded_ai.openclaw.gateway" ] && echo "npm \$* while-gateway-loaded" >> "\$STATE/npm_while_loaded"
  # CAN015: two installs can exist. \`--prefix P\` writes the package the supervisor
  # launches (P/lib/node_modules/openclaw); a bare \`install -g\` writes only the
  # copy \`openclaw\` on PATH reports (\$STATE/version). With \$STATE/split, the two
  # are separate; without it, the PATH copy follows the prefix install.
  PFX=""; VER=""; prev=""
  for a in "\$@"; do
    case "\$a" in openclaw@*) VER="\${a#openclaw@}" ;; esac
    [ "\$prev" = "--prefix" ] && PFX="\$a"
    prev="\$a"
  done
  # v1.2.3: \`#!/usr/bin/env node\` makes real npm run under the FIRST node on PATH; record that one.
  command -v node >> "\$STATE/npm_node" 2>/dev/null
  # v1.2.3: a real preinstall failure: 100 lines of chatter, a token-looking line, then the reason
  if [ "\$VER" = "$NEW_V" ] && [ -f "\$STATE/npm_noisy_fail" ]; then
    i=0; while [ "\$i" -lt 100 ]; do i=\$((i+1)); echo "npmline \$i" >&2; done
    echo '//registry.npmjs.org/:_authToken=SECRETVALUE123' >&2
    echo '[openclaw] error: this OpenClaw release requires Node >=26.12.1.' >&2
    exit 1
  fi
  if [ -n "\$PFX" ]; then
    mkdir -p "\$PFX/lib/node_modules/openclaw"
    printf '{"name":"openclaw","version":"%s"}\n' "\$VER" > "\$PFX/lib/node_modules/openclaw/package.json"
    mkdir -p "\$PFX/lib/node_modules/openclaw/dist"; : > "\$PFX/lib/node_modules/openclaw/dist/index.js"   # a complete install ships the file the gateway launches
    [ -f "\$STATE/split" ] || printf '%s' "\$VER" > "\$STATE/version"
  elif [ -n "\$VER" ]; then
    printf '%s' "\$VER" > "\$STATE/version"
  fi
  echo "npm-install-witness \$*" >> "\$STATE/npm_installs"
  ENTRY="\$PFX/lib/node_modules/openclaw/dist/index.js"
  # an npm that dies half-way: new package.json written, the file the gateway launches gone
  if [ "\$VER" = "$NEW_V" ] && [ -f "\$STATE/npm_half_new" ]; then rm -f "\$ENTRY"; echo "npm ERR! killed" >&2; exit 1; fi
  # a reinstall of the OLD build that leaves the same half-written tree
  if [ "\$VER" = "$OLD_V" ] && [ -f "\$STATE/half_old_install" ]; then rm -f "\$ENTRY"; fi
  # after the NEW install, launchd stops honouring bootout (the rollback cannot hold the job stopped)
  if [ "\$VER" = "$NEW_V" ] && [ -f "\$STATE/arm_bootout_noop_after_install" ]; then touch "\$STATE/bootout_noop"; fi
  exit 0
fi
exit 0
EOF

  # launchctl: `print` succeeds only while the job is "loaded". With pid_flip
  # set, every print returns a DIFFERENT pid -- the crash-loop signature the
  # script's stability window is built to catch.
  # ⚠️ THIS STUB IS STRICTER THAN THE REAL TOOL, DELIBERATELY. It validates the
  # launchd domain target instead of just basename-ing it. The first version
  # used `basename` alone, which normalises `gui//ai.openclaw.gateway` down to a
  # valid label -- and so it silently PASSED a real defect in which UIDN was
  # assigned inside a command substitution and discarded, making every domain
  # target malformed. On a real Mac that bootout fails, the gateway is never
  # stopped, and the config gets migrated under a LIVE gateway. A stub that is
  # more forgiving than the tool it stands in for hides exactly the bug it was
  # written to catch, so malformed targets are recorded and made fatal here.
  cat > "$dir/launchctl" <<EOF
#!/bin/bash
STATE="$state"
echo "launchctl \$*" >> "\$STATE/events"
_assert_domain() {
  case "\$1" in
    gui/[0-9]*/*)
      case "\$1" in
        *//*) echo "MALFORMED-DOMAIN \$1" >> "\$STATE/bad_domains" ;;
      esac
      ;;
    gui/[0-9]*)  : ;;
    *) echo "MALFORMED-DOMAIN \$1" >> "\$STATE/bad_domains" ;;
  esac
}
# Real bootout is ASYNCHRONOUS. With bootout_delay set, it only schedules the
# unload: the job stays "loaded" until that many seconds have passed.
_settle() {
  if [ -f "\$STATE/unload_at_\$1" ] && [ "\$(date +%s)" -ge "\$(cat "\$STATE/unload_at_\$1")" ]; then
    rm -f "\$STATE/loaded_\$1" "\$STATE/unload_at_\$1"
  fi
}
case "\${1:-}" in
  print)
    _assert_domain "\${2:-}"
    LBL="\$(basename "\${2:-}")"
    _settle "\$LBL"
    [ -f "\$STATE/loaded_\$LBL" ] || exit 1
    # BFR #33: while an orphan gateway owns the state directory the real job exits 78 (EX_CONFIG): loaded, NO pid
    if [ "\$LBL" = "ai.openclaw.gateway" ] && [ -f "\$STATE/orphan_pid" ] && kill -0 "\$(cat "\$STATE/orphan_pid")" 2>/dev/null; then
      echo "	state = spawn scheduled"; exit 0
    fi
    P="\$(cat "\$STATE/pid" 2>/dev/null)"
    # crash-loop is a property of the NEW build; the restored old build is stable
    if [ -f "\$STATE/pid_flip" ] && [ "\$(cat "\$STATE/version" 2>/dev/null)" != "$OLD_V" ]; then P=\$((P+1)); printf '%s' "\$P" > "\$STATE/pid"; fi
    echo "	pid = \$P"
    exit 0
    ;;
  bootout)
    _assert_domain "\${2:-}"
    LBL="\$(basename "\${2:-}")"
    if [ -f "\$STATE/bootout_noop" ]; then exit 0; fi
    if [ -f "\$STATE/bootout_delay" ]; then
      echo \$(( \$(date +%s) + \$(cat "\$STATE/bootout_delay") )) > "\$STATE/unload_at_\$LBL"
      exit 0
    fi
    rm -f "\$STATE/loaded_\$LBL"
    exit 0
    ;;
  bootstrap)
    _assert_domain "\${2:-}"
    LBL="\$(basename "\${3:-}" .plist)"
    _settle "\$LBL"
    if [ -f "\$STATE/bootstrap_fail" ]; then exit 1; fi
    if [ -f "\$STATE/bootstrap_fail_once" ]; then rm -f "\$STATE/bootstrap_fail_once"; exit 1; fi    # the first start fails, the next works
    [ -f "\$STATE/loaded_\$LBL" ] && exit 17     # already loaded / still tearing down
    touch "\$STATE/loaded_\$LBL"
    rm -f "\$STATE/ps_etime"                    # a (re)started gateway is a brand-new process
    exit 0
    ;;
esac
exit 0
EOF

  # curl: the ONLY thing that may answer /healthz in this suite -- the real
  # curl would hit whatever gateway is live on the dev box's port 18789.
  cat > "$dir/curl" <<EOF
#!/bin/bash
STATE="$state"
echo "curl \$*" >> "\$STATE/events"
if [ -f "\$STATE/healthz_down" ]; then printf '000'; exit 7; fi
printf '200'
exit 0
EOF

  # Real docker on this dev box must never be consulted: `docker ps -a` can hang
  # when the daemon is down, and a stray container would change the detected
  # supervisor and silently invalidate every case below.
  cat > "$dir/docker" <<'EOF'
#!/bin/bash
exit 1
EOF
  cat > "$dir/hostname" <<'EOF'
#!/bin/bash
echo "a-box"
EOF
  # node: the supervisor plist names a bare `node`; the resolver finds this one. The only script this suite hands to
  # `node -e` is the FTS5 repair that runs just before doctor (v1.4.0): $state/fts_mode picks its answer
  # (unset = every database clean | fixed | skipped | fail | nosummary | hang). Each call is logged to events with
  # the node that ran it, the root it was given and whether the gateway job was loaded at that moment.
  cat > "$dir/node" <<EOF
#!/bin/bash
STATE="$state"
case "\$*" in
  *FTS_REPAIR_SUMMARY*)
    echo "node-fts \$(command -v node) root=\${!#} gateway_loaded=\$([ -f "\$STATE/loaded_ai.openclaw.gateway" ] && echo yes || echo no)" >> "\$STATE/events"
    echo "FTS_REPAIR_RUNTIME node=v26.13.0 sqlite=3.54.0"
    case "\$(cat "\$STATE/fts_mode" 2>/dev/null)" in
      fixed)     echo "FIXED /r/agents/main/agent/openclaw-agent.sqlite tables=memory_index_chunks_fts"
                 echo "FTS_REPAIR_SUMMARY total=1 clean=0 fixed=1 skipped=0 unchecked=0 fail=0"; exit 0 ;;
      skipped)   echo "SKIPPED /r/agents/main/agent/openclaw-agent.sqlite non-fts-findings=1 fts-tables= (nothing changed, doctor decides)"
                 echo "FTS_REPAIR_SUMMARY total=1 clean=0 fixed=0 skipped=1 unchecked=0 fail=0"; exit 0 ;;
      fail)      echo "FAIL /r/agents/main/agent/openclaw-agent.sqlite tables=t_fts integrity_check not ok after rebuild (rolled back)"
                 echo "FTS_REPAIR_SUMMARY total=1 clean=0 fixed=0 skipped=0 unchecked=0 fail=1"; exit 1 ;;
      nosummary) exit 0 ;;
      hang)      sleep 30; exit 0 ;;
    esac
    echo "CLEAN /r/agents/main/agent/openclaw-agent.sqlite"
    echo "FTS_REPAIR_SUMMARY total=1 clean=1 fixed=0 skipped=0 unchecked=0 fail=0"; exit 0 ;;
esac
exit 0
EOF
  # ps: the live gateway's command line is the plist's launch path (or $STATE/ps_args); its age is
  # $STATE/ps_etime (default 00:00 = just started, i.e. after every fixture file was written).
  # A spawned state-database holder has its own answers: $state/ps_<pid>.args and ps_<pid>.etime.
  cat > "$dir/ps" <<EOF
#!/bin/bash
# a pid a test registered (a real background process) is answered by the real ps
PSBIN=/bin/ps; [ -x "\$PSBIN" ] || PSBIN=/usr/bin/ps
for a in "\$@"; do case "\$a" in [0-9]*) [ -f "$state/realps_\$a" ] && exec "\$PSBIN" "\$@" ;; esac; done
P=""; prev=""
for a in "\$@"; do [ "\$prev" = "-p" ] && P="\$a"; prev="\$a"; done
# a pid with a registered parent answers \`ps -o ppid=\` (the OpenClaw app worker cases); everything else keeps the old answers
case "\$*" in *ppid*) if [ -n "\$P" ] && [ -f "$state/ps_\$P.ppid" ]; then cat "$state/ps_\$P.ppid"; exit 0; fi ;; esac
case "\$*" in
  *etime*) if [ -n "\$P" ] && [ -f "$state/ps_\$P.etime" ]; then cat "$state/ps_\$P.etime"
           elif [ -f "$state/ps_etime" ]; then cat "$state/ps_etime"; else echo "00:00"; fi ;;
  *) if [ -n "\$P" ] && [ -f "$state/ps_\$P.args" ]; then cat "$state/ps_\$P.args"
     elif [ -f "$state/ps_args" ]; then cat "$state/ps_args"; else echo "node \$HOME/sup/lib/node_modules/openclaw/dist/index.js gateway"; fi ;;
esac
EOF
  # lsof: the pids in $state/lsof_holders that are still alive "hold" the state database.
  cat > "$dir/lsof" <<EOF
#!/bin/bash
STATE="$state"
echo "lsof \$*" >> "\$STATE/events"
# \`lsof -F fan -p PID\` (the access mode of one holder): \$STATE/lsof_mode_PID holds the letter it opens the main database with
case "\$*" in *-F*)
  P=""; prev=""; for a in "\$@"; do [ "\$prev" = "-p" ] && P="\$a"; prev="\$a"; done
  if [ -n "\$P" ] && [ -f "\$STATE/lsof_mode_\$P" ]; then
    printf 'p%s\nf8\na%s\nn%s\nf9\nau\nn%s\n' "\$P" "\$(cat "\$STATE/lsof_mode_\$P")" "\$HOME/.openclaw/state/openclaw.sqlite" "\$HOME/.openclaw/state/openclaw.sqlite-wal"
    exit 0
  fi
  exit 1 ;;
esac
[ -f "\$STATE/lsof_holders" ] || exit 1
rc=1
while read -r p; do
  if [ -n "\$p" ] && kill -0 "\$p" 2>/dev/null; then echo "\$p"; rc=0; fi
done < "\$STATE/lsof_holders"
exit \$rc
EOF
  cat > "$dir/plugin_enabled.py" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
e = ((cfg.get("plugins") or {}).get("entries") or {}).get(sys.argv[2])
sys.exit(0 if isinstance(e, dict) and e.get("enabled") is not False else 1)
PYEOF
  # flock: a Linux host has it and macOS does not, so the script's lease takes a different branch on each (`exec 9<>lease`
  # plus `flock -n 9`). Every box here gets a flock that grants (refuses `-n` while $state/flock_busy exists), so the suite
  # runs the LINUX lease path on a Mac too. Calls go to $state/flock_calls, not events (several cases count and order events).
  cat > "$dir/flock" <<EOF
#!/bin/bash
echo "flock \$*" >> "$state/flock_calls"
[ "\${1:-}" = "-n" ] && [ -f "$state/flock_busy" ] && exit 1     # another process holds the lock
exit 0
EOF
  chmod +x "$dir/openclaw" "$dir/npm" "$dir/launchctl" "$dir/docker" "$dir/hostname" "$dir/curl" "$dir/node" "$dir/ps" "$dir/lsof" "$dir/flock"
}

# write_supervisor <home> <node> <prefix> <version>
#   the LaunchAgent plist (ProgramArguments: node, the openclaw dist entry, gateway)
#   and the package it launches, at <version>.
write_supervisor() {
  local home="$1" node="$2" prefix="$3" ver="$4"
  mkdir -p "$home/Library/LaunchAgents" "$prefix/lib/node_modules/openclaw/dist"
  printf '{"name":"openclaw","version":"%s"}\n' "$ver" > "$prefix/lib/node_modules/openclaw/package.json"
  : > "$prefix/lib/node_modules/openclaw/dist/index.js"
  cat > "$home/Library/LaunchAgents/ai.openclaw.gateway.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>ai.openclaw.gateway</string>
<key>ProgramArguments</key><array>
<string>$node</string>
<string>$prefix/lib/node_modules/openclaw/dist/index.js</string>
<string>gateway</string>
</array></dict></plist>
EOF
}

# set_installed <home> <state> <version> -- put the PATH copy AND the supervisor's package at <version>
set_installed() {
  printf '%s' "$3" > "$2/version"
  printf '{"name":"openclaw","version":"%s"}\n' "$3" > "$1/sup/lib/node_modules/openclaw/package.json"
}

# make_box <name> <config-kind> -> echoes the box HOME
make_box() {
  local home="$SANDBOX/$1"
  mkdir -p "$home/.openclaw/scripts" "$home/Library/LaunchAgents"
  write_config "$home/.openclaw/openclaw.json" "$2"
  write_supervisor "$home" node "$home/sup" "$OLD_V"
  echo "$home"
}

# run_atomic <home> <stubs> <state> [script-override] -- returns the script's rc
run_atomic() {
  local home="$1" stubs="$2" state="$3" script="${4:-$ATOMIC}"
  [ -n "${T_GATEWAY_DOWN:-}" ] || touch "$state/loaded_ai.openclaw.gateway"     # the gateway starts out running
  HOME="$home" PATH="$stubs:/usr/bin:/bin:/usr/sbin:/sbin" \
    OC_ATOMIC_QUIESCE_PROOF_SECONDS=1 OC_ATOMIC_STABILITY_SECONDS=1 \
    OC_ATOMIC_BOOTOUT_TIMEOUT="${T_BOOTOUT_TIMEOUT:-6}" OC_ATOMIC_HEALTH_TIMEOUT="${T_HEALTH_TIMEOUT:-4}" \
    OC_ATOMIC_SETTLE_SECONDS="${T_SETTLE:-1}" OC_ATOMIC_DOCTOR_TIMEOUT="${T_DOCTOR_TIMEOUT:-60}" \
    OC_ATOMIC_DOCTOR_LOOP_LINES="${T_LOOP_LINES:-}" OC_ATOMIC_FTS_TIMEOUT="${T_FTS_TIMEOUT:-}" \
    bash "$script" --upgrade 2>&1
}

# Order of two recorded events. Prints "OK" when `first` really precedes `second`.
event_order() {
  local state="$1" first="$2" second="$3"
  python3 - "$state/events" "$first" "$second" <<'PY'
import sys
try:
    lines = open(sys.argv[1], encoding='utf-8').read().splitlines()
except Exception:
    print("NOFILE"); raise SystemExit(0)
a = b = None
for i, l in enumerate(lines):
    if a is None and sys.argv[2] in l: a = i
    if b is None and sys.argv[3] in l: b = i
if a is None: print("MISSING-FIRST"); raise SystemExit(0)
if b is None: print("MISSING-SECOND"); raise SystemExit(0)
print("OK" if a < b else "WRONG-ORDER")
PY
}

cfg_shape() {
  python3 - "$1" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding='utf-8'))
except Exception as e:
    print("UNPARSEABLE"); raise SystemExit(0)
a = d.get("agents") or {}
if not isinstance(a, dict): print("NOTOBJ"); raise SystemExit(0)
if "list" in a and "entries" in a: print("BOTH")
elif "list" in a: print("LEGACY:%d" % len(a["list"]))
elif "entries" in a: print("ENTRIES:%d" % len(a["entries"]))
else: print("NEITHER")
PY
}

# make_state_db <home> -- the shared state database with the audit checkpoint rows doctor trips over:
# two raw-archive rows (the ones that may be dropped), the LIVE coordination lease scope and an
# unrelated scope (which must never be touched).
make_state_db() {
  mkdir -p "$1/.openclaw/state"
  python3 - "$1/.openclaw/state/openclaw.sqlite" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("create table diagnostic_events (id integer primary key, scope text, key text, payload text)")
c.executemany("insert into diagnostic_events(scope, key, payload) values (?, ?, ?)", [
    ("migration.legacy-audit-raw", "k1", "{\"offset\": 10}"),
    ("migration.legacy-audit-raw", "k2", "{\"offset\": 20}"),
    ("migration.legacy-audit", "lease", "live"),
    ("other.scope", "x", "y")])
c.commit()
PY
}
scope_count() {   # <db> <scope>
  python3 -c 'import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("select count(*) from diagnostic_events where scope=?", (sys.argv[2],)).fetchone()[0])' "$1" "$2"
}
# spawn_holder <state> <ps args> <ps etime> -- a REAL background process that lsof reports as holding the state DB.
spawn_holder() {
  local state="$1" p
  sleep 300 >/dev/null 2>&1 </dev/null &
  p=$!
  echo "$p" >> "$state/lsof_holders"; echo "$p" >> "$state/spawned.pids"
  printf '%s\n' "$2" > "$state/ps_$p.args"; printf '%s\n' "$3" > "$state/ps_$p.etime"
  echo "$p"
}
alive() { kill -0 "$1" 2>/dev/null; }
doctor_calls() { grep -c '^openclaw doctor' "$1/events" 2>/dev/null || true; }
set_models() {   # <home> -- give the config a model selection for doctor to (not) change
  python3 - "$1/.openclaw/openclaw.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
c["agents"]["defaults"]["model"] = {"primary": "p/one", "fallbacks": ["p/two"]}
json.dump(c, open(sys.argv[1], "w"), indent=2)
PY
}

# ═══════════════════════════════════════════════════════════════════════════
echo "--- (0) the shipped files parse under the interpreter running this test ---"
bash -n "$ATOMIC" 2>/dev/null && pass "0a: oc-atomic-upgrade.sh parses" \
  || fail "0a: oc-atomic-upgrade.sh does NOT parse"
python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$MIGRATOR" 2>/dev/null \
  && pass "0b: oc-schema-migrate.py parses" || fail "0b: oc-schema-migrate.py does NOT parse"

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (1) CONTROL: a CLEAN box still upgrades (proves the harness works) ---"
H1="$(make_box b1 clean)"; S1="$SANDBOX/stubs1"; ST1="$SANDBOX/state1"
make_stubs "$S1" "$ST1" versioned
CFG1="$H1/.openclaw/openclaw.json"; SHA1_BEFORE="$(sha_of "$CFG1")"
OUT1="$(run_atomic "$H1" "$S1" "$ST1")"; RC1=$?

if [ "$RC1" -eq 0 ]; then
  pass "1a: CONTROL — a clean box upgraded successfully (rc=0)"
else
  fail "1a: CONTROL FAILED — a clean box did NOT upgrade (rc=$RC1). Every 'did not upgrade' below now proves NOTHING. Output: $OUT1"
fi
if [ -f "$ST1/npm_installs" ]; then
  pass "1b: CONTROL — the binary install actually ran"
else
  fail "1b: CONTROL FAILED — npm never installed anything, so the harness is not exercising the upgrade path"
fi
if [ "$(cat "$ST1/version" 2>/dev/null)" = "$NEW_V" ]; then
  pass "1c: CONTROL — the measured version moved $OLD_V -> $NEW_V"
else
  fail "1c: CONTROL — version did not move (still $(cat "$ST1/version" 2>/dev/null))"
fi
if [ "$(sha_of "$CFG1")" = "$SHA1_BEFORE" ]; then
  pass "1d: a clean config was left BYTE-IDENTICAL (nothing migrated that did not need it)"
else
  fail "1d: the clean config was MODIFIED — the transform ran on a box with nothing to migrate"
fi
if [ -f "$ST1/loaded_ai.openclaw.gateway" ]; then
  pass "1e: the gateway was bootstrapped back and is loaded"
else
  fail "1e: the gateway was left DOWN after a successful upgrade"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (2) ASSERTION: a LEGACY box is MIGRATED, never upgraded unmigrated ---"
H2="$(make_box b2 legacy)"; S2="$SANDBOX/stubs2"; ST2="$SANDBOX/state2"
make_stubs "$S2" "$ST2" versioned
CFG2="$H2/.openclaw/openclaw.json"
WS2_BEFORE="$(python3 "$MIGRATOR" workspace "$CFG2")"
OUT2="$(run_atomic "$H2" "$S2" "$ST2")"; RC2=$?

if [ "$RC2" -eq 0 ]; then
  pass "2a: the legacy box completed the atomic upgrade (rc=0)"
else
  fail "2a: the legacy box did not complete (rc=$RC2). Output: $OUT2"
fi
SHAPE2="$(cfg_shape "$CFG2")"
if [ "$SHAPE2" = "ENTRIES:3" ]; then
  pass "2b: the config is now \`agents.entries\` with all 3 agents ($SHAPE2)"
else
  fail "2b: expected ENTRIES:3, observed $SHAPE2 — the box is NOT correctly migrated"
fi
if [ -f "$ST2/npm_installs" ] && [ "$SHAPE2" = "ENTRIES:3" ]; then
  pass "2c: the binary was upgraded AND the config migrated — never one without the other"
elif [ -f "$ST2/npm_installs" ]; then
  fail "2c: THE LANDMINE — the binary was upgraded while the config is still $SHAPE2"
else
  fail "2c: the binary was never upgraded, so this case proves nothing"
fi

# ORDERING. The whole design rests on this: the config is only ever rewritten
# while nothing is running, and only after the binary that reads it is on disk.
O_A="$(event_order "$ST2" "bootout" "npm install")"
O_B="$(event_order "$ST2" "npm install" "bootstrap")"
[ "$O_A" = "OK" ] && pass "2d: ORDER — the gateway was stopped BEFORE the binary changed ($O_A)" \
                  || fail "2d: ORDER VIOLATION — bootout did not precede npm install ($O_A)"
[ "$O_B" = "OK" ] && pass "2e: ORDER — the binary changed BEFORE the gateway was started again ($O_B)" \
                  || fail "2e: ORDER VIOLATION — npm install did not precede bootstrap ($O_B)"

# WORKSPACE TRAP. main's workspace lived ONLY in the legacy array, and
# agents.defaults.workspace points somewhere else. If the resolved workspace
# moved, CANON_DIR moved with it.
WS2_AFTER="$(python3 "$MIGRATOR" workspace "$CFG2")"
if [ -n "$WS2_BEFORE" ] && [ "$WS2_BEFORE" = "$WS2_AFTER" ]; then
  pass "2f: WORKSPACE TRAP — the resolved workspace is unchanged across the migration ($WS2_AFTER)"
else
  fail "2f: WORKSPACE MOVED: '$WS2_BEFORE' -> '$WS2_AFTER' — CANON_DIR would have been relocated"
fi
if python3 - "$CFG2" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
a = d["agents"]
assert a["defaults"]["models"]["primary"] == "pinned-model-do-not-touch", "model pins were altered"
assert d["otherTopLevel"] == {"keep": "me"}, "an unrelated top-level key was altered"
assert d["channels"]["telegram"]["enabled"] is True, "channels were altered"
assert "id" not in a["entries"]["main"], "id was left inside the entry body"
assert a["entries"]["worker-b"]["nested"] == {"deep": [1, 2, 3]}, "nested entry data was lost"
PY
then
  pass "2g: model pins, channels, unrelated top-level keys and nested entry data all survived intact"
else
  fail "2g: the migration altered something outside the schema key"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (3) ASSERTION: an UNMIGRATABLE legacy box is REFUSED, not upgraded ---"
H3="$(make_box b3 legacy-dup)"; S3="$SANDBOX/stubs3"; ST3="$SANDBOX/state3"
make_stubs "$S3" "$ST3" versioned
CFG3="$H3/.openclaw/openclaw.json"; SHA3_BEFORE="$(sha_of "$CFG3")"
OUT3="$(run_atomic "$H3" "$S3" "$ST3")"; RC3=$?

[ "$RC3" -eq 78 ] && pass "3a: a config with duplicate agent ids was REFUSED (rc=78)" \
                  || fail "3a: expected rc=78 on an unmigratable config, got $RC3. Output: $OUT3"
if [ "$(sha_of "$CFG3")" = "$SHA3_BEFORE" ]; then
  pass "3b: the config is BYTE-IDENTICAL to before — nothing was guessed or dropped"
else
  fail "3b: the config was MODIFIED on a refusal path"
fi
if [ "$(cat "$ST3/version" 2>/dev/null)" = "$OLD_V" ]; then
  pass "3c: the binary was rolled back to $OLD_V — the box is not left on a build its config breaks"
else
  fail "3c: the box is left on $(cat "$ST3/version" 2>/dev/null) with an unmigrated config — THE LANDMINE"
fi
[ -f "$ST3/loaded_ai.openclaw.gateway" ] && pass "3d: the gateway is running again after the refusal" \
                                         || fail "3d: the box was left DARK after a refusal"

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (4) a box already on the new shape is a no-op, not a re-migration ---"
H4="$(make_box b4 entries)"; S4="$SANDBOX/stubs4"; ST4="$SANDBOX/state4"
make_stubs "$S4" "$ST4" versioned
CFG4="$H4/.openclaw/openclaw.json"; SHA4_BEFORE="$(sha_of "$CFG4")"
OUT4="$(run_atomic "$H4" "$S4" "$ST4")"; RC4=$?
[ "$RC4" -eq 0 ] && pass "4a: an already-migrated box upgrades cleanly (rc=0)" \
                 || fail "4a: rc=$RC4 on an already-migrated box. Output: $OUT4"
[ "$(sha_of "$CFG4")" = "$SHA4_BEFORE" ] \
  && pass "4b: its config was left BYTE-IDENTICAL" \
  || fail "4b: its config was rewritten — the transform ran twice"

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (5) MUTATION PROOF: neuter ONLY the shape detector ---"
# If this case FAILS, then cases (2)/(3) were passing for some reason other than
# the detector, and this whole test has stopped measuring runtime enforcement.
# ⚠️ THE MUTANT MUST LIVE BESIDE ITS ENGINE. oc-atomic-upgrade.sh resolves
# oc-schema-migrate.py relative to its OWN directory, so a mutated copy dropped
# anywhere else refuses early with "the transform engine is MISSING" -- a
# refusal that has nothing to do with the mutation. The first draft of this case
# did exactly that and reported a green-looking "the block held", while actually
# measuring a broken sandbox. So the mutant gets a scripts/ dir of its own, with
# the REAL, UNMUTATED engine next to it: the shape detector is then the only
# thing that differs between this run and case (2).
MUT_DIR="$SANDBOX/mutscripts"
mkdir -p "$MUT_DIR"
cp "$MIGRATOR" "$MUT_DIR/oc-schema-migrate.py"
cp "$SUPHELPER" "$MUT_DIR/oc-supervisor-install.py"
MUT="$MUT_DIR/oc-atomic-upgrade.sh"
MUT_SRC="$ATOMIC" MUT_DST="$MUT" python3 - <<'PY'
import os, sys
s = open(os.environ["MUT_SRC"], encoding="utf-8").read()
# The ONE line that turns the detector's exit code into the shape verdict.
mutated = s.replace('      10) shape="LEGACY_LIST" ;;',
                    '      10) shape="CLEAN" ;;   # MUTATED: detection removed')
if mutated == s:
    sys.stderr.write("MUTATION DID NOT APPLY — the detector line was not found\n")
    sys.exit(1)
open(os.environ["MUT_DST"], "w").write(mutated)
PY
MUT_RC=$?
[ "$MUT_RC" -eq 0 ] && pass "5a: the mutation applied (the detector line exists and was neutered)" \
                    || fail "5a: the mutation did NOT apply — the detector line was not found in the shipped script"

# SANDBOX CONTROL. Run the UNMUTATED script from the very same directory the
# mutant lives in, against the same fixture. If this does not migrate, the
# sandbox itself is broken and the mutation result below means nothing.
cp "$ATOMIC" "$MUT_DIR/oc-atomic-upgrade.control.sh"
H5C="$(make_box b5c legacy)"; S5C="$SANDBOX/stubs5c"; ST5C="$SANDBOX/state5c"
make_stubs "$S5C" "$ST5C" versioned
OUT5C="$(run_atomic "$H5C" "$S5C" "$ST5C" "$MUT_DIR/oc-atomic-upgrade.control.sh")"; RC5C=$?
SHAPE5C="$(cfg_shape "$H5C/.openclaw/openclaw.json")"
if [ "$SHAPE5C" = "ENTRIES:3" ] && [ -f "$ST5C/npm_installs" ]; then
  pass "5b: SANDBOX CONTROL — the UNMUTATED script run from the mutant's own directory still migrates ($SHAPE5C), so the only variable below is the mutation"
else
  fail "5b: SANDBOX CONTROL FAILED — the unmutated script did not migrate from $MUT_DIR (config=$SHAPE5C, rc=$RC5C). The mutation result below measures the sandbox, not the detector. Output: $OUT5C"
fi

H5="$(make_box b5 legacy)"; S5="$SANDBOX/stubs5"; ST5="$SANDBOX/state5"
make_stubs "$S5" "$ST5" versioned
CFG5="$H5/.openclaw/openclaw.json"
OUT5="$(run_atomic "$H5" "$S5" "$ST5" "$MUT")"; RC5=$?
SHAPE5="$(cfg_shape "$CFG5")"

# Guard against the exact false pass this case shipped with once: a mutant that
# aborts for an unrelated reason looks like "the guard held".
case "$OUT5" in
  *"transform engine is MISSING"*|*"npm ("*"is NOT ON PATH"*|*"CLI is NOT ON PATH"*)
    fail "5c: the mutated run aborted for an UNRELATED reason (missing engine / missing tool), so it never reached the detector. This case is measuring the sandbox. Output: $OUT5"
    ;;
  *)
    if [ -f "$ST5/npm_installs" ] && [ "${SHAPE5%%:*}" = "LEGACY" ]; then
      pass "5c: MUTATION PROOF — with ONLY the shape detector neutered, the SAME legacy box IS upgraded UNMIGRATED (binary=$(cat "$ST5/version"), config=$SHAPE5). That is the landmine reproduced on demand, so the block in (2)/(3) is caused by the detector and not by luck."
    else
      fail "5c: the mutated script did not produce the unguarded outcome (installs=$([ -f "$ST5/npm_installs" ] && echo yes || echo no), config=$SHAPE5, rc=$RC5) — cases (2)/(3) are NOT measuring the detector and this test proves nothing. Output: $OUT5"
    fi
    ;;
esac

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (6) ROLLBACK: mid-procedure failure AFTER the binary changed ---"
# The schema probe fails once the NEW binary is installed. The binary has
# already changed at that point, so the rollback must undo it.
H6="$(make_box b6 legacy)"; S6="$SANDBOX/stubs6"; ST6="$SANDBOX/state6"
make_stubs "$S6" "$ST6" versioned 1
CFG6="$H6/.openclaw/openclaw.json"; SHA6_BEFORE="$(sha_of "$CFG6")"
OUT6="$(run_atomic "$H6" "$S6" "$ST6")"; RC6=$?

[ "$RC6" -eq 78 ] && pass "6a: an unanswerable schema probe REFUSED the upgrade (rc=78)" \
                  || fail "6a: expected rc=78, got $RC6. Output: $OUT6"
if [ "$(cat "$ST6/version" 2>/dev/null)" = "$OLD_V" ]; then
  pass "6b: ROLLBACK — the ORIGINAL binary $OLD_V was reinstalled"
else
  fail "6b: ROLLBACK FAILED — the box is left on $(cat "$ST6/version" 2>/dev/null)"
fi
[ "$(sha_of "$CFG6")" = "$SHA6_BEFORE" ] \
  && pass "6c: ROLLBACK — the config is BYTE-IDENTICAL to before" \
  || fail "6c: ROLLBACK FAILED — the config differs from before"
[ -f "$ST6/loaded_ai.openclaw.gateway" ] \
  && pass "6d: ROLLBACK — the gateway was started again (the box is not dark)" \
  || fail "6d: ROLLBACK FAILED — the box was left DARK"

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (7) the gateway CRASH-LOOPS after a completed migration AND doctor: the NEW binary stays (v1.4.0) ---"
# Binary changed, config migrated, doctor --fix exited 0 (so the agent/session databases are migrated), then the
# gateway fails to stay up. A changing pid across the stability window is the crash-loop signature (exit 78 +
# KeepAlive respawn every ~11s). Before v1.4.0 this reinstalled the old build and restored the legacy config over
# migrated databases; now the previous build never goes back: one clean restart of the NEW build, and when that
# is still dark the script says so loudly (rc 70) and keeps the migrated config. The rollback-and-restore of
# everything is covered where it can still happen: any failure BEFORE doctor completes (6, 18h-k, KB-e, Fts-d..f).
H7="$(make_box b7 legacy)"; S7="$SANDBOX/stubs7"; ST7="$SANDBOX/state7"
make_stubs "$S7" "$ST7" versioned
CFG7="$H7/.openclaw/openclaw.json"; SHA7_BEFORE="$(sha_of "$CFG7")"
touch "$ST7/pid_flip" "$ST7/healthz_down"
OUT7="$(T_HEALTH_TIMEOUT=3 run_atomic "$H7" "$S7" "$ST7")"; RC7=$?

if [ "$RC7" -eq 70 ] && grep -q 'pid CHANGED during the stability window' <<<"$OUT7" && grep -q 'new binary unhealthy after migration; rollback unsafe' <<<"$OUT7"; then
  pass "7a: a crash-looping gateway after doctor was DETECTED; the new build got one clean restart and, still dark, the script failed loudly (rc=70)"
else
  fail "7a: expected rc=70 on a crash-loop after doctor, got $RC7. Output: $OUT7"
fi
SHAPE7="$(cfg_shape "$CFG7")"
if [ "$(cfg_shape "$CFG7" | cut -d: -f1)" = "ENTRIES" ] && [ "$(sha_of "$CFG7")" != "$SHA7_BEFORE" ]; then
  pass "7b: the MIGRATED config stays ($SHAPE7): the legacy list is not put back under a build that rejects it"
else
  fail "7b: the config was changed back to $SHAPE7 after doctor completed"
fi
if [ "$(cat "$ST7/version" 2>/dev/null)" = "$NEW_V" ] && ! grep -q "openclaw@$OLD_V" "$ST7/npm_installs" 2>/dev/null; then
  pass "7c: the NEW binary $NEW_V stays; the previous build was never reinstalled"
else
  fail "7c: the box is on $(cat "$ST7/version" 2>/dev/null)"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (8) QUIESCE: a gateway that will not stop must abort the procedure ---"
H8="$(make_box b8 legacy)"; S8="$SANDBOX/stubs8"; ST8="$SANDBOX/state8"
make_stubs "$S8" "$ST8" versioned
touch "$ST8/bootout_noop"     # bootout exits 0 but the job stays loaded
CFG8="$H8/.openclaw/openclaw.json"; SHA8_BEFORE="$(sha_of "$CFG8")"
OUT8="$(run_atomic "$H8" "$S8" "$ST8")"; RC8=$?
[ "$RC8" -eq 78 ] && pass "8a: a job still loaded after bootout ABORTED the procedure (rc=78)" \
                  || fail "8a: expected rc=78 when the gateway will not stop, got $RC8"
if [ ! -f "$ST8/npm_installs" ]; then
  pass "8b: the binary was NEVER touched — the abort happened before anything changed"
else
  fail "8b: the binary was installed even though the gateway never stopped"
fi
[ "$(sha_of "$CFG8")" = "$SHA8_BEFORE" ] \
  && pass "8c: the config is byte-identical — a live gateway's config was never rewritten" \
  || fail "8c: the config was rewritten while the gateway was still loaded"

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (11) CAN001: async bootout must be POLLED, and rollback must PROVE the gateway is back ---"
# Roll 20261019 canary: bootout returned, the job was still tearing down 2s
# later, the script refused ("STILL LOADED"), rolled back WITHOUT re-bootstrapping
# the gateway, and printed "exactly as it was found" -- the gateway was gone
# (launchctl: Could not find service, /healthz 000).

# 11a. bootout takes 4s to complete (longer than the old fixed `sleep 2`).
H11="$(make_box b11 clean)"; S11="$SANDBOX/stubs11"; ST11="$SANDBOX/state11"
make_stubs "$S11" "$ST11" versioned
echo 4 > "$ST11/bootout_delay"
OUT11="$(T_BOOTOUT_TIMEOUT=10 run_atomic "$H11" "$S11" "$ST11")"; RC11=$?
if [ "$RC11" -eq 0 ] && [ -f "$ST11/npm_installs" ]; then
  pass "11a: a bootout that completes after 4s is POLLED to completion and the upgrade proceeds (rc=0)"
else
  fail "11a: slow-but-successful bootout was treated as a failure (rc=$RC11, installs=$([ -f "$ST11/npm_installs" ] && echo yes || echo no)). Output: $OUT11"
fi

# 11b. the incident replay: slow bootout + a later failure -> rollback must leave
# the gateway loaded, answering /healthz, and say so truthfully.
H11B="$(make_box b11b legacy)"; S11B="$SANDBOX/stubs11b"; ST11B="$SANDBOX/state11b"
make_stubs "$S11B" "$ST11B" versioned 1
echo 4 > "$ST11B/bootout_delay"
OUT11B="$(T_BOOTOUT_TIMEOUT=10 run_atomic "$H11B" "$S11B" "$ST11B")"; RC11B=$?
# Let the slow bootout finish, THEN ask launchd (the stub) for the job's state.
# Checking only at script exit is how the canary missed it: the gateway looked
# fine until the teardown that had been issued earlier completed.
sleep 5
if [ "$RC11B" -eq 78 ] && "$S11B/launchctl" print "gui/501/ai.openclaw.gateway" >/dev/null 2>&1 \
   && [ "$(cat "$ST11B/version")" = "$OLD_V" ]; then
  pass "11b: slow bootout + forced failure -> rolled back (rc=78), gateway loaded, binary $OLD_V"
else
  fail "11b: rollback after a slow bootout left the box wrong (rc=$RC11B, loaded=$("$S11B/launchctl" print "gui/501/ai.openclaw.gateway" >/dev/null 2>&1 && echo yes || echo no), version=$(cat "$ST11B/version")). Output: $OUT11B"
fi
case "$OUT11B" in
  *"PROVEN back"*) pass "11c: the rollback output says the gateway was PROVEN back (loaded + pid + /healthz 200)" ;;
  *) fail "11c: no 'PROVEN back' line -- the restore was claimed without proof. Output: $OUT11B" ;;
esac
grep -q 'healthz' "$ST11B/events" 2>/dev/null \
  && pass "11d: /healthz was actually queried during the rollback" \
  || fail "11d: the rollback never queried /healthz"

# 11e. FALSE-CLAIM GUARD: the rollback cannot re-load the gateway. It must NOT
# claim success; it must exit 70 and name the job as down.
H11E="$(make_box b11e legacy)"; S11E="$SANDBOX/stubs11e"; ST11E="$SANDBOX/state11e"
make_stubs "$S11E" "$ST11E" versioned 1
OUT11E="$(
  touch "$ST11E/loaded_ai.openclaw.gateway"
  # bootstrap works for the first start only if we let it; here it never does.
  touch "$ST11E/bootstrap_fail"
  HOME="$H11E" PATH="$S11E:/usr/bin:/bin:/usr/sbin:/sbin" \
    OC_ATOMIC_QUIESCE_PROOF_SECONDS=1 OC_ATOMIC_STABILITY_SECONDS=1 \
    OC_ATOMIC_BOOTOUT_TIMEOUT=3 OC_ATOMIC_HEALTH_TIMEOUT=3 \
    bash "$ATOMIC" --upgrade 2>&1
)"; RC11E=$?
if [ "$RC11E" -eq 70 ]; then
  pass "11e: a gateway that cannot be re-loaded -> rollback exits 70 (needs a human), not 78"
else
  fail "11e: expected rc=70 when the gateway cannot be re-loaded, got $RC11E. Output: $OUT11E"
fi
case "$OUT11E" in
  *"exactly as it was found"*|*"gateway started again"*|*"rollback complete"*)
    fail "11f: FALSE CLAIM -- the rollback reported success while the gateway is not loaded. Output: $OUT11E" ;;
  *) pass "11f: no false 'rollback complete / exactly as it was found / started again' claim was printed" ;;
esac

# 11g. gateway re-loads fine but /healthz never answers 200 -> must NOT claim success.
H11G="$(make_box b11g legacy)"; S11G="$SANDBOX/stubs11g"; ST11G="$SANDBOX/state11g"
make_stubs "$S11G" "$ST11G" versioned 1
touch "$ST11G/healthz_down"
OUT11G="$(T_HEALTH_TIMEOUT=3 run_atomic "$H11G" "$S11G" "$ST11G")"; RC11G=$?
if [ "$RC11G" -eq 70 ]; then
  pass "11g: job loaded but /healthz != 200 -> rollback exits 70, not a clean 78"
else
  fail "11g: expected rc=70 when /healthz never answers, got $RC11G. Output: $OUT11G"
fi

# 11h. QC round 1 (HIGH): bootout still tearing down AFTER the quiesce timeout.
# The quiesce gives up (delay 8 > timeout 3), the rollback sees the job loaded
# with a pid and /healthz 200 -- and the pending bootout then removes it. The
# rollback must not take that one good moment as proof. Either the job is still
# loaded once the delay has passed (and nothing false was printed), or the script
# exited 70 and made no "rollback complete" claim.
H11H="$(make_box b11h legacy)"; S11H="$SANDBOX/stubs11h"; ST11H="$SANDBOX/state11h"
make_stubs "$S11H" "$ST11H" versioned
echo 8 > "$ST11H/bootout_delay"
OUT11H="$(T_BOOTOUT_TIMEOUT=3 T_SETTLE=10 run_atomic "$H11H" "$S11H" "$ST11H")"; RC11H=$?
sleep 9      # past the 8s delay: whatever the early bootout was going to do, it has done
LOADED11H=no; "$S11H/launchctl" print "gui/501/ai.openclaw.gateway" >/dev/null 2>&1 && LOADED11H=yes
CLAIM11H=no; case "$OUT11H" in *"rollback complete"*|*"exactly as it was found"*) CLAIM11H=yes ;; esac
if [ "$LOADED11H" = "yes" ] || { [ "$RC11H" -eq 70 ] && [ "$CLAIM11H" = "no" ]; }; then
  pass "11h: bootout outliving the quiesce timeout -> gateway still loaded afterwards (loaded=$LOADED11H, rc=$RC11H) or a loud rc=70 with no success claim"
else
  fail "11h: FALSE CLAIM -- box dark after the pending bootout (rc=$RC11H, loaded=$LOADED11H, claimed-success=$CLAIM11H). Output: $OUT11H"
fi
if [ "$LOADED11H" = "yes" ] && [ "$CLAIM11H" = "yes" ] && [ "$RC11H" -ne 78 ]; then
  fail "11i: success claimed but rc=$RC11H"
elif [ "$LOADED11H" = "no" ] && [ "$CLAIM11H" = "yes" ]; then
  fail "11i: 'rollback complete' printed for a box that is dark"
else
  pass "11i: output never claims success for a dark box"
fi

# 11j. a non-numeric timeout must fall back to the default, not hang _poll.
H11J="$(make_box b11j clean)"; S11J="$SANDBOX/stubs11j"; ST11J="$SANDBOX/state11j"
make_stubs "$S11J" "$ST11J" versioned
touch "$ST11J/loaded_ai.openclaw.gateway"
OUT11J="$(HOME="$H11J" PATH="$S11J:/usr/bin:/bin:/usr/sbin:/sbin" \
  OC_ATOMIC_QUIESCE_PROOF_SECONDS=1 OC_ATOMIC_STABILITY_SECONDS=1 \
  OC_ATOMIC_BOOTOUT_TIMEOUT=abc OC_ATOMIC_HEALTH_TIMEOUT=x1 OC_ATOMIC_SETTLE_SECONDS=zz \
  perl -e 'alarm 90; exec @ARGV' bash "$ATOMIC" --upgrade 2>&1)"; RC11J=$?
if [ "$RC11J" -eq 0 ]; then
  pass "11j: non-numeric timeouts fall back to defaults; the upgrade finishes (rc=0), no hang"
else
  fail "11j: non-numeric timeouts broke the run (rc=$RC11J; 142 = hung). Output: $OUT11J"
fi

# 11k. forward path: gateway up with a stable pid but /healthz never 200 must NOT
# print ATOMIC UPGRADE COMPLETE.
H11K="$(make_box b11k clean)"; S11K="$SANDBOX/stubs11k"; ST11K="$SANDBOX/state11k"
make_stubs "$S11K" "$ST11K" versioned
touch "$ST11K/healthz_down"
OUT11K="$(T_HEALTH_TIMEOUT=2 T_SETTLE=1 run_atomic "$H11K" "$S11K" "$ST11K")"; RC11K=$?
case "$OUT11K" in
  *"ATOMIC UPGRADE COMPLETE"*) fail "11k: success printed for a gateway that never answered /healthz. Output: $OUT11K" ;;
  *) pass "11k: a gateway that is up but not answering /healthz is not called a complete upgrade (rc=$RC11K)" ;;
esac

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (9) the transform engine refuses what it cannot prove ---"
T="$SANDBOX/t"; mkdir -p "$T"
write_config "$T/dup.json" legacy-dup
python3 "$MIGRATOR" apply "$T/dup.json" "$T/dup.out" >/dev/null 2>&1
[ "$?" -eq 3 ] && pass "9a: duplicate agent ids -> UNDETERMINED (exit 3), never a silent drop" \
               || fail "9a: duplicate ids were not refused"

printf '%s\n' '{"agents":{"list":[{"id":"a"}],"entries":{"a":{}}}}' > "$T/both.json"
python3 "$MIGRATOR" detect "$T/both.json" >/dev/null 2>&1
[ "$?" -eq 3 ] && pass "9b: a config carrying BOTH schema keys -> UNDETERMINED (valid on no build)" \
               || fail "9b: a both-keys config was not refused"

printf '%s\n' '{"agents":{"list":[{"role":"no-id-here"}]}}' > "$T/noid.json"
python3 "$MIGRATOR" apply "$T/noid.json" "$T/noid.out" >/dev/null 2>&1
[ "$?" -eq 3 ] && pass "9c: an entry with no usable id -> UNDETERMINED, never an invented key" \
               || fail "9c: an id-less entry was not refused"

printf 'not json at all' > "$T/bad.json"
python3 "$MIGRATOR" detect "$T/bad.json" >/dev/null 2>&1
[ "$?" -eq 3 ] && pass "9d: an unparseable config -> UNDETERMINED (exit 3), never a clean 0" \
               || fail "9d: an unparseable config did not return 3"

write_config "$T/leg.json" legacy
python3 "$MIGRATOR" detect "$T/leg.json" >/dev/null 2>&1
[ "$?" -eq 10 ] && pass "9e: a legacy config -> exit 10 (LEGACY), distinct from both clean and undetermined" \
                || fail "9e: a legacy config did not return 10"

# A verify that must FAIL: hand-build an "after" that silently drops an agent.
python3 - "$T/leg.json" "$T/lossy.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
lst = d["agents"].pop("list")
d["agents"]["entries"] = {e["id"]: {k: v for k, v in e.items() if k != "id"} for e in lst[:-1]}
json.dump(d, open(sys.argv[2], "w"), indent=2)
PY
python3 "$MIGRATOR" verify "$T/leg.json" "$T/lossy.json" >/dev/null 2>&1
[ "$?" -eq 1 ] && pass "9f: the verifier CATCHES a migration that drops an agent (exit 1)" \
               || fail "9f: the verifier passed a lossy migration — it is not enforcing"

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (9g) every launchd domain target was well-formed ---"
# REGRESSION GUARD. UIDN was once assigned inside _detect_supervisor(), which is
# called as `SUPERVISOR="$(...)"` -- a subshell -- so the assignment was
# discarded and every target came out as `gui//ai.openclaw.gateway`. On a real
# Mac that bootout FAILS: the gateway is never stopped, _gateway_pid() returns
# empty, the quiesce "proof" passes on a live box, and the config is then
# migrated underneath a RUNNING gateway that reverts it within a minute.
# The original stub used `basename`, which normalises the double slash, so every
# case passed. It now records malformed targets and this asserts on them.
BAD_TOTAL=0
BAD_DETAIL=""
for st in "$SANDBOX"/state*; do
  [ -d "$st" ] || continue
  if [ -f "$st/bad_domains" ]; then
    n=$(wc -l < "$st/bad_domains" | tr -d ' ')
    BAD_TOTAL=$((BAD_TOTAL + n))
    BAD_DETAIL="$BAD_DETAIL $(basename "$st"):$(head -1 "$st/bad_domains")"
  fi
done
if [ "$BAD_TOTAL" -eq 0 ]; then
  pass "9g: every launchctl domain target across all cases was a well-formed gui/<uid>/<label>"
else
  fail "9g: $BAD_TOTAL malformed launchd domain target(s) -- the gateway would NOT actually be stopped on a real box:$BAD_DETAIL"
fi

echo ""
echo "--- (10) --detect is read-only and reports a MEASURED version ---"
H10="$(make_box b10 legacy)"; S10="$SANDBOX/stubs10"; ST10="$SANDBOX/state10"
make_stubs "$S10" "$ST10" versioned
CFG10="$H10/.openclaw/openclaw.json"; SHA10="$(sha_of "$CFG10")"
touch "$ST10/loaded_ai.openclaw.gateway"
OUT10="$(HOME="$H10" PATH="$S10:/usr/bin:/bin" bash "$ATOMIC" --detect 2>&1)"; RC10=$?
[ "$RC10" -eq 10 ] && pass "10a: --detect returns 10 on a legacy box" \
                   || fail "10a: --detect returned $RC10 on a legacy box (expected 10)"
[ "$(sha_of "$CFG10")" = "$SHA10" ] && pass "10b: --detect changed nothing" \
                                    || fail "10b: --detect MODIFIED the config"
if [ -f "$ST10/npm_installs" ]; then
  fail "10c: --detect installed a binary"
else
  pass "10c: --detect installed nothing"
fi
case "$OUT10" in
  *"$OLD_V"*) pass "10d: --detect reported the MEASURED version ($OLD_V), not a recorded one" ;;
  *)          fail "10d: --detect did not report the measured version. Output: $OUT10" ;;
esac

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (12) CAN010: a leftover literal-named temp file must not break the upgrade ---"
# BSD/macOS mktemp only randomizes TRAILING X's. A template like
# oc-schema.XXXXXX.json is therefore used LITERALLY: once that file exists
# (leftover from any earlier or parallel run) mktemp fails and the upgrade
# rolls back. Pre-create every literal name the old and new templates could
# produce, in a private TMPDIR, then require the upgrade to still succeed.
H12="$(make_box b12 legacy)"; S12="$SANDBOX/stubs12"; ST12="$SANDBOX/state12"
make_stubs "$S12" "$ST12" versioned
T12="$SANDBOX/tmp12"; mkdir -p "$T12"
: > "$T12/oc-schema.XXXXXX.json"; : > "$T12/oc-schema.XXXXXX"
OUT12="$( export TMPDIR="$T12"; run_atomic "$H12" "$S12" "$ST12" )"; RC12=$?
if [ "$RC12" -eq 0 ] && [ "$(cfg_shape "$H12/.openclaw/openclaw.json")" = "ENTRIES:3" ]; then
  pass "12a: upgrade + migration succeeded with the literal-named temp files already present"
else
  fail "12a: upgrade FAILED with a colliding leftover temp file (rc=$RC12). Output: $OUT12"
fi
LEFT12="$(ls -A "$T12" | grep -vxE 'oc-schema\.XXXXXX(\.json)?' || true)"
if [ -z "$LEFT12" ]; then
  pass "12b: the upgrade removed every temp file it created"
else
  fail "12b: the upgrade leaked temp file(s): $LEFT12"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (13) CAN014: the NEW binary must accept the config before success is claimed ---"
# 2026.10.4 -> 2026.10.5 left skills.workshop.autonomous.mode "propose" in place; the
# new build rejects it, every CLI command exited 1, and this script still printed
# "ATOMIC UPGRADE COMPLETE". The stub's `config validate` models the new build.
H13="$(make_box b13 propose)"; S13="$SANDBOX/stubs13"; ST13="$SANDBOX/state13"
make_stubs "$S13" "$ST13" versioned
OUT13="$(run_atomic "$H13" "$S13" "$ST13")"; RC13=$?
CFG13="$H13/.openclaw/openclaw.json"
if [ "$RC13" -eq 0 ] && grep -q 'ATOMIC UPGRADE COMPLETE' <<<"$OUT13" && grep -Eq '"mode": *"off"' "$CFG13" && ! grep -q propose "$CFG13" \
   && [ "$(event_order "$ST13" "npm install" "openclaw config validate")" = "OK" ]; then
  pass "13a: propose was mapped to off and the NEW binary validated the config after the install"
else
  fail "13a: rc=$RC13 mode=$(grep -o '"mode": *"[a-z]*"' "$CFG13") events=$(tr '\n' '|' < "$ST13/events") out=$OUT13"
fi

# A box ALREADY on the new build and holding propose (the operator Mac): not "nothing to do".
H13B="$(make_box b13b propose)"; S13B="$SANDBOX/stubs13b"; ST13B="$SANDBOX/state13b"
make_stubs "$S13B" "$ST13B" versioned; set_installed "$H13B" "$ST13B" "$NEW_V"
OUT13B="$(run_atomic "$H13B" "$S13B" "$ST13B")"; RC13B=$?
if [ "$RC13B" -eq 0 ] && grep -Eq '"mode": *"off"' "$H13B/.openclaw/openclaw.json" && [ ! -f "$ST13B/npm_installs" ] && [ -f "$ST13B/loaded_ai.openclaw.gateway" ]; then
  pass "13b: a box already on the new build holding propose is repaired (no reinstall, gateway back up)"
else
  fail "13b: rc=$RC13B installs=$([ -f "$ST13B/npm_installs" ] && echo yes || echo no) out=$OUT13B"
fi

# A value with NO known migration, and a build that still rejects the config: roll back, never CLEAN.
for kind in bogus clean; do
  H13C="$(make_box "b13c-$kind" "$kind")"; S13C="$SANDBOX/stubs13c-$kind"; ST13C="$SANDBOX/state13c-$kind"
  make_stubs "$S13C" "$ST13C" versioned
  [ "$kind" = "clean" ] && touch "$ST13C/validate_fail"      # config is fine; the build still rejects it
  CFG13C="$H13C/.openclaw/openclaw.json"; SHA13C="$(sha_of "$CFG13C")"
  OUT13C="$(run_atomic "$H13C" "$S13C" "$ST13C")"; RC13C=$?
  # v1.4.0: the new build's verdict comes AFTER doctor --fix, so there is no rolling back to the old build any more:
  # never a success banner, the failing proof is named, the new binary and the (untouched) config stay, and the box
  # is left to takeover (rc 71 here; a real gateway that cannot boot on the rejected config ends rc 70, see KB-c).
  if [ "$RC13C" -eq 71 ] && ! grep -q 'ATOMIC UPGRADE COMPLETE' <<<"$OUT13C" && [ "$(sha_of "$CFG13C")" = "$SHA13C" ] \
     && [ "$(cat "$ST13C/version")" = "$NEW_V" ] && grep -Eq 'REJECTS the config|rejects and there is no known migration' <<<"$OUT13C" && grep -q 'ERROR NOT ROLLING BACK' <<<"$OUT13C"; then
    pass "13c($kind): config the new build rejects (after doctor) -> never success: STUCK (rc=71) naming the proof, new binary + config kept, old build not reinstalled"
  else
    fail "13c($kind): rc=$RC13C version=$(cat "$ST13C/version") out=$OUT13C"
  fi
done

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (14) CAN015: upgrade the install the SUPERVISOR launches, not the copy on PATH ---"
# Operator Mac, roll 20261019: launchd ran node ~/.npm-global/.../openclaw (2026.10.4)
# while `openclaw` on PATH was an nvm copy already at 2026.10.5 (an earlier failed run
# had installed it there). The script measured PATH, logged "binary already at
# 2026.10.5 - no install needed", exited 0, and the gateway stayed on 2026.10.4.
# Fixture: the plist's node + package live in sup14 (a DIFFERENT npm than the one on
# PATH); the PATH copy is already at the target.
H14="$(make_box b14 clean)"; S14="$SANDBOX/stubs14"; ST14="$SANDBOX/state14"
make_stubs "$S14" "$ST14" versioned
SUP14="$SANDBOX/sup14"; mkdir -p "$SUP14/node/bin"
cp "$S14/node" "$S14/npm" "$SUP14/node/bin/"
write_supervisor "$H14" "$SUP14/node/bin/node" "$SUP14/npm-global" "$OLD_V"
touch "$ST14/split"; printf '%s' "$NEW_V" > "$ST14/version"      # PATH copy already newer
printf 'node %s/npm-global/lib/node_modules/openclaw/dist/index.js gateway\n' "$SUP14" > "$ST14/ps_args"
OUT14="$(run_atomic "$H14" "$S14" "$ST14")"; RC14=$?
PKG14="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$SUP14/npm-global/lib/node_modules/openclaw/package.json" 2>/dev/null)"
if [ "$RC14" -eq 0 ] && [ "$PKG14" = "$NEW_V" ]; then
  pass "14a: the package the gateway launches moved $OLD_V -> $PKG14 even though PATH openclaw already reported the target"
else
  fail "14a: rc=$RC14, the supervisor's package is '$PKG14' (want $NEW_V) while the PATH copy says $NEW_V - the false 'already at target' success. Output: $OUT14"
fi
if grep -qF "npm install -g --prefix $SUP14/npm-global openclaw@$NEW_V #via=$SUP14/node/bin/npm" "$ST14/events" 2>/dev/null; then
  pass "14b: installed with the supervisor's node's npm into the supervisor's prefix"
else
  fail "14b: wrong npm or prefix. Events: $(tr '\n' '|' < "$ST14/events" 2>/dev/null)"
fi
if grep -q 'DISAGREE' <<<"$OUT14" && grep -q 'ATOMIC UPGRADE COMPLETE' <<<"$OUT14" && [ -f "$ST14/loaded_ai.openclaw.gateway" ]; then
  pass "14c: PATH/supervisor disagreement was logged, the upgrade completed and the gateway is back up"
else
  fail "14c: no disagreement log / completion / gateway. Output: $OUT14"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (15) CAN015 round 2: package at target is NOT 'already on target' unless the gateway runs it ---"
# Probe A: the supervisor's package is already at the target but the live gateway was launched
# from an OLD tree (an npm/openclaw update with no restart). Probe B: package at target, gateway
# job not loaded at all. Both used to return 0 'nothing to do' with no gateway proof.
H15="$(make_box b15 clean)"; S15="$SANDBOX/stubs15"; ST15="$SANDBOX/state15"
make_stubs "$S15" "$ST15" versioned
set_installed "$H15" "$ST15" "$NEW_V"
printf 'node %s/OLD/lib/node_modules/openclaw/dist/index.js gateway\n' "$SANDBOX" > "$ST15/ps_args"
OUT15="$(run_atomic "$H15" "$S15" "$ST15")"; RC15=$?
if ! grep -q 'nothing to do' <<<"$OUT15" && grep -q 'launchctl bootout' "$ST15/events" && [ "$RC15" -ne 0 ]; then
  pass "15a: package at target but live gateway on an old tree -> restarted and failed loudly (rc=$RC15), no false 'nothing to do'"
else
  fail "15a: rc=$RC15 (want nonzero, with a restart and no 'nothing to do'). Output: $OUT15"
fi
H15B="$(make_box b15b clean)"; S15B="$SANDBOX/stubs15b"; ST15B="$SANDBOX/state15b"
make_stubs "$S15B" "$ST15B" versioned
set_installed "$H15B" "$ST15B" "$NEW_V"
OUT15B="$(T_GATEWAY_DOWN=1 run_atomic "$H15B" "$S15B" "$ST15B")"; RC15B=$?
if ! grep -q 'nothing to do' <<<"$OUT15B" && grep -q 'launchctl bootstrap' "$ST15B/events" && [ -f "$ST15B/loaded_ai.openclaw.gateway" ]; then
  pass "15b: package at target but gateway not loaded -> gateway started and proven, no false 'nothing to do'"
else
  fail "15b: rc=$RC15B. Output: $OUT15B"
fi
H15C="$(make_box b15c clean)"; S15C="$SANDBOX/stubs15c"; ST15C="$SANDBOX/state15c"
make_stubs "$S15C" "$ST15C" versioned
set_installed "$H15C" "$ST15C" "$NEW_V"
OUT15C="$(run_atomic "$H15C" "$S15C" "$ST15C")"; RC15C=$?
if [ "$RC15C" -eq 0 ] && grep -q 'nothing to do' <<<"$OUT15C" && ! grep -q 'launchctl bootout' "$ST15C/events"; then
  pass "15c: package at target AND gateway running it with /healthz 200 -> still 'nothing to do', no restart"
else
  fail "15c: rc=$RC15C. Output: $OUT15C"
fi

# 15d: the package is at the target and the gateway's args/healthz look right, but the gateway was
# started BEFORE the package was installed in place (npm i -g, no restart) -> not proven, restart.
H15D="$(make_box b15d clean)"; S15D="$SANDBOX/stubs15d"; ST15D="$SANDBOX/state15d"
make_stubs "$S15D" "$ST15D" versioned
set_installed "$H15D" "$ST15D" "$NEW_V"
printf '05-00:00:00\n' > "$ST15D/ps_etime"   # the pid is 5 days old; the fixture package.json is seconds old
OUT15D="$(run_atomic "$H15D" "$S15D" "$ST15D")"; RC15D=$?
if ! grep -q 'nothing to do' <<<"$OUT15D" && grep -q 'launchctl bootout' "$ST15D/events" && grep -q 'predates the installed build' <<<"$OUT15D"; then
  pass "15d: gateway started before the package's last change -> not 'already on target'; restarted and re-proved (rc=$RC15D)"
else
  fail "15d: rc=$RC15D (want a restart, 'predates the installed build', no 'nothing to do'). Output: $OUT15D"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (16) CAN015 round 3: a systemd box is refused loudly, never a false success ---"
# Only launchd is stopped, restarted and pid-proven. A systemd unit used to resolve to
# SUPERVISOR=none: no restart, an EMPTY-pid "gateway pid  runs ..." proof, rc 0 -- while the old
# gateway kept answering /healthz. A: package already at the target. B: package at the old build.
for kind in A B; do
  H16="$(make_box "b16$kind" clean)"; S16="$SANDBOX/stubs16$kind"; ST16="$SANDBOX/state16$kind"
  make_stubs "$S16" "$ST16" versioned
  rm -f "$H16/Library/LaunchAgents/ai.openclaw.gateway.plist"
  mkdir -p "$H16/.config/systemd/user"
  printf '[Service]\nExecStart=/usr/bin/env node %s/sup/lib/node_modules/openclaw/dist/index.js gateway\n' "$H16" \
    > "$H16/.config/systemd/user/openclaw-gateway.service"
  [ "$kind" = "A" ] && set_installed "$H16" "$ST16" "$NEW_V"
  OUT16="$(T_GATEWAY_DOWN=1 run_atomic "$H16" "$S16" "$ST16")"; RC16=$?
  if [ "$RC16" -eq 78 ] && grep -q 'systemd' <<<"$OUT16" \
     && ! grep -Eq 'nothing to do|ATOMIC UPGRADE COMPLETE|gateway pid' <<<"$OUT16" \
     && [ ! -f "$ST16/npm_installs" ] && ! grep -q 'launchctl boot' "$ST16/events"; then
    pass "16$kind: systemd box -> refused (rc=78), nothing installed or stopped, no 'nothing to do' / empty-pid proof"
  else
    fail "16$kind: rc=$RC16 (want 78 with no install, no stop, no success text). Output: $OUT16"
  fi
done

# ═══════════════════════════════════════════════════════════════════════════
# BIG FLEET ROLL 20261019, errors #21 #24 #25 #33. Same rules as everything above: the
# real script runs against fixture boxes with stubbed tools, and every assertion is on an
# OBSERVED side effect. Each fix also has a MUTATION case (the one function neutered, the
# same box run again) so a green result cannot be a harness that stopped measuring.
# ═══════════════════════════════════════════════════════════════════════════

# mutate_copy <name> <python-replace-old> <python-replace-new> -> path of a mutated copy that sits
# beside the REAL, unmutated engine files (see case 5 for why that matters). Fails the case loudly
# when the line to neuter is not found.
mutate_copy() {
  local name="$1" dst="$MUT_DIR/$1.sh"
  MUT_SRC="$ATOMIC" MUT_DST="$dst" MUT_OLD="$2" MUT_NEW="$3" python3 - <<'PY'
import os, sys
s = open(os.environ["MUT_SRC"], encoding="utf-8").read()
old, new = os.environ["MUT_OLD"], os.environ["MUT_NEW"]
if s.count(old) != 1:
    sys.stderr.write("MUTATION DID NOT APPLY (%d matches)\n" % s.count(old)); sys.exit(1)
open(os.environ["MUT_DST"], "w").write(s.replace(old, new))
PY
  [ $? -eq 0 ] && printf '%s' "$dst"
}

# spawn_gateway_like <state> <home> [extra-args] [ignore-term] -> pid. A REAL background process whose
# command line is `node <entry> gateway ...`, registered as holding the state database (the lsof
# stub answers for it only while it is alive) and as visible to the real ps. ppid becomes 1.
spawn_gateway_like() {
  local state="$1" home="$2" extra="${3:-}" ign="${4:-}" pid
  mkdir -p "$home/.openclaw/state"; : > "$home/.openclaw/state/openclaw.sqlite"
  if [ -n "$ign" ]; then
    ( trap '' TERM; exec -a "node $home/sup/lib/node_modules/openclaw/dist/index.js gateway $extra" sleep 300 ) >/dev/null 2>&1 &
  else
    ( exec -a "node $home/sup/lib/node_modules/openclaw/dist/index.js gateway $extra" sleep 300 ) >/dev/null 2>&1 &
  fi
  pid=$!
  touch "$state/realps_$pid"; echo "$pid" >> "$state/lsof_holders"; echo "$pid" >> "$state/extra_pids"
  printf '%s' "$pid"
}

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B21) error #21: npm runs ONLY with the gateway job booted out; never a start onto an incomplete package ---"
# A job that is LOADED when the rollback runs (here: doctor --fix restarts the LaunchAgent itself, as the real one does,
# and then fails; a crash-looping start could do the same before v1.4.0) must be booted out BEFORE the rollback reinstalls the old build.
# KeepAlive then respawns the gateway against the half-written tree. The stub npm records every
# install that ran while the job was loaded (npm_while_loaded): the invariant is that it stays absent.
npm_window_check() {   # <events-file> -> OK, or the reason the rollback's reinstall was not inside a stopped window
  python3 - "$1" <<'PY'
import sys
L = open(sys.argv[1], encoding="utf-8").read().splitlines()
ni = [i for i, l in enumerate(L) if l.startswith("npm install")]
if len(ni) < 2: print("FEWER-THAN-2-INSTALLS"); raise SystemExit
last, prev = ni[-1], ni[-2]
gw = lambda l, verb: ("launchctl " + verb) in l and "ai.openclaw.gateway" in l
bo = [i for i in range(prev + 1, last) if gw(L[i], "bootout")]
if not bo: print("NO-BOOTOUT-BETWEEN-THE-TWO-INSTALLS"); raise SystemExit
inside = [l for l in L[bo[-1] + 1:last] if gw(l, "bootstrap")]
if inside: print("BOOTSTRAP-INSIDE-THE-WINDOW"); raise SystemExit
after = [l for l in L[last + 1:] if gw(l, "bootstrap")]
print("OK" if after else "NO-BOOTSTRAP-AFTER-THE-PACKAGE-WAS-COMPLETE")
PY
}
H21="$(make_box b21 clean)"; S21="$SANDBOX/stubs21"; ST21="$SANDBOX/state21"
make_stubs "$S21" "$ST21" versioned; touch "$ST21/pid_flip"; echo fail_loaded > "$ST21/doctor_mode"
OUT21="$(run_atomic "$H21" "$S21" "$ST21")"; RC21=$?
if [ "$RC21" -eq 78 ] && [ "$(cat "$ST21/version")" = "$OLD_V" ] && [ "$(grep -c npm-install-witness "$ST21/npm_installs")" -eq 2 ]; then
  pass "B21a: doctor loaded the (crash-looping) job and failed -> rolled back (rc=78) and the OLD build was reinstalled ($OLD_V)"
else
  fail "B21a: rc=$RC21 version=$(cat "$ST21/version") installs=$(grep -c npm-install-witness "$ST21/npm_installs" 2>/dev/null). Output: $OUT21"
fi
if [ ! -f "$ST21/npm_while_loaded" ]; then
  pass "B21b: npm NEVER ran while the gateway job was loaded (forward install and rollback reinstall)"
else
  fail "B21b: npm ran with the gateway job LOADED: $(cat "$ST21/npm_while_loaded")"
fi
W21="$(npm_window_check "$ST21/events")"
[ "$W21" = "OK" ] && pass "B21c: ORDER — bootout, then the rollback's npm install, and only then the bootstrap ($W21)" \
                  || fail "B21c: the rollback reinstall was not inside a stopped window ($W21). Events: $(tr '\n' '|' < "$ST21/events")"

# MUTATION: neuter ONLY the "make sure the job is out before npm" step. The same box must now show the
# invariant violated, else B21b was green for some other reason.
MUT21="$(mutate_copy bfr21-mut '_gateway_stop_for_npm() {
  _gateway_loaded || return 0' '_gateway_stop_for_npm() {
  return 0   # MUTATED
  _gateway_loaded || return 0')"
H21M="$(make_box b21m clean)"; S21M="$SANDBOX/stubs21m"; ST21M="$SANDBOX/state21m"
make_stubs "$S21M" "$ST21M" versioned; touch "$ST21M/pid_flip"; echo fail_loaded > "$ST21M/doctor_mode"
OUT21M="$(run_atomic "$H21M" "$S21M" "$ST21M" "$MUT21")"; RC21M=$?
if [ -n "$MUT21" ] && [ -f "$ST21M/npm_while_loaded" ]; then
  pass "B21d: MUTATION PROOF — with only the stop-before-npm step neutered, the rollback DID run npm with the job loaded ($(cat "$ST21M/npm_while_loaded"))"
else
  fail "B21d: the mutant did not reproduce the defect (mutant=${MUT21:-none}, rc=$RC21M), so B21b measures nothing. Output: $OUT21M"
fi

# The job can no longer be booted out (launchd stops honouring bootout after the new install): the
# rollback must REFUSE to run npm into a tree a respawning gateway is importing, and say a human is needed.
H21E="$(make_box b21e clean)"; S21E="$SANDBOX/stubs21e"; ST21E="$SANDBOX/state21e"
make_stubs "$S21E" "$ST21E" versioned; touch "$ST21E/pid_flip" "$ST21E/arm_bootout_noop_after_install"; echo fail_loaded > "$ST21E/doctor_mode"
OUT21E="$(T_BOOTOUT_TIMEOUT=2 run_atomic "$H21E" "$S21E" "$ST21E")"; RC21E=$?
if [ "$RC21E" -eq 70 ] && [ "$(grep -c npm-install-witness "$ST21E/npm_installs")" -eq 1 ] && [ ! -f "$ST21E/npm_while_loaded" ] \
   && grep -q 'BINARY RESTORE NOT ATTEMPTED' <<<"$OUT21E"; then
  pass "B21e: a job that cannot be held stopped -> NO reinstall into a live tree, exit 70 (a human is needed), nothing claimed"
else
  fail "B21e: rc=$RC21E installs=$(grep -c npm-install-witness "$ST21E/npm_installs") while_loaded=$([ -f "$ST21E/npm_while_loaded" ] && echo yes || echo no). Output: $OUT21E"
fi

# The old build's reinstall leaves a half-written tree (the entry file is missing): the gateway must NOT be
# bootstrapped onto it (it could only crash-loop), and the rollback must say so rather than claim success.
H21F="$(make_box b21f clean)"; S21F="$SANDBOX/stubs21f"; ST21F="$SANDBOX/state21f"
make_stubs "$S21F" "$ST21F" versioned; touch "$ST21F/pid_flip" "$ST21F/half_old_install"; echo fail_loaded > "$ST21F/doctor_mode"
OUT21F="$(run_atomic "$H21F" "$S21F" "$ST21F")"; RC21F=$?
LASTNPM21F="$(grep -n '^npm install' "$ST21F/events" | tail -1 | cut -d: -f1)"
BOOT_AFTER21F="$(tail -n +"$((LASTNPM21F+1))" "$ST21F/events" | grep -c 'launchctl bootstrap.*ai.openclaw.gateway')"
if [ "$RC21F" -eq 70 ] && [ "${BOOT_AFTER21F:-9}" -eq 0 ] && grep -q 'GATEWAY NOT RE-LOADED' <<<"$OUT21F" && ! grep -q 'rollback complete and VERIFIED' <<<"$OUT21F"; then
  pass "B21f: package incomplete after the reinstall -> the gateway was NOT bootstrapped onto it, rollback reports FAILED (rc=70)"
else
  fail "B21f: rc=$RC21F bootstraps-after-last-npm=$BOOT_AFTER21F. Output: $OUT21F"
fi

# npm itself dies half-way on the FORWARD install (new package.json written, entry file gone). The
# install "failed", but the tree is half-written: the rollback must repair it, not trust the exit code.
H21G="$(make_box b21g clean)"; S21G="$SANDBOX/stubs21g"; ST21G="$SANDBOX/state21g"
make_stubs "$S21G" "$ST21G" versioned; touch "$ST21G/npm_half_new"
OUT21G="$(run_atomic "$H21G" "$S21G" "$ST21G")"; RC21G=$?
if [ "$RC21G" -eq 78 ] && [ "$(cat "$ST21G/version")" = "$OLD_V" ] && [ -f "$H21G/sup/lib/node_modules/openclaw/dist/index.js" ] \
   && [ "$(grep -c npm-install-witness "$ST21G/npm_installs")" -eq 2 ] && [ ! -f "$ST21G/npm_while_loaded" ] && [ -f "$ST21G/loaded_ai.openclaw.gateway" ]; then
  pass "B21g: npm died half-way on the forward install -> the half-written tree was REPAIRED (old build reinstalled, entry file back), gateway back up"
else
  fail "B21g: rc=$RC21G version=$(cat "$ST21G/version") entry=$([ -f "$H21G/sup/lib/node_modules/openclaw/dist/index.js" ] && echo yes || echo MISSING). Output: $OUT21G"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B25) error #25: a config check against a SERVING gateway never takes the live lock ---"
# The stub's `config validate` models 2026.10.5: against the LIVE state dir while the job is loaded it
# takes the lock and the gateway stops answering (recorded in lock_collisions, job unloaded).
H25="$(make_box b25 clean)"; S25="$SANDBOX/stubs25"; ST25="$SANDBOX/state25"
make_stubs "$S25" "$ST25" versioned; set_installed "$H25" "$ST25" "$NEW_V"
OUT25="$(run_atomic "$H25" "$S25" "$ST25")"; RC25=$?
if [ "$RC25" -eq 0 ] && grep -q 'nothing to do' <<<"$OUT25" && [ ! -f "$ST25/lock_collisions" ] && [ -f "$ST25/loaded_ai.openclaw.gateway" ]; then
  pass "B25a: already on target with a SERVING gateway -> 'nothing to do', no live lock taken, the gateway is still loaded (rc=0)"
else
  fail "B25a: rc=$RC25 collisions=$(cat "$ST25/lock_collisions" 2>/dev/null) loaded=$([ -f "$ST25/loaded_ai.openclaw.gateway" ] && echo yes || echo NO). Output: $OUT25"
fi
V25="$(grep '^validate state=' "$ST25/events" | sed 's/state=[^ ]*/state=ISO/' | tr '\n' '|')"
if [ "$(grep -c '^validate state=' "$ST25/events")" -eq 3 ] && ! grep -q '^validate state=LIVE' "$ST25/events" \
   && [ "$V25" = "validate state=ISO cfg=control-good.json ro=1|validate state=ISO cfg=control-bad.json ro=1|validate state=ISO cfg=openclaw.json ro=1|" ]; then
  pass "B25b: the check ran in a private state dir, read-only, as known-good control -> known-bad control -> the real config"
else
  fail "B25b: validate calls were: $V25"
fi
# the config the box really has was what got checked, and the box's own config was not touched
H25B="$(make_box b25b propose)"; S25B="$SANDBOX/stubs25b"; ST25B="$SANDBOX/state25b"
make_stubs "$S25B" "$ST25B" versioned; set_installed "$H25B" "$ST25B" "$NEW_V"
OUT25B="$(run_atomic "$H25B" "$S25B" "$ST25B")"; RC25B=$?
if [ "$RC25B" -eq 0 ] && grep -Eq '"mode": *"off"' "$H25B/.openclaw/openclaw.json" && [ ! -f "$ST25B/lock_collisions" ] \
   && [ -f "$ST25B/loaded_ai.openclaw.gateway" ] && grep -q 'ATOMIC UPGRADE COMPLETE' <<<"$OUT25B"; then
  pass "B25c: a serving gateway on a config the build REJECTS -> rejected by the isolated check, repaired in the quiesce, no live lock taken while it served"
else
  fail "B25c: rc=$RC25B collisions=$(cat "$ST25B/lock_collisions" 2>/dev/null). Output: $OUT25B"
fi
# an instrument that cannot tell good from bad is UNDETERMINED, never 'valid'
H25C="$(make_box b25c clean)"; S25C="$SANDBOX/stubs25c"; ST25C="$SANDBOX/state25c"
make_stubs "$S25C" "$ST25C" versioned; set_installed "$H25C" "$ST25C" "$NEW_V"; touch "$ST25C/validate_blind"
OUT25C="$(run_atomic "$H25C" "$S25C" "$ST25C")"; RC25C=$?
if grep -q 'UNDETERMINED' <<<"$OUT25C" && ! grep -q 'nothing to do' <<<"$OUT25C" && [ ! -f "$ST25C/lock_collisions" ] && grep -q 'launchctl bootout' "$ST25C/events"; then
  pass "B25d: a validator that accepts the known-bad control is UNDETERMINED -> never 'nothing to do'; the full procedure checked it inside the quiesce (rc=$RC25C)"
else
  fail "B25d: rc=$RC25C. Output: $OUT25C"
fi
# MUTATION: take the isolation away. The same serving box must now lose its gateway to the validate.
MUT25="$(mutate_copy bfr25-mut '  if _gateway_loaded; then _config_valid_isolated; return $?; fi' '  :   # MUTATED: no isolation')"
H25M="$(make_box b25m clean)"; S25M="$SANDBOX/stubs25m"; ST25M="$SANDBOX/state25m"
make_stubs "$S25M" "$ST25M" versioned; set_installed "$H25M" "$ST25M" "$NEW_V"
OUT25M="$(run_atomic "$H25M" "$S25M" "$ST25M" "$MUT25")"; RC25M=$?
if [ -n "$MUT25" ] && [ -f "$ST25M/lock_collisions" ] && [ ! -f "$ST25M/loaded_ai.openclaw.gateway" ]; then
  pass "B25e: MUTATION PROOF — without the isolation the validate DID take the live lock and the serving gateway went down"
else
  fail "B25e: the mutant did not reproduce the defect (mutant=${MUT25:-none}, rc=$RC25M). Output: $OUT25M"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B33) error #33: an orphan gateway that owns the state dir is stopped by identity before the start ---"
# Case A: the orphan is there from the start (ppid 1, started by an earlier run). While it lives the
# stub's job is loaded but has NO pid - the LaunchAgent exiting 78. Only reaping it lets the upgrade finish.
H33="$(make_box b33 clean)"; S33="$SANDBOX/stubs33"; ST33="$SANDBOX/state33"
make_stubs "$S33" "$ST33" versioned
OP33="$(spawn_gateway_like "$ST33" "$H33" "--token SECRET-ORPHAN-TOKEN")"; echo "$OP33" > "$ST33/orphan_pid"
OUT33="$(run_atomic "$H33" "$S33" "$ST33")"; RC33=$?
if [ "$RC33" -eq 0 ] && ! kill -0 "$OP33" 2>/dev/null && grep -q "ORPHAN GATEWAY pid $OP33" <<<"$OUT33" && grep -q 'ATOMIC UPGRADE COMPLETE' <<<"$OUT33"; then
  pass "B33a: an orphan gateway (pid $OP33) holding the state dir was stopped and the upgrade completed (rc=0)"
else
  fail "B33a: rc=$RC33 orphan-alive=$(kill -0 "$OP33" 2>/dev/null && echo yes || echo no). Output: $OUT33"
fi
L_ORPHAN="$(grep -n "ORPHAN GATEWAY pid $OP33" <<<"$OUT33" | head -1 | cut -d: -f1)"; L_INSTALL="$(grep -n 'installing openclaw@' <<<"$OUT33" | head -1 | cut -d: -f1)"
if [ -n "$L_ORPHAN" ] && [ -n "$L_INSTALL" ] && [ "$L_ORPHAN" -lt "$L_INSTALL" ] && grep -q 'after the quiesce' <<<"$OUT33"; then
  pass "B33b: it was reaped right after the quiesce, BEFORE the install and the quiescence proof"
else
  fail "B33b: orphan line $L_ORPHAN, install line $L_INSTALL. Output: $OUT33"
fi
if ! grep -q 'SECRET-ORPHAN-TOKEN' <<<"$OUT33"; then
  pass "B33c: the gateway's command line (it carried a token) never reached the log - only the entry path was named"
else
  fail "B33c: a secret from the orphan's command line was LOGGED"
fi
# Case B: the orphan appears AFTER the quiesce and after doctor (so only the pre-start reap can catch it): the pre-start reap is the one that must catch it.
H33B="$(make_box b33b clean)"; S33B="$SANDBOX/stubs33b"; ST33B="$SANDBOX/state33b"
make_stubs "$S33B" "$ST33B" versioned; touch "$ST33B/spawn_orphan_on_doctor_fix"; mkdir -p "$H33B/.openclaw/state"; : > "$H33B/.openclaw/state/openclaw.sqlite"
OUT33B="$(run_atomic "$H33B" "$S33B" "$ST33B")"; RC33B=$?
OP33B="$(cat "$ST33B/orphan_pid" 2>/dev/null)"
if [ -n "$OP33B" ] && [ "$RC33B" -eq 0 ] && ! kill -0 "$OP33B" 2>/dev/null && grep -q 'before the gateway start' <<<"$OUT33B" && grep -q "ORPHAN GATEWAY pid $OP33B" <<<"$OUT33B"; then
  pass "B33d: an orphan that appeared after doctor was stopped just before the start, and the gateway came up (rc=0)"
else
  fail "B33d: rc=$RC33B orphan=$OP33B alive=$(kill -0 "${OP33B:-0}" 2>/dev/null && echo yes || echo no). Output: $OUT33B"
fi
# MUTATION: no reaper. The same box must now fail to start (job loaded, no pid) and roll back, orphan still alive.
MUT33="$(mutate_copy bfr33-mut '_reap_orphan_gateways() {
  local where="$1"' '_reap_orphan_gateways() {
  return 0   # MUTATED
  local where="$1"')"
H33M="$(make_box b33m clean)"; S33M="$SANDBOX/stubs33m"; ST33M="$SANDBOX/state33m"
make_stubs "$S33M" "$ST33M" versioned; touch "$ST33M/spawn_orphan_on_doctor_fix"; mkdir -p "$H33M/.openclaw/state"; : > "$H33M/.openclaw/state/openclaw.sqlite"
OUT33M="$(run_atomic "$H33M" "$S33M" "$ST33M" "$MUT33")"; RC33M=$?
OP33M="$(cat "$ST33M/orphan_pid" 2>/dev/null)"
if [ -n "$MUT33" ] && [ -n "$OP33M" ] && kill -0 "$OP33M" 2>/dev/null && [ "$RC33M" -ne 0 ] && ! grep -q 'ATOMIC UPGRADE COMPLETE' <<<"$OUT33M"; then
  pass "B33e: MUTATION PROOF — with no reaper the orphan survives, the start finds no pid, and the box rolls back (rc=$RC33M): the exact #33 failure"
else
  fail "B33e: the mutant did not reproduce the defect (mutant=${MUT33:-none}, rc=$RC33M, orphan alive=$(kill -0 "${OP33M:-0}" 2>/dev/null && echo yes || echo no))"
fi
[ -n "$OP33M" ] && kill -KILL "$OP33M" 2>/dev/null
# Case C: an orphan that ignores SIGTERM is killed (SIGKILL) after the bounded wait.
H33C="$(make_box b33c clean)"; S33C="$SANDBOX/stubs33c"; ST33C="$SANDBOX/state33c"
make_stubs "$S33C" "$ST33C" versioned
OP33C="$(spawn_gateway_like "$ST33C" "$H33C" "" ignore)"; echo "$OP33C" > "$ST33C/orphan_pid"
OUT33C="$(run_atomic "$H33C" "$S33C" "$ST33C")"; RC33C=$?
if [ "$RC33C" -eq 0 ] && ! kill -0 "$OP33C" 2>/dev/null && grep -q "orphan gateway pid $OP33C stopped" <<<"$OUT33C"; then
  pass "B33f: an orphan that ignores SIGTERM was stopped after the bounded wait (rc=0)"
else
  fail "B33f: rc=$RC33C alive=$(kill -0 "$OP33C" 2>/dev/null && echo yes || echo no). Output: $OUT33C"
fi

# Direct calls of the reaper (the script sourced without its main): what it must LEAVE ALONE.
SRC_DIR="$SANDBOX/srcable"; mkdir -p "$SRC_DIR"
cp "$MIGRATOR" "$SRC_DIR/oc-schema-migrate.py"; cp "$SUPHELPER" "$SRC_DIR/oc-supervisor-install.py"
python3 - "$ATOMIC" "$SRC_DIR/oc-atomic-upgrade.sh" <<'PY'
import sys
s = open(sys.argv[1], encoding="utf-8").read().rstrip()
assert s.endswith('main "$@"'), "the script no longer ends with main"
open(sys.argv[2], "w").write(s[:-len('main "$@"')] + "\n")
PY
direct() {   # <home> <stubs> <snippet> -> output of the snippet, run with the script's functions loaded
  HOME="$1" PATH="$2:/usr/bin:/bin:/usr/sbin:/sbin" bash -c 'source "$0" && _resolve_root && SUPERVISOR=launchd && '"$3" "$SRC_DIR/oc-atomic-upgrade.sh" 2>&1
}
H33D="$(make_box b33d clean)"; S33D="$SANDBOX/stubs33d"; ST33D="$SANDBOX/state33d"
make_stubs "$S33D" "$ST33D" versioned; touch "$ST33D/loaded_ai.openclaw.gateway"
JOB33D="$(spawn_gateway_like "$ST33D" "$H33D")"; printf '%s' "$JOB33D" > "$ST33D/pid"      # the launchd job's own gateway
ORP33D="$(spawn_gateway_like "$ST33D" "$H33D")"                                              # a second one: the orphan
( exec -a "python3 /opt/other-tool/run.py" sleep 300 ) >/dev/null 2>&1 &
OTH33D=$!; touch "$ST33D/realps_$OTH33D"; echo "$OTH33D" >> "$ST33D/lsof_holders"; echo "$OTH33D" >> "$ST33D/extra_pids"
( exec -a "node $H33D/sup/lib/node_modules/openclaw/dist/index.js status" sleep 300 ) >/dev/null 2>&1 &
CLI33D=$!; touch "$ST33D/realps_$CLI33D"; echo "$CLI33D" >> "$ST33D/lsof_holders"; echo "$CLI33D" >> "$ST33D/extra_pids"
OUT33D="$(direct "$H33D" "$S33D" '_reap_orphan_gateways "direct"; echo "rc=$?"')"
if ! kill -0 "$ORP33D" 2>/dev/null && kill -0 "$JOB33D" 2>/dev/null && kill -0 "$OTH33D" 2>/dev/null && kill -0 "$CLI33D" 2>/dev/null \
   && grep -q "pid $JOB33D is the launchd job's gateway - left alone" <<<"$OUT33D" && grep -q 'rc=0' <<<"$OUT33D"; then
  pass "B33g: of four state-database holders only the ORPHAN gateway was stopped; the launchd job's own gateway, a non-openclaw program and a bare openclaw CLI were left alone"
else
  fail "B33g: orphan-alive=$(kill -0 "$ORP33D" 2>/dev/null && echo yes || echo no) job-alive=$(kill -0 "$JOB33D" 2>/dev/null && echo yes || echo NO) other-alive=$(kill -0 "$OTH33D" 2>/dev/null && echo yes || echo NO) cli-alive=$(kill -0 "$CLI33D" 2>/dev/null && echo yes || echo NO). Output: $OUT33D"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B24) error #24: a plugin whose module fails to load is killed early, named, disabled (only its flag) and doctor re-run - never a hang ---"
# With $STATE/doctor_broken_plugin the stub doctor prints the SAME ERR_MODULE_NOT_FOUND line again and again
# (a timestamp in front, so no two lines are byte-identical) and never returns, for as long as that plugin's
# entry is enabled. The bound is 60s here: finishing in seconds proves the LOOP DETECTOR acted, not the bound.
H24="$(make_box b24 plugin)"; S24="$SANDBOX/stubs24"; ST24="$SANDBOX/state24"
make_stubs "$S24" "$ST24" versioned; printf 'codex' > "$ST24/doctor_broken_plugin"
CFG24="$H24/.openclaw/openclaw.json"; cp "$CFG24" "$SANDBOX/cfg24.before"
T24_START=$SECONDS
OUT24="$(run_atomic "$H24" "$S24" "$ST24")"; RC24=$?
T24_ELAPSED=$((SECONDS - T24_START))
if [ "$RC24" -eq 0 ] && grep -q 'ATOMIC UPGRADE COMPLETE' <<<"$OUT24" && grep -q "QUARANTINED plugin 'codex'" <<<"$OUT24" && [ "$T24_ELAPSED" -lt 40 ]; then
  pass "B24a: the looping plugin was named (codex) and quarantined; doctor then ran and the upgrade completed (rc=0) in ${T24_ELAPSED}s - far inside the 60s bound"
else
  fail "B24a: rc=$RC24 (${T24_ELAPSED}s). Output: $OUT24"
fi
if python3 - "$SANDBOX/cfg24.before" "$CFG24" <<'PY'
import json, sys
b = json.load(open(sys.argv[1], encoding="utf-8")); a = json.load(open(sys.argv[2], encoding="utf-8"))
assert a["plugins"]["entries"]["codex"]["enabled"] is False, "codex was not disabled"
a["plugins"]["entries"]["codex"]["enabled"] = True
assert a == b, "something besides plugins.entries.codex.enabled changed (allow list, entry config, other plugins, models, ...)"
PY
then
  pass "B24b: ONLY plugins.entries.codex.enabled changed - the allow list, codex's own config, the other plugin and everything else are identical"
else
  fail "B24b: the config changed beyond the one flag"
fi
REC24="$H24/.openclaw/oc-atomic-plugin-quarantine.jsonl"
if python3 - "$REC24" <<'PY'
import json, sys
r = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
assert len(r) == 1 and r[0]["event"] == "quarantined" and r[0]["plugin"] == "codex", r
assert r[0]["was_enabled"] == "true" and "restore" in r[0] and r[0]["config_backup"], r
assert "session-store-runtime" in r[0]["failing_import"], r
PY
then
  pass "B24c: the quarantine is RECORDED (plugin, failing import, previous value, config backup, how to restore)"
else
  fail "B24c: record missing or wrong: $(cat "$REC24" 2>/dev/null)"
fi
if ! grep -Eq '^openclaw plugins ' "$ST24/events" && ! grep -Eq 'plugins (install|enable|update)' "$ST24/events"; then
  pass "B24d: no 'openclaw plugins ...' call of any kind was made - codex is never installed, enabled or updated"
else
  fail "B24d: a plugins command ran: $(grep 'plugins' "$ST24/events" | tr '\n' '|')"
fi
if [ "$(grep -c '^openclaw doctor --fix' "$ST24/events")" -eq 2 ]; then
  pass "B24e: doctor --fix ran twice: killed when it began to loop, then run again once the plugin's entry was disabled"
else
  fail "B24e: doctor --fix runs: $(grep -c '^openclaw doctor --fix' "$ST24/events"). Events: $(tr '\n' '|' < "$ST24/events")"
fi
# A load error that names NO configured plugin is never acted on (no guessing): one noisy line + exit 0 is fine,
# and a failing doctor whose only clue is such a line is a plain failure -> rollback with the config untouched.
H24N="$(make_box b24n plugin)"; S24N="$SANDBOX/stubs24n"; ST24N="$SANDBOX/state24n"
make_stubs "$S24N" "$ST24N" versioned; touch "$ST24N/doctor_noise"
SHA24N="$(sha_of "$H24N/.openclaw/openclaw.json")"
OUT24N="$(run_atomic "$H24N" "$S24N" "$ST24N")"; RC24N=$?
if [ "$RC24N" -eq 0 ] && ! grep -q 'QUARANTINED' <<<"$OUT24N" && [ "$(sha_of "$H24N/.openclaw/openclaw.json")" = "$SHA24N" ] && [ ! -f "$H24N/.openclaw/oc-atomic-plugin-quarantine.jsonl" ]; then
  pass "B24f: a doctor that merely mentions a load error once and succeeds disabled NOTHING (config byte-identical, no record)"
else
  fail "B24f: rc=$RC24N. Output: $OUT24N"
fi
H24U="$(make_box b24u plugin)"; S24U="$SANDBOX/stubs24u"; ST24U="$SANDBOX/state24u"
make_stubs "$S24U" "$ST24U" versioned; touch "$ST24U/doctor_noise_fail"
SHA24U="$(sha_of "$H24U/.openclaw/openclaw.json")"
OUT24U="$(run_atomic "$H24U" "$S24U" "$ST24U")"; RC24U=$?
if [ "$RC24U" -eq 78 ] && ! grep -q 'QUARANTINED' <<<"$OUT24U" && [ "$(sha_of "$H24U/.openclaw/openclaw.json")" = "$SHA24U" ] && [ ! -f "$H24U/.openclaw/oc-atomic-plugin-quarantine.jsonl" ] \
   && [ "$(cat "$ST24U/version")" = "$OLD_V" ]; then
  pass "B24g: a failing doctor whose load error names no configured plugin -> NOTHING disabled, rolled back (rc=78), config byte-identical, binary $OLD_V"
else
  fail "B24g: rc=$RC24U. Output: $OUT24U"
fi
# ROLLBACK after a quarantine restores the config byte for byte (the entry is enabled again) and says so in the record.
H24R="$(make_box b24r plugin)"; S24R="$SANDBOX/stubs24r"; ST24R="$SANDBOX/state24r"
make_stubs "$S24R" "$ST24R" versioned; printf 'codex' > "$ST24R/doctor_broken_plugin"; echo fail > "$ST24R/doctor_mode"
SHA24R="$(sha_of "$H24R/.openclaw/openclaw.json")"
OUT24R="$(run_atomic "$H24R" "$S24R" "$ST24R")"; RC24R=$?
if [ "$RC24R" -eq 78 ] && [ "$(sha_of "$H24R/.openclaw/openclaw.json")" = "$SHA24R" ] && grep -q '"event": "reverted-by-rollback"' "$H24R/.openclaw/oc-atomic-plugin-quarantine.jsonl" 2>/dev/null; then
  pass "B24h: doctor failed on its second run, after the quarantine (so it never completed) -> rolled back (rc=78): the config is BYTE-IDENTICAL (codex enabled again) and the record says it was reverted"
else
  fail "B24h: rc=$RC24R sha-equal=$([ "$(sha_of "$H24R/.openclaw/openclaw.json")" = "$SHA24R" ] && echo yes || echo NO) record=$(cat "$H24R/.openclaw/oc-atomic-plugin-quarantine.jsonl" 2>/dev/null)"
fi
# The loop detector OFF (OC_ATOMIC_DOCTOR_LOOP_LINES=0): the bound alone ends the spin, and the same attribution works.
H24B="$(make_box b24b plugin)"; S24B="$SANDBOX/stubs24b"; ST24B="$SANDBOX/state24b"
make_stubs "$S24B" "$ST24B" versioned; printf 'codex' > "$ST24B/doctor_broken_plugin"
OUT24B="$(T_LOOP_LINES=0 T_DOCTOR_TIMEOUT=4 run_atomic "$H24B" "$S24B" "$ST24B")"; RC24B=$?
if [ "$RC24B" -eq 0 ] && grep -q "QUARANTINED plugin 'codex'" <<<"$OUT24B" && [ "$(grep -c '^openclaw doctor --fix' "$ST24B/events")" -eq 2 ]; then
  pass "B24i: with the loop detector off, a doctor killed at its 4s BOUND is attributed from its output the same way (rc=0)"
else
  fail "B24i: rc=$RC24B. Output: $OUT24B"
fi
# MUTATION: no quarantine. The same box's doctor is killed (loop detector) and the upgrade rolls back instead of finishing.
MUT24="$(mutate_copy bfr24-mut '_quarantine_from_output() {
  local hit id imp' '_quarantine_from_output() {
  return 1   # MUTATED
  local hit id imp')"
H24M="$(make_box b24m plugin)"; S24M="$SANDBOX/stubs24m"; ST24M="$SANDBOX/state24m"
make_stubs "$S24M" "$ST24M" versioned; printf 'codex' > "$ST24M/doctor_broken_plugin"
OUT24M="$(run_atomic "$H24M" "$S24M" "$ST24M" "$MUT24")"; RC24M=$?
if [ -n "$MUT24" ] && [ "$RC24M" -eq 78 ] && ! grep -q 'ATOMIC UPGRADE COMPLETE' <<<"$OUT24M" && grep -q 'spinning on the same module-load error' <<<"$OUT24M"; then
  pass "B24j: MUTATION PROOF — without the quarantine the same box's doctor is killed as a loop and the upgrade rolls back (rc=78)"
else
  fail "B24j: the mutant did not reproduce the failure (mutant=${MUT24:-none}, rc=$RC24M). Output: $OUT24M"
fi
# The loop detector itself, driven directly: the same normalised line N times kills the command (rc 125); fewer, or other
# text, does not - and the plain bound still reports 124.
LD_DIR="$SANDBOX/loopdet"; mkdir -p "$LD_DIR"
ld() {   # <bound> <loop-n> <script> -> rc of _run_bounded
  printf '%s\n' "$3" > "$LD_DIR/cmd.sh"
  PATH="/usr/bin:/bin:/usr/sbin:/sbin" OC_BOUNDED_LOOP_RE='ERR_MODULE_NOT_FOUND' OC_BOUNDED_LOOP_N="$2" \
    bash -c 'source "$0"; _run_bounded "$1" "$2" bash "$3"; echo $?' "$SRC_DIR/oc-atomic-upgrade.sh" "$1" "$LD_DIR/out.txt" "$LD_DIR/cmd.sh" 2>/dev/null | tail -1
}
LD1="$(ld 20 4 'for i in 1 2 3 4 5 6; do echo "[$i$i$i] ERR_MODULE_NOT_FOUND x $i"; done; sleep 60')"
LD2="$(ld 3 4 'echo "ERR_MODULE_NOT_FOUND a"; echo "ERR_MODULE_NOT_FOUND b"; echo "ERR_MODULE_NOT_FOUND c"; sleep 60')"
LD3="$(ld 20 4 'echo "ERR_MODULE_NOT_FOUND a"; sleep 1; echo done; exit 0')"
LD4="$(ld 20 0 'for i in 1 2 3 4 5 6; do echo "ERR_MODULE_NOT_FOUND"; done; sleep 1; exit 3')"
if [ "$LD1" = "125" ] && [ "$LD2" = "124" ] && [ "$LD3" = "0" ] && [ "$LD4" = "3" ]; then
  pass "B24k: loop detector — the same line (digits ignored) 4 times -> killed early (125); 3 DIFFERENT lines -> only the bound (124); one mention + success -> 0; detector off -> the command's own rc (3)"
else
  fail "B24k: LD1=$LD1 (want 125) LD2=$LD2 (want 124) LD3=$LD3 (want 0) LD4=$LD4 (want 3)"
fi

# The attribution rules themselves (pure engine calls): evidence is a path component or 'plugin <id>', never a bare word.
ATT_DIR="$SANDBOX/attr"; mkdir -p "$ATT_DIR"
printf '{"plugins":{"entries":{"codex":{"enabled":true},"other":{"enabled":true},"browser":{"enabled":true},"off":{"enabled":false}}}}\n' > "$ATT_DIR/cfg.json"
att() { printf '%s\n' "$1" > "$ATT_DIR/out.txt"; python3 "$MIGRATOR" plugin-attribute "$ATT_DIR/out.txt" "$ATT_DIR/cfg.json" 2>&1; }
A1="$(att "Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/o/openclaw/dist/plugin-sdk/x.js' imported from /h/.openclaw/extensions/codex/dist/a.js")"
A2="$(att "Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/o/openclaw/dist/browser/x.js' imported from /o/openclaw/dist/core/a.js")"
A3="$(att "ERR_MODULE_NOT_FOUND imported from /h/.openclaw/extensions/codex/a.js and from /h/.openclaw/extensions/other/b.js")"
A4="$(att "[plugins] plugin codex failed to load: ERR_MODULE_NOT_FOUND openclaw/plugin-sdk/session-store-runtime")"
A5="$(att "Error [ERR_MODULE_NOT_FOUND]: imported from /h/.openclaw/extensions/off/a.js")"
A6="$(att "everything is fine")"
if [ "${A1%%	*}" = "codex" ] && [[ "$A2" == NONE:* ]] && [[ "$A3" == NONE:*several* ]] && [ "${A4%%	*}" = "codex" ] && [[ "$A5" == NONE:* ]] && [[ "$A6" == NONE:* ]]; then
  pass "B24l: attribution — a path component (extensions/<id>) or 'plugin <id>' names the plugin; a bare directory word, two equally-named plugins, an already-disabled plugin and a clean log name NOTHING"
else
  fail "B24l: A1='$A1' A2='$A2' A3='$A3' A4='$A4' A5='$A5' A6='$A6'"
fi
python3 "$MIGRATOR" plugin-disable "$ATT_DIR/cfg.json" ghost "$ATT_DIR/ghost.out" >/dev/null 2>&1; RG=$?
if [ "$RG" -eq 3 ] && [ ! -e "$ATT_DIR/ghost.out" ]; then
  pass "B24m: disabling a plugin that has no entry is REFUSED (rc=3) - an entry is never invented, nothing written"
else
  fail "B24m: rc=$RG out-exists=$([ -e "$ATT_DIR/ghost.out" ] && echo yes || echo no)"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B-plan) --dry-run names the four new safeguards and touches nothing ---"
HPL="$(make_box bplan clean)"; SPL="$SANDBOX/stubsplan"; STPL="$SANDBOX/stateplan"
make_stubs "$SPL" "$STPL" versioned; touch "$STPL/loaded_ai.openclaw.gateway"
OUTPL="$(HOME="$HPL" PATH="$SPL:/usr/bin:/bin:/usr/sbin:/sbin" bash "$ATOMIC" --upgrade --dry-run 2>&1)"; RCPL=$?
if [ "$RCPL" -eq 0 ] && grep -q 'ORPHAN\|orphan gateway' <<<"$OUTPL" && grep -q 'plugins.entries' <<<"$OUTPL" && grep -q 'whole window' <<<"$OUTPL" \
   && grep -q 'known-good/known-bad controls' <<<"$OUTPL" \
   && grep -q '7a0\. (launchd) FTS5 repair' <<<"$OUTPL" && grep -q 'failure AFTER doctor --fix exited 0: the NEW binary' <<<"$OUTPL" \
   && ! grep -Eq 'launchctl (bootout|bootstrap)|^npm install|^openclaw doctor' "$STPL/events"; then
  pass "Bplan: --dry-run lists the orphan reap, the plugin quarantine, the held npm window, the isolated validate, the FTS5 repair and the keep-the-new-binary rule, and ran no stop/install/doctor"
else
  fail "Bplan: rc=$RCPL. Output: $OUTPL"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B-lease) on a host WITH flock the lease must not silence stderr for the rest of the run ---"
# A bare `exec 9<>"$OC_LEASE_PATH" 2>/dev/null` applies its 2>/dev/null to the WHOLE script (an exec with only redirections is
# permanent), so on Linux every later _err line and refusal banner - each rollback reason - vanished from the log, and B24j
# failed in CI only. make_stubs puts a flock on PATH so a Mac takes the same branch. The real script finds
# scripts/box-update-lock.sh beside it and uses that lease instead, so these cases run copies that sit beside the engine files
# only (mutate_copy), which take the inline flock branch. CONTROL = the shipped lease lines; each MUTANT puts back ONE old line.
LF1='{ exec 9<>"$OC_LEASE_PATH"; } 2>/dev/null || return 1'
LO1='exec 9<>"$OC_LEASE_PATH" 2>/dev/null || return 1'
LF2='if ! flock -n 9 2>/dev/null; then
      { exec 9>&-; } 2>/dev/null || true'
LO2='if ! flock -n 9 2>/dev/null; then
      exec 9>&- 2>/dev/null || true'
LF3='flock -u 9 2>/dev/null || true
      { exec 9>&-; } 2>/dev/null || true'
LO3='flock -u 9 2>/dev/null || true
      exec 9>&- 2>/dev/null || true'
LCTL="$(mutate_copy bfl-ctl "$LF1" "$LF1")"
LMU1="$(mutate_copy bfl-mut1 "$LF1" "$LO1")"
LMU2="$(mutate_copy bfl-mut2 "$LF2" "$LO2")"
LMU3="$(mutate_copy bfl-mut3 "$LF3" "$LO3")"

# lease_case <tag> <script> [busy] -> output; rc in RCL. The schema probe fails, so the run is refused AFTER the lease is
# taken and the only thing that says why is an _err line (the case-6 scenario). With "busy" the flock stub refuses -n.
lease_case() {
  local tag="$1" script="$2" busy="${3:-}" h s st
  h="$(make_box "bl$tag" clean)"; s="$SANDBOX/stubsbl$tag"; st="$SANDBOX/statebl$tag"
  make_stubs "$s" "$st" versioned 1
  [ -z "$busy" ] || touch "$st/flock_busy"
  run_atomic "$h" "$s" "$st" "$script"
}

OUTLA="$(lease_case a "$LCTL")"; RCLA=$?
if [ -n "$LCTL" ] && [ "$RCLA" -eq 78 ] && grep -qx 'flock -n 9' "$SANDBOX/statebla/flock_calls" 2>/dev/null \
   && grep -q 'flock + record' <<<"$OUTLA" && grep -q 'ERROR ROLLING BACK: `openclaw config schema` FAILED' <<<"$OUTLA" \
   && [ "$(grep -n 'flock + record' <<<"$OUTLA" | head -1 | cut -d: -f1)" -lt "$(grep -n 'ERROR ROLLING BACK' <<<"$OUTLA" | head -1 | cut -d: -f1)" ]; then
  pass "B-lease a: flock was used (flock -n 9) and the rollback reason logged AFTER the lease was taken reached the output (rc=78)"
else
  fail "B-lease a: rc=$RCLA flock_calls=$(tr '\n' '|' < "$SANDBOX/statebla/flock_calls" 2>/dev/null). Output: $OUTLA"
fi
OUTLB="$(lease_case b "$LMU1")"; RCLB=$?
if [ -n "$LMU1" ] && [ "$RCLB" -eq 78 ] && grep -q 'flock + record' <<<"$OUTLB" && grep -q 'rollback complete and VERIFIED' <<<"$OUTLB" \
   && ! grep -q 'ERROR ROLLING BACK' <<<"$OUTLB"; then
  pass "B-lease b: MUTATION PROOF - with the old 'exec 9<>lease 2>/dev/null' the same run rolls back (stdout) but the reason is GONE from the log"
else
  fail "B-lease b: the mutant did not reproduce the defect (mutant=${LMU1:-none}, rc=$RCLB). Output: $OUTLB"
fi

OUTLC="$(lease_case c "$LCTL" busy)"; RCLC=$?
if [ "$RCLC" -eq 78 ] && grep -q 'UPGRADE REFUSED' <<<"$OUTLC" && grep -q 'SHARED INSTALLATION LEASE is held' <<<"$OUTLC" \
   && ! grep -q 'installing openclaw@' <<<"$OUTLC"; then
  pass "B-lease c: a busy flock refuses (rc=78) and the refusal banner reaches the output; nothing was installed"
else
  fail "B-lease c: rc=$RCLC. Output: $OUTLC"
fi
OUTLD="$(lease_case d "$LMU2" busy)"; RCLD=$?
if [ -n "$LMU2" ] && [ "$RCLD" -eq 78 ] && ! grep -q 'UPGRADE REFUSED' <<<"$OUTLD"; then
  pass "B-lease d: MUTATION PROOF - with the old 'exec 9>&- 2>/dev/null' on the busy path the refusal banner is swallowed"
else
  fail "B-lease d: the mutant did not reproduce the defect (mutant=${LMU2:-none}, rc=$RCLD). Output: $OUTLD"
fi

# A live foreign updater already named in the lease: flock grants, the record says someone else owns it -> refuse. Pinned, because
# an unpinned run stands down earlier (the cron guard) and never reaches the acquire.
lease_foreign_case() {
  local tag="$1" script="$2" h s st sp
  h="$(make_box "bl$tag" clean)"; s="$SANDBOX/stubsbl$tag"; st="$SANDBOX/statebl$tag"
  make_stubs "$s" "$st" versioned 1
  sleep 300 >/dev/null 2>&1 & sp=$!; echo "$sp" >> "$st/spawned.pids"
  printf 'pid=%s\nrole=oc-atomic-upgrade\n' "$sp" > "$SANDBOX/lease-foreign-$tag"
  touch "$st/loaded_ai.openclaw.gateway"
  HOME="$h" PATH="$s:/usr/bin:/bin:/usr/sbin:/sbin" OPENCLAW_UPDATE_LEASE="$SANDBOX/lease-foreign-$tag" \
    OC_ATOMIC_QUIESCE_PROOF_SECONDS=1 OC_ATOMIC_STABILITY_SECONDS=1 \
    bash "$script" --upgrade --target-version "$NEW_V" 2>&1
  local rc=$?
  kill "$sp" 2>/dev/null
  return $rc
}
OUTLE="$(lease_foreign_case e "$LCTL")"; RCLE=$?
if [ "$RCLE" -eq 78 ] && grep -q 'UPGRADE REFUSED' <<<"$OUTLE" && grep -q 'SHARED INSTALLATION LEASE is held' <<<"$OUTLE"; then
  pass "B-lease e: a live foreign owner in the lease refuses the run (rc=78) and the banner reaches the output"
else
  fail "B-lease e: rc=$RCLE. Output: $OUTLE"
fi
OUTLF="$(lease_foreign_case f "$LMU3")"; RCLF=$?
if [ -n "$LMU3" ] && [ "$RCLF" -eq 78 ] && ! grep -q 'UPGRADE REFUSED' <<<"$OUTLF"; then
  pass "B-lease f: MUTATION PROOF - with the old 'exec 9>&- 2>/dev/null' on the foreign-owner path the refusal banner is swallowed"
else
  fail "B-lease f: the mutant did not reproduce the defect (mutant=${LMU3:-none}, rc=$RCLF). Output: $OUTLF"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (17) fleet-roll #18: stale openclaw CLI processes holding the state database are reaped, nothing else ---"
# Holders are REAL background processes; lsof is a stub that lists the ones still alive. Their
# command lines and ages come from the ps stub. The assertions are on which processes are alive.

# 17a. only stale bare CLIs hold it: both die, doctor runs afterwards, the upgrade completes.
H17="$(make_box b17 clean)"; S17="$SANDBOX/stubs17"; ST17="$SANDBOX/state17"
make_stubs "$S17" "$ST17" versioned
make_state_db "$H17"
P17A="$(spawn_holder "$ST17" "node /opt/x/bin/openclaw doctor --json" "05:00:00")"
P17B="$(spawn_holder "$ST17" "/usr/local/bin/openclaw config validate" "02-03:00:00")"
OUT17="$(run_atomic "$H17" "$S17" "$ST17")"; RC17=$?
if [ "$RC17" -eq 0 ] && ! alive "$P17A" && ! alive "$P17B"; then
  pass "17a: two stale bare openclaw CLI holders (a node-hosted one and a direct one, one days old) were stopped and the upgrade completed (rc=0)"
else
  fail "17a: rc=$RC17 stale holders alive: A=$(alive "$P17A" && echo yes || echo no) B=$(alive "$P17B" && echo yes || echo no). Output: $OUT17"
fi
if grep -q "reaped stale openclaw CLI holder pid $P17A (openclaw doctor" <<<"$OUT17" \
   && grep -q "reaped stale openclaw CLI holder pid $P17B (openclaw config" <<<"$OUT17"; then
  pass "17b: each kill was logged with its pid and subcommand"
else
  fail "17b: the kills were not logged. Output: $OUT17"
fi
L_REAP="$(grep -n "reaped stale openclaw CLI holder pid $P17A" <<<"$OUT17" | head -1 | cut -d: -f1)"
L_DOC="$(grep -n "running the NEW binary: openclaw doctor" <<<"$OUT17" | head -1 | cut -d: -f1)"
if [ -n "$L_REAP" ] && [ -n "$L_DOC" ] && [ "$L_REAP" -lt "$L_DOC" ]; then
  pass "17c: ORDER — the holder was reaped BEFORE doctor ran"
else
  fail "17c: reap line $L_REAP, doctor line $L_DOC"
fi

# 17d. a mixed set: the stale bare CLI dies, and so does the GATEWAY holding the database - the launchd job is
# booted out at this point, so a gateway that still owns the state dir is an ORPHAN (error #33, stopped by
# identity before anything else). A node service, the OpenClaw app, a CLI that started during this run and an
# unrelated program all survive. Doctor needs exclusive access, so it is NOT run and the upgrade rolls back
# instead of fighting over the database.
H17M="$(make_box b17m clean)"; S17M="$SANDBOX/stubs17m"; ST17M="$SANDBOX/state17m"
make_stubs "$S17M" "$ST17M" versioned
make_state_db "$H17M"
P_STALE="$(spawn_holder "$ST17M" "node /opt/x/bin/openclaw status" "05:00:00")"
P_GW="$(spawn_holder "$ST17M" "node /opt/x/lib/node_modules/openclaw/dist/index.js gateway" "05:00:00")"
P_NODE="$(spawn_holder "$ST17M" "node /opt/x/bin/openclaw node run" "05:00:00")"
P_APP="$(spawn_holder "$ST17M" "/Applications/OpenClaw.app/Contents/MacOS/OpenClaw" "05:00:00")"
P_FRESH="$(spawn_holder "$ST17M" "node /opt/x/bin/openclaw status" "00:00")"
P_OTHER="$(spawn_holder "$ST17M" "python3 /opt/x/other.py" "05:00:00")"
OUT17M="$(run_atomic "$H17M" "$S17M" "$ST17M")"; RC17M=$?
SURV=""; for p in "$P_NODE" "$P_APP" "$P_FRESH" "$P_OTHER"; do alive "$p" || SURV="$SURV $p(DEAD)"; done
if ! alive "$P_STALE" && ! alive "$P_GW" && [ -z "$SURV" ]; then
  pass "17d: the stale bare CLI and the orphan GATEWAY were stopped; the node service, OpenClaw app, a CLI started during this run and an unrelated program all survived"
else
  fail "17d: stale alive=$(alive "$P_STALE" && echo yes || echo no) gateway alive=$(alive "$P_GW" && echo yes || echo no); protected killed:$SURV"
fi
if [ "$RC17M" -eq 78 ] && [ "$(doctor_calls "$ST17M")" = "0" ] && [ "$(cat "$ST17M/version")" = "$OLD_V" ] && [ -f "$ST17M/loaded_ai.openclaw.gateway" ]; then
  pass "17e: holders that may not be stopped -> doctor NOT run, rolled back (rc=78), binary $OLD_V, gateway loaded"
else
  fail "17e: rc=$RC17M doctor_calls=$(doctor_calls "$ST17M") version=$(cat "$ST17M/version"). Output: $OUT17M"
fi
if grep -q "ORPHAN GATEWAY pid $P_GW" <<<"$OUT17M" && grep -q "pid $P_NODE is not a bare openclaw CLI" <<<"$OUT17M" \
   && grep -q "pid $P_APP is not a bare openclaw CLI" <<<"$OUT17M" && grep -q "pid $P_FRESH (openclaw status) started during this run" <<<"$OUT17M"; then
  pass "17f: the orphan gateway kill and each survivor's reason for being left alone were logged"
else
  fail "17f: missing 'left alone' reasons. Output: $OUT17M"
fi
for p in "$P_NODE" "$P_APP" "$P_FRESH" "$P_OTHER"; do kill "$p" 2>/dev/null; done

# 17g. MUTATION: with the reaper neutered the SAME stale holder survives -- so 17a measures the reaper.
python3 - "$ATOMIC" "$MUT_DIR/oc-atomic-upgrade.noreap.sh" <<'PY'
import sys
s = open(sys.argv[1], encoding="utf-8").read()
m = s.replace("_reap_state_holders() {\n", "_reap_state_holders() { return 0; }\n_reap_state_holders_neutered() {\n", 1)
if m == s:
    sys.exit(1)
open(sys.argv[2], "w", encoding="utf-8").write(m)
PY
H17N="$(make_box b17n clean)"; S17N="$SANDBOX/stubs17n"; ST17N="$SANDBOX/state17n"
make_stubs "$S17N" "$ST17N" versioned
make_state_db "$H17N"
P17N="$(spawn_holder "$ST17N" "node /opt/x/bin/openclaw doctor --json" "05:00:00")"
run_atomic "$H17N" "$S17N" "$ST17N" "$MUT_DIR/oc-atomic-upgrade.noreap.sh" >/dev/null 2>&1
if alive "$P17N" && ! cmp -s "$ATOMIC" "$MUT_DIR/oc-atomic-upgrade.noreap.sh"; then
  pass "17g: MUTATION PROOF — with _reap_state_holders neutered the same stale holder survives, so 17a is caused by the reaper"
else
  fail "17g: the stale holder died (or the mutation did not apply) with the reaper neutered"
fi
kill "$P17N" 2>/dev/null

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (18) fleet-roll #16: doctor --fix runs with the NEW binary, after the quiesce and before the start ---"
H18="$(make_box b18 clean)"; S18="$SANDBOX/stubs18"; ST18="$SANDBOX/state18"
make_stubs "$S18" "$ST18" versioned
make_state_db "$H18"
OUT18="$(run_atomic "$H18" "$S18" "$ST18")"; RC18=$?
DB18="$H18/.openclaw/state/openclaw.sqlite"
if [ "$RC18" -eq 0 ] && grep -q 'ATOMIC UPGRADE COMPLETE' <<<"$OUT18" && [ "$(doctor_calls "$ST18")" = "1" ]; then
  pass "18a: the upgrade ran doctor exactly once and completed (rc=0)"
else
  fail "18a: rc=$RC18 doctor_calls=$(doctor_calls "$ST18"). Output: $OUT18"
fi
if grep -qx 'args=doctor --fix --non-interactive' "$ST18/doctor_ctx" && grep -qx 'gateway_loaded=no' "$ST18/doctor_ctx" \
   && grep -qx "version=$NEW_V" "$ST18/doctor_ctx" && grep -qx 'stdin_rc=1' "$ST18/doctor_ctx"; then
  pass "18b: doctor ran non-interactively with stdin at EOF, with the gateway booted out, on the NEW binary ($NEW_V)"
else
  fail "18b: doctor's context was wrong: $(tr '\n' ' ' < "$ST18/doctor_ctx" 2>/dev/null)"
fi
if [ "$(event_order "$ST18" "launchctl bootout" "openclaw doctor")" = "OK" ] && [ "$(event_order "$ST18" "npm install" "openclaw doctor")" = "OK" ] \
   && [ "$(event_order "$ST18" "openclaw doctor" "launchctl bootstrap")" = "OK" ]; then
  pass "18c: ORDER — bootout, then install, then doctor, then the gateway start"
else
  fail "18c: ORDER VIOLATION. Events: $(tr '\n' '|' < "$ST18/events")"
fi
if [ "$(scope_count "$DB18" migration.legacy-audit-raw)" = "2" ]; then
  pass "18d: with doctor happy, the state database was not edited (no checkpoint rows deleted)"
else
  fail "18d: checkpoint rows were deleted although doctor never refused"
fi

# 18e. the legacy-audit-raw refusal: ONLY that scope's rows are dropped, doctor is re-run once and passes.
H18B="$(make_box b18b clean)"; S18B="$SANDBOX/stubs18b"; ST18B="$SANDBOX/state18b"
make_stubs "$S18B" "$ST18B" versioned
make_state_db "$H18B"; echo audit > "$ST18B/doctor_mode"
DB18B="$H18B/.openclaw/state/openclaw.sqlite"
OUT18B="$(run_atomic "$H18B" "$S18B" "$ST18B")"; RC18B=$?
if [ "$RC18B" -eq 0 ] && [ "$(doctor_calls "$ST18B")" = "2" ] && [ "$(scope_count "$DB18B" migration.legacy-audit-raw)" = "0" ]; then
  pass "18e: doctor refused on the audit checkpoint, the raw rows were dropped, doctor was re-run once and the upgrade completed (rc=0)"
else
  fail "18e: rc=$RC18B doctor_calls=$(doctor_calls "$ST18B") raw_rows=$(scope_count "$DB18B" migration.legacy-audit-raw). Output: $OUT18B"
fi
if [ "$(scope_count "$DB18B" migration.legacy-audit)" = "1" ] && [ "$(scope_count "$DB18B" other.scope)" = "1" ]; then
  pass "18f: the live lease scope 'migration.legacy-audit' and every other scope were left untouched (exact scope match, never a LIKE)"
else
  fail "18f: other scopes were damaged: lease=$(scope_count "$DB18B" migration.legacy-audit) other=$(scope_count "$DB18B" other.scope)"
fi
SAVED18B="$(ls "$H18B"/.openclaw/audit-checkpoint-rows-*.json 2>/dev/null | head -1)"
if [ -n "$SAVED18B" ] && [ "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$SAVED18B")" = "2" ] \
   && grep -q 'rows before=2 deleted=2 after=0' <<<"$OUT18B"; then
  pass "18g: the deleted rows were saved first and the before/after counts were logged (before=2 deleted=2 after=0)"
else
  fail "18g: no saved rows / no count log. saved='$SAVED18B'. Output: $OUT18B"
fi

# 18h. a refusal that persists after the repair: doctor is NOT looped on, the existing rollback runs.
H18C="$(make_box b18c clean)"; S18C="$SANDBOX/stubs18c"; ST18C="$SANDBOX/state18c"
make_stubs "$S18C" "$ST18C" versioned
make_state_db "$H18C"; echo audit_always > "$ST18C/doctor_mode"
CFG18C="$H18C/.openclaw/openclaw.json"; SHA18C="$(sha_of "$CFG18C")"
OUT18C="$(run_atomic "$H18C" "$S18C" "$ST18C")"; RC18C=$?
if [ "$RC18C" -eq 78 ] && [ "$(doctor_calls "$ST18C")" = "2" ] && [ "$(cat "$ST18C/version")" = "$OLD_V" ] \
   && [ "$(sha_of "$CFG18C")" = "$SHA18C" ] && [ -f "$ST18C/loaded_ai.openclaw.gateway" ]; then
  pass "18h: a refusal that survives the repair -> exactly 2 doctor runs, then rollback (rc=78): binary $OLD_V, config byte-identical, gateway loaded"
else
  fail "18h: rc=$RC18C doctor_calls=$(doctor_calls "$ST18C") version=$(cat "$ST18C/version"). Output: $OUT18C"
fi

# 18i. a doctor failure that is NOT the audit refusal: one run, no database edit, rollback -- and a stale
# CLI that grabbed the database during doctor is reaped before the rollback restarts the gateway.
H18D="$(make_box b18d clean)"; S18D="$SANDBOX/stubs18d"; ST18D="$SANDBOX/state18d"
make_stubs "$S18D" "$ST18D" versioned
make_state_db "$H18D"; echo fail_holder > "$ST18D/doctor_mode"
CFG18D="$H18D/.openclaw/openclaw.json"; SHA18D="$(sha_of "$CFG18D")"
OUT18D="$(run_atomic "$H18D" "$S18D" "$ST18D")"; RC18D=$?
if [ "$RC18D" -eq 78 ] && [ "$(doctor_calls "$ST18D")" = "1" ] && [ "$(scope_count "$H18D/.openclaw/state/openclaw.sqlite" migration.legacy-audit-raw)" = "2" ] \
   && [ "$(cat "$ST18D/version")" = "$OLD_V" ] && [ "$(sha_of "$CFG18D")" = "$SHA18D" ] && [ -f "$ST18D/loaded_ai.openclaw.gateway" ]; then
  pass "18i: doctor failure -> ONE run, no database edit, rolled back (rc=78): binary $OLD_V, config byte-identical, gateway loaded"
else
  fail "18i: rc=$RC18D doctor_calls=$(doctor_calls "$ST18D") version=$(cat "$ST18D/version"). Output: $OUT18D"
fi
P18D="$(tail -1 "$ST18D/spawned.pids" 2>/dev/null)"
if [ -n "$P18D" ] && ! alive "$P18D" && grep -q "reaped stale openclaw CLI holder pid $P18D (openclaw status, .*before the rollback restart)" <<<"$OUT18D"; then
  pass "18j: a stale CLI that took the database during doctor was reaped before the ROLLBACK restart, and logged"
else
  fail "18j: holder pid '$P18D' alive=$(alive "$P18D" && echo yes || echo no). Output: $OUT18D"
fi

# 18k. doctor that never returns is bounded and rolled back.
H18E="$(make_box b18e clean)"; S18E="$SANDBOX/stubs18e"; ST18E="$SANDBOX/state18e"
make_stubs "$S18E" "$ST18E" versioned
echo hang > "$ST18E/doctor_mode"
OUT18E="$(T_DOCTOR_TIMEOUT=2 run_atomic "$H18E" "$S18E" "$ST18E")"; RC18E=$?
if [ "$RC18E" -eq 78 ] && grep -q 'did not finish within 2s' <<<"$OUT18E" && [ "$(cat "$ST18E/version")" = "$OLD_V" ]; then
  pass "18k: a hung doctor was killed after the bound (2s) and the upgrade rolled back (rc=78)"
else
  fail "18k: rc=$RC18E. Output: $OUT18E"
fi

# 18l/m. model/provider names: doctor that changes them -> rollback; doctor that changes only something else -> fine.
H18F="$(make_box b18f clean)"; S18F="$SANDBOX/stubs18f"; ST18F="$SANDBOX/state18f"
make_stubs "$S18F" "$ST18F" versioned
set_models "$H18F"; echo models > "$ST18F/doctor_mode"
CFG18F="$H18F/.openclaw/openclaw.json"; cp "$CFG18F" "$SANDBOX/cfg18f.before"
OUT18F="$(run_atomic "$H18F" "$S18F" "$ST18F")"; RC18F=$?
# the put-back rewrites the file (a trailing newline), so "put back" is proved on the parsed JSON, not the bytes
if [ "$RC18F" -eq 71 ] && grep -q 'changed the model/provider selection' <<<"$OUT18F" \
   && python3 -c 'import json,sys; sys.exit(json.load(open(sys.argv[1])) != json.load(open(sys.argv[2])))' "$CFG18F" "$SANDBOX/cfg18f.before" \
   && [ "$(cat "$ST18F/version")" = "$NEW_V" ] && ! grep -q 'doctor-changed' "$CFG18F"; then
  # doctor exited 0, so the databases are migrated and the old build cannot go back (v1.4.0): the run still FAILS, but
  # the model keys are put back from the values saved before doctor (here the config comes out identical as JSON).
  pass "18l: doctor changed agents.defaults.model -> the run fails (rc=71), the model keys put back (config identical as JSON), binary stays $NEW_V"
else
  fail "18l: rc=$RC18F. Output: $OUT18F"
fi
H18G="$(make_box b18g clean)"; S18G="$SANDBOX/stubs18g"; ST18G="$SANDBOX/state18g"
make_stubs "$S18G" "$ST18G" versioned
set_models "$H18G"; echo touch > "$ST18G/doctor_mode"
OUT18G="$(run_atomic "$H18G" "$S18G" "$ST18G")"; RC18G=$?
if [ "$RC18G" -eq 0 ] && grep -q '"doctorWasHere": true' "$H18G/.openclaw/openclaw.json" && grep -q '"primary": "p/one"' "$H18G/.openclaw/openclaw.json" \
   && grep -q 'model/provider names identical' <<<"$OUT18G"; then
  pass "18m: CONTROL — doctor changed only an unrelated key, model names identical -> the upgrade completed (rc=0); the model check is not over-sensitive"
else
  fail "18m: rc=$RC18G. Output: $OUT18G"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B-bak) the config backup this run wrote is deleted once the upgrade is PROVEN complete, and kept on any rollback ---"
# Step 4 writes <root>/openclaw.json.bak-pre-atomic-upgrade-<ts>. Trevor's order of 2026-10-29: a backup made of
# somebody's OpenClaw is deleted as soon as the install is completed. "Completed" here = the doctor model/provider
# check and `config validate` passed, the stability window held, /healthz answered 200 and the gateway runs the
# target. Each case reads the backup path from the script's own "config backed up:" line, so a pass is never
# "no backup was ever written".
bak_path() { sed -n 's/.*config backed up: //p' <<<"$1" | head -1; }
bak_files() { ls "$1/.openclaw"/openclaw.json.bak-pre-atomic-upgrade-* 2>/dev/null | wc -l | tr -d ' '; }

# a. a clean box upgrades: the backup was written, then deleted, and the deletion is logged by path
HBA="$(make_box bbak-a clean)"; SBA="$SANDBOX/stubsbba"; STBA="$SANDBOX/statebba"
make_stubs "$SBA" "$STBA" versioned
OUTBA="$(run_atomic "$HBA" "$SBA" "$STBA")"; RCBA=$?
PBA="$(bak_path "$OUTBA")"
if [ "$RCBA" -eq 0 ] && [ -n "$PBA" ] && [ ! -e "$PBA" ] && [ "$(bak_files "$HBA")" = "0" ] \
   && grep -q "config backup deleted: $PBA" <<<"$OUTBA" && grep -q "backup deleted: $PBA" <<<"$OUTBA"; then
  pass "Ba: success (rc=0) wrote a config backup, then deleted it and logged the path; none is left in the root"
else
  fail "Ba: rc=$RCBA path='$PBA' left=$(bak_files "$HBA"). Output: $OUTBA"
fi

# b. a LEGACY box is migrated and the upgrade completes: the backup that protected the migration is deleted too
HBB="$(make_box bbak-b legacy)"; SBB="$SANDBOX/stubsbbb"; STBB="$SANDBOX/statebbb"
make_stubs "$SBB" "$STBB" versioned
OUTBB="$(run_atomic "$HBB" "$SBB" "$STBB")"; RCBB=$?
PBB="$(bak_path "$OUTBB")"
if [ "$RCBB" -eq 0 ] && [ -n "$PBB" ] && [ ! -e "$PBB" ] && [ "$(bak_files "$HBB")" = "0" ] \
   && [ "$(cfg_shape "$HBB/.openclaw/openclaw.json" | cut -d: -f1)" = "ENTRIES" ]; then
  pass "Bb: a migrated legacy box that completed the upgrade has no backup left, and the config is on agents.entries"
else
  fail "Bb: rc=$RCBB path='$PBB' left=$(bak_files "$HBB") shape=$(cfg_shape "$HBB/.openclaw/openclaw.json"). Output: $OUTBB"
fi

# c. the gateway crash-loops after the migration (stability window fails, v1.4.0: after doctor): the new build stays, the backup is KEPT and is the original
HBC="$(make_box bbak-c legacy)"; SBC="$SANDBOX/stubsbbc"; STBC="$SANDBOX/statebbc"
make_stubs "$SBC" "$STBC" versioned
SHABC="$(sha_of "$HBC/.openclaw/openclaw.json")"; touch "$STBC/pid_flip"
OUTBC="$(run_atomic "$HBC" "$SBC" "$STBC")"; RCBC=$?
PBC="$(bak_path "$OUTBC")"
if [ "$RCBC" -eq 71 ] && [ -n "$PBC" ] && [ -f "$PBC" ] && [ "$(sha_of "$PBC")" = "$SHABC" ] \
   && [ "$(cfg_shape "$HBC/.openclaw/openclaw.json" | cut -d: -f1)" = "ENTRIES" ] && ! grep -q 'config backup deleted' <<<"$OUTBC"; then
  pass "Bc: a failed stability window after doctor (rc=71, the new build stays) KEPT the backup, byte-identical to the original config"
else
  fail "Bc: rc=$RCBC path='$PBC' exists=$([ -f "$PBC" ] && echo yes || echo no). Output: $OUTBC"
fi

# d. doctor changes the model selection (the model check fails, v1.4.0: after doctor): the new build stays, the backup is KEPT
HBD="$(make_box bbak-d clean)"; SBD="$SANDBOX/stubsbbd"; STBD="$SANDBOX/statebbd"
make_stubs "$SBD" "$STBD" versioned
set_models "$HBD"; echo models > "$STBD/doctor_mode"
SHABD="$(sha_of "$HBD/.openclaw/openclaw.json")"
OUTBD="$(run_atomic "$HBD" "$SBD" "$STBD")"; RCBD=$?
PBD="$(bak_path "$OUTBD")"
if [ "$RCBD" -eq 71 ] && [ -n "$PBD" ] && [ -f "$PBD" ] && [ "$(sha_of "$PBD")" = "$SHABD" ] && ! grep -q 'config backup deleted' <<<"$OUTBD"; then
  pass "Bd: a failed model/provider check (rc=71) KEPT the backup"
else
  fail "Bd: rc=$RCBD path='$PBD' exists=$([ -f "$PBD" ] && echo yes || echo no). Output: $OUTBD"
fi

# e. a backup left by an EARLIER run is not this run's and is not touched
HBE="$(make_box bbak-e clean)"; SBE="$SANDBOX/stubsbbe"; STBE="$SANDBOX/statebbe"
make_stubs "$SBE" "$STBE" versioned
printf '{}\n' > "$HBE/.openclaw/openclaw.json.bak-pre-atomic-upgrade-20250101-000000"
OUTBE="$(run_atomic "$HBE" "$SBE" "$STBE")"; RCBE=$?
if [ "$RCBE" -eq 0 ] && [ -f "$HBE/.openclaw/openclaw.json.bak-pre-atomic-upgrade-20250101-000000" ] && [ "$(bak_files "$HBE")" = "1" ]; then
  pass "Be: success deleted only this run's backup; an earlier run's copy was left alone"
else
  fail "Be: rc=$RCBE left=$(bak_files "$HBE"). Output: $OUTBE"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B-node) v1.2.3, Big Fleet Roll 20261029: npm runs under the SUPERVISOR's node, and a failed install says why ---"
# Four Macs rolled back with exit 78 and no reason in the log. npm is a \`#!/usr/bin/env node\` script, so it
# runs under the FIRST node on PATH. The script put the supervisor's prefix bin (/opt/homebrew/bin, holding the
# stale Homebrew node the node-floor step had just replaced) IN FRONT of the supervisor's own node dir, so
# openclaw's preinstall guard saw Node 26.8.1 and exited 1. Fixture: the plist's node+npm live in
# supnode/node/bin; the prefix's own bin holds a DECOY node (the stale one). The stub npm records the first
# node on PATH when it runs.
make_node_box() {   # <tag> -> sets HN SN STN SUPN
  local tag="$1"
  HN="$(make_box "bn$tag" clean)"; SN="$SANDBOX/stubsbn$tag"; STN="$SANDBOX/statebn$tag"
  make_stubs "$SN" "$STN" versioned
  SUPN="$SANDBOX/supbn$tag"; mkdir -p "$SUPN/node/bin" "$SUPN/npm-global/bin"
  cp "$SN/node" "$SN/npm" "$SUPN/node/bin/"
  cp "$SN/node" "$SUPN/npm-global/bin/node"
  write_supervisor "$HN" "$SUPN/node/bin/node" "$SUPN/npm-global" "$OLD_V"
  printf 'node %s/npm-global/lib/node_modules/openclaw/dist/index.js gateway\n' "$SUPN" > "$STN/ps_args"
}
make_node_box a
OUTBN="$(run_atomic "$HN" "$SN" "$STN")"; RCBN=$?
if [ "$RCBN" -eq 0 ] && [ -s "$STN/npm_node" ] && ! grep -qvxF "$SUPN/node/bin/node" "$STN/npm_node"; then
  pass "Bn1: CONTROL — every npm install ran under the supervisor's node ($SUPN/node/bin/node), not the prefix bin's decoy; upgrade rc=0"
else
  fail "Bn1: rc=$RCBN, node npm ran under: $(tr '\n' '|' < "$STN/npm_node" 2>/dev/null). Output: $OUTBN"
fi
if ! grep -q 'npm| ' <<<"$OUTBN"; then
  pass "Bn2: a SUCCESSFUL install prints no npm output block (no noise)"
else
  fail "Bn2: npm output was printed for a successful install. Output: $OUTBN"
fi

# MUTATION: put the two PATH prepends back in the OLD order. The same box must now run npm under the decoy.
MUTBN="$(mutate_copy bnode-mut '  [ -d "$SUP_PREFIX/bin" ] && PATH="$SUP_PREFIX/bin:$PATH"
  [ -n "$node_dir" ] && [ -d "$node_dir" ] && PATH="$node_dir:$PATH"
' '  [ -n "$node_dir" ] && [ -d "$node_dir" ] && PATH="$node_dir:$PATH"
  [ -d "$SUP_PREFIX/bin" ] && PATH="$SUP_PREFIX/bin:$PATH"
')"
make_node_box m
OUTBNM="$(run_atomic "$HN" "$SN" "$STN" "$MUTBN")"; RCBNM=$?
if [ -n "$MUTBN" ] && grep -qxF "$SUPN/npm-global/bin/node" "$STN/npm_node" 2>/dev/null; then
  pass "Bn3: MUTATION PROOF — with only the PATH order reverted, npm ran under the prefix bin's (stale) node: the defect reproduces"
else
  fail "Bn3: the mutant did not reproduce the defect (mutant=${MUTBN:-none}, rc=$RCBNM, node: $(tr '\n' '|' < "$STN/npm_node" 2>/dev/null)), so Bn1 measures nothing"
fi

# FAILURE OUTPUT: npm dies with 100 lines, a token-looking line and the reason. The job log must carry the last
# 40 lines (the reason included), not the earlier ones, not the token, and say which node npm ran under.
make_node_box f; touch "$STN/npm_noisy_fail"
OUTBNF="$(run_atomic "$HN" "$SN" "$STN")"; RCBNF=$?
if [ "$RCBNF" -eq 78 ] && [ "$(cat "$STN/version")" = "$OLD_V" ]; then
  pass "Bn4: a failing npm install still rolls back cleanly (rc=78, binary $OLD_V)"
else
  fail "Bn4: rc=$RCBNF version=$(cat "$STN/version"). Output: $OUTBNF"
fi
if grep -q 'requires Node >=26.12.1' <<<"$OUTBNF" && grep -q 'npm| npmline 100$' <<<"$OUTBNF" && grep -q 'npm| npmline 63$' <<<"$OUTBNF"; then
  pass "Bn5: the failure reason and the tail of npm's output are in the job log"
else
  fail "Bn5: npm's error output is missing from the log. Output: $OUTBNF"
fi
if ! grep -q 'npmline 62$' <<<"$OUTBNF" && ! grep -q 'npmline 1$' <<<"$OUTBNF"; then
  pass "Bn6: only the LAST 40 lines are shown (line 62 and earlier are not)"
else
  fail "Bn6: more than the last 40 lines were printed. Output: $OUTBNF"
fi
if ! grep -q 'SECRETVALUE123' <<<"$OUTBNF"; then
  pass "Bn7: a token-looking line in npm's output is not copied into the log"
else
  fail "Bn7: a secret-looking line reached the log"
fi
if grep -qF "ran under $SUPN/node/bin/node" <<<"$OUTBNF"; then
  pass "Bn8: the log names the node npm ran under ($SUPN/node/bin/node)"
else
  fail "Bn8: the log does not say which node npm ran under. Output: $OUTBNF"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B-kb) v1.4.0: once doctor --fix exited 0 the NEW binary stays; the old one is never reinstalled on migrated state ---"
# doctor --fix stamps the config and migrates the agent/session SQLite databases forward. The previous build
# cannot read that pair, and the script takes no copy of the databases to restore, so a rollback that reinstalls
# it only trades a failed proof for a crash loop. Every case below fails AFTER doctor returned 0 and asserts what
# the box actually looks like afterwards: the binary, the config, the gateway, the exit code.
kb_setup() {   # <tag> <config-kind> -> KH (home) KS (stubs) KST (state), a state database for the holders to hold
  KH="$(make_box "$1" "$2")"; KS="$SANDBOX/stubs$1"; KST="$SANDBOX/state$1"
  make_stubs "$KS" "$KST" versioned
  make_state_db "$KH"
}
old_build_installed() { grep -q "openclaw@$OLD_V" "$1/npm_installs" 2>/dev/null; }   # the stub npm logs every install it was asked for

# KB-a. the gateway answers /healthz 200 on the new build, but the "launched from the supervisor's package" proof
# fails. A LEGACY config was migrated to agents.entries before doctor: it must stay migrated (the new build rejects `list`).
kb_setup bkba legacy
SHAKBA="$(sha_of "$KH/.openclaw/openclaw.json")"
echo "node /somewhere/else/index.js gateway" > "$KST/ps_args"
OUTKBA="$(run_atomic "$KH" "$KS" "$KST")"; RCKBA=$?
BAKKBA="$(sed -n 's/.*config backed up: //p' <<<"$OUTKBA" | head -1)"
if [ "$RCKBA" -eq 71 ] && [ "$(cat "$KST/version")" = "$NEW_V" ] && ! old_build_installed "$KST" \
   && ! grep -q 'reinstalling the previous binary' <<<"$OUTKBA"; then
  pass "KB-a1: a failed proof AFTER doctor -> rc=71 (STUCK), binary stays $NEW_V, the previous build is never reinstalled"
else
  fail "KB-a1: rc=$RCKBA version=$(cat "$KST/version") old_reinstalled=$(old_build_installed "$KST" && echo yes || echo no). Output: $OUTKBA"
fi
if [ "$(cfg_shape "$KH/.openclaw/openclaw.json" | cut -d: -f1)" = "ENTRIES" ] && [ "$(sha_of "$KH/.openclaw/openclaw.json")" != "$SHAKBA" ] \
   && ! grep -q 'config restored from' <<<"$OUTKBA"; then
  pass "KB-a2: the migrated config (agents.entries) was NOT restored to the legacy list the new build rejects"
else
  fail "KB-a2: config shape=$(cfg_shape "$KH/.openclaw/openclaw.json"). Output: $OUTKBA"
fi
if [ -n "$BAKKBA" ] && [ -f "$BAKKBA" ] && [ "$(sha_of "$BAKKBA")" = "$SHAKBA" ] && grep -qF "backup is KEPT for takeover: $BAKKBA" <<<"$OUTKBA"; then
  pass "KB-a3: the pre-migration backup is kept, byte-identical to the original, and named for takeover"
else
  fail "KB-a3: backup path='$BAKKBA'. Output: $OUTKBA"
fi
if [ -f "$KST/loaded_ai.openclaw.gateway" ] && [ "$(grep -c '^launchctl bootout' "$KST/events")" -le 2 ] \
   && ! grep -q 'launchctl kickstart' "$KST/events" && grep -q 'nothing is restarted' <<<"$OUTKBA"; then
  pass "KB-a4: the gateway already answered, so nothing was restarted; the gateway is loaded"
else
  fail "KB-a4: loaded=$([ -f "$KST/loaded_ai.openclaw.gateway" ] && echo yes || echo no). Output: $OUTKBA"
fi
if grep -q 'STUCK: openclaw@'"$NEW_V"' is installed on migrated state and the gateway is serving, but this proof failed: the gateway is not running the target build' <<<"$OUTKBA" \
   && grep -q 'was not launched from' <<<"$OUTKBA" \
   && grep -q 'ERROR NOT ROLLING BACK' <<<"$OUTKBA" && ! grep -q 'ERROR ROLLING BACK:' <<<"$OUTKBA"; then
  pass "KB-a5: STUCK names the exact failed proof (the gateway is not running the target build; its own error says it was not launched from the supervisor's package)"
else
  fail "KB-a5: no STUCK line with the failing proof. Output: $OUTKBA"
fi

# KB-b. the gateway cannot be started after doctor (bootstrap fails once, then works): ONE clean restart of the NEW
# binary, nothing else; it answers -> the same STUCK, rc 71, never the old build.
kb_setup bkbb clean
touch "$KST/bootstrap_fail_once"
OUTKBB="$(run_atomic "$KH" "$KS" "$KST")"; RCKBB=$?
if [ "$RCKBB" -eq 71 ] && [ "$(cat "$KST/version")" = "$NEW_V" ] && ! old_build_installed "$KST" && [ -f "$KST/loaded_ai.openclaw.gateway" ] \
   && grep -q 'ONE clean restart of the NEW build' <<<"$OUTKBB" && grep -q 'PROVEN back and HELD' <<<"$OUTKBB"; then
  pass "KB-b: a gateway that did not start after doctor got ONE clean restart on the new build, came back, STUCK (rc=71), old build never installed"
else
  fail "KB-b: rc=$RCKBB version=$(cat "$KST/version") loaded=$([ -f "$KST/loaded_ai.openclaw.gateway" ] && echo yes || echo no). Output: $OUTKBB"
fi

# KB-c. the gateway is loaded but never answers /healthz, and the one clean restart does not help: BROKEN, rc 70, loud,
# and the previous build is STILL not reinstalled.
kb_setup bkbc legacy
SHAKBC="$(sha_of "$KH/.openclaw/openclaw.json")"
touch "$KST/healthz_down"
OUTKBC="$(T_HEALTH_TIMEOUT=3 run_atomic "$KH" "$KS" "$KST")"; RCKBC=$?
if [ "$RCKBC" -eq 70 ] && grep -q 'new binary unhealthy after migration; rollback unsafe' <<<"$OUTKBC" \
   && [ "$(cat "$KST/version")" = "$NEW_V" ] && ! old_build_installed "$KST" && ! grep -q 'reinstalling the previous binary' <<<"$OUTKBC"; then
  pass "KB-c1: a gateway dark after the one clean restart -> rc=70 with 'new binary unhealthy after migration; rollback unsafe'; old build never installed"
else
  fail "KB-c1: rc=$RCKBC version=$(cat "$KST/version"). Output: $OUTKBC"
fi
if grep -q '^launchctl kickstart -k gui/[0-9]*/ai.openclaw.gateway' "$KST/events" \
   && [ "$(grep -c '^launchctl kickstart -k' "$KST/events")" = "1" ]; then
  pass "KB-c2: the loaded-but-silent gateway got exactly ONE clean restart (kickstart -k), not a loop"
else
  fail "KB-c2: restarts: $(grep '^launchctl kickstart' "$KST/events" | tr '\n' '|')"
fi
if [ "$(cfg_shape "$KH/.openclaw/openclaw.json" | cut -d: -f1)" = "ENTRIES" ] && [ "$(sha_of "$KH/.openclaw/openclaw.json")" != "$SHAKBC" ] \
   && ls "$KH/.openclaw"/openclaw.json.bak-pre-atomic-upgrade-* >/dev/null 2>&1 && grep -q 'Pre-migration config backup (kept):' <<<"$OUTKBC"; then
  pass "KB-c3: the dark box keeps its migrated config and the pre-migration backup (for the takeover)"
else
  fail "KB-c3: shape=$(cfg_shape "$KH/.openclaw/openclaw.json"). Output: $OUTKBC"
fi
if [ ! -e "$KH/.openclaw/.openclaw-maintenance-lock" ]; then
  pass "KB-c4: the maintenance lock was released even though the box is dark"
else
  fail "KB-c4: the maintenance lock is still held"
fi

# KB-d. doctor changes the model selection: the model keys (defaults.model, the pins, an agent's own model) are put
# back from the values saved before doctor; the config is NOT restored whole (it carries doctor's other work).
kb_setup bkbd legacy
python3 - "$KH/.openclaw/openclaw.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
c["agents"]["defaults"]["model"] = {"primary": "p/one", "fallbacks": ["p/two"]}
c["agents"]["list"][1]["model"] = "p/agent-own"
json.dump(c, open(sys.argv[1], "w"), indent=2)
PY
echo models_all > "$KST/doctor_mode"
OUTKBD="$(run_atomic "$KH" "$KS" "$KST")"; RCKBD=$?
CFGKBD="$KH/.openclaw/openclaw.json"
KBDCHK="$(python3 - "$CFGKBD" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])); a = c["agents"]; d = a["defaults"]
print("model=%s pins=%s agent=%s doctorWasHere=%s shape=%s" % (
    json.dumps(d.get("model"), sort_keys=True), json.dumps(d.get("models"), sort_keys=True),
    a["entries"]["worker-a"].get("model"), c.get("doctorWasHere"), "entries" if "entries" in a else "list"))
PY
)"
if [ "$RCKBD" -eq 71 ] && [ "$(cat "$KST/version")" = "$NEW_V" ] && ! old_build_installed "$KST" \
   && grep -q 'changed the model/provider selection' <<<"$OUTKBD" && grep -q 'model keys were put back' <<<"$OUTKBD"; then
  pass "KB-d1: doctor changed the model selection -> the run fails (rc=71) on the NEW binary; the old build is not reinstalled"
else
  fail "KB-d1: rc=$RCKBD version=$(cat "$KST/version"). Output: $OUTKBD"
fi
if [ "$KBDCHK" = 'model={"fallbacks": ["p/two"], "primary": "p/one"} pins={"primary": "pinned-model-do-not-touch"} agent=p/agent-own doctorWasHere=True shape=entries' ]; then
  pass "KB-d2: defaults.model, the pins and the agent's own model are exactly as before doctor; doctor's other change and the migrated shape stay"
else
  fail "KB-d2: config after: $KBDCHK"
fi

# KB-e. the doctor-refuses / doctor-fails / doctor-killed paths never COMPLETED doctor: the existing rollback, unchanged,
# on a MIGRATED config: the old binary and the legacy config go back byte for byte.
kb_setup bkbe legacy
SHAKBE="$(sha_of "$KH/.openclaw/openclaw.json")"; echo fail > "$KST/doctor_mode"
OUTKBE="$(run_atomic "$KH" "$KS" "$KST")"; RCKBE=$?
if [ "$RCKBE" -eq 78 ] && [ "$(cat "$KST/version")" = "$OLD_V" ] && [ "$(sha_of "$KH/.openclaw/openclaw.json")" = "$SHAKBE" ] \
   && [ -f "$KST/loaded_ai.openclaw.gateway" ] && grep -q 'ERROR ROLLING BACK:' <<<"$OUTKBE" && ! grep -q 'NOT ROLLING BACK' <<<"$OUTKBE"; then
  pass "KB-e: doctor exited non-zero (never completed) -> the unchanged rollback: rc=78, binary $OLD_V, legacy config byte-identical, gateway loaded"
else
  fail "KB-e: rc=$RCKBE version=$(cat "$KST/version"). Output: $OUTKBE"
fi

# KB-f. MUTATION: with ONLY the hook in _rollback neutered, the SAME box as KB-a is rolled back onto the old build
# and the legacy config -- proving KB-a is caused by DOCTOR_RAN, not by luck.
python3 - "$ATOMIC" "$MUT_DIR/oc-atomic-upgrade.nokeep.sh" <<'PY'
import sys
s = open(sys.argv[1], encoding="utf-8").read()
m = s.replace('if [ "$DOCTOR_RAN" = "1" ]; then _keep_new_binary "$why"; return $?; fi', ':', 1)
if m == s:
    sys.exit(1)
open(sys.argv[2], "w", encoding="utf-8").write(m)
PY
kb_setup bkbf legacy
SHAKBF="$(sha_of "$KH/.openclaw/openclaw.json")"
echo "node /somewhere/else/index.js gateway" > "$KST/ps_args"
OUTKBF="$(run_atomic "$KH" "$KS" "$KST" "$MUT_DIR/oc-atomic-upgrade.nokeep.sh")"; RCKBF=$?
if ! cmp -s "$ATOMIC" "$MUT_DIR/oc-atomic-upgrade.nokeep.sh" && [ "$RCKBF" -eq 78 ] && [ "$(cat "$KST/version")" = "$OLD_V" ] \
   && old_build_installed "$KST" && [ "$(sha_of "$KH/.openclaw/openclaw.json")" = "$SHAKBF" ]; then
  pass "KB-f: MUTATION PROOF — with the _rollback hook neutered the same box goes back to $OLD_V and the legacy config (the defect reproduced), so KB-a is caused by the hook"
else
  fail "KB-f: rc=$RCKBF version=$(cat "$KST/version"). Output: $OUTKBF"
fi

# KB-g. a plugin quarantined for doctor stays quarantined when a LATER proof fails (the config is not restored), and the
# record says "quarantined", not "reverted-by-rollback" (compare B24h, where doctor itself never completed).
kb_setup bkbg plugin
printf 'codex' > "$KST/doctor_broken_plugin"; echo "node /somewhere/else/index.js gateway" > "$KST/ps_args"
OUTKBG="$(run_atomic "$KH" "$KS" "$KST")"; RCKBG=$?
RECKBG="$KH/.openclaw/oc-atomic-plugin-quarantine.jsonl"
CODEXKBG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["plugins"]["entries"]["codex"]["enabled"])' "$KH/.openclaw/openclaw.json" 2>/dev/null)"
if [ "$RCKBG" -eq 71 ] && [ "$CODEXKBG" = "False" ] && grep -q '"event": "quarantined"' "$RECKBG" && ! grep -q 'reverted-by-rollback' "$RECKBG" \
   && grep -q "plugins: entry DISABLED because its module fails to load: codex" <<<"$OUTKBG"; then
  pass "KB-g: a plugin quarantined for doctor stays disabled after a later failed proof (rc=71); the record and the log say so, nothing claims it was reverted"
else
  fail "KB-g: rc=$RCKBG codex.enabled=$CODEXKBG record: $(cat "$RECKBG" 2>/dev/null). Output: $OUTKBG"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B-app) v1.4.0: the OpenClaw app's read-only openclaw-node-worker is tolerated, never stopped; nothing else is ---"
# On a Mac running /Applications/OpenClaw.app the app's child \`openclaw-node-worker\` holds state/openclaw.sqlite
# READ-ONLY and the app respawns it ~10 s after it is stopped, so the before-doctor gate refused and rolled back
# every time. The predicate is three facts at once: the name, an OpenClaw.app ancestor, lsof access mode r.
APPMAIN="/Applications/OpenClaw.app/Contents/MacOS/OpenClaw"
app_worker() {   # <state> <lsof mode> <worker name> <parent args> [grandparent args] -> prints the worker pid
  local st="$1" mode="$2" name="$3" parent="$4" grand="${5:-}" p
  p="$(spawn_holder "$st" "$name" "05:00:00")"
  echo "$mode" > "$st/lsof_mode_$p"
  if [ -n "$grand" ]; then
    echo "$((p + 100000))" > "$st/ps_$p.ppid"; echo "$parent" > "$st/ps_$((p + 100000)).args"
    echo "$((p + 200000))" > "$st/ps_$((p + 100000)).ppid"; echo "$grand" > "$st/ps_$((p + 200000)).args"
  else
    echo "$((p + 100000))" > "$st/ps_$p.ppid"; echo "$parent" > "$st/ps_$((p + 100000)).args"
  fi
  echo "$p"
}

# a. the worker (named, app parent, mode r) holds the database: the gate passes, the upgrade completes, the worker lives
kb_setup bapa clean
PAPA="$(app_worker "$KST" r openclaw-node-worker "$APPMAIN")"
OUTAPA="$(run_atomic "$KH" "$KS" "$KST")"; RCAPA=$?
if [ "$RCAPA" -eq 0 ] && alive "$PAPA" && [ "$(doctor_calls "$KST")" = "1" ] && [ "$(cat "$KST/version")" = "$NEW_V" ]; then
  pass "App-a1: with the app's read-only worker holding the database the before-doctor gate passed and the upgrade completed (rc=0); the worker is still alive"
else
  fail "App-a1: rc=$RCAPA worker alive=$(alive "$PAPA" && echo yes || echo no) doctor_calls=$(doctor_calls "$KST"). Output: $OUTAPA"
fi
if grep -q "state-database holder pid $PAPA is the OpenClaw app's own openclaw-node-worker, holding the database READ-ONLY - tolerated, NOT stopped" <<<"$OUTAPA" \
   && ! grep -q "reaped stale openclaw CLI holder pid $PAPA" <<<"$OUTAPA" && ! grep -q "state database is still held by pid(s): .*$PAPA" <<<"$OUTAPA"; then
  pass "App-a2: the tolerated worker was logged by pid, never signalled, and never counted as a holder that is left"
else
  fail "App-a2: Output: $OUTAPA"
fi
kill "$PAPA" 2>/dev/null

# b. the worker one level further up (a wrapper between it and the app) is still the app's child
kb_setup bapb clean
PAPB="$(app_worker "$KST" r openclaw-node-worker "sh -c /opt/x/run-worker" "$APPMAIN")"
OUTAPB="$(run_atomic "$KH" "$KS" "$KST")"; RCAPB=$?
if [ "$RCAPB" -eq 0 ] && alive "$PAPB"; then
  pass "App-b: an OpenClaw.app that is a grandparent (not only the parent) of the worker is found"
else
  fail "App-b: rc=$RCAPB. Output: $OUTAPB"
fi
kill "$PAPB" 2>/dev/null

# c-f. each of the three facts, broken ONE at a time, restores the refusal: the gate fails, doctor never runs, rollback
app_refused() {   # <label> <state> <worker pid> <rc> <out>
  if [ "$4" -eq 78 ] && [ "$(doctor_calls "$2")" = "0" ] && [ "$(cat "$2/version")" = "$OLD_V" ] && alive "$3" \
     && grep -q 'still holds .*state/openclaw.sqlite' <<<"$5"; then
    pass "$1"
  else
    fail "$1 -- rc=$4 doctor_calls=$(doctor_calls "$2") version=$(cat "$2/version") alive=$(alive "$3" && echo yes || echo no). Output: $5"
  fi
}
kb_setup bapc clean
PAPC="$(app_worker "$KST" u openclaw-node-worker "$APPMAIN")"
OUTAPC="$(run_atomic "$KH" "$KS" "$KST")"; RCAPC=$?
app_refused "App-c: the worker opens the database READ-WRITE (lsof mode u) -> refused: rc=78, doctor not run, rolled back, worker not killed" "$KST" "$PAPC" "$RCAPC" "$OUTAPC"
kill "$PAPC" 2>/dev/null
kb_setup bapd clean
PAPD="$(app_worker "$KST" r openclaw-node-worker "/usr/bin/some-other-parent")"
OUTAPD="$(run_atomic "$KH" "$KS" "$KST")"; RCAPD=$?
app_refused "App-d: the worker's parent is NOT OpenClaw.app -> refused: rc=78, doctor not run, rolled back, worker not killed" "$KST" "$PAPD" "$RCAPD" "$OUTAPD"
kill "$PAPD" 2>/dev/null
kb_setup bape clean
PAPE="$(app_worker "$KST" r openclaw-other-worker "$APPMAIN")"
OUTAPE="$(run_atomic "$KH" "$KS" "$KST")"; RCAPE=$?
app_refused "App-e: a read-only holder of the app that is NOT named openclaw-node-worker -> refused: rc=78, doctor not run, rolled back" "$KST" "$PAPE" "$RCAPE" "$OUTAPE"
kill "$PAPE" 2>/dev/null
kb_setup bapf clean
PAPF="$(app_worker "$KST" "" openclaw-node-worker "$APPMAIN")"
rm -f "$KST/lsof_mode_$PAPF"      # lsof cannot say how it opens the file: UNDETERMINED is not "read-only"
OUTAPF="$(run_atomic "$KH" "$KS" "$KST")"; RCAPF=$?
app_refused "App-f: lsof cannot show the access mode -> refused (undetermined is never read-only): rc=78, doctor not run, rolled back" "$KST" "$PAPF" "$RCAPF" "$OUTAPF"
kill "$PAPF" 2>/dev/null

# g. a stale bare CLI next to the worker is still reaped; the worker still survives
kb_setup bapg clean
PAPG="$(app_worker "$KST" r openclaw-node-worker "$APPMAIN")"
PCLI="$(spawn_holder "$KST" "node /opt/x/bin/openclaw status" "05:00:00")"
OUTAPG="$(run_atomic "$KH" "$KS" "$KST")"; RCAPG=$?
if [ "$RCAPG" -eq 0 ] && alive "$PAPG" && ! alive "$PCLI" && grep -q "reaped stale openclaw CLI holder pid $PCLI" <<<"$OUTAPG"; then
  pass "App-g: the stale bare CLI was still reaped while the app's worker was tolerated"
else
  fail "App-g: rc=$RCAPG worker alive=$(alive "$PAPG" && echo yes || echo no) cli alive=$(alive "$PCLI" && echo yes || echo no). Output: $OUTAPG"
fi
kill "$PAPG" 2>/dev/null

# h. MUTATION: with the predicate neutered the SAME box as App-a rolls back, so App-a is caused by the predicate
python3 - "$ATOMIC" "$MUT_DIR/oc-atomic-upgrade.noapp.sh" <<'PY'
import sys
s = open(sys.argv[1], encoding="utf-8").read()
m = s.replace("_benign_app_reader() {\n", "_benign_app_reader() { return 1; }\n_benign_app_reader_off() {\n", 1)
if m == s:
    sys.exit(1)
open(sys.argv[2], "w", encoding="utf-8").write(m)
PY
kb_setup bapm clean
PAPM="$(app_worker "$KST" r openclaw-node-worker "$APPMAIN")"
OUTAPM="$(run_atomic "$KH" "$KS" "$KST" "$MUT_DIR/oc-atomic-upgrade.noapp.sh")"; RCAPM=$?
if ! cmp -s "$ATOMIC" "$MUT_DIR/oc-atomic-upgrade.noapp.sh" && [ "$RCAPM" -eq 78 ] && [ "$(doctor_calls "$KST")" = "0" ]; then
  pass "App-h: MUTATION PROOF — with the predicate neutered the same box refuses and rolls back (the exit-78 defect reproduced), so App-a is caused by the predicate"
else
  fail "App-h: rc=$RCAPM doctor_calls=$(doctor_calls "$KST"). Output: $OUTAPM"
fi
kill "$PAPM" 2>/dev/null

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- (B-fts) v1.4.0: the FTS5 indexes the new Node's SQLite flags are rebuilt BEFORE doctor, under the same node ---"
# Node 26.13 ships SQLite 3.54, whose integrity_check flags FTS5 inverted indexes; doctor then refuses and the box
# rolled back. These cases drive the real script with a stub node whose answer is $STATE/fts_mode, and assert the
# ORDER, the node it ran under, and what a failed or unprovable repair does. The repair itself is run for real
# (below) on synthetic databases.
kb_setup bfta clean
OUTFTA="$(run_atomic "$KH" "$KS" "$KST")"; RCFTA=$?
if [ "$RCFTA" -eq 0 ] && [ "$(grep -c '^node-fts ' "$KST/events")" = "1" ] && grep -q "^node-fts $KS/node root=$KH/.openclaw gateway_loaded=no\$" "$KST/events"; then
  pass "Fts-a1: the repair ran exactly once, under the supervisor's node, on the box's root, with the gateway booted out"
else
  fail "Fts-a1: rc=$RCFTA events: $(grep -E 'node-fts' "$KST/events" | tr '\n' '|'). Output: $OUTFTA"
fi
if [ "$(event_order "$KST" "launchctl bootout" "node-fts")" = "OK" ] && [ "$(event_order "$KST" "npm install" "node-fts")" = "OK" ] \
   && [ "$(event_order "$KST" "node-fts" "openclaw doctor")" = "OK" ] && [ "$(event_order "$KST" "node-fts" "launchctl bootstrap")" = "OK" ]; then
  pass "Fts-a2: ORDER — bootout, install, the FTS5 repair, then doctor, then the gateway start"
else
  fail "Fts-a2: ORDER VIOLATION. Events: $(tr '\n' '|' < "$KST/events")"
fi
if grep -q 'FTS_REPAIR_SUMMARY total=1 clean=1 fixed=0 skipped=0 unchecked=0 fail=0' <<<"$OUTFTA"; then
  pass "Fts-a3: the repair's per-database report and summary are in the job log"
else
  fail "Fts-a3: no summary in the log. Output: $OUTFTA"
fi

kb_setup bftb clean; echo fixed > "$KST/fts_mode"
OUTFTB="$(run_atomic "$KH" "$KS" "$KST")"; RCFTB=$?
if [ "$RCFTB" -eq 0 ] && grep -q 'FIXED /r/agents/main/agent/openclaw-agent.sqlite tables=memory_index_chunks_fts' <<<"$OUTFTB" && [ "$(doctor_calls "$KST")" = "1" ]; then
  pass "Fts-b: a rebuilt index is reported by database and table, and doctor then runs (rc=0)"
else
  fail "Fts-b: rc=$RCFTB. Output: $OUTFTB"
fi

kb_setup bftc clean; echo skipped > "$KST/fts_mode"
OUTFTC="$(run_atomic "$KH" "$KS" "$KST")"; RCFTC=$?
if [ "$RCFTC" -eq 0 ] && grep -q 'SKIPPED .* non-fts-findings=1 .*doctor decides' <<<"$OUTFTC" && [ "$(doctor_calls "$KST")" = "1" ]; then
  pass "Fts-c: a non-FTS finding is left for doctor to decide: not a failure here, doctor still runs (rc=0)"
else
  fail "Fts-c: rc=$RCFTC. Output: $OUTFTC"
fi

fts_refused() {   # <label> <home> <state> <rc> <out> <sha before> <expected text>
  if [ "$4" -eq 78 ] && [ "$(doctor_calls "$3")" = "0" ] && [ "$(cat "$3/version")" = "$OLD_V" ] && [ -f "$3/loaded_ai.openclaw.gateway" ] \
     && [ "$(sha_of "$2/.openclaw/openclaw.json")" = "$6" ] && grep -q "$7" <<<"$5" && ! grep -q 'NOT ROLLING BACK' <<<"$5"; then
    pass "$1"
  else
    fail "$1 -- rc=$4 doctor_calls=$(doctor_calls "$3") version=$(cat "$3/version"). Output: $5"
  fi
}
kb_setup bftd legacy; echo fail > "$KST/fts_mode"; SHAFTD="$(sha_of "$KH/.openclaw/openclaw.json")"
OUTFTD="$(run_atomic "$KH" "$KS" "$KST")"; RCFTD=$?
fts_refused "Fts-d: a repair that leaves integrity_check not ok -> rolled back (rc=78): doctor not run, binary $OLD_V, legacy config byte-identical, gateway loaded" "$KH" "$KST" "$RCFTD" "$OUTFTD" "$SHAFTD" 'integrity_check not ok after rebuild'
kb_setup bfte clean; echo nosummary > "$KST/fts_mode"; SHAFTE="$(sha_of "$KH/.openclaw/openclaw.json")"
OUTFTE="$(run_atomic "$KH" "$KS" "$KST")"; RCFTE=$?
fts_refused "Fts-e: a repair that printed no summary (rc 0, empty output) is never a pass -> rolled back (rc=78), doctor not run" "$KH" "$KST" "$RCFTE" "$OUTFTE" "$SHAFTE" 'FTS5 repair FAILED'
kb_setup bftf clean; echo hang > "$KST/fts_mode"; SHAFTF="$(sha_of "$KH/.openclaw/openclaw.json")"
OUTFTF="$(T_FTS_TIMEOUT=2 run_atomic "$KH" "$KS" "$KST")"; RCFTF=$?
fts_refused "Fts-f: a repair that hits its bound (2s) is UNDETERMINED, never clean -> killed, rolled back (rc=78), doctor not run" "$KH" "$KST" "$RCFTF" "$OUTFTF" "$SHAFTF" 'UNDETERMINED, never reported clean'

# g. MUTATION: with the repair call removed the SAME failing box upgrades, so Fts-d is caused by the step
python3 - "$ATOMIC" "$MUT_DIR/oc-atomic-upgrade.nofts.sh" <<'PY'
import sys
s = open(sys.argv[1], encoding="utf-8").read()
m = s.replace("  _repair_fts5 || return 1\n", "", 1)
if m == s:
    sys.exit(1)
open(sys.argv[2], "w", encoding="utf-8").write(m)
PY
kb_setup bftg clean; echo fail > "$KST/fts_mode"
OUTFTG="$(run_atomic "$KH" "$KS" "$KST" "$MUT_DIR/oc-atomic-upgrade.nofts.sh")"; RCFTG=$?
if ! cmp -s "$ATOMIC" "$MUT_DIR/oc-atomic-upgrade.nofts.sh" && [ "$RCFTG" -eq 0 ] && ! grep -q '^node-fts ' "$KST/events"; then
  pass "Fts-g: MUTATION PROOF — with the repair step removed the node is never asked and the same box upgrades, so Fts-a..f measure the step"
else
  fail "Fts-g: rc=$RCFTG. Output: $OUTFTG"
fi

# ─────────────────────────────────────────────────────────────────────────────
# The repair ITSELF, run for real: the script text between its markers is handed to this machine's own node,
# exactly as the script hands it (node -e "$JS" <root>), against synthetic databases. A node without
# node:sqlite, or whose SQLite does not flag a tampered FTS5 index (before 3.44), cannot show the defect: those
# cases are SKIPPED, loudly, never counted as passes.
FTS_JS="$SANDBOX/fts-repair.js"
sed -n "/^IFS= read -r -d '' JS_FTS_REPAIR <<'JS_FTS5'\$/,/^JS_FTS5\$/p" "$ATOMIC" | sed '1d;$d' > "$FTS_JS"
fts_mk() {   # <db path> <tamper|clean|both|contentless|garbage>
  mkdir -p "$(dirname "$1")"
  node -e "
const {DatabaseSync} = require('node:sqlite');
const [p, mode] = [process.argv[1], process.argv[2]];
const c = new DatabaseSync(p, {defensive: false});
if (mode === 'contentless') {
  c.exec(\"create virtual table cl_fts using fts5(body, content='')\");
  for (let i = 1; i < 120; i++) c.prepare('insert into cl_fts(rowid, body) values (?, ?)').run(i, 'alpha beta ' + i);
  c.exec('update cl_fts_data set block = zeroblob(length(block)) where id > 10');
} else {
  for (const t of ['docs_fts', 'other_fts']) {
    c.exec('create virtual table ' + t + ' using fts5(body)');
    for (let i = 1; i < 120; i++) c.prepare('insert into ' + t + '(rowid, body) values (?, ?)').run(i, 'alpha beta ' + i + ' gamma ' + (i * 7));
  }
  if (mode === 'tamper' || mode === 'both') c.exec(\"update docs_fts_content set c0 = 'totally different words' where id = 5\");
  if (mode === 'both') { c.exec('create table notes (a integer check (a > 0))'); c.exec('pragma ignore_check_constraints = on'); c.exec('insert into notes values (-1)'); }
}
c.close();
" "$1" "$2" >/dev/null 2>&1
}
fts_run() { node -e "$(cat "$FTS_JS")" "$1" 2>&1; }
fts_tree_sums() { ( cd "$1" && find . -type f | sort | while read -r f; do printf '%s %s\n' "$f" "$(sha_of "$f")"; done ); }

# node prints normalised paths (TMPDIR ends in a slash, so $SANDBOX has a "//"): compare against the same spelling
FTSR="$(printf '%s' "$SANDBOX/ftsreal" | sed 's|//*|/|g')"; mkdir -p "$FTSR"
fts_mk "$FTSR/probe/agents/p/agent/openclaw-agent.sqlite" tamper
FTS_CAN="$(node -e "const {DatabaseSync}=require('node:sqlite');console.log(new DatabaseSync(process.argv[1]).prepare('PRAGMA integrity_check').all().map(r=>Object.values(r)[0]).join('|'))" "$FTSR/probe/agents/p/agent/openclaw-agent.sqlite" 2>/dev/null)"
if ! grep -q 'malformed inverted index for FTS5 table' <<<"$FTS_CAN"; then
  echo "  SKIP: Fts-real-*: this node ($(node -v 2>/dev/null || echo none)) cannot build or flag a tampered FTS5 index (integrity_check said: '${FTS_CAN:0:80}') - the real-database cases did NOT run"
else
  # r1. only the flagged index is rebuilt, from its own content; a clean database is not rewritten
  R1="$FTSR/r1"; FA="$R1/agents/a/agent/openclaw-agent.sqlite"; FB="$R1/agents/b/agent/openclaw-agent.sqlite"
  fts_mk "$FA" tamper; fts_mk "$FB" clean
  BEF="$(fts_tree_sums "$R1")"; SUMB="$(sha_of "$FB")"
  OUTR1="$(fts_run "$R1")"; RCR1=$?
  if [ "$RCR1" -eq 0 ] && grep -qx "FIXED $FA tables=docs_fts" <<<"$OUTR1" && grep -qx "CLEAN $FB" <<<"$OUTR1" \
     && grep -qx 'FTS_REPAIR_SUMMARY total=2 clean=1 fixed=1 skipped=0 unchecked=0 fail=0' <<<"$OUTR1" && grep -q 'FTS_REPAIR_RUNTIME node=v[0-9.]* sqlite=3\.' <<<"$OUTR1"; then
    pass "Fts-real-1: only the flagged table (docs_fts, not other_fts) was rebuilt; the clean database was reported clean (real node $(node -v), SQLite $(sed -n 's/.*sqlite=//p' <<<"$OUTR1" | head -1))"
  else
    fail "Fts-real-1: rc=$RCR1. Output: $OUTR1"
  fi
  CHK="$(node -e "
const {DatabaseSync} = require('node:sqlite'); const d = new DatabaseSync(process.argv[1]);
const n = (s) => d.prepare(s).all().map((r) => Object.values(r)[0]).join(',');
console.log([n('select count(*) from docs_fts'), n(\"select body from docs_fts where rowid = 5\"),
             n(\"select rowid from docs_fts where docs_fts match 'totally'\"), n(\"select count(*) from docs_fts where docs_fts match 'alpha' and rowid = 5\")].join('|'));
" "$FA")"
  if [ "$CHK" = "119|totally different words|5|0" ] && [ "$(sha_of "$FB")" = "$SUMB" ]; then
    pass "Fts-real-2: the stored rows are unchanged (119, row 5's content kept) and the index was rebuilt from them (it finds 'totally', no longer 'alpha' in row 5); the clean database's bytes are untouched"
  else
    fail "Fts-real-2: after-state '$CHK'"
  fi
  AFT="$(fts_tree_sums "$R1")"
  if [ "$(cut -d' ' -f1 <<<"$BEF" | tr '\n' ' ')" = "$(cut -d' ' -f1 <<<"$AFT" | tr '\n' ' ')" ]; then
    pass "Fts-real-3: no file was created, copied or deleted anywhere under the root (same file list before and after)"
  else
    fail "Fts-real-3: file list changed. before: $BEF after: $AFT"
  fi
  OUTR1B="$(fts_run "$R1")"
  if grep -qx 'FTS_REPAIR_SUMMARY total=2 clean=2 fixed=0 skipped=0 unchecked=0 fail=0' <<<"$OUTR1B"; then
    pass "Fts-real-4: re-running on the repaired root finds both databases clean (the rebuild is durable)"
  else
    fail "Fts-real-4: second run: $OUTR1B"
  fi

  # r2. ANY non-FTS finding leaves the database byte-for-byte alone; an unreadable file is UNCHECKED, never clean
  R2="$FTSR/r2"; FM="$R2/agents/m/agent/openclaw-agent.sqlite"; FS="$R2/state/openclaw.sqlite"; FJ="$R2/agents/j/agent/openclaw-agent.sqlite"
  fts_mk "$FM" both; fts_mk "$FS" clean
  node -e "const {DatabaseSync}=require('node:sqlite');const c=new DatabaseSync(process.argv[1],{defensive:false});c.exec('create table notes (a integer check (a > 0))');c.exec('pragma ignore_check_constraints = on');c.exec('insert into notes values (-1)');c.close()" "$FS" >/dev/null 2>&1
  mkdir -p "$(dirname "$FJ")"; i=0; : > "$FJ"; while [ "$i" -lt 40 ]; do printf 'this is not a database ' >> "$FJ"; i=$((i+1)); done
  BEF2="$(fts_tree_sums "$R2")"
  OUTR2="$(fts_run "$R2")"; RCR2=$?
  if [ "$RCR2" -eq 0 ] && grep -qx "SKIPPED $FM non-fts-findings=1 fts-tables=docs_fts (nothing changed, doctor decides)" <<<"$OUTR2" \
     && grep -qx "SKIPPED $FS non-fts-findings=1 fts-tables= (nothing changed, doctor decides)" <<<"$OUTR2" \
     && grep -q "^UNCHECKED $FJ " <<<"$OUTR2" && grep -qx 'FTS_REPAIR_SUMMARY total=3 clean=0 fixed=0 skipped=2 unchecked=1 fail=0' <<<"$OUTR2"; then
    pass "Fts-real-5: an FTS5 finding beside a non-FTS one is NOT rebuilt; a state database with only a non-FTS finding is skipped; a file that is no database is UNCHECKED (rc=0: doctor decides)"
  else
    fail "Fts-real-5: rc=$RCR2. Output: $OUTR2"
  fi
  if [ "$(fts_tree_sums "$R2")" = "$BEF2" ]; then
    pass "Fts-real-6: every byte of every database is untouched when anything but FTS5 is wrong"
  else
    fail "Fts-real-6: a database changed although the repair was not allowed to touch it"
  fi

  # r3. a rebuild that cannot be done (contentless table: nothing to rebuild from) fails the step and changes nothing
  R3="$FTSR/r3"; FC="$R3/agents/c/agent/openclaw-agent.sqlite"
  fts_mk "$FC" contentless
  BEF3="$(fts_tree_sums "$R3")"
  OUTR3="$(fts_run "$R3")"; RCR3=$?
  if [ "$RCR3" -eq 1 ] && grep -q "^FAIL $FC rebuild error: " <<<"$OUTR3" && grep -qx 'FTS_REPAIR_SUMMARY total=1 clean=0 fixed=0 skipped=0 unchecked=0 fail=1' <<<"$OUTR3" \
     && [ "$(fts_tree_sums "$R3")" = "$BEF3" ]; then
    pass "Fts-real-7: a rebuild that cannot be done exits 1 with the table named, rolls back, and leaves the database as it was"
  else
    fail "Fts-real-7: rc=$RCR3. Output: $OUTR3"
  fi
fi

# the repair's source never copies or deletes a database: the only write it can make is the FTS5 'rebuild' command
if [ -s "$FTS_JS" ] && ! grep -Eq 'copyFile|unlinkSync|rmSync|renameSync|writeFileSync|VACUUM|DROP |DELETE FROM' "$FTS_JS" \
   && [ "$(grep -c "VALUES(.*rebuild" "$FTS_JS")" = "1" ]; then
  pass "Fts-src: the repair's source has no copy, delete, rename, file write, VACUUM, DROP or DELETE; 'rebuild' is its only write"
else
  fail "Fts-src: the repair's source carries a forbidden write (or could not be extracted: $(wc -c < "$FTS_JS") bytes)"
fi

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi
echo "PASS: the atomic upgrade procedure enforces, and rolls back, at runtime"
exit 0

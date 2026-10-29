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
cleanup() {
  local _p
  for _p in $(cat "$SANDBOX"/state*/spawned.pids 2>/dev/null); do kill "$_p" 2>/dev/null; done
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
#   (unset) ok | fail | fail_holder (a stale CLI grabs the state DB, then doctor fails) | hang |
#   audit (refuses like the real audit-logs step until the raw checkpoint rows are gone) | audit_always |
#   models (rewrites agents.defaults.model) | touch (changes only an unrelated key)
if [ "\${1:-}" = "doctor" ]; then
  {
    echo "args=\$*"
    if [ -f "\$STATE/loaded_ai.openclaw.gateway" ]; then echo "gateway_loaded=yes"; else echo "gateway_loaded=no"; fi
    echo "version=\$V"
    read -r -t 2 _x; echo "stdin_rc=\$?"
  } >> "\$STATE/doctor_ctx"
  DB="\$HOME/.openclaw/state/openclaw.sqlite"
  MODE="\$(cat "\$STATE/doctor_mode" 2>/dev/null)"
  case "\$MODE" in
    fail) echo "doctor: agent database migration failed" >&2; exit 1 ;;
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
  esac
  echo "doctor: ok"; exit 0
fi
# CAN014: the NEW build rejects skills.workshop.autonomous.mode "propose" (2026.10.5).
# config validate --json is its verdict: rc 1 + {"valid":false,"issues":[...]}.
if [ "\${1:-}" = "config" ] && [ "\${2:-}" = "validate" ]; then
  if [ -f "\$STATE/validate_fail" ] || { [ "\$V" = "$NEW_V" ] && grep -Eq '"mode": *"(propose|bogus)"' "\$HOME/.openclaw/openclaw.json" 2>/dev/null; }; then
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
  if [ -n "\$PFX" ]; then
    mkdir -p "\$PFX/lib/node_modules/openclaw"
    printf '{"name":"openclaw","version":"%s"}\n' "\$VER" > "\$PFX/lib/node_modules/openclaw/package.json"
    [ -f "\$STATE/split" ] || printf '%s' "\$VER" > "\$STATE/version"
  elif [ -n "\$VER" ]; then
    printf '%s' "\$VER" > "\$STATE/version"
  fi
  echo "npm-install-witness \$*" >> "\$STATE/npm_installs"
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
  # node: the supervisor plist names a bare `node`; the resolver finds this one.
  printf '#!/bin/bash\nexit 0\n' > "$dir/node"
  # ps: the live gateway's command line is the plist's launch path (or $STATE/ps_args); its age is
  # $STATE/ps_etime (default 00:00 = just started, i.e. after every fixture file was written).
  # A spawned state-database holder has its own answers: $state/ps_<pid>.args and ps_<pid>.etime.
  cat > "$dir/ps" <<EOF
#!/bin/bash
P=""; prev=""
for a in "\$@"; do [ "\$prev" = "-p" ] && P="\$a"; prev="\$a"; done
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
[ -f "\$STATE/lsof_holders" ] || exit 1
rc=1
while read -r p; do
  if [ -n "\$p" ] && kill -0 "\$p" 2>/dev/null; then echo "\$p"; rc=0; fi
done < "\$STATE/lsof_holders"
exit \$rc
EOF
  chmod +x "$dir/openclaw" "$dir/npm" "$dir/launchctl" "$dir/docker" "$dir/hostname" "$dir/curl" "$dir/node" "$dir/ps" "$dir/lsof"
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
echo "--- (7) ROLLBACK: the gateway CRASH-LOOPS after a completed migration ---"
# The hardest case: binary changed AND config migrated, then the gateway fails
# to stay up. Both must be undone. A changing pid across the stability window is
# the crash-loop signature (exit 78 + KeepAlive respawn every ~11s).
H7="$(make_box b7 legacy)"; S7="$SANDBOX/stubs7"; ST7="$SANDBOX/state7"
make_stubs "$S7" "$ST7" versioned
CFG7="$H7/.openclaw/openclaw.json"; SHA7_BEFORE="$(sha_of "$CFG7")"
touch "$ST7/pid_flip"
OUT7="$(run_atomic "$H7" "$S7" "$ST7")"; RC7=$?

[ "$RC7" -eq 78 ] && pass "7a: a crash-looping gateway was DETECTED and the upgrade rolled back (rc=78)" \
                  || fail "7a: expected rc=78 on a crash-loop, got $RC7. Output: $OUT7"
SHAPE7="$(cfg_shape "$CFG7")"
if [ "$(sha_of "$CFG7")" = "$SHA7_BEFORE" ]; then
  pass "7b: ROLLBACK — the MIGRATED config was reverted byte-for-byte ($SHAPE7)"
else
  fail "7b: ROLLBACK FAILED — the config was left as $SHAPE7 after a failed start"
fi
if [ "$(cat "$ST7/version" 2>/dev/null)" = "$OLD_V" ]; then
  pass "7c: ROLLBACK — the ORIGINAL binary $OLD_V was reinstalled"
else
  fail "7c: ROLLBACK FAILED — the box is left on $(cat "$ST7/version" 2>/dev/null)"
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
  if [ "$RC13C" -eq 78 ] && ! grep -q 'ATOMIC UPGRADE COMPLETE' <<<"$OUT13C" && [ "$(sha_of "$CFG13C")" = "$SHA13C" ] \
     && [ "$(cat "$ST13C/version")" = "$OLD_V" ] && [ -f "$ST13C/loaded_ai.openclaw.gateway" ]; then
    pass "13c($kind): config the new build rejects -> rolled back (rc=78), config + binary restored, gateway up, no success banner"
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

# 17d. a mixed set: only the stale bare CLI dies. The gateway service, a node service, the OpenClaw
# app, a CLI that started during this run and an unrelated program all survive. Doctor needs exclusive
# access, so it is NOT run and the upgrade rolls back instead of fighting over the database.
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
SURV=""; for p in "$P_GW" "$P_NODE" "$P_APP" "$P_FRESH" "$P_OTHER"; do alive "$p" || SURV="$SURV $p(DEAD)"; done
if ! alive "$P_STALE" && [ -z "$SURV" ]; then
  pass "17d: ONLY the stale bare CLI was killed; the gateway service, node service, OpenClaw app, a CLI started during this run and an unrelated program all survived"
else
  fail "17d: stale alive=$(alive "$P_STALE" && echo yes || echo no); protected killed:$SURV"
fi
if [ "$RC17M" -eq 78 ] && [ "$(doctor_calls "$ST17M")" = "0" ] && [ "$(cat "$ST17M/version")" = "$OLD_V" ] && [ -f "$ST17M/loaded_ai.openclaw.gateway" ]; then
  pass "17e: holders that may not be stopped -> doctor NOT run, rolled back (rc=78), binary $OLD_V, gateway loaded"
else
  fail "17e: rc=$RC17M doctor_calls=$(doctor_calls "$ST17M") version=$(cat "$ST17M/version"). Output: $OUT17M"
fi
if grep -q "pid $P_GW is not a bare openclaw CLI" <<<"$OUT17M" && grep -q "pid $P_NODE is not a bare openclaw CLI" <<<"$OUT17M" \
   && grep -q "pid $P_APP is not a bare openclaw CLI" <<<"$OUT17M" && grep -q "pid $P_FRESH (openclaw status) started during this run" <<<"$OUT17M"; then
  pass "17f: each survivor was logged with the reason it was left alone"
else
  fail "17f: missing 'left alone' reasons. Output: $OUT17M"
fi
for p in "$P_GW" "$P_NODE" "$P_APP" "$P_FRESH" "$P_OTHER"; do kill "$p" 2>/dev/null; done

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
CFG18F="$H18F/.openclaw/openclaw.json"; SHA18F="$(sha_of "$CFG18F")"
OUT18F="$(run_atomic "$H18F" "$S18F" "$ST18F")"; RC18F=$?
if [ "$RC18F" -eq 78 ] && grep -q 'changed the model/provider selection' <<<"$OUT18F" && [ "$(sha_of "$CFG18F")" = "$SHA18F" ] \
   && [ "$(cat "$ST18F/version")" = "$OLD_V" ] && ! grep -q 'doctor-changed' "$CFG18F"; then
  pass "18l: doctor changed agents.defaults.model -> rolled back (rc=78), config restored byte-identical, binary $OLD_V"
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
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi
echo "PASS: the atomic upgrade procedure enforces, and rolls back, at runtime"
exit 0

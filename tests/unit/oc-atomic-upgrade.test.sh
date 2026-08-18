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

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/oc-atomic-test.XXXXXX")"
cleanup() { rm -rf "$SANDBOX"; }
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
    echo '{"properties":{"agents":{"additionalProperties":false,"properties":{"defaults":{},"entries":{}}}}}'
  else
    echo '{"properties":{"agents":{"additionalProperties":false,"properties":{"defaults":{},"list":{}}}}}'
  fi
  exit 0
fi
exit 0
EOF

  cat > "$dir/npm" <<EOF
#!/bin/bash
STATE="$state"
echo "npm \$*" >> "\$STATE/events"
if [ "\${1:-}" = "view" ]; then cat "\$STATE/latest"; exit 0; fi
if [ "\${1:-}" = "install" ]; then
  for a in "\$@"; do
    case "\$a" in
      openclaw@*) printf '%s' "\${a#openclaw@}" > "\$STATE/version" ;;
    esac
  done
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
case "\${1:-}" in
  print)
    _assert_domain "\${2:-}"
    LBL="\$(basename "\${2:-}")"
    [ -f "\$STATE/loaded_\$LBL" ] || exit 1
    P="\$(cat "\$STATE/pid" 2>/dev/null)"
    if [ -f "\$STATE/pid_flip" ]; then P=\$((P+1)); printf '%s' "\$P" > "\$STATE/pid"; fi
    echo "	pid = \$P"
    exit 0
    ;;
  bootout)
    _assert_domain "\${2:-}"
    LBL="\$(basename "\${2:-}")"
    if [ -f "\$STATE/bootout_noop" ]; then exit 0; fi
    rm -f "\$STATE/loaded_\$LBL"
    exit 0
    ;;
  bootstrap)
    _assert_domain "\${2:-}"
    LBL="\$(basename "\${3:-}" .plist)"
    if [ -f "\$STATE/bootstrap_fail" ]; then exit 1; fi
    touch "\$STATE/loaded_\$LBL"
    exit 0
    ;;
esac
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
  chmod +x "$dir/openclaw" "$dir/npm" "$dir/launchctl" "$dir/docker" "$dir/hostname"
}

# make_box <name> <config-kind> -> echoes the box HOME
make_box() {
  local home="$SANDBOX/$1"
  mkdir -p "$home/.openclaw/scripts" "$home/Library/LaunchAgents"
  write_config "$home/.openclaw/openclaw.json" "$2"
  echo "<plist/>" > "$home/Library/LaunchAgents/ai.openclaw.gateway.plist"
  echo "$home"
}

# run_atomic <home> <stubs> <state> [script-override] -- returns the script's rc
run_atomic() {
  local home="$1" stubs="$2" state="$3" script="${4:-$ATOMIC}"
  touch "$state/loaded_ai.openclaw.gateway"     # the gateway starts out running
  HOME="$home" PATH="$stubs:/usr/bin:/bin:/usr/sbin:/sbin" \
    OC_ATOMIC_QUIESCE_PROOF_SECONDS=1 OC_ATOMIC_STABILITY_SECONDS=1 \
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
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi
echo "PASS: the atomic upgrade procedure enforces, and rolls back, at runtime"
exit 0

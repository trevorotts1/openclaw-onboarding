#!/usr/bin/env bash
# tests/unit/legacy-agents-list-gate.test.sh
#
# CI guard for the LEGACY `agents.list` PRE-UPGRADE GATE.
#
# THE FAULT BEING GUARDED. The 2026.7.2-beta line rejects the legacy
# `agents.list` key outright ("agents: Unrecognized key: \"list\""). The gateway
# exits 78 (EX_CONFIG) ~0.4s after start, launchd's KeepAlive +
# ThrottleInterval=10 respawns it every ~11s (701 boots in 10 days on the box
# this was measured on), and the crash-loop breaker then latches channel
# auto-start OFF -- the box goes COMPLETELY DARK and queued deliveries are lost.
# The key is HARMLESS on the older line, so the only place to catch it is BEFORE
# a version change.
#
# ⛔ WHAT THIS TEST REFUSES TO BE. A previous unit test in this repo asserted
# that a safety cap was *defined* and passed happily while runtime enforcement
# was dead. Asserting "the function exists" or "the string appears in the file"
# proves nothing. EVERY case below RUNS the real shipped code and asserts on its
# OBSERVED BEHAVIOUR -- the exit code it returns, and whether the upgrade
# command actually executed. Case (7) is a MUTATION PROOF: it breaks the
# detector on purpose and requires this very test to stop passing. If the
# mutation case ever goes green, this test has stopped measuring anything.
#
# ⛔ EVERY BLOCK HAS A MATCHING CONTROL. A gate that blocks everything is
# indistinguishable from a gate that blocks correctly. Case (6a) proves a CLEAN
# box DOES upgrade through the very same harness that case (6b) proves a LEGACY
# box does not. Without that pair, "npm never ran" would be evidence of a broken
# test, not a working gate.
#
# Assertion groups:
#   (1) STANDALONE GATE, CLEAN        scripts/qc-assert-legacy-agents-list.sh -> 0
#   (2) STANDALONE GATE, LEGACY       -> 1, and the output names the key
#   (3) STANDALONE GATE, ABSENT/BAD   -> 3 (UNDETERMINED), never 0
#   (4) REAL REPO DATA                the gate runs against this repo's own
#                                     checked-in configs/fixtures, not only
#                                     against fixtures this test authored
#   (5) update-skills.sh agents_list_gate(), extracted and executed:
#                                     clean -> 0, legacy+no-CLI -> 3,
#                                     legacy+successful-migration -> 0,
#                                     legacy+lying-migration -> 3 AND rolled back,
#                                     migration that MOVES THE WORKSPACE -> 3
#                                     AND rolled back
#   (6) THE WEEKLY CRON, END TO END   the generated ~/.openclaw/skills/
#                                     .openclaw-self-update script:
#                                     (a) CLEAN  -> `npm update -g openclaw` RUNS
#                                     (b) LEGACY -> it DOES NOT RUN, exit 78
#                                     (c) LEGACY + working doctor -> it RUNS
#   (7) MUTATION PROOF                detection neutered -> the legacy config is
#                                     no longer blocked. Proves (2)/(6b) are
#                                     caused by the detector, not by luck.
#
# Every case is hermetic: a throwaway $HOME under a temp dir, stub `npm` /
# `openclaw` / `hostname` on PATH. No live gateway, no network, no real box, and
# nothing outside the sandbox is read or written.
#
# Run: bash tests/unit/legacy-agents-list-gate.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more checks failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$REPO_ROOT/scripts/qc-assert-legacy-agents-list.sh"
UPDATER="$REPO_ROOT/update-skills.sh"
WEEKLY="$REPO_ROOT/scripts/setup-weekly-update.sh"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== legacy-agents-list-gate.test.sh ==="
# Report the interpreter ACTUALLY RUNNING THIS FILE ($BASH_VERSION), not
# `bash --version`, which resolves through PATH. On a dev Mac that is Homebrew
# bash 5.x while the fleet's Macs run stock /bin/bash 3.2.57 -- and a prior
# change in this repo shipped a gate that parsed fine under 5.x and aborted at
# PARSE time under 3.2 on every client box. A test that misreports its own
# interpreter cannot catch that.
echo "    interpreter: bash ${BASH_VERSION:-unknown}  (\$0 was run by: ${BASH:-unknown})"
echo ""

for f in "$GATE" "$UPDATER" "$WEEKLY"; do
  if [ ! -f "$f" ]; then
    echo "FATAL: required file not found: $f" >&2
    exit 1
  fi
done

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/legacy-agents-list-test.XXXXXX")"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# ── fixture builders ─────────────────────────────────────────────────────────
# write_config <path> <clean|legacy|badjson|agents-not-object|legacy-with-ws>
write_config() {
  local path="$1" kind="$2"
  mkdir -p "$(dirname "$path")"
  case "$kind" in
    clean)
      printf '%s\n' '{"agents":{"defaults":{"workspace":"~/.openclaw/workspace"}},"models":{}}' > "$path" ;;
    legacy)
      printf '%s\n' '{"agents":{"list":[{"id":"main"}],"defaults":{"workspace":"~/.openclaw/workspace"}},"models":{}}' > "$path" ;;
    legacy-with-ws)
      # The dangerous shape: the workspace is declared ONLY inside the legacy
      # array, so a migration that drops the array MOVES the resolved workspace.
      printf '%s\n' '{"agents":{"list":[{"id":"main","workspace":"~/.openclaw/workspace"}]},"models":{}}' > "$path" ;;
    badjson)
      printf '%s\n' '{"agents": {"list": [' > "$path" ;;
    agents-not-object)
      printf '%s\n' '{"agents":["main"],"models":{}}' > "$path" ;;
  esac
}

# ---------------------------------------------------------------------------
# (1) STANDALONE GATE, CLEAN -> exit 0
# ---------------------------------------------------------------------------
echo "--- (1) standalone gate, CLEAN config -> exit 0 ---"
CLEAN_CFG="$SANDBOX/clean/openclaw.json"
write_config "$CLEAN_CFG" clean
out1="$(bash "$GATE" "$CLEAN_CFG" 2>&1)"; rc1=$?
if [ "$rc1" -eq 0 ]; then
  pass "1a: a clean config exits 0"
else
  fail "1a: clean config exited $rc1 (expected 0). Output: $out1"
fi

# ---------------------------------------------------------------------------
# (2) STANDALONE GATE, LEGACY -> exit 1 and names the key
# ---------------------------------------------------------------------------
echo "--- (2) standalone gate, LEGACY config -> exit 1 ---"
LEGACY_CFG="$SANDBOX/legacy/openclaw.json"
write_config "$LEGACY_CFG" legacy
out2="$(bash "$GATE" "$LEGACY_CFG" 2>&1)"; rc2=$?
if [ "$rc2" -eq 1 ]; then
  pass "2a: a legacy config exits 1 (THE GATE FIRES)"
else
  fail "2a: legacy config exited $rc2 (expected 1). Output: $out2"
fi
if printf '%s' "$out2" | grep -q 'agents.list'; then
  pass "2b: the failure names the offending key (agents.list)"
else
  fail "2b: the failure did not name agents.list. Output: $out2"
fi
if printf '%s' "$out2" | grep -q 'doctor --fix'; then
  pass "2c: the failure states the remedy (openclaw doctor --fix)"
else
  fail "2c: the failure did not state the remedy. Output: $out2"
fi

# ---------------------------------------------------------------------------
# (3) UNDETERMINED cases -> exit 3, NEVER 0
# ---------------------------------------------------------------------------
echo "--- (3) unreadable / unparseable -> exit 3 (never a silent pass) ---"
out3a="$(bash "$GATE" "$SANDBOX/nope/does-not-exist.json" 2>&1)"; rc3a=$?
if [ "$rc3a" -eq 3 ]; then
  pass "3a: an ABSENT config exits 3 (UNDETERMINED), not 0"
else
  fail "3a: absent config exited $rc3a (expected 3). Output: $out3a"
fi

BAD_CFG="$SANDBOX/bad/openclaw.json"
write_config "$BAD_CFG" badjson
out3b="$(bash "$GATE" "$BAD_CFG" 2>&1)"; rc3b=$?
if [ "$rc3b" -eq 3 ]; then
  pass "3b: an UNPARSEABLE config exits 3, not 0 — an unreadable config is not a clean one"
else
  fail "3b: unparseable config exited $rc3b (expected 3). Output: $out3b"
fi

NOTOBJ_CFG="$SANDBOX/notobj/openclaw.json"
write_config "$NOTOBJ_CFG" agents-not-object
out3c="$(bash "$GATE" "$NOTOBJ_CFG" 2>&1)"; rc3c=$?
if [ "$rc3c" -eq 3 ]; then
  pass "3c: a non-object \`agents\` exits 3 — the invariant could not be measured"
else
  fail "3c: non-object agents exited $rc3c (expected 3). Output: $out3c"
fi

# ---------------------------------------------------------------------------
# (4) REAL REPO DATA — not only fixtures this test wrote.
# Both prior gate defects in this repo were invisible to their own fixtures, so
# run the shipped gate over every openclaw.json-shaped file the REPO actually
# carries and require a defined verdict (0/1/3) with no crash (2, or anything
# else) from any of them.
# ---------------------------------------------------------------------------
echo "--- (4) the shipped gate against this repo's own real config files ---"
# Enumerate REAL repo data: every JSON file the repo actually carries that has a
# top-level `agents` key, i.e. every genuine openclaw-config-shaped file here.
REAL_LIST="$SANDBOX/real-configs.txt"
REAL_INJECTABLE="$SANDBOX/real-injectable.txt"
REPO_ROOT="$REPO_ROOT" REAL_LIST="$REAL_LIST" REAL_INJECTABLE="$REAL_INJECTABLE" python3 - <<'PY'
import json, os
root = os.environ["REPO_ROOT"]
found, injectable = [], []
for dp, dn, fn in os.walk(root):
    dn[:] = [d for d in dn if d not in ('.git', 'node_modules', '__pycache__')]
    for f in fn:
        if not f.endswith('.json'):
            continue
        p = os.path.join(dp, f)
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        if isinstance(d, dict) and 'agents' in d:
            found.append(p)
            # Only a file whose `agents` is an OBJECT is a genuine
            # openclaw-config shape and can meaningfully carry `agents.list`.
            # This repo really does contain a file whose `agents` is a LIST
            # (a role-roster template) -- the gate correctly reports
            # UNDETERMINED on it, and it must not be used for the injection
            # control. Real repo data has shapes hand-written fixtures do not.
            if isinstance(d.get('agents'), dict):
                injectable.append(p)
open(os.environ["REAL_LIST"], "w").write("\n".join(sorted(found)) + ("\n" if found else ""))
open(os.environ["REAL_INJECTABLE"], "w").write("\n".join(sorted(injectable)) + ("\n" if injectable else ""))
PY

REAL_COUNT=0
REAL_BAD=0
REAL_LEGACY=0
REAL_CLEAN=0
FIRST_REAL=""
[ -s "$REAL_INJECTABLE" ] && FIRST_REAL="$(head -1 "$REAL_INJECTABLE")"
while IFS= read -r real_cfg; do
  [ -n "$real_cfg" ] || continue
  REAL_COUNT=$((REAL_COUNT+1))
  bash "$GATE" "$real_cfg" >/dev/null 2>&1
  rrc=$?
  case "$rrc" in
    0) REAL_CLEAN=$((REAL_CLEAN+1)) ;;
    1) REAL_LEGACY=$((REAL_LEGACY+1)); echo "      LEGACY agents.list found in real repo file: $real_cfg" ;;
    3) : ;;
    *) REAL_BAD=$((REAL_BAD+1)); echo "      unexpected rc=$rrc from $real_cfg" ;;
  esac
done < "$REAL_LIST"

if [ "$REAL_COUNT" -eq 0 ]; then
  # Measuring nothing is NOT a pass. Say so out loud and fail: this case exists
  # precisely because both prior gate defects in this repo were invisible to
  # their own hand-written fixtures.
  fail "4a: found ZERO real openclaw-config-shaped files in the repo — case (4) measured nothing, so it proves nothing"
elif [ "$REAL_BAD" -eq 0 ]; then
  pass "4a: $REAL_COUNT REAL repo config(s) each produced a defined verdict ($REAL_CLEAN clean, $REAL_LEGACY legacy), no crashes"
else
  fail "4a: $REAL_BAD of $REAL_COUNT real repo config(s) produced an undefined exit code"
fi

# 4b — DISCRIMINATION ON REAL DATA. A gate that says CLEAN about everything
# would sail through 4a. Take a REAL repo config, inject the legacy key into a
# copy of it, and require the verdict to flip. This is the control that proves
# 4a's "all clean" is a measurement and not a default.
if [ -n "$FIRST_REAL" ]; then
  INJECTED="$SANDBOX/real-injected.json"
  SRC_REAL="$FIRST_REAL" DST_INJ="$INJECTED" python3 - <<'PY'
import json, os
d = json.load(open(os.environ["SRC_REAL"], encoding='utf-8'))
d.setdefault('agents', {})['list'] = [{"id": "main"}]
json.dump(d, open(os.environ["DST_INJ"], "w"))
PY
  bash "$GATE" "$FIRST_REAL" >/dev/null 2>&1; rc_real_clean=$?
  bash "$GATE" "$INJECTED"   >/dev/null 2>&1; rc_real_inj=$?
  if [ "$rc_real_clean" -eq 0 ] && [ "$rc_real_inj" -eq 1 ]; then
    pass "4b: the SAME real repo config reads CLEAN (0) and reads LEGACY (1) once the key is injected — the gate discriminates on real data"
  else
    fail "4b: real config gave rc=$rc_real_clean and its legacy-injected copy gave rc=$rc_real_inj (expected 0 then 1) — file: $FIRST_REAL"
  fi
fi

# ---------------------------------------------------------------------------
# (5) update-skills.sh agents_list_gate() — the REAL shipped function, extracted
# and executed. Extraction (rather than a re-implementation) means this breaks
# loudly if the function is renamed or deleted.
# ---------------------------------------------------------------------------
echo "--- (5) update-skills.sh agents_list_gate() executed against fixtures ---"
GATE_LIB="$SANDBOX/agents_list_gate.lib.sh"
UPDATER_PATH="$UPDATER" GATE_LIB_PATH="$GATE_LIB" python3 - <<'PY'
import os, re, sys
src = open(os.environ["UPDATER_PATH"], encoding="utf-8").read().splitlines()
wanted = ["agents_list_gate", "_agents_list_detect", "_agents_list_workspace",
          "_agents_list_restore", "_agents_list_refuse_banner"]
out, found = [], []
for name in wanted:
    start = None
    for i, l in enumerate(src):
        if re.match(r'^%s\(\) \{' % re.escape(name), l):
            start = i
            break
    if start is None:
        continue
    end = None
    for j in range(start + 1, len(src)):
        if src[j] == "}":
            end = j
            break
    if end is None:
        continue
    out.extend(src[start:end + 1])
    out.append("")
    found.append(name)
open(os.environ["GATE_LIB_PATH"], "w").write("\n".join(out) + "\n")
missing = [w for w in wanted if w not in found]
if missing:
    sys.stderr.write("EXTRACT-MISSING:" + ",".join(missing) + "\n")
    sys.exit(1)
PY
extract_rc=$?
if [ "$extract_rc" -eq 0 ]; then
  pass "5a: agents_list_gate() and its 4 helpers were found and extracted from update-skills.sh"
else
  fail "5a: could not extract agents_list_gate() from update-skills.sh (renamed or deleted?)"
fi

# Stub PATH: `hostname` always; `openclaw` behaviour is per-case.
STUBS="$SANDBOX/stubs"
mkdir -p "$STUBS"
cat > "$STUBS/hostname" <<'EOF'
#!/bin/bash
echo "a-box"
EOF
chmod +x "$STUBS/hostname"

# run_gate <case-home> <mode> -- runs the extracted gate with an isolated HOME.
run_gate() {
  local home="$1" mode="${2:-migrate}"
  HOME="$home" PATH="$STUBS:$PATH" bash -c '
    set -uo pipefail
    . "$1"
    agents_list_gate "$2"
  ' _ "$GATE_LIB" "$mode" 2>&1
}

# (5b) clean box -> 0
H_CLEAN="$SANDBOX/h-clean"
write_config "$H_CLEAN/.openclaw/openclaw.json" clean
out5b="$(run_gate "$H_CLEAN")"; rc5b=$?
if [ "$rc5b" -eq 0 ]; then
  pass "5b: a CLEAN box passes the updater gate (exit 0) — the control"
else
  fail "5b: clean box returned $rc5b (expected 0). Output: $out5b"
fi

# (5c) legacy box, `openclaw` NOT on PATH -> REFUSED (3), config untouched
H_NOCLI="$SANDBOX/h-nocli"
write_config "$H_NOCLI/.openclaw/openclaw.json" legacy
BEFORE_NOCLI="$(cat "$H_NOCLI/.openclaw/openclaw.json")"
out5c="$(HOME="$H_NOCLI" PATH="$STUBS:/usr/bin:/bin" bash -c '
  set -uo pipefail
  . "$1"
  agents_list_gate migrate
' _ "$GATE_LIB" 2>&1)"; rc5c=$?
if [ "$rc5c" -eq 3 ]; then
  pass "5c: LEGACY box with no \`openclaw\` CLI is REFUSED (exit 3) — never a silent proceed"
else
  fail "5c: legacy box with no CLI returned $rc5c (expected 3). Output: $out5c"
fi
if [ "$(cat "$H_NOCLI/.openclaw/openclaw.json")" = "$BEFORE_NOCLI" ]; then
  pass "5d: the refused box's config was left byte-identical (nothing was mutated)"
else
  fail "5d: the refused box's config was modified"
fi
if printf '%s' "$out5c" | grep -q 'ROLL REFUSED'; then
  pass "5e: the refusal prints the loud banner naming the box and the fix"
else
  fail "5e: no refusal banner. Output: $out5c"
fi

# (5f) legacy box, doctor GENUINELY fixes it -> 0
H_FIX="$SANDBOX/h-fix"
write_config "$H_FIX/.openclaw/openclaw.json" legacy
STUB_FIX="$SANDBOX/stubs-fix"
mkdir -p "$STUB_FIX"
cp "$STUBS/hostname" "$STUB_FIX/hostname"
cat > "$STUB_FIX/openclaw" <<'EOF'
#!/bin/bash
# stub: a doctor that really performs the migration (drops agents.list,
# preserving agents.defaults.workspace so the resolved workspace is unchanged)
if [ "${1:-}" = "doctor" ]; then
  python3 - "$HOME/.openclaw/openclaw.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d.get('agents', {}).pop('list', None)
json.dump(d, open(p, 'w'))
PY
  echo "doctor: migrated agents.list"
  exit 0
fi
exit 0
EOF
chmod +x "$STUB_FIX/openclaw"
out5f="$(HOME="$H_FIX" PATH="$STUB_FIX:/usr/bin:/bin" bash -c '
  set -uo pipefail
  . "$1"
  agents_list_gate migrate
' _ "$GATE_LIB" 2>&1)"; rc5f=$?
if [ "$rc5f" -eq 0 ]; then
  pass "5f: a LEGACY box whose migration genuinely works is MIGRATED and proceeds (exit 0)"
else
  fail "5f: successful migration returned $rc5f (expected 0). Output: $out5f"
fi
if ! python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if 'list' not in d.get('agents',{}) else 1)" "$H_FIX/.openclaw/openclaw.json"; then
  fail "5g: the migrated config still carries agents.list"
else
  pass "5g: the migrated config no longer carries agents.list (re-read from disk)"
fi

# (5h) legacy box, doctor LIES (exits 0, changes nothing) -> 3 AND rolled back.
# An exit code is a claim, not a result. This is the case that catches a
# migration tool that reports success without doing anything.
H_LIE="$SANDBOX/h-lie"
write_config "$H_LIE/.openclaw/openclaw.json" legacy
BEFORE_LIE="$(cat "$H_LIE/.openclaw/openclaw.json")"
STUB_LIE="$SANDBOX/stubs-lie"
mkdir -p "$STUB_LIE"
cp "$STUBS/hostname" "$STUB_LIE/hostname"
cat > "$STUB_LIE/openclaw" <<'EOF'
#!/bin/bash
# stub: a doctor that claims success and changes nothing
echo "doctor: all good (lying)"
exit 0
EOF
chmod +x "$STUB_LIE/openclaw"
out5h="$(HOME="$H_LIE" PATH="$STUB_LIE:/usr/bin:/bin" bash -c '
  set -uo pipefail
  . "$1"
  agents_list_gate migrate
' _ "$GATE_LIB" 2>&1)"; rc5h=$?
if [ "$rc5h" -eq 3 ]; then
  pass "5h: a migration that exits 0 but changes NOTHING is caught and REFUSED (exit 3)"
else
  fail "5h: lying migration returned $rc5h (expected 3). Output: $out5h"
fi
if [ "$(cat "$H_LIE/.openclaw/openclaw.json")" = "$BEFORE_LIE" ]; then
  pass "5i: the config was ROLLED BACK to its exact original bytes"
else
  fail "5i: the config was not restored after the failed migration"
fi

# (5j) legacy box whose workspace lives ONLY in the legacy array, and a doctor
# that drops the array without preserving it -> the resolved workspace MOVES.
# That silently re-points the box's shared AGENTS.md/TOOLS.md/USER.md, so it
# must be refused and rolled back even though the crash-loop key is gone.
H_WS="$SANDBOX/h-ws"
write_config "$H_WS/.openclaw/openclaw.json" legacy-with-ws
BEFORE_WS="$(cat "$H_WS/.openclaw/openclaw.json")"
STUB_WS="$SANDBOX/stubs-ws"
mkdir -p "$STUB_WS"
cp "$STUBS/hostname" "$STUB_WS/hostname"
cat > "$STUB_WS/openclaw" <<'EOF'
#!/bin/bash
if [ "${1:-}" = "doctor" ]; then
  python3 - "$HOME/.openclaw/openclaw.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d.get('agents', {}).pop('list', None)   # drops the ONLY workspace declaration
json.dump(d, open(p, 'w'))
PY
  echo "doctor: dropped agents.list (and the workspace with it)"
  exit 0
fi
exit 0
EOF
chmod +x "$STUB_WS/openclaw"
out5j="$(HOME="$H_WS" PATH="$STUB_WS:/usr/bin:/bin" bash -c '
  set -uo pipefail
  . "$1"
  agents_list_gate migrate
' _ "$GATE_LIB" 2>&1)"; rc5j=$?
if [ "$rc5j" -eq 3 ]; then
  pass "5j: a migration that MOVES the resolved workspace is refused (exit 3)"
else
  fail "5j: workspace-moving migration returned $rc5j (expected 3). Output: $out5j"
fi
if [ "$(cat "$H_WS/.openclaw/openclaw.json")" = "$BEFORE_WS" ]; then
  pass "5k: the workspace-moving migration was ROLLED BACK"
else
  fail "5k: the workspace-moving migration was not rolled back"
fi

# (5l) 'check' mode never mutates
H_CHECK="$SANDBOX/h-check"
write_config "$H_CHECK/.openclaw/openclaw.json" legacy
BEFORE_CHECK="$(cat "$H_CHECK/.openclaw/openclaw.json")"
out5l="$(HOME="$H_CHECK" PATH="$STUB_FIX:/usr/bin:/bin" bash -c '
  set -uo pipefail
  . "$1"
  agents_list_gate check
' _ "$GATE_LIB" 2>&1)"; rc5l=$?
if [ "$rc5l" -eq 3 ] && [ "$(cat "$H_CHECK/.openclaw/openclaw.json")" = "$BEFORE_CHECK" ]; then
  pass "5l: 'check' mode refuses (exit 3) and mutates nothing, even with a working doctor on PATH"
else
  fail "5l: check mode returned $rc5l or mutated the config. Output: $out5l"
fi

# ---------------------------------------------------------------------------
# (6) THE WEEKLY CRON, END TO END. This is the script that actually performs the
# version change on every box, unattended, every Saturday at 23:59. The
# assertion is not "the gate is present in the file" -- it is "the upgrade
# command DID NOT EXECUTE", observed by a stub npm that records its own
# invocation to a file.
# ---------------------------------------------------------------------------
echo "--- (6) the generated weekly-cron script: does \`npm update\` actually run? ---"
CRON_SCRIPT="$SANDBOX/openclaw-self-update"
WEEKLY_PATH="$WEEKLY" CRON_OUT="$CRON_SCRIPT" python3 - <<'PY'
import os, sys
src = open(os.environ["WEEKLY_PATH"], encoding="utf-8").read().splitlines()
start = end = None
for i, l in enumerate(src):
    if "<< 'OCUPDATE_EOF'" in l:
        start = i + 1
    elif start is not None and l.strip() == "OCUPDATE_EOF":
        end = i
        break
if start is None or end is None:
    sys.stderr.write("could not locate the OCUPDATE_EOF heredoc\n")
    sys.exit(1)
body = "\n".join(src[start:end])
if "npm update -g openclaw" not in body:
    sys.stderr.write("the generated script no longer contains the npm upgrade\n")
    sys.exit(1)
open(os.environ["CRON_OUT"], "w").write(body + "\n")
PY
if [ $? -eq 0 ]; then
  pass "6-pre: the generated self-update script was extracted from setup-weekly-update.sh"
else
  fail "6-pre: could not extract the generated self-update script"
fi
chmod +x "$CRON_SCRIPT"

# Stub npm/openclaw that RECORD whether they were invoked.
make_cron_stubs() {
  local dir="$1" doctor_mode="$2"
  mkdir -p "$dir"
  cat > "$dir/npm" <<EOF
#!/bin/bash
echo "NPM-CALLED \$*" >> "\$NPM_WITNESS"
exit 0
EOF
  chmod +x "$dir/npm"
  cp "$STUBS/hostname" "$dir/hostname"
  if [ "$doctor_mode" = "fix" ]; then
    cp "$STUB_FIX/openclaw" "$dir/openclaw"
  else
    cat > "$dir/openclaw" <<'EOF'
#!/bin/bash
if [ "${1:-}" = "--version" ]; then echo "2026.7.2-beta"; exit 0; fi
echo "doctor: nothing to do (lying)"
exit 0
EOF
    chmod +x "$dir/openclaw"
  fi
}

run_cron() {
  local home="$1" stubs="$2"
  mkdir -p "$home/.openclaw/skills"
  NPM_WITNESS="$home/npm-witness.txt" HOME="$home" PATH="$stubs:/usr/bin:/bin" \
    bash "$CRON_SCRIPT" 2>&1
}

# (6a) CONTROL: a CLEAN box must still upgrade. Without this, "npm never ran"
# below would be evidence of a broken harness, not a working gate.
H_CRON_CLEAN="$SANDBOX/cron-clean"
mkdir -p "$H_CRON_CLEAN/.openclaw/skills"
write_config "$H_CRON_CLEAN/.openclaw/openclaw.json" clean
S_CRON_CLEAN="$SANDBOX/cron-stubs-clean"
make_cron_stubs "$S_CRON_CLEAN" lie
out6a="$(run_cron "$H_CRON_CLEAN" "$S_CRON_CLEAN")"; rc6a=$?
if [ -f "$H_CRON_CLEAN/npm-witness.txt" ]; then
  pass "6a: CONTROL — on a CLEAN box \`npm update -g openclaw\` DID run (the harness works)"
else
  fail "6a: CONTROL FAILED — npm never ran even on a clean box, so case 6b proves nothing. Output: $out6a (rc=$rc6a)"
fi

# (6b) THE ASSERTION THAT MATTERS: a LEGACY box must NOT be upgraded.
H_CRON_LEG="$SANDBOX/cron-legacy"
mkdir -p "$H_CRON_LEG/.openclaw/skills"
write_config "$H_CRON_LEG/.openclaw/openclaw.json" legacy
S_CRON_LEG="$SANDBOX/cron-stubs-legacy"
make_cron_stubs "$S_CRON_LEG" lie
out6b="$(run_cron "$H_CRON_LEG" "$S_CRON_LEG")"; rc6b=$?
if [ ! -f "$H_CRON_LEG/npm-witness.txt" ]; then
  pass "6b: a LEGACY box was NOT upgraded — \`npm update -g openclaw\` never executed"
else
  fail "6b: THE GATE DID NOT FIRE — npm ran on a legacy box: $(cat "$H_CRON_LEG/npm-witness.txt")"
fi
if [ "$rc6b" -eq 78 ]; then
  pass "6c: the blocked upgrade exits 78 (EX_CONFIG) — loud, and distinct from success"
else
  fail "6c: blocked upgrade exited $rc6b (expected 78). Output: $out6b"
fi
if [ -f "$H_CRON_LEG/.openclaw/skills/.openclaw-upgrade-blocked" ]; then
  pass "6d: a block marker was written where a human will find it"
else
  fail "6d: no .openclaw-upgrade-blocked marker was written"
fi

# (6e) a LEGACY box WITH a working doctor migrates and then upgrades.
H_CRON_FIX="$SANDBOX/cron-fix"
mkdir -p "$H_CRON_FIX/.openclaw/skills"
write_config "$H_CRON_FIX/.openclaw/openclaw.json" legacy
S_CRON_FIX="$SANDBOX/cron-stubs-fix"
make_cron_stubs "$S_CRON_FIX" fix
out6e="$(run_cron "$H_CRON_FIX" "$S_CRON_FIX")"; rc6e=$?
if [ -f "$H_CRON_FIX/npm-witness.txt" ] && [ "$rc6e" -eq 0 ]; then
  pass "6e: a LEGACY box with a working migration was fixed and THEN upgraded (exit 0)"
else
  fail "6e: migrate-then-upgrade failed (rc=$rc6e, npm ran: $([ -f "$H_CRON_FIX/npm-witness.txt" ] && echo yes || echo no)). Output: $out6e"
fi

# ---------------------------------------------------------------------------
# (7) MUTATION PROOF. Neuter the detector inside a COPY of the generated cron
# script and require that the legacy box is then upgraded. If this case fails,
# cases (2)/(6b) were passing for some reason other than the detector, and this
# whole test has stopped measuring runtime enforcement.
# ---------------------------------------------------------------------------
echo "--- (7) MUTATION PROOF: break the detector, the block must disappear ---"
MUT_SCRIPT="$SANDBOX/openclaw-self-update.mutated"
MUT_SRC="$CRON_SCRIPT" MUT_DST="$MUT_SCRIPT" python3 - <<'PY'
import os, sys
s = open(os.environ["MUT_SRC"], encoding="utf-8").read()
# Neuter detection: make the analyzer always report a clean box.
mutated = s.replace(
    "print('ABSENT|no legacy list key' if 'list' not in agents else 'PRESENT|legacy agents.list key is present')",
    "print('ABSENT|MUTATED - detection removed')")
if mutated == s:
    sys.stderr.write("MUTATION DID NOT APPLY — the detector line was not found\n")
    sys.exit(1)
open(os.environ["MUT_DST"], "w").write(mutated)
PY
mut_applied=$?
if [ "$mut_applied" -eq 0 ]; then
  pass "7a: the mutation applied (the detector line exists and was neutered)"
else
  fail "7a: the mutation did not apply — the detector line was not found in the generated script"
fi
chmod +x "$MUT_SCRIPT" 2>/dev/null

H_MUT="$SANDBOX/cron-mutated"
mkdir -p "$H_MUT/.openclaw/skills"
write_config "$H_MUT/.openclaw/openclaw.json" legacy
S_MUT="$SANDBOX/cron-stubs-mut"
make_cron_stubs "$S_MUT" lie
NPM_WITNESS="$H_MUT/npm-witness.txt" HOME="$H_MUT" PATH="$S_MUT:/usr/bin:/bin" \
  bash "$MUT_SCRIPT" >/dev/null 2>&1
if [ -f "$H_MUT/npm-witness.txt" ]; then
  pass "7b: with detection neutered the SAME legacy box IS upgraded — so the block in (6b) is caused by the detector, not by luck"
else
  fail "7b: the mutated script still blocked the upgrade — case (6b) is not measuring the detector, and this test proves nothing"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi

echo "PASS: all legacy agents.list pre-upgrade gate checks pass"
exit 0

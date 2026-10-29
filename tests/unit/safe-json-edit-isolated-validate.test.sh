#!/usr/bin/env bash
# tests/unit/safe-json-edit-isolated-validate.test.sh
#
# CI guard for Big Fleet Roll error #25: update-skills.sh's safe_json_edit() ran
# `openclaw config validate` against the LIVE state dir. On OpenClaw 2026.10.x
# that command takes the sqlite maintenance lease even though it only reads, so
# on a box whose gateway was serving it left the gateway alive but unanswering
# (healthz 000, pid up) until a restart -- and under launchd KeepAlive it is the
# #18 "state is undergoing offline maintenance" crash loop.
#
# The fix: validate a throwaway COPY with OPENCLAW_HOME / OPENCLAW_STATE_DIR /
# OPENCLAW_CONFIG_PATH all pointed at a scratch dir (oc_validate_isolated).
#
# ⛔ WHAT THIS TEST REFUSES TO BE. Grepping for the env var names proves nothing.
# Every case RUNS the real, extracted shipped functions against a stub
# `openclaw` that behaves like the defective CLI: when its state dir is the
# box's LIVE one it "takes the lease" (writes a witness file there). The
# assertion is that no lease ever lands in the live state dir.
#
#   (1) extraction         oc_validate_isolated + safe_json_edit found verbatim
#   (2) CONTROL            the SAME stub, driven by the PRE-FIX code shape,
#                          DOES take the live lease -- so a clean (3) is
#                          a measurement, not a harness that cannot see the bug
#   (3) the shipped code   valid edit kept; no lease in the live state dir; the
#                          CLI saw scratch home/state/config, a copy of the
#                          edited config, and the scratch dir is gone afterwards
#   (4) rejected edit      an edit the validator rejects is ROLLED BACK
#   (5) fail closed        if the isolated check cannot be set up the edit is
#                          rolled back, never kept unvalidated
#   (6) MUTATION PROOF     calling the CLI directly (the old line) re-takes the
#                          live lease through the SHIPPED safe_json_edit
#
# Hermetic: throwaway HOME, stub openclaw on PATH, no network, no real box.
#
# Run: bash tests/unit/safe-json-edit-isolated-validate.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== safe-json-edit-isolated-validate.test.sh ==="
echo "    interpreter: bash ${BASH_VERSION:-unknown}"
echo ""

[ -f "$UPDATER" ] || { echo "FATAL: $UPDATER not found" >&2; exit 1; }

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/safe-json-edit-test.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT

# ---------------------------------------------------------------------------
# (1) Extract the shipped functions verbatim.
# ---------------------------------------------------------------------------
echo "--- (1) extract the shipped functions ---"
LIB="$SANDBOX/lib.sh"
UPDATER_PATH="$UPDATER" LIB_PATH="$LIB" python3 - <<'PY'
import os, re, sys
src = open(os.environ["UPDATER_PATH"], encoding="utf-8").read().splitlines()
out, missing = [], []
for name in ("oc_validate_isolated", "safe_json_edit"):
    start = next((i for i, l in enumerate(src) if re.match(r'^%s\(\) \{' % name, l)), None)
    end = None
    if start is not None:
        end = next((j for j in range(start + 1, len(src)) if src[j] == "}"), None)
    if start is None or end is None:
        missing.append(name)
        continue
    out.extend(src[start:end + 1]); out.append("")
open(os.environ["LIB_PATH"], "w").write("\n".join(out) + "\n")
if missing:
    sys.stderr.write("EXTRACT-MISSING:" + ",".join(missing) + "\n"); sys.exit(1)
PY
if [ $? -eq 0 ]; then
  pass "1a: oc_validate_isolated() and safe_json_edit() extracted from update-skills.sh"
else
  fail "1a: could not extract oc_validate_isolated()/safe_json_edit() (renamed or deleted?)"
  echo "=== Results: $PASS passed, $FAIL failed ==="; exit 1
fi
bash -n "$LIB" && pass "1b: the extracted functions parse" || fail "1b: extracted functions do not parse"

# ---------------------------------------------------------------------------
# Stub `openclaw` that behaves like the defective CLI.
#   - records the env it was given (STUB_LOG)
#   - "takes the maintenance lease": writes <OPENCLAW_STATE_DIR or $HOME/.openclaw>/lease
#     (that is the live dir whenever the caller did not isolate it)
#   - rejects a config whose text contains BAD-KEY (stands in for a schema error)
# ---------------------------------------------------------------------------
STUBS="$SANDBOX/stubs"
mkdir -p "$STUBS"
cat > "$STUBS/openclaw" <<'STUB'
#!/bin/bash
[ "${1:-}" = "config" ] && [ "${2:-}" = "validate" ] || exit 0
state="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"
cfg="${OPENCLAW_CONFIG_PATH:-$HOME/.openclaw/openclaw.json}"
mkdir -p "$state" && : > "$state/lease"
{
  echo "state=$state"
  echo "home=${OPENCLAW_HOME:-<unset>}"
  echo "cfg=$cfg"
  echo "skipupd=${OPENCLAW_SKIP_UPDATE_CHECK:-<unset>}"
  echo "cfg_content=$(tr -d '\n' < "$cfg" 2>/dev/null)"
} >> "$STUB_LOG"
if grep -q 'BAD-KEY' "$cfg" 2>/dev/null; then echo "Invalid config: BAD-KEY" >&2; exit 1; fi
exit 0
STUB
chmod +x "$STUBS/openclaw"

# edit functions handed to safe_json_edit (sourced by the runner shell)
EDITS="$SANDBOX/edits.sh"
cat > "$EDITS" <<'EDITS_EOF'
ADD_OK() { python3 - "$1" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d["added"] = "GOOD-KEY"; json.dump(d, open(p, "w"))
PY
}
ADD_BAD() { python3 - "$1" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d["added"] = "BAD-KEY"; json.dump(d, open(p, "w"))
PY
}
EDITS_EOF

# new_box <name> -> prints box HOME; makes a live config + live state dir
new_box() {
  local h="$SANDBOX/$1"
  mkdir -p "$h/.openclaw"
  printf '%s' '{"agents":{"defaults":{}},"original":true}' > "$h/.openclaw/openclaw.json"
  printf '%s' "$h"
}

# run_edit <box-home> <edit-fn> [libfile]   (ENV_EXTRA="NAME=value" optional)
# Runs the (shipped or mutated) safe_json_edit in a clean shell.
run_edit() {
  local h="$1" fn="$2" lib="${3:-$LIB}"
  env HOME="$h" PATH="$STUBS:/usr/bin:/bin" STUB_LOG="$h/stub.log" LOG_FILE="$h/update.log" \
    ${ENV_EXTRA:+"$ENV_EXTRA"} \
    bash -c '
      set -uo pipefail
      . "$1"; . "$2"
      safe_json_edit "$HOME/.openclaw/openclaw.json" "test edit" "$3"
    ' _ "$lib" "$EDITS" "$fn" > "$h/out.txt" 2>&1
}

ORIG='{"agents":{"defaults":{}},"original":true}'

# ---------------------------------------------------------------------------
# (2) CONTROL: the PRE-FIX call shape through the same stub DOES take the live
#     lease. Without this, "no lease" in (3) could just mean the stub is blind.
# ---------------------------------------------------------------------------
echo "--- (2) CONTROL: the pre-fix call takes the LIVE lease ---"
H2="$(new_box control)"
mkdir -p "$H2/.openclaw"
HOME="$H2" PATH="$STUBS:/usr/bin:/bin" STUB_LOG="$H2/stub.log" openclaw config validate >/dev/null 2>&1
if [ -f "$H2/.openclaw/lease" ]; then
  pass "2a: CONTROL -- a bare 'openclaw config validate' takes the lease in the LIVE state dir (the stub reproduces #25)"
else
  fail "2a: CONTROL FAILED -- the stub did not take the live lease for a bare validate, so (3) proves nothing"
fi

# ---------------------------------------------------------------------------
# (3) The shipped code, valid edit.
# ---------------------------------------------------------------------------
echo "--- (3) shipped safe_json_edit, VALID edit ---"
H3="$(new_box valid)"
run_edit "$H3" ADD_OK; rc3=$?
if [ ! -e "$H3/.openclaw/lease" ]; then
  pass "3a: NO lease was taken in the box's live state dir (the gateway's database is untouched)"
else
  fail "3a: a lease landed in the LIVE state dir -- validate ran against live state. Output: $(cat "$H3/out.txt")"
fi
if grep -q 'GOOD-KEY' "$H3/.openclaw/openclaw.json" 2>/dev/null && [ "$rc3" -eq 0 ]; then
  pass "3b: a valid edit is KEPT on the live config"
else
  fail "3b: valid edit was not kept (rc=$rc3). Output: $(cat "$H3/out.txt")"
fi
seen_state="$(sed -n 's/^state=//p' "$H3/stub.log" | head -1)"
seen_home="$(sed -n 's/^home=//p' "$H3/stub.log" | head -1)"
seen_cfg="$(sed -n 's/^cfg=//p' "$H3/stub.log" | head -1)"
seen_skip="$(sed -n 's/^skipupd=//p' "$H3/stub.log" | head -1)"
if [ -z "$seen_state" ]; then
  fail "3c: the stub never recorded an invocation (validate did not run)"
elif [ "$seen_state" = "$H3/.openclaw" ] || [ "$seen_home" = "$H3" ] || [ "$seen_cfg" = "$H3/.openclaw/openclaw.json" ]; then
  fail "3c: the CLI was pointed at the box's LIVE paths (state=$seen_state home=$seen_home cfg=$seen_cfg)"
else
  pass "3c: the CLI saw a scratch state dir / home / config, none of them the live ones"
fi
if [ -n "$seen_state" ] && [ "$seen_state" = "$seen_home" ] && [ "$(dirname "$seen_cfg")" = "$seen_state" ]; then
  pass "3d: home, state dir and config path all point at the SAME throwaway dir"
else
  fail "3d: home/state/config disagree (home=$seen_home state=$seen_state cfg=$seen_cfg)"
fi
if [ "$seen_skip" = "1" ]; then
  pass "3e: the update check is switched off for the throwaway run"
else
  fail "3e: OPENCLAW_SKIP_UPDATE_CHECK not set to 1 (got '$seen_skip')"
fi
if grep -q '^cfg_content=.*GOOD-KEY' "$H3/stub.log"; then
  pass "3f: the validator was handed a COPY carrying the EDITED config (it checked the real candidate)"
else
  fail "3f: the validator did not see the edited content. Log: $(cat "$H3/stub.log")"
fi
if [ -n "$seen_state" ] && [ ! -e "$seen_state" ]; then
  pass "3g: the scratch dir is removed afterwards"
else
  fail "3g: scratch dir '$seen_state' still exists after validation"
fi

# ---------------------------------------------------------------------------
# (4) A rejected edit is rolled back.
# ---------------------------------------------------------------------------
echo "--- (4) shipped safe_json_edit, REJECTED edit ---"
H4="$(new_box rejected)"
run_edit "$H4" ADD_BAD; rc4=$?
if [ "$(cat "$H4/.openclaw/openclaw.json")" = "$ORIG" ]; then
  pass "4a: an edit the validator rejects is ROLLED BACK byte-for-byte"
else
  fail "4a: rejected edit survived: $(cat "$H4/.openclaw/openclaw.json")"
fi
if [ ! -e "$H4/.openclaw/lease" ] && ! ls "$H4/.openclaw"/openclaw.json.bak-* >/dev/null 2>&1; then
  pass "4b: rejection took no live lease and left no backup file behind"
else
  fail "4b: live lease or leftover backup present after rejection"
fi
if grep -q 'validate FAILED' "$H4/out.txt"; then
  pass "4c: the rollback is announced"
else
  fail "4c: no rollback message. Output: $(cat "$H4/out.txt")"
fi

# ---------------------------------------------------------------------------
# (5) Fail closed: isolated check cannot be set up -> edit rolled back.
# ---------------------------------------------------------------------------
echo "--- (5) FAIL CLOSED when the scratch dir cannot be made ---"
H5="$(new_box failclosed)"
ENV_EXTRA="TMPDIR=$SANDBOX/does/not/exist" run_edit "$H5" ADD_OK; rc5=$?
if [ "$(cat "$H5/.openclaw/openclaw.json")" = "$ORIG" ] && [ ! -e "$H5/.openclaw/lease" ]; then
  pass "5a: with no scratch dir the edit is ROLLED BACK and the live state dir is still untouched (never an unvalidated keep, never a live fallback)"
else
  fail "5a: unvalidated edit kept or live fallback taken: $(cat "$H5/.openclaw/openclaw.json"); lease=$([ -e "$H5/.openclaw/lease" ] && echo yes || echo no)"
fi

# ---------------------------------------------------------------------------
# (6) MUTATION PROOF: swap the isolated call back to the old bare line inside a
#     COPY of the shipped function; the live lease must come back.
# ---------------------------------------------------------------------------
echo "--- (6) MUTATION PROOF: restore the old bare validate, the lease returns ---"
MUT="$SANDBOX/lib.mutated.sh"
MUT_SRC="$LIB" MUT_DST="$MUT" python3 - <<'PY'
import os, sys
s = open(os.environ["MUT_SRC"], encoding="utf-8").read()
m = s.replace('if ! oc_validate_isolated "$OCJSON"; then',
              'if ! openclaw config validate >> "$LOG_FILE" 2>&1; then')
if m == s:
    sys.stderr.write("MUTATION DID NOT APPLY\n"); sys.exit(1)
open(os.environ["MUT_DST"], "w").write(m)
PY
if [ $? -eq 0 ]; then
  pass "6a: the mutation applied (safe_json_edit calls oc_validate_isolated at the validate site)"
else
  fail "6a: mutation did not apply -- safe_json_edit no longer routes validation through oc_validate_isolated"
fi
H6="$(new_box mutated)"
run_edit "$H6" ADD_OK "$MUT"
if [ -e "$H6/.openclaw/lease" ]; then
  pass "6b: with the old bare line restored the live lease IS taken -- so (3a) is caused by the isolation, not by luck"
else
  fail "6b: mutated code did not take the live lease; (3a) is not measuring the isolation"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed"
  exit 1
fi
echo "PASS: safe_json_edit validates in isolation and never touches the live state dir"
exit 0

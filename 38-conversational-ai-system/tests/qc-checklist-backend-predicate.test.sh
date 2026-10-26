#!/usr/bin/env bash
# qc-checklist-backend-predicate.test.sh — pins the readiness predicate inside
# scripts/11-run-qc-checklist.sh to the PBB-017 decision: `model` is OPTIONAL on
# a hooks.mappings entry (agentId is sufficient), and only a PRESENT-but-BLANK
# override is refused.
#
# The predicate is extracted from the shipped script (not copied), so a future
# edit that re-introduces `no-model` fails here instead of passing a correct
# fresh install through a false failure.
#
# Run: bash tests/qc-checklist-backend-predicate.test.sh
# Exit: 0 = every case matched; 1 = at least one failed; 2 = missing tool.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKLIST="$HERE/../scripts/11-run-qc-checklist.sh"
command -v python3 >/dev/null 2>&1 || { echo "[SKIP] python3 absent"; exit 2; }
[ -f "$CHECKLIST" ] || { echo "FAIL checklist not found at $CHECKLIST"; exit 1; }

TMP="${TMPDIR:-/tmp}/qc-checklist-backend-predicate.$$"
mkdir -p "$TMP" || exit 2
trap 'rm -rf "$TMP"' EXIT

PRED="$TMP/predicate.py"
python3 -I - "$CHECKLIST" > "$PRED" <<'PY'
import re, sys
t = open(sys.argv[1]).read()
m = re.search(r"<<'PY_BACKEND_EOF'.*?\n(.*?)\nPY_BACKEND_EOF", t, re.S)
if not m:
    sys.exit("predicate heredoc not found")
sys.stdout.write(m.group(1) + "\n")
PY
[ -s "$PRED" ] || { echo "FAIL could not extract the readiness predicate"; exit 1; }

fails=0
run() { HOOK_NAME=hook-1 python3 -I - "$1" < "$PRED"; }
cfg() { printf '%s\n' "$2" > "$TMP/$1.json"; echo "$TMP/$1.json"; }

# One complete, contract-valid mapping body, varied only in the model/deliver keys.
body() {
  jq -nc --arg deliver "$1" --argjson model "$2" '
    {hooks:{enabled:true, mappings:[
      ({id:"hook-1", match:{path:"hook-1"}, action:"agent", agentId:"a",
        messageTemplate:"x", deliver:($deliver == "true")}
       + (if $model == null then {} else {model:$model} end))]}}'
}

expect() { # name expected-json-model deliver
  local name="$1" want="$2" model="$3" deliver="$4" f got
  f="$(cfg "$name" "$(body "$deliver" "$model")")"
  got="$(run "$f")"
  if [ "$got" = "$want" ]; then
    echo "ok   $name -> $got"
  else
    echo "FAIL $name: want '$want', got '$got'"
    fails=$((fails+1))
  fi
}

# The decision: an ABSENT model is valid (this is what the writer emits).
expect "no-model-key"          "OK"                       null   false
# Known-good control: a present, non-blank override is also valid.
expect "model-set"             "OK"                       '"m/x"' false
# Only a PRESENT-but-BLANK override is refused, and the reason names it.
expect "blank-model"           "ERR:blank-model-override" '""'   false
# deliver:false is still required, and the reason must not smuggle in "no-model".
expect "deliver-true"          "ERR:deliver-not-false"    null   true
expect "deliver-true-model"    "ERR:deliver-not-false"    '"m/x"' true

# Control on the instrument itself: a missing config must never read as OK.
_absent="$(HOOK_NAME=hook-1 python3 -I - "$TMP/absent.json" < "$PRED" 2>/dev/null)"
if [ -n "$_absent" ] && [ "$_absent" != "OK" ]; then
  echo "ok   instrument: unreadable config -> $_absent"
else
  echo "FAIL instrument: a missing config was not reported as an error"
  fails=$((fails+1))
fi

if [ "$fails" -ne 0 ]; then
  echo "qc-checklist-backend-predicate.test.sh: $fails FAILED"
  exit 1
fi
echo "qc-checklist-backend-predicate.test.sh: 6 cases, all met."

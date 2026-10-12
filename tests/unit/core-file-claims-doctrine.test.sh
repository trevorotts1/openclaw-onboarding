#!/usr/bin/env bash
# core-file-claims-doctrine.test.sh (RRS001) -- the Core-File Claims doctrine is in the shared
# AGENTS.md AND is stamped onto every box by apply-fleet-standards.sh, with identical text.
set -uo pipefail
P="[core-file-claims]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
R="$(python3 - "$ROOT" <<'PY'
import re, sys
root = sys.argv[1]
a = open(root + "/AGENTS.md", encoding="utf-8").read()
m = re.search(r"(<!-- CORE_FILE_CLAIMS_V1 -->\n.*?)\n<!-- WE_MOVE_IN_SILENCE_V1 -->", a, re.S)
f = open(root + "/scripts/apply-fleet-standards.sh", encoding="utf-8").read()
n = re.search(r"<<'CFCEOF'\n\n(.*?)\nCFCEOF\n", f, re.S)
print("section" if m else "no-section")
print("stamp" if n else "no-stamp")
print("same" if (m and n and m.group(1).strip() == n.group(1).strip()) else "differ")
print("n44" if re.search(r"^\| N44 \|", a, re.M) else "no-n44")
for needle in ("absolute path of every place you checked", "find -L",
               "Never judge the owner's files from a secondary agent's own folder", "OPENCLAW_WORKSPACE"):
    print(("has:" if m and needle in m.group(1) else "lacks:") + needle)
PY
)"
echo "$R" | grep -qx section && pass "AGENTS.md carries the CORE_FILE_CLAIMS_V1 section" || fail "AGENTS.md section missing"
echo "$R" | grep -qx stamp && pass "apply-fleet-standards.sh carries the stamp block" || fail "stamp block missing"
echo "$R" | grep -qx same && pass "AGENTS.md section and the stamped block are identical" || fail "AGENTS.md section and stamped block differ"
echo "$R" | grep -qx n44 && pass "N44 row is in the canonical index" || fail "N44 row missing"
echo "$R" | grep '^lacks:' | while read -r l; do echo "$P FAIL: doctrine ${l}" >&2; done
echo "$R" | grep -q '^lacks:' && FAIL=$((FAIL+1)) || pass "doctrine states all four rules"
echo "$P Results: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]

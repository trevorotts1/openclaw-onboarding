#!/usr/bin/env bash
# A contract-check that prints OK and then never exits (open stdin pipe) must be
# ended by run-bounded.sh within seconds, and a clean exit code must pass through.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RB="$ROOT/32-command-center-setup/scripts/run-bounded.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT; rc=0
cat > "$T/hang.mjs" <<'JS'
console.log("OK - all 10 hard contracts hold");
process.stdin.resume();
JS
echo 'process.exit(3)' > "$T/exit3.mjs"
command -v node >/dev/null || { echo "SKIP: no node"; exit 0; }
# Case 1: stdin-held-open hang (the Sheila bug). Parent feeds an open pipe; RB must close it.
start=$SECONDS
bash "$RB" 20 node "$T/hang.mjs" >"$T/out" 2>&1 < <(sleep 30)
elapsed=$((SECONDS-start))
if [[ $elapsed -le 6 ]] && grep -q "all 10 hard" "$T/out"; then echo "PASS: stdin hang ended in ${elapsed}s"; else echo "FAIL: stdin hang elapsed=${elapsed}s" >&2; rc=1; fi
# Case 2: hang not tied to stdin (timer) must be killed by the alarm.
echo 'console.log("OK"); setInterval(()=>{},1000)' > "$T/timer.mjs"
start=$SECONDS
bash "$RB" 2 node "$T/timer.mjs" >"$T/out2" 2>&1; erc=$?
elapsed=$((SECONDS-start))
if [[ $elapsed -le 6 && $erc -ne 0 ]]; then echo "PASS: timer hang killed in ${elapsed}s (rc=$erc)"; else echo "FAIL: timer hang elapsed=${elapsed}s rc=$erc" >&2; rc=1; fi
bash "$RB" 5 node "$T/exit3.mjs"; [[ $? -eq 3 ]] && echo "PASS: exit code passes through" || { echo "FAIL: exit code" >&2; rc=1; }
exit $rc

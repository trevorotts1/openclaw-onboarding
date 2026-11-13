#!/usr/bin/env bash
# Folded from .github/workflows/rescue-rangers-rr031-gates.yml (job "RR-031 gates (reconcile + abort + lock + deadlines + mutation drills)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Shell + Python syntax gates
echo "--- step: Shell + Python syntax gates"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards rescue-rangers-rr031-gates: step \"Shell + Python syntax gates\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash -n scripts/reconcile-rr-agent-map.sh
bash -n scripts/seed-rr-agent-map.sh
bash -n scripts/apply-fleet-standards.sh
bash -n tests/unit/rr031-reconcile-agent-map.test.sh
python3 -m py_compile scripts/_rr_registry_lib.py
python3 -m py_compile tests/unit/fixtures/mock-rr-datatable.py
)
( # step: RR-031 gate (identity, pagination, repair, container, pending, lock, deadlines, credentials)
echo "--- step: RR-031 gate (identity, pagination, repair, container, pending, lock, deadlines, credentials)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards rescue-rangers-rr031-gates: step \"RR-031 gate (identity, pagination, repair, container, pending, lock, deadlines, credentials)\" failed (exit $fg_rc)"' EXIT
bash tests/unit/rr031-reconcile-agent-map.test.sh
)
( # step: Anti-vacuity — mutation drills (each mutant MUST turn the gate red)
echo "--- step: Anti-vacuity — mutation drills (each mutant MUST turn the gate red)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards rescue-rangers-rr031-gates: step \"Anti-vacuity — mutation drills (each mutant MUST turn the gate red)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# A green that cannot go red is not a check. Five mutants, one per
# load-bearing behaviour, each must produce a non-zero exit:
#   A single-page reader      B insert-only (never repair)
#   C continue past an incomplete source
#   D no scoped lock          E wrapper reports a non-zero as ok
rm -rf /tmp/rr031-mut && mkdir -p /tmp/rr031-mut
for m in A B C D E; do
  mkdir -p "/tmp/rr031-mut/$m"
  cp -R scripts shared-utils tests "/tmp/rr031-mut/$m/"
done
python3 - <<'PY'
import sys
def patch(path, old, new, label):
    s = open(path).read()
    if old not in s:
        sys.exit("mutation anchor missing: %s" % label)
    open(path, "w").write(s.replace(old, new, 1))
patch("/tmp/rr031-mut/A/scripts/_rr_registry_lib.py",
      '    nxt = d.get("nextCursor")',
      '    nxt = None  # MUTANT A: single-page reader',
      "A")
patch("/tmp/rr031-mut/B/scripts/_rr_registry_lib.py",
      '        elif str(existing[0].get("local_agent_id") or "") == agent:\n            verified += 1\n        else:',
      '        elif True:  # MUTANT B: never repair an existing row\n            verified += 1\n        else:',
      "B")
s = open("/tmp/rr031-mut/C/scripts/reconcile-rr-agent-map.sh").read()
i = s.index('    py emit-empty "aborted=1"')
j = s.index("exit 1", i) + len("exit 1")
open("/tmp/rr031-mut/C/scripts/reconcile-rr-agent-map.sh", "w").write(
    s[:i] + '    echo "MUTANT C: continuing past an incomplete source" >&2' + s[j:])
s = open("/tmp/rr031-mut/D/scripts/reconcile-rr-agent-map.sh").read()
s = s.replace("acquire_lock() {", "acquire_lock() { return 0  # MUTANT D\n  : <<'NOLOCK'\n", 1)
s = s.replace('  printf \'%s\\n\' "$OWN_PID" > "$LOCK_PATH/pid"\n}',
              '  printf \'%s\\n\' "$OWN_PID" > "$LOCK_PATH/pid"\nNOLOCK\n}', 1)
open("/tmp/rr031-mut/D/scripts/reconcile-rr-agent-map.sh", "w").write(s)
# E: the wrapper reverts to the old fail-open (a skip reported as ok)
s = open("/tmp/rr031-mut/E/scripts/apply-fleet-standards.sh").read()
i = s.index("        3)")
j = s.index("      esac", i)
s = s[:i] + '        3|*) echo "[apply-fleet-standards] RR_AGENT_MAP_RECONCILE ok (changed=0 verified=0 pending=0)" ;;\n' + s[j:]
open("/tmp/rr031-mut/E/scripts/apply-fleet-standards.sh", "w").write(s)
PY
fail=0
for m in A B C D E; do
  if (cd "/tmp/rr031-mut/$m" && bash tests/unit/rr031-reconcile-agent-map.test.sh >/dev/null 2>&1); then
    echo "MUTANT $m PASSED the gate — the gate cannot detect it (vacuous)"
    fail=1
  else
    echo "mutant $m correctly turned the gate red"
  fi
done
exit "$fail"
)

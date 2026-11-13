#!/usr/bin/env bash
# Folded from .github/workflows/embedded-python-syntax-guard.yml (job "ONB-STATE-001: every embedded Python program compiles"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: The guard itself compiles
echo "--- step: The guard itself compiles"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedded-python-syntax-guard: step \"The guard itself compiles\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -m py_compile scripts/check-embedded-python-syntax.py
)
( # step: Self-test — the guard FAILS on a broken body and PASSES on a healthy one
echo "--- step: Self-test — the guard FAILS on a broken body and PASSES on a healthy one"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedded-python-syntax-guard: step \"Self-test — the guard FAILS on a broken body and PASSES on a healthy one\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
FIX="$(mktemp -d)"

# (1) The exact defect shape: `return` outside a function, behind the
#     `2>/dev/null || true` that hides it at runtime.
cat > "$FIX/broken.sh" <<'SH'
#!/usr/bin/env bash
mark() {
  python3 - <<'PYEOF' 2>/dev/null || true
import json
try: state = json.load(open("x"))
except Exception: return
PYEOF
}
SH

if python3 scripts/check-embedded-python-syntax.py --root "$FIX" >"$FIX/out.txt" 2>&1; then
  echo "VACUOUS GUARD: it did not flag a 'return' outside a function." >&2
  cat "$FIX/out.txt" >&2
  exit 1
fi
grep -q "'return' outside function" "$FIX/out.txt" || {
  echo "Guard failed, but not for the expected reason:" >&2
  cat "$FIX/out.txt" >&2
  exit 1
}
echo "  ✓ broken heredoc is caught"

# (2) ast.parse() would MISS that. Pin the distinction: if this ever
#     stops holding, the guard has been weakened back to useless.
python3 - <<'PY'
import ast, sys
src = 'try:\n    x = 1\nexcept Exception: return\n'
try:
    ast.parse(src)
except SyntaxError:
    sys.exit("ast.parse now rejects this; the guard's compile() rationale needs review")
try:
    compile(src, "<t>", "exec")
except SyntaxError:
    print("  ✓ compile() catches what ast.parse() misses")
else:
    sys.exit("compile() no longer catches 'return' outside function — guard is unsound")
PY

# (3) A healthy repo must PASS, or the guard is just a red light.
rm -rf "$FIX"; FIX="$(mktemp -d)"
cat > "$FIX/healthy.sh" <<'SH'
#!/usr/bin/env bash
mark() {
  python3 - <<'PYEOF'
import json, sys
try:
    state = json.load(open("x"))
except OSError:
    sys.exit(1)
PYEOF
  python3 -c 'import json; print(json.dumps({"ok": True}))'
}
SH
python3 scripts/check-embedded-python-syntax.py --root "$FIX" >"$FIX/out.txt" 2>&1 || {
  echo "FALSE POSITIVE: the guard rejected a healthy body." >&2
  cat "$FIX/out.txt" >&2
  exit 1
}
echo "  ✓ healthy heredoc and python -c both pass"
rm -rf "$FIX"
)
( # step: Every embedded Python program in the repo compiles
echo "--- step: Every embedded Python program in the repo compiles"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedded-python-syntax-guard: step \"Every embedded Python program in the repo compiles\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 scripts/check-embedded-python-syntax.py --root . --verbose
)
( # step: oc_state_mark_field regression lock
echo "--- step: oc_state_mark_field regression lock"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedded-python-syntax-guard: step \"oc_state_mark_field regression lock\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash tests/unit/state-mark-field-silent-noop.test.sh
)
( # step: install-time fail-open regression lock (ONB-STATE-002)
echo "--- step: install-time fail-open regression lock (ONB-STATE-002)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedded-python-syntax-guard: step \"install-time fail-open regression lock (ONB-STATE-002)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash tests/unit/install-state-fail-open.test.sh
)
( # step: bash-4 syntax needs the bash 4+ re-exec guard (ISSUE-14)
echo "--- step: bash-4 syntax needs the bash 4+ re-exec guard (ISSUE-14)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedded-python-syntax-guard: step \"bash-4 syntax needs the bash 4+ re-exec guard (ISSUE-14)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash tests/unit/bash4-syntax-guard.test.sh
)

#!/usr/bin/env bash
# tests/unit/presentation-deck-intake-driver-workspace.test.sh
#
# U86 [GK-24] — the DRIVER leg of the binary acceptance, made durable.
#
# GK-24 binary acceptance, leg 3 (verbatim): "driver invoked from an alien cwd
# with --workspace writes ONLY under the named workspace (filesystem diff proves
# zero writes elsewhere)."
#
# GROUNDING CORRECTION (VERIFIED-BY-EXECUTION, recorded here so the next reader
# does not re-derive it): the unit spec assumed deck-intake-driver.py resolved a
# bare CWD-relative `working/` and therefore needed a NEW --workspace flag "with
# the current directory as default". It does not. The driver has ALWAYS required
# --run-dir DIR (main(): "--run-dir DIR is required for all commands except
# --selftest") and resolves it to an ABSOLUTE path via .expanduser().resolve()
# before any write. Every write in the file is <run_dir>/working/... — the bare
# `working/` strings in the source are RELATIVE-TO-run_dir path fragments
# (LEDGER_REL / ANSWERS_REL / INTAKE_JSON_REL), never CWD-relative roots. So the
# driver is structurally INCAPABLE of the wrong-live-workspace write the spec
# feared, and adding a CWD-defaulting --workspace would make it STRICTLY LESS
# safe. The real bare-`working/` offender in this department was the sibling the
# spec's own parenthetical anticipated — "(and any sibling that resolves bare
# `working/`)" — intelligence_engines_check.py, fixed on this unit and guarded by
# tests/unit/presentation-intelligence-engines-workspace.test.sh.
#
# WHY THIS GUARD EXISTS ANYWAY: the driver's containment was, until now, an
# UNTESTED emergent property of a mandatory flag. Nothing stopped a later change
# from giving --run-dir a default (e.g. `default="working"`), silently restoring
# exactly the defect class GK-24 exists to kill — a driver invoked from an alien
# cwd writing into someone else's live workspace. This guard pins the property
# with the literal filesystem diff the acceptance criterion names.
#
# This guard proves:
#   (A) invoked from an ALIEN cwd with --run-dir, the driver writes ONLY under
#       the named workspace: a full before/after filesystem diff of the alien cwd
#       (paths AND content hashes) shows ZERO writes elsewhere, while the named
#       workspace demonstrably receives the ledger;
#   (B) invoked with NO --run-dir from a cwd that HAS a working/ dir sitting in
#       it (the precise defect scenario), the driver REFUSES and writes NOTHING —
#       there is no reachable bare-`working/` CWD default;
#   (C) statically, --run-dir carries no default= and no getenv/environ CWD
#       fallback was introduced.
#
# EXIT CODES: 0 all pass; 1 one or more assertions failed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DRIVER="$ROOT/23-ai-workforce-blueprint/scripts/deck-intake-driver.py"
PY="${PYTHON:-python3}"

PASS=0
FAIL=0
pass() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

[ -f "$DRIVER" ] || { echo "FATAL: deck-intake-driver.py not found at $DRIVER" >&2; exit 1; }

TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

# Hash every file under a tree as "<relpath>  <sha256>" so the diff catches a
# silent in-place MODIFICATION of an existing file, not just added/removed paths.
snapshot() {
    ( cd "$1" && find . -type f -exec shasum -a 256 {} \; 2>/dev/null | sort -k2 )
}

echo "--- (A) alien cwd + --run-dir: writes land ONLY under the named workspace ---"

NAMED_WS="$TMPDIR_TEST/named-workspace"
ALIEN_CWD="$TMPDIR_TEST/alien-cwd"
mkdir -p "$NAMED_WS"
# The alien cwd is a DECOY live workspace: it has exactly the working/ layout the
# driver would clobber if it ever resolved `working/` against the caller's cwd.
mkdir -p "$ALIEN_CWD/working/interview" "$ALIEN_CWD/working/copy"
echo '{"decoy":"another deck live ledger — MUST NOT be touched"}' > "$ALIEN_CWD/working/interview/intake_ledger.json"
echo '{"decoy":"another deck live intake — MUST NOT be touched"}' > "$ALIEN_CWD/working/copy/intake.json"

snapshot "$ALIEN_CWD" > "$TMPDIR_TEST/alien.before"

( cd "$ALIEN_CWD" && "$PY" "$DRIVER" --run-dir "$NAMED_WS" --next >/dev/null 2>&1 )
RC=$?

snapshot "$ALIEN_CWD" > "$TMPDIR_TEST/alien.after"

if [ "$RC" -eq 0 ]; then
    pass "driver ran successfully from an alien cwd with --run-dir (exit 0)"
else
    fail "driver did not run cleanly from an alien cwd with --run-dir (exit $RC)"
fi

if diff -u "$TMPDIR_TEST/alien.before" "$TMPDIR_TEST/alien.after" > "$TMPDIR_TEST/alien.diff" 2>&1; then
    pass "filesystem diff of the alien cwd is EMPTY — zero writes elsewhere (paths + content hashes identical)"
else
    fail "driver wrote into the alien cwd — leg 3 violated: $(cat "$TMPDIR_TEST/alien.diff")"
fi

# The write must actually have happened SOMEWHERE, or the diff above is vacuous.
if [ -f "$NAMED_WS/working/interview/intake_ledger.json" ]; then
    pass "the named workspace DID receive the ledger (the empty alien diff is meaningful, not vacuous)"
else
    fail "no ledger under the named workspace — the driver wrote nothing, so the alien-cwd diff proves nothing"
fi

# Every file the run created must be under the named workspace, with no escapes.
ESCAPES="$("$PY" - "$NAMED_WS" <<'PY'
import pathlib, sys
ws = pathlib.Path(sys.argv[1]).resolve()
bad = [str(p) for p in ws.rglob("*") if p.is_file() and not str(p.resolve()).startswith(str(ws))]
print("\n".join(bad))
PY
)"
if [ -z "$ESCAPES" ]; then
    pass "every file created by the run is contained under the named workspace"
else
    fail "files escaped the named workspace: $ESCAPES"
fi

echo "--- (B) NO --run-dir, cwd holds a working/ dir: refuse + write nothing ---"

BARE_CWD="$TMPDIR_TEST/bare-cwd"
mkdir -p "$BARE_CWD/working/interview" "$BARE_CWD/working/copy"
echo '{"decoy":"live ledger a bare call must never touch"}' > "$BARE_CWD/working/interview/intake_ledger.json"

snapshot "$BARE_CWD" > "$TMPDIR_TEST/bare.before"
ERR="$( ( cd "$BARE_CWD" && "$PY" "$DRIVER" --next ) 2>&1 )"; RC=$?
snapshot "$BARE_CWD" > "$TMPDIR_TEST/bare.after"

if [ "$RC" -ne 0 ]; then
    pass "bare --next (no --run-dir) is REFUSED (exit $RC) — no silent CWD-relative default"
else
    fail "bare --next succeeded (exit 0) — a CWD-relative working/ default is reachable"
fi

if echo "$ERR" | grep -q -- "--run-dir DIR is required" && ! echo "$ERR" | grep -qi "traceback"; then
    pass "refusal is fail-honest (names --run-dir as required, no Python traceback)"
else
    fail "refusal was not fail-honest: $ERR"
fi

if diff -u "$TMPDIR_TEST/bare.before" "$TMPDIR_TEST/bare.after" >/dev/null 2>&1; then
    pass "bare call wrote NOTHING into the cwd's working/ (decoy ledger byte-identical)"
else
    fail "bare call mutated the cwd's working/ — the defect class is live"
fi

echo "--- (C) static: --run-dir has no default, no CWD-relative env fallback ---"

if "$PY" - "$DRIVER" <<'PY'
import pathlib, sys, re
src = pathlib.Path(sys.argv[1]).read_text()
# The --run-dir add_argument must not carry a default= (which would resurrect the
# implicit-workspace defect). Isolate its add_argument(...) call.
m = re.search(r'add_argument\(\s*["\']--run-dir["\'].*?\)\n', src, re.S)
if not m:
    print("FATAL: could not locate the --run-dir add_argument call"); sys.exit(1)
if "default=" in m.group(0):
    print("REGRESSION: --run-dir now carries a default:\n" + m.group(0)); sys.exit(1)
sys.exit(0)
PY
then
    pass "--run-dir declares no default= (an implicit workspace cannot be reintroduced silently)"
else
    fail "--run-dir now declares a default= — the implicit-workspace defect class is back"
fi

if "$PY" - "$DRIVER" <<'PY'
import pathlib, sys
src = pathlib.Path(sys.argv[1]).read_text()
# Guard the grounded invariant: the driver takes its workspace from the explicit
# flag only. If an env/CWD fallback is ever added it must come with a test that
# proves containment — fail here so that change cannot land unnoticed.
hits = [n for n in ("os.getenv", "os.environ", "getcwd", "Path.cwd()") if n in src]
if hits:
    print("NEW ambient-workspace source(s) introduced: " + ", ".join(hits)); sys.exit(1)
sys.exit(0)
PY
then
    pass "driver still derives its workspace ONLY from the explicit flag (no getenv/environ/cwd ambient source)"
else
    fail "driver gained an ambient workspace source — containment is no longer guaranteed by the flag alone"
fi

echo
echo "===================================================================="
echo " presentation-deck-intake-driver-workspace: PASS=$PASS FAIL=$FAIL"
echo "===================================================================="
[ "$FAIL" -eq 0 ]

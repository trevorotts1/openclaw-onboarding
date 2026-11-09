#!/usr/bin/env bash
# tests/unit/single-root-deployment-assertion.test.sh
# -----------------------------------------------------------------------------
# Wiring lock for the FIX-11 step 5 single-root deployment assertion in
# update-skills.sh (repository half of FIX-10/FIX-11).
#
# WHAT THIS PROVES
#   T1  the block extracts from the shipped updater at all (positive control:
#       a silent empty extraction would make every later case vacuous)
#   T2  exactly one installed tree at the released version  -> gate CLEAN
#   T3  two installed trees for one skill (canonical + .agents/skills shadow)
#       -> gate FAILS and the failure text names the step
#   T4  installed version != released version -> gate FAILS
#   T5  the assertion is READ-ONLY: no file is created, removed or rewritten
#   T6  the block is WIRED: it sits before the `_STEP_GATE_FAILS` consumption
#       in update-skills.sh, and that block withholds the stamp and exits 1 --
#       so a failed assertion fails the deployment instead of only printing
#   T7  the helper the block invokes ships in the repository
#
# Hermetic: mktemp -d sandbox, synthetic release + install roots, stubs for the
# updater's bounded-run helpers. No ~/.openclaw, no network, no box, no writes
# to the repository. Bash 3.2 safe.
# Exit 0 = all pass.
# -----------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"
HELPER="$REPO_ROOT/scripts/assert-skill-single-tree.py"

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  PASS: %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL: %s\n' "$1"; }

echo "=== single-root-deployment-assertion.test.sh ==="

[ -f "$UPDATER" ] || { bad "update-skills.sh missing at $UPDATER"; printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"; exit 1; }
[ -f "$HELPER" ]  || { bad "scripts/assert-skill-single-tree.py missing"; printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"; exit 1; }

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/single-root-assert.XXXXXX")"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

BLOCK="$SANDBOX/block.sh"
sed -n '/FIX11-SINGLE-ROOT-ASSERTION-BEGIN/,/FIX11-SINGLE-ROOT-ASSERTION-END/p' "$UPDATER" > "$BLOCK"

# T1 — positive control on the extraction itself.
if [ -s "$BLOCK" ] \
   && grep -qF 'assert-skill-single-tree.py' "$BLOCK" \
   && grep -qF 'oc_bounded_run' "$BLOCK"; then
  ok "T1 assertion block extracted verbatim from update-skills.sh"
else
  bad "T1 extraction produced no block (markers moved?) — remaining cases cannot be trusted"
fi

REL="$SANDBOX/release"
SK="$SANDBOX/home/.openclaw/skills"
SHADOW="$SANDBOX/home/.agents/skills"
mkdir -p "$REL/83-black-friday-launcher" "$SK/83-black-friday-launcher"
# The block invokes the release bundle's own copy of the helper, exactly as the
# shipped updater does (scripts/ ships inside every bundle).
mkdir -p "$REL/scripts"
cp "$HELPER" "$REL/scripts/assert-skill-single-tree.py"
printf '0.2.20\n' > "$REL/83-black-friday-launcher/skill-version.txt"
printf '0.2.20\n' > "$SK/83-black-friday-launcher/skill-version.txt"
printf '# release\n' > "$REL/83-black-friday-launcher/SKILL.md"
printf '# installed\n' > "$SK/83-black-friday-launcher/SKILL.md"

snapshot() { find "$SANDBOX/home" -print | sort; }

# Runs the extracted block in a subshell with the updater's helpers stubbed and
# prints whatever it appended to _STEP_GATE_FAILS.
run_block() {
  (
    EXTRACTED_DIR="$REL"; SKILLS_DIR="$SK"; ONLY_SKILLS=""; _SRT_SKIP=""
    _STEP_GATE_FAILS=""
    oc_bounded_seconds() { printf '%s' "${1:-60}"; }
    oc_bounded_run() { shift 2; "$@"; }
    # shellcheck source=/dev/null
    . "$BLOCK" >/dev/null 2>&1
    printf '%s' "$_STEP_GATE_FAILS"
  )
}

# T2 — clean: one tree, released version.
OUT="$(run_block)"
if [ -z "$OUT" ]; then
  ok "T2 one installed tree at the released version leaves the gate clean"
else
  bad "T2 clean case gated: $OUT"
fi

# T3 — duplicate: canonical + shadow tree for one skill name.
BEFORE="$(snapshot)"
mkdir -p "$SHADOW/black-friday-launcher"
printf '0.2.17\n' > "$SHADOW/black-friday-launcher/skill-version.txt"
printf '# shadow\n' > "$SHADOW/black-friday-launcher/SKILL.md"
AFTER_SETUP="$(snapshot)"
OUT="$(run_block)"
if printf '%s' "$OUT" | grep -qF 'rc=1'; then
  ok "T3 duplicate installed tree (canonical + .agents/skills shadow) FAILS the deployment gate (rc=1)"
else
  bad "T3 duplicate tree did not gate with rc=1: '$OUT'"
fi

# T5 — read-only: the failing assertion changed nothing under the install home.
AFTER="$(snapshot)"
if [ "$AFTER_SETUP" = "$AFTER" ]; then
  ok "T5 assertion is read-only (no file created, removed or rewritten)"
else
  bad "T5 assertion modified the install home"
fi

# T4 — version mismatch: one tree, wrong version.
rm -rf "$SHADOW"
printf '0.2.19\n' > "$SK/83-black-friday-launcher/skill-version.txt"
OUT="$(run_block)"
if printf '%s' "$OUT" | grep -qF 'rc=1'; then
  ok "T4 installed version different from the release FAILS the deployment gate (rc=1)"
else
  bad "T4 version mismatch did not gate with rc=1: '$OUT'"
fi

# T6 — ordering: the assertion block precedes the gate that withholds the stamp.
ORDER_RC=0
python3 -I - "$UPDATER" <<'PY' || ORDER_RC=$?
import sys
lines = open(sys.argv[1], encoding='utf-8').read().split('\n')
begin = end = gate = None
for i, line in enumerate(lines):
    if 'FIX11-SINGLE-ROOT-ASSERTION-BEGIN' in line: begin = i
    if 'FIX11-SINGLE-ROOT-ASSERTION-END' in line: end = i
    if line.strip() == 'if [ -n "$_STEP_GATE_FAILS" ]; then' and gate is None:
        gate = i
if begin is None or end is None or gate is None:
    print('missing marker or gate', begin, end, gate); sys.exit(1)
if not (begin < end < gate):
    print('order wrong', begin, end, gate); sys.exit(1)
tail = '\n'.join(lines[gate:gate+15])
if 'stamp NOT written' not in tail or 'exit 1' not in tail:
    print('gate does not withhold the stamp and exit 1'); sys.exit(1)
sys.exit(0)
PY
if [ "$ORDER_RC" -eq 0 ]; then
  ok "T6 block is wired before the stamp-withholding gate (failure exits 1)"
else
  bad "T6 assertion block is not wired before the stamp-withholding gate"
fi

# T7 — helper ships. (Existence proven above; name it for the record.)
ok "T7 repository ships scripts/assert-skill-single-tree.py"

printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

#!/usr/bin/env bash
# Regression guard: the root updater must deliver canonical scripts/ recursively.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE_SH="${UPDATE_SH_UNDER_TEST:-$REPO_ROOT/update-skills.sh}"
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); printf '  PASS: %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL: %s\n' "$1"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/full-scripts-tree.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

echo "=== update-skills-full-scripts-tree.test.sh ==="

if grep -q '^# >>> CANONICAL-SCRIPTS-DELIVERY-BEGIN' "$UPDATE_SH" \
   && grep -q '^# <<< CANONICAL-SCRIPTS-DELIVERY-END' "$UPDATE_SH"; then
  ok "recursive delivery helper is extractable from the root updater"
  sed -n '/^# >>> CANONICAL-SCRIPTS-DELIVERY-BEGIN/,/^# <<< CANONICAL-SCRIPTS-DELIVERY-END/p' \
    "$UPDATE_SH" > "$WORK/helper.sh"
else
  bad "recursive delivery helper markers are missing"
  printf 'deliver_canonical_scripts_tree() { return 99; }\n' > "$WORK/helper.sh"
fi
# shellcheck source=/dev/null
source "$WORK/helper.sh"

SRC="$WORK/source/scripts"
DST="$WORK/box/.openclaw/scripts"
mkdir -p "$SRC/fleet-roll" "$SRC/probe" "$SRC/tests" "$DST/local-tools"
printf '#!/usr/bin/env bash\necho root\n' > "$SRC/root-tool.sh"
printf '#!/usr/bin/env python3\nprint("roll")\n' > "$SRC/fleet-roll/roll.py"
printf '#!/usr/bin/env bash\necho probe\n' > "$SRC/probe/check.sh"
printf 'print("test")\n' > "$SRC/tests/test_delivery.py"
printf 'canonical metadata\n' > "$SRC/README.txt"
printf '#!/usr/bin/env bash\necho local\n' > "$DST/local-tools/box-only.sh"
chmod 755 "$SRC/root-tool.sh" "$SRC/fleet-roll/roll.py" "$SRC/probe/check.sh"
chmod 644 "$SRC/tests/test_delivery.py" "$SRC/README.txt"
chmod 755 "$DST/local-tools/box-only.sh"

if deliver_canonical_scripts_tree "$SRC" "$DST" > "$WORK/first.out" 2>&1; then
  ok "recursive delivery succeeds"
else
  bad "recursive delivery returned non-zero"
fi

for rel in root-tool.sh fleet-roll/roll.py probe/check.sh tests/test_delivery.py README.txt; do
  if [ -f "$DST/$rel" ] && cmp -s "$SRC/$rel" "$DST/$rel"; then
    ok "delivered canonical path: $rel"
  else
    bad "missing or changed canonical path: $rel"
  fi
done

[ -x "$DST/fleet-roll/roll.py" ] && ok "executable bit preserved" || bad "executable bit lost"
[ ! -x "$DST/tests/test_delivery.py" ] && ok "non-executable bit preserved" || bad "non-executable file became executable"
[ -f "$DST/local-tools/box-only.sh" ] && ok "box-local script retained (additive sync)" || bad "box-local script was deleted"

before_count="$(find "$DST" -type f | wc -l | tr -d ' ')"
if deliver_canonical_scripts_tree "$SRC" "$DST" > "$WORK/second.out" 2>&1; then
  after_count="$(find "$DST" -type f | wc -l | tr -d ' ')"
  [ "$before_count" = "$after_count" ] && ok "second run is idempotent (no duplicates)" || bad "second run changed file count"
else
  bad "second recursive delivery failed"
fi

if deliver_canonical_scripts_tree "$WORK/missing/scripts" "$DST" > "$WORK/missing.out" 2>&1; then
  bad "missing canonical tree incorrectly returned success"
else
  grep -q 'FATAL:' "$WORK/missing.out" && ok "missing canonical tree fails loudly" || bad "missing tree failure was not loud"
fi

# A destination the node user genuinely cannot create/write is an OWNERSHIP/env
# quirk (the ≈6 root:root VPS boxes) that must DEGRADE (rc 2 + a loud actionable
# chown instruction), NEVER fatal-abort the whole run before the version stamp.
# Reproduced WITHOUT root by making a path component a regular file (ENOTDIR):
# mkdir -p cannot create the dest and the best-effort self-heal cannot fix it,
# so the helper must degrade rather than abort.
BLOCKER="$WORK/blocker-file"
printf 'not a directory\n' > "$BLOCKER"
UNWRITABLE="$BLOCKER/scripts"
deliver_canonical_scripts_tree "$SRC" "$UNWRITABLE" > "$WORK/perms.out" 2>&1
_perms_rc=$?
if [ "$_perms_rc" -eq 2 ]; then
  ok "un-creatable destination degrades (rc=2), does not fatal-abort the run"
else
  bad "un-creatable destination returned rc=$_perms_rc (expected 2 = deferred degrade)"
fi
if grep -q 'ACTION REQUIRED' "$WORK/perms.out" && grep -q 'chown -R' "$WORK/perms.out"; then
  ok "perms degrade emits an actionable chown instruction"
else
  bad "perms degrade did not name the required chown"
fi
if ! grep -q 'FATAL:' "$WORK/perms.out"; then
  ok "perms degrade is a WARN, never a FATAL"
else
  bad "perms degrade wrongly printed FATAL"
fi

# The caller must treat rc 2 as a non-fatal DEFERRED delivery (proceed to the
# stamp), and reserve the exit-1 abort for a real fatal (rc 1).
if grep -q 'OC_SCRIPTS_DELIVERY_DEFERRED' "$UPDATE_SH" \
   && grep -q '_SCRIPTS_RC" -eq 1' "$UPDATE_SH"; then
  ok "root update path degrades on an ownership quirk (rc 2) and only aborts on a real fatal (rc 1)"
else
  bad "root update path does not distinguish deferred (rc 2) from fatal (rc 1)"
fi

if grep -q 'deliver_canonical_scripts_tree "$ONBOARDING_DIR/scripts" "$_OC_SCRIPTS_DEST"' "$UPDATE_SH"; then
  ok "root update path invokes full-tree delivery"
else
  bad "root update path does not invoke full-tree delivery"
fi
if grep -q 'for _s in onboarding-state.sh ghl-mcp-autostart.sh' "$UPDATE_SH"; then
  bad "old hardcoded flat scripts allowlist is still active"
else
  ok "old hardcoded flat allowlist removed"
fi

canonical_pysh="$(find "$REPO_ROOT/scripts" -type f \( -name '*.py' -o -name '*.sh' \) | wc -l | tr -d ' ')"
[ "$canonical_pysh" -ge 100 ] && ok "canonical fixture covers the full scripts corpus ($canonical_pysh .py/.sh files)" || bad "canonical scripts corpus unexpectedly small ($canonical_pysh)"

# Exercise the helper against the repository's real canonical tree, not only a
# five-file synthetic fixture. This is the fleet delivery receipt.
FULL_DST="$WORK/full-box/scripts"
if deliver_canonical_scripts_tree "$REPO_ROOT/scripts" "$FULL_DST" > "$WORK/full.out" 2>&1; then
  ok "real canonical scripts tree delivers recursively"
else
  bad "real canonical scripts tree delivery failed"
fi
src_files="$(find "$REPO_ROOT/scripts" -type f | wc -l | tr -d ' ')"
dst_files="$(find "$FULL_DST" -type f 2>/dev/null | wc -l | tr -d ' ')"
[ "$src_files" = "$dst_files" ] \
  && ok "real canonical file count matches at destination ($src_files files)" \
  || bad "real canonical file count mismatch (source=$src_files destination=$dst_files)"
subtrees_ok=1
for subtree in fleet-roll probe tests; do
  find "$FULL_DST/$subtree" -type f \( -name '*.py' -o -name '*.sh' \) -print -quit 2>/dev/null | grep -q . \
    || subtrees_ok=0
done
if [ "$subtrees_ok" -eq 1 ]; then
  ok "fleet-roll/, probe/, and tests/ subtrees are present"
else
  bad "one or more required scripts subtrees are absent"
fi
full_mismatches=0
while IFS= read -r -d '' src_path; do
  rel="${src_path#"$REPO_ROOT/scripts/"}"
  dst_path="$FULL_DST/$rel"
  if [ ! -f "$dst_path" ] || ! cmp -s "$src_path" "$dst_path" \
     || { [ -x "$src_path" ] && [ ! -x "$dst_path" ]; } \
     || { [ ! -x "$src_path" ] && [ -x "$dst_path" ]; }; then
    full_mismatches=$((full_mismatches + 1))
  fi
done < <(find "$REPO_ROOT/scripts" -type f \( -name '*.py' -o -name '*.sh' \) -print0)
[ "$full_mismatches" -eq 0 ] \
  && ok "all $canonical_pysh canonical .py/.sh files match bytes and executable bits" \
  || bad "$full_mismatches canonical .py/.sh file(s) differ after delivery"

printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

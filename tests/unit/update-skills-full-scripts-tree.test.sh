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

# One destination FILE owned by another user (a root-owned mc-route.sh left by a
# root `docker exec`) inside a writable scripts/ dir. The node user can neither
# open it for writing nor chmod it, but may unlink it. Reproduced without root:
# a read-only file plus a no-op chmod so the self-heal cannot rescue it.
FOREIGN_DST="$WORK/foreign-box/scripts"
mkdir -p "$FOREIGN_DST"
printf 'stale foreign-owned copy\n' > "$FOREIGN_DST/root-tool.sh"
command chmod 444 "$FOREIGN_DST/root-tool.sh"
(
  chmod() { :; }
  deliver_canonical_scripts_tree "$SRC" "$FOREIGN_DST"
) > "$WORK/foreign.out" 2>&1
_foreign_rc=$?
if [ "$_foreign_rc" -eq 0 ] && cmp -s "$SRC/root-tool.sh" "$FOREIGN_DST/root-tool.sh"; then
  ok "an unwritable file in a writable scripts/ dir is replaced, not a FATAL"
else
  bad "an unwritable file in a writable scripts/ dir returned rc=$_foreign_rc (expected 0 + canonical bytes)"
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

# ── W07 / GU-019: the updater must PRUNE the retired community-MCP surfaces
# from the DESTINATION after every delivery, or each roll reinstalls the
# resurrection surfaces install.sh prunes at :4063-4094.
if grep -q '^# >>> GHL-MCP-RETIREMENT-PRUNE-BEGIN' "$UPDATE_SH" \
   && grep -q '^# <<< GHL-MCP-RETIREMENT-PRUNE-END' "$UPDATE_SH"; then
  ok "retirement prune block is extractable from the root updater"
  sed -n '/^# >>> GHL-MCP-RETIREMENT-PRUNE-BEGIN/,/^# <<< GHL-MCP-RETIREMENT-PRUNE-END/p' \
    "$UPDATE_SH" > "$WORK/prune.sh"
else
  bad "retirement prune block markers are missing"
  printf 'prune_retired_ghl_mcp_surfaces() { return 99; }\n' > "$WORK/prune.sh"
fi
# shellcheck source=/dev/null
source "$WORK/prune.sh"
type prune_retired_ghl_mcp_surfaces >/dev/null 2>&1 \
  && ok "prune function is callable in isolation (hermetic, no roll run)" \
  || bad "prune function missing or not callable"

# Both delivery call sites must invoke it (scripts tree + platform copy).
_prune_calls="$(grep -c 'prune_retired_ghl_mcp_surfaces "$_OC_SCRIPTS_DEST"' "$UPDATE_SH")"
[ "$_prune_calls" -ge 2 ] \
  && ok "both delivery sites (scripts tree, platform copy) invoke the prune ($_prune_calls calls)" \
  || bad "prune invoked at only $_prune_calls delivery site(s); at least scripts/ + platform/ are required"

# Hermetic fixture: retired files present, unrelated files present.
PRUNE_S="$WORK/prune-box/.openclaw/scripts"
PRUNE_P="$WORK/prune-box/.openclaw/skills/platform"
mkdir -p "$PRUNE_S/lib" "$PRUNE_S/local-tools" \
         "$PRUNE_P/vps/36-ghl-mcp-setup-scripts" "$PRUNE_P/vps/hostinger"
printf '#!/usr/bin/env bash\necho autostart\n' > "$PRUNE_S/ghl-mcp-autostart.sh"
printf '#!/usr/bin/env bash\necho probe\n'    > "$PRUNE_S/ghl-mcp-probe.sh"
printf '#!/usr/bin/env bash\necho digest\n'   > "$PRUNE_S/ghl-mcp-pin-digest.sh"
printf '#!/usr/bin/env bash\necho gate\n'     > "$PRUNE_S/qc-assert-ghl-mcp-supervised.sh"
printf '#!/usr/bin/env bash\necho paths\n'    > "$PRUNE_S/lib/ghl-mcp-paths.sh"
printf '#!/usr/bin/env bash\necho start\n'    > "$PRUNE_P/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"
printf '#!/usr/bin/env bash\necho keep\n'     > "$PRUNE_S/local-tools/box-only.sh"
printf '#!/usr/bin/env bash\necho keep\n'     > "$PRUNE_S/lib/shared-unrelated.sh"
printf 'keep\n'                               > "$PRUNE_P/vps/36-ghl-mcp-setup-scripts/unrelated-helper.sh"
printf 'keep\n'                               > "$PRUNE_P/common.sh"
printf 'keep\n'                               > "$PRUNE_P/vps/hostinger/keep.txt"

if _prune_out="$(prune_retired_ghl_mcp_surfaces "$PRUNE_S" "$PRUNE_P" 2>&1)"; then
  ok "prune exits 0 with the retired files present"
else
  bad "prune returned non-zero with the retired files present: $_prune_out"
fi
printf '%s\n' "$_prune_out" | grep -q 'pruned 6 supervision file(s)' \
  && ok "prune logs one line naming exactly what it removed (6)" \
  || bad "prune log line missing the removed count: $_prune_out"

for _prune_rel in ghl-mcp-autostart.sh ghl-mcp-probe.sh ghl-mcp-pin-digest.sh \
                  qc-assert-ghl-mcp-supervised.sh lib/ghl-mcp-paths.sh; do
  [ ! -e "$PRUNE_S/$_prune_rel" ] \
    && ok "retired scripts/$_prune_rel pruned" \
    || bad "retired scripts/$_prune_rel SURVIVED the prune"
done
[ ! -e "$PRUNE_P/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh" ] \
  && ok "retired platform start script pruned" \
  || bad "retired platform start script SURVIVED the prune"

# Unrelated files must survive — the prune is targeted, not a directory wipe.
for _keep_rel in local-tools/box-only.sh lib/shared-unrelated.sh; do
  [ -f "$PRUNE_S/$_keep_rel" ] \
    && ok "unrelated scripts/$_keep_rel survives" \
    || bad "unrelated scripts/$_keep_rel was deleted by the prune"
done
[ -f "$PRUNE_P/vps/hostinger/keep.txt" ] \
  && ok "unrelated platform/vps/hostinger file survives" \
  || bad "unrelated platform/vps/hostinger file was deleted"
[ -f "$PRUNE_P/common.sh" ] \
  && ok "unrelated platform/common.sh survives" \
  || bad "platform/common.sh was deleted by the prune"
[ -f "$PRUNE_P/vps/36-ghl-mcp-setup-scripts/unrelated-helper.sh" ] \
  && ok "unrelated file in the pruned platform dir survives" \
  || bad "unrelated file in the pruned platform dir was deleted"

# Idempotent + never fatal: second run, then a destination that does not exist.
if _prune_out2="$(prune_retired_ghl_mcp_surfaces "$PRUNE_S" "$PRUNE_P" 2>&1)"; then
  ok "second prune run exits 0 (idempotent)"
else
  bad "second prune run returned non-zero"
fi
printf '%s\n' "$_prune_out2" | grep -q 'nothing to prune' \
  && ok "second prune run logs 'nothing to prune'" \
  || bad "second prune run did not log the no-op: $_prune_out2"
if prune_retired_ghl_mcp_surfaces "$WORK/no-such/scripts" "$WORK/no-such/platform" >/dev/null 2>&1; then
  ok "prune exits 0 when the destination is absent (never fails the roll)"
else
  bad "prune failed on an absent destination"
fi

printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

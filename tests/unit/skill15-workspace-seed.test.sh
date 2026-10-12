#!/usr/bin/env bash
# skill15-workspace-seed.test.sh (RRS001) -- the remote-rescue workspace is SEEDED.
#
# THE LIVE BUG: install-remote-rescue.sh created ~/.openclaw/workspaces/remote-rescue
# EMPTY. On the first operator DM OpenClaw filled it with blank starter files plus a
# BOOTSTRAP.md "you were just born" script, so the agent had no identity, looked only
# inside its own near-empty folder, and told the operator the owner's workspace was
# unconfigured. Its folder also had no TOOLS.md, so it never saw the box's tool notes.
#
# Hermetic: mktemp sandbox, HOME redirected, a fake `openclaw`. No box, no network.
set -uo pipefail
P="[skill15-workspace-seed]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INST="$ROOT/15-blackceo-team-management/scripts/install-remote-rescue.sh"
QC="$ROOT/15-blackceo-team-management/qc-blackceo-team-management.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
cat > "$TMP/bin/openclaw" <<'FAKE'
#!/usr/bin/env bash
if [ "${1:-}" = "config" ] && [ "${2:-}" = "validate" ]; then echo '{"valid":true,"issues":[]}'; exit 0; fi
exit 0
FAKE
chmod +x "$TMP/bin/openclaw"

# fresh_box NAME -> sets H (home), OCR (.openclaw), MAIN (owner workspace), RR (rescue workspace)
fresh_box() {
  H="$TMP/$1/home"; OCR="$H/.openclaw"; MAIN="$OCR/workspace-owner"; RR="$OCR/workspaces/remote-rescue"
  mkdir -p "$OCR" "$MAIN"
  printf '{"agents":{"defaults":{"workspace":"%s"},"entries":{"main":{}}},"channels":{"telegram":{"allowFrom":[],"groupAllowFrom":[]}}}\n' "$MAIN" > "$OCR/openclaw.json"
}
run_inst() { HOME="$H" PATH="$TMP/bin:$PATH" env -u OPENCLAW_WORKSPACE bash "$INST" "$@" 2>&1; }
STARTER_ID='# IDENTITY.md - Who Am I?

_Fill this in during your first conversation. Make it yours._
- **Name:**
  _(pick something you like)_'
STARTER_SOUL="# SOUL.md - Who You Are

_You're not a chatbot. You're becoming someone._"
STARTER_BOOT='# BOOTSTRAP.md - Birth Sequence

_You just woke up. Keep this first conversation short and make it yours._'

# --- 1. fresh install: empty workspace gets the full seed ---------------------
fresh_box t1
printf 'BOX TOOL NOTES: send mail via the service account\n' > "$MAIN/TOOLS.md"
OUT="$(run_inst --idempotent)"; RC=$?
[[ $RC -eq 0 ]] && pass "t1 installer rc=0" || fail "t1 installer rc=$RC: $(printf '%s' "$OUT" | tail -3 | tr '\n' ' ')"
for f in IDENTITY.md SOUL.md AGENTS.md TOOLS.md; do
  [ -s "$RR/$f" ] && pass "t1 $f seeded" || fail "t1 $f missing or empty"
done
grep -q "rr-operator-support:v1" "$RR/IDENTITY.md" 2>/dev/null && pass "t1 IDENTITY.md is the operator-support identity (not a starter)" || fail "t1 IDENTITY.md not the seed"
grep -qF "$MAIN" "$RR/IDENTITY.md" && grep -qF "$MAIN" "$RR/AGENTS.md" && pass "t1 IDENTITY.md and AGENTS.md name the absolute main workspace ($MAIN)" || fail "t1 main workspace path not named"
grep -q "NOT the owner's workspace" "$RR/AGENTS.md" && pass "t1 AGENTS.md says this folder is not the owner's workspace" || fail "t1 AGENTS.md missing the not-owner's-workspace line"
grep -q "find -L" "$RR/AGENTS.md" && pass "t1 AGENTS.md carries the name-paths / follow-symlinks rule" || fail "t1 AGENTS.md missing find -L rule"
cmp -s "$MAIN/TOOLS.md" "$RR/TOOLS.md" && pass "t1 TOOLS.md is a copy of the box's main TOOLS.md" || fail "t1 TOOLS.md is not the main copy"
[ ! -e "$RR/BOOTSTRAP.md" ] && pass "t1 no BOOTSTRAP.md" || fail "t1 BOOTSTRAP.md present"
grep -rn "@@" "$RR" >/dev/null 2>&1 && fail "t1 an unfilled @@placeholder@@ was left in the seed" || pass "t1 no unfilled placeholders"

# --- 2. idempotent: a second run changes nothing ------------------------------
SUM1="$(cd "$RR" && cat IDENTITY.md SOUL.md AGENTS.md TOOLS.md | shasum | cut -d' ' -f1)"
run_inst --idempotent >/dev/null
SUM2="$(cd "$RR" && cat IDENTITY.md SOUL.md AGENTS.md TOOLS.md | shasum | cut -d' ' -f1)"
[[ "$SUM1" == "$SUM2" ]] && pass "t2 second run leaves the seeded files byte-identical" || fail "t2 second run changed seeded files"

# --- 3. OpenClaw starter files + birth script are replaced / removed ----------
fresh_box t3; mkdir -p "$RR"
printf '%s\n' "$STARTER_ID" > "$RR/IDENTITY.md"; printf '%s\n' "$STARTER_SOUL" > "$RR/SOUL.md"
printf '%s\n' "$STARTER_BOOT" > "$RR/BOOTSTRAP.md"
run_inst --idempotent >/dev/null
grep -q "rr-operator-support:v1" "$RR/IDENTITY.md" && grep -q "rr-operator-support:v1" "$RR/SOUL.md" && pass "t3 starter IDENTITY.md and SOUL.md replaced" || fail "t3 starter files not replaced"
[ ! -e "$RR/BOOTSTRAP.md" ] && pass "t3 template BOOTSTRAP.md removed" || fail "t3 template BOOTSTRAP.md still present"

# --- 4. a file the box already filled in is NEVER overwritten ----------------
fresh_box t4; mkdir -p "$RR"
printf 'OUR OWN IDENTITY, hand written\n' > "$RR/IDENTITY.md"
printf 'OUR OWN SOUL, hand written\n' > "$RR/SOUL.md"
printf 'OUR OWN AGENTS, hand written\n' > "$RR/AGENTS.md"
printf 'OUR OWN TOOLS, hand written\n' > "$RR/TOOLS.md"
printf '%s\n' "$STARTER_BOOT" > "$RR/BOOTSTRAP.md"
run_inst --idempotent >/dev/null
OK=1
for f in IDENTITY SOUL AGENTS TOOLS; do grep -q "OUR OWN $f, hand written" "$RR/$f.md" || OK=0; done
[[ $OK -eq 1 ]] && pass "t4 non-template files kept byte-for-byte" || fail "t4 a non-template file was overwritten"
[ ! -e "$RR/BOOTSTRAP.md" ] && pass "t4 template BOOTSTRAP.md still removed (identity is real)" || fail "t4 template BOOTSTRAP.md left behind"

# --- 5. a customised BOOTSTRAP.md is not ours to delete ----------------------
fresh_box t5; mkdir -p "$RR"
printf 'Custom bootstrap the box wrote itself.\n' > "$RR/BOOTSTRAP.md"
run_inst --idempotent >/dev/null
[ -f "$RR/BOOTSTRAP.md" ] && pass "t5 a non-template BOOTSTRAP.md is kept" || fail "t5 a custom BOOTSTRAP.md was deleted"

# --- 6. $OPENCLAW_WORKSPACE wins, like skill 70 pr_workspace() ---------------
fresh_box t6
OUT="$(HOME="$H" PATH="$TMP/bin:$PATH" OPENCLAW_WORKSPACE="$TMP/t6/env-main" bash "$INST" --idempotent 2>&1)"
grep -qF "$TMP/t6/env-main" "$RR/IDENTITY.md" && pass "t6 OPENCLAW_WORKSPACE is the named main workspace" || fail "t6 OPENCLAW_WORKSPACE ignored"

# --- 7. --check is read-only and reports the seed it would do ---------------
fresh_box t7
OUT="$(run_inst --check)"
[ ! -e "$RR/IDENTITY.md" ] && pass "t7 --check wrote no seed file" || fail "t7 --check wrote IDENTITY.md"
[[ "$OUT" == *"seed-needed"* ]] && pass "t7 --check reports seed-needed" || fail "t7 --check did not report seed-needed: $(printf '%s' "$OUT" | grep seed | head -2)"

# --- 8. the QC gate: fails a LeAnne-shaped workspace, passes a seeded one ----
qc_line() { HOME="$H" PATH="$TMP/bin:$PATH" bash "$QC" 2>&1 | grep -i "remote-rescue workspace" | head -1; }
fresh_box t8
HOME="$H" PATH="$TMP/bin:$PATH" bash "$INST" --repair >/dev/null 2>&1   # wires the config entry and seeds
printf '%s\n' "$STARTER_ID" > "$RR/IDENTITY.md"; printf '%s\n' "$STARTER_BOOT" > "$RR/BOOTSTRAP.md"; rm -f "$RR/SOUL.md" "$RR/AGENTS.md" "$RR/TOOLS.md"
L="$(qc_line)"
[[ "$L" == *FAIL* ]] && pass "t8 QC gate FAILS a starter-identity + birth-script workspace" || fail "t8 QC gate did not fail the bad workspace: '$L'"
HOME="$H" PATH="$TMP/bin:$PATH" bash "$INST" --repair >/dev/null 2>&1
L="$(qc_line)"
[[ "$L" == *PASS* ]] && pass "t8 QC gate PASSES after the installer seeds it" || fail "t8 QC gate did not pass the seeded workspace: '$L'"

echo "$P Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]

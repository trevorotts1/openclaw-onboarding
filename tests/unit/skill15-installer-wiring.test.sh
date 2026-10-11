#!/usr/bin/env bash
# skill15-installer-wiring.test.sh — the updater must DISCOVER and RUN skill 15's
# installer, and that installer must survive a GNU-userland box.
#
# THE LIVE BUG (two repo defects, one symptom — skill 15 QC fails 4 isolation
# gates on every box):
#   1. update-skills.sh only ran wire.sh / install.sh / scripts/install.sh /
#      setup-*.sh as a skill's installer. Skill 15 ships only
#      scripts/install-remote-rescue.sh, so the updater never ran it and no box
#      that skipped INSTALL.md Step 0.5 ever got the operator routing applied.
#   2. install-remote-rescue.sh used `mktemp -t rr032-report` under
#      `set -euo pipefail`. GNU coreutils rejects the legacy -t form ("too few
#      X's", rc=1), so every VPS/Contabo box died at the first temp file.
#   3. The same installer rejected the `--idempotent` flag the updater always
#      passes (usage, exit 2), so even once discovered it would not run.
set -uo pipefail
P="[skill15-installer-wiring]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPD="$ROOT/update-skills.sh"
INST="$ROOT/15-blackceo-team-management/scripts/install-remote-rescue.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# --- 1. the updater's candidate list discovers scripts/install-*.sh -----------
if grep -q '"$SKILL_DIR"/scripts/install-\*\.sh' "$UPD"; then
  pass "update-skills.sh candidate list includes \"\$SKILL_DIR\"/scripts/install-*.sh"
else
  fail "update-skills.sh candidate list does NOT match scripts/install-*.sh"
fi

# Mirror of the updater's discovery loop (kept in lockstep with the grep above).
pick() {
  local SKILL_DIR="$1" _candidate
  SKILL_INSTALLER=""
  for _candidate in "$SKILL_DIR/wire.sh" "$SKILL_DIR/install.sh" "$SKILL_DIR/scripts/install.sh" "$SKILL_DIR"/scripts/install-*.sh; do
    if [ -x "$_candidate" ]; then SKILL_INSTALLER="$_candidate"; break; fi
  done
  if [ -z "$SKILL_INSTALLER" ]; then
    for _candidate in "$SKILL_DIR"/setup-*.sh "$SKILL_DIR"/scripts/setup-*.sh; do
      if [ -x "$_candidate" ]; then SKILL_INSTALLER="$_candidate"; break; fi
    done
  fi
  printf '%s' "$SKILL_INSTALLER"
}

GOT="$(pick "$ROOT/15-blackceo-team-management")"
[[ "$GOT" == "$ROOT/15-blackceo-team-management/scripts/install-remote-rescue.sh" ]] \
  && pass "skill 15 discovery picks scripts/install-remote-rescue.sh" \
  || fail "skill 15 discovery picked '$GOT'"

# Control: a skill that ships wire.sh must STILL prefer wire.sh — proves the
# discovery change did not reorder the existing priority.
CTRL="$(pick "$ROOT/32-command-center-setup")"
[[ "$CTRL" == "$ROOT/32-command-center-setup/wire.sh" ]] \
  && pass "control: a skill with wire.sh still prefers wire.sh" \
  || fail "control: skill 32 discovery picked '$CTRL', expected wire.sh"

# --- 2. the installer accepts the updater's --idempotent flag -----------------
mkdir -p "$TMP/home/.openclaw" "$TMP/bin"
printf '{"agents":{"main":{}},"channels":{"telegram":{"allowFrom":[],"groupAllowFrom":["5252140759"]}}}\n' \
  > "$TMP/home/.openclaw/openclaw.json"
cat > "$TMP/bin/openclaw" <<'FAKE'
#!/usr/bin/env bash
if [ "${1:-}" = "config" ] && [ "${2:-}" = "validate" ]; then echo '{"valid":true,"issues":[]}'; exit 0; fi
exit 0
FAKE
chmod +x "$TMP/bin/openclaw"
OUT="$(HOME="$TMP/home" PATH="$TMP/bin:$PATH" bash "$INST" --idempotent 2>&1)"; RC=$?
if [[ $RC -eq 0 && "$OUT" == *"Remote Rescue state:"* ]]; then
  pass "--idempotent runs the installer to the engine (rc=0)"
else
  fail "--idempotent did not run the installer (rc=$RC): $(printf '%s' "$OUT" | head -2 | tr '\n' ' ')"
fi
# Control: an unknown flag must STILL be refused (the usage branch is live).
HOME="$TMP/home" bash "$INST" --nope >/dev/null 2>&1 \
  && fail "control: an unknown flag was accepted (usage branch dead)" \
  || pass "control: an unknown flag is still refused"

# --- 3. no legacy `mktemp -t` (rejected by GNU coreutils) ---------------------
if grep -q 'mktemp -t ' "$INST"; then
  fail "installer still uses the legacy 'mktemp -t' form (dies on GNU coreutils)"
else
  pass "installer uses no legacy 'mktemp -t' form"
fi

echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]

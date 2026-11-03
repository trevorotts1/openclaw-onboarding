#!/usr/bin/env bash
# tests/test_launch_family_prereqs.sh   (CON-13 + CON-14)
#
# CON-13  Skills 49, 71, 78-83, 44 and 38 import `jsonschema`; no installer
#         provisioned it. Proves: 83's PREREQS.json declares jsonschema>=4.0;
#         install.sh and update-skills.sh both call oc_ensure_jsonschema and
#         expose a --check; and, in a CLEAN python (a fresh venv without
#         jsonschema), --check flags it without mutating, --apply makes
#         `python3 -c 'import jsonschema'` exit 0, and the version floor and the
#         requirement read from PREREQS.json are enforced (negative controls).
# CON-14  The launch family 78-83 is either in a wave whose members all ship
#         verify.sh, or the exclusion is recorded in lib-onboarding-state.sh.
#
# Offline and hermetic: the "jsonschema" it installs is a stub wheel the test
# builds itself, served through PIP_NO_INDEX/PIP_FIND_LINKS. No network, nothing
# outside a mktemp dir is written. Pure bash + python3, no grep.
#
# Exit 0 = all pass, 1 = any failure.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
has() { [[ "$1" == *"$2"* ]]; }                 # has <text> <needle>

T="$(mktemp -d "${TMPDIR:-/tmp}/launch-prereqs.XXXXXX")" || { echo "mktemp failed"; exit 1; }
trap 'rm -rf "$T"' EXIT

echo "=== test_launch_family_prereqs.sh ==="

LIB="$REPO/lib-onboarding-state.sh"
INSTALL="$(<"$REPO/install.sh")"
UPDATE="$(<"$REPO/update-skills.sh")"
LIBTXT="$(<"$LIB")"

# ---- 1. PREREQS.json declares the requirement and passes the repo lint ------
PJ="$REPO/83-black-friday-launcher/PREREQS.json"
if python3 -c 'import json,sys
d = json.load(open(sys.argv[1]))
assert d["skill"] == "83-black-friday-launcher"
m = [p for p in d["prerequisites"] if p.get("pythonModule") == "jsonschema"]
assert len(m) == 1 and m[0]["requirement"] == "jsonschema>=4.0", m' "$PJ" 2>/dev/null; then
  ok "T1 83 PREREQS.json declares jsonschema>=4.0 (pythonModule entry)"
else
  bad "T1 83-black-friday-launcher/PREREQS.json missing or lacks the jsonschema>=4.0 entry"
fi
if bash "$REPO/scripts/qc-prereqs-json.sh" >"$T/lint.out" 2>&1; then
  ok "T1b scripts/qc-prereqs-json.sh accepts every PREREQS.json"
else
  bad "T1b scripts/qc-prereqs-json.sh FAILED: $(tail -n 3 "$T/lint.out")"
fi

# ---- 2. both installers call the ensure step and expose --check -------------
calls_ensure() { has "$1" 'oc_ensure_jsonschema --apply' && has "$1" 'oc_ensure_jsonschema --check'; }
if calls_ensure "$INSTALL"; then ok "T2 install.sh applies oc_ensure_jsonschema and has a --check path"
else bad "T2 install.sh does not both --apply and --check oc_ensure_jsonschema"; fi
if calls_ensure "$UPDATE"; then ok "T2 update-skills.sh applies oc_ensure_jsonschema and has a --check path"
else bad "T2 update-skills.sh does not both --apply and --check oc_ensure_jsonschema"; fi
if calls_ensure "${INSTALL//oc_ensure_jsonschema --apply/removed}"; then
  bad "T2 NON-DISCRIMINATING: detector passed install.sh with the --apply call removed"
else ok "T2 detector discriminates (call removed from a copy is rejected)"; fi
if has "$UPDATE" '*" --check "*|*" --prereqs-check "*)' && has "$INSTALL" '*" --check "*|*" --prereqs-check "*)'; then
  ok "T2 --check flag is parsed by both installers"
else bad "T2 --check flag is not parsed by both installers"; fi

# ---- 3. CON-13 proof in a CLEAN python --------------------------------------
if ! python3 -m venv "$T/venv" >"$T/venv.out" 2>&1; then
  bad "T3 could not create a clean venv: $(tail -n 2 "$T/venv.out")"
else
  export PATH="$T/venv/bin:$PATH"
  export PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1
  export OPENCLAW_ROOT="$T/oc"; mkdir -p "$T/oc/skills"
  unset OPENCLAW_PREREQS_CHECK OC_CONFIG OC_SKILLS_DIR

  mkwheel() {   # mkwheel <outdir> <version>
    mkdir -p "$1"
    python3 - "$1" "$2" <<'PYEOF'
import sys, zipfile
out, ver = sys.argv[1], sys.argv[2]
di = "jsonschema-%s.dist-info" % ver
with zipfile.ZipFile("%s/jsonschema-%s-py3-none-any.whl" % (out, ver), "w") as z:
    z.writestr("jsonschema/__init__.py", "__version__ = %r\n" % ver)
    z.writestr(di + "/METADATA", "Metadata-Version: 2.1\nName: jsonschema\nVersion: %s\n" % ver)
    z.writestr(di + "/WHEEL", "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
    z.writestr(di + "/RECORD", "")
PYEOF
  }
  mkwheel "$T/wheels-ok" 4.2.0
  mkwheel "$T/wheels-old" 3.2.0
  # PIP_FIND_LINKS is whitespace-split, and this checkout path may contain spaces:
  # hand pip a percent-encoded file:// URL instead of a raw path.
  uri() { python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve().as_uri())' "$1"; }
  W_OK="$(uri "$T/wheels-ok")"; W_OLD="$(uri "$T/wheels-old")"

  if python3 -c 'import jsonschema' 2>/dev/null; then
    bad "T3 precondition: the clean venv already imports jsonschema"
  else
    ok "T3 precondition: clean python cannot import jsonschema"

    # T5: EXECUTE the real scripts. Clean python first on PATH, no bypass env vars:
    # --check must need none, must exit before the update lock, and must not crash.
    mkdir -p "$T/home"
    t5_check() {   # t5_check <label> <bash-binary> <script>
      local rc=0 out
      out="$(cd "$T" && env -u ONBOARDING_DIR -u FLEET_PREFLIGHT_BYPASS -u FLEET_STANDING_GATE_BYPASS \
          -u OPENCLAW_UPDATE_SKIP_SELF_SYNC -u OPENCLAW_RELEASE_PIN_MODE HOME="$T/home" OPENCLAW_UPDATE_LEASE="$T/upd.lock" \
          "$2" "$REPO/$3" --check 2>&1)" || rc=$?
      T5_RC=$rc; T5_OUT="$out"
      if [ "$rc" -eq 2 ] && has "$out" '[prereq][83-black-friday-launcher][required] jsonschema' \
         && ! has "$out" 'unbound variable' && [ ! -e "$T/upd.lock" ] && ! python3 -c 'import jsonschema' 2>/dev/null; then
        ok "T5 $1: $3 --check flags missing jsonschema (rc=2), no crash, no lock, nothing installed"
      else bad "T5 $1: $3 --check rc=$rc out=[$out]"; fi
    }
    for SH in update-skills.sh install.sh; do t5_check "bash" "$(command -v bash)" "$SH"; done
    if [ -x /bin/bash ] && [ "$(command -v bash)" != "/bin/bash" ]; then t5_check "/bin/bash" /bin/bash update-skills.sh; fi
    # shellcheck source=/dev/null
    source "$LIB"

    rc=0; out="$(oc_ensure_jsonschema --check 2>&1)" || rc=$?
    if [ "$rc" -eq 2 ] && has "$out" '[prereq][83-black-friday-launcher][required] jsonschema'; then
      ok "T3 --check flags the missing jsonschema (rc=2, prerequisite line printed)"
    else bad "T3 --check rc=$rc out=[$out]"; fi
    if python3 -c 'import jsonschema' 2>/dev/null; then bad "T3 --check MUTATED the environment"
    else ok "T3 --check installed nothing"; fi

    rc=0; out="$(OPENCLAW_PREREQS_CHECK=1 oc_ensure_jsonschema --apply 2>&1)" || rc=$?
    if [ "$rc" -eq 2 ] && ! python3 -c 'import jsonschema' 2>/dev/null; then
      ok "T3 OPENCLAW_PREREQS_CHECK=1 forces check-only even with --apply"
    else bad "T3 OPENCLAW_PREREQS_CHECK=1 did not hold (rc=$rc)"; fi

    # negative control: only an OLD jsonschema is available -> must not pass
    rc=0; out="$(PIP_FIND_LINKS="$W_OLD" oc_ensure_jsonschema --apply 2>&1)" || rc=$?
    if [ "$rc" -eq 2 ] && has "$out" 'FAILED' && has "$out" '3.2.0'; then ok "T3 apply fails loudly when only jsonschema<4.0 exists (rc=2, FAILED)"
    else bad "T3 old-version control rc=$rc out=[$out]"; fi

    # the requirement is READ from PREREQS.json, not hard-wired: a stricter
    # file in OC_SKILLS_DIR must make 4.2.0 insufficient.
    mkdir -p "$T/strict/83-black-friday-launcher"
    sed 's/jsonschema>=4.0/jsonschema>=9.9/' "$PJ" > "$T/strict/83-black-friday-launcher/PREREQS.json"
    rc=0; out="$(OC_SKILLS_DIR="$T/strict" PIP_FIND_LINKS="$W_OK" oc_ensure_jsonschema --apply 2>&1)" || rc=$?
    if [ "$rc" -eq 2 ] && has "$out" 'jsonschema>=9.9' && has "$out" '4.2.0'; then ok "T3 requirement string is read from 83 PREREQS.json (>=9.9 not met by 4.2.0)"
    else bad "T3 spec-from-file control rc=$rc out=[$out]"; fi
    python3 -m pip uninstall -y jsonschema >/dev/null 2>&1 || true

    # the proof: apply -> `python3 -c 'import jsonschema'` exits 0
    rc=0; out="$(PIP_FIND_LINKS="$W_OK" oc_ensure_jsonschema --apply 2>&1)" || rc=$?
    if [ "$rc" -eq 0 ] && python3 -c 'import jsonschema'; then
      ok "T3 after --apply: rc=0 and python3 -c 'import jsonschema' exits 0"
    else bad "T3 apply rc=$rc out=[$out]"; fi
    # T5 control: the same real command flips from rc 2 to rc 0 on the real prerequisite state.
    rc=0; out="$(cd "$T" && env -u ONBOARDING_DIR -u FLEET_PREFLIGHT_BYPASS -u FLEET_STANDING_GATE_BYPASS \
        -u OPENCLAW_UPDATE_SKIP_SELF_SYNC -u OPENCLAW_RELEASE_PIN_MODE HOME="$T/home" OPENCLAW_UPDATE_LEASE="$T/upd.lock" \
        bash "$REPO/update-skills.sh" --check 2>&1)" || rc=$?
    if [ "$rc" -eq 0 ]; then ok "T5 control: update-skills.sh --check rc=0 once jsonschema>=4.0 is installed"
    else bad "T5 control: update-skills.sh --check after apply rc=$rc out=[$out]"; fi
    rc=0; out="$(oc_ensure_jsonschema --check 2>&1)" || rc=$?
    if [ "$rc" -eq 0 ]; then ok "T3 --check now reports satisfied (rc=0)"
    else bad "T3 --check after apply rc=$rc out=[$out]"; fi
  fi
fi

# ---- 4. CON-14: launch family is wave-gated with verify.sh, or exclusion is recorded
fam="78-signature-product-selection 79-signature-order-form 80-signature-upsell 81-signature-downsell 82-signature-thank-you 83-black-friday-launcher"
waves="$(bash -c 'source "$1" >/dev/null 2>&1; printf "%s %s %s %s %s %s" "$OC_WAVE1_SKILLS" "$OC_WAVE2_SKILLS" "$OC_WAVE3_SKILLS" "$OC_WAVE4_SKILLS" "$OC_WAVE5_SKILLS" "$OC_WAVE6_SKILLS"' _ "$LIB" 2>/dev/null)"
con14_ok() {   # con14_ok <waves-text> <lib-text>
  local s gated=0 missing_verify=0
  for s in $fam; do
    has " $1 " " $s " && { gated=$((gated+1)); [ -f "$REPO/$s/verify.sh" ] || missing_verify=$((missing_verify+1)); }
  done
  if [ "$gated" -eq 6 ] && [ "$missing_verify" -eq 0 ]; then return 0; fi          # all gated, all with verify.sh
  if [ "$gated" -eq 0 ] && has "$2" 'EXPLICIT EXCLUSION, CON-14' && has "$2" '72-motion-video-plus' \
     && has "$2" '83-black-friday-launcher'; then return 0; fi                      # recorded exclusion
  return 1
}
if con14_ok "$waves" "$LIBTXT"; then ok "T4 launch family 78-83 is wave-gated with verify.sh, or the exclusion is recorded"
else bad "T4 launch family 78-83 is neither gated with verify.sh nor explicitly excluded in lib-onboarding-state.sh"; fi
if con14_ok "$waves" "${LIBTXT//EXPLICIT EXCLUSION, CON-14/}"; then
  bad "T4 NON-DISCRIMINATING: passed with the exclusion record removed"
else ok "T4 detector discriminates (exclusion record removed from a copy is rejected)"; fi
for s in $fam; do
  has " $waves " " $s " && ok "T4 $s is in a wave" || true
done
if [ -d "$REPO/scripts" ] && [ -f "$REPO/scripts/qc-assert-wave-list-integrity.py" ]; then
  if python3 "$REPO/scripts/qc-assert-wave-list-integrity.py" >"$T/wave.out" 2>&1; then
    ok "T4b wave-list integrity gate still passes"
  else bad "T4b qc-assert-wave-list-integrity.py FAILED: $(tail -n 3 "$T/wave.out")"; fi
fi

echo ""
echo "  Result: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || { echo "  FAIL"; exit 1; }
echo "  OK"
exit 0

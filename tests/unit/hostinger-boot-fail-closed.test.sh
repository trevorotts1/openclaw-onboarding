#!/usr/bin/env bash
# hostinger-boot-fail-closed.test.sh -- the Hostinger wrapper boot patcher FAILS CLOSED.
#
# Trevor 2026-10-19 / docker-persistence.md D4: exit 0 means the approved per-wrapper
# profile was applied AND its postconditions verified on the text the box will boot,
# or a known-good copy whose RECORDED SHA-256 was proved was restored. Everything else
# - unknown profile, count mismatch, surviving postcondition, failed node --check, a
# fallback with no recorded or a wrong hash - exits non-zero so the boot stops instead
# of starting a gateway that dies on exit 78.
# Hermetic: no container, no network, no /data. Temp dirs only.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 9
REPO="$PWD"
HWP="$REPO/platform/vps/hostinger/hostinger-wrapper-patch.py"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   - %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL - %s\n' "$1"; }
TMP="$(mktemp -d "${TMPDIR:-/tmp}/hwp-fail-closed-XXXXXX")"; trap 'rm -rf "$TMP"' EXIT

if ! command -v node >/dev/null 2>&1; then
  echo "[hostinger-boot-fail-closed] node absent; the patcher verifies with node --check, nothing to test"
  exit 0
fi

# A synthetic "pristine" wrapper holding every fragment: 1-3 and 5-6 once, 4 twice.
mk_wrapper() { # $1 = path
  {
    printf 'const e={},r={},n={warn(){}},s=1,w=()=>1,d={writeFileSync(){}},q="q",t={};\n'
    printf 'c(e,"agents->list",[{id:"main",name:"main"}]);\n'
    printf 'c(e,"meta->lastTouchedAt",new Date().toISOString());\n'
    printf 'r.plugins.bundledDiscovery="compat";\n'
    printf 'if((!s||!w(s))&&(n.warn("No valid primary model found"))){};\n'
    printf 'if((!s||!w(s))&&(n.warn("No valid primary model found"))){};\n'
    printf 'd.writeFileSync(q,JSON.stringify(t,null,2));\n'
    printf 'e.gateway?.trustedProxies&&process.env.TRAEFIK_HOST&&delete e.gateway.trustedProxies;\n'
    printf 'function c(){}\n'
  } > "$1"
}
PROFILE='{"1":1,"2":1,"3":1,"4":2,"5":1,"6":1}'
run_hwp() { # env for one patcher run against $W
  env "$@" python3 -I "$HWP" >"$TMP/run.out" 2>&1
}

# ---------------------------------------------------------------- 1. approved profile applies
W="$TMP/w1.mjs"; mk_wrapper "$W"; mkdir -p "$TMP/t1"
cp "$W" "$TMP/pristine.mjs"
WRAPPER_PATH="$W" PATCH_LOG="$TMP/t1/p.log" PATCH_STATE="$TMP/t1/state" PATCH_PROFILE="$PROFILE" \
  python3 -I "$HWP" >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && ok "approved profile: exit 0" || bad "approved profile: rc=$rc ($(cat "$TMP/run.out" 2>/dev/null))"
[ "$(grep -c 'agents->list' "$W")" = 0 ] && [ "$(grep -c 'bundledDiscovery="compat"' "$W")" = 0 ] \
  && [ "$(grep -c 'writeFileSync(q' "$W")" = 0 ] && ok "approved profile: every fragment neutralised" \
  || bad "approved profile: a fragment survived"
node --check "$W" >/dev/null 2>&1 && ok "approved profile: patched wrapper passes node --check" || bad "approved profile: node --check failed"

# ---------------------------------------------------------------- 2. idempotent via the record
WRAPPER_PATH="$W" PATCH_LOG="$TMP/t1/p.log" PATCH_STATE="$TMP/t1/state" PATCH_PROFILE="$PROFILE" \
  python3 -I "$HWP" >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q 'already patched (postconditions verified)' "$TMP/t1/p.log" \
  && ok "idempotent: a second run accepts its own recorded output" || bad "idempotent: second run rc=$rc"

# ---------------------------------------------------------------- 3. count mismatch fails closed
W="$TMP/w3.mjs"; mk_wrapper "$W"
WRAPPER_PATH="$W" PATCH_LOG="$TMP/t3.log" PATCH_STATE="$TMP/s3" PATCH_PROFILE='{"1":1,"2":1,"3":1,"4":1,"5":1,"6":1}' \
  python3 -I "$HWP" >/dev/null 2>&1; rc=$?
[ "$rc" != 0 ] && grep -q 'fragment 4: found x2, expected x1' "$TMP/t3.log" \
  && cmp -s "$W" "$TMP/pristine.mjs" && ok "count mismatch: exit non-zero and the wrapper is untouched" \
  || bad "count mismatch: rc=$rc or the wrapper was written"

# ---------------------------------------------------------------- 4. unknown profile fails closed
W="$TMP/w4.mjs"; printf 'const x=1;\n' > "$W"
WRAPPER_PATH="$W" PATCH_LOG="$TMP/t4.log" PATCH_STATE="$TMP/s4" python3 -I "$HWP" >/dev/null 2>&1; rc=$?
[ "$rc" != 0 ] && grep -q 'unknown wrapper profile' "$TMP/t4.log" \
  && ok "unknown profile: exit non-zero, no counts assumed" || bad "unknown profile: rc=$rc"
grep -q 'FAILED: .*refusing to start\|no verified safe result' "$TMP/t4.log" \
  && ok "unknown profile: logs that it refuses to start" || bad "unknown profile: silent"

# ---------------------------------------------------------------- 5. digest-bound fallback: WRONG hash
W="$TMP/w5.mjs"; mk_wrapper "$W"
GOOD="$TMP/good5.mjs"; cp "$TMP/pristine.mjs" "$GOOD"; printf '\n/*marked*/\n' > /dev/null
printf 'const ok=1;\n' > "$GOOD"
WRAPPER_PATH="$W" PATCH_LOG="$TMP/t5.log" PATCH_STATE="$TMP/s5" \
  WRAPPER_KNOWN_GOOD="$GOOD" KNOWN_GOOD_SHA256="$(printf 'deadbeef%.0s' 1 2 3 4 5 6 7 8)" \
  python3 -I "$HWP" >/dev/null 2>&1; rc=$?
[ "$rc" != 0 ] && grep -q 'SHA-256 mismatch' "$TMP/t5.log" && ok "fallback: a wrong recorded SHA-256 is refused" || bad "fallback: wrong hash was restored (rc=$rc)"
cmp -s "$W" "$TMP/pristine.mjs" && ok "fallback: the wrapper is not overwritten by an unproved copy" || bad "fallback: wrapper was overwritten"

# ---------------------------------------------------------------- 6. digest-bound fallback: NO hash
W="$TMP/w6.mjs"; mk_wrapper "$W"
WRAPPER_PATH="$W" PATCH_LOG="$TMP/t6.log" PATCH_STATE="$TMP/s6" WRAPPER_KNOWN_GOOD="$GOOD" \
  python3 -I "$HWP" >/dev/null 2>&1; rc=$?
[ "$rc" != 0 ] && grep -q 'no KNOWN_GOOD_SHA256 recorded' "$TMP/t6.log" \
  && ok "fallback: no recorded SHA-256 means no restore and a non-zero exit" || bad "fallback: restored without a recorded hash (rc=$rc)"

# ---------------------------------------------------------------- 7. digest-bound fallback: PROVED
# An unknown wrapper plus a fallback whose recorded SHA-256 matches and which satisfies the
# postconditions: the boot is allowed because the text it will boot IS verified safe.
W="$TMP/w7.mjs"; printf 'const broken=1;\n' > "$W"
GOOD7="$TMP/good7.mjs"; cat "$TMP/w1.mjs" > "$GOOD7"   # the verified-patched text from case 1
SHA7="$(python3 -I -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$GOOD7")"
WRAPPER_PATH="$W" PATCH_LOG="$TMP/t7.log" PATCH_STATE="$TMP/s7" \
  WRAPPER_KNOWN_GOOD="$GOOD7" KNOWN_GOOD_SHA256="$SHA7" python3 -I "$HWP" >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q 'RESTORED digest-bound known-good wrapper' "$TMP/t7.log" \
  && cmp -s "$W" "$GOOD7" && ok "fallback: a proved compatible known-good is restored and the boot is allowed" \
  || bad "fallback: proved fallback not restored (rc=$rc)"

# ---------------------------------------------------------------- 8. proved hash, unsafe content
# Same hash proof but the fallback still carries a harmful fragment: never booted.
W="$TMP/w8.mjs"; printf 'const broken=1;\n' > "$W"
GOOD8="$TMP/good8.mjs"; mk_wrapper "$GOOD8"
SHA8="$(python3 -I -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$GOOD8")"
WRAPPER_PATH="$W" PATCH_LOG="$TMP/t8.log" PATCH_STATE="$TMP/s8" \
  WRAPPER_KNOWN_GOOD="$GOOD8" KNOWN_GOOD_SHA256="$SHA8" python3 -I "$HWP" >/dev/null 2>&1; rc=$?
[ "$rc" != 0 ] && grep -q 'known-good copy fails postconditions' "$TMP/t8.log" \
  && ok "fallback: a hash-proved but still-unpatched copy is refused" || bad "fallback: unpatched copy accepted (rc=$rc)"

# ---------------------------------------------------------------- 9. wiring is not fail-soft
CS="$REPO/platform/vps/hostinger/container-startup.sh"
# The invocation itself must be guarded, so its status is never discarded. (The
# diagnostic `echo` further down carries its own `|| true`; that only swallows the
# echo, never the patcher.)
if grep -q 'if ! python3 "\$HWP"' "$CS"; then
  ok "wiring: the patcher invocation is status-guarded, not fail-soft"
else
  bad "wiring: container-startup.sh swallows the patcher's exit status"
fi
grep -q 'exit 1' "$CS" && grep -q 'STOPPED: wrapper patcher failed' "$CS" \
  && ok "wiring: a failed patch stops the boot" || bad "wiring: no stop-on-failure path"

printf '[hostinger-boot-fail-closed] %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]

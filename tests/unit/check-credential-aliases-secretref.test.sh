#!/usr/bin/env bash
# check-credential-aliases-secretref.test.sh — credential alias families,
# hermetic OC_CONFIG_FILE, SecretRef-object apiKey, 9ROUTER_API_KEY safety.
#
#  1. key_resolver: xiaomi / mimo / 9router / ninerouter shorthands resolve
#     through the secret_names.json canon (incl. a 9ROUTER_API_KEY-only store).
#  2. check-credential.sh with OC_CONFIG_FILE set scans ONLY that file: a
#     matching provider block in $HOME/.openclaw/openclaw.json must not flip
#     NEEDS_BLOCK to PRESENT_WITH_BLOCK (provider mode, --self-test, and the
#     bash legacy key mode). Control: without OC_CONFIG_FILE the HOME config
#     is still read (production behavior unchanged).
#  3. apiKey {"id": "AGNES_AI_API_KEY"} (SecretRef object) -> PRESENT_WITH_BLOCK,
#     no auth warning when auth:"api-key" is set; the gate still fires without it.
#  4. 9ROUTER_API_KEY (not a valid shell name) causes no bash error.
#
# Every run uses a temp HOME; the machine's real secret stores are never read.
set -uo pipefail
P="[cc-aliases]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CC="${CC_SCRIPT:-$ROOT/shared-utils/check-credential.sh}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
H="$TMP/home"; mkdir -p "$H/.openclaw/secrets"
FAKE="crfk-7Qm2Zp9Lx4Vb8Nw3Rt6Yh1Jd5Kc0"   # shape-valid, not a real key

field() { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],'?'))" "$1" "$2" 2>/dev/null || echo PARSE_ERROR; }
ccp() {  # ccp <out-prefix> <cfg> <store> <provider>
  env HOME="$H" OC_CONFIG_FILE="$2" _SELFTEST_INJECT_ENV_STORE="$3" \
    bash "$CC" --provider "$4" --json >"$1.out" 2>"$1.err"; echo $? >"$1.rc"
}

# ── 1. key_resolver shorthands ────────────────────────────────────────────────
printf '9ROUTER_API_KEY=%s\nMIMO_API_KEY=%s\n' "$FAKE" "$FAKE" > "$H/.openclaw/secrets/.env"
if out="$(env -i HOME="$H" PATH="$PATH" python3 - "$ROOT/shared-utils" <<'PY' 2>&1
import sys; sys.path.insert(0, sys.argv[1])
import key_resolver as k
nine = ["NINEROUTER_API_KEY", "NINE_ROUTER_API_KEY", "ROUTER_API_KEY", "9ROUTER_API_KEY"]
for s in ("9router", "ninerouter"):
    assert k.SERVICE_ALIASES[s] == nine, (s, k.SERVICE_ALIASES.get(s))
for s in ("xiaomi", "mimo"):
    assert set(k.SERVICE_ALIASES[s]) == {"XIAOMI_API_KEY", "MIMO_API_KEY"}, (s, k.SERVICE_ALIASES.get(s))
assert k.SERVICE_ALIASES["xiaomi"][0] == "XIAOMI_API_KEY"
assert k.resolve_key("9router"), "9router did not resolve from a 9ROUTER_API_KEY-only store"
assert k.resolve_key("ninerouter") and k.resolve_key("xiaomi") and k.resolve_key("mimo")
print("ok")
PY
)"; [[ "$out" == ok ]]; then pass "key_resolver: xiaomi/mimo/9router/ninerouter resolve via canon"
else fail "key_resolver shorthands: $out"; fi
rm -f "$H/.openclaw/secrets/.env"

# ── 2. hermetic OC_CONFIG_FILE ────────────────────────────────────────────────
STORE="$TMP/store.env"; echo "OPENROUTER_API_KEY=$FAKE" > "$STORE"
echo '{"models":{"providers":{"openrouter":{"auth":"api-key","apiKey":"$OPENROUTER_API_KEY"}}},"env":{"vars":{"CRF_HERMETIC_PROBE_KEY":"x"}}}' \
  > "$H/.openclaw/openclaw.json"
EMPTY="$TMP/empty.json"; echo '{"models":{"providers":{}}}' > "$EMPTY"

ccp "$TMP/h" "$EMPTY" "$STORE" openrouter
v="$(field "$TMP/h.out" verdict)"; rc="$(cat "$TMP/h.rc")"
[[ "$v" == NEEDS_BLOCK && "$rc" == 3 ]] && pass "provider mode ignores HOME openclaw.json when OC_CONFIG_FILE is set" \
  || fail "provider mode hermeticity: verdict=$v rc=$rc (HOME config leaked)"

ccp "$TMP/c" "" "$STORE" openrouter
v="$(field "$TMP/c.out" verdict)"
[[ "$v" == PRESENT_WITH_BLOCK ]] && pass "control: without OC_CONFIG_FILE the HOME openclaw.json is still scanned" \
  || fail "control (no OC_CONFIG_FILE): verdict=$v, expected PRESENT_WITH_BLOCK"

st="$(env HOME="$H" bash "$CC" --self-test 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && pass "--self-test passes with a matching block in HOME openclaw.json" \
  || fail "--self-test rc=$rc with HOME config present: $(grep FAIL <<<"$st")"

env HOME="$H" OC_CONFIG_FILE="$EMPTY" bash "$CC" CRF_HERMETIC_PROBE_KEY --quiet >/dev/null 2>&1; rc=$?
env HOME="$H" bash "$CC" CRF_HERMETIC_PROBE_KEY --quiet >/dev/null 2>&1; rc_ctl=$?
[[ $rc -eq 1 && $rc_ctl -eq 0 ]] && pass "key mode: OC_CONFIG_FILE excludes HOME env.vars (control finds it)" \
  || fail "key mode hermeticity: with OC_CONFIG_FILE rc=$rc (want 1), control rc=$rc_ctl (want 0)"
rm -f "$H/.openclaw/openclaw.json"

# ── 3. SecretRef object apiKey ────────────────────────────────────────────────
echo "AGNES_AI_API_KEY=$FAKE" > "$STORE"
REF="$TMP/ref.json"
echo '{"models":{"providers":{"agnes":{"auth":"api-key","apiKey":{"source":"env","provider":"default","id":"AGNES_AI_API_KEY"}}}}}' > "$REF"
ccp "$TMP/r" "$REF" "$STORE" agnes
v="$(field "$TMP/r.out" verdict)"; rc="$(cat "$TMP/r.rc")"
if [[ "$v" == PRESENT_WITH_BLOCK && "$rc" == 0 ]] && ! grep -q WARNING "$TMP/r.err" \
   && [[ "$(field "$TMP/r.out" auth_gate_missing)" == False ]]; then
  pass "apiKey {\"id\":\"AGNES_AI_API_KEY\"} -> PRESENT_WITH_BLOCK, no auth warning"
else fail "SecretRef apiKey: verdict=$v rc=$rc stderr=$(cat "$TMP/r.err")"; fi
grep -q "$FAKE" "$TMP/r.out" "$TMP/r.err" && fail "SecretRef run printed a credential value" \
  || pass "SecretRef run prints no credential value"

echo '{"models":{"providers":{"agnes":{"apiKey":{"id":"AGNES_AI_API_KEY"}}}}}' > "$REF"
ccp "$TMP/g" "$REF" "$STORE" agnes
v="$(field "$TMP/g.out" verdict)"
[[ "$v" == PRESENT_WITH_BLOCK ]] && grep -q 'auth:"api-key"' "$TMP/g.err" \
  && pass "auth-gate warning unchanged: SecretRef block without auth still warns" \
  || fail "auth gate: verdict=$v stderr=$(cat "$TMP/g.err")"

# ── 4. 9ROUTER_API_KEY never breaks bash ──────────────────────────────────────
echo "9ROUTER_API_KEY=$FAKE" > "$STORE"
ccp "$TMP/n" "$EMPTY" "$STORE" 9router
v="$(field "$TMP/n.out" verdict)"; rc="$(cat "$TMP/n.rc")"
[[ "$v" == NEEDS_BLOCK && "$rc" == 3 ]] && ! grep -qiE 'bad substitution|not a valid identifier|syntax error|Traceback' "$TMP/n.err" \
  && pass "--provider 9router finds a 9ROUTER_API_KEY-only store, no bash error" \
  || fail "9router provider: verdict=$v rc=$rc stderr=$(cat "$TMP/n.err")"
grep -q suggested_block "$TMP/n.out" && fail "9router got a suggested provider block (must have none)" \
  || pass "no 9router block template is suggested"

echo "9ROUTER_API_KEY=$FAKE" > "$H/.openclaw/secrets/.env"
env HOME="$H" OC_CONFIG_FILE="$EMPTY" bash "$CC" 9ROUTER_API_KEY --json >"$TMP/k.out" 2>"$TMP/k.err"; rc=$?
[[ $rc -eq 0 ]] && ! grep -qiE 'bad substitution|not a valid identifier|syntax error' "$TMP/k.err" \
  && pass "key mode: 9ROUTER_API_KEY found, no bash error" \
  || fail "key mode 9ROUTER_API_KEY: rc=$rc stderr=$(cat "$TMP/k.err")"

echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]

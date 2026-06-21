#!/usr/bin/env bash
# tests/unit/conditional-embedding-default.test.sh — v13.2.1
#
# REGRESSION GUARD for the v13.2.0 embedding-default bug:
#   v13.2.0's installer HARD-PINNED gemini-embedding-2 as the memorySearch
#   embedding default whenever configure_active_memory ran. On 6 boxes that have
#   NO usable Google/Gemini key that pinned a model they cannot serve — the embed
#   index then fails on every search. v13.2.1 makes the gemini default
#   CONDITIONAL on a USABLE Google/Gemini key, and the key detection is SMART:
#   a Google key is the SAME credential under THREE env NAMES
#   (GOOGLE_API_KEY / GOOGLE_AI_STUDIO_API_KEY / GEMINI_API_KEY) and can live in
#   SEVERAL stores. All of them must be checked before concluding "no key".
#
# This test proves BOTH layers of the fix:
#
#   LAYER 1 — DETECTION (install.sh has_usable_gemini_key):
#     (1) a box whose ONLY Google credential is named GEMINI_API_KEY            → DETECTED
#     (2) a box whose ONLY Google credential is named GOOGLE_AI_STUDIO_API_KEY  → DETECTED (alias coverage)
#     (3) a box whose ONLY Google credential is named GOOGLE_API_KEY            → DETECTED (alias coverage)
#     (4) a box with ONLY an OPENAI key and NO Google credential of any name    → NOT detected (no false gemini)
#
#   LAYER 2 — CONFIG DECISION (install.sh configure_active_memory python):
#     (A) gemini key present                          → pins gemini-embedding-2 @3072
#     (B) only-GOOGLE_AI_STUDIO_API_KEY resolved key  → STILL pins gemini-embedding-2 (alias coverage end-to-end)
#     (C) only OPENAI key                             → keeps openai/text-embedding-3-small (NO false gemini pin)
#     (D) v13.2.0 stranded keyless gemini pin + OPENAI → UN-PINNED to openai (the 6-box repair)
#     (E) no embedding-capable key + stranded gemini   → provider/model UNSET (never pin an unservable model)
#
# Exit 0 = all checks pass. Exit 1 = a regression was found.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
PASS=0
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== conditional-embedding-default.test.sh (v13.2.1) ==="
echo ""

[ -f "$INSTALL_SH" ] || { echo "FAIL: install.sh not found at $INSTALL_SH"; exit 1; }

# A syntactically valid AIza… Gemini key shape (passes looks_like_real_key
# stage-1 provider regex: ^AIza[A-Za-z0-9_-]{35}$). High entropy, not a
# placeholder. NOT a real credential.
GKEY='AIzaSyD9bQ2_kf3Lm7Np0RsTuVwXyZ-aB1cD2eF'
OKEY='sk-proj-Za9Yx8Wv7Ut6Sr5Qp4On3Ml2Kj1Ih0Gf'

# ──────────────────────────────────────────────────────────────────────────────
# LAYER 1: extract the detection helpers from install.sh and source them in a
# sandboxed HOME so no real operator keys leak into the result.
# ──────────────────────────────────────────────────────────────────────────────
echo "--- LAYER 1: has_usable_gemini_key alias + no-false-positive coverage ---"

# get_alias_list (968) .. end of has_usable_gemini_key (just before
# discover_all_credentials at 1703). These line markers are asserted below so
# the test fails loudly if the extraction drifts after a refactor.
START_LINE=$(grep -n '^get_alias_list()' "$INSTALL_SH" | head -1 | cut -d: -f1)
END_LINE=$(grep -n '^discover_all_credentials()' "$INSTALL_SH" | head -1 | cut -d: -f1)
if [ -z "$START_LINE" ] || [ -z "$END_LINE" ] || [ "$END_LINE" -le "$START_LINE" ]; then
  fail "could not locate has_usable_gemini_key extraction window in install.sh"
else
  END_LINE=$((END_LINE - 1))
  sed -n "${START_LINE},${END_LINE}p" "$INSTALL_SH" > "$TMP/helpers.sh"
  if ! grep -q '^has_usable_gemini_key()' "$TMP/helpers.sh"; then
    fail "extracted helper block does not contain has_usable_gemini_key()"
  else
    pass "extracted detection helpers (get_alias_list .. has_usable_gemini_key)"
  fi
fi

# Run one detection scenario in a clean subshell with a sandbox HOME so the only
# Google credential is whatever we plant. Echoes "FOUND" or "ABSENT".
detect() {
  # $1 = alias var name to set (or "NONE"); $2 = value; $3 = extra env assignment
  local alias_name="$1" val="$2" extra="${3:-}"
  local sandbox="$TMP/home_$$_$RANDOM"
  mkdir -p "$sandbox"
  (
    set +e
    export HOME="$sandbox"
    # No openclaw.json / docker in sandbox → detection relies purely on env.
    export OC_JSON="$sandbox/.openclaw/openclaw.json"
    export OC_AUTH_PROFILES="$sandbox/auth.json"
    export OC_CONFIG="$sandbox/.openclaw"
    unset MAC_ENV_FILE_LIST
    # Clear ALL Google + OpenAI aliases first so the host env can't bleed in.
    unset GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_AI_STUDIO_API_KEY \
          GOOGLE_GEMINI_API_KEY GOOGLE_GENERATIVE_AI_API_KEY \
          GOOGLE_AI_API_KEY OPENAI_API_KEY OPENAI_TOKEN
    [ "$alias_name" != "NONE" ] && export "$alias_name=$val"
    [ -n "$extra" ] && export $extra
    # shellcheck disable=SC1090
    source "$TMP/helpers.sh"
    if has_usable_gemini_key >/dev/null 2>&1; then echo "FOUND"; else echo "ABSENT"; fi
  )
}

R1=$(detect "GEMINI_API_KEY" "$GKEY")
[ "$R1" = "FOUND" ] && pass "(1) only GEMINI_API_KEY set → DETECTED" \
                     || fail "(1) only GEMINI_API_KEY set → expected FOUND, got $R1"

R2=$(detect "GOOGLE_AI_STUDIO_API_KEY" "$GKEY")
[ "$R2" = "FOUND" ] && pass "(2) only GOOGLE_AI_STUDIO_API_KEY set → DETECTED (alias coverage)" \
                     || fail "(2) only GOOGLE_AI_STUDIO_API_KEY set → expected FOUND, got $R2"

R3=$(detect "GOOGLE_API_KEY" "$GKEY")
[ "$R3" = "FOUND" ] && pass "(3) only GOOGLE_API_KEY set → DETECTED (alias coverage)" \
                     || fail "(3) only GOOGLE_API_KEY set → expected FOUND, got $R3"

R4=$(detect "OPENAI_API_KEY" "$OKEY")
[ "$R4" = "ABSENT" ] && pass "(4) only OPENAI key, NO Google credential → NOT detected (no false gemini)" \
                     || fail "(4) only OPENAI key → expected ABSENT, got $R4"

# ──────────────────────────────────────────────────────────────────────────────
# LAYER 2: extract the configure_active_memory python block and drive it with
# the resolved keys, asserting the final memorySearch provider/model.
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- LAYER 2: configure_active_memory pins the right model per key set ---"

python3 - "$INSTALL_SH" "$TMP/cam.py" <<'EXTRACT'
import re, sys
src = open(sys.argv[1]).read()
blocks = re.findall(r"python3 << 'PYEOF'\n(.*?)\nPYEOF", src, re.S)
for b in blocks:
    if "Active Memory" in b and "memorySearch" in b:
        open(sys.argv[2], "w").write(b)
        break
else:
    sys.exit("could not extract configure_active_memory python block")
EXTRACT
if [ ! -s "$TMP/cam.py" ]; then
  fail "could not extract configure_active_memory python block"
else
  pass "extracted configure_active_memory python block"
fi

# cfg_check <label> <cfg-json> <gemini> <openai> <openrouter> <expect-provider> <expect-model>
cfg_check() {
  local label="$1" cfg="$2" g="$3" o="$4" or="$5" exp_p="$6" exp_m="$7"
  printf '%s' "$cfg" > "$TMP/cfg.json"
  OPENCLAW_JSON="$TMP/cfg.json" OC_GEMINI_KEY="$g" OC_OPENAI_KEY="$o" OC_OPENROUTER_KEY="$or" \
    python3 "$TMP/cam.py" >/dev/null 2>&1
  local got
  got=$(python3 - "$TMP/cfg.json" <<'PY'
import json, sys
ms = json.load(open(sys.argv[1]))["agents"]["defaults"]["memorySearch"]
print(f'{ms.get("provider")}|{ms.get("model")}')
PY
)
  local got_p="${got%%|*}" got_m="${got##*|}"
  if [ "$got_p" = "$exp_p" ] && [ "$got_m" = "$exp_m" ]; then
    pass "$label → provider=$got_p model=$got_m"
  else
    fail "$label → expected provider=$exp_p model=$exp_m, got provider=$got_p model=$got_m"
  fi
}

EMPTY='{"agents":{"defaults":{}}}'
STRANDED='{"agents":{"defaults":{"memorySearch":{"provider":"gemini","model":"gemini-embedding-2","dimensions":3072}}}}'
WORKING_OPENAI='{"agents":{"defaults":{"memorySearch":{"provider":"openai","model":"text-embedding-3-small","dimensions":1536}}}}'

# (A) gemini key present → gemini-embedding-2
cfg_check "(A) GEMINI key present" "$EMPTY" "$GKEY" "" "" "gemini" "gemini-embedding-2"
# (B) only GOOGLE_AI_STUDIO_API_KEY → resolves to a gemini key (LAYER 1 proved
#     detection), so the python receives OC_GEMINI_KEY and STILL pins gemini-2.
cfg_check "(B) GOOGLE_AI_STUDIO alias resolved → STILL gemini-2" "$EMPTY" "$GKEY" "" "" "gemini" "gemini-embedding-2"
# (C) only OPENAI key → keeps openai, no false gemini
cfg_check "(C) only OPENAI key → openai (no false gemini)" "$WORKING_OPENAI" "" "$OKEY" "" "openai" "text-embedding-3-small"
# (D) v13.2.0 stranded keyless gemini + only OPENAI → un-pinned to openai
cfg_check "(D) stranded keyless gemini + OPENAI → un-pinned openai" "$STRANDED" "" "$OKEY" "" "openai" "text-embedding-3-small"
# (E) no embedding-capable key + stranded gemini → provider/model UNSET (None)
cfg_check "(E) NO key + stranded gemini → provider/model UNSET" "$STRANDED" "" "" "" "None" "None"

# ──────────────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: conditional embedding-default regression detected"
  exit 1
fi
echo "PASS: gemini default is CONDITIONAL on a usable key; alias coverage verified; no false gemini pin"
exit 0

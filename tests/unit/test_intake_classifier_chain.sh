#!/usr/bin/env bash
# tests/unit/test_intake_classifier_chain.sh
#
# v25.2.23 order item A: the intake classifier chain resolver.
# Drives the REAL scripts/intake-classifier-chain.sh end-to-end against
# hermetic fixture roots (throwaway HOME + one fake key value per case). No
# network, no live model call, no real box state, no paid call.
#
# WHAT IS PROVEN
#   T1  IDEMPOTENT — two runs print byte-identical output (also on a box-main box).
#   T2  missing key on a CONFIGURED box SKIPS the step (never errors): exit 0,
#       one stdout line, REASON=missing-key, and the lower configured step or
#       box-main is chosen.
#   T3  box with NONE of the three reports `CHAIN_STEP=box-main`.
#   T4  precedence: OpenRouter first; otherwise configured Ollama; otherwise
#       configured Agnes; the GATE is real (an unconfigured provider's key is
#       ignored), and the alias chains resolve (OR_API_KEY / OLLAMA_CLOUD_API_KEY /
#       AGNES_KEY).
#   T5  NO KEY VALUE FROM ANY FIXTURE EVER APPEARS IN THE OUTPUT — asserted on
#       the output strings of every case, including the any-case combined check.
#   T6  the resolver carries the SAME six env stores as scripts/mc-route.sh
#       (_ENV_STORES), so the chain can never diverge from the store list the
#       routing helper already trusts.
#   T7  the policy artifact shared-utils/intake_classifier_policy.txt equals the
#       V4.3 POLICY constant of shared-utils/ceo_execution_policy.py verbatim,
#       plus the owner-message placeholder block only.
#
# FAIL-FIRST: this suite is new with the resolver; against the base tree the
# script does not exist and the policy artifact is absent, so both core blocks
# go red.

set -uo pipefail

PASS=0
FAIL=0
ERRORS=()

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHAIN="$REPO_ROOT/scripts/intake-classifier-chain.sh"
MC_ROUTE="$REPO_ROOT/scripts/mc-route.sh"
POLICY_TXT="$REPO_ROOT/shared-utils/intake_classifier_policy.txt"
POLICY_PY="$REPO_ROOT/shared-utils/ceo_execution_policy.py"

echo ""
echo "=== intake classifier chain resolver (v25.2.23 item A) ==="
echo ""

[ -f "$CHAIN" ] || { echo "  FAIL: scripts/intake-classifier-chain.sh not found"; exit 1; }
[ -f "$MC_ROUTE" ] || { echo "  FAIL: scripts/mc-route.sh not found"; exit 1; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/intake-chain-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# Fixture secret values are deliberately distinctive: T5 greps every case's
# output for each of them, so a leak is loud and unambiguous.
V_OPENROUTER="fixture-openrouter-9f13c2"
V_OLLAMA="fixture-ollama-7b40dd"
V_AGNES="fixture-agnes-5ac821"

# ── Fixture builders ─────────────────────────────────────────────────────────
# make_box <dir> <providers-json-or-empty> ; store/env files are layered after.
make_box() {
  local dir="$1" providers="${2:-}"
  mkdir -p "$dir/.openclaw/secrets"
  if [ -n "$providers" ]; then
    printf '{"models":{"providers":%s}}\n' "$providers" > "$dir/.openclaw/openclaw.json"
  else
    printf '{"models":{"providers":{}}}\n' > "$dir/.openclaw/openclaw.json"
  fi
}

run_chain() {  # $1 = HOME dir. Writes stdout to $WORK/out.txt; sets STATUS.
  env -i HOME="$1" PATH=/usr/bin:/bin WORKFORCE_PYTHON="${WORKFORCE_PYTHON:-python3}" \
    bash "$CHAIN" >"$WORK/out.txt" 2>>"$WORK/stderr-all.txt"
  STATUS=$?
}
: > "$WORK/stderr-all.txt"

one_line_only() {  # $1 = output. True when exactly one non-empty line.
  [ "$(printf '%s\n' "$1" | grep -c .)" -eq 1 ]
}

# ── Cases ────────────────────────────────────────────────────────────────────
P_OLLAMA='{"ollama":{"baseUrl":"https://ollama.com/v1"}}'
P_AGNES='{"agnes":{"baseUrl":"https://apihub.agnes-ai.com/v1"}}'
P_BOTH="{\"ollama\":{\"baseUrl\":\"https://ollama.com/v1\"},\"agnes\":{\"baseUrl\":\"https://apihub.agnes-ai.com/v1\"}}"

CASES=(

  # name | providers | env-file content | expected stdout
  "or_wins_over_everything|$P_BOTH|OPENROUTER_API_KEY=$V_OPENROUTER|CHAIN_STEP=openrouter-gpt-6-luna REASON=available"
  "or_alias_resolves||OR_API_KEY=$V_OPENROUTER|CHAIN_STEP=openrouter-gpt-6-luna REASON=available"
  "ollama_configured_key_present|$P_OLLAMA|OLLAMA_API_KEY=$V_OLLAMA|CHAIN_STEP=ollama-minimax-3 REASON=available"
  "ollama_alias_resolves|$P_OLLAMA|OLLAMA_CLOUD_API_KEY=$V_OLLAMA|CHAIN_STEP=ollama-minimax-3 REASON=available"
  "ollama_configured_key_missing|$P_OLLAMA||CHAIN_STEP=box-main REASON=missing-key"
  "ollama_unconfigured_key_ignored||OLLAMA_API_KEY=$V_OLLAMA|CHAIN_STEP=box-main REASON=no-provider"
  "agnes_configured_key_present|$P_AGNES|AGNES_API_KEY=$V_AGNES|CHAIN_STEP=agnes-3-0-flash REASON=available"
  "agnes_alias_resolves|$P_AGNES|AGNES_KEY=$V_AGNES|CHAIN_STEP=agnes-3-0-flash REASON=available"
  "agnes_configured_key_missing|$P_AGNES||CHAIN_STEP=box-main REASON=missing-key"
  "none_configured_reports_box_main|||CHAIN_STEP=box-main REASON=no-provider"
  "ollama_missing_key_falls_to_configured_agnes|$P_BOTH|AGNES_API_KEY=$V_AGNES|CHAIN_STEP=agnes-3-0-flash REASON=available"
)

ALL_OUTPUT=""
case_no=0
for case in "${CASES[@]}"; do
  IFS='|' read -r name providers envline expected <<<"$case"
  case_no=$((case_no + 1))
  home="$WORK/case$case_no"
  make_box "$home" "$providers"
  if [ -n "$envline" ]; then printf '%s\n' "$envline" > "$home/.openclaw/secrets/.env"; fi

  run_chain "$home"
  out="$(cat "$WORK/out.txt")"
  rc="$STATUS"
  ALL_OUTPUT="$ALL_OUTPUT
$out"

  if [ "$rc" -ne 0 ]; then
    fail "$name: exit $rc (a missing key must SKIP, never error); stderr: $(head -1 "$WORK/stderr-all.txt")"
    continue
  fi
  if [ "$out" = "$expected" ] && one_line_only "$out"; then
    ok "$name -> $out (exit 0)"
  else
    fail "$name: got '$out', expected '$expected' (one line, exit 0)"
  fi

  # T1 — idempotence: an immediate second run is byte-identical (same HOME, so
  # it also covers a store already present).
  run_chain "$home"
  out2="$(cat "$WORK/out.txt")"
  if [ "$out2" = "$out" ] && [ "$STATUS" -eq 0 ]; then
    ok "$name: idempotent across two runs"
  else
    fail "$name: second run drifted ('$out2' vs '$out', exit $STATUS)"
  fi
done

# T5 — no fixture key value in ANY output collected above, nor on stderr.
for label in "openrouter:$V_OPENROUTER" "ollama:$V_OLLAMA" "agnes:$V_AGNES"; do
  what="${label%%:*}"; val="${label#*:}"
  if printf '%s' "$ALL_OUTPUT" | grep -q -- "$val"; then
    fail "T5: the $what fixture key VALUE leaked into stdout"
  else
    ok "T5: no $what fixture key value in stdout"
  fi
  if grep -q -- "$val" "$WORK/stderr-all.txt" 2>/dev/null; then
    fail "T5: the $what fixture key VALUE leaked into stderr"
  else
    ok "T5: no $what fixture key value on stderr"
  fi
done

# T6 — the resolver carries the SAME six stores as mc-route.sh (_ENV_STORES).
stores_of() {  # $1 = file. Prints the six store paths, one per line.
  python3 - "$1" <<'PYSTORES'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"_ENV_STORES=\(\n(.*?)\n\)", text, re.S)
if not m:
    sys.exit(1)
for line in m.group(1).splitlines():
    line = line.strip()
    if line.startswith('"') and line.endswith('"'):
        print(line.strip('"'))
PYSTORES
}
if stores_of "$CHAIN" > "$WORK/chain-stores.txt" && stores_of "$MC_ROUTE" > "$WORK/mcroute-stores.txt"; then
  if cmp -s "$WORK/chain-stores.txt" "$WORK/mcroute-stores.txt" && [ "$(grep -c . "$WORK/chain-stores.txt")" -eq 6 ]; then
    ok "T6: resolver _ENV_STORES is byte-identical to mc-route.sh (6 stores)"
  else
    fail "T6: _ENV_STORES drifted from mc-route.sh: $(diff "$WORK/chain-stores.txt" "$WORK/mcroute-stores.txt" | head -4)"
  fi
else
  fail "T6: could not extract _ENV_STORES from one of the files"
fi

# T7 — policy artifact == V4.3 POLICY verbatim + placeholder block only.
if [ -f "$POLICY_TXT" ]; then
  python3 - "$POLICY_PY" "$POLICY_TXT" <<'PYPOLICY'
import sys
root = __import__("pathlib").Path(sys.argv[1]).resolve().parents[1]
sys.path.insert(0, str(root / "shared-utils"))
from ceo_execution_policy import POLICY
text = open(sys.argv[2], encoding="utf-8").read()
tail = (
    "---\n"
    "OWNER MESSAGE (the message the owner just sent; verbatim, nothing else is added):\n"
    "{{OWNER_MESSAGE}}\n"
)
assert text == POLICY + tail, "policy artifact is not POLICY verbatim + placeholder tail"
print("ok")
PYPOLICY
  if [ $? -eq 0 ]; then
    ok "T7: intake_classifier_policy.txt == V4.3 POLICY verbatim + owner-message placeholder"
  else
    fail "T7: policy artifact drifted from shared-utils/ceo_execution_policy.py POLICY"
  fi
else
  fail "T7: shared-utils/intake_classifier_policy.txt not found"
fi

echo ""
echo "=== $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Failures:"
  for e in "${ERRORS[@]}"; do echo "  - $e"; done
  exit 1
fi
exit 0

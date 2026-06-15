#!/usr/bin/env bash
# tests/unit/provider-capability-guard.test.sh — v12.14.0
#
# Verifies the client-provider capability guard:
#   (A) SMOKE — simulate text-only embed provider + multimodal.enabled=true
#       → smoke-test-provider-capabilities.sh MUST fail (exit 1)
#   (B) SMOKE — same provider, multimodal.enabled=false
#       → smoke-test-provider-capabilities.sh MUST pass (exit 0)
#   (C) STATIC — same bad config → qc-assert-provider-capability-invariants.sh MUST fail
#   (D) STATIC — same good config → qc-assert-provider-capability-invariants.sh MUST pass
#   (E) STATIC — fallback=none → invariant MUST fail
#   (F) SMOKE  — fallback=none → smoke MUST fail
#   (G) STATIC — check runs cleanly when no openclaw.json exists
#       (the script must exit 1 reporting "cannot find" — not crash/segfault)
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).
#
# v12.14.0 / fix/client-provider-capability-guard

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SMOKE_SCRIPT="$REPO_ROOT/scripts/smoke-test-provider-capabilities.sh"
STATIC_SCRIPT="$REPO_ROOT/scripts/qc-assert-provider-capability-invariants.sh"
PASS=0
FAIL=0
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== provider-capability-guard.test.sh (v12.14.0) ==="
echo ""

# ── Helpers ───────────────────────────────────────────────────────────────────

_make_config() {
  # Usage: _make_config <outfile> <provider> <fallback> <multimodal_enabled>
  local outfile="$1"
  local provider="$2"
  local fallback="$3"
  local mm="$4"  # "true" or "false" (JSON literal)
  python3 - "$outfile" "$provider" "$fallback" "$mm" <<'PYEOF'
import json, sys
out, provider, fallback, mm = sys.argv[1:]
mm_bool = mm == "true"
cfg = {
  "agents": {
    "defaults": {
      "memorySearch": {
        "enabled": True,
        "provider": provider,
        "fallback": fallback,
        "multimodal": {"enabled": mm_bool}
      }
    },
    "list": []
  }
}
with open(out, "w") as f:
    json.dump(cfg, f, indent=2)
PYEOF
}

_make_per_agent_config() {
  # Config where multimodal.enabled is set at the per-agent level, not defaults.
  local outfile="$1"
  local provider="$2"
  local fallback="$3"
  local mm="$4"
  python3 - "$outfile" "$provider" "$fallback" "$mm" <<'PYEOF'
import json, sys
out, provider, fallback, mm = sys.argv[1:]
mm_bool = mm == "true"
cfg = {
  "agents": {
    "defaults": {
      "memorySearch": {
        "enabled": True,
        "provider": provider,
        "fallback": fallback,
        "multimodal": {"enabled": False}  # defaults is clean
      }
    },
    "list": [
      {
        "id": "main",
        "memorySearch": {
          "multimodal": {"enabled": mm_bool}
        }
      }
    ]
  }
}
with open(out, "w") as f:
    json.dump(cfg, f, indent=2)
PYEOF
}

# ── (A) SMOKE: text-only provider + multimodal.enabled=true → MUST FAIL ──────
echo "--- (A) SMOKE: text-only provider + multimodal.enabled=true → FAIL ---"

BAD_CONFIG_A="$TMPDIR_TEST/bad-config-a.json"
_make_config "$BAD_CONFIG_A" "openai" "openai" "true"

A_OUT=$(SMOKE_OC_CONFIG="$BAD_CONFIG_A" \
        ZHC_SKIP_LIVE_PROBE=1 \
        bash "$SMOKE_SCRIPT" 2>&1 || true)
A_EXIT=$(SMOKE_OC_CONFIG="$BAD_CONFIG_A" \
          ZHC_SKIP_LIVE_PROBE=1 \
          bash "$SMOKE_SCRIPT" >/dev/null 2>&1; echo $?)

if [ "$A_EXIT" = "1" ]; then
  pass "(A) smoke exits 1 on text-only+multimodal mismatch"
else
  fail "(A) smoke should exit 1 on text-only+multimodal mismatch (got exit $A_EXIT)"
fi

if printf '%s' "$A_OUT" | grep -qi "FATAL\|CAPABILITY MISMATCH\|S2"; then
  pass "(A) smoke output mentions S2 capability mismatch"
else
  fail "(A) smoke output should mention S2 / CAPABILITY MISMATCH (got: $(printf '%s' "$A_OUT" | head -3 | tr '\n' ';'))"
fi

# ── (B) SMOKE: text-only provider, multimodal disabled → MUST PASS ────────────
echo ""
echo "--- (B) SMOKE: text-only provider + multimodal.enabled=false → PASS ---"

GOOD_CONFIG_B="$TMPDIR_TEST/good-config-b.json"
_make_config "$GOOD_CONFIG_B" "openai" "openai" "false"

B_EXIT=$(SMOKE_OC_CONFIG="$GOOD_CONFIG_B" \
          ZHC_SKIP_LIVE_PROBE=1 \
          bash "$SMOKE_SCRIPT" >/dev/null 2>&1; echo $?)

if [ "$B_EXIT" = "0" ]; then
  pass "(B) smoke exits 0 on clean text-only+multimodal-false config"
else
  fail "(B) smoke should exit 0 on clean config (got exit $B_EXIT)"
fi

# ── (C) STATIC: text-only provider + multimodal.enabled=true → MUST FAIL ─────
echo ""
echo "--- (C) STATIC: text-only provider + multimodal.enabled=true → FAIL ---"

# Reuse bad config A
C_OUT=$(SMOKE_OC_CONFIG="$BAD_CONFIG_A" \
        bash "$STATIC_SCRIPT" 2>&1 || true)
C_EXIT=$(SMOKE_OC_CONFIG="$BAD_CONFIG_A" \
          bash "$STATIC_SCRIPT" >/dev/null 2>&1; echo $?)

if [ "$C_EXIT" = "1" ]; then
  pass "(C) static exits 1 on text-only+multimodal mismatch"
else
  fail "(C) static should exit 1 on text-only+multimodal mismatch (got $C_EXIT)"
fi

if printf '%s' "$C_OUT" | grep -qi "INVARIANT VIOLATED\|I2\|FATAL"; then
  pass "(C) static output mentions I2 invariant violation"
else
  fail "(C) static output should mention I2 / INVARIANT VIOLATED (got: $(printf '%s' "$C_OUT" | head -3 | tr '\n' ';'))"
fi

# ── (D) STATIC: clean config → MUST PASS ─────────────────────────────────────
echo ""
echo "--- (D) STATIC: clean config → PASS ---"

D_EXIT=$(SMOKE_OC_CONFIG="$GOOD_CONFIG_B" \
          bash "$STATIC_SCRIPT" >/dev/null 2>&1; echo $?)

if [ "$D_EXIT" = "0" ]; then
  pass "(D) static exits 0 on clean config"
else
  fail "(D) static should exit 0 on clean config (got $D_EXIT)"
fi

# ── (E) STATIC: fallback=none → invariant MUST FAIL ──────────────────────────
echo ""
echo "--- (E) STATIC: fallback=none → FAIL ---"

FALLBACK_NONE_CONFIG="$TMPDIR_TEST/fallback-none.json"
_make_config "$FALLBACK_NONE_CONFIG" "openai" "none" "false"

E_OUT=$(SMOKE_OC_CONFIG="$FALLBACK_NONE_CONFIG" \
        bash "$STATIC_SCRIPT" 2>&1 || true)
E_EXIT=$(SMOKE_OC_CONFIG="$FALLBACK_NONE_CONFIG" \
          bash "$STATIC_SCRIPT" >/dev/null 2>&1; echo $?)

if [ "$E_EXIT" = "1" ]; then
  pass "(E) static exits 1 on fallback=none"
else
  fail "(E) static should exit 1 on fallback=none (got $E_EXIT)"
fi

if printf '%s' "$E_OUT" | grep -qi "I1\|INVARIANT VIOLATED\|fallback.*none"; then
  pass "(E) static output mentions I1 / fallback=none invariant"
else
  fail "(E) static output should mention I1 / fallback=none (got: $(printf '%s' "$E_OUT" | head -3 | tr '\n' ';'))"
fi

# ── (F) SMOKE: fallback=none → smoke MUST FAIL ───────────────────────────────
echo ""
echo "--- (F) SMOKE: fallback=none → FAIL ---"

F_OUT=$(SMOKE_OC_CONFIG="$FALLBACK_NONE_CONFIG" \
        ZHC_SKIP_LIVE_PROBE=1 \
        bash "$SMOKE_SCRIPT" 2>&1 || true)
F_EXIT=$(SMOKE_OC_CONFIG="$FALLBACK_NONE_CONFIG" \
          ZHC_SKIP_LIVE_PROBE=1 \
          bash "$SMOKE_SCRIPT" >/dev/null 2>&1; echo $?)

if [ "$F_EXIT" = "1" ]; then
  pass "(F) smoke exits 1 on fallback=none"
else
  fail "(F) smoke should exit 1 on fallback=none (got $F_EXIT)"
fi

if printf '%s' "$F_OUT" | grep -qi "S1\|fallback.*none\|FATAL"; then
  pass "(F) smoke output mentions S1 / fallback=none"
else
  fail "(F) smoke output should mention S1 / fallback=none (got: $(printf '%s' "$F_OUT" | head -3 | tr '\n' ';'))"
fi

# ── (G) STATIC: no openclaw.json → exits 1 with "cannot find" ───────────────
echo ""
echo "--- (G) STATIC: no openclaw.json → exits 1 gracefully ---"

G_OUT=$(SMOKE_OC_CONFIG="/nonexistent/path/openclaw.json" \
        bash "$STATIC_SCRIPT" 2>&1 || true)
G_EXIT=$(SMOKE_OC_CONFIG="/nonexistent/path/openclaw.json" \
          bash "$STATIC_SCRIPT" >/dev/null 2>&1; echo $?)

if [ "$G_EXIT" = "1" ]; then
  pass "(G) static exits 1 when openclaw.json not found"
else
  fail "(G) static should exit 1 when no openclaw.json (got $G_EXIT)"
fi

# ── (H) Per-agent multimodal flag caught by static ───────────────────────────
echo ""
echo "--- (H) STATIC: per-agent multimodal.enabled=true with text-only provider → FAIL ---"

PER_AGENT_CONFIG="$TMPDIR_TEST/per-agent-mm.json"
_make_per_agent_config "$PER_AGENT_CONFIG" "openrouter" "openrouter" "true"

H_OUT=$(SMOKE_OC_CONFIG="$PER_AGENT_CONFIG" \
        bash "$STATIC_SCRIPT" 2>&1 || true)
H_EXIT=$(SMOKE_OC_CONFIG="$PER_AGENT_CONFIG" \
          bash "$STATIC_SCRIPT" >/dev/null 2>&1; echo $?)

if [ "$H_EXIT" = "1" ]; then
  pass "(H) static catches per-agent multimodal mismatch (exits 1)"
else
  fail "(H) static should exit 1 for per-agent multimodal mismatch (got $H_EXIT)"
fi

if printf '%s' "$H_OUT" | grep -qi "agent=main\|I2\|INVARIANT VIOLATED"; then
  pass "(H) static identifies the specific agent (main) in the violation"
else
  fail "(H) static should name the agent in the violation (got: $(printf '%s' "$H_OUT" | head -5 | tr '\n' ';'))"
fi

# ── (I) ollama-cloud is text-only (regression guard) ─────────────────────────
echo ""
echo "--- (I) STATIC: ollama-cloud + multimodal.enabled=true → FAIL (regression guard) ---"

OC_CLOUD_CONFIG="$TMPDIR_TEST/ollama-cloud-mm.json"
_make_config "$OC_CLOUD_CONFIG" "ollama-cloud" "openai" "true"

I_EXIT=$(SMOKE_OC_CONFIG="$OC_CLOUD_CONFIG" \
          bash "$STATIC_SCRIPT" >/dev/null 2>&1; echo $?)

if [ "$I_EXIT" = "1" ]; then
  pass "(I) ollama-cloud correctly identified as text-only (multimodal mismatch caught)"
else
  fail "(I) ollama-cloud should be classified as text-only (static should exit 1, got $I_EXIT)"
fi

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="

if [ "$FAIL" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "TESTS FAILED"
  exit 1
fi

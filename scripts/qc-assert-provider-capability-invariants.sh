#!/usr/bin/env bash
# qc-assert-provider-capability-invariants.sh — v12.14.0
#
# STATIC QC INVARIANT: build-time / CI check.
# Fails the build if any agent config ships:
#   I1  memorySearch.fallback="none"  (no fallback path — silent memory death on provider failure)
#   I2  memorySearch.multimodal.enabled=true while the configured embedding provider
#       is TEXT_ONLY (multimodal adapter will throw on every message)
#
# Checks openclaw.json at the canonical location (or SMOKE_OC_CONFIG override).
# Part of the same gate family as verify-routing.sh (same exit-code contract).
#
# Exit codes:
#   0  — all invariants pass
#   1  — one or more invariants VIOLATED (FATAL — block the build/QC)
#
# Usage:
#   bash qc-assert-provider-capability-invariants.sh
#   bash qc-assert-provider-capability-invariants.sh --quiet
#   SMOKE_OC_CONFIG=/path/to/openclaw.json bash qc-assert-provider-capability-invariants.sh
#
# Wired in:
#   scripts/qc-system-integrity.sh  (section X: cross-cutting invariants)
#
# TEXT_ONLY_PROVIDERS: providers whose embedding models accept text input only.
# Setting multimodal.enabled=true against any of these causes the memory-core
# multimodal adapter to throw on every message.
# openai, openrouter, ollama, ollama-cloud, gemini, google, cohere, mistral,
# anthropic, groq, together, fireworks, perplexity, deepseek

set -uo pipefail

QUIET=0
for _arg in "$@"; do
  [[ "$_arg" == "--quiet" ]] && QUIET=1
done

_pass() { [ "$QUIET" = "0" ] && printf '[qc-provider-invariants] PASS  %s\n' "$*"; }
_fail() { printf '[qc-provider-invariants] FATAL %s\n' "$*" >&2; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-provider-invariants] INFO  %s\n' "$*"; }

FAILURES=0

# ─── Platform / config location ──────────────────────────────────────────────

OC_CONFIG="${SMOKE_OC_CONFIG:-}"
if [ -z "$OC_CONFIG" ]; then
  if [ -f /data/.openclaw/openclaw.json ]; then
    OC_CONFIG="/data/.openclaw/openclaw.json"
  elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
    OC_CONFIG="$HOME/.openclaw/openclaw.json"
  else
    _fail "cannot find openclaw.json in /data/.openclaw or $HOME/.openclaw"
    exit 1
  fi
fi

if [ ! -f "$OC_CONFIG" ]; then
  _fail "openclaw.json not found at: $OC_CONFIG"
  exit 1
fi

_info "checking: $OC_CONFIG"

# ─── Single-pass Python analysis (all-in-one, no stdin pipe chaining) ─────────
# All logic runs in one Python call to avoid heredoc+pipe stdin conflicts.
# Outputs a line-delimited report that bash parses.

ANALYSIS_RESULT=$(python3 - "$OC_CONFIG" <<'PYEOF'
import json, sys
from pathlib import Path

TEXT_ONLY_PROVIDERS = {
    "openai", "openrouter", "ollama", "ollama-cloud",
    "gemini", "google", "cohere", "mistral",
    "anthropic", "groq", "together", "fireworks",
    "perplexity", "deepseek",
}

def is_text_only(provider_str):
    """Return True if provider is in the text-only list (or empty/unknown)."""
    if not provider_str:
        return True  # unknown => treat as text-only (safe default)
    base = provider_str.split("/")[0].strip().lower()
    return base in TEXT_ONLY_PROVIDERS

try:
    cfg = json.loads(Path(sys.argv[1]).read_text())
except Exception as e:
    print(f"PARSE_ERROR:{e}")
    sys.exit(0)

agents_cfg = cfg.get("agents", {})
defaults = agents_cfg.get("defaults", {})
agents_list = agents_cfg.get("list", []) or []
memory_search = defaults.get("memorySearch", {})

embed_provider = (memory_search.get("provider") or "").strip().lower()
embed_fallback = (memory_search.get("fallback") or "").strip().lower()

print(f"PROVIDER:{embed_provider}")
print(f"FALLBACK:{embed_fallback}")

# I1: fallback=none check
if embed_fallback == "none":
    print("I1_FAIL:agents.defaults.memorySearch.fallback=none")
else:
    print("I1_PASS:ok")

# I2: multimodal.enabled=true against text-only provider
hard_violations = []

# Check defaults block
def_mm = (memory_search.get("multimodal") or {})
if def_mm.get("enabled"):
    resolved = embed_provider
    if is_text_only(resolved):
        hard_violations.append(f"agent=defaults provider={resolved or '<not set>'}")

# Check per-agent blocks
for ag in agents_list:
    if not isinstance(ag, dict):
        continue
    ag_id = ag.get("id", "<unknown>")
    ag_ms = ag.get("memorySearch") or {}
    ag_mm = ag_ms.get("multimodal") or {}
    if ag_mm.get("enabled"):
        # Per-agent provider; fall back to defaults if not set
        ag_provider = (ag_ms.get("provider") or embed_provider).strip().lower()
        if is_text_only(ag_provider):
            hard_violations.append(f"agent={ag_id} provider={ag_provider or '<not set>'}")

if hard_violations:
    for v in hard_violations:
        print(f"I2_FAIL:{v}")
else:
    print("I2_PASS:ok")

PYEOF
) || ANALYSIS_RESULT="PARSE_ERROR:python3_failed"

if printf '%s' "$ANALYSIS_RESULT" | grep -q "^PARSE_ERROR:"; then
  _fail "cannot parse openclaw.json: $(printf '%s' "$ANALYSIS_RESULT" | grep "^PARSE_ERROR:" | head -1)"
  exit 1
fi

EMBED_PROVIDER=$(printf '%s' "$ANALYSIS_RESULT" | grep "^PROVIDER:" | cut -d: -f2- || echo "")
EMBED_FALLBACK=$(printf '%s' "$ANALYSIS_RESULT" | grep "^FALLBACK:" | cut -d: -f2- || echo "")

_info "embed provider: ${EMBED_PROVIDER:-<not set>}"
_info "embed fallback: ${EMBED_FALLBACK:-<not set>}"

# ─── I1: fallback != "none" ───────────────────────────────────────────────────
_info "I1: agents.defaults.memorySearch.fallback must not be \"none\""
if printf '%s' "$ANALYSIS_RESULT" | grep -q "^I1_FAIL:"; then
  I1_MSG=$(printf '%s' "$ANALYSIS_RESULT" | grep "^I1_FAIL:" | cut -d: -f2-)
  _fail "I1: INVARIANT VIOLATED — $I1_MSG. A config with fallback=none has no recovery path when the primary embedding provider fails; memory search silently dies. This config MUST NOT ship. Set fallback to a working text-embedding provider (e.g. \"openai\", \"openrouter\")."
  FAILURES=$((FAILURES + 1))
else
  _pass "I1: memorySearch.fallback=${EMBED_FALLBACK:-<unset>} (not \"none\")"
fi

# ─── I2: no multimodal.enabled=true against a text-only provider ─────────────
_info "I2: no agent may enable multimodal embeddings against a text-only provider"

I2_FAIL_LINES=$(printf '%s' "$ANALYSIS_RESULT" | grep "^I2_FAIL:" || true)
if [ -n "$I2_FAIL_LINES" ]; then
  while IFS= read -r line; do
    detail="${line#I2_FAIL:}"
    _fail "I2: INVARIANT VIOLATED — multimodal.enabled=true on TEXT_ONLY provider: $detail. The memory-core multimodal adapter will throw on EVERY message. This config MUST NOT ship. Disable multimodal.enabled or switch to a multimodal-capable embedding provider."
    FAILURES=$((FAILURES + 1))
  done <<< "$I2_FAIL_LINES"
else
  if printf '%s' "$ANALYSIS_RESULT" | grep -q "^I2_PASS:"; then
    _pass "I2: no multimodal.enabled=true against a text-only provider"
  fi
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
if [ "$FAILURES" -eq 0 ]; then
  _info "ALL INVARIANTS PASS — provider config is safe to ship"
  exit 0
else
  _fail "$FAILURES invariant(s) VIOLATED — block this build"
  _fail "Fix: correct memorySearch.provider/fallback/multimodal in openclaw.json; never ship fallback=none or multimodal=true against a text-only provider"
  exit 1
fi

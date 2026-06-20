#!/usr/bin/env bash
# smoke-test-provider-capabilities.sh — v12.14.0
#
# CLIENT-KEYS SMOKE TEST: runs ON the client box with the CLIENT's own keys.
# Fails loud on any of:
#   (a) A live agent turn that does NOT return a real reply
#       (4xx, ECONNREFUSED, 402, model error)
#   (b) A memory search that throws (especially the multimodal adapter throw)
#   (c) Capability mismatch: an agent enables a feature (multimodal embeddings)
#       that the configured embedding provider cannot actually support.
#
# On failure: sets closeoutStatus=blocked-provider-mismatch + alerts operator.
#
# Usage:
#   bash smoke-test-provider-capabilities.sh
#   bash smoke-test-provider-capabilities.sh --quiet
#   ZHC_SKIP_PROVIDER_SMOKE=1  (env var: skip in unit-test environments)
#
# Wire-in points:
#   37-zhc-closeout/scripts/run-closeout.sh   (B7 gate before closeout begins)
#   Per-box embedding-health cron              (periodic health polling)
#
# Exit codes:
#   0  — all checks pass
#   1  — one or more checks FAILED (FATAL: do not proceed with closeout)
#
# Environment (read from openclaw.json; override via env vars for testing):
#   SMOKE_OC_CONFIG         — override path to openclaw.json
#   SMOKE_OPERATOR_CHAT_ID  — override operator Telegram chat ID
#   SMOKE_STATE_FILE        — override path to .workforce-build-state.json
#
# PROVIDER CAPABILITY MAP (TEXT_ONLY providers: multimodal.enabled MUST be false)
#
# TEXT_ONLY_PROVIDERS = providers whose embedding models process text input only;
#   they do not accept image or multimodal input. Setting multimodal.enabled=true
#   against these providers throws at the memory-core adapter level on every message.
#
# Authoritative list (add new text-only providers here as discovered):
#   openai, openrouter, ollama, ollama-cloud, gemini, google, cohere, mistral,
#   anthropic, groq, together, fireworks, perplexity, deepseek
#
# Multimodal-capable embedding providers (may support multimodal.enabled=true):
#   (currently none confirmed in OpenClaw fleet — update this comment when one is added)

set -uo pipefail

QUIET=0
for _arg in "$@"; do
  [[ "$_arg" == "--quiet" ]] && QUIET=1
done

_pass() { [ "$QUIET" = "0" ] && printf '[provider-smoke] PASS  %s\n' "$*"; }
_fail() { printf '[provider-smoke] FATAL %s\n' "$*" >&2; }
_info() { [ "$QUIET" = "0" ] && printf '[provider-smoke] INFO  %s\n' "$*"; }
_warn() { printf '[provider-smoke] WARN  %s\n' "$*" >&2; }

FAILURES=0
WARNINGS=0

# ─── Platform detection ───────────────────────────────────────────────────────

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

_info "config: $OC_CONFIG"

# ─── State file (for blocked-provider-mismatch writes) ───────────────────────

STATE_FILE="${SMOKE_STATE_FILE:-}"
if [ -z "$STATE_FILE" ]; then
  OC_ROOT="$(dirname "$(dirname "$OC_CONFIG")")"
  # Try the standard locations
  for _cand in \
    "${OC_ROOT}/.openclaw/workspace/.workforce-build-state.json" \
    "${OC_ROOT}/workspace/.workforce-build-state.json" \
    "$HOME/.openclaw/workspace/.workforce-build-state.json" \
    "/data/.openclaw/workspace/.workforce-build-state.json"; do
    [ -f "$_cand" ] && STATE_FILE="$_cand" && break
  done
fi

_state_set_blocked() {
  local reason="$1"
  if [ -n "$STATE_FILE" ] && [ -f "$STATE_FILE" ] && command -v jq >/dev/null 2>&1; then
    local _tmp
    _tmp=$(mktemp)
    jq ".closeoutStatus = \"blocked-provider-mismatch\" | .closeoutBlockReason = $(printf '%s' "$reason" | jq -Rs '.')" \
      "$STATE_FILE" > "$_tmp" && mv "$_tmp" "$STATE_FILE" || rm -f "$_tmp"
  fi
}

_operator_alert() {
  local msg="$1"
  # CO-MINGLING GUARD (v12.4.0): operator alert chat is OPT-IN. NO hardcoded chat.
  local chat_id="${SMOKE_OPERATOR_CHAT_ID:-${OPERATOR_ESCALATION_CHAT_ID:-${OPERATOR_TELEGRAM_CHAT_ID:-}}}"
  if [[ -n "$chat_id" ]] && command -v openclaw >/dev/null 2>&1; then
    openclaw message send --channel telegram -t "$chat_id" -m "$msg" >/dev/null 2>&1 || true
  fi
}

# ─── OpenClaw version + capability detection (S3 version-awareness) ────────────
#
# WHY: the S3 live-turn probe historically used `openclaw message send --channel
# internal` — a gateway loopback channel. That channel was REMOVED in OpenClaw
# 2026.6.x. On 2026.6.8 the CLI returns `Error: Unknown channel: internal`
# (verified: `openclaw message send --channel internal -t self --dry-run` ⇒
# "Unknown channel: internal"; `openclaw message send --help` lists the supported
# channels and 'internal' is NOT among them). The replacement live-turn surface is
# `openclaw agent --message <text> --json`, which "Runs an agent turn via the
# Gateway" and returns the agent's reply WITHOUT delivering to any channel (we omit
# --deliver). So the probe stays a genuine live model turn on every version; only
# the transport changes.
#
# VERSION ASSUMPTION (documented): the 'internal' channel exists on installs
# BELOW 2026.6.0 and was removed at/after 2026.6.0. We therefore branch on a
# detected-version threshold of 2026.6.0 AND fall back to a runtime capability
# probe (does `agent` exist? is 'internal' an accepted channel?) so the gate is
# correct even if the exact removal version differs slightly across builds.
INTERNAL_REMOVED_VERSION="2026.6.0"

# OC_VERSION = parsed YYYY.M.P token from `openclaw --version`, or "" if unknown.
OC_VERSION=""
if command -v openclaw >/dev/null 2>&1; then
  _oc_raw="$(openclaw --version 2>&1 | tr -d '\r' | head -n1 || true)"
  OC_VERSION="$(printf '%s' "$_oc_raw" | grep -oE '20[0-9]{2}\.[0-9]+\.[0-9]+' | head -n1 || true)"
fi
# Allow tests to pin the version (and bypass the live binary) deterministically.
OC_VERSION="${SMOKE_OC_VERSION_OVERRIDE:-$OC_VERSION}"
[ -n "$OC_VERSION" ] && _info "OpenClaw version detected: $OC_VERSION"

# _ver_ge A B  → returns 0 if version A >= version B (numeric YYYY.M.P compare).
# Mirrors the canonical comparator in 38-.../16-verify-openclaw-version.sh.
_ver_ge() {
  printf '%s\n%s\n' "$2" "$1" | sort -t. -k1,1n -k2,2n -k3,3n -C
}

# _internal_channel_supported → 0 (yes) / 1 (no). Branch by version when known,
# else fall back to a runtime capability probe so we never fail on a version
# artifact. Tests can force the answer with SMOKE_INTERNAL_CHANNEL_SUPPORTED=0|1.
_internal_channel_supported() {
  if [ -n "${SMOKE_INTERNAL_CHANNEL_SUPPORTED:-}" ]; then
    [ "${SMOKE_INTERNAL_CHANNEL_SUPPORTED}" = "1" ] && return 0 || return 1
  fi
  if [ -n "$OC_VERSION" ]; then
    # internal exists only on versions strictly BELOW the removal version.
    if _ver_ge "$OC_VERSION" "$INTERNAL_REMOVED_VERSION"; then
      return 1   # 2026.6.0+ → removed
    else
      return 0   # below 2026.6.0 → present
    fi
  fi
  # Version unknown: runtime capability probe. `openclaw message send --help`
  # enumerates the supported --channel values; 'internal' present ⇒ supported.
  if command -v openclaw >/dev/null 2>&1; then
    if openclaw message send --help 2>&1 | grep -qiwE 'internal'; then
      return 0
    fi
    return 1
  fi
  # No binary at all: caller will skip the live probe anyway.
  return 1
}

# ─── Read config via Python ───────────────────────────────────────────────────

CONFIG_READ=$(python3 - "$OC_CONFIG" <<'PYEOF'
import json, sys
from pathlib import Path

try:
    cfg = json.loads(Path(sys.argv[1]).read_text())
except Exception as e:
    print(f"ERROR:cannot_parse:{e}")
    sys.exit(0)

agents_cfg = cfg.get("agents", {})
defaults = agents_cfg.get("defaults", {})
agents_list = agents_cfg.get("list", []) or []

memory_search = defaults.get("memorySearch", {})
embed_provider = (memory_search.get("provider") or "").strip().lower()
embed_fallback = (memory_search.get("fallback") or "").strip().lower()
memory_enabled = bool(memory_search.get("enabled", False))

# Scan all agents for multimodal.enabled
multimodal_agents = []
for ag in agents_list:
    if not isinstance(ag, dict):
        continue
    ag_id = ag.get("id", "<unknown>")
    ag_ms = ag.get("memorySearch") or {}
    ag_mm = ag_ms.get("multimodal") or {}
    if ag_mm.get("enabled"):
        multimodal_agents.append(ag_id)

# Also check defaults
def_mm = (memory_search.get("multimodal") or {})
if def_mm.get("enabled"):
    multimodal_agents.append("defaults")

print(json.dumps({
    "embed_provider": embed_provider,
    "embed_fallback": embed_fallback,
    "memory_enabled": memory_enabled,
    "multimodal_agents": multimodal_agents,
}))
PYEOF
) || CONFIG_READ="ERROR:python3_failed"

if [[ "$CONFIG_READ" == ERROR:* ]]; then
  _fail "S1: cannot read openclaw.json: $CONFIG_READ"
  FAILURES=$((FAILURES + 1))
  exit 1
fi

EMBED_PROVIDER=$(printf '%s' "$CONFIG_READ" | python3 -c "import sys,json; print(json.load(sys.stdin)['embed_provider'])" 2>/dev/null || echo "")
EMBED_FALLBACK=$(printf '%s' "$CONFIG_READ" | python3 -c "import sys,json; print(json.load(sys.stdin)['embed_fallback'])" 2>/dev/null || echo "")
MEMORY_ENABLED=$(printf '%s' "$CONFIG_READ" | python3 -c "import sys,json; print('true' if json.load(sys.stdin)['memory_enabled'] else 'false')" 2>/dev/null || echo "false")
MULTIMODAL_AGENTS=$(printf '%s' "$CONFIG_READ" | python3 -c "import sys,json; print(','.join(json.load(sys.stdin)['multimodal_agents']))" 2>/dev/null || echo "")

_info "embed provider: ${EMBED_PROVIDER:-<not set>}"
_info "embed fallback: ${EMBED_FALLBACK:-<not set>}"
_info "memory enabled: $MEMORY_ENABLED"
_info "agents with multimodal.enabled=true: ${MULTIMODAL_AGENTS:-<none>}"

# ─── TEXT_ONLY provider list ──────────────────────────────────────────────────
# These providers support text-only embeddings. Setting multimodal.enabled=true
# against any of them causes the memory-core adapter to throw on every message.

TEXT_ONLY_PROVIDERS="openai openrouter ollama ollama-cloud gemini google cohere mistral anthropic groq together fireworks perplexity deepseek"

_provider_is_text_only() {
  local p="$1"
  [ -z "$p" ] && return 0  # treat unknown as text-only (safe default)
  for tp in $TEXT_ONLY_PROVIDERS; do
    # Strip model suffix (e.g. "ollama-cloud/deepseek-v4-pro:cloud" → "ollama-cloud")
    local base="${p%%/*}"
    base="${base%%-*}"  # handle "ollama-cloud" → check against "ollama" too
    local full_base="${p%%/*}"
    [ "$full_base" = "$tp" ] && return 0
    [ "$base" = "$tp" ] && return 0
  done
  return 1
}

# ─── S1: fallback MUST NOT be "none" ─────────────────────────────────────────
_info "S1: checking agents.defaults.memorySearch.fallback != \"none\""
if [ "$EMBED_FALLBACK" = "none" ]; then
  _fail "S1: agents.defaults.memorySearch.fallback is \"none\" — memory search has NO fallback path; on provider failure memory silently dies. Set fallback to a working text-embedding provider (e.g. \"openai\", \"openrouter\")."
  FAILURES=$((FAILURES + 1))
else
  _pass "S1: memorySearch.fallback=${EMBED_FALLBACK:-<unset>} (not \"none\")"
fi

# ─── S2: capability mismatch — multimodal vs text-only provider ───────────────
_info "S2: checking multimodal.enabled=true is not set against a text-only provider"

if [ -n "$MULTIMODAL_AGENTS" ]; then
  PROVIDER_TO_CHECK="$EMBED_PROVIDER"
  # If provider is empty, the fallback is used; check that too
  [ -z "$PROVIDER_TO_CHECK" ] && PROVIDER_TO_CHECK="$EMBED_FALLBACK"

  if _provider_is_text_only "$PROVIDER_TO_CHECK"; then
    _fail "S2: CAPABILITY MISMATCH — agent(s) [${MULTIMODAL_AGENTS}] have memorySearch.multimodal.enabled=true but the configured embedding provider '${PROVIDER_TO_CHECK:-<not set>}' is TEXT_ONLY. This causes the memory-core multimodal adapter to throw on EVERY message. Disable multimodal.enabled on those agents OR switch to a multimodal-capable embedding provider."
    FAILURES=$((FAILURES + 1))
    _state_set_blocked "S2: multimodal.enabled=true on text-only provider '${PROVIDER_TO_CHECK}' (agents: ${MULTIMODAL_AGENTS})"
    _operator_alert "🚨 PROVIDER MISMATCH on $(hostname): agents [${MULTIMODAL_AGENTS}] have multimodal.enabled=true but provider '${PROVIDER_TO_CHECK}' is text-only. Memory search will throw on every message. Fix before closeout."
  else
    _pass "S2: multimodal.enabled agents [${MULTIMODAL_AGENTS}] — provider '${PROVIDER_TO_CHECK}' supports multimodal (or is not in text-only list)"
  fi
else
  _pass "S2: no agents have multimodal.enabled=true — no capability mismatch possible"
fi

# ─── S3: live agent turn test ─────────────────────────────────────────────────
# Sends a minimal probe to the local gateway and verifies a real reply comes back.
# VERSION-AWARE TRANSPORT:
#   • OpenClaw < 2026.6.0: probe via `message send --channel internal` (loopback).
#   • OpenClaw >= 2026.6.0: the 'internal' channel was REMOVED, so probe via
#     `openclaw agent --message <text> --json` (runs a genuine agent turn through
#     the Gateway, no channel delivery). Same semantics: a real model reply must
#     come back. We do NOT skip the gate or require ZHC_SKIP_LIVE_PROBE — the gate
#     keeps fail-loud for a genuine provider/gateway failure on every version.
# Skip ONLY when: openclaw CLI not available, or ZHC_SKIP_LIVE_PROBE=1 (test mode).
_info "S3: live agent turn probe"
if [[ "${ZHC_SKIP_LIVE_PROBE:-0}" = "1" ]]; then
  _info "S3: ZHC_SKIP_LIVE_PROBE=1 — skipping live probe (test mode)"
elif ! command -v openclaw >/dev/null 2>&1; then
  _warn "S3: openclaw CLI not found — skipping live probe"
  WARNINGS=$((WARNINGS + 1))
else
  # Use a deterministic single-word probe that any model should answer in one token
  if _internal_channel_supported; then
    _info "S3: using legacy 'internal' loopback channel (OpenClaw < ${INTERNAL_REMOVED_VERSION})"
    PROBE_OUT=$(openclaw message send --channel internal -m "ping" --json --timeout 30 2>&1 || true)
  else
    _info "S3: 'internal' channel unavailable on this OpenClaw (>= ${INTERNAL_REMOVED_VERSION}); probing via 'openclaw agent' turn"
    # `agent` runs a real Gateway turn and returns the reply; omit --deliver so
    # nothing is sent to any channel. This preserves the live-turn semantics.
    PROBE_OUT=$(openclaw agent --message "ping" --json --timeout 30 2>&1 || true)
  fi
  PROBE_OK=0
  # Accept any non-empty reply that isn't a connectivity/auth error. Cover both
  # the message-send shape ("reply"/"content"/"message"/"response") and the
  # `openclaw agent --json` shape ("text"/"reply"/"output"/"result").
  if printf '%s' "$PROBE_OUT" | grep -qiE '"reply"|"content"|"message"|"response"|"text"|"output"|"result"'; then
    PROBE_OK=1
  fi
  # Explicit failure signals (genuine provider/gateway failure → keep fail-loud).
  if printf '%s' "$PROBE_OUT" | grep -qiE '4[0-9]{2}|ECONNREFUSED|402|model.*error|authentication.*fail|unauthorized|Unknown channel'; then
    PROBE_OK=0
  fi
  if [ "$PROBE_OK" = "1" ]; then
    _pass "S3: live agent probe returned a real reply"
  else
    _fail "S3: live agent probe FAILED — gateway returned no valid reply. Output: $(printf '%s' "$PROBE_OUT" | head -3 | tr '\n' ' ')"
    FAILURES=$((FAILURES + 1))
    _state_set_blocked "S3: live agent probe failed (no valid reply from gateway)"
    _operator_alert "🚨 PROVIDER SMOKE FAIL on $(hostname): live agent probe returned no valid reply. Check gateway + provider credentials before closeout."
  fi
fi

# ─── S4: memory search health probe ──────────────────────────────────────────
# Confirms memory search doesn't throw. Uses the embedding-health cron pattern.
# Skip when: openclaw CLI not available or ZHC_SKIP_LIVE_PROBE=1.
_info "S4: memory search health probe"
if [[ "${ZHC_SKIP_LIVE_PROBE:-0}" = "1" ]]; then
  _info "S4: ZHC_SKIP_LIVE_PROBE=1 — skipping memory probe (test mode)"
elif ! command -v openclaw >/dev/null 2>&1; then
  _warn "S4: openclaw CLI not found — skipping memory probe"
  WARNINGS=$((WARNINGS + 1))
elif [ "$MEMORY_ENABLED" != "true" ]; then
  _info "S4: memorySearch.enabled is not true — skipping memory probe (memory not configured)"
else
  MEM_OUT=$(openclaw memory search --query "smoke test probe" --limit 1 --json 2>&1 || true)
  if printf '%s' "$MEM_OUT" | grep -qiE 'multimodal.*adapter.*throw|TypeError|Error.*embed|embedding.*fail|memory.*error'; then
    _fail "S4: memory search threw an error — likely multimodal adapter throw or embedding provider failure. Output: $(printf '%s' "$MEM_OUT" | head -3 | tr '\n' ' ')"
    FAILURES=$((FAILURES + 1))
    _state_set_blocked "S4: memory search threw — $(printf '%s' "$MEM_OUT" | head -1)"
    _operator_alert "🚨 MEMORY SEARCH THREW on $(hostname): $(printf '%s' "$MEM_OUT" | head -2 | tr '\n' ' '). Likely multimodal adapter / text-only provider mismatch."
  else
    _pass "S4: memory search probe completed without throwing"
  fi
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
if [ "$FAILURES" -eq 0 ]; then
  _info "ALL CHECKS PASSED — provider capabilities are compatible with agent config"
  if [ "$WARNINGS" -gt 0 ]; then
    _warn "$WARNINGS warning(s) — some live probes skipped (see above)"
  fi
  exit 0
else
  _fail "$FAILURES check(s) FAILED — provider capability mismatch or live probe failure"
  _fail "Fix: correct memorySearch.provider/fallback/multimodal config in openclaw.json and re-run this check"
  exit 1
fi

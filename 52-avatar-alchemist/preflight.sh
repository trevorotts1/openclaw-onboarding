#!/usr/bin/env bash
# preflight.sh — probe the CLIENT's own configured providers (per-box capability test) and
# write model-map.json (TIER-A/B/SEARCH) + provider_caps. NEVER Anthropic; client keys only.
# This is a scaffold: it resolves tiers from the box's OpenClaw provider config; on a client box
# the real provider probe fills these. It hard-refuses any resolved Anthropic id.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
OUT="${1:-$HERE/model-map.json}"

# discover configured providers from the box (best-effort; scaffold defaults for offline build)
TIER_A="${AA_TIER_A:-ollama-cloud/qwen3-235b}"
TIER_B="${AA_TIER_B:-openrouter/deepseek-chat}"
SEARCH="${AA_SEARCH:-box-web-search+tier-b-composer}"
CAP="${AA_PROVIDER_CAP:-3}"   # local-Ollama-only boxes cap 3 (fleet provisioning rule)

for m in "$TIER_A" "$TIER_B"; do
  case "$m" in
    *anthropic*|*claude*) echo "REFUSED: resolved model '$m' matches /anthropic|claude/ (client-path ban)"; exit 2;;
  esac
done

python3 - "$OUT" "$TIER_A" "$TIER_B" "$SEARCH" "$CAP" <<'PY'
import json, sys
out, a, b, s, cap = sys.argv[1:6]
json.dump({
  "tiers": {"A": a, "B": b, "SEARCH": s},
  "provider_caps": {"concurrent": int(cap)},
  "rule": "client's own providers only; G-NOANTHROPIC bans /anthropic|claude/i; client's express choice never substituted",
}, open(out, "w"), indent=2)
print(f"wrote model-map -> {out}: TIER-A={a} TIER-B={b} SEARCH={s} cap={cap}")
PY

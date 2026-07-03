#!/usr/bin/env bash
# 53-book-writer/preflight.sh — per-box provider capability probe (idempotent).
# ============================================================================
# Probes the CLIENT's configured model providers and writes model-map.json +
# provider_caps next to this script, so the foreman resolves each capability tier
# (HEAVY-WRITER / MID-WRITER / FORMATTER / RESEARCHER / IMAGE) to the client's OWN
# providers — NEVER Anthropic, NEVER operator keys. Also notes the optional PDF
# toolchain (pandoc + weasyprint). Re-running is safe: it overwrites model-map.json
# in place and never aborts on an existing file.
#
# This is a PROBE + TEMPLATE writer: it does not hardcode any model id. A client's
# express model choice is never substituted (client-sovereignty rule).
# ============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
OUT="$SELF_DIR/model-map.json"

note() { echo "=== [preflight] $* ==="; }

command -v python3 >/dev/null 2>&1 || { echo "preflight: python3 required" >&2; exit 6; }

# concurrency cap heuristic: min(16, cores-2); local-Ollama boxes cap at 3 (set by
# the operator via OC_PROVIDER_CAP if the box is Ollama-only).
CORES="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
SLOTS=$(( CORES - 2 )); [ "$SLOTS" -lt 1 ] && SLOTS=1; [ "$SLOTS" -gt 16 ] && SLOTS=16
PROVIDER_CAP="${OC_PROVIDER_CAP:-$SLOTS}"

note "probing providers (cores=$CORES slots=$SLOTS provider_cap=$PROVIDER_CAP)"

# Emit a provider-neutral model-map TEMPLATE the operator/box fills with the
# client's OWN ids. Tiers only; zero Anthropic ids.
OUT="$OUT" SLOTS="$SLOTS" PROVIDER_CAP="$PROVIDER_CAP" python3 - <<'PY'
import json, os
out = os.environ["OUT"]
existing = {}
if os.path.exists(out):
    try:
        existing = json.load(open(out))
    except Exception:
        existing = {}
model_map = {
    "$note": "CLIENT providers only. Fill each tier with the client's OWN model id. NEVER an Anthropic/claude-* id (AF-BK-ANTHROPIC hard-fails). A client's express choice is never substituted.",
    "tiers": {
        "HEAVY-WRITER": existing.get("tiers", {}).get("HEAVY-WRITER", ""),
        "MID-WRITER":   existing.get("tiers", {}).get("MID-WRITER", ""),
        "FORMATTER":    existing.get("tiers", {}).get("FORMATTER", ""),
        "RESEARCHER":   existing.get("tiers", {}).get("RESEARCHER", ""),
        "IMAGE":        existing.get("tiers", {}).get("IMAGE", ""),
    },
    "provider_caps": {"slots": int(os.environ["SLOTS"]), "provider_cap": int(os.environ["PROVIDER_CAP"])},
    "search_capability": existing.get("search_capability", "unknown"),
    "image_capability":  existing.get("image_capability", "unknown"),
}
json.dump(model_map, open(out, "w"), indent=2)
print("wrote", out)
PY

# optional PDF toolchain note (never fails the run; manuscript .md always delivers)
if command -v pandoc >/dev/null 2>&1 && python3 -c 'import weasyprint' >/dev/null 2>&1; then
    note "PDF toolchain present (pandoc + weasyprint)"
else
    note "PDF toolchain optional/absent — install with: brew install pandoc && pip3 install weasyprint (manuscript .md still delivers)"
fi
note "preflight complete (idempotent)"

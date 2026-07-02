#!/usr/bin/env bash
# 54-anthology-writer/preflight.sh — resolve the CLIENT-PATH tier map per box.
# ----------------------------------------------------------------------------
# Reads assets/model-map.template.json and writes a resolved model-map.json into
# the run dir (or the skill dir if no --run-dir), mapping each capability TIER
# (HEAVY-WRITER / MID-WRITER / RESEARCHER / IMAGE) to the CLIENT's OWN strongest
# NON-Anthropic model. This stub emits the scaffold and asserts the template
# carries no Anthropic id; the real per-box resolution is wired to the client's
# configured providers by the fleet installer. Idempotent. NEVER writes an
# Anthropic id and NEVER an operator key.
#
# Exit 0 = resolved; 2 = template carries a banned id (fail-closed); 3 = usage.
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
TEMPLATE="$SELF_DIR/assets/model-map.template.json"
OUT_DIR="$SELF_DIR"
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir) OUT_DIR="${2:-}"; shift 2 ;;
        -h|--help) echo "usage: preflight.sh [--run-dir DIR]"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 3 ;;
    esac
done
[ -f "$TEMPLATE" ] || { echo "FATAL: template not found: $TEMPLATE" >&2; exit 3; }
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 required" >&2; exit 3; }

TEMPLATE="$TEMPLATE" OUT_DIR="$OUT_DIR" python3 - <<'PY'
import json, os, re, sys
tmpl = json.load(open(os.environ["TEMPLATE"]))
# fail-closed: the shipped template must never carry an Anthropic id
banned = re.compile(r"claude-|anthropic/|us\.anthropic\.")
blob = json.dumps(tmpl)
# the banned_model_id_prefixes LIST is documentation, not a resolved id; strip it
tiers = tmpl.get("tiers", {})
for name, t in tiers.items():
    for k in ("provider", "model"):
        v = str(t.get(k, ""))
        if banned.search(v):
            print("AF-AW-ANTHROPIC: template tier %s.%s carries a banned id %r" % (name, k, v), file=sys.stderr)
            sys.exit(2)
resolved = {
    "skill": "anthology-writer",
    "resolved_per_box": True,
    "note": "Scaffold — fleet installer fills provider/model from the CLIENT's own config. NEVER Anthropic, NEVER operator keys.",
    "tiers": {name: {"role": t.get("role", ""),
                     "provider": t.get("provider", "<CLIENT_PROVIDER_ID>"),
                     "model": t.get("model", "<CLIENT_MODEL>"),
                     "maxTokens": t.get("maxTokens")} for name, t in tiers.items()},
    "no_formatter_tier": True,
}
out = os.path.join(os.environ["OUT_DIR"], "model-map.json")
json.dump(resolved, open(out, "w"), indent=2)
print("  resolved model-map.json ->", out)
for name in tiers:
    print("   tier %-13s -> client's own NON-Anthropic model (resolved per box)" % name)
PY
rc=$?
[ "$rc" -eq 0 ] && echo "preflight: PASS (no Anthropic id; client tiers scaffolded)"
exit "$rc"

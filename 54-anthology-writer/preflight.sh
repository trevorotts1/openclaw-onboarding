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
# MODES:
#   (default) RESOLVE — write a resolved model-map.json scaffold into OUT_DIR.
#   --check           — PRE-GATE: read an existing OUT_DIR/model-map.json and
#                       fail-closed if it still carries <CLIENT_*> placeholders
#                       (AF-AW-UNRESOLVED-MODELMAP) or a banned Anthropic id. A
#                       missing map is a clean pass (the installer resolves per
#                       box). This wires preflight.sh as an entry pre-gate so a
#                       placeholder-laden resolved map can never reach a run.
#
# Exit 0 = ok; 2 = banned id / residual placeholder (fail-closed); 3 = usage.
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
TEMPLATE="$SELF_DIR/assets/model-map.template.json"
OUT_DIR="$SELF_DIR"
MODE="resolve"
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir) OUT_DIR="${2:-}"; shift 2 ;;
        --check)   MODE="check"; shift ;;
        -h|--help) echo "usage: preflight.sh [--run-dir DIR] [--check]"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 3 ;;
    esac
done
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 required" >&2; exit 3; }

if [ "$MODE" = "check" ]; then
    # PRE-GATE: assert a resolved run-dir model-map carries no residual
    # <CLIENT_*> placeholder and no banned Anthropic id. Missing map = clean pass.
    OUT_DIR="$OUT_DIR" python3 - <<'PY'
import json, os, re, sys
mp = os.path.join(os.environ["OUT_DIR"], "model-map.json")
if not os.path.isfile(mp):
    print("  preflight --check: no resolved model-map.json (installer resolves per box) — OK")
    sys.exit(0)
try:
    blob = open(mp, "r", encoding="utf-8").read()
    data = json.loads(blob)
except Exception as exc:
    print("AF-AW-UNRESOLVED-MODELMAP: model-map.json unreadable/invalid: %s" % exc, file=sys.stderr)
    sys.exit(2)
residual = sorted(set(re.findall(r"<CLIENT[A-Z0-9_]*>|<CLIENT_[^>]*>", blob)))
if residual:
    print("AF-AW-UNRESOLVED-MODELMAP: model-map.json still carries placeholder(s): %s"
          % ", ".join(residual), file=sys.stderr)
    sys.exit(2)
banned = re.compile(r"claude-|anthropic/|us\.anthropic\.")
for name, t in (data.get("tiers", {}) or {}).items():
    for k in ("provider", "model"):
        v = str((t or {}).get(k, ""))
        if banned.search(v):
            print("AF-AW-ANTHROPIC: resolved tier %s.%s carries a banned id %r" % (name, k, v),
                  file=sys.stderr)
            sys.exit(2)
print("  preflight --check: resolved model-map.json OK (no residual placeholder, no Anthropic id)")
sys.exit(0)
PY
    exit $?
fi

[ -f "$TEMPLATE" ] || { echo "FATAL: template not found: $TEMPLATE" >&2; exit 3; }

IS_TTY=false; [ -t 0 ] && IS_TTY=true
IS_TTY="$IS_TTY" TEMPLATE="$TEMPLATE" OUT_DIR="$OUT_DIR" python3 - <<'PY'
import json, os, re, sys

def prompt_tiers(tiers):
    """Interactive guided config: ask the user for provider + model per tier."""
    print("\n  === Interactive Model-Map Configuration ===", file=sys.stderr)
    print("  For each tier, enter the provider ID and model ID for your box.", file=sys.stderr)
    print("  Press Enter to accept the default shown in [brackets].", file=sys.stderr)
    print("  No provider/model may start with 'claude-', 'anthropic/', or 'us.anthropic.'.", file=sys.stderr)
    result = {}
    for name, t in sorted(tiers.items()):
        print("\n  --- Tier: %s (%s) ---" % (name, t.get("role", "")), file=sys.stderr)
        def_provider = os.environ.get("AW_PROVIDER_" + name, "")
        def_model    = os.environ.get("AW_MODEL_" + name, "")
        provider = input("  Provider for %s: " % name).strip()
        if not provider:
            provider = def_provider
        model = input("  Model for %s: " % name).strip()
        if not model:
            model = def_model
        result[name] = {"role": t.get("role", ""), "provider": provider or "",
                        "model": model or "", "maxTokens": t.get("maxTokens")}
    return result

tmpl = json.load(open(os.environ["TEMPLATE"]))
banned = re.compile(r"claude-|anthropic/|us\.anthropic\.")
blob = json.dumps(tmpl)
tiers = tmpl.get("tiers", {})
for name, t in tiers.items():
    for k in ("provider", "model"):
        v = str(t.get(k, ""))
        if banned.search(v):
            print("AF-AW-ANTHROPIC: template tier %s.%s carries a banned id %r" % (name, k, v), file=sys.stderr)
            sys.exit(2)

is_tty = os.environ.get("IS_TTY", "false") == "true"

if is_tty:
    # Interactive mode: prompt per tier so the resolved map is ready-to-run.
    resolved_tiers = prompt_tiers(tiers)
    note_text = "Resolved interactively — provider/model values entered by operator. NEVER Anthropic, NEVER operator keys."
else:
    # Non-interactive: emit placeholders requiring manual resolution.
    resolved_tiers = {name: {"role": t.get("role", ""),
                              "provider": t.get("provider", "<CLIENT_PROVIDER_ID>"),
                              "model": t.get("model", "<CLIENT_MODEL>"),
                              "maxTokens": t.get("maxTokens")} for name, t in tiers.items()}
    note_text = "Scaffold — fleet installer fills provider/model from the CLIENT's own config. NEVER Anthropic, NEVER operator keys."

resolved = {
    "skill": "anthology-writer",
    "resolved_per_box": True,
    "note": note_text,
    "tiers": resolved_tiers,
    "no_formatter_tier": True,
}
out = os.path.join(os.environ["OUT_DIR"], "model-map.json")
json.dump(resolved, open(out, "w"), indent=2)
print("  resolved model-map.json ->", out)
for name in resolved_tiers:
    prov = resolved_tiers[name].get("provider", "<PLACEHOLDER>")
    mod  = resolved_tiers[name].get("model", "<PLACEHOLDER>")
    print("   tier %-13s provider=%s model=%s" % (name, prov, mod))
PY
rc=$?
[ "$rc" -eq 0 ] && echo "preflight: PASS (no Anthropic id; client tiers scaffolded)"
exit "$rc"

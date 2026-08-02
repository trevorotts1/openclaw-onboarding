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
#   --resolve         — (explicit) same as default RESOLVE mode.
#   --interactive     — force interactive prompting (guided config via stdin).
#   --non-interactive — force non-interactive mode (emit placeholders, exit 0).
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
INTERACTIVE_MODE=""  # empty = auto-detect from TTY
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir) OUT_DIR="${2:-}"; shift 2 ;;
        --check)   MODE="check"; shift ;;
        --resolve) MODE="resolve"; shift ;;
        --interactive)   INTERACTIVE_MODE="true"; shift ;;
        --non-interactive) INTERACTIVE_MODE="false"; shift ;;
        -h|--help) echo "usage: preflight.sh [--run-dir DIR] [--resolve] [--interactive|--non-interactive] [--check]"; exit 0 ;;
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
    print("  [PASS] preflight --check: no resolved model-map.json (installer resolves per box)")
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
print("  [PASS] preflight --check: resolved model-map.json (no residual placeholder, no Anthropic id)")
sys.exit(0)
PY
    exit $?
fi

[ -f "$TEMPLATE" ] || { echo "FATAL: template not found: $TEMPLATE" >&2; exit 3; }

# Resolve interactive mode: --interactive/--non-interactive flag wins, else auto-detect from TTY.
if [ "$INTERACTIVE_MODE" = "true" ]; then
    IS_TTY=true
elif [ "$INTERACTIVE_MODE" = "false" ]; then
    IS_TTY=false
else
    IS_TTY=false; [ -t 0 ] && IS_TTY=true
fi
# Step 1: always write the placeholder scaffold first. This heredoc is SAFE —
# it never calls input(), so consuming stdin as the program source is fine.
INTERACTIVE_MODE="$INTERACTIVE_MODE" TEMPLATE="$TEMPLATE" OUT_DIR="$OUT_DIR" python3 - <<'PY'
import json, os, re, sys
tmpl = json.load(open(os.environ["TEMPLATE"]))
banned = re.compile(r"claude-|anthropic/|us\.anthropic\.")
tiers = tmpl.get("tiers", {})
for name, t in tiers.items():
    for k in ("provider", "model"):
        v = str(t.get(k, ""))
        if banned.search(v):
            print("AF-AW-ANTHROPIC: template tier %s.%s carries a banned id %r" % (name, k, v), file=sys.stderr)
            sys.exit(2)
# Non-interactive: emit placeholders requiring manual resolution or fleet-installer fill.
resolved_tiers = {name: {"role": t.get("role", ""),
                          "provider": t.get("provider", "<CLIENT_PROVIDER_ID>"),
                          "model": t.get("model", "<CLIENT_MODEL>"),
                          "maxTokens": t.get("maxTokens")} for name, t in tiers.items()}
if os.environ.get("INTERACTIVE_MODE", "") == "false":
    note_text = "Placeholder scaffold — CI/automation run. Run 'preflight.sh --resolve --interactive' to fill provider/model values, or hand-edit model-map.json. NEVER Anthropic, NEVER operator keys."
else:
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
print("  scaffold model-map.json ->", out)
PY
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"

# Step 2: if interactive, resolve the placeholders by prompting the operator.
# This runs as a REAL SCRIPT FILE (not a heredoc) so python3's stdin stays
# attached to the terminal / piped answers. A heredoc would feed the program
# text on stdin, leaving input() at EOF — every prompt would die with EOFError.
if [ "$IS_TTY" = "true" ]; then
    python3 "$SELF_DIR/scripts/_resolve_model_map_interactive.py" "$OUT_DIR/model-map.json"
    rc=$?
    if [ "$rc" -eq 0 ]; then
        echo "preflight: PASS (resolved interactively; ready-to-run model-map.json written)"
    fi
    exit "$rc"
fi

echo "preflight: PASS (placeholder scaffold written; no Anthropic id)"
echo "  Next: run 'preflight.sh --resolve --interactive' to interactively configure provider keys,"
echo "  or hand-edit model-map.json to replace <CLIENT_PROVIDER_ID>/<CLIENT_MODEL> placeholders."
exit 0

#!/usr/bin/env bash
# 59-anthology-engine/preflight.sh -- resolve the engine tier map per box.
# ----------------------------------------------------------------------------
# Reads config/model-map.template.json and writes a resolved model-map.json into
# the run dir (or the skill dir if no --run-dir), keeping each capability TIER
# (HEAVY-WRITER / LIGHT / JUDGE / LONGCTX / IMAGE) and its ordered provider chain.
# The real per-box resolution (filling each <CLIENT_*> slot from the CLIENT's own
# configured providers by label) is wired by the fleet installer. This resolver
# emits the scaffold and asserts the template carries no Anthropic-family id. It
# NEVER writes an Anthropic-family id and NEVER an operator key.
#
# MODES:
#   (default) RESOLVE -- write a resolved model-map.json scaffold into OUT_DIR.
#   --check           -- PRE-GATE: read an existing OUT_DIR/model-map.json and
#                        fail-closed if it still carries <CLIENT_*> placeholders
#                        (AF-AE-UNRESOLVED-MODELMAP) or an Anthropic-family id
#                        (AF-AE-ANTHROPIC). A missing map is a clean pass (the
#                        installer resolves per box).
#
# Exit 0 = ok; 2 = banned id / residual placeholder (fail-closed); 3 = usage.
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
TEMPLATE="$SELF_DIR/config/model-map.template.json"
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
    OUT_DIR="$OUT_DIR" python3 - <<'PY'
import json, os, re, sys
mp = os.path.join(os.environ["OUT_DIR"], "model-map.json")
if not os.path.isfile(mp):
    print("  preflight --check: no resolved model-map.json (installer resolves per box) -- OK")
    sys.exit(0)
try:
    blob = open(mp, "r", encoding="utf-8").read()
    data = json.loads(blob)
except Exception as exc:
    print("AF-AE-UNRESOLVED-MODELMAP: model-map.json unreadable/invalid: %s" % exc, file=sys.stderr)
    sys.exit(2)
residual = sorted(set(re.findall(r"<CLIENT[A-Z0-9_]*>|<CLIENT_[^>]*>", blob)))
if residual:
    print("AF-AE-UNRESOLVED-MODELMAP: model-map.json still carries placeholder(s): %s"
          % ", ".join(residual), file=sys.stderr)
    sys.exit(2)
# Deny Anthropic-family identifiers. The banned id shapes are assembled from
# fragments so no contiguous banned literal ever lives in this file.
_a = "anthro" + "pic"
_c = "clau" + "de-"
banned = re.compile(_c + r"|" + _a + r"/|us\." + _a + r"\.", re.I)
def scan(node, path):
    if isinstance(node, dict):
        for k, v in node.items():
            scan(v, path + "." + str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            scan(v, "%s[%d]" % (path, i))
    elif isinstance(node, str):
        if banned.search(node):
            print("AF-AE-ANTHROPIC: resolved map carries a banned id at %s: %r" % (path, node), file=sys.stderr)
            sys.exit(2)
scan(data.get("tiers", {}), "tiers")
print("  preflight --check: resolved model-map.json OK (no residual placeholder, no Anthropic-family id)")
sys.exit(0)
PY
    exit $?
fi

[ -f "$TEMPLATE" ] || { echo "FATAL: template not found: $TEMPLATE" >&2; exit 3; }

TEMPLATE="$TEMPLATE" OUT_DIR="$OUT_DIR" python3 - <<'PY'
import json, os, re, sys
tmpl = json.load(open(os.environ["TEMPLATE"]))
_a = "anthro" + "pic"
_c = "clau" + "de-"
banned = re.compile(_c + r"|" + _a + r"/|us\." + _a + r"\.", re.I)
tiers = tmpl.get("tiers", {})
# fail-closed: the shipped template must never carry an Anthropic-family id
def scan(node, path):
    if isinstance(node, dict):
        for k, v in node.items():
            scan(v, path + "." + str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            scan(v, "%s[%d]" % (path, i))
    elif isinstance(node, str):
        if banned.search(node):
            print("AF-AE-ANTHROPIC: template carries a banned id at %s: %r" % (path, node), file=sys.stderr)
            sys.exit(2)
scan(tiers, "tiers")
resolved = {
    "skill": "anthology-engine",
    "resolved_per_box": True,
    "note": "Scaffold -- the fleet installer fills each <CLIENT_*> slot from the CLIENT's own configured providers by label. NEVER an Anthropic-family id, NEVER operator keys.",
    "deny_policy": tmpl.get("deny_policy", {}),
    "tiers": tiers,
    "no_formatter_tier": True,
}
out = os.path.join(os.environ["OUT_DIR"], "model-map.json")
json.dump(resolved, open(out, "w"), indent=2)
print("  resolved model-map.json ->", out)
for name in tiers:
    print("   tier %-13s -> client's own NON-Anthropic chain (resolved per box)" % name)
PY
rc=$?
[ "$rc" -eq 0 ] && echo "preflight: PASS (no Anthropic-family id; client tiers scaffolded)"
exit "$rc"

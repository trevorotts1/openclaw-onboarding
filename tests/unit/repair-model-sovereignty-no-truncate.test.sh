#!/usr/bin/env bash
# tests/unit/repair-model-sovereignty-no-truncate.test.sh
# -----------------------------------------------------------------------------
# CI guard (D23): scripts/repair-model-sovereignty.sh must NEVER truncate a
# box's fallback chain. It used to cap agents.defaults.model.fallbacks (and the
# subagents + agents.list[*] chains) to 3 entries on every roll, silently
# deleting operator-ordered outage backups: on Dr. Stephanie Brown's box
# (openclaw-a3go) the 4th fallback openrouter/z-ai/glm-5.3-flash was dropped at
# 13:17Z by the roll that ran this script.
#
#   N1  4 default fallbacks (last one OpenRouter), defaults + subagents: the
#       file is byte-for-byte unchanged after --apply, receipt has no depth cap.
#   N2  a legacy agents.list agent with 6 legitimate fallbacks: all 6 kept.
#   N3  the scrub still works: a chain with an Anthropic slug and a -preview
#       slug among 4 legitimate entries loses ONLY those two; the 4 legitimate
#       ones (incl. the OpenRouter last entry) survive in order.
#
# Hermetic: own mktemp sandbox, a stub `openclaw` first on PATH (so the
# post-apply `openclaw config validate` never touches a real box config), no
# network, no credentials. bash 3.2-safe.
# Run: bash tests/unit/repair-model-sovereignty-no-truncate.test.sh
# -----------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/repair-model-sovereignty.sh"
SU="$REPO_ROOT/shared-utils"
PASS=0; FAIL=0
ok()  { printf '  ok   %s\n' "$1"; PASS=$((PASS + 1)); }
bad() { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL + 1)); }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
mkdir -p "$SANDBOX/bin"
printf '#!/bin/sh\nexit 0\n' > "$SANDBOX/bin/openclaw"
chmod +x "$SANDBOX/bin/openclaw"

run_repair() { # <config> <receipt-dir>
  PATH="$SANDBOX/bin:$PATH" bash "$SCRIPT" --config "$1" --receipt-dir "$2" \
    --box t --apply --shared-utils "$SU" >"$2.out" 2>&1
}

# ── N1 ──
python3 - "$SANDBOX/n1.json" <<'EOF'
import json, sys
fb = ["agnes/agnes-2.5-flash", "ollama/kimi-k2.6:cloud",
      "ollama/gemma4:31b-cloud", "openrouter/z-ai/glm-5.3-flash"]
prim = "ollama/glm-5.3-flash:cloud"
json.dump({"agents": {"defaults": {
    "model": {"primary": prim, "fallbacks": fb},
    "subagents": {"model": {"primary": prim, "fallbacks": fb}},
    "models": {m: {} for m in [prim] + fb}}}}, open(sys.argv[1], "w"), indent=2)
EOF
cp "$SANDBOX/n1.json" "$SANDBOX/n1.orig"
run_repair "$SANDBOX/n1.json" "$SANDBOX/r1"
if cmp -s "$SANDBOX/n1.json" "$SANDBOX/n1.orig"; then
  ok "N1a: 4-entry defaults + subagents chains untouched (file byte-identical)"
else
  bad "N1a: the roll changed a clean 4-fallback config (truncation regression)"
fi
if grep -q depth_caps "$SANDBOX/r1/t.json" 2>/dev/null; then
  bad "N1b: receipt still reports depth_caps"
else
  ok "N1b: receipt has no depth cap"
fi

# ── N2 ──
python3 - "$SANDBOX/n2.json" <<'EOF'
import json, sys
fb = ["ollama/a:cloud", "openrouter/b", "ollama/c:cloud", "openrouter/d",
      "ollama/e:cloud", "openrouter/f"]
prim = "ollama/p:cloud"
json.dump({"agents": {"defaults": {"models": {m: {} for m in [prim] + fb}},
    "list": [{"id": "dept-x", "model": {"primary": prim, "fallbacks": fb}}]}},
    open(sys.argv[1], "w"), indent=2)
EOF
run_repair "$SANDBOX/n2.json" "$SANDBOX/r2"
if python3 - "$SANDBOX/n2.json" <<'EOF'
import json, sys
fb = json.load(open(sys.argv[1]))["agents"]["list"][0]["model"]["fallbacks"]
sys.exit(0 if fb == ["ollama/a:cloud", "openrouter/b", "ollama/c:cloud",
                     "openrouter/d", "ollama/e:cloud", "openrouter/f"] else 1)
EOF
then ok "N2: legacy agents.list agent keeps all 6 fallbacks"
else bad "N2: agents.list fallbacks were truncated or reordered"; fi

# ── N3 ──
python3 - "$SANDBOX/n3.json" <<'EOF'
import json, sys
fb = ["agnes/agnes-2.5-flash", "anthropic/claude-x", "ollama/kimi-k2.6:cloud",
      "google/gemini-x-preview", "ollama/gemma4:31b-cloud",
      "openrouter/z-ai/glm-5.3-flash"]
prim = "ollama/glm-5.3-flash:cloud"
json.dump({"agents": {"defaults": {"model": {"primary": prim, "fallbacks": fb},
    "models": {m: {} for m in [prim] + fb}}}}, open(sys.argv[1], "w"), indent=2)
EOF
run_repair "$SANDBOX/n3.json" "$SANDBOX/r3"
if python3 - "$SANDBOX/n3.json" <<'EOF'
import json, sys
fb = json.load(open(sys.argv[1]))["agents"]["defaults"]["model"]["fallbacks"]
sys.exit(0 if fb == ["agnes/agnes-2.5-flash", "anthropic/claude-x",
                     "ollama/kimi-k2.6:cloud", "ollama/gemma4:31b-cloud",
                     "openrouter/z-ai/glm-5.3-flash"] else 1)
EOF
then ok "N3: -preview scrubbed; the Anthropic fallback and the 4 other fallbacks kept in order"
else bad "N3: scrub wrong (expected the 5 legitimate entries incl. the Anthropic one, -preview removed)"; fi

printf '\n----------------------------------------\n'
printf 'repair-model-sovereignty-no-truncate: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0

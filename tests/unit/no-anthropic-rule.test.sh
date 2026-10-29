#!/usr/bin/env bash
# tests/unit/no-anthropic-rule.test.sh
# -----------------------------------------------------------------------------
# CI guard: there is NO rule against Anthropic / Claude models (Trevor order
# 2026-10-29). Before this change the fleet update path (update-skills.sh ->
# apply-fleet-standards.sh -> repair-model-sovereignty.sh) silently stripped an
# Anthropic fallback, the anthropic provider block, the anthropic plugin entry and
# the anthropic plugins.allow id from a client's openclaw.json (Talaya Kelley lost
# openrouter/anthropic/claude-haiku-4.5 that way on 2026-10-29).
#
# WHAT THIS PROVES (hermetic: its own mktemp HOME, a stub `openclaw`, no network):
#   N1  repair-model-sovereignty.sh --apply on a planted config that carries an
#       Anthropic fallback + provider + plugin entry + plugins.allow id leaves the
#       file BYTE-IDENTICAL and records zero strip actions / fallback scrubs.
#   N2  the WHOLE fleet-standards roll (scripts/apply-fleet-standards.sh, which runs
#       the sovereignty repair as step 4a) keeps all four Anthropic items intact
#       (model, provider, plugin entry, plugins.allow compared as parsed JSON).
#   N3  control: the same roll still scrubs a `-preview` fallback and the free
#       sentinel (the rest of the sweep still works; we only removed the vendor rule).
#   N4  the selectors never forbid an Anthropic-family id (FORBIDDEN_PREFIXES empty).
# bash 3.2-safe. Run: bash tests/unit/no-anthropic-rule.test.sh
# -----------------------------------------------------------------------------
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { printf '  ok   %s\n' "$1"; PASS=$((PASS + 1)); }
bad() { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL + 1)); }

SB="$(mktemp -d)"; trap 'rm -rf "$SB"' EXIT
mkdir -p "$SB/bin" "$SB/home/.openclaw"
cat > "$SB/bin/openclaw" <<'STUB'
#!/bin/sh
case "$1" in
  --version) echo "OpenClaw 2026.10.8 (stub)";;
  plugins) echo '{"plugins":[{"id":"anthropic","origin":"bundled"},{"id":"moonshot","origin":"bundled"}]}';;
  *) exit 0;;
esac
STUB
chmod +x "$SB/bin/openclaw"

plant() { # <file> [extra-fallback ...]
  python3 - "$@" <<'PY'
import json, sys
path, extra = sys.argv[1], sys.argv[2:]
cfg = {"agents": {"defaults": {
         "model": {"primary": "ollama/glm-5.3-flash:cloud",
                   "fallbacks": ["openrouter/anthropic/claude-haiku-4.5"] + extra + ["agnes/agnes-3.0-flash"]},
         "models": {"openrouter/anthropic/claude-haiku-4.5": {}}}},
       "models": {"providers": {"anthropic": {"baseUrl": "https://api.anthropic.com", "timeoutSeconds": 120},
                                "ollama": {"baseUrl": "https://ollama.com/v1"}}},
       "plugins": {"allow": ["anthropic", "moonshot"],
                   "entries": {"anthropic": {"enabled": True}, "moonshot": {"enabled": True}}}}
json.dump(cfg, open(path, "w"), indent=2)
PY
}

# ── N1: repair-model-sovereignty.sh alone ──
plant "$SB/n1.json"; cp "$SB/n1.json" "$SB/n1.orig"
PATH="$SB/bin:$PATH" bash "$REPO_ROOT/scripts/repair-model-sovereignty.sh" --config "$SB/n1.json" \
  --receipt-dir "$SB/r1" --box t --apply --shared-utils "$REPO_ROOT/shared-utils" >"$SB/n1.out" 2>&1
if cmp -s "$SB/n1.json" "$SB/n1.orig"; then ok "N1a: Anthropic fallback/provider/plugin/allow left BYTE-IDENTICAL by the repair sweep"
else bad "N1a: repair-model-sovereignty.sh changed a config that only carries Anthropic items"; fi
if python3 - "$SB/r1/t.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
sys.exit(0 if (not any(r["strip_actions"].values()) and r["fallback_scrubs"] == [] and r["clean"]) else 1)
PY
then ok "N1b: receipt records zero strip actions, zero fallback scrubs, clean=true"
else bad "N1b: receipt reports strip/scrub actions for Anthropic items"; fi

# ── N2 / N3: the whole fleet-standards roll in a sandbox HOME ──
plant "$SB/home/.openclaw/openclaw.json" "google/gemini-x-preview"
cp "$SB/home/.openclaw/openclaw.json" "$SB/n2.orig"
( cd "$REPO_ROOT/scripts" && HOME="$SB/home" PATH="$SB/bin:$PATH" bash apply-fleet-standards.sh ) >"$SB/n2.out" 2>&1
n2rc=$?
[ "$n2rc" -eq 0 ] && ok "N2a: the fleet-standards roll completes (rc 0)" || bad "N2a: roll exited $n2rc: $(tail -3 "$SB/n2.out")"
if python3 - "$SB/n2.orig" "$SB/home/.openclaw/openclaw.json" <<'PY'
import json, sys
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
fb = b["agents"]["defaults"]["model"]["fallbacks"]
ok = (b["models"]["providers"]["anthropic"] == a["models"]["providers"]["anthropic"]
      and b["plugins"]["entries"]["anthropic"] == a["plugins"]["entries"]["anthropic"]
      and "anthropic" in b["plugins"]["allow"]
      and "openrouter/anthropic/claude-haiku-4.5" in fb
      and "openrouter/anthropic/claude-haiku-4.5" in b["agents"]["defaults"]["models"])
sys.exit(0 if ok else 1)
PY
then ok "N2b: after the whole roll the Anthropic fallback, provider, plugin entry and plugins.allow id are intact"
else bad "N2b: the roll removed an Anthropic item"; fi
if python3 - "$SB/home/.openclaw/openclaw.json" <<'PY'
import json, sys
fb = json.load(open(sys.argv[1]))["agents"]["defaults"]["model"]["fallbacks"]
sys.exit(0 if fb == ["openrouter/anthropic/claude-haiku-4.5", "agnes/agnes-3.0-flash"] else 1)
PY
then ok "N3: control -- the -preview fallback was still scrubbed, the Anthropic one kept, order preserved"
else bad "N3: fallbacks after the roll are not [anthropic haiku, agnes]"; fi

# ── N4: the selectors ──
if python3 - "$REPO_ROOT/shared-utils" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import select_model as sm
ids = ["anthropic/claude-opus-5", "openrouter/anthropic/claude-haiku-4.5", "claude-sonnet-5", "us.anthropic.claude-3"]
sys.exit(0 if sm.FORBIDDEN_PREFIXES == () and not any(sm._is_forbidden(i) for i in ids) else 1)
PY
then ok "N4: select_model forbids no Anthropic-family id"; else bad "N4: select_model still forbids an Anthropic-family id"; fi

printf '\n----------------------------------------\n'
printf 'no-anthropic-rule: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1

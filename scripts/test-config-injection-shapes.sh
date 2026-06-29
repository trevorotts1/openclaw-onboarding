#!/usr/bin/env bash
# test-config-injection-shapes.sh (v16.1.4)
#
# CI guard for the three config-injection bugs fixed in v16.1.4. FAILS if any
# write-site can produce — or the self-heal fails to repair — one of the three
# schema-invalid shapes (all proven against the live `openclaw config schema` on
# gateway 2026.5.28 + 2026.6.8):
#
#   B1  flat plugins.entries.active-memory option keys (must nest under config)
#         validator: "plugins.entries.active-memory: Invalid input"
#   B2  helpChatId on a telegram account (additionalProperties:false; co-mingling)
#         validator: '... accounts.operator: ... additional properties: "helpChatId"'
#   B3  channels.bindings / legacy flat binding shape (bindings is TOP-LEVEL,
#         entries are {agentId, match:{...}})
#         validator: "channels.bindings: unknown channel id: bindings"
#
# The guard is self-contained (stdlib python + bash only) so it runs in CI with
# NO gateway installed: it exercises the canonical healer and the operator
# telegram script against seeded bad configs and asserts the output shapes,
# idempotency, and the --check contract, plus static source invariants on the
# four write-sites.
#
# Security note: consumes only repo file content + locally-seeded fixtures (no
# untrusted GitHub event fields), so there is no injection surface.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HEAL="$SCRIPT_DIR/heal-config-shapes.py"
OPTG="$SCRIPT_DIR/configure-operator-telegram.sh"

PASS=0
FAIL=0
ok()  { printf '  PASS  %s\n' "$*"; PASS=$((PASS + 1)); }
nope(){ printf '  FAIL  %s\n' "$*"; FAIL=$((FAIL + 1)); }

TMP="$(mktemp -d 2>/dev/null || mktemp -d -t cfgshapes)"
trap 'rm -rf "$TMP"' EXIT

# Seed a config carrying ALL THREE bad shapes. $1 = operator botToken ("" = none).
seed_all_bad() {
  local optoken="$1" dest="$2"
  OP_TOKEN="$optoken" DEST="$dest" python3 <<'PY'
import json, os
op = os.environ["OP_TOKEN"]
operator = {"dmPolicy": "allowlist", "allowFrom": ["5252140759"], "helpChatId": "999"}
if op:
    operator["botToken"] = op
cfg = {
    "channels": {
        "telegram": {
            "botToken": "client-token", "allowFrom": ["111"], "helpChatId": "top-bad",
            "accounts": {
                "default": {"botToken": "client-token", "dmPolicy": "pairing", "allowFrom": ["111"]},
                "operator": operator,
            },
        },
        "bindings": [{"channel": "telegram", "accountId": "operator", "agentId": "main"}],
    },
    "plugins": {"entries": {"active-memory": {
        "enabled": True, "agents": ["main"], "allowedChatTypes": ["direct"],
        "queryMode": "recent", "promptStyle": "balanced", "timeoutMs": 15000,
        "maxSummaryChars": 220,
    }}},
}
json.dump(cfg, open(os.environ["DEST"], "w"), indent=2)
PY
}

# Assert a config file is FREE of all three bad shapes (the only valid end-state).
assert_clean() {
  local cfgf="$1" desc="$2"
  if CFG="$cfgf" python3 <<'PY'
import json, os, sys
c = json.load(open(os.environ["CFG"]))
TOP = {"enabled", "hooks", "subagent", "llm", "config"}
errs = []
for pid, e in (c.get("plugins") or {}).get("entries", {}).items():
    if isinstance(e, dict):
        stray = [k for k in e if k not in TOP]
        if stray:
            errs.append("B1 plugins.entries.%s flat keys %s" % (pid, stray))
tg = (c.get("channels") or {}).get("telegram") or {}
if "helpChatId" in tg:
    errs.append("B2 helpChatId on channels.telegram")
for aid, a in (tg.get("accounts") or {}).items():
    if isinstance(a, dict) and "helpChatId" in a:
        errs.append("B2 helpChatId on account %s" % aid)
if "bindings" in (c.get("channels") or {}):
    errs.append("B3 channels.bindings present")
for i, b in enumerate(c.get("bindings") or []):
    if not isinstance(b, dict) or not isinstance(b.get("match"), dict):
        errs.append("B3 top-level bindings[%d] not match-shape" % i)
if errs:
    sys.stderr.write("    " + "; ".join(errs) + "\n")
    sys.exit(1)
PY
  then ok "$desc"; else nope "$desc"; fi
}

echo "== 0. heal-config-shapes.py compiles =="
if python3 -m py_compile "$HEAL"; then ok "heal-config-shapes.py py_compile"; else nope "heal-config-shapes.py py_compile"; fi

echo "== 1. healer repairs all three shapes -> clean =="
C1="$TMP/c1.json"; seed_all_bad "op-token" "$C1"
[ -f "$C1" ] && ok "fixture seeded" || nope "fixture seeded"
python3 "$HEAL" "$C1" >/dev/null
assert_clean "$C1" "all three shapes healed"
# operator route is kept (token present) and reshaped to {agentId, match}
if CFG="$C1" python3 -c "import json,os;b=json.load(open(os.environ['CFG'])).get('bindings',[]);import sys;sys.exit(0 if any(x.get('agentId')=='main' and x.get('match',{}).get('accountId')=='operator' for x in b) else 1)"; then
  ok "operator route preserved as match-shape (token present)"; else nope "operator route preserved"; fi

echo "== 2. healer is idempotent =="
H1="$(shasum "$C1" | awk '{print $1}')"; python3 "$HEAL" "$C1" >/dev/null
H2="$(shasum "$C1" | awk '{print $1}')"
[ "$H1" = "$H2" ] && ok "second heal is a no-op" || nope "second heal changed the file"

echo "== 3. --check contract =="
python3 "$HEAL" --check "$C1" >/dev/null 2>&1 && ok "--check exit 0 on clean" || nope "--check should be 0 on clean"
C3="$TMP/c3.json"; seed_all_bad "op-token" "$C3"
python3 "$HEAL" --check "$C3" >/dev/null 2>&1; rc=$?
[ "$rc" = "3" ] && ok "--check exit 3 on bad shape" || nope "--check should exit 3 on bad (got $rc)"

echo "== 4. token-less operator route is dropped (inert) + channels.bindings removed =="
C4="$TMP/c4.json"; seed_all_bad "" "$C4"   # operator has NO token
python3 "$HEAL" "$C4" >/dev/null
assert_clean "$C4" "token-less config healed clean"
if CFG="$C4" python3 -c "import json,os;b=json.load(open(os.environ['CFG'])).get('bindings',[]);import sys;sys.exit(0 if not any(x.get('match',{}).get('accountId')=='operator' for x in b) else 1)"; then
  ok "inert token-less operator route dropped"; else nope "inert operator route NOT dropped"; fi

echo "== 5. configure-operator-telegram.sh self-heals an already-corrupted box =="
OH="$TMP/ophome"; mkdir -p "$OH/.openclaw/scripts"
cp "$OPTG" "$OH/.openclaw/scripts/"; cp "$HEAL" "$OH/.openclaw/scripts/"
seed_all_bad "op-token" "$OH/.openclaw/openclaw.json"
HOME="$OH" bash "$OH/.openclaw/scripts/configure-operator-telegram.sh" >/dev/null 2>&1 || true
assert_clean "$OH/.openclaw/openclaw.json" "configure-operator-telegram.sh produced a clean config"

echo "== 6. static source invariants (write-sites cannot emit a bad shape) =="
# B1: no write-site DELETES active-memory; the writers nest under config.
for f in install.sh scripts/update-skills.sh scripts/fix-active-memory-bug.sh; do
  if grep -Eq "del[[:space:]]+entries\[[\"']active-memory[\"']\]" "$REPO_ROOT/$f"; then
    nope "$f still DELETES active-memory"; else ok "$f does not delete active-memory"; fi
done
if grep -Eq '"enabled": True, "agents"' "$REPO_ROOT/scripts/update-skills.sh"; then
  nope "scripts/update-skills.sh still writes the flat active-memory literal"
else ok "scripts/update-skills.sh has no flat active-memory literal"; fi
# B2: operator-telegram script never WRITES helpChatId (pop/strip is allowed).
if grep -Eq 'helpChatId"?\][[:space:]]*=|setdefault\("helpChatId"' "$REPO_ROOT/scripts/configure-operator-telegram.sh"; then
  nope "configure-operator-telegram.sh still WRITES helpChatId"
else ok "configure-operator-telegram.sh never writes helpChatId"; fi
# B3: operator-telegram script writes TOP-LEVEL bindings, never channels.bindings.
if grep -Eq 'setdefault\("channels", \{\}\)\.setdefault\("bindings"|\["channels"\]\["bindings"\][[:space:]]*=' "$REPO_ROOT/scripts/configure-operator-telegram.sh"; then
  nope "configure-operator-telegram.sh still writes channels.bindings"
else ok "configure-operator-telegram.sh does not write channels.bindings"; fi
if grep -q 'cfg.setdefault("bindings"' "$REPO_ROOT/scripts/configure-operator-telegram.sh"; then
  ok "configure-operator-telegram.sh writes top-level bindings"
else nope "configure-operator-telegram.sh does not write top-level bindings"; fi

echo ""
echo "================ config-injection-shapes guard: $PASS passed, $FAIL failed ================"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL GREEN — none of the three bad shapes (flat active-memory / helpChatId / channels.bindings) can be produced; self-heal repairs each."

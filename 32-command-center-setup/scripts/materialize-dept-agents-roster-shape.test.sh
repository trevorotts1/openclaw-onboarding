#!/bin/bash
#
# materialize-dept-agents-roster-shape.test.sh
#
# 2026-09-04 incident. materialize-dept-agents.sh created
# cfg["agents"]["list"] UNCONDITIONALLY:
#
#     cfg["agents"] = {"list": []}
#   if "list" not in cfg["agents"] or not isinstance(cfg["agents"]["list"], list):
#       cfg["agents"]["list"] = []
#
# A schema-valid modern OpenClaw config CANNOT CONTAIN agents.list -- AgentsSchema
# is .strict() with exactly {ownership, defaults, entries} -- so on any migrated
# box that one key invalidated the whole config:
#
#     x openclaw.json:2 - agents: Unrecognized key: "list"
#
# Observed on the operator Mac: a config that validated rc=0 (agents.entries, 92
# agents) validated rc=1 after one `update-skills.sh --only 23` run, and the
# gateway wedged (port held, HTTP 200, websocket probe timing out) until the key
# was removed. Migrating forward is effectively mandatory now, so EVERY client on
# a migrated config had their own routine update invalidate their config -- and
# the remedy the validator prints (`openclaw doctor --fix`) has been observed on
# this fleet to restore an older last-known-good and silently DROP departments.
#
# Usage:
#   bash 32-command-center-setup/scripts/materialize-dept-agents-roster-shape.test.sh
#
# Pass criteria:
#   1. bash -n passes and every python heredoc compiles.
#   2. MODERN config (agents.entries, NO agents.list): departments are registered
#      into agents.entries, agents.list is NEVER created, no entry carries an "id"
#      key, no entry carries a top-level "memorySearch" key, and (when the
#      openclaw CLI is present) `openclaw config validate` returns 0.
#   3. LEGACY config (agents.list, no agents.entries): still registers into
#      agents.list[] and NEVER creates agents.entries -- the deployed runtime on
#      those boxes has no entries reader, so writing the new shape there would
#      enumerate ZERO agents.
#   4. IDEMPOTENT: a second run produces a byte-identical config.
#   5. A dept folder whose slug cannot be a schema-valid entries key is
#      NORMALIZED (never silently dropped), and two folders that normalize to the
#      SAME agent id are a LOUD FATAL with the config left untouched.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/32-command-center-setup/scripts/materialize-dept-agents.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*" >&2; exit 1; }
skip() { echo "[SKIP] $*"; }

# ─── G0: syntax ──────────────────────────────────────────────────────────────
bash -n "$SCRIPT" || fail "bash -n materialize-dept-agents.sh failed"
pass "bash -n materialize-dept-agents.sh passes"

python3 - "$SCRIPT" <<'PYEOF' || fail "a python heredoc inside materialize-dept-agents.sh does not compile"
import io, re, sys
path = sys.argv[1]
lines = io.open(path, encoding="utf-8").read().split("\n")
start = re.compile(r"python3\s+-?\s*<<\s*'([A-Za-z0-9_]+)'")
found = 0
i = 0
while i < len(lines):
    m = start.search(lines[i])
    if m:
        tag, j, body = m.group(1), i + 1, []
        while j < len(lines) and lines[j].strip() != tag:
            body.append(lines[j]); j += 1
        if j >= len(lines):
            print("unterminated heredoc %s" % tag); raise SystemExit(1)
        compile("\n".join(body), "%s@%d" % (tag, i + 2), "exec")
        found += 1
        i = j + 1
        continue
    i += 1
if found == 0:
    print("extractor found NO heredocs -- the check itself is broken"); raise SystemExit(1)
print("compiled %d python heredocs" % found)
PYEOF
pass "every python heredoc in materialize-dept-agents.sh compiles independently"

# ─── Hermetic fake box ───────────────────────────────────────────────────────
mkbox() {
  local box="$1" cfg="$2"; shift 2
  rm -rf "$box"
  mkdir -p "$box/.openclaw/workspace/departments"
  printf '%s' "$cfg" > "$box/.openclaw/openclaw.json"
  printf '{"interviewComplete": true, "companySlug": "roster-shape-fixture"}' \
    > "$box/.openclaw/workspace/.workforce-build-state.json"
  local s
  for s in "$@"; do mkdir -p "$box/.openclaw/workspace/departments/$s"; done
}

runbox() {  # runbox <box> ; prints output, returns the script's real exit code
  local box="$1" rc=0
  env -i PATH="$PATH" HOME="$box" LANG="${LANG:-C}" bash "$SCRIPT" > "$box/run.out" 2>&1 || rc=$?
  cat "$box/run.out"
  return $rc
}

cfg_probe() {  # cfg_probe <config> <python-expr over `ag`>
  CFG="$1" EXPR="$2" python3 -c '
import json, os, sys
ag = (json.load(open(os.environ["CFG"])).get("agents") or {})
sys.stdout.write(str(eval(os.environ["EXPR"])))
'
}

validate() {  # validate <box> <config> -> rc, or 99 when the CLI is absent
  command -v openclaw >/dev/null 2>&1 || return 99
  HOME="$1" OPENCLAW_CONFIG_PATH="$2" openclaw config validate >/dev/null 2>&1
}

MODERN='{"agents":{"ownership":"explicit","entries":{
  "main":{"name":"Main","workspace":"~/.openclaw/workspace"},
  "dept-marketing":{"name":"Chief Marketing Officer","workspace":"/stale/path",
    "memory":{"search":{"extraPaths":[],"multimodal":{"enabled":true,"modalities":["all"]},"fallback":"none"}}}}}}'
LEGACY='{"agents":{"list":[
  {"id":"main","name":"Main","workspace":"~/.openclaw/workspace"}]}}'

# ─── T1: MODERN config -- entries only, agents.list never created ────────────
BOX="$WORK/modern"
mkbox "$BOX" "$MODERN" marketing sales video
OUT1="$(runbox "$BOX")" || fail "T1: script exited non-zero: $OUT1"
CFG="$BOX/.openclaw/openclaw.json"

[ "$(cfg_probe "$CFG" "'list' in ag")" = "False" ] \
  || fail "T1: agents.list WAS CREATED on a modern config -- this is the bug. $(cat "$CFG")"
pass "T1: agents.list is NEVER created on a modern (agents.entries) config"

for want in dept-marketing dept-sales dept-video; do
  [ "$(cfg_probe "$CFG" "'$want' in ag['entries']")" = "True" ] \
    || fail "T1: $want was not registered into agents.entries"
done
pass "T1: every department is registered into agents.entries"

[ "$(cfg_probe "$CFG" "[k for k,v in ag['entries'].items() if isinstance(v,dict) and 'id' in v]")" = "[]" ] \
  || fail "T1: an agents.entries value carries an \"id\" key -- agents.entries.<id> rejects it"
pass "T1: no agents.entries value carries an \"id\" key (the key IS the id)"

[ "$(cfg_probe "$CFG" "[k for k,v in ag['entries'].items() if isinstance(v,dict) and 'memorySearch' in v]")" = "[]" ] \
  || fail "T1: an agents.entries value carries a top-level \"memorySearch\" key -- the schema rejects it"
pass "T1: memory search lives at entry.memory.search, not a top-level memorySearch"

[ "$(cfg_probe "$CFG" "ag['entries']['dept-marketing']['memory']['search']['multimodal']['enabled']")" = "False" ] \
  || fail "T1: the multimodal.enabled=false migration did not reach entry.memory.search (a copy was mutated, not the live config)"
[ "$(cfg_probe "$CFG" "ag['entries']['dept-marketing']['memory']['search']['fallback']")" = "openai" ] \
  || fail "T1: the fallback migration did not reach entry.memory.search"
pass "T1: the in-place memory-search migrations reach the LIVE config, not a copy"

if validate "$BOX" "$CFG"; then
  pass "T1: openclaw config validate returns 0 on the resulting config"
else
  rc=$?
  [ "$rc" = "99" ] && skip "T1: openclaw CLI not on PATH -- validate NOT run (structural checks above still ran)" \
                   || fail "T1: openclaw config validate returned $rc on the resulting config"
fi

# ─── T2: IDEMPOTENCE ─────────────────────────────────────────────────────────
SHA1="$(shasum -a 256 "$CFG" | cut -d' ' -f1)"
runbox "$BOX" >/dev/null || fail "T2: second run exited non-zero"
SHA2="$(shasum -a 256 "$CFG" | cut -d' ' -f1)"
[ "$SHA1" = "$SHA2" ] || fail "T2: NOT idempotent -- config changed on the second run ($SHA1 -> $SHA2)"
pass "T2: a second run leaves the config byte-identical"

# ─── T3: LEGACY config -- still list, entries never created ──────────────────
BOXL="$WORK/legacy"
mkbox "$BOXL" "$LEGACY" marketing sales
OUT3="$(runbox "$BOXL")" || fail "T3: script exited non-zero: $OUT3"
CFGL="$BOXL/.openclaw/openclaw.json"
[ "$(cfg_probe "$CFGL" "'entries' in ag")" = "False" ] \
  || fail "T3: agents.entries was created on a pre-migration box whose runtime has NO entries reader"
[ "$(cfg_probe "$CFGL" "sorted(a.get('id') for a in ag['list'])")" = "['dept-marketing', 'dept-sales', 'main']" ] \
  || fail "T3: legacy registration did not land in agents.list[] as before: $(cfg_probe "$CFGL" "ag['list']")"
pass "T3: a legacy (agents.list) config still registers into agents.list[] and never gains agents.entries"

# ─── T4: non-conforming slug is normalized, never dropped ────────────────────
BOXN="$WORK/oddslug"
mkbox "$BOXN" "$MODERN" "Sales & Marketing"
OUT4="$(runbox "$BOXN")" || fail "T4: script exited non-zero: $OUT4"
CFGN="$BOXN/.openclaw/openclaw.json"
[ "$(cfg_probe "$CFGN" "'dept-sales-marketing' in ag['entries']")" = "True" ] \
  || fail "T4: a dept folder with characters outside the entries key pattern was DROPPED instead of normalized"
pass "T4: a non-conforming dept slug is normalized to a schema-valid key, never dropped"

# ─── T5: two slugs that normalize to the same id are a LOUD FATAL ────────────
BOXC="$WORK/collide"
mkbox "$BOXC" "$MODERN" "Sales & Marketing" "sales-marketing"
CFGC="$BOXC/.openclaw/openclaw.json"
SHA_PRE="$(shasum -a 256 "$CFGC" | cut -d' ' -f1)"
set +e
OUT5="$(runbox "$BOXC")"; RC5=$?
set -e
[ "$RC5" -ne 0 ] || fail "T5: two departments collapsing to one agent id did NOT fail -- a department would be silently dropped"
echo "$OUT5" | grep -q "both normalize to the agent id" \
  || fail "T5: the collision was not reported by name. Output: $OUT5"
[ "$SHA_PRE" = "$(shasum -a 256 "$CFGC" | cut -d' ' -f1)" ] \
  || fail "T5: the config was mutated on the fatal path (partial write)"
pass "T5: a normalization collision is a loud FATAL naming both departments, with no partial write"

# ─── T6: a single-agent entries config gains agents.ownership="explicit" ─────
# Registering departments is what turns a single-agent config multi-agent, and
# the schema then requires ownership="explicit" (or one legacy default=true
# marker). Without it the config this script just wrote fails validation:
#   x agents.ownership: multi-agent rosters require agents.ownership="explicit"
BOXO="$WORK/ownership"
mkbox "$BOXO" '{"agents":{"entries":{"main":{"name":"Main","workspace":"~/.openclaw/workspace"}}}}' marketing sales
OUT6="$(runbox "$BOXO")" || fail "T6: script exited non-zero: $OUT6"
CFGO="$BOXO/.openclaw/openclaw.json"
[ "$(cfg_probe "$CFGO" "ag.get('ownership')")" = "explicit" ] \
  || fail "T6: agents.ownership was not set on a config this run made multi-agent"
if validate "$BOXO" "$CFGO"; then
  pass "T6: a single-agent entries config gains ownership=explicit and still validates"
else
  rc=$?
  [ "$rc" = "99" ] && skip "T6: openclaw CLI not on PATH -- validate NOT run (ownership key check above still ran)" \
                   || fail "T6: openclaw config validate returned $rc after the ownership write"
fi

# An ownership value that is ALREADY present must never be overwritten.
BOXO2="$WORK/ownership-preserved"
mkbox "$BOXO2" '{"agents":{"ownership":"explicit","entries":{"main":{"name":"Main","workspace":"~/.openclaw/workspace"},"other":{"name":"Other","default":true}}}}' marketing
runbox "$BOXO2" >/dev/null || fail "T6b: script exited non-zero"
[ "$(cfg_probe "$BOXO2/.openclaw/openclaw.json" "ag.get('ownership')")" = "explicit" ] \
  || fail "T6b: an existing agents.ownership value was changed"
pass "T6b: an existing agents.ownership value is preserved untouched"

echo ""
echo "All materialize-dept-agents.sh roster-shape tests passed."

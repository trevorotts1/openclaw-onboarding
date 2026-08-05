#!/usr/bin/env bash
# test-ceo-tool-gate.sh — self-test for the CEO routing posture.
#
# SCOPE CHANGE 2026-08-05: the CEO production-tool deny (write/edit/apply_patch/
# browser/canvas/image/process) was RETIRED per Trevor because denying `write`
# while memoryFlush demanded a memory write created a self-blocking loop that ate
# Telegram messages for two weeks. Every assertion about that deny set is GONE.
#
# This test is NOT a skip and NOT a historical record — it still runs and still
# fails CI. What it guards now is (a) that the retired deny STAYS retired, and
# (b) the parts of the routing posture that never had anything to do with the
# loop and are still load-bearing:
#
#   * EXPECT_DENY="" is PINNED — re-adding any production tool to
#     hooks/lib-ceo-tool-gate.sh CEO_GATE_DENY_TOOLS fails this test. That is the
#     regression guard against silently re-creating the two-week outage.
#   * GHL MCP deny (byProvider + name-glob) across all write-sites.
#   * skills:[] on the router, and the router-vs-PA classification (PA-freeze).
#   * per-agent tools schema validity (no sessions/agentToAgent) + self-heal.
#
# Write-sites kept in sync:
#   1. 23-ai-workforce-blueprint/scripts/build-workforce.py  (build-time origin)
#   2. scripts/apply-routing-fix.sh  Layer 5                  (already-built boxes)
#   3. scripts/apply-fleet-standards.sh  re-assert            (fleet roll)
#   4. hooks/lib-ceo-tool-gate.sh                             (grant/verify source)
#
# Then exercises:
#   A. apply-routing-fix.sh L5 applies the surviving posture to an ungated box.
#   B. L5 is idempotent (second run = no-op).
#   C. RETIRED — grant/revoke of the production deny (the deny no longer exists).
#   D. L5 SKIPS while an owner-consent grant is active (never revokes the owner).
#   E. verify-routing.sh G7 evaluates the box.
#
# ⛔ RUN ONLY WITH HOME POINTED AT A SANDBOX. This script reassigns HOME to a
# mktemp dir at section 3, but CEO_CONSENT_FILE is derived from HOME and `rm -f`d
# repeatedly. Invoke as: HOME=/some/sandbox bash scripts/test-ceo-tool-gate.sh
#
# Exit 0 = all pass. Exit 1 = a drift or behavior failure (FATAL).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ONBOARDING_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_WF="$ONBOARDING_DIR/23-ai-workforce-blueprint/scripts/build-workforce.py"
APPLY_FIX="$SCRIPT_DIR/apply-routing-fix.sh"
APPLY_STD="$SCRIPT_DIR/apply-fleet-standards.sh"
GATE_LIB="$ONBOARDING_DIR/hooks/lib-ceo-tool-gate.sh"
GRANT="$SCRIPT_DIR/grant-ceo-consent.sh"
VERIFY="$SCRIPT_DIR/verify-routing.sh"

FAILS=0
_ok()   { printf '[test-ceo-tool-gate] PASS  %s\n' "$*"; }
_bad()  { printf '[test-ceo-tool-gate] FAIL  %s\n' "$*" >&2; FAILS=$((FAILS+1)); }

# Canonical expected sets (the single source of truth this test enforces).
#
# EXPECT_DENY is INTENTIONALLY EMPTY and this emptiness is the assertion. The CEO
# production-tool deny was retired 2026-08-05 (it caused the write-deny/
# memoryFlush loop). If someone re-adds ANY tool to CEO_GATE_DENY_TOOLS, the
# "lib deny set canonical" check below FAILS — that is the point. Do not
# "helpfully" repopulate this string. GHL MCP deny lives in EXPECT_MCP.
EXPECT_DENY=""
# mc-route__route_task = the SHIPPED routing tool (scripts/mc-route.sh impl).
# Its presence is what lets verify-routing.sh G7 clear the INTERIM-exec warning.
# FABLE-5: the allow list ALSO carries the plugin/operational tools the CEO needs
# to function (memory_search/memory_get for active-memory, cron/gateway/nodes) —
# an explicit per-agent tools.allow is a HARD allowlist, so omitting them stripped
# the plugin's tool calls ("No callable tools remain ..."). Keep sorted to match
# the lib's sorted CEO_GATE_ALLOW_TOOLS.
# LOOP FIX 2026-08-05: `write` and `edit` are now REQUIRED members. An explicit
# tools.allow is a HARD allowlist, so omitting write denied it exactly as the
# retired deny did — memoryFlush then ordered a memory write the agent could not
# perform, and it looped. Emptying EXPECT_DENY was not sufficient; this set is the
# other half of the same fix. Removing them here re-creates the two-week outage.
EXPECT_ALLOW="cron discord edit exec gateway mc-route__route_task memory_get memory_search message nodes read sessions_history sessions_list sessions_send slack telegram web_fetch web_search write"
EXPECT_MCP="ghl-community-mcp ghl-mcp"

# ── 1. lib-ceo-tool-gate.sh is the reference; extract its canonical sets ───────
# shellcheck source=/dev/null
. "$GATE_LIB"
# BASH 3.2 SAFETY: macOS /bin/bash 3.2 treats an EMPTY array expanded as
# "${arr[@]}" under `set -u` as an unbound variable and ABORTS. CEO_GATE_DENY_TOOLS
# is now legitimately empty, so every expansion here MUST carry the
# "${arr[@]+"${arr[@]}"}" guard or this test dies before its first assertion.
LIB_DENY=$(printf '%s\n' "${CEO_GATE_DENY_TOOLS[@]+"${CEO_GATE_DENY_TOOLS[@]}"}" | sort | tr '\n' ' ' | sed 's/ $//')
LIB_ALLOW=$(printf '%s\n' "${CEO_GATE_ALLOW_TOOLS[@]+"${CEO_GATE_ALLOW_TOOLS[@]}"}" | sort | tr '\n' ' ' | sed 's/ $//')
LIB_MCP=$(printf '%s\n' "${CEO_GATE_MCP_PROVIDERS[@]+"${CEO_GATE_MCP_PROVIDERS[@]}"}" | sort | tr '\n' ' ' | sed 's/ $//')

[ "$LIB_DENY" = "$EXPECT_DENY" ]   && _ok "lib deny set canonical"   || _bad "lib deny drift: [$LIB_DENY] != [$EXPECT_DENY]"
[ "$LIB_ALLOW" = "$EXPECT_ALLOW" ] && _ok "lib allow set canonical" || _bad "lib allow drift: [$LIB_ALLOW] != [$EXPECT_ALLOW]"
[ "$LIB_MCP" = "$EXPECT_MCP" ]     && _ok "lib mcp set canonical"   || _bad "lib mcp drift: [$LIB_MCP] != [$EXPECT_MCP]"

# ── 2. Each write-site must mention every SURVIVING canonical deny token ──────
# Coarse but effective: a missing token in any site is a drift we must catch.
# RETIRED 2026-08-05: write/edit/apply_patch/browser/canvas/image/process are no
# longer expected in any write-site — they were the loop-causing gate. Only the
# GHL MCP name-globs survive as denies.
for tok in "ghl-community-mcp__\*" "ghl-mcp__\*"; do
  for f in "$BUILD_WF" "$APPLY_FIX" "$APPLY_STD"; do
    if ! grep -qE "\"${tok}\"|'${tok}'" "$f"; then
      _bad "deny token '${tok}' missing from $(basename "$f")"
    fi
  done
done
_ok "surviving deny tokens (GHL MCP globs) present across build-workforce.py / apply-routing-fix.sh / apply-fleet-standards.sh"

# ── 2b. Deny must stay retired AND write/edit must stay GRANTED ────────────────
# Both halves of the same outage, asserted per write-site:
#   (a) no retired production tool may reappear in a CEO_TOOL_DENY block;
#   (b) `write` and `edit` MUST be present in every CEO_TOOL_ALLOW block. An
#       explicit tools.allow is a HARD allowlist, so dropping them denies them
#       exactly as the retired deny did and re-creates the memoryFlush loop.
#
# PRECISION NOTE (2026-08-05): this used to be a blunt single-line scan,
#   grep -nE '^[[:space:]]*"?(write|edit|apply_patch)"?,' | grep -qvE 'GENERATION|allow'
# which cannot tell a deny array from an allow array — it excluded a hit only when
# the literal word "allow" happened to sit on that same line. The moment write/edit
# were legitimately added to CEO_TOOL_ALLOW it fired a FALSE FAILURE. It now parses
# the named DENY and ALLOW blocks and inspects their actual members.
#
# BASH 3.2 NOTE: the checker is written to a temp file and invoked, NOT inlined as
# a heredoc inside $( ). macOS /bin/bash 3.2 scans a command substitution for its
# matching ")" and mis-parses the quotes/parens in the Python body — "unexpected
# EOF while looking for matching `)'" — before the script ever runs.
_CHK_PY="$(mktemp)"
cat >"$_CHK_PY" <<'PY'
import os, re, sys
RETIRED  = {"write", "edit", "apply_patch", "browser", "canvas", "image", "process"}
REQUIRED = {"write", "edit"}
src = open(sys.argv[1], encoding="utf-8").read()

def block(name):
    m = re.search(r'^[ \t]*%s\s*=\s*\[(.*?)^[ \t]*\]' % name, src, re.S | re.M)
    return m.group(1) if m else None

def toks(body):
    if body is None:
        return None
    body = re.sub(r'#[^\n]*', '', body)          # drop comments first
    return {a or b for a, b in re.findall(r'"([^"]*)"|\'([^\']*)\'', body)}

problems, seen_allow = [], False
for n in ("CEO_TOOL_DENY", "_CEO_TOOL_DENY"):
    d = toks(block(n))
    if d is None:
        continue
    bad = sorted(RETIRED & d)
    if bad:
        problems.append("%s re-added retired deny: %s" % (n, ",".join(bad)))
for n in ("CEO_TOOL_ALLOW", "_CEO_TOOL_ALLOW"):
    a = toks(block(n))
    if a is None:
        continue
    seen_allow = True
    missing = sorted(REQUIRED - a)
    if missing:
        problems.append("%s missing required grant: %s" % (n, ",".join(missing)))
if not seen_allow:
    problems.append("no CEO_TOOL_ALLOW block found — parser drift, not a clean file")
print("; ".join(problems) if problems else "OK")
PY

for f in "$BUILD_WF" "$APPLY_FIX" "$APPLY_STD"; do
  _res="$(python3 "$_CHK_PY" "$f" 2>&1)" || _res="PARSE_ERROR (python3 exited non-zero): $_res"
  if [ "$_res" = "OK" ]; then
    _ok "2b: $(basename "$f") — deny stays retired, write+edit stay granted"
  else
    _bad "2b: $(basename "$f") — $_res"
  fi
done
rm -f "$_CHK_PY"

# Each site must deny BOTH GHL MCP providers.
for prov in "ghl-community-mcp" "ghl-mcp"; do
  for f in "$BUILD_WF" "$APPLY_FIX" "$APPLY_STD"; do
    grep -q "\"${prov}\"" "$f" || _bad "MCP provider '${prov}' missing from $(basename "$f")"
  done
done
_ok "both GHL MCP providers denied across all write-sites"

# ── 3. Behavior tests in a sandbox HOME ──────────────────────────────────────
SB="$(mktemp -d)"; STUB="$(mktemp -d)"
trap 'rm -rf "$SB" "$STUB"' EXIT
export HOME="$SB"
mkdir -p "$HOME/.openclaw/workspace" "$HOME/.openclaw/state" "$HOME/projects/command-center"
# stub openclaw so `config validate` / `gateway reload` are no-ops
printf '#!/bin/sh\nexit 0\n' > "$STUB/openclaw"; chmod +x "$STUB/openclaw"
export PATH="$STUB:$PATH"
export CEO_CONSENT_FILE="$HOME/.openclaw/state/ceo-consent.json"

_write_ungated() {
  cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "list": [ { "id": "main", "default": true, "skills": [] } ] } }
JSON
}

# A. apply gate
_write_ungated
bash "$APPLY_FIX" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
m=[a for a in json.load(open(sys.argv[1]))["agents"]["list"] if a["id"]=="main"][0]
t=m.get("tools",{})
# RETIRED 2026-08-05: the production-deny assertion (need ⊆ deny) is gone.
# The surviving posture is: GHL MCP denied by provider, exec allowed (routing
# path), skills:[] preserved. Also assert the retired deny did NOT come back.
RETIRED={"write","edit","apply_patch","browser","canvas","image","process"}
deny=set(t.get("deny") or [])
ok = (t.get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")==["*"]) and \
     "exec" in (t.get("allow") or []) and m.get("skills")==[] and \
     RETIRED.isdisjoint(deny)
sys.exit(0 if ok else 1)
PYEOF
then _ok "A: L5 applies the surviving posture (GHL MCP deny + exec + skills:[]) and does NOT re-add the retired production deny"
else _bad "A: L5 did not apply the surviving posture correctly (or re-added the retired production deny)"; fi

# B. idempotent.
# Was: grep the log for "L5: ... already", which depended on the ALREADY_GATED
# early-exit. That branch was gate machinery and is deleted (2026-08-05), so the
# log string is gone. Assert idempotence DIRECTLY instead — a byte-identical
# config across a re-run is a strictly stronger proof than a log-line match.
_B_BEFORE=$(shasum -a 256 "$HOME/.openclaw/openclaw.json" | awk '{print $1}')
bash "$APPLY_FIX" >/dev/null 2>&1 || true
_B_AFTER=$(shasum -a 256 "$HOME/.openclaw/openclaw.json" | awk '{print $1}')
[ "$_B_BEFORE" = "$_B_AFTER" ] \
  && _ok "B: L5 idempotent (re-run leaves openclaw.json byte-identical, sha256 unchanged)" \
  || _bad "B: L5 NOT idempotent — re-run changed openclaw.json ($_B_BEFORE -> $_B_AFTER)"

# C. RETIRED 2026-08-05 — consent lift / revoke of the production deny.
# C1 asserted that grant-ceo-consent.sh REMOVED "write" from tools.deny and C2
# that --revoke put it BACK. Both are meaningless now: the production deny no
# longer exists in any posture, so there is nothing to lift and nothing to
# restore. Retired rather than rewritten (same treatment as section K).
#
# What IS still worth proving is that the consent script does not CRASH — it
# sources hooks/lib-ceo-tool-gate.sh and calls ceo_gate_tools under
# `set -euo pipefail`, and an empty CEO_GATE_DENY_TOOLS array aborts macOS
# /bin/bash 3.2 unless the expansion is guarded. That is a real fleet-fatal path.
if /bin/bash -c 'set -euo pipefail; . "$1"; ceo_gate_tools >/dev/null' _ "$GATE_LIB" 2>/dev/null; then
  _ok "C: ceo_gate_tools survives bash 3.2 + set -u with an EMPTY deny array (grant-ceo-consent.sh path)"
else
  _bad "C: ceo_gate_tools ABORTS under bash 3.2 + set -u (empty-array unbound-variable) — grant-ceo-consent.sh dies on every macOS box"
fi
_ok "C1/C2: consent lift/revoke of the production deny RETIRED (Trevor 2026-08-05) — no deny exists to lift or restore"

# D. L5 skips while consent active
_write_ungated
printf '{"granted":true,"scope":"global"}\n' > "$CEO_CONSENT_FILE"
D_OUT=$(bash "$APPLY_FIX" 2>&1 | grep -E "L5:.*consent.*ACTIVE|CONSENT_ACTIVE" || true)
if [ -n "$D_OUT" ] && python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
m=[a for a in json.load(open(sys.argv[1]))["agents"]["list"] if a["id"]=="main"][0]
sys.exit(0 if "tools" not in m else 1)
PYEOF
then _ok "D: L5 skipped re-gate while consent active (owner grant preserved)"
else _bad "D: L5 re-gated despite active consent"; fi
rm -f "$CEO_CONSENT_FILE"

# E. verify-routing G7 (interim) reports gated-but-not-clean without a hard fail
_write_ungated
bash "$APPLY_FIX" >/dev/null 2>&1 || true
printf '<!-- ROLE_DISCIPLINE_V1 -->\nCEO_ROUTING_NO_LOOPHOLES_V1\n' > "$HOME/.openclaw/workspace/AGENTS.md"
printf '<!-- CEO_ORCHESTRATOR_RULE_V2 -->\n' > "$HOME/.openclaw/workspace/SOUL.md"
python3 -c "import sqlite3;c=sqlite3.connect('$HOME/projects/command-center/mission-control.db');c.execute('CREATE TABLE workspaces(id TEXT)');c.executemany('INSERT INTO workspaces VALUES(?)',[('default',),('presentations',)]);c.commit()"
E_OUT=$(bash "$VERIFY" 2>&1 || true)
# G7's message set changed with the retirement: the INTERIM/"tool-gate present"
# lines are gone; it now reports the retirement plus the surviving tools-policy
# result. Accept either the retirement INFO/PASS or the tools-policy PASS.
if printf '%s' "$E_OUT" | grep -qE "G7: CEO production-tool deny RETIRED|G7: CEO production-tool deny intentionally absent|G7: CEO agent tools policy OK"; then
  _ok "E: verify-routing G7 evaluated the box (retirement reported / tools policy checked)"
else
  _bad "E: verify-routing G7 did not evaluate the box — G7=[$(printf '%s' "$E_OUT" | grep -E 'G7:' | grep -v G7b | head -2 | tr '\n' '|')]"
fi

# ── F. GOAL-4 D4 (4B+4C) — no-refusal baseline + CEO-deny COORDINATION ────────
# After apply-fleet-standards.sh runs, assert BOTH at once:
#   (a) agents.defaults.tools.allow == ["*"]   (no department/sub-agent refuses)
#   (b) main.tools.deny ⊇ production set        (CEO still gated — ungate did NOT
#                                                re-open the CEO via the baseline)
# This is the mechanical proof that the fleetwide ungate and the CEO tool-gate
# do not fight: the wildcard default is present AND the per-agent main deny holds.

# F0. Source-presence: the no-refusal baseline must exist in BOTH the fleet roll
#     (apply-fleet-standards.sh) and the build origin (build-workforce.py).
if grep -q 'agents.defaults.tools.allow' "$APPLY_STD" && grep -q 'agents.defaults.tools.allow' "$BUILD_WF"; then
  _ok "F0: no-refusal baseline (agents.defaults.tools.allow) present in fleet roll + build origin"
else
  _bad "F0: no-refusal baseline missing from apply-fleet-standards.sh and/or build-workforce.py"
fi

# F1. Behavior: run apply-fleet-standards.sh on an ungated sandbox box, then
#     assert the baseline AND the re-asserted CEO deny coexist.
rm -f "$CEO_CONSENT_FILE"
cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "list": [ { "id": "main", "default": true, "skills": [] } ] } }
JSON
# apply-fleet-standards.sh validates via the stubbed `openclaw` (exit 0) and
# writes AGENTS.md/SOUL.md into $HOME/.openclaw/workspace (already created).
bash "$APPLY_STD" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
cfg=json.load(open(sys.argv[1]))
# (a) defaults baseline
base = cfg.get("agents",{}).get("defaults",{}).get("tools",{}).get("allow")
base_ok = base == ["*"]
# (b) RETIRED: "CEO still gated" (need ⊆ deny). The production deny is gone.
#     Replaced by its inverse — the retired deny must NOT be re-asserted, and
#     the surviving GHL MCP deny must still be in place.
m=[a for a in cfg["agents"]["list"] if a["id"]=="main"][0]
deny=set(m.get("tools",{}).get("deny") or [])
RETIRED={"write","edit","apply_patch","browser","canvas","image","process"}
ceo_ok = RETIRED.isdisjoint(deny) and \
         m.get("tools",{}).get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")==["*"]
# (c) the wildcard did NOT leak into main's allow
main_allow=set(m.get("tools",{}).get("allow") or [])
no_leak = "*" not in main_allow
sys.exit(0 if (base_ok and ceo_ok and no_leak) else 1)
PYEOF
then _ok "F1: ungate + surviving posture coexist — agents.defaults.tools.allow==['*'], GHL MCP denied, retired production deny NOT re-asserted, no wildcard leak into main.allow"
else _bad "F1: GOAL-4 D4 coordination broken — baseline absent OR retired production deny re-asserted OR GHL MCP deny lost OR wildcard leaked into main.allow"; fi

# F2. Idempotent: a second apply-fleet-standards.sh run keeps both invariants
#     and does not duplicate the CEO deny entries.
bash "$APPLY_STD" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
cfg=json.load(open(sys.argv[1]))
base = cfg.get("agents",{}).get("defaults",{}).get("tools",{}).get("allow")
m=[a for a in cfg["agents"]["list"] if a["id"]=="main"][0]
deny_list=m.get("tools",{}).get("deny") or []
deny=set(deny_list)
RETIRED={"write","edit","apply_patch","browser","canvas","image","process"}
no_dupes = len(deny_list)==len(deny)
sys.exit(0 if (base==["*"] and RETIRED.isdisjoint(deny) and no_dupes) else 1)
PYEOF
then _ok "F2: apply-fleet-standards.sh idempotent (baseline stable, deny not duplicated, retired deny not re-added on re-run)"
else _bad "F2: re-run drifted the baseline, duplicated deny entries, or re-added the retired production deny"; fi

# ── G. DEFECT 1 — schema-version-aware no-refusal baseline (2026.6.8) ──────────
# OpenClaw 2026.6.8 REJECTS agents.defaults.tools.* . apply-fleet-standards.sh must
# NOT write it on that schema (it would self-roll-back), and verify-routing.sh G7b
# must accept the FUNCTIONAL UNGATE (root tools.exec full+off + agents.defaults.
# subagents ungate) as the satisfied baseline instead.
rm -f "$CEO_CONSENT_FILE"

# G1: apply-fleet-standards.sh on a 2026.6.8 schema strips/omits agents.defaults.tools,
#     keeps config valid, and still leaves the functional ungate + CEO gate.
# Stub openclaw to REJECT agents.defaults.tools at validate (simulates 2026.6.8).
cat > "$STUB/openclaw" <<STUBEOF
#!/usr/bin/env python3
import json, os, sys
if len(sys.argv) >= 3 and sys.argv[1] == "config" and sys.argv[2] == "validate":
    cfg = json.load(open(os.path.join(os.environ["HOME"], ".openclaw", "openclaw.json")))
    if cfg.get("agents", {}).get("defaults", {}).get("tools") is not None:
        sys.stderr.write("agents.defaults: Invalid input\n"); sys.exit(1)
    print("config OK"); sys.exit(0)
if len(sys.argv) >= 2 and sys.argv[1] == "--version":
    print("openclaw 2026.6.8"); sys.exit(0)
sys.exit(0)
STUBEOF
chmod +x "$STUB/openclaw"
# Start with a pre-existing POISON agents.defaults.tools to prove it gets stripped.
cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "defaults": { "tools": { "allow": ["*"] } }, "list": [ { "id": "main", "default": true, "skills": [] } ] } }
JSON
FLEET_OC_VERSION_OVERRIDE="2026.6.8" bash "$APPLY_STD" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
cfg=json.load(open(sys.argv[1]))
adt=cfg.get("agents",{}).get("defaults",{}).get("tools")
exec_ok=cfg.get("tools",{}).get("exec")=={"security":"full","ask":"off"}
sub=cfg.get("agents",{}).get("defaults",{}).get("subagents",{}).get("allowAgents")
m=[a for a in cfg["agents"]["list"] if a["id"]=="main"][0]
deny=set(m.get("tools",{}).get("deny") or [])
RETIRED={"write","edit","apply_patch","browser","canvas","image","process"}
sys.exit(0 if (adt is None and exec_ok and sub==["*"] and RETIRED.isdisjoint(deny)) else 1)
PYEOF
then _ok "G1: 2026.6.8 schema — agents.defaults.tools stripped/omitted, config valid (no rollback), functional ungate present, retired deny absent"
else _bad "G1: apply-fleet-standards.sh wrote/kept agents.defaults.tools on a 2026.6.8 schema (would self-roll-back), or re-added the retired deny"; fi

# G2: verify-routing.sh G7b PASSES on the functional ungate at 2026.6.8 (no
#     agents.defaults.tools required). Provide AGENTS.md/SOUL.md/DB so the run
#     reaches G7b (other gates may warn; we grep only the G7b line).
printf '<!-- ROLE_DISCIPLINE_V1 -->\nCEO_ROUTING_NO_LOOPHOLES_V1\n' > "$HOME/.openclaw/workspace/AGENTS.md"
printf '<!-- CEO_ORCHESTRATOR_RULE_V2 -->\n' > "$HOME/.openclaw/workspace/SOUL.md"
G2_OUT=$(FLEET_OC_VERSION_OVERRIDE="2026.6.8" bash "$VERIFY" 2>&1 || true)
if printf '%s' "$G2_OUT" | grep -qE "PASS  G7b: no-refusal baseline present via FUNCTIONAL UNGATE"; then
  _ok "G2: verify-routing G7b PASSES via functional ungate on 2026.6.8 (no agents.defaults.tools)"
else
  _bad "G2: verify-routing G7b did NOT accept the functional ungate on 2026.6.8 — $(printf '%s' "$G2_OUT" | grep G7b | head -1)"
fi
# restore the no-op openclaw stub for the remaining tests
printf '#!/bin/sh\nexit 0\n' > "$STUB/openclaw"; chmod +x "$STUB/openclaw"

# ── H. DEFECT 2 — gate targets the box's ACTUAL default agent (not hardcoded main) ─
# Some boxes' default agent is "dept-executive-office" (default:true). The CEO
# gate (apply-routing-fix.sh L2+L5) and the verify checks (G4+G7) must target THAT
# agent, not a hardcoded "main".
rm -f "$CEO_CONSENT_FILE"
# H includes a non-default "main" AND a default:true "dept-executive-office" to
# prove default:true wins over a present "main".
cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "list": [
  { "id": "main", "skills": [] },
  { "id": "dept-executive-office", "default": true, "skills": ["pptx"] }
] } }
JSON
bash "$APPLY_FIX" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
cfg=json.load(open(sys.argv[1]))
ag={a["id"]:a for a in cfg["agents"]["list"]}
# "gated" now means the SURVIVING posture: GHL MCP denied by provider + skills:[].
# The retired production deny is no longer part of the definition.
deo=ag["dept-executive-office"]; mn=ag["main"]
deo_gated = (deo.get("tools",{}).get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")==["*"]) and \
            deo.get("skills")==[]
main_gated = (mn.get("tools",{}).get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")==["*"])
sys.exit(0 if (deo_gated and not main_gated) else 1)
PYEOF
then _ok "H1: apply-routing-fix.sh gated the default:true agent (dept-executive-office), NOT the present 'main'"
else _bad "H1: apply-routing-fix.sh gated the wrong agent (hardcoded main bug)"; fi

# H2: verify-routing G4 + G7 report dept-executive-office (the default agent).
printf '<!-- ROLE_DISCIPLINE_V1 -->\nCEO_ROUTING_NO_LOOPHOLES_V1\n' > "$HOME/.openclaw/workspace/AGENTS.md"
printf '<!-- CEO_ORCHESTRATOR_RULE_V2 -->\n' > "$HOME/.openclaw/workspace/SOUL.md"
H2_OUT=$(bash "$VERIFY" 2>&1 || true)
if printf '%s' "$H2_OUT" | grep -qE "G4: default agent \(id=dept-executive-office\)" \
   && printf '%s' "$H2_OUT" | grep -E "G7:" | grep -v "G7b" | grep -q "id=dept-executive-office"; then
  _ok "H2: verify-routing G4+G7 target the default agent (dept-executive-office)"
else
  _bad "H2: verify-routing did NOT target dept-executive-office — G4=[$(printf '%s' "$H2_OUT"|grep 'G4:'|head -1)] G7=[$(printf '%s' "$H2_OUT"|grep -E 'G7:'|grep -v G7b|head -1)]"
fi

# ── I. v13.2.2 PA-FREEZE FIX — a PERSONAL-ASSISTANT-default box is NEVER gated ─
# The v13.1.3 over-broadening (gate any default:true agent) froze a box whose
# default agent is a hands-on personal assistant. The fix gates the default agent
# ONLY if it is a ROUTER (is_master / role==router / known router id). A
# PA-default box must come out of apply-routing-fix.sh + apply-fleet-standards.sh
# with NO CEO production lock, NO skills:[], and NO byProvider GHL deny.
rm -f "$CEO_CONSENT_FILE"
_write_pa_default() {
  cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "list": [
  { "id": "personal-assistant", "default": true, "skills": ["inbox","calendar","deck"] }
] } }
JSON
}

# I1: apply-routing-fix.sh leaves a PA-default box completely ungated.
_write_pa_default
I1_OUT=$(bash "$APPLY_FIX" 2>&1 || true)
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
pa=[a for a in json.load(open(sys.argv[1]))["agents"]["list"] if a["id"]=="personal-assistant"][0]
t=pa.get("tools") or {}
RETIRED={"write","edit","apply_patch","browser","canvas","image","process"}
# NOT gated: no GHL byProvider deny, skills untouched (not []). The retired
# production deny must also be absent (it must never be stamped on a PA either).
ungated = RETIRED.isdisjoint(set(t.get("deny") or [])) \
          and not (t.get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")==["*"]) \
          and pa.get("skills")==["inbox","calendar","deck"]
sys.exit(0 if ungated else 1)
PYEOF
then _ok "I1: apply-routing-fix.sh did NOT gate the PA-default box (no CEO lock, no skills:[], no GHL deny)"
else _bad "I1: apply-routing-fix.sh FROZE a personal-assistant-default box (v13.1.3 regression)"; fi

# I1b: the run announces the PA-freeze skip on BOTH L2 and L5 (auditable).
if printf '%s' "$I1_OUT" | grep -qi "PERSONAL-ASSISTANT/non-router" \
   && printf '%s' "$I1_OUT" | grep -qiE "L2:.*SKIPPING" \
   && printf '%s' "$I1_OUT" | grep -qiE "L5:.*SKIPPING"; then
  _ok "I1b: apply-routing-fix.sh logged the PA-freeze SKIP on L2 and L5"
else
  _bad "I1b: apply-routing-fix.sh did not log the PA-freeze skip — L2/L5 — out=[$(printf '%s' "$I1_OUT" | grep -iE 'L2:|L5:' | tr '\n' '|')]"
fi

# I2: apply-fleet-standards.sh re-assert also SKIPS a PA-default box.
_write_pa_default
I2_OUT=$(bash "$APPLY_STD" 2>&1 || true)
if printf '%s' "$I2_OUT" | grep -qi "PERSONAL-ASSISTANT/non-router" \
   && python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
pa=[a for a in json.load(open(sys.argv[1]))["agents"]["list"] if a["id"]=="personal-assistant"][0]
RETIRED={"write","edit","apply_patch","browser","canvas","image","process"}
# Neither the retired production deny nor the GHL deny may be stamped on a PA.
t=(pa.get("tools") or {})
sys.exit(0 if (RETIRED.isdisjoint(set(t.get("deny") or []))
               and t.get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")!=["*"]) else 1)
PYEOF
then _ok "I2: apply-fleet-standards.sh re-assert SKIPPED the PA-default box (no CEO deny re-asserted)"
else _bad "I2: apply-fleet-standards.sh re-asserted the CEO gate onto a PA (froze it)"; fi

# I3: verify-routing.sh treats a PA-default box as PASSING (G4 + G7 not FATAL).
_write_pa_default
printf '<!-- ROLE_DISCIPLINE_V1 -->\nCEO_ROUTING_NO_LOOPHOLES_V1\n' > "$HOME/.openclaw/workspace/AGENTS.md"
printf '<!-- CEO_ORCHESTRATOR_RULE_V2 -->\n' > "$HOME/.openclaw/workspace/SOUL.md"
I3_OUT=$(bash "$VERIFY" 2>&1 || true)
if printf '%s' "$I3_OUT" | grep -qE "PASS  G4: default agent \(id=personal-assistant\).*PERSONAL-ASSISTANT" \
   && printf '%s' "$I3_OUT" | grep -E "G7:" | grep -v "G7b" | grep -qiE "PASS.*personal-assistant.*PERSONAL-ASSISTANT"; then
  _ok "I3: verify-routing G4+G7 PASS on a PA-default box (no false FATAL)"
else
  _bad "I3: verify-routing did NOT pass a PA-default box — G4=[$(printf '%s' "$I3_OUT"|grep 'G4:'|head -1)] G7=[$(printf '%s' "$I3_OUT"|grep -E 'G7:'|grep -v G7b|head -1)]"
fi

# I4: RETIRED 2026-08-05 — asserted that verify-routing.sh gate G8a did not
# force-wire the ceo-intent-gate hook on a PA-default box. G8a itself was DELETED
# from verify-routing.sh when the intent-gate was removed fleet-wide (all 6 of its
# occurrences are gone; origin/main still had them, so this is a real removal and
# not a search artifact). The hook is now unwired EVERYWHERE, PA-default or not,
# so there is no force-wiring left to guard against. Kept as an explicit skip so
# the numbering and the intent stay legible.
_write_pa_default
mkdir -p "$HOME/.claude"
printf '{}\n' > "$HOME/.claude/settings.json"
I4_OUT=$(CLAUDE_SETTINGS_FILE="$HOME/.claude/settings.json" bash "$VERIFY" 2>&1 || true)
if ! printf '%s' "$I4_OUT" | grep -q 'G8a'; then
  _ok "I4: G8a hook-wiring gate RETIRED (Trevor 2026-08-05) — verify-routing.sh no longer emits G8a; nothing can force-wire the removed hook"
else
  _bad "I4: verify-routing.sh still emits a G8a gate — the intent-gate hook was removed 2026-08-05, so G8a should be gone: [$(printf '%s' "$I4_OUT"|grep 'G8a'|head -1)]"
fi
rm -f "$HOME/.claude/settings.json"

# ── J. ROUTER-DEFAULT box still gets gated (the legitimate cases must not break) ─
# A dept-master-orchestrator default, a dept-executive-office default, plus a
# role:"router" / is_master:true marker — all must STILL be gated.
for RID in "dept-master-orchestrator" "dept-executive-office"; do
  rm -f "$CEO_CONSENT_FILE"
  cat > "$HOME/.openclaw/openclaw.json" <<JSON
{ "agents": { "list": [ { "id": "$RID", "default": true, "skills": ["pptx"] } ] } }
JSON
  bash "$APPLY_FIX" >/dev/null 2>&1 || true
  if RID="$RID" python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,os,sys
rid=os.environ["RID"]
a=[x for x in json.load(open(sys.argv[1]))["agents"]["list"] if x["id"]==rid][0]
t=a.get("tools") or {}
RETIRED={"write","edit","apply_patch","browser","canvas","image","process"}
# "gated" = the SURVIVING posture (GHL MCP deny + skills:[]); the retired
# production deny must NOT be present.
ok = t.get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")==["*"] \
     and a.get("skills")==[] \
     and RETIRED.isdisjoint(set(t.get("deny") or []))
sys.exit(0 if ok else 1)
PYEOF
  then _ok "J: router-default box (id=$RID) IS gated (GHL deny + skills:[], no retired production deny)"
  else _bad "J: router-default box (id=$RID) was NOT gated — legitimate router gating broke"; fi
done

# J2: an agent carrying role:"router" (id NOT in the known list) is STILL gated.
rm -f "$CEO_CONSENT_FILE"
cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "list": [ { "id": "orchestra-prime", "role": "router", "default": true, "skills": ["pptx"] } ] } }
JSON
bash "$APPLY_FIX" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
a=[x for x in json.load(open(sys.argv[1]))["agents"]["list"] if x["id"]=="orchestra-prime"][0]
# Surviving marker of "was gated": GHL MCP denied by provider (the retired
# production deny is no longer stamped, so it cannot be the probe).
t=(a.get("tools") or {})
sys.exit(0 if t.get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")==["*"] else 1)
PYEOF
then _ok "J2: role:'router' agent (unknown id) IS gated (explicit router marker honored)"
else _bad "J2: role:'router' marker was ignored — router not gated"; fi

# J3: an agent carrying is_master:true is STILL gated.
rm -f "$CEO_CONSENT_FILE"
cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "list": [ { "id": "the-boss", "is_master": true, "default": true, "skills": ["pptx"] } ] } }
JSON
bash "$APPLY_FIX" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
a=[x for x in json.load(open(sys.argv[1]))["agents"]["list"] if x["id"]=="the-boss"][0]
# Surviving marker of "was gated" — see J2.
t=(a.get("tools") or {})
sys.exit(0 if t.get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")==["*"] else 1)
PYEOF
then _ok "J3: is_master:true agent (unknown id) IS gated (explicit master marker honored)"
else _bad "J3: is_master:true marker was ignored — router not gated"; fi

# ── K. CEO intent-gate hook — INTENTIONALLY REMOVED (2026-08-05) ──────────────
# The ceo-intent-gate.sh PreToolUse hook has been REMOVED from the repo and all
# boxes per Trevor's directive (was creating loops). These tests are retired.
_ok "K: ceo-intent-gate hook INTENTIONALLY REMOVED (Trevor 2026-08-05) — hook tests skipped (no longer required)"

# ── L. lib router-detection canonical / drift ─────────────────────────────────
# hooks/lib-ceo-tool-gate.sh exposes ceo_agent_is_router + CEO_ROUTER_IDS; assert
# the canonical router-id set matches every embedded copy (apply-*, verify, hook).
EXPECT_ROUTER_IDS="ceo dept-ceo dept-executive-office dept-master-orchestrator main master-orchestrator"
LIB_ROUTER_IDS=$(printf '%s\n' "${CEO_ROUTER_IDS[@]+"${CEO_ROUTER_IDS[@]}"}" | sort | tr '\n' ' ' | sed 's/ $//')
[ "$LIB_ROUTER_IDS" = "$EXPECT_ROUTER_IDS" ] \
  && _ok "L0: lib CEO_ROUTER_IDS canonical" \
  || _bad "L0: CEO_ROUTER_IDS drift: [$LIB_ROUTER_IDS] != [$EXPECT_ROUTER_IDS]"

# Every embedded ROUTER_IDS copy must contain all six canonical ids + the markers.
# 2026-08-05: hooks/ceo-intent-gate.sh and scripts/install-ceo-intent-gate.sh were
# DELETED with the intent-gate removal. They were still listed here, so `grep -q`
# ran against missing files → rc=2 (an ERROR, not "no match") → 8 phantom
# failures. Dropped from the loop; 5 gate-target sites became 3.
for f in "$APPLY_FIX" "$APPLY_STD" "$VERIFY"; do
  for rid in "dept-master-orchestrator" "dept-executive-office" "master-orchestrator"; do
    grep -q "\"$rid\"" "$f" || _bad "L: router id '$rid' missing from $(basename "$f")"
  done
  grep -q "is_master" "$f" || _bad "L: is_master marker missing from $(basename "$f")"
done
_ok "L: router-id set + is_master marker present in all 3 surviving gate-target sites"

# L1b: the two deleted intent-gate files must STAY deleted (they are what wired
# the write-deny loop). A reappearance means someone restored the outage path.
for _gone in "$ONBOARDING_DIR/hooks/ceo-intent-gate.sh" \
             "$ONBOARDING_DIR/hooks/lib-ceo-consent.sh" \
             "$SCRIPT_DIR/install-ceo-intent-gate.sh"; do
  if [ -e "$_gone" ]; then
    _bad "L1b: $(basename "$_gone") REAPPEARED in the repo — the intent-gate was removed 2026-08-05 (loop cause); it must stay deleted"
  fi
done
_ok "L1b: the deleted intent-gate files (ceo-intent-gate.sh, lib-ceo-consent.sh, install-ceo-intent-gate.sh) are still absent"

# L2 (behavior): ceo_agent_is_router classifies router vs PA correctly.
ceo_agent_is_router '{"id":"main"}'                 && _ok "L-fn: id=main → router"          || _bad "L-fn: id=main misclassified"
ceo_agent_is_router '{"id":"dept-executive-office"}'&& _ok "L-fn: dept-executive-office → router" || _bad "L-fn: dept-executive-office misclassified"
ceo_agent_is_router '{"id":"x","is_master":true}'   && _ok "L-fn: is_master → router"        || _bad "L-fn: is_master misclassified"
ceo_agent_is_router '{"id":"x","role":"router"}'    && _ok "L-fn: role=router → router"      || _bad "L-fn: role=router misclassified"
if ceo_agent_is_router '{"id":"personal-assistant"}'; then _bad "L-fn: personal-assistant wrongly classified as router"; else _ok "L-fn: personal-assistant → NOT router"; fi

# ── M. v16.1.3 — sessions/agentToAgent on ROOT tools, NEVER per-agent + self-heal ─
# THE regression guard for the router-default-box cron-engine-down defect. The
# per-agent AgentEntry.tools schema is additionalProperties:false and REJECTS
# sessions/agentToAgent (allowed: allow/alsoAllow/byProvider/codeMode/deny/
# elevated/exec/fs/loopDetection/message/profile/sandbox/toolsBySender). Writing
# them per-agent fails `openclaw config validate` → reload skipped → cron engine
# down. They MUST live on ROOT config.tools (sessions.visibility + agentToAgent).
# This section CI-fails if any write-site puts them on a per-agent block, and
# proves the updater self-heals an already-corrupted box.
rm -f "$CEO_CONSENT_FILE"

# Shared structural assertion: per-agent block clean + root tools carries the keys.
_assert_routing_layout() {
  python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
m = [a for a in cfg.get("agents", {}).get("list", []) if a.get("id") == "main"][0]
t = m.get("tools", {}) or {}
peragent_clean = "sessions" not in t and "agentToAgent" not in t
root = cfg.get("tools", {}) or {}
root_ok = (root.get("sessions", {}).get("visibility") == "all"
           and root.get("agentToAgent", {}).get("enabled") is True)
sys.exit(0 if (peragent_clean and root_ok) else 1)
PYEOF
}

# M0. The canonical per-agent gated block (lib) must NOT carry sessions/agentToAgent.
if ceo_gate_tools | python3 -c "import json,sys; t=json.load(sys.stdin); sys.exit(0 if ('sessions' not in t and 'agentToAgent' not in t) else 1)"; then
  _ok "M0: lib ceo_gate_tools per-agent block is schema-clean (no sessions/agentToAgent)"
else
  _bad "M0: lib ceo_gate_tools STILL emits sessions/agentToAgent on the per-agent block"
fi

# M1. apply-routing-fix.sh L5 puts routing keys on ROOT tools, NOT per-agent.
_write_ungated
bash "$APPLY_FIX" >/dev/null 2>&1 || true
if _assert_routing_layout; then
  _ok "M1: apply-routing-fix.sh — routing keys on ROOT tools, per-agent block schema-clean"
else
  _bad "M1: apply-routing-fix.sh wrote sessions/agentToAgent to the per-agent block (router-default cron-down defect)"
fi

# M2. apply-fleet-standards.sh re-assert — same: root tools carries the keys.
rm -f "$CEO_CONSENT_FILE"
_write_ungated
bash "$APPLY_STD" >/dev/null 2>&1 || true
if _assert_routing_layout; then
  _ok "M2: apply-fleet-standards.sh — routing keys on ROOT tools, per-agent block schema-clean"
else
  _bad "M2: apply-fleet-standards.sh wrote sessions/agentToAgent to the per-agent block"
fi

# M3. SELF-HEAL: a box CORRUPTED with per-agent sessions/agentToAgent is REPAIRED
# (keys stripped from per-agent + ensured on root) by apply-fleet-standards.sh.
rm -f "$CEO_CONSENT_FILE"
cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "list": [ { "id": "main", "default": true, "skills": [],
  "tools": { "deny": ["ghl-mcp__*"], "sessions": {"visibility":"all"},
             "agentToAgent": {"enabled": true, "allow": ["*"]} } } ] } }
JSON
bash "$APPLY_STD" >/dev/null 2>&1 || true
if _assert_routing_layout; then
  _ok "M3: apply-fleet-standards.sh SELF-HEALED a corrupted box (per-agent keys stripped, on root)"
else
  _bad "M3: apply-fleet-standards.sh did NOT self-heal the corrupted per-agent keys"
fi

# M3b. apply-routing-fix.sh ALSO self-heals an ALREADY-GATED corrupted box (the
# heal runs FIRST, before any early-exit, so a corrupted box is repaired on every
# path. It used to also have to survive the ALREADY_GATED early-exit; that branch
# was deleted with the gate machinery on 2026-08-05, so the box now simply falls
# through to the idempotent deep-merge.)
rm -f "$CEO_CONSENT_FILE"
cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "list": [ { "id": "main", "default": true, "skills": [],
  "tools": { "deny": ["ghl-community-mcp__*","ghl-mcp__*"],
             "allow": ["read","exec"],
             "byProvider": {"ghl-community-mcp":{"deny":["*"]},"ghl-mcp":{"deny":["*"]}},
             "sessions": {"visibility":"all"},
             "agentToAgent": {"enabled": true, "allow": ["*"]} } } ] } }
JSON
bash "$APPLY_FIX" >/dev/null 2>&1 || true
if _assert_routing_layout && python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
m=[a for a in json.load(open(sys.argv[1]))["agents"]["list"] if a["id"]=="main"][0]
# The already-gated marker is now the MCP glob (the retired production deny is
# no longer stamped, so "write" can never be the probe). Prove it was PRESERVED
# through the heal — that is what "deny preserved" means post-retirement.
sys.exit(0 if "ghl-mcp__*" in (m.get("tools",{}).get("deny") or []) else 1)
PYEOF
then _ok "M3b: apply-routing-fix.sh SELF-HEALED an already-gated corrupted box (MCP deny preserved, per-agent keys stripped)"
else _bad "M3b: apply-routing-fix.sh did NOT self-heal an already-gated corrupted box"; fi

# M4. IDEMPOTENT: a second apply-fleet-standards.sh run never re-introduces the keys.
bash "$APPLY_STD" >/dev/null 2>&1 || true
if _assert_routing_layout; then
  _ok "M4: re-running apply-fleet-standards.sh never re-corrupts the per-agent block (idempotent)"
else
  _bad "M4: re-run re-introduced per-agent sessions/agentToAgent"
fi

# M5. SOURCE GUARD (build origin): the CEO agent_entry["tools"] per-agent literal
# in build-workforce.py must NOT contain sessions/agentToAgent. (Behavior tests
# cover the shell scripts; this catches a future regression in the build origin.)
if python3 - "$BUILD_WF" <<'PYEOF'
import re, sys
src = open(sys.argv[1]).read()
m = re.search(r'agent_entry\["tools"\]\s*=\s*\{([^}]*)\}', src)  # first = CEO branch
if not m:
    sys.exit(1)
block = m.group(1)
sys.exit(1 if ('"sessions"' in block or '"agentToAgent"' in block) else 0)
PYEOF
then _ok "M5: build-workforce.py CEO agent_entry['tools'] (per-agent) literal has no sessions/agentToAgent"
else _bad "M5: build-workforce.py still puts sessions/agentToAgent in the per-agent agent_entry['tools'] literal"; fi
rm -f "$CEO_CONSENT_FILE"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
if [ "$FAILS" -eq 0 ]; then
  echo "[test-ceo-tool-gate] ALL PASS"
  exit 0
else
  echo "[test-ceo-tool-gate] $FAILS FAILURE(S)" >&2
  exit 1
fi

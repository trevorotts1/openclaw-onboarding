#!/usr/bin/env bash
# tests/unit/fleet-standards-version-detector-rollback.test.sh
# -----------------------------------------------------------------------------
# CI guard for the 2026-11-06 fleet-wide self-rollback on OpenClaw 2026.10.8.
#
# THE DEFECT THIS GUARDS AGAINST (measured on oc-janet-pinkney, 2026.11.06)
#
#   The box's `openclaw` is a shim that writes an admission banner to STDERR
#   before the version line:
#       line 1 (stderr): openclaw: Retrying with ".../node" (cached OpenClaw runtime; ...)
#       line 2 (stdout): OpenClaw 2026.10.8 (dc2523e)
#   scripts/apply-fleet-standards.sh took `head -n1` of the MERGED stream, so it
#   parsed the banner, OC_VERSION stayed "", and the "version unknown" branch
#   wrote agents.defaults.tools.allow=["*"] onto a schema (>= 2026.6.8) that
#   REJECTS that key. `openclaw config validate` failed with
#       openclaw.json line 281 'Unrecognized key: "tools"'
#   The narrow repair only reverted ROOT tools.exec, which is a DIFFERENT
#   subtree, so the identical error came back one validator pass later and the
#   ENTIRE apply was rolled back. Consequence: no fleet standard landed on the
#   box, and the AGENTS.md doctrine stamping that runs later in the same script
#   never happened either.
#
# WHAT MUST HOLD AFTER THE FIX
#   A. A version on line 2 of the CLI output parses correctly; a rejecting
#      schema gets NO agents.defaults.tools write, the apply exits 0, and the
#      standards are genuinely present in the resulting config.
#   B. "Version unknown" takes the SAFE branch: no write, no delete.
#   C. If a pre-existing agents.defaults.tools still fails validate, the NARROW
#      repair removes that PARENT key and keeps every other standard (no full
#      rollback).
#   D. A genuine, unrelated validation failure STILL rolls back and exits 1.
#      The validator is never silenced and no real violation is turned into a pass.
#
# The stub `openclaw` below is a faithful copy of the box's shape: the banner is
# on stderr, the version is on stdout line 2, and `config validate` really
# rejects agents.defaults.tools the way the 2026.10.x validator does.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPLY_STD="$SCRIPT_DIR/scripts/apply-fleet-standards.sh"
VERIFY="$SCRIPT_DIR/scripts/verify-routing.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); echo "  ok  $*"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL $*"; }

[ -f "$APPLY_STD" ] || { echo "FATAL: missing $APPLY_STD"; exit 1; }

SB="$(mktemp -d)"; STUB="$(mktemp -d)"
trap 'rm -rf "$SB" "$STUB"' EXIT
export HOME="$SB"
mkdir -p "$HOME/.openclaw/workspace" "$HOME/.openclaw/state" "$HOME/projects/command-center"
export CEO_CONSENT_FILE="$HOME/.openclaw/state/ceo-consent.json"

CFG="$HOME/.openclaw/openclaw.json"

# Stub CLI. Version line shape is parameterised by $1: "banner" (banner on
# stderr, version on stdout line 2 — the oc-janet-pinkney shape), "silent" (no
# version at all — the unknown branch), "line1" (version on line 1).
write_stub() {
  local shape="$1"
  cat > "$STUB/openclaw" <<STUBEOF
#!/usr/bin/env python3
import json, os, sys

shape = "$shape"
cfg_path = os.path.join(os.environ["HOME"], ".openclaw", "openclaw.json")

if len(sys.argv) >= 2 and sys.argv[1] == "--version":
    if shape == "banner":
        sys.stderr.write('openclaw: Retrying with "/home/node/.openclaw/tools/cli-node/tools/node-v24.22.2/bin/node" (cached OpenClaw runtime; current Node failed runtime admission).\n')
        print("OpenClaw 2026.10.8 (dc2523e)")
    elif shape == "line1":
        print("OpenClaw 2026.10.8 (dc2523e)")
    else:
        print("no version here")
    sys.exit(0)

if len(sys.argv) >= 3 and sys.argv[1] == "config" and sys.argv[2] == "validate":
    try:
        cfg = json.load(open(cfg_path))
    except Exception as e:
        sys.stderr.write("cannot read config: %s\n" % e); sys.exit(1)
    if cfg.get("agents", {}).get("defaults", {}).get("tools") is not None:
        sys.stderr.write('- openclaw.json:281 — agents.defaults: Unrecognized key: "tools"\n')
        sys.exit(1)
    if "__badKey" in cfg:
        sys.stderr.write('- openclaw.json:3 — : Unrecognized key: "__badKey"\n')
        sys.exit(1)
    print("Config valid: %s" % cfg_path)
    sys.exit(0)

# plugins list --json / config get / anything else: no output, success.
sys.exit(0)
STUBEOF
  chmod +x "$STUB/openclaw"
  export PATH="$STUB:$PATH"
}

write_min_cfg() {
  cat > "$CFG" <<'JSON'
{ "agents": { "list": [ { "id": "main", "default": true, "skills": [] } ] } }
JSON
}

# Assert the standards genuinely landed (not merely "validate returned 0").
assert_standards() {
  python3 - "$CFG" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
ad = cfg.get("agents", {}).get("defaults", {}) or {}
tools = cfg.get("tools", {}) or {}
sub = ad.get("subagents", {}) or {}
checks = {
    "agents.defaults.tools absent": "tools" not in ad,
    "tools.exec security=full": tools.get("exec", {}).get("security") == "full",
    "tools.exec ask=off": tools.get("exec", {}).get("ask") == "off",
    "tools.toolSearch.enabled=true": tools.get("toolSearch", {}).get("enabled") is True,
    "tools.toolSearch.mode=directory": tools.get("toolSearch", {}).get("mode") == "directory",
    'agents.defaults.subagents.allowAgents=["*"]': sub.get("allowAgents") == ["*"],
    "agents.defaults.subagents.requireAgentId=false": sub.get("requireAgentId") is False,
    "whatsapp plugin disabled": cfg.get("plugins", {}).get("entries", {}).get("whatsapp", {}).get("enabled") is False,
}
bad = [name for name, good in checks.items() if not good]
if bad:
    print("MISSING: " + "; ".join(bad))
    sys.exit(1)
print("all standards present")
PYEOF
}

# ── A. banner-on-stderr, version on line 2, rejecting schema ─────────────────
echo "A: version on stdout line 2 (oc-janet-pinkney shape), 2026.10.x validator"
write_stub banner
write_min_cfg
OUT_A="$(bash "$APPLY_STD" 2>&1)"; RC_A=$?
if [ "$RC_A" -eq 0 ]; then
  ok "A1: apply exit 0 (no self-rollback)"
else
  bad "A1: apply exit $RC_A -- self-rollback reproduced; tail: $(printf '%s\n' "$OUT_A" | tail -3 | tr '\n' ' ')"
fi
if printf '%s' "$OUT_A" | grep -q "gateway 2026.10.8 >= 2026.6.8"; then
  ok "A2: detector parsed 2026.10.8 from line 2 of the CLI output"
else
  bad "A2: detector did NOT read the version from line 2 (line-1-only parse)"
fi
if ! python3 -c 'import json,sys; sys.exit(0 if "tools" in json.load(open(sys.argv[1])).get("agents",{}).get("defaults",{}) else 1)' "$CFG"; then
  ok "A3: agents.defaults.tools NOT written on the rejecting schema"
else
  bad "A3: agents.defaults.tools was written on a schema that rejects it"
fi
if A_MSG="$(assert_standards)"; then
  ok "A4: standards genuinely present in the resulting config ($A_MSG)"
else
  bad "A4: standards missing after the apply -- $A_MSG"
fi

# A5. The verifier agrees with the applier (same detector, same schema form).
VOUT="$(bash "$VERIFY" 2>&1 || true)"
if printf '%s' "$VOUT" | grep -q "version=2026.10.8"; then
  ok "A5: verify-routing.sh detector also parsed 2026.10.8 (applier and verifier agree)"
else
  bad "A5: verify-routing.sh still reads the version as unknown"
fi

# ── B. version unknown → safe branch (no write, no delete) ───────────────────
echo ""
echo "B: CLI prints no version at all (unknown branch)"
write_stub silent
write_min_cfg
OUT_B="$(bash "$APPLY_STD" 2>&1)"; RC_B=$?
if [ "$RC_B" -eq 0 ]; then ok "B1: apply exit 0"; else bad "B1: apply exit $RC_B on the unknown-version branch"; fi
if printf '%s' "$OUT_B" | grep -q "gateway version UNKNOWN — NOT writing"; then
  ok "B2: unknown version took the safe (non-writing) branch"
else
  bad "B2: unknown version did not announce the safe branch"
fi
if B_MSG="$(assert_standards)"; then
  ok "B3: standards still applied with an unknown version ($B_MSG)"
else
  bad "B3: standards missing on the unknown-version branch -- $B_MSG"
fi

# ── C. pre-existing poison parent key + unknown version → narrow repair ──────
echo ""
echo "C: pre-existing agents.defaults.tools on an unknown version (narrow repair must clear the PARENT key)"
write_stub silent
cat > "$CFG" <<'JSON'
{ "agents": { "defaults": { "tools": { "allow": ["*"] } },
              "list": [ { "id": "main", "default": true, "skills": [] } ] } }
JSON
OUT_C="$(bash "$APPLY_STD" 2>&1)"; RC_C=$?
if [ "$RC_C" -eq 0 ]; then
  ok "C1: apply exit 0 (narrow repair kept the run instead of rolling back)"
else
  bad "C1: apply exit $RC_C -- narrow repair could not clear agents.defaults.tools; tail: $(printf '%s\n' "$OUT_C" | tail -3 | tr '\n' ' ')"
fi
if printf '%s' "$OUT_C" | grep -q "removed agents.defaults.tools"; then
  ok "C2: narrow repair removed the rejected PARENT key"
else
  bad "C2: narrow repair did not report removing agents.defaults.tools"
fi
if C_MSG="$(assert_standards)"; then
  ok "C3: every other standard survived the narrow repair ($C_MSG)"
else
  bad "C3: standards lost after the narrow repair -- $C_MSG"
fi

# ── D. genuine unrelated failure STILL fails (rollback, exit 1) ──────────────
echo ""
echo "D: unrelated invalid key must still fail closed (no silencing, no false pass)"
write_stub banner
cat > "$CFG" <<'JSON'
{ "__badKey": true,
  "agents": { "list": [ { "id": "main", "default": true, "skills": [] } ] } }
JSON
cp "$CFG" "$SB/pre.json"
OUT_D="$(bash "$APPLY_STD" 2>&1)"; RC_D=$?
if [ "$RC_D" -ne 0 ]; then
  ok "D1: unrelated validation failure still exits non-zero"
else
  bad "D1: unrelated validation failure was silenced into a pass"
fi
if printf '%s' "$OUT_D" | grep -q "rolling back to:"; then
  ok "D2: full rollback still fires on a genuine failure"
else
  bad "D2: no rollback message on a genuine failure"
fi
if python3 - "$CFG" "$SB/pre.json" <<'PYEOF'
import json, sys
cur = json.load(open(sys.argv[1])); pre = json.load(open(sys.argv[2]))
sys.exit(0 if cur == pre else 1)
PYEOF
then
  ok "D3: config was restored to the pre-roll state"
else
  bad "D3: config was NOT restored after a genuine failure"
fi
if printf '%s' "$OUT_D" | grep -q '__badKey'; then
  ok "D4: the failing key is named in the output (reporting gap closed)"
else
  bad "D4: the failing key was not named in the output"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi
echo "PASS: version detector, unknown branch, narrow repair and fail-closed rollback all hold"
exit 0

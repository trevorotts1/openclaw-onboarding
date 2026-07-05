#!/usr/bin/env bash
# qc-model-fallback.sh (U-8 + U-10) - machine-enforce the model fallback chain and
# the per-workflow model tier.
#
# Two layers of enforcement:
#   (A) STATIC WIRING (always checked, CI-relevant): the fallback-chain reference
#       doc, the config-keys documentation (skill38.model_chain.primary +
#       .fallbacks), the preflight script, the MEMORY rule, the freshness-cron chain
#       review, and the JSONL sink seed must all exist in the skill repo. A missing
#       piece is a FAIL.
#   (B) PLAYBOOK CONTENT (checked when a conversation-workflows dir is present):
#       every playbook that carries a `model-tier:` header line MUST use one of the
#       three enum values realtime-light / realtime-standard / reasoning-max (U-10).
#       An out-of-enum tier is a FAIL.
#
# This gate does NOT parse playbook markdown itself. It shells out to the canonical
# parser tools/playbook_engine.py (U-16) for the model-tier header.
#
# Exit codes: 0 = pass; 1 = a violation or missing wiring; 2 = the engine is missing
#             / python3 unavailable (cannot judge).
#
# Usage:
#   bash scripts/qc-model-fallback.sh
#   bash scripts/qc-model-fallback.sh --dir <conversation-workflows>
#   bash scripts/qc-model-fallback.sh --json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"

WF_DIR=""
JSON_MODE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dir)  WF_DIR="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENGINE" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "qc-model-fallback: canonical engine tools/playbook_engine.py or python3 not available."
  exit 2
fi

if [ -z "$WF_DIR" ]; then
  POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
  if [ -f "$POINTER" ]; then
    MFD="$(head -n1 "$POINTER")"
    [ -n "$MFD" ] && WF_DIR="$MFD/conversation-workflows"
  fi
fi

export SKILL_ROOT ENGINE WF_DIR JSON_MODE

python3 - <<'PYEOF'
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(os.environ["SKILL_ROOT"])
ENGINE = Path(os.environ["ENGINE"])
WF_DIR = os.environ.get("WF_DIR", "")
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"

sys.path.insert(0, str(ENGINE.parent))
import playbook_engine as engine  # canonical parser (U-16)

TIER_ENUM = ("realtime-light", "realtime-standard", "reasoning-max")

failures = []
notes = []

def contains(path, needle):
    p = SKILL_ROOT / path
    return p.is_file() and needle in p.read_text(encoding="utf-8", errors="ignore")

# --- (A) Static wiring checks. -----------------------------------------------
REF = "references/model-fallback-chain.md"
if not (SKILL_ROOT / REF).is_file():
    failures.append("missing references/model-fallback-chain.md")
else:
    if not contains(REF, "skill38.model_chain.primary"):
        failures.append("model-fallback-chain.md does not document skill38.model_chain.primary")
    if not contains(REF, "skill38.model_chain.fallbacks"):
        failures.append("model-fallback-chain.md does not document skill38.model_chain.fallbacks")
    # U-10: the three model-tier enum values must be documented in the shared home.
    for t in TIER_ENUM:
        if not contains(REF, t):
            failures.append("model-fallback-chain.md does not document the model-tier value '%s'" % t)

if not (SKILL_ROOT / "scripts" / "32-verify-model-failover-support.sh").is_file():
    failures.append("missing scripts/32-verify-model-failover-support.sh (the Mode A/B preflight)")

if not contains("scripts/06-append-memory-rules.sh", "v1.8.0-rules-model-fallback"):
    failures.append("missing MEMORY Rule 38 (model fallback) in scripts/06-append-memory-rules.sh")

if not contains("scripts/25-seed-round3-feature-files.sh", "model-failover-events.jsonl"):
    failures.append("missing model-failover-events.jsonl seed in scripts/25-seed-round3-feature-files.sh")

# The Saturday freshness cron must review the CHAIN, not just the primary.
FRESH = "protocols/model-version-freshness-protocol.md"
if not (SKILL_ROOT / FRESH).is_file():
    failures.append("missing protocols/model-version-freshness-protocol.md")
elif not (contains(FRESH, "model_chain") or contains(FRESH, "fallback chain")):
    failures.append("model-version-freshness-protocol.md does not review the model chain (U-8)")

# --- (B) Playbook content checks (model-tier enum, U-10). --------------------
RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
            "--verification-checklist.md", "--ghl-side.md")

playbooks_checked = 0
tiers_seen = 0
wf = Path(WF_DIR) if WF_DIR else None
if wf and wf.is_dir():
    for f in sorted(wf.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        if f.name == "registry.md" or any(f.name.endswith(s) for s in RESERVED):
            continue
        playbooks_checked += 1
        parsed = engine.parse_playbook(f.read_text(encoding="utf-8", errors="ignore"))
        tier = (parsed.get("header") or {}).get("model_tier")
        if tier is None:
            continue  # default realtime-standard; nothing to validate
        tiers_seen += 1
        if tier not in TIER_ENUM:
            failures.append("%s: model-tier '%s' is not one of %s"
                            % (f.name, tier, ", ".join(TIER_ENUM)))
else:
    notes.append("no conversation-workflows dir - model-tier enum validation skipped (static wiring only)")

verdict = "PASS" if not failures else "FAIL"

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-model-fallback",
        "verdict": verdict,
        "playbooks_checked": playbooks_checked,
        "model_tiers_seen": tiers_seen,
        "workflows_dir": WF_DIR or None,
        "failures": failures,
        "notes": notes,
    }, indent=2))
else:
    print("=== qc-model-fallback: model fallback chain (U-8) + model tier (U-10) ===")
    print("skill root: %s" % SKILL_ROOT)
    print("workflows dir: %s" % (WF_DIR or "<none - static wiring only>"))
    print("playbooks checked: %d (with model-tier: %d)" % (playbooks_checked, tiers_seen))
    for nt in notes:
        print("  [note] %s" % nt)
    print("")
    if failures:
        for msg in failures:
            print("  [FAIL] %s" % msg)
        print("")
        print("RESULT: FAIL - %d model-fallback/model-tier violation(s)." % len(failures))
    else:
        print("RESULT: PASS - fallback chain wired, freshness reviews the chain, every model-tier is in enum.")

sys.exit(1 if failures else 0)
PYEOF

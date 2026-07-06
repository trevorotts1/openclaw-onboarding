#!/usr/bin/env bash
# qc-workflow-exits.sh (U-2) - machine-enforce tag-driven workflow exit rules.
#
# Two layers of enforcement:
#   (A) STATIC WIRING (always checked, CI-relevant): the workflow-exit-rules
#       protocol file, the AGENTS marker, the MEMORY rule, and the JSONL sink seed
#       must all exist in the skill repo. A missing piece is a FAIL.
#   (B) PLAYBOOK CONTENT (checked when a conversation-workflows dir is present):
#       every exit rule must use an action in {end, handoff, route}; a route
#       action REQUIRES a target, and that target must be present in registry.md.
#
# This gate does NOT parse playbook markdown itself. It shells out to the
# canonical parser tools/playbook_engine.py (U-16) and applies the exit-rule
# pass/fail policy to the engine's structured output.
#
# Exit codes: 0 = pass; 1 = an exit-rule violation or missing wiring; 2 = the
#             engine is missing / python3 unavailable (cannot judge).
#
# Usage:
#   bash scripts/qc-workflow-exits.sh                 # auto-locate workflows via pointer
#   bash scripts/qc-workflow-exits.sh --dir <conversation-workflows>
#   bash scripts/qc-workflow-exits.sh --json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"

WF_DIR=""
JSON_MODE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) WF_DIR="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENGINE" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "qc-workflow-exits: canonical engine tools/playbook_engine.py or python3 not available."
  exit 2
fi

if [ -z "$WF_DIR" ]; then
  POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
  if [ -f "$POINTER" ]; then
    MFD="$(cat "$POINTER")"; MFD="${MFD%$'\n'}"
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

failures = []

def contains(path, needle):
    p = SKILL_ROOT / path
    return p.is_file() and needle in p.read_text(encoding="utf-8", errors="ignore")

# --- (A) Static wiring checks. -------------------------------------------
if not (SKILL_ROOT / "protocols" / "workflow-exit-rules-protocol.md").is_file():
    failures.append("missing protocols/workflow-exit-rules-protocol.md")
if not contains("scripts/05-update-agents-md.sh", "STEP_1_30_EXIT_RULES"):
    failures.append("missing AGENTS marker STEP_1_30_EXIT_RULES in scripts/05-update-agents-md.sh")
if not contains("scripts/06-append-memory-rules.sh", "v1.8.0-rules-workflow-exits"):
    failures.append("missing MEMORY Rule 33 (workflow exits) in scripts/06-append-memory-rules.sh")
if not contains("scripts/25-seed-round3-feature-files.sh", "workflow-exit-events.jsonl"):
    failures.append("missing workflow-exit-events.jsonl seed in scripts/25-seed-round3-feature-files.sh")

# --- (B) Playbook content checks (when a workflows dir is present). -------
RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
            "--verification-checklist.md", "--ghl-side.md")

def registry_ids(reg_path):
    ids = set()
    if not reg_path.is_file():
        return ids
    for line in reg_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip().strip("`").strip() for c in s.strip("|").split("|")]
            if cells:
                rid = cells[0]
                if rid and rid.lower() != "id" and not (set(rid) <= set("-: ")):
                    ids.add(rid)
    return ids

playbooks_checked = 0
wf = Path(WF_DIR) if WF_DIR else None
if wf and wf.is_dir():
    reg_ids = registry_ids(wf / "registry.md")
    for f in sorted(wf.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        if f.name == "registry.md" or any(f.name.endswith(s) for s in RESERVED):
            continue
        playbooks_checked += 1
        parsed = engine.parse_playbook(f.read_text(encoding="utf-8", errors="ignore"))
        for idx, rule in enumerate(parsed["exit_rules"], start=1):
            label = "%s exit rule %d ('%s')" % (f.name, idx, rule.get("tag") or "?")
            action = rule.get("action")
            if action not in engine.EXIT_ACTIONS:
                failures.append("%s action '%s' is not one of end/handoff/route" % (label, action))
                continue
            if action == "route":
                tgt = rule.get("target")
                if not tgt:
                    failures.append("%s action route requires a target playbook id" % label)
                elif reg_ids and tgt not in reg_ids:
                    failures.append("%s routes to target '%s' which is absent from registry.md" % (label, tgt))

verdict = "PASS" if not failures else "FAIL"

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-workflow-exits",
        "verdict": verdict,
        "playbooks_checked": playbooks_checked,
        "workflows_dir": WF_DIR or None,
        "failures": failures,
    }, indent=2))
else:
    print("=== qc-workflow-exits: tag-driven workflow exits (U-2) ===")
    print("skill root: %s" % SKILL_ROOT)
    print("workflows dir: %s" % (WF_DIR or "<none - static wiring only>"))
    print("playbooks checked: %d" % playbooks_checked)
    print("")
    if failures:
        for msg in failures:
            print("  [FAIL] %s" % msg)
        print("")
        print("RESULT: FAIL - %d workflow-exit violation(s)." % len(failures))
    else:
        print("RESULT: PASS - exit rules wired and every checked rule has a valid action and resolvable route target.")

sys.exit(1 if failures else 0)
PYEOF

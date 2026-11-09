#!/usr/bin/env bash
# qc-playbook-craft.sh — enforce D-9 conversational craft contract on Layer-2 playbooks.
#
# Six craft contracts:
#   1. Objection library
#   2. Turn discipline
#   3. Ambiguity and multi-intent
#   4. Stall recovery
#   5. Golden transcript
#   6. Conversational KPIs
# Content quality beyond section presence is checked by engine.conversation_lint.
#
# Exit codes: 0 = PASS; 1 = one or more craft defects; 2 = usage or workflows-folder
# error, or no playbooks; 3 = reserved for empty-playbook scan result; 4 = canonical
# engine or python3 unavailable.
#
# Usage:
#   bash scripts/qc-playbook-craft.sh [--dir <conversation-workflows>] [--json]

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"

WF_DIR=""
JSON_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dir)
      if [ $# -lt 2 ] || [ -z "$2" ]; then
        echo "Missing path for --dir." >&2
        exit 2
      fi
      WF_DIR="$2"
      shift 2
      ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENGINE" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "qc-playbook-craft: canonical engine tools/playbook_engine.py or python3 not available."
  exit 4
fi

if [ -z "$WF_DIR" ]; then
  POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
  if [ -f "$POINTER" ]; then
    MFD="$(cat "$POINTER")"
    MFD="${MFD%$'\n'}"
    [ -n "$MFD" ] && WF_DIR="$MFD/conversation-workflows"
  fi
fi

if [ -z "$WF_DIR" ] || [ ! -d "$WF_DIR" ]; then
  echo "qc-playbook-craft: no conversation-workflows folder at '${WF_DIR:-<unset>}'." >&2
  echo "  Pass --dir <path>, or run after 01-locate-master-files-folder.sh has written the pointer." >&2
  exit 2
fi

export SKILL_ROOT ENGINE WF_DIR JSON_MODE

python3 - <<'PYEOF'
import json
import os
import sys
from pathlib import Path

ENGINE = Path(os.environ["ENGINE"])
SKILL_ROOT = Path(os.environ["SKILL_ROOT"])
WF_DIR = os.environ.get("WF_DIR", "")
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"

sys.path.insert(0, str(ENGINE.parent))
import playbook_engine as engine

RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
            "--verification-checklist.md", "--ghl-side.md")

def is_playbook(path):
    return (
        path.is_file()
        and path.name.endswith(".md")
        and path.name != "registry.md"
        and not any(path.name.endswith(suffix) for suffix in RESERVED)
    )

wf = Path(WF_DIR)
playbooks = sorted(path for path in wf.iterdir() if is_playbook(path))

if not playbooks:
    if JSON_MODE:
        print(json.dumps({
            "gate": "qc-playbook-craft",
            "verdict": "NO_PLAYBOOKS",
            "playbooks_checked": 0,
            "workflows_dir": WF_DIR,
            "failures": [],
        }, indent=2))
    else:
        print("=== qc-playbook-craft: conversational craft contract (D-9) ===")
        print("skill root: %s" % SKILL_ROOT)
        print("workflows dir: %s" % WF_DIR)
        print("playbooks checked: 0")
        print("")
        print("RESULT: NO PLAYBOOKS")
    sys.exit(3)

failures = []

required_sections = (
    "turn discipline",
    "ambiguity and multi-intent",
    "stall recovery",
)

for f in playbooks:
    text = f.read_text(encoding="utf-8", errors="ignore")
    parsed = engine.parse_playbook(text)

    failures.extend("%s: %s" % (f.name, d)
                    for d in engine.conversation_lint(parsed))

    lines = engine._strip_fence(text.splitlines())
    for heading in required_sections:
        section = engine.section_lines(lines, heading)
        if not engine._non_placeholder_lines(section):
            failures.append(
                "%s: missing the '%s' craft section (non-placeholder content required)"
                % (f.name, heading)
            )

verdict = "PASS" if not failures else "FAIL"

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-playbook-craft",
        "verdict": verdict,
        "playbooks_checked": len(playbooks),
        "workflows_dir": WF_DIR,
        "failures": failures,
    }, indent=2))
else:
    print("=== qc-playbook-craft: conversational craft contract (D-9) ===")
    print("skill root: %s" % SKILL_ROOT)
    print("workflows dir: %s" % WF_DIR)
    print("playbooks checked: %d" % len(playbooks))
    print("")
    for msg in failures:
        print("  [FAIL] %s" % msg)
    if failures:
        print("RESULT: FAIL - %d craft defect(s)." % len(failures))
    else:
        print("RESULT: PASS - all checked playbooks satisfy conversational craft contract.")

sys.exit(1 if failures else 0)
PYEOF

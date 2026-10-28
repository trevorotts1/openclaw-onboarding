#!/usr/bin/env bash
# qc-tool-gating.sh (U-1) - machine-enforce per-phase tool gating.
#
# Two layers of enforcement:
#   (A) STATIC WIRING (always checked, CI-relevant): the tool-gating protocol
#       file, the AGENTS marker, the MEMORY rule, and the JSONL sink seed must all
#       exist in the skill repo. A missing piece is a FAIL.
#   (B) PLAYBOOK CONTENT (checked when a conversation-workflows dir is present):
#       every registered playbook phase must reference only tools in the U-1
#       vocabulary, and NO phase may gate off escalate_to_human.
#
# This gate does NOT parse playbook markdown itself. It shells out to the
# canonical parser tools/playbook_engine.py (U-16) and applies the tool-gating
# pass/fail policy to the engine's structured output.
#
# Exit codes: 0 = pass; 1 = a tool-gating violation or missing wiring; 2 = the
#             engine is missing / python3 unavailable (cannot judge).
#
# Usage:
#   bash scripts/qc-tool-gating.sh                 # auto-locate workflows via pointer
#   bash scripts/qc-tool-gating.sh --dir <conversation-workflows>
#   bash scripts/qc-tool-gating.sh --json

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
  echo "qc-tool-gating: canonical engine tools/playbook_engine.py or python3 not available."
  exit 2
fi

# Auto-locate the client's conversation-workflows dir via the pointer file.
if [ -z "$WF_DIR" ]; then
  POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
  if [ -f "$POINTER" ]; then
    MFD="$(cat "$POINTER")"; MFD="${MFD%$'\n'}"
    [ -n "$MFD" ] && WF_DIR="$MFD/conversation-workflows"
  fi
fi

# ── LIVE AGENTS.md resolver (content-version-aware gate) — see qc-segmentation.sh
if [ -z "${AGENTS_MD:-}" ]; then
  if [ "$(uname -s)" = "Darwin" ]; then AGENTS_MD="$HOME/clawd/AGENTS.md"; else AGENTS_MD="/data/clawd/AGENTS.md"; fi
fi

export SKILL_ROOT ENGINE WF_DIR JSON_MODE AGENTS_MD

python3 - <<'PYEOF'
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(os.environ["SKILL_ROOT"])
ENGINE = Path(os.environ["ENGINE"])
WF_DIR = os.environ.get("WF_DIR", "")
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"
AGENTS_MD = os.environ.get("AGENTS_MD", "")

sys.path.insert(0, str(ENGINE.parent))
import playbook_engine as engine  # canonical parser (U-16)

failures = []

# --- (A) Static wiring checks. -------------------------------------------
def contains(path, needle):
    p = SKILL_ROOT / path
    return p.is_file() and needle in p.read_text(encoding="utf-8", errors="ignore")

def contains_live_agents(needle):
    # None = no live AGENTS.md to check (SKIP, not a failure).
    if not AGENTS_MD or not os.path.isfile(AGENTS_MD):
        return None
    try:
        return needle in Path(AGENTS_MD).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

if not (SKILL_ROOT / "protocols" / "tool-gating-protocol.md").is_file():
    failures.append("missing protocols/tool-gating-protocol.md")
if not contains("scripts/05-update-agents-md.sh", "STEP_1_88_TOOL_GATING"):
    failures.append("SOURCE scripts/05-update-agents-md.sh is missing the STEP_1_88_TOOL_GATING marker text")
_live = contains_live_agents("STEP_1_88_TOOL_GATING")
if _live is None:
    print("  [SKIP] no live AGENTS.md found at %r — cannot verify the box actually received the STEP_1_88_TOOL_GATING marker (set AGENTS_MD to override)" % AGENTS_MD, file=sys.stderr)
elif not _live:
    failures.append("LIVE AGENTS.md (%s) is MISSING the STEP_1_88_TOOL_GATING marker — the pointer-stanza writer (05-update-agents-md.sh) has not run on this box; a shipped-source check alone cannot prove this" % AGENTS_MD)
else:
    print("  [PASS] LIVE AGENTS.md (%s) carries the STEP_1_88_TOOL_GATING marker — 05-update-agents-md.sh has actually run on this box" % AGENTS_MD, file=sys.stderr)
if not contains("references/memory-design-rules.md", "v1.8.0-rules-tool-gating"):
    failures.append("missing MEMORY Rule 32 (tool gating) in references/memory-design-rules.md")
if not contains("scripts/25-seed-round3-feature-files.sh", "tool-gate-events.jsonl"):
    failures.append("missing tool-gate-events.jsonl seed in scripts/25-seed-round3-feature-files.sh")

# --- (B) Playbook content checks (when a workflows dir is present). -------
RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
            "--verification-checklist.md", "--ghl-side.md")

playbooks_checked = 0
wf = Path(WF_DIR) if WF_DIR else None
if wf and wf.is_dir():
    for f in sorted(wf.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        if f.name == "registry.md" or any(f.name.endswith(s) for s in RESERVED):
            continue
        playbooks_checked += 1
        parsed = engine.parse_playbook(f.read_text(encoding="utf-8", errors="ignore"))
        for ph in parsed["phases"]:
            label = "%s Phase %s (%s)" % (f.name, ph["number"], ph["name"] or "unnamed")
            if ph.get("tools") is not None:
                for tool in ph["tools"]:
                    if tool not in engine.TOOL_VOCABULARY:
                        failures.append("%s references out-of-vocabulary tool '%s'" % (label, tool))
            for g in (ph.get("disable_global") or []):
                if g in engine.ALWAYS_GRANTED:
                    failures.append("%s gates off always-granted tool '%s' (escalate_to_human can never be gated off)" % (label, g))

verdict = "PASS" if not failures else "FAIL"

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-tool-gating",
        "verdict": verdict,
        "playbooks_checked": playbooks_checked,
        "workflows_dir": WF_DIR or None,
        "failures": failures,
    }, indent=2))
else:
    print("=== qc-tool-gating: per-phase tool gating (U-1) ===")
    print("skill root: %s" % SKILL_ROOT)
    print("workflows dir: %s" % (WF_DIR or "<none - static wiring only>"))
    print("playbooks checked: %d" % playbooks_checked)
    print("")
    if failures:
        for msg in failures:
            print("  [FAIL] %s" % msg)
        print("")
        print("RESULT: FAIL - %d tool-gating violation(s)." % len(failures))
    else:
        print("RESULT: PASS - tool gating wired and every checked phase is in-vocabulary with escalate intact.")

sys.exit(1 if failures else 0)
PYEOF

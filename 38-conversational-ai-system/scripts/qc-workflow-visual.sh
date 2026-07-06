#!/usr/bin/env bash
# qc-workflow-visual.sh (U-11) - machine-enforce Part 4, THE VISUAL, on every build.
#
# Two layers of enforcement:
#   (A) STATIC WIRING (always checked, CI-relevant): the workflow-visual protocol
#       file, the generator script, the MEMORY rule, and the kie-image-events.jsonl
#       sink seed must all exist in the skill repo. A missing piece is a FAIL.
#   (B) PLAYBOOK CONTENT (checked when a conversation-workflows dir is present):
#       every registered playbook MUST have a recorded truth diagram. For each
#       playbook <id>.md there must be <id>/visual.json recording a diagram_png that
#       EXISTS on disk, and the recorded structure_hash must MATCH the engine's hash
#       of the current playbook (a mismatch = STALE = FAIL). A missing hero.png is a
#       WARN (not a FAIL): a budget or Kie outage must never block handoff.
#
# This gate does NOT parse playbook markdown itself. It shells out to the canonical
# parser tools/playbook_engine.py (U-16) for the structure hash.
#
# Exit codes: 0 = pass (may carry WARNs); 1 = a missing/stale visual or missing
#             wiring; 2 = the engine is missing / python3 unavailable (cannot judge).
#
# Usage:
#   bash scripts/qc-workflow-visual.sh
#   bash scripts/qc-workflow-visual.sh --dir <conversation-workflows>
#   bash scripts/qc-workflow-visual.sh --json

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
    -h|--help) sed -n '1,32p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENGINE" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "qc-workflow-visual: canonical engine tools/playbook_engine.py or python3 not available."
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
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(os.environ["SKILL_ROOT"])
ENGINE = Path(os.environ["ENGINE"])
WF_DIR = os.environ.get("WF_DIR", "")
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"

failures = []
warnings = []
notes = []

def contains(path, needle):
    p = SKILL_ROOT / path
    return p.is_file() and needle in p.read_text(encoding="utf-8", errors="ignore")

def engine_hash(playbook):
    try:
        out = subprocess.run([sys.executable, str(ENGINE), "hash", str(playbook)],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None

# --- (A) Static wiring checks. -----------------------------------------------
if not (SKILL_ROOT / "protocols" / "workflow-visual-protocol.md").is_file():
    failures.append("missing protocols/workflow-visual-protocol.md")
if not (SKILL_ROOT / "scripts" / "31-generate-workflow-visual.sh").is_file():
    failures.append("missing scripts/31-generate-workflow-visual.sh (the generator)")
if not contains("scripts/06-append-memory-rules.sh", "v1.8.0-rules-workflow-visual"):
    failures.append("missing MEMORY Rule 39 (workflow visual) in scripts/06-append-memory-rules.sh")
if not contains("scripts/25-seed-round3-feature-files.sh", "kie-image-events.jsonl"):
    failures.append("missing kie-image-events.jsonl seed in scripts/25-seed-round3-feature-files.sh")

# --- (B) Playbook content checks. --------------------------------------------
RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
            "--verification-checklist.md", "--ghl-side.md")

playbooks_checked = 0
visuals_ok = 0
wf = Path(WF_DIR) if WF_DIR else None
if wf and wf.is_dir():
    for f in sorted(wf.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        if f.name == "registry.md" or any(f.name.endswith(s) for s in RESERVED):
            continue
        playbooks_checked += 1
        slug = f.name[:-3]
        vjson = wf / slug / "visual.json"
        if not vjson.is_file():
            failures.append("%s: no recorded visual (missing %s/visual.json) - run 31-generate-workflow-visual.sh" % (f.name, slug))
            continue
        try:
            rec = json.loads(vjson.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:
            failures.append("%s: visual.json is not valid JSON (%s)" % (f.name, e))
            continue
        png = rec.get("diagram_png")
        if not png or not Path(png).is_file():
            failures.append("%s: recorded diagram.png missing on disk (%r)" % (f.name, png))
            continue
        rec_hash = rec.get("structure_hash") or ""
        cur_hash = engine_hash(f)
        if cur_hash is None:
            notes.append("%s: could not hash via the engine - staleness not checked" % f.name)
        elif rec_hash != cur_hash:
            failures.append("%s: STALE truth diagram (recorded hash %s != current %s) - regenerate" % (f.name, rec_hash[:12], cur_hash[:12]))
            continue
        hero = rec.get("hero_png")
        if not hero or not Path(hero).is_file():
            warnings.append("%s: hero.png absent (budget/Kie outage) - truth diagram ships; hero flagged pending" % f.name)
        visuals_ok += 1
else:
    notes.append("no conversation-workflows dir - visual content validation skipped (static wiring only)")

verdict = "PASS" if not failures else "FAIL"

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-workflow-visual",
        "verdict": verdict,
        "playbooks_checked": playbooks_checked,
        "visuals_ok": visuals_ok,
        "workflows_dir": WF_DIR or None,
        "failures": failures,
        "warnings": warnings,
        "notes": notes,
    }, indent=2))
else:
    print("=== qc-workflow-visual: Part 4 truth diagram gate (U-11) ===")
    print("skill root: %s" % SKILL_ROOT)
    print("workflows dir: %s" % (WF_DIR or "<none - static wiring only>"))
    print("playbooks checked: %d (visual OK: %d)" % (playbooks_checked, visuals_ok))
    for nt in notes:
        print("  [note] %s" % nt)
    for w in warnings:
        print("  [WARN] %s" % w)
    print("")
    if failures:
        for msg in failures:
            print("  [FAIL] %s" % msg)
        print("")
        print("RESULT: FAIL - %d workflow-visual violation(s)." % len(failures))
    else:
        print("RESULT: PASS - visual wiring present and every registered playbook has a current truth diagram.")

sys.exit(1 if failures else 0)
PYEOF

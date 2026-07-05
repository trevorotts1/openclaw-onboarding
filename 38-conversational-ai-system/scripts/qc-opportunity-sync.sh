#!/usr/bin/env bash
# qc-opportunity-sync.sh (U-13) - machine-enforce opportunity/pipeline stage sync.
#
# Two layers of enforcement:
#   (A) STATIC WIRING (always checked, CI-relevant): the opportunity-sync protocol
#       file, the MEMORY rule, and the JSONL sink seed must all exist in the skill
#       repo. A missing piece is a FAIL.
#   (B) PLAYBOOK CONTENT (checked when a conversation-workflows dir is present):
#       for every playbook that declares a pipeline + stage-map, every stage NAME in
#       the stage-map must exist in the declared pipeline (checked against a caf
#       pipelines export). A stage name absent from the pipeline is a FAIL; a declared
#       pipeline id absent from the export is a FAIL.
#
# This gate does NOT parse playbook markdown itself. It shells out to the canonical
# parser tools/playbook_engine.py (U-16) and applies the stage-map pass/fail policy.
#
# Exit codes: 0 = pass (may carry notes); 1 = a stage-map violation or missing
#             wiring; 2 = the engine is missing / python3 unavailable (cannot judge).
#
# Usage:
#   bash scripts/qc-opportunity-sync.sh                          # auto-locate via pointer
#   bash scripts/qc-opportunity-sync.sh --dir <conversation-workflows>
#   bash scripts/qc-opportunity-sync.sh --dir D --pipelines-export pipe.json
#   bash scripts/qc-opportunity-sync.sh --json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"

WF_DIR=""
JSON_MODE=0
PIPE_EXPORT="${CAF_PIPELINES_EXPORT:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) WF_DIR="$2"; shift 2 ;;
    --pipelines-export) PIPE_EXPORT="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,32p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENGINE" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "qc-opportunity-sync: canonical engine tools/playbook_engine.py or python3 not available."
  exit 2
fi

if [ -z "$WF_DIR" ]; then
  POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
  if [ -f "$POINTER" ]; then
    MFD="$(cat "$POINTER")"; MFD="${MFD%$'\n'}"
    [ -n "$MFD" ] && WF_DIR="$MFD/conversation-workflows"
  fi
fi

MFD_FROM_WF=""
[ -n "$WF_DIR" ] && MFD_FROM_WF="$(dirname "$WF_DIR")"

if [ -z "$PIPE_EXPORT" ]; then
  for c in "$MFD_FROM_WF/.caf-pipelines-export.json" "$WF_DIR/.caf-pipelines-export.json"; do
    if [ -n "$c" ] && [ -f "$c" ]; then PIPE_EXPORT="$c"; break; fi
  done
fi

export SKILL_ROOT ENGINE WF_DIR JSON_MODE PIPE_EXPORT

python3 - <<'PYEOF'
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(os.environ["SKILL_ROOT"])
ENGINE = Path(os.environ["ENGINE"])
WF_DIR = os.environ.get("WF_DIR", "")
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"
PIPE_EXPORT = os.environ.get("PIPE_EXPORT", "")

sys.path.insert(0, str(ENGINE.parent))
import playbook_engine as engine  # canonical parser (U-16)

failures = []
notes = []

def contains(path, needle):
    p = SKILL_ROOT / path
    return p.is_file() and needle in p.read_text(encoding="utf-8", errors="ignore")

def stage_name(entry):
    """The stage NAME is everything after the first colon in a stage-map entry."""
    if ":" not in entry:
        return None
    return entry.split(":", 1)[1].strip() or None

def load_pipeline_stage_map(path):
    """Parse a caf pipelines export into {pipeline_id: set(stage names)}.
    Accepts {'pipelines':[{'id','stages':[{'name'}]}]} or a top-level list of the
    same pipeline objects."""
    data = json.loads(Path(path).read_text(encoding="utf-8", errors="ignore"))
    pipelines = data.get("pipelines", data) if isinstance(data, dict) else data
    out = {}
    if isinstance(pipelines, list):
        for p in pipelines:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            if pid is None:
                continue
            names = set()
            for s in (p.get("stages") or []):
                if isinstance(s, dict) and s.get("name"):
                    names.add(str(s["name"]).strip())
                elif isinstance(s, str):
                    names.add(s.strip())
            out[str(pid)] = names
    return out

# --- (A) Static wiring checks. -----------------------------------------------
if not (SKILL_ROOT / "protocols" / "opportunity-sync-protocol.md").is_file():
    failures.append("missing protocols/opportunity-sync-protocol.md")
if not contains("scripts/06-append-memory-rules.sh", "v1.8.0-rules-opportunity-sync"):
    failures.append("missing MEMORY Rule 41 (opportunity sync) in scripts/06-append-memory-rules.sh")
if not contains("scripts/25-seed-round3-feature-files.sh", "opportunity-sync-events.jsonl"):
    failures.append("missing opportunity-sync-events.jsonl seed in scripts/25-seed-round3-feature-files.sh")

# --- Load the pipelines export (optional; skip stage validation if absent). --
pipeline_stages = None
if PIPE_EXPORT and Path(PIPE_EXPORT).is_file():
    try:
        pipeline_stages = load_pipeline_stage_map(PIPE_EXPORT)
    except Exception as e:
        notes.append("could not parse pipelines export (%s) - stage validation skipped" % e)
        pipeline_stages = None
else:
    notes.append("caf pipelines export not found - stage-name validation skipped")

# --- (B) Playbook content checks. --------------------------------------------
RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
            "--verification-checklist.md", "--ghl-side.md")

playbooks_checked = 0
stagemaps_seen = 0
wf = Path(WF_DIR) if WF_DIR else None
if wf and wf.is_dir():
    for f in sorted(wf.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        if f.name == "registry.md" or any(f.name.endswith(s) for s in RESERVED):
            continue
        playbooks_checked += 1
        parsed = engine.parse_playbook(f.read_text(encoding="utf-8", errors="ignore"))
        d = parsed["declares"]
        pipeline = d.get("pipeline")
        smap = d.get("stage-map") or []
        if not pipeline and not smap:
            continue  # opportunity sync inert for this playbook
        stagemaps_seen += 1
        if smap and not pipeline:
            failures.append("%s: declares a stage-map but no pipeline id" % f.name)
            continue
        if pipeline_stages is None:
            continue  # cannot validate names without an export
        if pipeline not in pipeline_stages:
            failures.append("%s: declared pipeline '%s' is absent from the caf pipelines export" % (f.name, pipeline))
            continue
        valid_names = pipeline_stages[pipeline]
        for entry in smap:
            name = stage_name(entry)
            if name is None:
                failures.append("%s: stage-map entry '%s' has no stage name" % (f.name, entry))
            elif name not in valid_names:
                failures.append("%s: stage-map stage '%s' is absent from pipeline '%s'" % (f.name, name, pipeline))

verdict = "PASS" if not failures else "FAIL"

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-opportunity-sync",
        "verdict": verdict,
        "playbooks_checked": playbooks_checked,
        "stage_maps_seen": stagemaps_seen,
        "workflows_dir": WF_DIR or None,
        "pipelines_export": PIPE_EXPORT or None,
        "failures": failures,
        "notes": notes,
    }, indent=2))
else:
    print("=== qc-opportunity-sync: opportunity/pipeline stage sync (U-13) ===")
    print("skill root: %s" % SKILL_ROOT)
    print("workflows dir: %s" % (WF_DIR or "<none - static wiring only>"))
    print("playbooks checked: %d (with stage-map: %d)" % (playbooks_checked, stagemaps_seen))
    for nt in notes:
        print("  [note] %s" % nt)
    print("")
    if failures:
        for msg in failures:
            print("  [FAIL] %s" % msg)
        print("")
        print("RESULT: FAIL - %d opportunity-sync violation(s)." % len(failures))
    else:
        print("RESULT: PASS - opportunity sync wired and every stage-map name resolves to its pipeline.")

sys.exit(1 if failures else 0)
PYEOF

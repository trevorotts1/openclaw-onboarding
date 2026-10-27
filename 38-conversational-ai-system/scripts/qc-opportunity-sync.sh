#!/usr/bin/env bash
# qc-opportunity-sync.sh (U-13) - machine-enforce opportunity/pipeline stage sync.
#
# Two layers of enforcement:
#   (A) STATIC WIRING (always checked, CI-relevant): the opportunity-sync protocol
#       file, the MEMORY rule, and the JSONL sink seed must all exist in the skill
#       repo. A missing piece is a FAIL.
#   (B) PLAYBOOK CONTENT (checked when a conversation-workflows dir is present):
#       every declared pipeline or stage-map requires a usable caf pipelines export.
#       A missing or unparseable export is a FAIL, never a skipped validation.
#
# This gate shells out to canonical parser tools/playbook_engine.py (U-16).
#
# Exit codes: 0 = pass (may carry notes); 1 = violation or missing wiring;
#             2 = the engine is missing / python3 unavailable (cannot judge).
#
# Usage:
#   bash scripts/qc-opportunity-sync.sh
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
    --dir)
      [ $# -ge 2 ] || { echo "Missing value for --dir" >&2; exit 2; }
      WF_DIR="$2"; shift 2 ;;
    --pipelines-export)
      [ $# -ge 2 ] || { echo "Missing value for --pipelines-export" >&2; exit 2; }
      PIPE_EXPORT="$2"; shift 2 ;;
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

export SKILL_ROOT ENGINE WF_DIR JSON_MODE PIPE_EXPORT MFD_FROM_WF

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
MFD_FROM_WF = os.environ.get("MFD_FROM_WF", "")

sys.path.insert(0, str(ENGINE.parent))
import playbook_engine as engine

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
    """Parse a caf pipelines export into {pipeline_id: set(stage names)}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pipelines = data.get("pipelines") if isinstance(data, dict) else data
    if not isinstance(pipelines, list):
        raise ValueError("expected a list under top-level key 'pipelines'")

    out = {}
    for pipeline in pipelines:
        if not isinstance(pipeline, dict) or pipeline.get("id") is None:
            continue
        stages = pipeline.get("stages") or []
        if not isinstance(stages, list):
            raise ValueError("pipeline %s has non-list stages" % pipeline["id"])
        names = set()
        for stage in stages:
            if isinstance(stage, dict) and stage.get("name"):
                names.add(str(stage["name"]).strip())
            elif isinstance(stage, str):
                names.add(stage.strip())
        out[str(pipeline["id"])] = names

    if not out:
        raise ValueError("no pipeline objects carrying IDs")
    return out


def missing_export_message(filename, pipeline, stage_map):
    if pipeline:
        declaration = "pipeline '%s'" % pipeline
    else:
        declaration = "a stage-map"
    return (
        "REQUIRES_OPERATOR: %s: declares %s but the caf pipelines export is missing. "
        "Produce it with 44-convert-and-flow-operator/tools/export_deps.py to "
        "%s/.caf-pipelines-export.json (or %s/.caf-pipelines-export.json)."
        % (
            filename,
            declaration,
            MFD_FROM_WF,
            WF_DIR,
        )
    )


# --- (A) Static wiring checks. -----------------------------------------------
if not (SKILL_ROOT / "protocols" / "opportunity-sync-protocol.md").is_file():
    failures.append("missing protocols/opportunity-sync-protocol.md")
if not contains("references/memory-design-rules.md", "v1.8.0-rules-opportunity-sync"):
    failures.append("missing MEMORY Rule 41 (opportunity sync) in references/memory-design-rules.md")
if not contains("scripts/25-seed-round3-feature-files.sh", "opportunity-sync-events.jsonl"):
    failures.append("missing opportunity-sync-events.jsonl seed in scripts/25-seed-round3-feature-files.sh")

# --- (B) Playbook content checks. --------------------------------------------
RESERVED = (
    "--build-with-ai-prompt.md",
    "--workflow-ai-prompt.md",
    "--verification-checklist.md",
    "--ghl-side.md",
)

playbooks_checked = 0
stagemaps_seen = 0
declared_playbooks = []
wf = Path(WF_DIR) if WF_DIR else None

if wf and wf.is_dir():
    for f in sorted(wf.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        if f.name == "registry.md" or any(f.name.endswith(s) for s in RESERVED):
            continue

        playbooks_checked += 1
        parsed = engine.parse_playbook(f.read_text(encoding="utf-8", errors="ignore"))
        declarations = parsed["declares"]
        pipeline = declarations.get("pipeline")
        stage_map = declarations.get("stage-map") or []

        if not pipeline and not stage_map:
            continue

        stagemaps_seen += 1
        declared_playbooks.append((f, pipeline, stage_map))

pipeline_stages = None
export_error = None
if PIPE_EXPORT and Path(PIPE_EXPORT).is_file():
    try:
        pipeline_stages = load_pipeline_stage_map(PIPE_EXPORT)
    except Exception as exc:
        export_error = str(exc)
else:
    export_error = "file not found"

if declared_playbooks and pipeline_stages is None:
    if PIPE_EXPORT and Path(PIPE_EXPORT).is_file():
        failures.append(
            "REQUIRES_OPERATOR: caf pipelines export exists but cannot be parsed: %s: %s"
            % (PIPE_EXPORT, export_error)
        )
    for f, pipeline, stage_map in declared_playbooks:
        failures.append(missing_export_message(f.name, pipeline, stage_map))
elif not declared_playbooks:
    notes.append("no checked playbook declares a pipeline or stage-map")

for f, pipeline, stage_map in declared_playbooks:
    if stage_map and not pipeline:
        failures.append("%s: declares a stage-map but no pipeline id" % f.name)
        continue
    if pipeline_stages is None:
        continue

    if pipeline not in pipeline_stages:
        failures.append(
            "%s: declared pipeline '%s' is absent from the caf pipelines export"
            % (f.name, pipeline)
        )
        continue

    valid_names = pipeline_stages[pipeline]
    for entry in stage_map:
        name = stage_name(entry)
        if name is None:
            failures.append("%s: stage-map entry '%s' has no stage name" % (f.name, entry))
        elif name not in valid_names:
            failures.append(
                "%s: stage-map stage '%s' is absent from pipeline '%s'"
                % (f.name, name, pipeline)
            )

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
    for note in notes:
        print("  [note] %s" % note)
    print("")
    if failures:
        for message in failures:
            print("  [FAIL] %s" % message)
        print("")
        print("RESULT: FAIL - %d opportunity-sync violation(s)." % len(failures))
    else:
        print("RESULT: PASS - opportunity sync wired and every stage-map name resolves to its pipeline.")

sys.exit(1 if failures else 0)
PYEOF

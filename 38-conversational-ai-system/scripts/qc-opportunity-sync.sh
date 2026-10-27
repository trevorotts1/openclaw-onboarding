#!/usr/bin/env bash
# qc-opportunity-sync.sh (U-13) - machine-enforce opportunity/pipeline stage sync.
#
# Two layers of enforcement:
#   (A) STATIC WIRING (always checked, CI-relevant): the opportunity-sync protocol
#       file, the MEMORY rule, and the JSONL sink seed must all exist in the skill
#       repo. A missing piece is a FAIL.
#   (B) PLAYBOOK CONTENT (checked when a conversation-workflows dir is present):
#       every declared pipeline or stage-map requires a usable caf pipelines export.
#       A missing, unparseable or STALE export is a FAIL, never a skipped validation.
#       Stale means exported_at is absent, unparseable, or older than 24h (see
#       MAX_EXPORT_AGE_SECONDS): a pipeline or stage deleted in GHL since the last
#       successful refresh would otherwise still validate against the old file.
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
    -h|--help) sed -n '1,24p' "$0"; exit 0 ;;
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

# PIPE_EXPORT (explicit) is honoured as given. Otherwise the two legacy locations
# are candidates, and the judge below picks the first one that is both readable and
# CURRENT, not merely present: a stale copy in one location must not shadow a fresh
# copy in the other.
PIPE_CANDIDATES=""
if [ -z "$PIPE_EXPORT" ]; then
  for base in "$MFD_FROM_WF" "$WF_DIR"; do
    [ -n "$base" ] || continue
    PIPE_CANDIDATES="${PIPE_CANDIDATES:+$PIPE_CANDIDATES$'\n'}$base/.caf-pipelines-export.json"
  done
fi

export SKILL_ROOT ENGINE WF_DIR JSON_MODE PIPE_EXPORT PIPE_CANDIDATES MFD_FROM_WF

python3 - <<'PYEOF'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(os.environ["SKILL_ROOT"])
ENGINE = Path(os.environ["ENGINE"])
WF_DIR = os.environ.get("WF_DIR", "")
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"
PIPE_EXPORT = os.environ.get("PIPE_EXPORT", "")
PIPE_CANDIDATES = [p for p in os.environ.get("PIPE_CANDIDATES", "").split("\n") if p]
MFD_FROM_WF = os.environ.get("MFD_FROM_WF", "")

sys.path.insert(0, str(ENGINE.parent))
import playbook_engine as engine

# Freshness contract for .caf-pipelines-export.json, written by
# 44-convert-and-flow-operator/tools/export_deps.py. An export is current
# evidence only if exported_at is present, parses, and is at most this old.
# "The file parses" and "the file is current" are two different questions, and
# only the second one makes a declared pipeline/stage name meaningful.
MAX_EXPORT_AGE_SECONDS = 24 * 60 * 60
CLOCK_SKEW_SECONDS = 5 * 60
NOW = datetime.now(timezone.utc)
REFRESH = "Re-run 44-convert-and-flow-operator/tools/export_deps.py to refresh it."

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


def human_age(seconds):
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return "%dd %dh" % (days, hours)
    if hours:
        return "%dh %dm" % (hours, minutes)
    return "%dm" % minutes


def freshness_violation(path, data):
    """None when the export is current evidence, else why it is not."""
    stamp = data.get("exported_at") if isinstance(data, dict) else None
    if not stamp:
        return (
            "EXPORT_UNDATED: %s carries no exported_at timestamp, so its age cannot be "
            "checked and it is not current evidence. %s" % (path, REFRESH)
        )
    try:
        when = datetime.fromisoformat(str(stamp).strip().replace("Z", "+00:00"))
    except ValueError:
        return (
            "EXPORT_TIMESTAMP_UNPARSEABLE: %s has exported_at %r, which is not an "
            "ISO-8601 timestamp, so its age cannot be checked. %s" % (path, stamp, REFRESH)
        )
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    age = (NOW - when).total_seconds()
    if age > MAX_EXPORT_AGE_SECONDS:
        return (
            "EXPORT_STALE: %s was exported %s ago (exported_at %s, limit %dh), so the "
            "pipeline ids and stage names it holds are not current evidence - a pipeline "
            "or stage deleted since then still validates against it. %s"
            % (path, human_age(age), stamp, MAX_EXPORT_AGE_SECONDS // 3600, REFRESH)
        )
    if age < -CLOCK_SKEW_SECONDS:
        return (
            "EXPORT_TIMESTAMP_IN_FUTURE: %s has exported_at %s, which is %s in the "
            "future; a freshness check cannot judge it. %s"
            % (path, stamp, human_age(-age), REFRESH)
        )
    return None


def load_pipeline_stage_map(data):
    """Parse a caf pipelines export into {pipeline_id: set(stage names)}."""
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
resolved_export = None
undated_or_stale = []
unparseable = []
candidates = [PIPE_EXPORT] if PIPE_EXPORT else PIPE_CANDIDATES

for candidate in candidates:
    if not Path(candidate).is_file():
        continue
    try:
        data = json.loads(Path(candidate).read_text(encoding="utf-8"))
    except Exception as exc:
        unparseable.append((candidate, str(exc)))
        continue
    violation = freshness_violation(candidate, data)
    if violation:
        undated_or_stale.append(violation)
        continue
    try:
        pipeline_stages = load_pipeline_stage_map(data)
    except Exception as exc:
        unparseable.append((candidate, str(exc)))
        continue
    resolved_export = candidate
    break

if declared_playbooks and pipeline_stages is None:
    for message in undated_or_stale:
        failures.append("REQUIRES_OPERATOR: " + message)
    for candidate, exc in unparseable:
        failures.append(
            "REQUIRES_OPERATOR: caf pipelines export exists but cannot be parsed: %s: %s"
            % (candidate, exc)
        )
    if not undated_or_stale and not unparseable:
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
        "pipelines_export": resolved_export or PIPE_EXPORT or None,
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

#!/usr/bin/env python3
# ======================================================================
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_IO = 3
EXIT_BLOCKED = 4

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parents[1] / "tools" / "engine"
# The units qc-built-workflow.sh WF-9 understands (it maps singular and plural to plural).
DELAY_UNITS = {"minute": "minutes", "minutes": "minutes", "hour": "hours", "hours": "hours",
               "day": "days", "days": "days"}


class EmitError(Exception):
    def __init__(self, code, message, exit_code=EXIT_INVALID):
        super().__init__("%s: %s" % (code, message))
        self.exit_code = exit_code


def _compile(document):
    sys.path.insert(0, str(ENGINE))
    try:
        from cli_anything.gohighlevel.utils.workflow_builder import compile_launch_builds
    except ImportError as exc:
        raise EmitError("ENGINE-MISSING", "the Skill 44 engine is not importable (%s)" % exc, EXIT_IO)
    finally:
        sys.path.remove(str(ENGINE))
    return compile_launch_builds(document, require_ready=True)


def _wait_entry(step, where):
    attrs = step.get("attributes") if isinstance(step.get("attributes"), dict) else {}
    start = attrs.get("startAfter")
    if isinstance(start, dict) and "value" in start and "type" in start:
        unit = DELAY_UNITS.get(str(start["type"]).lower())
        value = start["value"]
        if unit is None or not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise EmitError("WAIT-UNSUPPORTED", "%s wait startAfter %r is not a minutes/hours/days delay"
                            % (where, start))
        return {"kind": "delay", "value": value, "unit": unit}
    until = attrs.get("untilDate")
    if not (isinstance(until, str) and until.strip()):
        raise EmitError("WAIT-UNRESOLVED", "%s wait %r has no resolved date" % (where, step.get("id")))
    try:
        parsed = datetime.fromisoformat(until.strip().replace("Z", "+00:00"))
    except ValueError:
        raise EmitError("WAIT-UNRESOLVED", "%s wait date %r is not ISO-8601" % (where, until))
    if parsed.tzinfo is None:
        raise EmitError("WAIT-UNRESOLVED", "%s wait date %r has no UTC offset" % (where, until))
    return {"kind": "until_date", "until": until.strip()}


def emit(document, unit, workflow_key=None):
    """The {"waits": [...]} schedule of one compiled workflow of `unit`."""
    if not isinstance(document, dict):
        raise EmitError("DOCUMENT-INVALID", "the automation-build document is not a JSON object")
    builds = [b for b in document.get("builds") or [] if isinstance(b, dict)]
    if not any(b.get("id") == unit for b in builds):
        raise EmitError("UNIT-UNKNOWN", "no build %r in the document (have: %s)"
                        % (unit, ", ".join(sorted(str(b.get("id")) for b in builds))))
    campaign = _compile(document)
    refusal = next((r for r in campaign.refusals if r.get("id") == unit), None)
    if refusal:
        raise EmitError("UNIT-BLOCKED", "%s: %s" % (refusal.get("code"), refusal.get("reason")),
                        EXIT_BLOCKED)
    members = {k: v for k, v in campaign.items() if v.get("source_unit") == unit}
    if workflow_key is None:
        if len(members) != 1:
            raise EmitError("WORKFLOW-AMBIGUOUS", "unit %r compiles to %d workflows; pass "
                            "--workflow-key (one of: %s)" % (unit, len(members), ", ".join(sorted(members))))
        workflow_key = next(iter(members))
    elif workflow_key not in members:
        raise EmitError("WORKFLOW-UNKNOWN", "unit %r has no workflow %r (have: %s)"
                        % (unit, workflow_key, ", ".join(sorted(members))))
    steps = members[workflow_key].get("templates") or []
    waits = [_wait_entry(s, workflow_key) for s in steps
             if isinstance(s, dict) and str(s.get("type", "")).lower() == "wait"]
    if not waits:
        raise EmitError("NO-WAITS", "workflow %r compiles no wait steps; WF-9 refuses an empty "
                        "schedule, so a launch build here has nothing to compare" % workflow_key)
    return {"waits": waits}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Emit the WF-9 launch schedule for one automation unit.")
    ap.add_argument("--automation-build", required=True, help="launch-c automation-builds.json")
    ap.add_argument("--unit", required=True, help="the automation id (builds[].id)")
    ap.add_argument("--workflow-key", help="needed only when the unit compiles to several workflows")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        document = json.loads(Path(args.automation_build).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("emit-launch-schedule: cannot read %s: %s" % (args.automation_build, exc), file=sys.stderr)
        return EXIT_IO
    try:
        schedule = emit(document, args.unit, args.workflow_key)
        Path(args.out).write_text(json.dumps(schedule, indent=2) + "\n", encoding="utf-8")
    except EmitError as exc:
        print("emit-launch-schedule: %s" % exc, file=sys.stderr)
        return exc.exit_code
    except OSError as exc:
        print("emit-launch-schedule: IO: %s" % exc, file=sys.stderr)
        return EXIT_IO
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Export live CAF calendars and pipelines for Skill 38 QC gates.

This is the ONLY producer of .caf-calendars-export.json and
.caf-pipelines-export.json consumed by Skill 38's qc-playbook-declares.sh
and qc-opportunity-sync.sh. Requires live PIT-authenticated caf access.
No network access means no export, never a fabricated one.

Freshness contract (enforced by the consumers at read time)
-----------------------------------------------------------
Every export carries ``exported_at``, an ISO-8601 UTC timestamp. A consumer
treats an export as current evidence ONLY when that timestamp is present, is
parseable, and is no more than MAX_AGE_HOURS old. Anything else is rejected by
name - EXPORT_UNDATED, EXPORT_TIMESTAMP_UNPARSEABLE, EXPORT_STALE, or
EXPORT_TIMESTAMP_IN_FUTURE - never silently accepted. Undated evidence is not
current evidence, and "the file parses" is not the same question as "the file
is current".

A failed run exits 3 and deliberately leaves the previous export in place, so a
bad refresh never destroys a good file. That makes the file's age the only thing
separating "refreshed" from "abandoned", which is why the age is machine-checked
by the consumer rather than trusted here.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
POINTER = Path.home() / ".openclaw" / ".skill-38-master-files-dir"
CALENDAR_CMD = ["--json", "calendars", "list"]
PIPELINE_CMD = ["--json", "opportunities", "pipelines"]
# The consumers (Skill 38's qc-opportunity-sync.sh, qc-playbook-declares.sh)
# reject an export whose exported_at is older than this. Kept here so the
# producer's failure text states the same number the consumer enforces.
MAX_AGE_HOURS = 24
PIPELINE_LEFT_UNCHANGED = (
    "pipelines export failed; previous pipeline export left unchanged. "
    "That file is NOT refreshed: consumers reject an export whose exported_at "
    "is older than %d hours, so re-run this tool once caf recovers." % MAX_AGE_HOURS
)


def resolve_workflows_dir(override):
    tried = []
    if override:
        candidate = Path(override).expanduser()
        tried.append(str(candidate))
        if candidate.is_dir():
            return candidate.resolve()
        raise ValueError("Workflows directory does not exist. Paths tried: " + ", ".join(tried))

    env_dir = os.environ.get("CAF_WORKFLOWS_DIR")
    if env_dir:
        candidate = Path(env_dir).expanduser()
        tried.append(str(candidate))
        if candidate.is_dir():
            return candidate.resolve()

    tried.append(str(POINTER))
    if POINTER.is_file():
        try:
            master = POINTER.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError("Cannot read pointer %s: %s" % (POINTER, exc)) from exc
        if master:
            candidate = Path(master).expanduser() / "conversation-workflows"
            tried.append(str(candidate))
            if candidate.is_dir():
                return candidate.resolve()

    raise ValueError("Workflows directory not found. Paths tried: " + ", ".join(tried))


def resolve_caf(override):
    tried = []
    candidates = []
    if override:
        candidates.append(("--caf", Path(override).expanduser()))
    else:
        env_caf = os.environ.get("CAF_BIN")
        if env_caf:
            candidates.append(("CAF_BIN", Path(env_caf).expanduser()))
        candidates.append(("bundled", SKILL_ROOT / "tools" / "engine" / "caf"))

    for label, candidate in candidates:
        tried.append("%s=%s" % (label, candidate))
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())

    found = shutil.which("caf")
    tried.append("shutil.which('caf')=%s" % (found or "<not found>"))
    if found and os.access(found, os.X_OK):
        return found

    raise ValueError("Executable caf not found. Paths tried: " + ", ".join(tried))


def command_text(command):
    import shlex
    return shlex.join(command)


def stderr_excerpt(stderr):
    lines = (stderr or "").splitlines()
    return "\n".join(lines[:20]) or "<empty stderr>"


def fetch_payload(caf, args, timeout, label):
    command = [caf] + args
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        print(
            "%s failed: command=%s exit_status=timeout (%ss)\nstderr:\n%s"
            % (label, command_text(command), timeout, stderr_excerpt(stderr)),
            file=sys.stderr,
        )
        return None
    except OSError as exc:
        print(
            "%s failed: command=%s exit_status=execution-error\nstderr:\n%s"
            % (label, command_text(command), str(exc)),
            file=sys.stderr,
        )
        return None

    if result.returncode != 0:
        print(
            "%s failed: command=%s exit_status=%s\nstderr:\n%s"
            % (
                label,
                command_text(command),
                result.returncode,
                stderr_excerpt(result.stderr),
            ),
            file=sys.stderr,
        )
        return None

    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        print(
            "%s failed: command=%s exit_status=%s; JSON parse error: %s\nstderr:\n%s"
            % (
                label,
                command_text(command),
                result.returncode,
                exc,
                stderr_excerpt(result.stderr),
            ),
            file=sys.stderr,
        )
        return None


def validate_payload(payload, key, label):
    if isinstance(payload, dict):
        observed_keys = sorted(payload.keys())
    else:
        observed_keys = []

    items = payload.get(key) if isinstance(payload, dict) else None
    if (
        not isinstance(items, list)
        or not any(isinstance(item, dict) and item.get("id") is not None for item in items)
    ):
        print(
            "%s failed: invalid response shape; observed top-level keys=%s"
            % (label, observed_keys),
            file=sys.stderr,
        )
        return None
    return items


def normalise_calendars(items):
    output = []
    for item in items:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        output.append({
            "id": str(item["id"]),
            "name": str(item.get("name") or ""),
        })
    return output


def normalise_pipelines(items):
    output = []
    for item in items:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        stages = []
        raw_stages = item.get("stages") or []
        if isinstance(raw_stages, list):
            for stage in raw_stages:
                if not isinstance(stage, dict) or stage.get("id") is None:
                    continue
                position = stage.get("position")
                stages.append({
                    "id": str(stage["id"]),
                    "name": str(stage.get("name") or ""),
                    "position": position,
                })
        output.append({
            "id": str(item["id"]),
            "name": str(item.get("name") or ""),
            "stages": stages,
        })
    return output


def atomic_write(destination, payload):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(destination.parent),
            prefix=destination.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
    except OSError:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


def main():
    parser = argparse.ArgumentParser(description="Export live CAF calendar and pipeline dependencies.")
    parser.add_argument("--workflows-dir")
    parser.add_argument("--caf")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--json", action="store_true", dest="json_mode")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    try:
        workflows_dir = resolve_workflows_dir(args.workflows_dir)
        caf = resolve_caf(args.caf)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    calendar_path = workflows_dir / ".caf-calendars-export.json"
    pipeline_path = workflows_dir / ".caf-pipelines-export.json"
    calendar_command = [caf] + CALENDAR_CMD
    pipeline_command = [caf] + PIPELINE_CMD

    if args.dry_run:
        summary = {
            "calendars_export": str(calendar_path),
            "pipelines_export": str(pipeline_path),
            "calendars_count": None,
            "pipelines_count": None,
            "caf": caf,
            "dry_run": True,
        }
        if args.json_mode:
            print(json.dumps(summary, separators=(",", ":")))
        else:
            print("calendars export: %s" % calendar_path)
            print("calendars command: %s" % command_text(calendar_command))
            print("pipelines export: %s" % pipeline_path)
            print("pipelines command: %s" % command_text(pipeline_command))
        return 0

    location_id = (
        os.environ.get("GOHIGHLEVEL_LOCATION_ID")
        or os.environ.get("GHL_LOCATION_ID")
        or None
    )
    exported_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    calendar_payload = fetch_payload(caf, CALENDAR_CMD, args.timeout, "calendars")
    if calendar_payload is None:
        return 3
    calendars = validate_payload(calendar_payload, "calendars", "calendars")
    if calendars is None:
        return 3
    calendars = normalise_calendars(calendars)
    if not calendars:
        print("calendars failed: no valid calendar objects carrying IDs", file=sys.stderr)
        return 3

    try:
        atomic_write(calendar_path, {
            "exported_at": exported_at,
            "location_id": location_id,
            "calendars": calendars,
        })
    except OSError as exc:
        print("calendars export write failed: %s" % exc, file=sys.stderr)
        return 3

    pipeline_payload = fetch_payload(caf, PIPELINE_CMD, args.timeout, "pipelines")
    if pipeline_payload is None:
        print("calendars export succeeded: %s" % calendar_path, file=sys.stderr)
        print(PIPELINE_LEFT_UNCHANGED, file=sys.stderr)
        return 3
    pipelines = validate_payload(pipeline_payload, "pipelines", "pipelines")
    if pipelines is None:
        print("calendars export succeeded: %s" % calendar_path, file=sys.stderr)
        print(PIPELINE_LEFT_UNCHANGED, file=sys.stderr)
        return 3
    pipelines = normalise_pipelines(pipelines)
    if not pipelines:
        print("calendars export succeeded: %s" % calendar_path, file=sys.stderr)
        print("pipelines export failed: no valid pipeline objects carrying IDs", file=sys.stderr)
        return 3

    try:
        atomic_write(pipeline_path, {
            "exported_at": exported_at,
            "location_id": location_id,
            "pipelines": pipelines,
        })
    except OSError as exc:
        print("calendars export succeeded: %s" % calendar_path, file=sys.stderr)
        print("pipelines export write failed: %s" % exc, file=sys.stderr)
        return 3

    summary = {
        "calendars_export": str(calendar_path),
        "pipelines_export": str(pipeline_path),
        "calendars_count": len(calendars),
        "pipelines_count": len(pipelines),
        "caf": caf,
        "dry_run": False,
    }
    if args.json_mode:
        print(json.dumps(summary, separators=(",", ":")))
    else:
        print("calendars export: %s (%d)" % (calendar_path, len(calendars)))
        print("pipelines export: %s (%d)" % (pipeline_path, len(pipelines)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Export interrupted; no further exports written.", file=sys.stderr)
        sys.exit(3)

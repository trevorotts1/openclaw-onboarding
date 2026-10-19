#!/usr/bin/env python3
"""shared_page_service.py - Skill 71's shared image service entry point.

Produces the four image stages (desktop wireframe, mobile wireframe,
desktop mockup, mobile mockup) for ONE page of a named page_role, for
every role in the page-request enum. The owning skill's wrapper calls
this script ONCE per page; the 14-stage production contract is never
duplicated into Skills 78, 79, 80, 81 or 82.

The service stages the page-request, launch record, route graph and
brand file where Skill 71's launch-context import expects them, stamps
the shared-service marker (references/page-request.schema.json
`shared_image_service`) into the staged request, runs
scripts/write_intake.py -- the same seam 49-signature-funnel's
landing_bridge.py uses -- and then runs the caller-supplied production
pipeline command, which executes the stage contract including the four
image stages (scripts/stage_executor.py is that command: one Skill 74
call per image, four stage folders, no gate receipts).

Fail-closed: the page_role must be in the page-request enum, the
assigned_skill must be one of the sharing skills (71, 78, 79, 80, 81,
82), and the route graph and brand bytes must hash to the request's
recorded hashes. Nothing is written and no consumer runs on refusal.

Exit codes: 0 ok; 2 fail-closed / consumer failure; 3 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
WRITE_INTAKE = SKILL_ROOT / "scripts" / "write_intake.py"
REQUEST_SCHEMA = SKILL_ROOT / "references" / "page-request.schema.json"
MARKER = "shared_image_service"
MARKER_ID = "71-blackceo-signature-page"
SHARED_SKILLS = (71, 78, 79, 80, 81, 82)

class ServiceError(Exception):
    """The request cannot enter the shared image service; fail closed."""

def _read(path: Path, label: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise ServiceError(f"{label}: cannot read {path}: {exc}")

def _json(raw: bytes, label: str):
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise ServiceError(f"{label}: not valid JSON: {exc}")

def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _stage(run_dir: Path, ref: str, raw: bytes, label: str) -> None:
    rel = Path(ref)
    if rel.is_absolute() or ".." in rel.parts:
        raise ServiceError(
            f"{label}: {ref!r} is not a run-relative path; the service "
            "stages inside the run directory and refuses a ref that "
            "escapes it")
    target = run_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Skill 71 shared image service: admit one page of a "
                    "named page_role into the four-image pipeline.")
    p.add_argument("--request", type=Path, required=True)
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--page-version", choices=["standard", "long-form"],
                   required=True)
    p.add_argument("--brand-owner", required=True)
    p.add_argument("--image-cap", type=int, required=True)
    p.add_argument("--brand-file", type=Path, required=True)
    p.add_argument("--launch-record", type=Path, required=True)
    p.add_argument("--route-graph", type=Path, required=True)
    p.add_argument("--consent-statements", type=Path, default=None)
    p.add_argument("--pipeline-command", default=None,
                   help="the production pipeline command run after the "
                        "launch-context import (for example the run's "
                        "stage_gate sequence); one shell-style string")
    a = p.parse_args(argv)
    if a.image_cap < 0:
        print("REFUSED: --image-cap must be >= 0")
        return 2
    try:
        roles = _json(_read(REQUEST_SCHEMA, "page-request schema"),
                      "page-request schema")
        role_enum = roles["properties"]["page_role"]["enum"]
        request_raw = _read(a.request, "page-request")
        request = _json(request_raw, "page-request")
        if not isinstance(request, dict):
            raise ServiceError("page-request: the document is not a JSON "
                               "object")
        role = request.get("page_role")
        if role not in role_enum:
            raise ServiceError(
                f"page-request: page_role {role!r} is not one of "
                f"{role_enum}")
        if request.get("assigned_skill") not in SHARED_SKILLS:
            raise ServiceError(
                f"page-request: assigned_skill is "
                f"{request.get('assigned_skill')!r}; the shared image "
                f"service serves skills {SHARED_SKILLS} only")
        graph_raw = _read(a.route_graph, "route graph")
        if _sha256(graph_raw) != request.get("route_graph_hash"):
            raise ServiceError(
                "route graph: the supplied bytes do not hash to the "
                "request's route_graph_hash; stale routing is refused")
        brand_raw = _read(a.brand_file, "brand file")
        if _sha256(brand_raw) != request.get("brand_hash"):
            raise ServiceError(
                "brand file: the supplied bytes do not hash to the "
                "request's brand_hash; the approved brand is refused "
                "when it does not match")
        launch_raw = _read(a.launch_record, "launch record")

        run_dir = Path(a.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        staged = dict(request)
        staged[MARKER] = MARKER_ID
        staged_raw = (json.dumps(staged, indent=2, sort_keys=True)
                      + "\n").encode("utf-8")
        (run_dir / "page-request.json").write_bytes(staged_raw)
        (run_dir / "launch.json").write_bytes(launch_raw)
        _stage(run_dir, request["route_graph_ref"], graph_raw,
               "route_graph_ref")
        _stage(run_dir, request["brand_ref"], brand_raw, "brand_ref")

        intake_argv = [sys.executable, str(WRITE_INTAKE), str(run_dir),
                       "--page-version", a.page_version,
                       "--brand-owner", a.brand_owner,
                       "--brand-file", request["brand_ref"],
                       "--image-cap", str(a.image_cap),
                       "--launch-context", str(run_dir / "page-request.json"),
                       "--launch-record", str(run_dir / "launch.json"),
                       "--route-graph", str(run_dir / request["route_graph_ref"])]
        if a.consent_statements is not None:
            intake_argv += ["--consent-statements", str(a.consent_statements)]
        subprocess.run(intake_argv, check=True)
        if a.pipeline_command:
            subprocess.run(shlex.split(a.pipeline_command), check=True,
                           cwd=str(run_dir))
    except ServiceError as exc:
        print(f"REFUSED: {exc}")
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: consumer exited {exc.returncode}")
        return 2
    print(f"shared image service: page_role {role!r} admitted; the "
          "four image stages (desktop-wireframe, mobile-tablet, "
          "visual-mockup, final-mockups) run on the stage contract")
    return 0

if __name__ == "__main__":
    sys.exit(main())

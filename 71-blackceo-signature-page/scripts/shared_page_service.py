#!/usr/bin/env python3
"""shared_page_service.py - Skill 71's shared image service entry point.

Produces the four image stages (desktop wireframe, mobile wireframe,
desktop mockup, mobile mockup) for ONE page of a named page_role, for
every role in the page-request enum. The owning skill's wrapper calls
this script ONCE per page; the 14-stage production contract is never
duplicated into Skills 78, 79, 80, 81 or 82. Wired today: the upsell roles
(scripts/run_page_type.py calls this service, then builds and runs the
stages; Skill 49's upsell_wrapper.py --bridge-config calls that runner).
The other sharing skills' wrappers do not call it yet.

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

Modes:
  generation (default): requires --pipeline-command. Success is wired to
      image files on disk for the stages the run executed -- readable
      image bytes and desktop/mobile mockup widths -- never to the
      pipeline command merely exiting 0. Zero images is FAILED.
  validation-only (--validation-only): admits and stages the request,
      runs write_intake.py, generates nothing, and says so with the
      MODE=validation-only line. It can never read as a generated run.

Exit codes: 0 ok; 2 fail-closed / consumer failure / generation not
proven; 3 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import copy_forms  # noqa: E402  the one registry of copy forms
import page_role  # noqa: E402  a page type's own spec: role to form check below

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import design_style  # noqa: E402  the client's A / B / C choice rides through to the intake
import stage_gate  # noqa: E402  (artifact/format/dimension success check)
WRITE_INTAKE = SCRIPTS / "write_intake.py"
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
    p.add_argument("--page-version", choices=list(copy_forms.FORMS),
                   required=True,
                   help="the page's form: standard or long-form for a landing page, "
                        "product-selection for the order page (page_role product_selection), "
                        "upsell for the upsell pages (page_roles upsell_1, upsell_2), "
                        "thank-you for page_role thank_you")
    p.add_argument("--test-run", action="store_true")
    p.add_argument("--brand-owner")
    p.add_argument("--image-cap", type=int)
    p.add_argument("--brand-file", type=Path)
    p.add_argument("--image-inputs", type=Path, default=None,
                   help="the launch's shared image inputs file (image_inputs.json): supplies "
                        "--brand-owner, --image-cap, --brand-file and --design-style when they are "
                        "not typed here; a flag typed here wins")
    p.add_argument("--launch-record", type=Path, required=True)
    p.add_argument("--route-graph", type=Path, required=True)
    p.add_argument("--consent-statements", type=Path, default=None)
    p.add_argument("--design-style", default=None,
                   help="the client's design style (A Block, B Circle, C Hybrid), recorded in the "
                        "intake like any page; omitted, the intake notes it is still to be asked")
    p.add_argument("--pipeline-command", default=None,
                   help="the production pipeline command run after the "
                        "launch-context import (for example the run's "
                        "stage_gate sequence); one shell-style string. "
                        "Required for a generation run.")
    p.add_argument("--validation-only", action="store_true",
                   help="admit and stage the request, generate nothing, "
                        "and label the output MODE=validation-only")
    a = p.parse_args(argv)
    if a.image_inputs:
        try:
            shared = json.loads(a.image_inputs.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"REFUSED: --image-inputs {a.image_inputs}: {exc}")
            return 2
        for key, attr, cast in (("brand_owner", "brand_owner", str), ("image_cap", "image_cap", int),
                                ("brand_file", "brand_file", Path), ("design_style", "design_style", str)):
            if getattr(a, attr) is None and shared.get(key) not in (None, ""):
                setattr(a, attr, cast(shared[key]))
    absent = [f"--{n.replace('_', '-')}" for n in ("brand_owner", "image_cap", "brand_file")
              if getattr(a, n) is None]
    if absent:
        p.error("the following arguments are required (or pass --image-inputs): " + ", ".join(absent))
    if a.design_style and a.design_style not in design_style.STYLE_IDS:
        p.error(f"--design-style must be one of {design_style.STYLE_IDS}")
    if a.image_cap < 0:
        print("REFUSED: --image-cap must be >= 0")
        return 2
    if a.validation_only and a.pipeline_command:
        print("REFUSED: --validation-only and --pipeline-command are "
              "mutually exclusive; a validation run generates nothing")
        return 3
    if not a.validation_only and not a.pipeline_command:
        print("FAILED: a generation run requires --pipeline-command and "
              "none was supplied; nothing was generated (use "
              "--validation-only to admit the request without generating)")
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
        own = page_role.spec_for_role(role)
        want = own["copy_version"] if own else None
        wrong_form = (a.page_version != want) if own else (
            page_role.role_specs().get(a.page_version) is not None)
        if wrong_form:
            raise ServiceError(
                f"page-request: page_role {role!r} takes --page-version "
                f"{want or 'standard or long-form'}, not {a.page_version!r}; a page type is "
                "never forced into another page type's canonical sections")
        if request.get("assigned_skill") not in SHARED_SKILLS:
            raise ServiceError(
                f"page-request: assigned_skill is "
                f"{request.get('assigned_skill')!r}; the shared image "
                f"service serves skills {SHARED_SKILLS} only")
        form = copy_forms.form_for_role(role)
        if form != (a.page_version if a.page_version not in copy_forms.LANDING_FORMS else None):
            raise ServiceError(
                f"--page-version {a.page_version!r} does not fit page_role {role!r}: "
                + (f"this role is built from the {form!r} form" if form else
                   "this role is a landing page and takes standard or long-form"))
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
        if a.design_style:
            intake_argv += ["--design-style", a.design_style]
        if a.test_run:
            intake_argv.append("--test-run")
        subprocess.run(intake_argv, check=True)
        if a.validation_only:
            pass
        else:
            subprocess.run(shlex.split(a.pipeline_command), check=True,
                           cwd=str(run_dir))
    except ServiceError as exc:
        print(f"REFUSED: {exc}")
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"FAILED: consumer exited {exc.returncode}; the generation "
              "run is not proven")
        return 2
    if a.validation_only:
        print("MODE=validation-only: no artifacts generated")
        print(f"shared image service: page_role {role!r} admitted "
              "(validation only; the four image stages did not run)")
        return 0
    failures, image_count = stage_gate.verify_generated_images(run_dir)
    if failures:
        print("FAILED")
        for line in failures:
            print(f"- {line}")
        print(f"FAILED: the generation run produced {image_count} image(s) "
              "and does not prove a generation run")
        return 2
    print(f"shared image service: page_role {role!r} admitted; "
          f"{image_count} image(s) verified on disk for the stages that ran")
    return 0

if __name__ == "__main__":
    sys.exit(main())

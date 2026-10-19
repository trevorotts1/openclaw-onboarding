#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checkout_wrapper.py - bridge between S49 dispatch and the order form (checkout) page's
wireframes and mockups.

The order form itself is the native Convert and Flow form installed by Skill 06 (CR-S49-003);
Skill 79 ships fixture models and component drafts but no command that builds a page. This
wrapper is the invocable command dispatch runs for the checkout role, and what it produces is
the DESIGN of that page: desktop and mobile wireframes and the visual mockups, through Skill 71's
own pipeline. Nothing here duplicates that pipeline:

  1. ADMIT   71-blackceo-signature-page/scripts/shared_page_service.py checks the page-request
             (page_role checkout, assigned skill 79, route graph and brand hashes), stages the
             run and records the intake (launch context, brand, design style A / B / C).
  2. BUILD   scripts/build_production_request.py --page-role checkout turns the approved
             checkout manuscript into one production request per stage: five sections (the role
             spec references/copy-specs/roles/checkout.json), the client's brand colours, the
             role's slots, grounds, composition roles and desktop / mobile layout.
  3. RUN     scripts/stage_executor.py runs desktop-wireframe, mobile-tablet and visual-mockup.
             On the paid provider it also composes the one long PDF per stage and the overview
             boards (stage_executor / combine_review_pdf.py / build_overview_board.py).
  4. RESULT  a page-result 1.0 whose artifacts are those design files, validated through
             collect_launch_receipts.validate_result before it is placed.

The manuscript is a staged input (--manuscript, "## Section N: name" headings, written from the
approved references in the Skill 79 checkout request: offer, price display, bump, guarantee,
terms and consent). The wrapper never writes copy; a manuscript that names card, expiry or
security-code fields is refused, because the payment form is native only.

HONESTY CEILING: status authored, proof L0, native_bindings_ref null. The result names its
standing blockers: the form is still installed by Skill 06, the design board and final mockups
wait for the image chain and the client's board approval (design_board.py gate), and a stub run
carries placeholder images only. The default provider is stub (free); --provider kie needs
--allow-paid and the client's own KIE_API_KEY, exactly as stage_executor.py does.

Exit 0 result placed; 2 fail-closed refusal; 3 usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from collect_launch_receipts import validate_result  # noqa: E402
import page_set  # noqa: E402  the shared image inputs and the page's full deliverables list

EXIT_OK, EXIT_FAILCLOSED, EXIT_USAGE = 0, 2, 3
ROLE, SKILL = "checkout", 79
STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
DELIVERABLE_DIRS = (*STAGES, "review-pdfs")
CARD_FIELDS = re.compile(r"card number|credit card|cvc|cvv|security code|expiry|expiration date", re.I)
BLOCKERS = (
    "the native checkout form is installed by Skill 06; this result carries the page's design "
    "stages only and no native binding",
    "the design board and final-mockups wait for the image chain and the client's recorded "
    "board approval (design_board.py gate)",
)
STUB_BLOCKER = "stub provider: the images are placeholders, not design deliverables"


class WrapperError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd, what):
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        raise WrapperError(f"{what} exited {proc.returncode}: {' | '.join(tail)[:600]}")


def load(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WrapperError(f"{what}: cannot read {path}: {exc}")


def artifacts(run_dir: Path) -> list:
    """Every design file of the page (section images, PDFs, boards, stage records, visual bible)
    plus the production requests, sorted by path."""
    found = {a["path"]: a for a in page_set.design_artifacts("checkout", run_dir)}
    for s in STAGES:
        p = run_dir / f"production-request-{s}.json"
        found[str(p)] = {"path": str(p), "sha256": sha256(p)}
    for d in DELIVERABLE_DIRS:  # any other file a stage wrote into its own folder
        for p in (run_dir / d).rglob("*") if (run_dir / d).is_dir() else ():
            if p.is_file() and str(p) not in found:
                found[str(p)] = {"path": str(p), "sha256": sha256(p)}
    return [found[k] for k in sorted(found)]


def produce(args, request) -> dict:
    if request.get("page_role") != ROLE or request.get("assigned_skill") != SKILL:
        raise WrapperError(f"the request is for page_role {request.get('page_role')!r}, skill "
                           f"{request.get('assigned_skill')!r}; this wrapper serves {ROLE!r}, skill {SKILL}")
    manuscript = Path(args.manuscript)
    text = manuscript.read_text(encoding="utf-8") if manuscript.is_file() else None
    if text is None:
        raise WrapperError(f"manuscript {manuscript} is missing; the checkout copy is written from the "
                           "approved references in the Skill 79 checkout request, never by this wrapper")
    if CARD_FIELDS.search(text):
        raise WrapperError("the manuscript names card, expiry or security-code fields; the payment form is "
                           f"the native checkout form only ({CARD_FIELDS.search(text).group(0)!r})")
    s71 = Path(args.skill71_root) / "scripts"
    for name in ("shared_page_service.py", "build_production_request.py", "stage_executor.py"):
        if not (s71 / name).is_file():
            raise WrapperError(f"Skill 71 script {name} not found under {s71}")
    run_dir = Path(args.run_dir).resolve()
    admit = [sys.executable, s71 / "shared_page_service.py", "--request", args.request, "--run-dir", run_dir,
             "--page-version", "standard", "--brand-owner", args.brand_owner, "--image-cap", args.image_cap,
             "--brand-file", args.brand_file, "--launch-record", args.launch, "--route-graph", args.route_graph,
             "--validation-only"]  # admission seam only; the stages below generate
    if args.design_style:
        admit += ["--design-style", args.design_style]
    run(admit, "shared_page_service.py")
    page_set.stage_visual_bible(getattr(args, "inputs", None), run_dir)
    for stage in STAGES:
        name = f"production-request-{stage}.json"
        build = [sys.executable, s71 / "build_production_request.py", "--page-role", ROLE, "--manuscript",
                 manuscript, "--stage", stage, "--out", run_dir / name, "--run-dir", run_dir]
        for flag, value in (("--slots", args.slots), ("--design-prose", args.design_prose),
                            ("--model", args.model)):
            if value:
                build += [flag, value]
        run(build, f"build_production_request.py ({stage})")
        execute = [sys.executable, s71 / "stage_executor.py", run_dir, "--stages", stage, "--request", name,
                   "--provider", args.provider] + (["--allow-paid"] if args.allow_paid else [])
        run(execute, f"stage_executor.py ({stage})")
    return {"artifacts": artifacts(run_dir),
            "blockers": list(BLOCKERS) + ([STUB_BLOCKER] if args.provider == "stub" else [])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for flag in ("request", "result", "manuscript", "launch", "route-graph", "run-dir"):
        ap.add_argument(f"--{flag}", required=True)
    for flag in ("brand-file", "brand-owner", "image-cap"):  # or one --image-inputs file
        ap.add_argument(f"--{flag}")
    ap.add_argument("--image-inputs", help="the shared image inputs file (design style, brand file, owner, "
                                           "image cap, provider); a flag typed here still wins")
    ap.add_argument("--skill71-root", default=str(HERE.parents[1] / "71-blackceo-signature-page"))
    ap.add_argument("--design-style", choices=("A", "B", "C"))
    ap.add_argument("--slots", help="slots.json overriding the role spec's default slots")
    ap.add_argument("--design-prose", help="the run's measured design system, as build_production_request.py reads it")
    ap.add_argument("--model", help="image model id (default: build_production_request.py's)")
    ap.add_argument("--provider", choices=("stub", "kie"), default="stub")
    ap.add_argument("--allow-paid", action="store_true")
    ap.add_argument("--author-session", default=os.environ.get("SIGNATURE_LAUNCH_AUTHOR_SESSION")
                    or os.environ.get("OPENCLAW_SESSION_ID") or "s49-checkout-wrapper")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    result_path = Path(args.result)
    try:
        args.inputs = None
        if args.image_inputs:
            inputs = args.inputs = page_set.load_image_inputs(args.image_inputs)
            page_set.fill_args(args, inputs, {"brand_file": "brand_file", "brand_owner": "brand_owner",
                                              "image_cap": "image_cap", "design_style": "design_style",
                                              "design_prose_ref": "design_prose"})
            if args.provider == "stub" and inputs["image_provider"] == "kie":
                args.provider, args.allow_paid = "kie", inputs["allow_paid"]
        missing = [f for f in ("brand_file", "brand_owner", "image_cap") if args.__dict__.get(f) in (None, "")]
        if missing:
            raise WrapperError("missing " + ", ".join("--" + m.replace("_", "-") for m in missing)
                               + " (or pass --image-inputs)")
        args.image_cap = str(args.image_cap)
        request = load(args.request, "page-request")
        made = produce(args, request)
        result = {"schema_version": "1.0", **{k: request[k] for k in (
                      "tenant_id", "location_id", "launch_id", "revision", "request_id", "input_hash", "page_id")},
                  "status": "authored", "artifacts": made["artifacts"], "author_session": args.author_session,
                  "reviewer_session": None, "independent_review": False, "proof_class": "L0",
                  "blockers": made["blockers"], "native_bindings_ref": None, "test_only": request["test_only"]}
        fails = validate_result(result, request)
        if fails:
            raise WrapperError("page-result failed receipt validation: " + "; ".join(fails))
    except (WrapperError, page_set.PageSetError, OSError, KeyError) as exc:
        result_path.unlink(missing_ok=True)  # a failed run leaves no result to be mistaken for this run's
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return EXIT_FAILCLOSED
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"role": ROLE, "request_id": request["request_id"], "result_path": str(result_path),
                      "status": result["status"], "proof_class": result["proof_class"],
                      "artifacts": len(result["artifacts"]), "blockers": result["blockers"]}, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

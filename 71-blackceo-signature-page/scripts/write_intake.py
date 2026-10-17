#!/usr/bin/env python3
"""Write <run_dir>/intake.json, the intake stage artifact stage_gate.py reads.

image_engine is "kie" (default) or "agnes". stage_gate.py accepts the Agnes route on
image-generation-qc only when intake.json says "agnes" (references/kie-generation-route.md).
copy_version ("standard" or "long-form") is a required intake decision (fix plan
Amendment 6, Items 18/19): it selects the ONE copy guide, copy spec, and
emotional-quality extract the copy stage reads (see the copy stage's
copy_selection block in references/stage-contract.json and the selection
record in references/artifact-contracts.md). The flag stays optional at
this writer so older invocations keep working; a run whose intake.json has
no copy_version cannot pass the copy stage's structure validation.
Layout waivers (Item 13/14, S3 Request 3): --brand-fonts-waived and
--layout-references-waived, each with its own reason argument, are recorded
in intake.json as layout_waivers entries the gate's layout gate consumes;
an unrecorded absence is never a waiver.
Exit 0 written, 2 invalid input.

Delivery fields (Item 31, Amendment 4): the intake also records the publish
target, the automation scope, and the PRESENCE of the three delivery
credentials (booleans and variable names only; values are never read into
the record and never printed). Refusals are written, at intake:

- automation_scope "workflows" with a non-GHL publish target is refused:
  workflows live where the forms live;
- a GHL publish target without the Private Integration Token or the
  location ID present is refused, naming what to supply in this install's
  own secrets.env;
- automation scope without the Firebase refresh token requires a recorded
  choice (--firebase-choice): supply the token, declare the Tier 4 browser
  backstop, or drop the automation scope. The page job may proceed; the
  workflows may not pretend to exist.

Credential presence defaults to the process environment; the --*-present /
--*-absent flags override it (for provisioning records written before the
secrets.env exists).

Launch-context import (S71-02, profile signature_launch_landing):
--launch-context <page-request.json> imports the approved Signature
Launch context for the run. The page-request (and, when supplied, the
launch record, the route graph, and the popup consent statements) are
validated against the frozen 1.0 schemas vendored in references/ by
scripts/launch_context.py; on any violation the import is refused with
the violation named and nothing is written. On success the context's
fields are mapped into intake.json (launch_profile plus the launch
block), the validated documents are placed in the run where the S71-05
handoff reads them, and the interest popup config is emitted at
launch/popup-config.json. Without --launch-context this writer's
behavior is unchanged."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import launch_context

SKILL_ROOT = Path(__file__).resolve().parents[1]

ENGINES = ("kie", "agnes")

CREDENTIALS = (
    ("pit", "ghl_pit", "GHL_PRIVATE_INTEGRATION_TOKEN"),
    ("location_id", "ghl_location", "GHL_LOCATION_ID"),
    ("firebase_refresh_token", "ghl_firebase", "GHL_FIREBASE_REFRESH_TOKEN"),
)


def credential_presence(a):
    out = {}
    for key, dest, default_var in CREDENTIALS:
        var = getattr(a, f"{dest}_var") or default_var
        override = getattr(a, f"{dest}_present")
        present = (var in os.environ and bool(os.environ[var])) if override is None else override
        out[key] = {"variable": var, "present": bool(present)}
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("run_dir", type=Path)
    p.add_argument("--page-version", choices=["standard", "long-form"], required=True)
    p.add_argument("--brand-owner", required=True)
    p.add_argument("--brand-file", default="assets/brand/blackceo-brand.json")
    p.add_argument("--creative-direction", default=None)
    p.add_argument("--image-cap", type=int, required=True)
    p.add_argument("--image-engine", choices=ENGINES, default="kie")
    p.add_argument("--copy-version", choices=["standard", "long-form"], default=None,
                   help="the run's copy selection (required intake decision, "
                        "Amendment 6 Items 18/19); selects the copy guide, spec, "
                        "and emotional-quality extract for the copy stage")
    p.add_argument("--test-run", action="store_true")
    p.add_argument("--brand-fonts-waived", action="store_true",
                   help="record a waiver for the layout gate's brand-fonts check "
                        "(requires --brand-fonts-waiver-reason)")
    p.add_argument("--brand-fonts-waiver-reason", default=None)
    p.add_argument("--layout-references-waived", action="store_true",
                   help="record a waiver for the layout gate's reference-existence "
                        "check (requires --layout-references-waiver-reason)")
    p.add_argument("--layout-references-waiver-reason", default=None)
    # Launch-context import (S71-02).
    p.add_argument("--launch-context", type=Path, default=None,
                   help="Signature Launch page-request 1.0 document; validates "
                        "it against the frozen schemas in references/ and "
                        "imports the approved launch context, activating the "
                        "signature_launch_landing profile")
    p.add_argument("--launch-record", type=Path, default=None,
                   help="the launch record (launch.json 1.0) the request "
                        "belongs to; requires --launch-context")
    p.add_argument("--route-graph", type=Path, default=None,
                   help="the approved route graph (route-graph 1.0); its "
                        "SHA-256 must equal the request's route_graph_hash; "
                        "requires --launch-context")
    p.add_argument("--consent-statements", type=Path, default=None,
                   help="the approved popup consent statements as a JSON "
                        "list of {id, text, required} objects (the interest "
                        "popup component's config shape), carried verbatim "
                        "into launch/popup-config.json; requires "
                        "--launch-context")
    # Item 31 delivery fields (Amendment 4).
    p.add_argument("--publish-target", choices=["ghl", "vercel-embed", "vercel"])
    p.add_argument("--automation-scope", choices=["none", "workflows"], default="none")
    p.add_argument("--firebase-choice", choices=["supply", "backstop", "drop"])
    for _key, dest, _var in CREDENTIALS:
        flag = dest.replace("_", "-")
        p.add_argument(f"--{flag}-var")
        g = p.add_mutually_exclusive_group()
        g.add_argument(f"--{flag}-present", dest=f"{dest}_present",
                       action="store_const", const=True, default=None)
        g.add_argument(f"--{flag}-absent", dest=f"{dest}_present",
                       action="store_const", const=False, default=None)
    a = p.parse_args(argv)
    if a.image_cap < 0 or not a.run_dir.is_dir():
        print("FAIL: run_dir must exist and image_cap must be >= 0")
        return 2

    # Launch-context import (S71-02): validate everything in memory before
    # anything is written; a refusal here leaves the run untouched.
    launch_prepared = None
    if a.launch_context is None:
        for flag, value in (("--launch-record", a.launch_record),
                            ("--route-graph", a.route_graph),
                            ("--consent-statements", a.consent_statements)):
            if value is not None:
                print(f"REFUSED: {flag} is a launch-context import input and "
                      f"requires --launch-context (the page-request it "
                      f"belongs to).")
                return 2
    else:
        try:
            launch_prepared = launch_context.prepare_import(
                SKILL_ROOT, a.run_dir, a.launch_context,
                launch_path=a.launch_record, graph_path=a.route_graph,
                consent_path=a.consent_statements, brand_file=a.brand_file)
        except launch_context.LaunchContextError as exc:
            print(f"REFUSED: launch context import: {exc}")
            return 2
        mapped_copy = launch_prepared[0].get("copy_version")
        if (a.copy_version is not None and mapped_copy is not None
                and a.copy_version != mapped_copy):
            print(f"REFUSED: --copy-version \"{a.copy_version}\" conflicts "
                  f"with the launch context's approved copy_profile "
                  f"\"{mapped_copy}\"; the approved launch context governs, "
                  f"so drop the conflicting flag.")
            return 2

    intake = {"page_version": a.page_version, "brand_owner": a.brand_owner, "brand_file": a.brand_file,
              "creative_direction": a.creative_direction, "image_cap": a.image_cap,
              "image_engine": a.image_engine, "test_run": a.test_run,
              "copy_version": a.copy_version}

    waivers = []
    for flag, reason, gate_name in (
            (a.brand_fonts_waived, a.brand_fonts_waiver_reason, "brand-fonts"),
            (a.layout_references_waived, a.layout_references_waiver_reason, "layout-references")):
        if flag and not (reason and reason.strip()):
            print(f"REFUSED: the {gate_name} waiver requires its recorded reason "
                  f"argument; a waiver without a reason is not a waiver.")
            return 2
        if flag:
            waivers.append({"gate": gate_name, "reason": reason.strip()})
    if waivers:
        intake["layout_waivers"] = waivers

    if a.publish_target is not None:
        credentials = credential_presence(a)
        if a.automation_scope == "workflows" and a.publish_target != "ghl":
            print(f"REFUSED: automation_scope \"workflows\" requires publish_target "
                  f"\"ghl\" (workflows live where the forms live); got publish_target "
                  f"\"{a.publish_target}\". Drop the automation scope or target GHL.")
            return 2
        if a.publish_target == "ghl":
            missing = [credentials[k]["variable"] for k in ("pit", "location_id")
                       if not credentials[k]["present"]]
            if missing:
                print(f"REFUSED: publish_target \"ghl\" requires the GHL Private "
                      f"Integration Token and the location ID in this install's own "
                      f"secrets.env; not present: {', '.join(missing)}. Supply them "
                      f"at provisioning (per-container on fleet-contabo, never "
                      f"shared) and rerun intake.")
                return 2
        automation_scope = a.automation_scope
        extra = {}
        if automation_scope == "workflows" and not credentials["firebase_refresh_token"]["present"]:
            var = credentials["firebase_refresh_token"]["variable"]
            if a.firebase_choice is None:
                print(f"REFUSED: automation_scope \"workflows\" needs the Firebase "
                      f"refresh token ({var}) for workflow writes, or a recorded "
                      f"choice: rerun with --firebase-choice supply (provide the "
                      f"token), backstop (declare the Tier 4 browser backstop), or "
                      f"drop (drop the automation scope). The page job may proceed; "
                      f"the workflows may not pretend to exist.")
                return 2
            if a.firebase_choice == "supply":
                print(f"REFUSED: --firebase-choice supply was recorded but {var} is "
                      f"still not present in this install's secrets.env. Supply it "
                      f"and rerun intake.")
                return 2
            if a.firebase_choice == "backstop":
                extra["firebase_backstop_declared"] = True
            elif a.firebase_choice == "drop":
                automation_scope = "none"
                extra["automation_scope_dropped"] = "workflows (Firebase token not supplied)"
        intake["publish_target"] = a.publish_target
        intake["automation_scope"] = automation_scope
        intake["credentials"] = credentials
        intake.update(extra)

    if launch_prepared is not None:
        updates, _prepared_artifacts = launch_prepared
        intake.update(updates)

    (a.run_dir / "intake.json").write_text(json.dumps(intake, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {a.run_dir / 'intake.json'} (image_engine={intake['image_engine']})")
    if launch_prepared is not None:
        _updates, artifacts = launch_prepared
        launch_context.write_artifacts(a.run_dir, artifacts)
        print(f"launch profile {launch_context.PROFILE_NAME} imported: "
              f"{', '.join(sorted(artifacts))} written under {a.run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

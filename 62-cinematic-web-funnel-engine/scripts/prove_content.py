#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_content.py — the P2-METHODOLOGY and P3-CONTENT phase gates declared
in CWFE-MANIFEST.json:

    P2-METHODOLOGY  gate="scripts/prove_content.py"  py_symbol="prove_content.evaluate_methodology"  af_code="AF-CWFE-P2-METHODOLOGY"
    P3-CONTENT      gate="scripts/prove_content.py"  py_symbol="prove_content.evaluate_manifest"      af_code="AF-CWFE-P3-CONTENT"
    cross-cutting   py_symbol="prove_content.assert_delegated_methodology"                            af_code="AF-CWFE-CONTENT-DUPLICATE"

Both phases share this ONE gate script because run_cinematic_web_funnel.py's
_run_phase_gate invokes every phase uniformly as `<gate> --run-dir <run_dir>`
(see resolve_execution_environment's sibling prove_p0_environment.py for the
same convention). This is safe here because the two phases are strictly
ordered and each is idempotent against run_dir's current state: the FIRST
invocation (P2) finds no methodology-decision.json yet and computes one; the
SECOND invocation (P3) finds methodology-decision.json already written and
proceeds to build/lock content-manifest.json from it. main() dispatches on
that on-disk state rather than on a CLI flag, so the gate contract stays
identical to every other phase gate in the manifest.

Recognized environment variables (read here, not as extra CLI flags, for the
same uniform-invocation reason documented above):
  CWFE_REGISTRY_PATH           override for the shared funnel-engine registry
                                (default: 06-ghl-install-pages/funnel-engines/
                                registry.json at the repo root)
  CWFE_CONTENT_DELEGATE_DIR    required when P2 delegated to Skill 49/56 —
                                the delegate skill's completed run output
                                directory (must contain content-handoff.json)
  CWFE_CINEMATIC_NATIVE_PROFILE  optional, only used on the cinematic-native
                                path — path to a JSON file overriding the
                                placeholder page profile

Writes methodology-decision.json (P2) or content-manifest.json (P3) into
--run-dir on every invocation. Exit 0 = PASS, 2 = FAIL, 3 = usage error
(matches prove_p0_environment.py's convention exactly).

stdlib only.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import resolve_content_engine as rce  # noqa: E402
import state_engine as se  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3


# ---------------------------------------------------------------------------
# AF-CWFE-CONTENT-DUPLICATE — cross-cutting check declared in
# CWFE-MANIFEST.json's cross_cutting_af_codes with py_symbol
# "prove_content.assert_delegated_methodology". Defined here (not in
# resolve_content_engine.py) so the manifest's py_symbol reference resolves
# to exactly this module, matching the convention every other phase gate uses
# (evaluate() lives in the prove_*.py gate module, not the resolver module it
# wraps).
# ---------------------------------------------------------------------------
def assert_delegated_methodology(manifest_fields: Dict[str, Any], decision: Dict[str, Any], *, run_dir: Path) -> List[str]:
    """Returns a list of violation strings (empty == no violation). Fires
    whenever a content-manifest claims a delegated methodology_source
    (signature-funnel / sales-page-assets) but the evidence does not actually
    prove delegation:
      - source_skill must match the skill this router actually decided to
        delegate to (not the wrong skill's output);
      - approved_copy_paths must be non-empty, absolute, exist on disk, and
        resolve OUTSIDE run_dir — a path inside run_dir means this engine
        authored the copy itself, which ADR-10 forbids;
      - a declared certificate_ref (proof the delegate skill's OWN sacred
        gates passed) must exist on disk and name the expected skill.
    cinematic-native and existing-funnel-selector are not delegation paths and
    always return no violations (vacuous pass)."""
    source = manifest_fields.get("methodology_source")
    if source not in rce.EXPECTED_SKILL_DIR_FOR_SOURCE:
        return []

    violations: List[str] = []
    expected_skill_dir = rce.EXPECTED_SKILL_DIR_FOR_SOURCE[source]
    actual_skill_dir = manifest_fields.get("source_skill")
    if actual_skill_dir != expected_skill_dir:
        violations.append(
            f"source_skill={actual_skill_dir!r} does not match the expected delegate {expected_skill_dir!r} "
            f"for methodology_source={source!r}"
        )

    paths = manifest_fields.get("approved_copy_paths") or []
    if not paths:
        violations.append(
            "approved_copy_paths is empty — a delegated methodology_source must consume at least one "
            "approved copy artifact from the owning skill, never author it locally"
        )

    run_dir_resolved = run_dir.resolve()
    for p in paths:
        pp = Path(p)
        if not pp.is_absolute():
            violations.append(f"approved_copy_paths entry {p!r} is not an absolute path — cannot mechanically prove it is external to run_dir")
            continue
        if not pp.exists():
            violations.append(f"approved_copy_paths entry {p!r} does not exist on disk")
            continue
        resolved = pp.resolve()
        try:
            resolved.relative_to(run_dir_resolved)
        except ValueError:
            continue  # good: outside run_dir
        violations.append(
            f"approved_copy_paths entry {p!r} resolves INSIDE run_dir ({run_dir_resolved}) — this looks "
            "locally authored, not delegated (ADR-10 violation)"
        )

    cert_ref = (manifest_fields.get("copy_qc_receipt") or {}).get("delegation", {}).get("certificate_ref")
    if cert_ref is not None:
        cert_path = Path(cert_ref.get("path", ""))
        if not cert_path.is_absolute() or not cert_path.is_file():
            violations.append(
                f"certificate_ref path {cert_ref.get('path')!r} does not exist — cannot verify the delegate "
                "skill's own PROCESS-CERTIFICATE.json"
            )
        elif cert_ref.get("skill") != expected_skill_dir:
            violations.append(
                f"certificate_ref.skill={cert_ref.get('skill')!r} does not match expected delegate "
                f"{expected_skill_dir!r}"
            )

    return violations


# ---------------------------------------------------------------------------
# P2-METHODOLOGY
# ---------------------------------------------------------------------------
def evaluate_methodology(run_dir: Path) -> Tuple[bool, str]:
    """CWFE-MANIFEST.json py_symbol 'prove_content.evaluate_methodology'.
    Reads methodology-request.json from run_dir, runs resolve_content_engine.
    route(), writes methodology-decision.json, and returns (passed, detail)."""
    req_path = run_dir / "methodology-request.json"
    if not req_path.is_file():
        return False, (
            f"USAGE ERROR: methodology-request.json not found at {req_path} — P1-INTAKE (or an operator, "
            "before P1 is built) must supply it before P2-METHODOLOGY runs"
        )

    try:
        request = se.read_json(req_path)
    except se.StateEngineError as exc:
        return False, f"USAGE ERROR: {exc}"

    errors = rce.validate_request(request)
    if errors:
        return False, "METHODOLOGY-REQUEST-INVALID: " + "; ".join(errors)

    registry_path = os.environ.get("CWFE_REGISTRY_PATH") or None
    try:
        payload = rce.route(request, registry_path=registry_path)
    except rce.UsageError as exc:
        return False, f"USAGE ERROR: {exc}"

    try:
        out_path = rce.write_methodology_decision(payload, run_dir)
    except rce.SchemaValidationFailed as exc:
        return False, f"METHODOLOGY-DECISION-SCHEMA-INVALID: {exc}"

    if payload["status"] == "PASS":
        d = payload["decision"]
        detail = (
            f"methodology-decision.json written ({out_path.name}): methodology_source="
            f"'{d['methodology_source']}' via {d['rule_applied']} (score={d['confidence_score']})"
        )
        return True, detail

    return False, f"[{payload['af_code']}] " + "; ".join(payload["failure_reasons"])


# ---------------------------------------------------------------------------
# P3-CONTENT
# ---------------------------------------------------------------------------
def evaluate_manifest(run_dir: Path) -> Tuple[bool, str]:
    """CWFE-MANIFEST.json py_symbol 'prove_content.evaluate_manifest'. Reads
    methodology-decision.json (must already exist — P2 runs first), builds
    content-manifest.json per the decided methodology_source, runs
    assert_delegated_methodology (AF-CWFE-CONTENT-DUPLICATE), locks + hashes
    + saves it via state_engine, and returns (passed, detail)."""
    try:
        decision_payload = rce.read_methodology_decision(run_dir)
    except FileNotFoundError:
        return False, (
            f"USAGE ERROR: methodology-decision.json not found in {run_dir} — P2-METHODOLOGY must run and "
            "PASS before P3-CONTENT"
        )
    except rce.SchemaValidationFailed as exc:
        return False, f"USAGE ERROR: methodology-decision.json failed validation: {exc}"

    if decision_payload["status"] != "PASS":
        return False, "P2-METHODOLOGY did not PASS — P3-CONTENT cannot proceed"

    decision = decision_payload["decision"]
    project_id = decision_payload["project_id"]

    if decision["methodology_source"] == "existing-funnel-selector":
        return False, (
            f"NO_ENGINE_MATCH_FALLTHROUGH: spec 7.2 {decision['rule_applied']} routes this request to the "
            "existing funnel selector — the cinematic engine correctly declines to author or lock "
            "content-manifest.json rather than hijack a task no engine matched. This is intentional "
            "fail-closed non-certification, not a defect (mirrors CWFE-MANIFEST.json's own "
            "GATE-SCRIPT-MISSING convention for documented, expected non-PASS states)."
        )

    try:
        if decision["methodology_source"] == "cinematic-native":
            native_profile_path = os.environ.get("CWFE_CINEMATIC_NATIVE_PROFILE") or None
            manifest_fields = rce.build_cinematic_native_manifest_fields(
                project_id, decision_payload, native_profile_path=native_profile_path
            )
        else:
            delegate_dir_env = os.environ.get("CWFE_CONTENT_DELEGATE_DIR")
            if not delegate_dir_env:
                return False, (
                    f"USAGE ERROR: methodology_source='{decision['methodology_source']}' requires "
                    "CWFE_CONTENT_DELEGATE_DIR to point at the completed delegate skill's output directory "
                    "(containing content-handoff.json)"
                )
            manifest_fields = rce.build_delegated_manifest_fields(
                project_id, decision_payload, Path(delegate_dir_env)
            )
    except rce.NoEngineMatchFallthrough as exc:  # defensive; unreachable given the branch above
        return False, str(exc)
    except rce.ContentDuplicateViolation as exc:
        return False, f"[AF-CWFE-CONTENT-DUPLICATE] {exc}"
    except (rce.UsageError, rce.SchemaValidationFailed) as exc:
        return False, f"USAGE ERROR: {exc}"

    violations = assert_delegated_methodology(manifest_fields, decision, run_dir=run_dir)
    if violations:
        return False, "[AF-CWFE-CONTENT-DUPLICATE] " + "; ".join(violations)

    try:
        manifest = rce.finalize_and_save_content_manifest(run_dir, manifest_fields)
    except se.StateEngineError as exc:
        return False, f"CONTENT-MANIFEST-WRITE-FAILED: {exc}"

    ok, verify_detail = rce.verify_locked_manifest(manifest)
    if not ok:
        return False, f"CONTENT-HASH-VERIFY-FAILED: {verify_detail}"

    return True, (
        f"content-manifest.json written and locked: methodology_source='{manifest['methodology_source']}', "
        f"content_hash={manifest['content_hash']}"
    )


# ---------------------------------------------------------------------------
# CLI — dispatches on run_dir state (see module docstring)
# ---------------------------------------------------------------------------
def evaluate(run_dir: Path) -> Tuple[bool, str]:
    """Single entry point the CLI uses. Runs P2 if methodology-decision.json
    does not exist yet, else runs P3. This is what makes ONE gate script
    correctly serve both phase entries the orchestrator declares it for."""
    if not (run_dir / "methodology-decision.json").exists():
        return evaluate_methodology(run_dir)
    return evaluate_manifest(run_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P2-METHODOLOGY / P3-CONTENT phase gate for the Cinematic and Web Funnel Engine. "
        "Invoked by run_cinematic_web_funnel.py as `prove_content.py --run-dir <dir>`."
    )
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"USAGE ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    if not run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir is not a directory: {run_dir}", file=sys.stderr)
        sys.exit(EXIT_USAGE)

    # Determine the phase label BEFORE evaluate() runs — a successful P2 call
    # creates methodology-decision.json as its side effect, which would
    # otherwise make this same invocation misreport itself as P3-CONTENT.
    phase_label = "P3-CONTENT" if (run_dir / "methodology-decision.json").exists() else "P2-METHODOLOGY"
    passed, detail = evaluate(run_dir)
    if passed:
        print(f"[PASS] {phase_label} — {detail}")
        sys.exit(EXIT_OK)
    print(f"[FAIL] {phase_label} — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()

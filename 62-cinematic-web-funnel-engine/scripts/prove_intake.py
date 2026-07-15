#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_intake.py — the P1-INTAKE phase gate declared in CWFE-MANIFEST.json
(`"gate": "scripts/prove_intake.py"`, `"py_symbol": "prove_intake.evaluate"`,
`"af_code": "AF-CWFE-P1-INTAKE"`).

This is the "deterministic intake prover" spec Section 8.2 requires: it
"must validate required fields, approved budget[-cap], destination,
representation requirements, truth sources, and locked status before paid
generation." It is DELIBERATELY independent of intake_engine.py's own
bookkeeping — it re-reads the six intake/*.json artifacts straight off disk
and re-derives every pass/fail decision from their contents, so a bug in the
session's incremental state can never silently slip a bad brief past the
phase gate the rest of the pipeline (P2 onward) depends on.

Spec Section 17.1 ("Intake gate"): "Reject missing goal, audience, offer,
destination, required assets, conversion action, budget cap, approval
policy, or truth-source requirements." Mapped onto the locked
intake/project-brief.json groups this unit defines:

  goal                  -> groups.project_goal (deliverable_type + deadline)
  conversion action     -> groups.project_goal.success_action
  required assets       -> groups.project_goal.required_assets (non-empty)
  audience               -> groups.audience
  offer                  -> groups.offer
  destination            -> groups.hosting (vercel_project OR alternate_host set)
  budget cap              -> intake/budget-authorization.json.max_media_spend_usd > 0
  approval policy          -> intake/approval-policy.json (all three approvers set)
  truth-source requirements -> intake/truth-sources.json present, and every
                              claim_id referenced by project-brief.json's
                              truth_source_ids has exactly one matching entry
  representation requirements -> groups.brand.representation_requirements (non-empty)
  locked status            -> project-brief.json.locked == true (and the other
                              three artifacts' locked == true)

Exit 0 = PASS, 2 = FAIL (matches run_cinematic_web_funnel._run_phase_gate's
returncode == 0 => PASS convention), 3 = usage error.

stdlib only. Exposes evaluate(run_dir) -> (bool, str) as required by the
manifest's py_symbol reference.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import json_schema_lite as jsl  # noqa: E402

AF_CODE = "AF-CWFE-P1-INTAKE"

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

ARTIFACTS = {
    "project-brief": "intake/project-brief.json",
    "truth-sources": "intake/truth-sources.json",
    "approval-policy": "intake/approval-policy.json",
    "budget-authorization": "intake/budget-authorization.json",
}
SCHEMA_FILES = {
    "project-brief": "project-brief.schema.json",
    "truth-sources": "truth-sources.schema.json",
    "approval-policy": "approval-policy.schema.json",
    "budget-authorization": "budget-authorization.schema.json",
}


def _load_and_validate(run_dir: Path, kind: str, reasons: List[str]) -> Any:
    path = run_dir / ARTIFACTS[kind]
    if not path.exists():
        reasons.append(f"missing artifact intake/{path.name} ({kind})")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        reasons.append(f"{kind}: corrupt JSON ({exc})")
        return None
    schema = json.loads((_STRUCTURE_DIR / SCHEMA_FILES[kind]).read_text(encoding="utf-8"))
    errors = jsl.validate(data, schema)
    if errors:
        reasons.append(f"{kind}: schema validation failed — {'; '.join(errors)}")
        return None
    return data


def evaluate(run_dir: Path) -> Tuple[bool, str]:
    """Re-reads and independently re-validates the four locked intake
    artifacts under run_dir/intake/ and returns (passed, detail_message).
    Never imports or calls intake_engine.IntakeSession — a gate must be able
    to catch a bug in the session logic, not just echo it."""
    reasons: List[str] = []

    brief = _load_and_validate(run_dir, "project-brief", reasons)
    truth_sources = _load_and_validate(run_dir, "truth-sources", reasons)
    approval_policy = _load_and_validate(run_dir, "approval-policy", reasons)
    budget_authorization = _load_and_validate(run_dir, "budget-authorization", reasons)

    if brief is None or truth_sources is None or approval_policy is None or budget_authorization is None:
        return False, f"[{AF_CODE}] " + "; ".join(reasons)

    # -- locked status ----------------------------------------------------
    for kind, artifact in (
        ("project-brief", brief),
        ("truth-sources", truth_sources),
        ("approval-policy", approval_policy),
        ("budget-authorization", budget_authorization),
    ):
        if artifact.get("locked") is not True:
            reasons.append(f"{kind}: locked must be true, got {artifact.get('locked')!r}")

    groups: Dict[str, Any] = brief.get("groups", {})

    # -- goal ---------------------------------------------------------------
    goal = groups.get("project_goal", {})
    if not goal.get("deliverable_type"):
        reasons.append("missing goal: groups.project_goal.deliverable_type")
    if not goal.get("deadline"):
        reasons.append("missing goal: groups.project_goal.deadline")

    # -- conversion action ----------------------------------------------------
    if not goal.get("success_action"):
        reasons.append("missing conversion action: groups.project_goal.success_action")

    # -- required assets --------------------------------------------------
    required_assets = goal.get("required_assets")
    if not required_assets:
        reasons.append("missing required assets: groups.project_goal.required_assets must be a non-empty list")

    # -- audience -------------------------------------------------------------
    audience = groups.get("audience", {})
    if not all(audience.get(f) for f in ("identity", "pain", "aspiration", "awareness_level")):
        reasons.append("missing audience: groups.audience must have identity, pain, aspiration, awareness_level")

    # -- offer ----------------------------------------------------------------
    offer = groups.get("offer", {})
    if not all(offer.get(f) for f in ("name", "promise", "price", "mechanism")):
        reasons.append("missing offer: groups.offer must have name, promise, price, mechanism")

    # -- destination ------------------------------------------------------
    hosting = groups.get("hosting", {})
    if not (hosting.get("vercel_project") or hosting.get("alternate_host")):
        reasons.append("missing destination: groups.hosting must set vercel_project or alternate_host")

    # -- representation requirements -----------------------------------------
    brand = groups.get("brand", {})
    if not brand.get("representation_requirements"):
        reasons.append("missing representation requirements: groups.brand.representation_requirements must be a non-empty list")

    # -- budget cap -------------------------------------------------------
    cap = budget_authorization.get("max_media_spend_usd")
    if not isinstance(cap, (int, float)) or cap <= 0:
        reasons.append(f"missing/invalid budget cap: budget-authorization.max_media_spend_usd={cap!r} (must be > 0)")

    # -- approval policy --------------------------------------------------
    if not all(approval_policy.get(f) for f in ("anchor_approver", "draft_approver", "final_deployment_approver")):
        reasons.append("missing approval policy: approval-policy.json must set anchor_approver, draft_approver, final_deployment_approver")

    # -- truth-source requirements ------------------------------------------
    # Every claim_id project-brief.json's truth_source_ids names must have
    # EXACTLY one matching entry in truth-sources.json — re-derived from the
    # raw claim lists too, independent of what the brief claims about itself,
    # so a hand-edited/corrupt brief can never lie its way past this gate.
    ts_by_claim: Dict[str, int] = {}
    for entry in truth_sources.get("sources", []):
        ts_by_claim[entry["claim_id"]] = ts_by_claim.get(entry["claim_id"], 0) + 1

    all_claim_ids: List[str] = []
    for group_key in ("offer", "content_source"):
        for claim in groups.get(group_key, {}).get("proof" if group_key == "offer" else "claims", []) or []:
            all_claim_ids.append(claim["claim_id"])

    for claim_id in all_claim_ids:
        count = ts_by_claim.get(claim_id, 0)
        if count == 0:
            reasons.append(f"missing truth source: claim {claim_id!r} has no truth-sources.json entry")
        elif count > 1:
            reasons.append(f"duplicate truth source: claim {claim_id!r} has {count} truth-sources.json entries (must be exactly 1)")

    declared_ids = set(brief.get("truth_source_ids", []))
    actual_ids = set(all_claim_ids)
    if declared_ids != actual_ids:
        reasons.append(
            f"project-brief.truth_source_ids {sorted(declared_ids)!r} does not match the claims actually "
            f"present in groups.offer.proof/groups.content_source.claims {sorted(actual_ids)!r}"
        )

    if reasons:
        return False, f"[{AF_CODE}] " + "; ".join(reasons)

    detail = (
        f"locked project-brief.json (brief_hash={brief['brief_hash'][:12]}...) with "
        f"{len(all_claim_ids)} truth-sourced claim(s), budget cap ${cap:.2f}, "
        f"destination={'vercel:' + hosting['vercel_project'] if hosting.get('vercel_project') else hosting.get('alternate_host')}"
    )
    return True, detail


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P1-INTAKE phase gate for the Cinematic and Web Funnel Engine. "
        "Invoked by run_cinematic_web_funnel.py as `prove_intake.py --run-dir <dir>`."
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

    passed, detail = evaluate(run_dir)
    if passed:
        print(f"[PASS] P1-INTAKE — {detail}")
        sys.exit(EXIT_OK)
    print(f"[FAIL] P1-INTAKE — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()

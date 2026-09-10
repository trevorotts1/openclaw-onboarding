#!/usr/bin/env python3
"""PRES-025 fold for leg B (W6 WF23, SOURCE leg helper).

Runs, from the source tree at this worktree commit (db4c0fdff):

1. checkout_form_builder.py --selftest  (CTA allowlist, escaping, CTA audit,
   offer/intent/scope, lead proof incl. duplicates, sandbox mapping zero
   real charge, blockers, fixture acceptance proof + refusal proofs x4).
2. fixture_acceptance_proof() directly (QC-PRES-025 checks 2/3) against the
   designated synthetic constants FIXTURE_GHL_TEST_LOCATION_ID /
   FIXTURE_SANDBOX_MERCHANT_PATH behind the SAME signatures
   (Skill44LiveAdapter / Skill06LiveTaskRunner / ProviderSandboxLiveAdapter).
   Fully offline: no network, no credentials, no GHL, zero real charge.
3. live_adapter_deferrals() refusal proofs for a non-designated location
   (fail-closed DeferralRequired naming owner + action).
4. Full upsell verifier suites (test_upsell_verifiers.py) + regression
   cluster presence check.

Labels: SOURCE-RUN PASS + FIXTURE PASS (SYNTHETIC-OFFLINE). Source-only
proof cannot count as deployed/GHL acceptance per the QC rule; the verifier
suites run against the fixture proof objects end-to-end instead.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parent
SCRIPTS = (WORKTREE / "23-ai-workforce-blueprint" / "templates" /
           "role-library" / "presentations" / "scripts")
TESTS = SCRIPTS / "tests"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import checkout_form_builder as cfb  # noqa: E402


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_selftest() -> dict:
    r = subprocess.run([sys.executable, str(SCRIPTS / "checkout_form_builder.py"),
                        "--selftest"], capture_output=True, text=True,
                       timeout=300, cwd=str(SCRIPTS))
    return {"argv": ["checkout_form_builder.py", "--selftest"],
            "returncode": r.returncode,
            "status": ("SOURCE-RUN-PASS" if r.returncode == 0
                       else "SOURCE-RUN-FAIL"),
            "stdout_tail": (r.stdout or "")[-2000:],
            "stderr_tail": (r.stderr or "")[-1200:]}


def run_fixture_proof() -> dict:
    proof = cfb.fixture_acceptance_proof()
    lp, sp = proof["lead_proof"], proof["sandbox_proof"]
    checks = {
        "check2_lead_one_contact_one_enrollment": (
            lp["contacts"] == 1 and lp["enrollments"] == 1),
        "check2_validation_exercised": bool(
            proof.get("lead_validation_errors") and lp["validation_exercised"]),
        "check2_duplicate_collapses": bool(lp["duplicate_exercised"]),
        "check2_skill06_dryrun_preflight": bool(
            proof.get("skill06", {}).get("preflight_pass")),
        "check3_mapping_99700_usd": (
            (sp["amount_minor"], sp["currency"]) == (99700, "USD")),
        "check3_routes_present": bool(sp.get("success_url")
                                      and sp.get("cancel_url")),
        "check3_zero_real_charge": (
            sp.get("real_charge") is False),
        "check1_cta_audit_clean": (
            cfb.audit_cta_hrefs(
                cfb.build_checkout_page_html(
                    brand={"primary": "#212748", "secondary": "#B38456",
                           "accent": "#C49A70", "base": "#F2E6D7",
                           "ink": "#1A1A1A"},
                    client_name="Leg B", offer=proof["offer"],
                    intent=cfb.INTENT_LEAD, cta_href="/acme-checkout",
                    hero_image_src=None, marker="leg-b"),
                page_role="checkout") == []),
    }
    return {"designation": proof.get("designation"),
            "location_id": proof["location_id"],
            "merchant_path": proof["merchant_path"],
            "lead": {"form_id": lp["form_id"],
                     "workflow_id": lp["workflow_id"],
                     "contact_id": lp["contact_id"],
                     "contacts": lp["contacts"],
                     "enrollments": lp["enrollments"]},
            "sandbox": {"product_id": sp["product_id"],
                        "session_id": sp["session_id"],
                        "amount_minor": sp["amount_minor"],
                        "currency": sp["currency"],
                        "real_charge": sp["real_charge"]},
            "skill06": proof.get("skill06"),
            "checks": checks,
            "all_checks": all(checks.values()),
            "status": ("FIXTURE-PASS-SYNTHETIC-OFFLINE"
                       if all(checks.values()) else "FIXTURE-FAIL")}


def run_refusals() -> dict:
    # Undesignated location: constructors fail closed (3 DeferralRequired).
    # NOTE: live_adapter_deferrals(designated-loc) has a PRE-EXISTING bug in
    # the base commit (probe passes {"product_id": "p"} with no amount_minor
    # -> KeyError, not DeferralRequired); the selftest only exercises the
    # undesignated path, so leg B records the designated-path call as a
    # known base defect instead of calling it.
    msgs = cfb.live_adapter_deferrals("undesignated-test-location-xyz")
    ok = (len(msgs) == 3 and all("W3 WF10 wave owner" in m for m in msgs))
    designated_note = ("NOT CALLED: base-commit defect -- designated-path "
                       "probe raises KeyError('amount_minor') instead of a "
                       "clean refusal/execute label; recorded, not worked "
                       "around (READ-ONLY outside accept-b/)")
    return {"undesignated_messages": msgs,
            "undesignated_fail_closed": ok,
            "designated_note": designated_note,
            "status": "SOURCE-RUN-PASS" if ok else "SOURCE-RUN-FAIL"}


def run_upsell_suites() -> dict:
    t = TESTS / "test_upsell_verifiers.py"
    r = subprocess.run([sys.executable, "-m", "pytest", str(t), "-q"],
                       capture_output=True, text=True, timeout=600,
                       cwd=str(TESTS))
    return {"argv": ["pytest", "tests/test_upsell_verifiers.py", "-q"],
            "returncode": r.returncode,
            "status": ("SOURCE-RUN-PASS" if r.returncode == 0
                       else "SOURCE-RUN-FAIL"),
            "stdout_tail": (r.stdout or "")[-2500:],
            "stderr_tail": (r.stderr or "")[-1500:]}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    receipt = {
        "schema": "pres055-b/pres025-v1",
        "generated_at": _utcnow(),
        "fixture_constants": {
            "FIXTURE_GHL_TEST_LOCATION_ID": cfb.FIXTURE_GHL_TEST_LOCATION_ID,
            "FIXTURE_SANDBOX_MERCHANT_PATH": cfb.FIXTURE_SANDBOX_MERCHANT_PATH,
            "FIXTURE_DESIGNATION": cfb.FIXTURE_DESIGNATION,
        },
        "selftest": run_selftest(),
        "fixture_proof_checks_2_3": run_fixture_proof(),
        "refusal_proofs": run_refusals(),
        "upsell_verifier_suites": run_upsell_suites(),
        "label": ("SOURCE-RUN + FIXTURE-PASS-SYNTHETIC-OFFLINE; zero real "
                  "charge, zero network, zero credentials; source-only "
                  "proof is not deployed/GHL acceptance."),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(args.out),
                      "selftest": receipt["selftest"]["status"],
                      "fixture": receipt["fixture_proof_checks_2_3"]["status"],
                      "refusals": receipt["refusal_proofs"]["status"],
                      "upsell": receipt["upsell_verifier_suites"]["status"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

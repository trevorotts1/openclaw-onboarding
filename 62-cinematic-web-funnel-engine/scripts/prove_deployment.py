#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_deployment.py — the P14-PREVIEW / P15-PRODUCTION phase gates
declared in CWFE-MANIFEST.json (``"gate": "scripts/prove_deployment.py"``,
``"py_symbol": "prove_deployment.evaluate_preview"`` / ``"...evaluate_production"``,
``"af_code": "AF-CWFE-P14-PREVIEW"`` / ``"AF-CWFE-P15-PRODUCTION"``).

Spec Section 17.8 (deployment gate): "Validate preview URL, commit SHA,
deployment state, required environment configuration by key name only,
custom-domain status if requested, iframe security headers when used, and
successful post-deploy smoke tests."

Like every other ``prove_*.py`` in this skill, this module NEVER trusts
``scripts/deploy_vercel.py``'s own ``deployment-receipts.json`` as the
verdict — it treats the receipt as evidence/provenance only and
independently re-derives every pass/fail decision:

  1. STRUCTURAL checks against the receipt's own recorded fields (host,
     host_deployment_id, url scheme, commit_sha presence, status) — schema
     validity was already enforced by ``state_engine`` on load; this is a
     DIFFERENT, semantic pass over the same data.
  2. A SECRET-VALUE scan of the serialized receipt (reusing
     ``build_site.SECRET_PATTERNS`` — the same detector every other
     receipt/site scan in this skill already uses) — a receipt that leaked
     a token VALUE must never pass any gate, even though the formal
     AF-CWFE-SECRET-LEAK check is P16's job.
  3. An INDEPENDENT RE-FETCH of the deployment's live state directly from
     Vercel (via the same ``deploy_vercel.HostingAdapter`` contract,
     injected for tests) — a receipt hand-edited (or simply stale) to claim
     ``status="ready"`` while the host itself reports otherwise is caught
     here, because this module does not read the receipt's ``status``
     field to decide the final verdict, only to CROSS-CHECK it against
     what the host actually says right now.
  4. ``evaluate_production`` additionally requires a ``ready`` preview
     receipt to already exist for the same project, with the IDENTICAL
     ``commit_sha`` the production receipt recorded (spec 14.1 "production
     deployment only after generated-site QC passes"; the preview receipt
     is the mechanical proxy for "already proved," and pinning the same
     commit prevents a silent bait-and-switch between preview and
     production).

Exit 0 = PASS, 2 = FAIL, 3 = usage error. stdlib only for orchestration
(ADR-5).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent

sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import hosting_adapter as ha  # noqa: E402
import state_engine  # noqa: E402
import build_site as bs  # noqa: E402  (reuses SECRET_PATTERNS — same detector, independently invoked)
import deploy_vercel as dv  # noqa: E402  (VercelHostingAdapter/RequestsTransport/resolve_token, the SAME producer this gate independently re-checks)

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

_SUPPORTED_HOSTS = ("vercel",)  # spec 14.4: only Vercel is a proven/tested adapter in this unit.


def _structural_checks(receipt: Dict[str, Any]) -> list:
    reasons = []
    if receipt.get("host") not in _SUPPORTED_HOSTS:
        reasons.append(f"host is {receipt.get('host')!r}, expected one of {_SUPPORTED_HOSTS}")
    if not receipt.get("host_deployment_id"):
        reasons.append("host_deployment_id is missing/empty")
    url = receipt.get("url")
    if not url or not str(url).startswith("https://"):
        reasons.append(f"url is missing or not https: {url!r}")
    if not receipt.get("commit_sha"):
        reasons.append("commit_sha is missing/empty")
    if receipt.get("status") != "ready":
        reasons.append(f"receipt's own recorded status is {receipt.get('status')!r}, not 'ready'")
    return reasons


def _secret_scan(receipt: Dict[str, Any]) -> list:
    reasons = []
    serialized = json.dumps(receipt, sort_keys=True)
    for pattern in bs.SECRET_PATTERNS:
        if pattern.search(serialized):
            reasons.append(
                f"deployment receipt appears to contain a secret-shaped value "
                f"(pattern {pattern.pattern!r} matched) — refusing to certify"
            )
            break
    return reasons


def _evaluate(run_dir: "str | Path", *, environment: str,
              adapter: Optional[ha.HostingAdapter] = None) -> Tuple[bool, str]:
    run_dir = Path(run_dir)
    label = f"P14-PREVIEW" if environment == "preview" else "P15-PRODUCTION"

    if not (run_dir / "deployment-receipts.json").is_file():
        return False, f"{label} FAIL: deployment-receipts.json not found at {run_dir} — scripts/deploy_vercel.py must run first"

    state = state_engine.ProjectState(run_dir)
    try:
        receipt = state.latest_deployment_receipt(environment)
    except state_engine.StateEngineError as exc:
        return False, f"{label} FAIL: could not load deployment-receipts.json: {exc}"

    if receipt is None:
        return False, f"{label} FAIL: no {environment} deployment receipt found for this project"

    reasons = _structural_checks(receipt) + _secret_scan(receipt)
    if reasons:
        return False, f"{label} FAIL (receipt-only checks): " + " | ".join(reasons)

    # Independent re-fetch — NEVER trust the receipt's own "ready" claim.
    _adapter: ha.HostingAdapter = adapter if adapter is not None else dv.VercelHostingAdapter(dv.RequestsTransport(), dv.resolve_token())
    try:
        live = _adapter.get_status(receipt["host_deployment_id"])
    except Exception as exc:  # noqa: BLE001 — any adapter/transport failure is a gate FAIL, not a crash
        return False, f"{label} FAIL: independent re-fetch from the host failed: {exc}"

    if live.status != "ready":
        return False, (
            f"{label} FAIL: receipt claims status='ready' but an independent re-fetch from the host "
            f"reports status={live.status!r} — refusing to trust a stale or tampered receipt "
            f"(deployment_id={receipt['host_deployment_id']})"
        )
    if live.url and receipt.get("url") and live.url != receipt.get("url"):
        return False, (
            f"{label} FAIL: independent re-fetch URL {live.url!r} does not match the receipt's "
            f"recorded url {receipt.get('url')!r}"
        )

    return True, (
        f"{label} PASS: receipt structurally valid, no secret-shaped values, independently "
        f"re-verified 'ready' against {receipt['host']} (deployment_id={receipt['host_deployment_id']})"
    )


def evaluate_preview(run_dir: "str | Path", *, adapter: Optional[ha.HostingAdapter] = None) -> Tuple[bool, str]:
    return _evaluate(run_dir, environment="preview", adapter=adapter)


def evaluate_production(run_dir: "str | Path", *, adapter: Optional[ha.HostingAdapter] = None) -> Tuple[bool, str]:
    ok, detail = _evaluate(run_dir, environment="production", adapter=adapter)
    if not ok:
        return ok, detail

    run_dir = Path(run_dir)
    state = state_engine.ProjectState(run_dir)
    preview = state.latest_deployment_receipt("preview")
    production = state.latest_deployment_receipt("production")

    if preview is None:
        return False, (
            "P15-PRODUCTION FAIL: no preview receipt exists for this project — production must never "
            "be certified without a proven preview (P14-PREVIEW must precede P15-PRODUCTION)"
        )
    if preview["status"] != "ready":
        return False, f"P15-PRODUCTION FAIL: preview receipt status is {preview['status']!r}, not 'ready'"
    if preview["commit_sha"] != production["commit_sha"]:
        return False, (
            f"P15-PRODUCTION FAIL: production commit_sha {production['commit_sha']!r} does not match "
            f"preview commit_sha {preview['commit_sha']!r} — production must deploy the exact commit "
            "the preview already proved, never a silently different one"
        )

    return True, detail + f" | cross-checked against preview (commit_sha {preview['commit_sha']} matches)"


# ---------------------------------------------------------------------------
# Self-test — offline, deterministic, no network. Builds a real fixture
# project, real-deploys preview+production through deploy_vercel.py against
# a fake transport, proves both gates PASS, then proves three independent
# fail-closed paths: (a) a receipt whose independent re-fetch disagrees with
# its own stored "ready" claim, (b) a structurally invalid receipt
# (non-https url), (c) production certified against a mismatched commit_sha.
# ---------------------------------------------------------------------------


def _self_test() -> bool:
    import tempfile

    _fixture_dir = _SKILL_DIR / "tests" / "fixtures" / "site-fixture"
    sys.path.insert(0, str(_fixture_dir))
    import make_fixture  # noqa: E402

    ok_all = True

    with tempfile.TemporaryDirectory(prefix="cwfe-prove-deployment-selftest-") as tmp:
        run_dir = Path(tmp) / "run"
        make_fixture.write_fixture_run_dir(run_dir)

        state = state_engine.ProjectState(run_dir)
        state.create_project(
            project_id=make_fixture.PROJECT_ID,
            client_slug="cwfe-u17-prove-selftest",
            project_slug=make_fixture.PROJECT_ID,
            deliverable_type="cinematic-landing-page",
            budget_cap_usd=25.0,
        )

        print("building fixture site (real npm/next toolchain)...")
        bs.build_site(run_dir, skip_toolchain=False, toolchain_timeout=600)

        write_adapter = dv.VercelHostingAdapter(
            dv._SelfTestDeployTransport(), "fixture-token",
            poll_interval_seconds=0.0, sleep_fn=lambda *_: None,
        )
        dv.deploy_preview(run_dir, commit_sha="deadbeefcafefeed0001", adapter=write_adapter, project_name="cwfe-u17-prove-selftest")
        dv.deploy_production(run_dir, commit_sha="deadbeefcafefeed0001", adapter=write_adapter, project_name="cwfe-u17-prove-selftest")

        # Good path: an independent re-fetch that AGREES the deployment is ready.
        class _AlwaysReady(dv.VercelTransport):
            def get_json(self, url, *, headers, params, timeout):
                deployment_id = url.split("/deployments/", 1)[-1].split("?")[0]
                return dv.HttpResponse(status_code=200, json_body={"id": deployment_id, "url": f"{deployment_id}.vercel.app", "readyState": "READY", "projectId": "prj_selftest"})

        ready_adapter = dv.VercelHostingAdapter(_AlwaysReady(), "fixture-token")

        passed, detail = evaluate_preview(run_dir, adapter=ready_adapter)
        print("evaluate_preview (agreeing host):", passed, "-", detail[:200])
        if not passed:
            print("RESULT: FAIL (expected PASS on a genuinely ready preview)")
            ok_all = False

        passed, detail = evaluate_production(run_dir, adapter=ready_adapter)
        print("evaluate_production (agreeing host):", passed, "-", detail[:200])
        if not passed:
            print("RESULT: FAIL (expected PASS on a genuinely ready production matching its preview commit)")
            ok_all = False

        # Fail-closed (a): independent re-fetch DISAGREES with the stored
        # "ready" receipt — must fail even though the on-disk receipt itself
        # is well-formed and claims ready.
        class _AlwaysBuilding(dv.VercelTransport):
            def get_json(self, url, *, headers, params, timeout):
                deployment_id = url.split("/deployments/", 1)[-1].split("?")[0]
                return dv.HttpResponse(status_code=200, json_body={"id": deployment_id, "url": f"{deployment_id}.vercel.app", "readyState": "BUILDING", "projectId": "prj_selftest"})

        disagreeing_adapter = dv.VercelHostingAdapter(_AlwaysBuilding(), "fixture-token")
        passed, detail = evaluate_preview(run_dir, adapter=disagreeing_adapter)
        print("evaluate_preview (disagreeing host):", passed, "-", detail[:200])
        if passed:
            print("RESULT: FAIL (gate trusted a stale/tampered 'ready' receipt instead of the live host state)")
            ok_all = False

        # Fail-closed (b): structurally invalid receipt (non-https url),
        # caught WITHOUT even calling the adapter.
        receipts_path = run_dir / "deployment-receipts.json"
        receipts = json.loads(receipts_path.read_text(encoding="utf-8"))
        tampered = json.loads(json.dumps(receipts))
        for r in tampered:
            if r["environment"] == "preview":
                r["url"] = "http://not-https.example.com"
        receipts_path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        passed, detail = evaluate_preview(run_dir, adapter=ready_adapter)
        print("evaluate_preview (tampered non-https url):", passed, "-", detail[:200])
        if passed:
            print("RESULT: FAIL (gate accepted a non-https deployment url)")
            ok_all = False

        receipts_path.write_text(json.dumps(receipts, indent=2, sort_keys=True) + "\n", encoding="utf-8")  # restore

        # Fail-closed (c): production commit_sha no longer matches its
        # preview's commit_sha.
        receipts2 = json.loads(receipts_path.read_text(encoding="utf-8"))
        tampered2 = json.loads(json.dumps(receipts2))
        for r in tampered2:
            if r["environment"] == "production":
                r["commit_sha"] = "0" * 40
        receipts_path.write_text(json.dumps(tampered2, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        passed, detail = evaluate_production(run_dir, adapter=ready_adapter)
        print("evaluate_production (commit_sha mismatch):", passed, "-", detail[:200])
        if passed:
            print("RESULT: FAIL (gate certified production against a commit_sha its preview never proved)")
            ok_all = False

        receipts_path.write_text(json.dumps(receipts2, indent=2, sort_keys=True) + "\n", encoding="utf-8")  # leave tidy

    print("RESULT:", "PASS" if ok_all else "FAIL")
    return ok_all


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--environment", choices=["preview", "production"], default=None)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        ok = _self_test()
        return EXIT_OK if ok else EXIT_FAIL

    if not args.run_dir or not args.run_dir.is_dir():
        print("USAGE ERROR: --run-dir is required and must exist (unless --self-test)", file=sys.stderr)
        return EXIT_USAGE
    if not args.environment:
        print("USAGE ERROR: --environment is required (unless --self-test)", file=sys.stderr)
        return EXIT_USAGE

    fn = evaluate_preview if args.environment == "preview" else evaluate_production
    passed, detail = fn(args.run_dir)
    print(detail)
    return EXIT_OK if passed else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())

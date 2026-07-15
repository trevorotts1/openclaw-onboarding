#!/usr/bin/env python3
"""ghl_archive_receipt_gate.py — FAB-QC archive-receipt presence gate (U24/B-U10 item 3).

WHY THIS EXISTS
----------------
``ghl_github_archive.archive_async`` fires GitHub archival as a DETACHED,
non-blocking subprocess (see that module's docstring): a Vercel deploy can
finish, report PASS, and its archival can still be in flight — or it can
have silently never been attempted at all (``evidence_root`` not threaded
through, a caller predating the feature, a coverage gap in a new call site).
``ghl_github_reconcile.py`` is the RETRY sweep for that; this module is the
per-build QUALITY-GATE half of the same honesty discipline: "no receipt =
not archived" must be VISIBLE at build-QC time, not only discoverable later
by whoever happens to run the reconcile sweep.

THE RULE — never silence, never block (D6/B-D2 ratified doctrine)
-------------------------------------------------------------------
GitHub archival is NON-BLOCKING by ratified operator decision: nothing in
the archive path may roll back or block a live page. This gate honors that
absolutely — it NEVER fails a build merely because an archive attempt
failed (a transient GitHub API error, a temporarily-missing token). That
failure is already an honest ``failed`` F6 receipt that
``ghl_github_reconcile.py --retry`` (by hand or via the scheduled
maintenance-window sweep, ``--sweep-base``) will pick up and retry.

What this gate DOES fail on is SILENCE: a VERCEL_EMBED deploy (a
``vercel_deploy`` receipt exists) with NO archive receipt of ANY kind —
meaning ``archive_async`` was never even attempted. That is a build-quality
coverage gap, not a transient failure, and it is the one case "no receipt =
not archived" must never quietly pass FAB-QC.

It also reports GitHub token presence **by name only** — ``GH_TOKEN`` /
``GITHUB_TOKEN`` as ``SET``/``NOT-SET`` — never the value (item 4).

CLI
---
    python3 ghl_archive_receipt_gate.py --evidence-root <dir> [--json] [--gate]
    python3 ghl_archive_receipt_gate.py --selftest
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_receipts  # noqa: E402
import ghl_github_archive as gha  # noqa: E402


def check(evidence_root: str) -> dict:
    """Classify every VERCEL_EMBED deploy in ``evidence_root``:

      * ``ok``          — a verified archive receipt exists (verify.ok True).
      * ``failed_open`` — an archive receipt exists but isn't verified (an
                           honest FAILED receipt, non-blocking, open for the
                           reconcile sweep to retry).
      * ``missing``      — NO archive receipt at all (the one silent case
                           this gate flags — ``passed`` is False iff this
                           list is non-empty).

    ``applicable`` is False when the evidence root has no ``vercel_deploy``
    receipt at all (every non-VERCEL_EMBED build — the overwhelming
    majority — is a clean no-op here, matching every other per-build
    pre-gate's WARN-skip posture for evidence that doesn't use this path).
    Never raises: an unreadable/absent evidence root behaves exactly like
    "no deploys found".
    """
    all_receipts = ghl_receipts.list_receipts(evidence_root) if evidence_root else []
    deploy_markers = sorted({
        r["slug"] for r in all_receipts if r.get("object_type") == gha.DEPLOY_RECEIPT_TYPE
    })
    archive_by_slug = {
        r["slug"]: r for r in all_receipts if r.get("object_type") == gha.ARCHIVE_RECEIPT_TYPE
    }

    if not deploy_markers:
        return {"applicable": False, "passed": True, "total_deploys": 0,
                "ok": [], "failed_open": [], "missing": []}

    ok: list[str] = []
    failed_open: list[str] = []
    missing: list[str] = []
    for marker in deploy_markers:
        receipt: Optional[dict] = archive_by_slug.get(marker)
        if receipt is None:
            missing.append(marker)
        elif gha.is_archive_verified(receipt):
            ok.append(marker)
        else:
            failed_open.append(marker)

    return {
        "applicable": True,
        "passed": not missing,          # only total silence fails the gate
        "total_deploys": len(deploy_markers),
        "ok": ok,
        "failed_open": failed_open,
        "missing": missing,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _print_human(result: dict, token: dict) -> None:
    if not result["applicable"]:
        print("GitHub archive-receipt gate: N/A — no VERCEL_EMBED deploy in this evidence")
    else:
        print(f"GitHub archive-receipt gate: {result['total_deploys']} VERCEL_EMBED deploy(s) -- "
              f"ok={len(result['ok'])} failed_open={len(result['failed_open'])} "
              f"missing={len(result['missing'])}")
        for m in result["ok"]:
            print(f"  PASS  {m}: archive verified in GitHub")
        for m in result["failed_open"]:
            print(f"  WARN  {m}: archive receipt present but not verified (honest FAILED -- "
                  f"non-blocking per D6; reconcile --retry will retry this)")
        for m in result["missing"]:
            print(f"  FLAG  {m}: NO archive receipt at all (archive_async likely never ran -- "
                  f"a build-quality coverage gap, never silent)")
    print(f"  token presence (name only, value never printed): "
          f"GH_TOKEN={token['GH_TOKEN']} GITHUB_TOKEN={token['GITHUB_TOKEN']}")


def _selftest() -> int:
    """No network. Exercises every branch of ``check()`` plus the
    never-leak-a-secret contract of ``token_presence``."""
    import tempfile

    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        # 1. No evidence at all -> N/A, passed.
        er0 = os.path.join(tmp, "er0")
        r0 = check(er0)
        if r0["applicable"] is not False or r0["passed"] is not True:
            errors.append(f"empty evidence root must be N/A + passed: {r0}")

        # 2. Deploy + verified archive -> ok, passed.
        er1 = os.path.join(tmp, "er1")
        ghl_receipts.write_receipt(er1, ghl_receipts.make_receipt(
            gha.DEPLOY_RECEIPT_TYPE, "M1", "created", verify={"ok": True}))
        ghl_receipts.write_receipt(er1, ghl_receipts.make_receipt(
            gha.ARCHIVE_RECEIPT_TYPE, "M1", "created", verify={"ok": True}))
        r1 = check(er1)
        if r1["ok"] != ["M1"] or not r1["passed"]:
            errors.append(f"verified archive must pass: {r1}")

        # 3. Deploy + NO archive receipt at all -> missing, NOT passed (the FLAG case).
        er2 = os.path.join(tmp, "er2")
        ghl_receipts.write_receipt(er2, ghl_receipts.make_receipt(
            gha.DEPLOY_RECEIPT_TYPE, "M2", "created", verify={"ok": True}))
        r2 = check(er2)
        if r2["missing"] != ["M2"] or r2["passed"]:
            errors.append(f"a totally missing archive receipt must FLAG/fail: {r2}")

        # 4. Deploy + honest FAILED archive receipt -> failed_open, still passed
        #    (non-blocking doctrine: never gate a build over a transient failure).
        er3 = os.path.join(tmp, "er3")
        ghl_receipts.write_receipt(er3, ghl_receipts.make_receipt(
            gha.DEPLOY_RECEIPT_TYPE, "M3", "created", verify={"ok": True}))
        ghl_receipts.write_receipt(er3, ghl_receipts.make_receipt(
            gha.ARCHIVE_RECEIPT_TYPE, "M3", "failed", error="simulated"))
        r3 = check(er3)
        if r3["failed_open"] != ["M3"] or not r3["passed"]:
            errors.append(f"an honest FAILED receipt must be non-blocking (passed=True): {r3}")

        # 5. Mixed: one ok, one missing -> overall not passed, both classified correctly.
        er4 = os.path.join(tmp, "er4")
        ghl_receipts.write_receipt(er4, ghl_receipts.make_receipt(
            gha.DEPLOY_RECEIPT_TYPE, "OK-1", "created", verify={"ok": True}))
        ghl_receipts.write_receipt(er4, ghl_receipts.make_receipt(
            gha.ARCHIVE_RECEIPT_TYPE, "OK-1", "created", verify={"ok": True}))
        ghl_receipts.write_receipt(er4, ghl_receipts.make_receipt(
            gha.DEPLOY_RECEIPT_TYPE, "MISSING-1", "created", verify={"ok": True}))
        r4 = check(er4)
        if r4["passed"] or r4["ok"] != ["OK-1"] or r4["missing"] != ["MISSING-1"]:
            errors.append(f"mixed evidence root classified incorrectly: {r4}")

    # 6. token_presence never leaks the value (re-exercised here, at this
    #    module's own call site, not just ghl_github_archive's own selftest).
    secret = "another-secret-value-must-never-leak-XYZ789"
    tok = gha.token_presence(env={"GH_TOKEN": secret})
    if secret in json.dumps(tok):
        errors.append("token_presence leaked the token VALUE")
    if tok.get("GH_TOKEN") != "SET":
        errors.append(f"token_presence must report SET: {tok}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL -- {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS -- ghl_archive_receipt_gate verified (no network)")
    return 0


def main(argv: Optional[list] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="ghl_archive_receipt_gate",
        description="FAB-QC archive-receipt presence gate for VERCEL_EMBED builds (U24/B-U10).",
    )
    ap.add_argument("--evidence-root", help="evidence root dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gate", action="store_true",
                     help="exit non-zero when a VERCEL_EMBED deploy has NO archive receipt at all")
    ap.add_argument("--selftest", action="store_true",
                     help="run the no-network self-test and exit")
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest()
    if not a.evidence_root:
        ap.error("--evidence-root is required (unless --selftest)")
        return 2

    result = check(a.evidence_root)
    token = gha.token_presence()

    if a.json:
        print(json.dumps({**result, "token_presence": token}, indent=2))
    else:
        _print_human(result, token)

    if a.gate and not result["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

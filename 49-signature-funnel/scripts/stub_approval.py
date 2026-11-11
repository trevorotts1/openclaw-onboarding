#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stub_approval.py - the owner's permission to run PLACEHOLDER wireframes, verified (issue 38).

A stub run draws placeholder PNGs instead of the client's real images. It may exist only when the owner
approved it, and "approved" is a record the Command Center minted from the owner's own reply, never a
string the run wrote about itself (`--stub-approved-by "owner said yes"` certified placeholders before).

    verify_for_ledger(approval_id, ledger_path) -> {"approval_id", "kind", "plan_hash", "verified": True}
    recheck(stub_approval, ledger_path)         -> [] when the receipt's record still verifies, else problems

Both call the ONE shared verifier, shared-utils/signature_launch_contract/approval_record.verify with
kind "stub_render" and test_only=False, bound to the sha256 of the run's copy_ledger.json bytes (the
plan the placeholders are drawn from). A file, a dict or a free-text string is refused by that verifier;
a Command Center that cannot be reached is a refusal, never a pass (fail closed).
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Any, Dict, List

KIND = "stub_render"
_APPROVAL_RECORD = (Path(__file__).resolve().parents[2] / "shared-utils" /
                    "signature_launch_contract" / "approval_record.py")


class StubApprovalRefused(Exception):
    pass


def _verifier():
    if not _APPROVAL_RECORD.is_file():
        raise StubApprovalRefused("the approval verifier (shared-utils approval_record.py) is not installed")
    spec = importlib.util.spec_from_file_location("approval_record_stub", _APPROVAL_RECORD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ledger_plan_hash(ledger_path: Any) -> str:
    try:
        return hashlib.sha256(Path(ledger_path).read_bytes()).hexdigest()
    except OSError as exc:
        raise StubApprovalRefused(f"cannot read the copy ledger {ledger_path}: {exc}")


def verify_for_ledger(approval_id: Any, ledger_path: Any) -> Dict[str, Any]:
    if not isinstance(approval_id, str) or not approval_id.strip():
        raise StubApprovalRefused("no approval id was given")
    plan_hash = ledger_plan_hash(ledger_path)
    ver = _verifier()
    try:
        out = ver.verify(approval_id.strip(), KIND, plan_hash, [KIND], test_only=False)
    except (ver.ApprovalRefused, ver.ApprovalUnavailable) as exc:
        raise StubApprovalRefused(
            f"{approval_id!r} is not a verified stub_render approval from Command Center ({exc}); "
            "a free-text reference, a file or an unreachable Command Center never counts")
    return {"approval_id": out["approval_id"], "kind": KIND, "plan_hash": out["plan_hash"], "verified": True}


def recheck(stub_approval: Any, ledger_path: Any) -> List[str]:
    """Problems with a receipt's stub_approval, re-verified now against Command Center."""
    if not isinstance(stub_approval, dict) or stub_approval.get("verified") is not True:
        return ["the receipt's stub_approval is not a verified approval record (a bare string or an "
                "unverified entry is only a claim)"]
    try:
        want = ledger_plan_hash(ledger_path)
        if stub_approval.get("plan_hash") != want:
            return ["the receipt's stub_approval is bound to a different copy ledger than this run's "
                    "copy_ledger.json"]
        verify_for_ledger(stub_approval.get("approval_id"), ledger_path)
    except StubApprovalRefused as exc:
        return [str(exc)]
    return []

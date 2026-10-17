#!/usr/bin/env python3
"""ghl_receipts.py — the F6 per-object RECEIPTS STORE + REDUCER for Skill 06.

WHY THIS EXISTS
----------------
The 2026 Goal-2 V1 incident: a run's summary claimed "30/30 PASS" while the
LIVE object count was 1/6 — two verification writers produced two truths and
nobody caught it because the summary was hand-assembled, not derived.
``ghl_verify.py`` closed that hole for PAGE verification (single verifier,
``assert_consistent`` re-derives the summary from the raw log). F6 (spec §2)
extends the SAME discipline to every OBJECT WRITE across every builder — field,
tag, value, workflow, form, survey, community, course, channel:

  "No receipt = not created." A run summary is a PURE REDUCTION of the receipts
  written to disk during the run. It is never hand-assembled, never optimistic,
  and it CANNOT claim more than the receipts on disk prove.

WHAT THIS MODULE OWNS
----------------------
  • ``make_receipt`` / ``write_receipt`` — one JSON file per object under
    ``<evidence_root>/ecosystem/<type>-<slug>.json`` (request-shape hash,
    response id, read-back verify proof, disclosures, timestamp).
  • ``list_receipts`` / ``reduce_receipts`` — the ONLY way a caller may derive a
    run summary; it re-reads every receipt file on disk, never a running tally
    kept in memory (a crashed/killed mid-run process still leaves an honest
    partial summary behind).
  • ``assert_consistent`` — raises ``ReceiptContradiction`` if a hand-built
    summary dict ever claims more created/reused/verified objects than the
    receipts on disk actually contain. This is the un-fakeable guard: a
    builder that tries to report success it didn't earn fails loudly instead
    of shipping a silent partial.
  • Duplicate-receipt detection: two receipts for the same
    ``(object_type, slug)`` with DIFFERENT ``response_id`` is a contradiction
    on its own (the object was "created" twice under one slug) — surfaced by
    ``reduce_receipts(..., strict=True)`` / ``assert_consistent``.

This module performs NO GHL I/O and imports nothing GHL-specific — any Skill-6
builder (router, survey, form, funnel, future community/course builders) can
depend on it without pulling in browser/auth machinery. ``ghl_object_router.py``
re-exports these names for backward compatibility; new code should import this
module directly.

CLI
---
    python3 ghl_receipts.py --summarize <evidence_root>   # reduce + print JSON
    python3 ghl_receipts.py --selftest                     # no network, no I/O outside tmp

S06-08 (tenant-safe read-back + no-secret evidence)
---------------------------------------------------
Receipts carry the read-back contract fields additively (see
``tools/ghl_evidence.py``): ``expected_location_id`` /
``observed_location_id`` / ``tenant_binding`` (+ ``run_id`` when known).
``write_receipt`` is a no-secret sink: the receipt's free-form fields pass
through the evidence scrubber before write, the redaction count is stamped
as ``redactions``, and the file is written mode 0600 (Q4) with the mode set
on the temp file before the rename. ``reduce_receipts`` groups and flags
receipts by tenant binding in a ``tenant`` section (present whenever at
least one readable receipt exists; the empty-root reduction keeps its
exact historical shape). ``assert_consistent`` refuses a summary whose
declared tenant disagrees with a stamped receipt (cross-tenant receipt =
contradiction) and refuses an undeclared mixed-tenant reduction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_evidence  # noqa: E402  (S06-08 tenant contract + evidence scrubber)

RECEIPTS_VERSION = "v1.0.0"

# Which ``action`` values a receipt may carry. Anything else is a contradiction.
VALID_ACTIONS = ("created", "reused", "failed")


class ReceiptContradiction(AssertionError):
    """A summary (or the receipt set itself) claims more than the receipts prove."""


# ---------------------------------------------------------------------------
# Receipt construction + storage
# ---------------------------------------------------------------------------
def _request_shape_hash(request_shape: Any) -> str:
    try:
        raw = json.dumps(request_shape, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        raw = repr(request_shape)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def make_receipt(
    object_type: str,
    slug: str,
    action: str,
    *,
    rail: Optional[Any] = None,          # a RailStep-like obj with .rail/.tier/.tool/.token, or None
    response_id: Optional[str] = None,
    request_shape: Any = None,
    verify: Optional[dict] = None,
    disclosures: Optional[List[str]] = None,
    error: Optional[str] = None,
    expected_location_id: Optional[str] = None,
    observed_location_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> dict:
    """Build one F6 per-object receipt dict — the ONLY thing a summary may reduce.

    ``action`` MUST be one of ``VALID_ACTIONS``. ``created``/``reused`` receipts
    with no ``verify.get("ok")`` truthy are still written (an honest attempt
    record) but ``reduce_receipts`` will NOT count them as verified.

    S06-08: ``expected_location_id`` / ``observed_location_id`` / ``run_id``
    stamp the tenant read-back contract fields additively (derived
    ``tenant_binding`` included); omitting them leaves the receipt
    tenant-unbound, which the reducer flags, never silently bound (Q2).
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"invalid receipt action {action!r}; must be one of {VALID_ACTIONS}")
    return {
        "object_type": object_type,
        "slug": slug,
        "action": action,               # created | reused | failed
        "rail": getattr(rail, "rail", None) if rail is not None else None,
        "tier": getattr(rail, "tier", None) if rail is not None else None,
        "tool": getattr(rail, "tool", None) if rail is not None else None,
        "token_context": getattr(rail, "token", None) if rail is not None else None,
        "response_id": response_id,
        "request_shape_hash": _request_shape_hash(request_shape),
        "verify": verify or {},          # re-GET / rendered-DOM proof
        "disclosures": disclosures or [],
        "created": action in ("created", "reused"),
        "error": error,                  # honest failure record (None on success)
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "receipts_version": RECEIPTS_VERSION,
        **ghl_evidence.tenant_fields(
            expected_location_id, observed_location_id, run_id=run_id),
    }


def receipt_path(evidence_root: str, object_type: str, slug: str) -> str:
    """Deterministic path: one file per (object_type, slug). A re-run of the
    SAME slug overwrites its own receipt (idempotent re-verification), which is
    correct — the receipt reflects the object's CURRENT proven state, not a
    history of attempts. History is preserved by the ``ts`` field plus the
    caller's own evidence-root-per-run convention."""
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in slug)[:80]
    safe_type = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in object_type)[:40]
    return os.path.join(evidence_root, "ecosystem", f"{safe_type}-{safe}.json")


def write_receipt(evidence_root: str, receipt: dict, *, secret_values: Any = None) -> str:
    """Write one receipt to disk (atomic-enough for this use: write-then-rename
    avoids a reader ever seeing a half-written JSON file if a process is killed
    mid-write: important because F6's whole point is trusting what's on disk).

    S06-08: this is a no-secret sink. The receipt passes through the evidence
    scrubber before write (its free-form fields: ``verify``, ``disclosures``,
    ``error``, are caller-shaped text), the redaction count is stamped on
    the written receipt as ``redactions``, and the file mode is set to 0600
    explicitly on the temp file before the rename (Q4 interim default);
    the ecosystem dir is created 0700. The caller's dict is not mutated."""
    path = receipt_path(evidence_root, receipt["object_type"], receipt["slug"])
    to_write, redactions = ghl_evidence.EvidenceScrubber(secret_values).scrub_obj(receipt)
    to_write["redactions"] = int(to_write.get("redactions") or 0) + redactions
    ghl_evidence.ensure_private_dir(os.path.dirname(path))
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(to_write, fh, indent=2)
        fh.flush()
        os.chmod(tmp_path, ghl_evidence.FILE_MODE)
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)
    return path


# ---------------------------------------------------------------------------
# Reading + reducing — the ONLY legitimate path to a run summary
# ---------------------------------------------------------------------------
def list_receipts(evidence_root: str) -> List[dict]:
    """Read every receipt file under ``<evidence_root>/ecosystem/``. Corrupt or
    unreadable files are SKIPPED, never silently treated as success — a
    corrupt receipt means that object's true state is UNKNOWN, which
    ``reduce_receipts`` reports as neither created nor reused nor a clean
    failure (it surfaces under ``unreadable`` so it cannot vanish)."""
    eco = os.path.join(evidence_root, "ecosystem")
    out: List[dict] = []
    if not os.path.isdir(eco):
        return out
    for fn in sorted(os.listdir(eco)):
        if not fn.endswith(".json") or fn.endswith(".tmp"):
            continue
        path = os.path.join(eco, fn)
        try:
            with open(path, encoding="utf-8") as fh:
                r = json.load(fh)
            if not isinstance(r, dict) or "object_type" not in r or "slug" not in r:
                raise ValueError("missing required receipt fields")
        except Exception as exc:  # noqa: BLE001
            out.append({
                "object_type": None, "slug": fn, "action": "unreadable",
                "created": False, "error": f"corrupt receipt: {exc}", "_path": path,
            })
            continue
        r["_path"] = path
        out.append(r)
    return out


def reduce_receipts(evidence_root: str, *, strict: bool = False) -> dict:
    """Summary = pure reduction of receipts on disk (F6). No receipt = not
    created. This function NEVER trusts an in-memory counter — it re-reads
    every file every time it is called, which is exactly what makes a
    mid-run crash produce an honest partial summary instead of a stale lie.

    With ``strict=True``, duplicate CONFLICTING receipts for the same
    ``(object_type, slug)`` with different ``response_id`` values raise
    ``ReceiptContradiction`` immediately (the reduction refuses to average
    away a real inconsistency).
    """
    receipts = list_receipts(evidence_root)
    created: List[str] = []
    reused: List[str] = []
    failed: List[str] = []
    unreadable: List[str] = []
    verified: List[str] = []
    unverified: List[str] = []
    seen_response_id: Dict[str, str] = {}
    # S06-08: tenant grouping over the same disk read (never memory).
    tenant_bound: List[str] = []
    tenant_unbound: List[str] = []
    tenant_mismatch: List[str] = []
    tenant_expected_ids: set = set()

    for r in receipts:
        tag = f"{r.get('object_type')}:{r.get('slug')}"
        action = r.get("action")
        if action == "unreadable" or r.get("object_type") is None:
            unreadable.append(tag)
            continue
        if action not in VALID_ACTIONS:
            unreadable.append(tag)
            continue

        binding = ghl_evidence.effective_binding(r)
        if binding == ghl_evidence.BINDING_BOUND:
            tenant_bound.append(tag)
        elif binding == ghl_evidence.BINDING_MISMATCH:
            tenant_mismatch.append(tag)
        else:
            tenant_unbound.append(tag)
        if r.get("expected_location_id"):
            tenant_expected_ids.add(r["expected_location_id"])

        if action == "created":
            created.append(tag)
        elif action == "reused":
            reused.append(tag)
        else:
            failed.append(tag)

        if action in ("created", "reused"):
            if r.get("verify", {}).get("ok") is True:
                verified.append(tag)
            else:
                unverified.append(tag)

        rid = r.get("response_id")
        if rid:
            key = tag
            prior = seen_response_id.get(key)
            if prior is not None and prior != rid:
                msg = (f"conflicting response_id for {tag}: "
                       f"{prior!r} vs {rid!r} — same slug created twice under "
                       f"different objects")
                if strict:
                    raise ReceiptContradiction(msg)
            seen_response_id[key] = rid

    summary = {
        "created": created,
        "reused": reused,
        "failed": failed,
        "unreadable": unreadable,
        "verified": verified,
        "unverified": unverified,
        "total": len(created) + len(reused) + len(failed) + len(unreadable),
        "all_verified": not failed and not unreadable and not unverified,
    }
    # S06-08 tenant section: present whenever at least one READABLE receipt
    # exists on disk, so tenant state is always flagged on real runs (legacy
    # unstamped receipts land in "unbound", flagged, never silently bound).
    # The empty-root reduction keeps its exact historical shape (pinned by
    # tests/test_ghl_receipts.py's exact-equality assertion).
    if created or reused or failed:
        summary["tenant"] = {
            "bound": tenant_bound,
            "unbound": tenant_unbound,
            "mismatch": tenant_mismatch,
            "expected_location_ids": sorted(tenant_expected_ids),
            "mixed_tenant": len(tenant_expected_ids) > 1,
        }
    return summary


def assert_consistent(summary: dict, evidence_root: str) -> None:
    """Raise ``ReceiptContradiction`` unless ``summary`` is EXACTLY consistent
    with a fresh reduction of the receipts on disk. Call this immediately
    before a builder reports PASS/DONE to the board or the operator — it is
    the mechanical guard against the "30/30 PASS next to 1/6 live" class of
    incident (F6). A summary may UNDER-claim relative to disk (e.g. it only
    reports a subset intentionally) but may NEVER over-claim.
    """
    truth = reduce_receipts(evidence_root)

    def _as_set(x) -> set:
        return set(x) if x else set()

    claimed_created = _as_set(summary.get("created"))
    claimed_reused = _as_set(summary.get("reused"))
    claimed_verified = _as_set(summary.get("verified"))

    over_created = claimed_created - _as_set(truth["created"])
    if over_created:
        raise ReceiptContradiction(
            f"summary claims {sorted(over_created)} as created but no matching "
            f"receipt exists on disk under {evidence_root!r}"
        )
    over_reused = claimed_reused - _as_set(truth["reused"])
    if over_reused:
        raise ReceiptContradiction(
            f"summary claims {sorted(over_reused)} as reused but no matching "
            f"receipt exists on disk under {evidence_root!r}"
        )
    over_verified = claimed_verified - _as_set(truth["verified"])
    if over_verified:
        raise ReceiptContradiction(
            f"summary claims {sorted(over_verified)} as verified but the "
            f"receipt(s) on disk do not show verify.ok == True"
        )
    claimed_total = summary.get("total")
    if claimed_total is not None and claimed_total > truth["total"]:
        raise ReceiptContradiction(
            f"summary total={claimed_total} exceeds receipts-on-disk total="
            f"{truth['total']} under {evidence_root!r}"
        )

    # S06-08 tenant guard. Four refusals, all contradiction-class:
    #  (a) the summary declares an expected location and a receipt on disk is
    #      stamped for a DIFFERENT tenant: a cross-tenant page receipt or a
    #      cross-tenant result receipt is a contradiction, never a pass;
    #  (b) the receipts on disk span multiple tenants and the summary does
    #      not declare the mixed-tenant reduction;
    #  (c) the summary carries a tenant section that OMITS a mismatched
    #      receipt present on disk (over-claiming binding quality);
    #  (d) invariant-7 mirror (S06-08 cure): the summary declares an
    #      expected location and a VERIFIED created/reused receipt stamped
    #      for that same expected location is not tenant-bound (its
    #      read-back obtained no observation, or a different one): a
    #      verified success in a declared-expected run must be bound, the
    #      same trigger as ghl_verify's invariant 7. Receipts carrying no
    #      expected stamp (pure legacy) are skipped, exactly as in (a).
    # Legacy summaries (no tenant fields) over legacy receipts (no stamps)
    # trigger none of these: Q2 grandfathering.
    disk_tenant = truth.get("tenant") or {}
    declared_expected = summary.get("expected_location_id")
    if declared_expected:
        foreign = [
            e for e in (disk_tenant.get("expected_location_ids") or [])
            if e != declared_expected
        ]
        if foreign:
            raise ReceiptContradiction(
                f"cross-tenant receipt(s) on disk under {evidence_root!r}: "
                f"receipts stamped expected_location_id in {sorted(foreign)} "
                f"while the summary declares {declared_expected!r}"
            )
    if disk_tenant.get("mixed_tenant"):
        summary_tenant = summary.get("tenant") or {}
        declares_mixed = (
            summary_tenant.get("mixed_tenant") is True
            or summary.get("mixed_tenant") is True
            or set(summary_tenant.get("expected_location_ids") or [])
            == set(disk_tenant.get("expected_location_ids") or [])
        )
        if not declares_mixed:
            raise ReceiptContradiction(
                "receipts on disk span multiple tenants "
                f"({sorted(disk_tenant.get('expected_location_ids') or [])}) "
                "but the summary does not declare the mixed-tenant reduction"
            )
    summary_tenant = summary.get("tenant") or {}
    if "mismatch" in summary_tenant:
        omitted = _as_set(disk_tenant.get("mismatch")) - _as_set(
            summary_tenant.get("mismatch"))
        if omitted:
            raise ReceiptContradiction(
                f"summary tenant section omits tenant-mismatched receipt(s) "
                f"{sorted(omitted)} present on disk under {evidence_root!r}"
            )
    # (d) invariant-7 mirror. The declared set comes from the summary's own
    # declaration surfaces: its top-level expected_location_id and/or its
    # tenant section's expected_location_ids. Only receipts stamped for one
    # of those declared locations are judged; unstamped legacy receipts are
    # skipped (Q2 grandfathering), and a summary declaring nothing is
    # judged on nothing.
    declared_ids = set()
    if declared_expected:
        declared_ids.add(declared_expected)
    declared_ids.update(summary_tenant.get("expected_location_ids") or [])
    if declared_ids:
        verified_tags = _as_set(truth["verified"])
        not_bound = set()
        for r in list_receipts(evidence_root):
            tag = f"{r.get('object_type')}:{r.get('slug')}"
            if tag not in verified_tags:
                continue
            stamped_expected = r.get("expected_location_id")
            if not stamped_expected or stamped_expected not in declared_ids:
                continue
            if ghl_evidence.effective_binding(r) != ghl_evidence.BINDING_BOUND:
                not_bound.add(tag)
        if not_bound:
            raise ReceiptContradiction(
                f"summary declares expected location(s) "
                f"{sorted(declared_ids)} but verified receipt(s) "
                f"{sorted(not_bound)} under {evidence_root!r} are not "
                f"tenant-bound to a declared location (invariant-7 mirror: "
                f"a verified success in a declared-expected run must carry "
                f"tenant_binding 'bound')"
            )


# ---------------------------------------------------------------------------
# Self-test — no network, no browser, no GHL writes (tmp dir only)
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    errors: List[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        # 1. Empty evidence root reduces to an honest all-zero summary.
        summ = reduce_receipts(tmp)
        if summ["total"] != 0 or summ["created"] or summ["all_verified"] is not True:
            errors.append(f"empty root should reduce to zero/true, got {summ}")

        # 2. Write + read back one receipt round-trip.
        r1 = make_receipt("tag", "zhc_dupe", "created", response_id="t1",
                           verify={"ok": True, "proof": "GET matched"})
        p1 = write_receipt(tmp, r1)
        if not os.path.exists(p1):
            errors.append("write_receipt did not create a file")
        loaded = list_receipts(tmp)
        if len(loaded) != 1 or loaded[0]["response_id"] != "t1":
            errors.append(f"list_receipts round-trip broken: {loaded}")

        # 3. reduce_receipts counts created + verified.
        summ = reduce_receipts(tmp)
        if summ["created"] != ["tag:zhc_dupe"] or summ["verified"] != ["tag:zhc_dupe"]:
            errors.append(f"reduce_receipts missed the created+verified object: {summ}")

        # 4. A receipt with no successful verify is NOT counted verified.
        r2 = make_receipt("custom_field", "zhc_fav", "created", response_id="cf1",
                           verify={"ok": False, "detail": "read-back mismatch"})
        write_receipt(tmp, r2)
        summ = reduce_receipts(tmp)
        if "custom_field:zhc_fav" in summ["verified"]:
            errors.append("unverified create should not appear in verified[]")
        if "custom_field:zhc_fav" not in summ["unverified"]:
            errors.append("unverified create must appear in unverified[]")

        # 5. A failed receipt is counted honestly, never as created/reused.
        r3 = make_receipt("survey", "zhc_survey", "failed", error="public URL 404")
        write_receipt(tmp, r3)
        summ = reduce_receipts(tmp)
        if "survey:zhc_survey" not in summ["failed"]:
            errors.append("failed receipt missing from failed[]")
        if summ["all_verified"] is not False:
            errors.append("all_verified must go False once ANY failure exists")

        # 6. Corrupt receipt file surfaces as unreadable, never silently dropped.
        eco = os.path.join(tmp, "ecosystem")
        with open(os.path.join(eco, "custom_field-broken.json"), "w") as fh:
            fh.write("{not json")
        summ = reduce_receipts(tmp)
        if not summ["unreadable"]:
            errors.append("corrupt receipt file must surface in unreadable[]")
        if summ["total"] != 4:  # 3 good receipts + 1 unreadable
            errors.append(f"total should include the unreadable receipt: {summ}")

        # 7. Invalid action is rejected at construction time (fail loud, not silent).
        try:
            make_receipt("tag", "x", "maybe")
            errors.append("make_receipt should reject an invalid action")
        except ValueError:
            pass

        # 8. assert_consistent passes for a truthful summary.
        truth = reduce_receipts(tmp)
        try:
            assert_consistent(truth, tmp)
        except ReceiptContradiction as exc:
            errors.append(f"assert_consistent should pass on a truthful summary: {exc}")

        # 9. assert_consistent RAISES on an over-claiming summary (the F6 guard).
        lie = dict(truth)
        lie["created"] = list(truth["created"]) + ["tag:zhc_never_happened"]
        try:
            assert_consistent(lie, tmp)
            errors.append("assert_consistent must raise on an over-claiming summary")
        except ReceiptContradiction:
            pass

        # 10. assert_consistent RAISES if verified[] claims more than proven.
        lie2 = dict(truth)
        lie2["verified"] = list(truth["verified"]) + ["custom_field:zhc_fav"]
        try:
            assert_consistent(lie2, tmp)
            errors.append("assert_consistent must raise on a fabricated verified claim "
                          "(the exact '30/30 PASS next to 1/6 live' shape)")
        except ReceiptContradiction:
            pass

        # 11. assert_consistent allows UNDER-claiming (a partial report is honest).
        under = {"created": [], "reused": [], "verified": [], "total": 0}
        try:
            assert_consistent(under, tmp)
        except ReceiptContradiction as exc:
            errors.append(f"assert_consistent must allow under-claiming: {exc}")

    # 12. strict=True raises on conflicting response_id under the same slug.
    with tempfile.TemporaryDirectory() as tmp2:
        write_receipt(tmp2, make_receipt("tag", "zhc_x", "created", response_id="A"))
        # Overwrite the SAME file path but simulate a conflicting record by writing
        # a second object_type/slug pair that collides only in content, not path —
        # exercise the strict duplicate-response_id detector directly via two
        # differently-pathed receipts sharing object_type/slug (simulated by hand).
        conflicting = [
            make_receipt("tag", "zhc_x", "created", response_id="A"),
            make_receipt("tag", "zhc_x", "created", response_id="B"),
        ]
        # reduce_receipts reads from disk; to exercise the in-memory conflict path
        # directly we call it on a synthetic list via list_receipts monkeypoint is
        # unnecessary — write both under distinct filenames sharing slug identity.
        write_receipt(tmp2, conflicting[0])
        # second write overwrites the same path (receipt_path is deterministic per
        # slug) so simulate the true multi-writer race by writing to an explicit
        # second filename with the same object_type/slug fields.
        p2 = os.path.join(tmp2, "ecosystem", "tag-zhc_x__race.json")
        with open(p2, "w", encoding="utf-8") as fh:
            json.dump(conflicting[1], fh)
        try:
            reduce_receipts(tmp2, strict=True)
            errors.append("strict reduce_receipts must raise on conflicting response_id")
        except ReceiptContradiction:
            pass
        # non-strict mode must NOT raise (backward-compatible default)
        try:
            reduce_receipts(tmp2, strict=False)
        except ReceiptContradiction:
            errors.append("non-strict reduce_receipts must not raise on conflicts")

    # 13. S06-08: tenant-stamped receipts group by binding in the reduction;
    # an unstamped (legacy) receipt flags as unbound, never silently bound.
    with tempfile.TemporaryDirectory() as tmp3:
        write_receipt(tmp3, make_receipt(
            "page", "zhc_bound", "created", response_id="p1",
            verify={"ok": True}, expected_location_id="locA",
            observed_location_id="locA", run_id="run-t"))
        write_receipt(tmp3, make_receipt(
            "page", "zhc_legacy", "created", response_id="p2",
            verify={"ok": True}))
        summ3 = reduce_receipts(tmp3)
        tenant3 = summ3.get("tenant") or {}
        if tenant3.get("bound") != ["page:zhc_bound"]:
            errors.append(f"bound receipt must group as bound: {tenant3}")
        if tenant3.get("unbound") != ["page:zhc_legacy"]:
            errors.append(f"legacy receipt must flag as unbound: {tenant3}")
        if tenant3.get("mixed_tenant") is not False:
            errors.append(f"one expected tenant is not mixed: {tenant3}")
        # A truthful reduce-produced summary stays consistent.
        try:
            assert_consistent(summ3, tmp3)
        except ReceiptContradiction as exc:
            errors.append(f"truthful tenant summary must be consistent: {exc}")
        # A summary declaring tenant A over a receipt stamped tenant B is a
        # cross-tenant contradiction.
        write_receipt(tmp3, make_receipt(
            "page", "zhc_foreign", "created", response_id="p3",
            verify={"ok": True}, expected_location_id="locB",
            observed_location_id="locB"))
        foreign_summary = dict(reduce_receipts(tmp3))
        foreign_summary["expected_location_id"] = "locA"
        try:
            assert_consistent(foreign_summary, tmp3)
            errors.append("cross-tenant receipt must contradict a locA summary")
        except ReceiptContradiction:
            pass
        # And the mixed-tenant disk state must be DECLARED: the same summary
        # without its tenant section refuses.
        undeclared = dict(reduce_receipts(tmp3))
        undeclared.pop("tenant", None)
        try:
            assert_consistent(undeclared, tmp3)
            errors.append("undeclared mixed-tenant reduction must be refused")
        except ReceiptContradiction:
            pass

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — receipts store + reducer verified (no network / no browser)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_receipts",
        description="Skill-6 F6 per-object receipts store + reducer.",
    )
    p.add_argument("--selftest", action="store_true",
                   help="Run the no-network self-test and exit.")
    p.add_argument("--summarize", metavar="EVIDENCE_ROOT",
                   help="Reduce all receipts under EVIDENCE_ROOT/ecosystem/ and print JSON.")
    p.add_argument("--strict", action="store_true",
                   help="With --summarize: raise on conflicting duplicate receipts.")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.summarize:
        try:
            summ = reduce_receipts(args.summarize, strict=args.strict)
        except ReceiptContradiction as exc:
            print(f"ReceiptContradiction: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(summ, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

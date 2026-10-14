#!/usr/bin/env python3
"""
ghl_ops.py - the FIX-PLAN Item 33a seam module (presentations side).

THE SEAM
-------------------------------------------------------------------------------------
Presentations never calls the GoHighLevel (Convert and Flow) API for the
operations a run needs around its forms and workflows. Skill 44
(44-convert-and-flow-operator, the Tier 0 caf operator) executes them under
its own gates (PLAN MODE, dry-run first, draft-only default, location
whitelist, approval gate, WF-1..21 + rubric QC). This module is the
presentations side of that two-way seam:

  OUT  working/ghl/ghl-ops-request.json
       A versioned request listing the GHL operations this run needs
       (form creation/attachment, workflow trigger coverage, product and
       order-form binding for the sandbox path, test-submission proof,
       booking-calendar verification), each carrying the Wiring Gate's
       verification expectations: the named read-back checks the receipt
       must answer before the operation may be called done.

  IN   working/ghl/ghl-ops-receipt.json
       Written by the Skill 44 side at execution. Per-object results WITH
       verification read-backs (the object exists in GHL, attached to the
       right funnel/page, triggers covered, a test submission landed where
       it should, order forms and products bound and priced correctly).
       This module only READS and judges it.

THE JUDGING RULE (the whole point of the seam)
-------------------------------------------------------------------------------------
A receipt entry that claims success WITHOUT its verification read-back is
judged UNVERIFIED, never success. An operation is "verified" only when the
receipt entry carries the remote object id AND a read-back in which every
check the request named for that operation is present and ok. Partial
read-backs judge partial. A missing entry judges missing. An absent
receipt judges absent (Skill 44 not available or not yet executed), which
is pending, never a failure and never a pass: the run proceeds exactly as
it does today and no operation is marked done.

RELATIONSHIP TO THE PHASE RECEIPTS (never conflated)
-------------------------------------------------------------------------------------
ghl_external_installer.py owns the per-phase install receipts
(P-U-GHL-SALES / P-U-GHL-VSL / P-U-FORM-GATE) and validate_receipt remains
the phase-completion judge. This seam is the run-level operations contract
the FIX-PLAN names: emitted at install and at delivery (the --stage flag),
consumed by the install path and by delivery. Its operations are DERIVED
from the same contract builders the phases already use
(checkout_form_builder.build_skill44_contract,
ghl_external_installer.build_gate_form_plan), never re-derived here, so
the request cannot drift from the contracts the phases emit. Scope
binding delegates to ghl_external_installer.resolve_scope and the
elections to the builders' own gates, exactly like page_brief.py.

EXECUTION IS SPECIFIED, NOT IMPERSONATED
-------------------------------------------------------------------------------------
Nothing in this module calls GHL, caf, or any network. The request names
Skill 44's execution surface (caf under its own gates, the shared Skill 36
rate-limit bucket, the access tier the executor records on the receipt).
If Skill 44 is absent, the fallback is today's behavior unchanged, and the
judge records the receipt as absent because Skill 44 was not available.

USAGE
    python3 scripts/ghl_ops.py --run-dir <run_dir> [--stage install|delivery]
    python3 scripts/ghl_ops.py --run-dir <run_dir> --judge
    python3 scripts/ghl_ops.py --selftest

EXIT CODES
    0 - emitted / no operations requested (all elections deferred or
        waived) / judge: receipt complete, or receipt absent (pending)
    2 - usage error
    3 - GATE BLOCKED (an election gate failed closed)
    4 - VALIDATION / JUDGE FAILED (request failed write-time validation,
        or a present receipt is invalid, incomplete, or unverified)
    5 - BLOCKED (scope / offer / intent blocker, phase-scoped)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_GATE_BLOCKED = 3
EXIT_VERIFY_FAILED = 4
EXIT_BLOCKED = 5

REQUEST_SCHEMA_NAME = "ghl-ops-request"
RECEIPT_SCHEMA_NAME = "ghl-ops-receipt"
SCHEMA_VERSION = "1.0"

REQUEST_REL = Path("working") / "ghl" / "ghl-ops-request.json"
RECEIPT_REL = Path("working") / "ghl" / "ghl-ops-receipt.json"
LEDGER_REL = Path("working") / "checkpoints" / "ghl_ops.json"
INTAKE_REL = Path("working") / "copy" / "intake.json"

# Run artifacts a request references by path + sha256 when they exist (the
# per-phase contracts the operations derive from).
SOURCE_CONTRACT_RELS = (
    Path("working") / "sales-checkout" / "checkout_form_skill44.json",
    Path("working") / "sales-checkout" / "checkout_form.json",
    Path("working") / "vsl" / "gate_form_skill44_plan.json",
)

# Operation kinds (the standard operation set).
OP_FORM = "form.create_or_reuse"
OP_WORKFLOW = "workflow.ensure_trigger_coverage"
OP_TEST_SUBMISSION = "form.test_submission"
OP_PRODUCT = "product.create_or_reuse"
OP_ORDER_FORM = "order_form.bind_product"
OP_CALENDAR = "calendar.verify_booking"
OP_KINDS = (OP_FORM, OP_WORKFLOW, OP_TEST_SUBMISSION, OP_PRODUCT,
            OP_ORDER_FORM, OP_CALENDAR)

# Verification check catalog (the Wiring Gate, named per object). Every
# check named here must be answered in the receipt's read-back for the
# operation to judge verified.
CHECK_OBJECT_EXISTS = "object_exists"
CHECK_ATTACHED = "attached_to_target"
CHECK_FIELDS_MATCH = "fields_match_contract"
CHECK_EMBED_LIVE = "embed_live_on_page"
CHECK_TRIGGER_BOUND = "trigger_bound"
CHECK_STEPS_MATCH = "steps_match_contract"
CHECK_DRAFT_STATE = "draft_state_recorded"
CHECK_SUBMISSION_LANDED = "submission_landed"
CHECK_CONTACT_SCOPED = "contact_scoped"
CHECK_WORKFLOW_ENROLLED = "workflow_enrolled"
CHECK_TAG_APPLIED = "tag_applied"
CHECK_PRICE_MATCHES = "price_matches_offer"
CHECK_PRODUCT_BOUND = "product_bound"
CHECK_CALENDAR_EXISTS = "calendar_exists"
CHECK_APPOINTMENTS_READ = "upcoming_appointments_read"

# Receipt claim vocabulary (what the executor asserts) vs judge verdicts
# (what presentations concludes). Claims never become verdicts directly.
CLAIMS_SUCCESS = ("created", "reused", "verified")
CLAIM_FAILED = "failed"
CLAIM_PARTIAL = "partial"
CLAIM_SKIPPED = "skipped"

VERDICT_VERIFIED = "verified"
VERDICT_PARTIAL = "partial"
VERDICT_UNVERIFIED = "unverified"
VERDICT_MISSING = "missing"
VERDICT_FAILED = "failed"

OVERALL_COMPLETE = "complete"
OVERALL_PARTIAL = "partial"
OVERALL_UNVERIFIED = "unverified"
OVERALL_FAILED = "failed"
OVERALL_INVALID = "invalid"
OVERALL_ABSENT = "absent"
OVERALL_NO_REQUEST = "no_request"

EXECUTOR_BLOCK = {
    "owner_skill": "44-convert-and-flow-operator",
    "surface": ("caf CLI, executed by an agent running Skill 44 under its "
                "own gates (PLAN MODE, dry-run first, draft-only default, "
                "location whitelist, approval gate, per-build QC). "
                "Presentations never calls the GHL API for these "
                "operations and never impersonates the execution."),
    "access_tiers": ["tier0_caf_pit", "tier0_caf_firebase",
                      "tier4_managed_browser"],
    "rate_limit": {
        "bucket": "ghl-shared-all-tiers",
        "daily_cap": 200000,
        "note": ("one shared GHL bucket across all tiers (Skill 36 "
                 "routing law; Skill 44 INSTRUCTIONS.md rate-limit "
                 "protocol). On a 429 the executor STOPS and surfaces "
                 "the reset time; it never falls through tiers."),
    },
    "absent_fallback": ("if Skill 44 is not available, the run proceeds "
                        "exactly as it does today and the judge records "
                        "the receipt as absent because Skill 44 was not "
                        "available; no operation is marked done"),
}


class OpsError(RuntimeError):
    """A fail-closed seam failure (message names the refusing gate)."""


class OpsValidationError(OpsError):
    """validate_request rejected the request at write time."""

    def __init__(self, errors: List[str]):
        super().__init__("request validation failed: " + "; ".join(errors))
        self.errors = errors


# ---------------------------------------------------------------------------
# Small helpers (repo style: stdlib only, atomic writes, ISO-UTC stamps)
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return ""


def _read_json(p: Path) -> dict:
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_atomic(p: Path, data: dict) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def _here() -> Path:
    return Path(__file__).resolve().parent


def _load_siblings() -> Dict[str, Any]:
    """Import the sibling executors this seam delegates to (fail-soft at
    import, fail-CLOSED at use, the installer's own posture)."""
    here = str(_here())
    if here not in sys.path:
        sys.path.insert(0, here)
    mods: Dict[str, Any] = {}
    for name in ("sales_checkout_builder", "vsl_builder",
                 "checkout_form_builder", "ghl_external_installer"):
        try:
            mods[name] = __import__(name)
        except Exception:  # noqa: BLE001
            mods[name] = None
    return mods


def _rel(run_dir: Path, p: Path) -> str:
    try:
        return str(p.relative_to(run_dir))
    except ValueError:
        return str(p)


def _new_request_id() -> str:
    return f"gxo_{uuid.uuid4().hex[:12]}"


def _record_ledger(run_dir: Path, event: dict) -> dict:
    ledger = _read_json(run_dir / LEDGER_REL)
    events = ledger.setdefault("events", [])
    events.append(event)
    ledger["last"] = event
    ledger["updated_at"] = _now_iso()
    _write_json_atomic(run_dir / LEDGER_REL, ledger)
    return ledger


def load_request(run_dir: Path) -> dict:
    return _read_json(run_dir / REQUEST_REL)


def load_receipt(run_dir: Path) -> dict:
    return _read_json(run_dir / RECEIPT_REL)


# ---------------------------------------------------------------------------
# Operation builders (derived from the phase contracts, never re-derived)
# ---------------------------------------------------------------------------
def _expect(*checks: str) -> List[Dict[str, str]]:
    return [{"check": c} for c in checks]


def _form_op(op_id: str, *, title: str, form_name: str,
             fields: List[dict], receipt_ref: str,
             target: Dict[str, Any],
             embed: Optional[Dict[str, Any]] = None) -> dict:
    return {
        "op_id": op_id,
        "kind": OP_FORM,
        "title": title,
        "spec": {
            "name": form_name,
            "fields": fields,
            "embed": embed or {"mechanism": "SKILL44_WIDGET -> FORM",
                               "frame_src": "https://api.leadconnectorhq.com/widget/form/{form_id}",
                               "instructions": ("embed the form verbatim in "
                                                "the page; no SRI on the "
                                                "embed script")},
            "receipt_ref": receipt_ref,
        },
        "target": target,
        "expect": _expect(CHECK_OBJECT_EXISTS, CHECK_ATTACHED,
                          CHECK_FIELDS_MATCH, CHECK_EMBED_LIVE),
        "executor_notes": ("create or reuse by exact name in the bound "
                           "location; the object's live id replaces "
                           "{form_id} in the embed at build time"),
    }


def _workflow_op(op_id: str, *, title: str, workflow_name: str,
                 trigger_form_op: str, trigger_form_name: str,
                 steps: List[dict], receipt_ref: str,
                 template_match: Optional[dict] = None) -> dict:
    op = {
        "op_id": op_id,
        "kind": OP_WORKFLOW,
        "title": title,
        "spec": {
            "name": workflow_name,
            "trigger": {"type": "form_submitted",
                        "form_op": trigger_form_op,
                        "form_name": trigger_form_name},
            "steps": steps,
            "draft_only": True,
            "receipt_ref": receipt_ref,
        },
        "expect": _expect(CHECK_OBJECT_EXISTS, CHECK_TRIGGER_BOUND,
                          CHECK_STEPS_MATCH, CHECK_DRAFT_STATE),
        "executor_notes": ("build through Skill 44 PLAN MODE; the workflow "
                           "stays DRAFT until a human publishes it; the "
                           "trigger binds the LIVE form id produced by "
                           "the form operation, never the planned name"),
    }
    if template_match:
        op["template_match_request"] = template_match
    return op


def _test_submission_op(op_id: str, *, title: str, form_op: str,
                        workflow_op: str, extra_checks: Tuple[str, ...] = ()
                        ) -> dict:
    return {
        "op_id": op_id,
        "kind": OP_TEST_SUBMISSION,
        "title": title,
        "spec": {
            "form_op": form_op,
            "workflow_op": workflow_op,
            "method": ("submit the live form once with an obviously-test "
                       "contact scoped to the run (test marker on the "
                       "contact), then read back the form's submission "
                       "list and the contact's workflow enrollment"),
        },
        "expect": _expect(CHECK_SUBMISSION_LANDED, CHECK_CONTACT_SCOPED,
                          CHECK_WORKFLOW_ENROLLED, *extra_checks),
        "executor_notes": ("this is the Wiring Gate's landing proof: the "
                           "submission must be observed in GHL, not "
                           "inferred from a 200 on the embed"),
    }


def _checkout_operations(run_dir: Path, intake: dict, scope: dict,
                         mods: Dict[str, Any]) -> Tuple[List[dict], List[str], Optional[dict]]:
    """Checkout family. Returns (operations, notes, blocker). Every fact
    is resolved by checkout_form_builder itself (page_brief.py's
    delegation pattern); this seam never re-derives an offer, an intent,
    or an approved-URL decision."""
    cfb = mods["checkout_form_builder"]
    notes: List[str] = []
    brief = intake.get("deck_brief")
    brief = brief if isinstance(brief, dict) else {}
    offer, blocker = cfb.resolve_offer(brief)
    if blocker is not None or offer is None:
        return [], notes, blocker
    intent, blocker = cfb.resolve_intent(brief, offer)
    if blocker is not None:
        return [], notes, blocker
    company = ""
    if isinstance(intake.get("company"), str):
        company = intake["company"]
    elif isinstance(brief.get("COMPANY"), str):
        company = brief["COMPANY"]
    approved_url, url_blocker = cfb.resolve_approved_url(
        brief, deck_slug=scope["deck_slug"], company=company)
    if url_blocker is not None:
        return [], notes, url_blocker
    if approved_url:
        notes.append("checkout form operation omitted: the run carries a "
                     "client-approved checkout URL "
                     f"({approved_url}); Skill 44 builds no form for "
                     "this checkout (checkout_form_builder reuse "
                     "posture)")
        return [], notes, None
    fields = cfb.build_form_schema(offer=offer, intent=intent,
                                   deck_slug=scope["deck_slug"])
    consent = cfb.resolve_consent_copy(intake, brief)
    contract = cfb.build_skill44_contract(offer=offer, intent=intent,
                                          scope=scope, fields=fields,
                                          consent=consent)
    form_name = contract["form"]["name"]
    workflow_name = contract["workflow"]["name"]
    field_specs = [{"field_key": f.get("field_key") or f.get("query_key"),
                    "label": f.get("label"),
                    "source": f.get("source"),
                    "required": bool(f.get("required"))}
                   for f in fields]
    ops: List[dict] = []
    ops.append(_form_op(
        "checkout-form", title="Checkout form (sales/checkout phase)",
        form_name=form_name, fields=field_specs,
        receipt_ref="working/sales-checkout/checkout_form.json",
        target={"page_role": "checkout",
                "funnel_name": f"{scope.get('deck_slug', '')} funnel",
                "attach_rule": ("the form embeds on the checkout page of "
                                "this run's funnel")},
        embed=contract.get("embed_contract")))
    ops.append(_workflow_op(
        "checkout-workflow",
        title="Checkout enrollment workflow (form-submitted trigger)",
        workflow_name=workflow_name, trigger_form_op="checkout-form",
        trigger_form_name=form_name,
        steps=contract["workflow"].get("steps", []),
        receipt_ref="working/sales-checkout/checkout_form.json",
        template_match={
            "requested": True,
            "library": "44-convert-and-flow-operator/automation-templates",
            "context": ("elected follow-up for a completed checkout; "
                        "Skill 44's own matcher decides the match. A "
                        "request, never an instruction to build "
                        "unmatched automations."),
        }))
    ops.append(_test_submission_op(
        "checkout-test-submission",
        title="Checkout form test submission (landing proof)",
        form_op="checkout-form", workflow_op="checkout-workflow"))
    if intent == cfb.INTENT_PAYMENT_SANDBOX:
        product_name = f"ZHC {scope.get('deck_slug', '')} {offer['name']}"
        ops.append({
            "op_id": "checkout-product",
            "kind": OP_PRODUCT,
            "title": "Checkout product (sandbox binding target)",
            "spec": {"name": product_name,
                     "amount_minor": offer.get("amount_minor"),
                     "price_display": offer.get("price_display"),
                     "currency": offer.get("currency"),
                     "mode": "payment_sandbox",
                     "live_payment": ("never requested: live payment is "
                                      "out of scope for this seam "
                                      "(checkout_form_builder "
                                      "UNSUPPORTED_PAYMENT posture)")},
            "expect": _expect(CHECK_OBJECT_EXISTS, CHECK_PRICE_MATCHES),
            "executor_notes": ("create or reuse by exact name; the price "
                               "read-back must equal the offer amount and "
                               "currency exactly"),
        })
        ops.append({
            "op_id": "checkout-order-form",
            "kind": OP_ORDER_FORM,
            "title": "Order-form product binding (sandbox)",
            "spec": {"product_op": "checkout-product",
                     "form_op": "checkout-form",
                     "mode": "payment_sandbox"},
            "expect": _expect(CHECK_PRODUCT_BOUND, CHECK_PRICE_MATCHES),
            "executor_notes": ("bind the product to the checkout form's "
                               "order form; the binding read-back must "
                               "show the same amount and currency as the "
                               "offer"),
        })
    return ops, notes, None


def _gate_operations(scope: dict, mods: Dict[str, Any]) -> List[dict]:
    """VSL gate family, from the installer's own PRES-011 plan builder."""
    gx = mods["ghl_external_installer"]
    plan = gx.build_gate_form_plan(scope=scope)
    form = plan.get("form", {})
    workflow = plan.get("workflow", {})
    fields = [{"field_key": f.get("field_key"),
               "label": f.get("label"),
               "field_type": f.get("field_type"),
               "required": bool(f.get("required"))}
              for f in gx.gate_form_fields()]
    ops: List[dict] = []
    ops.append(_form_op(
        "gate-form", title="VSL gate form (PRES-011 P-U-FORM-GATE)",
        form_name=form.get("name", ""),
        fields=fields,
        receipt_ref="ecosystem/gate-form.json",
        target={"page_role": "vsl",
                "attach_rule": ("the REAL GHL form embed replaces the "
                                "page's native gate form; the page's gate "
                                "overlay listens for the page-relayed "
                                "submit-success event")}))
    ops.append(_workflow_op(
        "gate-workflow",
        title="VSL gate workflow (tag on submit)",
        workflow_name=workflow.get("name", ""),
        trigger_form_op="gate-form",
        trigger_form_name=form.get("name", ""),
        steps=workflow.get("steps", []),
        receipt_ref="workflows/gate-workflow.json"))
    ops.append(_test_submission_op(
        "gate-test-submission",
        title="Gate form test submission (landing proof)",
        form_op="gate-form", workflow_op="gate-workflow",
        extra_checks=(CHECK_TAG_APPLIED,)))
    return ops


def _resolve_calendar(intake: dict) -> str:
    for key in ("BOOKING_CALENDAR_ID", "CALENDAR_ID"):
        value = intake.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    brief = intake.get("deck_brief") or {}
    if isinstance(brief, dict):
        for key in ("BOOKING_CALENDAR_ID", "CALENDAR_ID",
                    "BOOKING_CALENDAR"):
            value = brief.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _calendar_op(calendar_id: str) -> dict:
    return {
        "op_id": "booking-calendar",
        "kind": OP_CALENDAR,
        "title": "Booking calendar verification (deck CTA target)",
        "spec": {"calendar_id": calendar_id,
                 "method": ("read back the named calendar and its "
                            "upcoming appointments; confirm the deck's "
                            "CTA points at this calendar")},
        "expect": _expect(CHECK_CALENDAR_EXISTS, CHECK_APPOINTMENTS_READ),
        "executor_notes": ("read-only verification; this operation "
                           "creates nothing"),
    }


# ---------------------------------------------------------------------------
# Request validation (write-time, fail-closed, like page_brief.validate_brief)
# ---------------------------------------------------------------------------
def validate_request(request: dict) -> List[str]:
    errs: List[str] = []
    if request.get("schema") != REQUEST_SCHEMA_NAME:
        errs.append(f"schema != {REQUEST_SCHEMA_NAME!r}")
    if request.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version != {SCHEMA_VERSION!r}")
    if not request.get("request_id"):
        errs.append("request_id missing")
    if request.get("stage") not in ("install", "delivery"):
        errs.append("stage must be 'install' or 'delivery'")
    scope = request.get("scope") or {}
    for key in ("deck_slug", "run_id"):
        if not scope.get(key):
            errs.append(f"scope.{key} missing (the receipt cannot bind "
                        "without it)")
    executor = request.get("executor") or {}
    if executor.get("owner_skill") != "44-convert-and-flow-operator":
        errs.append("executor.owner_skill must name Skill 44")
    ops = request.get("operations")
    if not isinstance(ops, list) or not ops:
        errs.append("operations must be a non-empty list")
        ops = ops if isinstance(ops, list) else []
    seen: set = set()
    for op in ops:
        op_id = op.get("op_id")
        if not op_id or op_id in seen:
            errs.append(f"operation op_id missing or duplicated: {op_id!r}")
        seen.add(op_id)
        if op.get("kind") not in OP_KINDS:
            errs.append(f"{op_id}: unknown kind {op.get('kind')!r}")
        expect = op.get("expect")
        if not isinstance(expect, list) or not expect:
            errs.append(f"{op_id}: a Wiring Gate operation with no "
                        "verification expectations is not a request, it "
                        "is a hope; expect must name the read-back checks")
        if op.get("kind") == OP_WORKFLOW:
            trigger = (op.get("spec") or {}).get("trigger") or {}
            if trigger.get("type") != "form_submitted" or \
                    not trigger.get("form_op"):
                errs.append(f"{op_id}: workflow trigger must be "
                            "form_submitted bound to a form operation")
        if op.get("kind") == OP_TEST_SUBMISSION:
            spec = op.get("spec") or {}
            if not spec.get("form_op") or not spec.get("workflow_op"):
                errs.append(f"{op_id}: test submission must name its "
                            "form and workflow operations")
    return errs


# ---------------------------------------------------------------------------
# Request builder (delegates every fact to the owning module)
# ---------------------------------------------------------------------------
def build_request(run_dir: Path, stage: str = "install",
                  env: Optional[dict] = None) -> Tuple[int, dict]:
    """Returns (exit_code, payload). On EXIT_OK the payload is the emitted
    request, or {"operations": [], "notes": [...]} when every election
    deferred or waived (no request file is written then). On a blocker the
    payload is {"blocker": {...}} and nothing is written."""
    env = dict(env or {})
    mods = _load_siblings()
    for name in ("sales_checkout_builder", "vsl_builder",
                 "checkout_form_builder", "ghl_external_installer"):
        if mods[name] is None:
            raise OpsError(f"sibling module unavailable: {name}.py")
    scb, vb, cfb, gx = (mods["sales_checkout_builder"], mods["vsl_builder"],
                        mods["checkout_form_builder"],
                        mods["ghl_external_installer"])
    intake = _read_json(run_dir / INTAKE_REL)
    if not intake:
        blocker = {"code": "MISSING_INPUT",
                   "detail": ("no run intake at " +
                              str(INTAKE_REL) + "; a ghl-ops-request "
                              "cannot bind to a run that does not exist")}
        _record_ledger(run_dir, {"event": "blocked", "stage": stage,
                                 "blocker": blocker, "at": _now_iso()})
        return EXIT_BLOCKED, {"blocker": blocker}
    scope, blocker = gx.resolve_scope(run_dir, intake, env=env)
    if blocker is not None or scope is None:
        _record_ledger(run_dir, {"event": "blocked", "stage": stage,
                                 "blocker": blocker, "at": _now_iso()})
        return EXIT_BLOCKED, {"blocker": blocker}

    sales_gate = scb.resolve_sales_checkout_gate(intake)
    vsl_gate = vb.resolve_vsl_gate(intake)
    gates = {"sales_checkout": sales_gate, "vsl": vsl_gate}
    for gate in gates.values():
        if gate.get("decision") == "fail_closed":
            _record_ledger(run_dir, {"event": "gate_fail_closed",
                                     "stage": stage, "gates": gates,
                                     "at": _now_iso()})
            return EXIT_GATE_BLOCKED, {"gates": gates}
    notes: List[str] = []
    operations: List[dict] = []
    if sales_gate.get("decision") == "build":
        ops, op_notes, blocker = _checkout_operations(run_dir, intake,
                                                      scope, mods)
        if blocker is not None:
            _record_ledger(run_dir, {"event": "blocked", "stage": stage,
                                     "blocker": blocker,
                                     "at": _now_iso()})
            return EXIT_BLOCKED, {"blocker": blocker}
        operations.extend(ops)
        notes.extend(op_notes)
    else:
        notes.append(f"checkout operations omitted: sales/checkout "
                     f"election is {sales_gate.get('decision')}")
    if vsl_gate.get("decision") == "build":
        operations.extend(_gate_operations(scope, mods))
    else:
        notes.append(f"gate form operations omitted: VSL election is "
                     f"{vsl_gate.get('decision')}")
    calendar_id = _resolve_calendar(intake)
    if calendar_id:
        operations.append(_calendar_op(calendar_id))
    else:
        notes.append("calendar operation omitted: the intake names no "
                     "booking calendar for the deck's CTA")
    if not operations:
        _record_ledger(run_dir, {"event": "no_operations", "stage": stage,
                                 "gates": gates, "notes": notes,
                                 "at": _now_iso()})
        return EXIT_OK, {"operations": [], "notes": notes, "gates": gates}

    prior = load_request(run_dir)
    version = 1
    if prior.get("request_id"):
        version = int(prior.get("request_version") or 1) + 1
    source_contracts: List[dict] = []
    input_hashes: Dict[str, str] = {}
    intake_hash = _sha256_file(run_dir / INTAKE_REL)
    if intake_hash:
        input_hashes["intake"] = intake_hash
    for rel in SOURCE_CONTRACT_RELS:
        candidate = run_dir / rel
        if candidate.exists():
            digest = _sha256_file(candidate)
            source_contracts.append({"path": str(rel), "sha256": digest})
            input_hashes[str(rel)] = digest
    request = {
        "schema": REQUEST_SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "request_id": _new_request_id(),
        "request_version": version,
        "stage": stage,
        "emitted_at": _now_iso(),
        "emitter": "scripts/ghl_ops.py (FIX-PLAN Item 33a seam)",
        "scope": scope,
        "executor": EXECUTOR_BLOCK,
        "gates": gates,
        "source_contracts": source_contracts,
        "input_hashes": input_hashes,
        "operations": operations,
        "notes": notes,
        "receipt_contract": {
            "path": str(RECEIPT_REL),
            "schema": RECEIPT_SCHEMA_NAME,
            "rule": ("every operation result must carry its verification "
                     "read-back; an entry claiming success without the "
                     "read-back is judged unverified, never success"),
        },
    }
    errors = validate_request(request)
    if errors:
        raise OpsValidationError(errors)
    _write_json_atomic(run_dir / REQUEST_REL, request)
    _record_ledger(run_dir, {"event": "emitted", "stage": stage,
                             "request_id": request["request_id"],
                             "request_version": version,
                             "operations": [o["op_id"]
                                            for o in operations],
                             "at": _now_iso()})
    return EXIT_OK, request


# ---------------------------------------------------------------------------
# Receipt judging (the reader; a claim is never a verdict)
# ---------------------------------------------------------------------------
def _check_map(readback: Any) -> Dict[str, dict]:
    """Normalize a receipt read-back into {check_name: entry}. Accepts the
    canonical list-of-{check, ok, observed} form or a dict keyed by check
    name. Anything else normalizes to empty (unproven)."""
    out: Dict[str, dict] = {}
    if isinstance(readback, list):
        for entry in readback:
            if isinstance(entry, dict) and entry.get("check"):
                out[str(entry["check"])] = entry
    elif isinstance(readback, dict):
        for name, value in readback.items():
            if isinstance(value, dict):
                out[str(name)] = value
            else:
                out[str(name)] = {"ok": bool(value), "observed": value}
    return out


def _judge_operation(op: dict, entry: Optional[dict]) -> dict:
    op_id = op.get("op_id")
    required = [e.get("check") for e in (op.get("expect") or [])
                if isinstance(e, dict) and e.get("check")]
    if entry is None:
        return {"op_id": op_id, "verdict": VERDICT_MISSING,
                "detail": "the receipt carries no result for this "
                          "operation"}
    claimed = str(entry.get("status_claimed") or "")
    remote = entry.get("remote") or {}
    object_id = remote.get("object_id") if isinstance(remote, dict) \
        else None
    checks = _check_map(entry.get("readback"))
    answered_ok = [c for c in required
                   if checks.get(c, {}).get("ok") is True]
    answered_bad = [c for c in required
                    if c in checks and checks[c].get("ok") is not True]
    unanswered = [c for c in required if c not in checks]
    base = {"op_id": op_id, "claimed": claimed,
            "checks_ok": answered_ok, "checks_failed": answered_bad,
            "checks_missing": unanswered}
    if claimed == CLAIM_FAILED:
        return {**base, "verdict": VERDICT_FAILED,
                "detail": entry.get("detail") or
                "the executor reported this operation failed"}
    if claimed in CLAIMS_SUCCESS:
        if checks == {} or entry.get("readback") in (None, [], {}):
            return {**base, "verdict": VERDICT_UNVERIFIED,
                    "detail": ("success claimed with NO verification "
                               "read-back; judged unverified, never "
                               "success (the seam's core rule)")}
        if not object_id:
            return {**base, "verdict": VERDICT_UNVERIFIED,
                    "detail": ("success claimed but the entry names no "
                               "remote object id; nothing to bind the "
                               "read-back to")}
        rb_object = checks.get(CHECK_OBJECT_EXISTS, {}).get("object_id")
        if rb_object and rb_object != object_id:
            return {**base, "verdict": VERDICT_UNVERIFIED,
                    "detail": ("the read-back's object id does not match "
                               "the result's remote object id")}
        if not unanswered and not answered_bad:
            return {**base, "verdict": VERDICT_VERIFIED,
                    "detail": "every required read-back check present "
                              "and ok"}
        if answered_ok:
            return {**base, "verdict": VERDICT_PARTIAL,
                    "detail": ("some read-back checks are proven; the "
                               "operation is not Wiring-Gate complete "
                               "until every named check answers ok")}
        return {**base, "verdict": VERDICT_UNVERIFIED,
                "detail": ("success claimed but no required read-back "
                           "check answers ok")}
    if claimed == CLAIM_PARTIAL:
        verdict = VERDICT_PARTIAL if answered_ok else VERDICT_UNVERIFIED
        return {**base, "verdict": verdict,
                "detail": entry.get("detail") or
                "the executor claims partial completion"}
    if claimed == CLAIM_SKIPPED:
        return {**base, "verdict": VERDICT_UNVERIFIED,
                "detail": ("the executor skipped this operation; a skip "
                           "is not wiring and is never judged done")}
    return {**base, "verdict": VERDICT_UNVERIFIED,
            "detail": f"unrecognized status_claimed {claimed!r}"}


def judge_receipt(run_dir: Path) -> Tuple[int, dict]:
    """Judge working/ghl/ghl-ops-receipt.json against the emitted
    request. Returns (exit_code, verdict). Absent receipt = pending
    (exit 0). A present receipt completes only when every operation in
    the CURRENT request judges verified."""
    request = load_request(run_dir)
    if not request.get("request_id"):
        verdict = {"overall": OVERALL_NO_REQUEST,
                   "detail": "no ghl-ops-request.json has been emitted "
                             "for this run; there is nothing to judge "
                             "a receipt against"}
        return EXIT_VERIFY_FAILED, verdict
    receipt_path = run_dir / RECEIPT_REL
    if not receipt_path.exists():
        verdict = {"overall": OVERALL_ABSENT,
                   "request_id": request.get("request_id"),
                   "detail": ("no ghl-ops-receipt.json: Skill 44 has "
                              "not returned a receipt for this request "
                              "(not available, or not yet executed). "
                              "Pending, never a failure and never a "
                              "pass; no operation is judged done.")}
        _record_ledger(run_dir, {"event": "judged", **verdict,
                                 "at": _now_iso()})
        return EXIT_OK, verdict
    receipt = load_receipt(run_dir)
    binding_errors: List[str] = []
    if receipt.get("schema") != RECEIPT_SCHEMA_NAME:
        binding_errors.append(f"receipt schema != {RECEIPT_SCHEMA_NAME!r}")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        binding_errors.append("receipt schema_version mismatch")
    if receipt.get("request_id") != request.get("request_id"):
        binding_errors.append("receipt answers a different request_id "
                              "(stale or foreign receipt)")
    if receipt.get("request_version") != request.get("request_version"):
        binding_errors.append("receipt answers a superseded "
                              "request_version (stale receipt)")
    rscope = receipt.get("scope") or {}
    for key in ("run_id", "deck_slug"):
        if rscope.get(key) != (request.get("scope") or {}).get(key):
            binding_errors.append(f"receipt scope.{key} does not match "
                                  "the request")
    expected_location = (request.get("scope") or {}).get("location_id")
    if expected_location not in (None, "", "unbound-test") and \
            rscope.get("location_id") != expected_location:
        binding_errors.append("receipt scope.location_id does not match "
                              "the bound location (WRONG_LOCATION)")
    results = receipt.get("results")
    if not isinstance(results, list):
        binding_errors.append("receipt results must be a list")
        results = []
    if binding_errors:
        verdict = {"overall": OVERALL_INVALID,
                   "request_id": request.get("request_id"),
                   "binding_errors": binding_errors,
                   "operations": [],
                   "detail": "the receipt does not bind to the current "
                             "request; nothing in it is judged"}
        _record_ledger(run_dir, {"event": "judged", **verdict,
                                 "at": _now_iso()})
        return EXIT_VERIFY_FAILED, verdict
    by_id: Dict[str, dict] = {}
    for entry in results:
        if isinstance(entry, dict) and entry.get("op_id"):
            by_id[str(entry["op_id"])] = entry
    op_verdicts = [_judge_operation(op, by_id.get(op.get("op_id")))
                   for op in (request.get("operations") or [])]
    verdicts = [v["verdict"] for v in op_verdicts]
    if all(v == VERDICT_VERIFIED for v in verdicts):
        overall = OVERALL_COMPLETE
    elif any(v == VERDICT_FAILED for v in verdicts):
        overall = OVERALL_FAILED
    elif any(v == VERDICT_VERIFIED for v in verdicts):
        overall = OVERALL_PARTIAL
    else:
        overall = OVERALL_UNVERIFIED
    verdict = {"overall": overall,
               "request_id": request.get("request_id"),
               "execution": receipt.get("execution") or {},
               "operations": op_verdicts,
               "detail": ("complete: every operation carries its "
                          "verification read-back and judges verified"
                          if overall == OVERALL_COMPLETE else
                          "not complete: see per-operation verdicts; "
                          "an entry without its read-back is unverified, "
                          "never success")}
    _record_ledger(run_dir, {"event": "judged", **verdict,
                             "at": _now_iso()})
    return (EXIT_OK if overall == OVERALL_COMPLETE
            else EXIT_VERIFY_FAILED), verdict


# ---------------------------------------------------------------------------
# Selftest (offline; fixture runs + fabricated receipts; no GHL, no caf)
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    failures: List[str] = []

    def check(cond: bool, label: str) -> None:
        if not cond:
            failures.append(label)

    def mk_run(base: Path, name: str, intake: dict) -> Path:
        run = base / name
        (run / "working" / "copy").mkdir(parents=True, exist_ok=True)
        (run / "working" / "checkpoints").mkdir(parents=True,
                                                exist_ok=True)
        (run / INTAKE_REL).write_text(json.dumps(intake),
                                      encoding="utf-8")
        return run

    def base_intake(**brief_over) -> dict:
        brief = {"OFFER_NAME": "Momentum Method", "FINAL_PRICE": "$997"}
        brief.update(brief_over)
        return {"deck_slug": "acme-ops", "company": "Acme Co",
                "GHL_LOCATION_ID": "loc-test-1",
                "pre_presentation_capture": {
                    "WANT_SALES_CHECKOUT": "yes", "WANT_VSL_PAGE": "yes"},
                "deck_brief": brief}

    def full_readback(op: dict, object_id: str) -> list:
        entries = []
        for e in op["expect"]:
            entry = {"check": e["check"], "ok": True,
                     "observed": "selftest"}
            if e["check"] == CHECK_OBJECT_EXISTS:
                entry["object_id"] = object_id
            entries.append(entry)
        return entries

    def receipt_for(request: dict, run_name: str, mutate=None) -> dict:
        results = []
        for op in request["operations"]:
            oid = f"obj-{op['op_id']}"
            claimed = "verified" if op["kind"] == OP_TEST_SUBMISSION \
                else "created"
            results.append({
                "op_id": op["op_id"], "kind": op["kind"],
                "status_claimed": claimed,
                "remote": {"object_id": oid},
                "readback": full_readback(op, oid),
            })
        receipt = {"schema": RECEIPT_SCHEMA_NAME,
                   "schema_version": SCHEMA_VERSION,
                   "request_id": request["request_id"],
                   "request_version": request["request_version"],
                   "scope": {"run_id": run_name, "deck_slug": "acme-ops",
                             "location_id": "loc-test-1"},
                   "execution": {"execution_id": "gx_selftest0001",
                                 "access_tier_used": "tier0_caf_firebase"},
                   "results": results}
        if mutate:
            receipt = mutate(receipt)
        return receipt

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        # A: lead capture, both families elected -> the standard op set.
        run = mk_run(base, "run-a", base_intake())
        code, req = build_request(run, "install")
        check(code == EXIT_OK, "A: emit exit 0")
        op_ids = [o["op_id"] for o in req.get("operations", [])]
        check(op_ids == ["checkout-form", "checkout-workflow",
                         "checkout-test-submission", "gate-form",
                         "gate-workflow", "gate-test-submission"],
              f"A: standard op set, got {op_ids}")
        check(validate_request(req) == [], "A: request validates")
        check((run / REQUEST_REL).exists(), "A: request file written")
        check(req["executor"]["rate_limit"]["daily_cap"] == 200000,
              "A: shared bucket named with its daily cap")
        # B: payment sandbox adds product + order-form binding ops.
        run_b = mk_run(base, "run-b",
                       base_intake(CHECKOUT_MODE="payment_sandbox"))
        code, req_b = build_request(run_b, "install")
        kinds_b = [o["kind"] for o in req_b.get("operations", [])]
        check(code == EXIT_OK and OP_PRODUCT in kinds_b
              and OP_ORDER_FORM in kinds_b, "B: sandbox ops present")
        # C: approved URL reuse omits the checkout family only.
        run_c = mk_run(base, "run-c", base_intake(
            APPROVED_CHECKOUT_URL="https://payments.acme-co.com/acme-ops"))
        code, req_c = build_request(run_c, "install")
        ids_c = [o["op_id"] for o in req_c.get("operations", [])]
        check(code == EXIT_OK and "checkout-form" not in ids_c
              and "gate-form" in ids_c, "C: reuse posture honored")
        # D: both elections waived with verbatim reasons -> no request.
        intake_d = base_intake()
        intake_d["pre_presentation_capture"] = {
            "WANT_SALES_CHECKOUT": "no",
            "SALES_CHECKOUT_DECLINED_REASON": "we sell on calls only",
            "WANT_VSL_PAGE": "no",
            "VSL_PAGE_DECLINED_REASON": "no video this launch"}
        run_d = mk_run(base, "run-d", intake_d)
        code, payload_d = build_request(run_d, "install")
        check(code == EXIT_OK and payload_d.get("operations") == []
              and not (run_d / REQUEST_REL).exists(),
              "D: waived elections emit no request")
        # E: VSL declined without a verbatim reason -> gate fail-closed.
        intake_e = base_intake()
        intake_e["pre_presentation_capture"] = {
            "WANT_SALES_CHECKOUT": "yes", "WANT_VSL_PAGE": "no"}
        run_e = mk_run(base, "run-e", intake_e)
        code, _ = build_request(run_e, "install")
        check(code == EXIT_GATE_BLOCKED, "E: fail-closed gate exit 3")
        # F: missing offer -> phase blocker, nothing written.
        intake_f = base_intake()
        del intake_f["deck_brief"]["OFFER_NAME"]
        run_f = mk_run(base, "run-f", intake_f)
        code, payload_f = build_request(run_f, "install")
        check(code == EXIT_BLOCKED
              and (payload_f.get("blocker") or {}).get("code")
              == "MISSING_OFFER", "F: MISSING_OFFER blocker exit 5")
        # G: judging on run A.
        code, verdict = judge_receipt(run)
        check(code == EXIT_OK and verdict["overall"] == OVERALL_ABSENT,
              "G1: absent receipt is pending, exit 0")
        good = receipt_for(req, "run-a")
        _write_json_atomic(run / RECEIPT_REL, good)
        code, verdict = judge_receipt(run)
        check(code == EXIT_OK and verdict["overall"] == OVERALL_COMPLETE,
              f"G2: complete receipt judges complete, "
              f"got {verdict['overall']}")
        def strip_one(r):
            for entry in r["results"]:
                if entry["op_id"] == "checkout-workflow":
                    entry.pop("readback")
            return r
        _write_json_atomic(run / RECEIPT_REL,
                           receipt_for(req, "run-a", strip_one))
        code, verdict = judge_receipt(run)
        by_id = {v["op_id"]: v for v in verdict["operations"]}
        check(code == EXIT_VERIFY_FAILED
              and by_id["checkout-workflow"]["verdict"]
              == VERDICT_UNVERIFIED
              and verdict["overall"] == OVERALL_PARTIAL,
              "G3: success claim without read-back judges unverified")
        def strip_all(r):
            for entry in r["results"]:
                entry.pop("readback")
            return r
        _write_json_atomic(run / RECEIPT_REL,
                           receipt_for(req, "run-a", strip_all))
        code, verdict = judge_receipt(run)
        check(verdict["overall"] == OVERALL_UNVERIFIED,
              "G4: no read-backs anywhere judges unverified overall")
        def fail_one(r):
            for entry in r["results"]:
                if entry["op_id"] == "gate-form":
                    entry["status_claimed"] = "failed"
                    entry["detail"] = "caf refused: name collision"
            return r
        _write_json_atomic(run / RECEIPT_REL,
                           receipt_for(req, "run-a", fail_one))
        code, verdict = judge_receipt(run)
        check(verdict["overall"] == OVERALL_FAILED,
              "G5: a failed operation fails the receipt")
        def stale(r):
            r["request_version"] = 99
            return r
        _write_json_atomic(run / RECEIPT_REL,
                           receipt_for(req, "run-a", stale))
        code, verdict = judge_receipt(run)
        check(verdict["overall"] == OVERALL_INVALID,
              "G6: stale request_version judges invalid")
        def wrong_location(r):
            r["scope"]["location_id"] = "loc-someone-else"
            return r
        _write_json_atomic(run / RECEIPT_REL,
                           receipt_for(req, "run-a", wrong_location))
        code, verdict = judge_receipt(run)
        check(verdict["overall"] == OVERALL_INVALID,
              "G7: wrong location judges invalid")
    if failures:
        print("ghl_ops selftest -> FAIL: " + "; ".join(failures))
        return 1
    print("ghl_ops selftest -> PASS (emit: standard op set lead + "
          "sandbox product/binding ops, approved-URL reuse, waived -> no "
          "request, fail-closed gate, MISSING_OFFER blocker; judge: "
          "absent pending, complete, no-read-back unverified, all-bare "
          "unverified, failed, stale invalid, wrong-location invalid)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ghl_ops.py",
        description="FIX-PLAN Item 33a seam: emit ghl-ops-request.json "
                    "for Skill 44, or judge the ghl-ops-receipt.json it "
                    "returns (a success claim without its verification "
                    "read-back judges unverified, never success).")
    p.add_argument("--run-dir", default=".",
                   help="presentation run directory")
    p.add_argument("--stage", default="install",
                   choices=("install", "delivery"),
                   help="request stage (default install)")
    p.add_argument("--judge", action="store_true",
                   help="judge the receipt against the emitted request "
                        "instead of emitting")
    p.add_argument("--selftest", action="store_true",
                   help="run the embedded offline selftest")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.selftest:
        return _selftest()
    run_dir = Path(args.run_dir).resolve()
    try:
        if args.judge:
            code, verdict = judge_receipt(run_dir)
            print(json.dumps(verdict, indent=2))
            return code
        code, payload = build_request(run_dir, args.stage)
        print(json.dumps(payload, indent=2))
        return code
    except OpsValidationError as exc:
        print(f"VALIDATION FAILED: {exc}", file=sys.stderr)
        return EXIT_VERIFY_FAILED
    except OpsError as exc:
        print(f"SEAM ERROR: {exc}", file=sys.stderr)
        return EXIT_BLOCKED


if __name__ == "__main__":
    sys.exit(main())

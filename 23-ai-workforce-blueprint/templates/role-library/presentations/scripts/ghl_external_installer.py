#!/usr/bin/env python3
"""
ghl_external_installer.py -- the P-U-GHL-SALES / P-U-GHL-VSL / P-U-FORM-GATE
real producer (PRES-011).

THE DEFECT (TODO PRES-011): P-U-FORM-GATE, P-U-GHL-SALES and P-U-GHL-VSL
declared executor.kind=agent, so the dispatcher authored their "completion"
by writing model text to one artifact file. A JSON-looking receipt with no
GHL form, workflow or page behind it passed the generic presence verifier.
Strengthening the gate alone would convert false completion into endless
retries -- this module fixes the executor in the same wave.

WHAT THIS MODULE IS (mirrors PRES-025 checkout_form_builder.py, the sibling
pattern for P-U-FORM-CHECKOUT -- same receipt discipline, same memory-adapter
proof shape, same blocker taxonomy):

  offer/plan derivation -> Skill 06 page-install / Skill 44 form-workflow
  contracts -> adapter execution (IDs) -> remote readback -> persisted
  receipt. Models may draft validated PLANS; only successful tool results can
  write execution receipts. A plan-emitted result is
  pending_external_execution, never complete.

THREE PHASES, TWO ADAPTER FAMILIES:

  P-U-GHL-SALES  (Skill 06 canonical page-install path):
      sales.html + checkout.html -> ONE funnel (funnel_create), TWO pages
      (step_create + page_autosave, the ghl_rest_canvas.py sequence the
      sales_checkout_builder push plan already emits). Receipt:
      working/sales-checkout/ghl_build_receipt.json.
  P-U-GHL-VSL    (Skill 06 canonical page-install path):
      vsl.html -> VSL page. Reuses the sales verified funnel_id when this
      run already pushed sales+checkout (mirrors
      vsl_builder.resolve_shared_funnel_id); otherwise its own funnel.
      Receipt: working/vsl/ghl_build_receipt.json.
  P-U-FORM-GATE  (Skill 44 supported form/workflow operations):
      vsl-gate-form-spec.json (SKILL44_WIDGET -> FORM: Email + First Name +
      Cell Phone custom fields, Form-Submitted -> zhc_vsl_engaged tag
      workflow, DRAFT-only) via `caf workflows build --from-plan` /
      ghl_workflow_builder.py managed-gateway harness. Receipts:
      ecosystem/gate-form.json + workflows/gate-workflow.json (TWO
      artifacts; resume handles the partial state of form-created but
      workflow-missing).

CANONICAL REFERENCES (never reimplemented here, only named in plans):

  * 06-ghl-install-pages/tools/ghl_rest_canvas.py -- funnel_create /
    step_create / page_autosave (REST step shapes; the Cloudflare-WAF-gated
    calls run inside a live agent-browser eval, exactly as the builders'
    push plans document).
  * 06-ghl-install-pages/tools/ghl_builder.py -- subaccount_matches
    (location hard gate), may_publish (DRAFT default), resume_point
    (never re-create an existing step).
  * 06-ghl-install-pages/tools/ghl_workflow_builder.py -- managed-gateway
    Automations builder harness (MissingGateError instead of invented
    selectors; workflow id read back from the builder URL).
  * 44-convert-and-flow-operator Skill 44 -- `caf workflows build
    --from-plan` (CampaignBuilder.build under WriteLock; existing workflow
    names refused into errors, never duplicated) + `caf workflows list` /
    `export` / `get` for readback.

SCOPE BINDING (TODO step 3): every operation and receipt carries deck_slug
(presentation), run_id, company (resolved client name), location_id,
input hashes, execution_id, timestamp and remote readback. Credentials
(PITs, Firebase tokens) NEVER enter artifacts -- only the non-secret
location_id travels. An intake-declared location disagreeing with the bound
location is WRONG_LOCATION and is refused (a cross-client write).

DURABLE STATES (TODO step 4): dispatched/running/remote-created/verified in
working/checkpoints/ghl_external_ops.json (merged, never clobbered).
Remote IDs are persisted IMMEDIATELY after creation, before the final
receipt -- a kill between creation and receipt resumes by reusing the
recorded remote ID (no duplicate) and continuing at the recorded
next_action. Live board/CEO progress flows through the engine's existing
reporter (script phases already emit start/done); phase-scoped blockers
land as actionable receipts with exit 5, never as deck failure.

USAGE
    python3 scripts/ghl_external_installer.py --run-dir <run_dir> --phase <id>
    python3 scripts/ghl_external_installer.py --selftest

    --phase     One of P-U-GHL-SALES, P-U-GHL-VSL, P-U-FORM-GATE.
    --selftest  Deterministic offline self-test (no network, no GHL call).
                Memory adapters stand in for Skill 06/44 -- proof only,
                never production.

EXIT CODES
    0 -- DEFERRED / WAIVED (gate), PLAN_EMITTED/pending_external_execution
         (offline contracts emitted, awaiting delegated Skill 06/44
         execution), or VERIFIED (an existing complete receipt re-validated,
         or memory/live adapters proved the contract -- tests only, never
         production).
    2 -- usage error.
    3 -- GATE BLOCKED (fail_closed, same as the page builders).
    4 -- VERIFY FAILED (bad receipt / stale inputs / readback mismatch).
    5 -- BLOCKED (WRONG_LOCATION / UNBOUND_LOCATION / MISSING_INPUT --
         this phase only, actionable detail).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_OK = 0
EXIT_BUILD_FAILED = 1
EXIT_USAGE = 2
EXIT_GATE_BLOCKED = 3
EXIT_VERIFY_FAILED = 4
EXIT_BLOCKED = 5

RECEIPT_SCHEMA = "1.0"

# The three external-effect phases this module owns (TODO PRES-011).
PHASE_GHL_SALES = "P-U-GHL-SALES"
PHASE_GHL_VSL = "P-U-GHL-VSL"
PHASE_FORM_GATE = "P-U-FORM-GATE"
EXTERNAL_PHASES = (PHASE_GHL_SALES, PHASE_GHL_VSL, PHASE_FORM_GATE)

# TODO step 1 -- explicit executor capabilities. External-effect phases must
# never be routed to a text-only writer.
CAP_TEXT_ARTIFACT = "text_artifact"
CAP_MULTI_ARTIFACT = "multi_artifact"
CAP_GHL_MEDIA_REST = "ghl_media_rest"
CAP_GHL_PAGE_INSTALL = "ghl_page_install"
CAP_GHL_WORKFLOW_INSTALL = "ghl_workflow_install"
ALL_CAPABILITIES = (
    CAP_TEXT_ARTIFACT, CAP_MULTI_ARTIFACT, CAP_GHL_MEDIA_REST,
    CAP_GHL_PAGE_INSTALL, CAP_GHL_WORKFLOW_INSTALL,
)
EXTERNAL_CAPABILITIES = (
    CAP_GHL_MEDIA_REST, CAP_GHL_PAGE_INSTALL, CAP_GHL_WORKFLOW_INSTALL,
)
TEXT_CAPABILITIES = (CAP_TEXT_ARTIFACT, CAP_MULTI_ARTIFACT)

# Default capability per external phase (a manifest executor.capability
# always wins over this map).
DEFAULT_CAPABILITY = {
    PHASE_GHL_SALES: CAP_GHL_PAGE_INSTALL,
    PHASE_GHL_VSL: CAP_GHL_PAGE_INSTALL,
    PHASE_FORM_GATE: CAP_GHL_WORKFLOW_INSTALL,
}
# Owning adapter family per phase (documentation + plan routing).
DEFAULT_ADAPTER = {
    PHASE_GHL_SALES: "skill06",
    PHASE_GHL_VSL: "skill06",
    PHASE_FORM_GATE: "skill44",
}

# Receipt locations (the manifest's produces_artifact for each phase).
RECEIPT_REL = {
    PHASE_GHL_SALES: Path("working") / "sales-checkout" / "ghl_build_receipt.json",
    PHASE_GHL_VSL: Path("working") / "vsl" / "ghl_build_receipt.json",
}
FORM_RECEIPT_REL = Path("ecosystem") / "gate-form.json"
WORKFLOW_RECEIPT_REL = Path("workflows") / "gate-workflow.json"

OPS_LEDGER_REL = Path("working") / "checkpoints" / "ghl_external_ops.json"
INTAKE_REL = Path("working") / "copy" / "intake.json"

# Phase-scoped blockers (this phase only; deck production continues).
BLOCK_WRONG_LOCATION = "WRONG_LOCATION"
BLOCK_UNBOUND_LOCATION = "UNBOUND_LOCATION"
BLOCK_MISSING_INPUT = "MISSING_INPUT"

# Pending state name (TODO step 4): a plan-emitted result is
# pending_external_execution, never complete.
STATUS_PENDING = "pending_external_execution"
STATUS_REMOTE_CREATED = "remote-created"
STATUS_VERIFIED = "verified"
STATUS_COMPLETE = "complete"
STATUS_BLOCKED = "blocked"

STATUSES_COMPLETE = (STATUS_VERIFIED, STATUS_COMPLETE)


def _here() -> Path:
    return Path(__file__).resolve().parent


def _sha256_file(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return ""


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_execution_id() -> str:
    return f"gx_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# TODO step 1 -- capability + preflight.
# ---------------------------------------------------------------------------
def capability_for_phase(phase_id: str, manifest_entry: Optional[dict] = None) -> str:
    """The executor capability for a manifest phase entry.

    An explicit executor.capability always wins. The three external phases
    default to their install capability; every other phase defaults to
    text_artifact (the dispatcher's model-text path).
    """
    entry = manifest_entry or {}
    ex = entry.get("executor") if isinstance(entry, dict) else None
    if isinstance(ex, dict) and ex.get("capability"):
        return str(ex["capability"])
    if phase_id in DEFAULT_CAPABILITY:
        return DEFAULT_CAPABILITY[phase_id]
    return CAP_TEXT_ARTIFACT


def is_external_phase(phase_id: str, phase_obj: Any = None,
                      order: Optional[dict] = None) -> bool:
    """True when this phase has external effects and must never be completed
    from model text. Accepts a Manifest Phase object, a raw manifest dict, or
    a dispatcher work-order dict -- whichever the caller holds."""
    if phase_id in EXTERNAL_PHASES:
        return True
    cap = None
    if phase_obj is not None:
        cap = getattr(phase_obj, "executor_capability", None)
        if cap is None and isinstance(phase_obj, dict):
            cap = (phase_obj.get("executor") or {}).get("capability")
    if cap is None and isinstance(order, dict):
        cap = ((order.get("executor") or {}).get("capability")
               if isinstance(order.get("executor"), dict) else None)
    return cap in EXTERNAL_CAPABILITIES


def preflight_check_phase(phase_id: str, manifest_entry: Optional[dict] = None) -> Tuple[bool, str]:
    """TODO step 1: reject external-effect phases routed to a text-only
    writer during preflight. Returns (ok, detail)."""
    entry = manifest_entry or {}
    ex = entry.get("executor") if isinstance(entry, dict) else None
    kind = (ex.get("kind") if isinstance(ex, dict) else None) or "agent"
    cap = capability_for_phase(phase_id, entry)
    if phase_id in EXTERNAL_PHASES or cap in EXTERNAL_CAPABILITIES:
        if kind == "agent" or cap in TEXT_CAPABILITIES:
            return False, (
                f"AF-EXTERNAL-TEXT-ROUTING: {phase_id} has external effects "
                f"(capability={cap}) but is routed to a text-only writer "
                f"(executor.kind={kind}). Model text cannot install GHL "
                "pages/forms/workflows -- wire a script executor with an "
                "install capability (ghl_external_installer.py) instead."
            )
        return True, f"{phase_id}: external capability {cap} on a {kind} executor -- routed correctly"
    return True, f"{phase_id}: capability {cap} -- no external routing constraint"


# ---------------------------------------------------------------------------
# Scope binding (TODO step 3). Mirrors checkout_form_builder.resolve_scope.
# ---------------------------------------------------------------------------
def _load_builders():
    here = str(_here())
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import sales_checkout_builder as scb  # noqa: E402
    except ImportError:
        scb = None  # type: ignore[assignment]
    try:
        import vsl_builder as vb  # noqa: E402
    except ImportError:
        vb = None  # type: ignore[assignment]
    return scb, vb


def resolve_gate(run_dir: Path, phase_id: str, intake: dict) -> Dict[str, Any]:
    """The SAME gate decision the page builders use (delegated, never
    re-derived): sales branch for P-U-GHL-SALES, VSL branch for P-U-GHL-VSL
    and P-U-FORM-GATE."""
    _scb, _vb = _load_builders()
    if phase_id == PHASE_GHL_SALES:
        if _scb is None:
            return {"decision": "fail_closed",
                    "detail": "sales_checkout_builder unavailable -- fail-closed, not a pass"}
        return _scb.resolve_sales_checkout_gate(intake)
    if _vb is None:
        return {"decision": "fail_closed",
                "detail": "vsl_builder unavailable -- fail-closed, not a pass"}
    return _vb.resolve_vsl_gate(intake)


def resolve_scope(run_dir: Path, intake: dict,
                  env: Optional[dict] = None) -> Tuple[Optional[dict], Optional[dict]]:
    """Bind company/presentation/run/location scope. WRONG_LOCATION is a
    phase-scoped blocker, never a silent default. Credentials never enter
    the scope -- only the non-secret location_id travels."""
    env = env if env is not None else os.environ
    deck_slug = str(intake.get("deck_slug") or run_dir.name).strip() or "presentation"
    brief = intake.get("deck_brief") if isinstance(intake.get("deck_brief"), dict) else {}
    company = ""
    for key in ("company", "business_name", "client_name", "name"):
        v = intake.get(key)
        if isinstance(v, str) and v.strip():
            company = v.strip()
            break
    if not company:
        v = brief.get("OFFER_NAME")
        company = str(v).strip() if isinstance(v, str) and v.strip() else deck_slug
    loc_env = ""
    for key in ("GOHIGHLEVEL_LOCATION_ID", "GHL_LOCATION_ID"):
        v = str(env.get(key, "") or "").strip().strip("'\"")
        if v:
            loc_env = v
            break
    loc_declared = ""
    for key in ("GHL_LOCATION_ID", "GOHIGHLEVEL_LOCATION_ID"):
        v = intake.get(key)
        if isinstance(v, str) and v.strip():
            loc_declared = v.strip()
            break
    if not loc_declared and isinstance(brief.get("MERCHANT_LOCATION_ID"), str):
        loc_declared = brief["MERCHANT_LOCATION_ID"].strip()
    if loc_declared and loc_env and loc_declared != loc_env:
        return None, {
            "code": BLOCK_WRONG_LOCATION,
            "detail": (f"intake-declared location {loc_declared!r} disagrees with "
                       f"the bound location {loc_env!r} -- a GHL install in the "
                       "wrong client location is a cross-client write and is refused."),
            "action": "fix the location binding (env) or the intake record, re-run",
        }
    location_id = loc_env or loc_declared
    return {
        "deck_slug": deck_slug,
        "run_id": run_dir.name,
        "company": company,
        "location_id": location_id or "unbound-test",
        "location_bound": bool(loc_env or loc_declared),
    }, None


# ---------------------------------------------------------------------------
# Plans (TODO step 2 -- models may draft these; plans never complete).
# Each plan names the CANONICAL Skill 06 / Skill 44 entry point, never a
# reimplemented REST shape.
# ---------------------------------------------------------------------------
def build_page_install_plan(*, phase_id: str, scope: dict, pages: List[dict],
                            funnel_name: str,
                            shared_funnel_id: Optional[str] = None) -> dict:
    """Delegated Skill 06 page-install plan: funnel_create once, then per
    page step_create + page_autosave (the ghl_rest_canvas.py sequence), run
    inside a live agent-browser eval like the builders' push plans."""
    seq: List[dict] = []
    step_no = 1
    if shared_funnel_id:
        seq.append({
            "step": step_no,
            "call": "reuse_funnel",
            "args": {"funnel_id": shared_funnel_id},
            "then": "verified sales push funnel -- no second funnel for one client",
        })
        step_no += 1
    else:
        seq.append({
            "step": step_no,
            "call": "ghl_rest_canvas.funnel_create",
            "args": {"location_id": scope["location_id"], "name": funnel_name,
                     "funnel_type": "funnel"},
            "then": "run the eval; parse response body.id -> FUNNEL_ID",
        })
        step_no += 1
    for pg in pages:
        key = pg["key"].upper().replace("-", "_")
        seq.append({
            "step": step_no,
            "call": "ghl_rest_canvas.step_create",
            "args": {"funnel_id": "FUNNEL_ID", "name": pg["name"],
                     "slug": pg["slug"]},
            "then": f"run the eval; created_page_id(response) -> {key}_PAGE_ID",
        })
        step_no += 1
        seq.append({
            "step": step_no,
            "call": "ghl_rest_canvas.page_autosave",
            "args": {"page_id": f"{key}_PAGE_ID", "funnel_id": "FUNNEL_ID",
                     "page_version": 1,
                     "page_data": f"<{pg['key']} page blob built at execution "
                                  "time via ghl_rest_canvas.new_page_blob>"},
            "then": "run the eval; expect 201; live pointer unchanged (draft)",
        })
        step_no += 1
    return {
        "plan_version": "1.0",
        "phase": phase_id,
        "skill": "06-ghl-install-pages",
        "entry_points": [
            "06-ghl-install-pages/tools/ghl_rest_canvas.py "
            "(funnel_create/step_create/page_autosave/created_page_id)",
            "06-ghl-install-pages/tools/ghl_builder.py "
            "(subaccount_matches location gate, may_publish draft default, "
            "resume_point never-recreate)",
        ],
        "guards": [
            "subaccount_matches(live_location, scope.location_id) must pass "
            "before ANY write (NO-COMINGLING)",
            "may_publish: DRAFT only unless an owner approval record exists",
            "resume_point: never re-create a step that already exists",
        ],
        "scope": {k: scope.get(k) for k in
                  ("deck_slug", "run_id", "company", "location_id")},
        "funnel_name": funnel_name,
        "shared_funnel_id": shared_funnel_id,
        "pages": pages,
        "sequence": seq,
        "receipt_note": ("The executing agent writes the resulting funnel_id + "
                         "page_ids into the phase receipt; only adapter tool "
                         "results complete this phase."),
    }


def build_gate_form_plan(*, scope: dict, fields: Optional[List[dict]] = None,
                         form_fields: Optional[List[dict]] = None) -> dict:
    """Delegated Skill 44 gate form+workflow plan per vsl-gate-form-spec.json
    (SKILL44_WIDGET -> FORM, DRAFT-only workflow)."""
    form_fields = fields if fields is not None else form_fields
    if form_fields is None:
        form_fields = gate_form_fields()
    slug = scope["deck_slug"]
    form_name = f"ZHC {slug} VSL Gate"
    workflow_name = f"ZHC {slug} VSL Gate Engaged"
    return {
        "plan_version": "1.0",
        "phase": PHASE_FORM_GATE,
        "skill": "44-convert-and-flow-operator",
        "entry_points": [
            "caf workflows build --from-plan <plan.json> --folder "
            f"{workflow_name!r} (CampaignBuilder.build under WriteLock; "
            "existing names refused, never duplicated)",
            "06-ghl-install-pages/tools/ghl_workflow_builder.py "
            "(Tier-4 managed-gateway harness; MissingGateError instead of "
            "invented selectors; workflow id read back from builder URL)",
            "caf workflows list / export / get (readback)",
        ],
        "guards": [
            "PLAN MODE + Step 0.7 pre-build existence check before any build",
            "workflows created as DRAFT, never auto-published",
            "location whitelist: build only on scope.location_id",
        ],
        "scope": {k: scope.get(k) for k in
                  ("deck_slug", "run_id", "company", "location_id")},
        "form": {
            "name": form_name,
            "mechanism": "SKILL44_WIDGET -> FORM",
            "start_from": "scratch",
            "fields": form_fields,
            "embed_target": {
                "type": "website",
                "note": "Skill 6 resolves the gate overlay div; the embed "
                        "snippet splices VERBATIM, no SRI attrs.",
            },
        },
        "workflow": {
            "name": workflow_name,
            "trigger": {"type": "form_submitted",
                        "filter": {"form": "<this gate form -- bound AFTER creation>"}},
            "steps": [
                {"id": "s1", "type": "add_contact_tag",
                 "attributes": {"tags": ["zhc_vsl_engaged"]}},
            ],
            "draft_only": True,
        },
        "receipt_note": ("The executing agent writes the resulting form_id + "
                         "workflow_id into ecosystem/gate-form.json and "
                         "workflows/gate-workflow.json; only adapter tool "
                         "results complete this phase."),
    }


def gate_form_fields() -> List[dict]:
    """The vsl-gate-form-spec.json field contract (email + first name + cell)."""
    return [
        {"field_key": "zhc_vsl_email", "label": "Email", "element": "Email",
         "field_type": "single_line", "required": True, "validate": "email",
         "merge_token": "{{contact.zhc_vsl_email}}"},
        {"field_key": "zhc_vsl_first_name", "label": "First Name",
         "element": "Single Line", "field_type": "single_line",
         "required": True,
         "merge_token": "{{contact.zhc_vsl_first_name}}"},
        {"field_key": "zhc_vsl_phone", "label": "Cell Phone", "element": "Phone",
         "field_type": "single_line", "required": True, "validate": "phone",
         "merge_token": "{{contact.zhc_vsl_phone}}"},
    ]


# ---------------------------------------------------------------------------
# Adapters (TODO step 2 -- client-scoped; only successful tool results write
# execution receipts). Memory fakes are proof-only, never production.
# ---------------------------------------------------------------------------
class PageInstallAdapter:
    """Protocol: Skill 06 canonical authenticated page-install path."""

    def create_funnel(self, plan: dict) -> str:
        raise NotImplementedError

    def install_page(self, funnel_id: str, page: dict) -> str:
        raise NotImplementedError

    def readback_page(self, page_id: str) -> dict:
        raise NotImplementedError


class GateFormAdapter:
    """Protocol: Skill 44 supported form/workflow operations."""

    def create_form(self, contract: dict) -> str:
        raise NotImplementedError

    def create_workflow(self, contract: dict, form_id: str) -> str:
        raise NotImplementedError

    def readback_form(self, form_id: str) -> dict:
        raise NotImplementedError

    def readback_workflow(self, workflow_id: str) -> dict:
        raise NotImplementedError


class MemoryPageAdapter(PageInstallAdapter):
    """In-memory Skill 06 stand-in: location-scoped funnels + pages with
    readback. For proof only."""

    def __init__(self, location_id: str):
        self.location_id = location_id
        self.funnels: Dict[str, dict] = {}
        self.pages: Dict[str, dict] = {}
        self.calls: List[str] = []
        self._n = 0

    def _new_id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_mem_{self._n:04d}"

    def _check_scope(self, scope: dict) -> None:
        loc = (scope or {}).get("location_id", "")
        if loc != self.location_id:
            raise ValueError(f"WRONG_LOCATION: plan scope {loc!r} != "
                             f"adapter location {self.location_id!r}")

    def create_funnel(self, plan: dict) -> str:
        self.calls.append("create_funnel")
        self._check_scope(plan.get("scope") or {})
        fid = self._new_id("funnel")
        self.funnels[fid] = {"plan": plan, "location_id": self.location_id,
                             "pages": []}
        return fid

    def install_page(self, funnel_id: str, page: dict) -> str:
        self.calls.append("install_page")
        if funnel_id not in self.funnels:
            raise ValueError(f"unknown funnel {funnel_id!r}")
        pid = self._new_id("page")
        self.pages[pid] = {"funnel_id": funnel_id, "page": dict(page),
                           "location_id": self.location_id, "version": 1,
                           "draft": True}
        self.funnels[funnel_id]["pages"].append(pid)
        return pid

    def readback_page(self, page_id: str) -> dict:
        self.calls.append("readback_page")
        rec = self.pages.get(page_id)
        if rec is None:
            raise ValueError(f"unknown page {page_id!r}")
        return {"page_id": page_id, "funnel_id": rec["funnel_id"],
                "location_id": rec["location_id"], "version": rec["version"],
                "draft": rec["draft"],
                "slug": rec["page"].get("slug")}


class MemoryGateAdapter(GateFormAdapter):
    """In-memory Skill 44 stand-in: location-scoped forms + workflows with
    readback. For proof only."""

    def __init__(self, location_id: str):
        self.location_id = location_id
        self.forms: Dict[str, dict] = {}
        self.workflows: Dict[str, dict] = {}
        self.calls: List[str] = []
        self._n = 0

    def _new_id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_mem_{self._n:04d}"

    def create_form(self, contract: dict) -> str:
        self.calls.append("create_form")
        loc = ((contract.get("scope") or {}).get("location_id", "")
               or (contract.get("form") or {}).get("location_id", ""))
        if loc != self.location_id:
            raise ValueError(f"WRONG_LOCATION: contract scope {loc!r} != "
                             f"adapter location {self.location_id!r}")
        fields = (contract.get("form") or {}).get("fields") or []
        keys = {f.get("field_key") for f in fields if isinstance(f, dict)}
        if not {"zhc_vsl_email", "zhc_vsl_first_name",
                "zhc_vsl_phone"} <= keys:
            raise ValueError("gate form contract missing required fields "
                             "(zhc_vsl_email/first_name/phone)")
        fid = self._new_id("form")
        self.forms[fid] = {"contract": contract,
                           "location_id": self.location_id}
        return fid

    def create_workflow(self, contract: dict, form_id: str) -> str:
        self.calls.append("create_workflow")
        if form_id not in self.forms:
            raise ValueError(f"unknown form {form_id!r}")
        if ((contract.get("scope") or {}).get("location_id", "")
                != self.location_id):
            raise ValueError("WRONG_LOCATION: workflow scope != adapter location")
        wid = self._new_id("wf")
        self.workflows[wid] = {"form_id": form_id,
                               "location_id": self.location_id,
                               "draft": True}
        return wid

    def readback_form(self, form_id: str) -> dict:
        self.calls.append("readback_form")
        rec = self.forms.get(form_id)
        if rec is None:
            raise ValueError(f"unknown form {form_id!r}")
        wf_ids = [w for w, r in self.workflows.items()
                  if r["form_id"] == form_id]
        return {"form_id": form_id, "location_id": rec["location_id"],
                "workflow_ids": wf_ids, "http": 200}

    def readback_workflow(self, workflow_id: str) -> dict:
        self.calls.append("readback_workflow")
        rec = self.workflows.get(workflow_id)
        if rec is None:
            raise ValueError(f"unknown workflow {workflow_id!r}")
        return {"workflow_id": workflow_id, "form_id": rec["form_id"],
                "location_id": rec["location_id"], "draft": rec["draft"],
                "http": 200}


# ---------------------------------------------------------------------------
# Durable ops ledger + receipts (TODO step 4).
# ---------------------------------------------------------------------------
def _read_json(p: Path) -> dict:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_atomic(p: Path, obj: dict) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def load_ops(run_dir: Path) -> dict:
    return _read_json(run_dir / OPS_LEDGER_REL)


def record_ops(run_dir: Path, phase_id: str, record: dict) -> dict:
    """Merge one phase's ops record into the durable ledger (never
    clobbered). Remote IDs land here IMMEDIATELY after creation -- before
    the final receipt -- so a kill resumes without duplicates."""
    ops = load_ops(run_dir)
    cur = ops.get(phase_id) if isinstance(ops.get(phase_id), dict) else {}
    cur.update(record)
    cur["updated_at"] = _now_iso()
    ops[phase_id] = cur
    _write_json_atomic(run_dir / OPS_LEDGER_REL, ops)
    return cur


def receipt_paths(run_dir: Path, phase_id: str) -> List[Path]:
    if phase_id == PHASE_FORM_GATE:
        return [run_dir / FORM_RECEIPT_REL, run_dir / WORKFLOW_RECEIPT_REL]
    rel = RECEIPT_REL[phase_id]
    return [run_dir / rel]


def load_receipt(run_dir: Path, phase_id: str) -> dict:
    """The phase's primary receipt (gate-form.json for the gate pair)."""
    return _read_json(receipt_paths(run_dir, phase_id)[0])


def _input_files(run_dir: Path, phase_id: str) -> List[Path]:
    if phase_id == PHASE_GHL_SALES:
        return [run_dir / "working" / "sales-checkout" / "html" / "sales.html",
                run_dir / "working" / "sales-checkout" / "html" / "checkout.html"]
    if phase_id == PHASE_GHL_VSL:
        return [run_dir / "working" / "vsl" / "html" / "vsl.html"]
    return [run_dir / "working" / "vsl" / "html" / "vsl.html"]


def input_hashes(run_dir: Path, phase_id: str) -> Dict[str, str]:
    out = {}
    for p in _input_files(run_dir, phase_id):
        try:
            rel = str(p.relative_to(run_dir))
        except ValueError:
            rel = p.name
        out[rel] = _sha256_file(p)
    out["intake"] = _sha256_file(run_dir / INTAKE_REL)
    return out


# ---------------------------------------------------------------------------
# Receipt validation (TODO steps 2-3 -- what the verifiers call). A
# perfect-looking model receipt with no adapter IDs and no readback is
# pending_external_execution, never complete.
# ---------------------------------------------------------------------------
def validate_receipt(run_dir: Path, phase_id: str,
                     env: Optional[dict] = None) -> Tuple[bool, str, dict]:
    """Returns (complete, detail, data). complete=True ONLY when adapter
    remote IDs plus a matching-location readback prove the install."""
    paths = receipt_paths(run_dir, phase_id)
    data = _read_json(paths[0])
    if not data:
        return False, (f"{phase_id}: no receipt at "
                       f"{paths[0].relative_to(run_dir) if paths[0].is_relative_to(run_dir) else paths[0]} "
                       "-- pending_external_execution"), {}
    if not isinstance(data, dict):
        return False, f"{phase_id}: receipt is not a JSON object", {}
    if data.get("schema_version") != RECEIPT_SCHEMA:
        return False, (f"{phase_id}: receipt schema_version "
                       f"{data.get('schema_version')!r} != {RECEIPT_SCHEMA!r}"), data
    status = data.get("status")
    if status == STATUS_PENDING:
        return False, (f"{phase_id}: receipt is pending_external_execution "
                       "-- a plan was emitted, no tool result yet"), data
    scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
    if scope.get("run_id") and scope["run_id"] != run_dir.name:
        return False, (f"{phase_id}: receipt run_id {scope['run_id']!r} != "
                       f"this run {run_dir.name!r} (stale/foreign receipt)"), data
    # Location binding: a receipt bound to a DIFFERENT location than this
    # box's bound location is a cross-client artifact -- refuse.
    env = env if env is not None else os.environ
    bound = ""
    for key in ("GOHIGHLEVEL_LOCATION_ID", "GHL_LOCATION_ID"):
        v = str(env.get(key, "") or "").strip().strip("'\"")
        if v:
            bound = v
            break
    if bound and scope.get("location_id") and scope["location_id"] not in (
            bound, "unbound-test"):
        return False, (f"{phase_id}: receipt location {scope['location_id']!r} "
                       f"!= bound location {bound!r} (WRONG_LOCATION)"), data
    remote = data.get("remote") if isinstance(data.get("remote"), dict) else {}
    readback = data.get("readback") if isinstance(data.get("readback"), dict) else {}
    # Provenance: the receipt must trace to a real adapter execution in THIS
    # run's durable ops ledger (same execution_id + same remote IDs). A
    # model-fabricated receipt -- however perfect-looking -- has no such
    # entry and can never complete (QC check 1).
    ops = load_ops(run_dir).get(phase_id) or {}
    ops_remote = ops.get("remote") if isinstance(ops.get("remote"), dict) else {}
    ops_exec = ops.get("execution_id")
    rec_exec = (data.get("execution") or {}).get("execution_id") \
        if isinstance(data.get("execution"), dict) else None
    if ops.get("status") not in (STATUS_REMOTE_CREATED, STATUS_VERIFIED,
                                 "done") or not ops_exec or ops_exec != rec_exec:
        return False, (f"{phase_id}: receipt has no matching adapter execution "
                       "in this run's ops ledger (no recorded remote-created/verified "
                       "entry with the same execution_id) -- model text cannot "
                       "complete this phase"), data
    if phase_id == PHASE_FORM_GATE:
        return _validate_gate_receipts(run_dir, data, scope, bound, ops_remote)
    # Page phases: funnel + page IDs plus a readback proving them.
    funnel_id = remote.get("funnel_id")
    page_ids = [v for k, v in remote.items()
                if k.endswith("_page_id") and v]
    if not funnel_id or not page_ids:
        return False, (f"{phase_id}: receipt carries no adapter remote IDs "
                       "(funnel_id/page_ids) -- model text cannot complete "
                       "this phase"), data
    if not readback.get("ok"):
        return False, (f"{phase_id}: receipt carries remote IDs but no "
                       "successful remote readback -- unverified"), data
    rb_pages = readback.get("pages") if isinstance(readback.get("pages"), dict) else {}
    missing_rb = [p for p in page_ids if p not in rb_pages]
    if missing_rb:
        return False, (f"{phase_id}: readback missing pages {missing_rb}"), data
    for pid in page_ids:
        if rb_pages[pid].get("location_id") not in (
                scope.get("location_id"), bound, "unbound-test", None, "") \
                and scope.get("location_id") != rb_pages[pid].get("location_id"):
            return False, (f"{phase_id}: readback location mismatch on {pid}"), data
    # Ledger agreement: the receipt's remote IDs must equal the ops ledger's
    # recorded IDs. A receipt naming IDs the ledger never recorded is
    # fabricated, even when the execution_id matches.
    for key in ("funnel_id", *[f"{pg}_page_id" for pg in ("sales", "checkout", "vsl")]):
        if remote.get(key) and ops_remote.get(key) and remote[key] != ops_remote[key]:
            return False, (f"{phase_id}: receipt {key} {remote[key]!r} != ops "
                           f"ledger {ops_remote[key]!r} -- fabricated"), data
    # Input freshness: inputs changed since the install need a re-install.
    recorded = data.get("input_hashes") if isinstance(
        data.get("input_hashes"), dict) else {}
    if recorded:
        current = input_hashes(run_dir, phase_id)
        stale = [k for k, v in recorded.items()
                 if v and current.get(k) and current[k] != v]
        if stale:
            return False, (f"{phase_id}: inputs changed since install "
                           f"(stale: {stale}) -- re-install required"), data
    else:
        # No input hashes at all: the receipt cannot prove it was built from
        # THIS run's inputs -- a model-fabricated receipt never records them.
        return False, (f"{phase_id}: receipt records no input hashes -- "
                       "unbound to this run's inputs"), data
    return True, (f"{phase_id}: verified install (funnel {funnel_id}, "
                  f"{len(page_ids)} page(s), readback ok)"), data


def _validate_gate_receipts(run_dir: Path, data: dict, scope: dict,
                            bound: str,
                            ops_remote: Optional[dict] = None) -> Tuple[bool, str, dict]:
    """P-U-FORM-GATE: BOTH receipts required, each with IDs + readback."""
    wf_data = _read_json(receipt_paths(run_dir, PHASE_FORM_GATE)[1])
    form = data.get("form") if isinstance(data.get("form"), dict) else {}
    workflow = (wf_data.get("workflow") if isinstance(wf_data.get("workflow"), dict)
                else data.get("workflow") if isinstance(data.get("workflow"), dict)
                else {})
    form_id = form.get("form_id")
    workflow_id = workflow.get("workflow_id")
    if not form_id:
        return False, (f"{PHASE_FORM_GATE}: gate-form.json carries no adapter "
                       "form_id -- model text cannot complete this phase"), data
    if not workflow_id:
        return False, (f"{PHASE_FORM_GATE}: gate-workflow.json carries no adapter "
                       "workflow_id -- model text cannot complete this phase"), data
    readback = data.get("readback") if isinstance(data.get("readback"), dict) else {}
    if not readback.get("ok"):
        return False, (f"{PHASE_FORM_GATE}: receipts carry IDs but no "
                       "successful remote readback -- unverified"), data
    rb_form = readback.get("form") if isinstance(readback.get("form"), dict) else {}
    rb_wf = readback.get("workflow") if isinstance(readback.get("workflow"), dict) else {}
    if rb_form.get("form_id") != form_id:
        return False, (f"{PHASE_FORM_GATE}: form readback does not match {form_id}"), data
    if rb_wf.get("workflow_id") != workflow_id:
        return False, (f"{PHASE_FORM_GATE}: workflow readback does not match "
                       f"{workflow_id}"), data
    for label, rb in (("form", rb_form), ("workflow", rb_wf)):
        loc = rb.get("location_id")
        if loc and scope.get("location_id") and loc != scope["location_id"]:
            return False, (f"{PHASE_FORM_GATE}: {label} readback location "
                           f"{loc!r} != receipt scope {scope['location_id']!r}"), data
    ops_remote = ops_remote or {}
    for key, val in (("form_id", form_id), ("workflow_id", workflow_id)):
        if ops_remote.get(key) and val != ops_remote[key]:
            return False, (f"{PHASE_FORM_GATE}: receipt {key} {val!r} != ops "
                           f"ledger {ops_remote[key]!r} -- fabricated"), data
    recorded = data.get("input_hashes") if isinstance(
        data.get("input_hashes"), dict) else {}
    if not recorded:
        return False, (f"{PHASE_FORM_GATE}: receipt records no input hashes -- "
                       "unbound to this run's inputs"), data
    return True, (f"{PHASE_FORM_GATE}: verified gate form {form_id} + workflow "
                  f"{workflow_id} (readback ok)"), data


# ---------------------------------------------------------------------------
# Execution with adapters (TODO steps 2+4). Resume reuses recorded remote
# IDs -- it never creates a duplicate.
# ---------------------------------------------------------------------------
def shared_funnel_id(run_dir: Path) -> Optional[str]:
    """This run's verified sales funnel, when P-U-GHL-SALES already proved
    one (mirrors vsl_builder.resolve_shared_funnel_id)."""
    ok, _detail, data = validate_receipt(run_dir, PHASE_GHL_SALES)
    if not ok:
        return None
    remote = data.get("remote") if isinstance(data.get("remote"), dict) else {}
    fid = remote.get("funnel_id")
    return str(fid) if fid else None


def execute_phase(run_dir: Path, phase_id: str, *,
                  page_adapter: Optional[PageInstallAdapter] = None,
                  gate_adapter: Optional[GateFormAdapter] = None,
                  env: Optional[dict] = None) -> Tuple[int, dict]:
    """Run one external phase through its client-scoped adapter with durable
    resume. Returns (exit_code, receipt-or-plan)."""
    run_dir = run_dir.resolve()
    try:
        intake = json.loads((run_dir / INTAKE_REL).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        intake = {}
    if not isinstance(intake, dict):
        intake = {}

    gate = resolve_gate(run_dir, phase_id, intake)
    decision = gate.get("decision")
    if decision == "defer":
        record_ops(run_dir, phase_id, {"status": "deferred", "gate": gate})
        return EXIT_OK, {"status": "deferred", "gate": gate}
    if decision == "waived":
        record_ops(run_dir, phase_id, {"status": "waived", "gate": gate})
        return EXIT_OK, {"status": "waived", "gate": gate}
    if decision == "fail_closed":
        record_ops(run_dir, phase_id, {"status": "fail_closed", "gate": gate})
        print(f"FATAL: {gate['detail']}", file=sys.stderr)
        return EXIT_GATE_BLOCKED, {"status": "fail_closed", "gate": gate}
    if decision != "build":
        record_ops(run_dir, phase_id,
                   {"status": "fail_closed", "gate": gate})
        print(f"FATAL: unrecognized gate decision {decision!r}",
              file=sys.stderr)
        return EXIT_GATE_BLOCKED, {"status": "fail_closed", "gate": gate}

    scope, blocker = resolve_scope(run_dir, intake, env=env)
    if blocker is not None:
        receipt = _blocked_receipt(run_dir, phase_id, intake, blocker, gate)
        _write_receipts(run_dir, phase_id, receipt)
        record_ops(run_dir, phase_id, {"status": STATUS_BLOCKED,
                                       "blocker": blocker, "gate": gate})
        print(f"BLOCKED [{blocker['code']}]: {blocker['detail']}",
              file=sys.stderr)
        print(f"ACTION: {blocker['action']}", file=sys.stderr)
        return EXIT_BLOCKED, receipt
    assert scope is not None

    if not scope["location_bound"]:
        # Offline/test runs bind explicitly via adapters; a live delegated
        # run with no bound location cannot prove client binding -- the plan
        # is still emitted (bound at execution time), honestly pending.
        pass

    if phase_id in (PHASE_GHL_SALES, PHASE_GHL_VSL):
        if page_adapter is None:
            return _emit_page_plan(run_dir, phase_id, intake, scope, gate)
        return _execute_pages(run_dir, phase_id, intake, scope, gate,
                              page_adapter)
    if gate_adapter is None:
        return _emit_gate_plan(run_dir, intake, scope, gate)
    return _execute_gate(run_dir, intake, scope, gate, gate_adapter)


def _blocked_receipt(run_dir: Path, phase_id: str, intake: dict,
                     blocker: dict, gate: dict) -> dict:
    return {
        "schema_version": RECEIPT_SCHEMA,
        "phase": phase_id,
        "deck_slug": str(intake.get("deck_slug") or run_dir.name),
        "run_id": run_dir.name,
        "scope": {"deck_slug": str(intake.get("deck_slug") or run_dir.name),
                  "run_id": run_dir.name,
                  "company": "", "location_id": None},
        "input_hashes": input_hashes(run_dir, phase_id),
        "execution": {"execution_id": _new_execution_id(),
                      "started_at": _now_iso(), "adapter": None},
        "remote": {},
        "readback": {"ok": False},
        "status": STATUS_BLOCKED,
        "blocker": blocker,
        "proof": None,
        "built_at": _now_iso(),
    }


def _write_receipts(run_dir: Path, phase_id: str, receipt: dict) -> List[Path]:
    out = []
    if phase_id == PHASE_FORM_GATE:
        form_rec = dict(receipt)
        wf_rec = dict(receipt)
        wf_rec["artifact"] = "workflows/gate-workflow.json"
        form_rec["artifact"] = "ecosystem/gate-form.json"
        out.append(_write_json_atomic(receipt_paths(run_dir, phase_id)[0], form_rec))
        out.append(_write_json_atomic(receipt_paths(run_dir, phase_id)[1], wf_rec))
        return out
    out.append(_write_json_atomic(receipt_paths(run_dir, phase_id)[0], receipt))
    return out


def _page_specs(run_dir: Path, phase_id: str, scope: dict) -> Tuple[str, List[dict]]:
    slug = scope["deck_slug"]
    if phase_id == PHASE_GHL_SALES:
        return (f"{scope['company']} -- Sales/Checkout", [
            {"key": "sales", "name": f"{scope['company']} -- Sales",
             "slug": f"{slug}-sales",
             "source": "working/sales-checkout/html/sales.html"},
            {"key": "checkout", "name": f"{scope['company']} -- Checkout",
             "slug": f"{slug}-checkout",
             "source": "working/sales-checkout/html/checkout.html"},
        ])
    return (f"{scope['company']} -- VSL", [
        {"key": "vsl", "name": f"{scope['company']} -- VSL",
         "slug": f"{slug}-vsl",
         "source": "working/vsl/html/vsl.html"},
    ])


def _missing_inputs(run_dir: Path, phase_id: str) -> List[str]:
    missing = []
    for p in _input_files(run_dir, phase_id):
        if not p.is_file() or p.stat().st_size < 200:
            try:
                rel = str(p.relative_to(run_dir))
            except ValueError:
                rel = p.name
            missing.append(rel)
    return missing


def _emit_page_plan(run_dir: Path, phase_id: str, intake: dict,
                    scope: dict, gate: dict) -> Tuple[int, dict]:
    """No adapter in this process (production delegated path): emit the
    Skill 06 plan + a pending_external_execution receipt. Never complete."""
    missing = _missing_inputs(run_dir, phase_id)
    if missing:
        blocker = {"code": BLOCK_MISSING_INPUT,
                   "detail": (f"page HTML missing/too small: {missing} -- "
                              "the page builders must run first"),
                   "action": "run the page-builder phases, then re-run"}
        receipt = _blocked_receipt(run_dir, phase_id, intake, blocker, gate)
        _write_receipts(run_dir, phase_id, receipt)
        record_ops(run_dir, phase_id, {"status": STATUS_BLOCKED,
                                       "blocker": blocker})
        return EXIT_BLOCKED, receipt
    funnel_name, pages = _page_specs(run_dir, phase_id, scope)
    shared = shared_funnel_id(run_dir) if phase_id == PHASE_GHL_VSL else None
    plan = build_page_install_plan(phase_id=phase_id, scope=scope,
                                   pages=pages, funnel_name=funnel_name,
                                   shared_funnel_id=shared)
    plan_dir = run_dir / (Path("working") / "sales-checkout"
                          if phase_id == PHASE_GHL_SALES
                          else Path("working") / "vsl")
    plan_path = plan_dir / "ghl_install_plan.json"
    _write_json_atomic(plan_path, plan)
    # Preserve already-recorded remote IDs across re-runs (resume honesty:
    # never overwrite proven IDs with a pending shell).
    prior = load_receipt(run_dir, phase_id)
    prior_remote = prior.get("remote") if isinstance(prior, dict) else None
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "phase": phase_id,
        "deck_slug": scope["deck_slug"],
        "run_id": scope["run_id"],
        "scope": {k: scope.get(k) for k in
                  ("deck_slug", "run_id", "company", "location_id")},
        "input_hashes": input_hashes(run_dir, phase_id),
        "execution": {"execution_id": _new_execution_id(),
                      "started_at": _now_iso(), "adapter": "skill06-delegated"},
        "remote": prior_remote if isinstance(prior_remote, dict) else {},
        "readback": (prior.get("readback") if isinstance(prior, dict)
                     else {"ok": False}),
        "status": STATUS_PENDING,
        "plan": str(plan_path),
        "blocker": None,
        "proof": None,
        "built_at": _now_iso(),
    }
    _write_receipts(run_dir, phase_id, receipt)
    record_ops(run_dir, phase_id,
               {"status": "dispatched", "gate": gate,
                "next_action": "delegated Skill 06 agent executes "
                               f"{plan_path.name}, then re-run to verify"})
    print(f"\n{phase_id}: PLAN EMITTED (Skill 06 page-install contract; "
          "IDs land at delegated execution)")
    return EXIT_OK, receipt


def _execute_pages(run_dir: Path, phase_id: str, intake: dict, scope: dict,
                   gate: dict, adapter: PageInstallAdapter) -> Tuple[int, dict]:
    """Adapter path (tests / live tool runs): create-once, read back,
    receipt. Resume reuses recorded remote IDs -- no duplicates."""
    missing = _missing_inputs(run_dir, phase_id)
    if missing:
        blocker = {"code": BLOCK_MISSING_INPUT,
                   "detail": f"page HTML missing/too small: {missing}",
                   "action": "run the page-builder phases, then re-run"}
        receipt = _blocked_receipt(run_dir, phase_id, intake, blocker, gate)
        _write_receipts(run_dir, phase_id, receipt)
        return EXIT_BLOCKED, receipt
    ops = load_ops(run_dir).get(phase_id) or {}
    ops_remote = ops.get("remote") if isinstance(ops.get("remote"), dict) else {}
    execution_id = ops.get("execution_id") or _new_execution_id()
    record_ops(run_dir, phase_id,
               {"status": "running", "execution_id": execution_id, "gate": gate,
                "next_action": "create funnel/pages via Skill 06 adapter"})
    funnel_name, pages = _page_specs(run_dir, phase_id, scope)
    funnel_id = ops_remote.get("funnel_id")
    if not funnel_id and phase_id == PHASE_GHL_VSL:
        funnel_id = shared_funnel_id(run_dir)
    if not funnel_id:
        plan = build_page_install_plan(
            phase_id=phase_id, scope=scope, pages=pages,
            funnel_name=funnel_name,
            shared_funnel_id=(shared_funnel_id(run_dir)
                              if phase_id == PHASE_GHL_VSL else None))
        try:
            funnel_id = adapter.create_funnel(plan)
        except Exception as exc:  # noqa: BLE001
            record_ops(run_dir, phase_id,
                       {"status": "running", "execution_id": execution_id,
                        "next_action": f"retry create_funnel: {exc!r}"})
            return EXIT_BUILD_FAILED, {"status": "running", "error": str(exc)}
        # Persist the remote ID IMMEDIATELY -- a kill after this line
        # resumes without creating a second funnel.
        ops_remote = dict(ops_remote)
        ops_remote["funnel_id"] = funnel_id
        record_ops(run_dir, phase_id,
                   {"status": STATUS_REMOTE_CREATED,
                    "execution_id": execution_id, "remote": ops_remote,
                    "next_action": "install pages, then read back"})
    remote = {"funnel_id": funnel_id}
    for pg in pages:
        key = f"{pg['key']}_page_id"
        pid = ops_remote.get(key)
        if not pid:
            try:
                pid = adapter.install_page(funnel_id, pg)
            except Exception as exc:  # noqa: BLE001
                record_ops(run_dir, phase_id,
                           {"status": STATUS_REMOTE_CREATED,
                            "execution_id": execution_id,
                            "remote": ops_remote,
                            "next_action": f"retry install_page {pg['key']}: {exc!r}"})
                return EXIT_BUILD_FAILED, {"status": STATUS_REMOTE_CREATED,
                                           "error": str(exc)}
            ops_remote = dict(ops_remote)
            ops_remote[key] = pid
            record_ops(run_dir, phase_id,
                       {"status": STATUS_REMOTE_CREATED,
                        "execution_id": execution_id, "remote": ops_remote,
                        "next_action": "read back all pages"})
        remote[key] = pid
    try:
        pages_rb = {pid: adapter.readback_page(pid) for pid in
                    [remote[f"{pg['key']}_page_id"] for pg in pages]}
    except Exception as exc:  # noqa: BLE001
        record_ops(run_dir, phase_id,
                   {"status": STATUS_REMOTE_CREATED,
                    "execution_id": execution_id, "remote": ops_remote,
                    "next_action": f"retry readback: {exc!r}"})
        return EXIT_BUILD_FAILED, {"status": STATUS_REMOTE_CREATED,
                                   "error": str(exc)}
    for pid, rb in pages_rb.items():
        if rb.get("location_id") != scope["location_id"]:
            detail = (f"readback location {rb.get('location_id')!r} != scope "
                      f"{scope['location_id']!r} on {pid} (WRONG_LOCATION)")
            record_ops(run_dir, phase_id,
                       {"status": STATUS_REMOTE_CREATED,
                        "execution_id": execution_id, "remote": ops_remote,
                        "next_action": detail})
            return EXIT_VERIFY_FAILED, {"status": STATUS_REMOTE_CREATED,
                                        "error": detail}
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "phase": phase_id,
        "deck_slug": scope["deck_slug"],
        "run_id": scope["run_id"],
        "scope": {k: scope.get(k) for k in
                  ("deck_slug", "run_id", "company", "location_id")},
        "input_hashes": input_hashes(run_dir, phase_id),
        "execution": {"execution_id": execution_id,
                      "started_at": _now_iso(),
                      "adapter": type(adapter).__name__},
        "remote": remote,
        "readback": {"ok": True, "checked_at": _now_iso(), "pages": pages_rb},
        "status": STATUS_COMPLETE,
        "blocker": None,
        "proof": {"pages": len(pages_rb), "location_id": scope["location_id"]},
        "built_at": _now_iso(),
    }
    _write_receipts(run_dir, phase_id, receipt)
    record_ops(run_dir, phase_id,
               {"status": STATUS_VERIFIED, "execution_id": execution_id,
                "remote": remote, "next_action": "done"})
    return EXIT_OK, receipt


def _emit_gate_plan(run_dir: Path, intake: dict, scope: dict,
                    gate: dict) -> Tuple[int, dict]:
    """No adapter in this process: emit the Skill 44 plan + pending receipts."""
    plan = build_gate_form_plan(scope=scope, fields=gate_form_fields())
    plan_path = run_dir / "working" / "vsl" / "gate_form_skill44_plan.json"
    _write_json_atomic(plan_path, plan)
    exec_rec = {"execution_id": _new_execution_id(),
                "started_at": _now_iso(), "adapter": "skill44-delegated"}
    hashes = input_hashes(run_dir, PHASE_FORM_GATE)
    scope_rec = {k: scope.get(k) for k in
                 ("deck_slug", "run_id", "company", "location_id")}
    base = {"schema_version": RECEIPT_SCHEMA, "phase": PHASE_FORM_GATE,
            "deck_slug": scope["deck_slug"], "run_id": scope["run_id"],
            "scope": scope_rec, "input_hashes": hashes,
            "execution": exec_rec, "status": STATUS_PENDING,
            "plan": str(plan_path), "blocker": None, "built_at": _now_iso()}
    form_rec = dict(base, artifact="ecosystem/gate-form.json",
                    form={"name": plan["form"]["name"], "form_id": None},
                    remote={}, readback={"ok": False}, proof=None)
    wf_rec = dict(base, artifact="workflows/gate-workflow.json",
                  workflow={"name": plan["workflow"]["name"],
                            "workflow_id": None, "draft_only": True},
                  remote={}, readback={"ok": False}, proof=None)
    _write_json_atomic(receipt_paths(run_dir, PHASE_FORM_GATE)[0], form_rec)
    _write_json_atomic(receipt_paths(run_dir, PHASE_FORM_GATE)[1], wf_rec)
    record_ops(run_dir, PHASE_FORM_GATE,
               {"status": "dispatched", "gate": gate,
                "next_action": "delegated Skill 44 agent executes "
                               f"{plan_path.name}, then re-run to verify"})
    print(f"\n{PHASE_FORM_GATE}: PLAN EMITTED (Skill 44 form/workflow "
          "contract; IDs land at delegated execution)")
    return EXIT_OK, form_rec


def _execute_gate(run_dir: Path, intake: dict, scope: dict, gate: dict,
                  adapter: GateFormAdapter) -> Tuple[int, dict]:
    """Adapter path for the gate form+workflow, with partial-state resume
    (form created but workflow missing continues without duplicating)."""
    ops = load_ops(run_dir).get(PHASE_FORM_GATE) or {}
    ops_remote = ops.get("remote") if isinstance(ops.get("remote"), dict) else {}
    execution_id = ops.get("execution_id") or _new_execution_id()
    record_ops(run_dir, PHASE_FORM_GATE,
               {"status": "running", "execution_id": execution_id,
                "gate": gate,
                "next_action": "create form/workflow via Skill 44 adapter"})
    plan = build_gate_form_plan(scope=scope, fields=gate_form_fields())
    form_id = ops_remote.get("form_id")
    if not form_id:
        try:
            form_id = adapter.create_form(
                {"scope": plan["scope"], "form": plan["form"]})
        except Exception as exc:  # noqa: BLE001
            record_ops(run_dir, PHASE_FORM_GATE,
                       {"status": "running", "execution_id": execution_id,
                        "next_action": f"retry create_form: {exc!r}"})
            return EXIT_BUILD_FAILED, {"status": "running", "error": str(exc)}
        ops_remote = dict(ops_remote)
        ops_remote["form_id"] = form_id
        record_ops(run_dir, PHASE_FORM_GATE,
                   {"status": STATUS_REMOTE_CREATED,
                    "execution_id": execution_id, "remote": ops_remote,
                    "next_action": "create workflow, then read back"})
    workflow_id = ops_remote.get("workflow_id")
    if not workflow_id:
        try:
            workflow_id = adapter.create_workflow(
                {"scope": plan["scope"], "workflow": plan["workflow"]},
                form_id)
        except Exception as exc:  # noqa: BLE001
            record_ops(run_dir, PHASE_FORM_GATE,
                       {"status": STATUS_REMOTE_CREATED,
                        "execution_id": execution_id, "remote": ops_remote,
                        "next_action": f"retry create_workflow: {exc!r}"})
            return EXIT_BUILD_FAILED, {"status": STATUS_REMOTE_CREATED,
                                       "error": str(exc)}
        ops_remote = dict(ops_remote)
        ops_remote["workflow_id"] = workflow_id
        record_ops(run_dir, PHASE_FORM_GATE,
                   {"status": STATUS_REMOTE_CREATED,
                    "execution_id": execution_id, "remote": ops_remote,
                    "next_action": "read back form + workflow"})
    try:
        rb_form = adapter.readback_form(form_id)
        rb_wf = adapter.readback_workflow(workflow_id)
    except Exception as exc:  # noqa: BLE001
        record_ops(run_dir, PHASE_FORM_GATE,
                   {"status": STATUS_REMOTE_CREATED,
                    "execution_id": execution_id, "remote": ops_remote,
                    "next_action": f"retry readback: {exc!r}"})
        return EXIT_BUILD_FAILED, {"status": STATUS_REMOTE_CREATED,
                                   "error": str(exc)}
    for label, rb in (("form", rb_form), ("workflow", rb_wf)):
        if rb.get("location_id") != scope["location_id"]:
            detail = (f"{label} readback location {rb.get('location_id')!r} != "
                      f"scope {scope['location_id']!r} (WRONG_LOCATION)")
            return EXIT_VERIFY_FAILED, {"status": STATUS_REMOTE_CREATED,
                                        "error": detail}
    if rb_wf.get("form_id") != form_id:
        return EXIT_VERIFY_FAILED, {"status": STATUS_REMOTE_CREATED,
                                    "error": "workflow readback not bound to "
                                             f"form {form_id}"}
    exec_rec = {"execution_id": execution_id, "started_at": _now_iso(),
                "adapter": type(adapter).__name__}
    hashes = input_hashes(run_dir, PHASE_FORM_GATE)
    scope_rec = {k: scope.get(k) for k in
                 ("deck_slug", "run_id", "company", "location_id")}
    form_rec = {"schema_version": RECEIPT_SCHEMA, "phase": PHASE_FORM_GATE,
                "artifact": "ecosystem/gate-form.json",
                "deck_slug": scope["deck_slug"], "run_id": scope["run_id"],
                "scope": scope_rec, "input_hashes": hashes,
                "execution": exec_rec,
                "form": {"name": plan["form"]["name"], "form_id": form_id},
                "remote": {"form_id": form_id, "workflow_id": workflow_id},
                "readback": {"ok": True, "checked_at": _now_iso(),
                             "form": rb_form, "workflow": rb_wf},
                "status": STATUS_COMPLETE, "blocker": None,
                "proof": {"location_id": scope["location_id"]},
                "built_at": _now_iso()}
    wf_rec = dict(form_rec, artifact="workflows/gate-workflow.json",
                  workflow={"name": plan["workflow"]["name"],
                            "workflow_id": workflow_id, "draft_only": True})
    _write_json_atomic(receipt_paths(run_dir, PHASE_FORM_GATE)[0], form_rec)
    _write_json_atomic(receipt_paths(run_dir, PHASE_FORM_GATE)[1], wf_rec)
    record_ops(run_dir, PHASE_FORM_GATE,
               {"status": STATUS_VERIFIED, "execution_id": execution_id,
                "remote": dict(ops_remote), "next_action": "done"})
    return EXIT_OK, form_rec


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Install elected GHL pages/forms/workflows (offer-derived "
                    "contracts -> Skill 06/44 adapters -> readback receipts).")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--phase", default=None,
                    choices=list(EXTERNAL_PHASES),
                    help="external phase to execute")
    ap.add_argument("--selftest", action="store_true",
                    help="offline deterministic self-test")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.run_dir or not args.phase:
        ap.error("--run-dir and --phase are required (or --selftest)")
    run_dir = Path(args.run_dir).resolve()

    # Idempotent fast path: an existing COMPLETE receipt re-validates
    # without touching anything (same banked-work discipline as the engine).
    ok, detail, _data = validate_receipt(run_dir, args.phase)
    if ok:
        record_ops(run_dir, args.phase,
                   {"status": STATUS_VERIFIED,
                    "next_action": "done (banked receipt re-validated)"})
        print(f"\n{args.phase}: VERIFIED (banked receipt: {detail})")
        return EXIT_OK

    rc, _receipt = execute_phase(run_dir, args.phase)
    return rc


# ---------------------------------------------------------------------------
# Offline deterministic self-test (no network, no GHL call).
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    fails: List[str] = []

    # 1) Preflight: external phases routed to text writers are refused.
    for pid in EXTERNAL_PHASES:
        ok, detail = preflight_check_phase(pid, {"executor": {"kind": "agent"}})
        if ok:
            fails.append(f"preflight ACCEPTED text-routed {pid}: {detail}")
        if "AF-EXTERNAL-TEXT-ROUTING" not in detail:
            fails.append(f"preflight refusal for {pid} names no code: {detail}")
    ok, _d = preflight_check_phase(
        PHASE_GHL_SALES, {"executor": {"kind": "script",
                                       "capability": CAP_GHL_PAGE_INSTALL}})
    if not ok:
        fails.append("preflight REJECTED a correctly-wired page-install phase")
    ok, _d = preflight_check_phase(
        PHASE_FORM_GATE, {"executor": {"kind": "script",
                                       "capability": CAP_GHL_WORKFLOW_INSTALL}})
    if not ok:
        fails.append("preflight REJECTED a correctly-wired workflow-install phase")

    # 2) Scope: location disagreement blocks WRONG_LOCATION.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run"
        scope, blk = resolve_scope(
            rd, {"deck_slug": "acme", "GHL_LOCATION_ID": "locX"},
            env={"GOHIGHLEVEL_LOCATION_ID": "loc1"})
        if not blk or blk["code"] != BLOCK_WRONG_LOCATION:
            fails.append(f"scope must block WRONG_LOCATION: {scope} {blk}")
        scope, blk = resolve_scope(rd, {"deck_slug": "acme"},
                                   env={"GOHIGHLEVEL_LOCATION_ID": "loc1"})
        if blk or not scope or scope["location_id"] != "loc1":
            fails.append(f"scope wrong: {scope} {blk}")

    # 3) Fake-model receipt cannot complete (QC check 1).
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run"
        (rd / "working" / "sales-checkout").mkdir(parents=True)
        fake = {"schema_version": RECEIPT_SCHEMA, "phase": PHASE_GHL_SALES,
                "deck_slug": "run", "run_id": "run",
                "scope": {"deck_slug": "run", "run_id": "run",
                          "company": "Acme", "location_id": "loc1"},
                "input_hashes": {}, "execution": {"execution_id": "gx_fake"},
                "remote": {"funnel_id": "funnel_XXXX",
                           "sales_page_id": "page_XXXX",
                           "checkout_page_id": "page_YYYY"},
                "readback": {"ok": True, "checked_at": _now_iso(),
                             "pages": {"page_XXXX": {"location_id": "loc1"},
                                       "page_YYYY": {"location_id": "loc1"}}},
                "status": STATUS_COMPLETE, "built_at": _now_iso()}
        _write_json_atomic(rd / RECEIPT_REL[PHASE_GHL_SALES], fake)
        ok, detail, _d = validate_receipt(rd, PHASE_GHL_SALES)
        if ok:
            fails.append(f"validate ACCEPTED a fake-model receipt: {detail}")
        if "readback" not in detail and "remote" not in detail \
                and "IDs" not in detail:
            fails.append(f"fake refusal names no mechanism: {detail}")

    # 4) Mock adapters: IDs + readback prove completion; wrong location
    #    refused (QC check 2). Kill-resume reuses IDs, no dup (QC check 3).
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run"
        (rd / "working" / "copy").mkdir(parents=True)
        (rd / "working" / "sales-checkout" / "html").mkdir(parents=True)
        (rd / "working" / "vsl" / "html").mkdir(parents=True)
        (rd / "working" / "sales-checkout" / "html" / "sales.html").write_text(
            "<h1>Sales</h1>" + "x" * 300)
        (rd / "working" / "sales-checkout" / "html" / "checkout.html").write_text(
            "<h1>Checkout</h1>" + "x" * 300)
        (rd / "working" / "vsl" / "html" / "vsl.html").write_text(
            "<h1>VSL</h1><video src='m.mp4'></video>" + "x" * 300)
        (rd / "working" / "copy" / "intake.json").write_text(json.dumps({
            "deck_slug": "acme", "company": "Acme Co",
            "pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes",
                                         "WANT_VSL_PAGE": "yes"}}))
        env = {"GOHIGHLEVEL_LOCATION_ID": "loc1"}
        # ONE page adapter for sales+VSL (like production: one Skill 06
        # session per location, so the shared-funnel reuse resolves).
        mem_pages = MemoryPageAdapter("loc1")
        rc, _r = execute_phase(rd, PHASE_GHL_SALES, page_adapter=mem_pages,
                               env=env)
        if rc != EXIT_OK:
            fails.append(f"sales adapter run failed rc={rc}: {_r}")
        ok, _d, _dd = validate_receipt(rd, PHASE_GHL_SALES, env=env)
        if not ok:
            fails.append(f"sales adapter receipt must validate: {_d}")
        if mem_pages.calls.count("create_funnel") != 1:
            fails.append(f"sales created funnel {mem_pages.calls.count('create_funnel')}x")
        # Wrong-location adapter must refuse the write (fresh dir, so no
        # shared funnel masks the scope check).
        import shutil as _shutil
        rd_evil = Path(td) / "evil"
        _shutil.copytree(rd, rd_evil,
                         ignore=_shutil.ignore_patterns(
                             "ghl_build_receipt.json", "ghl_external_ops.json"))
        evil = MemoryPageAdapter("locEVIL")
        rc, r = execute_phase(rd_evil, PHASE_GHL_SALES, page_adapter=evil,
                              env=env)
        if rc == EXIT_OK:
            fails.append(f"wrong-location adapter run must not complete: {r}")
        if not any("WRONG_LOCATION" in str(x) for x in
                   (r.get("error", ""),)):
            fails.append(f"wrong-location refusal names no code: {r}")
        # VSL reuses the verified sales funnel (no second funnel).
        rc, _r = execute_phase(rd, PHASE_GHL_VSL, page_adapter=mem_pages,
                               env=env)
        if rc != EXIT_OK:
            fails.append(f"vsl adapter run failed rc={rc}: {_r}")
        if mem_pages.calls.count("create_funnel") != 1:
            fails.append("vsl must reuse the sales funnel, not create a second")
        # Kill-resume: IDs recorded in ops, receipt gone -> resume reuses.
        first_ids = dict(load_ops(rd)[PHASE_GHL_VSL]["remote"])
        (rd / RECEIPT_REL[PHASE_GHL_VSL]).unlink()
        creates_before = list(mem_pages.calls).count("create_funnel") + \
            list(mem_pages.calls).count("install_page")
        rc, _r = execute_phase(rd, PHASE_GHL_VSL, page_adapter=mem_pages,
                               env=env)
        creates_after = list(mem_pages.calls).count("create_funnel") + \
            list(mem_pages.calls).count("install_page")
        if rc != EXIT_OK:
            fails.append(f"vsl resume failed rc={rc}: {_r}")
        if creates_after != creates_before:
            fails.append("resume created duplicate remote objects "
                         f"({creates_before} -> {creates_after})")
        if dict(load_ops(rd)[PHASE_GHL_VSL]["remote"]) != first_ids:
            fails.append("resume changed remote IDs")
        # Gate pair via the Skill 44 stand-in.
        mem_gate = MemoryGateAdapter("loc1")
        rc, _r = execute_phase(rd, PHASE_FORM_GATE, gate_adapter=mem_gate,
                               env=env)
        if rc != EXIT_OK:
            fails.append(f"gate adapter run failed rc={rc}: {_r}")
        ok, _d, _dd = validate_receipt(rd, PHASE_FORM_GATE, env=env)
        if not ok:
            fails.append(f"gate adapter receipts must validate: {_d}")

    if fails:
        print("ghl_external_installer selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("ghl_external_installer selftest -> PASS (preflight, scope, "
          "fake-receipt refusal, mock adapters + readback + location, "
          "kill-resume no-dup, gate pair)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""ghl_id_handoff.py - S06-06: the ONE unified per-run ID-handoff record for
Skill 06 (prep step 3, gap 6).

WHY THIS MODULE EXISTS
----------------------
A run's created-object IDs surface through FIVE different mechanisms, and
before this module nothing assembled them into one artifact for downstream
consumers (S44's handoff back, S71's A07 evidence, S79's A08 evidence):

  1. funnel ID     - the funnel-create 201 response body (``id``).
  2. page ID       - the create-step response (``created_page_id``).
  3. form ID       - the form-builder iframe ``src`` (``/form-builder-v2/<id>``),
                     shape-gated ``[A-Za-z0-9]{15,30}`` and polled by
                     ``ghl_form_builder._capture_form_id``.
  4. workflow ID   - parsed from the Automations builder URL after save
                     (``ghl_workflow_builder``).
  5. pipeline ID   - NOT captured at build time at all: the pipeline builder
                     proves the pipeline by rendered name, and the ID is bound
                     LATER by name through the Skill 44 read API. This record
                     therefore carries the pipeline as a NAME binding with
                     ``id: None`` - it never invents a pipeline ID.

This module assembles those IDs, each with its SOURCE MECHANISM recorded as
provenance, into ONE record per run:

    <run_dir>/routing/id-handoff.json

The ``run_dir`` is the run's durable evidence root (SKILL.md: run evidence
lives at ``skill6-fix/v2-<RUN_ID>/`` outside the skill dir; ``/tmp`` is
ephemeral scratch only and is never a run-evidence root). The record sits
ALONGSIDE the unified routing record (``routing/method-decision.json``,
schema ``skill6-method-decision/1``) but is a DISTINCT artifact with its own
schema (``skill6-id-handoff/1``): the routing record carries decisions and
deliberately NO created-object IDs; this record carries IDs and no decisions.
Neither file's name or schema collides with the other.

HONESTY RULES (the F6 discipline, applied to IDs)
-------------------------------------------------
  * No receipt / no capture = no ID. An object kind with no proven ID is
    listed under ``missing`` - it is never filled with a guessed, derived, or
    placeholder value.
  * Every recorded ID names the mechanism that surfaced it (``source``) and
    may carry ``evidenceRefs`` (run-dir-relative paths) to the artifact that
    proves it.
  * Product references are carried VERBATIM from the caller (an S44 Phase A
    product reference when one is delivered, otherwise an explicitly
    caller-supplied reference). This module never fabricates S44 IDs,
    provisioning state, prices, or catalog data.
  * ``assemble_from_receipts`` derives entries ONLY from the F6 receipts
    store on disk (``ghl_receipts.list_receipts``) - the same
    read-from-disk, never-an-in-memory-tally discipline as
    ``ghl_receipts.reduce_receipts`` and ``ghl_method_decision``.

CLI
---
    python3 ghl_id_handoff.py --selftest
    python3 ghl_id_handoff.py --assemble <run_dir>   # build from receipts + print
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

SCHEMA_ID = "skill6-id-handoff/1"
HANDOFF_FILENAME = "id-handoff.json"

# The form ID shape gate, identical to ghl_form_builder._FORM_ID_SHAPE_RE: a
# real GHL form id is an opaque 15-30 char alphanumeric token. A recorded form
# ID that does not match this shape is not trusted as a form ID.
_FORM_ID_SHAPE_RE = re.compile(r"[A-Za-z0-9]{15,30}")

# The workflow ID read-back, identical to
# ghl_workflow_builder._WORKFLOW_ID_RE: the saved workflow routes to
# .../workflows/<id> (optionally .../workflows/builder/<id>).
_WORKFLOW_ID_RE = re.compile(r"/workflows/(?:builder/)?([A-Za-z0-9_-]{6,})")

#: Object kinds the handoff tracks, in record order.
OBJECT_KINDS = ("funnel", "pages", "form", "workflow", "pipeline",
                "products", "order_elements")

#: Binding provenance values an order-element / product entry may carry. A
#: product reference is either delivered by S44 Phase A provisioning or
#: supplied explicitly by the caller; there is no third, invented source.
BINDING_SOURCES = ("s44_phase_a", "caller_supplied")


class HandoffError(ValueError):
    """Raised when a caller tries to record an ID this module cannot honestly
    stand behind: an empty ID, a form ID that fails the shape gate, a
    workflow URL with no parseable ID, or a binding with no provenance.
    Never silently defaulted."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def handoff_path(run_dir: str) -> str:
    """The handoff record's path: ``<run_dir>/routing/id-handoff.json``,
    alongside the unified routing record (a distinct file and schema)."""
    return os.path.join(str(run_dir), "routing", HANDOFF_FILENAME)


def new_handoff(*, run_id: Optional[str] = None,
                location_ref: Optional[str] = None) -> dict:
    """A fresh handoff skeleton. Every object kind starts ABSENT (listed in
    ``missing``); kinds move out of ``missing`` only when a ``record_*``
    call supplies a proven ID (or, for the pipeline, a name binding)."""
    return {
        "schema": SCHEMA_ID,
        "runId": run_id or "",
        "generatedAt": _now(),
        "scope": {"locationRef": location_ref},
        "objects": {},
        "missing": list(OBJECT_KINDS),
    }


def _set(handoff: dict, kind: str, entry: dict) -> dict:
    handoff.setdefault("objects", {})[kind] = entry
    missing = [m for m in handoff.get("missing", []) if m != kind]
    handoff["missing"] = missing
    return handoff


def _require_id(value: Any, kind: str) -> str:
    v = str(value or "").strip()
    if not v:
        raise HandoffError(
            f"{kind} id is empty - refusing to record an unproven ID "
            "(no receipt / no capture = no ID)")
    return v


def _refs(evidence_refs: Optional[List[str]]) -> List[str]:
    return [str(r) for r in (evidence_refs or []) if str(r).strip()]


def record_funnel(handoff: dict, funnel_id: Any, *,
                  evidence_refs: Optional[List[str]] = None) -> dict:
    """Record the funnel ID. Source mechanism: the funnel-create 201
    response body (``id``)."""
    fid = _require_id(funnel_id, "funnel")
    return _set(handoff, "funnel", {
        "id": fid,
        "source": "funnel_create_response",
        "evidenceRefs": _refs(evidence_refs),
    })


def record_page(handoff: dict, step: str, page_id: Any, *,
                evidence_refs: Optional[List[str]] = None) -> dict:
    """Record ONE page ID under its funnel step name. Source mechanism: the
    create-step response (``created_page_id``). Pages accumulate; recording
    the same step again replaces its entry (latest proven state wins)."""
    pid = _require_id(page_id, "page")
    step_name = str(step or "").strip()
    if not step_name:
        raise HandoffError("page step name is required (the funnel step the "
                           "page ID belongs to)")
    pages = [p for p in (handoff.get("objects", {}).get("pages") or [])
             if p.get("step") != step_name]
    pages.append({
        "step": step_name,
        "page_id": pid,
        "source": "create_step_response",
        "evidenceRefs": _refs(evidence_refs),
    })
    pages.sort(key=lambda p: p["step"])
    handoff.setdefault("objects", {})["pages"] = pages
    handoff["missing"] = [m for m in handoff.get("missing", []) if m != "pages"]
    return handoff


def record_form(handoff: dict, form_id: Any, *,
                evidence_refs: Optional[List[str]] = None) -> dict:
    """Record the form ID. Source mechanism: the form-builder iframe ``src``
    (``/form-builder-v2/<id>``), captured and shape-gated by
    ``ghl_form_builder._capture_form_id``. The same shape gate is re-applied
    here: a value that is not a 15-30 char alphanumeric token is refused."""
    fid = _require_id(form_id, "form")
    if not _FORM_ID_SHAPE_RE.fullmatch(fid):
        raise HandoffError(
            f"form id {fid!r} fails the GHL form-id shape gate "
            "([A-Za-z0-9]{15,30}) - refusing to record a value the capture "
            "mechanism itself would not trust")
    return _set(handoff, "form", {
        "id": fid,
        "source": "form_builder_iframe_src",
        "evidenceRefs": _refs(evidence_refs),
    })


def record_workflow(handoff: dict, workflow_id_or_url: Any, *,
                    evidence_refs: Optional[List[str]] = None) -> dict:
    """Record the workflow ID. Source mechanism: read back from the
    Automations builder URL after save (``ghl_workflow_builder``). Accepts
    either the bare ID or the builder URL it was parsed from; a URL with no
    parseable workflow ID is refused."""
    raw = str(workflow_id_or_url or "").strip()
    if not raw:
        raise HandoffError("workflow id/url is empty - refusing to record "
                           "an unproven ID")
    if "/" in raw:
        m = _WORKFLOW_ID_RE.search(raw)
        if not m:
            raise HandoffError(
                f"no workflow id parseable from builder URL {raw!r} - "
                "refusing to guess")
        wid = m.group(1)
    else:
        wid = raw
    return _set(handoff, "workflow", {
        "id": wid,
        "source": "workflow_builder_url",
        "evidenceRefs": _refs(evidence_refs),
    })


def record_pipeline_by_name(handoff: dict, pipeline_name: Any, *,
                            evidence_refs: Optional[List[str]] = None) -> dict:
    """Record the pipeline as a NAME BINDING. The pipeline builder does NOT
    capture a pipeline ID (it proves the pipeline by rendered name); the ID
    is bound later by name through the Skill 44 read API
    (``caf opportunities pipelines``). This entry therefore carries
    ``id: None`` and ``bound_by: "name"`` - an honest absence, never an
    invented ID."""
    name = str(pipeline_name or "").strip()
    if not name:
        raise HandoffError("pipeline name is empty - a name binding needs "
                           "the exact rendered pipeline name")
    return _set(handoff, "pipeline", {
        "id": None,
        "bound_by": "name",
        "name": name,
        "source": "pipeline_name_binding",
        "note": ("pipeline ID is NOT captured at build time; it is bound "
                 "later by this exact name via the Skill 44 read API"),
        "evidenceRefs": _refs(evidence_refs),
    })


def record_product(handoff: dict, product_ref: Any, binding_source: str, *,
                   evidence_refs: Optional[List[str]] = None) -> dict:
    """Record ONE product reference, carried VERBATIM from its source. The
    reference is an S44 Phase A product reference when Phase A delivered
    one, otherwise an explicitly caller-supplied reference; the provenance
    (``binding_source``) is recorded either way. This module never derives,
    looks up, or fabricates a product ID, price, or catalog entry."""
    ref = str(product_ref or "").strip()
    if not ref:
        raise HandoffError("product reference is empty - refusing to record "
                           "a binding with no reference")
    if binding_source not in BINDING_SOURCES:
        raise HandoffError(
            f"binding_source {binding_source!r} is not one of "
            f"{BINDING_SOURCES} - a product reference must name its "
            "provenance (delivered by S44 Phase A, or explicitly supplied "
            "by the caller)")
    products = [p for p in (handoff.get("objects", {}).get("products") or [])
                if p.get("product_ref") != ref]
    products.append({
        "product_ref": ref,
        "binding_source": binding_source,
        "evidenceRefs": _refs(evidence_refs),
    })
    handoff.setdefault("objects", {})["products"] = products
    handoff["missing"] = [m for m in handoff.get("missing", [])
                          if m != "products"]
    return handoff


def record_order_element(handoff: dict, element: str, product_ref: Any,
                         binding_source: str, *,
                         form_id: Optional[str] = None,
                         evidence_refs: Optional[List[str]] = None) -> dict:
    """Record ONE placed order element and the product binding it carries.
    The element's own native ID is recorded only when a mechanism surfaced
    one (``element_id``); the product reference is carried verbatim with its
    provenance, exactly as in :func:`record_product`."""
    el = str(element or "").strip()
    if not el:
        raise HandoffError("order element name is required")
    ref = str(product_ref or "").strip()
    if not ref:
        raise HandoffError(
            f"order element {el!r} has no product reference - an order "
            "element without a binding is not a handoff entry (fail closed)")
    if binding_source not in BINDING_SOURCES:
        raise HandoffError(
            f"binding_source {binding_source!r} is not one of "
            f"{BINDING_SOURCES}")
    entry: Dict[str, Any] = {
        "element": el,
        "product_ref": ref,
        "binding_source": binding_source,
        "source": "order_plan",
        "evidenceRefs": _refs(evidence_refs),
    }
    if form_id:
        entry["form_id"] = str(form_id)
    elements = [e for e in (handoff.get("objects", {}).get("order_elements")
                           or []) if e.get("element") != el]
    elements.append(entry)
    handoff.setdefault("objects", {})["order_elements"] = elements
    handoff["missing"] = [m for m in handoff.get("missing", [])
                          if m != "order_elements"]
    return handoff


# ── Persistence ──────────────────────────────────────────────────────────────

def load_handoff(run_dir: str) -> Optional[dict]:
    """Read the handoff record if one exists (None when absent). Raises
    :class:`HandoffError` on a corrupt or foreign-schema file - a record
    this module cannot recognize must not be silently overwritten."""
    path = handoff_path(run_dir)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        record = json.load(fh)
    if not isinstance(record, dict) or record.get("schema") != SCHEMA_ID:
        raise HandoffError(
            f"{path} exists but is not a {SCHEMA_ID} record - refusing to "
            "overwrite a file this module does not own")
    return record


def write_handoff(run_dir: str, handoff: dict) -> str:
    """Persist the handoff record (write-then-rename, the ``ghl_receipts``
    discipline, so a killed process never leaves a half-written record)."""
    record = dict(handoff)
    record["schema"] = SCHEMA_ID
    record["generatedAt"] = _now()
    if not record.get("runId"):
        record["runId"] = os.path.basename(
            os.path.normpath(str(run_dir))) or "run"
    path = handoff_path(run_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)
    return path


# ── Assembly from the F6 receipts store ──────────────────────────────────────

def assemble_from_receipts(evidence_root: str, *,
                           run_id: Optional[str] = None,
                           location_ref: Optional[str] = None,
                           binding_source: str = "caller_supplied") -> dict:
    """Build a handoff from the F6 receipts ON DISK under
    ``<evidence_root>/ecosystem/``. Only receipts whose action is
    ``created``/``reused`` AND that carry a ``response_id`` contribute an
    ID - a failed or ID-less receipt proves nothing (no receipt = not
    created). Object types map as: ``funnel`` -> funnel, ``page`` -> pages
    (slug = step), ``form`` -> form, ``workflow`` -> workflow, ``product``
    -> products (the receipt's ``response_id`` carried verbatim as the
    product reference, provenance = ``binding_source``)."""
    import ghl_receipts

    handoff = new_handoff(run_id=run_id, location_ref=location_ref)
    for r in ghl_receipts.list_receipts(evidence_root):
        if r.get("action") not in ("created", "reused"):
            continue
        rid = r.get("response_id")
        if not rid:
            continue
        otype = r.get("object_type")
        slug = str(r.get("slug") or "")
        ref = None
        if r.get("_path"):
            try:
                ref = os.path.relpath(r["_path"], str(evidence_root))
            except ValueError:
                ref = None
        refs = [ref] if ref else []
        try:
            if otype == "funnel":
                record_funnel(handoff, rid, evidence_refs=refs)
            elif otype == "page":
                record_page(handoff, slug, rid, evidence_refs=refs)
            elif otype == "form":
                record_form(handoff, rid, evidence_refs=refs)
            elif otype == "workflow":
                record_workflow(handoff, rid, evidence_refs=refs)
            elif otype == "product":
                record_product(handoff, rid, binding_source,
                               evidence_refs=refs)
        except HandoffError:
            # A receipt whose response_id fails this module's gates (e.g. a
            # form receipt carrying a non-form-shaped id) is NOT promoted
            # into the handoff; the kind stays honestly missing.
            continue
    return handoff


def verify_against_receipts(handoff: dict, evidence_root: str) -> dict:
    """Re-check every handoff ID that claims a receipts-store provenance
    against the receipts ON DISK. Returns ``{ok, problems}`` (pure verdict,
    never raises). An ID with no matching created/reused receipt is a
    problem - the handoff may never claim more than the receipts prove."""
    import ghl_receipts

    proven: Dict[str, set] = {}
    for r in ghl_receipts.list_receipts(evidence_root):
        if r.get("action") in ("created", "reused") and r.get("response_id"):
            proven.setdefault(str(r.get("object_type")), set()).add(
                str(r["response_id"]))
    problems: List[str] = []
    objects = handoff.get("objects", {}) or {}
    funnel = objects.get("funnel") or {}
    if funnel.get("id") and funnel["id"] not in proven.get("funnel", set()):
        problems.append(f"funnel id {funnel['id']!r} has no matching receipt")
    for p in objects.get("pages") or []:
        if p.get("page_id") and p["page_id"] not in proven.get("page", set()):
            problems.append(
                f"page id {p['page_id']!r} (step {p.get('step')!r}) has no "
                "matching receipt")
    form = objects.get("form") or {}
    if form.get("id") and form["id"] not in proven.get("form", set()):
        problems.append(f"form id {form['id']!r} has no matching receipt")
    wf = objects.get("workflow") or {}
    if wf.get("id") and wf["id"] not in proven.get("workflow", set()):
        problems.append(f"workflow id {wf['id']!r} has no matching receipt")
    return {"ok": not problems, "problems": problems}


# ── Self-test - no network, no browser, tmp only ─────────────────────────────

def _selftest() -> int:
    import tempfile

    errors: List[str] = []

    h = new_handoff(run_id="selftest-run", location_ref="LOC")
    if h["missing"] != list(OBJECT_KINDS):
        errors.append(f"fresh handoff must list every kind missing: {h['missing']}")

    record_funnel(h, "FUNNEL123")
    record_page(h, "optin", "PAGE123")
    record_page(h, "sales", "PAGE456")
    record_form(h, "cuPqQhLbk0GKeguEbGYW")
    record_workflow(
        h, "https://app.gohighlevel.com/v2/location/L/automation/workflows/WF9x8y7z")
    record_pipeline_by_name(h, "ZHC Sales Pipeline")
    record_product(h, "prod_ref_abc", "caller_supplied")
    record_order_element(h, "Sell Products", "prod_ref_abc", "caller_supplied",
                         form_id="cuPqQhLbk0GKeguEbGYW")

    objs = h["objects"]
    if objs["funnel"]["id"] != "FUNNEL123" \
            or objs["funnel"]["source"] != "funnel_create_response":
        errors.append(f"funnel entry wrong: {objs.get('funnel')}")
    if [p["step"] for p in objs["pages"]] != ["optin", "sales"]:
        errors.append(f"pages not sorted/accumulated: {objs.get('pages')}")
    if objs["form"]["source"] != "form_builder_iframe_src":
        errors.append(f"form source wrong: {objs.get('form')}")
    if objs["workflow"]["id"] != "WF9x8y7z":
        errors.append(f"workflow URL parse wrong: {objs.get('workflow')}")
    if objs["pipeline"]["id"] is not None or objs["pipeline"]["bound_by"] != "name":
        errors.append(f"pipeline must be a name binding with id None: "
                      f"{objs.get('pipeline')}")
    if h["missing"] != []:
        errors.append(f"all kinds recorded, missing must be empty: {h['missing']}")

    # Fail-closed gates.
    for fn in (
        lambda: record_funnel(new_handoff(), ""),
        lambda: record_form(new_handoff(), "not a form id!!"),
        lambda: record_workflow(new_handoff(), "https://x.example/nope"),
        lambda: record_product(new_handoff(), "p1", "invented_source"),
        lambda: record_order_element(new_handoff(), "Sell Products", "",
                                     "caller_supplied"),
    ):
        try:
            fn()
            errors.append("a fail-closed gate did not raise")
        except HandoffError:
            pass

    # Persistence round-trip + foreign-schema refusal.
    with tempfile.TemporaryDirectory() as tmp:
        path = write_handoff(tmp, h)
        loaded = load_handoff(tmp)
        if not loaded or loaded["objects"]["funnel"]["id"] != "FUNNEL123":
            errors.append(f"write/load round-trip broken: {loaded}")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"schema": "something-else/9"}, fh)
        try:
            load_handoff(tmp)
            errors.append("foreign-schema handoff file was not refused")
        except HandoffError:
            pass

    # Assembly from receipts: only proven IDs land; a failed receipt and an
    # ID-less receipt contribute nothing.
    with tempfile.TemporaryDirectory() as tmp:
        import ghl_receipts
        ghl_receipts.write_receipt(tmp, ghl_receipts.make_receipt(
            "funnel", "main", "created", response_id="FUNNEL999",
            verify={"ok": True}))
        ghl_receipts.write_receipt(tmp, ghl_receipts.make_receipt(
            "workflow", "followup", "failed", response_id="WF_should_not_appear",
            error="boom"))
        ghl_receipts.write_receipt(tmp, ghl_receipts.make_receipt(
            "page", "optin", "created", response_id=None))
        assembled = assemble_from_receipts(tmp, run_id="r1")
        if assembled["objects"].get("funnel", {}).get("id") != "FUNNEL999":
            errors.append(f"assembly missed the funnel receipt: {assembled}")
        if "workflow" not in assembled["missing"] or "pages" not in assembled["missing"]:
            errors.append(f"assembly promoted unproven objects: {assembled}")
        verdict = verify_against_receipts(assembled, tmp)
        if not verdict["ok"]:
            errors.append(f"verify_against_receipts flagged a truthful handoff: {verdict}")
        assembled["objects"]["funnel"]["id"] = "FUNNEL_fabricated"
        verdict = verify_against_receipts(assembled, tmp)
        if verdict["ok"]:
            errors.append("verify_against_receipts accepted a fabricated funnel id")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL - {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS - ID-handoff record verified (no network / no browser)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_id_handoff",
        description="Skill-6 unified per-run ID-handoff record "
                    "(schema skill6-id-handoff/1).",
    )
    p.add_argument("--selftest", action="store_true",
                   help="Run the no-network self-test and exit.")
    p.add_argument("--assemble", metavar="RUN_DIR",
                   help="Assemble a handoff from the run's F6 receipts, "
                        "write routing/id-handoff.json, and print it.")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.assemble:
        handoff = assemble_from_receipts(args.assemble)
        path = write_handoff(args.assemble, handoff)
        print(json.dumps({"path": path, **handoff}, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

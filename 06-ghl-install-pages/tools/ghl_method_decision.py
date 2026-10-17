#!/usr/bin/env python3
"""ghl_method_decision.py — S06-02: the ONE unified per-run operation-routing
decision record for Skill 06 (spec 05 section 4).

WHY THIS MODULE EXISTS
----------------------
Before this unit, a run's routing decisions lived in THREE systems with three
vocabularies and three record shapes:

  1. ``ghl_method.decide_and_record`` — per-page records at
     ``<run_dir>/routing/method-decision-<page>.json`` (method vocabulary:
     ``direct`` / ``vercel_embed`` / widget blocks), while SKILL.md's Phase-5
     table names the run's record ``routing/method-decision.json`` — a file
     nothing wrote.
  2. ``ghl_object_router.execute_write`` — per-object F6 receipts (via
     ``ghl_receipts``) under ``<evidence_root>/ecosystem/`` (rail vocabulary:
     ``skill44_caf`` / ``rest_services`` / ``browser`` / ...).
  3. ``ghl_fallback_ladder.run_ladder`` — per-surface ladder receipts
     (transport vocabulary: ``api`` / ``browser`` / ``mcp``).

This module is the AGGREGATOR over those three systems. It changes NONE of
their decision logic. It collects what they decided — from the per-page record
FILES on disk (never an in-memory tally, the same discipline as
``ghl_receipts.reduce_receipts``), from the router result dicts handed in at
call time, and from ladder result dicts when a ladder ran — and writes ONE
record per run at the exact path SKILL.md already promises:

    <run_dir>/routing/method-decision.json

RECORD SHAPE (schema ``skill6-method-decision/1``)
--------------------------------------------------
::

    {
      "schema": "skill6-method-decision/1",
      "runId": "<run identity: caller-supplied, else the run_dir basename>",
      "generatedAt": "YYYY-MM-DDTHH:MM:SSZ",
      "scope": {"locationRef": <ref-or-null>, "publishGate": "<state>"},
      "capabilitiesObserved": [<run-level capability refs>],
      "operations": [ <entry>, ... ],          # sorted by entry id
      "warnings": [ ... ]                        # only when a source file was unreadable
    }

Each operation entry::

    {
      "id": "page:<page>" | "page:<page>#widget:<block_key>"
            | "object:<object_type>:<slug>" | "ladder:<surface>",
      "source": "ghl_method" | "ghl_object_router" | "ghl_fallback_ladder",
      "operation": "<the page / object / surface the entry is about>",
      "operationClass": "<spec 05 section 4 step-1 class, see mapping below>",
      "chosenLane": "<the source system's OWN lane word, never renamed>",
      "outcome": "<the source system's own outcome word>",
      "capabilitiesObserved": [<refs / observed labels — never secret values>],
      "rejectedAlternatives": [{"lane": ..., "reason": ...}, ...],
      "scope": {"locationRef": ..., "publishGate": ...},
      "evidenceRefs": ["routing/method-decision-<page>.json", ...],
      "detail": { ... small non-secret source fields ... }
    }

OPERATION-CLASS MAPPING (spec 05 section 4, step 1)
---------------------------------------------------
Step 1's vocabulary is: ``metadata_read``, ``crm_product_write``,
``media_upload``, ``visual_builder_write``, ``workflow_write``,
``payment_configuration``, ``publish``. The three source systems' own terms
map onto it as follows (the mapping is the ONLY translation this module does;
lane names are carried verbatim, never translated):

From ``ghl_method`` (page method decisions):
  * page method ``direct`` / ``vercel_embed`` -> ``visual_builder_write``
    (a page build IS a visual builder write; the chosen lane is the method).
  * a widget block (kind ``form`` / ``booking``) -> ``visual_builder_write``
    with chosen lane ``widget`` (the block is placed by the native builder's
    widget embed, regardless of the page's own method).

From ``ghl_object_router`` object types:
  * ``custom_field``, ``custom_value``, ``tag``, ``contact``, ``product``
    -> ``crm_product_write``.
  * ``subaccount``, ``snapshot`` -> ``crm_product_write`` (provisioning
    writes; the nearest step-1 class — recorded here so the grouping is a
    reviewed choice, not an accident).
  * ``media`` -> ``media_upload``.
  * ``workflow``, ``workflow_trigger`` -> ``workflow_write``.
  * ``funnel``, ``website``, ``page``, ``form``, ``survey``, ``community``,
    ``course``, ``channel`` -> ``visual_builder_write`` (page/form builder
    writes; community/course/channel are builder writes with no closer
    step-1 class).

From ``ghl_fallback_ladder`` surfaces:
  * ``page``, ``funnel``, ``form``, ``survey``, ``community``, ``course``
    -> ``visual_builder_write``; ``workflow`` -> ``workflow_write``;
    ``media`` -> ``media_upload``; ``pipeline`` -> ``crm_product_write``.

Classes NO current source system emits (never fabricated by this module):
  * ``payment_configuration`` — no router object type, ladder surface, or
    page method covers payment configuration today.
  * ``metadata_read`` — the router's idempotency probe is a read, but it
    produces no standalone decision record; reads are not dressed up as
    routing decisions here.
  * ``publish`` — publish gating lives in ``ghl_builder.may_publish``,
    outside the three routing systems; this record carries the publish GATE
    STATE in ``scope.publishGate`` instead of inventing publish entries.

SECRET HYGIENE
--------------
Entries carry references and labels only: evidence file paths, tier numbers,
token-CONTEXT NAMES (``location_pit`` etc. — context labels from the router
matrix, not credential values), classifier scores and signal names, ladder
taxonomy codes. Credential VALUES are never copied into this record;
``locationRef`` is whatever reference the caller supplies (an env-var name,
an opaque ref, or a location identifier already present in a source record).

WIRING
------
``ghl_method.decide_and_record`` calls :func:`refresh_from_page_records`
after writing each per-page record, so any run that decides pages gets the
unified record automatically. Router and ladder outcomes are recorded by the
run through :func:`record_router_result` / :func:`record_ladder_result` —
there is no hidden hook inside the router or the ladder; the caller passes
the result dict it already holds ("available at call time"). Re-recording the
same operation replaces its entry (entries are keyed by ``id``), so the
record always reflects the latest proven state, exactly like the F6 receipts
store it sits beside.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

SCHEMA_ID = "skill6-method-decision/1"
UNIFIED_FILENAME = "method-decision.json"
_PAGE_RECORD_PREFIX = "method-decision-"
_PAGE_RECORD_SUFFIX = ".json"


class MethodDecisionRecordError(ValueError):
    """Raised when a source outcome cannot be honestly aggregated — an
    unknown object type / surface, or a router result with no receipt and
    no caller-supplied identity. Never silently defaulted, matching
    ``ghl_method.MethodDecisionError``."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Operation-class mapping tables (see module docstring) ────────────────────

OBJECT_TYPE_OPERATION_CLASS: Dict[str, str] = {
    "custom_field": "crm_product_write",
    "custom_value": "crm_product_write",
    "tag": "crm_product_write",
    "contact": "crm_product_write",
    "product": "crm_product_write",
    "subaccount": "crm_product_write",
    "snapshot": "crm_product_write",
    "media": "media_upload",
    "workflow": "workflow_write",
    "workflow_trigger": "workflow_write",
    "funnel": "visual_builder_write",
    "website": "visual_builder_write",
    "page": "visual_builder_write",
    "form": "visual_builder_write",
    "survey": "visual_builder_write",
    "community": "visual_builder_write",
    "course": "visual_builder_write",
    "channel": "visual_builder_write",
}

LADDER_SURFACE_OPERATION_CLASS: Dict[str, str] = {
    "page": "visual_builder_write",
    "funnel": "visual_builder_write",
    "form": "visual_builder_write",
    "survey": "visual_builder_write",
    "community": "visual_builder_write",
    "course": "visual_builder_write",
    "workflow": "workflow_write",
    "media": "media_upload",
    "pipeline": "crm_product_write",
}

#: Step-1 classes no current source system produces (see docstring).
UNEMITTED_OPERATION_CLASSES = ("metadata_read", "payment_configuration", "publish")


# ── Record skeleton / persistence ─────────────────────────────────────────────

def unified_record_path(run_dir: str) -> str:
    """The unified record's path: ``<run_dir>/routing/method-decision.json``
    (the exact name SKILL.md's Phase-5 table already promises)."""
    return os.path.join(str(run_dir), "routing", UNIFIED_FILENAME)


def _new_record(run_dir: str, *, run_id: Optional[str] = None,
                location_ref: Optional[str] = None,
                publish_gate: Optional[str] = None,
                capabilities_observed: Optional[List[str]] = None) -> dict:
    return {
        "schema": SCHEMA_ID,
        "runId": run_id or os.path.basename(os.path.normpath(str(run_dir))) or "run",
        "generatedAt": _now(),
        "scope": {
            "locationRef": location_ref,
            "publishGate": publish_gate if publish_gate is not None else "unknown",
        },
        "capabilitiesObserved": list(capabilities_observed or []),
        "operations": [],
    }


def load_unified_record(run_dir: str) -> Optional[dict]:
    """Read the unified record if one exists (None when absent). Raises
    :class:`MethodDecisionRecordError` on a corrupt or foreign-schema file —
    a record this module cannot recognize must not be silently overwritten."""
    path = unified_record_path(run_dir)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        record = json.load(fh)
    if not isinstance(record, dict) or record.get("schema") != SCHEMA_ID:
        raise MethodDecisionRecordError(
            f"{path} exists but is not a {SCHEMA_ID} record — refusing to "
            "overwrite a file this module does not own"
        )
    return record


def _load_or_new(run_dir: str, *, run_id=None, location_ref=None,
                 publish_gate=None, capabilities_observed=None) -> dict:
    record = load_unified_record(run_dir)
    if record is None:
        return _new_record(run_dir, run_id=run_id, location_ref=location_ref,
                           publish_gate=publish_gate,
                           capabilities_observed=capabilities_observed)
    # Caller-supplied scope/capability facts update the record; omitted ones
    # keep what earlier calls recorded.
    if run_id:
        record["runId"] = run_id
    if location_ref is not None:
        record.setdefault("scope", {})["locationRef"] = location_ref
    if publish_gate is not None:
        record.setdefault("scope", {})["publishGate"] = publish_gate
    if capabilities_observed:
        merged = list(record.get("capabilitiesObserved") or [])
        for ref in capabilities_observed:
            if ref not in merged:
                merged.append(ref)
        record["capabilitiesObserved"] = merged
    return record


def write_unified_record(run_dir: str, record: dict) -> str:
    """Persist the unified record (write-then-rename, the ``ghl_receipts``
    discipline, so a killed process never leaves a half-written record).
    Entries are stored sorted by ``id`` for a stable, diffable file."""
    record = dict(record)
    record["generatedAt"] = _now()
    ops = list(record.get("operations") or [])
    ops.sort(key=lambda e: str(e.get("id", "")))
    record["operations"] = ops
    path = unified_record_path(run_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)
    return path


def _upsert(record: dict, entries: List[dict]) -> dict:
    by_id = {e.get("id"): e for e in record.get("operations") or []}
    for entry in entries:
        by_id[entry["id"]] = entry
    record["operations"] = list(by_id.values())
    return record


def _rel_ref(path: Optional[str], run_dir: Optional[str]) -> Optional[str]:
    """Evidence refs are stored relative to the run dir when the path lives
    under it (stable across machines); otherwise the path is kept as given."""
    if not path:
        return None
    if run_dir:
        try:
            rel = os.path.relpath(path, str(run_dir))
        except ValueError:
            return path
        if not rel.startswith(".."):
            return rel
    return path


def _entry_scope(record: dict, location_ref: Optional[str] = None) -> dict:
    scope = dict(record.get("scope") or {})
    if location_ref:
        scope["locationRef"] = location_ref
    scope.setdefault("locationRef", None)
    scope.setdefault("publishGate", "unknown")
    return scope


# ── Source 1: ghl_method per-page records ─────────────────────────────────────

def page_record_filenames(run_dir: str) -> List[str]:
    """Every per-page method-decision filename in ``<run_dir>/routing`` —
    ``method-decision-<page>.json`` only. The unified record itself
    (``method-decision.json``) and the site record
    (``site-method-decision.json``) never match this pattern."""
    routing = os.path.join(str(run_dir), "routing")
    if not os.path.isdir(routing):
        return []
    return sorted(
        fn for fn in os.listdir(routing)
        if fn.startswith(_PAGE_RECORD_PREFIX) and fn.endswith(_PAGE_RECORD_SUFFIX)
    )


def entries_from_page_record(page_record: dict, source_filename: str,
                             record: dict) -> List[dict]:
    """Translate ONE per-page record dict (the exact shape
    ``ghl_method.decide_and_record`` writes) into unified entries: one for
    the page itself, plus one per widget block the classifier detected."""
    page_name = str(page_record.get("page_name") or source_filename)
    method = page_record.get("method")
    reason = str(page_record.get("reason") or "")
    score = page_record.get("score")
    threshold = page_record.get("threshold")
    signals = page_record.get("signals") or []

    capabilities = []
    if score is not None:
        capabilities.append(f"classifier-score:{score}")
    if threshold is not None:
        capabilities.append(f"classifier-threshold:{threshold}")
    for sig in signals:
        if isinstance(sig, dict) and sig.get("name"):
            capabilities.append(f"signal:{sig['name']}")

    if method == "vercel_embed":
        rejected = [{
            "lane": "direct",
            "reason": f"rejected by the classifier: {reason}",
        }]
    else:
        rejected = [{
            "lane": "vercel_embed",
            "reason": f"rejected by the classifier: {reason}",
        }]

    entries: List[dict] = [{
        "id": f"page:{page_name}",
        "source": "ghl_method",
        "operation": page_name,
        "operationClass": "visual_builder_write",
        "chosenLane": method,
        "outcome": "decided",
        "capabilitiesObserved": capabilities,
        "rejectedAlternatives": rejected,
        "scope": _entry_scope(record),
        "evidenceRefs": [f"routing/{source_filename}"],
        "detail": {
            "score": score,
            "threshold": threshold,
            "hardForced": page_record.get("hard_forced"),
            "decidedAt": page_record.get("decided_at"),
        },
    }]

    for w in page_record.get("widgets") or []:
        if not isinstance(w, dict):
            continue
        kind = w.get("kind")
        block_key = w.get("block_key")
        entries.append({
            "id": f"page:{page_name}#widget:{block_key}",
            "source": "ghl_method",
            "operation": f"{page_name} widget block {block_key}",
            "operationClass": "visual_builder_write",
            "chosenLane": "widget",
            "outcome": "decided",
            "capabilitiesObserved": [f"widget-kind:{kind}"] if kind else [],
            "rejectedAlternatives": [{
                "lane": "static_html",
                "reason": "faking a form/calendar block as static HTML is "
                          "forbidden; the block routes to the native "
                          "GoHighLevel widget embed regardless of the "
                          "page's own method (ghl_method doctrine)",
            }],
            "scope": _entry_scope(record, location_ref=w.get("location_id") or None),
            "evidenceRefs": [f"routing/{source_filename}"],
            "detail": {
                "widgetKind": kind,
                "blockKey": block_key,
                "objectId": w.get("object_id") or "",
            },
        })
    return entries


def refresh_from_page_records(run_dir: str, *, run_id: Optional[str] = None,
                              location_ref: Optional[str] = None,
                              publish_gate: Optional[str] = None,
                              capabilities_observed: Optional[List[str]] = None) -> dict:
    """Rebuild the unified record's ``ghl_method`` entries from the per-page
    record FILES on disk, preserving any router/ladder entries already
    recorded, and write the record. Called by
    ``ghl_method.decide_and_record`` after every page decision; also safe to
    call standalone at any point in a run. An unreadable per-page file is
    surfaced under ``warnings`` (the receipts store's ``unreadable``
    discipline), never silently dropped and never counted as a decision."""
    record = _load_or_new(run_dir, run_id=run_id, location_ref=location_ref,
                          publish_gate=publish_gate,
                          capabilities_observed=capabilities_observed)
    # Drop prior page entries; they are re-derived from disk below so the
    # unified record can never claim a page whose per-page file is gone.
    record["operations"] = [
        e for e in record.get("operations") or [] if e.get("source") != "ghl_method"
    ]
    record.pop("warnings", None)

    entries: List[dict] = []
    warnings: List[str] = []
    routing = os.path.join(str(run_dir), "routing")
    for fn in page_record_filenames(run_dir):
        try:
            with open(os.path.join(routing, fn), "r", encoding="utf-8") as fh:
                page_record = json.load(fh)
            if not isinstance(page_record, dict):
                raise ValueError("per-page record is not a JSON object")
        except Exception as exc:  # noqa: BLE001 — surfaced as a warning entry
            warnings.append(f"unreadable-page-record:{fn}: {exc}")
            continue
        entries.extend(entries_from_page_record(page_record, fn, record))
    if warnings:
        record["warnings"] = warnings
    _upsert(record, entries)
    write_unified_record(run_dir, record)
    return load_unified_record(run_dir) or record


# ── Source 2: ghl_object_router outcomes ──────────────────────────────────────

def entry_from_router_result(result: dict, *, object_type: Optional[str] = None,
                             slug: Optional[str] = None,
                             run_dir: Optional[str] = None,
                             record: Optional[dict] = None) -> dict:
    """Translate ONE ``ghl_object_router.execute_write`` result dict (the
    shape available to the caller at call time) into a unified entry. The
    object's identity and the chosen rail come from the result's own F6
    receipt when present; ``object_type``/``slug`` keywords override."""
    if not isinstance(result, dict):
        raise MethodDecisionRecordError(
            f"router result must be a dict, got {type(result).__name__!r}"
        )
    receipt = result.get("receipt") or {}
    object_type = object_type or receipt.get("object_type")
    slug = slug or receipt.get("slug")
    if not object_type:
        raise MethodDecisionRecordError(
            "router result carries no receipt.object_type and no "
            "object_type was supplied — refusing to guess the operation"
        )
    if object_type not in OBJECT_TYPE_OPERATION_CLASS:
        raise MethodDecisionRecordError(
            f"object type {object_type!r} has no operation-class mapping; "
            "add it to OBJECT_TYPE_OPERATION_CLASS (with the mapping "
            "reviewed) instead of letting it fall through unmapped"
        )

    # The declared rail order is the router's own data — read it, never
    # re-declare it here.
    import ghl_object_router as _router
    try:
        route = _router.route(object_type)
        rail_names = route.rail_names()
    except KeyError:
        rail_names = []

    chosen = result.get("rail") or receipt.get("rail")
    action = result.get("action") or receipt.get("action")

    rejected: List[dict] = []
    for name in rail_names:
        if name == chosen:
            continue
        if chosen is None:
            reason = ("declared rail in the router's ordered list; the run "
                      "recorded no successful rail for this operation")
        elif rail_names.index(name) < rail_names.index(chosen):
            reason = ("earlier in the router's declared rail order; not the "
                      "rail recorded as used for this operation")
        else:
            reason = ("later in the router's declared rail order; not "
                      "reached once the chosen rail produced the recorded "
                      "outcome")
        rejected.append({"lane": name, "reason": reason})

    capabilities: List[str] = []
    tier = result.get("tier", receipt.get("tier"))
    if tier is not None:
        capabilities.append(f"tier:{tier}")
    if receipt.get("token_context"):
        capabilities.append(f"token-context:{receipt['token_context']}")
    if receipt.get("tool"):
        capabilities.append(f"tool:{receipt['tool']}")

    evidence: List[str] = []
    ref = _rel_ref(result.get("receipt_path"), run_dir)
    if ref:
        evidence.append(ref)

    scope_record = record if record is not None else _new_record(run_dir or "")
    return {
        "id": f"object:{object_type}:{slug}",
        "source": "ghl_object_router",
        "operation": f"{object_type} {slug}".strip(),
        "operationClass": OBJECT_TYPE_OPERATION_CLASS[object_type],
        "chosenLane": chosen,
        "outcome": action,
        "capabilitiesObserved": capabilities,
        "rejectedAlternatives": rejected,
        "scope": _entry_scope(scope_record),
        "evidenceRefs": evidence,
        "detail": {
            "boardNote": result.get("board_note"),
            "hasError": bool(result.get("error") or receipt.get("error")),
            "responseId": receipt.get("response_id"),
            "verifyOk": (receipt.get("verify") or {}).get("ok"),
        },
    }


def record_router_result(run_dir: str, result: dict, *,
                         object_type: Optional[str] = None,
                         slug: Optional[str] = None,
                         run_id: Optional[str] = None,
                         location_ref: Optional[str] = None,
                         publish_gate: Optional[str] = None,
                         capabilities_observed: Optional[List[str]] = None) -> dict:
    """Upsert one object-router outcome into the run's unified record and
    write it. The explicit call is the integration seam: the run passes the
    ``execute_write`` result it already holds; nothing is hooked or hidden
    inside the router."""
    record = _load_or_new(run_dir, run_id=run_id, location_ref=location_ref,
                          publish_gate=publish_gate,
                          capabilities_observed=capabilities_observed)
    entry = entry_from_router_result(result, object_type=object_type,
                                     slug=slug, run_dir=run_dir, record=record)
    _upsert(record, [entry])
    write_unified_record(run_dir, record)
    return load_unified_record(run_dir) or record


# ── Source 3: ghl_fallback_ladder outcomes ────────────────────────────────────

def entry_from_ladder_result(ladder_result: Any, *,
                             receipt_path: Optional[str] = None,
                             run_dir: Optional[str] = None,
                             record: Optional[dict] = None) -> dict:
    """Translate ONE ladder outcome — a ``LadderResult`` or its ``to_dict()``
    shape — into a unified entry. Failed attempts become the rejected
    alternatives, with the run's own taxonomy code + detail as the reason."""
    if hasattr(ladder_result, "to_dict"):
        ladder_result = ladder_result.to_dict()
    if not isinstance(ladder_result, dict):
        raise MethodDecisionRecordError(
            f"ladder result must be a dict or LadderResult, got "
            f"{type(ladder_result).__name__!r}"
        )
    surface = ladder_result.get("surface")
    if surface not in LADDER_SURFACE_OPERATION_CLASS:
        raise MethodDecisionRecordError(
            f"ladder surface {surface!r} has no operation-class mapping; "
            "add it to LADDER_SURFACE_OPERATION_CLASS (with the mapping "
            "reviewed) instead of letting it fall through unmapped"
        )

    order = list(ladder_result.get("order") or [])
    attempts = ladder_result.get("attempts") or []
    attempted = {a.get("transport") for a in attempts if isinstance(a, dict)}
    chosen = ladder_result.get("succeeded_rung")
    active = bool(ladder_result.get("ladder_active"))

    rejected: List[dict] = []
    for a in attempts:
        if not isinstance(a, dict) or a.get("ok"):
            continue
        code = a.get("code") or "UNKNOWN"
        detail = str(a.get("detail") or "").strip()
        reason = f"{code}: {detail}" if detail else str(code)
        rejected.append({"lane": a.get("transport"), "reason": reason})
    for name in order:
        if name in attempted or name == chosen:
            continue
        if not active:
            reason = ("declared rung not attempted: the fallback ladder flag "
                      "is off, so only the first declared rung is attempted")
        elif ladder_result.get("ok"):
            reason = ("declared rung not attempted: the ladder stops at the "
                      "first successful rung")
        else:
            reason = "declared rung not attempted"
        rejected.append({"lane": name, "reason": reason})

    evidence: List[str] = []
    ref = _rel_ref(receipt_path, run_dir)
    if ref:
        evidence.append(ref)

    scope_record = record if record is not None else _new_record(run_dir or "")
    return {
        "id": f"ladder:{surface}",
        "source": "ghl_fallback_ladder",
        "operation": f"{surface} fallback ladder",
        "operationClass": LADDER_SURFACE_OPERATION_CLASS[surface],
        "chosenLane": chosen,
        "outcome": ladder_result.get("decision"),
        "capabilitiesObserved": [f"ladder-active:{str(active).lower()}"],
        "rejectedAlternatives": rejected,
        "scope": _entry_scope(scope_record),
        "evidenceRefs": evidence,
        "detail": {
            "surface": surface,
            "order": order,
            "ok": ladder_result.get("ok"),
            "ladderRunId": ladder_result.get("run_id"),
            "decidedAt": ladder_result.get("decided_at"),
        },
    }


def record_ladder_result(run_dir: str, ladder_result: Any, *,
                         receipt_path: Optional[str] = None,
                         run_id: Optional[str] = None,
                         location_ref: Optional[str] = None,
                         publish_gate: Optional[str] = None,
                         capabilities_observed: Optional[List[str]] = None) -> dict:
    """Upsert one fallback-ladder outcome into the run's unified record and
    write it. Call only when the ladder actually ran for the run — an absent
    ladder leaves no entry, which the record shows honestly (no entry, not
    an invented one)."""
    record = _load_or_new(run_dir, run_id=run_id, location_ref=location_ref,
                          publish_gate=publish_gate,
                          capabilities_observed=capabilities_observed)
    entry = entry_from_ladder_result(ladder_result, receipt_path=receipt_path,
                                     run_dir=run_dir, record=record)
    _upsert(record, [entry])
    write_unified_record(run_dir, record)
    return load_unified_record(run_dir) or record


# ── Self-test — no network, no browser, tmp only ──────────────────────────────

def _selftest() -> int:
    import tempfile

    errors: List[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        routing = os.path.join(tmp, "routing")
        os.makedirs(routing)
        page_record = {
            "page_name": "home",
            "method": "direct",
            "score": 0,
            "threshold": 3,
            "hard_forced": False,
            "signals": [],
            "widgets": [
                {"kind": "form", "block_key": "contact_form",
                 "object_id": "", "location_id": ""},
            ],
            "reason": "DIRECT: no advanced signals detected; default method.",
            "decided_at": "2026-01-01T00:00:00Z",
        }
        with open(os.path.join(routing, "method-decision-home.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(page_record, fh, indent=2)

        record = refresh_from_page_records(tmp, run_id="selftest-run")
        ids = [e["id"] for e in record["operations"]]
        if "page:home" not in ids or "page:home#widget:contact_form" not in ids:
            errors.append(f"page + widget entries missing: {ids}")
        page_entry = next(e for e in record["operations"] if e["id"] == "page:home")
        if page_entry["chosenLane"] != "direct" \
                or page_entry["operationClass"] != "visual_builder_write":
            errors.append(f"page entry mistranslated: {page_entry}")

        record = record_router_result(tmp, {
            "ok": True, "action": "created", "rail": "skill44_caf", "tier": 0,
            "receipt_path": os.path.join(tmp, "ecosystem", "tag-zhc_x.json"),
            "board_note": None, "error": None,
            "receipt": {"object_type": "tag", "slug": "zhc_x",
                        "action": "created", "rail": "skill44_caf", "tier": 0,
                        "token_context": "location_pit",
                        "tool": "caf tags", "response_id": "t1",
                        "verify": {"ok": True}, "error": None},
        })
        obj_entry = next(e for e in record["operations"] if e["id"] == "object:tag:zhc_x")
        if obj_entry["operationClass"] != "crm_product_write" \
                or obj_entry["chosenLane"] != "skill44_caf" \
                or not obj_entry["rejectedAlternatives"]:
            errors.append(f"router entry mistranslated: {obj_entry}")

        record = record_ladder_result(tmp, {
            "surface": "form", "order": ["mcp", "browser"],
            "attempts": [
                {"transport": "mcp", "ok": False, "code": "SELECTOR-MISS",
                 "detail": "fixture miss"},
                {"transport": "browser", "ok": True, "code": None, "detail": ""},
            ],
            "ok": True, "succeeded_rung": "browser", "decision": "SUCCESS",
            "ladder_active": True, "run_id": "abc123", "decided_at": "2026-01-01T00:00:00Z",
        })
        lad_entry = next(e for e in record["operations"] if e["id"] == "ladder:form")
        if lad_entry["chosenLane"] != "browser" \
                or lad_entry["rejectedAlternatives"][0]["lane"] != "mcp" \
                or "SELECTOR-MISS" not in lad_entry["rejectedAlternatives"][0]["reason"]:
            errors.append(f"ladder entry mistranslated: {lad_entry}")

        # The unified file itself is never re-ingested as a page record.
        record2 = refresh_from_page_records(tmp)
        page_ids = [e["id"] for e in record2["operations"] if e["source"] == "ghl_method"]
        if sorted(page_ids) != ["page:home", "page:home#widget:contact_form"]:
            errors.append(f"refresh re-ingested the wrong files: {page_ids}")
        # Router/ladder entries survive a page refresh.
        all_ids = {e["id"] for e in record2["operations"]}
        if "object:tag:zhc_x" not in all_ids or "ladder:form" not in all_ids:
            errors.append(f"refresh dropped non-page entries: {sorted(all_ids)}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — unified method-decision record verified (no network / no browser)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="ghl_method_decision",
        description="Skill-6 unified per-run method-decision record (spec 05 section 4).",
    )
    p.add_argument("--selftest", action="store_true",
                   help="Run the no-network aggregation self-test and exit.")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

__all__ = [
    "SCHEMA_ID",
    "UNIFIED_FILENAME",
    "MethodDecisionRecordError",
    "OBJECT_TYPE_OPERATION_CLASS",
    "LADDER_SURFACE_OPERATION_CLASS",
    "UNEMITTED_OPERATION_CLASSES",
    "unified_record_path",
    "load_unified_record",
    "write_unified_record",
    "page_record_filenames",
    "entries_from_page_record",
    "refresh_from_page_records",
    "entry_from_router_result",
    "record_router_result",
    "entry_from_ladder_result",
    "record_ladder_result",
]

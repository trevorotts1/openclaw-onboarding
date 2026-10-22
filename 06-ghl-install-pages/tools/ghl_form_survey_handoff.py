#!/usr/bin/env python3
"""ghl_form_survey_handoff.py — the ONE Skill 44 → Skill 06 dependency handoff
contract for native FORMS and SURVEYS (Skill 06 v3.0 §3.2 / B06-B08).

WHY THIS EXISTS
---------------
The responsibility split (§3.1) is fixed:

  • Skill 44 (``44-convert-and-flow-operator``, ``caf`` CLI, LOCATION PIT)
    creates or REUSES the approved custom fields and tags, and later owns the
    authorized downstream CRM/workflow wiring + tag behavior.
  • Skill 06 creates or opens the NATIVE form/survey, places the fields,
    configures the UI, saves, captures the native ID/embed, and verifies
    persistence.

Both rails already emitted a dependency PLAN (``ghl_form_builder.plan_dependencies``
/ ``ghl_survey_builder.plan_survey_dependencies``) but neither had a way to
RECEIVE, VALIDATE and RECORD what Skill 44 actually did. Without that, a browser
walk can start against a plan nobody proved, and the classic failure follows: the
browser cannot find a ``zhc_`` field, so a human/agent "fixes" it by creating a
SECOND custom field. This module makes that impossible — the native build refuses
to start unless every planned field/tag carries a proven create/reuse result from
the SAME location.

ONE RECORD (§3.2)
-----------------
    <run>/routing/form-survey-handoff.json     schema skill6-form-survey-handoff/1

carrying, in one place: the approved ``location_ref``, the dependency plan, the
actual field/tag IDs, the create/reuse results, and the dependency verification
receipt.

HARD RULES ENFORCED HERE (each a refusal, never a warning)
----------------------------------------------------------
1. **Missing dependency stops BEFORE mutation** (B06). ``assert_ready_for_native_build``
   raises ``HandoffIncomplete`` for any planned field/tag with no proven result, or
   any plan whose verification receipt is absent/failed. It is called from the
   builders' preflight, i.e. before a browser step is ever emitted.
2. **Never create a duplicate custom field because a lookup missed** (§3.2).
   A result action of ``not_found`` / ``create_failed`` / ``unknown`` is a STOP,
   never a licence to create. Reuse is proven by ID, not by label.
3. **Matching location/account identity on both sides** (§3.2). The Skill 44
   result side, the approved ``location_ref`` and Skill 06's own build location
   must all agree; a mismatch is ``LocationMismatch`` (a contradiction, never a
   pass — same rule as ``ghl_evidence.tenant_binding``).
4. **Never attach tags by inventing a native form setting** (§3.2). Only the two
   documented attachment methods are accepted: a ``Form Submitted → Add Contact
   Tag`` workflow owned by Skill 44, or the built-in hidden Tags object-field.
   Anything else is ``TagAttachmentUnsupported``.
5. **Four distinct operations, four separate receipts** (§3.2): native object
   creation, field creation, embedding and workflow wiring. ``operation_receipt``
   refuses an operation name outside ``OPERATIONS`` and refuses to overwrite a
   receipt with a different native id (a silent re-target is a contradiction).
6. **Uncertain save → reconcile before retry** (B07). ``reconcile_uncertain_save``
   returns an explicit verdict (``reuse`` / ``create`` / ``blocked``); the caller
   may only retry on ``create``. ``blocked`` means read back again — never a blind
   second Save.
7. **Restart/resume reuses the native object id** (B07/§10.1). ``resume_target``
   returns the recorded id so a re-run opens THAT object instead of building a
   second one.

Everything here is pure: no network, no browser, no GHL client, no login code, no
new API client. It consumes dicts the rails already produce and writes one JSON
record. ``--selftest`` is fully offline.

CLI
---
    python3 ghl_form_survey_handoff.py --selftest
    python3 ghl_form_survey_handoff.py --validate <handoff.json> [--build-location ID]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

HANDOFF_SCHEMA = "skill6-form-survey-handoff/1"
HANDOFF_REL = os.path.join("routing", "form-survey-handoff.json")

OBJECT_KINDS = ("form", "survey")

# The four operations §3.2 requires to be DISTINCT with SEPARATE receipts. The
# object kind names WHAT is created; the operation names the step.
OPERATIONS = ("native_create", "field_create", "embed", "workflow_wiring")

# A dependency result action that PROVES the dependency exists. Anything else
# (not_found / create_failed / unknown / absent) is a stop.
PROVEN_ACTIONS = ("reuse", "create")

# The only two documented tag-attachment methods (ghl_form_builder
# ``_tag_attachment_plan``). A native form has no "add tag" setting.
TAG_ATTACHMENT_METHODS = ("workflow", "hidden_field")

# Reconcile verdicts for an uncertain save (B07).
VERDICT_REUSE = "reuse"      # the object IS there — adopt it, do not save again
VERDICT_CREATE = "create"    # proven absent — a retry is safe
VERDICT_BLOCKED = "blocked"  # cannot tell — read back again; NEVER retry blind


class HandoffIncomplete(RuntimeError):
    """The handoff does not prove a dependency. Raised BEFORE any native mutation."""


class LocationMismatch(HandoffIncomplete):
    """Two sides of the handoff name different locations/accounts (contradiction)."""


class TagAttachmentUnsupported(HandoffIncomplete):
    """A tag-attachment method GHL does not offer on a native form/survey."""


class OperationContradiction(AssertionError):
    """Two receipts for the same operation disagree about the native object id."""


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------
def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _norm(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def make_handoff(
    object_kind: str,
    location_ref: Dict[str, Any],
    dependency_plan: Dict[str, Any],
    *,
    object_name: str = "",
    run_id: Optional[str] = None,
    handoff_id: Optional[str] = None,
) -> dict:
    """Open the ONE handoff record for a form/survey build.

    ``location_ref`` = the APPROVED location/account the build is authorized for,
    e.g. ``{"location_id": "...", "account_id": "...", "approved": true,
    "source": "dispatcher"}``. ``dependency_plan`` is the plan the owning builder
    emitted (``plan_dependencies`` / ``plan_survey_dependencies``).
    """
    kind = _norm(object_kind).lower()
    if kind not in OBJECT_KINDS:
        raise ValueError(f"object_kind must be one of {OBJECT_KINDS}, got {object_kind!r}")
    if not isinstance(dependency_plan, dict) or "custom_fields" not in dependency_plan:
        raise ValueError("dependency_plan must be the plan dict from the owning builder "
                         "(carrying 'custom_fields')")
    loc = _norm(location_ref.get("location_id")) if isinstance(location_ref, dict) else ""
    if not loc:
        raise ValueError("location_ref.location_id is required (the approved location)")
    return {
        "schema": HANDOFF_SCHEMA,
        "handoff_id": handoff_id or f"{kind}-{loc}-{int(time.time())}",
        "created_at": _ts(),
        "object_kind": kind,
        "object_name": object_name,
        "run_id": run_id,
        "location_ref": {
            "location_id": loc,
            "account_id": _norm(location_ref.get("account_id")) or None,
            "approved": bool(location_ref.get("approved", False)),
            "source": _norm(location_ref.get("source")) or None,
        },
        "dependency_plan": dependency_plan,
        "dependency_results": {
            "location_id": None,
            "account_id": None,
            "custom_fields": [],
            "tags": [],
            "received_at": None,
        },
        "dependency_verification": {"ok": False, "reason": "no verification receipt yet"},
        "operations": {op: None for op in OPERATIONS},
        "native_object": {"id": None, "id_source": None, "name": None},
        "tag_attachment": None,
        "history": [],
    }


def _append_history(record: dict, event: str, **detail: Any) -> None:
    record.setdefault("history", []).append({"ts": _ts(), "event": event, **detail})


# ---------------------------------------------------------------------------
# Step 1 — receive what Skill 44 actually did
# ---------------------------------------------------------------------------
def record_dependency_results(
    record: dict,
    *,
    location_id: str,
    custom_fields: List[dict],
    tags: Optional[List[dict]] = None,
    account_id: Optional[str] = None,
) -> dict:
    """Stamp Skill 44's ACTUAL results onto the handoff (mutates + returns it).

    Each custom field entry: ``{"field_key", "id", "action", "label"?}`` where
    ``action`` is one of ``reuse`` / ``create`` / ``not_found`` / ``create_failed``
    / ``unknown``. Each tag entry: ``{"tag", "id", "action"}``.

    A location that disagrees with the approved ``location_ref`` raises
    ``LocationMismatch`` — the results are NOT recorded, so nothing downstream can
    treat them as proven.
    """
    approved = _norm(record["location_ref"]["location_id"])
    got = _norm(location_id)
    if not got:
        raise LocationMismatch("Skill 44 dependency results carry no location_id — "
                               "cannot prove the dependencies are on the approved location")
    if got != approved:
        raise LocationMismatch(
            f"dependency results are for location {got!r} but the build is approved for "
            f"{approved!r}; refusing to record cross-tenant dependencies")
    ref_account = _norm(record["location_ref"].get("account_id"))
    got_account = _norm(account_id)
    if ref_account and got_account and ref_account != got_account:
        raise LocationMismatch(
            f"dependency results are for account {got_account!r} but the build is approved "
            f"for account {ref_account!r}")

    record["dependency_results"] = {
        "location_id": got,
        "account_id": got_account or None,
        "custom_fields": [dict(f) for f in (custom_fields or [])],
        "tags": [dict(t) for t in (tags or [])],
        "received_at": _ts(),
    }
    _append_history(record, "dependency_results_recorded",
                    custom_fields=len(custom_fields or []), tags=len(tags or []))
    return record


# ---------------------------------------------------------------------------
# Step 2 — the verification receipt (read-back proof, not a claim)
# ---------------------------------------------------------------------------
def _result_index(results: List[dict], key_name: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for r in results or []:
        if not isinstance(r, dict):
            continue
        key = _norm(r.get(key_name)).lower()
        if key:
            out[key] = r
    return out


def _planned_keys(record: dict) -> Tuple[List[str], List[str]]:
    plan = record["dependency_plan"]
    fields = [_norm(f.get("field_key")).lower() for f in plan.get("custom_fields", [])
              if _norm(f.get("field_key"))]
    tags = [_norm(t.get("tag")).lower() for t in plan.get("tags", [])
            if _norm(t.get("tag"))]
    return fields, tags


def verify_dependencies(
    record: dict,
    *,
    readback_field_keys: Optional[List[str]] = None,
    readback_tag_names: Optional[List[str]] = None,
) -> dict:
    """Compare the PLAN against the RESULTS (and, when supplied, a live read-back)
    and stamp ``dependency_verification``.

    ``ok`` requires, for every planned field/tag: a result whose action is
    ``reuse`` or ``create`` AND a non-empty native ``id``; plus (when a read-back is
    supplied) that the key/name is actually present in it. A ``create`` result that
    the read-back does not show is a FAILED verification — the field does not exist,
    so the native build must not start.
    """
    planned_fields, planned_tags = _planned_keys(record)
    results = record["dependency_results"]
    field_idx = _result_index(results.get("custom_fields", []), "field_key")
    tag_idx = _result_index(results.get("tags", []), "tag")
    rb_fields = {_norm(k).lower() for k in (readback_field_keys or [])}
    rb_tags = {_norm(t).lower() for t in (readback_tag_names or [])}
    readback_supplied = readback_field_keys is not None or readback_tag_names is not None

    problems: List[str] = []
    # A build with NO planned dependencies has nothing to prove — that is a
    # legitimate "ok", not a missing delivery. Anything planned DOES need results.
    if results.get("location_id") is None and (planned_fields or planned_tags):
        problems.append("no dependency results recorded (Skill 44 has not delivered)")

    for key in planned_fields:
        r = field_idx.get(key)
        if r is None:
            problems.append(f"custom field {key!r} has no create/reuse result")
            continue
        action = _norm(r.get("action")).lower()
        if action not in PROVEN_ACTIONS:
            problems.append(f"custom field {key!r} result action={action or 'absent'!r} "
                            "proves nothing (never create a duplicate to 'fix' this)")
            continue
        if not _norm(r.get("id")):
            problems.append(f"custom field {key!r} action={action} carries no native id")
            continue
        if readback_supplied and key not in rb_fields:
            problems.append(f"custom field {key!r} claimed {action} but the read-back "
                            "does not contain it")

    for tag in planned_tags:
        r = tag_idx.get(tag)
        if r is None:
            problems.append(f"tag {tag!r} has no create/reuse result")
            continue
        action = _norm(r.get("action")).lower()
        if action not in PROVEN_ACTIONS:
            problems.append(f"tag {tag!r} result action={action or 'absent'!r} proves nothing")
            continue
        if not _norm(r.get("id")):
            problems.append(f"tag {tag!r} action={action} carries no native id")
            continue
        if readback_supplied and tag not in rb_tags:
            problems.append(f"tag {tag!r} claimed {action} but the read-back does not contain it")

    verification = {
        "ok": not problems,
        "verified_at": _ts(),
        "readback_supplied": readback_supplied,
        "planned_custom_fields": planned_fields,
        "planned_tags": planned_tags,
        "problems": problems,
        "reason": "all planned dependencies proven" if not problems else "; ".join(problems),
    }
    record["dependency_verification"] = verification
    _append_history(record, "dependencies_verified", ok=verification["ok"],
                    problems=len(problems))
    return verification


# ---------------------------------------------------------------------------
# Step 3 — THE GATE the builders' preflight calls (before any browser step)
# ---------------------------------------------------------------------------
def assert_ready_for_native_build(record: dict, *, build_location_id: Optional[str] = None,
                                  tag_attachment_method: Optional[str] = None) -> None:
    """Raise ``HandoffIncomplete`` unless the handoff PROVES every dependency.

    Called from preflight, i.e. BEFORE the click list is walked and before any
    native object is created. This is B06: a missing/wrong-tenant dependency stops
    the form/survey before mutation.
    """
    ref = record.get("location_ref") or {}
    approved = _norm(ref.get("location_id"))
    if not approved:
        raise HandoffIncomplete("handoff carries no approved location_ref.location_id")
    if not ref.get("approved"):
        raise HandoffIncomplete(
            f"location_ref {approved!r} is not APPROVED (approved=False); "
            "a native build needs an approved location")

    if build_location_id is not None:
        build_loc = _norm(build_location_id)
        if build_loc != approved:
            raise LocationMismatch(
                f"Skill 06 build location {build_loc!r} != approved handoff location "
                f"{approved!r}")

    verification = record.get("dependency_verification") or {}
    if not verification.get("ok"):
        raise HandoffIncomplete(
            "dependency verification is not ok: "
            + str(verification.get("reason") or "no verification receipt"))

    # Re-check the results directly: a hand-edited record must not slip past a
    # stale verification block.
    results = record.get("dependency_results") or {}
    planned_fields, planned_tags = _planned_keys(record)
    if (planned_fields or planned_tags) and _norm(results.get("location_id")) != approved:
        raise LocationMismatch(
            f"dependency results location {results.get('location_id')!r} != approved "
            f"{approved!r}")
    field_idx = _result_index(results.get("custom_fields", []), "field_key")
    tag_idx = _result_index(results.get("tags", []), "tag")
    for key in planned_fields:
        r = field_idx.get(key) or {}
        if _norm(r.get("action")).lower() not in PROVEN_ACTIONS or not _norm(r.get("id")):
            raise HandoffIncomplete(f"custom field {key!r} is not proven created/reused")
    for tag in planned_tags:
        r = tag_idx.get(tag) or {}
        if _norm(r.get("action")).lower() not in PROVEN_ACTIONS or not _norm(r.get("id")):
            raise HandoffIncomplete(f"tag {tag!r} is not proven created/reused")

    if tag_attachment_method is not None:
        validate_tag_attachment(record, method=tag_attachment_method)


def validate_tag_attachment(record: dict, *, method: Optional[str] = None) -> dict:
    """Accept only the two documented attachment methods (§3.2). Mutates + returns
    the ``tag_attachment`` block. Never invents a native form setting."""
    plan_method = None
    attachment = (record.get("dependency_plan") or {}).get("tag_attachment") or {}
    if isinstance(attachment, dict):
        plan_method = attachment.get("method")
    chosen = _norm(method or plan_method or "workflow").lower()
    if chosen not in TAG_ATTACHMENT_METHODS:
        raise TagAttachmentUnsupported(
            f"tag attachment method {chosen!r} is not a documented GHL capability; "
            f"allowed: {TAG_ATTACHMENT_METHODS}. A native form/survey has NO 'add tag' "
            "setting — wiring belongs to Skill 44.")
    planned_tags = _planned_keys(record)[1]
    block = {
        "method": chosen,
        "owner_skill": "44-convert-and-flow-operator",
        "tags": planned_tags,
        "validated_at": _ts(),
    }
    if chosen == "workflow":
        block["requires"] = "Form Submitted trigger filtered to this native object + "
        block["requires"] += "Add Contact Tag action, built by Skill 44 AFTER the "
        block["requires"] += "native id exists"
    else:
        block["requires"] = "built-in Tags object-field placed HIDDEN with the planned "
        block["requires"] += "values; no native 'tag' setting is used"
    record["tag_attachment"] = block
    _append_history(record, "tag_attachment_validated", method=chosen)
    return block


# ---------------------------------------------------------------------------
# Step 4 — four operations, four receipts
# ---------------------------------------------------------------------------
def operation_receipt(
    record: dict,
    operation: str,
    *,
    state: str,
    native_id: Optional[str] = None,
    evidence: Optional[dict] = None,
) -> dict:
    """Record ONE of the four distinct operations (``OPERATIONS``).

    ``state`` is a free-form outcome label (``done`` / ``pending`` / ``failed`` /
    ``skipped``) recorded verbatim. A receipt for an operation that already exists
    with a DIFFERENT ``native_id`` raises ``OperationContradiction`` — a silent
    re-target would make "which object did we embed?" unanswerable.
    """
    op = _norm(operation)
    if op not in OPERATIONS:
        raise ValueError(f"unknown operation {operation!r}; must be one of {OPERATIONS}")
    existing = (record.get("operations") or {}).get(op)
    new_id = _norm(native_id) or None
    if isinstance(existing, dict) and existing.get("native_id") and new_id \
            and existing["native_id"] != new_id:
        raise OperationContradiction(
            f"operation {op!r} already recorded native_id={existing['native_id']!r}, "
            f"refusing to re-target it to {new_id!r}")
    receipt = {
        "operation": op,
        "object_kind": record.get("object_kind"),
        "state": _norm(state) or "unknown",
        "native_id": new_id,
        "evidence": dict(evidence or {}),
        "ts": _ts(),
    }
    record.setdefault("operations", {})[op] = receipt
    if op == "native_create" and new_id:
        record["native_object"] = {
            "id": new_id,
            "id_source": _norm((evidence or {}).get("id_source")) or "native_create",
            "name": _norm((evidence or {}).get("name")) or record.get("object_name") or None,
        }
    _append_history(record, "operation_recorded", operation=op, state=receipt["state"])
    return receipt


def operations_complete(record: dict) -> dict:
    """Which of the four operations carry a ``done`` receipt (reporting helper)."""
    ops = record.get("operations") or {}
    done = [op for op in OPERATIONS if isinstance(ops.get(op), dict)
            and _norm(ops[op].get("state")).lower() == "done"]
    return {"done": done, "missing": [op for op in OPERATIONS if op not in done],
            "complete": len(done) == len(OPERATIONS)}


# ---------------------------------------------------------------------------
# B07 — uncertain save: reconcile BEFORE any retry
# ---------------------------------------------------------------------------
def reconcile_uncertain_save(
    record: dict,
    *,
    readback: Optional[dict],
    expected_name: Optional[str] = None,
) -> dict:
    """Decide what to do after a Save/Create whose outcome is UNKNOWN (B07).

    ``readback`` is the observed native state: ``{"objects": [{"id", "name"}, …]}``
    (or a single ``{"id", "name"}``), or ``None``/``{"error": …}`` when the read
    itself failed.

      • the recorded native id is present in the read-back → ``reuse`` (adopt it)
      • the read-back succeeded and shows no matching object  → ``create``
      • the read failed, or shows a same-NAME object with a DIFFERENT id → ``blocked``

    ``blocked`` is deliberately not a retry: a same-name/different-id read-back is
    exactly how a duplicate gets created, and a failed read proves nothing.
    """
    recorded_id = _norm((record.get("native_object") or {}).get("id"))
    name = _norm(expected_name) or _norm((record.get("native_object") or {}).get("name"))

    if readback is None or (isinstance(readback, dict) and readback.get("error")):
        verdict = {
            "verdict": VERDICT_BLOCKED,
            "native_id": recorded_id or None,
            "reason": "read-back unavailable/failed — the object's true state is unknown; "
                      "read back again before retrying (never a blind second Save)",
        }
        _append_history(record, "reconcile", verdict=VERDICT_BLOCKED)
        return verdict

    objects: List[dict] = []
    if isinstance(readback, dict):
        if isinstance(readback.get("objects"), list):
            objects = [o for o in readback["objects"] if isinstance(o, dict)]
        elif readback.get("id"):
            objects = [readback]
    ids = {_norm(o.get("id")) for o in objects if _norm(o.get("id"))}

    if recorded_id and recorded_id in ids:
        verdict = {"verdict": VERDICT_REUSE, "native_id": recorded_id,
                   "reason": "recorded native id is present in the read-back — adopt it, "
                             "do NOT save again"}
    else:
        same_name = [o for o in objects
                     if name and _norm(o.get("name")).lower() == name.lower()]
        if same_name:
            verdict = {
                "verdict": VERDICT_BLOCKED,
                "native_id": _norm(same_name[0].get("id")) or None,
                "reason": (f"a same-name object {_norm(same_name[0].get('id'))!r} exists with a "
                           f"different id than recorded {recorded_id or None!r} — reconcile "
                           "manually; creating another would duplicate"),
            }
        else:
            verdict = {"verdict": VERDICT_CREATE, "native_id": None,
                       "reason": "read-back succeeded and shows no matching object — "
                                 "a retry is safe"}
    _append_history(record, "reconcile", verdict=verdict["verdict"])
    return verdict


def resume_target(record: dict) -> Optional[str]:
    """The native object id a resumed run must RE-OPEN rather than rebuild (§10.1)."""
    native = record.get("native_object") or {}
    nid = _norm(native.get("id"))
    if nid:
        return nid
    op = (record.get("operations") or {}).get("native_create") or {}
    return _norm(op.get("native_id")) or None


# ---------------------------------------------------------------------------
# Persistence — one record per run
# ---------------------------------------------------------------------------
def handoff_path(evidence_root: str) -> str:
    return os.path.join(evidence_root, HANDOFF_REL)


def write_handoff(evidence_root: str, record: dict) -> str:
    """Write the handoff atomically (write-then-rename) under ``routing/``."""
    path = handoff_path(evidence_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def load_handoff(evidence_root_or_path: str) -> Optional[dict]:
    """Load a handoff record from a run dir or a direct file path. ``None`` when
    absent/unparseable — the caller decides (a missing handoff is NOT a pass)."""
    path = evidence_root_or_path
    if os.path.isdir(evidence_root_or_path):
        path = handoff_path(evidence_root_or_path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != HANDOFF_SCHEMA:
        return None
    return data


# ---------------------------------------------------------------------------
# CLI / selftest — fully offline
# ---------------------------------------------------------------------------
def _selftest() -> int:  # noqa: C901
    errors: List[str] = []

    def check(label: str, cond: bool) -> None:
        if not cond:
            errors.append(label)

    plan = {
        "custom_fields": [{"field_key": "zhc_podcast_rating", "action": "create"},
                          {"field_key": "zhc_facebook_url", "action": "reuse"}],
        "tags": [{"tag": "zhc_podcast_lead", "action": "create"}],
        "tag_attachment": {"method": "workflow"},
    }
    ref = {"location_id": "LOC1", "account_id": "ACC1", "approved": True,
           "source": "dispatcher"}

    # 1. construction + bad inputs
    rec = make_handoff("form", ref, plan, object_name="ZHC Podcast Signup")
    check("schema", rec["schema"] == HANDOFF_SCHEMA)
    check("ops initialised", set(rec["operations"]) == set(OPERATIONS))
    for bad_kind in ("page", ""):
        try:
            make_handoff(bad_kind, ref, plan)
            errors.append(f"make_handoff must refuse object_kind={bad_kind!r}")
        except ValueError:
            pass
    try:
        make_handoff("form", {"location_id": ""}, plan)
        errors.append("make_handoff must require a location_id")
    except ValueError:
        pass

    # 2. the gate STOPS before mutation when nothing has been delivered (B06)
    try:
        assert_ready_for_native_build(rec)
        errors.append("gate must refuse a handoff with no dependency results")
    except HandoffIncomplete:
        pass

    # 3. wrong tenant is refused on the result side (both sides must match)
    try:
        record_dependency_results(rec, location_id="LOC_OTHER", custom_fields=[], tags=[])
        errors.append("record_dependency_results must refuse a different location")
    except LocationMismatch:
        pass
    try:
        record_dependency_results(rec, location_id="LOC1", account_id="ACC_OTHER",
                                  custom_fields=[], tags=[])
        errors.append("record_dependency_results must refuse a different account")
    except LocationMismatch:
        pass
    check("mismatch not recorded", rec["dependency_results"]["location_id"] is None)

    # 4. an unapproved location is refused even when fully proven
    unapproved = make_handoff("form", {**ref, "approved": False}, plan)
    record_dependency_results(
        unapproved, location_id="LOC1", account_id="ACC1",
        custom_fields=[{"field_key": "zhc_podcast_rating", "id": "CF1", "action": "create"},
                       {"field_key": "zhc_facebook_url", "id": "CF2", "action": "reuse"}],
        tags=[{"tag": "zhc_podcast_lead", "id": "TG1", "action": "create"}])
    verify_dependencies(unapproved)
    try:
        assert_ready_for_native_build(unapproved)
        errors.append("gate must refuse an unapproved location_ref")
    except HandoffIncomplete:
        pass

    # 5. pre-existing fields/tags reuse + create both satisfy the gate
    record_dependency_results(
        rec, location_id="LOC1", account_id="ACC1",
        custom_fields=[{"field_key": "zhc_podcast_rating", "id": "CF1", "action": "create"},
                       {"field_key": "zhc_facebook_url", "id": "CF2", "action": "reuse"}],
        tags=[{"tag": "zhc_podcast_lead", "id": "TG1", "action": "create"}])
    v = verify_dependencies(rec, readback_field_keys=["zhc_podcast_rating", "zhc_facebook_url"],
                            readback_tag_names=["zhc_podcast_lead"])
    check("verification ok", v["ok"])
    assert_ready_for_native_build(rec, build_location_id="LOC1",
                                 tag_attachment_method="workflow")
    check("tag attachment stamped", rec["tag_attachment"]["method"] == "workflow")

    # 6. a lookup MISS must never license a create (no duplicate fields)
    miss = make_handoff("form", ref, plan)
    record_dependency_results(
        miss, location_id="LOC1",
        custom_fields=[{"field_key": "zhc_podcast_rating", "id": None, "action": "not_found"},
                       {"field_key": "zhc_facebook_url", "id": "CF2", "action": "reuse"}],
        tags=[{"tag": "zhc_podcast_lead", "id": "TG1", "action": "create"}])
    mv = verify_dependencies(miss)
    check("not_found fails verification", not mv["ok"])
    try:
        assert_ready_for_native_build(miss)
        errors.append("gate must refuse a not_found dependency (never duplicate)")
    except HandoffIncomplete:
        pass

    # 7. a create claimed but absent from the read-back is a FAILED verification
    ghost = make_handoff("form", ref, plan)
    record_dependency_results(
        ghost, location_id="LOC1",
        custom_fields=[{"field_key": "zhc_podcast_rating", "id": "CF1", "action": "create"},
                       {"field_key": "zhc_facebook_url", "id": "CF2", "action": "reuse"}],
        tags=[{"tag": "zhc_podcast_lead", "id": "TG1", "action": "create"}])
    gv = verify_dependencies(ghost, readback_field_keys=["zhc_facebook_url"],
                             readback_tag_names=["zhc_podcast_lead"])
    check("readback miss fails verification", not gv["ok"])

    # 8. build-side location mismatch is refused
    try:
        assert_ready_for_native_build(rec, build_location_id="LOC_ELSEWHERE")
        errors.append("gate must refuse a build location != approved location")
    except LocationMismatch:
        pass

    # 9. invented tag attachment settings are refused
    for bad in ("native_setting", "form_setting", "auto"):
        try:
            validate_tag_attachment(rec, method=bad)
            errors.append(f"tag attachment method {bad!r} must be refused")
        except TagAttachmentUnsupported:
            pass

    # 10. four distinct operations, separate receipts; no silent re-target
    operation_receipt(rec, "native_create", state="done", native_id="FORM123",
                      evidence={"id_source": "iframe_src", "name": "ZHC Podcast Signup"})
    operation_receipt(rec, "field_create", state="done", native_id="FORM123")
    operation_receipt(rec, "embed", state="done", evidence={"snippet_len": 120})
    operation_receipt(rec, "workflow_wiring", state="pending")
    check("native id captured", rec["native_object"]["id"] == "FORM123")
    check("ops incomplete while wiring pending", not operations_complete(rec)["complete"])
    operation_receipt(rec, "workflow_wiring", state="done", native_id="WF9")
    check("ops complete", operations_complete(rec)["complete"])
    try:
        operation_receipt(rec, "native_create", state="done", native_id="FORM999")
        errors.append("a re-targeted native_create receipt must be refused")
    except OperationContradiction:
        pass
    try:
        operation_receipt(rec, "make_coffee", state="done")
        errors.append("unknown operation must be refused")
    except ValueError:
        pass

    # 11. B07 — interrupted save: reconcile before retry
    rb_hit = reconcile_uncertain_save(rec, readback={"objects": [
        {"id": "FORM123", "name": "ZHC Podcast Signup"}]})
    check("recorded id present → reuse", rb_hit["verdict"] == VERDICT_REUSE)
    rb_gone = reconcile_uncertain_save(rec, readback={"objects": []})
    check("proven absent → create", rb_gone["verdict"] == VERDICT_CREATE)
    rb_fail = reconcile_uncertain_save(rec, readback={"error": "timeout"})
    check("failed read → blocked", rb_fail["verdict"] == VERDICT_BLOCKED)
    rb_dup = reconcile_uncertain_save(rec, readback={"objects": [
        {"id": "FORM_OTHER", "name": "ZHC Podcast Signup"}]})
    check("same name, different id → blocked", rb_dup["verdict"] == VERDICT_BLOCKED)

    # 12. restart/resume reuses the native object id
    check("resume target", resume_target(rec) == "FORM123")
    check("resume target absent when nothing built", resume_target(make_handoff("form", ref, plan)) is None)

    # 13. survey kind carries the same contract
    srec = make_handoff("survey", ref, {"custom_fields": [], "tags": []})
    verify_dependencies(srec)
    assert_ready_for_native_build(srec, build_location_id="LOC1")
    check("survey kind", srec["object_kind"] == "survey")

    # 14. persistence round-trip
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = write_handoff(tmp, rec)
        check("handoff path", path == handoff_path(tmp))
        loaded = load_handoff(tmp)
        check("round-trip", isinstance(loaded, dict) and loaded["native_object"]["id"] == "FORM123")
        check("absent handoff is None", load_handoff(os.path.join(tmp, "nope")) is None)

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        print(f"\n[selftest] FAIL — {len(errors)} error(s)")
        return 1
    print("[selftest] PASS — one handoff record; gate stops before mutation; tenant "
          "identity enforced both sides; no duplicate fields; 4 separate operation "
          "receipts; reconcile-before-retry; resume reuses native id (offline)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_form_survey_handoff",
        description="Skill 44 → Skill 06 form/survey dependency handoff contract. Offline.")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--validate", metavar="HANDOFF_JSON",
                   help="validate a handoff record against the native-build gate")
    p.add_argument("--build-location", default=None,
                   help="Skill 06's own build location (checked against the approved ref)")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.validate:
        record = load_handoff(args.validate)
        if record is None:
            print(f"REFUSED: {args.validate!r} is not a {HANDOFF_SCHEMA} record")
            return 2
        try:
            assert_ready_for_native_build(record, build_location_id=args.build_location)
        except HandoffIncomplete as exc:
            print(f"REFUSED ({type(exc).__name__}): {exc}")
            return 1
        print(f"READY: {record['object_kind']} on location "
              f"{record['location_ref']['location_id']} — all dependencies proven")
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

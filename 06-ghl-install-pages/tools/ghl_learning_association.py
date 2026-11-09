#!/usr/bin/env python3
"""ghl_learning_association.py — Skill 6 narrow operator: attach / inspect / detach an
EXISTING GHL course in a Community group's Learning tab (spec v3.0 §9.4, defect D10).

The association is a SEPARATE relationship object from the course. This module:
  * validates a relationship plan (same location, resolved course id, resolved group,
    approved access policy, approval reference) BEFORE touching a browser;
  * enumerates existing associations first and returns an idempotent verified result
    when the intended course + policy already match (never a duplicate attach);
  * attaches by selecting the EXISTING course (never "Create new course") and setting
    only the approved access policy;
  * detaches ONLY the relationship — it never deletes the course, and it proves the
    course still exists after the detach;
  * writes a relationship receipt separate from the course-create receipt.

It is a NARROW operator: the caller (ghl_community_builder / Skill 6 router) owns the
seeded browser session. This module never spawns an independent browser and never
implements a second login. Live selectors live in
`selectors-live-communities-courses.json` under `community.learning.*`; every one that
has not been captured live is `capture-pending`, so the live path STOP-and-reports
(D8: zero invented selectors).

FROZEN INTERFACE — WF09-CP01 (consumed by WF07 routing and WF13 launch/fulfillment):
    plan_association(task: dict) -> dict
    read_associations(session, sels, plan) -> list[dict]
    attach_existing_course(session, sels, plan, evidence_root) -> dict
    detach_course(session, sels, plan, evidence_root) -> dict
    execute(session, sels, plan, evidence_root) -> dict
    build_association(task, evidence_root, *, dry_run=True, session=None) -> dict
Result envelope keys (stable): ok, object_type, operation, location_id,
course_product_id, group_ref, action, verify, artifact_path, receipt_path, dry_run,
error. A later change is WF09-CP02 with a migration note and the affected-consumer list.

Usage:
    python3 ghl_learning_association.py --selftest
    python3 ghl_learning_association.py --dry-run --plan-json association.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_community_builder as _cb  # noqa: E402  (shared selector gate + receipts + executor)

StopAndReport = _cb.StopAndReport

OBJECT_TYPE = "learning_association"
SCHEMA_VERSION = "1.0.0"
ALLOWED_MODES = ("all_members", "level", "time_limited", "paid")
DEFAULT_POLICY_LABEL = {"all_members": "All members"}
# A relationship may NEVER be created through a course-create control (spec §9.4 step 4).
FORBIDDEN_SELECTOR_TOKENS = ("create_new_course", "create_course", "course.create_modal")
_BILLING_KEYS = ("price", "amount", "recurring", "billing", "subscription_price")


def _ts() -> str:
    return _cb._ts()


def _write_json(path: str, data: Any) -> None:
    _cb._write_json(path, data)


def _log(msg: str) -> None:
    _cb._log(msg)


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _norm(text: str) -> str:
    return " ".join((text or "").split()).strip().lower()


# ---------------------------------------------------------------------------
# THINK layer — validate the relationship plan (no browser, no network)
# ---------------------------------------------------------------------------
def plan_association(task: dict) -> dict:
    """Validate + normalize a relationship plan. Raises StopAndReport on any unsafe
    or unresolvable input (wrong location, create-new intent, unpaid approval, etc.)."""
    if not isinstance(task, dict):
        raise StopAndReport("plan.shape", "association plan must be a JSON object")

    location_id = (task.get("location_id") or "").strip()
    if not location_id:
        raise StopAndReport("plan.location", "location_id is required (sub-account gate)")

    course_product_id = str(task.get("course_product_id") or "").strip()
    if _is_blank(course_product_id) or course_product_id.lower() in (
            "new", "create", "create_new", "new_course", "tbd"):
        raise StopAndReport(
            "plan.course",
            "course_product_id must reference an EXISTING resolved course; this operator "
            "never creates a course (use ghl_course_builder, then attach by its id).")
    if task.get("create_course") or task.get("create_new_course"):
        raise StopAndReport(
            "plan.course",
            "create_course intent supplied — Learning association attaches an EXISTING "
            "course only (spec §9.4 step 4).")

    group_ref = task.get("group_ref") or {}
    if not isinstance(group_ref, dict):
        raise StopAndReport("plan.group", "group_ref must be an object")
    group_id = str(group_ref.get("group_id") or "").strip()
    group_slug = str(group_ref.get("group_slug") or "").strip()
    portal_host = str(group_ref.get("portal_host") or "").strip()
    if not group_id and not group_slug:
        raise StopAndReport("plan.group", "group_ref needs group_id or group_slug")
    if not group_id and not portal_host:
        raise StopAndReport(
            "plan.group",
            "a slug-only group_ref needs portal_host so the relationship is bound to an "
            "observable portal group (slug alone is not proof of the backend group).")

    operation = str(task.get("operation") or "attach").strip().lower()
    if operation not in ("attach", "detach"):
        raise StopAndReport("plan.operation", f"operation must be attach|detach (got {operation!r})")

    desired = task.get("desired_access") or {}
    if not isinstance(desired, dict):
        raise StopAndReport("plan.access", "desired_access must be an object")
    mode = str(desired.get("mode") or "all_members").strip().lower()
    if mode not in ALLOWED_MODES:
        raise StopAndReport(
            "plan.access", f"desired_access.mode must be one of {ALLOWED_MODES} (got {mode!r})")
    policy_ref = str(desired.get("policy_ref") or "").strip()
    policy_label = str(desired.get("policy_label") or "").strip() or DEFAULT_POLICY_LABEL.get(mode, "")
    if mode != "all_members" and not policy_ref:
        raise StopAndReport(
            "plan.access",
            f"mode {mode!r} changes learner access — policy_ref (the approved policy) is "
            "required so the exact policy can be verified after save.")
    if not policy_label:
        raise StopAndReport(
            "plan.access", "desired_access.policy_label is required for verification")
    if mode == "paid":
        leaked = [k for k in _BILLING_KEYS if k in task or k in desired]
        if leaked:
            raise StopAndReport(
                "plan.access",
                f"paid-mode association must not set price/billing fields from this operator "
                f"(found {leaked}); price changes are not authorized here.")

    approval_ref = str(task.get("approval_ref") or "").strip()
    if not approval_ref:
        raise StopAndReport(
            "plan.approval",
            f"{operation} writes a learner-visible relationship — approval_ref is required")

    # Same-location proof inputs. A caller that KNOWS either id must agree with location_id.
    loc_evidence: List[str] = [f"location_id={location_id}"]
    for key in ("course_location_id", "group_location_id"):
        val = str(task.get(key) or "").strip()
        if val:
            loc_evidence.append(f"{key}={val}")
            if val != location_id:
                raise StopAndReport(
                    "plan.location",
                    f"{key}={val!r} does not match location_id={location_id!r} — "
                    "cross-location association is forbidden.")

    return {
        "schema_version": str(task.get("schema_version") or SCHEMA_VERSION),
        "object_type": OBJECT_TYPE,
        "location_id": location_id,
        "course_product_id": course_product_id,
        "course_name": str(task.get("course_name") or "").strip(),
        "course_slug": str(task.get("course_slug") or "").strip()
                        or _cb._slug(str(task.get("course_name") or course_product_id)),
        "group_ref": {"group_id": group_id, "group_slug": group_slug,
                      "portal_host": portal_host},
        "desired_access": {"mode": mode, "policy_ref": policy_ref,
                           "policy_label": policy_label},
        "operation": operation,
        "approval_ref": approval_ref,
        "same_location": True,
        "location_evidence": loc_evidence,
        "idempotency_key": "existing_course+policy",
        "planned_at": _ts(),
    }


def preflight_association(plan: dict) -> dict:
    checks: List[dict] = []

    def chk(name: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        checks.append({"check": name, "pass": bool(ok), "hard": hard, "detail": detail})

    chk("LA-P1:course_resolved", bool(plan["course_product_id"]), "existing course id required")
    chk("LA-P2:group_resolved",
        bool(plan["group_ref"]["group_id"] or plan["group_ref"]["group_slug"]),
        "group id or slug required")
    chk("LA-P3:same_location", plan.get("same_location") is True, "same-location link required")
    chk("LA-P4:approval", bool(plan.get("approval_ref")), "approval_ref required")
    chk("LA-P5:policy_label", bool(plan["desired_access"]["policy_label"]),
        "verifiable policy label required")
    hard_fail = [c for c in checks if c["hard"] and not c["pass"]]
    return {"pass": not hard_fail, "checks": checks,
            "stop_reason": (hard_fail[0]["detail"] if hard_fail else "")}


# ---------------------------------------------------------------------------
# DUMB layer — browser read/write through the shared Skill-6 executor
# ---------------------------------------------------------------------------
def _click(session: str, sels: dict, dotted: str, *, required: bool = True) -> dict:
    """Every click path is checked against the forbidden create-new-course controls."""
    low = dotted.lower()
    for token in FORBIDDEN_SELECTOR_TOKENS:
        if token in low:
            raise StopAndReport(
                f"forbid:{dotted}",
                f"selector {dotted!r} is a course-CREATE control; the Learning operator may "
                "only select an existing course (spec §9.4 step 4).")
    return _cb._ex_click(session, sels, dotted, required=required)


def _fill(session: str, sels: dict, dotted: str, value: str, *, required: bool = True) -> dict:
    low = dotted.lower()
    for token in FORBIDDEN_SELECTOR_TOKENS:
        if token in low:
            raise StopAndReport(
                f"forbid:{dotted}",
                f"selector {dotted!r} is a course-CREATE control; refusing to fill it.")
    return _cb._ex_fill(session, sels, dotted, value, required=required)


_ROWS_JS = (
    "(() => { const out=[];"
    " const nodes=[...document.querySelectorAll('[data-testid*=association],[role=row],[role=listitem],li')];"
    " for (const n of nodes){ const t=(n.innerText||'').replace(/\\s+/g,' ').trim();"
    "   if(t) out.push({text:t}); }"
    " return JSON.stringify(out); })()"
)


def _parse_rows(raw: str) -> List[dict]:
    raw = (raw or "").strip()
    if not raw.startswith("["):
        return []
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return []
    return [r for r in data if isinstance(r, dict) and r.get("text")]


def read_associations(session: str, sels: dict, plan: dict) -> List[dict]:
    """Enumerate the group's existing course associations (D8: the read anchor must be
    actionable; a capture-pending read anchor STOP-and-reports)."""
    _cb.anchor(sels, "community.learning.association_rows")
    rows = _parse_rows(_cb._eval(session, _ROWS_JS, timeout=12) or "")
    out: List[dict] = []
    for r in rows:
        text = r["text"]
        out.append({
            "raw": text,
            "matches_course_id": plan["course_product_id"].lower() in text.lower(),
            "matches_course_name": bool(plan.get("course_name"))
                                   and _norm(plan["course_name"]) in _norm(text),
            "policy_observed": text,
        })
    return out


def _association_matches(row: dict, plan: dict) -> bool:
    if row.get("matches_course_id"):
        return True
    return bool(plan.get("course_name")) and row.get("matches_course_name")


def _policy_matches(row: dict, plan: dict) -> bool:
    return _norm(plan["desired_access"]["policy_label"]) in _norm(row.get("raw", ""))


def _scoped_detach(session: str, plan: dict) -> bool:
    """Detach ONLY the matching association row's own remove control (never a global
    first-match, never a course-delete control)."""
    want_id = plan["course_product_id"]
    want_name = plan.get("course_name") or ""
    js = (
        "(() => { const id=" + json.dumps(want_id) + ", nm=" + json.dumps(want_name) + ";"
        " const norm=s=>(s||'').replace(/\\s+/g,' ').trim().toLowerCase();"
        " const rows=[...document.querySelectorAll('[data-testid*=association],[role=row],[role=listitem],li')];"
        " const row=rows.find(r=>norm(r.innerText).includes(norm(id))"
        "   || (nm && norm(r.innerText).includes(norm(nm))));"
        " if(!row) return 'NO_ROW';"
        " const ctl=[...row.querySelectorAll('button,[role=button],a')]"
        "   .find(b=>/remove|detach|unlink/i.test(norm(b.innerText))||/x|trash/i.test(norm(b.getAttribute('aria-label')||'')));"
        " if(!ctl) return 'NO_CTL'; ctl.click(); return 'OK'; })()")
    return _cb._ok_scoped(_cb._eval(session, js, timeout=12))


def _course_present(session: str, plan: dict) -> Optional[bool]:
    """Post-detach proof that the COURSE itself survived. None = could not observe."""
    try:
        if plan.get("course_name"):
            return bool(_cb._list_has(session, plan["course_name"], plan.get("course_slug", "")))
        raw = _cb._eval(
            session,
            "(() => { const t=(document.body?document.body.innerText:'');"
            "return JSON.stringify({has:t.indexOf(" + json.dumps(plan["course_product_id"]) + ")!==-1});})()",
            timeout=12) or ""
        if raw.strip().startswith("{"):
            return bool(json.loads(raw).get("has"))
    except Exception as exc:  # noqa: BLE001
        _log(f"course presence read failed: {exc}")
    return None


def attach_existing_course(session: str, sels: dict, plan: dict, evidence_root: str) -> dict:
    _click(session, sels, "community.learning.learning_tab")
    existing = read_associations(session, sels, plan)
    matched = next((r for r in existing if _association_matches(r, plan)), None)

    if matched and _policy_matches(matched, plan):
        verify = {"ok": True, "association_present": True, "policy_matched": True,
                  "policy_label": plan["desired_access"]["policy_label"],
                  "evidence": "enumerated before write — no duplicate created"}
        receipt = _cb._receipt(OBJECT_TYPE, plan["course_slug"], "reused",
                               response_id=plan["course_product_id"],
                               request_shape={"course": plan["course_product_id"],
                                              "group": plan["group_ref"],
                                              "policy": plan["desired_access"]},
                               verify=verify)
        _cb._write_receipt(evidence_root, receipt)
        return {"action": "reused", "verify": verify, "receipt": receipt}

    if matched:  # same course, policy differs → update policy ONLY (no second association)
        _click(session, sels, "community.learning.policy_select")
        _click(session, sels, "community.learning.policy_option")
        _click(session, sels, "community.learning.save_association")
    else:
        _click(session, sels, "community.learning.add_existing_course_control")
        _fill(session, sels, "community.learning.course_picker_search",
              plan.get("course_name") or plan["course_product_id"], required=False)
        _click(session, sels, "community.learning.course_option")
        _click(session, sels, "community.learning.policy_select")
        _click(session, sels, "community.learning.policy_option")
        _click(session, sels, "community.learning.save_association")

    _click(session, sels, "community.learning.associations_reload", required=False)
    after = read_associations(session, sels, plan)
    got = next((r for r in after if _association_matches(r, plan)), None)
    if not got:
        raise StopAndReport(
            "attach.verify",
            f"association for course {plan['course_product_id']!r} not present after save "
            "(reload read-back miss). STOP — no brute-force.")
    if not _policy_matches(got, plan):
        raise StopAndReport(
            "attach.policy",
            f"association saved but policy {plan['desired_access']['policy_label']!r} was not "
            f"confirmed in the relationship view (observed: {got.get('raw','')[:160]!r}).")
    verify = {"ok": True, "association_present": True, "policy_matched": True,
              "policy_label": plan["desired_access"]["policy_label"],
              "evidence": "relationship view reloaded and matched"}
    receipt = _cb._receipt(OBJECT_TYPE, plan["course_slug"], "created",
                           response_id=plan["course_product_id"],
                           request_shape={"course": plan["course_product_id"],
                                          "group": plan["group_ref"],
                                          "policy": plan["desired_access"]},
                           verify=verify)
    _cb._write_receipt(evidence_root, receipt)
    return {"action": "created", "verify": verify, "receipt": receipt}


def detach_course(session: str, sels: dict, plan: dict, evidence_root: str) -> dict:
    """Remove ONLY the relationship. The course row is checked afterwards and is NEVER
    deleted by this operator."""
    _click(session, sels, "community.learning.learning_tab")
    existing = read_associations(session, sels, plan)
    matched = next((r for r in existing if _association_matches(r, plan)), None)
    if not matched:
        verify = {"ok": True, "association_present_before": False,
                  "association_present_after": False, "course_deleted": False,
                  "note": "already absent — idempotent no-op"}
        return {"action": "already_absent", "verify": verify}

    if not _scoped_detach(session, plan):
        raise StopAndReport(
            "detach.control",
            "could not find the matching association row's OWN remove control — nothing "
            "removed (never a global first-match, never a course delete).")
    _click(session, sels, "community.learning.detach_confirm", required=False)
    _click(session, sels, "community.learning.associations_reload", required=False)

    after = read_associations(session, sels, plan)
    still = next((r for r in after if _association_matches(r, plan)), None)
    if still:
        raise StopAndReport("detach.verify",
                            "association still present after detach + reload — STOP.")
    course_present = _course_present(session, plan)
    verify = {"ok": True, "association_present_before": True,
              "association_present_after": False, "course_deleted": False,
              "course_still_present": course_present,
              "removal_scope": "relationship_only"}
    if course_present is None:
        verify["warning"] = ("course presence could not be observed after detach; this "
                             "operator never deletes courses")
    return {"action": "detached", "verify": verify}


def execute(session: str, sels: dict, plan: dict, evidence_root: str) -> dict:
    if plan["operation"] == "detach":
        return detach_course(session, sels, plan, evidence_root)
    return attach_existing_course(session, sels, plan, evidence_root)


# ---------------------------------------------------------------------------
# Entry point used by the builder / router
# ---------------------------------------------------------------------------
def build_association(task: dict, evidence_root: str, *, dry_run: bool = True,
                      session: Optional[str] = None) -> dict:
    started = time.monotonic()
    os.makedirs(os.path.join(evidence_root, "routing"), exist_ok=True)
    plan = plan_association(task)
    preflight = preflight_association(plan)
    _write_json(os.path.join(evidence_root, "routing", "learning-association-plan.json"),
                {"plan": plan, "preflight": preflight})

    base = {"object_type": OBJECT_TYPE, "operation": plan["operation"],
            "location_id": plan["location_id"],
            "course_product_id": plan["course_product_id"],
            "group_ref": plan["group_ref"], "dry_run": bool(task.get("dry_run", dry_run))}
    if not preflight["pass"]:
        return {**base, "ok": False, "action": None, "verify": {},
                "artifact_path": None, "receipt_path": None,
                "error": preflight["stop_reason"], "preflight": preflight,
                "duration_s": time.monotonic() - started}

    if task.get("dry_run", dry_run) or session is None:
        if session is None and not task.get("dry_run", dry_run):
            raise RuntimeError(
                "live association execution requires the caller's seeded browser session — "
                "this operator never spawns its own browser/login.")
        return {**base, "ok": True, "action": "planned", "verify": {}, "preflight": preflight,
                "plan": plan, "artifact_path": None, "receipt_path": None, "error": None,
                "duration_s": time.monotonic() - started}

    sels = _cb.load_selectors()
    try:
        res = execute(session, sels, plan, evidence_root)
    except StopAndReport as sr:
        _write_json(os.path.join(evidence_root, "routing", "learning-association.json"),
                    {"ok": False, "operation": plan["operation"], "stop": str(sr),
                     "stop_step": sr.step, "course_deleted": False, "same_location": True})
        return {**base, "ok": False, "action": None, "verify": {},
                "artifact_path": os.path.join(evidence_root, "routing", "learning-association.json"),
                "receipt_path": None, "error": str(sr),
                "duration_s": time.monotonic() - started}

    artifact_path = os.path.join(evidence_root, "routing", "learning-association.json")
    _write_json(artifact_path, {
        "ok": True, "schema_version": plan["schema_version"],
        "operation": plan["operation"], "location_id": plan["location_id"],
        "course_product_id": plan["course_product_id"],
        "group_ref": plan["group_ref"], "desired_access": plan["desired_access"],
        "approval_ref": plan["approval_ref"], "same_location": plan["same_location"],
        "action": res["action"], "verify": res["verify"],
        "receipt_path": (_cb._write_receipt(evidence_root, res["receipt"])
                         if res.get("receipt") else None),
        "observed_at": _ts(),
    })
    return {**base, "ok": True, "action": res["action"], "verify": res["verify"],
            "artifact_path": artifact_path,
            "receipt_path": (_cb._write_receipt(evidence_root, res["receipt"])
                             if res.get("receipt") else None),
            "error": None, "duration_s": time.monotonic() - started}


# ---------------------------------------------------------------------------
# Self-test — no network, no browser (fake session primitives)
# ---------------------------------------------------------------------------
def _selftest() -> int:  # noqa: C901
    import copy
    import tempfile
    errors: List[str] = []

    def good_task(**over):
        t = {
            "schema_version": "1.0.0", "location_id": "LOC",
            "course_product_id": "COURSE_123",
            "course_name": "ZHC Launch 101",
            "group_ref": {"group_id": "", "group_slug": "zhc-founders",
                          "portal_host": "portal.example.com"},
            "desired_access": {"mode": "all_members", "policy_ref": "APPROVED_POLICY",
                               "policy_label": "All members"},
            "operation": "attach", "approval_ref": "APPR-1",
        }
        t.update(over)
        return t

    # 1. valid plan round-trips with same-location evidence
    plan = plan_association(good_task())
    if plan["same_location"] is not True or plan["course_product_id"] != "COURSE_123":
        errors.append(f"plan shape wrong: {plan}")

    # 2. create-new intent / unresolved course rejected
    for bad in ({"course_product_id": ""}, {"course_product_id": "new"},
                {"create_course": True}):
        try:
            plan_association(good_task(**bad))
            errors.append(f"create-new intent not rejected: {bad}")
        except StopAndReport:
            pass

    # 3. same-location mismatch rejected
    try:
        plan_association(good_task(course_location_id="OTHER"))
        errors.append("cross-location association not rejected")
    except StopAndReport:
        pass

    # 4. approval + paid price guard
    try:
        plan_association(good_task(approval_ref=""))
        errors.append("missing approval_ref not rejected")
    except StopAndReport:
        pass
    try:
        plan_association(good_task(desired_access={"mode": "paid", "policy_ref": "P",
                                                   "policy_label": "Paid", "price": 99}))
        errors.append("paid-mode price field not rejected")
    except StopAndReport:
        pass

    # 5. forbidden create-new-course control is refused by the click wrapper
    try:
        _click("s", {}, "course.create_modal.create_confirm")
        errors.append("forbidden create control not refused")
    except StopAndReport:
        pass

    # 6. idempotent attach + separate relationship receipt (fake browser)
    sels = copy.deepcopy(_cb.load_selectors())
    for dotted in ("community.learning.learning_tab", "community.learning.association_rows"):
        node = _cb._target(sels, dotted)
        node["status"] = "locked"
        node["anchor"] = node.get("anchor") or "getByText('Learning')"
    orig = (_cb._eval, _cb._ab, _cb._ex_click, _cb._ex_fill, _cb._list_has,
            _cb._snapshot, _cb.load_selectors)
    rows = {"raw": json.dumps([{"text": "ZHC Launch 101 — COURSE_123 — All members"}]),
            "detached": False}

    def fake_eval(session, js, timeout=12):
        if "data-testid*=association" in js and "JSON.stringify(out)" in js:
            return "[]" if rows["detached"] else rows["raw"]
        if "NO_ROW" in js and "NO_CTL" in js:          # scoped detach control
            rows["detached"] = True
            return "OK"
        return ""

    def fake_ab(session, *args, timeout=15, stdin=None):
        rows["n"] += 1
        return type("CP", (), {"returncode": 0, "stdout": "ZHC Launch 101", "stderr": ""})()
    try:
        _cb._eval = fake_eval
        _cb._ab = fake_ab
        _cb._ex_click = lambda session, s, d, **kw: {"ok": True, "path": "find"}
        _cb._ex_fill = lambda session, s, d, v, **kw: {"ok": True, "path": "find"}
        _cb._list_has = lambda session, name, slug="": True
        _cb._snapshot = lambda s, timeout=20: "ZHC Launch 101"
        _cb.load_selectors = lambda path=None: sels
        with tempfile.TemporaryDirectory() as tmp:
            res = build_association(good_task(), tmp, dry_run=False, session="s")
            if not res["ok"] or res["action"] != "reused":
                errors.append(f"idempotent attach should reuse (got {res.get('action')})")
            if not res.get("receipt_path") or "learning_association" not in (res.get("receipt_path") or ""):
                errors.append("relationship receipt not written separately")
            # 7. detach does not delete the course
            rows["raw"] = json.dumps([{"text": "ZHC Launch 101 — COURSE_123 — All members"}])
            rows["detached"] = False
            dres = build_association(good_task(operation="detach"), tmp, dry_run=False,
                                     session="s")
            if not dres["ok"] or dres["action"] not in ("detached", "already_absent"):
                errors.append(f"detach failed: {dres.get('error')}")
            art = json.load(open(os.path.join(tmp, "routing", "learning-association.json"),
                                 encoding="utf-8"))
            if art.get("verify", {}).get("course_deleted") is not False:
                errors.append("detach artifact must record course_deleted=False")
    finally:
        (_cb._eval, _cb._ab, _cb._ex_click, _cb._ex_fill, _cb._list_has,
         _cb._snapshot, _cb.load_selectors) = orig

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — Learning association plan gate + idempotent attach + "
          "detach-without-course-delete (no network / no browser)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="ghl_learning_association",
                                description="Skill 6 Learning association operator "
                                            "(attach/inspect/detach an EXISTING course).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--plan-json", default="", help="relationship plan JSON file")
    p.add_argument("--evidence-root", default="")
    p.add_argument("--session", default="", help="existing seeded session (live only)")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.plan_json:
        p.error("--plan-json is required (or use --selftest)")
    with open(args.plan_json, encoding="utf-8") as fh:
        task = json.load(fh)
    task.setdefault("dry_run", args.dry_run)
    root = args.evidence_root or os.path.join(
        os.environ.get("TMPDIR", "/tmp"), "ghl-learning-association-run")
    res = build_association(task, root, dry_run=args.dry_run,
                            session=(args.session or None))
    print(json.dumps(res, indent=2, default=str))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

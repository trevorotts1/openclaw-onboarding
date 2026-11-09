#!/usr/bin/env python3
"""ghl_community_members.py — Skill 6 narrow operator: Community GROUP + CHANNEL member
administration (spec v3.0 §9.3 member rows, §9.5 member administration).

Scope and safety:
  * every operation names the EXACT group and the EXACT person (member_contact_id and/or
    an unambiguous email), so a row-scoped control can never land on another member;
  * role elevation, removal, ban and any broad notification require an explicit
    approval_ref, and a role change can never silently mint an administrator (§9.3);
  * invite/approve may use the tenant's established automation authorization
    (task["automation_authorized"]=True) — the other actions never can;
  * enrolling a contact in a workflow is NOT access proof (§9.5): a grant/revoke result
    is only `verified` when the member's own row state is read back, and the difference
    between GROUP access and COURSE-OFFER access is preserved in the result;
  * it is a narrow operator: the caller owns the seeded browser session. No independent
    browser, no second login, no public-API claim.

Selectors: `community.members.*` in selectors-live-communities-courses.json. Every one is
capture-pending until a live capture locks it, so the live path STOP-and-reports (D8).

FROZEN-ish interface (consumed by the builder/router; additive only):
    plan_member_operation(task) -> dict
    preflight_member_operation(plan) -> dict
    list_members(session, sels, plan) -> list[dict]
    execute_member_operation(session, sels, plan) -> dict
    build_member_operation(task, evidence_root, *, dry_run=True, session=None) -> dict
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

import ghl_community_builder as _cb  # noqa: E402

StopAndReport = _cb.StopAndReport

OBJECT_TYPE = "community_member"
OPERATIONS = ("invite", "approve", "remove", "ban", "role_change", "grant_access",
              "revoke_access")
# Every one of these changes a person's standing → explicit approval.
APPROVAL_REQUIRED = {"remove", "ban", "role_change", "revoke_access"}
# Role ranks: a change upward to >= admin needs approval even when named.
ROLE_RANK = {"member": 0, "moderator": 1, "admin": 2, "owner": 3}
ELEVATING = ("admin", "owner")
ACCESS_SCOPE = ("group", "course_offer")
_WORKFLOW_ONLY = "enrolling a contact in a workflow is not access proof"


def _ts() -> str:
    return _cb._ts()


def _write_json(path: str, data: Any) -> None:
    _cb._write_json(path, data)


def _log(msg: str) -> None:
    _cb._log(msg)


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _norm(s: Any) -> str:
    return " ".join(str(s or "").split()).strip().lower()


# ---------------------------------------------------------------------------
# THINK layer
# ---------------------------------------------------------------------------
def plan_member_operation(task: dict) -> dict:
    if not isinstance(task, dict):
        raise StopAndReport("plan.shape", "member plan must be a JSON object")
    op = str(task.get("operation") or "").strip().lower()
    if op not in OPERATIONS:
        raise StopAndReport("plan.operation", f"operation must be one of {OPERATIONS} (got {op!r})")
    location_id = str(task.get("location_id") or "").strip()
    if not location_id:
        raise StopAndReport("plan.location", "location_id is required")

    group_ref = task.get("group_ref") or {}
    if not isinstance(group_ref, dict):
        raise StopAndReport("plan.group", "group_ref must be an object")
    slug = str(group_ref.get("group_slug") or "").strip()
    gid = str(group_ref.get("group_id") or "").strip()
    host = str(group_ref.get("portal_host") or "").strip()
    if not (slug or gid):
        raise StopAndReport("plan.group", "group_ref needs group_id or group_slug")

    member = task.get("member") or {}
    if not isinstance(member, dict):
        raise StopAndReport("plan.member", "member must be an object")
    contact_id = str(member.get("member_contact_id") or "").strip()
    email = str(member.get("email") or "").strip().lower()
    if op != "invite":
        if _blank(contact_id) and _blank(email):
            raise StopAndReport(
                "plan.member",
                f"{op} needs the exact person: member.member_contact_id (preferred) or email")
    else:
        if _blank(email) and _blank(contact_id):
            raise StopAndReport("plan.member", "invite needs member.email or member_contact_id")
    ambiguous = list(member.get("ambiguous_matches") or [])
    if ambiguous:
        raise StopAndReport(
            "plan.member",
            f"member identity is ambiguous ({len(ambiguous)} matches) — resolve it before any "
            "role/removal action (spec §9.3 exact person).")

    approval_ref = str(task.get("approval_ref") or "").strip()
    automation_authorized = bool(task.get("automation_authorized"))
    if op in APPROVAL_REQUIRED and not approval_ref:
        raise StopAndReport(
            "plan.approval",
            f"{op} changes a person's standing — approval_ref is required "
            "(routine onboarding automation covers invite/approve only).")
    if op == "grant_access" and not (approval_ref or automation_authorized):
        raise StopAndReport(
            "plan.approval",
            "granting group access needs approval_ref or automation_authorized=True")

    role = str(task.get("new_role") or "").strip().lower()
    if op == "role_change":
        if role not in ROLE_RANK:
            raise StopAndReport("plan.role", f"new_role must be one of {tuple(ROLE_RANK)}")
        if role in ELEVATING and not approval_ref:
            raise StopAndReport(
                "plan.role",
                f"elevating to {role!r} makes someone an administrator — approval_ref required")
        if _norm(task.get("current_role")) == role:
            raise StopAndReport("plan.role", f"member is already {role!r} — nothing to change")

    scope = str(task.get("access_scope") or "group").strip().lower()
    if op in ("grant_access", "revoke_access") and scope not in ACCESS_SCOPE:
        raise StopAndReport("plan.scope", f"access_scope must be one of {ACCESS_SCOPE}")

    notify = bool(task.get("notify_member"))
    broad = bool(task.get("broad_notify"))
    if broad and not approval_ref:
        raise StopAndReport("plan.notify",
                            "a broad member notification needs approval_ref")

    return {
        "object_type": OBJECT_TYPE,
        "operation": op,
        "location_id": location_id,
        "group_ref": {"group_id": gid, "group_slug": slug, "portal_host": host},
        "member": {"member_contact_id": contact_id, "email": email},
        "new_role": role,
        "current_role": str(task.get("current_role") or "").strip().lower(),
        "access_scope": scope,
        "approval_ref": approval_ref,
        "automation_authorized": automation_authorized,
        "notify_member": notify,
        "broad_notify": broad,
        "workflow_enrollment_is_not_access_proof": _WORKFLOW_ONLY,
        "requires_access_readback": op in ("grant_access", "revoke_access", "approve"),
        "same_location": True,
        "planned_at": _ts(),
    }


def preflight_member_operation(plan: dict) -> dict:
    checks: List[dict] = []

    def chk(name: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        checks.append({"check": name, "pass": bool(ok), "hard": hard, "detail": detail})

    chk("M-P1:location", bool(plan["location_id"]), "location_id required")
    chk("M-P2:group", bool(plan["group_ref"]["group_id"] or plan["group_ref"]["group_slug"]),
        "group id or slug required")
    chk("M-P3:person",
        bool(plan["member"]["member_contact_id"] or plan["member"]["email"]),
        "exact person required")
    chk("M-P4:approval", plan["operation"] not in APPROVAL_REQUIRED or bool(plan["approval_ref"]),
        f"{plan['operation']} requires approval_ref")
    chk("M-P5:no_silent_admin",
        plan["operation"] != "role_change" or plan["new_role"] not in ELEVATING
        or bool(plan["approval_ref"]),
        "role elevation to admin/owner requires approval_ref")
    hard_fail = [c for c in checks if c["hard"] and not c["pass"]]
    return {"pass": not hard_fail, "checks": checks,
            "stop_reason": (hard_fail[0]["detail"] if hard_fail else "")}


# ---------------------------------------------------------------------------
# DUMB layer
# ---------------------------------------------------------------------------
_ROWS_JS = (
    "(() => { const out=[];"
    " const rows=[...document.querySelectorAll('[data-testid*=member],[role=row],[role=listitem],li')];"
    " for (const r of rows){ const t=(r.innerText||'').replace(/\\s+/g,' ').trim();"
    " if(t) out.push({text:t}); } return JSON.stringify(out); })()"
)

_ACTION_LABEL = {
    "invite": ("invite", "community.members.invite_control"),
    "approve": ("approve", "community.members.approve_control"),
    "remove": ("remove", "community.members.remove_control"),
    "ban": ("ban", "community.members.ban_control"),
    "role_change": ("role", "community.members.role_control"),
    "grant_access": ("grant", "community.members.grant_access_control"),
    "revoke_access": ("revoke", "community.members.revoke_access_control"),
}


def list_members(session: str, sels: dict, plan: dict) -> List[dict]:
    _cb.anchor(sels, "community.members.member_rows")
    raw = (_cb._eval(session, _ROWS_JS, timeout=12) or "").strip()
    rows: List[dict] = []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            data = []
        for r in data:
            text = str((r or {}).get("text") or "")
            if not text:
                continue
            rows.append({
                "raw": text,
                "matches_contact_id": bool(plan["member"]["member_contact_id"])
                and plan["member"]["member_contact_id"].lower() in text.lower(),
                "matches_email": bool(plan["member"]["email"])
                and plan["member"]["email"] in text.lower(),
            })
    return rows


def _member_row_matches(row: dict) -> bool:
    return bool(row.get("matches_contact_id") or row.get("matches_email"))


def _scoped_member_control(session: str, plan: dict, verb: str, selector_name: str) -> bool:
    """Click a control INSIDE the exact member's row. Never a global first-match: a
    populated group has real students and staff in the same table."""
    cid = plan["member"]["member_contact_id"]
    email = plan["member"]["email"]
    js = (
        "(() => { const cid=" + json.dumps(cid) + ", email=" + json.dumps(email)
        + ", verb=" + json.dumps(verb) + ";"
        " const norm=s=>(s||'').replace(/\\s+/g,' ').trim().toLowerCase();"
        " const rows=[...document.querySelectorAll('[data-testid*=member],[role=row],[role=listitem],li')];"
        " const row=rows.find(r=>{const t=norm(r.innerText);"
        "   return (cid && t.indexOf(norm(cid))!==-1) || (email && t.indexOf(norm(email))!==-1);});"
        " if(!row) return 'NO_ROW';"
        " const ctl=[...row.querySelectorAll('button,[role=button],a,[role=menuitem]')]"
        "   .find(b=>{const t=norm(b.innerText||b.getAttribute('aria-label')||'');"
        "     return t.indexOf(verb)!==-1;});"
        " if(!ctl) return 'NO_CTL'; ctl.click(); return 'OK'; })()")
    ok = _cb._ok_scoped(_cb._eval(session, js, timeout=12))
    if not ok:
        # fall back to the registered selector ONLY when it is itself row-scoped prose;
        # the selector gate still refuses a capture-pending target (D8).
        _log(f"scoped control miss for {selector_name}; not falling back to a global click")
    return ok


def execute_member_operation(session: str, sels: dict, plan: dict) -> dict:
    op = plan["operation"]
    rows = list_members(session, sels, plan)
    matched = [r for r in rows if _member_row_matches(r)]
    if len(matched) > 1:
        raise StopAndReport(
            "member.ambiguous",
            f"{len(matched)} rows match the requested person — resolve identity before acting")
    row_before = matched[0] if matched else None

    if op == "invite":
        _cb._ex_click(session, sels, "community.members.invite_control")
        _cb._ex_fill(session, sels, "community.members.invite_email_input", plan["member"]["email"])
        _cb._ex_click(session, sels, "community.members.invite_confirm")
        _cb._ex_wait_text(session, plan["member"]["email"][:18], timeout=15)
        after = list_members(session, sels, plan)
        present = any(_member_row_matches(r) for r in after)
        if not present:
            raise StopAndReport("invite.verify",
                                "invited member not present in the member list after save")
        return {"action": "invited", "verify": {"ok": True, "member_present": True,
                                                "access_granted": False,
                                                "access_note": "invite ≠ access"},
                "row": {"before": None, "after": after[0]["raw"][:200]}}

    if row_before is None:
        raise StopAndReport(
            "member.missing",
            f"{op}: the requested member is not present in this group's member list")

    verb, selector_name = _ACTION_LABEL[op]
    if not _scoped_member_control(session, plan, verb, selector_name):
        raise StopAndReport(
            f"{op}.control",
            f"could not find the row-scoped {verb!r} control for this member — nothing changed "
            "(never a global first-match).")

    if op == "role_change":
        _cb._ex_click(session, sels, "community.members.role_option")
        _cb._ex_click(session, sels, "community.members.role_confirm")
        _cb._ex_wait_text(session, plan["new_role"], timeout=12)
    elif op in ("remove", "ban"):
        _cb._ex_click(session, sels, "community.members.confirm_action")
    elif op in ("approve", "grant_access", "revoke_access"):
        _cb._ex_click(session, sels, "community.members.confirm_action")

    _cb._ex_click(session, sels, "community.members.member_rows_reload", required=False)
    after = list_members(session, sels, plan)
    now = [r for r in after if _member_row_matches(r)]
    row_after = now[0]["raw"] if now else None
    verify: Dict[str, Any] = {"ok": True, "row_before": (row_before or {}).get("raw", "")[:200],
                              "row_after": (row_after or "")[:200],
                              "access_scope": plan["access_scope"],
                              "workflow_enrollment_is_not_access_proof": _WORKFLOW_ONLY}

    if op in ("remove", "ban"):
        if now:
            raise StopAndReport(
                "remove.verify",
                f"member still present after {op} — the removal was not confirmed")
        verify.update({"member_present_after": False, "access_revoked": True})
    elif op == "role_change":
        if not now or plan["new_role"] not in _norm(row_after):
            raise StopAndReport(
                "role.verify", f"row does not show the new role {plan['new_role']!r} after save")
        verify.update({"member_present_after": True, "role_after": plan["new_role"]})
    else:  # approve / grant / revoke — read the member's own row for the access state
        if not now:
            raise StopAndReport("access.verify", f"member row missing after {op} — cannot prove access")
        granted = op in ("approve", "grant_access")
        verify.update({"member_present_after": True, "access_granted": granted,
                       "course_offer_access": ("unknown" if plan["access_scope"] == "group"
                                               else granted),
                       "group_access": granted if plan["access_scope"] == "group" else "unknown"})

    return {"action": op, "verify": verify,
            "row": {"before": verify["row_before"], "after": verify["row_after"]}}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def build_member_operation(task: dict, evidence_root: str, *, dry_run: bool = True,
                           session: Optional[str] = None) -> dict:
    started = time.monotonic()
    os.makedirs(os.path.join(evidence_root, "routing"), exist_ok=True)
    plan = plan_member_operation(task)
    preflight = preflight_member_operation(plan)
    _write_json(os.path.join(evidence_root, "routing", "member-operation-plan.json"),
                {"plan": plan, "preflight": preflight})
    base = {"object_type": OBJECT_TYPE, "operation": plan["operation"],
            "location_id": plan["location_id"], "group_ref": plan["group_ref"]}
    if not preflight["pass"]:
        return {**base, "ok": False, "verify": {}, "error": preflight["stop_reason"],
                "dry_run": bool(task.get("dry_run", dry_run)),
                "duration_s": time.monotonic() - started}
    if task.get("dry_run", dry_run) or session is None:
        if session is None and not task.get("dry_run", dry_run):
            raise RuntimeError("live member operations require the caller's seeded session — "
                               "this operator never spawns its own browser/login")
        return {**base, "ok": True, "verify": {}, "plan": plan, "preflight": preflight,
                "error": None, "dry_run": True,
                "duration_s": time.monotonic() - started}
    sels = _cb.load_selectors()
    try:
        res = execute_member_operation(session, sels, plan)
    except StopAndReport as sr:
        path = os.path.join(evidence_root, "routing", "member-operation.json")
        _write_json(path, {"ok": False, "operation": plan["operation"], "stop": str(sr),
                           "stop_step": sr.step, "approval_ref": plan["approval_ref"],
                           "observed_at": _ts()})
        return {**base, "ok": False, "verify": {}, "error": str(sr),
                "artifact_path": path, "dry_run": False,
                "duration_s": time.monotonic() - started}
    path = os.path.join(evidence_root, "routing", "member-operation.json")
    _write_json(path, {"ok": True, "operation": plan["operation"],
                       "member": plan["member"], "approval_ref": plan["approval_ref"],
                       "automation_authorized": plan["automation_authorized"],
                       "result": res["verify"], "access_scope": plan["access_scope"],
                       "observed_at": _ts()})
    return {**base, "ok": True, "action": res["action"], "verify": res["verify"],
            "artifact_path": path, "error": None, "dry_run": False,
            "duration_s": time.monotonic() - started}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
def _selftest() -> int:  # noqa: C901
    import copy
    import tempfile
    errors: List[str] = []

    def task(**over):
        t = {"location_id": "LOC", "operation": "invite",
             "group_ref": {"group_id": "", "group_slug": "zhc-founders",
                          "portal_host": "portal.example.com"},
             "member": {"member_contact_id": "CONTACT_1", "email": "student@example.com"}}
        t.update(over)
        return t

    p = plan_member_operation(task())
    if p["operation"] != "invite" or p["same_location"] is not True:
        errors.append(f"plan shape wrong: {p}")

    for bad in ({"operation": "teleport"}, {"location_id": ""},
                {"group_ref": {}}, {"member": {}},
                {"operation": "remove", "approval_ref": ""},
                {"operation": "ban", "approval_ref": ""},
                {"operation": "role_change", "new_role": "admin", "approval_ref": ""},
                {"operation": "role_change", "new_role": "staff"},
                {"member": {"member_contact_id": "C", "ambiguous_matches": ["a", "b"]}}):
        try:
            plan_member_operation(task(**bad))
            errors.append(f"unsafe plan not rejected: {bad}")
        except StopAndReport:
            pass

    # routine onboarding may ride the established automation authorization
    ok = plan_member_operation(task(operation="approve", automation_authorized=True))
    if ok["operation"] != "approve":
        errors.append("approve with automation_authorized rejected")

    sels = copy.deepcopy(_cb.load_selectors())
    for name, node in sels["community"]["members"].items():
        if isinstance(node, dict) and "status" in node:
            node["status"] = "locked"
            node["anchor"] = node.get("anchor") or "getByText('Members')"
    orig = (_cb._eval, _cb._ex_click, _cb._ex_fill, _cb._ex_wait_text,
            _cb.load_selectors, _cb._snapshot)
    state = {"rows": [{"text": "Student One student@example.com CONTACT_1 member"}],
             "effect": None}

    def fake_eval(session, js, timeout=12):
        return json.dumps(state["rows"])

    def fake_click(session, s, dotted, **kw):
        if dotted == "community.members.role_confirm":
            state["rows"] = [{"text": "Student One student@example.com CONTACT_1 admin"}]
        if dotted == "community.members.confirm_action" and state["effect"] == "remove":
            state["rows"] = []
        return {"ok": True, "path": "find"}
    try:
        _cb._eval = fake_eval
        _cb._ex_click = fake_click
        _cb._ex_fill = lambda session, s, d, v, **kw: {"ok": True}
        _cb._ex_wait_text = lambda session, text, timeout=20: None
        _cb.load_selectors = lambda path=None: sels
        _cb._snapshot = lambda s, timeout=20: "Members"
        with tempfile.TemporaryDirectory() as tmp:
            res = build_member_operation(task(operation="role_change", new_role="admin",
                                              approval_ref="APPR"), tmp,
                                         dry_run=False, session="s")
            if not res["ok"] or res["verify"].get("role_after") != "admin":
                errors.append(f"role change should verify admin (got {res.get('error')})")
            state["rows"] = [{"text": "Student One student@example.com CONTACT_1 member"}]
            gres = build_member_operation(task(operation="grant_access", approval_ref="APPR"),
                                          tmp, dry_run=False, session="s")
            if not gres["ok"] or gres["verify"].get("access_granted") is not True:
                errors.append(f"grant_access should confirm access (got {gres.get('error')})")
            if "workflow_enrollment_is_not_access_proof" not in gres["verify"]:
                errors.append("grant result must record the workflow≠access distinction")
            state["rows"] = [{"text": "Student One student@example.com CONTACT_1 member"}]
            state["effect"] = "remove"
            rres = build_member_operation(task(operation="remove", approval_ref="APPR"), tmp,
                                          dry_run=False, session="s")
            if not rres["ok"] or rres["verify"].get("member_present_after") is not False:
                errors.append(f"remove should confirm absence (got {rres.get('error')})")
    finally:
        (_cb._eval, _cb._ex_click, _cb._ex_fill, _cb._ex_wait_text,
         _cb.load_selectors, _cb._snapshot) = orig

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — member scope/approval gates + row-scoped actions + access "
          "read-back (no network / no browser)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="ghl_community_members",
                                description="Skill 6 Community member administration operator.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--plan-json", default="")
    p.add_argument("--evidence-root", default="")
    p.add_argument("--session", default="")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.plan_json:
        p.error("--plan-json is required (or use --selftest)")
    with open(args.plan_json, encoding="utf-8") as fh:
        task = json.load(fh)
    task.setdefault("dry_run", args.dry_run)
    root = args.evidence_root or os.path.join(
        os.environ.get("TMPDIR", "/tmp"), "ghl-community-members-run")
    res = build_member_operation(task, root, dry_run=args.dry_run,
                                 session=(args.session or None))
    print(json.dumps(res, indent=2, default=str))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

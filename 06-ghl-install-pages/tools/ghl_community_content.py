#!/usr/bin/env python3
"""ghl_community_content.py — Skill 6 narrow operator: Community UI CONTENT and
MODERATION gaps (spec v3.0 §9.3 rows for pin/moderate/delete and member-view content).

Public Social Planner owns post create/edit/schedule/read and supported comments
(WF10 / `public/community_social.py`). This module deliberately does NOT implement a
second public client: `classify_route()` sends those intents to WF10 and only the
managed-UI gaps land here — pin/unpin, hide/restore, delete, and reading the
moderation queue.

Safety:
  * destructive/moderation effects require an exact content identity (content_id and/or
    an exact permalink) and an approval_ref;
  * a moderator/admin role is required for moderation actions;
  * every action is row-scoped to that exact content; a global first-match is never used;
  * state is read back after the action and must match, else STOP-and-report.

Selectors: `community.content.*`. All capture-pending until a live capture locks them
(D8), so a live run STOP-and-reports honestly.

Interface:
    classify_route(request) -> dict
    plan_content_operation(task) -> dict
    preflight_content_operation(plan) -> dict
    list_moderation_queue(session, sels, plan) -> list[dict]
    execute_content_operation(session, sels, plan) -> dict
    build_content_operation(task, evidence_root, *, dry_run=True, session=None) -> dict
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

OBJECT_TYPE = "community_content"
OPERATIONS = ("pin", "unpin", "hide", "restore", "delete", "list_pending", "verify_view")
APPROVAL_REQUIRED = {"hide", "delete"}
MODERATION_ROLES = ("moderator", "admin", "owner")
ROLE_RANK = {"member": 0, "moderator": 1, "admin": 2, "owner": 3}
PUBLIC_INTENTS = ("post_create", "post_update", "post_schedule", "post_read",
                  "comment_create", "comment_reply", "comment_list")
_STATE_AFTER = {"pin": "pinned", "unpin": "unpinned", "hide": "hidden",
                "restore": "visible", "delete": "deleted"}


def _ts() -> str:
    return _cb._ts()


def _write_json(path: str, data: Any) -> None:
    _cb._write_json(path, data)


def _norm(s: Any) -> str:
    return " ".join(str(s or "").split()).strip().lower()


# ---------------------------------------------------------------------------
# Route classification — public contract vs managed UI gap
# ---------------------------------------------------------------------------
def classify_route(request: dict) -> dict:
    """Route a content intent without claiming a rail that does not exist."""
    intent = _norm((request or {}).get("intent"))
    if intent in PUBLIC_INTENTS:
        return {"intent": intent, "route": "public_social_planner",
                "owner": "WF10", "supported_here": False,
                "reason": "post/comment public operations belong to the Community social adapter"}
    if intent in OPERATIONS or intent in ("moderate", "content_read"):
        return {"intent": intent, "route": "managed_browser_ui", "owner": "WF09",
                "supported_here": True, "reason": "moderation/pin/delete is a UI-only gap"}
    return {"intent": intent, "route": "feature_unavailable", "owner": None,
            "supported_here": False,
            "reason": "no supported public or managed-UI executor is registered for this intent"}


# ---------------------------------------------------------------------------
# THINK layer
# ---------------------------------------------------------------------------
def plan_content_operation(task: dict) -> dict:
    if not isinstance(task, dict):
        raise StopAndReport("plan.shape", "content plan must be a JSON object")
    op = _norm(task.get("operation"))
    if op == "moderate":
        op = _norm(task.get("effect")) or "hide"
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
    if not (slug or gid):
        raise StopAndReport("plan.group", "group_ref needs group_id or group_slug")

    content_id = str(task.get("content_id") or "").strip()
    permalink = str(task.get("permalink") or "").strip()
    if op not in ("list_pending",) and not (content_id or permalink):
        raise StopAndReport(
            "plan.content",
            f"{op} needs the exact content identity (content_id, or an exact permalink)")
    raw_viewer = task.get("viewer")
    if isinstance(raw_viewer, dict):
        viewer_ident = str(raw_viewer.get("email") or raw_viewer.get("contact_id") or "").strip()
    else:
        viewer_ident = str(raw_viewer or "").strip()
    if op == "verify_view" and not viewer_ident:
        raise StopAndReport("plan.viewer", "verify_view needs the authorized viewer identity")

    approval_ref = str(task.get("approval_ref") or "").strip()
    if op in APPROVAL_REQUIRED and not approval_ref:
        raise StopAndReport("plan.approval",
                            f"{op} is destructive/moderating — approval_ref is required")
    role = _norm(task.get("operator_role"))
    if op in ("pin", "unpin", "hide", "restore", "delete") and \
            ROLE_RANK.get(role, -1) < ROLE_RANK["moderator"]:
        raise StopAndReport(
            "plan.role", f"{op} requires a moderator/admin role (operator_role={role!r})")

    return {
        "object_type": OBJECT_TYPE,
        "operation": op,
        "location_id": location_id,
        "group_ref": {"group_id": gid, "group_slug": slug,
                      "portal_host": str(group_ref.get("portal_host") or "").strip()},
        "content_id": content_id,
        "permalink": permalink,
        "operator_role": role,
        "approval_ref": approval_ref,
        "viewer": (raw_viewer if isinstance(raw_viewer, dict) else
                   ({"email": viewer_ident} if viewer_ident else {})),
        "public_route_note": "post/comment public operations belong to WF10",
        "planned_at": _ts(),
    }


def preflight_content_operation(plan: dict) -> dict:
    checks: List[dict] = []

    def chk(name: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        checks.append({"check": name, "pass": bool(ok), "hard": hard, "detail": detail})

    chk("C-P1:location", bool(plan["location_id"]), "location_id required")
    chk("C-P2:group", bool(plan["group_ref"]["group_id"] or plan["group_ref"]["group_slug"]),
        "group id or slug required")
    chk("C-P3:content", plan["operation"] == "list_pending"
        or bool(plan["content_id"] or plan["permalink"]), "exact content identity required")
    chk("C-P4:role",
        plan["operation"] not in ("pin", "unpin", "hide", "restore", "delete")
        or ROLE_RANK.get(plan["operator_role"], -1) >= ROLE_RANK["moderator"],
        "moderation requires moderator+")
    chk("C-P5:approval", plan["operation"] not in APPROVAL_REQUIRED or bool(plan["approval_ref"]),
        f"{plan['operation']} requires approval_ref")
    hard_fail = [c for c in checks if c["hard"] and not c["pass"]]
    return {"pass": not hard_fail, "checks": checks,
            "stop_reason": (hard_fail[0]["detail"] if hard_fail else "")}


# ---------------------------------------------------------------------------
# DUMB layer
# ---------------------------------------------------------------------------
_ROWS_JS = (
    "(() => { const out=[];"
    " const rows=[...document.querySelectorAll('[data-testid*=post],[data-testid*=content],[role=article],[role=row],li')];"
    " for (const r of rows){ const t=(r.innerText||'').replace(/\\s+/g,' ').trim();"
    "   if(!t) continue; const m=(r.getAttribute('data-content-id')||'');"
    "   out.push({text:t, content_id:m}); } return JSON.stringify(out); })()"
)


def list_moderation_queue(session: str, sels: dict, plan: dict) -> List[dict]:
    _cb.anchor(sels, "community.content.content_rows")
    raw = (_cb._eval(session, _ROWS_JS, timeout=12) or "").strip()
    rows: List[dict] = []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            data = []
        for r in data:
            if not isinstance(r, dict) or not r.get("text"):
                continue
            text = str(r["text"])
            rows.append({
                "raw": text,
                "content_id_attr": str(r.get("content_id") or ""),
                "matches_content_id": bool(plan.get("content_id"))
                and plan["content_id"].lower() in (text + " " + str(r.get("content_id") or "")).lower(),
                "matches_permalink": bool(plan.get("permalink"))
                and _norm(plan["permalink"]) in _norm(text),
                "state": _state_from_text(text),
            })
    return rows


def _state_from_text(text: str) -> str:
    t = _norm(text)
    for state in ("pinned", "hidden", "deleted"):
        if state in t:
            return state
    return "visible"


def _content_matches(row: dict) -> bool:
    return bool(row.get("matches_content_id") or row.get("matches_permalink"))


def _scoped_content_control(session: str, plan: dict, verb: str) -> bool:
    cid = plan.get("content_id") or ""
    perm = plan.get("permalink") or ""
    js = (
        "(() => { const cid=" + json.dumps(cid) + ", perm=" + json.dumps(perm)
        + ", verb=" + json.dumps(verb) + ";"
        " const norm=s=>(s||'').replace(/\\s+/g,' ').trim().toLowerCase();"
        " const rows=[...document.querySelectorAll('[data-testid*=post],[data-testid*=content],[role=article],[role=row],li')];"
        " const row=rows.find(r=>{const t=norm(r.innerText); const id=norm(r.getAttribute('data-content-id')||'');"
        "   return (cid && (id===norm(cid) || t.indexOf(norm(cid))!==-1))"
        "       || (perm && t.indexOf(norm(perm))!==-1);});"
        " if(!row) return 'NO_ROW';"
        " const ctl=[...row.querySelectorAll('button,[role=button],a,[role=menuitem]')]"
        "   .find(b=>norm(b.innerText||b.getAttribute('aria-label')||'').indexOf(verb)!==-1);"
        " if(!ctl) return 'NO_CTL'; ctl.click(); return 'OK'; })()")
    ok = _cb._ok_scoped(_cb._eval(session, js, timeout=12))
    if not ok:
        _cb._log(f"row-scoped content control miss for {verb!r}; a global click is never used")
    return ok


def execute_content_operation(session: str, sels: dict, plan: dict) -> dict:
    op = plan["operation"]
    _cb._ex_click(session, sels, "community.content.content_tab", required=False)
    rows = list_moderation_queue(session, sels, plan)

    if op == "list_pending":
        pending = [r for r in rows if r.get("state") == "hidden"]
        return {"action": "listed", "verify": {"ok": True, "rows": len(rows),
                                               "pending_moderation": len(pending)},
                "rows": [r["raw"][:200] for r in rows[:50]]}
    if op == "verify_view":
        viewer = _norm(plan["viewer"].get("email") or plan["viewer"].get("contact_id"))
        matched = [r for r in rows if _content_matches(r) and (not viewer or viewer in _norm(r["raw"]))]
        if not matched and viewer:
            raise StopAndReport(
                "verify_view.absent",
                f"authorized viewer {viewer!r} cannot see the exact content in this group — "
                "access policy does not match the requested outcome")
        return {"action": "view_verified",
                "verify": {"ok": bool(matched), "viewer": viewer,
                           "content_visible": bool(matched)}}

    matched = [r for r in rows if _content_matches(r)]
    if len(matched) > 1:
        raise StopAndReport("content.ambiguous",
                            f"{len(matched)} content rows match — resolve identity before acting")
    if not matched:
        raise StopAndReport("content.missing",
                            f"{op}: the exact content is not present in this group view")

    verb = {"pin": "pin", "unpin": "unpin", "hide": "hide",
            "restore": "restore", "delete": "delete"}[op]
    if not _scoped_content_control(session, plan, verb):
        raise StopAndReport(f"{op}.control",
                            f"could not find the row-scoped {verb!r} control — nothing changed")
    if op in ("hide", "delete"):
        _cb._ex_click(session, sels, "community.content.confirm_action")
    _cb._ex_click(session, sels, "community.content.content_reload", required=False)

    after = list_moderation_queue(session, sels, plan)
    now = [r for r in after if _content_matches(r)]
    if op == "delete":
        if now:
            raise StopAndReport("delete.verify", "content still present after delete")
        return {"action": "deleted", "verify": {"ok": True, "content_present_after": False,
                                                "row_before": matched[0]["raw"][:200]}}
    observed = now[0]["state"] if now else None
    want = _STATE_AFTER[op]
    if observed != want:
        raise StopAndReport(
            f"{op}.verify", f"observed state {observed!r} != expected {want!r} after action")
    return {"action": op, "verify": {"ok": True, "state_before": matched[0]["state"],
                                     "state_after": observed,
                                     "row_before": matched[0]["raw"][:200]}}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def build_content_operation(task: dict, evidence_root: str, *, dry_run: bool = True,
                            session: Optional[str] = None) -> dict:
    started = time.monotonic()
    os.makedirs(os.path.join(evidence_root, "routing"), exist_ok=True)
    plan = plan_content_operation(task)
    preflight = preflight_content_operation(plan)
    _write_json(os.path.join(evidence_root, "routing", "content-operation-plan.json"),
                {"plan": plan, "preflight": preflight})
    base = {"object_type": OBJECT_TYPE, "operation": plan["operation"],
            "location_id": plan["location_id"], "group_ref": plan["group_ref"]}
    if not preflight["pass"]:
        return {**base, "ok": False, "error": preflight["stop_reason"],
                "dry_run": bool(task.get("dry_run", dry_run)),
                "duration_s": time.monotonic() - started}
    if task.get("dry_run", dry_run) or session is None:
        if session is None and not task.get("dry_run", dry_run):
            raise RuntimeError("live content operations require the caller's seeded session")
        return {**base, "ok": True, "plan": plan, "preflight": preflight, "dry_run": True,
                "error": None, "duration_s": time.monotonic() - started}
    sels = _cb.load_selectors()
    path = os.path.join(evidence_root, "routing", "content-operation.json")
    try:
        res = execute_content_operation(session, sels, plan)
    except StopAndReport as sr:
        _write_json(path, {"ok": False, "operation": plan["operation"], "stop": str(sr),
                           "stop_step": sr.step, "approval_ref": plan["approval_ref"],
                           "observed_at": _ts()})
        return {**base, "ok": False, "error": str(sr), "artifact_path": path, "dry_run": False,
                "duration_s": time.monotonic() - started}
    _write_json(path, {"ok": True, "operation": plan["operation"],
                       "content_id": plan["content_id"], "permalink": plan["permalink"],
                       "approval_ref": plan["approval_ref"], "result": res["verify"],
                       "observed_at": _ts()})
    return {**base, "ok": True, "action": res.get("action"), "verify": res.get("verify", {}),
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
        t = {"location_id": "LOC", "operation": "pin", "content_id": "POST_1",
             "group_ref": {"group_id": "", "group_slug": "zhc-founders",
                          "portal_host": "portal.example.com"},
             "operator_role": "moderator", "approval_ref": ""}
        t.update(over)
        return t

    if classify_route({"intent": "post_create"})["owner"] != "WF10":
        errors.append("public post intent must route to WF10")
    if classify_route({"intent": "moderate"})["supported_here"] is not True:
        errors.append("moderation must be supported here")
    if classify_route({"intent": "teleport"})["route"] != "feature_unavailable":
        errors.append("unknown intent must be feature_unavailable")

    p = plan_content_operation(task())
    if p["operation"] != "pin":
        errors.append(f"plan wrong: {p}")
    for bad in ({"operation": "hide", "approval_ref": ""},
                {"operation": "delete", "approval_ref": ""},
                {"operation": "pin", "operator_role": "member"},
                {"content_id": "", "permalink": ""},
                {"operation": "nope"}):
        try:
            plan_content_operation(task(**bad))
            errors.append(f"unsafe plan not rejected: {bad}")
        except StopAndReport:
            pass

    sels = copy.deepcopy(_cb.load_selectors())
    for name, node in sels["community"]["content"].items():
        if isinstance(node, dict) and "status" in node:
            node["status"] = "locked"
            node["anchor"] = node.get("anchor") or "getByText('Content')"
    orig = (_cb._eval, _cb._ex_click, _cb._ex_wait_text, _cb.load_selectors)
    state = {"rows": [{"text": "POST_1 welcome everyone", "content_id": "POST_1"}],
             "effect": None}

    def fake_eval(session, js, timeout=12):
        return json.dumps(state["rows"])

    def fake_click(session, s, dotted, **kw):
        if dotted == "community.content.confirm_action":
            if state["effect"] == "hidden":
                state["rows"] = [{"text": "POST_1 hidden post", "content_id": "POST_1"}]
            elif state["effect"] == "deleted":
                state["rows"] = []
        return {"ok": True}
    try:
        _cb._eval = fake_eval
        _cb._ex_click = fake_click
        _cb._ex_wait_text = lambda *a, **k: None
        _cb.load_selectors = lambda path=None: sels
        with tempfile.TemporaryDirectory() as tmp:
            state["effect"] = "hidden"
            res = build_content_operation(task(operation="hide", approval_ref="APPR",), tmp,
                                          dry_run=False, session="s")
            if not res["ok"]:
                errors.append(f"hide with approval should pass (got {res.get('error')})")
            state["rows"] = [{"text": "POST_1 welcome everyone", "content_id": "POST_1"}]
            state["effect"] = "deleted"
            dres = build_content_operation(task(operation="delete", approval_ref="APPR"), tmp,
                                           dry_run=False, session="s")
            if not dres["ok"] or dres["verify"].get("content_present_after") is not False:
                errors.append(f"delete should confirm absence (got {dres.get('error')})")
    finally:
        (_cb._eval, _cb._ex_click, _cb._ex_wait_text, _cb.load_selectors) = orig

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — content route split + moderation approvals + row-scoped "
          "state read-back (no network / no browser)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="ghl_community_content",
                                description="Skill 6 Community UI content/moderation operator.")
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
        os.environ.get("TMPDIR", "/tmp"), "ghl-community-content-run")
    res = build_content_operation(task, root, dry_run=args.dry_run,
                                  session=(args.session or None))
    print(json.dumps(res, indent=2, default=str))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""ghl_course_builder.py — Skill 06 browser-control builder for a GoHighLevel /
Convert and Flow COURSE in the Memberships area (spec §5.2, unit U14).

GoHighLevel has NO known public create API for a course (spec §3 marks it ASSUMED
until the first-hour Tier-1/Tier-2 tool-list check; the router flips primary
automatically if a create tool is found). The create + outline surface is
browser-only — this is the DUMB / DO layer driver, split from a SMART / THINK layer
exactly like the form and community builders:

  • THINK layer (this Python): resolves the plan — ZHC-prefixed course name, the
    modules→lessons tree (titles + body copy from the APPROVED source), lesson media
    as ghl_media CDN URLs (NEVER browser-uploaded), publish gated by may_publish
    (default DRAFT) — and emits, WITHOUT any browser, under <evidence_root>/routing/:
        course-plan.json · course-click-list.json · course-preflight.json
  • DUMB layer (agent-browser 0.27.0): Memberships → Courses list → search-first
    (idempotency) → Create → walk the outline module-by-module / lesson-by-lesson,
    saving per lesson (RateGovernor-spaced). EACH lesson is a ledgered, resumable
    step with its OWN F6 receipt, so a 40-lesson course resumes at lesson
    granularity. Verify = outline read-back (module/lesson names match the plan 1:1)
    + course preview render_check. ALWAYS delete the scratch course in cleanup.

D8 — ZERO INVENTED SELECTORS. Every in-area anchor is loaded from
`selectors-live-communities-courses.json`; a REQUIRED `capture-pending` anchor makes
the live walk STOP-and-report (never guesses CSS). dry-run + selftest are fully
network-free and prove the THINK layer + walk logic (incl. the STOP-and-report gate
and a mocked-browser lesson walk).

Usage:
    result = build_course(task, "/tmp/course-run-01")             # dry_run=True default
    result = build_course(task, "/tmp/course-run-01", dry_run=False)   # live (gated)
    python3 ghl_course_builder.py --dry-run --location-id LOC --course-name "Launch 101" \
        --plan-json /path/to/course.json
    python3 ghl_course_builder.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

# ── generic LIVE glue (form builder, imported not re-implemented) ─────────────
try:
    import ghl_form_builder as _ffb  # type: ignore
    _ab = _ffb._ab
    _eval = _ffb._eval
    _click = _ffb._click
    _fill = _ffb._fill
    _wait_text = _ffb._wait_text
    _snapshot = _ffb._snapshot
    _screenshot = _ffb._screenshot
    _shot = _ffb._shot
    _seed_and_land = _ffb._seed_and_land
    _close_session = _ffb._close_session
    _canonical_session = _ffb._canonical_session
    StopAndReport = _ffb.StopAndReport
    _slug = _ffb._slug
    _write_json = _ffb._write_json
    _log = _ffb._log
    _ts = _ffb._ts
    ensure_zhc_name = _ffb.ensure_zhc_name
    _HAVE_FFB = True
except Exception:  # noqa: BLE001
    _HAVE_FFB = False
    from ghl_community_builder import StopAndReport, _ts, _log, _write_json, _slug, ensure_zhc_name  # type: ignore

# ── shared selector/receipt layer (owned by ghl_community_builder) ────────────
import ghl_community_builder as _cb  # type: ignore
anchor = _cb.anchor
load_selectors = _cb.load_selectors
_receipt = _cb._receipt
_write_receipt = _cb._write_receipt
_governor = _cb._governor
_keepalive = _cb._keepalive
_capture_id_from_url = _cb._capture_id_from_url
# shared agent-browser 0.27.0 executor wrappers + list-scan idempotency (fixes a/b),
# owned by ghl_community_builder so both builders share ONE adapter. They read _cb's
# module globals at CALL time, so a test that patches _cb._ab/_eval/_snapshot is honored.
_ex_click = _cb._ex_click
_ex_fill = _cb._ex_fill
_ex_wait_text = _cb._ex_wait_text
_list_has = _cb._list_has

try:
    import ghl_object_router as _router  # type: ignore
    _HAVE_ROUTER = True
except Exception:  # noqa: BLE001
    _router = None  # type: ignore
    _HAVE_ROUTER = False


# ---------------------------------------------------------------------------
# THINK layer
# ---------------------------------------------------------------------------
def _resolve_modules(task: dict) -> List[dict]:
    raw = task.get("modules") or []
    out: List[dict] = []
    seen_mod: set = set()
    for mi, m in enumerate(raw):
        mtitle = (m.get("title") if isinstance(m, dict) else str(m)).strip()
        if not mtitle:
            continue
        mkey = mtitle.lower()
        if mkey in seen_mod:                 # dedupe modules (F14)
            continue
        seen_mod.add(mkey)
        lessons: List[dict] = []
        seen_les: set = set()
        for li, lraw in enumerate((m.get("lessons") if isinstance(m, dict) else []) or []):
            ltitle = (lraw.get("title") if isinstance(lraw, dict) else str(lraw)).strip()
            if not ltitle:
                continue
            lkey = ltitle.lower()
            if lkey in seen_les:
                continue
            seen_les.add(lkey)
            media = (lraw.get("media_url", "") if isinstance(lraw, dict) else "")
            if media and "firebase" in media.lower():
                raise StopAndReport("plan.media",
                                    f"lesson {ltitle!r} media_url is a Firebase URL — use a "
                                    "ghl_media CDN URL (media is never browser-routed; §5.2).")
            lessons.append({
                "index": li,
                "title": ltitle,
                "slug": _slug(f"{mtitle}-{ltitle}"),
                "body": (lraw.get("body", "") if isinstance(lraw, dict) else ""),
                "media_url": media,          # CDN URL only, inserted as a link/embed
            })
        out.append({"index": mi, "title": mtitle, "slug": _slug(mtitle), "lessons": lessons})
    return out


def plan_course(task: dict) -> dict:
    name = ensure_zhc_name(task.get("course_name", task.get("name", "New Course")))
    modules = _resolve_modules(task)
    approval = task.get("approval", "")
    publish = bool(task.get("publish", False)) and _may_publish(approval)
    return {
        "object_type": "course",
        "location_id": task.get("location_id", ""),
        "course_name": name,
        "slug": _slug(name),
        "product_type": task.get("product_type", "course"),
        "description": task.get("description", ""),
        "modules": modules,
        "lesson_count": sum(len(m["lessons"]) for m in modules),
        "publish": publish,                  # default DRAFT (may_publish gate)
        "idempotency_key": "zhc_name_search",
        "created_at": _ts(),
    }


def _may_publish(approval: str) -> bool:
    """Publish only on an explicit recorded approval token (mirror funnel may_publish)."""
    return str(approval).strip().lower() in ("approved", "publish", "go-live")


def emit_click_list(plan: dict) -> dict:
    steps: List[dict] = []

    def add(phase: str, action: str, target: str, note: str = "") -> None:
        steps.append({"n": len(steps) + 1, "phase": phase, "action": action,
                      "target": target, "note": note})

    add("M1", "nav", "Memberships → Courses/Products list",
        "SPA router.push after Memberships left-rail; never deep-link the builder")
    add("M2", "search", plan["course_name"],
        "search-first idempotency (F14): reuse a matching ZHC course, skip create")
    add("M3", "click", "Create Course", "list-page create button (capture-pending)")
    add("M3", "fill", "Course name", plan["course_name"])
    add("M3", "click", "Create", "confirm → capture COURSE_ID from location.href/iframe src")
    for m in plan["modules"]:
        add("M4", "add_module", m["title"], "each module = one ledgered step (resumable)")
        for l in m["lessons"]:
            add("M4", "add_lesson", f"{m['title']} ▸ {l['title']}",
                "each lesson = one ledgered step + its OWN F6 receipt (resume granularity)")
            if l["media_url"]:
                add("M4", "set", f"media(CDN) → {l['title']}",
                    "insert the ghl_media CDN URL as a link/embed — NEVER browser-upload")
            add("M4", "save", l["title"], "RateGovernor-spaced save per lesson")
    add("M5", "capture", "course preview URL", "read the preview URL for render_check")
    add("M5", "verify", "outline read-back + render_check",
        "module/lesson names match the plan 1:1 (snapshot) + preview 200")
    if plan["publish"]:
        add("M6", "publish", plan["course_name"], "publish (approval recorded)")
    else:
        add("M6", "note", "DRAFT", "default DRAFT — no publish (may_publish gate)")
    return {"object_type": "course", "total_steps": len(steps), "steps": steps,
            "selector_source": os.path.basename(_cb.SELECTORS_FILE),
            "notes": ["DUMB-BROWSER SCRIPT — in-area targets resolve through the selector "
                      "map; a capture-pending REQUIRED target STOPs-and-reports (D8).",
                      "Lesson media is never browser-routed — CDN links only.",
                      "Per-lesson receipts make a long course resumable at lesson granularity."]}


def _preflight(plan: dict) -> dict:
    checks: List[dict] = []

    def chk(name: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        checks.append({"check": name, "pass": bool(ok), "hard": hard, "detail": detail})

    chk("M-P1:zhc_name", plan["course_name"].startswith("ZHC "),
        f"course name must be ZHC-prefixed (got {plan['course_name']!r})")
    chk("M-P2:location_id", bool(plan["location_id"]),
        "location_id required (sub-account gate before any write)")
    chk("M-P3:has_modules", len(plan["modules"]) > 0, "a course needs >=1 module")
    chk("M-P4:has_lessons", plan["lesson_count"] > 0, "a course needs >=1 lesson")
    chk("M-P5:publish_gated", (not plan["publish"]) or _may_publish(""),
        "publish must be gated by a recorded approval (default DRAFT)", hard=False)
    hard_fail = [c for c in checks if c["hard"] and not c["pass"]]
    return {"pass": not hard_fail, "checks": checks,
            "stop_reason": (hard_fail[0]["detail"] if hard_fail else "")}


# ---------------------------------------------------------------------------
# DUMB layer — live outline walk (resumable, per-lesson receipts)
# ---------------------------------------------------------------------------
def _resume_done_lessons(evidence_root: str) -> set:
    """Read the lesson receipts already written → the set of completed lesson slugs
    (resume granularity, F6/§6). A resumed run SKIPS anything already receipted."""
    eco = os.path.join(evidence_root, "ecosystem")
    done: set = set()
    if os.path.isdir(eco):
        for fn in os.listdir(eco):
            if fn.startswith("lesson-") and fn.endswith(".json"):
                try:
                    with open(os.path.join(eco, fn), encoding="utf-8") as fh:
                        r = json.load(fh)
                    if r.get("created"):
                        done.add(r.get("slug"))
                except Exception:  # noqa: BLE001
                    continue
    return done


def _add_lesson(session: str, sels: dict, module: dict, lesson: dict,
                evidence_root: str, shot_n: List[int], gov, keep) -> dict:
    """Add ONE lesson under the open module. Every in-area anchor is a REQUIRED
    capture-pending gate today (STOP-and-report). Returns a lesson receipt."""
    title = lesson["title"]
    if keep.due():
        _ab(session, "eval", "--stdin", timeout=10, stdin="true")     # keepalive (F5)
    _ex_click(session, sels, "course.outline.add_lesson")
    _ex_fill(session, sels, "course.outline.lesson_title_input", title)
    if lesson["body"] or lesson["media_url"]:
        # body/media go into the lesson editor; media as a CDN link/embed (never upload)
        body = lesson["body"]
        if lesson["media_url"]:
            body = (body + f"\n[media]({lesson['media_url']})").strip()
        _ex_fill(session, sels, "course.outline.lesson_body_editor", body, required=False)
    gov.before_save()
    _ex_wait_text(session, title, timeout=15)
    if not _list_has(session, title):                                  # fix b: list-scan read-back
        raise StopAndReport(f"M4.lesson:{title}",
                            f"added lesson {title!r} but it did not appear in the outline "
                            "(snapshot-and-bind miss). STOP — no brute-force.")
    _screenshot(session, _shot(evidence_root, shot_n, f"m4-lesson-{lesson['slug']}"))
    return _receipt("lesson", lesson["slug"], "created",
                    request_shape={"module": module["title"], "title": title},
                    verify={"present_in_outline": True, "method": "snapshot"})


def _verify_outline(session: str, plan: dict) -> dict:
    """Read-back: every module + lesson title present in the live outline (list-scan)."""
    missing: List[str] = []
    for m in plan["modules"]:
        if not _list_has(session, m["title"]):
            missing.append(f"module:{m['title']}")
        for l in m["lessons"]:
            if not _list_has(session, l["title"]):
                missing.append(f"lesson:{l['title']}")
    return {"outline_match": not missing, "missing": missing, "method": "list-scan"}


def _capture_preview_url(session: str) -> str:
    js = ("(() => { const a=Array.from(document.querySelectorAll('a[href],input'))"
          ".map(e=>(e.href||e.value||'')).find(u=>/(course|preview|portal|memberships)/i.test(u)); "
          "return a||location.href||''; })()")
    return _eval(session, js, timeout=12) or ""


def _delete_course(session: str, sels: dict, plan: dict) -> dict:
    """Cleanup for a COURSE — a REAL delete (fix d). Unlike community groups, courses ARE
    deletable: the row 'More actions' menu has a Delete path (live-observed 2026-07-10) and
    Tier-2 ships delete_course/delete_course_* API tools. So the true 0-residue proof is
    scoped HERE. Idempotency + residue check are list-scans (fix b — no search box needed)."""
    try:
        _ex_click(session, sels, "shared_rail.memberships_left_rail")
        _ex_wait_text(session, "Memberships", timeout=15)
        _ex_click(session, sels, "course.list_page.row_actions")           # 'More actions'
        _ex_click(session, sels, "course.list_page.delete_menuitem")       # menu 'Delete'
        _ex_click(session, sels, "course.list_page.delete_confirm")        # dialog confirm (native)
        _ex_wait_text(session, "Create", timeout=12)
        residue = _list_has(session, plan["course_name"], plan["slug"])
        return {"cleanup_primitive": "delete", "deleted": not residue, "residue_in_list": residue}
    except StopAndReport as sr:
        return {"cleanup_primitive": "delete", "deleted": False,
                "residue_in_list": True, "stop": str(sr)}


def _live_build(task: dict, plan: dict, click_list: dict, preflight: dict,
                evidence_root: str, started: float, resume: bool) -> dict:
    if not (_HAVE_FFB and getattr(_ffb, "browser_manager", None) is not None):
        raise RuntimeError("LIVE build requires the Skill-6 tools/ modules importable — "
                           "run --dry-run/--selftest here, live only from the skill's tools/ dir.")
    location_id = plan["location_id"]
    os.environ["GHL_LOCATION_ID"] = location_id
    session = _canonical_session(location_id)
    sels = load_selectors()
    gov, keep = _governor(), _keepalive()
    shot_n: List[int] = [0]
    warnings: List[str] = []
    steps_done: List[str] = []
    course_id = ""
    preview_url = ""
    stop: Optional[StopAndReport] = None
    cleanup: Dict[str, Any] = {"attempted": False}
    done_lessons = _resume_done_lessons(evidence_root) if resume else set()

    _ffb.browser_manager.headless_guard()
    _ffb.browser_manager.assert_agent_browser_version()
    _cm = _ffb.browser_manager.browser_session(location_id)
    _sess = _cm.__enter__()
    if _sess:
        session = _sess
    try:
        auth = _seed_and_land(session, location_id, evidence_root)
        _write_json(os.path.join(evidence_root, "routing", "auth-receipt.json"),
                    {"landed": auth["landed"], "seeded_at": _ts()})

        # M1 — Memberships nav (verified-shared-rail).
        _ex_click(session, sels, "shared_rail.memberships_left_rail")
        _ex_wait_text(session, "Memberships", timeout=20)
        steps_done.append("M1:memberships")

        # M2 — LIST-SCAN idempotency (fix b): the search box is OPTIONAL, not required.
        existed = _list_has(session, plan["course_name"], plan["slug"])
        if existed and not resume:
            warnings.append("M2: a ZHC course of this name/slug already exists — REUSED")
            action = "reused"
        else:
            if not existed:
                _ex_click(session, sels, "course.list_page.create_course_button")
                _ex_fill(session, sels, "course.create_modal.name_input", plan["course_name"])
                gov.before_save()
                _ex_click(session, sels, "course.create_modal.create_confirm")   # exec:native
                _ex_wait_text(session, plan["course_name"][:18], timeout=25)
            course_id = _capture_id_from_url(session)
            action = "created" if not existed else "resumed"
        steps_done.append(f"M3:{action}")

        # M4 — outline: modules → lessons (resumable, per-lesson receipt).
        for m in plan["modules"]:
            if not (resume and all(l["slug"] in done_lessons for l in m["lessons"])):
                _ex_click(session, sels, "course.outline.add_module")
                _ex_fill(session, sels, "course.outline.module_title_input", m["title"])
                _ex_wait_text(session, m["title"][:18], timeout=15)
            for l in m["lessons"]:
                if l["slug"] in done_lessons:
                    steps_done.append(f"M4:resume-skip:{l['title'][:20]}")
                    continue
                rc = _add_lesson(session, sels, m, l, evidence_root, shot_n, gov, keep)
                _write_receipt(evidence_root, rc)
                steps_done.append(f"M4:lesson:{l['title'][:20]}")

        # M5 — verify outline + capture preview.
        outline = _verify_outline(session, plan)
        preview_url = _capture_preview_url(session)
        verify_block = {"outline": outline, "preview_url": preview_url}
        try:
            import ghl_verify  # type: ignore
            if preview_url:
                rec = ghl_verify.verify_page(
                    {"step": "course", "name": plan["course_name"], "page_id": plan["slug"],
                     "preview_url": preview_url, "marker": plan["course_name"]},
                    run_dir=evidence_root, live=True)
                verify_block.update({"http": rec.get("http"),
                                     "marker_in_rendered_dom": rec.get("marker_in_rendered_dom"),
                                     "render_errors": rec.get("render_errors", [])})
            else:
                verify_block["status"] = "deferred"
                verify_block["reason"] = "no preview URL captured — outline snapshot only"
        except Exception as exc:  # noqa: BLE001
            verify_block["status"] = "deferred"
            verify_block["reason"] = f"ghl_verify unavailable ({exc})"

        _write_receipt(evidence_root, _receipt(
            "course", plan["slug"], action if action != "resumed" else "created",
            response_id=course_id, request_shape={"name": plan["course_name"]},
            verify=verify_block))

        # M6 — publish gate (default DRAFT).
        if plan["publish"]:
            _ex_click(session, sels, "shared_rail.builder_save")     # capture-pending → STOP
            steps_done.append("M6:publish")
        else:
            steps_done.append("M6:draft")

        _write_json(os.path.join(evidence_root, "routing", "course-built.json"), {
            "course_id": course_id, "course_name": plan["course_name"],
            "preview_url": preview_url, "verify": verify_block,
            "modules": [{"title": m["title"], "lessons": [l["title"] for l in m["lessons"]]}
                        for m in plan["modules"]],
            "published": bool(plan["publish"]),
            "warnings": warnings, "steps_done": steps_done, "built_at": _ts()})
    except StopAndReport as sr:
        stop = sr
        _log(f"STOP-and-report @ {sr.step}: {sr.reason}")
    except Exception as exc:  # noqa: BLE001
        stop = StopAndReport("unexpected", f"{type(exc).__name__}: {exc}")
    finally:
        cleanup["attempted"] = True
        try:
            if course_id or plan["course_name"]:
                cleanup.update(_delete_course(session, sels, plan))
            else:
                cleanup["deleted"] = True
        except Exception as exc:  # noqa: BLE001
            cleanup["deleted"] = False
            cleanup["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                _cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            _close_session(location_id)
        _write_json(os.path.join(evidence_root, "routing", "cleanup.json"), cleanup)

    summary = _router.reduce_receipts(evidence_root) if _HAVE_ROUTER else {}
    duration = time.monotonic() - started
    if stop is not None:
        return {"ok": False, "object_type": "course", "duration_s": duration,
                "course_id": course_id, "preview_url": preview_url,
                "error": str(stop), "stop_step": stop.step, "stop_reason": stop.reason,
                "warnings": warnings, "steps_done": steps_done, "cleanup": cleanup,
                "receipts_summary": summary, "dry_run": False}
    return {"ok": True, "object_type": "course", "duration_s": duration,
            "course_id": course_id, "preview_url": preview_url,
            "warnings": warnings, "steps_done": steps_done, "cleanup": cleanup,
            "receipts_summary": summary, "dry_run": False}


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def build_course(task: dict, evidence_root: str, *, dry_run: bool = True,
                 resume: bool = False) -> dict:
    started = time.monotonic()
    dry_run = bool(task.get("dry_run", dry_run))
    os.makedirs(os.path.join(evidence_root, "routing"), exist_ok=True)
    os.makedirs(os.path.join(evidence_root, "shots"), exist_ok=True)

    plan = plan_course(task)
    preflight = _preflight(plan)
    click_list = emit_click_list(plan)
    _write_json(os.path.join(evidence_root, "routing", "course-plan.json"), plan)
    _write_json(os.path.join(evidence_root, "routing", "course-click-list.json"), click_list)
    _write_json(os.path.join(evidence_root, "routing", "course-preflight.json"), preflight)

    if not preflight["pass"]:
        return {"ok": False, "object_type": "course", "duration_s": time.monotonic() - started,
                "preflight": preflight, "error": preflight["stop_reason"], "dry_run": dry_run}

    if dry_run:
        disclosure = (_router.tier_disclosure(_router.route("course").rails[0])
                      if _HAVE_ROUTER else "[GHL tier used: 4 — ghl_course_builder.py]")
        _log(f"[dry-run] course plan + click list ({click_list['total_steps']} steps, "
             f"{plan['lesson_count']} lessons) written. {disclosure}")
        return {"ok": True, "object_type": "course", "duration_s": time.monotonic() - started,
                "plan": plan, "click_list": click_list, "preflight": preflight,
                "tier_disclosure": disclosure, "dry_run": True}

    return _live_build(task, plan, click_list, preflight, evidence_root, started, resume)


# ---------------------------------------------------------------------------
# Self-test — no network, no browser
# ---------------------------------------------------------------------------
def _selftest() -> int:  # noqa: C901
    import tempfile
    errors: List[str] = []

    task = {"course_name": "Launch 101", "location_id": "LOC",
            "modules": [
                {"title": "Welcome", "lessons": [
                    {"title": "Intro", "body": "hello"},
                    {"title": "Intro", "body": "dup"},          # dedupe
                    {"title": "Setup", "media_url": "https://storage.leadconnectorhq.com/x.mp4"}]},
                {"title": "Welcome", "lessons": []},            # dup module dropped
                {"title": "Build", "lessons": [{"title": "First page"}]}]}
    plan = plan_course(task)
    if plan["course_name"] != "ZHC Launch 101":
        errors.append(f"zhc name wrong: {plan['course_name']!r}")
    if [m["title"] for m in plan["modules"]] != ["Welcome", "Build"]:
        errors.append(f"module dedupe failed: {[m['title'] for m in plan['modules']]}")
    if plan["modules"][0]["lessons"][0]["title"] != "Intro" or len(plan["modules"][0]["lessons"]) != 2:
        errors.append("lesson dedupe failed")
    if plan["lesson_count"] != 3:
        errors.append(f"lesson_count wrong: {plan['lesson_count']}")
    if plan["publish"]:
        errors.append("default must be DRAFT (publish False)")

    # publish requires recorded approval
    p2 = plan_course({**task, "publish": True})
    if p2["publish"]:
        errors.append("publish without approval must stay DRAFT")
    p3 = plan_course({**task, "publish": True, "approval": "approved"})
    if not p3["publish"]:
        errors.append("publish with approval should be True")

    # Firebase media rejected
    try:
        plan_course({"course_name": "X", "location_id": "L",
                     "modules": [{"title": "M", "lessons": [
                         {"title": "L", "media_url": "https://firebasestorage.googleapis.com/x"}]}]})
        errors.append("firebase media not rejected")
    except StopAndReport:
        pass

    # preflight fails on no modules
    if _preflight(plan_course({"course_name": "Empty", "location_id": "L", "modules": []}))["pass"]:
        errors.append("preflight should fail with no modules")

    # dry-run
    with tempfile.TemporaryDirectory() as tmp:
        res = build_course(task, tmp, dry_run=True)
        if not res.get("dry_run") or "click_list" not in res:
            errors.append("dry-run missing click_list")
        phases = {s["phase"] for s in res["click_list"]["steps"]}
        for want in ("M1", "M2", "M3", "M4", "M5", "M6"):
            if want not in phases:
                errors.append(f"click list missing phase {want}")
        if not os.path.isfile(os.path.join(tmp, "routing", "course-plan.json")):
            errors.append("course-plan.json not written")

    # D8 gate: course create button is capture-pending → STOP
    sels = load_selectors()
    raised = False
    try:
        anchor(sels, "course.list_page.create_course_button")
    except StopAndReport:
        raised = True
    if not raised:
        errors.append("capture-pending course anchor did NOT STOP (D8 gate broken)")

    # cleanup reality (fix d): course = TRUE delete; community group = inactivate (no delete)
    reality = sels.get("_cleanup_reality", {})
    if reality.get("course", {}).get("primitive") != "delete" or \
            not reality.get("course", {}).get("has_api_delete"):
        errors.append("fix d: course cleanup reality should be true delete + API delete")
    if reality.get("community_group", {}).get("primitive") != "inactivate" or \
            reality.get("community_group", {}).get("has_ui_delete"):
        errors.append("fix d: community_group cleanup reality should be inactivate / no delete")

    # mocked-browser lesson walk proves REAL code routed through the executor (fix a) +
    # resume skip. Reads/clicks funnel through _cb (shared wrappers + list-scan), so we
    # patch _cb globals (ab/eval/snapshot) and this module's _screenshot.
    if _HAVE_FFB:
        import copy
        locked = copy.deepcopy(sels)
        for t in locked["course"]["outline"].values():
            t["status"] = "locked"
        present = {"Welcome"}
        calls: List[tuple] = []
        evals: List[str] = []

        def fake_ab(session, *args, timeout=30, stdin=None):
            calls.append(args)
            verb = args[0] if args else ""
            if verb == "wait" and len(args) >= 3:
                present.add(args[2].strip("'\""))
            snap = " ".join(sorted(present)) if verb == "snapshot" else ""
            return subprocess.CompletedProcess(args=list(args), returncode=0, stdout=snap, stderr="")

        def fake_eval(session, js, timeout=20):
            evals.append(js)
            return "CLICKED:x" if ".click()" in js else ""

        orig_ab, orig_eval, orig_snap = _cb._ab, _cb._eval, _cb._snapshot
        try:
            _cb._ab = fake_ab
            _cb._eval = fake_eval
            _cb._snapshot = lambda s, timeout=20: (fake_ab(s, "snapshot").stdout or "")
            globals()["_screenshot"] = lambda s, p: None
            with tempfile.TemporaryDirectory() as tmp2:
                os.makedirs(os.path.join(tmp2, "shots"), exist_ok=True)
                rc = _add_lesson("s", locked, {"title": "Welcome", "slug": "welcome"},
                                 {"title": "Intro", "slug": "welcome-intro", "body": "hi",
                                  "media_url": "https://storage.leadconnectorhq.com/x.mp4"},
                                 tmp2, [0], _cb._NoopGovernor(), _cb._NoopKeepalive())
                if rc["action"] != "created":
                    errors.append(f"mocked lesson walk: expected created (got {rc['action']})")
                if not any(c and c[0] == "find" for c in calls):
                    errors.append("mocked lesson walk: no real `find` command (executor skeleton?)")
                _write_receipt(tmp2, rc)
                done = _resume_done_lessons(tmp2)
                if "welcome-intro" not in done:
                    errors.append("resume: written lesson receipt not detected as done")
        finally:
            _cb._ab, _cb._eval, _cb._snapshot = orig_ab, orig_eval, orig_snap
            globals()["_screenshot"] = _ffb._screenshot

    if _HAVE_ROUTER:
        try:
            _router.route("course")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"router missing course: {exc}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — course THINK + click list + D8 gate + mocked lesson walk + "
          "resume (no network / no browser)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_course_builder",
        description="GHL (Convert and Flow) COURSE builder — Skill 06. Default --dry-run. "
                    "Live path STOP-and-reports on any capture-pending selector (D8) until "
                    "SELECTORS-LIVE-course.md is captured.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--resume", action="store_true", help="Skip lessons already receipted")
    p.add_argument("--evidence-root", default="/tmp/course-run-01")
    p.add_argument("--course-name", default="New Course")
    p.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID", ""))
    p.add_argument("--plan-json", default="", help="Path to a JSON with modules[] (THINK input)")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    task: Dict[str, Any] = {"course_name": args.course_name, "location_id": args.location_id}
    if args.plan_json and os.path.isfile(args.plan_json):
        with open(args.plan_json, encoding="utf-8") as fh:
            task.update(json.load(fh))
    result = build_course(task, args.evidence_root, dry_run=args.dry_run, resume=args.resume)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())

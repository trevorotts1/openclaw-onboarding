#!/usr/bin/env python3
"""ghl_course_builder.py — Skill 06 API-FIRST course coordinator (WF07 / doc 1 s8).

TWO RAILS, ONE FACADE
---------------------
  • API-FIRST (default when a public adapter is supplied) — the THINK layer
    validates the course plan (logical-key identity, parent-before-child
    categories, required content) and ``CourseCoordinator`` drives the shared
    typed Courses public adapter: create/reuse the course shell, create
    categories parent-before-child, create each lesson with its OWN checkpoint
    (per-lesson resume), hand media/assessment content to the WF08 seam, apply
    deterministic final sequencing with a read-back, associate a Community group
    ONLY when the plan asks, then reduce an aggregate course-delivery receipt
    (``ghl_course_delivery.py``). NO browser is started on this path.
  • MANAGED-BROWSER FALLBACK (``execution_mode="browser"``) — the Phase-B
    proven DUMB/DO layer driver: Memberships → Courses list → search-first
    idempotency → outline walk with a per-lesson ledger and its own F6 receipt
    → outline read-back + preview render_check → cleanup. PRESERVED, never
    deleted; it is simply no longer the only rail.

``build_course(...)`` and the CLI shape are compatible: an existing caller that
supplies no adapter keeps the exact browser behaviour it had.

D8 — ZERO INVENTED SELECTORS. Every in-area anchor is loaded from
`selectors-live-communities-courses.json`; a REQUIRED `capture-pending` anchor makes
the live browser walk STOP-and-report (never guesses CSS). dry-run + selftest are
fully network-free and prove the THINK layer + walk logic.

Usage:
    result = build_course(task, "/tmp/course-run-01")             # dry_run=True default
    result = build_course(task, "/tmp/course-run-01", dry_run=False, adapter=adapter)
    python3 ghl_course_builder.py --dry-run --location-id LOC --course-name "Launch 101" \
        --plan-json /path/to/course.json [--execution-mode api|browser]
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

# U8/U10 — shared phase-checkpoint store + the uniform RUN REPORT emitter.
import ghl_run_state  # noqa: E402
from ghl_run_state import PhaseSpec, run_phase  # noqa: E402

# WF07 — plan validation, logical-key identity map and the aggregate delivery
# reducer live in their own pure module so the coordinator and the tests share
# ONE definition of "addressable course object" and "delivered".
try:
    import ghl_course_delivery as _delivery  # noqa: E402
    _HAVE_DELIVERY = True
except Exception:  # noqa: BLE001
    _delivery = None  # type: ignore
    _HAVE_DELIVERY = False

# ── U8: the course builder's declared phase walk ────────────────────────────────
# The course builder ALREADY had the skill's only resume — a per-LESSON receipt
# skip inside M4 (`_resume_done_lessons`). That is FINER than a phase, and it is
# kept exactly as it was: `--resume` with no run id still means "skip lessons
# already receipted". What is new is the run-id-keyed PHASE ledger around it, so
# the course builder reports the same RUN REPORT and takes the same
# `--resume <run_id>` as every other builder — with the lesson-level skip still
# doing the fine-grained work inside M4.
# Sentinel for a BARE `--resume` (legacy: lesson-receipt skip, no run id). It must
# not collide with any real run id, hence the spaces.
_RESUME_LESSONS_ONLY = "__lessons_only__"

COURSE_PHASES: List[PhaseSpec] = [
    PhaseSpec("plan",       "course plan (THINK)", resumable=False),
    PhaseSpec("preflight",  "preflight gate",      resumable=False),
    PhaseSpec("click_list", "click list",          resumable=False),
    PhaseSpec("m_walk",     "M1–M5 — create course + modules + lessons (per-lesson resume)"),
]
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
_reactive_fill = _cb._reactive_fill
_nav_to_list = _cb._nav_to_list
_scoped_card_kebab = _cb._scoped_card_kebab
_select_dropdown_option = _cb._select_dropdown_option
_click_bottom_button = _cb._click_bottom_button

try:
    import ghl_object_router as _router  # type: ignore
    _HAVE_ROUTER = True
except Exception:  # noqa: BLE001
    _router = None  # type: ignore
    _HAVE_ROUTER = False


# ---------------------------------------------------------------------------
# THINK layer
# ---------------------------------------------------------------------------
def _unique_key(base: str, used: set, index: int) -> str:
    """A stable logical key from a title, disambiguated by DECLARATION INDEX.

    Duplicate display titles are legal (A09); the index suffix is what keeps two
    lessons both called "Introduction" addressable as distinct objects. The same
    input always yields the same keys, which is what makes resume and
    reconciliation deterministic.
    """
    key = _slug(base or f"item-{index + 1}") or f"item-{index + 1}"
    if key in used:
        key = f"{key}-{index + 1}"
    used.add(key)
    return key


def _resolve_modules(task: dict) -> List[dict]:
    """Resolve the plan's module/lesson tree.

    IDENTITY IS THE LOGICAL KEY, NEVER THE TITLE. A module/lesson may supply its
    own ``module_key`` / ``lesson_key``; otherwise one is derived from the title
    and disambiguated by declaration index. Titles are display text: two lessons
    named "Introduction" both survive.
    """
    raw = task.get("modules") or []
    out: List[dict] = []
    used_mod: set = set()
    for mi, m in enumerate(raw):
        mtitle = (m.get("title") if isinstance(m, dict) else str(m)).strip()
        if not mtitle:
            continue
        mkey = (m.get("module_key") if isinstance(m, dict) else "") or ""
        mkey = str(mkey).strip() or _unique_key(mtitle, used_mod, mi)
        used_mod.add(mkey)
        lessons: List[dict] = []
        used_les: set = set()
        for li, lraw in enumerate((m.get("lessons") if isinstance(m, dict) else []) or []):
            ltitle = (lraw.get("title") if isinstance(lraw, dict) else str(lraw)).strip()
            if not ltitle:
                continue
            lkey = (lraw.get("lesson_key") if isinstance(lraw, dict) else "") or ""
            lkey = str(lkey).strip() or _unique_key(ltitle, used_les, li)
            used_les.add(lkey)
            media = (lraw.get("media_url", "") if isinstance(lraw, dict) else "")
            if media and "firebase" in media.lower():
                raise StopAndReport("plan.media",
                                    f"lesson {ltitle!r} media_url is a Firebase URL — use a "
                                    "ghl_media CDN URL (media is never browser-routed; §5.2).")
            body = (lraw.get("body", lraw.get("description", ""))
                    if isinstance(lraw, dict) else "")
            description_ref = (lraw.get("description_ref", "")
                               if isinstance(lraw, dict) else "")
            lessons.append({
                "index": li,
                "lesson_key": lkey,
                "identity_key": f"lesson:{mkey}/{lkey}",
                "title": ltitle,
                "slug": _slug(f"{mtitle}-{ltitle}-{lkey}"),
                "body": body,
                "description": body,
                "description_ref": description_ref,
                "position": (lraw.get("position", li + 1)
                             if isinstance(lraw, dict) else li + 1),
                "visibility": (lraw.get("visibility", "draft")
                               if isinstance(lraw, dict) else "draft"),
                "asset_refs": list(lraw.get("asset_refs") or [])
                if isinstance(lraw, dict) else [],
                "assessment_ref": (lraw.get("assessment_ref") if isinstance(lraw, dict)
                                   else None),
                # A legacy lesson that only carries a title has no approved content
                # to require; only an explicit reference (or an explicit flag) makes
                # content a delivery requirement.
                "required_for_delivery": bool(
                    lraw.get("required_for_delivery",
                             bool(description_ref or body))
                ) if isinstance(lraw, dict) else False,
                "media_url": media,          # CDN URL only, inserted as a link/embed
            })
        out.append({
            "index": mi,
            "module_key": mkey,
            "identity_key": f"module:{mkey}",
            "parent_module_key": (m.get("parent_module_key", "")
                                  if isinstance(m, dict) else ""),
            "title": mtitle,
            "slug": _slug(mtitle),
            "position": (m.get("position", mi + 1) if isinstance(m, dict) else mi + 1),
            "visibility": (m.get("visibility", "draft") if isinstance(m, dict) else "draft"),
            "lessons": lessons,
        })
    return out


def plan_course(task: dict) -> dict:
    name = ensure_zhc_name(task.get("course_name", task.get("name", "New Course")))
    modules = _resolve_modules(task)
    approval = task.get("approval", "")
    publish = bool(task.get("publish", False)) and _may_publish(approval)
    plan = {
        "schema_version": ("course-build-plan/1.0.0" if _HAVE_DELIVERY else "skill6-course-plan/1"),
        "object_type": "course",
        "run_id": task.get("run_id", ""),
        "location_id": task.get("location_id", ""),
        "course_key": task.get("course_key") or _slug(name),
        "title": name,
        "course_name": name,
        "slug": _slug(name),
        "product_type": task.get("product_type", "course"),
        "description": task.get("description", ""),
        "modules": modules,
        "lesson_count": sum(len(m["lessons"]) for m in modules),
        "publish": publish,                  # default DRAFT (may_publish gate)
        "release_intent": task.get("release_intent", "draft_only"),
        "existing_course_product_id": task.get("existing_course_product_id"),
        "community": task.get("community") or {},
        "offer_plan_ref": task.get("offer_plan_ref"),
        "idempotency_key": "logical_key_manifest",
        "created_at": _ts(),
    }
    if _HAVE_DELIVERY:
        errors = _delivery.validate_plan(plan)
        if errors:
            raise _delivery.CoursePlanError(errors)
    return plan


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


def api_preflight(plan: dict, adapter: Any = None, *, required: bool = True) -> dict:
    """API-ONLY preflight — no browser capability probe, no session, no page.

    The old preflight implicitly required a managed browser because the only
    create rail was the UI. An outline build is now a pure public-API operation,
    so this gate checks exactly what an API build needs: a validated plan, a
    location, and a public adapter. It NEVER starts agent-browser.
    """
    checks: List[dict] = []

    def chk(name: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        checks.append({"check": name, "pass": bool(ok), "hard": hard, "detail": detail})

    chk("A-P1:location_id", bool(plan.get("location_id")),
        "location_id required (tenant gate before any write)")
    chk("A-P2:has_modules", len(plan.get("modules") or []) > 0,
        "a course needs >=1 module")
    chk("A-P3:has_lessons", int(plan.get("lesson_count") or 0) > 0,
        "a course needs >=1 lesson")
    if _HAVE_DELIVERY:
        errs = _delivery.validate_plan(plan)
        chk("A-P4:plan_valid", not errs, "; ".join(errs[:5]))
    chk("A-P5:public_adapter", adapter is not None,
        "an API build requires the shared typed public adapter (WF06); "
        "no browser is started to compensate", hard=required)
    chk("A-P6:no_browser_required", True,
        "public outline build performs no browser capability probe (doc 1 s8.4 step 2)",
        hard=False)
    hard_fail = [c for c in checks if c["hard"] and not c["pass"]]
    return {"pass": not hard_fail, "mode": "api", "browser_required": False,
            "checks": checks,
            "stop_reason": (hard_fail[0]["detail"] if hard_fail else "")}


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
    """Read the lesson receipts already written → the set of completed lesson
    identities (resume granularity, F6/§6). A resumed run SKIPS anything already
    receipted.

    Both identity spellings are returned: the legacy receipt ``slug`` and the
    WF07 ``verify.logical_key`` (``<module_key>/<lesson_key>``). Logical keys are
    what the API coordinator resumes on, so a kill mid-course never duplicates a
    lesson whose display title happens to collide with another one.
    """
    eco = os.path.join(evidence_root, "ecosystem")
    done: set = set()
    if os.path.isdir(eco):
        for fn in os.listdir(eco):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(eco, fn), encoding="utf-8") as fh:
                    r = json.load(fh)
                if not r.get("created"):
                    continue
                if r.get("slug"):
                    done.add(r.get("slug"))
                logical = (r.get("verify") or {}).get("logical_key")
                if logical:
                    done.add(logical)
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
    # Phase B live flow: '+ Add Content' -> 'Add Lesson' -> title (REACTIVE fill, else the
    # submit stays DISABLED) -> REQUIRED 'Select Module' dropdown -> 'Create Lesson'.
    _ex_click(session, sels, "course.outline.add_content")
    _ex_click(session, sels, "course.outline.add_lesson")
    if not _reactive_fill(session, "Enter lesson title", title):
        _ex_fill(session, sels, "course.outline.lesson_title_input", title)   # find-fill fallback
    _ex_click(session, sels, "course.outline.lesson_module_select")           # open 'Select Module'
    if not _select_dropdown_option(session, module["title"]):
        raise StopAndReport(f"M4.lesson-module:{title}",
                            f"could not select the required module {module['title']!r} for "
                            f"lesson {title!r} (Create Lesson stays disabled) — STOP.")
    gov.before_save()
    _ex_click(session, sels, "course.outline.lesson_create_confirm")          # 'Create Lesson'
    _ex_wait_text(session, title, timeout=15)
    if not _list_has(session, title):                                  # fix b: list-scan read-back
        raise StopAndReport(f"M4.lesson:{title}",
                            f"added lesson {title!r} but it did not appear in the outline "
                            "(snapshot-and-bind miss). STOP — no brute-force.")
    _screenshot(session, _shot(evidence_root, shot_n, f"m4-lesson-{lesson['slug']}"))
    return _receipt("lesson", lesson["slug"], "created",
                    request_shape={"module": module["title"], "title": title},
                    verify={"present_in_outline": True, "method": "snapshot"})


def _build_outline(session: str, sels: dict, plan: dict, evidence_root: str,
                   shot_n: List[int], gov, keep, resume: bool, done_lessons: set, *,
                   add_lesson=None, write_receipt=None, log=None) -> dict:
    """U106 — smoke-first gated outline bulk-add (companion to U30's smoke_first
    on the iframe/page-code drag surfaces). The FIRST not-yet-done lesson across
    the plan is the ONE proof-create (ghl_run_state.smoke_first): only a
    PASSING store-delta verify (the lesson actually present in the outline)
    unlocks the rest of the — potentially many-lesson — walk. A failing smoke
    raises SmokeFirstFailed BEFORE any further module/lesson is attempted.

    `add_lesson`/`write_receipt`/`log` are dependency-injected (default: the
    real `_add_lesson` / `_write_receipt` / `_log`) so this is directly
    unit-testable without a live browser. Module creation + resume-skip
    bookkeeping is unchanged from the original inline walk."""
    _add = add_lesson or _add_lesson
    _wr = write_receipt or _write_receipt
    _lg = log or _log
    steps_done: List[str] = []

    first_ref = None
    for m in plan["modules"]:
        for l in m["lessons"]:
            if l["slug"] not in done_lessons:
                first_ref = (m["slug"], l["slug"])
                break
        if first_ref:
            break

    smoked = False
    for m in plan["modules"]:
        if not (resume and all(l["slug"] in done_lessons for l in m["lessons"])):
            _ex_click(session, sels, "course.outline.add_module")
            _ex_fill(session, sels, "course.outline.module_title_input", m["title"])
            _ex_wait_text(session, m["title"][:18], timeout=15)
        for l in m["lessons"]:
            if l["slug"] in done_lessons:
                steps_done.append(f"M4:resume-skip:{l['title'][:20]}")
                continue
            if (not smoked) and first_ref == (m["slug"], l["slug"]):
                def _create_smoke(_m=m, _l=l) -> dict:
                    return _add(session, sels, _m, _l, evidence_root, shot_n, gov, keep)

                def _verify_smoke(rc: dict) -> dict:
                    return {"ok": bool((rc.get("verify") or {}).get("present_in_outline")),
                            "receipt": rc}

                rc = ghl_run_state.smoke_first(f"M4:smoke:{l['slug']}", _create_smoke,
                                               _verify_smoke, log=_lg)
                smoked = True
            else:
                rc = _add(session, sels, m, l, evidence_root, shot_n, gov, keep)
            _wr(evidence_root, rc)
            steps_done.append(f"M4:lesson:{l['title'][:20]}")
    return {"steps_done": steps_done}


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


def _delete_course(session: str, sels: dict, plan: dict, location_id: str = "") -> dict:
    """TRUE 0-residue delete (fix d) — SAFETY-CRITICAL on a POPULATED account: SEARCH-NARROW
    to isolate the scratch course, then click ITS OWN card kebab (card-scoped), 'Delete', TYPE
    the literal CONFIRM guard token into the type-to-proceed box, then Confirm. NEVER a blind
    first-'More actions' (that would hit a REAL member course). Phase B live-proven 0-residue."""
    name = plan["course_name"]
    try:
        if location_id:
            _nav_to_list(session, location_id, sels, "course.routes.courses_list", "Create New")
        _ex_fill(session, sels, "course.list_page.search_box", name, required=False)  # isolate
        _ex_wait_text(session, name[:18], timeout=10)
        if not _scoped_card_kebab(session, name):
            raise StopAndReport("delete.kebab",
                                f"could not open the {name!r} card kebab (card-scoped) — "
                                "course NOT deleted (never blind-delete a real course).")
        _ex_click(session, sels, "course.list_page.delete_menuitem")          # 'Delete'
        if not _reactive_fill(session, "CONFIRM", "CONFIRM"):                  # type-to-proceed guard
            raise StopAndReport("delete.confirm-type",
                                "could not type the CONFIRM guard token — course NOT deleted.")
        _ex_click(session, sels, "course.list_page.delete_confirm")           # 'Confirm'
        _ex_wait_text(session, "Create New", timeout=12)
        residue = _list_has(session, name, plan["slug"])
        return {"cleanup_primitive": "delete", "deleted": not residue, "residue_in_list": residue,
                "safety": "search-narrowed + card-scoped + type-CONFIRM"}
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
        # U106: smoke-first gated — see _build_outline().
        outline_res = _build_outline(session, sels, plan, evidence_root, shot_n, gov, keep,
                                     resume, done_lessons)
        steps_done.extend(outline_res["steps_done"])

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
                cleanup.update(_delete_course(session, sels, plan, location_id))
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
# API-FIRST COORDINATOR (WF07 / doc 1 s8.4)
#
# This is the published coordinator interface (WF07-CP01). Callers inject:
#   • ``adapter``      — the shared typed Courses public adapter (WF06). Required
#                        keyword calls, each returning a dict carrying ``id``:
#                          create_course(location_id=, payload=)
#                          get_course(location_id=, course_id=)          [optional]
#                          create_category(location_id=, payload=)
#                          create_lesson(location_id=, payload=)
#                          list_lessons(location_id=, course_id=)        [optional]
#                          sequence(location_id=, course_id=, ordering=)[optional]
#   • ``media_binder`` — the WF08 native-content seam. Optional; called only when
#                        the plan actually requests media/attachments.
#   • ``association``  — the WF09 Learning-association seam. Called ONLY when the
#                        plan sets ``community.required`` (a standalone course
#                        needs no group).
# No browser is opened on this path. The managed-browser walk stays reachable as
# an EXPLICIT fallback (``execution_mode="browser"``), never as the default.
# ---------------------------------------------------------------------------
COURSE_MANIFEST_REL = os.path.join("routing", "course-identity-manifest.json")


def _manifest_path(evidence_root: str) -> str:
    return os.path.join(str(evidence_root), COURSE_MANIFEST_REL)


def load_course_manifest(evidence_root: str) -> dict:
    """The recorded logical-key -> object-ID manifest (reconciliation by RECORDED
    ID, never by title). Absent/corrupt reads as an empty manifest."""
    path = _manifest_path(evidence_root)
    if not os.path.isfile(path):
        return {"schema_version": "skill6-course-identity-manifest/1", "objects": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict):
            raise ValueError("manifest is not an object")
        doc.setdefault("objects", {})
        return doc
    except Exception:  # noqa: BLE001 — a corrupt manifest must not fake identity
        return {"schema_version": "skill6-course-identity-manifest/1", "objects": {},
                "corrupt": True}


def save_course_manifest(evidence_root: str, manifest: dict) -> str:
    path = _manifest_path(evidence_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def _adapter_call(adapter: Any, name: str, **kwargs) -> dict:
    """Call one adapter method honestly: absent method or non-dict return is a
    STOP, never a silent no-op that would let an unbuilt object look created."""
    fn = getattr(adapter, name, None)
    if fn is None:
        raise StopAndReport(f"adapter.{name}",
                            f"the public course adapter does not implement {name}() — "
                            "an API-only outline build cannot continue")
    out = fn(**kwargs)
    if not isinstance(out, dict):
        raise StopAndReport(f"adapter.{name}",
                            f"adapter.{name}() returned {type(out).__name__}, not a dict")
    return out


def _adapter_optional(adapter: Any, name: str, **kwargs) -> Any:
    fn = getattr(adapter, name, None)
    if fn is None:
        return None
    try:
        return fn(**kwargs)
    except Exception:  # noqa: BLE001 — optional capability, recorded not fatal
        return None


class CourseCoordinator:
    """API-first, resumable course coordinator over an injected public adapter."""

    def __init__(self, plan: dict, evidence_root: str, *,
                 adapter: Any,
                 media_binder: Any = None,
                 association: Any = None,
                 state: Optional["ghl_run_state.RunState"] = None,
                 log: Any = None) -> None:
        self.plan = plan
        self.evidence_root = str(evidence_root)
        self.adapter = adapter
        self.media_binder = media_binder
        self.association = association
        self.state = state
        self._log = log or _log
        self.manifest = load_course_manifest(self.evidence_root)
        self.objects: Dict[str, dict] = self.manifest.setdefault("objects", {})
        self.steps: List[str] = []
        self.warnings: List[str] = []
        self.course_id: Optional[str] = None

    # -- helpers ----------------------------------------------------------
    def _remember(self, logical_key: str, object_type: str, object_id: str,
                  action: str, visibility: str = "") -> None:
        self.objects[logical_key] = {
            "object_type": object_type, "object_id": object_id,
            "action": action, "visibility": visibility or None,
        }
        save_course_manifest(self.evidence_root, self.manifest)

    def _record(self, object_type: str, logical_key: str, action: str, *,
                object_id: Optional[str] = None, verify: Optional[dict] = None,
                request_shape: Any = None) -> Optional[str]:
        try:
            receipt = _receipt(object_type, logical_key.replace("/", "_"), action,
                               response_id=object_id, verify=verify or {},
                               request_shape=request_shape)
            return _write_receipt(self.evidence_root, receipt)
        except Exception as exc:  # noqa: BLE001 — receipt failure is surfaced, not hidden
            self.warnings.append(f"receipt {object_type}:{logical_key} failed: {exc}")
            return None

    def _phase(self, name: str, fn):
        return run_phase(self.state, name, fn, log=self._log)

    # -- steps -------------------------------------------------------------
    def _ensure_course_shell(self) -> dict:
        location = self.plan["location_id"]
        # Reconcile by the RECORDED ID first: a resumed run must never create a
        # second course shell for the same logical plan.
        prior = self.objects.get("course")
        if isinstance(prior, dict) and prior.get("object_id"):
            got = _adapter_optional(self.adapter, "get_course",
                                    location_id=location,
                                    course_id=str(prior["object_id"]))
            if got is None:
                self.warnings.append(
                    f"recorded course id {prior['object_id']!r} could not be re-read on "
                    "this run — reusing the recorded id, not creating a duplicate")
            self.course_id = str(prior["object_id"])
            self.steps.append("course:reused:manifest")
            return {"id": self.course_id, "action": "reused"}
        existing = self.plan.get("existing_course_product_id")
        existing_id = existing.get("id") if isinstance(existing, dict) else (
            existing if isinstance(existing, str) else None)
        if existing_id:
            got = _adapter_optional(self.adapter, "get_course",
                                    location_id=location, course_id=existing_id)
            if isinstance(got, dict) and got.get("id"):
                self.course_id = str(got["id"])
                self.steps.append("course:reused:recorded_id")
                self._record("course", self.plan["course_key"], "reused",
                             object_id=self.course_id,
                             verify={"ok": True, "matched_by": "recorded_course_id"})
                return {"id": self.course_id, "action": "reused"}
            self.warnings.append(
                f"existing_course_product_id {existing_id!r} was not found in "
                f"location {location!r} — creating instead of guessing")
        payload = {"title": self.plan["title"]}
        if self.plan.get("description"):
            payload["description"] = self.plan["description"]
        out = _adapter_call(self.adapter, "create_course",
                            location_id=location, payload=payload)
        cid = out.get("id")
        if not cid:
            raise StopAndReport("course.create", "create_course returned no id")
        self.course_id = str(cid)
        self.steps.append("course:created")
        self._remember("course", "course", self.course_id, "created")
        self._record("course", self.plan["course_key"], "created",
                     object_id=self.course_id,
                     verify={"ok": True, "created": True}, request_shape=payload)
        return {"id": self.course_id, "action": "created"}

    def _create_module(self, module: dict, parent_id: Optional[str]) -> dict:
        payload: Dict[str, Any] = {
            "title": module["title"],
            "visibility": module.get("visibility") or "draft",
            "sequenceNo": module.get("position") or 1,
        }
        if parent_id:
            payload["parentCategory"] = parent_id
        out = _adapter_call(self.adapter, "create_category",
                            location_id=self.plan["location_id"], payload=payload)
        mid = out.get("id")
        if not mid:
            raise StopAndReport(f"category.create:{module['module_key']}",
                                "create_category returned no id")
        return {"id": str(mid), "payload": payload}

    def _create_lesson(self, module: dict, lesson: dict, category_id: str) -> dict:
        payload: Dict[str, Any] = {
            "title": lesson["title"],
            "categoryId": category_id,
            "visibility": lesson.get("visibility") or "draft",
            "sequenceNo": lesson.get("position") or 1,
        }
        if lesson.get("body"):
            payload["description"] = lesson["body"]
        out = _adapter_call(self.adapter, "create_lesson",
                            location_id=self.plan["location_id"], payload=payload)
        lid = out.get("id")
        if not lid:
            raise StopAndReport(f"lesson.create:{lesson['lesson_key']}",
                                "create_lesson returned no id")
        return {"id": str(lid), "payload": payload}

    def _sequence_and_readback(self, module_ids: Dict[str, str],
                               lesson_ids: Dict[str, str],
                               module_order: List[str]) -> dict:
        """Deterministic final sequencing, then READ BACK the actual order."""
        ordering = []
        for mkey in module_order:
            mid = module_ids.get(mkey)
            if mid:
                m = next(x for x in self.plan["modules"] if x["module_key"] == mkey)
                ordering.append({"object_type": "category", "id": mid,
                                 "sequenceNo": m.get("position") or 1})
                for l in m["lessons"]:
                    lid = lesson_ids.get(f"lesson:{mkey}/{l['lesson_key']}")
                    if lid:
                        ordering.append({"object_type": "lesson", "id": lid,
                                         "sequenceNo": l.get("position") or 1})
        applied = _adapter_optional(self.adapter, "sequence",
                                    location_id=self.plan["location_id"],
                                    course_id=self.course_id, ordering=ordering)
        readback = _adapter_optional(self.adapter, "list_lessons",
                                     location_id=self.plan["location_id"],
                                     course_id=self.course_id)
        order_ok = None
        if isinstance(readback, list):
            observed = [str(x.get("id")) for x in readback if isinstance(x, dict)]
            wanted = [o["id"] for o in ordering if o["object_type"] == "lesson"]
            if wanted:
                # Order is the OBSERVED order restricted to the objects we own —
                # a set-membership test would report a reversed list as a match.
                observed_owned = [i for i in observed if i in set(wanted)]
                order_ok = observed_owned == wanted
        return {
            "applied": bool(applied.get("ok")) if isinstance(applied, dict) else False,
            "readback_present": isinstance(readback, list),
            "order_matches": order_ok,
            "ordering": ordering,
        }

    def run(self) -> dict:
        if not _HAVE_DELIVERY:
            raise StopAndReport("plan", "ghl_course_delivery is unavailable — the API "
                                        "coordinator cannot validate or reduce a plan")
        errors = _delivery.validate_plan(self.plan)
        if errors:
            raise _delivery.CoursePlanError(errors)

        idmap = _delivery.identity_map(self.plan)
        module_order = _delivery.parent_order(self.plan)
        pref = api_preflight(self.plan, self.adapter)
        if not pref["pass"]:
            return {"ok": False, "mode": "api", "error": pref["stop_reason"],
                    "preflight": pref}

        shell = self._phase("api_course_shell", self._ensure_course_shell)

        # Modules in parent-before-child order, each checkpointed.
        module_ids: Dict[str, str] = {}
        for mkey in module_order:
            module = next(m for m in self.plan["modules"] if m["module_key"] == mkey)
            rec = idmap[f"module:{mkey}"]

            def _mk(_m=module, _r=rec) -> dict:
                prior = self.objects.get(f"module:{_r['module_key']}")
                if isinstance(prior, dict) and prior.get("object_id"):
                    # Reconcile by the RECORDED ID: a resumed run must never
                    # create a second category for the same logical key.
                    self.steps.append(f"module:reused:{_r['module_key']}")
                    return {"id": str(prior["object_id"]), "reused": True}
                parent_id = module_ids.get(_r["parent_module_key"]) if _r["parent_module_key"] else None
                if _r["parent_module_key"] and not parent_id:
                    raise StopAndReport(
                        f"category:{_r['module_key']}",
                        f"parent module {_r['parent_module_key']!r} has no resolved ID — "
                        "parent-before-child order was not honoured")
                out = self._create_module(_m, parent_id)
                self._remember(f"module:{_r['module_key']}", "course_module",
                               out["id"], "created", _m.get("visibility", ""))
                self._record("course_module", _r["module_key"], "created",
                             object_id=out["id"],
                             verify={"ok": True, "visibility": _m.get("visibility", "draft")},
                             request_shape=out["payload"])
                self.steps.append(f"module:{_r['module_key']}")
                return out

            out = self._phase(f"module:{mkey}", _mk)
            module_ids[mkey] = out["id"]

        # Lessons, each with its OWN checkpoint so one failure never rebuilds the rest.
        lesson_ids: Dict[str, str] = {}
        for mkey in module_order:
            module = next(m for m in self.plan["modules"] if m["module_key"] == mkey)
            for lesson in module["lessons"]:
                lkey = f"lesson:{mkey}/{lesson['lesson_key']}"

                def _mk_lesson(_m=module, _l=lesson, _k=lkey, _cat=module_ids[mkey]) -> dict:
                    prior = self.objects.get(_k)
                    if isinstance(prior, dict) and prior.get("object_id"):
                        self.steps.append(f"{_k}:reused")
                        return {"id": str(prior["object_id"]), "reused": True}
                    out = self._create_lesson(_m, _l, _cat)
                    self._remember(_k, "course_lesson", out["id"], "created",
                                   _l.get("visibility", ""))
                    self._record("course_lesson", _k.replace("/", "_"), "created",
                                 object_id=out["id"],
                                 verify={"ok": True, "logical_key": _k,
                                         "category_id": _cat,
                                         "visibility": _l.get("visibility", "draft")},
                                 request_shape=out["payload"])
                    self.steps.append(_k)
                    return out

                out = self._phase(lkey, _mk_lesson)
                lesson_ids[lkey] = out["id"]

        # Native-content handoff (WF08 seam) — only when the plan asks for media.
        needs_media = any(
            lesson.get("asset_refs") or lesson.get("media_url")
            or lesson.get("assessment_ref")
            for m in self.plan["modules"] for lesson in m["lessons"]
        )
        content_proof: dict = {"required": bool(needs_media)}
        if needs_media:
            if self.media_binder is None:
                self.warnings.append(
                    "plan requests media/assessments but no WF08 media binder was "
                    "supplied — delivery will report the content as unbound")
            else:
                try:
                    proof = self.media_binder(plan=self.plan, identity=idmap,
                                              course_id=self.course_id,
                                              lesson_ids=dict(lesson_ids),
                                              evidence_root=self.evidence_root)
                    if isinstance(proof, dict):
                        content_proof.update(proof)
                except Exception as exc:  # noqa: BLE001 — surfaced, never faked
                    self.warnings.append(f"media binder raised: {type(exc).__name__}: {exc}")
            content_proof.setdefault("required", True)

        sequencing = self._phase(
            "api_sequencing",
            lambda: self._sequence_and_readback(module_ids, lesson_ids, module_order))

        # Community association ONLY when requested (a standalone course is legal).
        community_art = None
        community_spec = self.plan.get("community") or {}
        if community_spec.get("required"):
            if self.association is None:
                self.warnings.append(
                    "plan requires a Community association but no WF09 association "
                    "seam was supplied — delivery will report it pending")
                community_art = {"state": "not_requested_by_runtime"}
            else:
                try:
                    community_art = self.association(
                        plan=self.plan, course_id=self.course_id,
                        evidence_root=self.evidence_root)
                except Exception as exc:  # noqa: BLE001
                    community_art = {"state": "failed",
                                     "error": f"{type(exc).__name__}: {exc}"}

        artifacts: Dict[str, dict] = {"course": {
            "state": "verified", "verified": True, "object_id": self.course_id}}
        for key, rec in self.objects.items():
            if key == "course":
                continue
            artifacts[key] = {"state": "verified", "verified": True,
                              "object_id": rec.get("object_id"),
                              "visibility": rec.get("visibility")}
        delivery = _delivery.reduce_delivery(
            self.plan, artifacts,
            community_artifact=community_art,
            content_proof=content_proof if needs_media else None,
        )
        receipt_path = _delivery.write_delivery_receipt(self.evidence_root, delivery)

        summary = _router.reduce_receipts(self.evidence_root) if _HAVE_ROUTER else {}
        ok = delivery["state"] == _delivery.DELIVERY_DELIVERED
        return {
            "ok": ok,
            "mode": "api",
            "browser_started": False,
            "course_id": self.course_id,
            "steps_done": self.steps,
            "warnings": self.warnings,
            "sequencing": sequencing,
            "delivery": delivery,
            "delivery_receipt_path": receipt_path,
            "receipts_summary": summary,
            "dry_run": False,
        }


def build_course_api(task: dict, evidence_root: str, *, adapter: Any,
                     media_binder: Any = None, association: Any = None,
                     state: Optional["ghl_run_state.RunState"] = None,
                     resume: bool = False, plan: Optional[dict] = None) -> dict:
    """Run the API-first coordinator. ``build_course`` selects it by mode."""
    del resume  # resumability comes from the phase ledger + identity manifest
    started = time.monotonic()
    os.makedirs(os.path.join(evidence_root, "routing"), exist_ok=True)
    if plan is None:
        plan = run_phase(state, "plan", lambda: plan_course(task), log=_log)
    _write_json(os.path.join(evidence_root, "routing", "course-plan.json"), plan)
    coord = CourseCoordinator(plan, evidence_root, adapter=adapter,
                              media_binder=media_binder, association=association,
                              state=state)
    try:
        result = coord.run()
    except StopAndReport as sr:
        _log(f"STOP-and-report @ {sr.step}: {sr.reason}")
        return {"ok": False, "mode": "api", "error": str(sr),
                "stop_step": sr.step, "stop_reason": sr.reason,
                "steps_done": coord.steps, "warnings": coord.warnings,
                "duration_s": time.monotonic() - started, "dry_run": False}
    result["duration_s"] = time.monotonic() - started
    return result


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def build_course(task: dict, evidence_root: str, *, dry_run: bool = True,
                 resume: bool = False,
                 state: Optional["ghl_run_state.RunState"] = None,
                 adapter: Any = None,
                 media_binder: Any = None,
                 association: Any = None,
                 execution_mode: str = "") -> dict:
    """Build a course.

    ``execution_mode`` selects the rail EXPLICITLY:
      * ``"api"``            — API-first coordinator (requires ``adapter``);
      * ``"browser"``        — the legacy managed-browser walk (fallback);
      * ``""`` (default)     — ``"api"`` when an adapter is supplied, otherwise
                               ``"browser"`` so every existing caller keeps its
                               exact behaviour.

    An API outline build never starts a browser. The managed-browser path is
    preserved as an explicit, selectable fallback (doc 1 s8.1).
    """
    started = time.monotonic()
    dry_run = bool(task.get("dry_run", dry_run))
    mode = (execution_mode or task.get("execution_mode")
            or ("api" if adapter is not None else "browser")).strip().lower()
    if mode not in ("api", "browser"):
        raise ValueError(f"execution_mode {mode!r} is not one of ('api', 'browser')")
    # A run-id resume implies the lesson-level skip too: re-walking a lesson that
    # already has a receipt would just duplicate it.
    resume = bool(resume or task.get("resume") or (state is not None and state.doc.get("attempts", 1) > 1))
    os.makedirs(os.path.join(evidence_root, "routing"), exist_ok=True)
    os.makedirs(os.path.join(evidence_root, "shots"), exist_ok=True)

    plan = run_phase(state, "plan", lambda: plan_course(task), log=_log)
    preflight = run_phase(state, "preflight", lambda: _preflight(plan), log=_log)
    click_list = run_phase(state, "click_list", lambda: emit_click_list(plan), log=_log)
    api_gate = api_preflight(plan, adapter, required=(mode == "api"))
    _write_json(os.path.join(evidence_root, "routing", "course-plan.json"), plan)
    _write_json(os.path.join(evidence_root, "routing", "course-click-list.json"), click_list)
    _write_json(os.path.join(evidence_root, "routing", "course-preflight.json"), preflight)
    _write_json(os.path.join(evidence_root, "routing", "course-api-preflight.json"), api_gate)

    if not preflight["pass"]:
        return {"ok": False, "object_type": "course", "duration_s": time.monotonic() - started,
                "preflight": preflight, "error": preflight["stop_reason"], "dry_run": dry_run,
                "execution_mode": mode}

    if dry_run:
        disclosure = (_router.tier_disclosure(_router.route("course").rails[0])
                      if _HAVE_ROUTER else "[GHL tier used: 4 — ghl_course_builder.py]")
        _log(f"[dry-run] course plan + click list ({click_list['total_steps']} steps, "
             f"{plan['lesson_count']} lessons) written. {disclosure}")
        return {"ok": True, "object_type": "course", "duration_s": time.monotonic() - started,
                "plan": plan, "click_list": click_list, "preflight": preflight,
                "api_preflight": api_gate, "tier_disclosure": disclosure,
                "execution_mode": mode, "browser_required": bool(mode == "browser"),
                "dry_run": True}

    if mode == "api":
        if not api_gate["pass"]:
            return {"ok": False, "object_type": "course", "mode": "api",
                    "duration_s": time.monotonic() - started,
                    "error": api_gate["stop_reason"], "api_preflight": api_gate,
                    "plan": plan, "dry_run": False}
        return build_course_api(task, evidence_root, adapter=adapter,
                                media_binder=media_binder, association=association,
                                state=state, resume=resume, plan=plan)

    return run_phase(state, "m_walk", lambda: _live_build(
        task, plan, click_list, preflight, evidence_root, started, resume), log=_log)


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
                    {"title": "Intro", "body": "dup"},          # SAME TITLE, distinct key
                    {"title": "Setup", "media_url": "https://storage.leadconnectorhq.com/x.mp4"}]},
                {"title": "Welcome", "lessons": []},            # SAME TITLE, distinct module key
                {"title": "Build", "lessons": [{"title": "First page"}]}]}
    plan = plan_course(task)
    if plan["course_name"] != "ZHC Launch 101":
        errors.append(f"zhc name wrong: {plan['course_name']!r}")
    # A09: duplicate DISPLAY titles are legal; identity is the logical key.
    if [m["title"] for m in plan["modules"]] != ["Welcome", "Welcome", "Build"]:
        errors.append(f"same-title modules were dropped: {[m['title'] for m in plan['modules']]}")
    mkeys = [m["module_key"] for m in plan["modules"]]
    if len(mkeys) != len(set(mkeys)):
        errors.append(f"module logical keys are not unique: {mkeys}")
    if len(plan["modules"][0]["lessons"]) != 3:
        errors.append("same-title lessons were deduped away (A09 forbids it)")
    lkeys = [l["lesson_key"] for l in plan["modules"][0]["lessons"]]
    if lkeys != ["intro", "intro-2", "setup"]:
        errors.append(f"lesson logical keys are not stable/distinct: {lkeys}")
    if plan["lesson_count"] != 4:
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

    # plan validation fails BEFORE any write (empty outline is not a course)
    empty_rejected = False
    try:
        _preflight(plan_course({"course_name": "Empty", "location_id": "L", "modules": []}))
    except ValueError as exc:      # CoursePlanError subclasses ValueError
        empty_rejected = "modules" in str(exc)
    if not empty_rejected:
        errors.append("plan with no modules must be rejected at plan time")

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
        anchor(sels, "course.outline.lesson_body_editor")
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
            return "CLICKED:x" if ".click()" in js else "OK"

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
    # BACKWARDS-COMPATIBLE --resume (U8). Bare `--resume` keeps its original
    # meaning — "skip lessons already receipted in --evidence-root" — so every
    # existing invocation behaves exactly as before. `--resume <run_id>` is the new
    # uniform form: it reopens that run's PHASE ledger (and still skips the
    # already-receipted lessons inside M4).
    p.add_argument("--resume", nargs="?", const=_RESUME_LESSONS_ONLY, default="",
                   metavar="RUN_ID",
                   help="Bare: skip lessons already receipted (legacy behaviour). "
                        "With a RUN_ID: resume that run's phase ledger as well.")
    p.add_argument("--run-id", metavar="RUN_ID", default="",
                   help="Force this run's id (default: generated).")
    p.add_argument("--state-root", metavar="DIR", default=ghl_run_state.default_state_root(),
                   help="Where per-run phase state is stored "
                        f"(default: {ghl_run_state.default_state_root()}).")
    p.add_argument("--stop-after-phase", metavar="PHASE", default="",
                   help="Stop cleanly AFTER this phase completes; resume with --resume.")
    p.add_argument("--evidence-root", default="/tmp/course-run-01")
    p.add_argument("--course-name", default="New Course")
    p.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID", ""))
    p.add_argument("--execution-mode", choices=("", "api", "browser"), default="",
                   help="Rail selection: 'api' = API-first coordinator (needs the "
                        "shared public adapter), 'browser' = the managed-browser "
                        "fallback, '' = api when an adapter is supplied else browser.")
    p.add_argument("--plan-json", default="", help="Path to a JSON with modules[] (THINK input)")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()

    # Split the two meanings of --resume apart before anything else looks at it.
    lessons_only = (args.resume == _RESUME_LESSONS_ONLY)
    run_id_to_resume = "" if lessons_only else (args.resume or "")
    args.resume = run_id_to_resume     # what ghl_run_state.cli_run reads

    task: Dict[str, Any] = {"course_name": args.course_name, "location_id": args.location_id}
    if args.execution_mode:
        task["execution_mode"] = args.execution_mode
    if args.plan_json and os.path.isfile(args.plan_json):
        with open(args.plan_json, encoding="utf-8") as fh:
            task.update(json.load(fh))
    if lessons_only:
        task["resume"] = True

    return ghl_run_state.cli_run(
        args, builder="ghl_course_builder", specs=COURSE_PHASES,
        script_path=__file__, task=task, build=build_course,
        ok_key="ok", url_key="preview_url",
        argv=list(argv if argv is not None else sys.argv[1:]),
    )


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""ghl_meeting_rooms.py — Skill 06 managed-browser operator for GoHighLevel /
Convert and Flow MEETING ROOMS (Document 1 §23, workflow WF26).

WHY THIS IS BROWSER-ONLY. No public Meeting Room lifecycle contract was confirmed
in the revision-3 research (§23.1). A Calendar API field for a meeting location, a
physical calendar resource, or a generic room URL is NOT proof of a video-room
create API. So the create/configure surface is driven through Skill 6's existing
managed-browser system, and this module ADOPTS a documented public operation only
after its exact contract is added to the shared registry by the registry owner.
This module never invents an HTTP route for an internal operation.

SPLIT (same shape as ghl_form_builder / ghl_community_builder / ghl_course_builder):

  • THINK layer (network-free): resolves the ROOM PLAN from the approved brief and
    emits, with no browser, under <evidence_root>/routing/:
        meeting-room-plan.json · meeting-room-click-list.json ·
        meeting-room-preflight.json · meeting-room-subresults.json
  • DUMB layer (agent-browser 0.27.0 through the browser_manager singleton and the
    SHARED ghl_ab_executor adapter): bind identity → probe the feature → inventory
    and reuse → observed setup flow → apply only supported controls → save and
    re-open → integration branch → isolated guest check → authorized rehearsal →
    link delivery.

HARD RULES THIS MODULE ENFORCES
  * D8 — ZERO INVENTED SELECTORS. Every in-area anchor comes from the DEDICATED
    map `selectors-live-meeting-rooms.json`. Every target there is
    `capture-pending` until a real capture run flips it, so a live run STOPs and
    reports instead of guessing CSS. Nothing here reuses a Community/Course
    selector for a meeting surface.
  * PASSCODE IS A SECRET REFERENCE ONLY. The plan carries
    `passcode_secret_reference`; the value is resolved at run time by an injected
    resolver, used in the browser, and never written to any artifact, receipt or
    log. `assert_no_secret_leak` proves it against the artifacts on disk.
  * HOST IDENTITY IS EXPLICIT. `host_user_id` is required. There is no default to
    the operator's own identity, so one person's room is never silently reused as
    every coach's room.
  * EXISTING ROOMS ARE NEVER IMPLICITLY TOUCHED. Cleanup removes only a scratch
    room this run CREATED, and only with an explicit authorization reference.
  * NO IMPLICIT ZOOM MIGRATION. Replacing an existing meeting location requires a
    `migration_authorization` reference; otherwise the plan records the gap and
    leaves the existing link alone.
  * LIVE AV IS NEVER CLAIMED FROM HEADLESS SETUP. Setup, host identity, guest flow
    and calendar behaviour are separate sub-results; audio/video, screen sharing,
    recording, transcript, summary and follow-up are separate sub-results too. A
    headless environment returns SETUP_VERIFIED with live AV PENDING.

Usage:
    plan = plan_room({"location_id": "SYNTHETIC_LOCATION", "host_user_id": "u1",
                      "purpose": "office hours", "room_link_mode": "reusable"})
    result = build_meeting_room(task, "<evidence-root>")                    # dry run
    result = build_meeting_room(task, "<evidence-root>", dry_run=False, deps=deps)
    python3 ghl_meeting_rooms.py --dry-run --location-id LOC --host-user-id u1 \
        --purpose "office hours" --room-link-mode reusable
    python3 ghl_meeting_rooms.py --selftest
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

import ghl_run_state  # noqa: E402
from ghl_run_state import PhaseSpec, run_phase  # noqa: E402

# ── shared live glue: the form builder owns the seed/land/nav primitives, the
# community builder owns the selector gate + executor wrappers + receipts. Both are
# IMPORTED, never re-implemented (spec F7/F11: new builders route through the
# shared layer, and §21.6 forbids a competing browser priority list here).
try:
    import ghl_form_builder as _ffb  # type: ignore
    _ab = _ffb._ab
    _eval = _ffb._eval
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
    _HAVE_FFB = True
except Exception:  # noqa: BLE001 — bare checkout: the THINK layer still works
    _HAVE_FFB = False
    from ghl_community_builder import (  # type: ignore
        StopAndReport, _ts, _log, _write_json, _slug,
    )

import ghl_community_builder as _cb  # noqa: E402  (selector gate + executor + receipts)

try:
    import ghl_object_router as _router  # type: ignore
    _HAVE_ROUTER = True
except Exception:  # noqa: BLE001
    _router = None  # type: ignore
    _HAVE_ROUTER = False


# ---------------------------------------------------------------------------
# Phase walk (the same resume ledger every Skill-6 builder takes)
# ---------------------------------------------------------------------------
ROOM_PHASES: List[PhaseSpec] = [
    PhaseSpec("plan",        "meeting-room plan (THINK)",       resumable=False),
    PhaseSpec("preflight",   "preflight gate",                  resumable=False),
    PhaseSpec("click_list",  "click list",                      resumable=False),
    PhaseSpec("bind",        "bind subaccount + host identity",  resumable=False),
    PhaseSpec("probe",       "probe the feature",               resumable=False),
    PhaseSpec("inventory",   "inventory + reuse decision"),
    PhaseSpec("setup",       "create/configure the room"),
    PhaseSpec("save_reopen", "save and re-open"),
    PhaseSpec("integration", "calendar / course / event integration"),
    PhaseSpec("guest_check", "isolated guest check"),
    PhaseSpec("rehearsal",   "authorized rehearsal"),
    PhaseSpec("delivery",    "link + instruction delivery"),
]

#: Internal room-link modes. INTERNAL labels, not a vendor enum — translated only
#: through observed UI controls or a verified API field.
ROOM_LINK_MODES = ("reusable", "appointment_unique", "existing_room")

#: The honest sub-results of §23.9. Each is answered independently; none may be
#: inferred from another (recording ON is not transcript ON, and so on).
SUB_RESULT_KEYS = (
    "configuration_saved_and_reopened",
    "host_identity_verified",
    "guest_join_flow_verified",
    "calendar_link_generation_verified",
    "reschedule_and_cancellation_verified",
    "live_audio_video_verified",
    "screen_sharing_verified",
    "recording_verified",
    "transcript_verified",
    "summary_verified",
    "follow_up_task_creation_verified",
    # §23.8 advanced branch. A created/assigned breakout room is NOT proof that
    # participants moved, so this is its own independent sub-result.
    "breakout_opened_verified",
)

#: Optional advanced branches. Absent from a brief means NOT REQUESTED, which is a
#: valid final state — never a failure and never a silent "passed".
OPTIONAL_SUB_RESULTS = (
    "screen_sharing_verified",
    "recording_verified",
    "transcript_verified",
    "summary_verified",
    "follow_up_task_creation_verified",
    "breakout_opened_verified",
)

STATE_NOT_REQUESTED = "not_requested"
STATE_NOT_RUN = "not_run"
STATE_PENDING = "pending"
STATE_VERIFIED = "verified"
STATE_FAILED = "failed"

STATUS_PLANNED = "PLANNED"
STATUS_SETUP_VERIFIED = "SETUP_VERIFIED"
STATUS_VERIFIED = "VERIFIED"
STATUS_BLOCKED = "BLOCKED"
LIVE_AV_PENDING = "LIVE_AV_PENDING"
LIVE_AV_VERIFIED = "LIVE_AV_VERIFIED"

SELECTORS_FILE = os.path.join(_TOOLS_DIR, "selectors-live-meeting-rooms.json")
_ACTIONABLE_STATUS = {"verified-shared-rail", "locked"}

#: Centralized browser policy: this operator names NO priority list of its own. It
#: uses the shared browser_manager session + the shared executor adapter, exactly as
#: Document 1 §21.6 requires.
BROWSER_POLICY = "shared_browser_manager+shared_ghl_ab_executor"


# ---------------------------------------------------------------------------
# Selector map + the D8 gate (same semantics as the community/course builders)
# ---------------------------------------------------------------------------
def load_selectors(path: Optional[str] = None) -> dict:
    with open(path or SELECTORS_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def _target(selectors: dict, dotted: str) -> dict:
    node: Any = selectors
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"selector path {dotted!r} not present in the meeting-room map")
        node = node[part]
    return node


def anchor(selectors: dict, dotted: str, *, required: bool = True) -> str:
    """Return the actionable anchor for a dotted path, or STOP-and-report when the
    target is still `capture-pending`. This is the D8 gate: an uncaptured REQUIRED
    surface never becomes a guessed click."""
    t = _target(selectors, dotted)
    status = t.get("status")
    if status in _ACTIONABLE_STATUS:
        return t.get("anchor", "")
    msg = (f"selector {dotted!r} is status={status!r} — it has NOT been captured live for "
           f"Meeting Rooms. D8 forbids inventing a selector. Run the live capture "
           f"(references/meeting-room-operations.md §capture procedure: create a scratch "
           f"room owned by the authorized test host, walk it, record the real anchor + "
           f"confidence, read it back after Save, then remove the scratch room under an "
           f"explicit cleanup authorization) to flip it to 'locked'. Fallback chain "
           f"(a CAPTURE RECIPE, not a fact): {t.get('fallbacks')}")
    if required:
        raise StopAndReport(f"selector:{dotted}", msg)
    _log(f"optional selector {dotted!r} capture-pending — skipped: {msg}")
    return ""


def selector_status_report(selectors: Optional[dict] = None) -> dict:
    """Machine-readable inventory of what is captured vs pending. Used by the probe
    phase and by the reference doc so code and prose cannot drift."""
    sels = selectors if selectors is not None else load_selectors()
    out: Dict[str, Any] = {"locked": [], "capture-pending": [], "other": []}
    root = sels.get("meeting_room") or {}

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if "status" in node and "anchor" in node:
                st = node.get("status")
                if st in _ACTIONABLE_STATUS:
                    out["locked"].append(path)
                elif st == "capture-pending":
                    out["capture-pending"].append(path)
                else:
                    out["other"].append(path)
                return
            for k, v in node.items():
                if str(k).startswith("_"):
                    continue
                walk(v, f"{path}.{k}" if path else k)

    walk(root, "meeting_room")
    out["locked_count"] = len(out["locked"])
    out["capture_pending_count"] = len(out["capture-pending"])
    out["capture_complete"] = out["capture_pending_count"] == 0
    return out


# ---------------------------------------------------------------------------
# Executor wrappers. The shared executor stays ghl_ab_executor (owned by the
# community builder glue); these thin wrappers only put THIS surface's D8 gate in
# front of it so a capture-pending Meeting Room target stops with the Meeting
# Room capture procedure in the message, never the Community one.
# ---------------------------------------------------------------------------
def ex_click(session: str, sels: dict, dotted: str, *, required: bool = True,
             timeout: int = 15) -> dict:
    a = anchor(sels, dotted, required=required)  # meeting-room gate + message
    if not a:
        return {"ok": False, "path": "skipped", "reason": "optional capture-pending"}
    return _cb._ex_click(session, sels, dotted, required=False, timeout=timeout)


def ex_fill(session: str, sels: dict, dotted: str, value: str, *, required: bool = True,
            timeout: int = 15) -> dict:
    a = anchor(sels, dotted, required=required)  # meeting-room gate + message
    if not a:
        return {"ok": False, "path": "skipped", "reason": "optional capture-pending"}
    return _cb._ex_fill(session, sels, dotted, value, required=False, timeout=timeout)


# ---------------------------------------------------------------------------
# THINK layer — the room plan (§23.3)
# ---------------------------------------------------------------------------
def _norm_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [p.strip() for p in raw.split(",")]
    out: List[str] = []
    seen: set = set()
    for item in raw:
        val = str(item).strip()
        if not val or val.lower() in seen:
            continue
        seen.add(val.lower())
        out.append(val)
    return out


def _policy(task: dict, key: str, default: str = "inherit_client_policy") -> str:
    val = task.get(key, default)
    return str(val or default).strip()


def plan_room(task: dict) -> dict:
    """Resolve the room plan from the approved brief. Network-free and browser-free.

    Raises StopAndReport on a decision-critical gap so a missing host identity or an
    unknown link mode can never silently become a room owned by the wrong person.
    """
    location_id = str(task.get("location_id") or "").strip()
    host_user_id = str(task.get("host_user_id") or "").strip()
    if not location_id:
        raise StopAndReport("plan.location_id", "location_id is required — the subaccount "
                                               "gate runs before ANY write")
    if not host_user_id:
        raise StopAndReport(
            "plan.host_user_id",
            "host_user_id is required and is NEVER defaulted to the operator identity: a "
            "room must belong to the actual authorized host (a coach's room is not the "
            "operator's room). Pass the staff user id that will own the room.")

    mode = str(task.get("room_link_mode") or "reusable").strip().lower()
    if mode not in ROOM_LINK_MODES:
        raise StopAndReport(
            "plan.room_link_mode",
            f"room_link_mode {mode!r} is not one of {ROOM_LINK_MODES}. These are internal "
            "labels; translate them only through observed UI controls or a verified API field.")

    existing_ref = str(task.get("existing_room_reference") or "").strip()
    if mode == "existing_room" and not existing_ref:
        raise StopAndReport(
            "plan.existing_room_reference",
            "room_link_mode='existing_room' needs existing_room_reference (the approved room "
            "name or id observed in the inventory).")

    secret_ref = str(task.get("passcode_secret_reference") or "").strip()
    if task.get("passcode"):
        # A raw passcode in the task is refused outright: accepting it would put the
        # value in the plan, the evidence and every log that dumps the task.
        raise StopAndReport(
            "plan.passcode",
            "passcode must be supplied as passcode_secret_reference (a resolver reference), "
            "never as a literal value. A literal would land in the plan and in evidence.")

    plan: Dict[str, Any] = {
        "object_type": "meeting_room",
        "plan_version": "meeting-room-plan/1",
        "location_id": location_id,
        "host_user_id": host_user_id,
        "purpose": str(task.get("purpose") or "").strip(),
        "room_link_mode": mode,
        "existing_room_reference": existing_ref,
        "calendar_id": str(task.get("calendar_id") or "").strip(),
        "course_id": str(task.get("course_id") or "").strip(),
        "event_id": str(task.get("event_id") or "").strip(),
        "cohost_user_ids": _norm_list(task.get("cohost_user_ids")),
        "participant_audience": str(task.get("participant_audience") or "invited").strip().lower(),
        "allow_guests": bool(task.get("allow_guests", False)),
        "waiting_room_policy": _policy(task, "waiting_room_policy", "controlled_admission"),
        "passcode_secret_reference": secret_ref,
        "schedule_timezone": str(task.get("schedule_timezone") or "America/New_York").strip(),
        "duration_minutes": int(task.get("duration_minutes") or 30),
        "notice_minutes": int(task.get("notice_minutes") or 0),
        "buffer_before_minutes": int(task.get("buffer_before_minutes") or 0),
        "buffer_after_minutes": int(task.get("buffer_after_minutes") or 0),
        "recurrence": task.get("recurrence") or None,
        "recording_policy": _policy(task, "recording_policy", "off_unless_approved"),
        "transcription_policy": _policy(task, "transcription_policy", "off_unless_approved"),
        "transcription_language": str(task.get("transcription_language") or "").strip(),
        "summary_policy": _policy(task, "summary_policy", "not_requested"),
        "review_owner": str(task.get("review_owner") or "").strip(),
        "retention_and_sharing_policy": _policy(task, "retention_and_sharing_policy",
                                                "client_default"),
        "notification_policy": _policy(task, "notification_policy", "client_default"),
        "approval_references": _norm_list(task.get("approval_references")),
        "migration_authorization": str(task.get("migration_authorization") or "").strip(),
        "cleanup_authorization": str(task.get("cleanup_authorization") or "").strip(),
        "requested_outputs": _norm_list(task.get("requested_outputs")),
        "breakout_requested": bool(task.get("breakout_requested", False)),
        "created_at": _ts(),
    }
    plan["slug"] = _slug(f"{host_user_id}-{plan['purpose'] or mode}")
    plan["sub_results"] = initial_sub_results(plan)
    return plan


def initial_sub_results(plan: dict) -> Dict[str, str]:
    """Every sub-result starts NOT RUN. Requested-but-untested is never 'passed'."""
    requested = set(plan.get("requested_outputs") or [])
    out = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    for key in OPTIONAL_SUB_RESULTS:
        if key == "breakout_opened_verified":
            continue  # gated by breakout_requested, not by requested_outputs
        if key not in requested:
            out[key] = STATE_NOT_REQUESTED
    out["breakout_opened_verified"] = (STATE_NOT_RUN if plan.get("breakout_requested")
                                       else STATE_NOT_REQUESTED)
    return out


def preflight(plan: dict) -> dict:
    """Hard gates that must pass before ANY live write."""
    checks: List[dict] = []

    def chk(name: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        checks.append({"check": name, "pass": bool(ok), "hard": hard, "detail": detail})

    chk("R-P1:location_id", bool(plan.get("location_id")),
        "location_id required (subaccount gate before any write)")
    chk("R-P2:host_user_id", bool(plan.get("host_user_id")),
        "host_user_id required; never defaulted to the operator identity")
    chk("R-P3:link_mode", plan.get("room_link_mode") in ROOM_LINK_MODES,
        f"room_link_mode must be one of {ROOM_LINK_MODES}")
    chk("R-P4:no_literal_passcode",
        "passcode" not in plan and "passcode_value" not in plan,
        "a literal passcode must never be present in the plan")
    chk("R-P5:existing_room_ref",
        plan.get("room_link_mode") != "existing_room"
        or bool(plan.get("existing_room_reference")),
        "existing_room mode requires existing_room_reference")
    chk("R-P6:recording_policy",
        plan.get("recording_policy") not in ("on", "always"),
        "recording defaults OFF unless an approved policy explicitly says otherwise",
        hard=False)
    chk("R-P7:transcription_needs_approval",
        not (plan.get("transcription_policy") in ("on", "always")
             and not plan.get("approval_references")),
        "enabling transcription needs an approval reference", hard=True)
    hard_fail = [c for c in checks if c["hard"] and not c["pass"]]
    return {"pass": not hard_fail, "checks": checks,
            "stop_reason": (hard_fail[0]["detail"] if hard_fail else "")}


def emit_click_list(plan: dict) -> dict:
    """The ordered walk. Steps name the SELECTOR PATHS, never raw CSS."""
    steps: List[dict] = []

    def add(phase: str, action: str, target: str, note: str = "") -> None:
        steps.append({"n": len(steps) + 1, "phase": phase, "action": action,
                      "target": target, "note": note})

    add("B0", "bind", f"location={plan['location_id']}",
        "confirm the subaccount and that the signed-in identity may configure the "
        "intended host's room — never assume the operator owns it")
    add("B0", "bind", f"host_user_id={plan['host_user_id']}",
        "the room must belong to the authorized host; no default to the operator")
    add("P1", "probe", "meeting_room.nav.meeting_room_rail_item",
        "distinguish missing entitlement vs missing user permission vs incomplete rollout "
        "vs selector drift before any write")
    add("P1", "probe", "selector-status",
        "report every capture-pending target; a REQUIRED pending target STOPs here")
    add("I1", "inventory", "meeting_room.inventory.room_list_container",
        "enumerate rooms so an approved existing room is REUSED, never duplicated per run")
    if plan["room_link_mode"] == "existing_room":
        add("I1", "reuse", plan["existing_room_reference"],
            "existing_room mode: reuse the approved room; no create step")
    else:
        add("S1", "click", "meeting_room.nav.my_room_card",
            "documented entry: Meeting Room > My room")
        add("S1", "click", "meeting_room.my_room.create_room_button",
            "Create room (only after the inventory proved no approved room to reuse)")
        add("S2", "fill", "meeting_room.my_room.room_name_input", plan["purpose"] or "Room")
        if plan.get("waiting_room_policy") == "controlled_admission":
            add("S2", "set", "meeting_room.security.waiting_room_toggle",
                "controlled admission for private consultations and paid groups")
        if plan.get("passcode_secret_reference"):
            add("S2", "set", "meeting_room.security.passcode_toggle",
                "passcode VALUE resolved at run time from "
                f"{plan['passcode_secret_reference']} — never written to any artifact")
        if plan.get("allow_guests"):
            add("S2", "set", "meeting_room.security.guest_access_toggle",
                "guest access only because the brief asks for an outside audience")
        for uid in plan.get("cohost_user_ids", []):
            add("S2", "add_cohost", uid,
                "co-host must be an identified, authorized user (never a shared login)")
        add("S3", "save", "meeting_room.my_room.room_save_button",
            "native submit — a toast alone is NOT proof of persistence")
        add("S4", "reopen", "meeting_room.my_room.reopen_entry",
            "save-and-reopen: read name/owner/link/security/co-hosts back from the UI")
    if plan.get("calendar_id") or plan.get("event_id") or plan.get("course_id"):
        add("X1", "integrate", "meeting_room.calendar.meeting_location_select",
            "Skill 44 owns the supported Calendar/Appointment API; use the managed UI only "
            "where no verified API field exists")
        add("X1", "integrate", "meeting_room.calendar.native_room_option",
            "native Meeting Room option — do NOT assume a field exists")
        if plan.get("migration_authorization"):
            add("X1", "migrate", plan["migration_authorization"],
                "replacing an existing meeting location needs this authorization reference")
        else:
            add("X1", "preserve", "existing meeting location",
                "no implicit Zoom migration: leave an existing link alone and record the gap")
        if plan["room_link_mode"] == "appointment_unique":
            add("X2", "appointment", "first authorized test appointment",
                "read the ACTUAL event/notification join link — never fabricate it")
            add("X2", "appointment", "second authorized test appointment",
                "verify link uniqueness where appointment_unique is the chosen mode")
            add("X2", "reschedule", "first test appointment",
                "verify the platform's real reschedule behaviour; do not presume link "
                "invalidation or regeneration")
            add("X2", "cancel", "second test appointment",
                "verify cancellation behaviour; check for stale or duplicate Zoom links")
    add("G1", "guest_check", "isolated guest context",
        "join flow in a SEPARATE context — never the authenticated host session")
    add("V1", "rehearsal", "approved host + approved guest/test identity",
        "record exactly which capabilities were exercised; headless has no usable devices")
    add("D1", "delivery", "guest join link + host/admin controls + booking link",
        "distinguish the three; never hand out host controls as the guest link")
    if plan.get("cleanup_authorization"):
        add("C1", "cleanup", "meeting_room.cleanup.delete_room_control",
            "ONLY a scratch room this run created, ONLY under this explicit authorization")
    else:
        add("C1", "cleanup", "skipped",
            "no cleanup_authorization — existing rooms are never deleted, disabled or "
            "migrated as implicit cleanup")
    return {"object_type": "meeting_room", "total_steps": len(steps), "steps": steps,
            "selector_source": os.path.basename(SELECTORS_FILE),
            "browser_policy": BROWSER_POLICY,
            "notes": ["DUMB-BROWSER SCRIPT — every in-area target resolves through the "
                      "DEDICATED meeting-room selector map; a capture-pending REQUIRED "
                      "target STOPs-and-reports (D8, no invented CSS).",
                      "Passcode is a secret REFERENCE; the value never reaches evidence."]}


# ---------------------------------------------------------------------------
# Reuse decision (§23.4 step 3) — inventory, never create-on-every-run
# ---------------------------------------------------------------------------
def reuse_decision(plan: dict, inventory: List[dict]) -> dict:
    """Decide reuse vs create from an OBSERVED inventory. Pure function: no browser.

    `inventory` rows are {"name", "owner_user_id", "join_url"} read from the UI.
    A row owned by a different user is NOT a reuse candidate — a shared room must
    not silently become another host's room.
    """
    want_ref = plan.get("existing_room_reference") or ""
    purpose = (plan.get("purpose") or "").strip().lower()
    host = plan.get("host_user_id") or ""
    rows = [r for r in (inventory or []) if isinstance(r, dict)]
    owned = [r for r in rows if str(r.get("owner_user_id") or "") == host]
    if plan.get("room_link_mode") == "existing_room":
        for r in owned:
            if want_ref and str(r.get("name") or "") == want_ref:
                return {"action": "reuse", "room": r,
                        "reason": "existing_room mode and the approved reference is present"}
        return {"action": "blocked", "room": None,
                "reason": (f"existing_room mode requested {want_ref!r} but no room of that "
                           f"name is owned by host {host!r} in the observed inventory")}
    if purpose:
        for r in owned:
            if str(r.get("name") or "").strip().lower() == purpose:
                return {"action": "reuse", "room": r,
                        "reason": "an approved room of this purpose already exists for this host"}
    others = [r for r in rows if str(r.get("owner_user_id") or "") != host]
    note = ""
    if others:
        note = (f"{len(others)} room(s) in the inventory belong to other users and are NOT "
                "reuse candidates")
    return {"action": "create", "room": None,
            "reason": "no owned room matches the brief", "note": note}


# ---------------------------------------------------------------------------
# Honest result assembly (§23.9)
# ---------------------------------------------------------------------------
def finalize_result(plan: dict, sub_results: Dict[str, str], *,
                    stopped: Optional[str] = None,
                    warnings: Optional[List[str]] = None) -> dict:
    """Turn sub-results into the honest top-line status. Never promotes an untested
    sub-result to 'passed', and never lets a headless run claim live AV."""
    sr = dict(sub_results)
    warnings = list(warnings or [])
    setup_keys = ("configuration_saved_and_reopened", "host_identity_verified")
    live_keys = ("live_audio_video_verified", "screen_sharing_verified")

    setup_ok = all(sr.get(k) == STATE_VERIFIED for k in setup_keys)
    live_verified = all(sr.get(k) == STATE_VERIFIED for k in live_keys)
    live_requested = any(sr.get(k) != STATE_NOT_REQUESTED for k in live_keys)
    failed = [k for k in SUB_RESULT_KEYS if sr.get(k) == STATE_FAILED]

    if failed:
        warnings.append("requested sub-result(s) FAILED: " + ", ".join(failed)
                        + " — the run is BLOCKED, not a partial success")

    if stopped or failed:
        status = STATUS_BLOCKED
    elif setup_ok:
        status = STATUS_VERIFIED if live_verified else STATUS_SETUP_VERIFIED
    else:
        status = STATUS_BLOCKED

    if live_verified:
        live_status = LIVE_AV_VERIFIED
    else:
        live_status = LIVE_AV_PENDING
        if not live_requested:
            warnings.append("live AV was not requested in this brief — reported PENDING, "
                            "never as passed")

    unmet = [k for k in SUB_RESULT_KEYS
             if sr.get(k) not in (STATE_VERIFIED, STATE_NOT_REQUESTED)]
    return {
        "status": status,
        "live_av_status": live_status,
        "sub_results": sr,
        "unmet_sub_results": unmet,
        "warnings": warnings,
        "stopped_at": stopped,
        "plan_version": plan.get("plan_version"),
        "room_link_mode": plan.get("room_link_mode"),
    }


# ---------------------------------------------------------------------------
# Secret hygiene — the passcode value must never reach disk
# ---------------------------------------------------------------------------
def assert_no_secret_leak(evidence_root: str, secret_values: List[str]) -> List[str]:
    """Return the artifact paths that contain a secret VALUE. Empty list = clean.

    This is a test-and-run guard, not a redactor: if it ever finds the value, the
    caller has a real leak and must fail loudly rather than scrub and move on.
    """
    leaks: List[str] = []
    values = [v for v in (secret_values or []) if v and len(str(v)) >= 4]
    if not values:
        return leaks
    for root, _dirs, files in os.walk(evidence_root):
        for name in files:
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    blob = fh.read()
            except OSError:
                continue
            if any(str(v) in blob for v in values):
                leaks.append(path)
    return leaks


# ---------------------------------------------------------------------------
# DUMB layer — the live walk. Every collaborator is injectable so the walk is
# testable without a browser, and so no component is faked inside this module.
# ---------------------------------------------------------------------------
def _default_deps() -> dict:
    """Real collaborators. Any of these may be absent in a bare checkout; the walk
    records the absence honestly instead of pretending the step passed."""
    return {
        "seed_and_land": _seed_and_land if _HAVE_FFB else None,
        "close": _close_session if _HAVE_FFB else None,
        "room_inventory": None,   # must be supplied by the caller/live glue
        "guest_context": None,    # MUST be a separate context; no default
        "media_devices": None,
        "rehearsal_observation": None,
        "calendar": None,         # Skill 44 owns calendar; never re-implemented here
        "follow_up_tasks": None,
        "resolve_secret": None,
        "secret_values": [],
    }


def _inventory_rows(session: str, sels: dict, deps: dict) -> List[dict]:
    lister = deps.get("room_inventory")
    if lister is None:
        return []
    rows = lister(session, sels) or []
    return [r for r in rows if isinstance(r, dict)]


def _apply_security(session: str, sels: dict, plan: dict, deps: dict,
                    warnings: List[str]) -> None:
    """Apply only SUPPORTED controls. An unsupported requested setting becomes a
    named gap — it is never silently dropped and never reported as applied."""
    if plan.get("waiting_room_policy") == "controlled_admission":
        try:
            ex_click(session, sels, "meeting_room.security.waiting_room_toggle",
                          required=False)
        except StopAndReport as sr:
            warnings.append(f"waiting room not applied: {sr.reason[:120]}")
    if plan.get("passcode_secret_reference"):
        resolver = deps.get("resolve_secret")
        if resolver is None:
            warnings.append("passcode requested but no secret resolver was supplied — "
                            "control left unset")
        else:
            value = resolver(plan["passcode_secret_reference"])
            if not value:
                warnings.append("secret resolver returned nothing for "
                                f"{plan['passcode_secret_reference']} — passcode left unset")
            else:
                ex_fill(session, sels, "meeting_room.security.passcode_input", str(value),
                             required=False)
    if plan.get("allow_guests"):
        try:
            ex_click(session, sels, "meeting_room.security.guest_access_toggle",
                          required=False)
        except StopAndReport as sr:
            warnings.append(f"guest access not applied: {sr.reason[:120]}")
    for uid in plan.get("cohost_user_ids", []):
        try:
            ex_click(session, sels, "meeting_room.security.cohost_add_control",
                          required=False)
            ex_fill(session, sels, "meeting_room.security.cohost_user_input", uid,
                         required=False)
            ex_click(session, sels, "meeting_room.security.cohost_confirm", required=False)
        except StopAndReport as sr:
            warnings.append(f"co-host {uid} not applied: {sr.reason[:120]}")


def _snapshot_now(session: str) -> str:
    """Late-bound snapshot so a test that patches the shared glue is honored."""
    fn = globals().get("_snapshot")
    try:
        return (fn(session) or "") if fn else ""
    except Exception:  # noqa: BLE001
        return ""


def _verify_saved_and_reopened(session: str, plan: dict,
                               sub: Dict[str, str], warnings: List[str]) -> dict:
    """Save-and-reopen proof. The reopened panel must show the room name, the host
    identity and the configured co-hosts. A toast is explicitly not accepted."""
    snap = _snapshot_now(session)
    observed: Dict[str, Any] = {"name": "", "owner_user_id": "", "cohosts": [],
                                "join_url": "", "surface": "reopened_room"}
    want = (plan.get("purpose") or "").strip()
    if want and want.lower() in snap.lower():
        observed["name"] = want
    # Host identity must be readable from the reopened surface. If it cannot be read
    # it stays unverified — never assumed from the request.
    if plan.get("host_user_id") and plan["host_user_id"].lower() in snap.lower():
        observed["owner_user_id"] = plan["host_user_id"]
    for uid in plan.get("cohost_user_ids", []):
        if uid.lower() in snap.lower():
            observed["cohosts"].append(uid)

    missing = [u for u in plan.get("cohost_user_ids", []) if u not in observed["cohosts"]]
    # Independence matters: persistence (name + requested co-hosts) and host ownership
    # are separate proofs. A surface that cannot show the owner must not also fail the
    # configuration proof, and vice versa.
    if observed["name"] and not missing:
        sub["configuration_saved_and_reopened"] = STATE_VERIFIED
    else:
        if not observed["name"]:
            warnings.append("reopened room did not show the configured name — persistence "
                            "is NOT proven")
        if missing:
            warnings.append(f"co-hosts not visible after reopen: {missing}")
    if observed["owner_user_id"]:
        sub["host_identity_verified"] = STATE_VERIFIED
    else:
        warnings.append("reopened room did not show the expected host identity — host "
                        "ownership is NOT proven")
    return observed


def _calendar_branch(plan: dict, deps: dict, sub: Dict[str, str],
                     warnings: List[str]) -> dict:
    """Calendar / course / event integration. Skill 44 owns the calendar operations,
    so this asks the injected adapter and records whatever it actually observed."""
    out: Dict[str, Any] = {"mode": plan.get("room_link_mode"), "appointments": [],
                           "links": [], "reschedule": None, "cancel": None,
                           "reusable_link": ""}
    adapter = deps.get("calendar")
    if adapter is None:
        warnings.append("no authorized Skill 44 calendar adapter supplied — calendar "
                        "integration recorded PENDING, not presumed")
        sub["calendar_link_generation_verified"] = STATE_PENDING
        sub["reschedule_and_cancellation_verified"] = STATE_PENDING
        return out

    existing = None
    if hasattr(adapter, "read_appointment"):
        existing = adapter.read_appointment(
            calendar_id=plan.get("calendar_id"), appointment_id=plan.get("event_id"))
        out["existing"] = existing or {}
        prior = (existing or {}).get("meeting_location") or ""
        if prior and "meeting room" not in str(prior).lower() and not plan.get(
                "migration_authorization"):
            warnings.append(
                f"existing meeting location {prior!r} preserved — replacing it needs a "
                "migration_authorization reference (no implicit Zoom migration)")
            sub["calendar_link_generation_verified"] = STATE_PENDING
            return out

    if plan.get("room_link_mode") == "reusable":
        link = (existing or {}).get("join_url") or ""
        out["reusable_link"] = link
        if link:
            sub["calendar_link_generation_verified"] = STATE_VERIFIED
        else:
            warnings.append("reusable link was not observed on the appointment — recorded "
                            "PENDING, never fabricated")
            sub["calendar_link_generation_verified"] = STATE_PENDING
        return out

    if plan.get("room_link_mode") != "appointment_unique":
        sub["calendar_link_generation_verified"] = STATE_NOT_REQUESTED
        return out

    # appointment_unique: create TWO test appointments, read the ACTUAL links, then
    # reschedule one and cancel the other, recording the platform's real behaviour.
    first = adapter.create_test_appointment(calendar_id=plan.get("calendar_id"),
                                            sequence=1, plan=plan)
    second = adapter.create_test_appointment(calendar_id=plan.get("calendar_id"),
                                             sequence=2, plan=plan)
    out["appointments"] = [first, second]
    links = [(a or {}).get("join_url") or "" for a in (first, second)]
    out["links"] = links
    if all(links) and links[0] != links[1]:
        sub["calendar_link_generation_verified"] = STATE_VERIFIED
    elif all(links):
        warnings.append("both test appointments received the SAME link — that is reusable "
                        "behaviour, not appointment-unique; reported as unverified")
    else:
        warnings.append("a test appointment returned no observed join link — uniqueness is "
                        "NOT proven")

    try:
        out["reschedule"] = adapter.reschedule(
            appointment_id=(first or {}).get("appointment_id"), sequence=1)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"reschedule probe failed: {type(exc).__name__}: {exc}")
    try:
        out["cancel"] = adapter.cancel(appointment_id=(second or {}).get("appointment_id"),
                                       sequence=2)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"cancel probe failed: {type(exc).__name__}: {exc}")

    r_ok = bool((out.get("reschedule") or {}).get("observed"))
    c_ok = bool((out.get("cancel") or {}).get("observed"))
    if r_ok and c_ok:
        sub["reschedule_and_cancellation_verified"] = STATE_VERIFIED
        stale = ((out["reschedule"].get("stale_links") or [])
                 + (out["cancel"].get("stale_links") or []))
        if stale:
            warnings.append("stale or duplicate meeting links observed after reschedule/"
                            f"cancel: {stale}")
    else:
        warnings.append("reschedule/cancellation behaviour was NOT observed — reported "
                        "PENDING, never presumed")
        sub["reschedule_and_cancellation_verified"] = STATE_PENDING
    return out


def _guest_check(plan: dict, deps: dict, join_url: str, sub: Dict[str, str],
                 warnings: List[str]) -> dict:
    """Guest flow in an ISOLATED context. A guest check that shares the host session
    proves nothing, so a caller-supplied context is mandatory and is never the host's."""
    opener = deps.get("guest_context")
    if opener is None:
        warnings.append("no isolated guest context supplied — guest flow recorded PENDING "
                        "(never verified from the authenticated host session)")
        sub["guest_join_flow_verified"] = STATE_PENDING
        return {"isolated": None, "joined": None}
    if not join_url:
        warnings.append("no join link available for the guest check — PENDING")
        sub["guest_join_flow_verified"] = STATE_PENDING
        return {"isolated": None, "joined": None}
    ctx = opener(join_url, plan=plan)
    ctx = ctx if isinstance(ctx, dict) else {}
    if ctx.get("isolated") is not True:
        warnings.append("the supplied guest context was not declared isolated — refusing to "
                        "count the guest result")
        sub["guest_join_flow_verified"] = STATE_FAILED
        return {"isolated": False, "joined": ctx.get("joined")}
    if ctx.get("joined") is True:
        sub["guest_join_flow_verified"] = STATE_VERIFIED
    else:
        warnings.append(f"guest could not join: {ctx.get('reason') or 'no reason recorded'}")
        sub["guest_join_flow_verified"] = STATE_FAILED
    return {"isolated": True, "joined": ctx.get("joined"),
            "waiting_room": ctx.get("waiting_room")}


def _rehearsal(plan: dict, deps: dict, sub: Dict[str, str], warnings: List[str]) -> dict:
    """Authorized functional rehearsal. Two independent facts are required before any
    live media claim: usable devices AND an observed rehearsal result. Devices alone
    prove nothing — a camera present is not audio/video exercised."""
    devices = None
    probe = deps.get("media_devices")
    if probe is not None:
        devices = probe() or {}
    observe = deps.get("rehearsal_observation")
    observed = (observe() if callable(observe) else observe) or {}
    out: Dict[str, Any] = {"devices": devices, "observed": observed, "exercised": []}
    if not devices or not (devices.get("audio") or devices.get("video")):
        warnings.append("no usable microphone/camera in this environment — live audio/video "
                        "is PENDING, never passed")
        for k in ("live_audio_video_verified", "screen_sharing_verified"):
            if sub.get(k) != STATE_NOT_REQUESTED:
                sub[k] = STATE_PENDING
    elif not observed:
        warnings.append("usable devices were reported but no rehearsal was observed — "
                        "device presence alone never proves audio/video; reported PENDING")
        for k in ("live_audio_video_verified", "screen_sharing_verified"):
            if sub.get(k) != STATE_NOT_REQUESTED:
                sub[k] = STATE_PENDING
    else:
        if observed.get("audio") and observed.get("video"):
            sub["live_audio_video_verified"] = STATE_VERIFIED
            out["exercised"].append("audio+video")
        else:
            if sub.get("live_audio_video_verified") != STATE_NOT_REQUESTED:
                sub["live_audio_video_verified"] = STATE_PENDING
        if observed.get("screen"):
            sub["screen_sharing_verified"] = STATE_VERIFIED
            out["exercised"].append("screen_share")
    if plan.get("breakout_requested"):
        # A created/assigned breakout room is NOT proof participants moved.
        out["breakout"] = {"created": None, "assigned": None, "opened": None,
                           "participants_inside": None}
        warnings.append("breakout requested but no live session was run — created/assigned/"
                        "opened stay UNVERIFIED (an assignment is not an active session)")
    return out


def _recording_branch(plan: dict, deps: dict, sub: Dict[str, str],
                      warnings: List[str]) -> dict:
    """Recording / transcription / summary / follow-up are SEPARATE outputs. Each is
    only ever VERIFIED from an observed post-meeting artifact."""
    out: Dict[str, Any] = {}
    for key, policy_key in (("recording_verified", "recording_policy"),
                            ("transcript_verified", "transcription_policy"),
                            ("summary_verified", "summary_policy")):
        if sub.get(key) == STATE_NOT_REQUESTED:
            continue
        policy = str(plan.get(policy_key) or "")
        if policy in ("on", "always") and not plan.get("approval_references"):
            warnings.append(f"{key}: policy {policy!r} without an approval reference — not "
                            "enabled, reported PENDING")
            sub[key] = STATE_PENDING
        elif policy in ("on", "always"):
            warnings.append(f"{key}: enabled by policy but no post-meeting artifact was "
                            "observed in this run — reported PENDING")
            sub[key] = STATE_PENDING
        else:
            sub[key] = STATE_NOT_REQUESTED
        out[key] = policy
    if plan.get("recording_policy") in ("on", "always") and plan.get(
            "transcription_policy") not in ("on", "always"):
        warnings.append("recording is ON but transcription is not — recording alone does "
                        "NOT produce a transcript")
    if sub.get("follow_up_task_creation_verified") != STATE_NOT_REQUESTED:
        if deps.get("follow_up_tasks") is None:
            sub["follow_up_task_creation_verified"] = STATE_PENDING
            warnings.append("follow-up task creation needs an authorized Skill 44 task "
                            "adapter — PENDING")
    return out


def _cleanup(session: str, sels: dict, plan: dict, created: bool,
             warnings: List[str]) -> dict:
    """Remove ONLY a scratch room this run created, ONLY under an explicit
    authorization. Everything else is left exactly as it was (IG-MEET-09)."""
    out: Dict[str, Any] = {"attempted": False, "deleted": False}
    if not created:
        out["note"] = "nothing created by this run — no cleanup performed"
        return out
    auth = plan.get("cleanup_authorization")
    if not auth:
        out["note"] = ("scratch room created but no cleanup_authorization was given — left in "
                       "place on purpose; deleting without authorization is forbidden")
        warnings.append(out["note"])
        return out
    out["attempted"] = True
    try:
        ex_click(session, sels, "meeting_room.cleanup.delete_room_control", required=True)
        ex_click(session, sels, "meeting_room.cleanup.delete_confirm", required=True)
        out["deleted"] = True
        out["authorization"] = auth
    except StopAndReport as sr:
        out["stop"] = str(sr)
        out["deleted"] = False
    return out


# ---------------------------------------------------------------------------
# The live walk itself
# ---------------------------------------------------------------------------
def _live_build(task: dict, plan: dict, click_list: dict, pre: dict,
                evidence_root: str, started: float,
                state: Optional["ghl_run_state.RunState"] = None,
                deps: Optional[dict] = None) -> dict:
    if not (_HAVE_FFB and getattr(_ffb, "browser_manager", None) is not None):
        raise RuntimeError(
            "LIVE build requires the Skill-6 tools/ modules (ghl_form_builder glue + "
            "browser_manager) importable — run --dry-run/--selftest here, live only from "
            "the skill's tools/ dir.")
    d = dict(_default_deps())
    d.update(deps or {})

    location_id = plan["location_id"]
    os.environ["GHL_LOCATION_ID"] = location_id
    session = _canonical_session(location_id)
    sels = load_selectors()
    sub = dict(plan["sub_results"])
    warnings: List[str] = []
    steps_done: List[str] = []
    stop: Optional[StopAndReport] = None
    created = False
    identity: Dict[str, Any] = {}
    inventory_rows: List[dict] = []
    reuse: Dict[str, Any] = {}
    integration: Dict[str, Any] = {}
    guest: Dict[str, Any] = {}
    rehearsal: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
    delivery: Dict[str, Any] = {}
    cleanup: Dict[str, Any] = {"attempted": False}

    _ffb.browser_manager.headless_guard()
    _ffb.browser_manager.assert_agent_browser_version()
    _cm = _ffb.browser_manager.browser_session(location_id)
    _sess = _cm.__enter__()
    if _sess:
        session = _sess
    try:
        # B0 — bind identity. Never assume the operator may configure the host's room.
        def _do_bind() -> dict:
            seed = d.get("seed_and_land") or _seed_and_land
            auth = seed(session, location_id, evidence_root) or {}
            _write_json(os.path.join(evidence_root, "routing", "auth-receipt.json"),
                        {"landed": auth.get("landed"), "seeded_at": _ts()})
            steps_done.append("B0:bound")
            return {"landed": auth.get("landed"), "host_user_id": plan["host_user_id"]}

        run_phase(state, "bind", _do_bind, log=_log)

        # P1 — probe the feature: entitlement vs permission vs rollout vs selector drift.
        def _do_probe() -> dict:
            report = selector_status_report(sels)
            probe = {"selector_status": report, "entitlement": "unknown",
                     "permission": "unknown", "rollout": "unknown"}
            ex_click(session, sels, "meeting_room.nav.meeting_room_rail_item",
                          required=True)
            probe["visible"] = True
            _write_json(os.path.join(evidence_root, "routing", "meeting-room-probe.json"), probe)
            steps_done.append("P1:probed")
            return probe

        run_phase(state, "probe", _do_probe, log=_log)

        # I1 — inventory and reuse decision.
        def _do_inventory() -> dict:
            nonlocal inventory_rows, reuse
            inventory_rows = _inventory_rows(session, sels, d)
            reuse = reuse_decision(plan, inventory_rows)
            _write_json(os.path.join(evidence_root, "routing", "meeting-room-inventory.json"),
                        {"rooms": inventory_rows, "reuse": reuse})
            steps_done.append(f"I1:{reuse['action']}")
            if reuse["action"] == "blocked":
                raise StopAndReport("I1.reuse", reuse["reason"])
            return reuse

        run_phase(state, "inventory", _do_inventory, log=_log)

        # S1-S3 — create or reuse, apply only supported controls, save.
        def _do_setup() -> dict:
            nonlocal created, identity
            if reuse.get("action") == "reuse":
                identity = dict(reuse.get("room") or {})
                steps_done.append("S1:reused")
                return {"action": "reuse", "identity": identity}
            ex_click(session, sels, "meeting_room.nav.my_room_card", required=True)
            ex_click(session, sels, "meeting_room.my_room.create_room_button", required=True)
            ex_fill(session, sels, "meeting_room.my_room.room_name_input",
                         plan.get("purpose") or "Room")
            _apply_security(session, sels, plan, d, warnings)
            ex_click(session, sels, "meeting_room.my_room.room_save_button", required=True)
            created = True
            steps_done.append("S1:created")
            return {"action": "create"}

        run_phase(state, "setup", _do_setup, log=_log)

        # S4 — save and RE-OPEN; the reopened panel is the proof, not the toast.
        def _do_save_reopen() -> dict:
            nonlocal identity
            ex_click(session, sels, "meeting_room.my_room.reopen_entry", required=False)
            observed = _verify_saved_and_reopened(session, plan, sub, warnings)
            if not identity:
                identity = dict(observed)
            else:
                for k, v in observed.items():
                    identity.setdefault(k, v)
            _write_json(os.path.join(evidence_root, "routing", "meeting-room-reopen.json"),
                        observed)
            steps_done.append("S4:reopened")
            return observed

        run_phase(state, "save_reopen", _do_save_reopen, log=_log)

        # X1/X2 — integration branch (calendar / course / event).
        def _do_integration() -> dict:
            nonlocal integration
            integration = _calendar_branch(plan, d, sub, warnings)
            integration["join_url"] = (integration.get("reusable_link")
                                       or identity.get("join_url") or "")
            _write_json(os.path.join(evidence_root, "routing", "meeting-room-integration.json"),
                        integration)
            steps_done.append(f"X1:{plan['room_link_mode']}")
            return integration

        run_phase(state, "integration", _do_integration, log=_log)

        # G1 — isolated guest check.
        def _do_guest() -> dict:
            nonlocal guest
            guest = _guest_check(plan, d, integration.get("join_url", ""), sub, warnings)
            _write_json(os.path.join(evidence_root, "routing", "meeting-room-guest.json"), guest)
            steps_done.append(f"G1:{sub.get('guest_join_flow_verified')}")
            return guest

        run_phase(state, "guest_check", _do_guest, log=_log)

        # V1 — authorized rehearsal + the SEPARATE output checks.
        def _do_rehearsal() -> dict:
            nonlocal rehearsal, outputs
            rehearsal = _rehearsal(plan, d, sub, warnings)
            outputs = _recording_branch(plan, d, sub, warnings)
            _write_json(os.path.join(evidence_root, "routing", "meeting-room-rehearsal.json"),
                        {"rehearsal": rehearsal, "outputs": outputs})
            steps_done.append("V1:rehearsed")
            return rehearsal

        run_phase(state, "rehearsal", _do_rehearsal, log=_log)

        # D1 — deliver only OBSERVED links, and keep the three link kinds apart.
        def _do_delivery() -> dict:
            nonlocal delivery
            calendar = d.get("calendar")
            delivery = {
                "guest_join_link": integration.get("join_url", "") or "",
                "host_controls": "authenticated host UI only — never sent as a guest link",
                "booking_link": (getattr(calendar, "booking_link", "") if calendar else ""),
                "delivered": bool(integration.get("join_url")),
            }
            if not delivery["delivered"]:
                warnings.append("no observed join link to deliver — nothing was handed out")
            _write_json(os.path.join(evidence_root, "routing", "meeting-room-delivery.json"),
                        delivery)
            steps_done.append(f"D1:{delivery['delivered']}")
            return delivery

        run_phase(state, "delivery", _do_delivery, log=_log)

        cleanup = _cleanup(session, sels, plan, created, warnings)
    except StopAndReport as sr:
        stop = sr
        _log(f"STOP-and-report @ {sr.step}: {sr.reason}")
    except Exception as exc:  # noqa: BLE001
        stop = StopAndReport("unexpected", f"{type(exc).__name__}: {exc}")
    finally:
        try:
            closer = d.get("close")
            if closer:
                closer(location_id)
        except Exception:  # noqa: BLE001
            pass
        try:
            _cm.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        _write_json(os.path.join(evidence_root, "routing", "meeting-room-cleanup.json"), cleanup)

    final = finalize_result(plan, sub, stopped=(str(stop) if stop else None),
                            warnings=warnings)
    secrets = [str(v) for v in (d.get("secret_values") or [])]
    leaks = assert_no_secret_leak(evidence_root, secrets) if secrets else []
    if leaks:
        final["secret_leaks"] = leaks
        final["status"] = STATUS_BLOCKED
        final["warnings"].append(f"SECRET LEAK: {len(leaks)} artifact(s) contain a resolved "
                                 "secret value — run blocked")
    final.update({
        "ok": final["status"] != STATUS_BLOCKED,
        "object_type": "meeting_room",
        "dry_run": False,
        "duration_s": time.monotonic() - started,
        "location_id": plan["location_id"],
        "host_user_id": plan["host_user_id"],
        "room_link_mode": plan["room_link_mode"],
        "identity": identity,
        "reuse": reuse,
        "integration": integration,
        "guest": guest,
        "rehearsal": rehearsal,
        "outputs": outputs,
        "delivery": delivery,
        "cleanup": cleanup,
        "steps_done": steps_done,
        "stop_step": (stop.step if stop else ""),
        "stop_reason": (stop.reason if stop else ""),
        "browser_policy": BROWSER_POLICY,
    })
    return final


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def _router_is_registered(object_type: str) -> bool:
    try:
        _router.route(object_type)
        return True
    except Exception:  # noqa: BLE001
        return False


def build_meeting_room(task: dict, evidence_root: str, *, dry_run: bool = True,
                       state: Optional["ghl_run_state.RunState"] = None,
                       deps: Optional[dict] = None) -> dict:
    started = time.monotonic()
    dry_run = bool(task.get("dry_run", dry_run))
    routing = os.path.join(evidence_root, "routing")
    os.makedirs(routing, exist_ok=True)
    os.makedirs(os.path.join(evidence_root, "shots"), exist_ok=True)

    plan = run_phase(state, "plan", lambda: plan_room(task), log=_log)
    pre = run_phase(state, "preflight", lambda: preflight(plan), log=_log)
    click_list = run_phase(state, "click_list", lambda: emit_click_list(plan), log=_log)
    _write_json(os.path.join(routing, "meeting-room-plan.json"), plan)
    _write_json(os.path.join(routing, "meeting-room-click-list.json"), click_list)
    _write_json(os.path.join(routing, "meeting-room-preflight.json"), pre)
    _write_json(os.path.join(routing, "meeting-room-subresults.json"), plan["sub_results"])

    if not pre["pass"]:
        return {"ok": False, "status": STATUS_BLOCKED, "object_type": "meeting_room",
                "duration_s": time.monotonic() - started, "preflight": pre,
                "error": pre["stop_reason"], "dry_run": dry_run,
                "sub_results": plan["sub_results"]}

    if dry_run:
        disclosure = (_router.tier_disclosure(_router.route("meeting_room").rails[0])
                      if (_HAVE_ROUTER and _router_is_registered("meeting_room"))
                      else "[GHL tier used: 4 — ghl_meeting_rooms.py managed browser]")
        _log(f"[dry-run] meeting-room plan + click list ({click_list['total_steps']} steps). "
             f"{disclosure}")
        return {"ok": True, "status": STATUS_PLANNED, "dry_run": True,
                "setup_verified": False,
                "object_type": "meeting_room", "duration_s": time.monotonic() - started,
                "plan": plan, "click_list": click_list, "preflight": pre,
                "sub_results": plan["sub_results"], "tier_disclosure": disclosure,
                "live_av_status": LIVE_AV_PENDING,
                "browser_policy": BROWSER_POLICY,
                "selector_status": selector_status_report(),
                "note": ("dry run: nothing was written to GoHighLevel. Live AV, recording, "
                         "transcript, summary and follow-up stay NOT RUN by construction.")}

    return _live_build(task, plan, click_list, pre, evidence_root, started,
                       state=state, deps=deps)


# ---------------------------------------------------------------------------
# Frozen interface checkpoint WF26-CP01 — room-plan schema fragment + dry-run
# interface. Consumers (WF07 dispatcher, WF09 gates, WF22 integration) read this
# shape instead of inventing their own.
# ---------------------------------------------------------------------------
SCHEMA_PATH = os.path.join(_TOOLS_DIR, "meeting-room-plan.schema.json")

DRY_RUN_INTERFACE = {
    "entrypoint": "build_meeting_room(task, evidence_root, dry_run=True) -> dict",
    "status": STATUS_PLANNED,
    "network": "none — plan, preflight and click list only; nothing is written to GoHighLevel",
    "artifacts": [
        "routing/meeting-room-plan.json",
        "routing/meeting-room-click-list.json",
        "routing/meeting-room-preflight.json",
        "routing/meeting-room-subresults.json",
    ],
    "requires": ["location_id", "host_user_id", "room_link_mode in ROOM_LINK_MODES"],
    "refuses": [
        "a literal passcode (passcode_secret_reference only)",
        "room_link_mode='existing_room' without existing_room_reference",
        "an unknown room_link_mode",
        "any hard preflight gate failure",
    ],
    "live_av_status": LIVE_AV_PENDING,
    "browser_policy": BROWSER_POLICY,
}


def _json_type(value: Any) -> Any:
    if value is None:
        return ["object", "null"]
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def plan_room_schema() -> dict:
    """The frozen room-plan schema fragment for checkpoint WF26-CP01.

    Generated from plan_room() itself so the published interface cannot drift from
    the executable plan. tests/test_ghl_meeting_rooms.py regenerates this and
    compares it to the committed meeting-room-plan.schema.json.
    """
    sample = plan_room({"location_id": "SYNTHETIC_LOCATION",
                        "host_user_id": "SYNTHETIC_HOST_USER",
                        "purpose": "office hours",
                        "room_link_mode": "reusable"})
    props: Dict[str, Any] = {k: {"type": _json_type(v)} for k, v in sample.items()}
    props["location_id"]["description"] = (
        "GHL sub-account. The subaccount gate runs before any write.")
    props["host_user_id"]["description"] = (
        "Staff user that must OWN the room. Required; never defaulted to the operator.")
    props["room_link_mode"]["enum"] = list(ROOM_LINK_MODES)
    props["room_link_mode"]["description"] = (
        "Internal label only; translate through observed UI controls or a verified API field.")
    props["passcode_secret_reference"]["description"] = (
        "Secret REFERENCE only. plan_room() refuses a literal passcode value.")
    props["sub_results"]["description"] = (
        "Honest per-capability sub-results (Document 1 §23.9). A requested but "
        "untested capability is never 'verified'.")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "meeting-room-plan/1",
        "title": "Meeting room plan (workflow WF26)",
        "type": "object",
        "required": ["object_type", "plan_version", "location_id", "host_user_id",
                     "room_link_mode", "sub_results"],
        "additionalProperties": True,
        "properties": props,
    }


def write_plan_schema(path: Optional[str] = None) -> str:
    out = path or SCHEMA_PATH
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(plan_room_schema(), fh, indent=2, sort_keys=True)
        fh.write("\n")
    return out


def _click_list_targets(click_list: dict) -> List[str]:
    """Every selector-map path the click list names (free-text targets excluded)."""
    return [str(s.get("target") or "") for s in (click_list.get("steps") or [])
            if str(s.get("target") or "").startswith("meeting_room.")]


def task_from_args(args: Any) -> dict:
    """CLI Namespace -> the same task dict plan_room() consumes."""
    def _csv(raw: Any) -> List[str]:
        return [p.strip() for p in str(raw or "").split(",") if p.strip()]
    return {
        "location_id": getattr(args, "location_id", ""),
        "host_user_id": getattr(args, "host_user_id", ""),
        "purpose": getattr(args, "purpose", ""),
        "room_link_mode": getattr(args, "room_link_mode", "reusable"),
        "existing_room_reference": getattr(args, "existing_room_reference", ""),
        "calendar_id": getattr(args, "calendar_id", ""),
        "course_id": getattr(args, "course_id", ""),
        "event_id": getattr(args, "event_id", ""),
        "cohost_user_ids": _csv(getattr(args, "cohost_user_ids", "")),
        "participant_audience": getattr(args, "participant_audience", "invited"),
        "allow_guests": bool(getattr(args, "allow_guests", False)),
        "waiting_room_policy": getattr(args, "waiting_room_policy", "controlled_admission"),
        "passcode_secret_reference": getattr(args, "passcode_secret_reference", ""),
        "schedule_timezone": getattr(args, "schedule_timezone", "America/New_York"),
        "duration_minutes": getattr(args, "duration_minutes", 30),
        "notice_minutes": getattr(args, "notice_minutes", 0),
        "buffer_before_minutes": getattr(args, "buffer_before_minutes", 0),
        "buffer_after_minutes": getattr(args, "buffer_after_minutes", 0),
        "recording_policy": getattr(args, "recording_policy", "off_unless_approved"),
        "transcription_policy": getattr(args, "transcription_policy", "off_unless_approved"),
        "transcription_language": getattr(args, "transcription_language", ""),
        "summary_policy": getattr(args, "summary_policy", "not_requested"),
        "review_owner": getattr(args, "review_owner", ""),
        "retention_and_sharing_policy": getattr(args, "retention_and_sharing_policy",
                                                "client_default"),
        "notification_policy": getattr(args, "notification_policy", "client_default"),
        "approval_references": list(getattr(args, "approval_reference", None) or []),
        "requested_outputs": _csv(getattr(args, "requested_outputs", "")),
        "breakout_requested": bool(getattr(args, "breakout", False)),
        "migration_authorization": getattr(args, "migration_authorization", ""),
        "cleanup_authorization": getattr(args, "cleanup_authorization", ""),
    }


class _FakeCalendar:
    """Self-test only. Never used by the live path: the walk takes the injected
    Skill-44 adapter and never brands a fake as a real calendar."""

    def __init__(self, links=("https://join/a", "https://join/b"),
                 existing=None, reschedule=True, cancel=True):
        self.links = list(links)
        self.existing = existing
        self._n = 0
        self._reschedule = reschedule
        self._cancel = cancel
        self.booking_link = "https://book.example/cal"

    def read_appointment(self, calendar_id=None, appointment_id=None):
        return self.existing or {}

    def create_test_appointment(self, calendar_id=None, sequence=1, plan=None):
        link = self.links[sequence - 1] if sequence - 1 < len(self.links) else ""
        self._n += 1
        return {"appointment_id": f"appt-{self._n}", "join_url": link}

    def reschedule(self, appointment_id=None, sequence=1):
        return {"appointment_id": appointment_id, "observed": self._reschedule,
                "stale_links": []}

    def cancel(self, appointment_id=None, sequence=2):
        return {"appointment_id": appointment_id, "observed": self._cancel,
                "stale_links": []}


def _selftest() -> int:  # pragma: no cover - exercised by tests/test_ghl_meeting_rooms.py
    """Network-free, browser-free proof of the THINK layer and the safety gates."""
    import tempfile

    failures: List[str] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(f"{name}: {detail}")

    sels = load_selectors()
    base = {"location_id": "SYNTHETIC_LOCATION", "host_user_id": "SYNTHETIC_HOST_USER",
            "purpose": "office hours", "room_link_mode": "reusable"}
    plan = plan_room(dict(base))
    ok("plan/defaults", plan["room_link_mode"] == "reusable" and plan["host_user_id"],
       "plan defaults")
    ok("plan/sub_results_start_not_run",
       plan["sub_results"]["configuration_saved_and_reopened"] == STATE_NOT_RUN, "init")
    ok("plan/breakout_not_requested",
       plan["sub_results"]["breakout_opened_verified"] == STATE_NOT_REQUESTED, "breakout")

    def raises(fn, label: str) -> bool:
        try:
            fn()
        except StopAndReport:
            return True
        except Exception:  # noqa: BLE001
            return False
        return False

    ok("plan/refuses_missing_host",
       raises(lambda: plan_room({"location_id": "L"}), "missing host"),
       "a missing host_user_id must STOP, never default to the operator")
    ok("plan/refuses_literal_passcode",
       raises(lambda: plan_room(dict(base, passcode="1234")), "literal passcode"),
       "a literal passcode must be refused")
    ok("plan/refuses_existing_room_without_ref",
       raises(lambda: plan_room(dict(base, room_link_mode="existing_room")), "existing ref"),
       "existing_room needs existing_room_reference")
    ok("plan/refuses_unknown_mode",
       raises(lambda: plan_room(dict(base, room_link_mode="zoom")), "unknown mode"),
       "an unknown room_link_mode must be refused")

    pre = preflight(plan)
    ok("preflight/pass", pre["pass"], str(pre.get("stop_reason")))

    click = emit_click_list(plan)
    missing = [t for t in _click_list_targets(click) if not _target_present(sels, t)]
    ok("click_list/targets_resolve", not missing, f"missing selector paths: {missing}")
    ok("click_list/no_raw_css",
       all("." in t for t in _click_list_targets(click)), "dotted selector paths only")

    schema = plan_room_schema()
    ok("schema/parity", set(schema["properties"]) == set(plan),
       "schema properties must equal the executable plan keys")
    if os.path.exists(SCHEMA_PATH):
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            frozen = json.load(fh)
        ok("schema/frozen_file_matches", frozen == schema,
           "regenerate with write_plan_schema() — the frozen schema drifted")

    reuse = reuse_decision(plan, [{"name": "Office Hours",
                                   "owner_user_id": "SYNTHETIC_HOST_USER",
                                   "join_url": "https://join/x"}])
    ok("reuse/owned_match", reuse["action"] == "reuse", str(reuse))
    other = reuse_decision(plan, [{"name": "Office Hours", "owner_user_id": "someone-else",
                                   "join_url": "https://join/y"}])
    ok("reuse/other_owner_not_candidate", other["action"] == "create", str(other))
    blocked = reuse_decision(dict(plan, room_link_mode="existing_room",
                                  existing_room_reference="Coaching"),
                             [{"name": "Coaching", "owner_user_id": "someone-else"}])
    ok("reuse/existing_room_blocked", blocked["action"] == "blocked", str(blocked))

    sub_fail: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    sub_fail["configuration_saved_and_reopened"] = STATE_VERIFIED
    sub_fail["host_identity_verified"] = STATE_VERIFIED
    res_fail = finalize_result(plan, dict(sub_fail, guest_join_flow_verified=STATE_FAILED))
    ok("finalize/failed_subresult_blocks", res_fail["status"] == STATUS_BLOCKED,
       "a failed requested sub-result must never leave the run 'verified'")

    sub_ok = dict(sub_fail)
    res_ok = finalize_result(plan, sub_ok)
    ok("finalize/setup_verified_live_pending",
       res_ok["status"] == STATUS_SETUP_VERIFIED and res_ok["live_av_status"] == LIVE_AV_PENDING,
       str(res_ok["status"]))

    sub_guest: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    g_shared = _guest_check(plan, {"guest_context": lambda url, plan=None: {
        "isolated": False, "joined": True}}, "https://join/x", sub_guest, [])
    ok("guest/shared_session_refused",
       sub_guest["guest_join_flow_verified"] == STATE_FAILED and g_shared["isolated"] is False,
       "a guest check inside the host session proves nothing")
    sub_guest2: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    _guest_check(plan, {"guest_context": lambda url, plan=None: {
        "isolated": True, "joined": True}}, "https://join/x", sub_guest2, [])
    ok("guest/isolated_join_verified",
       sub_guest2["guest_join_flow_verified"] == STATE_VERIFIED, "isolated guest join")

    sub_av: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    w_av: List[str] = []
    _rehearsal(plan, {"media_devices": lambda: {"audio": True, "video": True}}, sub_av, w_av)
    ok("rehearsal/devices_alone_not_verified",
       sub_av["live_audio_video_verified"] == STATE_PENDING, "device presence is not proof")
    sub_av2: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    _rehearsal(plan, {"media_devices": lambda: {"audio": True, "video": True},
                      "rehearsal_observation": lambda: {"audio": True, "video": True,
                                                        "screen": True}}, sub_av2, [])
    ok("rehearsal/observed_verifies",
       sub_av2["live_audio_video_verified"] == STATE_VERIFIED
       and sub_av2["screen_sharing_verified"] == STATE_VERIFIED, "observed rehearsal")

    sub_cal: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    out_cal = _calendar_branch(plan, {"calendar": _FakeCalendar(
        existing={"meeting_location": "Meeting Room", "join_url": "https://join/reuse"})},
        sub_cal, [])
    ok("calendar/reusable_observed",
       sub_cal["calendar_link_generation_verified"] == STATE_VERIFIED
       and out_cal["reusable_link"] == "https://join/reuse", str(out_cal))

    plan_u = dict(plan, room_link_mode="appointment_unique")
    sub_u: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    _calendar_branch(plan_u, {"calendar": _FakeCalendar()}, sub_u, [])
    ok("calendar/appointment_unique_distinct_links",
       sub_u["calendar_link_generation_verified"] == STATE_VERIFIED
       and sub_u["reschedule_and_cancellation_verified"] == STATE_VERIFIED, "unique links")
    sub_same: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    w_same: List[str] = []
    _calendar_branch(plan_u, {"calendar": _FakeCalendar(
        links=("https://join/same", "https://join/same"))}, sub_same, w_same)
    ok("calendar/identical_links_not_unique",
       sub_same["calendar_link_generation_verified"] == STATE_NOT_RUN and w_same,
       "identical links must not be reported as appointment-unique")

    sub_zoom: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    w_zoom: List[str] = []
    _calendar_branch(plan, {"calendar": _FakeCalendar(
        existing={"meeting_location": "Zoom", "join_url": "https://zoom/x"})},
        sub_zoom, w_zoom)
    ok("calendar/no_implicit_zoom_migration",
       sub_zoom["calendar_link_generation_verified"] == STATE_PENDING and w_zoom,
       str(w_zoom))

    sub_rec: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    sub_rec["recording_verified"] = STATE_NOT_RUN
    sub_rec["transcript_verified"] = STATE_NOT_RUN
    w_rec: List[str] = []
    _recording_branch(dict(plan, recording_policy="on", transcription_policy="off_unless_approved",
                           approval_references=["APPROVED-REC-1"]),
                      {}, sub_rec, w_rec)
    ok("outputs/recording_is_not_transcript",
       sub_rec["transcript_verified"] == STATE_NOT_REQUESTED
       and any("recording alone" in w for w in w_rec), str(w_rec))

    sub_clean: Dict[str, str] = {k: STATE_NOT_RUN for k in SUB_RESULT_KEYS}
    cleanup = _cleanup("session", sels, plan, created=True, warnings=[])
    ok("cleanup/needs_authorization",
       cleanup["deleted"] is False and cleanup["attempted"] is False,
       "deleting a scratch room needs an explicit cleanup_authorization")

    with tempfile.TemporaryDirectory(prefix="mr-selftest-") as root:
        with open(os.path.join(root, "leak.json"), "w", encoding="utf-8") as fh:
            json.dump({"passcode": "SYNTHETIC-SECRET-VALUE"}, fh)
        leaks = assert_no_secret_leak(root, ["SYNTHETIC-SECRET-VALUE"])
        ok("secret/leak_detected", len(leaks) == 1, f"leaks={leaks}")
        clean = assert_no_secret_leak(root, ["DIFFERENT-SECRET"])
        ok("secret/clean_when_absent", clean == [], f"leaks={clean}")

    print(f"SELFTEST {'PASS' if not failures else 'FAIL'} ({len(failures)} failure(s))")
    for f in failures:
        print("  - " + f)
    return 0 if not failures else 1


def _target_present(selectors: dict, dotted: str) -> bool:
    try:
        _target(selectors, dotted)
        return True
    except KeyError:
        return False


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_meeting_rooms",
        description="GHL (Convert and Flow) MEETING ROOM operator — Skill 06, workflow WF26. "
                    "Default --dry-run: plan + preflight + click list, no network. The live "
                    "walk STOP-and-reports on any capture-pending REQUIRED selector (D8).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    p.add_argument("--selftest", action="store_true",
                   help="network-free proof of the THINK layer and safety gates")
    p.add_argument("--print-schema", action="store_true",
                   help="print the frozen WF26-CP01 room-plan schema fragment")
    p.add_argument("--evidence-root", default="/tmp/meeting-room-run-01")
    p.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID", ""))
    p.add_argument("--host-user-id", default="",
                   help="REQUIRED staff user id that will OWN the room")
    p.add_argument("--purpose", default="")
    p.add_argument("--room-link-mode", default="reusable", choices=list(ROOM_LINK_MODES))
    p.add_argument("--existing-room-reference", default="")
    p.add_argument("--calendar-id", default="")
    p.add_argument("--course-id", default="")
    p.add_argument("--event-id", default="")
    p.add_argument("--cohost-user-ids", default="", help="Comma-separated staff user ids")
    p.add_argument("--participant-audience", default="invited")
    p.add_argument("--allow-guests", action="store_true")
    p.add_argument("--waiting-room-policy", default="controlled_admission")
    p.add_argument("--passcode-secret-reference", default="",
                   help="Secret REFERENCE only; a literal passcode is refused")
    p.add_argument("--schedule-timezone", default="America/New_York")
    p.add_argument("--duration-minutes", type=int, default=30)
    p.add_argument("--notice-minutes", type=int, default=0)
    p.add_argument("--buffer-before-minutes", type=int, default=0)
    p.add_argument("--buffer-after-minutes", type=int, default=0)
    p.add_argument("--recording-policy", default="off_unless_approved")
    p.add_argument("--transcription-policy", default="off_unless_approved")
    p.add_argument("--transcription-language", default="")
    p.add_argument("--summary-policy", default="not_requested")
    p.add_argument("--review-owner", default="")
    p.add_argument("--retention-and-sharing-policy", default="client_default")
    p.add_argument("--notification-policy", default="client_default")
    p.add_argument("--approval-reference", action="append", default=[],
                   help="Repeatable approval reference (recording/transcription etc.)")
    p.add_argument("--requested-outputs", default="",
                   help="Comma-separated optional sub-results, e.g. screen_sharing_verified")
    p.add_argument("--breakout", action="store_true")
    p.add_argument("--migration-authorization", default="")
    p.add_argument("--cleanup-authorization", default="")
    ghl_run_state.add_run_state_args(p)
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.print_schema:
        json.dump(plan_room_schema(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    task = task_from_args(args)
    return ghl_run_state.cli_run(
        args, builder="ghl_meeting_rooms", specs=ROOM_PHASES,
        script_path=__file__, task=task, build=build_meeting_room,
        ok_key="ok", url_key="guest_join_link",
        argv=list(argv if argv is not None else sys.argv[1:]),
    )


if __name__ == "__main__":
    sys.exit(main())

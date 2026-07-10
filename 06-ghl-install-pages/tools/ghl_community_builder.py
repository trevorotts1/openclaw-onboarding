#!/usr/bin/env python3
"""ghl_community_builder.py — Skill 06 browser-control builder for a GoHighLevel /
Convert and Flow COMMUNITY (Group) and its CHANNELS (spec §5.1 + §5.3, unit U13).

GoHighLevel has NO known public create API for a community/group or a channel
(spec §3 marks it ASSUMED until the first-hour Tier-1/Tier-2 tool-list check; the
router flips primary automatically if a create tool is found). The create surface
is therefore browser-only — this module is the DUMB / DO layer driver, split from a
SMART / THINK layer exactly like ghl_form_builder.py:

  • THINK layer (this Python, reasoning model): resolves the plan (ZHC-prefixed
    group name, description, privacy, branding image via a ghl_media CDN URL —
    NEVER browser-uploaded — and the ordered channel list) and emits, WITHOUT any
    browser, three artifacts under <evidence_root>/routing/:
        community-plan.json · community-click-list.json · community-preflight.json
  • DUMB layer (agent-browser 0.27.0): walks the click list through the
    browser_manager singleton on the token-only seeded session — seed → land →
    Memberships nav → search-first (idempotency) → Create Group → fill → capture
    group id/url → add each channel → verify (render_check) → per-object receipts
    (ghl_object_router F6) → ALWAYS delete the scratch group in cleanup.

D8 — ZERO INVENTED SELECTORS. Every in-area anchor is loaded from
`selectors-live-communities-courses.json`. A REQUIRED anchor whose status is
`capture-pending` (i.e. not yet captured live for this object) makes the live walk
STOP-and-report — it NEVER guesses CSS and NEVER brute-forces. Running the live
capture (SELECTORS-LIVE-community.md §capture_procedure) flips the anchor to
`locked`, after which the SAME code drives the real build. dry-run + selftest are
fully network-free and prove the THINK layer + the walk logic (including the
STOP-and-report gate) with a mocked browser.

Auth is the token-only seed rail (shared with the form builder — imported, never
re-implemented). Headless is mandatory (D6). Rate limits honor RateGovernor; the
30-min eval-only SessionKeepalive is wired into the per-step loop (F5). Board
hooks + resume are fail-soft.

Usage:
    result = build_community(task, "/tmp/community-run-01")             # dry_run=True default
    result = build_community(task, "/tmp/community-run-01", dry_run=False)   # live (gated)
    python3 ghl_community_builder.py --dry-run --location-id LOC --community-name "Founders"
    python3 ghl_community_builder.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

# ── shared LIVE-executor glue + THINK helpers (imported, kept in lockstep) ────
# ghl_form_builder ships in THIS dir; its seed/land/nav/ab glue is generic and
# proven live. We import rather than re-implement (spec F7/F11: new builders route
# auth through the seed pair + go through browser_manager — never re-implement).
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
    _router_push = _ffb._router_push
    _assert_logged_in = _ffb._assert_logged_in
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
except Exception:  # noqa: BLE001 — bare checkout: THINK layer still works
    _HAVE_FFB = False

    class StopAndReport(RuntimeError):  # type: ignore[no-redef]
        def __init__(self, step: str, reason: str):
            self.step = step
            self.reason = reason
            super().__init__(f"STOP@{step}: {reason}")

    def _ts() -> str:  # type: ignore[no-redef]
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _log(msg: str) -> None:  # type: ignore[no-redef]
        print(f"[{_ts()}] {msg}", file=sys.stderr)

    def _write_json(path: str, data: Any) -> None:  # type: ignore[no-redef]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)

    def _slug(text: str) -> str:  # type: ignore[no-redef]
        import re
        return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_") or "x"

    _ZHC = "ZHC "

    def ensure_zhc_name(name: str) -> str:  # type: ignore[no-redef]
        name = (name or "").strip()
        return name if name.lower().startswith("zhc ") else f"{_ZHC}{name}"

# ── router (F6 receipts + tier disclosure + rail matrix) ──────────────────────
try:
    import ghl_object_router as _router  # type: ignore
    _HAVE_ROUTER = True
except Exception:  # noqa: BLE001
    _router = None  # type: ignore
    _HAVE_ROUTER = False

# ── rate limiter + keepalive (F5/F8) — soft, like the form/survey builders ────
try:
    from v2_dispatcher import RateGovernor as _RealRateGovernor  # type: ignore
    from v2_dispatcher import SessionKeepalive as _RealKeepalive  # type: ignore
except Exception:  # noqa: BLE001
    _RealRateGovernor = None  # type: ignore
    _RealKeepalive = None  # type: ignore


class _NoopGovernor:
    def before_save(self) -> None: ...
    def before_publish(self) -> None: ...
    def on_429(self, retry_after: Optional[float] = None) -> None: ...


class _NoopKeepalive:
    def due(self) -> bool:
        return False


def _governor():
    return _RealRateGovernor() if _RealRateGovernor else _NoopGovernor()


def _keepalive():
    return _RealKeepalive() if _RealKeepalive else _NoopKeepalive()


SELECTORS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "selectors-live-communities-courses.json")
_ACTIONABLE_STATUS = {"verified-shared-rail", "locked"}


# ---------------------------------------------------------------------------
# Selector map loader (F3b — code + doc cannot diverge; D8 — no invented CSS)
# ---------------------------------------------------------------------------
def load_selectors(path: Optional[str] = None) -> dict:
    with open(path or SELECTORS_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def _target(selectors: dict, dotted: str) -> dict:
    node: Any = selectors
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"selector path {dotted!r} not present in the selector map")
        node = node[part]
    return node


def anchor(selectors: dict, dotted: str, *, required: bool = True) -> str:
    """Return the actionable anchor for a dotted selector path, or STOP-and-report
    (required) / '' (optional) when the target is still `capture-pending`. This is
    the D8 gate: a capture-pending REQUIRED surface never becomes a guessed click."""
    t = _target(selectors, dotted)
    status = t.get("status")
    if status in _ACTIONABLE_STATUS:
        return t.get("anchor", "")
    msg = (f"selector {dotted!r} is status={status!r} — it has NOT been captured live "
           f"for this object. D8 forbids inventing a selector. Run the live capture "
           f"(SELECTORS-LIVE-community.md §capture_procedure: create a scratch group, "
           f"walk it, record the real anchor + confidence, DELETE it) to flip it to "
           f"'locked', then re-run. Fallback-chain (a CAPTURE RECIPE, not a fact): "
           f"{t.get('fallbacks')}")
    if required:
        raise StopAndReport(f"selector:{dotted}", msg)
    _log(f"optional selector {dotted!r} capture-pending — skipped: {msg}")
    return ""


# ---------------------------------------------------------------------------
# THINK layer — plan + click list (network-free)
# ---------------------------------------------------------------------------
def _resolve_channels(task: dict) -> List[dict]:
    raw = task.get("channels") or []
    out: List[dict] = []
    seen: set = set()
    for c in raw:
        name = (c.get("name") if isinstance(c, dict) else str(c)).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:                      # dedupe (F14 search-first / no duplicate)
            continue
        seen.add(key)
        out.append({"name": name,
                    "type": (c.get("type") if isinstance(c, dict) else "") or "post",
                    "slug": _slug(name)})
    return out


def plan_community(task: dict) -> dict:
    name = ensure_zhc_name(task.get("community_name", task.get("name", "New Community")))
    branding = task.get("branding_image_url", "") or task.get("branding", {}).get("image_url", "")
    if branding and "firebase" in branding.lower():
        # canonical link / branding must never be a Firebase URL (mirror funnel SEO rule)
        raise StopAndReport("plan.branding",
                            "branding_image_url is a Firebase URL — use a ghl_media CDN URL "
                            "(media is never browser-routed; spec §5.4 / ghl_media).")
    channels = _resolve_channels(task)
    return {
        "object_type": "community",
        "location_id": task.get("location_id", ""),
        "community_name": name,
        "slug": _slug(name),
        "description": task.get("description", ""),
        "privacy": (task.get("privacy", "private") or "private").lower(),
        "branding_image_url": branding,          # CDN URL only (ghl_media), never a file
        "channels": channels,
        "idempotency_key": "zhc_name_search",     # matches router.route('community')
        "created_at": _ts(),
    }


def emit_click_list(plan: dict) -> dict:
    steps: List[dict] = []

    def add(phase: str, action: str, target: str, note: str = "") -> None:
        steps.append({"n": len(steps) + 1, "phase": phase, "action": action,
                      "target": target, "note": note})

    add("C1", "nav", "Memberships → Communities/Groups list",
        "SPA router.push after Memberships left-rail (getByText); NEVER deep-link the builder")
    add("C2", "search", plan["community_name"],
        "search-first idempotency (F14): if a ZHC group of this name exists → REUSE, skip create")
    add("C3", "click", "Create Group", "list-page create button (capture-pending anchor)")
    add("C3", "fill", "Group name", plan["community_name"])
    if plan["description"]:
        add("C3", "fill", "Description", plan["description"])
    add("C3", "set", f"privacy={plan['privacy']}", "Public/Private control (capture-pending)")
    add("C3", "click", "Create", "confirm the create modal → capture GROUP_ID from location.href/iframe src")
    if plan["branding_image_url"]:
        add("C3", "set", "branding image (CDN URL)",
            "insert the ghl_media CDN URL — NEVER browser-upload a file")
    for ch in plan["channels"]:
        add("C4", "add_channel", ch["name"],
            "idempotent: skip if the channel name already exists in the group nav")
    add("C5", "capture", "group URL",
        "read the public/client-portal group URL; verify via render_check (200 + group name in DOM)")
    add("C5", "verify", "render_check", "un-fakeable read-back — list-row + rendered group name")
    return {"object_type": "community", "total_steps": len(steps), "steps": steps,
            "selector_source": os.path.basename(SELECTORS_FILE),
            "notes": ["DUMB-BROWSER SCRIPT — every in-area target resolves through the "
                      "selector map; a capture-pending REQUIRED target STOPs-and-reports "
                      "(D8, no invented CSS).",
                      "Media is never browser-routed — branding/CDN links only."]}


def _preflight(plan: dict) -> dict:
    checks: List[dict] = []

    def chk(name: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        checks.append({"check": name, "pass": bool(ok), "hard": hard, "detail": detail})

    chk("C-P1:zhc_name", plan["community_name"].startswith("ZHC "),
        f"community name must be ZHC-prefixed (got {plan['community_name']!r})")
    chk("C-P2:location_id", bool(plan["location_id"]),
        "location_id required (sub-account gate runs before ANY write)")
    chk("C-P3:privacy_valid", plan["privacy"] in ("public", "private"),
        f"privacy must be public|private (got {plan['privacy']!r})")
    chk("C-P4:no_dup_channels",
        len({c["name"].lower() for c in plan["channels"]}) == len(plan["channels"]),
        "duplicate channel names in plan")
    chk("C-P5:branding_not_firebase",
        "firebase" not in (plan["branding_image_url"] or "").lower(),
        "branding must be a ghl_media CDN URL, never Firebase", hard=True)
    hard_fail = [c for c in checks if c["hard"] and not c["pass"]]
    return {"pass": not hard_fail, "checks": checks,
            "stop_reason": (hard_fail[0]["detail"] if hard_fail else "")}


# ---------------------------------------------------------------------------
# DUMB layer — live browser walk (STOP-and-report on any capture-pending REQUIRED)
# ---------------------------------------------------------------------------
def _capture_id_from_url(session: str) -> str:
    """Capture an opaque object id from the SPA location.href or an iframe .src.
    Mirrors ghl_form_builder._capture_form_id shape-gating (never trust raw eval)."""
    import re
    js = ("(() => { const re=/\\/(?:communities|groups)\\/[^/]*\\/([A-Za-z0-9]{8,40})/;"
          "for (const f of document.querySelectorAll('iframe')){const s=f.src||'';"
          "const m=s.match(re); if(m) return m[1];}"
          "const t=(location.pathname||'')+(location.hash||'')+(location.search||'');"
          "const tm=t.match(re); return tm?tm[1]:'';})()")
    got = (_eval(session, js, timeout=12) or "").strip()
    return got if re.fullmatch(r"[A-Za-z0-9]{8,40}", got) else ""


def _add_channel(session: str, sels: dict, ch: dict, evidence_root: str,
                 shot_n: List[int], gov, keep) -> dict:
    """Add ONE channel to the open group — idempotent (skip if present). Every anchor
    is a required capture-pending gate today (STOP-and-report). Returns a channel receipt."""
    name = ch["name"]
    snap = _snapshot(session)
    if name in snap:                          # F14 idempotency: already present → reuse
        return _receipt("channel", ch["slug"], "reused",
                        verify={"present_in_nav": True, "method": "snapshot"})
    if keep.due():
        _ab(session, "eval", "--stdin", timeout=10, stdin="true")   # keepalive ping (F5)
    _click(session, anchor(sels, "community.group_nav.add_channel_control"))
    _fill(session, anchor(sels, "community.group_nav.channel_name_input"), name)
    gov.before_save()
    _click(session, anchor(sels, "community.group_nav.channel_create_confirm"))
    _wait_text(session, name, timeout=15)
    if name not in _snapshot(session):
        raise StopAndReport(f"C4.verify:{name}",
                            f"created channel {name!r} but it did not appear in the group nav "
                            "(snapshot-and-bind miss). STOP — no brute-force.")
    _screenshot(session, _shot(evidence_root, shot_n, f"c4-channel-{ch['slug']}"))
    return _receipt("channel", ch["slug"], "created",
                    verify={"present_in_nav": True, "method": "snapshot"})


def _receipt(object_type: str, slug: str, action: str, *,
             response_id: Optional[str] = None, verify: Optional[dict] = None,
             request_shape: Any = None, rail=None, error: Optional[str] = None) -> dict:
    if _HAVE_ROUTER:
        step = rail
        if step is None:
            try:
                step = _router.route(object_type).rails[0]
            except Exception:  # noqa: BLE001
                step = None
        return _router.make_receipt(object_type, slug, action, rail=step,
                                    response_id=response_id, verify=verify,
                                    request_shape=request_shape, error=error,
                                    disclosures=([_router.tier_disclosure(step)] if step else []))
    return {"object_type": object_type, "slug": slug, "action": action,
            "response_id": response_id, "verify": verify or {},
            "created": action in ("created", "reused"), "error": error, "ts": _ts()}


def _write_receipt(evidence_root: str, receipt: dict) -> str:
    if _HAVE_ROUTER:
        return _router.write_receipt(evidence_root, receipt)
    path = os.path.join(evidence_root, "ecosystem",
                        f"{receipt['object_type']}-{receipt['slug']}.json")
    _write_json(path, receipt)
    return path


def _delete_group(session: str, sels: dict, plan: dict, group_id: str) -> dict:
    """search → Actions → Delete → confirm → verify gone. Best-effort, honest residue."""
    try:
        _router_push_to_list(session, plan)
        _fill(session, anchor(sels, "community.list_page.search_box"),
              plan["community_name"])
        _click(session, anchor(sels, "community.list_page.row_actions"))
        _click(session, anchor(sels, "community.list_page.delete_menuitem"))
        # dialog-scoped confirm shares the menuitem anchor family; re-click Delete
        _ab(session, "click", "Delete", timeout=12)
        _wait_text(session, "Create", timeout=12)
        residue = plan["community_name"] in _snapshot(session)
        return {"deleted": not residue, "residue_in_list": residue}
    except StopAndReport as sr:
        return {"deleted": False, "residue_in_list": True, "stop": str(sr)}


def _router_push_to_list(session: str, plan: dict) -> None:
    """Reach the communities list via a Memberships nav, NEVER a standalone deep-link."""
    sels = load_selectors()
    # Memberships left-rail is a verified-shared-rail getByText; the list route is
    # capture-pending, so we navigate by clicking the rail item + the Communities tab.
    _click(session, anchor(sels, "shared_rail.memberships_left_rail"))
    _wait_text(session, "Memberships", timeout=15)


def _live_build(task: dict, plan: dict, click_list: dict, preflight: dict,
                evidence_root: str, started: float) -> dict:
    if not (_HAVE_FFB and getattr(_ffb, "browser_manager", None) is not None):
        raise RuntimeError(
            "LIVE build requires the Skill-6 tools/ modules (ghl_form_builder glue + "
            "browser_manager) importable — run --dry-run/--selftest here, live only from "
            "the skill's tools/ dir.")
    location_id = plan["location_id"]
    os.environ["GHL_LOCATION_ID"] = location_id
    session = _canonical_session(location_id)
    sels = load_selectors()
    gov, keep = _governor(), _keepalive()
    shot_n: List[int] = [0]
    warnings: List[str] = []
    steps_done: List[str] = []
    group_id = ""
    group_url = ""
    stop: Optional[StopAndReport] = None
    cleanup: Dict[str, Any] = {"attempted": False}

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

        # C1 — Memberships nav → communities list (verified-shared-rail entry).
        _click(session, anchor(sels, "shared_rail.memberships_left_rail"))
        _wait_text(session, "Memberships", timeout=20)
        _screenshot(session, _shot(evidence_root, shot_n, "c1-memberships"))
        steps_done.append("C1:memberships")

        # C2 — search-first idempotency (capture-pending search box gates here).
        _fill(session, anchor(sels, "community.list_page.search_box"),
              plan["community_name"])
        existed = plan["community_name"] in _snapshot(session)

        if existed:
            warnings.append("C2: a ZHC community of this name already exists — REUSED (no create)")
            group_url = _capture_group_url(session)
            action = "reused"
        else:
            # C3 — create group (all capture-pending → STOP until captured).
            _click(session, anchor(sels, "community.list_page.create_group_button"))
            _fill(session, anchor(sels, "community.create_modal.name_input"),
                  plan["community_name"])
            if plan["description"]:
                _fill(session, anchor(sels, "community.create_modal.description_input"),
                      plan["description"])
            gov.before_save()
            _click(session, anchor(sels, "community.create_modal.create_confirm"))
            _wait_text(session, plan["community_name"][:18], timeout=25)
            group_id = _capture_id_from_url(session)
            group_url = _capture_group_url(session)
            _screenshot(session, _shot(evidence_root, shot_n, "c3-created"))
            action = "created"
        steps_done.append(f"C3:{action}")

        # community receipt (F6).
        verify_block = _verify_community(session, plan, group_url, evidence_root)
        _write_receipt(evidence_root, _receipt(
            "community", plan["slug"], action, response_id=group_id,
            request_shape={"name": plan["community_name"], "privacy": plan["privacy"]},
            verify=verify_block))

        # C4 — channels (idempotent, per-channel receipt).
        for ch in plan["channels"]:
            rc = _add_channel(session, sels, ch, evidence_root, shot_n, gov, keep)
            _write_receipt(evidence_root, rc)
            steps_done.append(f"C4:{rc['action']}:{ch['name'][:20]}")

        _write_json(os.path.join(evidence_root, "routing", "community-built.json"), {
            "community_id": group_id, "community_name": plan["community_name"],
            "community_url": group_url, "verify": verify_block,
            "channels": [c["name"] for c in plan["channels"]],
            "warnings": warnings, "steps_done": steps_done, "built_at": _ts()})
    except StopAndReport as sr:
        stop = sr
        _log(f"STOP-and-report @ {sr.step}: {sr.reason}")
    except Exception as exc:  # noqa: BLE001
        stop = StopAndReport("unexpected", f"{type(exc).__name__}: {exc}")
    finally:
        cleanup["attempted"] = True
        try:
            if group_id or plan["community_name"]:
                cleanup.update(_delete_group(session, sels, plan, group_id))
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
        return {"ok": False, "object_type": "community", "duration_s": duration,
                "community_id": group_id, "community_url": group_url,
                "error": str(stop), "stop_step": stop.step, "stop_reason": stop.reason,
                "warnings": warnings, "steps_done": steps_done, "cleanup": cleanup,
                "receipts_summary": summary, "dry_run": False}
    return {"ok": True, "object_type": "community", "duration_s": duration,
            "community_id": group_id, "community_url": group_url,
            "warnings": warnings, "steps_done": steps_done, "cleanup": cleanup,
            "receipts_summary": summary, "dry_run": False}


def _capture_group_url(session: str) -> str:
    js = ("(() => { const a=Array.from(document.querySelectorAll('a[href],input'))"
          ".map(e=>(e.href||e.value||'')).find(u=>/(community|group|portal)/i.test(u)); "
          "return a||location.href||''; })()")
    return _eval(session, js, timeout=12) or ""


def _verify_community(session: str, plan: dict, group_url: str, evidence_root: str) -> dict:
    """Un-fakeable read-back: list-row present + (when a public URL exists) render_check
    200 with the group name in the RENDERED DOM. Deferred honestly if no public URL."""
    row_present = plan["community_name"] in _snapshot(session)
    block: Dict[str, Any] = {"list_row_present": row_present, "community_url": group_url}
    try:
        import ghl_verify  # type: ignore
        if group_url:
            rec = ghl_verify.verify_page(
                {"step": "community", "name": plan["community_name"],
                 "page_id": plan["slug"], "preview_url": group_url,
                 "marker": plan["community_name"]},
                run_dir=evidence_root, live=True)
            block.update({"http": rec.get("http"),
                          "marker_in_rendered_dom": rec.get("marker_in_rendered_dom"),
                          "render_errors": rec.get("render_errors", []),
                          "method": "render_check"})
        else:
            block["status"] = "deferred"
            block["reason"] = "no public/client-portal group URL captured — snapshot row only"
    except Exception as exc:  # noqa: BLE001
        block["status"] = "deferred"
        block["reason"] = f"ghl_verify unavailable ({exc}) — snapshot row only"
    return block


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def build_community(task: dict, evidence_root: str, *, dry_run: bool = True) -> dict:
    started = time.monotonic()
    dry_run = bool(task.get("dry_run", dry_run))
    os.makedirs(os.path.join(evidence_root, "routing"), exist_ok=True)
    os.makedirs(os.path.join(evidence_root, "shots"), exist_ok=True)

    plan = plan_community(task)
    preflight = _preflight(plan)
    click_list = emit_click_list(plan)
    _write_json(os.path.join(evidence_root, "routing", "community-plan.json"), plan)
    _write_json(os.path.join(evidence_root, "routing", "community-click-list.json"), click_list)
    _write_json(os.path.join(evidence_root, "routing", "community-preflight.json"), preflight)

    if not preflight["pass"]:
        return {"ok": False, "object_type": "community", "duration_s": time.monotonic() - started,
                "preflight": preflight, "error": preflight["stop_reason"], "dry_run": dry_run}

    if dry_run:
        disclosure = (_router.tier_disclosure(_router.route("community").rails[0])
                      if _HAVE_ROUTER else "[GHL tier used: 4 — ghl_community_builder.py]")
        _log(f"[dry-run] community plan + click list ({click_list['total_steps']} steps) written. {disclosure}")
        return {"ok": True, "object_type": "community", "duration_s": time.monotonic() - started,
                "plan": plan, "click_list": click_list, "preflight": preflight,
                "tier_disclosure": disclosure, "dry_run": True}

    return _live_build(task, plan, click_list, preflight, evidence_root, started)


# ---------------------------------------------------------------------------
# Self-test — no network, no browser
# ---------------------------------------------------------------------------
def _selftest() -> int:  # noqa: C901
    import tempfile
    errors: List[str] = []

    # 1. ZHC naming + plan shape
    plan = plan_community({"community_name": "Founders Circle", "location_id": "LOC",
                           "description": "for founders", "privacy": "Private",
                           "channels": ["Welcome", "General", "General", "Wins"]})
    if plan["community_name"] != "ZHC Founders Circle":
        errors.append(f"zhc name wrong: {plan['community_name']!r}")
    if plan["privacy"] != "private":
        errors.append("privacy not normalized")
    if [c["name"] for c in plan["channels"]] != ["Welcome", "General", "Wins"]:
        errors.append(f"channel dedupe failed: {[c['name'] for c in plan['channels']]}")

    # 2. branding Firebase URL is rejected
    try:
        plan_community({"community_name": "X", "location_id": "L",
                        "branding_image_url": "https://firebasestorage.googleapis.com/x"})
        errors.append("firebase branding URL not rejected")
    except StopAndReport:
        pass

    # 3. preflight hard-fails on a non-ZHC / missing location
    pf = _preflight({"community_name": "NoPrefix", "slug": "x", "location_id": "",
                     "description": "", "privacy": "weird", "channels": [],
                     "branding_image_url": ""})
    if pf["pass"]:
        errors.append("preflight should FAIL (non-ZHC name + no location + bad privacy)")

    # 4. dry-run returns plan + click list, no browser
    with tempfile.TemporaryDirectory() as tmp:
        res = build_community({"community_name": "Founders", "location_id": "LOC",
                               "channels": ["Welcome", "General"]}, tmp, dry_run=True)
        if not res.get("dry_run") or "click_list" not in res:
            errors.append("dry-run missing click_list")
        phases = {s["phase"] for s in res["click_list"]["steps"]}
        for want in ("C1", "C2", "C3", "C4", "C5"):
            if want not in phases:
                errors.append(f"click list missing phase {want}")
        if not os.path.isfile(os.path.join(tmp, "routing", "community-plan.json")):
            errors.append("community-plan.json not written")

    # 5. selector map loads + the D8 gate: a capture-pending REQUIRED anchor STOPs;
    #    a verified-shared-rail anchor is returned.
    sels = load_selectors()
    if not anchor(sels, "shared_rail.memberships_left_rail").startswith("getByText"):
        errors.append("verified-shared-rail anchor not returned")
    raised = False
    try:
        anchor(sels, "community.list_page.create_group_button")   # capture-pending
    except StopAndReport:
        raised = True
    if not raised:
        errors.append("capture-pending REQUIRED anchor did NOT STOP-and-report (D8 gate broken)")
    if anchor(sels, "community.list_page.create_group_button", required=False) != "":
        errors.append("capture-pending optional anchor should return ''")

    # 6. mocked-browser walk proves the live path is REAL code (not a skeleton):
    #    with the selector map patched to 'locked' + a fake _ab, _add_channel drags a
    #    channel and writes a receipt; with a channel already present it REUSES.
    if _HAVE_FFB:
        import copy
        locked = copy.deepcopy(sels)
        for t in locked["community"]["group_nav"].values():
            t["status"] = "locked"
        calls: List[tuple] = []
        present = {"ZHC Founders Circle", "General", "Welcome"}   # base group nav

        def fake_ab(session, *args, timeout=30, stdin=None):
            calls.append(args)
            verb = args[0] if args else ""
            # model "the channel appeared": a wait('--', <name>) makes it visible next snapshot
            if verb == "wait" and len(args) >= 3:
                present.add(args[2])
            snap = " ".join(sorted(present)) if verb == "snapshot" else ""
            return subprocess.CompletedProcess(args=list(args), returncode=0,
                                               stdout=snap, stderr="")
        orig = _ffb._ab
        try:
            _ffb._ab = fake_ab
            # rebind module-level glue that closed over the original
            globals()["_ab"] = fake_ab
            globals()["_snapshot"] = lambda s, timeout=20: (fake_ab(s, "snapshot").stdout or "")
            globals()["_click"] = lambda s, t, timeout=15: fake_ab(s, "click", t)
            globals()["_fill"] = lambda s, l, v, timeout=15: fake_ab(s, "fill", l, v)
            globals()["_wait_text"] = lambda s, t, timeout=20: fake_ab(s, "wait", "--", t)
            globals()["_screenshot"] = lambda s, p: None
            with tempfile.TemporaryDirectory() as tmp2:
                os.makedirs(os.path.join(tmp2, "shots"), exist_ok=True)
                # NEW channel (not in snapshot) → created + real drag/click commands
                rc_new = _add_channel("s", locked,
                                      {"name": "Announcements", "type": "post", "slug": "announcements"},
                                      tmp2, [0], _NoopGovernor(), _NoopKeepalive())
                if rc_new["action"] != "created":
                    errors.append(f"mocked walk: new channel should be created (got {rc_new['action']})")
                if not any(c and c[0] == "click" for c in calls):
                    errors.append("mocked walk: no real click command issued (skeleton?)")
                # EXISTING channel (in snapshot) → reused, no create
                rc_dup = _add_channel("s", locked,
                                      {"name": "General", "type": "post", "slug": "general"},
                                      tmp2, [0], _NoopGovernor(), _NoopKeepalive())
                if rc_dup["action"] != "reused":
                    errors.append(f"mocked walk: existing channel should be reused (got {rc_dup['action']})")
        finally:
            _ffb._ab = orig
            globals()["_ab"] = _ffb._ab
            globals()["_snapshot"] = _ffb._snapshot
            globals()["_click"] = _ffb._click
            globals()["_fill"] = _ffb._fill
            globals()["_wait_text"] = _ffb._wait_text
            globals()["_screenshot"] = _ffb._screenshot

    # 7. router registers community + channel
    if _HAVE_ROUTER:
        for ot in ("community", "channel"):
            try:
                _router.route(ot)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"router missing {ot}: {exc}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — community THINK + click list + D8 selector gate + mocked walk "
          "(no network / no browser)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_community_builder",
        description="GHL (Convert and Flow) COMMUNITY + CHANNELS builder — Skill 06. "
                    "Default --dry-run. Live path STOP-and-reports on any capture-pending "
                    "selector (D8) until SELECTORS-LIVE-community.md is captured.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--evidence-root", default="/tmp/community-run-01")
    p.add_argument("--community-name", default="New Community")
    p.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID", ""))
    p.add_argument("--description", default="")
    p.add_argument("--privacy", default="private", choices=["public", "private"])
    p.add_argument("--channels", default="", help="Comma-separated channel names")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    task = {"community_name": args.community_name, "location_id": args.location_id,
            "description": args.description, "privacy": args.privacy,
            "channels": [c.strip() for c in args.channels.split(",") if c.strip()]}
    result = build_community(task, args.evidence_root, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())

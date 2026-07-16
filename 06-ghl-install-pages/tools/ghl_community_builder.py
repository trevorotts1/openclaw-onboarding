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

# U8/U10 — shared phase-checkpoint store + the uniform RUN REPORT emitter.
# It ships in THIS dir; bootstrap the path so an import from any cwd resolves it.
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_run_state  # noqa: E402
from ghl_run_state import PhaseSpec, run_phase  # noqa: E402

# ── U8: the community builder's declared phase walk ─────────────────────────────
# resumable=False: gates + pure THINK output + the navigation that walks back in.
COMMUNITY_PHASES: List[PhaseSpec] = [
    PhaseSpec("plan",         "community plan (THINK)",   resumable=False),
    PhaseSpec("preflight",    "preflight gate",           resumable=False),
    PhaseSpec("click_list",   "click list",               resumable=False),
    PhaseSpec("c1_list",      "C1 — communities list",    resumable=False),
    PhaseSpec("c3_create",    "C2/C3 — create/reuse group"),
    PhaseSpec("c4_channels",  "C4 — channels"),
]

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

# ── agent-browser 0.27.0 anchor→executor resolver (fix a) ─────────────────────
# Playwright-style anchors (getByRole/getByText/getByPlaceholder) are REJECTED by
# agent-browser 0.27.0 `click`/`fill`. This adapter translates them into the accepted
# `find <locator> <value> <action> [--name]` calls (+ native eval .click() for Naive-UI
# submits). Every in-area click/fill routes through it. See ghl_ab_executor.py.
import ghl_ab_executor as _abx  # type: ignore

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
# agent-browser 0.27.0 executor wrappers (fix a) — SHARED by both builders
# ---------------------------------------------------------------------------
# These reference the module globals `_ab`/`_eval` at CALL time (late binding), so a
# test that monkeypatches `_cb._ab`/`_cb._eval` is honored. The course builder imports
# `_ex_click`/`_ex_fill`/`_ex_wait_text` from here so both drivers share ONE adapter.
def _exec():
    return _abx.AbExecutor(ab=_ab, ev=_eval, log=_log)


def _ex_click(session: str, sels: dict, dotted: str, *, native: Optional[bool] = None,
              required: bool = True, timeout: int = 15) -> dict:
    """Resolve a Playwright anchor (D8 gate) and click via the 0.27.0 executor. `native`
    forces the eval .click() path (Naive-UI submits); None reads the node's `exec` hint.
    Raises StopAndReport if the executor cannot resolve+click (never brute-forces)."""
    a = anchor(sels, dotted, required=required)
    if not a:
        return {"ok": False, "path": "skipped", "reason": "optional capture-pending"}
    node = _target(sels, dotted)
    if native is None:
        native = node.get("exec") == "native"
    res = _exec().click(session, a, kind=node.get("kind", ""),
                        mode=("native" if native else "auto"), timeout=timeout)
    if not res.get("ok"):
        raise StopAndReport(
            f"click:{dotted}",
            f"agent-browser 0.27.0 could not resolve+click {a!r} "
            f"(path={res.get('path')}, detail={res.get('detail')}). STOP — no brute-force.")
    return res


def _ex_fill(session: str, sels: dict, dotted: str, value: str, *,
             required: bool = True, timeout: int = 15) -> dict:
    a = anchor(sels, dotted, required=required)
    if not a:
        return {"ok": False, "path": "skipped", "reason": "optional capture-pending"}
    node = _target(sels, dotted)
    res = _exec().fill(session, a, value, kind=node.get("kind", ""), timeout=timeout)
    if not res.get("ok"):
        raise StopAndReport(
            f"fill:{dotted}",
            f"agent-browser 0.27.0 could not resolve+fill {a!r} (path={res.get('path')}). STOP.")
    return res


def _ex_wait_text(session: str, text: str, *, timeout: int = 20):
    """Wait for text — routed through the executor so a multi-word name is quoted as ONE
    argv token (the raw `_ab(session,'wait','--',text)` glue splits it)."""
    return _exec().wait_text(session, text, timeout=timeout)


# ---------------------------------------------------------------------------
# Phase B (2026-07-10) LIVE-verified helpers — shared by both builders.
# ---------------------------------------------------------------------------
_APP_HOST = "https://app.convertandflow.com"


def _reactive_fill(session: str, placeholder: str, value: str, timeout: int = 12) -> bool:
    """Set an input/textarea value + dispatch input/change so a Naive-UI (Vue) field BINDS.
    Phase B live: some GHL fields (course lesson title, the delete type-to-proceed box)
    accept a plain `fill` visually but do NOT bind to Vue's model, leaving the submit
    DISABLED. This forces the reactive bind. Matches by placeholder (exact, then contains)."""
    js = (
        "(() => { const want=" + json.dumps(placeholder) + "; const val=" + json.dumps(value) + ";"
        " const norm=s=>(s||'').replace(/\\s+/g,' ').trim();"
        " const all=Array.from(document.querySelectorAll('input,textarea'));"
        " let el=all.find(e=>norm(e.placeholder)===want)||all.find(e=>norm(e.placeholder).includes(want));"
        " if(!el) return 'NOTFOUND'; el.focus();"
        " const proto = el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;"
        " const setter=Object.getOwnPropertyDescriptor(proto,'value'); setter.set.call(el,val);"
        " el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true}));"
        " return 'FILLED'; })()")
    res = (_eval(session, js, timeout=timeout) or "").strip()
    return bool(res) and "NOTFOUND" not in res


def _nav_to_list(session: str, location_id: str, sels: dict, dotted_route: str,
                 expect_text: str) -> None:
    """C1/M1 nav (Phase B): the Memberships left-rail text is a non-navigating SPAN on some
    accounts, so reach the LIST by navigating its route directly (proven: the LIST route
    loads reliably; only the builder/editor route spins). Substitutes <LOCATION_ID>."""
    route = anchor(sels, dotted_route)                       # locked route template
    path = route.replace("<LOCATION_ID>", location_id)
    url = path if path.startswith("http") else f"{_APP_HOST}{path}"
    _ab(session, "navigate", url, timeout=45)
    _ex_wait_text(session, expect_text, timeout=25)


def _scoped_status_dropdown(session: str, name: str) -> bool:
    """Deactivate (fix d, card-scoped): click the group's OWN list-card Status 'Active'
    dropdown so a global first-match can never hit a REAL group. Phase B live."""
    js = (
        "(() => { const want=" + json.dumps(name) + "; const norm=s=>(s||'').replace(/\\s+/g,' ').trim();"
        " let el=[...document.querySelectorAll('*')].find(e=>norm(e.textContent)===want && e.children.length===0);"
        " if(!el) return 'NO_CARD'; let card=el;"
        " for(let i=0;i<8&&card.parentElement;i++){card=card.parentElement;"
        "   if(/Members/.test(card.textContent)&&/Status/.test(card.textContent)) break;}"
        " const cand=[...card.querySelectorAll('*')].filter(e=>norm(e.textContent)==='Active' && e.children.length<=1);"
        " const t=cand[cand.length-1]; if(!t) return 'NO_CTL'; t.click(); return 'OK'; })()")
    return (_eval(session, js, timeout=12) or "").strip() == "OK"


def _ok_scoped(res: str, *fails: str) -> bool:
    """Success predicate for the scoped-native helpers: truthy and not a known NO_*/NOTFOUND
    marker (so a mocked _eval returning 'OK'/'CLICKED:x'/'FILLED' all count as success, while
    a real NO_CARD/NO_OPT/NOTFOUND fails)."""
    res = (res or "").strip()
    bad = {"", "NOTFOUND", "NO_CARD", "NO_CTL", "NO_KEBAB", "NO_OPT", "NO_ROW"} | set(fails)
    return bool(res) and res not in bad


def _scoped_card_kebab(session: str, name: str) -> bool:
    """Course delete (fix d): after ISOLATING the scratch course by search, click ITS OWN
    card kebab (More actions) so a real member course can NEVER be hit (card-scoped)."""
    js = (
        "(() => { const want=" + json.dumps(name) + "; const norm=s=>(s||'').replace(/\\s+/g,' ').trim();"
        " let el=[...document.querySelectorAll('*')].find(e=>norm(e.textContent)===want && e.children.length===0);"
        " if(!el) return 'NO_CARD'; let card=el;"
        " for(let i=0;i<7&&card.parentElement;i++){card=card.parentElement; if(/member/i.test(card.textContent)) break;}"
        " const btns=[...card.querySelectorAll('button,[role=button]')];"
        " let kebab=btns.find(b=>!norm(b.textContent) && b.querySelector('svg'))||btns[btns.length-1];"
        " if(!kebab) return 'NO_KEBAB'; kebab.click(); return 'OK'; })()")
    return _ok_scoped(_eval(session, js, timeout=12))


def _select_dropdown_option(session: str, label: str) -> bool:
    """Pick a Naive-UI select option by exact label via FULL mouse events (mousedown+mouseup+
    click) — a plain click does not register (Phase B: Add-Lesson 'Select Module')."""
    js = (
        "(() => { const want=" + json.dumps(label) + "; const norm=s=>(s||'').replace(/\\s+/g,' ').trim();"
        " const opts=[...document.querySelectorAll('.n-base-select-option,[role=option],[class*=select-option],div,li,span')];"
        " let el=opts.find(e=>norm(e.textContent)===want && e.children.length<=1);"
        " if(!el) return 'NO_OPT';"
        " ['mousedown','mouseup','click'].forEach(t=>el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window})));"
        " return 'OK'; })()")
    return _ok_scoped(_eval(session, js, timeout=12))


def _click_bottom_button(session: str, text: str, min_y: int = 600) -> bool:
    """Click the BOTTOM-most button whose text contains `text` (Phase B: the create wizard's
    final 'Create Course' at the page bottom vs. the same-labelled top back-nav)."""
    js = (
        "(() => { const want=" + json.dumps(text) + "; const norm=s=>(s||'').replace(/\\s+/g,' ').trim();"
        " const cands=[...document.querySelectorAll('button,[role=button]')].filter(e=>norm(e.textContent).includes(want));"
        " let pick=cands.map(e=>[e,e.getBoundingClientRect().y]).filter(p=>p[1]>" + str(min_y) + ").sort((a,b)=>b[1]-a[1])[0];"
        " if(!pick) pick=cands.map(e=>[e,e.getBoundingClientRect().y]).sort((a,b)=>b[1]-a[1])[0];"
        " if(!pick) return 'NOTFOUND'; if(pick[0].disabled) return 'DISABLED'; pick[0].click();"
        " return 'CLICKED@'+Math.round(pick[1]); })()")
    return (_eval(session, js, timeout=12) or "").strip().startswith("CLICKED")


# ---------------------------------------------------------------------------
# List-scan idempotency (fix b) — the communities list has NO search box
# ---------------------------------------------------------------------------
_LIST_SCAN_JS = (
    "(() => Array.from(document.querySelectorAll("
    "'a,[role=listitem],[role=row],[role=gridcell],h1,h2,h3,h4,h5,button,"
    "[class*=group],[class*=card],[data-testid]'))"
    ".map(e => (e.textContent || '').replace(/\\s+/g, ' ').trim())"
    ".filter(Boolean).join(' | '))()"
)


def _list_scan(session: str) -> str:
    """Enumerate the rendered list items into one text blob. Uses the a11y snapshot
    (the builder's read primitive) PLUS a light DOM text sweep — because the communities
    list has NO search box to type into (live-captured); membership is read, not typed."""
    blob = _snapshot(session) or ""
    try:
        dom = _eval(session, _LIST_SCAN_JS, timeout=12) or ""
    except Exception:  # noqa: BLE001
        dom = ""
    return blob + "\n" + dom


def _list_has(session: str, name: str, slug: str = "") -> bool:
    """Idempotency read (fix b): is a group/course named `name` (or slugged `slug`)
    already present in the rendered list? Match by name first, then slug."""
    blob = _list_scan(session)
    if name and name in blob:
        return True
    if slug and slug.lower() in blob.lower():
        return True
    return False


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
                    "description": (c.get("description") if isinstance(c, dict) else "") or "",
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
        "SPA nav after Memberships left-rail (getByText); NEVER deep-link the builder")
    add("C2", "list-scan", plan["community_name"],
        "list-scan idempotency (fix b): the communities list has NO search box — enumerate "
        "the rendered group list; if a ZHC group of this name/slug exists → REUSE, skip create")
    add("C3", "click", "Create Group",
        "list button → opens the create-group PAGE (not a modal; capture-pending anchor)")
    add("C3", "fill", "Group Name", plan["community_name"])
    add("C3", "note", f"slug={plan['slug']}",
        "slug auto-derives from the name; the SLUG is the group identity key (fix c)")
    if plan["description"]:
        add("C3", "fill", "Description", plan["description"])
    add("C3", "set", f"privacy={plan['privacy']}",
        "create-page privacy switch (default PUBLIC; set Private explicitly when needed)")
    add("C3", "native-click", "Create Group (submit)",
        "Naive-UI submit — native DOM .click() (exec:native); find/@ref click do NOT submit")
    add("C3", "capture", "group identity",
        "read location.href → slug + white-label portal host (fix c); no opaque group id exists")
    if plan["branding_image_url"]:
        add("C3", "set", "branding image (CDN URL)",
            "insert the ghl_media CDN URL — NEVER browser-upload a file")
    for ch in plan["channels"]:
        add("C4", "add_channel", ch["name"],
            "idempotent: skip if the channel name already exists in the group nav")
    add("C5", "capture", "portal URL",
        "member-visible portal URL https://<portal_host>/communities/groups/<slug>/home (fix c/e)")
    add("C5", "verify", "render_check",
        "un-fakeable read-back: PUBLIC → anonymous render_check 200 + name; PRIVATE → "
        "authenticated in-session portal DOM shows the group name (fix e)")
    add("C6", "cleanup", f"deactivate (privacy={plan['privacy']})",
        "community has NO delete (Tier 1/2 + UI both lack one) — cleanup = set Inactive (fix d); "
        "documented residue, NOT a fake delete")
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
    if _list_has(session, name):              # F14/fix-b idempotency: present → reuse
        return _receipt("channel", ch["slug"], "reused",
                        verify={"present_in_nav": True, "method": "list-scan"})
    if keep.due():
        _ab(session, "eval", "--stdin", timeout=10, stdin="true")   # keepalive ping (F5)
    _ex_click(session, sels, "community.group_nav.add_channel_control")
    _ex_fill(session, sels, "community.group_nav.channel_name_input", name)
    if ch.get("description"):
        _ex_fill(session, sels, "community.group_nav.channel_description_input",
                 ch["description"], required=False)
    gov.before_save()
    _ex_click(session, sels, "community.group_nav.channel_create_confirm")   # exec:native
    _ex_wait_text(session, name, timeout=15)
    if not _list_has(session, name):
        raise StopAndReport(f"C4.verify:{name}",
                            f"created channel {name!r} but it did not appear in the group nav "
                            "(snapshot-and-bind miss). STOP — no brute-force.")
    _screenshot(session, _shot(evidence_root, shot_n, f"c4-channel-{ch['slug']}"))
    return _receipt("channel", ch["slug"], "created",
                    verify={"present_in_nav": True, "method": "list-scan"})


def _build_channels(session: str, sels: dict, plan: dict, evidence_root: str,
                    shot_n: List[int], gov, keep, *,
                    add_channel=None, write_receipt=None, log=None) -> dict:
    """U106 — smoke-first gated channel bulk-add (companion to U30's smoke_first
    on the iframe/page-code drag surfaces). The FIRST channel in the plan is
    the ONE proof-create (ghl_run_state.smoke_first): only a PASSING
    store-delta verify (the channel actually present in the group nav) unlocks
    the rest of the — potentially long — channel walk. A failing smoke raises
    SmokeFirstFailed BEFORE any further channel is attempted; the shipped drag
    doctrine applies here too — a CLI '✓ Done' that created nothing is a FALSE
    PASS, the snapshot/store delta is the only honest arbiter.

    `add_channel`/`write_receipt`/`log` are dependency-injected (default: the
    real `_add_channel` / `_write_receipt` / `_log`) so this is directly
    unit-testable without a live browser."""
    _add = add_channel or _add_channel
    _wr = write_receipt or _write_receipt
    _lg = log or _log
    steps_done: List[str] = []
    channels = plan["channels"]
    if not channels:
        return {"channels": 0, "steps_done": steps_done}

    first, rest = channels[0], channels[1:]

    def _create_first() -> dict:
        return _add(session, sels, first, evidence_root, shot_n, gov, keep)

    def _verify_first(rc: dict) -> dict:
        return {"ok": bool((rc.get("verify") or {}).get("present_in_nav")), "receipt": rc}

    first_rc = ghl_run_state.smoke_first(f"C4:smoke:{first['slug']}", _create_first,
                                         _verify_first, log=_lg)
    _wr(evidence_root, first_rc)
    steps_done.append(f"C4:{first_rc['action']}:{first['name'][:20]}")

    for ch in rest:
        rc = _add(session, sels, ch, evidence_root, shot_n, gov, keep)
        _wr(evidence_root, rc)
        steps_done.append(f"C4:{rc['action']}:{ch['name'][:20]}")
    return {"channels": len(channels), "steps_done": steps_done}


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


def _deactivate_group(session: str, sels: dict, plan: dict, identity: dict,
                      location_id: str = "") -> dict:
    """Cleanup for a community GROUP (fix d) — HONEST: GHL has NO group delete.

    PHASE B LIVE-verified flow (card-scoped so a global first-match can NEVER hit a REAL
    group on a populated account): navigate the communities list -> click the group's OWN
    card Status 'Active' dropdown -> click the 'inactive' option -> Confirm the 'Deactivate
    Group' dialog. There is NO delete on any known rail (UI has only Active<->Inactive; the
    toggle lives on the APP list card, NOT in the portal group Settings dialog; Tier-1/2
    have no delete_*). Literal 0-residue is IMPOSSIBLE for a group; the group ROW/portal
    REMAINS as documented residue. NOT a fake delete — the true 0-residue proof is COURSES."""
    name = plan.get("community_name") or plan.get("slug", "")
    result: Dict[str, Any] = {
        "cleanup_primitive": "inactivate",
        "deleted": False,
        "inactivated": False,
        "slug": identity.get("slug", plan.get("slug", "")),
        "residue": "group remains (GHL has no group delete on any known rail); set Inactive",
    }
    try:
        if location_id:
            _nav_to_list(session, location_id, sels,
                         "community.routes.communities_list", "Create Group")
        if not _scoped_status_dropdown(session, name):
            raise StopAndReport("C6.status",
                                "could not open the group's OWN card Status dropdown "
                                "(card-scoped deactivate) — group left Active (residue).")
        _ex_click(session, sels, "community.deactivate.inactive_option")     # 'inactive'
        _ex_click(session, sels, "community.deactivate.confirm")             # Deactivate dialog
        _ex_wait_text(session, "Deactivated", timeout=12)
        result["inactivated"] = True
    except StopAndReport as sr:
        result["stop"] = str(sr)
        result["residue"] += f" (deactivate STOP — {sr.reason[:80]})"
    return result


def _live_build(task: dict, plan: dict, click_list: dict, preflight: dict,
                evidence_root: str, started: float,
                state: Optional["ghl_run_state.RunState"] = None) -> dict:
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
    action = ""
    identity: Dict[str, Any] = {}
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

        # C1 — reach the communities LIST by navigating its route directly (Phase B:
        # the Memberships left-rail text is a non-navigating SPAN on some accounts).
        # NON-RESUMABLE: this is the navigation that walks back in.
        def _do_c1() -> dict:
            _nav_to_list(session, location_id, sels,
                         "community.routes.communities_list", "Create Group")
            _screenshot(session, _shot(evidence_root, shot_n, "c1-communities-list"))
            steps_done.append("C1:communities-list")
            return {"landed": "communities-list"}

        run_phase(state, "c1_list", _do_c1, log=_log)

        # C2/C3 — create or REUSE. Already idempotent (list-scan), so a resume that
        # re-enters here reuses rather than duplicating; the checkpoint just spares
        # the walk from paying for it twice.
        def _do_c3() -> dict:
            # C2 — LIST-SCAN idempotency (fix b): the communities list has NO search box.
            existed = _list_has(session, plan["community_name"], plan["slug"])
            if existed:
                warnings.append("C2: a ZHC community of this name/slug already exists — "
                                "REUSED (no create)")
                ident = _capture_group_identity(session, plan)
                act = "reused"
            else:
                # C3 — create group on the create PAGE (all capture-pending → STOP until captured).
                _ex_click(session, sels, "community.list_page.create_group_button")
                _ex_fill(session, sels, "community.create_page.name_input", plan["community_name"])
                if plan["description"]:
                    _ex_fill(session, sels, "community.create_page.description_input",
                             plan["description"], required=False)
                if plan["privacy"] == "private":
                    _ex_click(session, sels, "community.create_page.privacy_switch", required=False)
                gov.before_save()
                _ex_click(session, sels, "community.create_page.create_confirm")   # exec:native submit
                _ex_wait_text(session, plan["community_name"][:18], timeout=25)
                ident = _capture_group_identity(session, plan)          # fix c: slug + portal host
                _screenshot(session, _shot(evidence_root, shot_n, "c3-created"))
                act = "created"
            steps_done.append(f"C3:{act}")

            # community receipt (F6).
            vb = _verify_community(session, plan, ident, evidence_root)   # fix e
            _write_receipt(evidence_root, _receipt(
                "community", plan["slug"], act, response_id=ident.get("slug", ""),
                request_shape={"name": plan["community_name"], "privacy": plan["privacy"],
                               "slug": ident.get("slug"),
                               "portal_host": ident.get("portal_host")},
                verify=vb))
            return {"identity": ident, "action": act, "verify": vb}

        c3 = run_phase(state, "c3_create", _do_c3, log=_log) or {}
        identity = c3.get("identity", {}) or {}
        action = c3.get("action", "")
        verify_block = c3.get("verify", {}) or {}
        group_id = identity.get("slug", "")            # groups are keyed by SLUG (fix c)
        group_url = identity.get("portal_url", "")

        # C4 — channels (idempotent, per-channel receipt). U106: smoke-first
        # gated — see _build_channels().
        def _do_c4() -> dict:
            res = _build_channels(session, sels, plan, evidence_root, shot_n, gov, keep)
            steps_done.extend(res["steps_done"])
            return {"channels": res["channels"]}

        run_phase(state, "c4_channels", _do_c4, log=_log)

        _write_json(os.path.join(evidence_root, "routing", "community-built.json"), {
            "community_id": group_id, "community_slug": identity.get("slug", ""),
            "community_name": plan["community_name"], "community_url": group_url,
            "portal_host": identity.get("portal_host", ""), "verify": verify_block,
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
            # Only touch a scratch group we CREATED (never deactivate a reused/existing
            # group; a STOP-and-report before create means nothing was made — no-op).
            if action == "created" and identity.get("slug"):
                cleanup.update(_deactivate_group(session, sels, plan, identity, location_id))   # fix d
            else:
                cleanup["deleted"] = True
                cleanup["note"] = ("nothing to clean — no scratch group created "
                                   "(reused, or STOP-and-report before create)")
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


# ── group identity (fix c) — slug + white-label portal host, not an opaque id ──
_GROUP_IDENTITY_JS = (
    "(() => {"
    "  const RE = /\\/communities\\/groups\\/([^/?#]+)/;"
    "  let host = location.host || '';"
    "  let slug = '';"
    "  const hay = (location.pathname || '') + (location.hash || '');"
    "  let m = hay.match(RE);"
    "  if (m) { slug = m[1]; } else {"
    "    for (const f of document.querySelectorAll('iframe')) {"
    "      const s = f.src || ''; const mm = s.match(RE);"
    "      if (mm) { slug = mm[1]; try { host = new URL(s).host; } catch (e) {} break; }"
    "    }"
    "  }"
    "  return JSON.stringify({ url: location.href || '', host: host, slug: slug });"
    "})()"
)


def _capture_group_identity(session: str, plan: dict) -> dict:
    """Fix (c): group identity = SLUG + white-label portal host (NOT an opaque id). Live
    capture proved groups are keyed by SLUG and the post-create URL is
    ``https://<portal_host>/communities/groups/<slug>/home`` — there is NO opaque group id
    in the route; the Tier-2 `validate_group_slug` tool independently confirms slug keying.
    Returns {slug, portal_host, portal_url}; falls back to the planned slug on any miss."""
    raw = _eval(session, _GROUP_IDENTITY_JS, timeout=12) or ""
    data: Dict[str, Any] = {}
    try:
        if raw.strip().startswith("{"):
            data = json.loads(raw)
    except Exception:  # noqa: BLE001
        data = {}
    slug = (data.get("slug") or "").strip() or plan["slug"]
    host = (data.get("host") or "").strip()
    url = (data.get("url") or "").strip()
    is_app_host = any(h in host for h in ("convertandflow.com", "leadconnector", "gohighlevel"))
    portal_url = url
    if host and slug and not is_app_host:
        portal_url = f"https://{host}/communities/groups/{slug}/home"
    return {"slug": slug, "portal_host": ("" if is_app_host else host), "portal_url": portal_url}


# ── render-check on the RIGHT url (fix e) — public anon vs private authenticated ──
_AUTH_PORTAL_CHECK_JS_TMPL = (
    "(() => {"
    "  const want = %s;"
    "  const t = (document.body ? (document.body.innerText || '') : '');"
    "  return JSON.stringify({"
    "    ready: document.readyState === 'complete',"
    "    has: t.indexOf(want) !== -1,"
    "    url: location.href || ''"
    "  });"
    "})()"
)


def _authenticated_portal_check(session: str, name: str) -> dict:
    """Fix (e): a PRIVATE group's portal requires login, so an anonymous render_check
    can't return 200 + name. Verify in the ALREADY-authenticated seeded session — the
    member-visible portal (we landed on it after Create) shows the group name."""
    raw = _eval(session, _AUTH_PORTAL_CHECK_JS_TMPL % json.dumps(name), timeout=12) or ""
    d: Dict[str, Any] = {}
    try:
        if raw.strip().startswith("{"):
            d = json.loads(raw)
    except Exception:  # noqa: BLE001
        d = {}
    has = bool(d.get("has"))
    return {"http": 200 if (has and d.get("ready")) else None,
            "marker_in_rendered_dom": has, "render_errors": [],
            "render_method": "authenticated_in_session", "current_url": d.get("url", "")}


def _verify_community(session: str, plan: dict, identity: dict, evidence_root: str) -> dict:
    """Un-fakeable read-back (fix e). PUBLIC group → anonymous `render_check` on the
    derived member-visible portal URL (200 + name in RENDERED DOM). PRIVATE group →
    authenticated in-session portal check (an anonymous fetch would hit the login wall).
    Always records which URL + mode was used; deferred cleanly when no portal URL exists."""
    portal_url = identity.get("portal_url", "")
    is_private = plan["privacy"] == "private"
    block: Dict[str, Any] = {
        "privacy": plan["privacy"],
        "slug": identity.get("slug", plan["slug"]),
        "portal_host": identity.get("portal_host", ""),
        "community_url": portal_url,
        "requires_auth": is_private,
        "list_row_present": _list_has(session, plan["community_name"], plan["slug"]),
    }
    if is_private:
        block.update(_authenticated_portal_check(session, plan["community_name"]))
        if block.get("http") != 200:
            block["status"] = "deferred"
            block["reason"] = ("private group not confirmed in the authenticated portal DOM "
                               "(capture-pending create flow may not have landed) — Phase B")
        return block
    if not portal_url:
        block["status"] = "deferred"
        block["reason"] = "no member-visible portal URL captured — snapshot row only"
        return block
    try:
        import ghl_verify  # type: ignore
        rec = ghl_verify.verify_page(
            {"step": "community", "name": plan["community_name"], "page_id": plan["slug"],
             "preview_url": portal_url, "marker": plan["community_name"]},
            run_dir=evidence_root, live=True)
        block.update({"http": rec.get("http"),
                      "marker_in_rendered_dom": rec.get("marker_in_rendered_dom"),
                      "render_errors": rec.get("render_errors", []),
                      "render_method": "anonymous_render_check"})
    except Exception as exc:  # noqa: BLE001
        block["status"] = "deferred"
        block["reason"] = f"ghl_verify unavailable ({exc}) — snapshot row only"
    return block


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def build_community(task: dict, evidence_root: str, *, dry_run: bool = True,
                    state: Optional["ghl_run_state.RunState"] = None) -> dict:
    started = time.monotonic()
    dry_run = bool(task.get("dry_run", dry_run))
    os.makedirs(os.path.join(evidence_root, "routing"), exist_ok=True)
    os.makedirs(os.path.join(evidence_root, "shots"), exist_ok=True)

    plan = run_phase(state, "plan", lambda: plan_community(task), log=_log)
    preflight = run_phase(state, "preflight", lambda: _preflight(plan), log=_log)
    click_list = run_phase(state, "click_list", lambda: emit_click_list(plan), log=_log)
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

    return _live_build(task, plan, click_list, preflight, evidence_root, started, state=state)


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
        anchor(sels, "community.create_page.privacy_switch")   # still capture-pending
    except StopAndReport:
        raised = True
    if not raised:
        errors.append("capture-pending REQUIRED anchor did NOT STOP-and-report (D8 gate broken)")
    if anchor(sels, "community.create_page.privacy_switch", required=False) != "":
        errors.append("capture-pending optional anchor should return ''")

    # 6. mocked-browser walk proves the live path is REAL code routed through the
    #    agent-browser 0.27.0 executor (fix a): with group_nav LOCKed + fake ab/eval,
    #    _add_channel issues a real `find` command AND a native `.click()` for the
    #    Naive-UI 'CREATE CHANNEL' submit, and writes a receipt; an already-present
    #    channel REUSES via list-scan (fix b).
    if _HAVE_FFB:
        import copy
        locked = copy.deepcopy(sels)
        for t in locked["community"]["group_nav"].values():
            t["status"] = "locked"
        calls: List[tuple] = []
        evals: List[str] = []
        present = {"ZHC Founders Circle", "General", "Welcome"}   # base group nav

        def fake_ab(session, *args, timeout=30, stdin=None):
            calls.append(args)
            verb = args[0] if args else ""
            # a wait('--', <name>) makes the channel visible next snapshot (list-scan)
            if verb == "wait" and len(args) >= 3:
                present.add(args[2].strip("'\""))
            snap = " ".join(sorted(present)) if verb == "snapshot" else ""
            return subprocess.CompletedProcess(args=list(args), returncode=0,
                                               stdout=snap, stderr="")

        def fake_eval(session, js, timeout=20):
            evals.append(js)
            return "CLICKED:x" if ".click()" in js else ""   # list-scan DOM sweep → empty

        orig_ab, orig_eval = globals().get("_ab"), globals().get("_eval")
        try:
            globals()["_ab"] = fake_ab
            globals()["_eval"] = fake_eval
            globals()["_snapshot"] = lambda s, timeout=20: (fake_ab(s, "snapshot").stdout or "")
            globals()["_screenshot"] = lambda s, p: None
            with tempfile.TemporaryDirectory() as tmp2:
                os.makedirs(os.path.join(tmp2, "shots"), exist_ok=True)
                # NEW channel (not present) → created + real `find`/native-click commands
                rc_new = _add_channel("s", locked,
                                      {"name": "Announcements", "type": "post",
                                       "description": "", "slug": "announcements"},
                                      tmp2, [0], _NoopGovernor(), _NoopKeepalive())
                if rc_new["action"] != "created":
                    errors.append(f"mocked walk: new channel should be created (got {rc_new['action']})")
                if not any(c and c[0] == "find" for c in calls):
                    errors.append("mocked walk: no real `find` command issued (executor skeleton?)")
                if not any(".click()" in j for j in evals):
                    errors.append("mocked walk: Naive-UI submit did not use native .click() (fix a)")
                # EXISTING channel (present) → reused via list-scan, no create
                rc_dup = _add_channel("s", locked,
                                      {"name": "General", "type": "post",
                                       "description": "", "slug": "general"},
                                      tmp2, [0], _NoopGovernor(), _NoopKeepalive())
                if rc_dup["action"] != "reused":
                    errors.append(f"mocked walk: existing channel should be reused (got {rc_dup['action']})")
        finally:
            globals()["_ab"] = orig_ab if orig_ab is not None else _ffb._ab
            globals()["_eval"] = orig_eval if orig_eval is not None else _ffb._eval
            globals()["_snapshot"] = _ffb._snapshot
            globals()["_screenshot"] = _ffb._screenshot

    # 7. FIXES b/c/d/e — network-free proofs with injected fakes.
    if _HAVE_FFB:
        try:
            globals()["_snapshot"] = lambda s, timeout=20: "ZHC Alpha | zhc-beta-group | Gamma"
            globals()["_eval"] = lambda s, js, timeout=20: ""
            if not _list_has("s", "ZHC Alpha"):                       # fix b: match by name
                errors.append("fix b: list_has should match by name")
            if not _list_has("s", "Nope", slug="zhc-beta-group"):    # fix b: match by slug
                errors.append("fix b: list_has should match by slug")
            if _list_has("s", "Missing", slug="absent"):
                errors.append("fix b: list_has false positive")

            # fix c: identity = slug + portal host derived from the post-create URL
            globals()["_eval"] = lambda s, js, timeout=20: json.dumps(
                {"url": "https://portal.example.com/communities/groups/zhc-founders/home",
                 "host": "portal.example.com", "slug": "zhc-founders"})
            ident = _capture_group_identity("s", {"slug": "zhc-founders"})
            if ident["slug"] != "zhc-founders" or ident["portal_host"] != "portal.example.com":
                errors.append(f"fix c: identity wrong: {ident}")
            if ident["portal_url"] != "https://portal.example.com/communities/groups/zhc-founders/home":
                errors.append(f"fix c: portal_url wrong: {ident['portal_url']}")

            # fix e: PRIVATE group verify uses the authenticated in-session check + derived URL
            globals()["_eval"] = lambda s, js, timeout=20: json.dumps(
                {"ready": True, "has": True, "url": "https://portal.example.com/x"})
            globals()["_snapshot"] = lambda s, timeout=20: "ZHC Founders"
            vb = _verify_community("s", {"community_name": "ZHC Founders", "slug": "zhc-founders",
                                         "privacy": "private"}, ident, "/tmp/x")
            if vb.get("render_method") != "authenticated_in_session" or vb.get("http") != 200:
                errors.append(f"fix e: private authenticated verify wrong: {vb}")
            if vb.get("community_url") != ident["portal_url"]:
                errors.append("fix e: verify did not use the derived portal URL")

            # fix d: community cleanup = inactivate (no delete); capture-pending toggle → residue
            cl = _deactivate_group("s", load_selectors(), {"slug": "zhc-founders"}, ident)
            if cl["cleanup_primitive"] != "inactivate" or cl["deleted"] is not False:
                errors.append(f"fix d: cleanup should be inactivate/not-deleted: {cl}")
            if "stop" not in cl:
                errors.append("fix d: capture-pending toggle should record a STOP residue note")
        finally:
            globals()["_snapshot"] = _ffb._snapshot
            globals()["_eval"] = _ffb._eval

    # 8. router registers community + channel
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
    # U8/U10 — identical flags on every Skill-6 builder.
    ghl_run_state.add_run_state_args(p)
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    task = {"community_name": args.community_name, "location_id": args.location_id,
            "description": args.description, "privacy": args.privacy,
            "channels": [c.strip() for c in args.channels.split(",") if c.strip()]}
    return ghl_run_state.cli_run(
        args, builder="ghl_community_builder", specs=COMMUNITY_PHASES,
        script_path=__file__, task=task, build=build_community,
        ok_key="ok", url_key="community_url",
        argv=list(argv if argv is not None else sys.argv[1:]),
    )


if __name__ == "__main__":
    sys.exit(main())

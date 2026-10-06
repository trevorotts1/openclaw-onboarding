#!/usr/bin/env python3
"""iframe_router.py — the SINGLE adaptive iframe entrypoint for Skill 06
(fix-plan 9.7-1; the 9.3 "dual iframe tool stacks" gap; lane table 9.6;
activeFrameId discipline 3.4; multi-iframe selection 9.7-3).

WHY THIS EXISTS
---------------
Skill 6 has TWO honest iframe stacks and no single picker between them:

  * AB ladder            — tools/ghl_iframe_dragdrop.py: IframeDragDrop(ab, ev)
                           text-drag → in-frame coord-drag, dependency-injected
                           through the builder's own agent-browser glue. Works
                           with ZERO Playwright installed. Its receipts are
                           HONEST NEGATIVES when the ladder walls (ok=False).
  * Playwright CDP       — tools/ghl_iframe_drag.py: coordinate_drag /
                           frame_click attach over CDP to the SAME logged-in
                           agent-browser Chromium and use frame-scoped locators
                           (the only thing that REACHES a cross-origin,
                           ref-less drag tile). Raises IframeDragError —
                           never fakes success.

Docs pointed builders at both and left the choice to each call site (9.3 gap:
"no single adaptive picker that chooses AB-only vs AB+Playwright ... from host
resources"). This router IS that picker. The decision matrix (lane table 9.6):

    capability.iframeDrag.available == true   → Playwright CDP lane
      (requires cdp_url + the sibling's PLAYWRIGHT_AVAILABLE flag; when the CDP
       lane cannot proceed — no cdp_url, Playwright absent — the router
       DEGRADES to the AB ladder when an AB session was provided, otherwise it
       FAILS CLOSED. An honest AB lane beats a failed hybrid; nothing here
       fakes a placement.)
    capability.iframeDrag.available != true   → AB ladder, ONLY IF the caller
      supplied ab/ev. The capability file GATES the CDP lane: a cdp_url without
      a probed capability does NOT open it (9.7-4: "either hybrid OK or builds
      that need drag are blocked with a clear message").
    neither lane possible                     → IframeDragError
      ('iframe-drag-unavailable', 'no hybrid lane: playwright unavailable and
      no AB session provided') — NEVER a fabricated receipt.

Multi-iframe selection (9.7-3): an explicit iframe_selector or iframe_index
declares the frame; when kind resolves but the caller supplies an ambiguous
selector LIST without an index, or the snapshot shows MULTIPLE builder iframes
for the resolved preset, the router raises IframeDragError('iframe-ambiguous',
listing the candidates) instead of guessing a frame.

activeFrameId discipline (3.4): every route_* receipt carries the
iframe_selector actually used + a frame_epoch int. Callers hold the epoch from
get_frame_epoch() and bump_frame_epoch() after ANY navigation / panel open /
"two saves" (which invalidates every frame ref); a call made with an epoch that
is no longer current raises IframeDragError('iframe-refs-stale') — you cannot
act on a stale frame map through this router.

FAIL-CLOSED CODES raised here (all IframeDragError, sibling class when the
sibling module is importable, shape-identical fallback otherwise):
  iframe-drag-unavailable   no honest lane exists for this call (per matrix)
  iframe-ambiguous          N > 1 builder iframes and no explicit index/selector
  iframe-refs-stale         caller's frame_epoch predates the current epoch
  iframe-detect-*           detect_iframes could not run honestly
Plus raise-through codes from the siblings (unknown-iframe-kind,
playwright-unavailable, no-cdp-url, cdp-connect-failed, source-not-found,
not-placed, ...) — the router NEVER catches an IframeDragError into ok:true.

SOFT IMPORTS: both siblings are imported inside try/except; this module imports
clean (and its --selftest runs) with NEITHER present. Playwright availability
comes ONLY from ghl_iframe_drag.PLAYWRIGHT_AVAILABLE — this module never
imports playwright itself. If the sibling is absent, the router raises its own
shape-identical IframeDragError twin (it never re-imports the sibling to flip
flags — a second import object would carry a distinct error class and dodge
except clauses).

USAGE
-----
    import iframe_router as ir
    try:
        receipt = ir.route_drag(
            "form", "State", "Submit",
            cdp_url=cdp_url,            # from `agent-browser get cdp-url`
            verify_text="State",        # count-delta arbiter (CDP lane)
            url_marker="form-builder",
            frame_epoch=my_epoch,       # 3.4: declare the frame generation
        )
    except ir.IframeDragError as exc:
        ...STOP-and-report (classify via ghl_iframe_drag.board_note)...

    python3 tools/iframe_router.py --selftest       # offline, injectable fakes
    python3 tools/iframe_router.py --dry --kind form  # print the lane decision
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, Optional, Tuple

IFRAME_ROUTER_VERSION = "v1.0.0"

# ---------------------------------------------------------------------------
# sys.path — builders import siblings with the tools dir on sys.path
# (ghl_form_builder.py:129 does `import ghl_iframe_drag`); make that hold even
# when this module is run as a bare script.
# ---------------------------------------------------------------------------
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# ---------------------------------------------------------------------------
# SOFT sibling imports — the router stays importable with NEITHER sibling
# present; every lane that needs one checks for None and fails closed.
# ---------------------------------------------------------------------------
_DRAG: Any = None    # tools/ghl_iframe_drag.py (Playwright CDP primitive)
_DROP: Any = None    # tools/ghl_iframe_dragdrop.py (AB/eval ladder)
try:  # pragma: no cover - import success is environment-dependent
    import ghl_iframe_drag as _DRAG  # type: ignore
except Exception:  # noqa: BLE001
    _DRAG = None
try:  # pragma: no cover
    import ghl_iframe_dragdrop as _DROP  # type: ignore
except Exception:  # noqa: BLE001
    _DROP = None

if _DRAG is not None:
    # Alias the SIBLING's class object — never a second import of the module
    # (a distinct import object would carry a distinct IframeDragError class
    # and silently dodge every caller's `except ghl_iframe_drag.IframeDragError`).
    IframeDragError = _DRAG.IframeDragError  # type: ignore[misc]
else:  # pragma: no cover - only on a broken install
    class IframeDragError(RuntimeError):
        """Shape-identical fallback twin used ONLY when the sibling primitive
        module itself is not importable (same .code/.reason/.details contract
        so callers' except clauses and board_note() classification keep
        working)."""

        def __init__(self, code: str, reason: str,
                     details: Optional[Dict[str, Any]] = None):
            self.code = code
            self.reason = reason
            self.details = details
            super().__init__(f"{code}: {reason}")


# ---------------------------------------------------------------------------
# Presets — prefer the SIBLING's IFRAME_SELECTORS (single source of truth);
# the literal fallback below is byte-identical and exists so the router can
# still resolve/validate kinds on a broken install (it fails closed there
# anyway on any live call, but kind validation should still speak precisely).
# ---------------------------------------------------------------------------
if _DRAG is not None:
    _IFRAME_PRESETS: Dict[str, str] = dict(_DRAG.IFRAME_SELECTORS)
else:  # pragma: no cover - only on a broken install
    _IFRAME_PRESETS = {
        "form": 'iframe[src*="form-builder-v2"]',
        "survey": 'iframe[src*="survey-builder-v2"]',
        "page_code": 'iframe[src*="page-builder"]',
    }

_PRESET_MARKER_RE = re.compile(r'iframe\[src\*="([^"]+)"\]')

# src markers per kind, extracted from the preset selectors themselves.
_IFRAME_SRC_MARKERS: Dict[str, str] = {}
for _kind, _sel in _IFRAME_PRESETS.items():
    _m = _PRESET_MARKER_RE.search(_sel)
    _IFRAME_SRC_MARKERS[_kind] = _m.group(1) if _m else _sel

_IFRAME_SRC_RE = re.compile(
    r"<iframe\b[^>]*?\bsrc\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE | re.DOTALL)


def iframe_selector_for(kind: str) -> str:
    """Resolve a builder kind ('form' | 'survey' | 'page_code') to its preset
    iframe selector. Prefers the sibling's accessor (identical error contract);
    raises IframeDragError('unknown-iframe-kind', ...) for a typo so an unknown
    kind can never silently target the wrong frame."""
    if _DRAG is not None:
        return _DRAG.iframe_selector_for(kind)
    try:  # pragma: no cover - only on a broken install
        return _IFRAME_PRESETS[kind]
    except KeyError as exc:
        raise IframeDragError(
            "unknown-iframe-kind",
            f"no known iframe selector for kind {kind!r}; known: "
            f"{sorted(_IFRAME_PRESETS)}") from exc


# ---------------------------------------------------------------------------
# Capability — the probe output (tools/capability_probe.py →
# working/skill6-capability.json). The CDP lane is GATED on
# capability.iframeDrag.available (9.7-4): no probed capability, no CDP lane.
# ---------------------------------------------------------------------------
DEFAULT_CAPABILITY_PATH = os.path.normpath(
    os.path.join(_TOOLS_DIR, os.pardir, "working", "skill6-capability.json"))

_TRUTHY = ("1", "true", "yes")


def _flag_true(value: Any) -> bool:
    """Truthiness for probe flags, mirroring page_code_drag_enabled()'s
    convention ("1"/"true"/"yes", case-insensitive) so a stringy JSON value
    like "false" can never read as available."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY
    return bool(value)


def load_capability(path: Optional[str] = None) -> Dict[str, Any]:
    """Load the capability probe JSON. A MISSING file returns {} (the CDP lane
    then stays OFF — absence of a probe is never proof of a hybrid host). An
    unreadable/malformed file returns {"_read_error": ...} so the corruption is
    visible to anyone inspecting the decision instead of silently swallowed."""
    p = path or DEFAULT_CAPABILITY_PATH
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        return {"_read_error": f"{type(exc).__name__}: {exc}"}


def _capability_from(capability: Any,
                     capability_path: Optional[str]) -> Tuple[Dict[str, Any], str]:
    """Resolve the injected-dict / injected-path / default-file capability and
    name its source honestly for the receipt."""
    if capability is None:
        path = capability_path or DEFAULT_CAPABILITY_PATH
        cap = load_capability(path)
        if "_read_error" in cap:
            return cap, f"file:{path} (READ ERROR)"
        if not cap:
            return cap, f"file:{path} (missing/empty)"
        return cap, f"file:{path}"
    if isinstance(capability, (str, os.PathLike)):
        path = os.fspath(capability)
        return load_capability(path), f"file:{path}"
    return dict(capability), "injected"


# ---------------------------------------------------------------------------
# activeFrameId discipline (plan 3.4) — a module-scope frame epoch. Callers
# hold the value returned by get_frame_epoch() when they snapshot/map frames
# and bump_frame_epoch() after ANY navigation / panel open / "two saves" (which
# invalidates every frame ref). route_* accepts frame_epoch= and raises
# 'iframe-refs-stale' when the caller's declaration predates the current epoch.
# GHL builder parallelism is maxParallelTabs=1, so a single module counter is
# the whole discipline.
# ---------------------------------------------------------------------------
_FRAME_EPOCH = 0


def get_frame_epoch() -> int:
    """Current frame epoch — the value a caller declares with when acting."""
    return _FRAME_EPOCH


def bump_frame_epoch() -> int:
    """Invalidate all frame refs (call after any navigation / panel open /
    second save) and return the NEW epoch."""
    global _FRAME_EPOCH
    _FRAME_EPOCH += 1
    return _FRAME_EPOCH


def _require_current_epoch(frame_epoch: Optional[int]) -> None:
    if frame_epoch is None:
        return
    current = _FRAME_EPOCH
    if int(frame_epoch) != current:
        raise IframeDragError(
            "iframe-refs-stale",
            f"caller declared frame_epoch {frame_epoch} but the router is at "
            f"epoch {current} — frame references were invalidated by a "
            "navigation/panel-open; re-snapshot the page, bump_frame_epoch(), "
            "and retry with the current get_frame_epoch().")


# ---------------------------------------------------------------------------
# Multi-iframe detection (9.7-3) — count/classify builder iframes WITHOUT
# guessing. The snapshot path is fully offline (regex over an agent-browser
# snapshot / HTML); the live path attaches over CDP only when explicitly asked.
# ---------------------------------------------------------------------------
def detect_iframes(cdp_url: Optional[str] = None,
                   snapshot_text: Optional[str] = None) -> Dict[str, Any]:
    """Detect builder iframes and classify each against the known presets.

    snapshot_text given  → offline classification of every <iframe src=...>
        occurrence (source: "snapshot"). NEVER needs a browser — this is the
        path the selftest and the ambiguity gate use.
    else cdp_url given   → live enumeration of child frames over CDP via the
        sibling's soft Playwright flag (source: "live"). Fails closed with
        'iframe-detect-unavailable' / 'iframe-detect-failed' — it never
        reports an empty frame list it did not actually observe.
    neither              → IframeDragError('iframe-detect-unavailable', ...):
        an empty result would be a FALSE NEGATIVE about the page, so asking
        for detection with no input is itself the error.
    """
    if snapshot_text is not None:
        iframes = []
        for src in _IFRAME_SRC_RE.findall(snapshot_text):
            kind: Optional[str] = None
            for k, marker in _IFRAME_SRC_MARKERS.items():
                if marker and marker in src:
                    kind = k
                    break
            iframes.append({
                "kind": kind,
                "src": src,
                "selector": _IFRAME_PRESETS.get(kind) if kind else None,
            })
        return {"source": "snapshot", "iframes": iframes}

    if cdp_url and str(cdp_url).strip():
        if _DRAG is None or not getattr(_DRAG, "PLAYWRIGHT_AVAILABLE", False):
            raise IframeDragError(
                "iframe-detect-unavailable",
                "live iframe detection needs Playwright via ghl_iframe_drag "
                "(PLAYWRIGHT_AVAILABLE is false) — pass snapshot_text instead")
        try:
            with _DRAG.sync_playwright() as p:  # type: ignore[union-attr]
                browser = p.chromium.connect_over_cdp(cdp_url)
                try:
                    iframes = []
                    for context in browser.contexts:
                        for page in context.pages:
                            for frame in page.frames:
                                if frame is getattr(page, "main_frame", None):
                                    continue  # only CHILD frames are iframes
                                src = frame.url or ""
                                kind = None
                                for k, marker in _IFRAME_SRC_MARKERS.items():
                                    if marker and marker in src:
                                        kind = k
                                        break
                                iframes.append({
                                    "kind": kind,
                                    "src": src,
                                    "selector": _IFRAME_PRESETS.get(kind) if kind else None,
                                })
                finally:
                    try:
                        browser.close()  # detaches the CDP client only
                    except Exception:  # noqa: BLE001
                        pass
        except IframeDragError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise IframeDragError(
                "iframe-detect-failed",
                f"live iframe detection over CDP failed: "
                f"{type(exc).__name__}: {exc}") from exc
        return {"source": "live", "iframes": iframes}

    raise IframeDragError(
        "iframe-detect-unavailable",
        "detect_iframes needs snapshot_text (offline) or cdp_url (live); "
        "neither was provided — refusing to claim 'no iframes' it never saw")


# ---------------------------------------------------------------------------
# Selector resolution + ambiguity gate (9.7-3)
# ---------------------------------------------------------------------------
def _resolve_selector(
    kind: str,
    *,
    iframe_selector: Any = None,
    iframe_index: Optional[int] = None,
    snapshot_text: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Resolve the iframe selector for a route_* call and ENFORCE the
    ambiguity gate. Returns (selector, meta) where meta records explicit /
    match_count / iframe_index for the receipt.

    * explicit single string → used as-is (the caller declared the frame).
    * list/tuple of 1        → that one.
    * list/tuple of N > 1    → IframeDragError('iframe-ambiguous', listing the
      candidates and requiring an explicit selector or iframe_index) unless
      iframe_index names one (validated in range) — the index is CONSUMED by
      the list pick itself (no second narrowing is composed downstream).
    * no override            → iframe_selector_for(kind) — a typo'd kind raises
      'unknown-iframe-kind' — then, when a snapshot was supplied, MULTIPLE
      builder iframes matching that preset without an explicit index raise
      'iframe-ambiguous' with the candidate srcs.
    """
    _require_known_kind(kind)
    meta: Dict[str, Any] = {"explicit": False, "match_count": None,
                            "iframe_index": iframe_index,
                            "compose_nth": False}

    if iframe_selector is not None:
        if isinstance(iframe_selector, (list, tuple)):
            sels = [str(s).strip() for s in iframe_selector if s and str(s).strip()]
            if not sels:
                raise IframeDragError(
                    "empty-iframe-selector",
                    "iframe_selector override was an empty list — pass a "
                    "non-empty selector string, a 1-item list, or nothing")
            if len(sels) == 1:
                meta["explicit"] = True
                return sels[0], meta
            if iframe_index is None:
                raise IframeDragError(
                    "iframe-ambiguous",
                    f"{len(sels)} builder iframe selectors were supplied "
                    f"without an explicit index — declare WHICH frame with "
                    f"iframe_index=0..{len(sels) - 1} or pass ONE selector "
                    f"string. candidates: {sels!r}")
            if not 0 <= int(iframe_index) < len(sels):
                raise IframeDragError(
                    "iframe-ambiguous",
                    f"iframe_index {iframe_index} is out of range for "
                    f"{len(sels)} candidates: {sels!r}")
            meta["explicit"] = True
            return sels[int(iframe_index)], meta
        sel = str(iframe_selector).strip()
        if not sel:
            raise IframeDragError(
                "empty-iframe-selector",
                "iframe_selector override must be a non-empty string")
        meta["explicit"] = True
        meta["compose_nth"] = iframe_index is not None
        return sel, meta

    sel = iframe_selector_for(kind)  # unknown-iframe-kind raise-through
    if snapshot_text:
        det = detect_iframes(snapshot_text=snapshot_text)
        matches = [d for d in det["iframes"] if d.get("selector") == sel]
        meta["match_count"] = len(matches)
        if len(matches) > 1 and iframe_index is None:
            raise IframeDragError(
                "iframe-ambiguous",
                f"{len(matches)} iframes on this page match the {kind!r} "
                f"builder preset {sel!r} with no explicit purpose/index — "
                f"pass an explicit iframe_selector (one per builder purpose) "
                f"or iframe_index=0..{len(matches) - 1}. candidates: "
                f"{[d['src'] for d in matches]!r}")
        if len(matches) > 1 and iframe_index is not None \
                and not 0 <= int(iframe_index) < len(matches):
            raise IframeDragError(
                "iframe-ambiguous",
                f"iframe_index {iframe_index} is out of range for "
                f"{len(matches)} {kind!r} builder iframes on this page")
    meta["compose_nth"] = iframe_index is not None
    return sel, meta


def _require_known_kind(kind: str) -> None:
    """Fail closed on a typo'd kind BEFORE anything else runs."""
    iframe_selector_for(kind)


def _compose_selector(sel: str, iframe_index: Optional[int]) -> str:
    """Narrow an ambiguous preset to the Nth match for the Playwright lane
    ('sel >> nth=k' is Playwright's honest frame-scoping syntax)."""
    if iframe_index is None:
        return sel
    return f"{sel} >> nth={int(iframe_index)}"


# ---------------------------------------------------------------------------
# Receipt augmentation — routing metadata rides on the LANE's OWN receipt.
# The router NEVER manufactures ok/placed/verify keys: an AB receipt that came
# back ok=False stays ok=False, and a CDP IframeDragError propagates uncaught.
# ---------------------------------------------------------------------------
_CDP_ONLY_KW = frozenset({
    "url_marker", "interpolated_moves", "move_interval_ms", "settle_ms",
    "timeout_ms", "target_dx", "target_dy", "source_scroll_hint",
})
# AB-ladder-only kwargs (IframeDragDrop.drag/tab_click). Never forwarded to the
# CDP primitives (they would TypeError) and CDP-only kwargs are never silently
# forwarded to the AB ladder — dropped ones are NAMED in the receipt.
_AB_ONLY_KW = frozenset({"verify_expr", "timeout"})


def _with_routing(receipt: Dict[str, Any], *, lane: str, kind: str,
                  sel_used: str, cap_source: str,
                  extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = dict(receipt) if isinstance(receipt, dict) else {}
    out.update({
        "router": f"iframe_router {IFRAME_ROUTER_VERSION}",
        "lane": lane,
        "kind": kind,
        "iframe_selector": sel_used,
        "frame_epoch": _FRAME_EPOCH,
        "capability_source": cap_source,
    })
    if extra:
        for k, v in extra.items():
            if v is not None:
                out[k] = v
    return out


def _ab_lane(session: Any, ab: Any, ev: Any) -> "Any":
    """Construct the AB ladder (and enforce the session contract) or raise."""
    if _DROP is None:
        raise IframeDragError(
            "iframe-drag-unavailable",
            "the AB ladder module ghl_iframe_dragdrop is not importable — "
            "no honest lane remains for this call")
    if session is None or not str(session).strip():
        raise IframeDragError(
            "iframe-drag-unavailable",
            "the AB ladder was selected but no agent-browser session id was "
            "provided — pass session=<session id> alongside ab/ev")
    return _DROP.IframeDragDrop(ab=ab, ev=ev)


def _cdp_lane_ok(cap_available: bool, cdp_url: Any) -> Tuple[bool, str]:
    """Decide whether the Playwright CDP lane can actually proceed, and name
    the reason when it cannot (for the receipt's cdp_lane_skipped_reason)."""
    if not cap_available:
        return False, "capability.iframeDrag.available is not true (9.6 lane gate)"
    if _DRAG is None:
        return False, "sibling primitive ghl_iframe_drag is not importable"
    if not getattr(_DRAG, "PLAYWRIGHT_AVAILABLE", False):
        return False, "Playwright unavailable (ghl_iframe_drag.PLAYWRIGHT_AVAILABLE is false)"
    if not (cdp_url and str(cdp_url).strip()):
        return False, "no cdp_url supplied (`agent-browser get cdp-url`)"
    return True, ""


# ===========================================================================
# ROUTE_DRAG — the single adaptive drag entrypoint (9.7-1)
# ===========================================================================
def route_drag(
    kind: str,
    tile_text: str,
    target_text: str,
    *,
    capability: Any = None,
    capability_path: Optional[str] = None,
    cdp_url: Optional[str] = None,
    session: Optional[str] = None,
    ab: Optional[Any] = None,
    ev: Optional[Any] = None,
    verify_text: Optional[str] = None,
    iframe_selector: Any = None,
    iframe_index: Optional[int] = None,
    snapshot_text: Optional[str] = None,
    frame_epoch: Optional[int] = None,
    **kw: Any,
) -> Dict[str, Any]:
    """Route ONE cross-origin-iframe drag down the honest lane for this host.

    Decision matrix (plan 9.6, task 9.7-1):
      1. capability.iframeDrag.available true AND Playwright importable AND
         cdp_url supplied → Playwright CDP via ghl_iframe_drag.coordinate_drag.
         Its IframeDragError (source-not-found, not-placed, cdp-connect-failed,
         ...) raises THROUGH uncaught — a placement that did not count-delta
         verify is never reported as placed.
      2. CDP lane unavailable (flag off / no cdp_url / capability off) but the
         caller supplied ab/ev (+ session) → the AB ladder via
         ghl_iframe_dragdrop.IframeDragDrop(ab, ev).drag(...). Its ok=False
         (a walled text-drag whose coord-drag delta never landed) is returned
         AS-IS — an honest negative, never flipped. Pass verify_expr= (a JS
         EXPRESSION returning a number) for the honest delta arbiter on this
         lane; verify_text has no AB-ladder equivalent and is only RECORDED.
      3. neither lane → IframeDragError('iframe-drag-unavailable',
         'no hybrid lane: playwright unavailable and no AB session provided').
         NEVER a fabricated receipt.

    Frame discipline (plan 3.4): pass frame_epoch=get_frame_epoch() as held by
    the caller; a stale value raises 'iframe-refs-stale'. Every receipt carries
    the iframe_selector used + the epoch it acted in.

    Ambiguity gate (9.7-3): see _resolve_selector — an ambiguous selector list
    or a snapshot showing multiple builder iframes without an explicit
    selector/index raises 'iframe-ambiguous'.

    capability / capability_path: inject the probe dict (tests) or an alternate
    probe file; default loads working/skill6-capability.json. A MISSING probe
    keeps the CDP lane OFF (absence of a probe is never proof of a hybrid host).

    Extra kwargs: CDP-only (url_marker, interpolated_moves, move_interval_ms,
    settle_ms, timeout_ms, target_dx, target_dy, source_scroll_hint) are
    forwarded to coordinate_drag on the CDP lane; AB-only (verify_expr,
    timeout) to the ladder. A kwarg foreign to the taken lane is dropped and
    NAMED in the receipt ('ab_ignored_kwargs' / 'cdp_ignored_kwargs') — never
    silently discarded, never smuggled across.
    """
    _require_current_epoch(frame_epoch)
    sel, selmeta = _resolve_selector(
        kind, iframe_selector=iframe_selector, iframe_index=iframe_index,
        snapshot_text=snapshot_text)

    cap, cap_source = _capability_from(capability, capability_path)
    cap_available = _flag_true((cap.get("iframeDrag") or {}).get("available"))
    cdp_ok, cdp_block_reason = _cdp_lane_ok(cap_available, cdp_url)
    ab_present = ab is not None or ev is not None

    if cdp_ok:
        sel_used = _compose_selector(sel, iframe_index) \
                if selmeta.get("compose_nth") else sel
        cdp_kw = {k: v for k, v in kw.items() if k not in _AB_ONLY_KW}
        receipt = _DRAG.coordinate_drag(  # raise-through IframeDragError
            cdp_url,
            iframe_selector=sel_used,
            source=tile_text,
            target=target_text,
            verify_text=verify_text,
            **cdp_kw,
        )
        return _with_routing(
            receipt, lane="playwright-cdp", kind=kind, sel_used=sel_used,
            cap_source=cap_source,
            extra={"cdp_ignored_kwargs": sorted(k for k in kw
                                                if k in _AB_ONLY_KW)} |
                  ({} if selmeta.get("explicit") or sel_used == sel
                   else {"selector_preset": sel}))

    if ab_present:
        ladder = _ab_lane(session, ab, ev)
        ab_kw = {k: v for k, v in kw.items() if k in _AB_ONLY_KW}
        receipt = ladder.drag(session, tile_text, target_text, **ab_kw)
        return _with_routing(
            receipt, lane="ab-ladder", kind=kind, sel_used=sel,
            cap_source=cap_source,
            extra={
                # verify_text is RECORDED, never claimed as proof — the AB
                # ladder's honest arbiter is verify_expr's count delta.
                "verify_text": verify_text,
                "ab_ignored_kwargs": sorted(k for k in kw
                                            if k not in _AB_ONLY_KW),
                "cdp_lane_skipped_reason": cdp_block_reason,
            } | ({"verify_expr": kw["verify_expr"]}
                 if "verify_expr" in kw else {}))

    if cap_available:
        raise IframeDragError(
            "iframe-drag-unavailable",
            f"hybrid capability is probed available but the Playwright CDP "
            f"lane could not proceed ({cdp_block_reason}) and no AB session "
            f"was provided — supply `agent-browser get cdp-url` or an AB "
            f"session (ab/ev + session)")
    raise IframeDragError(
        "iframe-drag-unavailable",
        "no hybrid lane: playwright unavailable and no AB session provided")


# ===========================================================================
# ROUTE_CLICK — the frame-scoped click counterpart (ghl_iframe_drag.frame_click
# vs the AB ladder's find/click rung, 9.7-1)
# ===========================================================================
def route_click(
    kind: str,
    target: str,
    *,
    capability: Any = None,
    capability_path: Optional[str] = None,
    cdp_url: Optional[str] = None,
    session: Optional[str] = None,
    ab: Optional[Any] = None,
    ev: Optional[Any] = None,
    verify_text: Optional[str] = None,
    verify_absent: bool = False,
    iframe_selector: Any = None,
    iframe_index: Optional[int] = None,
    snapshot_text: Optional[str] = None,
    frame_epoch: Optional[int] = None,
    **kw: Any,
) -> Dict[str, Any]:
    """Route ONE in-iframe click down the honest lane (same matrix/epoch/
    ambiguity contract as :func:`route_drag`).

    CDP lane → ghl_iframe_drag.frame_click (raise-through IframeDragError,
    incl. 'click-not-verified' when the click's effect never verified).
    AB lane  → IframeDragDrop(ab, ev).tab_click(session, target) — the
    `find text <t> click` → native .click() rung; ok=False when the tab never
    resolved is returned AS-IS.
    neither  → IframeDragError('iframe-drag-unavailable', ...), never a fake.
    """
    _require_current_epoch(frame_epoch)
    sel, selmeta = _resolve_selector(
        kind, iframe_selector=iframe_selector, iframe_index=iframe_index,
        snapshot_text=snapshot_text)

    cap, cap_source = _capability_from(capability, capability_path)
    cap_available = _flag_true((cap.get("iframeDrag") or {}).get("available"))
    cdp_ok, cdp_block_reason = _cdp_lane_ok(cap_available, cdp_url)
    ab_present = ab is not None or ev is not None

    if cdp_ok:
        sel_used = _compose_selector(sel, iframe_index) \
                if selmeta.get("compose_nth") else sel
        cdp_kw = {k: v for k, v in kw.items() if k not in _AB_ONLY_KW}
        receipt = _DRAG.frame_click(  # raise-through IframeDragError
            cdp_url,
            iframe_selector=sel_used,
            target=target,
            verify_text=verify_text,
            verify_absent=verify_absent,
            **cdp_kw,
        )
        return _with_routing(
            receipt, lane="playwright-cdp", kind=kind, sel_used=sel_used,
            cap_source=cap_source,
            extra={"cdp_ignored_kwargs": sorted(k for k in kw
                                                if k in _AB_ONLY_KW)} |
                  ({} if selmeta.get("explicit") or sel_used == sel
                   else {"selector_preset": sel}))

    if ab_present:
        ladder = _ab_lane(session, ab, ev)
        tab_kw = {"timeout": kw["timeout"]} if "timeout" in kw else {}
        receipt = ladder.tab_click(session, target, **tab_kw)
        return _with_routing(
            receipt, lane="ab-ladder", kind=kind, sel_used=sel,
            cap_source=cap_source,
            extra={
                "verify_text": verify_text,
                "verify_absent": verify_absent,
                "ab_ignored_kwargs": sorted(k for k in kw if k != "timeout"),
                "cdp_lane_skipped_reason": cdp_block_reason,
            })

    if cap_available:
        raise IframeDragError(
            "iframe-drag-unavailable",
            f"hybrid capability is probed available but the Playwright CDP "
            f"lane could not proceed ({cdp_block_reason}) and no AB session "
            f"was provided — supply `agent-browser get cdp-url` or an AB "
            f"session")
    raise IframeDragError(
        "iframe-drag-unavailable",
        "no hybrid lane: playwright unavailable and no AB session provided")


# ---------------------------------------------------------------------------
# CLI / selftest — fully OFFLINE: injectable fakes, no network, no browser,
# no Playwright requirement. Exit 0 only when every contract holds.
# ---------------------------------------------------------------------------
def _selftest() -> int:  # noqa: C901
    import subprocess as _sp

    errors = []

    # Fakes — injected in place of the sibling primitives; the real modules are
    # NEVER re-imported and the flag flips below happen on the SIBLING's own
    # globals (a second import object would dodge except clauses).
    CDP_CALLS: list = []
    AB_CALLS: list = []

    def fake_coordinate_drag(cdp_url, *, iframe_selector, source, target,
                             verify_text=None, **kw):
        CDP_CALLS.append({"cdp_url": cdp_url, "iframe_selector": iframe_selector,
                          "source": source, "target": target,
                          "verify_text": verify_text, "kw": kw})
        return {"ok": True, "placed": True, "source": source, "target": target,
                "iframe_selector": iframe_selector, "verify_text": verify_text}

    def fake_frame_click(cdp_url, *, iframe_selector, target, verify_text=None,
                         verify_absent=False, **kw):
        CDP_CALLS.append({"cdp_url": cdp_url, "iframe_selector": iframe_selector,
                          "click_target": target, "verify_text": verify_text})
        return {"ok": True, "clicked": target, "iframe_selector": iframe_selector}

    def fake_ab(session, *args, timeout=15):
        AB_CALLS.append(args)
        return _sp.CompletedProcess(args=list(args), returncode=0,
                                    stdout="✓ Done", stderr="")

    def fake_ev_ok(session, js, timeout=15):
        if "pointerdown" in js:
            return '{"ok":true,"before":0,"after":1}'
        return "CLICKED:Tab"

    def fake_ev_wall(session, js, timeout=15):
        if "pointerdown" in js:
            return '{"ok":false,"before":0,"after":0}'
        return ""

    CAP_HYBRID = {"iframeDrag": {"available": True}}
    CAP_AB = {"iframeDrag": {"available": False}}
    PRESET_FORM = 'iframe[src*="form-builder-v2"]'

    orig_cd = getattr(_DRAG, "coordinate_drag", None)
    orig_fc = getattr(_DRAG, "frame_click", None)
    orig_pw = getattr(_DRAG, "PLAYWRIGHT_AVAILABLE", None)
    try:
        if _DRAG is None or _DROP is None:
            errors.append("sibling modules must be importable for the full "
                          "selftest (they are stdlib-only)")
        else:
            _DRAG.PLAYWRIGHT_AVAILABLE = True
            _DRAG.coordinate_drag = fake_coordinate_drag
            _DRAG.frame_click = fake_frame_click

            # 1. hybrid available -> routes CDP (raise-through contract held)
            r = route_drag("form", "State", "Submit", capability=CAP_HYBRID,
                           cdp_url="ws://selftest", verify_text="State",
                           url_marker="form-builder",
                           frame_epoch=get_frame_epoch())
            if r.get("lane") != "playwright-cdp":
                errors.append(f"hybrid did not route CDP: {r.get('lane')!r}")
            if not r.get("ok"):
                errors.append(f"CDP ok was not carried through: {r}")
            if r.get("iframe_selector") != PRESET_FORM:
                errors.append(f"wrong iframe_selector: {r.get('iframe_selector')!r}")
            if not isinstance(r.get("frame_epoch"), int):
                errors.append("receipt missing int frame_epoch")
            if CDP_CALLS and CDP_CALLS[-1].get("verify_text") != "State":
                errors.append("verify_text was not forwarded to the CDP drag")
            if CDP_CALLS and CDP_CALLS[-1].get("kw", {}).get("url_marker") != "form-builder":
                errors.append("url_marker was not forwarded to the CDP drag")

            # 2. route_click hybrid -> frame_click fake
            CDP_CALLS.clear()
            rc = route_click("survey", "Save", capability=CAP_HYBRID,
                             cdp_url="ws://selftest",
                             frame_epoch=get_frame_epoch())
            if rc.get("lane") != "playwright-cdp" or not rc.get("ok"):
                errors.append(f"route_click CDP failed: {rc}")

            # 3. AB-only -> AB ladder (rung1 done + verify_expr delta proves)
            AB_CALLS.clear()
            rd = route_drag("survey", "Rating", "Slide 2", capability=CAP_AB,
                            session="s", ab=fake_ab, ev=fake_ev_ok,
                            verify_expr="s.slides.length",
                            frame_epoch=get_frame_epoch())
            if rd.get("lane") != "ab-ladder":
                errors.append(f"capability-off did not route AB: {rd.get('lane')!r}")
            if not (rd.get("ok") and rd.get("path") == "coord-drag"):
                errors.append(f"AB ladder receipt wrong: {rd}")
            if not AB_CALLS:
                errors.append("AB ladder never invoked the injected ab callable")
            if rd.get("verify_text") is not None:
                errors.append("stray verify_text should be absent when not given")

            # 4. walled AB drag stays an HONEST negative (never flipped to ok)
            rw = route_drag("form", "City", "Submit", capability=CAP_AB,
                            session="s", ab=fake_ab, ev=fake_ev_wall,
                            verify_expr="x", frame_epoch=get_frame_epoch())
            if rw.get("ok") is not False:
                errors.append(f"walled AB receipt must stay ok=False: {rw}")

            # 5. capability off + cdp_url present STILL routes AB (capability
            #    gates the CDP lane — a bare cdp_url does not open it)
            CDP_CALLS.clear()
            rg = route_drag("form", "A", "B", capability=CAP_AB, cdp_url="ws://x",
                            session="s", ab=fake_ab, ev=fake_ev_ok,
                            frame_epoch=get_frame_epoch())
            if CDP_CALLS or rg.get("lane") != "ab-ladder":
                errors.append("cdp_url without capability.iframeDrag.available "
                              "must NOT open the CDP lane")

            # 6. hybrid flag OFF + AB present -> honest degrade to the ladder
            _DRAG.PLAYWRIGHT_AVAILABLE = False
            rdg = route_drag("form", "A", "B", capability=CAP_HYBRID,
                             cdp_url="ws://selftest", session="s",
                             ab=fake_ab, ev=fake_ev_ok,
                             frame_epoch=get_frame_epoch())
            if rdg.get("lane") != "ab-ladder":
                errors.append(f"flag-off hybrid did not degrade to AB: {rdg}")
            if not rdg.get("cdp_lane_skipped_reason"):
                errors.append("degraded receipt must NAME why the CDP lane skipped")
            _DRAG.PLAYWRIGHT_AVAILABLE = True

            # 7. route_click AB lane (find/click rung)
            rca = route_click("form", "Quick Add", capability=CAP_AB,
                              session="s", ab=fake_ab, ev=fake_ev_ok,
                              frame_epoch=get_frame_epoch())
            if rca.get("lane") != "ab-ladder" or not rca.get("ok"):
                errors.append(f"route_click AB failed: {rca}")

            # 8. selector LIST + explicit index picks THAT item as-is —
            #    no second nth narrowing (it would match nothing real)
            CDP_CALLS.clear()
            ridx = route_drag("form", "A", "B", capability=CAP_HYBRID,
                              cdp_url="ws://selftest",
                              iframe_selector=[PRESET_FORM, "iframe#second"],
                              iframe_index=1, frame_epoch=get_frame_epoch())
            if CDP_CALLS and CDP_CALLS[-1]["iframe_selector"] != "iframe#second":
                errors.append("list+iframe_index must pick the named item "
                              f"verbatim, got: {CDP_CALLS[-1]['iframe_selector']!r}")

            # 9. capability FILE round-trip (tmp file, injected path)
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                cap_file = os.path.join(td, "cap.json")
                with open(cap_file, "w", encoding="utf-8") as fh:
                    json.dump(CAP_AB, fh)
                rcf = route_drag("form", "A", "B", capability_path=cap_file,
                                 session="s", ab=fake_ab, ev=fake_ev_ok,
                                 frame_epoch=get_frame_epoch())
                if rcf.get("lane") != "ab-ladder" or \
                        not str(rcf.get("capability_source", "")).startswith("file:"):
                    errors.append(f"capability_path routing failed: {rcf}")

            # 14b. snapshot multi-match + explicit index -> gate opens and the
            #      CDP lane composes the nth (fakes still patched here).
            CDP_CALLS.clear()
            snap2b = ('<iframe src="https://x.leadconnectorhq.com/form-builder-v2/aaa"></iframe>'
                      '<iframe src="https://x.leadconnectorhq.com/form-builder-v2/bbb"></iframe>')
            rn = route_drag("form", "A", "B", capability=CAP_HYBRID,
                            cdp_url="ws://selftest", snapshot_text=snap2b,
                            iframe_index=1, frame_epoch=get_frame_epoch())
            if rn.get("lane") != "playwright-cdp":
                errors.append(f"snapshot+index did not route CDP: {rn.get('lane')!r}")
            if CDP_CALLS and CDP_CALLS[-1]["iframe_selector"] != f"{PRESET_FORM} >> nth=1":
                errors.append("snapshot+index did not compose the nth selector: "
                              f"{CDP_CALLS[-1]['iframe_selector']!r}")
    finally:
        if _DRAG is not None:
            if orig_cd is not None:
                _DRAG.coordinate_drag = orig_cd
            if orig_fc is not None:
                _DRAG.frame_click = orig_fc
            if orig_pw is not None:
                _DRAG.PLAYWRIGHT_AVAILABLE = orig_pw

    # 10. nothing available -> fail closed with the PINNED reason, no receipt
    try:
        route_drag("form", "A", "B", capability=CAP_AB)
        errors.append("no-lane route_drag did NOT raise")
    except IframeDragError as e:
        if e.code != "iframe-drag-unavailable":
            errors.append(f"unexpected no-lane code: {e.code}")
        if e.reason != "no hybrid lane: playwright unavailable and no AB session provided":
            errors.append(f"pinned no-lane reason drifted: {e.reason!r}")

    # 11. hybrid probed true but no cdp_url and no AB -> fail closed, named
    try:
        route_drag("form", "A", "B", capability=CAP_HYBRID)
        errors.append("cdp-less hybrid route_drag did NOT raise")
    except IframeDragError as e:
        if e.code != "iframe-drag-unavailable" or "no cdp_url" not in e.reason:
            errors.append(f"cdp-less hybrid fail-closed wrong: {e}")

    # 12. AB lane without a session id -> fail closed
    try:
        route_drag("form", "A", "B", capability=CAP_AB, ab=fake_ab, ev=fake_ev_ok)
        errors.append("session-less AB route_drag did NOT raise")
    except IframeDragError as e:
        if e.code != "iframe-drag-unavailable" or "session" not in e.reason:
            errors.append(f"session-less fail-closed wrong: {e}")

    # 13. ambiguous selector list without an index -> fail closed
    try:
        route_drag("form", "A", "B", capability=CAP_AB, ab=fake_ab, ev=fake_ev_ok,
                   session="s", iframe_selector=["iframe#one", "iframe#two"])
        errors.append("ambiguous selector list did NOT raise")
    except IframeDragError as e:
        if e.code != "iframe-ambiguous" or "candidates" not in e.reason:
            errors.append(f"ambiguity fail-closed wrong: {e}")

    # 14. snapshot with MULTIPLE builder iframes and no index -> fail closed
    snap2 = ('<iframe src="https://x.leadconnectorhq.com/form-builder-v2/aaa"></iframe>'
             '<iframe src="https://x.leadconnectorhq.com/form-builder-v2/bbb"></iframe>')
    try:
        route_drag("form", "A", "B", capability=CAP_HYBRID, cdp_url="ws://selftest",
                   snapshot_text=snap2, frame_epoch=get_frame_epoch())
        errors.append("double builder iframe without index did NOT raise")
    except IframeDragError as e:
        if e.code != "iframe-ambiguous":
            errors.append(f"snapshot ambiguity fail-closed wrong: {e}")

    # 15. STALE epoch -> fail closed before any lane is touched
    old = get_frame_epoch()
    bump_frame_epoch()
    CDP_CALLS.clear()
    try:
        route_drag("form", "A", "B", capability=CAP_HYBRID, cdp_url="ws://selftest",
                   frame_epoch=old)
        errors.append("stale frame_epoch did NOT raise")
    except IframeDragError as e:
        if e.code != "iframe-refs-stale":
            errors.append(f"stale-epoch fail-closed wrong: {e}")
    if CDP_CALLS:
        errors.append("a stale-epoch call must never reach a lane")

    # 16. unknown kind -> unknown-iframe-kind (sibling contract, raise-through)
    try:
        route_drag("page", "A", "B", capability=CAP_HYBRID, cdp_url="ws://selftest")
        errors.append("unknown kind did NOT raise")
    except IframeDragError as e:
        if e.code != "unknown-iframe-kind":
            errors.append(f"unknown-kind fail-closed wrong: {e}")

    # 17. detect_iframes — offline snapshot classification + honest unavailability
    det = detect_iframes(snapshot_text=snap2)
    if det.get("source") != "snapshot" or len(det.get("iframes", [])) != 2:
        errors.append(f"detect_iframes snapshot count wrong: {det}")
    if any(d.get("kind") != "form" for d in det["iframes"]):
        errors.append(f"detect_iframes kind classification wrong: {det}")
    det1 = detect_iframes(snapshot_text='<iframe src="https://page-builder.leadconnectorhq.com/x"></iframe>')
    if det1["iframes"][0]["kind"] != "page_code":
        errors.append(f"page_code marker misclassified: {det1}")
    det0 = detect_iframes(snapshot_text="<p>no iframes here</p>")
    if det0["iframes"] != []:
        errors.append(f"iframe-free snapshot should classify empty: {det0}")
    try:
        detect_iframes()
        errors.append("detect_iframes with no inputs did NOT raise")
    except IframeDragError as e:
        if e.code != "iframe-detect-unavailable":
            errors.append(f"detect no-input fail-closed wrong: {e}")

    # 18. epoch helpers
    if bump_frame_epoch() != get_frame_epoch():
        errors.append("bump_frame_epoch != get_frame_epoch after bump")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — decision matrix (CDP/AB-degrade/AB-only), raise-through, "
          "fail-closed (unavailable/ambiguous/stale/unknown-kind), honest AB negatives, "
          "epoch discipline + snapshot detection (offline, injectable fakes)")
    return 0


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="iframe_router",
        description="The single adaptive iframe entrypoint for Skill 6 — picks "
                    "the AB ladder vs Playwright CDP from the host capability "
                    "probe, fails closed when no honest lane exists.")
    p.add_argument("--selftest", action="store_true",
                   help="Offline structural proof (injectable fakes; no "
                        "Playwright/browser/network). Exit 0 = all contracts hold.")
    p.add_argument("--dry", action="store_true",
                   help="Print the lane DECISION for --kind (no live calls).")
    p.add_argument("--kind", default="form",
                   help="Builder kind: form | survey | page_code")
    p.add_argument("--tile", default="State", help="Drag-source tile text (dry info)")
    p.add_argument("--target", default="Submit", help="Drop landmark text (dry info)")
    p.add_argument("--iframe-selector", default=None,
                   help="Explicit iframe selector override (dry info)")
    p.add_argument("--capability-path", default=None,
                   help="Alternate capability probe JSON (default: working/skill6-capability.json)")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.dry:
        cap, cap_source = _capability_from(None, args.capability_path)
        cap_available = _flag_true((cap.get("iframeDrag") or {}).get("available"))
        pw_ready = _DRAG is not None and bool(getattr(_DRAG, "PLAYWRIGHT_AVAILABLE", False))
        try:
            sel, _ = _resolve_selector(args.kind, iframe_selector=args.iframe_selector)
            if cap_available and pw_ready:
                lane = "playwright-cdp (needs cdp_url from `agent-browser get cdp-url`)"
            elif cap_available:
                lane = "playwright-cdp blocked: Playwright unavailable (ghl_iframe_drag flag)"
            else:
                lane = "ab-ladder (capability.iframeDrag.available is not true)"
            print(json.dumps({
                "ok": True, "mode": "dry", "router": IFRAME_ROUTER_VERSION,
                "kind": args.kind, "tile_text": args.tile,
                "target_text": args.target, "iframe_selector": sel,
                "iframeDrag.available": cap_available,
                "playwright_ready": pw_ready, "would_route_to": lane,
                "capability_source": cap_source,
                "frame_epoch": get_frame_epoch(),
            }))
        except IframeDragError as exc:
            print(json.dumps({"ok": False, "mode": "dry", "kind": args.kind,
                              "error": exc.code, "reason": exc.reason}))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
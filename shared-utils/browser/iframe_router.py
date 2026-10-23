#!/usr/bin/env python3
"""shared-utils/browser/iframe_router.py — canonical tab/frame/capability
safeguards for GHL builder automation (W3B; spec gap 3).

WHY THIS EXISTS
---------------
Spec gap 3: "Helper calls bypass adaptive target / fresh-frame / capability
checks; never pick the first browser tab when the intended account/page is
ambiguous." This module is the single guarded entrypoint those helpers must
route through. It enforces, fail-closed, in order:

  1. TARGET  — the intended account/page must be EXACTLY identified. A spec
     with no identifying fields is refused outright, and when more than one
     open tab matches the spec the router raises `tab-ambiguous` listing the
     candidates. There is NO first-tab fallback anywhere in this module.
  2. CAPABILITY — a probed capability flag must read as literally available
     before any lane opens. Absent probe, read error, or a stringy "false"
     all fail closed with `capability-unavailable` / `capability-unreadable`.
  3. FRESH FRAME — the caller must declare the frame generation it snapshotted
     (`frame_epoch`). Any navigation / panel open / second save bumps the
     epoch; acting on a stale generation raises `iframe-refs-stale`.
  4. FRAME — the frame itself is selected exactly (explicit index, or a
     selector matching exactly one frame). N > 1 candidates with no explicit
     index raises `frame-ambiguous`.

FAIL-CLOSED CODES (IframeRouteError, .code/.reason/.details):
  tab-unspecified-target   no identifying field given — identity unverifiable
  tab-not-found            spec matched zero tabs
  tab-ambiguous            spec matched > 1 tab (candidates listed; NEVER a
                           silent first-tab pick)
  frame-not-found          selector/index matched zero frames
  frame-ambiguous          > 1 frame matched and no explicit index
  iframe-refs-stale        caller's frame_epoch predates the current epoch
  capability-unavailable   probed flag missing or not literally available
  capability-unreadable    capability document present but unreadable

CONTRACT: every resolver returns ONLY on an exact, verified match. Ambiguity
is an error, never a guess. This module is stdlib-only, never imports
Playwright, never opens a browser, and its --selftest runs fully offline.

USAGE
-----
    import iframe_router as ir

    tab = ir.select_tab(tab_inventory, ir.TargetSpec(
        account_id="acc_123", page_id="pg_456"))     # raises on ambiguity
    ir.require_capability(cap_doc, "iframeDrag")      # raises when gated
    frame = ir.select_frame(frames, index=0)          # exact selection

    # or the one-shot guarded path helpers must use:
    resolved = ir.guarded_resolve(
        tabs=tab_inventory, frames=frame_list, capability=cap_doc,
        spec=ir.TargetSpec(account_id="acc_123", page_id="pg_456"),
        frame_index=0, frame_epoch=ir.get_frame_epoch())

    python3 shared-utils/browser/iframe_router.py --selftest
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

IFRAME_ROUTER_VERSION = "v1.0.0"

# Truthiness for probe flags: a stringy "false" must never read as available.
_TRUTHY = ("1", "true", "yes")


class IframeRouteError(RuntimeError):
    """Fail-closed router error. Shape-compatible (.code/.reason/.details)
    with the skill-06 IframeDragError contract so adapter call sites can
    classify either with the same except clause."""

    def __init__(self, code: str, reason: str,
                 details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.reason = reason
        self.details = details or {}
        super().__init__(f"{code}: {reason}")


# ---------------------------------------------------------------------------
# Target identity — the intended account/page/tab. At least ONE identifying
# field is mandatory: an empty spec can never verify which tab is meant, so it
# is refused before any tab list is even consulted.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TargetSpec:
    """What the caller means by 'the tab'. Identifying fields are ANDed."""
    account_id: Optional[str] = None   # GHL account / agency
    location_id: Optional[str] = None  # GHL location
    page_id: Optional[str] = None      # page/funnel/site node identity
    url_marker: Optional[str] = None   # substring that must appear in tab URL
    tab_id: Optional[str] = None       # explicit browser tab id

    def identifying_fields(self) -> Dict[str, str]:
        return {k: v for k, v in (
            ("account_id", self.account_id),
            ("location_id", self.location_id),
            ("page_id", self.page_id),
            ("url_marker", self.url_marker),
            ("tab_id", self.tab_id),
        ) if v is not None and str(v).strip() != ""}

    def matches(self, tab: "TabCandidate") -> bool:
        """True only when EVERY identifying field matches this tab exactly
        (url_marker is a substring match on the URL)."""
        f = self.identifying_fields()
        for key, want in f.items():
            if key == "url_marker":
                if want not in (tab.url or ""):
                    return False
            else:
                if str(getattr(tab, key, None) or "") != str(want):
                    return False
        return True


@dataclass(frozen=True)
class TabCandidate:
    """One open browser tab as reported by the harness inventory."""
    tab_id: str
    url: str = ""
    title: str = ""
    account_id: Optional[str] = None
    location_id: Optional[str] = None
    page_id: Optional[str] = None


def select_tab(tabs: Sequence[TabCandidate], spec: TargetSpec) -> TabCandidate:
    """Resolve EXACTLY one tab, or fail closed.

    There is no fallback: an unspecified target, a zero match, and an
    ambiguous match each raise their own error. tabs[0] is never returned
    unless it is the unique verified match of a fully identified spec.
    """
    fields = spec.identifying_fields()
    if not fields:
        raise IframeRouteError(
            "tab-unspecified-target",
            "refusing to choose a tab: TargetSpec carries no identifying "
            "field (account_id/location_id/page_id/url_marker/tab_id) — the "
            "intended account/page is unverifiable, so no tab (including the "
            "first) may be selected",
            {"tab_count": len(list(tabs))})
    if not tabs:
        raise IframeRouteError(
            "tab-not-found",
            "no open tabs in the inventory to match against",
            {"wanted": fields})
    matches = [t for t in tabs if spec.matches(t)]
    if not matches:
        raise IframeRouteError(
            "tab-not-found",
            f"no open tab matches {fields}",
            {"wanted": fields,
             "seen": [{"tab_id": t.tab_id, "url": t.url} for t in tabs]})
    if len(matches) > 1:
        raise IframeRouteError(
            "tab-ambiguous",
            f"{len(matches)} open tabs match {fields} — the intended "
            "account/page is ambiguous; narrow the spec (add page_id, "
            "location_id or an exact tab_id). The router never picks the "
            "first tab.",
            {"wanted": fields,
             "candidates": [{"tab_id": t.tab_id, "url": t.url,
                             "account_id": t.account_id,
                             "page_id": t.page_id} for t in matches]})
    return matches[0]


# ---------------------------------------------------------------------------
# Frame selection — exact only. An explicit index selects by position; a
# selector must resolve to exactly one frame. Never "first frame".
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FrameCandidate:
    frame_id: str
    selector: str = ""
    src: str = ""
    kind: Optional[str] = None  # 'form' | 'survey' | 'page_code' | None


def select_frame(frames: Sequence[FrameCandidate],
                 index: Optional[int] = None,
                 selector: Optional[str] = None,
                 kind: Optional[str] = None) -> FrameCandidate:
    """Resolve EXACTLY one frame, or fail closed.

    index given   → exact positional selection over the candidate list
                    (a selector/kind, when also given, must match that frame).
    selector/kind → the matching set must contain exactly ONE frame.
    neither       → refused: an unqualified frame choice is a guess.
    """
    pool = list(frames)
    if not pool:
        raise IframeRouteError(
            "frame-not-found",
            "no frames in the inventory to select from",
            {"selector": selector, "kind": kind, "index": index})

    if index is not None:
        if index < 0 or index >= len(pool):
            raise IframeRouteError(
                "frame-not-found",
                f"frame index {index} out of range (0..{len(pool) - 1})",
                {"frame_count": len(pool)})
        chosen = pool[index]
        if selector is not None and chosen.selector != selector:
            raise IframeRouteError(
                "frame-not-found",
                f"frame at index {index} has selector {chosen.selector!r}, "
                f"not the declared {selector!r} — refusing a mismatched pick",
                {"index": index, "want": selector,
                 "got": chosen.selector})
        if kind is not None and chosen.kind not in (None, kind):
            raise IframeRouteError(
                "frame-not-found",
                f"frame at index {index} is kind {chosen.kind!r}, not "
                f"{kind!r} — refusing a mismatched pick",
                {"index": index, "want": kind, "got": chosen.kind})
        return chosen

    if selector is None and kind is None:
        raise IframeRouteError(
            "frame-ambiguous",
            "no frame index, selector or kind declared — with "
            f"{len(pool)} frame(s) present the router cannot verify which "
            "frame is meant and will not pick the first",
            {"frame_count": len(pool)})

    matches = [f for f in pool
               if (selector is None or f.selector == selector)
               and (kind is None or f.kind == kind)]
    if not matches:
        raise IframeRouteError(
            "frame-not-found",
            f"no frame matches selector={selector!r} kind={kind!r}",
            {"selector": selector, "kind": kind,
             "seen": [{"frame_id": f.frame_id, "selector": f.selector,
                       "kind": f.kind} for f in pool]})
    if len(matches) > 1:
        raise IframeRouteError(
            "frame-ambiguous",
            f"{len(matches)} frames match selector={selector!r} kind="
            f"{kind!r} and no explicit index was declared — the router "
            "will not pick the first; pass frame_index=",
            {"selector": selector, "kind": kind,
             "candidates": [{"frame_id": f.frame_id, "src": f.src,
                             "kind": f.kind} for f in matches]})
    return matches[0]


# ---------------------------------------------------------------------------
# Capability gate — probed availability only. Absence is never availability.
# ---------------------------------------------------------------------------
def _flag_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY
    return bool(value)


def require_capability(capability: Optional[Dict[str, Any]],
                       name: str) -> Dict[str, Any]:
    """Gate on capability.<name>.available, fail-closed.

    capability None/{}    → capability-unavailable (no probe = not available)
    probe read error key  → capability-unreadable (corruption is visible)
    flag missing/false    → capability-unavailable (stringy "false" included)
    """
    if capability is None:
        raise IframeRouteError(
            "capability-unavailable",
            f"no capability probe supplied — {name!r} cannot be assumed "
            "available without one",
            {"capability": name})
    if not isinstance(capability, dict):
        raise IframeRouteError(
            "capability-unreadable",
            f"capability probe is {type(capability).__name__}, not a dict",
            {"capability": name})
    if "_read_error" in capability:
        raise IframeRouteError(
            "capability-unreadable",
            f"capability probe unreadable: {capability['_read_error']}",
            {"capability": name})
    entry = capability.get(name)
    if not isinstance(entry, dict):
        raise IframeRouteError(
            "capability-unavailable",
            f"capability probe has no {name!r} entry — not available",
            {"capability": name, "probe_keys": sorted(capability)})
    if not _flag_true(entry.get("available")):
        raise IframeRouteError(
            "capability-unavailable",
            f"capability {name!r} probed available="
            f"{entry.get('available')!r} — lane stays closed",
            {"capability": name, "probed": entry})
    return entry


# ---------------------------------------------------------------------------
# Frame-epoch discipline (fresh-frame check) — callers snapshot frames at a
# generation and must act at that same generation. Anything that invalidates
# frame refs (navigation, panel open, second save) bumps the epoch.
# ---------------------------------------------------------------------------
_FRAME_EPOCH = 0


def get_frame_epoch() -> int:
    return _FRAME_EPOCH


def bump_frame_epoch() -> int:
    global _FRAME_EPOCH
    _FRAME_EPOCH += 1
    return _FRAME_EPOCH


def require_current_epoch(frame_epoch: Optional[int]) -> None:
    if frame_epoch is None:
        return
    if int(frame_epoch) != _FRAME_EPOCH:
        raise IframeRouteError(
            "iframe-refs-stale",
            f"caller declared frame_epoch {frame_epoch} but the router is at "
            f"epoch {_FRAME_EPOCH} — frame refs were invalidated; re-snapshot, "
            "bump_frame_epoch(), and retry with the current epoch",
            {"declared": int(frame_epoch), "current": _FRAME_EPOCH})


# ---------------------------------------------------------------------------
# guarded_resolve — the ONE entrypoint helper calls must use. Runs target →
# capability → fresh-frame → frame in that order and returns the verified
# selection. A helper cannot reach a tab or frame without passing every gate.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolvedTarget:
    tab: TabCandidate
    frame: FrameCandidate
    frame_epoch: int
    capability: Dict[str, Any] = field(default_factory=dict)


def guarded_resolve(*,
                    tabs: Sequence[TabCandidate],
                    frames: Sequence[FrameCandidate],
                    capability: Optional[Dict[str, Any]],
                    spec: TargetSpec,
                    frame_index: Optional[int] = None,
                    frame_selector: Optional[str] = None,
                    frame_kind: Optional[str] = None,
                    frame_epoch: Optional[int] = None,
                    capability_name: str = "iframeDrag") -> ResolvedTarget:
    """Exact target + capability + fresh-frame + frame resolution, fail-closed.

    Order matters: identity is verified before any lane is gated, and the
    frame is only selected at the caller's declared generation.
    """
    tab = select_tab(tabs, spec)                      # never first-tab
    cap = require_capability(capability, capability_name)
    require_current_epoch(frame_epoch)                # stale → refuse
    frame = select_frame(frames, index=frame_index,
                         selector=frame_selector, kind=frame_kind)
    return ResolvedTarget(tab=tab, frame=frame,
                          frame_epoch=_FRAME_EPOCH, capability=cap)


# ---------------------------------------------------------------------------
# Offline self-check — assert-based, no network, no browser, no Playwright.
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import traceback

    t1 = TabCandidate("tab-1", url="https://app.gohighlevel.com/v2/location/agencyA",
                      account_id="accA", location_id="locA", page_id="pg1")
    t2 = TabCandidate("tab-2", url="https://app.gohighlevel.com/v2/location/agencyB",
                      account_id="accB", location_id="locB", page_id="pg2")
    t3 = TabCandidate("tab-3", url="https://app.gohighlevel.com/v2/location/agencyA/edit",
                      account_id="accA", location_id="locA", page_id="pg3")
    inv: List[TabCandidate] = [t1, t2, t3]

    f1 = FrameCandidate("fr-1", selector='iframe[src*="form-builder-v2"]',
                        kind="form")
    f2 = FrameCandidate("fr-2", selector='iframe[src*="form-builder-v2"]',
                        kind="form")
    f3 = FrameCandidate("fr-3", selector='iframe[src*="page-builder"]',
                        kind="page_code")
    frames: List[FrameCandidate] = [f1, f2, f3]

    checks: List[str] = []

    def ok(name: str) -> None:
        checks.append(name)

    # --- tab: empty spec is refused even with exactly one tab (no first-tab).
    for pool in (inv, [t1]):
        try:
            select_tab(pool, TargetSpec())
        except IframeRouteError as exc:
            assert exc.code == "tab-unspecified-target", exc.code
        else:
            raise AssertionError("empty TargetSpec must never select a tab")
    ok("tab-unspecified-target refused (multi and single tab)")

    # --- tab: unique exact match wins even when NOT the first tab.
    got = select_tab(inv, TargetSpec(account_id="accB", page_id="pg2"))
    assert got is t2, "must resolve tab-2, not tabs[0]"
    ok("unique match resolves non-first tab")

    # --- tab: url_marker substring matching.
    got = select_tab(inv, TargetSpec(account_id="accA", url_marker="/edit"))
    assert got is t3
    ok("url_marker narrows within one account")

    # --- tab: ambiguous account → refuse, never tabs[0].
    try:
        select_tab(inv, TargetSpec(account_id="accA"))
    except IframeRouteError as exc:
        assert exc.code == "tab-ambiguous", exc.code
        assert exc.details["candidates"][0]["tab_id"] == "tab-1"
    else:
        raise AssertionError("two accA tabs must be tab-ambiguous")
    ok("ambiguous account refused with candidates listed")

    # --- tab: zero match.
    try:
        select_tab(inv, TargetSpec(account_id="accZ"))
    except IframeRouteError as exc:
        assert exc.code == "tab-not-found", exc.code
    else:
        raise AssertionError("unknown account must be tab-not-found")
    ok("zero-match is tab-not-found")

    # --- tab: empty inventory.
    try:
        select_tab([], TargetSpec(account_id="accA"))
    except IframeRouteError as exc:
        assert exc.code == "tab-not-found", exc.code
    else:
        raise AssertionError("empty inventory must fail closed")
    ok("empty inventory fails closed")

    # --- frame: explicit index selects exactly (and it is #2, not #1).
    got = select_frame(frames, index=1)
    assert got is f2
    ok("explicit frame index selects exactly")

    # --- frame: index out of range.
    try:
        select_frame(frames, index=7)
    except IframeRouteError as exc:
        assert exc.code == "frame-not-found", exc.code
    else:
        raise AssertionError("out-of-range index must fail")
    ok("out-of-range frame index fails")

    # --- frame: two form-builder frames, no index → ambiguous.
    try:
        select_frame(frames, kind="form")
    except IframeRouteError as exc:
        assert exc.code == "frame-ambiguous", exc.code
    else:
        raise AssertionError("2 form frames without index must be ambiguous")
    ok("selector-match without index is frame-ambiguous")

    # --- frame: kind unique → resolved.
    got = select_frame(frames, kind="page_code")
    assert got is f3
    ok("unique kind match resolves")

    # --- frame: no index/selector/kind → refused even with 1 frame.
    try:
        select_frame([f1])
    except IframeRouteError as exc:
        assert exc.code == "frame-ambiguous", exc.code
    else:
        raise AssertionError("unqualified frame choice must be refused")
    ok("unqualified frame choice refused")

    # --- frame: index + mismatched declared selector → refuse.
    try:
        select_frame(frames, index=2,
                     selector='iframe[src*="form-builder-v2"]')
    except IframeRouteError as exc:
        assert exc.code == "frame-not-found", exc.code
    else:
        raise AssertionError("index/selector mismatch must fail")
    ok("index/selector mismatch refused")

    # --- capability: missing probe, empty probe, stringy false all closed.
    for bad in (None, {}, {"iframeDrag": {}},
                {"iframeDrag": {"available": "false"}},
                {"iframeDrag": {"available": False}}):
        try:
            require_capability(bad, "iframeDrag")
        except IframeRouteError as exc:
            assert exc.code == "capability-unavailable", (bad, exc.code)
        else:
            raise AssertionError(f"capability must stay closed for {bad!r}")
    ok("capability fail-closed on missing/false probe")

    # --- capability: read error surfaces as unreadable.
    try:
        require_capability({"_read_error": "JSONDecodeError: x"},
                           "iframeDrag")
    except IframeRouteError as exc:
        assert exc.code == "capability-unreadable", exc.code
    else:
        raise AssertionError("read error must be capability-unreadable")
    ok("capability read error is capability-unreadable")

    # --- capability: literal true (and truthy string) opens.
    cap = {"iframeDrag": {"available": True}}
    assert require_capability(cap, "iframeDrag") is cap["iframeDrag"]
    assert require_capability({"iframeDrag": {"available": "true"}},
                              "iframeDrag")
    ok("capability opens only on literal availability")

    # --- epoch: stale declaration refused.
    e0 = get_frame_epoch()
    e1 = bump_frame_epoch()
    assert e1 == e0 + 1
    try:
        require_current_epoch(e0)
    except IframeRouteError as exc:
        assert exc.code == "iframe-refs-stale", exc.code
    else:
        raise AssertionError("stale epoch must be refused")
    require_current_epoch(e1)  # current declared epoch passes
    require_current_epoch(None)  # undeclared epoch is not a stale claim
    ok("stale frame_epoch refused; current passes")

    # --- guarded_resolve: full happy path at the current epoch.
    cur = get_frame_epoch()
    res = guarded_resolve(tabs=inv, frames=frames, capability=cap,
                          spec=TargetSpec(account_id="accB", page_id="pg2"),
                          frame_index=1, frame_epoch=cur)
    assert res.tab is t2 and res.frame is f2 and res.frame_epoch == cur
    assert res.capability is cap["iframeDrag"]
    ok("guarded_resolve happy path returns exact tab+frame")

    # --- gated_resolve order: ambiguous tab refuses BEFORE any lane use.
    try:
        guarded_resolve(tabs=inv, frames=frames, capability=cap,
                        spec=TargetSpec(account_id="accA"),
                        frame_index=0, frame_epoch=cur)
    except IframeRouteError as exc:
        assert exc.code == "tab-ambiguous", exc.code
    else:
        raise AssertionError("guarded_resolve must refuse ambiguous tab")
    ok("guarded_resolve refuses ambiguous target")

    # --- guarded_resolve: capability closed blocks even with exact tab/frame.
    try:
        guarded_resolve(tabs=inv, frames=frames,
                        capability={"iframeDrag": {"available": False}},
                        spec=TargetSpec(account_id="accB", page_id="pg2"),
                        frame_index=1, frame_epoch=cur)
    except IframeRouteError as exc:
        assert exc.code == "capability-unavailable", exc.code
    else:
        raise AssertionError("closed capability must block the lane")
    ok("guarded_resolve enforces capability gate")

    # --- guarded_resolve: stale epoch blocks the frame selection.
    try:
        guarded_resolve(tabs=inv, frames=frames, capability=cap,
                        spec=TargetSpec(account_id="accB", page_id="pg2"),
                        frame_index=1, frame_epoch=cur - 1)
    except IframeRouteError as exc:
        assert exc.code == "iframe-refs-stale", exc.code
    else:
        raise AssertionError("stale epoch must block guarded_resolve")
    ok("guarded_resolve enforces fresh-frame epoch")

    for name in checks:
        print(f"ok - {name}")
    print(f"SELFTEST PASS ({len(checks)} checks)")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(argv if argv is not None else __import__("sys").argv[1:])
    if "--selftest" in args:
        try:
            return _selftest()
        except AssertionError:
            import traceback
            traceback.print_exc()
            print("SELFTEST FAIL")
            return 1
    if "--version" in args:
        print(IFRAME_ROUTER_VERSION)
        return 0
    print("usage: iframe_router.py --selftest | --version")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

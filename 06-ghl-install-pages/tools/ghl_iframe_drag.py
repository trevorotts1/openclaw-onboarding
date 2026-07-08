#!/usr/bin/env python3
"""ghl_iframe_drag.py — SHARED, reusable frame-scoped coordinate-drag primitive
for EVERY Skill-6 GoHighLevel (Convert and Flow) builder surface.

WHY THIS EXISTS (the bug it fixes)
----------------------------------
The GHL visual builders (FORM, SURVEY, and the PAGE/FUNNEL "Code" element) render
inside a CROSS-ORIGIN iframe embedded in the ``app.convertandflow.com`` shell:

  • Forms   → ``leadgen-apps-form-survey-builder.leadconnectorhq.com/form-builder-v2/<id>``
  • Surveys → ``leadgen-apps-form-survey-builder.leadconnectorhq.com/survey-builder-v2/<id>``
  • Pages   → ``page-builder.leadconnectorhq.com`` (Quick-Add "Code" tile; gates.json)

``agent-browser`` (the Skill-6 PRIMARY engine, v0.27.0) auto-inlines the iframe's
ACCESSIBILITY tree into a top-frame snapshot and gives CDP ``@ref``s to real
interactive ARIA leaves (buttons / textboxes / links / menuitems) — those work.
But the drag-SOURCE tiles (Quick-Add field tiles, Add-Object-Field rows) are
NON-interactive ``generic`` / ``StaticText`` nodes with NO ref, and neither
``text=`` / CSS / ``find text`` NOR the ``frame`` verb can REACH ACROSS the
cross-origin boundary to grab them. VERIFIED LIVE (SELECTORS-LIVE-form.md §7:
``drag text=State`` / ``find text 'Add Object Fields'`` → *Element not found*) and
re-verified against a two-origin fixture during this fix:

  * ``agent-browser frame @eN`` only re-scopes the READ-ONLY a11y snapshot; after
    switching, ``eval`` STILL runs in the TOP frame (``document.getElementById``
    of an in-iframe node → false) and ``find`` / ``drag`` / ``get`` STILL bind to
    the top frame. There is no ``--frame`` flag on ``eval``. So agent-browser
    0.27.0 has NO working frame-scoping primitive for LOCATING or DRAGGING a
    non-interactive element inside a cross-origin child frame.

THE FIX (hybrid: agent-browser PRIMARY, Playwright for JUST the drag)
---------------------------------------------------------------------
This is NOT a "drag is unsupported" problem — it is a "cannot LOCATE the source
across a cross-origin iframe" problem. Playwright solves exactly that with
first-class frame-scoped locators. The architecture keeps everything
agent-browser already does well (Firebase-token login injection, navigation,
button/field clicks) and uses Playwright ONLY for the frame-scoped
coordinate-drag step:

  1. agent-browser owns + drives the ONE seeded, logged-in Chromium (the singleton
     pooled-browser gateway). Its CDP endpoint is read with ``get cdp-url``.
  2. Playwright ``chromium.connect_over_cdp(<cdp_url>)`` ATTACHES to that SAME
     already-running, already-authenticated Chromium — ONE browser, ONE login,
     zero duplicate auth (the Firebase-token login is tool-agnostic; nothing here
     re-logs-in).
  3. ``page.frame_locator(<iframe_selector>).locator(<source>).bounding_box()``
     resolves TRUE page/viewport coordinates for the tile EVEN across the
     cross-origin boundary (bounding-box math is not blocked by same-origin
     policy — only scripted DOM access is).
  4. The drag is performed as a RAW page-level synthetic MOUSE sequence
     (``mouse.move`` → ``mouse.down`` → many INTERPOLATED ``mouse.move`` steps →
     settle → ``mouse.up``). Raw pointer input is NOT tied to any specific JS
     event a developer chose to listen for, so it drives GHL's own
     pointer-distance drag sensor regardless of whether the builder uses the
     native HTML5 Drag-and-Drop API or a custom mousedown-based dragger — and it
     crosses the iframe boundary the same way a real human mouse would. This
     mirrors gates.json ``playwright_fallback_recipes.code_element_drag_drop``
     (>= 20 interpolated moves, ~16 ms apart; a single down->up move does NOT trip
     the sensor).

GENERAL / DURABLE — NOT A FORMS-ONLY ONE-OFF
--------------------------------------------
``coordinate_drag`` is builder-AGNOSTIC: it is parameterized by (iframe selector,
source locator, target locator) so ANY current or future Skill-6 script can import
and call it. It is wired into the FORM builder (``ghl_form_builder.py``) and the
SURVEY builder (``ghl_survey_builder.py``) by this fix; the PAGE/FUNNEL "Code"
element drag (gates.json recipe, currently REST-served so not yet a live drag) can
be wired to the SAME primitive when that path goes live.

SCROLL-INTO-VIEW + CATEGORY-HINT LOCATE (v1.1.0 — the ``F5.locate:City`` fix)
-----------------------------------------------------------------------------
The Quick-Add panel is a SCROLLABLE column of category sections (SELECTORS-LIVE-
form.md §8: Personal Info · Submit · Payments · Address · Text · Choice · Rating ·
Customized · Other). A tile in a category below the fold (live 2026-07-07:
``City`` under ``Address``) is NOT on screen at drag time, so the old flow either
missed it in the a11y snapshot (→ a false ``F5.locate`` STOP) or aimed the pointer
at off-viewport coordinates. Fix, for ANY field in ANY category (never a
City-only patch):
  • ``drive_drag`` now calls Playwright's ``scroll_into_view_if_needed()`` on BOTH
    the source tile and the drop target BEFORE reading their bounding boxes
    (actionability-aware; no-op when already fully visible per IntersectionObserver
    — playwright.dev/python docs, verified 2026-07-07).
  • ``source_scroll_hint`` (e.g. the tile's CATEGORY header text ``"Address"``):
    when the source cannot be located/scrolled directly, the hint element is
    scrolled into view FIRST (revealing its section), then the source is retried.
    Fail-closed at every step — a tile that genuinely does not exist still raises
    ``source-not-found``.

VISIBLE-MATCH RESOLUTION + ROLE/PLACEHOLDER SPECS + FIELD REMOVE (v1.2.0)
-------------------------------------------------------------------------
Live 2026-07-08 (attempt #5 against a real account): the drop target
``text=Submit`` timed out (``target-not-found``) even though the canvas Submit
button was on screen — inside the builder iframe that text ALSO matches the
Quick-Add panel's 'Submit' CATEGORY header + its 'Submit' tile (SELECTORS-LIVE-
form.md §8), and the blind ``.first`` bound to a HIDDEN match. Three durable
fixes, none Submit-specific:
  • ``_resolve_visible``: source/target resolution scans ALL matches in DOM
    order and binds the FIRST VISIBLE one (poll/wait fallback preserved);
    honest fail-closed codes now carry attached-match diagnostics.
  • New locator specs: ``role=<role>:<name>`` (``get_by_role(..., exact=True)``
    — the same class of fix as the F2 'Create' collision; SELECTORS §5 locks
    the canvas Submit as role=button) and ``placeholder=<text>`` (§6 — the
    documented per-field canvas anchors).
  • ``drive_remove_canvas_field`` / ``remove_canvas_field``: the F4 default-
    field reconciliation primitive — select the canvas field by its documented
    anchor, click the per-field ``role=link 'Remove field'`` control (§6), and
    prove the removal by a COUNT-DECREASE of the field's own anchor (mirror of
    the v1.1.1 count-delta placement proof). 0 matches = a truthful idempotent
    already-absent no-op; everything else fails closed.

FRAME-SCOPED INLINE-TITLE READ/SET (v1.1.0 — the F3 rename fix)
----------------------------------------------------------------
The builder's title ("Form 55" / "Survey 0") is an in-iframe INLINE-EDIT surface
— not a top-frame input — so agent-browser's top-frame ``dblclick``/``fill`` can
never reach it (same cross-origin constraint as the drag). ``set_inline_title``
attaches over the SAME CDP session and, inside the iframe: locates the title by a
PATTERN list (regex-capable — the default number in "Form <n>" is unknowable),
clicks (then double-clicks) it into edit mode, VERIFIES an editable element
actually took focus (fail-closed ``title-not-editable`` otherwise), selects-all
(``ControlOrMeta+A``), types the new title, commits (Enter), and VERIFIES the new
text is present in the iframe (fail-closed ``title-not-set``). ``read_inline_title``
returns the CURRENT title text so cleanup can positively target the form by the
name it ACTUALLY carries even when the rename failed.

HEADLESS (D6): this module NEVER opens a visible window. The live path attaches to
agent-browser's already-headless Chromium via CDP; the self-test's own browser
uses ``launch_persistent_context(..., headless=True)`` (never a bare ``launch()``,
never ``headless=False``).

FAIL-CLOSED: a source/target that cannot be located, a null bounding box, a
missing page/frame, or an unavailable Playwright all raise :class:`IframeDragError`
— the caller converts that to its own STOP-and-report. This primitive NEVER fakes
a successful placement.

USAGE
-----
    from ghl_iframe_drag import coordinate_drag, IframeDragError
    res = coordinate_drag(
        cdp_url,                                   # from `agent-browser get cdp-url`
        iframe_selector='iframe[src*="form-builder-v2"]',
        source="text=State",                       # visible-text tile in the iframe
        target="text=Submit",                      # canvas drop landmark in the iframe
        url_marker="form-builder",                 # pick the builder tab/page
        verify_text="State",                       # confirm it landed on the canvas
    )

    python3 ghl_iframe_drag.py --selftest        # dep-free structural proof (CI-safe)
    python3 ghl_iframe_drag.py --live-selftest   # real Playwright + local 2-origin fixture
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Soft import — the module stays importable (and its dep-free --selftest stays
# runnable) with ZERO Playwright installed. Only the LIVE drag path + the
# --live-selftest require it; both report cleanly when it is absent.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - availability is environment-dependent
    from playwright.sync_api import sync_playwright  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except Exception:  # noqa: BLE001
    sync_playwright = None  # type: ignore
    PLAYWRIGHT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants — the canonical drag-sensor parameters (gates.json
# playwright_fallback_recipes.code_element_drag_drop). A single down->up move does
# NOT trip GHL's pointer-distance drag sensor; >= 20 interpolated moves do.
# ---------------------------------------------------------------------------
IFRAME_DRAG_VERSION = "v1.2.0"
DEFAULT_INTERPOLATED_MOVES = 24     # >= gates.json interpolated_moves_min (20)
DEFAULT_MOVE_INTERVAL_MS = 16       # gates.json move_interval_ms (~16ms / 60fps)
DEFAULT_SETTLE_MS = 250             # settle at the target before releasing
DEFAULT_TIMEOUT_MS = 15000

# Known Skill-6 cross-origin builder iframe selectors (documentation + convenient
# presets; callers may pass any selector). These are the hosts proven to embed a
# cross-origin builder — see the module docstring.
IFRAME_SELECTORS: Dict[str, str] = {
    "form": 'iframe[src*="form-builder-v2"]',
    "survey": 'iframe[src*="survey-builder-v2"]',
    "page_code": 'iframe[src*="page-builder"]',
}


class IframeDragError(RuntimeError):
    """A frame-scoped coordinate-drag could not be completed HONESTLY (source /
    target unlocatable, null bounding box, page/frame missing, Playwright absent,
    or a placement that did not verify). Carries a short ``code`` + human reason so
    the caller can STOP-and-report rather than fake success."""

    def __init__(self, code: str, reason: str):
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


# ---------------------------------------------------------------------------
# Pure helpers (no browser) — unit-testable coordinate math
# ---------------------------------------------------------------------------
def _center(box: Optional[Dict[str, float]]) -> Tuple[float, float]:
    if not box:
        raise IframeDragError(
            "null-bounding-box",
            "the element resolved but has no bounding box (not laid out / zero-size "
            "/ off-screen) — cannot compute drag coordinates; STOP (never guess a point)")
    return (box["x"] + box["width"] / 2.0, box["y"] + box["height"] / 2.0)


def _interpolate(sx: float, sy: float, tx: float, ty: float, steps: int):
    """Yield ``steps`` intermediate points strictly BETWEEN source and target
    (linear). ``steps`` must be >= 1. The final exact-target move is emitted by the
    caller after these, so the pointer crosses the drag-activation distance in many
    small hops (a single jump does not trip GHL's sensor)."""
    steps = max(1, int(steps))
    for i in range(1, steps + 1):
        f = i / (steps + 1)
        yield (sx + (tx - sx) * f, sy + (ty - sy) * f)


def _resolve_locator_all(frame: Any, spec: str) -> Any:
    """Resolve a locator SPEC against a Playwright FrameLocator — UN-NARROWED
    (no ``.first``), so callers can scan every match (see :func:`_resolve_visible`).

    Spec grammar (kept deliberately small; GHL tiles are located by visible text):
      * ``"text=Foo"``  → ``frame.get_by_text("Foo", exact=False)`` (default)
      * ``"exact=Foo"`` → ``frame.get_by_text("Foo", exact=True)``
      * ``"re:PAT"``    → ``frame.get_by_text(re.compile(PAT))`` (regex —
                          needed for pattern-only surfaces like the default
                          builder title ``Form <n>``, whose number is unknowable)
      * ``"css=SEL"``   → ``frame.locator("SEL")``
      * ``"role=R:Name"`` → ``frame.get_by_role("R", name="Name", exact=True)``
                          (v1.2.0 — the F2-'Create'-collision class of fix for
                          AMBIGUOUS visible text: SELECTORS-LIVE-form.md §5 locks
                          the canvas Submit as role=button name='Submit', while
                          plain ``text=Submit`` ALSO matches the Quick-Add panel's
                          'Submit' CATEGORY header + tile — live 2026-07-08)
      * ``"placeholder=P"`` → ``frame.get_by_placeholder("P")`` (v1.2.0 — the
                          documented per-field canvas anchors, SELECTORS §6)
      * bare ``"Foo"``  → treated as ``text=Foo``
    """
    if not spec or not str(spec).strip():
        raise IframeDragError("empty-locator", "a source/target locator spec was empty")
    s = str(spec)
    if s.startswith("css="):
        return frame.locator(s[4:])
    if s.startswith("exact="):
        return frame.get_by_text(s[6:], exact=True)
    if s.startswith("re:"):
        return frame.get_by_text(re.compile(s[3:]))
    if s.startswith("role="):
        body = s[5:]
        role, sep, name = body.partition(":")
        if not sep or not role.strip() or not name.strip():
            raise IframeDragError(
                "bad-role-locator",
                f"role= spec must be 'role=<role>:<accessible name>', got {spec!r}")
        return frame.get_by_role(role.strip(), name=name, exact=True)
    if s.startswith("placeholder="):
        return frame.get_by_placeholder(s[12:])
    if s.startswith("text="):
        return frame.get_by_text(s[5:], exact=False)
    return frame.get_by_text(s, exact=False)


def _resolve_locator(frame: Any, spec: str) -> Any:
    """First match for SPEC (``_resolve_locator_all(...).first``) — kept for the
    single-element surfaces (inline title, scroll hints)."""
    return _resolve_locator_all(frame, spec).first


def _safe_count(loc_all: Any) -> int:
    try:
        return int(loc_all.count())
    except Exception:  # noqa: BLE001
        return -1


def _first_visible_match(loc_all: Any) -> Optional[Any]:
    """Scan the matches of an un-narrowed locator IN DOM ORDER and return the
    first one that is CURRENTLY visible, else None. Never raises — an
    unevaluable candidate simply doesn't count as visible (fail-closed)."""
    try:
        n = int(loc_all.count())
    except Exception:  # noqa: BLE001
        return None
    for i in range(n):
        try:
            cand = loc_all.nth(i)
            if cand.is_visible():
                return cand
        except Exception:  # noqa: BLE001
            continue
    return None


def _resolve_visible(frame: Any, spec: str, *, timeout_ms: int) -> Tuple[Any, int]:
    """Resolve SPEC to a VISIBLE element, robust to AMBIGUOUS matches.

    THE LIVE 2026-07-08 BUG THIS FIXES: a text spec can legitimately match
    several in-iframe nodes (``text=Submit`` matched the Quick-Add panel's
    'Submit' CATEGORY header + its 'Submit' tile + the canvas Submit button —
    SELECTORS-LIVE-form.md §5/§8), and a blind ``.first`` binds to the first
    DOM-order match. When that match is HIDDEN, ``wait_for(state='visible')``
    times out (→ a false ``target-not-found``) even though the real landmark is
    plainly on screen — proven live against the real account (attempt #5).

    Resolution order:
      1. immediate scan → the FIRST currently-visible match wins;
      2. no visible match yet → ``first.wait_for(visible, timeout)`` (the
         pre-existing behavior — correct for unambiguous/slow-rendering specs);
      3. the wait missed → ONE final scan (content may have rendered with a
         hidden first-in-DOM match) → else re-raise the wait's failure.

    Returns ``(locator, attached_match_count)``; the count rides along for
    honest diagnostics. Raises whatever ``wait_for`` raised when nothing
    visible can be resolved (callers wrap it into their own fail-closed code)."""
    loc_all = _resolve_locator_all(frame, spec)
    cand = _first_visible_match(loc_all)
    if cand is not None:
        return cand, _safe_count(loc_all)
    first = loc_all.first
    try:
        first.wait_for(state="visible", timeout=timeout_ms)
        return first, _safe_count(loc_all)
    except Exception:
        cand = _first_visible_match(loc_all)
        if cand is not None:
            return cand, _safe_count(loc_all)
        raise


def _scroll_into_view(loc: Any, *, what: str, spec: str, timeout_ms: int) -> None:
    """Scroll ``loc`` into view via Playwright's actionability-aware
    ``scroll_into_view_if_needed`` (a no-op when the element is already fully
    visible per IntersectionObserver). FAIL-CLOSED: a scroll that cannot complete
    (detached / permanently hidden element) raises :class:`IframeDragError` — the
    pointer must NEVER be aimed at coordinates that were never brought on-screen."""
    try:
        loc.scroll_into_view_if_needed(timeout=timeout_ms)
    except IframeDragError:
        raise
    except Exception as exc:  # noqa: BLE001 - any Playwright timeout/lookup failure
        raise IframeDragError(
            f"{what}-scroll-failed",
            f"{what} {spec!r} resolved but could not be scrolled into view within "
            f"{timeout_ms}ms ({type(exc).__name__}). STOP — never aim the pointer at "
            "an off-screen element.") from exc


def _bring_source_into_view(frame: Any, source: str, *,
                            iframe_selector: str,
                            scroll_hint: Optional[str],
                            timeout_ms: int) -> Any:
    """Make the drag SOURCE actually on-screen inside the iframe, fail-closed,
    and RETURN the resolved locator (v1.2.0 — resolution is visible-match-aware,
    so an AMBIGUOUS source text with a hidden first-in-DOM match still resolves
    to the on-screen tile; see :func:`_resolve_visible`).

    1. Direct path: resolve a VISIBLE match for the source, then
       ``scroll_into_view_if_needed`` (this alone fixes a tile that is rendered
       but below the fold of its panel).
    2. Hint path (``scroll_hint`` — e.g. the Quick-Add CATEGORY header text): when
       the direct path misses (a lazily-rendered / far-off-screen section), scroll
       the HINT element into view first to reveal its section, then retry the
       source. The hint element missing too → ``scroll-hint-not-found``; the
       source still missing after the hint scroll → ``source-not-found`` (honest —
       the tile genuinely is not there)."""
    direct_exc: Optional[Exception] = None
    try:
        src, _ = _resolve_visible(frame, source, timeout_ms=timeout_ms)
        _scroll_into_view(src, what="source", spec=source, timeout_ms=timeout_ms)
        return src
    except IframeDragError as exc:
        direct_exc = exc
    except Exception as exc:  # noqa: BLE001
        direct_exc = exc
    if not scroll_hint:
        raise IframeDragError(
            "source-not-found",
            f"drag SOURCE {source!r} was not found/visible inside the cross-origin "
            f"iframe {iframe_selector!r} within {timeout_ms}ms "
            f"({type(direct_exc).__name__}), and no scroll hint (category) was "
            "given to reveal it. STOP — the tile is genuinely unreachable; do not "
            "brute-force.") from direct_exc
    hint = _resolve_locator(frame, scroll_hint)
    try:
        hint.wait_for(state="visible", timeout=timeout_ms)
        _scroll_into_view(hint, what="scroll-hint", spec=scroll_hint,
                          timeout_ms=timeout_ms)
    except IframeDragError as exc:
        raise IframeDragError(
            "scroll-hint-not-found",
            f"drag SOURCE {source!r} missed directly AND its scroll hint "
            f"{scroll_hint!r} could not be scrolled into view ({exc.code}). "
            "STOP — cannot reveal the tile's section.") from exc
    except Exception as exc:  # noqa: BLE001
        raise IframeDragError(
            "scroll-hint-not-found",
            f"drag SOURCE {source!r} missed directly AND its scroll hint "
            f"{scroll_hint!r} was not found/visible inside {iframe_selector!r} "
            f"within {timeout_ms}ms ({type(exc).__name__}). STOP.") from exc
    try:
        src, _ = _resolve_visible(frame, source, timeout_ms=timeout_ms)
        _scroll_into_view(src, what="source", spec=source, timeout_ms=timeout_ms)
        return src
    except IframeDragError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IframeDragError(
            "source-not-found",
            f"drag SOURCE {source!r} is still not found/visible inside "
            f"{iframe_selector!r} even after scrolling its hint {scroll_hint!r} "
            f"into view ({type(exc).__name__}). STOP — the tile is genuinely "
            "absent; do not brute-force.") from exc


# ---------------------------------------------------------------------------
# The load-bearing core — drives ONE coordinate-drag against a Playwright ``page``.
# Shared by the live CDP path AND the live self-test, so the exact mechanism is
# what gets proven. Accepts any object exposing the Playwright ``page`` surface
# used here (``frame_locator``, ``mouse.move/down/up``), which is what lets the
# dep-free ``--selftest`` drive it with a mock.
# ---------------------------------------------------------------------------
def drive_drag(
    page: Any,
    *,
    iframe_selector: str,
    source: str,
    target: str,
    interpolated_moves: int = DEFAULT_INTERPOLATED_MOVES,
    move_interval_ms: int = DEFAULT_MOVE_INTERVAL_MS,
    settle_ms: int = DEFAULT_SETTLE_MS,
    verify_text: Optional[str] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    target_dx: float = 0.0,
    target_dy: float = 0.0,
    source_scroll_hint: Optional[str] = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Perform the frame-scoped coordinate-drag on ``page`` and return a receipt.

    Resolve source + target INSIDE the (possibly cross-origin) iframe, SCROLL BOTH
    INTO VIEW (with the optional ``source_scroll_hint`` — e.g. the Quick-Add
    category header — revealing a below-the-fold section first; v1.1.0), take
    their true page-coordinate bounding boxes AFTER the scrolls, then move the
    real pointer from source to target in many interpolated hops so GHL's drag
    sensor fires. FAIL-CLOSED: any unlocatable / unscrollable element / null box
    raises :class:`IframeDragError`. When ``verify_text`` is given, the placement
    is confirmed by re-querying the iframe for that text and the receipt's
    ``placed`` reflects the truth (never faked)."""
    if not iframe_selector or not str(iframe_selector).strip():
        raise IframeDragError("empty-iframe-selector", "iframe_selector must be non-empty")

    frame = page.frame_locator(iframe_selector)

    # COUNT-DELTA verification baseline (v1.1.1): for a Quick-Add drag the
    # verify text EQUALS the tile's own label, which is already present in the
    # panel BEFORE the drag (and an object-field's search row matches too) — a
    # plain "text exists" check would report a FAILED drop as placed. Read the
    # pre-drag match count NOW; the placement proof below is count > pre.
    pre_count = 0
    if verify_text:
        try:
            pre_count = int(frame.get_by_text(verify_text, exact=False).count())
        except Exception:  # noqa: BLE001
            pre_count = 0

    # Bring the SOURCE tile on-screen (visible-match resolve; scroll;
    # category-hint fallback) — fail-closed.
    src = _bring_source_into_view(frame, source, iframe_selector=iframe_selector,
                                  scroll_hint=source_scroll_hint, timeout_ms=timeout_ms)

    # Resolve the drop TARGET to a VISIBLE landmark (v1.2.0 — the live 2026-07-08
    # 'target-not-found' fix: `text=Submit` ALSO matches the Quick-Add panel's
    # 'Submit' category header/tile, and a blind `.first` bound to a HIDDEN match
    # timed out for the full budget while the real canvas button sat on screen).
    # Then bring it on-screen too (a canvas landmark can equally sit below the
    # fold — the KEPT default fields push Submit under it). Fail-closed with its
    # own honest codes, now carrying the attached-match diagnostics.
    try:
        tgt, tgt_matches = _resolve_visible(frame, target, timeout_ms=timeout_ms)
    except IframeDragError:
        raise
    except Exception as exc:  # noqa: BLE001
        n_attached = _safe_count(_resolve_locator_all(frame, target))
        raise IframeDragError(
            "target-not-found",
            f"drop TARGET {target!r} was not found/visible inside the cross-origin "
            f"iframe {iframe_selector!r} within {timeout_ms}ms ({type(exc).__name__}; "
            f"{max(n_attached, 0)} attached match(es), none visible). "
            "STOP — no drop landmark to aim at.") from exc
    _scroll_into_view(tgt, what="target", spec=target, timeout_ms=timeout_ms)

    # Boxes are read AFTER both scrolls so the coordinates reflect the final
    # scroll positions (a stale pre-scroll box would aim the pointer wrong).
    sbox = src.bounding_box()
    tbox = tgt.bounding_box()
    if sbox is None:
        raise IframeDragError(
            "source-no-box",
            f"drag SOURCE {source!r} resolved but has no bounding box inside "
            f"{iframe_selector!r} (not laid out / zero-size). STOP.")
    if tbox is None:
        raise IframeDragError(
            "target-no-box",
            f"drop TARGET {target!r} resolved but has no bounding box inside "
            f"{iframe_selector!r}. STOP — no drop landmark to aim at.")

    sx, sy = _center(sbox)
    tx, ty = _center(tbox)
    tx += float(target_dx)
    ty += float(target_dy)

    # Raw synthetic pointer drag — library-agnostic, crosses the iframe boundary.
    moves = 0
    page.mouse.move(sx, sy)
    moves += 1
    page.mouse.down()
    interval_s = max(0.0, float(move_interval_ms) / 1000.0)
    for mx, my in _interpolate(sx, sy, tx, ty, interpolated_moves):
        page.mouse.move(mx, my)
        moves += 1
        if interval_s:
            sleeper(interval_s)
    page.mouse.move(tx, ty)          # exact-target settle move
    moves += 1
    if settle_ms:
        sleeper(max(0.0, float(settle_ms) / 1000.0))
    page.mouse.up()

    placed: Optional[bool] = None
    if verify_text:
        # Placement proof = the match count INCREASED past its pre-drag
        # baseline (the tile/search-row that matched before the drag can never
        # satisfy this on its own — the v1.1.1 count-delta hardening).
        placed = _verify_placed(frame, verify_text, timeout_ms,
                                min_count=pre_count + 1)

    receipt = {
        "ok": True,
        "iframe_selector": iframe_selector,
        "source": source,
        "target": target,
        "target_matches": tgt_matches,   # attached matches for the target spec (diagnostics)
        "source_box": sbox,
        "target_box": tbox,
        "source_point": [sx, sy],
        "target_point": [tx, ty],
        "mouse_events": moves,        # move + down(implicit) + interp + settle
        "interpolated_moves": int(max(1, interpolated_moves)),
        "source_scroll_hint": source_scroll_hint,
        "verify_text": verify_text,
        "verify_pre_count": pre_count if verify_text else None,
        "placed": placed,
    }
    if verify_text and placed is False:
        raise IframeDragError(
            "not-placed",
            f"performed the drag but the match count for {verify_text!r} never "
            f"EXCEEDED its pre-drag baseline ({pre_count}) inside the iframe — "
            f"the placement did NOT verify (a pre-existing tile/search-row match "
            f"is not proof). STOP (never report a fake success). receipt={receipt}")
    return receipt


def _verify_placed(frame: Any, text: str, timeout_ms: int, *,
                   min_count: int = 1) -> bool:
    """Best-effort confirmation that at least ``min_count`` matches of ``text``
    are present inside the iframe (callers pass pre-drag-count + 1 so a match
    that existed BEFORE the action can never fake the proof). Returns
    True/False; never raises for a plain 'not found' (the caller decides)."""
    deadline = time.monotonic() + max(0.0, timeout_ms / 1000.0)
    loc = frame.get_by_text(text, exact=False)
    need = max(1, int(min_count))
    while True:
        try:
            if loc.count() >= need:
                return True
        except Exception:  # noqa: BLE001
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


# ---------------------------------------------------------------------------
# Page selection (which tab/page carries the builder)
# ---------------------------------------------------------------------------
def _select_page(browser: Any, url_marker: Optional[str], iframe_selector: str) -> Any:
    """Pick the attached page that hosts the builder. Prefer a URL substring match
    (``url_marker``); else the first page whose iframe selector resolves; else the
    first page. Raises :class:`IframeDragError` when the browser exposes no page."""
    pages = []
    for ctx in getattr(browser, "contexts", []) or []:
        pages.extend(getattr(ctx, "pages", []) or [])
    if not pages:
        raise IframeDragError(
            "no-page",
            "connected over CDP but the browser exposes no open page — agent-browser "
            "must have navigated to the builder BEFORE the drag handoff")
    if url_marker:
        for pg in pages:
            try:
                if url_marker in (pg.url or ""):
                    return pg
            except Exception:  # noqa: BLE001
                continue
    # Fall back to a page whose iframe is present, else the first page.
    for pg in pages:
        try:
            if pg.frame_locator(iframe_selector).owner.count() > 0:  # type: ignore[attr-defined]
                return pg
        except Exception:  # noqa: BLE001
            continue
    return pages[0]


# ---------------------------------------------------------------------------
# The public LIVE entry point — attach to agent-browser's Chromium via CDP.
# ---------------------------------------------------------------------------
def _attach_over_cdp(p: Any, cdp_url: str) -> Any:
    """Attach Playwright to the already-running agent-browser Chromium; fail-closed."""
    try:
        return p.chromium.connect_over_cdp(cdp_url)
    except Exception as exc:  # noqa: BLE001
        raise IframeDragError(
            "cdp-connect-failed",
            f"could not attach Playwright to agent-browser's Chromium at the given "
            f"CDP endpoint ({type(exc).__name__}). Confirm the session is alive "
            f"(`get cdp-url`).") from exc


def _require_playwright(capability: str) -> None:
    if not PLAYWRIGHT_AVAILABLE:
        raise IframeDragError(
            "playwright-unavailable",
            f"the frame-scoped {capability} needs Playwright (Python) to reach into "
            "the cross-origin GHL builder iframe, and it is not importable here. Install "
            "it SCOPED to Skill 6 (e.g. `python3 -m pip install playwright && python3 -m "
            "playwright install chromium`). agent-browser 0.27.0 alone CANNOT reach a "
            "non-interactive element across a cross-origin iframe (see module docstring).")


def _require_cdp_url(cdp_url: str) -> None:
    if not cdp_url or not str(cdp_url).strip():
        raise IframeDragError(
            "no-cdp-url",
            "no CDP url was supplied — read it from the live agent-browser session with "
            "`get cdp-url` and pass it in so Playwright attaches to the SAME logged-in "
            "Chromium (no second browser, no re-login).")


def coordinate_drag(
    cdp_url: str,
    *,
    iframe_selector: str,
    source: str,
    target: str,
    url_marker: Optional[str] = None,
    interpolated_moves: int = DEFAULT_INTERPOLATED_MOVES,
    move_interval_ms: int = DEFAULT_MOVE_INTERVAL_MS,
    settle_ms: int = DEFAULT_SETTLE_MS,
    verify_text: Optional[str] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    target_dx: float = 0.0,
    target_dy: float = 0.0,
    source_scroll_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach Playwright to the ALREADY-RUNNING agent-browser Chromium over CDP and
    perform ONE frame-scoped coordinate-drag inside a (cross-origin) builder iframe.

    Args:
        cdp_url: The CDP websocket endpoint from ``agent-browser get cdp-url``.
        iframe_selector: CSS selector for the builder iframe on the top frame
            (see :data:`IFRAME_SELECTORS`).
        source: Locator spec for the drag-source tile inside the iframe (see
            :func:`_resolve_locator`; default is visible-text).
        target: Locator spec for the drop landmark inside the iframe.
        url_marker: Substring to pick the builder page among open tabs.
        verify_text: If given, confirm this text appears in the iframe after drop.
        source_scroll_hint: Optional locator spec (e.g. the tile's CATEGORY header
            text) scrolled into view FIRST when the source misses directly — the
            general below-the-fold Quick-Add fix (v1.1.0).
        (others): drag-sensor tuning + a small target offset.

    Returns:
        A receipt dict (see :func:`drive_drag`).

    Raises:
        IframeDragError: fail-closed on any unavailable Playwright, missing page/
            frame, unlocatable source/target, or an unverified placement. NEVER
            fakes success. The underlying agent-browser Chromium is NOT closed —
            only the Playwright CDP connection is detached.
    """
    _require_playwright("coordinate-drag")
    _require_cdp_url(cdp_url)

    with sync_playwright() as p:  # type: ignore[union-attr]
        browser = _attach_over_cdp(p, cdp_url)
        try:
            page = _select_page(browser, url_marker, iframe_selector)
            return drive_drag(
                page,
                iframe_selector=iframe_selector,
                source=source,
                target=target,
                interpolated_moves=interpolated_moves,
                move_interval_ms=move_interval_ms,
                settle_ms=settle_ms,
                verify_text=verify_text,
                timeout_ms=timeout_ms,
                target_dx=target_dx,
                target_dy=target_dy,
                source_scroll_hint=source_scroll_hint,
            )
        finally:
            # Detach the Playwright CDP connection WITHOUT killing agent-browser's
            # Chromium (it owns the singleton pooled session + its teardown). For a
            # connect_over_cdp browser, close() disconnects the client only.
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# FRAME-SCOPED CANVAS-FIELD REMOVE (v1.2.0) — the F4 default-field
# reconciliation fix. GHL's "Start from Scratch" template pre-seeds the canvas
# (First Name, Last Name, Phone, Email, the Terms & Conditions consent block —
# SELECTORS-LIVE-form.md §6); the plan's `default_fields_delete` entries were
# previously warn-and-KEPT (live 2026-07-08 attempt #5), leaving extra fields
# on the canvas — which both ships a form that deviates from the spec AND
# poisons later drags (the kept default 'Phone' label collides with the Quick-
# Add 'Phone' tile text; the taller canvas pushes Submit below the fold).
# The DOCUMENTED delete affordance (§6, conf 8): select/hover the field → the
# per-field controls appear as REAL links → getByRole('link', { name:
# 'Remove field' }). All inside the cross-origin iframe → same CDP handoff as
# the drag. FAIL-CLOSED; removal is verified by a COUNT-DECREASE of the
# field's own anchor (mirror of the v1.1.1 count-delta placement proof).
# ---------------------------------------------------------------------------
REMOVE_FIELD_LINK_SPEC = "role=link:Remove field"    # SELECTORS-LIVE-form.md §6


def _verify_count_at_most(loc_all: Any, max_count: int, timeout_ms: int) -> Tuple[bool, int]:
    """Poll until the locator's attached-match count is <= ``max_count``.
    Returns (ok, last_count). Never raises for a plain miss (caller decides)."""
    deadline = time.monotonic() + max(0.0, timeout_ms / 1000.0)
    last = -1
    while True:
        last = _safe_count(loc_all)
        if 0 <= last <= max_count:
            return True, last
        if time.monotonic() >= deadline:
            return False, last
        time.sleep(0.25)


def drive_remove_canvas_field(
    page: Any,
    *,
    iframe_selector: str,
    field: str,
    remove_link_spec: str = REMOVE_FIELD_LINK_SPEC,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Dict[str, Any]:
    """Remove ONE canvas field inside the builder iframe and VERIFY it is gone.

    ``field`` is a locator spec for the field's DOCUMENTED canvas anchor
    (SELECTORS §6 — e.g. ``placeholder=+1 (555) 000-0000`` for the default
    Phone field; the consent paragraph text for the Terms & Conditions block).

    Mechanism (all frame-scoped — Playwright drives the cross-origin iframe
    natively): 0 matches → the field is ALREADY absent → a truthful idempotent
    no-op receipt (reconciliation semantics: the desired end-state holds);
    else resolve a VISIBLE match, scroll it on-screen, hover + click it to
    select (the per-field controls appear on hover/selected — §6), resolve the
    'Remove field' LINK by role+exact name, click it, and VERIFY the field
    anchor's match count DECREASED below its pre-remove baseline. FAIL-CLOSED
    codes: ``field-not-found`` (attached but never visible/selectable),
    ``remove-link-not-found``, ``field-not-removed``. NEVER fakes a removal."""
    if not iframe_selector or not str(iframe_selector).strip():
        raise IframeDragError("empty-iframe-selector", "iframe_selector must be non-empty")
    if not field or not str(field).strip():
        raise IframeDragError("empty-locator", "the field anchor spec was empty")

    frame = page.frame_locator(iframe_selector)
    loc_all = _resolve_locator_all(frame, field)
    pre = _safe_count(loc_all)
    if pre == 0:
        return {"ok": True, "removed": False, "already_absent": True,
                "field": field, "pre_count": 0, "post_count": 0,
                "remove_link": remove_link_spec}

    try:
        anchor, _ = _resolve_visible(frame, field, timeout_ms=timeout_ms)
    except IframeDragError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IframeDragError(
            "field-not-found",
            f"canvas field anchor {field!r} has {max(pre, 0)} attached match(es) but "
            f"none became visible inside {iframe_selector!r} within {timeout_ms}ms "
            f"({type(exc).__name__}). STOP — cannot select a field that is not on "
            "screen (never blind-click).") from exc
    _scroll_into_view(anchor, what="field", spec=field, timeout_ms=timeout_ms)
    try:
        anchor.hover()          # reveals the per-field hover controls (§6)
    except Exception:  # noqa: BLE001
        pass                    # hover is best-effort; the click below selects
    try:
        anchor.click()          # selecting the field also shows its controls (§6)
    except Exception as exc:  # noqa: BLE001
        raise IframeDragError(
            "field-not-selectable",
            f"located canvas field {field!r} but the select-click failed "
            f"({type(exc).__name__}). STOP.") from exc

    try:
        link, _ = _resolve_visible(frame, remove_link_spec, timeout_ms=timeout_ms)
    except IframeDragError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IframeDragError(
            "remove-link-not-found",
            f"selected canvas field {field!r} but the documented per-field control "
            f"{remove_link_spec!r} (SELECTORS §6) never became visible within "
            f"{timeout_ms}ms ({type(exc).__name__}). STOP — never invent another "
            "delete affordance.") from exc
    try:
        link.click()
    except Exception as exc:  # noqa: BLE001
        raise IframeDragError(
            "remove-click-failed",
            f"the {remove_link_spec!r} control resolved for field {field!r} but the "
            f"click failed ({type(exc).__name__}). STOP.") from exc

    ok, post = _verify_count_at_most(loc_all, max(0, pre - 1), timeout_ms)
    receipt = {"ok": True, "removed": ok, "already_absent": False, "field": field,
               "pre_count": pre, "post_count": post, "remove_link": remove_link_spec}
    if not ok:
        raise IframeDragError(
            "field-not-removed",
            f"clicked {remove_link_spec!r} for field {field!r} but its anchor match "
            f"count never DROPPED below the pre-remove baseline ({pre} → {post}) — "
            f"the removal did NOT verify. STOP (never report a fake delete). "
            f"receipt={receipt}")
    return receipt


def remove_canvas_field(
    cdp_url: str,
    *,
    iframe_selector: str,
    field: str,
    url_marker: Optional[str] = None,
    remove_link_spec: str = REMOVE_FIELD_LINK_SPEC,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Dict[str, Any]:
    """LIVE entry point: attach over CDP (same logged-in Chromium; no second
    browser, no re-login) and remove ONE canvas field inside the builder iframe,
    fail-closed. See :func:`drive_remove_canvas_field` for mechanism + receipt."""
    _require_playwright("canvas-field remove")
    _require_cdp_url(cdp_url)
    with sync_playwright() as p:  # type: ignore[union-attr]
        browser = _attach_over_cdp(p, cdp_url)
        try:
            page = _select_page(browser, url_marker, iframe_selector)
            return drive_remove_canvas_field(
                page, iframe_selector=iframe_selector, field=field,
                remove_link_spec=remove_link_spec, timeout_ms=timeout_ms)
        finally:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# FRAME-SCOPED INLINE-TITLE READ/SET (v1.1.0) — the F3 rename fix.
# The builder title ("Form 55" / "Survey 0") is an in-iframe inline-edit surface;
# top-frame verbs can never reach it (same cross-origin constraint as the drag).
# ---------------------------------------------------------------------------
DEFAULT_FORM_TITLE_SPECS: Tuple[str, ...] = (r"re:^Form\s*\d+$", "text=Untitled")
DEFAULT_SURVEY_TITLE_SPECS: Tuple[str, ...] = (r"re:^Survey\s*\d+$", "text=Untitled")

_FOCUSED_EDITABLE_JS = (
    "el => { const d = el.ownerDocument; const a = d.activeElement;"
    "  if (!a) return false;"
    "  const t = (a.tagName || '').toUpperCase();"
    "  return t === 'INPUT' || t === 'TEXTAREA' || a.isContentEditable === true; }"
)


def _frame_has_focused_editable(frame: Any) -> bool:
    """True iff the iframe's document currently focuses an editable element
    (input / textarea / contenteditable). Evaluated on the always-attached
    ``body`` (the clicked title node may be REPLACED by the editor and detach).
    Never raises — an unevaluable frame reads as 'not editable' (fail-closed)."""
    try:
        return bool(frame.locator("body").first.evaluate(_FOCUSED_EDITABLE_JS))
    except Exception:  # noqa: BLE001
        return False


def _select_all(page: Any) -> None:
    """Select-all in the FOCUSED element. ``ControlOrMeta+A`` (Playwright's
    cross-platform alias — playwright.dev/python Keyboard docs) with per-platform
    fallbacks for older Playwrights that predate the alias."""
    for combo in ("ControlOrMeta+a", "Meta+a", "Control+a"):
        try:
            page.keyboard.press(combo)
            return
        except Exception:  # noqa: BLE001
            continue
    raise IframeDragError(
        "select-all-failed",
        "could not issue a select-all keystroke (ControlOrMeta/Meta/Control+a all "
        "failed) — cannot safely replace the inline title text. STOP.")


def _find_first_title(frame: Any, title_specs: Sequence[str], *,
                      timeout_ms: int) -> Tuple[Any, str]:
    """Resolve the FIRST title spec that is present+visible in the iframe.
    Returns (locator, matched_spec); raises ``title-not-found`` when none match.
    The per-spec wait is a short slice of the budget so a long pattern list
    cannot multiply the total wait unboundedly."""
    specs = [s for s in (title_specs or []) if str(s).strip()]
    if not specs:
        raise IframeDragError("title-not-found", "no title locator specs were given")
    per_spec = max(500, int(timeout_ms / len(specs)))
    last: Optional[Exception] = None
    for spec in specs:
        loc = _resolve_locator(frame, spec)
        try:
            loc.wait_for(state="visible", timeout=per_spec)
            return loc, spec
        except Exception as exc:  # noqa: BLE001
            last = exc
            continue
    raise IframeDragError(
        "title-not-found",
        f"no inline title matched any of the specs {list(specs)!r} inside the "
        f"iframe within ~{timeout_ms}ms ({type(last).__name__ if last else 'none'}). "
        "STOP — cannot rename/read a title that cannot be located.")


def drive_read_inline_title(page: Any, *, iframe_selector: str,
                            title_specs: Sequence[str],
                            timeout_ms: int = DEFAULT_TIMEOUT_MS) -> Dict[str, Any]:
    """Read the CURRENT inline title text inside the builder iframe (fail-closed).
    Returns {ok, title, matched_spec}."""
    if not iframe_selector or not str(iframe_selector).strip():
        raise IframeDragError("empty-iframe-selector", "iframe_selector must be non-empty")
    frame = page.frame_locator(iframe_selector)
    loc, spec = _find_first_title(frame, title_specs, timeout_ms=timeout_ms)
    try:
        text = (loc.text_content() or "").strip()
    except Exception as exc:  # noqa: BLE001
        raise IframeDragError(
            "title-not-readable",
            f"located the inline title via {spec!r} but could not read its text "
            f"({type(exc).__name__}). STOP.") from exc
    return {"ok": True, "title": text, "matched_spec": spec}


def drive_set_inline_title(
    page: Any,
    *,
    iframe_selector: str,
    new_title: str,
    title_specs: Sequence[str] = DEFAULT_FORM_TITLE_SPECS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    commit_key: str = "Enter",
    sleeper: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Rename the in-iframe inline title to ``new_title`` and VERIFY it, fail-closed.

    Mechanism (all inside the cross-origin iframe, which Playwright drives natively):
      1. locate the title by the FIRST matching spec (regex-capable — the default
         number in "Form <n>" is unknowable ahead of time);
      2. read the OLD title text (receipt evidence — cleanup can target it);
      3. click it; if no editable takes focus, double-click; still nothing →
         ``title-not-editable`` (STOP — never blind-type into a non-editor);
      4. select-all + type ``new_title`` + commit (``commit_key``);
      5. VERIFY ``new_title`` is present in the iframe → else ``title-not-set``.
    NEVER fakes success; the receipt carries the truth."""
    if not iframe_selector or not str(iframe_selector).strip():
        raise IframeDragError("empty-iframe-selector", "iframe_selector must be non-empty")
    if not new_title or not str(new_title).strip():
        raise IframeDragError("empty-title", "new_title must be non-empty")

    frame = page.frame_locator(iframe_selector)
    loc, spec = _find_first_title(frame, title_specs, timeout_ms=timeout_ms)
    _scroll_into_view(loc, what="title", spec=spec, timeout_ms=timeout_ms)
    try:
        old_title = (loc.text_content() or "").strip()
    except Exception:  # noqa: BLE001
        old_title = ""

    entered_via = "click"
    try:
        loc.click()
    except Exception as exc:  # noqa: BLE001
        raise IframeDragError(
            "title-not-clickable",
            f"located the inline title via {spec!r} but the click to enter edit "
            f"mode failed ({type(exc).__name__}). STOP.") from exc
    if not _frame_has_focused_editable(frame):
        entered_via = "dblclick"
        try:
            loc.dblclick()
        except Exception:  # noqa: BLE001
            pass
        if not _frame_has_focused_editable(frame):
            raise IframeDragError(
                "title-not-editable",
                f"clicked (and double-clicked) the inline title ({spec!r}, current "
                f"text {old_title!r}) but NO editable element took focus inside the "
                "iframe — this surface did not enter edit mode. STOP — typing now "
                "would go nowhere (the silent-failure mode this fix removes).")

    _select_all(page)
    page.keyboard.type(str(new_title))
    if commit_key:
        try:
            page.keyboard.press(commit_key)
        except Exception as exc:  # noqa: BLE001
            raise IframeDragError(
                "title-commit-failed",
                f"typed the new title but the commit key {commit_key!r} failed "
                f"({type(exc).__name__}). STOP — the rename is unverified.") from exc

    verified = _verify_placed(frame, str(new_title), timeout_ms)
    receipt = {
        "ok": True,
        "old_title": old_title,
        "new_title": str(new_title),
        "matched_spec": spec,
        "entered_via": entered_via,
        "verified": verified,
    }
    if not verified:
        raise IframeDragError(
            "title-not-set",
            f"typed + committed the new title but {new_title!r} did not appear "
            f"inside the iframe afterwards — the rename did NOT verify. STOP "
            f"(never report a fake rename). receipt={receipt}")
    return receipt


def set_inline_title(
    cdp_url: str,
    *,
    iframe_selector: str,
    new_title: str,
    title_specs: Sequence[str] = DEFAULT_FORM_TITLE_SPECS,
    url_marker: Optional[str] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    commit_key: str = "Enter",
) -> Dict[str, Any]:
    """LIVE entry point: attach over CDP (same logged-in Chromium; no second
    browser, no re-login) and rename the in-iframe inline title, fail-closed.
    See :func:`drive_set_inline_title` for the mechanism + receipt."""
    _require_playwright("inline-title rename")
    _require_cdp_url(cdp_url)
    with sync_playwright() as p:  # type: ignore[union-attr]
        browser = _attach_over_cdp(p, cdp_url)
        try:
            page = _select_page(browser, url_marker, iframe_selector)
            return drive_set_inline_title(
                page, iframe_selector=iframe_selector, new_title=new_title,
                title_specs=title_specs, timeout_ms=timeout_ms, commit_key=commit_key)
        finally:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass


def read_inline_title(
    cdp_url: str,
    *,
    iframe_selector: str,
    title_specs: Sequence[str],
    url_marker: Optional[str] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Dict[str, Any]:
    """LIVE entry point: read the CURRENT in-iframe inline title text (so cleanup
    can positively target the container by the name it ACTUALLY carries, even
    after a failed rename). Fail-closed; see :func:`drive_read_inline_title`."""
    _require_playwright("inline-title read")
    _require_cdp_url(cdp_url)
    with sync_playwright() as p:  # type: ignore[union-attr]
        browser = _attach_over_cdp(p, cdp_url)
        try:
            page = _select_page(browser, url_marker, iframe_selector)
            return drive_read_inline_title(
                page, iframe_selector=iframe_selector, title_specs=title_specs,
                timeout_ms=timeout_ms)
        finally:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass


def iframe_selector_for(kind: str) -> str:
    """Return a known builder iframe selector by kind ('form' | 'survey' |
    'page_code'); raises for an unknown kind so a typo can't silently target the
    wrong frame."""
    try:
        return IFRAME_SELECTORS[kind]
    except KeyError as exc:
        raise IframeDragError(
            "unknown-iframe-kind",
            f"no known iframe selector for kind {kind!r}; known: "
            f"{sorted(IFRAME_SELECTORS)}") from exc


# ===========================================================================
# Self-tests
# ===========================================================================
def _selftest() -> int:
    """Dep-free structural proof (NO Playwright, NO browser, NO network) — drives
    the REAL drag core with a mock page and proves the mechanism + fail-closed."""
    errors = []

    # 1. interpolation: strictly-between, correct count, monotonic toward target.
    pts = list(_interpolate(0.0, 0.0, 100.0, 200.0, 24))
    if len(pts) != 24:
        errors.append(f"interpolate count wrong: {len(pts)}")
    if pts and (pts[0][0] <= 0 or pts[-1][0] >= 100):
        errors.append("interpolate points not strictly between source/target")
    if any(pts[i][0] > pts[i + 1][0] for i in range(len(pts) - 1)):
        errors.append("interpolate x not monotonic increasing")

    # 2. _center math + null-box fail-closed.
    if _center({"x": 10, "y": 20, "width": 4, "height": 8}) != (12.0, 24.0):
        errors.append("_center math wrong")
    try:
        _center(None)
        errors.append("_center(None) did not raise IframeDragError")
    except IframeDragError:
        pass

    # 3. locator spec dispatch (incl. the v1.2.0 role= / placeholder= specs).
    class _FrameSpy:
        def __init__(self):
            self.calls = []

        def get_by_text(self, text, exact=False):
            self.calls.append(("text", text, exact))
            return _LocStub()

        def locator(self, sel):
            self.calls.append(("css", sel))
            return _LocStub()

        def get_by_role(self, role, name=None, exact=False):
            self.calls.append(("role", role, name, exact))
            return _LocStub()

        def get_by_placeholder(self, text):
            self.calls.append(("placeholder", text))
            return _LocStub()

    class _LocStub:
        @property
        def first(self):
            return self

    fs = _FrameSpy()
    _resolve_locator(fs, "State")
    _resolve_locator(fs, "text=City")
    _resolve_locator(fs, "exact=Submit")
    _resolve_locator(fs, "css=#tile-state")
    _resolve_locator(fs, "role=button:Submit")
    _resolve_locator(fs, "placeholder=+1 (555) 000-0000")
    if fs.calls != [("text", "State", False), ("text", "City", False),
                    ("text", "Submit", True), ("css", "#tile-state"),
                    ("role", "button", "Submit", True),
                    ("placeholder", "+1 (555) 000-0000")]:
        errors.append(f"locator dispatch wrong: {fs.calls}")
    try:
        _resolve_locator(fs, "")
        errors.append("empty locator spec did not raise")
    except IframeDragError:
        pass
    try:
        _resolve_locator(fs, "role=button")     # missing ':<name>' part
        errors.append("malformed role= spec did not raise")
    except IframeDragError as e:
        if e.code != "bad-role-locator":
            errors.append(f"malformed role= wrong code: {e.code}")

    # 4. HAPPY drag: mock page records the exact pointer sequence.
    class _MockMouse:
        def __init__(self):
            self.ops = []

        def move(self, x, y):
            self.ops.append(("move", round(x, 3), round(y, 3)))

        def down(self):
            self.ops.append(("down",))

        def up(self):
            self.ops.append(("up",))

    class _MockLoc:
        """Models the v1.1.1 count-delta world: count() returns 1 on the FIRST
        read (the pre-drag baseline — the tile itself already matches) and,
        when the placement 'landed' (present_after), 2 on later reads (tile +
        the newly placed canvas field). A failed placement stays at 1 forever —
        which must now read as NOT placed. v1.2.0: also exposes the
        nth()/is_visible() surface the visible-match scan touches."""
        def __init__(self, frame, box, present_after=True):
            self._frame = frame
            self._box = box
            self._present = present_after

        @property
        def first(self):
            return self

        def nth(self, i):
            return self

        def is_visible(self):
            return self._box is not None

        def wait_for(self, state="visible", timeout=0):
            if self._box is None:
                raise TimeoutError("mock: not visible")

        def scroll_into_view_if_needed(self, timeout=0):
            if self._box is None:
                raise TimeoutError("mock: cannot scroll a missing element")

        def bounding_box(self):
            return self._box

        def count(self):
            self._frame.count_reads += 1
            if self._frame.count_reads == 1:
                return 1                        # pre-drag baseline: the tile itself
            return 2 if self._present else 1    # placed → one MORE match; failed → same

    class _MockFrame:
        def __init__(self, boxes, verify_present=True):
            self._boxes = boxes
            self._verify_present = verify_present
            self.count_reads = 0

        def get_by_text(self, text, exact=False):
            return _MockLoc(self, self._boxes.get(text),
                            present_after=self._verify_present)

        def locator(self, sel):
            return _MockLoc(self, self._boxes.get(sel))

    class _MockPage:
        def __init__(self, frame):
            self.mouse = _MockMouse()
            self._frame = frame

        def frame_locator(self, sel):
            return self._frame

    boxes = {"State": {"x": 100, "y": 150, "width": 80, "height": 30},
             "Submit": {"x": 90, "y": 400, "width": 120, "height": 40}}
    page = _MockPage(_MockFrame(boxes, verify_present=True))
    rec = drive_drag(page, iframe_selector='iframe[src*="form-builder-v2"]',
                     source="text=State", target="text=Submit",
                     interpolated_moves=24, move_interval_ms=0, settle_ms=0,
                     verify_text="State", sleeper=lambda s: None)
    ops = page.mouse.ops
    if ops[0][0] != "move" or ops[1] != ("down",) or ops[-1] != ("up",):
        errors.append(f"drag op envelope wrong: {ops[:2]} .. {ops[-1]}")
    n_moves = sum(1 for o in ops if o[0] == "move")
    if n_moves != 26:   # 1 start + 24 interpolated + 1 settle
        errors.append(f"expected 26 moves (1+24+1), got {n_moves}")
    if rec["placed"] is not True or rec["mouse_events"] != 26:
        errors.append(f"receipt wrong: placed={rec['placed']} moves={rec['mouse_events']}")
    # start point == source center; final move == target center
    if ops[0][1:] != (140.0, 165.0):
        errors.append(f"start point not source center: {ops[0]}")
    last_move = [o for o in ops if o[0] == "move"][-1]
    if last_move[1:] != (150.0, 420.0):
        errors.append(f"final move not target center: {last_move}")

    # 5. FAIL-CLOSED: source has no bounding box → IframeDragError, no fake success.
    page2 = _MockPage(_MockFrame({"State": None, "Submit": boxes["Submit"]}))
    try:
        drive_drag(page2, iframe_selector="iframe", source="text=State",
                   target="text=Submit", move_interval_ms=0, settle_ms=0,
                   sleeper=lambda s: None)
        errors.append("missing source box did NOT raise IframeDragError")
    except IframeDragError as e:
        if e.code not in ("source-not-found", "source-no-box"):
            errors.append(f"unexpected fail-closed code: {e.code}")

    # 6. FAIL-CLOSED: placement does not verify → IframeDragError (never fake).
    page3 = _MockPage(_MockFrame(boxes, verify_present=False))
    try:
        drive_drag(page3, iframe_selector="iframe", source="text=State",
                   target="text=Submit", verify_text="State",
                   move_interval_ms=0, settle_ms=0, timeout_ms=0,
                   sleeper=lambda s: None)
        errors.append("unverified placement did NOT raise IframeDragError")
    except IframeDragError as e:
        if e.code != "not-placed":
            errors.append(f"unexpected unverified code: {e.code}")

    # 7. coordinate_drag reports cleanly when Playwright is unavailable. Flip the
    #    flag on THIS module's own globals (never re-import — a second import object
    #    would carry a distinct IframeDragError class and dodge the except below).
    _orig = globals()["PLAYWRIGHT_AVAILABLE"]
    try:
        globals()["PLAYWRIGHT_AVAILABLE"] = False
        coordinate_drag("ws://x", iframe_selector="iframe",
                        source="text=A", target="text=B")
        errors.append("coordinate_drag with no Playwright did NOT raise")
    except IframeDragError as e:
        if e.code != "playwright-unavailable":
            errors.append(f"unexpected no-playwright code: {e.code}")
    finally:
        globals()["PLAYWRIGHT_AVAILABLE"] = _orig

    # 8. unknown iframe kind fails loud.
    try:
        iframe_selector_for("bogus")
        errors.append("iframe_selector_for('bogus') did not raise")
    except IframeDragError:
        pass
    if iframe_selector_for("form") != 'iframe[src*="form-builder-v2"]':
        errors.append("iframe_selector_for('form') wrong")

    # 9. SCROLL-HINT locate (v1.1.0 — the F5.locate:City fix): a tile hidden below
    #    the fold is revealed by scrolling its CATEGORY header into view, then
    #    scrolled + dragged; without the hint the same miss fails closed.
    class _ScrollWorld:
        def __init__(self):
            self.boxes = {"Address": {"x": 20, "y": 300, "width": 100, "height": 20},
                          "Submit": {"x": 90, "y": 400, "width": 120, "height": 40}}
            self.hidden = {"City": {"x": 24, "y": 340, "width": 80, "height": 30}}
            self.scrolled = []

        def visible(self, key):
            return key in self.boxes

        def scroll(self, key):
            self.scrolled.append(key)
            if key == "Address":            # revealing the category reveals its tiles
                self.boxes.update(self.hidden)
                self.hidden = {}

    class _ScrollLoc:
        def __init__(self, world, key):
            self._w = world
            self._k = key

        @property
        def first(self):
            return self

        def nth(self, i):
            return self

        def is_visible(self):
            return self._w.visible(self._k)

        def wait_for(self, state="visible", timeout=0):
            if not self._w.visible(self._k):
                raise TimeoutError(f"mock: {self._k} not visible")

        def scroll_into_view_if_needed(self, timeout=0):
            if not self._w.visible(self._k):
                raise TimeoutError(f"mock: {self._k} cannot scroll")
            self._w.scroll(self._k)

        def bounding_box(self):
            return self._w.boxes.get(self._k)

        def count(self):
            return 1 if self._w.visible(self._k) else 0

    class _ScrollFrame:
        def __init__(self, world):
            self._w = world

        def get_by_text(self, text, exact=False):
            key = text if isinstance(text, str) else "City"
            return _ScrollLoc(self._w, key)

        def locator(self, sel):
            return _ScrollLoc(self._w, sel)

    world = _ScrollWorld()
    page9 = _MockPage(_ScrollFrame(world))
    rec9 = drive_drag(page9, iframe_selector="iframe", source="text=City",
                      target="text=Submit", source_scroll_hint="text=Address",
                      verify_text="City", move_interval_ms=0, settle_ms=0,
                      sleeper=lambda s: None)
    if world.scrolled != ["Address", "City", "Submit"]:
        errors.append(f"hint scroll order wrong: {world.scrolled}")
    if rec9.get("placed") is not True or rec9.get("source_scroll_hint") != "text=Address":
        errors.append(f"hint receipt wrong: {rec9}")
    if page9.mouse.ops[-1] != ("up",):
        errors.append("hint drag did not complete the pointer envelope")
    # same miss WITHOUT the hint fails closed (never a guessed point).
    try:
        drive_drag(_MockPage(_ScrollFrame(_ScrollWorld())), iframe_selector="iframe",
                   source="text=City", target="text=Submit",
                   move_interval_ms=0, settle_ms=0, sleeper=lambda s: None)
        errors.append("hidden tile WITHOUT hint did not raise")
    except IframeDragError as e:
        if e.code != "source-not-found":
            errors.append(f"hidden-no-hint wrong code: {e.code}")

    # 10. INLINE-TITLE rename (v1.1.0 — the F3 fix): locate by regex pattern,
    #     enter edit mode, select-all + type + commit, VERIFY — plus fail-closed
    #     when the surface never becomes editable (the old silent-failure mode).
    class _TitleFrame:
        def __init__(self, editable=True):
            self.texts = {"Form 55"}
            self.editable = editable
            self.focused = False

        def get_by_text(self, pattern, exact=False):
            if hasattr(pattern, "search"):
                for t in sorted(self.texts):
                    if pattern.search(t):
                        return _TitleLoc(self, t)
                return _TitleLoc(self, None)
            hit = next((t for t in sorted(self.texts)
                        if (t == pattern if exact else str(pattern) in t)), None)
            return _TitleLoc(self, hit)

        def locator(self, sel):
            return _BodyLoc(self) if sel == "body" else _TitleLoc(self, None)

    class _TitleLoc:
        def __init__(self, frame, text):
            self._f = frame
            self._t = text

        @property
        def first(self):
            return self

        def wait_for(self, state="visible", timeout=0):
            if self._t is None:
                raise TimeoutError("mock: title text absent")

        def scroll_into_view_if_needed(self, timeout=0):
            pass

        def text_content(self):
            return self._t

        def click(self):
            if self._f.editable:
                self._f.focused = True

        def dblclick(self):
            if self._f.editable:
                self._f.focused = True

        def count(self):
            return 1 if self._t is not None else 0

    class _BodyLoc:
        def __init__(self, frame):
            self._f = frame

        @property
        def first(self):
            return self

        def evaluate(self, js):
            return self._f.focused

    class _TitleKeyboard:
        def __init__(self, frame):
            self._f = frame
            self.ops = []

        def press(self, combo):
            self.ops.append(("press", combo))

        def type(self, text):
            self.ops.append(("type", text))
            if self._f.focused:
                self._f.texts.add(text)     # the typed title renders in the iframe

    class _TitlePage:
        def __init__(self, frame):
            self._frame = frame
            self.keyboard = _TitleKeyboard(frame)
            self.mouse = _MockMouse()

        def frame_locator(self, sel):
            return self._frame

    tf = _TitleFrame(editable=True)
    tp = _TitlePage(tf)
    rec10 = drive_set_inline_title(
        tp, iframe_selector="iframe", new_title="ZHC TEST Title",
        title_specs=(r"re:^Form\s*\d+$",), timeout_ms=1000, sleeper=lambda s: None)
    if rec10.get("old_title") != "Form 55" or rec10.get("verified") is not True:
        errors.append(f"inline-title receipt wrong: {rec10}")
    presses = [o[1] for o in tp.keyboard.ops if o[0] == "press"]
    if not any(p.lower().endswith("+a") for p in presses):
        errors.append(f"inline-title did not select-all first: {presses}")
    if presses[-1] != "Enter":
        errors.append(f"inline-title did not commit with Enter: {presses}")
    if ("type", "ZHC TEST Title") not in tp.keyboard.ops:
        errors.append("inline-title did not type the new title")
    rd = drive_read_inline_title(
        _TitlePage(tf), iframe_selector="iframe",
        title_specs=("re:^ZHC TEST",), timeout_ms=500)
    if rd.get("title") != "ZHC TEST Title":
        errors.append(f"read_inline_title wrong: {rd}")

    # 11. FAIL-CLOSED: a title that never becomes editable STOPs BEFORE typing.
    tf2 = _TitleFrame(editable=False)
    tp2 = _TitlePage(tf2)
    try:
        drive_set_inline_title(tp2, iframe_selector="iframe", new_title="X",
                               title_specs=(r"re:^Form\s*\d+$",), timeout_ms=500,
                               sleeper=lambda s: None)
        errors.append("non-editable title did NOT raise")
    except IframeDragError as e:
        if e.code != "title-not-editable":
            errors.append(f"non-editable wrong code: {e.code}")
    if any(o[0] == "type" for o in tp2.keyboard.ops):
        errors.append("typed into a non-editable title (must STOP first)")

    # 12. AMBIGUOUS DROP TARGET (v1.2.0 — the live 2026-07-08 attempt-#5 fix):
    #     'Submit' matches TWO in-iframe nodes — the first in DOM order HIDDEN
    #     (the Quick-Add panel world), the second the VISIBLE canvas landmark.
    #     The old blind `.first` timed out (a false target-not-found); the
    #     visible-match resolve must aim the drop at the VISIBLE match. And
    #     when NO match is visible, the honest target-not-found remains, now
    #     carrying the attached-match diagnostics.
    class _AmbigLoc:
        def __init__(self, frame, key, boxes):
            self._frame, self._key, self._boxes = frame, key, boxes
            self._i = 0

        @property
        def first(self):
            return self.nth(0)

        def nth(self, i):
            c = _AmbigLoc(self._frame, self._key, self._boxes)
            c._i = i
            return c

        def is_visible(self):
            return 0 <= self._i < len(self._boxes) and self._boxes[self._i] is not None

        def wait_for(self, state="visible", timeout=0):
            if not self.is_visible():
                raise TimeoutError(f"mock: {self._key}[{self._i}] hidden")

        def scroll_into_view_if_needed(self, timeout=0):
            if not self.is_visible():
                raise TimeoutError("mock: cannot scroll a hidden element")

        def bounding_box(self):
            return self._boxes[self._i] if 0 <= self._i < len(self._boxes) else None

        def count(self):
            if self._key == "State":            # count-delta verify surface
                self._frame.state_reads += 1
                return 1 if self._frame.state_reads == 1 else 2
            return len(self._boxes)

    class _AmbigFrame:
        def __init__(self, submit_boxes):
            self.state_reads = 0
            self._submit = submit_boxes
            self._state = [{"x": 100, "y": 150, "width": 80, "height": 30}]

        def get_by_text(self, text, exact=False):
            key = "Submit" if "Submit" in str(text) else "State"
            return _AmbigLoc(self, key, self._submit if key == "Submit" else self._state)

        def locator(self, sel):
            return _AmbigLoc(self, "css", [])

    vis_box = {"x": 90, "y": 400, "width": 120, "height": 40}
    page12 = _MockPage(_AmbigFrame([None, vis_box]))    # DOM-first match HIDDEN
    rec12 = drive_drag(page12, iframe_selector="iframe", source="text=State",
                       target="text=Submit", verify_text="State",
                       move_interval_ms=0, settle_ms=0, timeout_ms=250,
                       sleeper=lambda s: None)
    if rec12.get("placed") is not True or rec12.get("target_matches") != 2:
        errors.append(f"ambiguous-target receipt wrong: {rec12}")
    last12 = [o for o in page12.mouse.ops if o[0] == "move"][-1]
    if last12[1:] != (150.0, 420.0):
        errors.append(f"ambiguous target did not aim at the VISIBLE match: {last12}")
    try:
        drive_drag(_MockPage(_AmbigFrame([None, None])), iframe_selector="iframe",
                   source="text=State", target="text=Submit",
                   move_interval_ms=0, settle_ms=0, timeout_ms=100,
                   sleeper=lambda s: None)
        errors.append("all-hidden target did NOT raise target-not-found")
    except IframeDragError as e:
        if e.code != "target-not-found" or "2 attached match(es)" not in e.reason:
            errors.append(f"all-hidden target wrong code/diagnostics: {e.code}: {e.reason}")

    # 13. CANVAS-FIELD REMOVE (v1.2.0 — F4 default-field reconciliation): select
    #     the field → documented 'Remove field' link (§6) → count-decrease proof;
    #     already-absent = truthful idempotent no-op; link-never-appears and
    #     count-never-drops both fail closed.
    class _RWLoc:
        def __init__(self, world, kind):
            self._w, self._kind = world, kind

        @property
        def first(self):
            return self

        def nth(self, i):
            return self

        def is_visible(self):
            return (self._w.field_count > 0) if self._kind == "field" else self._w.link_visible

        def count(self):
            return self._w.field_count if self._kind == "field" else int(self._w.link_visible)

        def wait_for(self, state="visible", timeout=0):
            if not self.is_visible():
                raise TimeoutError(f"mock: {self._kind} hidden")

        def scroll_into_view_if_needed(self, timeout=0):
            if not self.is_visible():
                raise TimeoutError("mock: cannot scroll")

        def hover(self):
            self._w.events.append(f"hover:{self._kind}")

        def click(self):
            self._w.events.append(f"click:{self._kind}")
            if self._kind == "field" and self._w.link_appears:
                self._w.link_visible = True
            if self._kind == "link" and self._w.removal_works:
                self._w.field_count = 0

    class _RWFrame:
        def __init__(self, world):
            self._w = world

        def get_by_placeholder(self, text):
            return _RWLoc(self._w, "field")

        def get_by_text(self, text, exact=False):
            return _RWLoc(self._w, "field")

        def get_by_role(self, role, name=None, exact=False):
            self._w.events.append(("role", role, name, exact))
            return _RWLoc(self._w, "link")

        def locator(self, sel):
            return _RWLoc(self._w, "field")

    class _RWWorld:
        def __init__(self, field_count=1, link_appears=True, removal_works=True):
            self.field_count = field_count
            self.link_visible = False
            self.link_appears = link_appears
            self.removal_works = removal_works
            self.events = []

    w13 = _RWWorld()
    rec13 = drive_remove_canvas_field(
        _MockPage(_RWFrame(w13)), iframe_selector="iframe",
        field="placeholder=+1 (555) 000-0000", timeout_ms=500)
    if rec13.get("removed") is not True or rec13.get("pre_count") != 1 or rec13.get("post_count") != 0:
        errors.append(f"remove-field happy receipt wrong: {rec13}")
    if "click:field" not in w13.events or "click:link" not in w13.events:
        errors.append(f"remove-field did not select then remove: {w13.events}")
    if w13.events.index("click:field") > w13.events.index("click:link"):
        errors.append(f"remove-field clicked the link BEFORE selecting: {w13.events}")
    if ("role", "link", "Remove field", True) not in w13.events:
        errors.append(f"remove-field did not use the documented role=link anchor: {w13.events}")
    w13b = _RWWorld(field_count=0)
    rec13b = drive_remove_canvas_field(
        _MockPage(_RWFrame(w13b)), iframe_selector="iframe",
        field="placeholder=+1 (555) 000-0000", timeout_ms=100)
    if rec13b.get("already_absent") is not True or rec13b.get("removed") is not False:
        errors.append(f"remove-field already-absent receipt wrong: {rec13b}")
    if any(str(e).startswith("click") for e in w13b.events):
        errors.append(f"already-absent must be a NO-OP (no clicks): {w13b.events}")
    w13c = _RWWorld(link_appears=False)
    try:
        drive_remove_canvas_field(_MockPage(_RWFrame(w13c)), iframe_selector="iframe",
                                  field="placeholder=+1 (555) 000-0000", timeout_ms=100)
        errors.append("remove-field with no link did NOT raise")
    except IframeDragError as e:
        if e.code != "remove-link-not-found":
            errors.append(f"remove-field no-link wrong code: {e.code}")
    if w13c.field_count != 1 or "click:link" in w13c.events:
        errors.append("remove-field no-link path must leave the field untouched")
    w13d = _RWWorld(removal_works=False)
    try:
        drive_remove_canvas_field(_MockPage(_RWFrame(w13d)), iframe_selector="iframe",
                                  field="placeholder=+1 (555) 000-0000", timeout_ms=0)
        errors.append("remove-field unverified removal did NOT raise")
    except IframeDragError as e:
        if e.code != "field-not-removed":
            errors.append(f"remove-field unverified wrong code: {e.code}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — coordinate-drag mechanism + fail-closed proven "
          "(no Playwright / no browser / no network)")
    return 0


def _live_selftest() -> int:
    """Real-Playwright proof against a LOCAL two-origin fixture that mimics a GHL
    canvas builder: a MOUSE-EVENT drag source tile inside a CROSS-ORIGIN iframe.
    Proves the exact mechanism (frame-scoped bounding box across origins + raw
    interpolated pointer drag) end-to-end, HEADLESS. Reports cleanly (nonzero) if
    Playwright is unavailable — never a false pass."""
    if not PLAYWRIGHT_AVAILABLE:
        print("[live-selftest] SKIP/UNAVAILABLE — Playwright (Python) is not importable. "
              "Install scoped to Skill 6: `python3 -m pip install playwright && "
              "python3 -m playwright install chromium`. The frame-scoped drag CANNOT be "
              "proven without it (and agent-browser 0.27.0 alone cannot do it).",
              file=sys.stderr)
        return 2

    import http.server
    import socketserver
    import tempfile
    import threading
    import os as _os

    top_html = (
        "<!doctype html><html><head><title>TOP</title></head><body>"
        "<h1>builder shell</h1>"
        '<iframe id="builder" src="http://localhost:{iport}/inner.html" '
        'style="width:900px;height:520px;border:0"></iframe>'
        "</body></html>")
    # Mimics the REAL GHL builder iframe surfaces: an inline-edit TITLE ("Form 55"
    # — click swaps to an input, Enter commits), a fixed-height SCROLLABLE Quick-Add
    # panel with CATEGORY sections ("City" sits under "Address", far below the
    # fold), and a mouse-event drag canvas with a pointer-distance sensor.
    inner_html = (
        "<!doctype html><html><head><title>inner</title><style>"
        ".tile{padding:8px;margin:4px;border:1px solid #4a4;cursor:grab;user-select:none}"
        "#panel{height:170px;overflow:auto;width:240px;border:1px solid #aaa}"
        "h3{margin:6px 4px 2px}"
        "#canvas{min-height:180px;border:2px dashed #999;padding:10px}</style></head><body>"
        # HIDDEN first-in-DOM 'Submit' text (v1.2.0 fixture) — mimics the live
        # 2026-07-08 ambiguity: `text=Submit` must NOT bind to this node.
        '<div id="ghost-submit" style="display:none">Submit</div>'
        '<div id="titlewrap"></div>'
        "<h2>Quick Add</h2>"
        '<div id="panel">'
        "<h3>Personal Info</h3>"
        '<div class="tile" id="tile-state">State</div>'
        '<div class="tile">Full Name</div>'
        '<div class="tile">Phone</div>'
        '<div class="tile">Email</div>'
        "<h3>Payments</h3>"
        '<div class="tile">Sell Products</div>'
        '<div class="tile">Collect Payment</div>'
        "<h3>Address</h3>"
        '<div class="tile" id="tile-city">City</div>'
        '<div class="tile">Postal Code</div>'
        "</div>"
        # Default canvas field + per-field 'Remove field' link (v1.2.0 fixture —
        # the F4 reconciliation surface, SELECTORS §6) and a REAL role=button
        # Submit landmark (§5) instead of a bare text node.
        '<div id="fields">'
        '<div class="field" id="f-phone">Phone'
        '<input placeholder="+1 (555) 000-0000"></div>'
        "</div>"
        '<a id="remove-link" href="#" style="display:none">Remove field</a>'
        '<div id="canvas"><button id="submit-btn" type="button">Submit</button></div>'
        "<script>"
        "let dragging=null,moves=0;"
        "document.querySelectorAll('.tile').forEach(t=>{"
        "  t.addEventListener('mousedown',e=>{dragging=t.textContent;moves=0;e.preventDefault();});"
        "});"
        "document.addEventListener('mousemove',e=>{if(dragging)moves++;});"
        "const canvas=document.getElementById('canvas');"
        "document.addEventListener('mouseup',e=>{"
        "  if(!dragging)return;"
        "  const r=canvas.getBoundingClientRect();"
        "  const over=e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom;"
        "  if(over&&moves>=3){const d=document.createElement('div');d.className='placed';"
        "    d.textContent=dragging+' placed';canvas.appendChild(d);}"
        "  dragging=null;});"
        "let selectedField=null;"
        "const removeLink=document.getElementById('remove-link');"
        "document.querySelectorAll('.field').forEach(f=>{"
        "  f.addEventListener('click',()=>{selectedField=f;removeLink.style.display='inline';});"
        "});"
        "removeLink.addEventListener('click',e=>{e.preventDefault();"
        "  if(selectedField){selectedField.remove();selectedField=null;"
        "  removeLink.style.display='none';}});"
        "const tw=document.getElementById('titlewrap');"
        "function mountTitle(text){"
        "  tw.innerHTML='';"
        "  const d=document.createElement('div');d.id='title';d.textContent=text;"
        "  d.addEventListener('click',()=>{"
        "    const i=document.createElement('input');i.id='title-edit';i.value=d.textContent;"
        "    tw.innerHTML='';tw.appendChild(i);i.focus();"
        "    i.addEventListener('keydown',e=>{if(e.key==='Enter'){mountTitle(i.value);}});"
        "  });"
        "  tw.appendChild(d);"
        "}"
        "mountTitle('Form 55');"
        "</script></body></html>")

    tmp = tempfile.mkdtemp(prefix="ghl-iframe-drag-live-")
    topdir = _os.path.join(tmp, "top")
    innerdir = _os.path.join(tmp, "inner")
    _os.makedirs(topdir)
    _os.makedirs(innerdir)

    # Two HTTP servers on ephemeral ports; 127.0.0.1 vs localhost = CROSS-ORIGIN.
    class _Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    def _serve(directory):
        handler = lambda *a, **k: _Q(*a, directory=directory, **k)  # noqa: E731
        httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd, port

    errors = []
    top_srv = inner_srv = None
    udd = _os.path.join(tmp, "udd")
    try:
        inner_srv, iport = _serve(innerdir)
        with open(_os.path.join(innerdir, "inner.html"), "w", encoding="utf-8") as fh:
            fh.write(inner_html)
        top_srv, tport = _serve(topdir)
        with open(_os.path.join(topdir, "top.html"), "w", encoding="utf-8") as fh:
            fh.write(top_html.format(iport=iport))

        with sync_playwright() as p:  # type: ignore[union-attr]
            # launch_persistent_context (NOT a bare launch()) — headless, D6-safe.
            ctx = p.chromium.launch_persistent_context(udd, headless=True)
            try:
                page = ctx.new_page()
                # Cross-origin: top served from 127.0.0.1, iframe from localhost.
                page.goto(f"http://127.0.0.1:{tport}/top.html")
                iframe_selector = 'iframe[src*="inner.html"]'

                # (a) HAPPY — drag 'State' onto the canvas 'Submit' landmark.
                rec = drive_drag(page, iframe_selector=iframe_selector,
                                 source="text=State", target="text=Submit",
                                 interpolated_moves=24, verify_text="State placed",
                                 timeout_ms=8000)
                if rec.get("placed") is not True:
                    errors.append(f"live happy-path did not place: {rec}")

                # (b) FAIL-CLOSED — an absent tile raises source-not-found.
                try:
                    drive_drag(page, iframe_selector=iframe_selector,
                               source="text=Nonexistent Tile XYZ", target="text=Submit",
                               interpolated_moves=8, timeout_ms=1500)
                    errors.append("live absent-tile did NOT raise IframeDragError")
                except IframeDragError as e:
                    if e.code != "source-not-found":
                        errors.append(f"live absent-tile wrong code: {e.code}")

                # (c) SCROLL-HINT — 'City' sits under the 'Address' category BELOW
                #     the fold of the fixed-height panel; the category-hint scroll
                #     reveals it and the drag then places it (the F5.locate fix).
                rec_c = drive_drag(page, iframe_selector=iframe_selector,
                                   source="text=City", target="text=Submit",
                                   source_scroll_hint="text=Address",
                                   interpolated_moves=24, verify_text="City placed",
                                   timeout_ms=8000)
                if rec_c.get("placed") is not True:
                    errors.append(f"live scroll-hint drag did not place: {rec_c}")

                # (d) INLINE-TITLE rename — click-to-edit surface inside the
                #     cross-origin iframe (the F3 fix): pattern-locate 'Form 55',
                #     edit, commit, VERIFY.
                rec_d = drive_set_inline_title(
                    page, iframe_selector=iframe_selector,
                    new_title="ZHC TEST Title",
                    title_specs=(r"re:^Form\s*\d+$",), timeout_ms=8000)
                if rec_d.get("old_title") != "Form 55" or rec_d.get("verified") is not True:
                    errors.append(f"live inline-title rename wrong: {rec_d}")

                # (e) INLINE-TITLE read-back — cleanup targets the name the
                #     container ACTUALLY carries.
                rec_e = drive_read_inline_title(
                    page, iframe_selector=iframe_selector,
                    title_specs=("re:^ZHC TEST",), timeout_ms=4000)
                if rec_e.get("title") != "ZHC TEST Title":
                    errors.append(f"live inline-title read wrong: {rec_e}")

                # (f) COUNT-DELTA against a REAL browser (v1.1.1): 'State placed'
                #     already exists from (a); a SECOND drag must push the match
                #     count PAST that baseline (1 → 2) to verify.
                rec_f = drive_drag(page, iframe_selector=iframe_selector,
                                   source="text=State", target="text=Submit",
                                   interpolated_moves=24,
                                   verify_text="State placed", timeout_ms=8000)
                if rec_f.get("verify_pre_count") != 1 or rec_f.get("placed") is not True:
                    errors.append(f"live count-delta verify wrong: {rec_f}")
                # NOTE (v1.2.0): cases (a)/(c)/(f) above now ALSO regression-prove
                # the ambiguous-target fix against a real browser — the fixture
                # carries a HIDDEN first-in-DOM 'Submit' node, so the old blind
                # `.first` would have timed out on every one of them.

                # (g) ROLE-SCOPED drop target (v1.2.0 — SELECTORS §5): the canvas
                #     Submit is a REAL button; `role=button:Submit` must resolve
                #     it (exact accessible name) and the drag must place.
                rec_g = drive_drag(page, iframe_selector=iframe_selector,
                                   source="text=Full Name",
                                   target="role=button:Submit",
                                   interpolated_moves=24,
                                   verify_text="Full Name placed", timeout_ms=8000)
                if rec_g.get("placed") is not True:
                    errors.append(f"live role-target drag did not place: {rec_g}")

                # (h) CANVAS-FIELD REMOVE (v1.2.0 — F4 reconciliation): select
                #     the default 'Phone' field by its DOCUMENTED placeholder
                #     anchor, click the per-field 'Remove field' link, VERIFY
                #     the count dropped; a second remove is a truthful
                #     already-absent NO-OP (idempotent reconciliation).
                rec_h = drive_remove_canvas_field(
                    page, iframe_selector=iframe_selector,
                    field="placeholder=+1 (555) 000-0000", timeout_ms=8000)
                if rec_h.get("removed") is not True or rec_h.get("pre_count") != 1:
                    errors.append(f"live remove-field wrong: {rec_h}")
                rec_h2 = drive_remove_canvas_field(
                    page, iframe_selector=iframe_selector,
                    field="placeholder=+1 (555) 000-0000", timeout_ms=4000)
                if rec_h2.get("already_absent") is not True:
                    errors.append(f"live remove-field re-run not idempotent: {rec_h2}")
            finally:
                ctx.close()
    except IframeDragError as e:
        errors.append(f"unexpected IframeDragError: {e}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"live-selftest crashed: {type(exc).__name__}: {exc}")
    finally:
        for s in (top_srv, inner_srv):
            try:
                if s:
                    s.shutdown()
            except Exception:  # noqa: BLE001
                pass

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[live-selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[live-selftest] PASS — frame-scoped coordinate-drag placed a tile inside a "
          "CROSS-ORIGIN iframe headlessly, and failed closed on an absent tile.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_iframe_drag",
        description="Shared frame-scoped coordinate-drag primitive for Skill-6 GHL "
                    "cross-origin builder iframes (Playwright over agent-browser CDP).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true",
                   help="Dep-free structural proof (no Playwright/browser/network).")
    g.add_argument("--live-selftest", action="store_true",
                   help="Real Playwright proof vs a local cross-origin fixture (headless).")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    return _live_selftest()


if __name__ == "__main__":
    sys.exit(main())

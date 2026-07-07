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
import sys
import time
from typing import Any, Callable, Dict, Optional, Tuple

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
IFRAME_DRAG_VERSION = "v1.0.0"
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


def _resolve_locator(frame: Any, spec: str) -> Any:
    """Resolve a locator SPEC against a Playwright FrameLocator.

    Spec grammar (kept deliberately small; GHL tiles are located by visible text):
      * ``"text=Foo"``  → ``frame.get_by_text("Foo", exact=False).first`` (default)
      * ``"exact=Foo"`` → ``frame.get_by_text("Foo", exact=True).first``
      * ``"css=SEL"``   → ``frame.locator("SEL").first``
      * bare ``"Foo"``  → treated as ``text=Foo``
    """
    if not spec or not str(spec).strip():
        raise IframeDragError("empty-locator", "a source/target locator spec was empty")
    s = str(spec)
    if s.startswith("css="):
        return frame.locator(s[4:]).first
    if s.startswith("exact="):
        return frame.get_by_text(s[6:], exact=True).first
    if s.startswith("text="):
        return frame.get_by_text(s[5:], exact=False).first
    return frame.get_by_text(s, exact=False).first


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
    sleeper: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Perform the frame-scoped coordinate-drag on ``page`` and return a receipt.

    Resolve source + target INSIDE the (possibly cross-origin) iframe, take their
    true page-coordinate bounding boxes, then move the real pointer from source to
    target in many interpolated hops so GHL's drag sensor fires. FAIL-CLOSED: any
    unlocatable element / null box raises :class:`IframeDragError`. When
    ``verify_text`` is given, the placement is confirmed by re-querying the iframe
    for that text and the receipt's ``placed`` reflects the truth (never faked)."""
    if not iframe_selector or not str(iframe_selector).strip():
        raise IframeDragError("empty-iframe-selector", "iframe_selector must be non-empty")

    frame = page.frame_locator(iframe_selector)
    src = _resolve_locator(frame, source)
    tgt = _resolve_locator(frame, target)

    # Wait for the SOURCE tile to be present in the iframe (fail-closed on absence).
    try:
        src.wait_for(state="visible", timeout=timeout_ms)
    except IframeDragError:
        raise
    except Exception as exc:  # noqa: BLE001 - any Playwright timeout/lookup failure
        raise IframeDragError(
            "source-not-found",
            f"drag SOURCE {source!r} was not found/visible inside the cross-origin "
            f"iframe {iframe_selector!r} within {timeout_ms}ms ({type(exc).__name__}). "
            "STOP — the tile is genuinely unreachable; do not brute-force.") from exc

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
        placed = _verify_placed(frame, verify_text, timeout_ms)

    receipt = {
        "ok": True,
        "iframe_selector": iframe_selector,
        "source": source,
        "target": target,
        "source_box": sbox,
        "target_box": tbox,
        "source_point": [sx, sy],
        "target_point": [tx, ty],
        "mouse_events": moves,        # move + down(implicit) + interp + settle
        "interpolated_moves": int(max(1, interpolated_moves)),
        "verify_text": verify_text,
        "placed": placed,
    }
    if verify_text and placed is False:
        raise IframeDragError(
            "not-placed",
            f"performed the drag but {verify_text!r} did not appear inside the iframe "
            f"after drop — the placement did NOT verify. STOP (never report a fake "
            f"success). receipt={receipt}")
    return receipt


def _verify_placed(frame: Any, text: str, timeout_ms: int) -> bool:
    """Best-effort confirmation that ``text`` is now present inside the iframe.
    Returns True/False; never raises for a plain 'not found' (the caller decides)."""
    deadline = time.monotonic() + max(0.0, timeout_ms / 1000.0)
    loc = frame.get_by_text(text, exact=False)
    while True:
        try:
            if loc.count() > 0:
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
        (others): drag-sensor tuning + a small target offset.

    Returns:
        A receipt dict (see :func:`drive_drag`).

    Raises:
        IframeDragError: fail-closed on any unavailable Playwright, missing page/
            frame, unlocatable source/target, or an unverified placement. NEVER
            fakes success. The underlying agent-browser Chromium is NOT closed —
            only the Playwright CDP connection is detached.
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise IframeDragError(
            "playwright-unavailable",
            "the frame-scoped coordinate-drag needs Playwright (Python) to reach into "
            "the cross-origin GHL builder iframe, and it is not importable here. Install "
            "it SCOPED to Skill 6 (e.g. `python3 -m pip install playwright && python3 -m "
            "playwright install chromium`). agent-browser 0.27.0 alone CANNOT locate a "
            "non-interactive tile across a cross-origin iframe (see module docstring).")
    if not cdp_url or not str(cdp_url).strip():
        raise IframeDragError(
            "no-cdp-url",
            "no CDP url was supplied — read it from the live agent-browser session with "
            "`get cdp-url` and pass it in so Playwright attaches to the SAME logged-in "
            "Chromium (no second browser, no re-login).")

    with sync_playwright() as p:  # type: ignore[union-attr]
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
        except Exception as exc:  # noqa: BLE001
            raise IframeDragError(
                "cdp-connect-failed",
                f"could not attach Playwright to agent-browser's Chromium at the given "
                f"CDP endpoint ({type(exc).__name__}). Confirm the session is alive "
                f"(`get cdp-url`).") from exc
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
            )
        finally:
            # Detach the Playwright CDP connection WITHOUT killing agent-browser's
            # Chromium (it owns the singleton pooled session + its teardown). For a
            # connect_over_cdp browser, close() disconnects the client only.
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

    # 3. locator spec dispatch.
    class _FrameSpy:
        def __init__(self):
            self.calls = []

        def get_by_text(self, text, exact=False):
            self.calls.append(("text", text, exact))
            return _LocStub()

        def locator(self, sel):
            self.calls.append(("css", sel))
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
    if fs.calls != [("text", "State", False), ("text", "City", False),
                    ("text", "Submit", True), ("css", "#tile-state")]:
        errors.append(f"locator dispatch wrong: {fs.calls}")
    try:
        _resolve_locator(fs, "")
        errors.append("empty locator spec did not raise")
    except IframeDragError:
        pass

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
        def __init__(self, box, present_after=True):
            self._box = box
            self._present = present_after

        @property
        def first(self):
            return self

        def wait_for(self, state="visible", timeout=0):
            if self._box is None:
                raise TimeoutError("mock: not visible")

        def bounding_box(self):
            return self._box

        def count(self):
            return 1 if self._present else 0

    class _MockFrame:
        def __init__(self, boxes, verify_present=True):
            self._boxes = boxes
            self._verify_present = verify_present

        def get_by_text(self, text, exact=False):
            return _MockLoc(self._boxes.get(text), present_after=self._verify_present)

        def locator(self, sel):
            return _MockLoc(self._boxes.get(sel))

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
    inner_html = (
        "<!doctype html><html><head><title>inner</title><style>"
        ".tile{padding:8px;margin:4px;border:1px solid #4a4;cursor:grab;user-select:none}"
        "#canvas{min-height:180px;border:2px dashed #999;padding:10px}</style></head><body>"
        "<h2>Quick Add</h2>"
        '<div class="tile" id="tile-state">State</div>'
        '<div class="tile" id="tile-city">City</div>'
        '<div id="canvas">Submit</div>'
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

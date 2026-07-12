"""Regression tests for the cross-origin-iframe drag FIX (fix/skill6-ghl-form-iframe-drag).

LOCKS IN the shared frame-scoped coordinate-drag primitive
(``06-ghl-install-pages/tools/ghl_iframe_drag.py``) and its wiring into the FORM
builder (``ghl_form_builder.py``) and SURVEY builder (``ghl_survey_builder.py``).

THE BUG: the GHL form/survey builders render inside a CROSS-ORIGIN iframe. The
Quick-Add / Add-Object-Field tiles are non-interactive nodes with no CDP ref, and
agent-browser 0.27.0 cannot LOCATE them across the cross-origin boundary (its
``frame`` verb only re-scopes the read-only a11y snapshot; ``eval``/``find``/
``drag`` still bind to the top frame — verified live, SELECTORS-LIVE-form.md §7).
So ``drag`` failed to resolve the source and the build correctly STOPPED.

THE FIX: delegate ONLY the drag to Playwright, attached over CDP to the SAME
already-logged-in agent-browser Chromium, using a frame-scoped locator +
bounding-box + raw interpolated-pointer drag. This suite proves:
  1. the primitive's coordinate mechanism + fail-closed behavior (hermetic mock);
  2. both builders route the drag through the frame-scoped seam (NOT a top-frame
     ``drag``) and STOP-and-report when the primitive/CDP is unavailable;
  3. (Playwright-gated) the real end-to-end drag places a tile inside a genuine
     cross-origin iframe, headless — skipped cleanly when Playwright is absent.

HERMETIC by default — NO network, NO live browser, NO GHL. Style + sys.path mirror
``test_ghl_form_builder_capture.py`` so this runs under the same pytest CI.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# ── sys.path setup (mirrors the sibling 06 tests) ─────────────────────────────
_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ghl_iframe_drag as idg  # noqa: E402
import ghl_form_builder as fb  # noqa: E402
import ghl_survey_builder as sb  # noqa: E402


# ---------------------------------------------------------------------------
# Mock Playwright surface (only the members drive_drag touches)
# ---------------------------------------------------------------------------
class _MockMouse:
    def __init__(self):
        self.ops = []

    def move(self, x, y):
        self.ops.append(("move", round(x, 2), round(y, 2)))

    def down(self):
        self.ops.append(("down",))

    def up(self):
        self.ops.append(("up",))


class _MockLoc:
    """Count-delta world (v1.1.1): count() returns 1 on the FIRST read (the
    pre-drag baseline — the tile itself already matches the verify text) and,
    when the placement 'landed' (present), 2 on later reads. A failed placement
    stays at the baseline forever — which must read as NOT placed.
    v1.2.0: also exposes nth()/is_visible() for the visible-match scan."""
    def __init__(self, frame, box, present=True):
        self._frame = frame
        self._box = box
        self._present = present
        self.scrolled = 0

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
        self.scrolled += 1

    def bounding_box(self):
        return self._box

    def count(self):
        self._frame.count_reads += 1
        if self._frame.count_reads == 1:
            return 1
        return 2 if self._present else 1


class _MockFrame:
    def __init__(self, boxes, verify_present=True):
        self._boxes = boxes
        self._verify_present = verify_present
        self.count_reads = 0

    def get_by_text(self, text, exact=False):
        return _MockLoc(self, self._boxes.get(text), present=self._verify_present)

    def locator(self, sel):
        return _MockLoc(self, self._boxes.get(sel))


class _MockPage:
    def __init__(self, frame):
        self.mouse = _MockMouse()
        self._frame = frame

    def frame_locator(self, sel):
        return self._frame


# ---------------------------------------------------------------------------
# 1. Primitive mechanism (hermetic)
# ---------------------------------------------------------------------------
def test_selftest_passes():
    """The module's own dep-free structural self-test passes."""
    assert idg._selftest() == 0


def test_drive_drag_pointer_envelope_and_verify():
    boxes = {"State": {"x": 100, "y": 150, "width": 80, "height": 30},
             "Submit": {"x": 90, "y": 400, "width": 120, "height": 40}}
    page = _MockPage(_MockFrame(boxes, verify_present=True))
    rec = idg.drive_drag(page, iframe_selector='iframe[src*="form-builder-v2"]',
                         source="text=State", target="text=Submit",
                         interpolated_moves=24, move_interval_ms=0, settle_ms=0,
                         verify_text="State", sleeper=lambda s: None)
    ops = page.mouse.ops
    assert ops[0][0] == "move" and ops[1] == ("down",) and ops[-1] == ("up",)
    # 1 start + 24 interpolated + 1 settle == 26 moves; must cross the sensor threshold
    assert sum(1 for o in ops if o[0] == "move") == 26
    assert rec["placed"] is True
    assert rec["source_point"] == [140.0, 165.0]
    assert rec["target_point"] == [150.0, 420.0]


def test_interpolated_moves_meet_sensor_minimum():
    """gates.json requires >= 20 interpolated moves; a single jump does not trip
    GHL's drag sensor. Default must satisfy the minimum."""
    assert idg.DEFAULT_INTERPOLATED_MOVES >= 20
    pts = list(idg._interpolate(0, 0, 10, 10, idg.DEFAULT_INTERPOLATED_MOVES))
    assert len(pts) == idg.DEFAULT_INTERPOLATED_MOVES


def test_fail_closed_missing_source_box():
    page = _MockPage(_MockFrame({"State": None, "Submit": {"x": 0, "y": 0, "width": 1, "height": 1}}))
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_drag(page, iframe_selector="iframe", source="text=State",
                       target="text=Submit", move_interval_ms=0, settle_ms=0,
                       sleeper=lambda s: None)
    assert ei.value.code in ("source-not-found", "source-no-box")


def test_fail_closed_unverified_placement():
    boxes = {"State": {"x": 0, "y": 0, "width": 10, "height": 10},
             "Submit": {"x": 0, "y": 50, "width": 10, "height": 10}}
    page = _MockPage(_MockFrame(boxes, verify_present=False))
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_drag(page, iframe_selector="iframe", source="text=State",
                       target="text=Submit", verify_text="State",
                       move_interval_ms=0, settle_ms=0, timeout_ms=0,
                       sleeper=lambda s: None)
    assert ei.value.code == "not-placed"


def test_preexisting_tile_match_cannot_fake_placement():
    """v1.1.1 COUNT-DELTA hardening: for a Quick-Add drag the verify text
    equals the TILE's own label, which matches BEFORE the drag. A drop that
    never landed leaves the count at its baseline — that must be `not-placed`,
    never a success (this was trivially satisfiable before)."""
    boxes = {"City": {"x": 0, "y": 0, "width": 10, "height": 10},
             "Submit": {"x": 0, "y": 50, "width": 10, "height": 10}}
    frame = _MockFrame(boxes, verify_present=False)   # count NEVER increases
    page = _MockPage(frame)
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_drag(page, iframe_selector="iframe", source="text=City",
                       target="text=Submit", verify_text="City",
                       move_interval_ms=0, settle_ms=0, timeout_ms=0,
                       sleeper=lambda s: None)
    assert ei.value.code == "not-placed"
    assert "pre-drag baseline" in str(ei.value)


def test_receipt_carries_the_verify_baseline():
    boxes = {"State": {"x": 100, "y": 150, "width": 80, "height": 30},
             "Submit": {"x": 90, "y": 400, "width": 120, "height": 40}}
    page = _MockPage(_MockFrame(boxes, verify_present=True))
    rec = idg.drive_drag(page, iframe_selector="iframe", source="text=State",
                         target="text=Submit", verify_text="State",
                         move_interval_ms=0, settle_ms=0, sleeper=lambda s: None)
    assert rec["verify_pre_count"] == 1, "the tile's own pre-drag match is the baseline"
    assert rec["placed"] is True, "count 2 > baseline 1 = the real placement proof"


def test_coordinate_drag_reports_when_playwright_absent(monkeypatch):
    monkeypatch.setattr(idg, "PLAYWRIGHT_AVAILABLE", False)
    with pytest.raises(idg.IframeDragError) as ei:
        idg.coordinate_drag("ws://x", iframe_selector="iframe",
                            source="text=A", target="text=B")
    assert ei.value.code == "playwright-unavailable"


def test_iframe_selector_presets():
    assert idg.iframe_selector_for("form") == 'iframe[src*="form-builder-v2"]'
    assert idg.iframe_selector_for("survey") == 'iframe[src*="survey-builder-v2"]'
    with pytest.raises(idg.IframeDragError):
        idg.iframe_selector_for("nope")


# ---------------------------------------------------------------------------
# 2. Builder wiring — drag routes through the frame-scoped seam, fail-closed
# ---------------------------------------------------------------------------
def test_form_builder_drag_routes_through_frame_scoped_seam(monkeypatch):
    """The FORM builder must call the frame-scoped seam (NOT a top-frame `_ab drag`)
    and pass the form-builder iframe selector + the tile's CATEGORY scroll hint."""
    calls = []

    def fake_drag(session, source_text, drop_anchor, *, verify_text,
                  iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR, source_scroll_hint=""):
        calls.append((source_text, drop_anchor, verify_text, iframe_selector,
                      source_scroll_hint))
        return {"ok": True, "placed": True}

    ab_calls = []

    def fake_ab(session, *args, timeout=30, stdin=None):
        ab_calls.append(args)
        snap = ("Form Element Quick Add Submit Email State City Label Query Key "
                "Field Width Required Hidden")
        out = snap if (args and args[0] == "snapshot") else ""
        return subprocess.CompletedProcess(args=list(args), returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(fb, "_ab", fake_ab)
    monkeypatch.setattr(fb, "_perform_iframe_drag", fake_drag)
    field = {"source": "standard", "element": "State", "label": "State",
             "query_key": "state", "width_pct": 50, "required": True, "hidden": False}
    fb._place_quick_add_field("s", field, "/tmp/x-iframe-test", [0], [], [])

    assert len(calls) == 1, "standard field must be placed via the frame-scoped seam"
    assert calls[0][3] == fb.GHL_FORM_IFRAME_SELECTOR
    assert calls[0][4] == "Address", "the tile's Quick-Add CATEGORY must ride along as the scroll hint"
    assert not any(c and c[0] == "drag" for c in ab_calls), "must NOT use a top-frame `_ab drag`"


def test_form_builder_drag_stops_when_primitive_absent(monkeypatch):
    """When ghl_iframe_drag is unavailable, the FORM seam STOPS-and-reports (never
    a fake success, never a top-frame brute-force)."""
    monkeypatch.setattr(fb, "ghl_iframe_drag", None)
    with pytest.raises(fb.StopAndReport) as ei:
        fb._perform_iframe_drag("s", "State", "Submit", verify_text="State")
    assert ei.value.step == "iframe-drag.dep"


def test_form_builder_drag_stops_when_no_cdp(monkeypatch):
    monkeypatch.setattr(fb, "_get_cdp_url", lambda session: "")
    # ghl_iframe_drag must be importable for this path (it is, in-repo).
    assert fb.ghl_iframe_drag is not None
    with pytest.raises(fb.StopAndReport) as ei:
        fb._perform_iframe_drag("s", "State", "Submit", verify_text="State")
    assert ei.value.step == "iframe-drag.cdp"


def test_survey_builder_uses_shared_primitive_and_selector():
    """The SURVEY builder wires the SAME shared primitive with its own iframe host."""
    assert sb.GHL_SURVEY_IFRAME_SELECTOR == 'iframe[src*="survey-builder-v2"]'
    assert hasattr(sb, "_perform_iframe_drag")
    # both builders resolve the SAME primitive module object.
    assert sb._ghl_iframe_drag is not None


def test_survey_builder_drag_stops_when_no_cdp(monkeypatch):
    monkeypatch.setattr(sb, "_get_cdp_url", lambda session: "")
    with pytest.raises(RuntimeError) as ei:
        sb._perform_iframe_drag("s", "Rating", "Slide 2", verify_text="Rating")
    # P3-04 (c)4 fix-loop item 6: this pre-flight STOP is now a classified
    # sb._InfraStop (still a RuntimeError -- pytest.raises above is unchanged)
    # carrying a SELECTOR-MISS board note instead of a bare, unclassified
    # "STOP (survey iframe-drag): ..." string.
    assert "cdp-url-missing" in str(ei.value)
    assert ei.value.board_note.startswith("SELECTOR-MISS: ")


def test_survey_rename_routes_through_frame_scoped_primitive(monkeypatch):
    """v18.1.5: the SURVEY Phase-B rename must ride set_inline_title with the
    survey iframe selector + the 'Survey <n>' pattern specs — the old top-frame
    dblclick/fill walk could never reach the in-iframe title (the same silent
    failure the FORM builder hit live 2026-07-07)."""
    calls = {}

    class _FakeIdg:
        DEFAULT_SURVEY_TITLE_SPECS = (r"re:^Survey\s*\d+$", "text=Untitled")

        class IframeDragError(RuntimeError):
            def __init__(self, code, reason):
                self.code, self.reason = code, reason
                super().__init__(f"{code}: {reason}")

        @staticmethod
        def set_inline_title(cdp_url, *, iframe_selector, new_title,
                             title_specs, url_marker):
            calls["set"] = {"iframe_selector": iframe_selector,
                            "new_title": new_title,
                            "title_specs": tuple(title_specs),
                            "url_marker": url_marker}
            return {"ok": True, "old_title": "Survey 0", "verified": True}

    monkeypatch.setattr(sb, "_ghl_iframe_drag", _FakeIdg)
    monkeypatch.setattr(sb, "_get_cdp_url", lambda session: "ws://live")
    monkeypatch.setattr(sb, "_wait", lambda session, text, timeout=25: None)
    monkeypatch.setattr(sb, "_screenshot", lambda session, path: None)
    sb._p2_rename_survey("s", "ZHC Intake Survey", "/tmp/x-sb-rename", [0])
    assert calls["set"]["iframe_selector"] == sb.GHL_SURVEY_IFRAME_SELECTOR
    assert calls["set"]["url_marker"] == "survey-builder"
    assert calls["set"]["new_title"] == "ZHC Intake Survey"
    assert any(s.startswith("re:^Survey") for s in calls["set"]["title_specs"])


def test_survey_rename_stops_when_primitive_or_cdp_missing(monkeypatch):
    """A survey must never proceed default-named: no primitive / no CDP / a
    failed rename are all honest STOPs, not warnings."""
    monkeypatch.setattr(sb, "_ghl_iframe_drag", None)
    with pytest.raises(RuntimeError) as ei:
        sb._p2_rename_survey("s", "ZHC X", "/tmp/x-sb-r1", [0])
    # P3-04 (c)4 fix-loop item 6: this pre-flight STOP is now a classified
    # sb._InfraStop (still a RuntimeError -- pytest.raises above is unchanged)
    # carrying a SELECTOR-MISS board note instead of a bare, unclassified
    # "STOP (survey rename): ..." string.
    assert "primitive-unavailable" in str(ei.value)
    assert ei.value.board_note.startswith("SELECTOR-MISS: ")

    class _FailingIdg:
        DEFAULT_SURVEY_TITLE_SPECS = (r"re:^Survey\s*\d+$",)

        class IframeDragError(RuntimeError):
            def __init__(self, code, reason):
                self.code, self.reason = code, reason
                super().__init__(f"{code}: {reason}")

        # P3-04 (c)4: the real IframeDragStop's __init__ closes over the real
        # module's classify_board_reason()/board_note() (pure, duck-typed on
        # .code/.reason/.details) — reuse it verbatim rather than re-implementing.
        IframeDragStop = idg.IframeDragStop

        @classmethod
        def set_inline_title(cls, *a, **k):
            raise cls.IframeDragError("title-not-editable", "no editor took focus")

    monkeypatch.setattr(sb, "_ghl_iframe_drag", _FailingIdg)
    monkeypatch.setattr(sb, "_get_cdp_url", lambda session: "")
    with pytest.raises(RuntimeError):
        sb._p2_rename_survey("s", "ZHC X", "/tmp/x-sb-r2", [0])
    monkeypatch.setattr(sb, "_get_cdp_url", lambda session: "ws://live")
    with pytest.raises(RuntimeError) as ei3:
        sb._p2_rename_survey("s", "ZHC X", "/tmp/x-sb-r3", [0])
    assert "title-not-editable" in str(ei3.value)


# ---------------------------------------------------------------------------
# 3. SCROLL-INTO-VIEW + CATEGORY-HINT locate (v1.1.0 — the F5.locate:City fix)
# ---------------------------------------------------------------------------
class _ScrollWorld:
    """City is hidden below the Quick-Add fold until 'Address' is scrolled into view."""
    def __init__(self):
        self.boxes = {"Address": {"x": 20, "y": 300, "width": 100, "height": 20},
                      "Submit": {"x": 90, "y": 400, "width": 120, "height": 40}}
        self.hidden = {"City": {"x": 24, "y": 340, "width": 80, "height": 30}}
        self.scrolled = []

    def scroll(self, key):
        self.scrolled.append(key)
        if key == "Address":
            self.boxes.update(self.hidden)
            self.hidden = {}


class _ScrollLoc:
    def __init__(self, world, key):
        self._w, self._k = world, key

    @property
    def first(self):
        return self

    def nth(self, i):
        return self

    def is_visible(self):
        return self._k in self._w.boxes

    def wait_for(self, state="visible", timeout=0):
        if self._k not in self._w.boxes:
            raise TimeoutError(f"mock: {self._k} not visible")

    def scroll_into_view_if_needed(self, timeout=0):
        if self._k not in self._w.boxes:
            raise TimeoutError(f"mock: {self._k} cannot scroll")
        self._w.scroll(self._k)

    def bounding_box(self):
        return self._w.boxes.get(self._k)

    def count(self):
        return 1 if self._k in self._w.boxes else 0


class _ScrollFrame:
    def __init__(self, world):
        self._w = world

    def get_by_text(self, text, exact=False):
        return _ScrollLoc(self._w, text if isinstance(text, str) else "City")

    def locator(self, sel):
        return _ScrollLoc(self._w, sel)


def test_scroll_hint_reveals_below_the_fold_tile_and_drag_places_it():
    """The general F5.locate fix: a tile in a category below the panel fold is
    revealed by scrolling the CATEGORY header, then scrolled + dragged — for ANY
    field/category, not a City-only patch."""
    world = _ScrollWorld()
    page = _MockPage(_ScrollFrame(world))
    rec = idg.drive_drag(page, iframe_selector="iframe", source="text=City",
                         target="text=Submit", source_scroll_hint="text=Address",
                         verify_text="City", move_interval_ms=0, settle_ms=0,
                         sleeper=lambda s: None)
    assert world.scrolled == ["Address", "City", "Submit"], \
        "hint scrolls first, then the revealed tile, then the drop target"
    assert rec["placed"] is True
    assert rec["source_scroll_hint"] == "text=Address"
    assert page.mouse.ops[-1] == ("up",)


def test_scroll_hint_missing_tile_still_fails_closed():
    """The hint reveals the section but the tile is GENUINELY absent → honest
    source-not-found (never a guessed pointer target)."""
    world = _ScrollWorld()
    world.hidden = {}                      # Address scroll reveals nothing
    page = _MockPage(_ScrollFrame(world))
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_drag(page, iframe_selector="iframe", source="text=City",
                       target="text=Submit", source_scroll_hint="text=Address",
                       move_interval_ms=0, settle_ms=0, sleeper=lambda s: None)
    assert ei.value.code == "source-not-found"
    assert "Address" in str(ei.value)


def test_hidden_tile_without_hint_fails_closed():
    page = _MockPage(_ScrollFrame(_ScrollWorld()))
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_drag(page, iframe_selector="iframe", source="text=City",
                       target="text=Submit", move_interval_ms=0, settle_ms=0,
                       sleeper=lambda s: None)
    assert ei.value.code == "source-not-found"


def test_absent_scroll_hint_fails_closed_with_its_own_code():
    world = _ScrollWorld()
    page = _MockPage(_ScrollFrame(world))
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_drag(page, iframe_selector="iframe", source="text=City",
                       target="text=Submit", source_scroll_hint="text=Nope",
                       move_interval_ms=0, settle_ms=0, sleeper=lambda s: None)
    assert ei.value.code == "scroll-hint-not-found"


def test_boxes_read_after_scroll_positions():
    """The drag must aim at the POST-scroll coordinates of the revealed tile."""
    world = _ScrollWorld()
    page = _MockPage(_ScrollFrame(world))
    rec = idg.drive_drag(page, iframe_selector="iframe", source="text=City",
                         target="text=Submit", source_scroll_hint="text=Address",
                         move_interval_ms=0, settle_ms=0, sleeper=lambda s: None)
    assert rec["source_point"] == [64.0, 355.0]     # center of the REVEALED City box


def test_regex_locator_spec_dispatch():
    """The 're:' spec resolves through get_by_text(re.compile(...)) — needed for
    pattern-only surfaces like the default builder title 'Form <n>'."""
    calls = []

    class _F:
        def get_by_text(self, pat, exact=False):
            calls.append(pat)
            class _L:
                first = None
            l = _L()
            l.first = l
            return l

        def locator(self, sel):
            raise AssertionError("re: must not fall through to CSS")

    idg._resolve_locator(_F(), r"re:^Form\s*\d+$")
    assert len(calls) == 1 and hasattr(calls[0], "search"), "must pass a compiled regex"


# ---------------------------------------------------------------------------
# 4. FRAME-SCOPED INLINE-TITLE read/set (v1.1.0 — the F3 rename fix)
# ---------------------------------------------------------------------------
class _TitleFrame:
    def __init__(self, editable=True):
        self.texts = {"Form 55"}
        self.editable = editable
        self.focused = False

    def get_by_text(self, pattern, exact=False):
        if hasattr(pattern, "search"):
            hit = next((t for t in sorted(self.texts) if pattern.search(t)), None)
        else:
            hit = next((t for t in sorted(self.texts)
                        if (t == pattern if exact else str(pattern) in t)), None)
        return _TitleLoc(self, hit)

    def locator(self, sel):
        return _BodyLoc(self) if sel == "body" else _TitleLoc(self, None)


class _TitleLoc:
    def __init__(self, frame, text):
        self._f, self._t = frame, text

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
            self._f.texts.add(text)


class _TitlePage:
    def __init__(self, frame):
        self._frame = frame
        self.keyboard = _TitleKeyboard(frame)
        self.mouse = _MockMouse()

    def frame_locator(self, sel):
        return self._frame


def test_set_inline_title_renames_and_verifies():
    tf = _TitleFrame(editable=True)
    tp = _TitlePage(tf)
    rec = idg.drive_set_inline_title(
        tp, iframe_selector="iframe", new_title="ZHC TEST - DO NOT USE",
        title_specs=(r"re:^Form\s*\d+$",), timeout_ms=1000, sleeper=lambda s: None)
    assert rec["old_title"] == "Form 55"
    assert rec["verified"] is True
    presses = [o[1] for o in tp.keyboard.ops if o[0] == "press"]
    assert any(p.lower().endswith("+a") for p in presses), "select-all must precede typing"
    assert presses[-1] == "Enter", "commit key must be pressed"
    assert ("type", "ZHC TEST - DO NOT USE") in tp.keyboard.ops


def test_set_inline_title_fails_closed_when_not_editable():
    """The OLD silent-failure mode (typing into a surface that never entered edit
    mode) must now be an honest STOP, BEFORE any keystroke."""
    tf = _TitleFrame(editable=False)
    tp = _TitlePage(tf)
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_set_inline_title(tp, iframe_selector="iframe", new_title="X",
                                   title_specs=(r"re:^Form\s*\d+$",),
                                   timeout_ms=500, sleeper=lambda s: None)
    assert ei.value.code == "title-not-editable"
    assert not any(o[0] == "type" for o in tp.keyboard.ops), \
        "must NOT type into a non-editable surface"


def test_set_inline_title_fails_closed_when_title_absent():
    tf = _TitleFrame()
    tf.texts = {"Something Else"}
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_set_inline_title(_TitlePage(tf), iframe_selector="iframe",
                                   new_title="X", title_specs=(r"re:^Form\s*\d+$",),
                                   timeout_ms=500, sleeper=lambda s: None)
    assert ei.value.code == "title-not-found"


def test_read_inline_title_returns_actual_text():
    tf = _TitleFrame()
    rec = idg.drive_read_inline_title(_TitlePage(tf), iframe_selector="iframe",
                                      title_specs=(r"re:^Form\s*\d+$",),
                                      timeout_ms=500)
    assert rec["title"] == "Form 55"


def test_title_entry_points_require_playwright_and_cdp(monkeypatch):
    monkeypatch.setattr(idg, "PLAYWRIGHT_AVAILABLE", False)
    with pytest.raises(idg.IframeDragError) as ei:
        idg.set_inline_title("ws://x", iframe_selector="iframe", new_title="T")
    assert ei.value.code == "playwright-unavailable"
    with pytest.raises(idg.IframeDragError) as ei2:
        idg.read_inline_title("ws://x", iframe_selector="iframe",
                              title_specs=("text=T",))
    assert ei2.value.code == "playwright-unavailable"
    monkeypatch.setattr(idg, "PLAYWRIGHT_AVAILABLE", True)
    with pytest.raises(idg.IframeDragError) as ei3:
        idg.set_inline_title("", iframe_selector="iframe", new_title="T")
    assert ei3.value.code == "no-cdp-url"


# ---------------------------------------------------------------------------
# 5. FORM-BUILDER F5 wiring of the scroll-hint locate (the live failure surface)
# ---------------------------------------------------------------------------
def _snap_ab(snap_text):
    def fake_ab(session, *args, timeout=30, stdin=None):
        out = snap_text if (args and args[0] == "snapshot") else ""
        return subprocess.CompletedProcess(args=list(args), returncode=0,
                                           stdout=out, stderr="")
    return fake_ab


def test_f5_snapshot_miss_no_longer_stops_and_passes_category_hint(monkeypatch):
    """LIVE 2026-07-07 regression (F5.locate:City): the tile absent from the
    TOP-FRAME snapshot must NOT stop the walk — the frame-scoped drag runs with
    the tile's category as the scroll hint."""
    calls = []

    def fake_drag(session, source_text, drop_anchor, *, verify_text,
                  iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR, source_scroll_hint=""):
        calls.append((source_text, drop_anchor, source_scroll_hint))
        return {"ok": True, "placed": True}

    # snapshot has the canvas anchors but NOT the City tile (below the fold)
    monkeypatch.setattr(fb, "_ab", _snap_ab("Form Element Quick Add Submit Email"))
    monkeypatch.setattr(fb, "_perform_iframe_drag", fake_drag)
    field = {"source": "standard", "element": "City", "label": "City",
             "query_key": "city", "quick_add_category": "Address",
             "width_pct": 50, "required": True, "hidden": False}
    warnings, steps = [], []
    fb._place_quick_add_field("s", field, "/tmp/x-f5-city", [0], warnings, steps)
    # v18.1.9: the drop anchor is the ROLE-SCOPED Submit spec (SELECTORS §5) —
    # plain 'Submit' text is ambiguous inside the iframe (live 2026-07-08).
    assert calls == [("City", "role=button:Submit", "Address")]
    assert any(s.startswith("F5:place:City") for s in steps)


def test_f5_frame_scoped_locate_miss_maps_to_f5_locate_step(monkeypatch):
    """A GENUINE in-frame miss (tile absent even after the category scroll) must
    surface as the honest F5.locate:<tile> STOP."""
    def missing_drag(session, source_text, drop_anchor, *, verify_text,
                     iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR, source_scroll_hint=""):
        raise fb.StopAndReport("iframe-drag:source-not-found", "mock: genuinely absent")

    monkeypatch.setattr(fb, "_ab", _snap_ab("Form Element Quick Add Submit Email"))
    monkeypatch.setattr(fb, "_perform_iframe_drag", missing_drag)
    field = {"source": "standard", "element": "City", "label": "City",
             "query_key": "city", "quick_add_category": "Address",
             "width_pct": 100, "required": False, "hidden": False}
    with pytest.raises(fb.StopAndReport) as ei:
        fb._place_quick_add_field("s", field, "/tmp/x-f5-miss", [0], [], [])
    assert ei.value.step == "F5.locate:City"
    assert "Address" in ei.value.reason


def test_f5_in_frame_verified_placement_survives_snapshot_lag(monkeypatch):
    """The frame-scoped verify is AUTHORITATIVE: a placement verified in-frame
    must not be failed by a lagging top-frame snapshot — it is recorded as a
    warning instead (the same unreliable surface that caused the false STOP)."""
    monkeypatch.setattr(fb, "_ab", _snap_ab("Form Element Quick Add Submit Email"))
    monkeypatch.setattr(
        fb, "_perform_iframe_drag",
        lambda session, s, a, *, verify_text, iframe_selector=None,
        source_scroll_hint="": {"ok": True, "placed": True})
    field = {"source": "standard", "element": "City", "label": "City",
             "query_key": "city", "quick_add_category": "Address",
             "width_pct": 100, "required": False, "hidden": False}
    warnings, steps = [], []
    fb._place_quick_add_field("s", field, "/tmp/x-f5-lag", [0], warnings, steps)
    assert any("snapshot" in w for w in warnings), "snapshot lag recorded as evidence"
    assert any(s.startswith("F5:place:City") for s in steps), "placement still recorded"


# ---------------------------------------------------------------------------
# 6. AMBIGUOUS-TARGET + role/placeholder specs (v1.2.0 — LIVE 2026-07-08 fix)
#    Attempt #5 against the real account: the drop target `text=Submit` timed
#    out (`target-not-found`) with the canvas Submit button ON SCREEN, because
#    the Quick-Add panel carries its own 'Submit' CATEGORY header + tile
#    (SELECTORS §8) and the blind `.first` bound to a hidden match. The
#    template's KEPT default fields (Phone, Terms & Conditions) are what made
#    those panel surfaces + the taller canvas collide in the first place.
# ---------------------------------------------------------------------------
class _AmbigLoc:
    """A text spec with SEVERAL matches — per-match box (None = hidden)."""
    def __init__(self, frame, key, boxes, idx=0):
        self._frame, self._key, self._boxes, self._i = frame, key, boxes, idx

    @property
    def first(self):
        return self.nth(0)

    def nth(self, i):
        return _AmbigLoc(self._frame, self._key, self._boxes, i)

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
        if self._key == "State":                 # count-delta verify surface
            self._frame.state_reads += 1
            return 1 if self._frame.state_reads == 1 else 2
        return len(self._boxes)


class _AmbigFrame:
    """'Submit' matches N nodes (panel header/tile vs canvas button world);
    'State' is the ordinary drag source."""
    def __init__(self, submit_boxes):
        self.state_reads = 0
        self._submit = submit_boxes
        self._state = [{"x": 100, "y": 150, "width": 80, "height": 30}]

    def get_by_text(self, text, exact=False):
        key = "Submit" if "Submit" in str(text) else "State"
        return _AmbigLoc(self, key, self._submit if key == "Submit" else self._state)

    def locator(self, sel):
        return _AmbigLoc(self, "css", [])


def test_ambiguous_target_resolves_the_visible_match_not_dom_first():
    """THE live 2026-07-08 regression: the first-in-DOM 'Submit' match is HIDDEN
    while the real canvas landmark is visible — the drag must bind the VISIBLE
    match (the old blind `.first` timed out here) and aim the drop at ITS center."""
    vis = {"x": 90, "y": 400, "width": 120, "height": 40}
    page = _MockPage(_AmbigFrame([None, vis]))
    rec = idg.drive_drag(page, iframe_selector="iframe", source="text=State",
                         target="text=Submit", verify_text="State",
                         move_interval_ms=0, settle_ms=0, timeout_ms=250,
                         sleeper=lambda s: None)
    assert rec["placed"] is True
    assert rec["target_matches"] == 2, "diagnostics: both attached matches counted"
    assert rec["target_point"] == [150.0, 420.0], "aimed at the VISIBLE match's center"


def test_all_hidden_target_still_fails_closed_with_match_diagnostics():
    """When NO 'Submit' match is visible the honest target-not-found remains —
    now naming how many attached matches were scanned (evidence for the receipt)."""
    page = _MockPage(_AmbigFrame([None, None]))
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_drag(page, iframe_selector="iframe", source="text=State",
                       target="text=Submit", move_interval_ms=0, settle_ms=0,
                       timeout_ms=100, sleeper=lambda s: None)
    assert ei.value.code == "target-not-found"
    assert "2 attached match(es)" in ei.value.reason


def test_role_and_placeholder_locator_specs_dispatch():
    """`role=button:Submit` → get_by_role(..., exact=True) (the F2-'Create'
    collision class of fix, SELECTORS §5); `placeholder=...` → get_by_placeholder
    (the §6 documented per-field canvas anchors)."""
    calls = []

    class _L:
        @property
        def first(self):
            return self

    class _F:
        def get_by_role(self, role, name=None, exact=False):
            calls.append(("role", role, name, exact))
            return _L()

        def get_by_placeholder(self, text):
            calls.append(("placeholder", text))
            return _L()

        def get_by_text(self, text, exact=False):
            raise AssertionError("role=/placeholder= must not fall through to text")

        def locator(self, sel):
            raise AssertionError("role=/placeholder= must not fall through to CSS")

    idg._resolve_locator(_F(), "role=button:Submit")
    idg._resolve_locator(_F(), "placeholder=+1 (555) 000-0000")
    assert calls == [("role", "button", "Submit", True),
                     ("placeholder", "+1 (555) 000-0000")]
    with pytest.raises(idg.IframeDragError) as ei:
        idg._resolve_locator(_F(), "role=button")     # missing ':<name>'
    assert ei.value.code == "bad-role-locator"


def test_form_builder_drop_target_is_role_scoped_submit_with_defaults_present(monkeypatch):
    """REGRESSION (live attempt #5): with the scratch template's DEFAULT FIELDS
    still on the canvas (Phone + the consent block visible in the snapshot,
    exactly the failing run's world) the F5 drag must aim at the ROLE-SCOPED
    Submit spec — never bare 'Submit'/'text=Submit'."""
    calls = []

    def fake_drag(session, source_text, drop_spec, *, verify_text,
                  iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR, source_scroll_hint=""):
        calls.append((source_text, drop_spec))
        return {"ok": True, "placed": True}

    # The attempt-#5 builder world: defaults present, panel 'Submit' category too.
    snap = ("Form Element Quick Add Add Object Fields Personal Info Submit "
            "First Name Last Name Phone Email Terms & Conditions State "
            "Label Query Key Field Width Required Hidden")
    monkeypatch.setattr(fb, "_ab", _snap_ab(snap))
    monkeypatch.setattr(fb, "_perform_iframe_drag", fake_drag)
    field = {"source": "standard", "element": "State", "label": "State",
             "query_key": "state", "width_pct": 100, "required": False,
             "hidden": False, "quick_add_category": "Address"}
    fb._place_quick_add_field("s", field, "/tmp/x-role-submit", [0], [], [])
    assert calls == [("State", "role=button:Submit")]


def test_canvas_drop_anchor_always_returns_a_spec(monkeypatch):
    """The top-frame snapshot is ADVISORY (documented laggy) — when it shows no
    anchor name, the drop anchor falls back to the documented role-scoped Submit
    spec instead of a false STOP; the frame-scoped resolve stays the
    authoritative fail-closed gate (`target-not-found`)."""
    monkeypatch.setattr(fb, "_ab", _snap_ab("Form Element Quick Add"))
    assert fb._canvas_drop_anchor("s") == "role=button:Submit"
    monkeypatch.setattr(fb, "_ab", _snap_ab("Form Element Quick Add Submit Email"))
    assert fb._canvas_drop_anchor("s") == "role=button:Submit"


# ---------------------------------------------------------------------------
# 7. F4 DEFAULT-FIELD RECONCILIATION (v18.1.9) — delete-for-real, fail-closed
# ---------------------------------------------------------------------------
class _RemoveWorld:
    def __init__(self, field_count=1, link_appears=True, removal_works=True):
        self.field_count = field_count
        self.link_visible = False
        self.link_appears = link_appears
        self.removal_works = removal_works
        self.events = []


class _RemoveLoc:
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


class _RemoveFrame:
    def __init__(self, world):
        self._w = world

    def get_by_placeholder(self, text):
        return _RemoveLoc(self._w, "field")

    def get_by_text(self, text, exact=False):
        return _RemoveLoc(self._w, "field")

    def get_by_role(self, role, name=None, exact=False):
        self._w.events.append(("role", role, name, exact))
        return _RemoveLoc(self._w, "link")

    def locator(self, sel):
        return _RemoveLoc(self._w, "field")


def test_remove_canvas_field_selects_then_removes_and_verifies_count_drop():
    """F4 mechanism: select the field by its DOCUMENTED anchor → click the
    per-field role=link 'Remove field' control (SELECTORS §6) → the removal
    proof is the COUNT-DECREASE of the field's own anchor (mirror of the
    v1.1.1 count-delta placement proof)."""
    w = _RemoveWorld()
    rec = idg.drive_remove_canvas_field(
        _MockPage(_RemoveFrame(w)), iframe_selector="iframe",
        field="placeholder=+1 (555) 000-0000", timeout_ms=500)
    assert rec["removed"] is True
    assert rec["pre_count"] == 1 and rec["post_count"] == 0
    assert w.events.index("click:field") < w.events.index("click:link"), \
        "the field must be SELECTED before its Remove link is clicked"
    assert ("role", "link", "Remove field", True) in w.events, \
        "must use the documented role=link 'Remove field' anchor (§6)"


def test_remove_canvas_field_already_absent_is_truthful_idempotent_noop():
    """Reconciliation semantics: 0 matches = the desired end-state already holds
    — a truthful no-op receipt, no clicks, never an error (re-runs stay safe)."""
    w = _RemoveWorld(field_count=0)
    rec = idg.drive_remove_canvas_field(
        _MockPage(_RemoveFrame(w)), iframe_selector="iframe",
        field="placeholder=+1 (555) 000-0000", timeout_ms=100)
    assert rec["already_absent"] is True and rec["removed"] is False
    assert not any(str(e).startswith("click") for e in w.events)


def test_remove_canvas_field_fails_closed_when_remove_link_never_appears():
    w = _RemoveWorld(link_appears=False)
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_remove_canvas_field(
            _MockPage(_RemoveFrame(w)), iframe_selector="iframe",
            field="placeholder=+1 (555) 000-0000", timeout_ms=100)
    assert ei.value.code == "remove-link-not-found"
    assert w.field_count == 1, "the field must be left untouched"
    assert "click:link" not in w.events


def test_remove_canvas_field_fails_closed_when_count_never_drops():
    w = _RemoveWorld(removal_works=False)
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_remove_canvas_field(
            _MockPage(_RemoveFrame(w)), iframe_selector="iframe",
            field="placeholder=+1 (555) 000-0000", timeout_ms=0)
    assert ei.value.code == "field-not-removed"
    assert "never DROPPED" in ei.value.reason


# ---------------------------------------------------------------------------
# 7b. F4 REMOVE-CONTROL POLL (v1.2.1) — the LIVE ATTEMPT-#6 STOP@F4.delete fix.
#     Live 2026-07-08: the Phone field was located, hovered, and click-selected
#     against the real account, but `role=link:'Remove field'` never became
#     visible inside ONE opaque 15s wait (TimeoutError). The primitive must now
#     poll on a monotonic deadline, re-stimulate the §6 hover/selected reveal
#     (park-away + re-enter), scan BOTH the exact spec and the literal
#     documented lock form, and pick the control NEAREST the field.
# ---------------------------------------------------------------------------
class _F4World:
    """Configurable remove-control world:
      * reveal='hover'   — the control appears on the FIRST hover (pure
                           hover-then-appear; no select-click needed);
      * reveal='rehover' — the control appears ONLY on a hover AFTER the
                           select-click, i.e. a REAL re-entry (the live
                           attempt-#6 stimulation gap);
      * reveal='never'   — the control never appears (must fail closed);
      * exact_name=False — only the case-insensitive documented lock form
                           matches (accessible-name drift)."""

    def __init__(self, reveal="hover", exact_name=True):
        self.reveal = reveal
        self.exact_name = exact_name
        self.field_count = 1
        self.link_visible = False
        self.clicked_field = False
        self.hovers = 0
        self.events = []

    def on_hover(self):
        self.hovers += 1
        self.events.append("hover:field")
        if self.reveal == "hover":
            self.link_visible = True
        elif self.reveal == "rehover" and self.clicked_field and self.hovers >= 2:
            self.link_visible = True

    def on_field_click(self):
        self.clicked_field = True
        self.events.append("click:field")

    def on_link_click(self):
        self.events.append("click:link")
        self.field_count = 0
        self.link_visible = False


class _F4Loc:
    def __init__(self, world, kind, match=True):
        self._w, self._kind, self._match = world, kind, match

    @property
    def first(self):
        return self

    def nth(self, i):
        return self

    def is_visible(self):
        if not self._match:
            return False
        return (self._w.field_count > 0) if self._kind == "field" else self._w.link_visible

    def count(self):
        return int(self.is_visible())

    def wait_for(self, state="visible", timeout=0):
        if not self.is_visible():
            raise TimeoutError(f"mock: {self._kind} hidden")

    def scroll_into_view_if_needed(self, timeout=0):
        pass

    def hover(self):
        if self._kind == "field":
            self._w.on_hover()

    def click(self):
        if self._kind == "field":
            self._w.on_field_click()
        else:
            self._w.on_link_click()


class _F4Frame:
    def __init__(self, world):
        self._w = world

    def get_by_placeholder(self, text):
        return _F4Loc(self._w, "field")

    def get_by_text(self, text, exact=False):
        return _F4Loc(self._w, "field")

    def get_by_role(self, role, name=None, exact=False):
        self._w.events.append(("role", role, name, exact))
        # The exact form only matches when the accessible name is exactly
        # right; the documented lock form (non-exact) always matches.
        return _F4Loc(self._w, "link", match=(self._w.exact_name or not exact))

    def locator(self, sel):
        return _F4Loc(self._w, "field")


def test_locator_spec_role_nonexact_lock_form_grammar():
    """`role~=<role>:<name>` resolves via Playwright-DEFAULT name matching
    (exact NOT set) — the literal form the SELECTORS §6 lock records; a
    malformed spec still fails closed as bad-role-locator."""
    class _Spy:
        def __init__(self):
            self.calls = []

        def get_by_role(self, role, name=None, exact=False):
            self.calls.append(("role", role, name, exact))
            return object()

    spy = _Spy()
    idg._resolve_locator_all(spy, "role~=link:Remove field")
    assert spy.calls == [("role", "link", "Remove field", False)]
    with pytest.raises(idg.IframeDragError) as ei:
        idg._resolve_locator_all(spy, "role~=link")
    assert ei.value.code == "bad-role-locator"


def test_remove_canvas_field_hover_revealed_control_needs_no_select_click():
    """A control revealed by HOVER alone (§6: 'hover/selected') is used WITHOUT
    the select-click — least canvas disturbance, and the receipt says so."""
    w = _F4World(reveal="hover")
    rec = idg.drive_remove_canvas_field(
        _MockPage(_F4Frame(w)), iframe_selector="iframe",
        field="placeholder=+1 (555) 000-0000", timeout_ms=500,
        sleeper=lambda s: None)
    assert rec["removed"] is True
    assert rec["select_clicked"] is False and rec["hover_cycles"] == 0
    assert "click:field" not in w.events
    assert rec["remove_link_matched"] == idg.REMOVE_FIELD_LINK_SPEC


def test_remove_canvas_field_rehover_cycle_reveals_selected_field_control(monkeypatch):
    """THE LIVE ATTEMPT-#6 STIMULATION GAP: after the select-click the pointer
    never left the field, so the builder's hover reveal never re-fired and one
    opaque 15s wait burned the whole budget. The poll must PARK the pointer
    away, RE-enter the field (a REAL mouseenter), and then use the control."""
    monkeypatch.setattr(idg, "_REMOVE_REHOVER_EVERY_S", 0.0)
    w = _F4World(reveal="rehover")
    page = _MockPage(_F4Frame(w))
    rec = idg.drive_remove_canvas_field(
        page, iframe_selector="iframe",
        field="placeholder=+1 (555) 000-0000", timeout_ms=2000,
        sleeper=lambda s: None)
    assert rec["removed"] is True
    assert rec["select_clicked"] is True and rec["hover_cycles"] >= 1
    assert w.hovers >= 2, "the control needed a REAL re-entry hover"
    assert ("move", 0.0, 0.0) in page.mouse.ops, \
        "the pointer must PARK AWAY so mouseenter re-fires on re-entry"
    assert w.events.index("click:field") < w.events.index("click:link")


def test_remove_canvas_field_falls_back_to_documented_lock_form_name():
    """THE LIVE ATTEMPT-#6 SELECTOR CLASS: SELECTORS §6 records the lock as
    getByRole('link', { name: 'Remove field' }) WITHOUT exact — Playwright-
    default case-insensitive substring matching. v1.2.0 hardened the spec to
    exact=True, so an accessible name drifting by case/suffix attaches ZERO
    nodes for the whole budget (the observed TimeoutError). The poll must ALSO
    scan the literal documented lock form and succeed through it."""
    w = _F4World(reveal="hover", exact_name=False)
    rec = idg.drive_remove_canvas_field(
        _MockPage(_F4Frame(w)), iframe_selector="iframe",
        field="placeholder=+1 (555) 000-0000", timeout_ms=500,
        sleeper=lambda s: None)
    assert rec["removed"] is True
    assert rec["remove_link_matched"] == idg.REMOVE_FIELD_LINK_LOCK_SPEC
    assert ("role", "link", "Remove field", False) in w.events, \
        "must resolve the documented non-exact lock form"


def test_remove_canvas_field_never_appearing_control_still_fails_closed(monkeypatch):
    """A control that NEVER appears must still STOP honestly — after the select
    -click AND re-hover stimulation were genuinely tried — with per-spec
    attached-match diagnostics in the reason (so the next live run is
    decisive), and the field left untouched."""
    monkeypatch.setattr(idg, "_REMOVE_REHOVER_EVERY_S", 0.0)
    w = _F4World(reveal="never")
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_remove_canvas_field(
            _MockPage(_F4Frame(w)), iframe_selector="iframe",
            field="placeholder=+1 (555) 000-0000", timeout_ms=300)
    assert ei.value.code == "remove-link-not-found"
    assert "attached match(es)" in ei.value.reason
    assert "re-hover cycle" in ei.value.reason
    assert w.clicked_field is True, "the select-click stimulation must be tried"
    assert w.hovers >= 2, "the re-hover stimulation must be tried"
    assert w.field_count == 1 and "click:link" not in w.events, \
        "an unremovable field must be left untouched (never a fake delete)"


class _NearWorld:
    def __init__(self):
        self.field_count = 1
        self.clicked = []


class _NearLink:
    def __init__(self, world, box, is_right_one):
        self._w, self._box, self._right = world, box, is_right_one

    def is_visible(self):
        return True

    def bounding_box(self):
        return self._box

    def click(self):
        self._w.clicked.append("near" if self._right else "far")
        if self._right:
            self._w.field_count = 0


class _NearLinkAll:
    def __init__(self, links):
        self._links = links

    @property
    def first(self):
        return self._links[0]

    def count(self):
        return len(self._links)

    def nth(self, i):
        return self._links[i]


class _NearField:
    def __init__(self, world):
        self._w = world

    @property
    def first(self):
        return self

    def nth(self, i):
        return self

    def is_visible(self):
        return self._w.field_count > 0

    def count(self):
        return self._w.field_count

    def wait_for(self, state="visible", timeout=0):
        pass

    def scroll_into_view_if_needed(self, timeout=0):
        pass

    def bounding_box(self):
        return {"x": 380, "y": 280, "width": 60, "height": 40}   # center (410, 300)

    def hover(self):
        pass

    def click(self):
        pass


class _NearFrame:
    def __init__(self, world):
        self._w = world
        far = _NearLink(world, {"x": 40, "y": 40, "width": 20, "height": 10}, False)
        near = _NearLink(world, {"x": 400, "y": 285, "width": 20, "height": 10}, True)
        self._links = _NearLinkAll([far, near])    # DOM-first = the WRONG one

    def get_by_placeholder(self, text):
        return _NearField(self._w)

    def get_by_role(self, role, name=None, exact=False):
        return self._links

    def get_by_text(self, text, exact=False):
        return _NearField(self._w)

    def locator(self, sel):
        return _NearField(self._w)


def test_remove_canvas_field_clicks_the_control_nearest_the_field():
    """When SEVERAL 'Remove field' controls are visible at once (one per canvas
    field), the one nearest the TARGET field's own box must be clicked — the
    DOM-first one belongs to a KEEP field, and blind-clicking it would delete
    the wrong field and only fail at the count proof AFTER the damage."""
    w = _NearWorld()
    rec = idg.drive_remove_canvas_field(
        _MockPage(_NearFrame(w)), iframe_selector="iframe",
        field="placeholder=+1 (555) 000-0000", timeout_ms=500,
        sleeper=lambda s: None)
    assert w.clicked == ["near"], \
        f"must click the control NEAREST the field, never the DOM-first: {w.clicked}"
    assert rec["removed"] is True


def test_form_builder_f4_deletes_defaults_before_the_drag(monkeypatch):
    """REGRESSION (live attempt #5, `final_result.json` warnings): the F4
    delete_field steps for 'Phone' + 'Terms & Conditions' were warn-and-KEPT.
    The walk must now delete them FOR REAL — via the documented §6 anchors, in
    click-list order, BEFORE any F5 drag — with the defaults present on the
    canvas exactly as the failing run's snapshot showed."""
    removes, drags = [], []

    def fake_remove(session, field_spec, *, iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR):
        removes.append(field_spec)
        return {"ok": True, "removed": True, "already_absent": False,
                "pre_count": 1, "post_count": 0}

    def fake_drag(session, source_text, drop_spec, *, verify_text,
                  iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR, source_scroll_hint=""):
        drags.append((source_text, drop_spec))
        return {"ok": True, "placed": True}

    snap = ("Form Element Quick Add Add Object Fields Personal Info Submit "
            "First Name Last Name Phone Email Terms & Conditions "
            "Label Query Key Field Width Required Hidden")
    monkeypatch.setattr(fb, "_ab", _snap_ab(snap))
    monkeypatch.setattr(fb, "_perform_iframe_field_remove", fake_remove)
    monkeypatch.setattr(fb, "_perform_iframe_drag", fake_drag)
    monkeypatch.setattr(fb, "_screenshot", lambda session, path: None)

    plan = {"location_id": "TESTLOCATION12345678", "form_name": "ZHC Test Form",
            "default_fields_keep": ["First Name", "Last Name", "Email"],
            "fields": [{"source": "standard", "element": "Phone", "label": "Phone",
                        "query_key": "phone", "width_pct": 100, "required": False,
                        "hidden": False, "quick_add_category": "Personal Info"}]}
    click_list = {"steps": [
        {"phase": "F4", "action": "delete_field", "target": "Phone"},
        {"phase": "F4", "action": "delete_field", "target": "Terms & Conditions"},
        {"phase": "F5", "action": "drag", "target": "Phone → form canvas"},
    ]}
    steps_done = []
    fb._walk_click_list("s", click_list, plan, "/tmp/x-f4-walk", [0], [], steps_done)
    assert removes == ["placeholder=+1 (555) 000-0000", "text=I consent"], \
        "each unwanted default must be removed via its DOCUMENTED §6 anchor"
    assert drags == [("Phone", "role=button:Submit")], \
        "the F5 drag still runs, role-scoped, AFTER the reconciliation"
    want = ["F4:delete:Phone", "F4:delete:Terms & Conditions", "F5:place:Phone"]
    assert [s for s in steps_done if s in want] == want, \
        f"deletes must precede the drag in steps_done: {steps_done}"


def test_form_builder_f4_keeps_kept_defaults_untouched(monkeypatch):
    """default_fields_keep entries never reach the remove seam — the click list
    only emits delete_field for the plan's delete set, and the F5 skip for kept
    defaults still applies (no duplicate placement)."""
    removes = []

    def fake_remove(session, field_spec, *, iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR):
        removes.append(field_spec)
        return {"ok": True, "removed": True, "already_absent": False,
                "pre_count": 1, "post_count": 0}

    monkeypatch.setattr(fb, "_ab", _snap_ab("Form Element Quick Add Submit Email"))
    monkeypatch.setattr(fb, "_perform_iframe_field_remove", fake_remove)
    monkeypatch.setattr(fb, "_screenshot", lambda session, path: None)
    plan = {"location_id": "TESTLOCATION12345678", "form_name": "ZHC Test Form",
            "default_fields_keep": ["First Name", "Last Name", "Email"],
            "fields": [{"source": "standard", "element": "Email", "label": "Email",
                        "query_key": "email", "width_pct": 100, "required": False,
                        "hidden": False, "quick_add_category": "Personal Info"}]}
    click_list = {"steps": [
        {"phase": "F4", "action": "delete_field", "target": "Phone"},
        {"phase": "F5", "action": "drag", "target": "Email → form canvas"},
    ]}
    steps_done = []
    fb._walk_click_list("s", click_list, plan, "/tmp/x-f4-keep", [0], [], steps_done)
    assert removes == ["placeholder=+1 (555) 000-0000"], "only the DELETE set is removed"
    assert any(s.startswith("F5:default-kept:Email") for s in steps_done), \
        "a kept default is skipped by F5 (never re-dragged)"


def test_form_builder_f4_remove_miss_stops_at_the_honest_f4_step(monkeypatch):
    """A genuine remove miss STOPs at F4.delete:<name> (fail-closed — the form
    must never ship carrying fields the plan excluded) and the walk never
    reaches the F5 drag."""
    drags = []

    def failing_remove(session, field_spec, *, iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR):
        raise fb.StopAndReport("iframe-remove:remove-link-not-found",
                               "mock: the documented control never appeared")

    monkeypatch.setattr(fb, "_ab", _snap_ab("Form Element Quick Add Submit Email"))
    monkeypatch.setattr(fb, "_perform_iframe_field_remove", failing_remove)
    monkeypatch.setattr(
        fb, "_perform_iframe_drag",
        lambda *a, **k: drags.append(a) or {"ok": True, "placed": True})
    monkeypatch.setattr(fb, "_screenshot", lambda session, path: None)
    plan = {"location_id": "TESTLOCATION12345678", "form_name": "ZHC Test Form",
            "default_fields_keep": [], "fields": []}
    click_list = {"steps": [
        {"phase": "F4", "action": "delete_field", "target": "Phone"},
        {"phase": "F5", "action": "drag", "target": "Phone → form canvas"},
    ]}
    with pytest.raises(fb.StopAndReport) as ei:
        fb._walk_click_list("s", click_list, plan, "/tmp/x-f4-stop", [0], [], [])
    assert ei.value.step == "F4.delete:Phone"
    assert "remove-link-not-found" in ei.value.reason
    assert drags == [], "must not drag past a failed default delete"


def test_form_builder_f4_already_absent_is_recorded_not_fatal(monkeypatch):
    """An already-absent default (idempotent re-run / template drift) is the
    desired end-state: recorded in steps_done + warnings, never a STOP."""
    monkeypatch.setattr(fb, "_ab", _snap_ab("Form Element Quick Add Submit Email"))
    monkeypatch.setattr(
        fb, "_perform_iframe_field_remove",
        lambda session, field_spec, *, iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR: {
            "ok": True, "removed": False, "already_absent": True,
            "pre_count": 0, "post_count": 0})
    monkeypatch.setattr(fb, "_screenshot", lambda session, path: None)
    plan = {"location_id": "TESTLOCATION12345678", "form_name": "ZHC Test Form",
            "default_fields_keep": [], "fields": []}
    click_list = {"steps": [{"phase": "F4", "action": "delete_field", "target": "Phone"}]}
    warnings, steps_done = [], []
    fb._walk_click_list("s", click_list, plan, "/tmp/x-f4-absent", [0], warnings, steps_done)
    assert any(s.startswith("F4:default-absent:Phone") for s in steps_done)
    assert any("already absent" in w for w in warnings)


def test_form_builder_f4_unknown_default_stops_without_inventing_a_selector(monkeypatch):
    """A plan naming a default with NO documented canvas anchor must STOP at
    F4.anchor:<name> — never invent CSS (SELECTORS §7 doctrine)."""
    monkeypatch.setattr(fb, "_ab", _snap_ab("Form Element Quick Add Submit Email"))
    monkeypatch.setattr(fb, "_screenshot", lambda session, path: None)
    plan = {"location_id": "TESTLOCATION12345678", "form_name": "ZHC Test Form",
            "default_fields_keep": [], "fields": []}
    click_list = {"steps": [{"phase": "F4", "action": "delete_field",
                             "target": "Mystery Field"}]}
    with pytest.raises(fb.StopAndReport) as ei:
        fb._walk_click_list("s", click_list, plan, "/tmp/x-f4-unk", [0], [], [])
    assert ei.value.step == "F4.anchor:Mystery Field"
    assert "never invent" in ei.value.reason


def test_form_builder_field_remove_seam_stops_when_primitive_absent(monkeypatch):
    """The F4 seam mirrors the drag seam's fail-closed shell: a missing shared
    primitive STOPs at iframe-remove.dep (never a top-frame brute-force)."""
    monkeypatch.setattr(fb, "ghl_iframe_drag", None)
    with pytest.raises(fb.StopAndReport) as ei:
        fb._perform_iframe_field_remove("s", "placeholder=+1 (555) 000-0000")
    assert ei.value.step == "iframe-remove.dep"


def test_form_builder_field_remove_seam_stops_when_no_cdp(monkeypatch):
    """No CDP url from the live session → STOP at iframe-remove.cdp (the removal
    can never be handed to Playwright on the same logged-in Chromium)."""
    monkeypatch.setattr(fb, "_get_cdp_url", lambda session: "")
    assert fb.ghl_iframe_drag is not None
    with pytest.raises(fb.StopAndReport) as ei:
        fb._perform_iframe_field_remove("s", "placeholder=+1 (555) 000-0000")
    assert ei.value.step == "iframe-remove.cdp"


# ---------------------------------------------------------------------------
# 8. Playwright-gated real cross-origin proof (skipped cleanly when absent)
# ---------------------------------------------------------------------------
def _pw_browser_installed() -> bool:
    """The Playwright PACKAGE can import while its BROWSER BINARY was never
    downloaded (`playwright install`). Without this check the live selftest below
    HARD-FAILS on every box that has not run `playwright install`, instead of
    skipping — a fleet-wide false red. Environment check only: whenever a browser
    IS present the test still runs, so this can never mask a code regression."""
    if not idg.PLAYWRIGHT_AVAILABLE:
        return False
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        with sync_playwright() as pw:
            return bool(pw.chromium.executable_path)
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _pw_browser_installed(),
                    reason="Playwright browser binary not installed (run `playwright install`)")
def test_live_selftest_places_tile_across_cross_origin_iframe():
    """End-to-end: real Playwright drags a tile into a genuine CROSS-ORIGIN iframe
    canvas headlessly (including the below-the-fold category-hint scroll, the
    inline-title rename, the AMBIGUOUS hidden-'Submit' world, the role-scoped
    button target, and the F4 'Remove field' flow), and fails closed on an
    absent tile."""
    assert idg._live_selftest() == 0

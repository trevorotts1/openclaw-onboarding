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
    def __init__(self, box, present=True):
        self._box = box
        self._present = present
        self.scrolled = 0

    @property
    def first(self):
        return self

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
        return 1 if self._present else 0


class _MockFrame:
    def __init__(self, boxes, verify_present=True):
        self._boxes = boxes
        self._verify_present = verify_present

    def get_by_text(self, text, exact=False):
        return _MockLoc(self._boxes.get(text), present=self._verify_present)

    def locator(self, sel):
        return _MockLoc(self._boxes.get(sel))


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
    assert "iframe-drag" in str(ei.value)


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
    assert "survey rename" in str(ei.value)

    class _FailingIdg:
        DEFAULT_SURVEY_TITLE_SPECS = (r"re:^Survey\s*\d+$",)

        class IframeDragError(RuntimeError):
            def __init__(self, code, reason):
                self.code, self.reason = code, reason
                super().__init__(f"{code}: {reason}")

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
    assert calls == [("City", "Submit", "Address")]
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
# 6. Playwright-gated real cross-origin proof (skipped cleanly when absent)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not idg.PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
def test_live_selftest_places_tile_across_cross_origin_iframe():
    """End-to-end: real Playwright drags a tile into a genuine CROSS-ORIGIN iframe
    canvas headlessly (including the below-the-fold category-hint scroll and the
    inline-title rename), and fails closed on an absent tile."""
    assert idg._live_selftest() == 0

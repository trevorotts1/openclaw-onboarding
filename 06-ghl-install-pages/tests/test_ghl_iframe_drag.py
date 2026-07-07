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
    and pass the form-builder iframe selector."""
    calls = []

    def fake_drag(session, source_text, drop_anchor, *, verify_text,
                  iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR):
        calls.append((source_text, drop_anchor, verify_text, iframe_selector))
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


# ---------------------------------------------------------------------------
# 3. Playwright-gated real cross-origin proof (skipped cleanly when absent)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not idg.PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
def test_live_selftest_places_tile_across_cross_origin_iframe():
    """End-to-end: real Playwright drags a tile into a genuine CROSS-ORIGIN iframe
    canvas headlessly, and fails closed on an absent tile."""
    assert idg._live_selftest() == 0

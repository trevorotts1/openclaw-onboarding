"""Regression locks for the v1.3.0 F4 remove-control TIERED ACQUISITION redesign
(fix/skill6-ghl-form-iframe-drag, v18.1.12).

THE EVIDENCE THIS ENCODES: three consecutive live runs (2026-07-07/08, attempts
#6, #7, and the v18.1.11 `skill6-live-verify-20260708-040836` run) all STOPped
at ``F4.delete:Phone`` with the SAME decisive diagnostic — after the
select-click AND 13 genuine park-away/re-hover cycles, BOTH documented forms of
the SELECTORS-LIVE-form.md §6 lock attached **ZERO** nodes for the whole 15s
budget::

    'role=link:Remove field': 0 attached match(es);
    'role~=link:Remove field': 0 attached match(es)

That is NOT a timing bug. Cross-evidence (the training video's CLICK-MAP Step 8:
"Delete a field = select it → trash icon (top-right of the selected field's
blue bar)"; the 2026-07-02 live-capture screenshot showing a selected field's
blue pill with two ICON-ONLY controls, gear + trash; GHL help docs: "hover over
the field until you see the delete or trash icon") says the real control is an
ICON, very likely with NO accessible name (the §5-documented icon-only pattern).

THE REDESIGN (ghl_iframe_drag v1.3.0): the acquisition is a tiered ladder —
documented §6 specs first (unchanged), then a broad role-name scan
(/remove|delete|trash/i), then an aria-label/title attribute scan (both gated
to the field's top-right CONTROL ZONE), and finally a last-resort GEOMETRIC
icon-pill ladder (JS census of small visible clickables in the zone, clicked
rightmost-first, each click count-verified). Failure now carries RICH
diagnostics on ``IframeDragError.details`` and the F4 caller persists them as
``routing/f4-remove-diag-<field>.json`` plus a failure-moment screenshot.

HERMETIC — no network, no browser, no GHL.
"""
from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# Shared fake world. Geometry: the field anchor box is fixed so the control
# zone is known — zone x in [440, 750], y in [90, 240] (pads from the module
# constants; the pill region overlaps the field's TOP-RIGHT corner).
# ---------------------------------------------------------------------------
FIELD_BOX = {"x": 300.0, "y": 200.0, "width": 400.0, "height": 50.0}
IN_ZONE_BOX = {"x": 660.0, "y": 170.0, "width": 24.0, "height": 24.0}     # ✔ zone
FAR_BOX = {"x": 20.0, "y": 20.0, "width": 24.0, "height": 24.0}           # ✘ zone
WRAPPER_POINT = (500.0, 188.0)     # (center-x, top-12) of FIELD_BOX


class _World:
    def __init__(self):
        self.field_count = 1
        self.events = []
        self.census = {"candidates": []}
        self.aria = None
        self.role_results = {}      # (role, kind-of-name) -> list of controls
        self.attr_results = []      # controls for the attribute-scan CSS
        self.pointer_hooks = []     # callables fired on every pointer up

    # -- stimulation hooks ---------------------------------------------------
    def on_hover(self):
        self.events.append("hover:field")

    def on_field_click(self):
        self.events.append("click:field")

    def on_pointer_up(self, x, y):
        self.events.append(("pointer-up", x, y))
        for hook in self.pointer_hooks:
            hook(x, y)


class _Ctl:
    """A visible control with a box; clicking it may remove the field."""

    def __init__(self, world, box, tag, removes=False, visible=lambda: True):
        self._w, self._box, self.tag = world, box, tag
        self._removes, self._visible = removes, visible

    def is_visible(self):
        return self._visible()

    def bounding_box(self):
        return dict(self._box)

    def click(self):
        self._w.events.append(f"click:{self.tag}")
        if self._removes:
            self._w.field_count = 0


class _List:
    def __init__(self, items):
        self._items = items

    @property
    def first(self):
        return self._items[0] if self._items else self

    def count(self):
        return len(self._items)

    def nth(self, i):
        return self._items[i]

    def is_visible(self):
        return False

    def wait_for(self, state="visible", timeout=0):
        raise TimeoutError("mock: empty list")


class _Field:
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
        return dict(FIELD_BOX)

    def hover(self):
        self._w.on_hover()

    def click(self):
        self._w.on_field_click()

    def evaluate(self, js):
        return self._w.census


class _Body:
    def __init__(self, world):
        self._w = world

    @property
    def first(self):
        return self

    def aria_snapshot(self):
        if self._w.aria is None:
            raise AttributeError("mock: no aria snapshot")
        return self._w.aria


class _Frame:
    def __init__(self, world):
        self._w = world

    def get_by_placeholder(self, text):
        return _Field(self._w)

    def get_by_text(self, text, exact=False):
        return _Field(self._w)

    def get_by_role(self, role, name=None, exact=False):
        kind = "doc" if isinstance(name, str) else "regex"
        self._w.events.append(("role", role, name, exact))
        return _List(self._w.role_results.get((role, kind), []))

    def locator(self, sel):
        if sel == "body":
            return _Body(self._w)
        return _List(self._w.attr_results)


class _Mouse:
    def __init__(self, world):
        self.ops = []
        self._w = world
        self._last = (0.0, 0.0)

    def move(self, x, y):
        self.ops.append(("move", x, y))
        self._last = (float(x), float(y))

    def down(self):
        self.ops.append(("down",))

    def up(self):
        self.ops.append(("up",))
        self._w.on_pointer_up(*self._last)


class _Page:
    def __init__(self, world):
        self._frame = _Frame(world)
        self.mouse = _Mouse(world)

    def frame_locator(self, sel):
        return self._frame


def _run(world, **kw):
    kw.setdefault("iframe_selector", "iframe")
    kw.setdefault("field", "placeholder=+1 (555) 000-0000")
    return idg.drive_remove_canvas_field(_Page(world), **kw)


# ---------------------------------------------------------------------------
# 1. Broad tiers — the live 0-attached class
# ---------------------------------------------------------------------------
def test_name_scan_button_finds_drifted_control_when_doc_specs_attach_zero():
    """THE LIVE CLASS: both §6 doc specs attach ZERO nodes. A control exposed
    as role=button with a deletion-ish accessible name inside the control zone
    must be found by the broad name scan and count-verified."""
    w = _World()
    w.role_results[("button", "regex")] = [
        _Ctl(w, IN_ZONE_BOX, "delete-btn", removes=True)]
    rec = _run(w, timeout_ms=500)
    assert rec["removed"] is True
    assert rec["strategy"] == "name-scan-button"
    assert "click:delete-btn" in w.events
    # the broad scan must query with the case-insensitive deletion-name regex
    regex_queries = [e for e in w.events
                     if isinstance(e, tuple) and e[0] == "role"
                     and not isinstance(e[2], str) and e[2] is not None]
    assert regex_queries, f"no regex-name role query issued: {w.events}"
    pat = regex_queries[0][2]
    assert pat.search("DELETE") and pat.search("Remove field") and pat.search("trash")
    assert not pat.search("Duplicate")


def test_attr_scan_finds_control_named_only_by_title_attribute():
    """A control carrying ONLY [title]/[aria-label] deletion hints (no role
    name) is found by the attribute-scan tier, zone-gated."""
    w = _World()
    w.attr_results = [_Ctl(w, IN_ZONE_BOX, "titled-trash", removes=True)]
    rec = _run(w, timeout_ms=500)
    assert rec["removed"] is True
    assert rec["strategy"] == "attr-scan"
    assert rec["remove_link_matched"] == idg.REMOVE_ATTR_CSS


def test_broad_tiers_never_click_a_deletion_control_outside_the_zone():
    """A visible 'Delete' control far from the field (settings panel, dialog,
    another surface) must NEVER be clicked by the broad tiers — wrong-target
    deletion is worse than an honest failure."""
    w = _World()
    far = _Ctl(w, FAR_BOX, "far-delete", removes=True)
    w.role_results[("button", "regex")] = [far]
    w.role_results[("link", "regex")] = [far]
    w.attr_results = [far]
    with pytest.raises(idg.IframeDragError) as ei:
        _run(w, timeout_ms=0)
    assert ei.value.code == "remove-link-not-found"
    assert "click:far-delete" not in w.events
    assert w.field_count == 1, "the far control must never delete anything"


def test_doc_spec_still_wins_over_broad_scans_when_both_attach():
    """First-among-equals: when the documented §6 exact spec DOES attach a
    visible control, it wins over every broad tier (v1.2.1 semantics kept)."""
    w = _World()
    w.role_results[("link", "doc")] = [_Ctl(w, IN_ZONE_BOX, "doc-link", removes=True)]
    w.role_results[("button", "regex")] = [_Ctl(w, IN_ZONE_BOX, "broad-btn", removes=True)]
    rec = _run(w, timeout_ms=500)
    assert rec["strategy"] == "doc-exact"
    assert rec["remove_link_matched"] == idg.REMOVE_FIELD_LINK_SPEC
    assert "click:doc-link" in w.events and "click:broad-btn" not in w.events


def test_already_absent_receipt_keeps_idempotent_semantics():
    w = _World()
    w.field_count = 0
    rec = _run(w, timeout_ms=100)
    assert rec["already_absent"] is True and rec["removed"] is False
    assert rec["strategy"] is None


# ---------------------------------------------------------------------------
# 2. Geometric icon-pill ladder (tier 4) — the REAL GHL pattern
# ---------------------------------------------------------------------------
def _pill_census(*cands):
    return {"field": {"x": FIELD_BOX["x"], "y": FIELD_BOX["y"],
                      "w": FIELD_BOX["width"], "h": FIELD_BOX["height"]},
            "zone": {"x0": 440.0, "x1": 750.0, "y0": 90.0, "y1": 240.0},
            "candidates": list(cands)}


GEAR = {"tag": "a", "cls": "icon-btn", "aria": None, "title": None, "text": "",
        "x": 680.0, "y": 185.0, "w": 20.0, "h": 20.0, "rejected": None}
TRASH = {"tag": "a", "cls": "icon-btn", "aria": None, "title": None, "text": "",
         "x": 706.0, "y": 185.0, "w": 20.0, "h": 20.0, "rejected": None}
DUP_SVG = {"tag": "svg", "cls": "", "aria": None, "title": None, "text": "",
           "x": 706.0, "y": 185.0, "w": 16.0, "h": 16.0,
           "rejected": "duplicate-position"}


def test_geometric_ladder_clicks_rightmost_icon_first_and_verifies(monkeypatch):
    """No tier attaches anything (icon-only pill, no names — the evidenced
    live UI). After the poll budget the geometric ladder must census the pill,
    click the RIGHTMOST accepted icon (trash sits right of gear) with a REAL
    pointer, and prove the removal by the count decrease."""
    monkeypatch.setattr(idg, "_GEOM_VERIFY_MS", 0)
    w = _World()
    w.census = _pill_census(GEAR, TRASH, DUP_SVG)

    def trash_hook(x, y):
        if abs(x - TRASH["x"]) < 2 and abs(y - TRASH["y"]) < 2:
            w.field_count = 0
    w.pointer_hooks.append(trash_hook)

    rec = _run(w, timeout_ms=0)
    assert rec["removed"] is True
    assert rec["strategy"] == "geometric-pill"
    assert rec["remove_link_matched"] == "geometric-pill"
    ups = [e for e in w.events if isinstance(e, tuple) and e[0] == "pointer-up"]
    assert ups and ups[0][1] == TRASH["x"] and ups[0][2] == TRASH["y"], \
        f"the RIGHTMOST icon (trash) must be clicked first: {ups}"
    assert len(rec["geometric_trail"]) == 1
    assert rec["geometric_trail"][0]["removed"] is True


def test_geometric_ladder_tries_next_candidate_when_first_click_is_a_noop(monkeypatch):
    """A wrong first click (e.g. the pill's OTHER icon) fails its own count
    proof and the ladder moves to the next candidate — never a fake success,
    never an instant give-up."""
    monkeypatch.setattr(idg, "_GEOM_VERIFY_MS", 0)
    w = _World()
    w.census = _pill_census(GEAR, TRASH)

    def gear_hook(x, y):     # only the LEFT icon actually removes here
        if abs(x - GEAR["x"]) < 2 and abs(y - GEAR["y"]) < 2:
            w.field_count = 0
    w.pointer_hooks.append(gear_hook)

    rec = _run(w, timeout_ms=0)
    assert rec["removed"] is True
    assert rec["strategy"] == "geometric-pill"
    trail = rec["geometric_trail"]
    assert len(trail) == 2
    assert trail[0]["removed"] is False and trail[1]["removed"] is True
    assert trail[0]["x"] == TRASH["x"] and trail[1]["x"] == GEAR["x"]


def test_geometric_ladder_never_runs_without_a_select_click(monkeypatch):
    """The pill only exists on a SELECTED field — a run that could not even
    select (field-not-selectable raised earlier) or a 0ms budget where the
    select-click DID happen still gates the ladder on select_clicked. Here:
    census candidates exist but the field click raises, so the primitive
    fails closed BEFORE any geometric click."""
    monkeypatch.setattr(idg, "_GEOM_VERIFY_MS", 0)
    w = _World()
    w.census = _pill_census(TRASH)

    class _UnselectableField(_Field):
        def click(self):
            raise RuntimeError("mock: canvas swallowed the click")

    class _UFrame(_Frame):
        def get_by_placeholder(self, text):
            return _UnselectableField(self._w)

        def get_by_text(self, text, exact=False):
            return _UnselectableField(self._w)

    page = _Page(w)
    page._frame = _UFrame(w)
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_remove_canvas_field(
            page, iframe_selector="iframe",
            field="placeholder=+1 (555) 000-0000", timeout_ms=0)
    assert ei.value.code == "field-not-selectable"
    assert not [e for e in w.events if isinstance(e, tuple) and e[0] == "pointer-up"], \
        "no geometric click may fire when the field was never selected"


# ---------------------------------------------------------------------------
# 3. Wrapper-click stimulation (the never-actually-selected hypothesis)
# ---------------------------------------------------------------------------
def test_wrapper_click_fires_once_and_can_reveal_the_control(monkeypatch):
    """If clicking the INPUT never registers as field selection, ONE real
    pointer click on the wrapper/label strip (just above the anchor) must be
    tried after the configured fruitless re-hover cycles — and a control it
    reveals is then used normally."""
    monkeypatch.setattr(idg, "_REMOVE_REHOVER_EVERY_S", 0.0)
    w = _World()
    revealed = {"on": False}
    ctl = _Ctl(w, IN_ZONE_BOX, "doc-link", removes=True,
               visible=lambda: revealed["on"])
    w.role_results[("link", "doc")] = [ctl]

    def wrapper_hook(x, y):
        if (x, y) == WRAPPER_POINT:
            revealed["on"] = True
    w.pointer_hooks.append(wrapper_hook)

    rec = _run(w, timeout_ms=5000, sleeper=lambda s: None)
    assert rec["removed"] is True
    assert rec["wrapper_click_done"] is True
    assert rec["strategy"] == "doc-exact"
    wrapper_ups = [e for e in w.events if isinstance(e, tuple)
                   and e[0] == "pointer-up" and (e[1], e[2]) == WRAPPER_POINT]
    assert len(wrapper_ups) == 1, f"wrapper click must fire EXACTLY once: {wrapper_ups}"
    assert rec["hover_cycles"] >= idg._REMOVE_WRAPPER_CLICK_AT_CYCLE


# ---------------------------------------------------------------------------
# 4. Rich failure diagnostics — a 4th live failure must explain itself
# ---------------------------------------------------------------------------
def test_failure_details_carry_census_aria_and_strategy_counts():
    w = _World()
    w.census = _pill_census(DUP_SVG)          # nothing accepted, one rejected
    w.aria = '- textbox "Phone"\n- button "Save"'
    with pytest.raises(idg.IframeDragError) as ei:
        _run(w, timeout_ms=0)
    e = ei.value
    assert e.code == "remove-link-not-found"
    # message keeps the decisive live-run phrases AND names the new evidence
    assert "attached match(es)" in e.reason
    assert "re-hover cycle" in e.reason
    assert "aria snapshot" in e.reason
    d = e.details
    assert isinstance(d, dict)
    names = [s["strategy"] for s in d["strategies"]]
    assert names == ["doc-exact", "doc-lock", "name-scan-link",
                     "name-scan-button", "attr-scan"]
    for s in d["strategies"]:
        assert "attached" in s and "visible" in s and "spec" in s
    assert d["stimulation"]["select_clicked"] is True
    assert "wrapper_click_done" in d["stimulation"]
    census = d["geometric"]["census"]
    assert census["accepted"] == []
    assert census["rejected_count"] == 1
    assert census["rejected_sample"][0]["rejected"] == "duplicate-position"
    assert d["aria_snapshot"] == w.aria
    # details must be JSON-serializable — it becomes the F4 evidence receipt
    json.dumps(d)


def test_failure_details_survive_unevaluable_census_and_missing_aria():
    """Hermetic fakes / hostile frames: an unevaluable census and a missing
    aria snapshot must degrade to honest placeholders, never mask the STOP."""
    w = _World()

    class _NoEvalField(_Field):
        def evaluate(self, js):
            raise RuntimeError("mock: no JS bridge")

    class _NFrame(_Frame):
        def get_by_placeholder(self, text):
            return _NoEvalField(self._w)

        def get_by_text(self, text, exact=False):
            return _NoEvalField(self._w)

    page = _Page(w)
    page._frame = _NFrame(w)
    with pytest.raises(idg.IframeDragError) as ei:
        idg.drive_remove_canvas_field(
            page, iframe_selector="iframe",
            field="placeholder=+1 (555) 000-0000", timeout_ms=0)
    d = ei.value.details
    assert isinstance(d, dict)
    assert "census-unevaluable" in str(d["geometric"]["census"].get("error", ""))
    assert d["aria_snapshot"] is None


def test_iframe_drag_error_details_attribute_contract():
    assert idg.IframeDragError("c", "r").details is None
    assert idg.IframeDragError("c", "r", details={"k": 1}).details == {"k": 1}


def test_remove_name_hint_regex_matches_deletion_names_only():
    pat = idg.REMOVE_NAME_HINT_REGEX
    for hit in ("Remove field", "remove", "Delete", "DELETE FIELD", "trash-icon"):
        assert pat.search(hit), hit
    for miss in ("Duplicate", "Open settings", "Save", "Submit"):
        assert not pat.search(miss), miss


# ---------------------------------------------------------------------------
# 5. Form-builder wiring: diagnostics receipt + failure screenshot
# ---------------------------------------------------------------------------
def test_perform_iframe_field_remove_threads_details_onto_stop(monkeypatch):
    monkeypatch.setattr(fb, "_get_cdp_url", lambda session: "ws://mock-cdp")

    def boom(cdp_url, *, iframe_selector, field, url_marker):
        raise idg.IframeDragError("remove-link-not-found", "mock: nothing",
                                  details={"strategies": [], "marker": 42})
    monkeypatch.setattr(fb.ghl_iframe_drag, "remove_canvas_field", boom)
    with pytest.raises(fb.StopAndReport) as ei:
        fb._perform_iframe_field_remove("sess", "placeholder=+1 (555) 000-0000")
    assert ei.value.step == "iframe-remove:remove-link-not-found"
    assert getattr(ei.value, "details", None) == {"strategies": [], "marker": 42}


def test_delete_default_field_failure_writes_diag_receipt_and_screenshot(
        tmp_path, monkeypatch):
    """THE 4TH-FAILURE INSURANCE: an F4 miss must leave (a) the rich
    diagnostics as routing/f4-remove-diag-<field>.json, (b) a failure-moment
    screenshot, and (c) the diagnostics on the raised StopAndReport — so a
    live miss finally explains itself instead of a generic timeout."""
    shots = []
    monkeypatch.setattr(fb, "_screenshot", lambda session, path: shots.append(path))
    details = {"strategies": [{"strategy": "doc-exact", "attached": 0}],
               "stimulation": {"select_clicked": True, "hover_cycles": 13,
                               "wrapper_click_done": True},
               "aria_snapshot": "- button \"Save\""}

    def boom(session, spec, *, iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR):
        sr = fb.StopAndReport("iframe-remove:remove-link-not-found", "mock: nothing")
        sr.details = details
        raise sr
    monkeypatch.setattr(fb, "_perform_iframe_field_remove", boom)

    with pytest.raises(fb.StopAndReport) as ei:
        fb._delete_default_field("sess", "Phone", str(tmp_path), [0], [], [])
    assert ei.value.step == "F4.delete:Phone"
    diag_file = tmp_path / "routing" / "f4-remove-diag-phone.json"
    assert diag_file.is_file(), "the diagnostics receipt MUST be persisted"
    payload = json.loads(diag_file.read_text(encoding="utf-8"))
    assert payload["field"] == "Phone"
    assert payload["anchor"] == "placeholder=+1 (555) 000-0000"
    assert payload["details"] == details
    assert payload["details"]["stimulation"]["hover_cycles"] == 13
    assert getattr(ei.value, "details", None) == details
    assert "f4-remove-diag-phone.json" in ei.value.reason
    assert shots and "f4-delete-FAILED-phone" in shots[0], \
        f"a failure-moment screenshot must be captured: {shots}"


def test_delete_default_field_success_path_unchanged(monkeypatch):
    shots = []
    monkeypatch.setattr(fb, "_screenshot", lambda session, path: shots.append(path))

    def ok(session, spec, *, iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR):
        return {"ok": True, "removed": True, "already_absent": False,
                "pre_count": 1, "post_count": 0, "strategy": "doc-exact"}
    monkeypatch.setattr(fb, "_perform_iframe_field_remove", ok)
    steps, warnings = [], []
    fb._delete_default_field("sess", "Phone", "/tmp/unused-evidence", [0],
                             warnings, steps)
    assert steps == ["F4:delete:Phone"]
    assert warnings == []
    assert shots and "f4-delete-phone" in shots[0]


def test_delete_default_field_diag_write_failure_still_stops_honestly(
        tmp_path, monkeypatch):
    """Evidence persistence is best-effort: an unwritable receipt must never
    mask the honest STOP (and the reason then omits the dead path)."""
    monkeypatch.setattr(fb, "_screenshot", lambda session, path: None)
    monkeypatch.setattr(fb, "_write_json",
                        lambda path, data: (_ for _ in ()).throw(OSError("disk")))

    def boom(session, spec, *, iframe_selector=fb.GHL_FORM_IFRAME_SELECTOR):
        raise fb.StopAndReport("iframe-remove:remove-link-not-found", "mock: nothing")
    monkeypatch.setattr(fb, "_perform_iframe_field_remove", boom)
    with pytest.raises(fb.StopAndReport) as ei:
        fb._delete_default_field("sess", "Phone", str(tmp_path), [0], [], [])
    assert ei.value.step == "F4.delete:Phone"
    assert "f4-remove-diag" not in ei.value.reason

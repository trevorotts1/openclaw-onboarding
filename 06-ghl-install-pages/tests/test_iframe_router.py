"""Tests for the adaptive iframe router (fix-plan 9.7-1 / 9.6 lane table).

Covers the DECISION MATRIX from host capability:
  * iframeDrag.available=true  -> Playwright CDP lane (raise-through contract
    held, routing metadata on the lane's OWN receipt, never manufactured keys);
  * available=false / probe absent + AB session present -> AB ladder degrade
    (CDP-only kwargs dropped and NAMED, cdp_lane_skipped_reason recorded);
  * a bare cdp_url WITHOUT a probed capability never opens the CDP lane;
  * the walled AB ladder stays an HONEST ok=False negative (never flipped);
  * all fail-closed paths: iframe-drag-unavailable (pinned reason),
    iframe-ambiguous (candidates named), iframe-refs-stale (before ANY lane is
    touched), unknown-iframe-kind (sibling contract, raise-through);
  * receipt frame_epoch discipline (get/bump helpers, int on every receipt).

HERMETIC — no network, no browser, no Playwright attach. Sibling modules are
patched via monkeypatch on their OWN globals (never re-imported — a second
import object would carry a distinct IframeDragError and dodge except clauses).

Style + sys.path mirror the sibling 06 tests (test_ghl_fallback_ladder.py).
"""
from __future__ import annotations

import json
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

import iframe_router as ir  # noqa: E402
import ghl_iframe_drag    # noqa: E402,F401  (the sibling _DRAG target)

PRESET_FORM = 'iframe[src*="form-builder-v2"]'
CAP_HYBRID = {"iframeDrag": {"available": True}}
CAP_OFF = {"iframeDrag": {"available": False}}
PINNED_NO_LANE = (
    "no hybrid lane: playwright unavailable and no AB session provided")


# ── fakes ─────────────────────────────────────────────────────────────────────
class Fakes:
    """Injectable lane fakes + call ledgers. All state is per-test."""

    def __init__(self):
        self.cdp_calls: list = []
        self.ab_calls: list = []

    def coordinate_drag(self, cdp_url, *, iframe_selector, source, target,
                        verify_text=None, **kw):
        self.cdp_calls.append({"cdp_url": cdp_url, "iframe_selector": iframe_selector,
                         "source": source, "target": target,
                         "verify_text": verify_text, "kw": kw})
        return {"ok": True, "placed": True, "source": source, "target": target,
                "iframe_selector": iframe_selector, "verify_text": verify_text}

    def frame_click(self, cdp_url, *, iframe_selector, target,
                    verify_text=None, verify_absent=False, **kw):
        self.cdp_calls.append({"cdp_url": cdp_url, "iframe_selector": iframe_selector,
                         "click_target": target, "verify_text": verify_text})
        return {"ok": True, "clicked": target, "iframe_selector": iframe_selector}

    def raise_drag(self, cdp_url, **kw):  # CDP lane that fails closed
        raise ir.IframeDragError("selector-miss", "fake CDP miss",
                                 {"iframe_selector": kw.get("iframe_selector")})

    def ab(self, session, *args, timeout=15):
        self.ab_calls.append(args)
        return _completed(args, returncode=0, stdout="✓ Done")

    def ab_wall(self, session, *args, timeout=15):
        self.ab_calls.append(args)
        return _completed(args, returncode=0, stdout="✗ no movement")

    @staticmethod
    def ev_ok(session, js, timeout=15):
        if "pointerdown" in js:
            return '{"ok":true,"before":0,"after":1}'
        return "CLICKED:Tab"

    @staticmethod
    def ev_wall(session, js, timeout=15):
        if "pointerdown" in js:
            return '{"ok":false,"before":0,"after":0}'
        return ""


def _completed(args, *, returncode, stdout):
    import subprocess as _sp
    return _sp.CompletedProcess(args=list(args), returncode=returncode,
                                stdout=stdout, stderr="")


@pytest.fixture()
def patched(monkeypatch):
    """Patch the SIBLING's own globals (never re-import the module)."""
    f = Fakes()
    monkeypatch.setattr(ghl_iframe_drag, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(ghl_iframe_drag, "coordinate_drag", f.coordinate_drag)
    monkeypatch.setattr(ghl_iframe_drag, "frame_click", f.frame_click)
    return f


@pytest.fixture(autouse=True)
def fresh_epoch():
    """Each test starts from a known epoch; stale-epoch tests bump locally."""
    ir.bump_frame_epoch()
    yield


def cap_file(tmp_path, cap):
    p = tmp_path / "capability.json"
    p.write_text(json.dumps(cap), encoding="utf-8")
    return str(p)


# ── decision matrix (9.6 lane table) ──────────────────────────────────────────
def test_hybrid_available_routes_cdp_drag(patched):
    r = ir.route_drag("form", "State", "Submit", capability=CAP_HYBRID,
                      cdp_url="ws://t", verify_text="State", url_marker="fb",
                      frame_epoch=ir.get_frame_epoch())
    assert r["lane"] == "playwright-cdp"
    assert r["ok"] is True and r["placed"] is True
    assert r["iframe_selector"] == PRESET_FORM
    assert isinstance(r["frame_epoch"], int)
    assert r["kind"] == "form"
    assert r["capability_source"] == "injected"
    call = patched.cdp_calls[-1]
    assert call["verify_text"] == "State" and call["kw"].get("url_marker") == "fb"


def test_hybrid_available_routes_cdp_click(patched):
    r = ir.route_click("survey", "Save", capability=CAP_HYBRID,
                       cdp_url="ws://t", verify_text="Saved",
                       frame_epoch=ir.get_frame_epoch())
    assert r["lane"] == "playwright-cdp" and r["ok"] is True
    assert r["iframe_selector"] == 'iframe[src*="survey-builder-v2"]'
    assert patched.cdp_calls[-1]["verify_text"] == "Saved"


def test_capability_off_with_ab_routes_ab_ladder(patched):
    r = ir.route_drag("survey", "Rating", "Slide 2", capability=CAP_OFF,
                      session="s", ab=patched.ab, ev=Fakes.ev_ok,
                      verify_expr="s.slides.length",
                      frame_epoch=ir.get_frame_epoch())
    assert r["lane"] == "ab-ladder"
    assert r["ok"] is True and r["path"] == "coord-drag"
    assert patched.cdp_calls == []            # CDP lane never opened
    assert r["cdp_lane_skipped_reason"]
    assert r["verify_expr"] == "s.slides.length"
    assert patched.ab_calls                   # ladder actually ran


def test_bare_cdp_url_without_capability_does_not_open_cdp(patched):
    r = ir.route_drag("form", "A", "B", capability=CAP_OFF, cdp_url="ws://x",
                      session="s", ab=patched.ab, ev=Fakes.ev_ok,
                      frame_epoch=ir.get_frame_epoch())
    assert r["lane"] == "ab-ladder" and patched.cdp_calls == []


def test_missing_probe_file_means_cdp_lane_off(tmp_path, patched):
    # absence of a probe is never proof of a hybrid host
    r = ir.route_drag("form", "A", "B",
                      capability_path=str(tmp_path / "absent.json"),
                      session="s", ab=patched.ab, ev=Fakes.ev_ok,
                      frame_epoch=ir.get_frame_epoch())
    assert r["lane"] == "ab-ladder"


def test_capability_file_round_trip(tmp_path, patched):
    r = ir.route_drag("form", "A", "B", capability_path=cap_file(tmp_path, CAP_OFF),
                      session="s", ab=patched.ab, ev=Fakes.ev_ok,
                      frame_epoch=ir.get_frame_epoch())
    assert r["lane"] == "ab-ladder"
    assert r["capability_source"].startswith("file:")


def test_flag_off_hybrid_degrades_to_ab_with_named_reason(patched, monkeypatch):
    monkeypatch.setattr(ghl_iframe_drag, "PLAYWRIGHT_AVAILABLE", False)
    r = ir.route_drag("form", "A", "B", capability=CAP_HYBRID, cdp_url="ws://t",
                      session="s", ab=patched.ab, ev=Fakes.ev_ok,
                      frame_epoch=ir.get_frame_epoch())
    assert r["lane"] == "ab-ladder"
    assert r["cdp_lane_skipped_reason"]
    assert patched.cdp_calls == []


def test_lane_foreign_kwargs_dropped_and_named(patched):
    # CDP lane: AB-only kwargs dropped + named
    r = ir.route_drag("form", "A", "B", capability=CAP_HYBRID, cdp_url="ws://t",
                      verify_expr="x", timeout=99,
                      frame_epoch=ir.get_frame_epoch())
    assert r["cdp_ignored_kwargs"] == ["timeout", "verify_expr"]
    # AB lane: CDP-only kwargs dropped + named
    r2 = ir.route_drag("form", "A", "B", capability=CAP_OFF,
                       session="s", ab=patched.ab, ev=Fakes.ev_ok,
                       url_marker="fb", interpolated_moves=7,
                       frame_epoch=ir.get_frame_epoch())
    assert r2["ab_ignored_kwargs"] == ["interpolated_moves", "url_marker"]


def test_hybrid_probed_but_cdp_blocked_and_no_ab_fails_named(patched, monkeypatch):
    monkeypatch.setattr(ghl_iframe_drag, "PLAYWRIGHT_AVAILABLE", False)
    with pytest.raises(ir.IframeDragError) as ei:
        ir.route_drag("form", "A", "B", capability=CAP_HYBRID, cdp_url="ws://t")
    assert ei.value.code == "iframe-drag-unavailable"
    assert "playwright" in ei.value.reason.lower()


# ── honest AB negatives (never flipped into ok:true) ──────────────────────────
def test_walled_ab_drag_stays_ok_false(patched):
    r = ir.route_drag("form", "City", "Submit", capability=CAP_OFF,
                      session="s", ab=patched.ab_wall, ev=Fakes.ev_wall,
                      verify_expr="x", frame_epoch=ir.get_frame_epoch())
    assert r["ok"] is False
    assert r["lane"] == "ab-ladder"


# ── fail-closed paths ─────────────────────────────────────────────────────────
def test_no_lane_at_all_fails_closed_pinned_reason():
    with pytest.raises(ir.IframeDragError) as ei:
        ir.route_drag("form", "A", "B", capability=CAP_OFF)
    assert ei.value.code == "iframe-drag-unavailable"
    assert ei.value.reason == PINNED_NO_LANE


def test_ab_without_session_fails_closed():
    with pytest.raises(ir.IframeDragError) as ei:
        ir.route_drag("form", "A", "B", capability=CAP_OFF,
                      ab=lambda *a, **k: None, ev=Fakes.ev_ok)
    assert ei.value.code == "iframe-drag-unavailable"
    assert "session" in ei.value.reason


def test_ambiguous_selector_list_fails_closed(patched):
    with pytest.raises(ir.IframeDragError) as ei:
        ir.route_drag("form", "A", "B", capability=CAP_OFF, session="s",
                      ab=patched.ab, ev=Fakes.ev_ok,
                      iframe_selector=["iframe#one", "iframe#two"])
    assert ei.value.code == "iframe-ambiguous"
    assert "candidates" in ei.value.reason


def test_double_builder_iframe_without_index_fails_closed(patched):
    snap = ('<iframe src="https://x.leadconnectorhq.com/form-builder-v2/aaa"></iframe>'
            '<iframe src="https://x.leadconnectorhq.com/form-builder-v2/bbb"></iframe>')
    with pytest.raises(ir.IframeDragError) as ei:
        ir.route_drag("form", "A", "B", capability=CAP_HYBRID, cdp_url="ws://t",
                      snapshot_text=snap, frame_epoch=ir.get_frame_epoch())
    assert ei.value.code == "iframe-ambiguous"
    assert "aaa" in ei.value.reason and "bbb" in ei.value.reason


def test_stale_epoch_fails_closed_before_any_lane(patched):
    old = ir.get_frame_epoch()
    ir.bump_frame_epoch()
    with pytest.raises(ir.IframeDragError) as ei:
        ir.route_drag("form", "A", "B", capability=CAP_HYBRID,
                      cdp_url="ws://t", frame_epoch=old)
    assert ei.value.code == "iframe-refs-stale"
    assert patched.cdp_calls == []            # never reached a lane


def test_omitted_epoch_uses_current(patched):
    # no frame_epoch kwarg -> current epoch, no raise
    r = ir.route_drag("form", "A", "B", capability=CAP_OFF, session="s",
                      ab=patched.ab, ev=Fakes.ev_ok)
    assert r["lane"] == "ab-ladder"


def test_unknown_kind_fails_closed_raise_through():
    with pytest.raises(ir.IframeDragError) as ei:
        ir.route_drag("page", "A", "B", capability=CAP_HYBRID, cdp_url="ws://t")
    assert ei.value.code == "unknown-iframe-kind"


def test_cdp_lane_error_raises_through_uncaught(patched, monkeypatch):
    monkeypatch.setattr(ghl_iframe_drag, "coordinate_drag",
                        patched.raise_drag)
    with pytest.raises(ir.IframeDragError) as ei:
        ir.route_drag("form", "A", "B", capability=CAP_HYBRID, cdp_url="ws://t")
    assert ei.value.code == "selector-miss"   # not swallowed, not re-coded


# ── multi-iframe selection (9.7-3) ────────────────────────────────────────────
def test_list_with_index_picks_item_verbatim(patched):
    ir.route_drag("form", "A", "B", capability=CAP_HYBRID, cdp_url="ws://t",
                  iframe_selector=[PRESET_FORM, "iframe#second"], iframe_index=1,
                  frame_epoch=ir.get_frame_epoch())
    assert patched.cdp_calls[-1]["iframe_selector"] == "iframe#second"


def test_preset_with_snapshot_index_composes_nth(patched):
    snap = ('<iframe src="https://x.leadconnectorhq.com/form-builder-v2/aaa"></iframe>'
            '<iframe src="https://x.leadconnectorhq.com/form-builder-v2/bbb"></iframe>')
    ir.route_drag("form", "A", "B", capability=CAP_HYBRID, cdp_url="ws://t",
                  snapshot_text=snap, iframe_index=1,
                  frame_epoch=ir.get_frame_epoch())
    assert patched.cdp_calls[-1]["iframe_selector"] == f"{PRESET_FORM} >> nth=1"


def test_empty_selector_override_fails_closed():
    with pytest.raises(ir.IframeDragError) as ei:
        ir.route_drag("form", "A", "B", capability=CAP_OFF, session="s",
                      ab=lambda *a, **k: None, ev=Fakes.ev_ok,
                      iframe_selector="   ")
    assert ei.value.code == "empty-iframe-selector"


def test_list_index_out_of_range_fails_closed(patched):
    with pytest.raises(ir.IframeDragError) as ei:
        ir.route_drag("form", "A", "B", capability=CAP_OFF, session="s",
                      ab=patched.ab, ev=Fakes.ev_ok,
                      iframe_selector=["iframe#one", "iframe#two"],
                      iframe_index=5)
    assert ei.value.code == "iframe-ambiguous"


# ── detect_iframes (offline snapshot path; never needs a live browser) ────────
def test_detect_snapshot_classifies_two_form_iframes():
    snap = ('<iframe src="https://x.leadconnectorhq.com/form-builder-v2/aaa"></iframe>'
            '<iframe src="https://x.leadconnectorhq.com/form-builder-v2/bbb"></iframe>')
    det = ir.detect_iframes(snapshot_text=snap)
    assert det["source"] == "snapshot" and len(det["iframes"]) == 2
    assert all(d["kind"] == "form" for d in det["iframes"])


def test_detect_snapshot_page_code_and_empty():
    det1 = ir.detect_iframes(
        snapshot_text='<iframe src="https://page-builder.leadconnectorhq.com/x"></iframe>')
    assert det1["iframes"][0]["kind"] == "page_code"
    det0 = ir.detect_iframes(snapshot_text="<p>no iframes here</p>")
    assert det0["iframes"] == []


def test_detect_no_inputs_fails_closed():
    with pytest.raises(ir.IframeDragError) as ei:
        ir.detect_iframes()
    assert ei.value.code == "iframe-detect-unavailable"


# ── epoch helpers (plan 3.4 activeFrameId discipline) ─────────────────────────
def test_bump_then_get_match():
    v = ir.bump_frame_epoch()
    assert ir.get_frame_epoch() == v and isinstance(v, int)


def test_route_receipts_carry_int_frame_epoch(patched):
    for r in (
        ir.route_drag("form", "A", "B", capability=CAP_HYBRID, cdp_url="ws://t",
                      frame_epoch=ir.get_frame_epoch()),
        ir.route_drag("survey", "R", "S", capability=CAP_OFF, session="s",
                      ab=patched.ab, ev=Fakes.ev_ok),
        ir.route_click("form", "Quick Add", capability=CAP_OFF, session="s",
                       ab=patched.ab, ev=Fakes.ev_ok),
    ):
        assert isinstance(r["frame_epoch"], int)
        assert r["iframe_selector"]


# ── CLI --selftest (offline; subprocess, real exit code) ──────────────────────
def test_cli_selftest_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / "iframe_router.py"), "--selftest"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout

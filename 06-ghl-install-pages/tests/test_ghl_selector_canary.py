"""Offline tests for U2 (F3) — selector-drift canary + STOP-with-snapshot resolver.

No network, no browser, no GHL writes: every finder in this file is a fake
callable. These wrap the module's own --selftest AND add direct behavioural
assertions so a regression in the "never blind-click" resolver or the
fail-soft board-notify path fails CI, not a live client build.
"""

import json
import os
import sys
import tempfile

import pytest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_selector_canary as canary  # noqa: E402


# ---------------------------------------------------------------------------
# Module selftest (belt-and-suspenders)
# ---------------------------------------------------------------------------
def test_module_selftest_passes():
    assert canary._selftest() == 0


# ---------------------------------------------------------------------------
# Schema / loading
# ---------------------------------------------------------------------------
def test_loads_default_selectors_file():
    data = canary.load_selectors()
    assert set(canary.VALID_OBJECT_TYPES).issubset(data["objects"].keys())


def test_load_selectors_rejects_malformed_file():
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "bad.json")
        with open(bad, "w") as fh:
            json.dump({"no_objects_key": True}, fh)
        with pytest.raises(ValueError):
            canary.load_selectors(bad)


def test_every_anchor_has_unique_id_and_required_fields():
    data = canary.load_selectors()
    anchors = canary.iter_anchors(data)
    ids = [a["id"] for a in anchors]
    assert len(ids) == len(set(ids)), "duplicate anchor ids in selectors-live.json"
    for a in anchors:
        assert a["object_type"] in canary.VALID_OBJECT_TYPES
        assert isinstance(a.get("confidence"), (int, float))
        assert isinstance(a.get("runtime_capture"), bool)
        assert "kind" in a["primary"]


def test_iter_anchors_object_type_filter():
    data = canary.load_selectors()
    form_only = canary.iter_anchors(data, ["form"])
    assert form_only and all(a["object_type"] == "form" for a in form_only)
    assert len(form_only) < len(canary.iter_anchors(data))


def test_get_anchor_raises_keyerror_on_unknown_id():
    data = canary.load_selectors()
    with pytest.raises(KeyError):
        canary.get_anchor(data, "does.not.exist")


# ---------------------------------------------------------------------------
# resolve_anchor — the STOP-with-snapshot core contract
# ---------------------------------------------------------------------------
def test_resolve_anchor_primary_hit_short_circuits_fallbacks():
    data = canary.load_selectors()
    anchor = canary.get_anchor(data, "form.builder.save")
    calls = []

    def finder(a, candidate):
        calls.append(candidate)
        return "ref-primary"

    res = canary.resolve_anchor(anchor, finder)
    assert res.status == "primary"
    assert res.ref == "ref-primary"
    assert len(calls) == 1, "must not probe fallbacks once the primary resolves"


def test_resolve_anchor_falls_back_in_order():
    data = canary.load_selectors()
    anchor = canary.get_anchor(data, "form.list.search")
    assert anchor["fallbacks"], "fixture anchor must carry at least one fallback"
    tried = []

    def finder(a, candidate):
        tried.append(candidate)
        return "ref-fallback" if candidate is not a_primary(a) else None

    def a_primary(a):
        return a["primary"]

    res = canary.resolve_anchor(anchor, finder)
    assert res.status == "fallback"
    assert tried[0] is anchor["primary"]  # primary tried FIRST, in order


def test_resolve_anchor_total_miss_raises_never_returns_guess():
    data = canary.load_selectors()
    anchor = canary.get_anchor(data, "form.builder.save")

    def finder(a, candidate):
        return None

    with pytest.raises(canary.SelectorMissError) as exc_info:
        canary.resolve_anchor(anchor, finder, snapshot_provider=lambda: {"excerpt": "dom-here"})
    err = exc_info.value
    assert err.anchor_id == "form.builder.save"
    assert err.snapshot_excerpt == {"excerpt": "dom-here"}
    assert len(err.chain_tried) >= 1
    d = err.to_dict()
    assert d["anchor_id"] == "form.builder.save" and "chain_tried" in d


def test_resolve_anchor_snapshot_provider_failure_is_captured_not_raised():
    data = canary.load_selectors()
    anchor = canary.get_anchor(data, "form.builder.save")

    def finder(a, candidate):
        return None

    def boom():
        raise RuntimeError("snapshot backend down")

    with pytest.raises(canary.SelectorMissError) as exc_info:
        canary.resolve_anchor(anchor, finder, snapshot_provider=boom)
    assert "snapshot_capture_error" in exc_info.value.snapshot_excerpt


def test_resolve_anchor_known_gap_short_circuits_without_probing():
    data = canary.load_selectors()
    gap_anchor = canary.get_anchor(data, "page.builder.chrome")
    probed = []

    def finder(a, candidate):
        probed.append(candidate)
        return None

    res = canary.resolve_anchor(gap_anchor, finder)
    assert res.status == "gap"
    assert probed == []


# ---------------------------------------------------------------------------
# run_canary — the read-only weekly drift scan
# ---------------------------------------------------------------------------
def test_run_canary_all_clean():
    data = canary.load_selectors()

    def always_hit(a, candidate):
        return "ref"

    report = canary.run_canary(data, always_hit, object_types=["survey"])
    summary = report.summary()
    assert summary["clean"] is True
    assert summary["counts"]["missing"] == 0


def test_run_canary_reports_miss_and_notifies_board():
    data = canary.load_selectors()

    def only_save_misses(a, candidate):
        return None if a["id"] == "form.builder.save" else "ref"

    notified = []
    report = canary.run_canary(
        data, only_save_misses, object_types=["form"],
        board_notifier=lambda payload: notified.append(payload),
    )
    summary = report.summary()
    assert summary["clean"] is False
    assert "form.builder.save" in summary["misses"]
    assert len(notified) == 1
    assert notified[0]["prefix"] == canary.BOARD_NOTE_SELECTOR_MISS
    assert notified[0]["anchor_id"] == "form.builder.save"


def test_run_canary_continues_scanning_past_a_miss():
    """A miss on one anchor must not abort the scan of the remaining anchors —
    the canary is a read-only reduction, not a build that must STOP on first
    failure (that discipline belongs to resolve_anchor() when called from a
    live builder, not from the scanner)."""
    data = canary.load_selectors()
    form_anchor_ids = [a["id"] for a in canary.iter_anchors(data, ["form"])]

    def only_first_misses(a, candidate):
        return None if a["id"] == form_anchor_ids[0] else "ref"

    report = canary.run_canary(data, only_first_misses, object_types=["form"])
    assert len(report.results) == len(form_anchor_ids)
    assert len(report.misses) == 1


def test_run_canary_board_notifier_failure_is_fail_soft():
    data = canary.load_selectors()

    def only_save_misses(a, candidate):
        return None if a["id"] == "form.builder.save" else "ref"

    def boom(payload):
        raise RuntimeError("board unreachable")

    report = canary.run_canary(data, only_save_misses, object_types=["form"], board_notifier=boom)
    assert "form.builder.save" in report.summary()["misses"], "board outage must not swallow the miss"


def test_run_canary_writes_evidence_file():
    data = canary.load_selectors()

    def always_hit(a, candidate):
        return "ref"

    with tempfile.TemporaryDirectory() as tmp:
        report = canary.run_canary(data, always_hit, object_types=["page"], evidence_root=tmp)
        files = [f for f in os.listdir(tmp) if f.startswith("selector-canary-")]
        assert len(files) == 1
        with open(os.path.join(tmp, files[0])) as fh:
            on_disk = json.load(fh)
        assert on_disk["summary"]["total_anchors"] == len(report.results)


def test_run_canary_gap_anchor_never_counted_as_miss():
    data = canary.load_selectors()

    def never_hit(a, candidate):
        return None

    report = canary.run_canary(data, never_hit, object_types=["page"])
    summary = report.summary()
    assert "page.builder.chrome" in summary["gaps"]
    assert "page.builder.chrome" not in summary["misses"]


# ---------------------------------------------------------------------------
# live_finder_over_browser_manager — pure expression-building, still offline
# ---------------------------------------------------------------------------
def test_live_finder_builds_role_name_expression_and_never_fabricates_runtime_capture():
    data = canary.load_selectors()
    anchor = canary.get_anchor(data, "form.builder.save")
    seen = []

    def fake_ab_eval(session, expr):
        seen.append((session, expr))
        return "ref-from-eval"

    finder = canary.live_finder_over_browser_manager("sess-1", fake_ab_eval)
    ref = finder(anchor, anchor["primary"])
    assert ref == "ref-from-eval"
    assert seen[-1][0] == "sess-1"
    assert "button" in seen[-1][1] and "Save" in seen[-1][1]

    # runtime-capture candidate kinds (svg_d_signature/order/coordinate_recipe)
    # must never be sent through as a fabricated live match.
    ref2 = finder(anchor, {"kind": "svg_d_signature", "d": "M0 0", "order": 1})
    assert ref2 is None
    assert len(seen) == 1, "runtime-capture kinds must not even call ab_eval"


# ---------------------------------------------------------------------------
# CLI smoke (subprocess-free — call main() directly)
# ---------------------------------------------------------------------------
def test_cli_selftest_returns_zero():
    assert canary.main(["--selftest"]) == 0


def test_cli_matrix_returns_zero(capsys):
    rc = canary.main(["--matrix"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["total_anchors"] > 0


def test_cli_canary_without_finder_wiring_refuses_cleanly():
    rc = canary.main(["--canary"])
    assert rc == 2, "must refuse rather than silently no-op or fabricate results"


def test_cli_canary_with_selftest_finder_offline_dry_run(capsys):
    rc = canary.main(["--canary", "--selftest-finder", "--object-type", "survey"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["clean"] is True

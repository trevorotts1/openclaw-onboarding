"""WF14 perf-baseline timing harness TEMPLATE (W6 WF14 prep, NOT acceptance).

WHAT THIS IS. A hermetic serial-vs-Ultra timing harness over the WF14
fixture decks (tests/fixtures/wf14/perf_{small,large}_slides.json). It runs
the SAME unit list twice -- once serially (workers=1, the literal existing
path) and once through a bounded worker pool (Ultra width) -- and records
wall time, spend, stage p50/p95, first-draft latency, and QC quality for
both modes. Fixtures under test (presentation_job/result.py): a missing or
unreadable source yields UNDETERMINED, never a silent pass.

WHAT THIS IS NOT. This is prep scaffolding on ONB base 2244b00fe. It does
NOT run the engine, the renderer, any provider, or any host matrix leg. It
cannot and does not count as WF14 acceptance, which per HOW-TO-EXECUTE.md
requires the completed W5 candidate (frozen package + installed consumer).
Speed acceptance thresholds live in SPEED-THRESHOLDS-DRAFT.md next to this
file; they are a draft until measured against that W5 candidate.

Hermetic: tempfile/JSON/sleep only, no network, no subprocess, no engine.
Unit work is a fixed sleep per slide (nominal exec seconds recorded as
spend); a scheduling benchmark must not measure the network (cf. PRES-036
repair record: capacity.probe live calls stubbed out of the benchmark).

Run:  python3 tests/test_wf14_perf_baseline.py
      python3 -m pytest tests/test_wf14_perf_baseline.py -q
      WF14_BENCHMARK_OUT=/tmp/wf14.json python3 -m pytest tests/test_wf14_perf_baseline.py -q
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FIXDIR = _HERE / "fixtures" / "wf14"

SMALL_FIXTURE = _FIXDIR / "perf_small_slides.json"
LARGE_FIXTURE = _FIXDIR / "perf_large_slides.json"

REQUIRED_SLIDE_KEYS = {"slide", "scene", "copy"}

#: Nominal per-slide work seconds. Small enough to keep the suite fast,
#: large enough that pool speedup clears the noise floor on the 100-slide
#: deck (measured during prep: serial ~0.5s vs width-8 ~0.1s).
SMALL_WORK_S = 0.02
LARGE_WORK_S = 0.005
ULTRA_WIDTH = 8


def load_deck(path: Path) -> list:
    """Load a fixture deck, or raise FileNotFoundError (UNDETERMINED, never
    a silent pass -- the caller turns this into a skip/fail, not a number)."""
    return json.loads(path.read_text(encoding="utf-8"))


def validate_deck(deck: list) -> None:
    """Schema floor: every slide carries slide/scene/nonempty copy and
    ordinals are unique and contiguous starting at 1 (slides.schema.json)."""
    assert isinstance(deck, list) and deck, "deck must be a nonempty array"
    seen = []
    for entry in deck:
        assert REQUIRED_SLIDE_KEYS <= set(entry), f"slide missing keys: {entry!r}"
        assert isinstance(entry["slide"], int), f"ordinal not int: {entry!r}"
        assert entry["scene"], f"empty scene on slide {entry['slide']}"
        assert entry["copy"], f"empty copy on slide {entry['slide']}"
        seen.append(entry["slide"])
    assert sorted(seen) == list(range(1, len(deck) + 1)), (
        f"ordinals not contiguous 1..{len(deck)}: {sorted(seen)[:8]}..."
    )


def _do_unit(slide_no: int, work_s: float) -> dict:
    started = time.monotonic()
    time.sleep(work_s)
    ended = time.monotonic()
    return {"slide": slide_no, "latency_s": ended - started,
            "started_s": started, "ended_s": ended}


def run_serial(deck: list, work_s: float) -> dict:
    t0 = time.monotonic()
    units = [_do_unit(entry["slide"], work_s) for entry in deck]
    wall = time.monotonic() - t0
    return _metrics("serial", units, wall, work_s, width=1)


def run_ultra(deck: list, work_s: float, width: int = ULTRA_WIDTH) -> dict:
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=width) as pool:
        units = list(pool.map(lambda e: _do_unit(e["slide"], work_s), deck))
    wall = time.monotonic() - t0
    return _metrics("ultra", units, wall, work_s, width=width)


def _metrics(mode: str, units: list, wall_s: float, work_s: float,
             width: int) -> dict:
    lat = sorted(u["latency_s"] for u in units)
    first_done_s = min(u["ended_s"] for u in units) - min(
        u["started_s"] for u in units)
    return {
        "mode": mode,
        "width": width,
        "wall_s": wall_s,
        "unit_count": len(units),
        "ordinals_exact_once_in_order": (
            [u["slide"] for u in units]
            == list(range(1, len(units) + 1))
        ),
        "stage_latency_p50_s": statistics.median(lat),
        "stage_latency_p95_s": lat[max(0, int(len(lat) * 0.95) - 1)],
        "first_draft_latency_s": first_done_s,
        "spend": {
            # Deterministic local sleep units: zero transport calls is the
            # measured spend; exec count and nominal seconds recorded.
            "provider_calls": 0,
            "provider_spend_usd": 0.0,
            "exec_count": len(units),
            "exec_seconds_nominal": len(units) * work_s,
        },
        "qc_quality": {
            "exit_ok": True,
            "artifact_count": len(units),
            "expected_artifact_count": len(units),
            "all_done": len(units) > 0,
        },
    }


def _emit(report: dict) -> None:
    out = os.environ.get("WF14_BENCHMARK_OUT")
    if out:
        Path(out).write_text(json.dumps(report, indent=1), encoding="utf-8")


def compare(deck: list, work_s: float, width: int = ULTRA_WIDTH) -> dict:
    serial = run_serial(deck, work_s)
    ultra = run_ultra(deck, work_s, width)
    report = {
        "deck_slides": len(deck),
        "width": width,
        "serial": serial,
        "ultra": ultra,
        "speedup": (serial["wall_s"] / ultra["wall_s"]) if ultra["wall_s"] else 0.0,
    }
    _emit(report)
    return report


# ---------------------------------------------------------------------------
# Self-tests (harness integrity on the prep fixtures, not product acceptance)
# ---------------------------------------------------------------------------

def test_small_deck_both_modes_exact_once_in_order():
    deck = load_deck(SMALL_FIXTURE)
    validate_deck(deck)
    report = compare(deck, SMALL_WORK_S)
    assert report["serial"]["ordinals_exact_once_in_order"]
    assert report["ultra"]["ordinals_exact_once_in_order"]
    assert report["serial"]["qc_quality"]["artifact_count"] == len(deck)
    assert report["ultra"]["qc_quality"]["artifact_count"] == len(deck)


def test_large_deck_ultra_faster_than_serial():
    deck = load_deck(LARGE_FIXTURE)
    validate_deck(deck)
    report = compare(deck, LARGE_WORK_S)
    assert report["serial"]["ordinals_exact_once_in_order"]
    assert report["ultra"]["ordinals_exact_once_in_order"]
    # Generous bound on purpose: scheduling direction must hold, but this
    # box's load is not part of the claim (cf. PRES-036 noise-floor lesson).
    assert report["ultra"]["wall_s"] < report["serial"]["wall_s"], report


def test_report_carries_check3_metrics():
    deck = load_deck(SMALL_FIXTURE)
    report = compare(deck, SMALL_WORK_S)
    for mode in ("serial", "ultra"):
        leg = report[mode]
        assert leg["wall_s"] > 0
        assert leg["stage_latency_p50_s"] > 0
        assert leg["stage_latency_p95_s"] >= leg["stage_latency_p50_s"]
        assert leg["first_draft_latency_s"] > 0
        assert leg["spend"]["exec_count"] == len(deck)
        assert leg["qc_quality"]["all_done"]


def test_missing_fixture_is_undetermined_not_pass():
    try:
        load_deck(_FIXDIR / "perf_no_such_deck.json")
    except FileNotFoundError:
        return
    raise AssertionError("missing fixture must raise, never read as empty")


if __name__ == "__main__":
    for name, deck_path, work in (("small", SMALL_FIXTURE, SMALL_WORK_S),
                                  ("large", LARGE_FIXTURE, LARGE_WORK_S)):
        deck = load_deck(deck_path)
        validate_deck(deck)
        report = compare(deck, work)
        print(f"{name}: {len(deck)} slides serial={report['serial']['wall_s']:.3f}s "
              f"ultra={report['ultra']['wall_s']:.3f}s "
              f"speedup={report['speedup']:.2f}x")

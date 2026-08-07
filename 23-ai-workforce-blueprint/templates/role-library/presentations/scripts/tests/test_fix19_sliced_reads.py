#!/usr/bin/env python3
"""
test_fix19_sliced_reads.py — FIX-19 regression test (right-size tool results / D18).

Proves the QC gate for FIX-19:

  "Read a large file (34-102KB class) through the sliced-read path.
   Result returns only the requested slice; zero [tool-result-truncation]
   events in the session. Slice bounds + byte counts; truncation counter = 0."

The 2026-08-06 E2E session logged 33 `[tool-result-truncation]` events because the
agent read WHOLE 34-102KB SOP/role files into tool results (D18). This test proves
the engine's sliced-read path (scripts/read_slice.py) returns ONLY the requested
slice and keeps the truncation counter at 0 when reads are sliced:

  1. read_slice() on a >90KB file returns only the requested line range
     (slice bounds + byte counts reported; total_bytes == the whole file).
  2. byte-range reads return exactly the requested bytes.
  3. the truncation counter increments ONLY when a read would exceed the
     guard budget (MAX_SLICE_BYTES) — the D18 oversized-read case.
  4. many small sliced reads (the normal build pattern) keep the counter at 0.
  5. index mode emits the markdown section table of contents (a cheap way to
     find the slice you need without reading the whole file).
  6. a bare SOP filename resolves to the department sops/ mirror — the exact
     ref the engine's --next payload hands the agent.

Pytest-native (each test_* uses assert) AND directly runnable via main().

Run:  python3 tests/test_fix19_sliced_reads.py
      python3 -m pytest tests/test_fix19_sliced_reads.py -q
Exit: 0 = all assertions passed; 1 = a case failed.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import read_slice as rs  # noqa: E402

MAX_SLICE_BYTES = rs.MAX_SLICE_BYTES


def _big_file(td, n_sections=2000):
    """A ~100KB markdown fixture: n_sections x a 2-line block."""
    body = "\n".join(
        f"## Section {i}\nLine content number {i} — " + ("x" * 40)
        for i in range(1, n_sections + 1)
    )
    p = Path(td) / "big-sop.md"
    p.write_text(body)
    return p, len(body.splitlines())


def test_sliced_read_returns_only_the_slice():
    """QC gate: a large file (34-102KB class) read through the sliced-read path
    returns only the requested slice, with slice bounds + byte counts."""
    with tempfile.TemporaryDirectory(prefix="fix19_slice_") as td:
        big, total_lines = _big_file(td)
        assert big.stat().st_size > 90_000, big.stat().st_size
        total = big.stat().st_size

        # Isolated counter so the assertion is hermetic (a shared counter could
        # carry a pre-existing truncation event from another test's run).
        ctr = Path(td) / "working" / "checkpoints" / "trunc_slice.json"
        r = rs.read_slice(big, lines=(50, 60), here=Path(td), counter=ctr)
        assert r["total_bytes"] == total, r
        assert r["slice"] == {"lines": [50, 60], "lines_total": total_lines}, r
        # only the 11 requested lines came back (50..60 inclusive)
        got = [l for l in r["text"].splitlines() if l.strip()]
        assert len(got) == 11, f"returned {len(got)} lines, want 11"
        # every 'content number' line maps to the section index implied by the
        # requested line range: section i occupies file lines (2i-1, 2i), so
        # lines 50..60 carry content lines 25..30 (at 50,52,54,56,58,60).
        nums = [int(l.split()[3]) for l in got if "content number" in l]
        assert nums == list(range(25, 31)), nums
        # the slice is a tiny fraction of the whole file
        assert r["returned_bytes"] < 4000, r
        assert r["returned_bytes"] / total < 0.05, r
        # sliced read never trips the truncation budget
        assert r["would_exceed_budget"] is False, r
        assert r["truncation_events"] == 0, r


def test_byte_range_read():
    with tempfile.TemporaryDirectory(prefix="fix19_bytes_") as td:
        big, _ = _big_file(td)
        r = rs.read_slice(big, offset=0, length=1000, here=Path(td))
        assert r["slice"]["length"] == 1000, r
        assert r["returned_bytes"] == 1000, r
        assert r["returned_bytes"] < r["total_bytes"], r

        r2 = rs.read_slice(big, offset=500, length=250, here=Path(td))
        assert r2["slice"]["length"] == 250 and r2["returned_bytes"] == 250, r2


def test_oversized_read_increments_truncation_counter():
    """D18 case: an oversized read (whole-file) would trip the budget; the
    counter is incremented so the event is visible, not silent."""
    with tempfile.TemporaryDirectory(prefix="fix19_over_") as td:
        big, _ = _big_file(td)
        ctr = Path(td) / "working" / "checkpoints" / "trunc.json"
        r = rs.read_slice(big, lines=(1, 10_000), here=Path(td), counter=ctr)
        assert r["would_exceed_budget"] is True, r
        assert r["returned_bytes"] > MAX_SLICE_BYTES, r
        assert r["truncation_events"] == 1, r
        obj = json.loads(ctr.read_text())
        assert obj["truncation_events"] == 1, obj


def test_sliced_build_keeps_counter_zero():
    """QC gate: a build that reads in slices never accumulates truncation events."""
    with tempfile.TemporaryDirectory(prefix="fix19_zero_") as td:
        big, _ = _big_file(td)
        ctr = Path(td) / "working" / "checkpoints" / "trunc2.json"
        for lo in range(1, 200, 20):
            rs.read_slice(big, lines=(lo, lo + 9), here=Path(td), counter=ctr)
        obj = json.loads(ctr.read_text())
        assert obj.get("truncation_events", 0) == 0, obj
        assert len(obj.get("reads", [])) == 10, obj
        # every read stayed under the budget
        assert all(not r.get("would_exceed_budget") for r in obj["reads"]), obj


def test_index_mode():
    """Index mode gives the agent a cheap table of contents of a large SOP, so it
    can find the slice it needs without reading the whole file."""
    with tempfile.TemporaryDirectory(prefix="fix19_index_") as td:
        big, _ = _big_file(td)
        r = rs.read_slice(big, index=True, here=Path(td))
        assert len(r["index"]) >= 100, r
        assert r["index"][0]["header"].startswith("Section"), r
        assert all(isinstance(s["line"], int) for s in r["index"]), r


def test_sop_filename_resolves_to_mirror():
    """The engine's --next payload hands the agent bare SOP filenames
    (e.g. 'qc-specialist-presentations-sops.md'); the sliced-read path must
    resolve them to the department sops/ mirror the same way the engine does."""
    r = rs.read_slice("qc-specialist-presentations-sops.md", index=True,
                      here=HERE)
    assert r["total_bytes"] > 100_000, r  # the 34-102KB class
    assert "sops" in r["file"], r
    # the real 125KB QC SOP's section headers resolve
    assert any("9.1" in s["header"] or "9.2" in s["header"] for s in r["index"]), \
        [s["header"] for s in r["index"]][:10]


def test_cli():
    """CLI self-test + a real sliced read round-trip."""
    r = subprocess.run([sys.executable, str(HERE / "read_slice.py"), "--self-test"],
                       capture_output=True, text=True, cwd=str(HERE))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout, r.stdout

    # Isolated counter so the CLI's truncation_events assertion is hermetic.
    with tempfile.TemporaryDirectory(prefix="fix19_cli_") as td:
        ctr = str(Path(td) / "cli_trunc.json")
        r2 = subprocess.run(
            [sys.executable, str(HERE / "read_slice.py"),
             "qc-specialist-presentations-sops.md", "--lines", "262-270",
             "--json", "--counter", ctr],
            capture_output=True, text=True, cwd=str(HERE))
        assert r2.returncode == 0, r2.stderr
        payload = json.loads(r2.stdout)
        assert payload["total_bytes"] > 100_000, payload
        assert payload["returned_bytes"] < 4000, payload
        assert payload["truncation_events"] == 0, payload
        assert payload["slice"]["lines"] == [262, 270], payload


# ---------------------------------------------------------------------------
# Direct-run wrapper (pytest uses the test_* functions above).
# ---------------------------------------------------------------------------
def _run_all():
    failures = []
    for fn in (test_sliced_read_returns_only_the_slice, test_byte_range_read,
               test_oversized_read_increments_truncation_counter,
               test_sliced_build_keeps_counter_zero, test_index_mode,
               test_sop_filename_resolves_to_mirror, test_cli):
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, exc))
            print(f"  [FAIL] {fn.__name__}: {exc}")
    print("=" * 60)
    if failures:
        print(f"FIX-19 test: FAIL — {len(failures)} case(s) failed")
        return 1
    print("FIX-19 test: PASS — sliced reads return only the requested slice; "
          "truncation counter stays 0 on a sliced build.")
    return 0


if __name__ == "__main__":
    sys.exit(_run_all())

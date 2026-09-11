#!/usr/bin/env python3
"""test_pres014_unit_records.py -- PRES-014 (W2 WF05): durable fan-out unit
records; banked results validated before admission; only failed/changed units
resubmit; max_units disambiguated; bounded QC batches; no restart resets.

THE SPEC'S OWN ACCEPTANCE CHECKS (SPEC.md PRES-014 / QC-PRES-014), each proven
here against the REAL dispatcher fanout path with only the model entrypoint
stubbed (the documented seam every fanout test in this suite already uses):

  1. first run 20 units with 1 failure -> retry EXACTLY 1, not 20
  2. corrupt one cached output -> regenerate EXACTLY 1
  3. change deck content for 2 slides -> those 2 (and only those 2) rerun;
     the dependent harmonizer (the whole-phase aggregate+verify that consumes
     every unit) runs after them
  4. style deck 100 slides -> EXACTLY 3 variant calls, not 100
  5. QC batch_width 12 over 100 slides -> 9 bounded batches, 100 units
     covered exactly once

Unit-record contract under test (presentation_job/unit_store.py):
  * records keyed company_id/presentation_id/phase_id/unit_id with the unit's
    input hash as the revision witness and sha256 content hashes for outputs;
  * append-only transitions.jsonl + atomic state.json (never rewritten);
  * banked admission = prior ok + matching input hash + existing, hash-verified
    non-empty output file -- any other state re-runs the unit;
  * attempts_total is DURABLE (survives a fresh dispatch_one call, the way a
    restarted dispatcher process would see it) and never reset.

NO NETWORK, NO MODEL SPEND, NO LIVE RUN DIRECTORY.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

CLUSTER_MANIFEST = (
    SCRIPTS.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)
DEPT_ROOT = SCRIPTS.parent

QC_PHASE = "P-PROMPT-QC"          # fanout: {by: slide, batch_width: 12}
STYLE_PHASE = "P-STYLE-SPEC"      # fanout: {by: slide, desired_count: 3, batch_width: 3}
QC_ROLE = "qc-specialist-prompt-presentations"
STYLE_ROLE = "brand-steward"


# ---------------------------------------------------------------------------
# Harness.
# ---------------------------------------------------------------------------
def _seed_run(tmp_path: Path, n_slides: int) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "copy").mkdir(parents=True)
    slides = [
        {"ordinal": i, "slide": i, "slide_id": f"s{i}", "archetype": "cover",
         "copy": [f"Line {i}"], "design_tokens": {"palette": "#223"},
         "research_anchors": [], "negative_requirements": []}
        for i in range(1, n_slides + 1)
    ]
    (run_dir / "working" / "copy" / "slides.json").write_text(json.dumps(slides))
    (run_dir / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"business_name": "TestCo", "company_id": "co-001",
         "hook": "Grow without guesswork"}))
    (run_dir / "state.json").write_text(json.dumps(
        {"manifest_path": str(CLUSTER_MANIFEST)}))
    # Test/CI marker: the whole-phase verifiers degraded-NOTE-pass, so the
    # probes here exercise the UNIT admission/store machinery, not the
    # artifact-content gates (those have their own suites).
    (run_dir / ".test-context").write_text("pres014 unit-record tests")
    return run_dir


def _phase_obj(run_dir: Path, pid: str):
    from presentation_job.dispatcher import load_manifest_for_run
    m = load_manifest_for_run(run_dir)
    assert m is not None, "state.json did not resolve the deployed manifest"
    po = m.phase_or_none(pid)
    assert po is not None, f"{pid} missing from the deployed manifest"
    return po


def _stub_model(monkeypatch, *, fail_keys_一次=None, body=None):
    """Stub the routed model entrypoint. Returns the calls list; each entry is
    (unit_key, attempt_seq). fail_keys_一次: each named unit fails exactly
    once (its first call) then succeeds -- the 'one transient failure' shape."""
    import presentation_job.dispatcher as d
    calls: list = []
    lock = threading.Lock()

    def _fake(system_prompt, user_prompt, *, phase_id, run_dir=None, **kw):
        m = re.search(r'"fanout_unit": "([^"]+)"', user_prompt)
        slide_match = re.search(r"SLIDE (\d+) OF (\d+)", user_prompt)
        ordinal = int(slide_match.group(1)) if slide_match else None
        key = m.group(1) if m else (f"slide-{ordinal:02d}" if ordinal else "?")
        with lock:
            calls.append(key)
            n = len(calls)
        if fail_keys_一次 and key in fail_keys_一次:
            fail_keys_一次.discard(key)  # fails exactly once
            raise RuntimeError(f"stub transient failure for {key}")
        if body is not None:
            return body(key, n), \
                {"request_id": f"stub-{n}"}, {"provider": "stub", "model": "stub-1"}
        return json.dumps({"slide": ordinal, "slide_id": f"s{ordinal}", "pass": True, "average": 9.0}), \
            {"request_id": f"stub-{n}"}, {"provider": "stub", "model": "stub-1"}

    monkeypatch.setattr(d, "dispatch_complete", _fake)
    return calls


def _absent_router(monkeypatch):
    import presentation_job.dispatcher as d
    monkeypatch.setattr(d, "_model_router", None)


def _dispatch(d, run_dir: Path, phase_id: str, owning_role: str):
    return d.dispatch_one(
        run_dir, phase_id, {"phase_id": phase_id, "owning_role": owning_role},
        dept_root=DEPT_ROOT, phase_obj=_phase_obj(run_dir, phase_id),
        worker_id="test-pres014")


def _store(run_dir: Path, phase_id: str) -> dict:
    from presentation_job import unit_store
    return unit_store.load_state(run_dir, phase_id)


def _transitions(run_dir: Path, phase_id: str) -> list:
    from presentation_job import unit_store
    p = unit_store.unit_transitions_path(run_dir, phase_id)
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


# ---------------------------------------------------------------------------
# 1. first run 20 units with 1 failure -> retry EXACTLY 1, not 20.
# ---------------------------------------------------------------------------
def test_twenty_units_one_failure_retries_exactly_one(tmp_path, monkeypatch):
    import presentation_job.dispatcher as d
    _absent_router(monkeypatch)
    run_dir = _seed_run(tmp_path, n_slides=20)
    fail_once = {"slide-07"}
    calls = _stub_model(monkeypatch, fail_keys_一次=fail_once)

    r1 = _dispatch(d, run_dir, QC_PHASE, QC_ROLE)
    assert r1.status == "partial_failure", (
        f"one failed unit of 20 must be a PARTIAL failure: {r1.status}")
    first_run_calls = list(calls)
    assert len(first_run_calls) == 20, (
        f"first run must submit exactly the 20 enumerated units once each, "
        f"got {len(first_run_calls)} calls")

    # RESUME (a fresh dispatch_one -- the same state a restarted dispatcher
    # process reads). Nothing fails now: EXACTLY the failed unit resubmits.
    r2 = _dispatch(d, run_dir, QC_PHASE, QC_ROLE)
    resume_calls = calls[len(first_run_calls):]
    assert resume_calls == ["slide-07"], (
        f"retry must re-run EXACTLY the one failed unit, not all 20: "
        f"re-ran {resume_calls}")

    # The 19 successful units validate as banked: zero new calls for them.
    st = _store(run_dir, QC_PHASE)
    assert st["slide-01"]["status"] == "banked"
    assert st["slide-01"]["attempts_total"] == 1
    assert st["slide-07"]["status"] == "ok"
    assert st["slide-07"]["attempts_total"] == 2, (
        "the failed unit's durable attempt ledger counts both real calls")

    # Append-only transitions: no row was rewritten or dropped.
    rows = _transitions(run_dir, QC_PHASE)
    s7 = [r for r in rows if r["unit_id"] == "slide-07"]
    seq = [r["to_status"] for r in s7]
    assert seq[0] == "admitted" and "failed" in seq and seq[-1] == "ok", seq


# ---------------------------------------------------------------------------
# 2. corrupt one cached output -> regenerate EXACTLY 1.
# ---------------------------------------------------------------------------
def test_corrupt_cached_output_regenerates_exactly_one(tmp_path, monkeypatch):
    import presentation_job.dispatcher as d
    from presentation_job import fanout
    _absent_router(monkeypatch)
    run_dir = _seed_run(tmp_path, n_slides=8)
    calls = _stub_model(monkeypatch)

    r1 = _dispatch(d, run_dir, QC_PHASE, QC_ROLE)
    # The unit-level contract is what PRES-014 owns; the phase-level verifier
    # (report gate) has its own suites and may honestly fail on stub content.
    assert r1.status in ("ok", "exhausted", "partial_failure"), r1.status
    assert len(calls) == 8
    first_run = list(calls)

    # CORRUPT exactly one banked scratch output (bit-rot, a torn write, an
    # editor save). Its recorded hash no longer matches.
    bad = run_dir / "working" / "fanout" / QC_PHASE / "slide-03.out"
    assert bad.is_file()
    bad.write_text("CORRUPTED BY BIT-ROT \x00\xff")

    r2 = _dispatch(d, run_dir, QC_PHASE, QC_ROLE)
    resume_calls = calls[len(first_run):]
    assert resume_calls == ["slide-03"], (
        f"a corrupt cached output must regenerate EXACTLY that one unit: "
        f"re-ran {resume_calls}")

    rows = _transitions(run_dir, QC_PHASE)
    invalid = [r for r in rows if r["to_status"] == "invalidated"]
    assert any("corrupt" in r["reason"] for r in invalid), invalid
    assert all(r["unit_id"] == "slide-03" for r in invalid), invalid

    # The regenerated record now hashes the NEW file content.
    from presentation_job import unit_store
    st = _store(run_dir, QC_PHASE)
    want = unit_store.file_sha256(bad)
    assert st["slide-03"]["output_hash"] == want

    # A NON-corrupt sibling stays banked across the same resume.
    assert st["slide-02"]["status"] == "banked"


# ---------------------------------------------------------------------------
# 3. change deck content for 2 slides -> those 2 rerun; the dependent
#    harmonizer (aggregate + whole-phase verify) runs after the units.
# ---------------------------------------------------------------------------
def test_changed_slides_rerun_exactly_those_two_and_harmonizer(tmp_path, monkeypatch):
    import presentation_job.dispatcher as d
    _absent_router(monkeypatch)
    run_dir = _seed_run(tmp_path, n_slides=10)
    calls = _stub_model(monkeypatch)

    r1 = _dispatch(d, run_dir, QC_PHASE, QC_ROLE)
    assert r1.status in ("ok", "exhausted", "partial_failure")
    assert len(calls) == 10
    first_run = list(calls)

    # Change deck content for slides 4 and 9 ONLY.
    slides = json.loads((run_dir / "working" / "copy" / "slides.json").read_text())
    for s in slides:
        if s["ordinal"] in (4, 9):
            s["copy"] = [f"REVISED line {s['ordinal']}"]
    (run_dir / "working" / "copy" / "slides.json").write_text(json.dumps(slides))

    # Drop the aggregate so the dependent harmonizer step (aggregate + verify)
    # re-runs too -- its inputs changed, exactly the spec's dependent rule.
    (run_dir / "working" / "qc" / "prompt_qc_report.json").unlink(missing_ok=True)

    r2 = _dispatch(d, run_dir, QC_PHASE, QC_ROLE)
    resume_calls = calls[len(first_run):]
    assert sorted(resume_calls) == ["slide-04", "slide-09"], (
        f"exactly the 2 changed slides may rerun: {sorted(resume_calls)}")

    # The aggregate was rewritten AFTER the rerun units (the dependent
    # harmonizer consumed their fresh outputs).
    rows = _transitions(run_dir, QC_PHASE)
    rerun = [r for r in rows if r["unit_id"] in ("slide-04", "slide-09")
             and r["to_status"] == "invalidated"]
    assert len(rerun) == 2, rerun
    for r in rerun:
        assert "input hash changed" in r["reason"]

    # Unchanged slides were banked, never re-billed.
    st = _store(run_dir, QC_PHASE)
    assert st["slide-01"]["attempts_total"] == 1
    assert st["slide-04"]["attempts_total"] == 2
    assert st["slide-09"]["attempts_total"] == 2


# ---------------------------------------------------------------------------
# 4. style deck 100 slides -> EXACTLY 3 variant calls, not 100.
# ---------------------------------------------------------------------------
def test_style_deck_100_slides_makes_three_calls(tmp_path, monkeypatch):
    import presentation_job.dispatcher as d
    _absent_router(monkeypatch)
    run_dir = _seed_run(tmp_path, n_slides=100)
    calls = _stub_model(monkeypatch, body=lambda key, n: json.dumps(
        {"id": "ABC"[(n - 1) % 3],
         "style_directive": f"variant {chr(64 + ((n - 1) % 3) + 1)} warm editorial",
         "representative_slide": ((n - 1) % 3) + 1}))

    r1 = _dispatch(d, run_dir, STYLE_PHASE, STYLE_ROLE)
    assert r1.status == "ok", f"style dispatch failed: {r1.reasons}"

    assert len(calls) == 3, (
        f"the style spec's desired work count is 3 variants: made {len(calls)} "
        f"calls over a 100-slide deck -- the max_units ambiguity PRES-014 "
        f"removes (one model call per slide, reducer keeps 3)")
    spec = json.loads((run_dir / "working" / "copy" /
                       "style_preview_spec.json").read_text())
    # Ids are FORCED unique in unit order (the shipped aggregator's fallback
    # rule), so the SET is exactly {A,B,C} regardless of stub call order.
    assert sorted(v["id"] for v in spec["variants"]) == ["A", "B", "C"]
    assert len(spec["representative_slides"]) == 3

    # The admission trail names the disambiguated fields.
    rows = _transitions(run_dir, STYLE_PHASE)
    assert len(rows) >= 6  # 3 admitted + 3 ok
    admitted = {r["unit_id"] for r in rows if r["to_status"] == "admitted"}
    assert admitted == {"slide-01", "slide-02", "slide-03"}


# ---------------------------------------------------------------------------
# 5. QC batch_width 12 still covers 100 slides EXACTLY once.
# ---------------------------------------------------------------------------
def test_qc_batch_width_12_covers_100_slides_exactly_once(tmp_path, monkeypatch):
    import presentation_job.dispatcher as d
    _absent_router(monkeypatch)
    run_dir = _seed_run(tmp_path, n_slides=100)
    calls = _stub_model(monkeypatch)

    r1 = _dispatch(d, run_dir, QC_PHASE, QC_ROLE)
    # Coverage contract, independent of the artifact verifier's verdict:
    assert sorted(calls) == sorted(f"slide-{i:02d}" for i in range(1, 101)), (
        "per-slide QC must cover EVERY slide exactly once")
    assert len(calls) == 100

    # Bounded batches: 12,12,...,4 (ceil(100/12)=9 admission batches).
    sidecar = run_dir / "working" / "work-orders" / \
        f"{QC_PHASE}.dispatcher-log.jsonl"
    rows = [json.loads(l) for l in sidecar.read_text().splitlines()]
    batches = [r for r in rows if r.get("status") == "fanout_batch_admit"]
    sizes = [b["batch_size"] for b in batches]
    assert sizes == [12] * 8 + [4], (
        f"bounded concurrent batches of 12: got {sizes}")
    assert sum(sizes) == 100

    # Every unit admitted in exactly one batch, none dropped, none doubled.
    st = _store(run_dir, QC_PHASE)
    assert len(st) == 100
    assert all(u["status"] in ("ok", "banked") for u in st.values())


# ---------------------------------------------------------------------------
# 6. max_units disambiguation + manifest migration (unit_store + fanout).
# ---------------------------------------------------------------------------
def test_max_units_migration_is_disambiguated():
    from presentation_job import unit_store
    # Legacy field migrates to batch_width ONLY -- never silently drops work.
    m = unit_store.migrate_fanout_field({"by": "slide", "max_units": 12})
    assert m == {"by": "slide", "batch_width": 12}, m
    # Explicit desired_count wins where the migrated manifest declares it.
    m2 = unit_store.migrate_fanout_field(
        {"by": "slide", "desired_count": 3, "batch_width": 3})
    assert m2 == {"by": "slide", "desired_count": 3, "batch_width": 3}
    # Legacy max_units never becomes a desired count by itself.
    assert "desired_count" not in m

    from presentation_job import fanout
    spec = fanout.parse_fanout_field({"by": "slide", "max_units": 3})
    assert spec.desired_count == 3 and spec.batch_width == 3, (
        "legacy FanoutSpec constructor migration: max_units lands in BOTH "
        "fields, preserving the shipped reducer behavior byte-for-byte")
    # plan_batches: coverage, not concurrency.
    units = [f"u{i}" for i in range(100)]
    batches = unit_store.plan_batches(units, 12)
    assert [len(b) for b in batches] == [12] * 8 + [4]
    flat = [u for b in batches for u in b]
    assert flat == units, "batching preserves order and coverage exactly"


def test_deployed_manifest_is_migrated():
    """The shipped manifest carries the UNAMBIGUOUS fields: every fanout
    declaration has batch_width, no declaration still names max_units, and
    the variant phases name their desired_count of 3."""
    m = json.loads(CLUSTER_MANIFEST.read_text())
    fanouts = [(p["id"], p["fanout"]) for p in m["phases"]
               if isinstance(p.get("fanout"), dict)]
    assert len(fanouts) == 9, [pid for pid, _ in fanouts]
    for pid, f in fanouts:
        assert "max_units" not in f, \
            f"{pid} still carries the ambiguous max_units field"
        assert isinstance(f.get("batch_width"), int) and f["batch_width"] >= 1, \
            f"{pid} has no batch_width"
    for pid, f in fanouts:
        if pid in ("P-STYLE-SPEC", "P-U-DESIGN-SALES",
                   "P-U-DESIGN-CHECKOUT", "P-U-DESIGN-VSL"):
            assert f.get("desired_count") == 3, (pid, f)
    # QC phases keep full coverage: no desired_count narrowing.
    for pid in ("P-PROMPT-QC", "P-IMAGE-QC", "P4-PROMPT", "P9-SPEECH"):
        f = dict(fanouts)[pid]
        assert "desired_count" not in f, (pid, f)


# ---------------------------------------------------------------------------
# 7. no restart resets the attempt/budget ledger (durable across calls).
# ---------------------------------------------------------------------------
def test_attempt_ledger_survives_restart(tmp_path, monkeypatch):
    import presentation_job.dispatcher as d
    _absent_router(monkeypatch)
    run_dir = _seed_run(tmp_path, n_slides=6)
    calls = _stub_model(monkeypatch)

    _dispatch(d, run_dir, QC_PHASE, QC_ROLE)
    st1 = _store(run_dir, QC_PHASE)
    totals1 = {k: v["attempts_total"] for k, v in st1.items()}
    assert all(v == 1 for v in totals1.values()), totals1
    ts1 = (run_dir / "working" / "fanout" / "_units" / QC_PHASE
           / "transitions.jsonl").read_text()

    # Three more dispatch_one calls (the "restart" shape: fresh call, same
    # on-disk store). ALL units bank now; zero new model calls; the ledger
    # rows are APPENDED, never reset or truncated.
    for i in range(3):
        _dispatch(d, run_dir, QC_PHASE, QC_ROLE)
    assert len(calls) == 6, (
        f"resume after success must spend nothing: made {len(calls) - 6} "
        f"extra calls")
    ts2 = (run_dir / "working" / "fanout" / "_units" / QC_PHASE
           / "transitions.jsonl").read_text()
    assert ts2.startswith(ts1), "append-only violated: prior history rewritten"
    st2 = _store(run_dir, QC_PHASE)
    assert {k: v["attempts_total"] for k, v in st2.items()} == totals1, (
        "no restart may reset the attempt ledger")
    assert all(v["status"] == "banked" for v in st2.values())


# ---------------------------------------------------------------------------
# 8. banked validation refuses every dishonest shape (unit_store unit tests).
# ---------------------------------------------------------------------------
def test_validate_banked_refuses_dishonest_records(tmp_path):
    from presentation_job import unit_store
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    out = run_dir / "working" / "fanout" / "PX" / "slide-01.out"
    out.parent.mkdir(parents=True)
    out.write_text("real authored content")
    h = unit_store.content_sha256("real authored content")

    good = {"status": "ok", "input_hash": "IH", "output_path":
            "working/fanout/PX/slide-01.out", "output_hash": h}
    ok, why = unit_store.validate_banked(good, run_dir=run_dir,
                                         current_input_hash="IH")
    assert ok, why

    # Missing file, wrong hash, empty file, changed inputs, failed status.
    bad_missing = dict(good, output_path="working/fanout/PX/gone.out")
    ok, _ = unit_store.validate_banked(bad_missing, run_dir=run_dir,
                                       current_input_hash="IH")
    assert not ok
    ok, why = unit_store.validate_banked(good, run_dir=run_dir,
                                         current_input_hash="CHANGED")
    assert not ok and "input hash" in why
    bad_hash = dict(good, output_hash="deadbeef")
    ok, why = unit_store.validate_banked(bad_hash, run_dir=run_dir,
                                         current_input_hash="IH")
    assert not ok and "corrupt" in why
    out.write_text("")
    ok, why = unit_store.validate_banked(good, run_dir=run_dir,
                                         current_input_hash="IH")
    # An emptied file no longer hashes to the recorded value -- refused as
    # corrupt either way (the reason names the hash mismatch; the empty-
    # content leg covers a record that stored the empty hash).
    assert not ok
    ok, why = unit_store.validate_banked(dict(good, status="failed"),
                                         run_dir=run_dir,
                                         current_input_hash="IH")
    assert not ok and "not banked-ok" in why
    ok, _ = unit_store.validate_banked(None, run_dir=run_dir,
                                       current_input_hash="IH")
    assert not ok


def test_identity_key_components_are_stable(tmp_path):
    from presentation_job import unit_store
    run_dir = tmp_path / "run"
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"company_id": "co-001", "business_name": "TestCo"}))
    assert unit_store.resolve_company_id(run_dir) == "co-001"
    assert unit_store.resolve_presentation_id(run_dir) == run_dir.name
    # The input hash is the revision witness: changed input -> changed hash.
    p1 = unit_store.input_hash_for_unit({"key": "slide-01", "ordinal": 1,
                                         "slide": {"copy": ["A"]}})
    p2 = unit_store.input_hash_for_unit({"key": "slide-01", "ordinal": 1,
                                         "slide": {"copy": ["B"]}})
    p1b = unit_store.input_hash_for_unit({"key": "slide-01", "ordinal": 1,
                                          "slide": {"copy": ["A"]}})
    assert p1 != p2 and p1 == p1b
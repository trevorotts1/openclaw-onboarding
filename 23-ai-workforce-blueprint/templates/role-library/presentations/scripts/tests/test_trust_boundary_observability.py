"""
test_trust_boundary_observability.py — TRUST BOUNDARY, OBSERVABILITY SURFACE
("obs"): proves trust_boundary_observability.py + trust_boundary_report.py
against REAL, unmodified code already on origin/main -- not a fixture
authored for this test. The fixtures used below are the exact literals
already present in test_runfacts.py (SealTypographyQcTest), which this file
does not modify or duplicate logic from -- only reuses the same input shapes
to drive the SAME real call (phase_verifiers.verify("P-TYPO-QC", run_dir),
which internally calls presentation_job.runfacts.shadow_compare()) through
this builder's capture layer instead of letting its stderr line go
uncaptured, which is what happens today.

Three things this file proves, matching the dispatch acceptance criteria:
  1. A legitimate run is unaffected: no would-have-blocked observation is
     recorded, and the wrapped call's return value is untouched.
  2. A tampered run is DETECTED and recorded, but still proceeds: the
     wrapped call still returns the legacy (permissive) result -- report-only,
     not enforced -- while an observation IS persisted to disk.
  3. The record names the specific fact that failed and where it came from:
     the persisted observation's `new_reason` names the exact rubric
     violations (gate label / average / pass / independence), and `source`
     names the exact function that decided it
     (presentation_job.runfacts.shadow_compare).

Also unit-tests parse_line() directly against literal strings copied from
shadow_compare()'s own f-string (runfacts.py), independent of any live
capture, so a parsing regression is caught even if the capture plumbing
itself is fine.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import trust_boundary_observability as obs  # noqa: E402
import trust_boundary_report as report  # noqa: E402

from presentation_job import runfacts as rf  # noqa: E402  (real, unmodified)
import phase_verifiers as pv  # noqa: E402  (real, unmodified)

import build_deck  # noqa: E402  (real, unmodified -- drives the PREFLIGHT family below)
from presentation_job import preflight_shadow  # noqa: E402  (real, unmodified)
from test_preflight import make_workdir  # noqa: E402  -- REUSE the real fixture, author none here


# ---------------------------------------------------------------------------
# Part 1 — parse_line() against literal, hand-verified stderr lines. These
# strings are the EXACT shape shadow_compare()/seal() print today (grepped
# from presentation_job/runfacts.py at HEAD), not invented.
# ---------------------------------------------------------------------------

class TestParseLine:
    def test_divergence_line_real_shape(self):
        line = (
            "TRUST-BOUNDARY-DIVERGENCE gate=qc:typography run_dir=/tmp/run123 "
            "legacy=PASS('') "
            "runfacts=FAIL(\"gate='typography', expected 'Phase Typography-QC'; "
            "average=2.1 below the 8.5 pass threshold; report does not "
            "affirmatively mark pass:true (got False)\") "
            "enforcing=False"
        )
        o = obs.parse_line(line)
        assert o is not None
        assert o.kind == obs.DIVERGENCE_PREFIX
        assert o.source == "presentation_job.runfacts.shadow_compare"
        assert o.gate == "qc:typography"
        assert o.run_dir == "/tmp/run123"
        assert o.legacy_verdict == "PASS"
        assert o.legacy_reason == ""
        assert o.new_verdict == "FAIL"
        assert "average=2.1 below the 8.5 pass threshold" in o.new_reason
        assert "(got False)" in o.new_reason  # proves internal-paren parsing is correct
        assert o.enforcing is False
        assert o.would_have_blocked is True

    def test_divergence_line_pass_direction_is_not_would_have_blocked(self):
        line = ("TRUST-BOUNDARY-DIVERGENCE gate=qc:speech run_dir=/tmp/x "
                "legacy=FAIL('stale reason') runfacts=PASS('now fine') enforcing=False")
        o = obs.parse_line(line)
        assert o is not None
        assert o.would_have_blocked is False  # runfacts says PASS -- nothing to block

    def test_seal_finding_line(self):
        line = ("TRUST-BOUNDARY-SEAL-FINDING run_dir=/tmp/run123 "
                "qc[typography] (working/qc/typography_qc_report.json): "
                "UNTRUSTED — average=2.1 below 8.5")
        o = obs.parse_line(line)
        assert o is not None
        assert o.kind == obs.FINDING_PREFIX
        assert o.source == "presentation_job.runfacts.seal"
        assert "UNTRUSTED" in o.detail

    def test_shadow_error_line(self):
        line = "TRUST-BOUNDARY-SHADOW-ERROR qc:typography: ValueError('boom')"
        o = obs.parse_line(line)
        assert o is not None
        assert o.kind == obs.ERROR_PREFIX

    def test_unrelated_line_is_not_an_observation(self):
        assert obs.parse_line("[2026-08-18T00:00:00Z] phase.start: P-TYPO-QC") is None
        assert obs.parse_line("") is None
        assert obs.parse_line("random build output") is None

    def test_recognised_prefix_but_malformed_shape_is_recorded_degraded(self):
        o = obs.parse_line("TRUST-BOUNDARY-DIVERGENCE this is not the real shape")
        assert o is not None
        assert o.kind == "UNRECOGNISED-SHAPE"
        assert "did not match the expected shape" in o.detail


# ---------------------------------------------------------------------------
# Part 2 — end-to-end against the REAL phase_verifiers.verify("P-TYPO-QC", ...)
# call, using the exact fixture literals from test_runfacts.py's
# SealTypographyQcTest (not modified, not re-derived).
# ---------------------------------------------------------------------------

def _write(p: pathlib.Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, str):
        p.write_text(obj)
    else:
        p.write_text(json.dumps(obj))


class TestEndToEndCapture:
    def setup_method(self):
        self._td = tempfile.TemporaryDirectory()
        self.run_dir = pathlib.Path(self._td.name)
        rf.reset_cache_for_tests()
        os.environ.pop(rf.ENFORCE_ENV, None)

    def teardown_method(self):
        self._td.cleanup()
        os.environ.pop(rf.ENFORCE_ENV, None)
        rf.reset_cache_for_tests()

    def _report_path(self) -> pathlib.Path:
        return self.run_dir / "working" / "qc" / "typography_qc_report.json"

    # -- Known-good control: legitimate run is unaffected --------------------
    def test_legitimate_run_is_unaffected_and_nothing_would_have_blocked(self):
        _write(self._report_path(), {
            "gate": "Phase Typography-QC", "average": 9.1, "pass": True,
            "triggered_autofails": [],
            "qc_independence": {"graded_by": "typography-qc-specialist", "independent": True},
        })

        captured = []
        with obs.capture_stderr(self.run_dir, observations=captured):
            ok, reasons = pv.verify("P-TYPO-QC", self.run_dir)

        assert ok is True
        assert reasons == []
        # No divergence -- shadow_compare() itself prints nothing on a match.
        assert captured == []

        persisted = obs.load_observations(self.run_dir)
        assert persisted == []
        would_block = [o for o in persisted if o.would_have_blocked]
        assert would_block == []

        rendered = report.render_text(persisted, str(self.run_dir))
        assert "no TRUST-BOUNDARY-* observations recorded" in rendered

    # -- Tampered run: detected + recorded, run still proceeds --------------
    def test_tampered_run_detected_recorded_and_still_proceeds(self):
        # THE PROVEN GAP, verbatim from phase_verifiers.py's own module
        # docstring and test_runfacts.py's proven-gap fixture: a report that
        # says pass:false is accepted as a PASS by the legacy (file-exists-
        # only) verifier.
        _write(self._report_path(),
               '{"gate":"typography","pass":false,"average":2.1,'
               '"failures":["everything is broken"]}')

        captured = []
        with obs.capture_stderr(self.run_dir, observations=captured):
            ok, reasons = pv.verify("P-TYPO-QC", self.run_dir)

        # ACCEPTANCE: "a tampered run is DETECTED and recorded (but still
        # proceeds)" -- the call must still return the legacy permissive
        # result. Report-only means this pass cannot brick a real run.
        assert ok is True, "report-only mode must not change the legacy PASS result"
        assert reasons == []

        # DETECTED: this single verify() call touches BOTH existing signal
        # emitters -- get_or_seal() prints its own TRUST-BOUNDARY-SEAL-FINDING
        # for the same untrusted report, and shadow_compare() separately
        # prints the TRUST-BOUNDARY-DIVERGENCE for the gate check itself.
        # Both are real, both are captured -- this module doesn't privilege
        # one emitter over the other.
        assert len(captured) == 2
        by_kind = {o.kind: o for o in captured}
        assert obs.FINDING_PREFIX in by_kind
        assert obs.DIVERGENCE_PREFIX in by_kind
        live = by_kind[obs.DIVERGENCE_PREFIX]
        assert live.would_have_blocked is True

        # RECORDED: the SAME observations are now on disk, independent of the
        # in-process list -- proves persistence, not just in-memory capture.
        log_path = self.run_dir / obs.SHADOW_LOG_REL
        assert log_path.is_file()
        assert oct(log_path.stat().st_mode)[-3:] == "600"
        persisted = obs.load_observations(self.run_dir)
        assert len(persisted) == 2
        divergences = [o for o in persisted if o.kind == obs.DIVERGENCE_PREFIX]
        assert len(divergences) == 1
        p = divergences[0]

        # ACCEPTANCE: "the record names the specific fact that failed and
        # where it came from".
        assert p.gate == "qc:typography"                              # WHAT gate
        assert p.new_verdict == "FAIL"                                 # the stricter verdict
        assert "below the 8.5" in p.new_reason                         # the SPECIFIC fact
        assert "does not affirmatively mark pass:true" in p.new_reason  # a second specific fact
        assert p.legacy_verdict == "PASS"                              # what the run actually got
        assert p.source == "presentation_job.runfacts.shadow_compare"  # WHERE it came from
        assert p.enforcing is False
        assert p.run_dir == str(self.run_dir)
        assert p.would_have_blocked is True

        # The operator-facing reader surfaces the same specific facts.
        rendered = report.render_text(persisted, str(self.run_dir))
        assert "WOULD-HAVE-BLOCKED" in rendered
        assert "gate=qc:typography" in rendered
        assert "below the 8.5" in rendered
        assert "presentation_job.runfacts.shadow_compare" in rendered
        assert "PROCEEDED anyway" in rendered
        assert "SEAL-FINDING" in rendered  # the second, independent signal is surfaced too

        json_rendered = json.loads(report.render_json(persisted, str(self.run_dir)))
        assert json_rendered["would_have_blocked_count"] == 1
        assert json_rendered["total"] == 2

    def test_capture_is_a_true_pass_through_real_stderr_still_receives_the_line(self, capsys):
        _write(self._report_path(),
               '{"gate":"typography","pass":false,"average":2.1}')
        with obs.capture_stderr(self.run_dir):
            pv.verify("P-TYPO-QC", self.run_dir)
        captured_stderr = capsys.readouterr().err
        assert obs.DIVERGENCE_PREFIX in captured_stderr, (
            "capture_stderr must be a pass-through tee -- the real stderr "
            "consumer (a build log) must still see the exact same line it "
            "would have seen with no observability layer present at all."
        )

    def test_record_observation_write_failure_is_swallowed_not_raised(self):
        # An unwritable log path (parent is a file, not a dir) must degrade
        # silently -- observability must never be the reason a run breaks.
        blocker = self.run_dir / "working"
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("not a directory")
        o = obs.ShadowObservation(
            captured_at="x", kind=obs.DIVERGENCE_PREFIX, source="test",
            gate="g", run_dir=str(self.run_dir), legacy_verdict="PASS",
            legacy_reason="", new_verdict="FAIL", new_reason="x",
            enforcing=False, detail=None, raw_line="x",
        )
        obs.record_observation(o, self.run_dir)  # must not raise


# ---------------------------------------------------------------------------
# Part 3 — the enforcing=1 case never reaches this module at all: proves the
# observability layer records identically regardless of enforcement state
# (it observes what shadow_compare reports, not what the caller decides to
# do about it), and that this file does not itself change behavior when
# enforcing is flipped -- that decision belongs to runfacts.py, not here.
# ---------------------------------------------------------------------------

class TestEnforcingIsOrthogonalToRecording:
    def setup_method(self):
        self._td = tempfile.TemporaryDirectory()
        self.run_dir = pathlib.Path(self._td.name)
        rf.reset_cache_for_tests()
        os.environ.pop(rf.ENFORCE_ENV, None)

    def teardown_method(self):
        self._td.cleanup()
        os.environ.pop(rf.ENFORCE_ENV, None)
        rf.reset_cache_for_tests()

    def test_enforcing_on_still_gets_recorded_with_enforcing_true(self):
        p = self.run_dir / "working" / "qc" / "typography_qc_report.json"
        _write(p, '{"gate":"typography","pass":false,"average":2.1}')
        os.environ[rf.ENFORCE_ENV] = "1"
        try:
            rf.reset_cache_for_tests()
            with obs.capture_stderr(self.run_dir):
                ok, reasons = pv.verify("P-TYPO-QC", self.run_dir)
            # This file makes NO claim about what the caller does when
            # enforcing -- that is runfacts.py's contract, not this
            # module's. It only asserts the observation is still captured,
            # and captured with enforcing=True this time.
            assert ok is False
            persisted = obs.load_observations(self.run_dir)
            divergences = [o for o in persisted if o.kind == obs.DIVERGENCE_PREFIX]
            assert len(divergences) == 1
            assert divergences[0].enforcing is True
        finally:
            os.environ.pop(rf.ENFORCE_ENV, None)


# ---------------------------------------------------------------------------
# Part 4 — the PREFLIGHT family (presentation_job/preflight_shadow.py, wired
# into build_deck.run_preflight()). REGRESSION GUARD for the exact bug fixed
# on fix/trust-parser: parse_line()'s KNOWN_KINDS never listed any of these
# four `-PREFLIGHT-`-infixed prefixes, so it returned None on every line this
# surface printed. Every line asserted on below comes from calling the REAL
# build_deck.run_preflight() (in-process, same pattern as
# test_preflight_shadow.py's own CASE A/B/C) or the REAL preflight_shadow
# open_run()/record() functions directly with an input shaped to make their
# OWN internal except clauses fire -- nothing here is a hand-typed fixture
# string standing in for wrapper output.
# ---------------------------------------------------------------------------

def _run_preflight_captured(root: pathlib.Path):
    import contextlib
    import io
    out, err = io.StringIO(), io.StringIO()
    exited_3 = False
    slides_path = root / "slides.json"
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            build_deck.run_preflight(root, slides_path=slides_path)
        except SystemExit as e:
            exited_3 = (e.code == 3)
    return exited_3, out.getvalue(), err.getvalue()


class TestPreflightFamily:
    def _assert_every_trust_boundary_line_parses(self, stderr_text: str):
        tb_lines = [ln for ln in stderr_text.splitlines() if "TRUST-BOUNDARY" in ln]
        assert tb_lines, "expected at least one TRUST-BOUNDARY line to check"
        unparsed = [ln for ln in tb_lines if obs.parse_line(ln) is None]
        assert unparsed == [], (
            f"parse_line() returned None for {len(unparsed)}/{len(tb_lines)} real "
            f"wrapper lines (the exact regression this test guards): {unparsed}"
        )
        return tb_lines

    def test_clean_run_summary_line_is_parsed(self):
        root = make_workdir(with_artifacts=True)
        exited_3, _out, err = _run_preflight_captured(root)
        assert not exited_3
        tb_lines = self._assert_every_trust_boundary_line_parses(err)
        summaries = [obs.parse_line(ln) for ln in tb_lines
                     if ln.startswith(obs.PREFLIGHT_SUMMARY_PREFIX)]
        assert len(summaries) == 1
        s = summaries[0]
        assert s.kind == obs.PREFLIGHT_SUMMARY_PREFIX
        assert s.run_dir == str(root)
        assert "entries=62" in s.detail
        assert "divergences=0" in s.detail
        assert s.would_have_blocked is False

    def test_tampered_run_divergence_and_would_block_lines_are_parsed(self):
        root = make_workdir(with_artifacts=True)
        idx = None
        for i, entry in enumerate(build_deck.PREFLIGHT_REQUIRED):
            if entry[0] == "working/copy/intake.json":
                idx = i
                break
        assert idx is not None
        rel, label, phase, real_check = build_deck.PREFLIGHT_REQUIRED[idx]

        def _tamper_then_check(path):
            p = pathlib.Path(path)
            o = json.loads(p.read_text())
            o["_test_injected_field"] = "race"
            p.write_text(json.dumps(o))
            return real_check(path)

        build_deck.PREFLIGHT_REQUIRED[idx] = (rel, label, phase, _tamper_then_check)
        try:
            exited_3, _out, err = _run_preflight_captured(root)
        finally:
            build_deck.PREFLIGHT_REQUIRED[idx] = (rel, label, phase, real_check)
        assert not exited_3, "report-only surface must never block"

        tb_lines = self._assert_every_trust_boundary_line_parses(err)
        parsed = [obs.parse_line(ln) for ln in tb_lines]

        divergences = [o for o in parsed if o.kind == obs.PREFLIGHT_DIVERGENCE_PREFIX]
        assert len(divergences) == 1
        d = divergences[0]
        assert d.gate == label  # names the SPECIFIC gate, including its spaces
        assert d.run_dir == str(root)
        assert d.legacy_verdict == "PASS"
        assert d.enforcing is False
        assert "intake.json" in d.detail  # names WHERE the fact came from

        would_blocks = [o for o in parsed if o.kind == obs.PREFLIGHT_WOULD_BLOCK_PREFIX]
        assert len(would_blocks) == 1
        wb = would_blocks[0]
        assert wb.gate == label
        assert wb.would_have_blocked is True
        assert "artifact changed" in wb.detail

    def test_preflight_shadow_own_open_run_error_is_parsed(self):
        # Real trigger for preflight_shadow.py's OWN internal except (no
        # colon after the prefix): Path(run_dir) raises inside open_run()'s
        # own try/except when given a non-path-like object.
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = preflight_shadow.open_run(object(), [])
        assert result is None
        line = buf.getvalue().strip()
        assert line.startswith(obs.PREFLIGHT_ERROR_PREFIX)
        o = obs.parse_line(line)
        assert o is not None
        assert o.kind == obs.PREFLIGHT_ERROR_PREFIX
        assert "open_run" in o.detail

    def test_preflight_shadow_own_record_error_is_parsed(self):
        # Real trigger for preflight_shadow.py's OWN internal except in
        # record(): a ctx object missing the attribute record() unconditionally
        # touches (entry_count) makes record()'s own try/except fire.
        import contextlib
        import io

        class _BrokenCtx:
            pass

        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            preflight_shadow.record(_BrokenCtx(), label="test_gate", display="x",
                                     resolved_path=None, legacy_reason=None)
        line = buf.getvalue().strip()
        assert line.startswith(obs.PREFLIGHT_ERROR_PREFIX)
        o = obs.parse_line(line)
        assert o is not None
        assert o.kind == obs.PREFLIGHT_ERROR_PREFIX
        assert "test_gate" in o.detail

    def test_build_deck_own_defense_in_depth_open_run_error_is_parsed(self):
        # Real trigger for build_deck.py's OWN except (colon variant, a
        # DIFFERENT call site than preflight_shadow.py's own): monkeypatch
        # preflight_shadow.open_run itself to raise, bypassing its internal
        # try/except entirely -- build_deck.py's own wrapping try/except
        # around the call site is what fires. Same technique as
        # test_preflight_shadow.py's CASE C.
        root = make_workdir(with_artifacts=True)
        real_open_run = preflight_shadow.open_run

        def _boom(*a, **k):
            raise RuntimeError("test-injected open_run failure")

        preflight_shadow.open_run = _boom
        try:
            exited_3, _out, err = _run_preflight_captured(root)
        finally:
            preflight_shadow.open_run = real_open_run
        assert not exited_3

        tb_lines = self._assert_every_trust_boundary_line_parses(err)
        errors = [obs.parse_line(ln) for ln in tb_lines
                  if ln.startswith(obs.PREFLIGHT_ERROR_PREFIX)]
        assert errors, "expected at least one PREFLIGHT-SHADOW-ERROR line"
        assert any("open_run failed" in (e.detail or "") for e in errors)

    def test_build_deck_own_defense_in_depth_record_error_is_parsed(self):
        # Same technique, the OTHER call site: monkeypatch
        # preflight_shadow.record itself to raise, so build_deck.py's own
        # try/except around ITS record() call (not record()'s own internal
        # one) is what fires -- the fourth and last distinct emission path.
        root = make_workdir(with_artifacts=True)
        real_record = preflight_shadow.record

        def _boom(*a, **k):
            raise RuntimeError("test-injected record failure")

        preflight_shadow.record = _boom
        try:
            exited_3, _out, err = _run_preflight_captured(root)
        finally:
            preflight_shadow.record = real_record
        assert not exited_3

        tb_lines = self._assert_every_trust_boundary_line_parses(err)
        errors = [obs.parse_line(ln) for ln in tb_lines
                  if ln.startswith(obs.PREFLIGHT_ERROR_PREFIX)]
        # One per PREFLIGHT_REQUIRED entry -- record() is monkeypatched to
        # raise on every call in the loop, not just one.
        assert len(errors) == len(build_deck.PREFLIGHT_REQUIRED)
        assert all("record failed" in (e.detail or "") for e in errors)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))

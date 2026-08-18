"""Tests for presentation_job process engine (U011 step 9)."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Ensure the parent (scripts) dir is on sys.path so we can import presentation_job
_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.state import StateStore, RunLock, EXIT_OK, EXIT_LOCK_HELD, EXIT_STATE_CORRUPT, EXIT_GATE_BLOCKED, EXIT_WAIVER_INVALID
from presentation_job.manifest import Manifest, Phase, PHASE_BUDGET_MINUTES, MIN_MANIFEST_VERSION, MIN_MANIFEST_PHASES
from presentation_job.manifest import _assert_manifest_current, resolve_manifest
from presentation_job.board import BoardMirror
from presentation_job.board import BoardMirror

# Override exit codes — test constants
EXIT_MANIFEST_MISMATCH = 7
EXIT_USAGE = 2


def _canonical_manifest() -> Path:
    """Locate the canonical PIPELINE-MANIFEST.json the way the deployed tree and
    the repo tree carry it. Deployed layout first (scripts/../sops/), repo
    layout as fallback (walk up to universal-sops/presentation-slide-craft/).
    Same two-tier resolution manifest_source.resolve_manifest uses."""
    deployed = _scripts_dir.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = _scripts_dir
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError(
        "PIPELINE-MANIFEST.json not found (looked in scripts/../sops/ and the "
        "universal-sops/presentation-slide-craft walk-up)")



# ---------------------------------------------------------------------------
# Test 1: StateStore save then load round-trips, and no .state-*.tmp remains
# ---------------------------------------------------------------------------
class TestStateStore:
    def test_save_load_roundtrip(self, tmp_path):
        """StateStore.save then .load returns the same data."""
        store = StateStore(tmp_path)
        state = {"job_id": "pj_test123", "schema_version": 1, "phases": []}
        store.save(state)

        loaded = store.load()
        assert loaded["job_id"] == "pj_test123"
        assert loaded["schema_version"] == 1

    def test_save_cleans_temp_files(self, tmp_path):
        """After save, no .state-*.tmp file remains."""
        store = StateStore(tmp_path)
        store.save({"job_id": "pj_test", "schema_version": 1, "phases": []})

        tmp_files = list(tmp_path.glob(".state-*.tmp"))
        assert len(tmp_files) == 0, f"Temp files left behind: {tmp_files}"

    # Test 2: schema_version mismatch exits 8
    def test_schema_version_2_exits_8(self, tmp_path):
        """StateStore.load on schema_version 2 exits 8."""
        store = StateStore(tmp_path)
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"job_id": "pj_test", "schema_version": 2, "phases": []}))

        with pytest.raises(SystemExit) as exc:
            store.load()
        assert exc.value.code == EXIT_STATE_CORRUPT


# ---------------------------------------------------------------------------
# Test 3: RunLock prevents concurrent access
# ---------------------------------------------------------------------------
class TestRunLock:
    def test_second_lock_exits_6(self, tmp_path):
        """A second RunLock on the same run dir exits 6."""
        lock1 = RunLock(tmp_path)
        with lock1:
            # Try to acquire a second lock on the same dir
            with pytest.raises(SystemExit) as exc:
                lock2 = RunLock(tmp_path)
                lock2.__enter__()
            assert exc.value.code == EXIT_LOCK_HELD


# ---------------------------------------------------------------------------
# Test 4: Manifest.verify_pin with mismatched sha exits 7
# ---------------------------------------------------------------------------
class TestManifest:
    def test_verify_pin_mismatch_exits_7(self, tmp_path):
        """Manifest.verify_pin with wrong sha exits 7."""
        # Create a minimal manifest file
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "manifest_version": 25,
            "phases": [{"id": "P0A-INTAKE", "order": 1, "owning_role": "test"}],
            "deliverables_required": [],
            "client_package_files": [],
        }))

        m = Manifest(manifest_path)
        with pytest.raises(SystemExit) as exc:
            m.verify_pin("deadbeef00000000000000000000000000000000000000000000000000000000")
        assert exc.value.code == EXIT_MANIFEST_MISMATCH

    # Test 5: _assert_manifest_current on stale fixture exits 7
    def test_assert_manifest_current_stale_exits_7(self, tmp_path):
        """_assert_manifest_current on v18 20-phase manifest exits 7."""
        p = tmp_path / "manifest.json"
        p.write_text(json.dumps({
            "manifest_version": 18,
            "phases": [{"id": f"P{i}", "order": i} for i in range(20)],
            "autofails": [],
        }))
        with pytest.raises(SystemExit) as exc:
            _assert_manifest_current(p)
        assert exc.value.code == EXIT_MANIFEST_MISMATCH

    def test_assert_manifest_current_on_canonical_passes(self):
        """_assert_manifest_current on the real canonical file exits normally."""
        canonical = _canonical_manifest()
        # Should not raise
        _assert_manifest_current(canonical)

    # Test 6: resolve_manifest does NOT search upward
    def test_resolve_manifest_no_upward_search(self, tmp_path, monkeypatch):
        """resolve_manifest with no candidate present exits 2 and does NOT search upward."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        sops_dir = tmp_path / "sops"
        sops_dir.mkdir()

        # Put a v25 manifest TWO levels above, but NOT at candidate location
        far_manifest = tmp_path.parent.parent / "sops" / "PIPELINE-MANIFEST.json"
        far_manifest.parent.mkdir(parents=True, exist_ok=True)
        far_manifest.write_text(json.dumps({
            "manifest_version": 25,
            "phases": [{"id": f"P{i}", "order": i} for i in range(26)],
            "autofails": [{"code": "AF-SP-TEST"} for _ in range(16)],
        }))

        # Clear PRESENTATION_MANIFEST env
        monkeypatch.delenv("PRESENTATION_MANIFEST", raising=False)

        # Should fail: no manifest at candidate location
        with pytest.raises(SystemExit) as exc:
            resolve_manifest(None, run_dir, scripts_dir)
        assert exc.value.code == EXIT_USAGE

    # Test 7: PHASE_BUDGET_MINUTES covers every canonical phase id
    def test_budget_covers_all_canonical_phases(self):
        """PHASE_BUDGET_MINUTES covers every id in the canonical manifest."""
        canonical = _canonical_manifest()
        assert canonical.is_file(), f"Canonical manifest not found at {canonical}"
        manifest_data = json.loads(canonical.read_text())
        manifest_ids = {p["id"] for p in manifest_data["phases"]}
        uncovered = manifest_ids - set(PHASE_BUDGET_MINUTES)
        assert uncovered == set(), f"Canonical phase ids with no budget entry: {uncovered}"

    # Test 8: Phase.budget_minutes vs heartbeat_minutes are different
    def test_p4_render_budget_vs_heartbeat(self):
        """P4-RENDER budget_minutes is 240, heartbeat_interval is 10."""
        phase = Phase(
            id="P4-RENDER", order=1, owning_role="renderer",
            produces_artifact=["test.png"], executor_kind="script",
            executor_cmd=None, verifier=None,
            heartbeat_minutes=10, long_running=True,
            client_report={},
        )
        assert phase.budget_minutes == 240
        assert phase.heartbeat_interval_minutes == 10


# ---------------------------------------------------------------------------
# Test 9: BoardMirror with both URLs unset
# ---------------------------------------------------------------------------
class TestBoardMirror:
    def _make_boardmirror(self, tmp_path, fake_cc_board, monkeypatch):
        """Helper to create a BoardMirror with cc_board patched."""
        import presentation_job.board as board_module
        from presentation_job.state import StateStore

        monkeypatch.delenv("COMMAND_CENTER_URL", raising=False)
        monkeypatch.delenv("MISSION_CONTROL_URL", raising=False)

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        state = {"job_id": "test", "events": []}
        store = StateStore(run_dir)

        # Create a simple reporter that records events
        class TestReporter:
            def __init__(self):
                self.events = []
            def event(self, kind, message, **extra):
                self.events.append({"kind": kind, "message": message})
                state.setdefault("events", []).append({"kind": kind, "message": message})

        reporter = TestReporter()

        # Patch cc_board in board module
        with mock.patch.object(board_module, "_cc_board", fake_cc_board):
            bm = board_module.BoardMirror(run_dir, state, store, reporter)
            return bm, state, reporter

    def test_disabled_board_makes_zero_http_calls(self, tmp_path, monkeypatch):
        """BoardMirror with both URLs unset returns None from every method."""
        fake_cc = mock.MagicMock()
        fake_cc.board_config.return_value = None
        # Make every function raise ConnectionRefusedError if called
        fake_cc.ingest_deck_task.side_effect = ConnectionRefusedError("should not be called")
        fake_cc.post_activity.side_effect = ConnectionRefusedError("should not be called")
        fake_cc.patch_phase.side_effect = ConnectionRefusedError("should not be called")

        bm, state, reporter = self._make_boardmirror(tmp_path, fake_cc, monkeypatch)

        # All methods should return None without raising
        assert bm.open_card("test", "title", "desc") is None
        assert bm.phase_progress("P4-RENDER", "done") is None
        assert bm.mark_in_progress() is None
        assert bm.mark_review() is None
        assert bm.mark_blocked("P4-RENDER", "stuck") is None

        # Should have recorded at least one board.* event
        board_events = [e for e in state["events"] if e["kind"].startswith("board.")]
        assert len(board_events) >= 1, "No board.* events recorded"

        # No HTTP calls were made
        fake_cc.ingest_deck_task.assert_not_called()
        fake_cc.post_activity.assert_not_called()
        fake_cc.patch_phase.assert_not_called()

    # Test 9b: TypeError raised by cc_board is recorded as board.internal_error, not board.error
    def test_typeerror_records_internal_error(self, tmp_path, monkeypatch):
        """A TypeError from cc_board records board.internal_error, not board.error."""
        import presentation_job.board as board_module
        from presentation_job.state import StateStore
        fake_cc = mock.MagicMock()
        fake_cc.board_config.return_value = {"url": "http://example.com"}  # enabled
        fake_cc.CC_TASK_STATUSES = frozenset({"in_progress", "review", "blocked"})
        fake_cc.ingest_deck_task.side_effect = TypeError("wrong argument name")

        monkeypatch.delenv("COMMAND_CENTER_URL", raising=False)
        monkeypatch.delenv("MISSION_CONTROL_URL", raising=False)

        # Keep mock active for the ENTIRE test. The bare `board_module._cc_board =
        # fake_cc` assignment is itself the leak that poisoned every later test in
        # this module: mock.patch only restores the attribute it patched
        # (_get_cc_board); the direct assignment to _cc_board survives the with
        # block, so BoardMirror.__init__ in subsequent tests read `_read_manifest()`
        # off the leftover MagicMock, stuffed a MagicMock task_id into
        # state["board"], and json.dumps blew up (test-order-dependent failures).
        with mock.patch.object(board_module, "_cc_board", fake_cc), \
             mock.patch("presentation_job.board._get_cc_board", return_value=fake_cc):
            run_dir = tmp_path / "run"
            run_dir.mkdir()
            state = {"job_id": "test", "events": []}
            store = StateStore(run_dir)
            class R:
                def event(self, kind, message, **extra):
                    state.setdefault("events", []).append({"kind": kind, "message": message})
            reporter = R()
            bm = BoardMirror(run_dir, state, store, reporter)

            # Should NOT raise
            result = bm.open_card("test", "title", "desc")
            assert result is None

            # Should have board.internal_error, not just board.error
            internal_errors = [e for e in state["events"] if e["kind"] == "board.internal_error"]
            assert len(internal_errors) >= 1, (
                f"No board.internal_error events. All board events: "
                f"{[e['kind'] for e in state['events']]}"
            )

    # Test 10: BoardMirror.mark_review refuses "done"
    def test_mark_review_refuses_done(self, tmp_path, monkeypatch):
        """BoardMirror.mark_review never passes 'done' to patch_phase."""
        fake_cc = mock.MagicMock()
        fake_cc.board_config.return_value = {"url": "http://example.com"}  # enabled
        fake_cc.CC_TASK_STATUSES = frozenset({"review"})
        fake_cc.patch_phase.return_value = True

        bm, state, reporter = self._make_boardmirror(tmp_path, fake_cc, monkeypatch)

        # Set a task_id so the call goes through
        state.setdefault("board", {})["task_id"] = "task-123"

        bm.mark_review()

        # Check that patch_phase was NOT called with "done"
        for call_args in fake_cc.patch_phase.call_args_list:
            args, kwargs = call_args
            # args: (run_dir, task_id, phase_id, status, note, env)
            status = args[3] if len(args) > 3 else kwargs.get("status")
            assert status != "done", f"mark_review sent status='done': {call_args}"

    # Test 11: run_phase with empty executor returns 3 and sets BLOCKED
    def test_run_phase_empty_executor_returns_3(self, tmp_path):
        """run_phase on a phase producing nothing returns 3 and BLOCKED."""
        from presentation_job.state import StateStore
        from presentation_job.manifest import Manifest, Phase
        from presentation_job.phases import Engine

        run_dir = tmp_path / "run"
        run_dir.mkdir()

        # Create a minimal manifest
        manifest_path = tmp_path / "manifest.json"
        manifest_json = {
            "manifest_version": 25,
            "phases": [{
                "id": "P0A-INTAKE",
                "order": 1,
                "owning_role": "test",
                "produces_artifact": ["output.txt"],
                "executor": {"kind": "none"},
            }],
        }
        manifest_path.write_text(json.dumps(manifest_json))
        manifest = Manifest(manifest_path)

        store = StateStore(run_dir)
        state = {
            "schema_version": 1,
            "job_id": "test_job",
            "run_dir": str(run_dir),
            "created_at": "2026-01-01T00:00:00+00:00",
            "manifest_path": str(manifest_path),
            "manifest_version": 25,
            "manifest_sha256": manifest.sha256,
            "presentation_type": "from_scratch",
            "requester": {"chat_id": "test"},
            "current_phase": None,
            "phases": [],
            "gates": {},
            "waivers": [],
            "events": [],
            "sent": {},
            "undeliverable": [],
            "heartbeat": {},
            "terminal": None,
        }
        store.save(state)

        engine = Engine(run_dir, manifest, store, state, dry_run=True)
        rc = engine.run_phase(manifest.phase("P0A-INTAKE"))
        assert rc == EXIT_GATE_BLOCKED, f"Expected EXIT_GATE_BLOCKED (3), got {rc}"
        assert state["terminal"] == "BLOCKED"

    # Test 12: run_phase calls persona governance for a BLEND_PHASE_FOR-mapped phase
    def test_run_phase_calls_persona_governance_for_mapped_phase(self, tmp_path, monkeypatch):
        """run_phase must call persona.resolve_for_phase(run_dir, phase.id) for a
        phase id that is one of the four BLEND_PHASE_FOR keys (e.g. P4-COPY).
        This is the integration test that bleeds if the U024 call site in
        phases.py is ever removed."""
        from presentation_job.state import StateStore
        from presentation_job.manifest import Manifest, Phase
        from presentation_job.phases import Engine
        import presentation_job.phases as phases_mod

        run_dir = tmp_path / "run"
        run_dir.mkdir()

        manifest_path = tmp_path / "manifest.json"
        manifest_json = {
            "manifest_version": 25,
            "phases": [{
                "id": "P4-COPY",
                "order": 1,
                "owning_role": "test",
                "produces_artifact": ["output.txt"],
                "executor": {"kind": "none"},
            }],
        }
        manifest_path.write_text(json.dumps(manifest_json))
        manifest = Manifest(manifest_path)

        store = StateStore(run_dir)
        state = {
            "schema_version": 1,
            "job_id": "test_job",
            "run_dir": str(run_dir),
            "created_at": "2026-01-01T00:00:00+00:00",
            "manifest_path": str(manifest_path),
            "manifest_version": 25,
            "manifest_sha256": manifest.sha256,
            "presentation_type": "from_scratch",
            "requester": {"chat_id": "test"},
            "current_phase": None,
            "phases": [],
            "gates": {},
            "waivers": [],
            "events": [],
            "sent": {},
            "undeliverable": [],
            "heartbeat": {},
            "terminal": None,
        }
        store.save(state)

        calls = []
        stub = mock.MagicMock(side_effect=lambda run_dir, phase_id, *a, **kw:
                               calls.append(phase_id) or None)
        monkeypatch.setattr(phases_mod.persona, "resolve_for_phase", stub)

        engine = Engine(run_dir, manifest, store, state, dry_run=True)
        engine.run_phase(manifest.phase("P4-COPY"))

        stub.assert_called_once()
        assert calls == ["P4-COPY"], (
            f"Expected persona.resolve_for_phase to be called with phase id "
            f"'P4-COPY', got calls={calls}"
        )


# ---------------------------------------------------------------------------
# Test 12: Mutation guard — importing state must not import phases
# ---------------------------------------------------------------------------
class TestModuleBoundaries:
    def test_import_state_does_not_import_phases(self):
        """Importing presentation_job.state must not import presentation_job.phases."""
        # Snapshot every already-imported presentation_job.* module, then clean
        # sys.modules so the import below starts from a blank slate, and put the
        # snapshot BACK afterward (try/finally -- must run on failure too).
        #
        # Leaving the deletion in place (as this test used to) corrupts every
        # later test in the same pytest session that imports presentation_job.report,
        # .phases, etc. fresh: e.g. Test8MessageBound in test_report.py does
        # `import presentation_job.report as rpt` inside its own test body, and
        # with the real module gone from sys.modules that import silently creates
        # a SECOND, distinct module object. Test8 then monkeypatches `_parse_minutes`
        # on that second object while the `Reporter` class it actually exercises
        # (imported at test_report.py's top level, before this test ran) still
        # points at the ORIGINAL module's globals -- so the monkeypatch has no
        # effect, real wall-clock time is used, and the throttle test fails
        # nondeterministically depending on file/test collection order. Confirmed
        # by running `pytest tests/test_presentation_job.py tests/test_report.py`:
        # FAILED before this fix (Test8 saw real epoch-minute timestamps instead of
        # the monkeypatched fake clock); passes after restoring sys.modules here.
        saved = {k: v for k, v in sys.modules.items() if k.startswith("presentation_job")}
        for k in list(sys.modules):
            if k.startswith("presentation_job"):
                del sys.modules[k]
        try:
            import presentation_job.state
            assert "presentation_job.phases" not in sys.modules, (
                "state.py causes phases.py to be imported — circular dependency"
            )
        finally:
            for k in list(sys.modules):
                if k.startswith("presentation_job"):
                    del sys.modules[k]
            sys.modules.update(saved)


# ---------------------------------------------------------------------------
# U069: shell-injection fix --- three tests
# ---------------------------------------------------------------------------
class TestU069ShellInjectionFix:
    """U069: Stop shell=True on manifest strings and run-dir path."""

    def _make_engine_state(self, run_dir, manifest_path, manifest):
        from presentation_job.state import StateStore
        store = StateStore(run_dir)
        state = {
            "schema_version": 1, "job_id": "u069_test",
            "run_dir": str(run_dir), "created_at": "2026-01-01T00:00:00+00:00",
            "manifest_path": str(manifest_path), "manifest_version": 25,
            "manifest_sha256": manifest.sha256, "presentation_type": "from_scratch",
            "requester": {"chat_id": "test"}, "current_phase": None,
            "phases": [], "gates": {}, "waivers": [], "events": [],
            "sent": {}, "undeliverable": [], "heartbeat": {}, "terminal": None,
        }
        store.save(state)
        return store, state

    def _seed_intake_artifact(self, run_dir):
        """WORK-ITEM-14 (R3 U03): phase_verifiers.verify(P0A-INTAKE) is now a
        PRIMARY gate — a missing working/copy/intake.json BLOCKS the phase
        (exit 3) instead of warning. These tests are about executor.cmd
        handling, not the intake gate, so they must satisfy the substance
        verifier for the phase to reach done."""
        (run_dir / "working" / "copy").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "copy" / "intake.json").write_text(json.dumps(
            {"topic": "U069 executor handling", "deck_slug": "deck"}))

    def test_u069_space_in_run_dir_preserves_path(self, tmp_path):
        """U069-a: space in run dir path must arrive as ONE argument."""
        from presentation_job.manifest import Manifest, Phase
        from presentation_job.phases import Engine
        from presentation_job.state import EXIT_OK

        run_dir = tmp_path / "run dir with spaces"
        run_dir.mkdir()
        (run_dir / "echo_argv.py").write_text(
            "import json, sys\njson.dump(sys.argv, open('argv_out.json', 'w'))\n"
        )
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "manifest_version": 25,
            "phases": [{"id": "P0A-INTAKE", "order": 1, "owning_role": "test",
                        "produces_artifact": ["argv_out.json"],
                        "executor": {"kind": "script",
                                     "cmd": "python3 echo_argv.py {run_dir}"}}],
        }))
        manifest = Manifest(manifest_path)
        store, state = self._make_engine_state(run_dir, manifest_path, manifest)
        self._seed_intake_artifact(run_dir)
        engine = Engine(run_dir, manifest, store, state, dry_run=False)
        rc = engine.run_phase(manifest.phase("P0A-INTAKE"))
        assert rc == EXIT_OK, f"Phase should pass, got rc={rc}"
        output = run_dir / "argv_out.json"
        assert output.is_file()
        argv_data = json.loads(output.read_text())
        assert len(argv_data) >= 2
        assert argv_data[1] == str(run_dir), (
            f"argv[1]={argv_data[1]!r} expected {str(run_dir)!r}"
        )

    def test_u069_shell_injection_blocked(self, tmp_path):
        """U069-b: shell metachar in executor.cmd must NOT be interpreted."""
        from presentation_job.manifest import Manifest, Phase
        from presentation_job.phases import Engine
        from presentation_job.state import EXIT_GATE_BLOCKED

        run_dir = tmp_path / "run"; run_dir.mkdir()
        sentinel = tmp_path / "PWNED_U069"
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "manifest_version": 25,
            "phases": [{"id": "P0A-INTAKE", "order": 1, "owning_role": "test",
                        "produces_artifact": ["does_not_exist.txt"],
                        "executor": {"kind": "script",
                                     "cmd": "echo hello; touch " + str(sentinel)}}],
        }))
        manifest = Manifest(manifest_path)
        store, state = self._make_engine_state(run_dir, manifest_path, manifest)
        self._seed_intake_artifact(run_dir)
        engine = Engine(run_dir, manifest, store, state, dry_run=False)
        rc = engine.run_phase(manifest.phase("P0A-INTAKE"))
        assert rc == EXIT_GATE_BLOCKED
        assert not sentinel.exists(), f"SECURITY FAILURE: sentinel {sentinel} exists!"
        for p in state.get("phases", []):
            if p["id"] == "P0A-INTAKE":
                assert p.get("status") != "done"

    def test_u069_unbalanced_quote_raises_contract_error(self, tmp_path):
        """U069-c: unparseable executor.cmd raises PhaseExecutorContractError."""
        from presentation_job.manifest import Manifest, Phase
        from presentation_job.phases import Engine, PhaseExecutorContractError

        run_dir = tmp_path / "run"; run_dir.mkdir()
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "manifest_version": 25,
            "phases": [{"id": "P0A-INTAKE", "order": 1, "owning_role": "test",
                        "produces_artifact": ["out.txt"],
                        "executor": {"kind": "script",
                                     "cmd": "echo \"unclosed quote"}}],
        }))
        manifest = Manifest(manifest_path)
        store, state = self._make_engine_state(run_dir, manifest_path, manifest)
        self._seed_intake_artifact(run_dir)
        engine = Engine(run_dir, manifest, store, state, dry_run=False)
        with pytest.raises(PhaseExecutorContractError) as exc_info:
            engine.run_phase(manifest.phase("P0A-INTAKE"))
        assert "P0A-INTAKE" in str(exc_info.value)
        for p in state.get("phases", []):
            if p["id"] == "P0A-INTAKE":
                assert p.get("status") != "done"


# ---------------------------------------------------------------------------
# WARN_ONLY_GATES / ocr_readback contradiction: MASTER-SPEC 7.4 says an unchecked
# slide-content readback BLOCKS the job; gates.py had ocr_readback in WARN_ONLY_GATES,
# so close() routed a failing readback into the non-blocking gate_warnings list and a
# job could reach DONE with zero OCR-verified slides. These drive Engine.close() itself
# (not just Gates in isolation) to prove the observable, end-to-end behaviour.
# ---------------------------------------------------------------------------
def _seed_curated_bundle(run_dir):
    """WORK-ITEM-13 (R2/R3): Engine.close() now runs curate.curate() after the
    gates pass, and curation hard-fails (AF-BUNDLE-INCOMPLETE, exit 3) when any
    deliverable in the canonical whitelist (fix_bundle_complete.REQUIRED_KEYS)
    is missing. close() tests that only assert gate behaviour must therefore
    seed the FULL curated deliverable set, or the pass-path tests die on
    curation before DONE. The two files this family already seeds
    (PRESENTERS-SPEECH.md, presenter-teleprompter.html) are kept here for
    continuity; the other eight come from the canonical standardized
    destination names in DELIVERABLE_AUDIT_SPEC (suffix- and size-checked by
    locate_deliverable, so each is a non-empty real file).

    Wave-2 wired self_audit's magic-byte checks into Engine.close(), so a
    seeded file of plain b"x" padding now fails the audit: the .pptx/.pdf/.mp3/
    .png files must open with their real magic bytes (read from _AUDIT_SPEC),
    the html must carry a DOCTYPE marker (check_html_marker reads the first
    2000 bytes), and the mp4 must carry an ftyp box (check_mp4_ftyp scans the
    first 512 bytes). Sizes are taken from each spec's min_bytes, never
    guessed. After writing, every seeded name that has a magic_bytes entry in
    _AUDIT_SPEC is re-verified through check_magic_bytes so a future spec
    change breaks fixture authoring loudly instead of drifting silently."""
    from self_audit import _AUDIT_SPEC, check_magic_bytes

    (run_dir / "working" / "deliverables").mkdir(parents=True, exist_ok=True)
    spec_by_name = {s["standardized_dest"]: s for s in _AUDIT_SPEC}

    def _min_bytes(name: str) -> int:
        return spec_by_name[name]["min_bytes"]

    def _seed_bytes(prefix: bytes, size: int, suffix: bytes = b"") -> bytes:
        return prefix + b"x" * (size - len(prefix) - len(suffix)) + suffix

    seeded = {
        "PRESENTERS-SPEECH.md": (
            _min_bytes("PRESENTERS-SPEECH.md"),
            lambda sz: b"x" * sz,
        ),
        "presenter-teleprompter.html": (
            12000,
            lambda sz: _seed_bytes(b"<!DOCTYPE html>\n", sz),
        ),
        "DECK-FINAL.pptx": (
            _min_bytes("DECK-FINAL.pptx"),
            lambda sz: _seed_bytes(b"PK\x03\x04", sz),
        ),
        "DECK-FINAL.pdf": (
            _min_bytes("DECK-FINAL.pdf"),
            lambda sz: _seed_bytes(b"%PDF-1.4\n", sz, b"\n%%EOF\n"),
        ),
        "PRESENTER-GUIDE.pdf": (
            _min_bytes("PRESENTER-GUIDE.pdf"),
            lambda sz: _seed_bytes(b"%PDF-1.4\n", sz, b"\n%%EOF\n"),
        ),
        "PRESENTERS-SPEECH.pdf": (
            _min_bytes("PRESENTERS-SPEECH.pdf"),
            lambda sz: _seed_bytes(b"%PDF-1.4\n", sz, b"\n%%EOF\n"),
        ),
        "PRESENTERS-SPEECH-FISH-TAGGED.md": (
            _min_bytes("PRESENTERS-SPEECH-FISH-TAGGED.md"),
            lambda sz: b"x" * sz,
        ),
        "PRESENTER-AUDIO.mp3": (
            _min_bytes("PRESENTER-AUDIO.mp3"),
            lambda sz: _seed_bytes(b"ID3", sz),
        ),
        "INFOGRAPHIC.png": (
            _min_bytes("INFOGRAPHIC.png"),
            lambda sz: _seed_bytes(b"\x89PNG\r\n\x1a\n", sz),
        ),
        "WEBINAR-VIDEO.mp4": (
            _min_bytes("WEBINAR-VIDEO.mp4"),
            lambda sz: _seed_bytes(b"\x00\x00\x00\x18ftypmp42", sz),
        ),
    }
    for name, (size, factory) in seeded.items():
        path = run_dir / "working" / "deliverables" / name
        path.write_bytes(factory(size))
        spec = spec_by_name[name]
        magic = spec.get("magic_bytes")
        if magic is not None:
            ok, reason = check_magic_bytes(
                str(path), magic, spec.get("magic_offset", 0)
            )
            assert ok, f"seeded {name}: magic-byte check failed: {reason}"


class TestOCRReadbackGateBlocks:
    def _seed_other_gates_passing(self, run_dir):
        """Every gate except ocr_readback/qc satisfied, so a close() failure can only
        be attributed to the one gate each test is about."""
        _seed_curated_bundle(run_dir)
        (run_dir / "working" / "prompts").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "qc").mkdir(parents=True, exist_ok=True)
        (run_dir / "renders").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "prompts" / "slide-01.txt").write_text("p" * 9500)
        (run_dir / "working" / "checkpoints" / "media_library.json").write_text(json.dumps(
            {"ghl_folder_id": "root",
             "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"}],
             "pptx_ghl_media_id": "p9"}))
        (run_dir / "working" / "qc" / "final_qc_report.json").write_text(json.dumps({"average": 9.2}))

    def _make_engine(self, run_dir):
        from presentation_job.manifest import Manifest
        from presentation_job.phases import Engine
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps({"manifest_version": 25, "phases": []}))
        manifest = Manifest(manifest_path)
        store = StateStore(run_dir)
        state = {
            "schema_version": 1, "job_id": "ocr_gate_test",
            "run_dir": str(run_dir), "created_at": "2026-01-01T00:00:00+00:00",
            "manifest_path": str(manifest_path), "manifest_version": 25,
            "manifest_sha256": manifest.sha256, "presentation_type": "from_scratch",
            "requester": {"chat_id": "test"}, "current_phase": None,
            "phases": [], "gates": {}, "waivers": [], "events": [],
            "sent": {}, "undeliverable": [], "heartbeat": {}, "terminal": None,
        }
        store.save(state)
        return Engine(run_dir, manifest, store, state, dry_run=False)

    def test_close_blocks_on_unchecked_readback(self, tmp_path, capsys):
        """The exact scenario the contradiction describes: zero OCR-verified slides.
        close() must exit EXIT_GATE_BLOCKED, never reach DONE, and name the gate in a
        plain-language reason in the same '--close' output style as every other
        fail-closed gate."""
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        # Deliberately no renders/*.ocr.json sidecars at all: the "zero OCR-verified
        # slides" case from the bug report.
        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        assert rc == EXIT_GATE_BLOCKED, f"expected EXIT_GATE_BLOCKED, got {rc}"
        assert engine.state["terminal"] == "BLOCKED"
        assert "CANNOT CLOSE -- fail-closed gates did not pass:" in captured.err
        assert "ocr_readback" in captured.err
        assert engine.state.get("gate_warnings") is None or all(
            w.get("gate") != "ocr_readback" for w in engine.state.get("gate_warnings", [])
        ), "ocr_readback must never land in the non-blocking gate_warnings list"

    def test_close_succeeds_with_fully_checked_readback(self, tmp_path, capsys):
        """Bleed-test companion: a job whose every rendered slide really was OCR-verified
        must still close DONE. Fixing the block must not break the good path."""
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        (run_dir / "renders" / "slide-01.ocr.json").write_text(
            json.dumps({"checked": True, "matched": True}))
        (run_dir / "renders" / "slide-02.ocr.json").write_text(
            json.dumps({"checked": True, "matched": True}))
        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        assert rc == EXIT_OK, f"expected EXIT_OK, got {rc}; stderr={captured.err}"
        assert engine.state["terminal"] == "DONE"
        assert "CANNOT CLOSE" not in captured.err


# ---------------------------------------------------------------------------
# qc gate fail-open: gates.py carried `qc` in WARN_ONLY_GATES with every one of
# _qc_gate's failure branches setting "warn_only": True. close() routes any gate result
# carrying warn_only: True into the non-blocking state["gate_warnings"] list instead of
# failures -- so a job with NO working/qc/final_qc_report.json at all (the real situation
# on every run today: no phase in the manifest produces that file) could reach DONE with
# zero QC score. The department's ratified strictness decision (D10) is fail-closed: no
# close without QC >= 8.5, with a client-quoted waiver as the only bypass. These drive
# Engine.close() itself (not just Gates in isolation) to prove the observable,
# end-to-end behaviour -- the same shape as TestOCRReadbackGateBlocks above.
# ---------------------------------------------------------------------------
class TestQCGateBlocks:
    def _seed_other_gates_passing(self, run_dir):
        """Every gate except qc satisfied for real, so a close() failure can only be
        attributed to qc."""
        _seed_curated_bundle(run_dir)
        (run_dir / "working" / "prompts").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "qc").mkdir(parents=True, exist_ok=True)
        (run_dir / "renders").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "prompts" / "slide-01.txt").write_text("p" * 9500)
        (run_dir / "working" / "checkpoints" / "media_library.json").write_text(json.dumps(
            {"ghl_folder_id": "root",
             "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"}],
             "pptx_ghl_media_id": "p9"}))
        (run_dir / "renders" / "slide-01.ocr.json").write_text(
            json.dumps({"checked": True, "matched": True}))
        # Deliberately no working/qc/final_qc_report.json.

    def _make_engine(self, run_dir):
        from presentation_job.manifest import Manifest
        from presentation_job.phases import Engine
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps({"manifest_version": 25, "phases": []}))
        manifest = Manifest(manifest_path)
        store = StateStore(run_dir)
        state = {
            "schema_version": 1, "job_id": "qc_gate_test",
            "run_dir": str(run_dir), "created_at": "2026-01-01T00:00:00+00:00",
            "manifest_path": str(manifest_path), "manifest_version": 25,
            "manifest_sha256": manifest.sha256, "presentation_type": "from_scratch",
            "requester": {"chat_id": "test"}, "current_phase": None,
            "phases": [], "gates": {}, "waivers": [], "events": [],
            "sent": {}, "undeliverable": [], "heartbeat": {}, "terminal": None,
        }
        store.save(state)
        return Engine(run_dir, manifest, store, state, dry_run=False)

    def test_close_blocks_with_no_qc_report(self, tmp_path, capsys):
        """The exact scenario the fail-open bug describes: no phase ever wrote
        final_qc_report.json. close() must exit EXIT_GATE_BLOCKED, never reach DONE, and
        name the gate in the same '--close' output style as every other fail-closed gate."""
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        assert rc == EXIT_GATE_BLOCKED, f"expected EXIT_GATE_BLOCKED, got {rc}"
        assert engine.state["terminal"] == "BLOCKED"
        assert "CANNOT CLOSE -- fail-closed gates did not pass:" in captured.err
        assert "qc" in captured.err
        assert engine.state.get("gate_warnings") is None or all(
            w.get("gate") != "qc" for w in engine.state.get("gate_warnings", [])
        ), "qc must never land in the non-blocking gate_warnings list"

    def test_close_blocks_below_threshold_qc_score(self, tmp_path, capsys):
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        (run_dir / "working" / "qc" / "final_qc_report.json").write_text(
            json.dumps({"average": 6.0}))
        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        assert rc == EXIT_GATE_BLOCKED, f"expected EXIT_GATE_BLOCKED, got {rc}"
        assert engine.state["terminal"] == "BLOCKED"
        assert "qc" in captured.err

    def test_close_succeeds_with_genuine_passing_qc_report(self, tmp_path, capsys):
        """Bleed-test companion: a job with a real, passing QC score must still close
        DONE. Fixing the block must not break the good path."""
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        (run_dir / "working" / "qc" / "final_qc_report.json").write_text(
            json.dumps({"average": 9.2}))
        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        assert rc == EXIT_OK, f"expected EXIT_OK, got {rc}; stderr={captured.err}"
        assert engine.state["terminal"] == "DONE"
        assert "CANNOT CLOSE" not in captured.err

    def test_close_succeeds_with_client_quoted_qc_waiver(self, tmp_path, capsys):
        """The only sanctioned bypass: a waiver quoting the client's own recorded words.
        Must not be weakened by this fix (waivers.py is untouched)."""
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        (run_dir / "working" / "copy").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "copy" / "intake.json").write_text(json.dumps(
            {"skip_qc": "Please skip the QC check for this run, we are on a deadline."}))
        (run_dir / "waivers.json").write_text(json.dumps([
            {"rule": "qc", "source": "intake_field", "intake_field": "skip_qc",
             "client_request_quote": "skip the QC check",
             "captured_at": "2026-01-01T00:00:00Z"}]))
        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        assert rc == EXIT_OK, f"expected EXIT_OK, got {rc}; stderr={captured.err}"
        assert engine.state["terminal"] == "DONE"
        assert engine.state["gates"]["qc"]["state"] == "waived"


# ---------------------------------------------------------------------------
# P-QC-AGGREGATE end-to-end: qc_aggregate.py is the producer the fail-closed qc
# gate above was missing. These run the REAL script (subprocess, exactly what the
# manifest's script executor invokes: `python3 scripts/qc_aggregate.py --run-dir
# {run_dir} --phase-mode`) against a run dir carrying the six domain QC reports,
# then drive Engine.close() to prove the observable end-to-end behaviour: a
# flawless set of six genuine reports reaches DONE; a missing/sub-threshold/
# untrusted domain BLOCKS with EXIT_GATE_BLOCKED and names the problem; a forged
# qc waiver exits EXIT_WAIVER_INVALID; a genuine one still closes DONE.
# ---------------------------------------------------------------------------
class TestQCAggregatePhaseEndToEnd:
    def _seed_other_gates_passing(self, run_dir):
        _seed_curated_bundle(run_dir)
        (run_dir / "working" / "prompts").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "qc").mkdir(parents=True, exist_ok=True)
        (run_dir / "renders").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "prompts" / "slide-01.txt").write_text("p" * 9500)
        (run_dir / "working" / "checkpoints" / "media_library.json").write_text(json.dumps(
            {"ghl_folder_id": "root",
             "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"}],
             "pptx_ghl_media_id": "p9"}))
        (run_dir / "renders" / "slide-01.ocr.json").write_text(
            json.dumps({"checked": True, "matched": True}))

    def _genuine_domain_report(self, gate, average=9.4):
        return {"gate": gate, "average": average, "pass": average >= 8.5,
                "triggered_autofails": [],
                "qc_independence": {"graded_by": "qc-specialist-independent-reviewer",
                                    "independent": True}}

    def _genuine_priority_shift_report(self, passing=True):
        return {"schema": "priority_shift_report/v1", "gate": "AF-PRIORITY-SHIFT",
                "phase": "P-SHIFT-QC (order 7.5)", "pass": passing,
                "items": [{"item": f"item_{i}", "pass": passing, "evidence": "ok"}
                          for i in range(15)]}

    def _seed_six_domain_reports(self, run_dir, average=9.4):
        qc = run_dir / "working" / "qc"
        qc.mkdir(parents=True, exist_ok=True)
        (qc / "copy_qc_report.json").write_text(
            json.dumps(self._genuine_domain_report("Phase 1Q", average)))
        (qc / "typography_qc_report.json").write_text(
            json.dumps(self._genuine_domain_report("Phase Typography-QC", average)))
        (qc / "prompt_qc_report.json").write_text(
            json.dumps(self._genuine_domain_report("Phase Prompt-QC", average)))
        (qc / "image_qc_report.json").write_text(
            json.dumps(self._genuine_domain_report("Phase Image-QC", average)))
        (qc / "speech_qc_report.json").write_text(
            json.dumps(self._genuine_domain_report("Phase Speech-QC", average)))
        (qc / "priority_shift_report.json").write_text(
            json.dumps(self._genuine_priority_shift_report(True)))

    def _run_qc_aggregate(self, run_dir, phase_mode=True):
        """Runs the REAL qc_aggregate.py as a subprocess -- exactly the command
        the manifest's P-QC-AGGREGATE executor invokes."""
        import subprocess
        cmd = [sys.executable, str(_scripts_dir / "qc_aggregate.py"),
               "--run-dir", str(run_dir)]
        if phase_mode:
            cmd.append("--phase-mode")
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    def _make_engine(self, run_dir):
        from presentation_job.manifest import Manifest
        from presentation_job.phases import Engine
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps({"manifest_version": 25, "phases": []}))
        manifest = Manifest(manifest_path)
        store = StateStore(run_dir)
        state = {
            "schema_version": 1, "job_id": "qc_aggregate_e2e_test",
            "run_dir": str(run_dir), "created_at": "2026-01-01T00:00:00+00:00",
            "manifest_path": str(manifest_path), "manifest_version": 25,
            "manifest_sha256": manifest.sha256, "presentation_type": "from_scratch",
            "requester": {"chat_id": "test"}, "current_phase": None,
            "phases": [], "gates": {}, "waivers": [], "events": [],
            "sent": {}, "undeliverable": [], "heartbeat": {}, "terminal": None,
        }
        store.save(state)
        return Engine(run_dir, manifest, store, state, dry_run=False)

    def test_flawless_six_reports_reach_done(self, tmp_path, capsys):
        """Reproduces the QC agent's exact scenario: speech, teleprompter, a
        9,500-char prompt, a full media library, a passing OCR sidecar, and all
        six genuine domain QC reports at score 9.4. qc_aggregate.py (run for
        real, as a subprocess) must aggregate them into a passing
        final_qc_report.json, and close() must reach DONE."""
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        self._seed_six_domain_reports(run_dir, average=9.4)

        agg = self._run_qc_aggregate(run_dir)
        assert agg.returncode == 0, f"phase-mode must exit 0: {agg.stdout}{agg.stderr}"
        final = json.loads((run_dir / "working" / "qc" / "final_qc_report.json").read_text())
        assert final["pass"] is True, final
        assert final["average"] == 9.4, final

        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        print(agg.stdout)  # surfaced in the real pytest -s output for the demonstration
        assert rc == EXIT_OK, f"expected EXIT_OK, got {rc}; stderr={captured.err}"
        assert engine.state["terminal"] == "DONE"
        assert engine.state["gates"]["qc"]["state"] == "pass"
        assert engine.state["gates"]["qc"]["score"] == 9.4

    def test_missing_domain_blocks_and_names_it(self, tmp_path, capsys):
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        self._seed_six_domain_reports(run_dir)
        (run_dir / "working" / "qc" / "speech_qc_report.json").unlink()

        agg = self._run_qc_aggregate(run_dir)
        assert agg.returncode == 0  # phase-mode: mechanically written regardless of verdict

        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        assert rc == EXIT_GATE_BLOCKED, f"expected EXIT_GATE_BLOCKED, got {rc}"
        assert engine.state["terminal"] == "BLOCKED"
        assert "speech_qc_report.json" in captured.err, captured.err
        assert "P-SPEECH-QC" in captured.err, captured.err

    def test_sub_threshold_domain_blocks_non_zero(self, tmp_path, capsys):
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        self._seed_six_domain_reports(run_dir)
        (run_dir / "working" / "qc" / "image_qc_report.json").write_text(
            json.dumps(self._genuine_domain_report("Phase Image-QC", 6.0)))

        agg = self._run_qc_aggregate(run_dir)
        assert agg.returncode == 0

        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        assert rc == EXIT_GATE_BLOCKED
        assert rc != 0, "sub-threshold must exit non-zero"
        assert engine.state["terminal"] == "BLOCKED"
        assert "6.0" in captured.err

    def test_ungoverned_generator_blocks_via_existing_af_codes(self, tmp_path, capsys):
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        self._seed_six_domain_reports(run_dir)
        (run_dir / "_build_qc_report.py").write_text(
            "def score_prompt_length(text):\n"
            "    words = len(text.split())\n"
            "    return 10 if 80 <= words <= 180 else 3\n"
            "import json\n"
            "json.dump({'average': 10}, open('working/qc/rogue_qc_report.json', 'w'))\n")

        agg = self._run_qc_aggregate(run_dir)
        assert agg.returncode == 0
        final = json.loads((run_dir / "working" / "qc" / "final_qc_report.json").read_text())
        assert final["pass"] is False
        codes = {f["af_code"] for f in final["generator_guard"]["blocking"]}
        assert "AF-QC-GENERATOR-UNGOVERNED" in codes

        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        assert rc == EXIT_GATE_BLOCKED
        assert engine.state["terminal"] == "BLOCKED"
        assert "AF-QC-GENERATOR-UNGOVERNED" in captured.err, captured.err

    def test_forged_qc_waiver_exits_waiver_invalid(self, tmp_path, capsys):
        """A forged waiver (quote nobody said, attached to a real intake field) must
        exit EXIT_WAIVER_INVALID (9) -- waivers.py's existing quote-substring check,
        untouched by this change."""
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        self._seed_six_domain_reports(run_dir)
        (run_dir / "working" / "qc" / "speech_qc_report.json").unlink()  # force a real qc failure
        (run_dir / "working" / "copy").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "copy" / "intake.json").write_text(
            json.dumps({"topic": "Our Q3 sales roadmap"}))
        (run_dir / "waivers.json").write_text(json.dumps([
            {"rule": "qc", "source": "intake_field", "intake_field": "topic",
             "client_request_quote": "the client said we can skip QC entirely",
             "captured_at": "2026-01-01T00:00:00Z"}]))

        self._run_qc_aggregate(run_dir)
        engine = self._make_engine(run_dir)
        rc = engine.close()
        assert rc == EXIT_WAIVER_INVALID, f"expected exit 9, got {rc}"
        assert engine.state["terminal"] is None, \
            "an invalid waiver must not resolve the job to any terminal state"

    def test_genuine_client_quoted_waiver_still_closes_done(self, tmp_path, capsys):
        run_dir = tmp_path / "run"; run_dir.mkdir()
        self._seed_other_gates_passing(run_dir)
        self._seed_six_domain_reports(run_dir)
        (run_dir / "working" / "qc" / "speech_qc_report.json").unlink()  # force a real qc failure
        (run_dir / "working" / "copy").mkdir(parents=True, exist_ok=True)
        (run_dir / "working" / "copy" / "intake.json").write_text(json.dumps(
            {"skip_qc": "Please skip the QC check for this run, we are on a deadline."}))
        (run_dir / "waivers.json").write_text(json.dumps([
            {"rule": "qc", "source": "intake_field", "intake_field": "skip_qc",
             "client_request_quote": "skip the QC check",
             "captured_at": "2026-01-01T00:00:00Z"}]))

        self._run_qc_aggregate(run_dir)
        engine = self._make_engine(run_dir)
        rc = engine.close()
        captured = capsys.readouterr()
        assert rc == EXIT_OK, f"expected EXIT_OK, got {rc}; stderr={captured.err}"
        assert engine.state["terminal"] == "DONE"
        assert engine.state["gates"]["qc"]["state"] == "waived"

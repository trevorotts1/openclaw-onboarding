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

from presentation_job.state import StateStore, RunLock, EXIT_OK, EXIT_LOCK_HELD, EXIT_STATE_CORRUPT, EXIT_GATE_BLOCKED
from presentation_job.manifest import Manifest, Phase, PHASE_BUDGET_MINUTES, MIN_MANIFEST_VERSION, MIN_MANIFEST_PHASES
from presentation_job.manifest import _assert_manifest_current, resolve_manifest
from presentation_job.board import BoardMirror
from presentation_job.board import BoardMirror

# Override exit codes — test constants
EXIT_MANIFEST_MISMATCH = 7
EXIT_USAGE = 2


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
        canonical = _scripts_dir.parent.parent.parent.parent.parent / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if canonical.is_file():
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
        canonical = _scripts_dir.parent.parent.parent.parent.parent / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
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

        # Keep mock active for the ENTIRE test
        with mock.patch("presentation_job.board._get_cc_board", return_value=fake_cc):
            board_module._cc_board = fake_cc
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
        engine = Engine(run_dir, manifest, store, state, dry_run=False)
        with pytest.raises(PhaseExecutorContractError) as exc_info:
            engine.run_phase(manifest.phase("P0A-INTAKE"))
        assert "P0A-INTAKE" in str(exc_info.value)
        for p in state.get("phases", []):
            if p["id"] == "P0A-INTAKE":
                assert p.get("status") != "done"

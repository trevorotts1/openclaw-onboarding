"""test_b_u15_env_matrix_live_proof.py — B-U15 (crosswalk U29): "ENV-MATRIX
live proof: the ASSUMED VPS mount row + first-hour ground truth on one Mac +
one VPS + stale-env preflight."

HERMETIC, OFFLINE, no network, no Docker, no live browser, no real VPS.

This unit's BINARY acceptance (master spec, Section B.7):
  (a) VPS mount proof: `state save`, `docker compose up -d
      --force-recreate`, `state load` succeeds and the receipt records the
      mount type.
  (b) The same fixture build passes end-to-end on one Mac and one VPS with
      `durable_root()` resolving correctly on each; receipts compared.
  (c) `tests/test_env_matrix.py` green on both boxes' checkouts.
  (d) The stale-env preflight fires on a seeded stale `.env` and stays
      silent otherwise.

WHAT THIS TEST FILE PROVES OFFLINE (the repo-side MECHANISM — see each
module's docstring for the full "why"):
  (d) is fully provable offline — `stale_env_preflight()`'s inputs (is this a
      VPS, what did docker report as the container's StartedAt, what is the
      env file's mtime) are all injectable, so "fires on stale, silent
      otherwise" is a hermetic fixture test, not a live requirement.
  (a) and (b) each have a real LIVE leg (a real VPS container recreate; a
      real Mac+VPS fixture build) that CANNOT be proven from this sandbox —
      this file proves the offline MECHANISM behind each (classify/marker/
      receipt for (a); schema+comparator for (b)) is correct against fixture
      inputs, and that the live wrapper scripts refuse cleanly (never
      fabricate a pass) when no real Docker/VPS is reachable. The live round
      trips themselves are OWED to the operator's own VPS box — logged in
      ENV-MATRIX.md, never faked here.
  (c) is proven by the fact that `tests/test_env_matrix.py` is part of THIS
      suite run and passes on this checkout.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent
_TOOLS_DIR = _SKILL_DIR / "tools"
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
_MANAGER_PY = _TOOLS_DIR / "browser_manager.py"
_MANAGER_SH = _TOOLS_DIR / "browser_manager.sh"
_MOUNT_PROOF_PY = _TOOLS_DIR / "ghl_vps_mount_proof.py"
_GROUND_TRUTH_PY = _TOOLS_DIR / "ghl_env_matrix_ground_truth.py"
_LIVE_WRAPPER_SH = _SCRIPTS_DIR / "vps-mount-proof.sh"

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


def _reload_bm():
    import importlib
    import browser_manager as bm
    importlib.reload(bm)
    return bm


# ---------------------------------------------------------------------------
# (d) stale-env preflight — Python mechanism, fully hermetic
# ---------------------------------------------------------------------------
class TestStaleEnvPreflight:
    def test_silent_on_a_mac_box(self):
        """A Mac has no container to be stale relative to — must be silent
        regardless of what inspect/mtime would otherwise say."""
        bm = _reload_bm()
        msg = bm.stale_env_preflight(
            container="c1", env_path="/docker/x/.env",
            env={"GHL_LOCATION_ID": "loc"},
            isvps_fn=lambda: False,
            inspect_fn=lambda c: "2000-01-01T00:00:00.000000000Z",
            mtime_fn=lambda p: 9999999999.0,
        )
        assert msg is None

    def test_fires_on_a_seeded_stale_env(self):
        """VPS box, env mtime strictly AFTER the container's StartedAt ->
        a WARN naming the file, the container, and the fix command."""
        bm = _reload_bm()
        msg = bm.stale_env_preflight(
            container="ghl-mcp-1", env_path="/docker/proj/.env",
            env={},
            isvps_fn=lambda: True,
            inspect_fn=lambda c: "2026-07-15T00:00:00.000000000Z",
            mtime_fn=lambda p: 2000000000.0,  # 2033-ish — after the StartedAt above
        )
        assert msg is not None
        assert "/docker/proj/.env" in msg
        assert "ghl-mcp-1" in msg
        assert "force-recreate" in msg

    def test_silent_when_env_is_fresh(self):
        """VPS box, env mtime BEFORE StartedAt (a normal, non-stale restart)
        -> silent."""
        bm = _reload_bm()
        msg = bm.stale_env_preflight(
            container="c1", env_path="/docker/x/.env",
            env={},
            isvps_fn=lambda: True,
            inspect_fn=lambda c: "2026-07-15T00:00:00.000000000Z",
            mtime_fn=lambda p: 1000000000.0,  # 2001 — well before StartedAt
        )
        assert msg is None

    @pytest.mark.parametrize("inspect_ret,mtime_ret", [
        (None, 123.0),
        ("2026-07-15T00:00:00Z", None),
        (None, None),
    ])
    def test_silent_when_undeterminable_never_guesses(self, inspect_ret, mtime_ret):
        """docker inspect failed, or the env file doesn't exist, or both —
        never treated as 'stale' by default; an absence must never become a
        false-positive WARN."""
        bm = _reload_bm()
        msg = bm.stale_env_preflight(
            container="c1", env_path="/docker/x/.env", env={},
            isvps_fn=lambda: True,
            inspect_fn=lambda c: inspect_ret,
            mtime_fn=lambda p: mtime_ret,
        )
        assert msg is None

    def test_unparseable_docker_timestamp_is_silent_not_a_crash(self):
        bm = _reload_bm()
        msg = bm.stale_env_preflight(
            container="c1", env_path="/docker/x/.env", env={},
            isvps_fn=lambda: True,
            inspect_fn=lambda c: "not-a-timestamp",
            mtime_fn=lambda p: 1234.0,
        )
        assert msg is None

    def test_docker_timestamp_parser_handles_nanosecond_precision(self):
        bm = _reload_bm()
        ts = bm._parse_docker_timestamp("2026-07-15T05:20:11.123456789Z")
        assert ts is not None
        # Round-trips to the same second (sub-microsecond precision is
        # deliberately truncated — see the function's own docstring).
        import datetime
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        assert dt.year == 2026 and dt.month == 7 and dt.day == 15
        assert dt.hour == 5 and dt.minute == 20 and dt.second == 11

    def test_hostinger_env_path_matches_session_name_slug_resolution(self):
        bm = _reload_bm()
        path = bm.hostinger_env_path(env={"CLIENT_SLUG": "Acme Test Co!!"})
        assert path == "/docker/acme-test-co/.env"

    def test_real_docker_inspect_absent_binary_returns_none_not_raise(self):
        """When `docker` genuinely is not on PATH, the real (non-injected)
        inspector must fail soft, not raise."""
        bm = _reload_bm()
        env = dict(os.environ)
        env["PATH"] = "/nonexistent-bin-dir-for-this-test"
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r); import browser_manager as bm; "
             "print(bm._docker_inspect_started_at('whatever'))" % str(_TOOLS_DIR)],
            capture_output=True, text=True, env=env, timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "None"

    def test_cli_is_silent_and_exit_0_on_this_non_vps_dev_box(self):
        """End-to-end CLI proof: on THIS test box (not a real VPS), the
        --stale-env-preflight CLI prints nothing and always exits 0 — never a
        build-blocking gate."""
        result = subprocess.run(
            [sys.executable, str(_MANAGER_PY), "--stale-env-preflight"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# (d) stale-env preflight — shell-side wiring into bm_ensure (the actual
# "build-unit preflight", not a standalone function nobody calls)
# ---------------------------------------------------------------------------
def _write_stub(bindir: Path, name: str, body: str) -> None:
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / name
    stub.write_text(body, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)


def _isolated_bindir(tmp_path: Path, label: str) -> Path:
    bindir = tmp_path / f"bin-{label}"
    bindir.mkdir(parents=True, exist_ok=True)
    needed = ["bash", "sh", "cat", "mkdir", "rm", "rmdir", "sleep", "date",
              "printf", "kill", "basename", "dirname", "tr", "sed", "wc",
              "flock", "hostname"]
    import shutil
    for name in needed:
        found = shutil.which(name)
        if found and not (bindir / name).exists():
            (bindir / name).symlink_to(found)
    return bindir


class TestStaleEnvPreflightShellWiring:
    def test_bm_stale_env_preflight_function_exists_and_is_silent_by_default(self, tmp_path):
        """Sourcing the real browser_manager.sh with the REAL python3/real
        browser_manager.py (this dev box is not a VPS) must define the
        function and return silently, exit 0."""
        env = dict(
            os.environ,
            TMPDIR=str(tmp_path / "tmpdir"), HOME=str(tmp_path / "home"),
            GHL_LOCATION_ID="stalewiringfixture",
        )
        os.makedirs(env["HOME"], exist_ok=True)
        res = subprocess.run(
            ["bash", "-c", f'source "{_MANAGER_SH}"; bm_stale_env_preflight; echo "RC=$?"'],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert res.returncode == 0, res.stderr
        assert "RC=0" in res.stdout
        assert res.stderr.strip() == "" or "WARN" not in res.stderr

    def test_bm_ensure_wires_the_preflight_call_in_by_call_site(self):
        """Static proof the call site actually exists in bm_ensure (not just
        that the function is defined) — mirrors how TestBash32Safety already
        does structural source-text assertions in this same test module
        family (test_env_matrix.py)."""
        src = _MANAGER_SH.read_text(encoding="utf-8")
        ensure_start = src.index("bm_ensure() {")
        ensure_body_end = src.index("\n}\n", ensure_start)
        ensure_body = src[ensure_start:ensure_body_end]
        assert "bm_stale_env_preflight" in ensure_body, (
            "bm_ensure must call bm_stale_env_preflight — B-U15 item 3 requires "
            "folding this into the actual build-unit preflight entrypoint, not "
            "leaving it as a standalone function nobody calls."
        )

    def test_a_stubbed_warning_from_the_preflight_surfaces_through_bm_ensure(self, tmp_path):
        """Full integration proof: stub `python3` (in an isolated PATH) to
        emit a fixed WARN line for `browser_manager.py --stale-env-preflight`,
        then run the REAL `bm_ensure` (via the `ensure` verb) and assert that
        WARN line reaches stderr — proving the wiring is live, not decorative."""
        bindir = _isolated_bindir(tmp_path, "stalewarn")
        _write_stub(bindir, "agent-browser",
                    "#!/usr/bin/env bash\nprintf ''\nexit 0\n")
        marker = "WARN (stale-env preflight, B-U15): FIXTURE-STALE-ENV-MARKER"
        _write_stub(bindir, "python3",
                    "#!/usr/bin/env bash\n"
                    'if [ "$2" = "--stale-env-preflight" ] || [ "$1" = "--stale-env-preflight" ]; then\n'
                    f'  echo "{marker}"\n'
                    "  exit 0\n"
                    "fi\n"
                    "exit 0\n")
        env = dict(
            PATH=str(bindir),
            TMPDIR=str(tmp_path / "lockdir"), HOME=str(tmp_path / "home"),
            GHL_LOCATION_ID="stalewarnintegrationfixture",
            AB_MAX_SESSIONS="5", AB_LOCK_WAIT="5", AB_SESSION_TTL="5",
        )
        os.makedirs(env["HOME"], exist_ok=True)
        res = subprocess.run(
            ["bash", str(_MANAGER_SH), "ensure"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
        assert marker in res.stderr, (
            f"the stubbed preflight WARN must surface through bm_ensure's stderr.\n"
            f"stdout={res.stdout}\nstderr={res.stderr}"
        )
        assert "ENSURED" in res.stdout, "a preflight WARN must never block bm_ensure from succeeding"


# ---------------------------------------------------------------------------
# (a) VPS mount proof — classify / marker / receipt mechanism
# ---------------------------------------------------------------------------
class TestVpsMountProofMechanism:
    def test_module_selftest_passes(self):
        res = subprocess.run(
            [sys.executable, str(_MOUNT_PROOF_PY), "--selftest"],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 0, res.stdout + res.stderr

    def test_cli_pre_then_post_round_trip_writes_a_receipt_with_mount_type(self, tmp_path):
        target = tmp_path / "agent-browser"
        evidence = tmp_path / "evidence"
        res_pre = subprocess.run(
            [sys.executable, str(_MOUNT_PROOF_PY), "pre", str(target),
             "--run-id", "cli-rt-1", "--evidence-root", str(evidence), "--box-label", "test-box"],
            capture_output=True, text=True, timeout=30,
        )
        assert res_pre.returncode == 0, res_pre.stderr
        res_post = subprocess.run(
            [sys.executable, str(_MOUNT_PROOF_PY), "post", str(target),
             "--run-id", "cli-rt-1", "--evidence-root", str(evidence), "--box-label", "test-box"],
            capture_output=True, text=True, timeout=30,
        )
        assert res_post.returncode == 0, res_post.stderr
        receipt_path = evidence / "routing" / "vps-mount-receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert receipt["mount_type"] is not None
        assert receipt["survived_recreate"] is True
        assert receipt["live_leg_status"] == "complete"

    def test_cli_post_with_wrong_run_id_exits_nonzero(self, tmp_path):
        target = tmp_path / "agent-browser"
        subprocess.run(
            [sys.executable, str(_MOUNT_PROOF_PY), "pre", str(target), "--run-id", "real-id"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        res = subprocess.run(
            [sys.executable, str(_MOUNT_PROOF_PY), "post", str(target), "--run-id", "wrong-id"],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 1

    def test_classify_cli_prints_json(self, tmp_path):
        res = subprocess.run(
            [sys.executable, str(_MOUNT_PROOF_PY), "classify", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 0, res.stderr
        parsed = json.loads(res.stdout)
        assert "is_persistent" in parsed
        assert "mount_type" in parsed


class TestVpsMountProofLiveWrapperRefusesCleanly:
    """`scripts/vps-mount-proof.sh` must NEVER fabricate a live pass when no
    real Docker/VPS is reachable — it refuses loudly with a distinct exit
    code, exactly like the existing `run-selector-drift-probe.sh --live`
    pattern this unit's wrapper deliberately mirrors."""

    def test_offline_default_runs_the_selftest_and_exits_0(self):
        res = subprocess.run(
            ["bash", str(_LIVE_WRAPPER_SH)],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "OK" in res.stdout

    def test_live_mode_with_no_docker_binary_refuses_with_exit_3(self, tmp_path):
        bindir = _isolated_bindir(tmp_path, "nodocker")
        env = dict(PATH=str(bindir))
        res = subprocess.run(
            ["bash", str(_LIVE_WRAPPER_SH), "--live",
             "--path", str(tmp_path / "x"), "--run-id", "r1",
             "--compose-file", str(tmp_path / "compose.yml")],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert res.returncode == 3
        assert "REFUSE" in res.stderr
        assert "docker" in res.stderr.lower()

    def test_live_mode_missing_required_args_refuses_with_exit_64(self):
        res = subprocess.run(
            ["bash", str(_LIVE_WRAPPER_SH), "--live", "--path", "/tmp/x"],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 64

    def test_shell_script_is_bash32_safe(self):
        """Redundant with TestBash32Safety in test_env_matrix.py (it globs
        this same scripts/ dir) — asserted again here, locally, so this
        unit's own live-wrapper addition is self-evidently covered even if
        that shared parametrized test list is read in isolation."""
        res = subprocess.run(["/bin/bash", "-n", str(_LIVE_WRAPPER_SH)],
                              capture_output=True, text=True, timeout=15)
        assert res.returncode == 0, res.stderr


# ---------------------------------------------------------------------------
# (b) first-hour ground truth — receipt schema + Mac-vs-VPS comparator
# ---------------------------------------------------------------------------
class TestGroundTruthComparator:
    def test_module_selftest_passes(self):
        res = subprocess.run(
            [sys.executable, str(_GROUND_TRUTH_PY), "--selftest"],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 0, res.stdout + res.stderr

    @staticmethod
    def _fixture(**overrides) -> dict:
        base = {
            "box_label": "fixture-mac", "platform": "darwin",
            "durable_root": "/Users/fixture/.openclaw", "is_vps": False,
            "supervisor": "launchd", "run_id": "gt-1",
            "dispatch_ok": True, "build_ok": True, "verify_passed": True,
            "fab_qc_score": 9.0, "fab_qc_gate": "PASS", "receipts_total": 3,
        }
        base.update(overrides)
        return base

    def test_cli_compare_matching_pair_exits_0(self, tmp_path):
        mac = self._fixture()
        vps = self._fixture(box_label="fixture-vps", platform="linux", is_vps=True,
                             supervisor="pm2-or-systemd", durable_root="/data/.openclaw",
                             run_id="gt-2")
        mac_path = tmp_path / "mac.json"
        vps_path = tmp_path / "vps.json"
        mac_path.write_text(json.dumps(mac))
        vps_path.write_text(json.dumps(vps))
        res = subprocess.run(
            [sys.executable, str(_GROUND_TRUTH_PY), "compare", str(mac_path), str(vps_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        result = json.loads(res.stdout)
        assert result["pass"] is True

    def test_cli_compare_divergent_pair_exits_1(self, tmp_path):
        mac = self._fixture()
        # VPS receipt with a Mac-shaped durable_root — the exact false-parity
        # bug this comparator exists to catch.
        vps = self._fixture(box_label="bad-vps", platform="linux", is_vps=True,
                             supervisor="pm2-or-systemd",
                             durable_root="/Users/fixture/.openclaw", run_id="gt-3")
        mac_path = tmp_path / "mac.json"
        vps_path = tmp_path / "vps.json"
        mac_path.write_text(json.dumps(mac))
        vps_path.write_text(json.dumps(vps))
        res = subprocess.run(
            [sys.executable, str(_GROUND_TRUTH_PY), "compare", str(mac_path), str(vps_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 1
        result = json.loads(res.stdout)
        assert result["pass"] is False

    def test_cli_validate_reports_missing_fields(self, tmp_path):
        incomplete = {"box_label": "x"}
        p = tmp_path / "incomplete.json"
        p.write_text(json.dumps(incomplete))
        res = subprocess.run(
            [sys.executable, str(_GROUND_TRUTH_PY), "validate", str(p)],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 1
        assert "INVALID" in res.stderr


# ---------------------------------------------------------------------------
# (b) first-hour ground truth — the EMITTER half (`run_fixture_ground_truth`
# / `ghl_env_matrix_ground_truth.py run`): actually produces a compare()-ready
# receipt via v2_dispatcher.dispatch_one(), closing the "who writes the
# receipt this module compares" gap the comparator's own docstring names as
# out of its scope. Still OFFLINE/FIXTURE tier — the genuine live run
# (real builder/verifier against a designated GHL test location, on an
# actual Mac AND an actual VPS) remains operator-owed.
# ---------------------------------------------------------------------------

class TestGroundTruthEmitter:
    def _mod(self):
        import ghl_env_matrix_ground_truth as g
        return g

    def test_run_fixture_ground_truth_reaches_verified_and_matches_schema(self, tmp_path):
        g = self._mod()
        receipt = g.run_fixture_ground_truth(str(tmp_path), box_label="pytest-fixture-box")
        problems = g.validate_ground_truth_receipt(receipt)
        assert not problems, f"emitted receipt fails its own module's schema: {problems}"
        assert receipt["dispatch_ok"] is True
        assert receipt["build_ok"] is True
        assert receipt["verify_passed"] is True
        assert receipt["fab_qc_gate"] == "PASS"
        assert receipt["fab_qc_score"] >= g.FAB_QC_PASS_THRESHOLD
        assert receipt["receipts_total"] > 0
        assert receipt["live"] is False
        assert "FIXTURE PLACEHOLDER" in receipt["fab_qc_note"]

    def test_run_fixture_ground_truth_box_identity_is_real_not_guessed(self, tmp_path):
        """The box fields come from the REAL (unmocked) browser_manager
        primitives — proves the emitter is actually wired to durable_root()/
        is_vps()/supervisor(), not hand-typed constants."""
        g = self._mod()
        receipt = g.run_fixture_ground_truth(
            str(tmp_path),
            env={"HOME": "/Users/fixture"},
            isdir=lambda p: p == "/data/.openclaw",
        )
        assert receipt["is_vps"] is True
        assert receipt["durable_root"] == "/data/.openclaw"
        assert receipt["supervisor"] in ("launchd", "pm2-or-systemd")

    def test_run_fixture_ground_truth_default_run_id_is_unique(self, tmp_path):
        g = self._mod()
        r1 = g.run_fixture_ground_truth(str(tmp_path / "a"))
        r2 = g.run_fixture_ground_truth(str(tmp_path / "b"))
        assert r1["run_id"] != r2["run_id"]

    def test_emitted_receipt_feeds_compare_and_passes(self, tmp_path, monkeypatch):
        """End-to-end: emit a receipt, feed it straight into compare() paired
        with a synthetic VPS-side receipt, and confirm real parity checks
        pass — proves the two halves of this module are actually wired
        together, not just independently self-consistent. `supervisor()`
        reads real `sys.platform` (no injection seam), so the VPS half is
        emitted under a monkeypatched `sys.platform='linux'` — the box-id
        fields under test (durable_root/is_vps/supervisor) are exercised for
        real, just under the platform this fixture is simulating."""
        g = self._mod()
        mac_receipt = g.run_fixture_ground_truth(
            str(tmp_path / "mac"), box_label="fixture-mac",
            env={"HOME": "/Users/fixture"}, isdir=lambda p: p == "/Users/fixture/.openclaw",
        )
        monkeypatch.setattr(sys, "platform", "linux")
        vps_receipt = g.run_fixture_ground_truth(
            str(tmp_path / "vps"), box_label="fixture-vps",
            env={"HOME": "/root"}, isdir=lambda p: p == "/data/.openclaw",
        )
        result = g.compare_ground_truth(mac_receipt, vps_receipt)
        assert result["pass"] is True, result["checks"]

    def test_write_and_read_ground_truth_receipt_round_trip(self, tmp_path):
        g = self._mod()
        receipt = g.run_fixture_ground_truth(str(tmp_path), box_label="pytest-fixture")
        out = g.write_ground_truth_receipt(str(tmp_path), receipt)
        assert out == g.ground_truth_receipt_path(str(tmp_path))
        assert os.path.exists(out)
        on_disk = json.loads(Path(out).read_text(encoding="utf-8"))
        assert on_disk["run_id"] == receipt["run_id"]


class TestGroundTruthEmitterCli:
    def test_run_subcommand_writes_a_valid_receipt_and_exits_0(self, tmp_path):
        res = subprocess.run(
            [sys.executable, str(_GROUND_TRUTH_PY), "run",
             "--evidence-root", str(tmp_path), "--box-label", "pytest-cli-box"],
            capture_output=True, text=True, timeout=30,
        )
        assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
        payload = json.loads(res.stdout)
        assert payload["dispatch_ok"] is True
        receipt_file = tmp_path / "routing" / "env-matrix-ground-truth-receipt.json"
        assert receipt_file.exists()

    def test_run_then_validate_round_trip_via_subprocess(self, tmp_path):
        run_res = subprocess.run(
            [sys.executable, str(_GROUND_TRUTH_PY), "run", "--evidence-root", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert run_res.returncode == 0, run_res.stderr
        receipt_file = tmp_path / "routing" / "env-matrix-ground-truth-receipt.json"
        validate_res = subprocess.run(
            [sys.executable, str(_GROUND_TRUTH_PY), "validate", str(receipt_file)],
            capture_output=True, text=True, timeout=30,
        )
        assert validate_res.returncode == 0, validate_res.stderr
        assert validate_res.stdout.strip() == "valid"

    def test_run_subcommand_stdout_is_clean_json_despite_cc_board_noop_warning(self, tmp_path):
        """cc_board's `MISSION_CONTROL_URL unset` advisory (fired by
        dispatch_one's best-effort board mirror) must land on stderr, never
        contaminate the JSON on stdout this CLI's consumers parse."""
        res = subprocess.run(
            [sys.executable, str(_GROUND_TRUTH_PY), "run", "--evidence-root", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        json.loads(res.stdout)  # raises if stdout is not pure JSON
        assert "MISSION_CONTROL_URL" not in res.stdout

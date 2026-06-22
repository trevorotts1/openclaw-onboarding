"""Goal-B defect tests — qc-built-workflow.sh invocation contract.

Covers:
  - The script calls `caf workflows export --workflow-id <id> --out <file>`
    (not a bare positional, not a different flag name).
  - The script reads the exported file from disk (not from a pipe or inline).
  - WF-18 and WF-21 record N/A (not FAIL) on a fresh build that has no prior
    snapshot.
  - Unknown / non-mechanical WF items get REQUIRES_HUMAN_REVIEW in JSON output.

All tests are offline — a stub `caf` binary is placed on PATH so no live CLI
or GHL API is contacted.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path to the script under test
# ---------------------------------------------------------------------------

_SCRIPT = Path(__file__).parent.parent / "qc-built-workflow.sh"


def _skip_if_no_bash():
    if not Path("/bin/bash").exists() and not Path("/usr/bin/bash").exists():
        pytest.skip("bash not available")


# ---------------------------------------------------------------------------
# Fixture: build a temporary stub `caf` binary on PATH
# ---------------------------------------------------------------------------

@pytest.fixture()
def stub_caf_env(tmp_path):
    """Return an env dict with a stub `caf` on PATH.

    The stub writes a minimal JSON workflow export to --out and exits 0.
    It records the full argv to <tmp_path>/caf_argv.txt for inspection.
    """
    caf_bin = tmp_path / "caf"
    caf_bin.write_text(textwrap.dedent("""\
        #!/usr/bin/env bash
        # Record argv for assertions
        echo "$@" >> "$(dirname "$0")/caf_argv.txt"

        OUT_FILE=""
        WF_ID=""
        i=1
        while [ $i -le $# ]; do
            arg="${!i}"
            case "$arg" in
                --out)
                    i=$((i+1)); OUT_FILE="${!i}" ;;
                --workflow-id)
                    i=$((i+1)); WF_ID="${!i}" ;;
            esac
            i=$((i+1))
        done

        # Write a minimal valid workflow JSON
        if [ -n "$OUT_FILE" ]; then
            cat > "$OUT_FILE" <<'EOF'
{
  "id": "WFTEST001",
  "name": "ZHC-test-workflow",
  "status": "draft",
  "triggers": [{"id": "T1", "type": "form_submitted"}],
  "steps": [
    {"id": "A1", "type": "EMAIL", "order": 0, "targetActionId": "exit"}
  ],
  "allowMultiple": false,
  "active": false
}
EOF
        fi
        exit 0
    """))
    caf_bin.chmod(caf_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Point HOME to a fresh dir so the mac CAF_DATA path has no snapshot.
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + ":" + env.get("PATH", "")
    env["HOME"] = str(fake_home)
    env["OPENCLAW_PLATFORM"] = "mac"
    return env, tmp_path


@pytest.fixture()
def stub_caf_env_with_snapshot(tmp_path):
    """Like stub_caf_env but pre-creates a snapshot for WF-18/WF-21 PASS tests.

    The script (qc-built-workflow.sh) computes SNAPSHOT_DIR as:
      mac:  $HOME/.openclaw/tools/convert-and-flow-cli/data/snapshots
      vps:  /data/.openclaw/tools/convert-and-flow-cli/data/snapshots
    We override HOME so the mac path lands under tmp_path, then pre-seed the
    snapshot at: $HOME/.openclaw/tools/convert-and-flow-cli/data/snapshots/WFTEST001/
    """
    caf_bin = tmp_path / "caf"
    caf_bin.write_text(textwrap.dedent("""\
        #!/usr/bin/env bash
        echo "$@" >> "$(dirname "$0")/caf_argv.txt"
        OUT_FILE=""
        i=1
        while [ $i -le $# ]; do
            arg="${!i}"
            case "$arg" in
                --out) i=$((i+1)); OUT_FILE="${!i}" ;;
            esac
            i=$((i+1))
        done
        if [ -n "$OUT_FILE" ]; then
            cat > "$OUT_FILE" <<'EOF'
{
  "id": "WFTEST001",
  "name": "ZHC-test-workflow",
  "status": "draft",
  "triggers": [{"id": "T1", "type": "form_submitted"}],
  "steps": [{"id": "A1", "type": "EMAIL", "order": 0, "targetActionId": "exit"}],
  "allowMultiple": false,
  "active": false
}
EOF
        fi
        exit 0
    """))
    caf_bin.chmod(caf_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Pre-seed snapshot under the mac CAF_DATA path ($HOME-based).
    fake_home = tmp_path / "fakehome"
    snap_dir = (
        fake_home
        / ".openclaw" / "tools" / "convert-and-flow-cli" / "data"
        / "snapshots" / "WFTEST001"
    )
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "20260601T000000Z.json").write_text('{"id":"WFTEST001"}')

    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + ":" + env.get("PATH", "")
    env["HOME"] = str(fake_home)
    env["OPENCLAW_PLATFORM"] = "mac"
    return env, tmp_path


def _bash_bin() -> str:
    """Return a bash >= 4.0 binary path (needed for ^^ and declare -A)."""
    # macOS ships bash 3.2 at /bin/bash. Homebrew installs 5.x.
    for candidate in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", "/bin/bash"):
        if Path(candidate).exists():
            try:
                out = subprocess.run(
                    [candidate, "-c", 'echo "${1^^}"', "_", "ok"],
                    capture_output=True, text=True, timeout=3,
                )
                if out.returncode == 0 and "OK" in out.stdout.upper():
                    return candidate
            except Exception:
                pass
    pytest.skip("No bash >= 4 (^^ support) found on this system")


def _run_qc(args: list[str], env: dict) -> subprocess.CompletedProcess:
    """Run qc-built-workflow.sh via bash >= 4 and return the completed process."""
    _skip_if_no_bash()
    bash = _bash_bin()
    return subprocess.run(
        [bash, str(_SCRIPT)] + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )


# ---------------------------------------------------------------------------
# TEST GROUP 1: caf is called with --workflow-id and --out flags
# ---------------------------------------------------------------------------

class TestCafExportFlags:
    """The script must invoke: caf workflows export --workflow-id <id> --out <file>."""

    def test_export_called_with_workflow_id_flag(self, stub_caf_env):
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        argv_file = tmp / "caf_argv.txt"
        assert argv_file.exists(), (
            "stub caf was never called — script did not invoke caf"
        )
        argv = argv_file.read_text()
        assert "--workflow-id" in argv, (
            f"--workflow-id flag not found in caf invocation. argv: {argv!r}"
        )

    def test_export_called_with_correct_workflow_id_value(self, stub_caf_env):
        env, tmp = stub_caf_env
        _run_qc(["WFTEST001", "--json"], env)
        argv = (tmp / "caf_argv.txt").read_text()
        assert "WFTEST001" in argv, (
            f"workflow id 'WFTEST001' not passed to caf. argv: {argv!r}"
        )

    def test_export_called_with_out_flag(self, stub_caf_env):
        env, tmp = stub_caf_env
        _run_qc(["WFTEST001", "--json"], env)
        argv = (tmp / "caf_argv.txt").read_text()
        assert "--out" in argv, (
            f"--out flag not found in caf invocation. argv: {argv!r}"
        )

    def test_export_subcmd_is_workflows_export(self, stub_caf_env):
        env, tmp = stub_caf_env
        _run_qc(["WFTEST001", "--json"], env)
        argv = (tmp / "caf_argv.txt").read_text()
        assert "workflows" in argv and "export" in argv, (
            f"'workflows export' subcommand not found in caf argv. argv: {argv!r}"
        )

    def test_script_reads_out_file_from_disk(self, stub_caf_env):
        """The script must parse the file written by --out, not a pipe.

        Proof: if the script ignored --out and piped stdout instead, removing
        the file-write side of caf would produce empty output and exit 2.
        With --out writing the file, exit code is 0 (all mechanical items pass).
        """
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        # Script exits 0 when all mechanical items pass (they do with the stub)
        assert result.returncode in (0, 1), (
            f"Script should exit 0 or 1 (not 2 = prereq failure). "
            f"returncode={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        # JSON output must be parseable and contain the workflow_id
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            pytest.fail(
                f"Script output is not valid JSON. stdout={result.stdout!r}\nstderr={result.stderr}"
            )
        assert data.get("workflow_id") == "WFTEST001"

    def test_script_exits_2_when_caf_not_on_path(self, tmp_path):
        """Without caf on PATH the script must exit 2 (hard prereq failure)."""
        bash = _bash_bin()
        bash_dir = str(Path(bash).parent)
        # Build a PATH that contains bash but NOT caf (use a fresh empty tmpdir).
        env = os.environ.copy()
        # Include bash's directory so the script can execute, but NOT the
        # caller's PATH which may have caf on it.
        env["PATH"] = f"{bash_dir}:/usr/bin:/bin"
        result = _run_qc(["WFTEST001", "--json"], env)
        assert result.returncode == 2, (
            f"Expected exit 2 (caf not found). Got {result.returncode}.\n"
            f"stderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# TEST GROUP 2: WF-18 and WF-21 record N/A on fresh build
# ---------------------------------------------------------------------------

class TestWF18WF21FreshBuild:
    """WF-18 and WF-21 must be N/A (not FAIL) when no prior snapshot exists."""

    def test_wf18_is_na_on_fresh_build(self, stub_caf_env):
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        wf18 = data["items"]["WF-18"]
        assert wf18["status"] == "N/A", (
            f"WF-18 must be N/A on a fresh build (no prior snapshot). "
            f"Got status={wf18['status']!r}"
        )

    def test_wf21_is_na_on_fresh_build(self, stub_caf_env):
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        wf21 = data["items"]["WF-21"]
        assert wf21["status"] == "N/A", (
            f"WF-21 must be N/A on a fresh build (no prior snapshot). "
            f"Got status={wf21['status']!r}"
        )

    def test_fresh_build_overall_mechanical_can_pass(self, stub_caf_env):
        """N/A items must not count as mechanical failures on a fresh build."""
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        # With the stub workflow (trigger + action + correct publish), only a
        # snapshot-absent build should not force FAIL on mechanical_fail.
        # WF-18 and WF-21 being N/A means they don't increment FAIL count.
        assert data["mechanical_fail"] == 0, (
            f"N/A items must not count as mechanical failures. "
            f"mechanical_fail={data['mechanical_fail']}\nitems={data['items']}"
        )

    def test_wf18_passes_when_snapshot_exists(self, stub_caf_env_with_snapshot):
        """When a snapshot file exists, WF-18 must be PASS."""
        env, tmp = stub_caf_env_with_snapshot
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        wf18 = data["items"]["WF-18"]
        assert wf18["status"] == "PASS", (
            f"WF-18 must be PASS when snapshot exists. Got: {wf18}"
        )

    def test_wf21_passes_when_snapshot_exists(self, stub_caf_env_with_snapshot):
        """When a snapshot file exists, WF-21 must be PASS."""
        env, tmp = stub_caf_env_with_snapshot
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        wf21 = data["items"]["WF-21"]
        assert wf21["status"] == "PASS", (
            f"WF-21 must be PASS when snapshot exists. Got: {wf21}"
        )


# ---------------------------------------------------------------------------
# TEST GROUP 3: Unknown items get REQUIRES_HUMAN_REVIEW
# ---------------------------------------------------------------------------

class TestHumanReviewItems:
    """Non-mechanical WF items must always appear as REQUIRES_HUMAN_REVIEW."""

    HUMAN_ITEMS = [
        "WF-1", "WF-2", "WF-8", "WF-9", "WF-10", "WF-11",
        "WF-13", "WF-14", "WF-16", "WF-17", "WF-19", "WF-20",
    ]

    @pytest.mark.parametrize("item", HUMAN_ITEMS)
    def test_human_item_status_is_requires_human_review(self, item, stub_caf_env):
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        assert item in data["items"], f"{item} missing from JSON output"
        status = data["items"][item]["status"]
        assert status == "REQUIRES_HUMAN_REVIEW", (
            f"{item} must be REQUIRES_HUMAN_REVIEW. Got: {status!r}"
        )

    def test_human_items_do_not_increment_mechanical_fail(self, stub_caf_env):
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        # REQUIRES_HUMAN_REVIEW items are never counted in mechanical_fail
        # (the script counts FAIL, not REQUIRES_HUMAN_REVIEW).
        for item in self.HUMAN_ITEMS:
            assert data["items"][item]["status"] == "REQUIRES_HUMAN_REVIEW"
        # mechanical_fail must only reflect actual FAIL entries.
        mechanical_fail = data["mechanical_fail"]
        human_in_fail = sum(
            1 for it in self.HUMAN_ITEMS
            if data["items"].get(it, {}).get("status") == "FAIL"
        )
        assert human_in_fail == 0, (
            "REQUIRES_HUMAN_REVIEW items must not appear as FAIL. "
            f"Found: {[it for it in self.HUMAN_ITEMS if data['items'].get(it, {}).get('status') == 'FAIL']}"
        )


# ---------------------------------------------------------------------------
# TEST GROUP 4: JSON output shape
# ---------------------------------------------------------------------------

class TestJsonOutputShape:
    """--json flag must produce a well-formed JSON object with required keys."""

    def test_json_has_workflow_id_key(self, stub_caf_env):
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        assert "workflow_id" in data

    def test_json_has_items_key(self, stub_caf_env):
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        assert "items" in data

    def test_json_has_mechanical_pass_and_fail(self, stub_caf_env):
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        assert "mechanical_pass" in data
        assert "mechanical_fail" in data

    def test_json_has_rubric_with_weighted_floor(self, stub_caf_env):
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        assert "rubric" in data
        assert "weighted_floor" in data["rubric"]

    def test_json_item_has_status_observed_expected_notes(self, stub_caf_env):
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        for item_id, item_data in data["items"].items():
            for key in ("status", "observed", "expected", "notes"):
                assert key in item_data, (
                    f"Item {item_id} missing key {key!r}. Got: {item_data}"
                )

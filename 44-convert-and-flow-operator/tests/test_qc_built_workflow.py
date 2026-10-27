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
  "workflowData": {
    "templates": [
      {
        "id": "n1",
        "type": "sms",
        "name": "Send",
        "parentKey": null,
        "next": "n2",
        "attributes": {
          "body": "Test message",
          "fromNumber": "+15555550100"
        }
      },
      {
        "id": "n2",
        "type": "end",
        "name": "Finish",
        "parentKey": "n1"
      }
    ]
  },
  "triggers": [{"id": "T1", "type": "form_submitted", "targetActionId": "n1"}],
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
  "workflowData": {
    "templates": [
      {
        "id": "n1",
        "type": "sms",
        "name": "Send",
        "parentKey": null,
        "next": "n2",
        "attributes": {
          "body": "Test message",
          "fromNumber": "+15555550100"
        }
      },
      {
        "id": "n2",
        "type": "end",
        "name": "Finish",
        "parentKey": "n1"
      }
    ]
  },
  "triggers": [{"id": "T1", "type": "form_submitted", "targetActionId": "n1"}],
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


@pytest.fixture()
def stub_caf_with_custom_export(tmp_path):
    """Factory fixture: write a stub `caf` that exports a caller-supplied
    workflow object, so WF-7 can be exercised against arbitrary step types.

    Usage: env, tmp = stub_caf_with_custom_export({"steps": [...]})
    """
    def _make(export_obj: dict):
        caf_bin = tmp_path / "caf"
        payload = json.dumps(export_obj)
        assert "EOF_WF_EXPORT" not in payload
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
                cat > "$OUT_FILE" <<'EOF_WF_EXPORT'
%s
EOF_WF_EXPORT
            fi
            exit 0
        """) % payload)
        caf_bin.chmod(caf_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        fake_home = tmp_path / "fakehome"
        fake_home.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["PATH"] = str(tmp_path) + ":" + env.get("PATH", "")
        env["HOME"] = str(fake_home)
        env["OPENCLAW_PLATFORM"] = "mac"
        return env, tmp_path

    return _make


def _builder_verified_actions() -> list[str]:
    """Read VERIFIED_ACTIONS from the engine builder (the source the QC
    script derives its action types from)."""
    import re

    builder = (
        Path(__file__).parent.parent
        / "tools" / "engine" / "cli_anything" / "gohighlevel"
        / "utils" / "workflow_builder.py"
    )
    src = builder.read_text(encoding="utf-8")
    match = re.search(
        r"VERIFIED_ACTIONS\s*=\s*frozenset\(\s*\[(.*?)\]\s*\)",
        src, re.S)
    assert match, "VERIFIED_ACTIONS not found in workflow_builder.py"
    return [t for t in re.findall(r'["\']([^"\']+)["\']', match.group(1)) if t]


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
        # With the stub export the graph has no templates, so WF-23 is UNVERIFIED
        # and the script must return 2 (never 0) — UNVERIFIED is not a pass.
        assert result.returncode in (0, 1, 2), (
            f"Script should exit 0, 1, or 2 (2 = unverified graph or prereq). "
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

    def test_wf18_fails_without_a_dependency_manifest(self, stub_caf_env):
        """WF-18 is the dependency-manifest gate. No manifest is a FAIL, not N/A:
        a snapshot proves reversibility (WF-21) and nothing about whether the
        tags/fields/calendars the export references exist."""
        env, tmp = stub_caf_env
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        wf18 = data["items"]["WF-18"]
        assert wf18["status"] == "FAIL", (
            f"WF-18 must FAIL when no --deps manifest is supplied. Got: {wf18}"
        )
        assert "manifest" in (wf18["observed"] + wf18["notes"]).lower(), (
            f"WF-18 must name the missing manifest. Got: {wf18}"
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
        """With a dependency manifest supplied, nothing mechanical must fail.

        WF-21 stays N/A on a first-time build (no prior state to snapshot) and
        N/A items still do not count as failures."""
        env, tmp = stub_caf_env
        manifest = tmp / "deps.json"
        manifest.write_text("{}", encoding="utf-8")
        result = _run_qc(["WFTEST001", "--deps", str(manifest), "--json"], env)
        data = json.loads(result.stdout)
        assert data["items"]["WF-21"]["status"] == "N/A", (
            f"WF-21 must stay N/A on a fresh build. Got: {data['items']['WF-21']}"
        )
        assert data["items"]["WF-18"]["status"] == "PASS", (
            f"an empty manifest with no referenced dependencies must PASS WF-18. "
            f"Got: {data['items']['WF-18']}"
        )
        assert data["mechanical_fail"] == 0, (
            f"mechanical_fail must be 0 with a manifest supplied. "
            f"mechanical_fail={data['mechanical_fail']}\nitems={data['items']}"
        )

    def test_snapshot_does_not_satisfy_wf18(self, stub_caf_env_with_snapshot):
        """The D-4 regression: a snapshot must never satisfy the dependency gate.

        Before the fix this exact fixture made WF-18 PASS with the observed text
        'dependencies_pre_existed_or_snapshot_present' — a reversibility check
        standing in for a dependency check."""
        env, tmp = stub_caf_env_with_snapshot
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        assert data["items"]["WF-21"]["status"] == "PASS", (
            f"WF-21 must PASS when a snapshot exists. Got: {data['items']['WF-21']}"
        )
        wf18 = data["items"]["WF-18"]
        assert wf18["status"] == "FAIL", (
            f"a snapshot must NOT satisfy WF-18; the dependency gate needs a "
            f"manifest. Got: {wf18}"
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


# ---------------------------------------------------------------------------
# TEST GROUP 5: WF-7 action-node recognition (valid-node + invalid-node tests)
# ---------------------------------------------------------------------------
# Regression background: the original WF-7 grep recognised only 12 legacy
# uppercase names (SMS|EMAIL|WAIT|IF_ELSE|ADD_TAG|REMOVE_TAG|UPDATE_CONTACT|
# WEBHOOK|CREATE_TASK|CREATE_NOTE|REMOVE_FROM_WORKFLOW|END). The builder's
# VERIFIED_ACTIONS uses GHL's snake_case types — add_contact_tag, for example,
# matched none of them, so a tag-only build reported 0 action nodes and WF-7
# failed. The documented route-around (inserting a WAIT node) masked the bug.
# The fix derives the recognition list from the builder's VERIFIED_ACTIONS.

def _stub_caf_env_with_export(tmp_path, export_json: str):
    """stub_caf_env variant whose caf writes the given export JSON."""
    caf_bin = tmp_path / "caf"
    caf_bin.write_text(textwrap.dedent("""\
        #!/usr/bin/env bash
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
            cat > "$OUT_FILE" <<'EXPORT_EOF'
        """ + export_json + """
EXPORT_EOF
        fi
        exit 0
    """))
    caf_bin.chmod(caf_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + ":" + env.get("PATH", "")
    env["HOME"] = str(fake_home)
    env["OPENCLAW_PLATFORM"] = "mac"
    return env, tmp_path


def _export_with_steps(steps: list) -> str:
    return json.dumps(
        {
            "id": "WFTEST005",
            "name": "ZHC-wf7-node-test",
            "status": "draft",
            "triggers": [{"id": "T1", "type": "form_submitted"}],
            "steps": steps,
            "allowMultiple": False,
            "active": False,
        }
    )


class TestWF7ValidNodeRecognition:
    """Valid-node tests: every builder VERIFIED_ACTIONS type must be counted."""

    @pytest.mark.parametrize(
        "step_type",
        [
            "add_contact_tag",        # the regression case (was invisible)
            "remove_contact_tag",     # was invisible
            "update_contact_field",
            "create_update_contact",
            "webhook",
            "custom_webhook",
            "custom_code",
            "sms",                    # lowercase GHL spelling
            "wait",                   # recognised; no longer REQUIRED
        ],
    )
    def test_verified_action_type_counts_as_action_node(self, step_type, tmp_path):
        env, _ = _stub_caf_env_with_export(
            tmp_path, _export_with_steps([{"id": "A1", "type": step_type}])
        )
        result = _run_qc(["WFTEST005", "--json"], env)
        data = json.loads(result.stdout)
        assert data["items"]["WF-7"]["status"] == "PASS", (
            f"WF-7 must PASS for builder-verified action type {step_type!r}. "
            f"Got: {data['items']['WF-7']}"
        )

    @pytest.mark.parametrize("legacy_type", ["SMS", "END", "EMAIL"])
    def test_legacy_uppercase_names_still_recognized(self, legacy_type, tmp_path):
        """Back-compat: old export shapes with uppercase types keep passing."""
        env, _ = _stub_caf_env_with_export(
            tmp_path, _export_with_steps([{"id": "A1", "type": legacy_type}])
        )
        result = _run_qc(["WFTEST005", "--json"], env)
        data = json.loads(result.stdout)
        assert data["items"]["WF-7"]["status"] == "PASS", (
            f"WF-7 must keep recognising legacy name {legacy_type!r}. "
            f"Got: {data['items']['WF-7']}"
        )

    def test_add_contact_tag_only_workflow_passes_without_wait_node(self, tmp_path):
        """The regression scenario itself: a build whose only action node is
        add_contact_tag must pass WF-7 WITHOUT any WAIT node (the old
        route-around is no longer necessary and is not a fix)."""
        export = json.loads(_export_with_steps(
            [{"id": "A1", "type": "add_contact_tag", "tag": "ZHC-wf7-test"}]
        ))
        export["workflowData"] = {
            "templates": [
                {"id": "A1", "type": "add_contact_tag", "parentKey": None,
                 "next": "n2"},
                {"id": "n2", "type": "end", "parentKey": "A1"},
            ]
        }
        export["triggers"] = [
            {"id": "T1", "type": "form_submitted", "targetActionId": "A1"}
        ]
        env, _ = _stub_caf_env_with_export(tmp_path, json.dumps(export))
        manifest = tmp_path / "deps.json"
        manifest.write_text('{"tags": ["ZHC-wf7-test"]}', encoding="utf-8")
        result = _run_qc(["WFTEST005", "--deps", str(manifest), "--json"], env)
        data = json.loads(result.stdout)
        assert data["items"]["WF-7"]["status"] == "PASS", (
            f"Tag-only build must pass WF-7 with no wait node. Got: {data['items']['WF-7']}"
        )
        assert data["mechanical_fail"] == 0, (
            f"Tag-only build must have zero mechanical failures. "
            f"items={data['items']}"
        )


class TestWF7InvalidNodeRejection:
    """Invalid-node tests: exports with no recognisable action node must FAIL."""

    def test_trigger_only_export_fails_wf7(self, tmp_path):
        env, _ = _stub_caf_env_with_export(
            tmp_path,
            json.dumps(
                {
                    "id": "WFTEST006",
                    "name": "ZHC-wf7-no-action",
                    "status": "draft",
                    "triggers": [{"id": "T1", "type": "form_submitted"}],
                    "steps": [],
                    "allowMultiple": False,
                    "active": False,
                }
            ),
        )
        result = _run_qc(["WFTEST006", "--json"], env)
        data = json.loads(result.stdout)
        assert data["items"]["WF-7"]["status"] == "FAIL", (
            f"A trigger-only export must FAIL WF-7. Got: {data['items']['WF-7']}"
        )

    def test_unknown_type_only_export_fails_wf7(self, tmp_path):
        """A step whose type is not a verified GHL action must not be counted."""
        env, _ = _stub_caf_env_with_export(
            tmp_path,
            _export_with_steps([{"id": "B1", "type": "totally_bogus_action"}]),
        )
        result = _run_qc(["WFTEST006", "--json"], env)
        data = json.loads(result.stdout)
        assert data["items"]["WF-7"]["status"] == "FAIL", (
            f"Unknown step types must not satisfy WF-7. Got: {data['items']['WF-7']}"
        )


class TestWF7BuilderFallback:
    """When workflow_builder.py is absent, the inline fallback list must still
    recognise every VERIFIED action (recognition can never regress to the old
    12-name list)."""

    def test_fallback_recognises_add_contact_tag_without_builder_file(self, tmp_path):
        iso_root = tmp_path / "iso-skill"
        iso_root.mkdir()
        iso_script = iso_root / "qc-built-workflow.sh"
        iso_script.write_text(_SCRIPT.read_text())
        assert not (iso_root / "tools").exists(), "iso dir must not contain the engine"

        env, _ = _stub_caf_env_with_export(
            tmp_path,
            _export_with_steps([{"id": "A1", "type": "add_contact_tag"}]),
        )
        result = _run_qc_with_script(str(iso_script), ["WFTEST007", "--json"], env)
        data = json.loads(result.stdout)
        assert data["items"]["WF-7"]["status"] == "PASS", (
            "Inline fallback must still count add_contact_tag without the "
            f"builder file. Got: {data['items']['WF-7']}"
        )


def _run_qc_with_script(script_path: str, args: list, env: dict) -> subprocess.CompletedProcess:
    """_run_qc bound to an arbitrary script path (for the fallback test)."""
    _skip_if_no_bash()
    bash = _bash_bin()
    return subprocess.run(
        [bash, script_path] + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )


# ---------------------------------------------------------------------------
# TEST GROUP 5: WF-7 recognises every type the builder can emit
# ---------------------------------------------------------------------------

class TestWF7ActionTypeDerivation:
    """WF-7's action-type set must come from the builder's VERIFIED_ACTIONS.

    Regression pinned: the old hand-written regex omitted add_contact_tag —
    a node the builder legitimately emits — so a correct build got WF-7 FAIL.
    Unknown types must still FAIL (the fix must not become a wildcard).
    """

    @staticmethod
    def _export(step_types: list[str]) -> dict:
        return {
            "id": "WFTEST001",
            "name": "ZHC-test-workflow",
            "status": "draft",
            "triggers": [{"id": "T1", "type": "form_submitted"}],
            "steps": [
                {"id": f"A{i}", "type": t, "order": i,
                 "targetActionId": "exit"}
                for i, t in enumerate(step_types)
            ],
            "allowMultiple": False,
            "active": False,
        }

    def test_wf7_passes_for_add_contact_tag(self, stub_caf_with_custom_export):
        env, tmp = stub_caf_with_custom_export(self._export(["add_contact_tag"]))
        manifest = tmp / "deps.json"
        manifest.write_text("{}", encoding="utf-8")
        result = _run_qc(["WFTEST001", "--deps", str(manifest), "--json"], env)
        data = json.loads(result.stdout)
        wf7 = data["items"]["WF-7"]
        assert wf7["status"] == "PASS", (
            f"add_contact_tag is a VERIFIED_ACTIONS type and must PASS WF-7. "
            f"Got: {wf7}"
        )
        assert result.returncode != 0, (
            f"WF-7 itself passes, but the export carries no graph templates and no "
            f"trigger link, so WF-23 is UNVERIFIED and WF-24 fails as "
            f"trigger_evidence_absent; overall must never be 0. "
            f"Got {result.returncode}\nstdout={result.stdout}"
        )

    def test_wf7_fails_for_unknown_action_type(
            self, stub_caf_with_custom_export):
        env, tmp = stub_caf_with_custom_export(self._export(["MAGIC_BEAM"]))
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        wf7 = data["items"]["WF-7"]
        assert wf7["status"] == "FAIL", (
            f"an unknown action type must still FAIL WF-7. Got: {wf7}"
        )
        assert result.returncode == 1, (
            f"WF-7 FAIL must exit 1. Got {result.returncode}\n"
            f"stdout={result.stdout}"
        )

    def test_wf7_rejects_a_verified_prefix_with_unknown_suffix(
            self, stub_caf_with_custom_export):
        """Matching is exact: 'add_contact_tag_extra' is NOT a verified type."""
        env, tmp = stub_caf_with_custom_export(
            self._export(["add_contact_tag_extra"]))
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        assert data["items"]["WF-7"]["status"] == "FAIL", (
            f"an unknown suffix on a known prefix must FAIL WF-7. "
            f"Got: {data['items']['WF-7']}"
        )
        assert result.returncode == 1

    def test_wf7_recognises_every_verified_action(self,
                                                  stub_caf_with_custom_export):
        types = _builder_verified_actions()
        assert types, "builder advertises no VERIFIED_ACTIONS"
        env, tmp = stub_caf_with_custom_export(self._export(types))
        result = _run_qc(["WFTEST001", "--json"], env)
        data = json.loads(result.stdout)
        wf7 = data["items"]["WF-7"]
        assert wf7["status"] == "PASS", (
            f"every VERIFIED_ACTIONS type must be recognised by WF-7. Got: {wf7}"
        )
        assert wf7["observed"].startswith(f"{len(types)}_"), (
            f"expected all {len(types)} builder types counted, got: "
            f"{wf7['observed']}"
        )


def test_wf21_fails_on_an_empty_snapshot(stub_caf_env_with_snapshot):
    """A zero-byte snapshot restores nothing, so its presence is not
    reversibility. The old gate matched the filename and never measured size."""
    env, tmp = stub_caf_env_with_snapshot
    snap = (
        tmp / "fakehome" / ".openclaw" / "tools" / "convert-and-flow-cli"
        / "data" / "snapshots" / "WFTEST001" / "20260601T000000Z.json"
    )
    assert snap.is_file(), "fixture did not seed the snapshot this test empties"
    snap.write_text("")

    result = _run_qc(["WFTEST001", "--json"], env)
    wf21 = json.loads(result.stdout)["items"]["WF-21"]
    assert wf21["status"] == "FAIL", (
        "an empty snapshot must FAIL rather than record reversibility; got %r"
        % (wf21,)
    )
    assert "snapshot_empty" in wf21["observed"] + wf21["notes"], wf21
def test_export_temp_template_is_portable(tmp_path, monkeypatch):
    """The export temp file must use a mktemp template that both BSD and GNU accept.

    BSD mktemp requires the Xs to be the LAST characters of the template. With a
    suffix after them it creates that literal path instead of a unique one, so the
    first export succeeds and every later one dies with 'File exists'. This test
    runs the real template twice and requires two distinct files.
    """
    import re
    script = (Path(__file__).resolve().parent.parent / "qc-built-workflow.sh").read_text()
    m = re.search(r'mktemp\s+"([^"]+)"', script)
    assert m, "no quoted mktemp template found in qc-built-workflow.sh"
    template = m.group(1).replace("${TMPDIR:-/tmp}", str(tmp_path))
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    first = subprocess.run(["mktemp", template], capture_output=True, text=True)
    second = subprocess.run(["mktemp", template], capture_output=True, text=True)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, (
        "second mktemp call failed - the template is not portable: " + second.stderr
    )
    assert first.stdout.strip() != second.stdout.strip(), "mktemp returned the same path twice"

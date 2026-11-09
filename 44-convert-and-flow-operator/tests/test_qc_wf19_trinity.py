import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_QC = ROOT / "qc-built-workflow.sh"
SOURCE_VALIDATOR = ROOT / "tools" / "validate_graph.py"


def _linear_export():
    return {
        "targetActionId": "n1",
        "workflowData": {
            "templates": [
                {
                    "id": "n1",
                    "type": "sms",
                    "name": "Send",
                    "parentKey": None,
                    "next": "n2",
                    "attributes": {
                        "body": "Test message",
                        "fromNumber": "+15555550100",
                    },
                },
                {
                    "id": "n2",
                    "type": "end",
                    "name": "Finish",
                    "parentKey": "n1",
                    "next": None,
                },
            ]
        },
    }


def _setup(tmp_path, *, slug_exit=0, bare_exit=0, slug_output="TRINITY COMPLETE"):
    skill_dir = tmp_path / "44-convert-and-flow-operator"
    skill_dir.mkdir()
    script = skill_dir / "qc-built-workflow.sh"
    shutil.copy2(SOURCE_QC, script)

    validator_dir = skill_dir / "tools"
    validator_dir.mkdir()
    shutil.copy2(SOURCE_VALIDATOR, validator_dir / "validate_graph.py")

    trinity_dir = tmp_path / "38-conversational-ai-system" / "scripts"
    trinity_dir.mkdir(parents=True)
    trinity_log = tmp_path / "trinity-argv.log"
    trinity = trinity_dir / "qc-trinity-registry.sh"
    trinity.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        'printf "%s\\n" "$@" >> "$TRINITY_LOG"\n'
        'has_slug=0\n'
        'for arg in "$@"; do [[ "$arg" == "--slug" ]] && has_slug=1; done\n'
        'if [[ "$has_slug" -eq 1 ]]; then\n'
        '  if [[ "${TRINITY_UNKNOWN_OPTION:-0}" == "1" ]]; then\n'
        '    echo "unknown option --slug"\n'
        '    exit "${TRINITY_EXIT_SLUG:-3}"\n'
        '  fi\n'
        '  echo "${TRINITY_SLUG_OUTPUT:-TRINITY COMPLETE}"\n'
        '  exit "${TRINITY_EXIT_SLUG:-0}"\n'
        "fi\n"
        'echo "${TRINITY_BARE_OUTPUT:-TRINITY COMPLETE}"\n'
        'exit "${TRINITY_EXIT_BARE:-0}"\n',
        encoding="utf-8",
    )
    trinity.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixture = tmp_path / "export.json"
    fixture.write_text(json.dumps(_linear_export()), encoding="utf-8")

    caf = bin_dir / "caf"
    caf.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        '[[ "$1" == workflows && "$2" == export ]]\n'
        'while (($#)); do\n'
        '  if [[ "$1" == --out ]]; then cp "$QC_FIXTURE" "$2"; exit 0; fi\n'
        "  shift\n"
        "done\n"
        "exit 2\n",
        encoding="utf-8",
    )
    caf.chmod(0o755)

    env = os.environ.copy()
    env.update({
        "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
        "HOME": str(home),
        "OPENCLAW_PLATFORM": "mac",
        "QC_FIXTURE": str(fixture),
        "TRINITY_LOG": str(trinity_log),
        "TRINITY_EXIT_SLUG": str(slug_exit),
        "TRINITY_EXIT_BARE": str(bare_exit),
        "TRINITY_SLUG_OUTPUT": slug_output,
    })
    return script, env, trinity_log


def _run(tmp_path, *, args, slug_exit=0, bare_exit=0,
         slug_output="TRINITY COMPLETE", unknown_option=False):
    script, env, trinity_log = _setup(
        tmp_path,
        slug_exit=slug_exit,
        bare_exit=bare_exit,
        slug_output=slug_output,
    )
    if unknown_option:
        env["TRINITY_UNKNOWN_OPTION"] = "1"

    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps({"playbook_slug": "acme-closer"}),
        encoding="utf-8",
    )

    command = ["bash", str(script), "WFTEST019"] + list(args)
    result = subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result, trinity_log, handoff


def _wf19(result):
    assert result.stdout, result.stderr
    return json.loads(result.stdout)["items"]["WF-19"]


def _scope_text(item):
    return item["observed"] + " " + item["notes"]


def _logged_args(log):
    return log.read_text(encoding="utf-8").splitlines()


def test_handoff_scopes_trinity_to_playbook_slug(tmp_path):
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps({"playbook_slug": "acme-closer"}),
        encoding="utf-8",
    )
    result, log, _ = _run(
        tmp_path,
        args=["--conversational", "--handoff", str(handoff), "--json"],
        slug_exit=0,
    )
    item = _wf19(result)
    assert item["status"] == "PASS"
    logged = _logged_args(log)
    assert "--slug" in logged
    assert "acme-closer" in logged
    assert "--json" in logged
    assert "slug=acme-closer" in item["observed"]


def test_no_handoff_records_registry_wide_scope(tmp_path):
    result, log, _ = _run(
        tmp_path,
        args=["--conversational", "--json"],
        bare_exit=0,
    )
    item = _wf19(result)
    assert item["status"] == "PASS"
    assert "registry-wide (no handoff)" in _scope_text(item)
    assert "--slug" not in _logged_args(log)


def test_rejected_slug_option_falls_back_to_registry_wide(tmp_path):
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps({"playbook_slug": "acme-closer"}),
        encoding="utf-8",
    )
    result, log, _ = _run(
        tmp_path,
        args=["--conversational", "--handoff", str(handoff), "--json"],
        slug_exit=3,
        bare_exit=0,
        unknown_option=True,
    )
    item = _wf19(result)
    assert item["status"] == "PASS"
    assert "fallback: qc-trinity-registry.sh rejected --slug" in _scope_text(item)
    logged = _logged_args(log)
    assert "--slug" in logged
    assert "acme-closer" in logged
    assert "--json" in logged


def test_slug_scoped_trinity_failure_fails_wf19(tmp_path):
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps({"playbook_slug": "acme-closer"}),
        encoding="utf-8",
    )
    result, log, _ = _run(
        tmp_path,
        args=["--conversational", "--handoff", str(handoff), "--json"],
        slug_exit=2,
        bare_exit=0,
        slug_output="TRINITY INCOMPLETE",
    )
    item = _wf19(result)
    assert item["status"] == "FAIL"
    assert "trinity_incomplete_exit_2" in item["observed"]
    assert "acme-closer" in item["notes"]
    logged = _logged_args(log)
    assert "--slug" in logged
    assert "acme-closer" in logged
    assert "--json" in logged

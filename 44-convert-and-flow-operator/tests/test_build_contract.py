import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_graph.py"


def _contract():
    return {
        "playbook_structure_hash": "sha256:abc123",
        "tags": {"applies": ["tag-one", "tag-two"]},
        "fields": [{"name": "email"}],
        "calendars": [{"id": "calendar-one"}],
        "pipeline": {"stages": [{"name": "Qualified"}]},
        "acceptance": {
            "must_pass": [
                "tags_exist",
                "fields_exist",
                "calendars_exist",
                "pipeline_stages_exist",
            ]
        },
    }


def _manifest():
    return {
        "tags": ["tag-one", "tag-two"],
        "custom_fields": ["email"],
        "calendars": ["calendar-one"],
        "pipelines": ["Qualified"],
    }


def _run(args):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "deps"] + list(args),
        capture_output=True,
        text=True,
        check=False,
    )


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _report(result):
    assert result.stdout, result.stderr
    return json.loads(result.stdout)


def test_missing_contract_returns_absolute_expected_path(tmp_path):
    result = _run([
        "--build-contract", "acme",
        "--master-files", str(tmp_path),
    ])
    report = _report(result)
    expected_suffix = "/conversation-workflows/acme--build-contract.json"
    assert result.returncode == 2
    assert report["verdict"] == "UNVERIFIED"
    assert report["contract_path"].endswith(expected_suffix)
    assert os.path.isabs(report["contract_path"])
    assert report["contract_path"] in result.stderr


def test_slug_resolution_and_manifest_cover_all_declared_kinds(tmp_path):
    _write_json(
        tmp_path / "conversation-workflows" / "acme--build-contract.json",
        _contract(),
    )
    manifest = _write_json(tmp_path / "manifest.json", _manifest())
    result = _run([
        "--build-contract", "acme",
        "--master-files", str(tmp_path),
        "--deps", str(manifest),
    ])
    report = _report(result)
    assert result.returncode == 0
    assert report["verdict"] == "PASS"
    assert {entry["kind"] for entry in report["present"]} == {
        "tags", "custom_fields", "calendars", "pipelines"
    }
    assert report["missing"] == []


def test_unreachable_declared_entry_fails(tmp_path):
    _write_json(
        tmp_path / "conversation-workflows" / "acme--build-contract.json",
        _contract(),
    )
    manifest_data = _manifest()
    manifest_data["tags"].remove("tag-two")
    manifest = _write_json(tmp_path / "manifest.json", manifest_data)
    result = _run([
        "--build-contract", "acme",
        "--master-files", str(tmp_path),
        "--deps", str(manifest),
    ])
    report = _report(result)
    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    assert {"kind": "tags", "name": "tag-two"} in report["missing"]


def test_schema_errors_fail_contract_validation(tmp_path):
    contract = _contract()
    del contract["pipeline"]
    contract["playbook_structure_hash"] = ""
    contract["tags"]["applies"] = "tag-one"
    contract_path = _write_json(tmp_path / "broken.json", contract)
    manifest = _write_json(tmp_path / "manifest.json", _manifest())
    result = _run([
        "--build-contract", str(contract_path),
        "--deps", str(manifest),
    ])
    report = _report(result)
    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    errors = report["schema_errors"]
    assert errors
    assert any("pipeline" in error for error in errors)
    assert any("playbook_structure_hash" in error for error in errors)
    assert any("tags.applies" in error for error in errors)


def test_missing_manifest_marks_reachability_unverified(tmp_path):
    contract_path = _write_json(tmp_path / "valid.json", _contract())
    result = _run(["--build-contract", str(contract_path)])
    report = _report(result)
    assert result.returncode == 2
    assert report["verdict"] == "UNVERIFIED"
    assert "reachability" in report["reason"]
    assert report["present"] == []
    assert report["missing"] == []


def test_literal_contract_path_works_like_slug(tmp_path):
    contract_path = _write_json(
        tmp_path / "conversation-workflows" / "acme--build-contract.json",
        _contract(),
    )
    manifest = _write_json(tmp_path / "manifest.json", _manifest())
    result = _run([
        "--build-contract", str(contract_path),
        "--deps", str(manifest),
    ])
    report = _report(result)
    assert result.returncode == 0
    assert report["verdict"] == "PASS"
    assert report["contract_path"] == str(contract_path.resolve())


def test_empty_must_pass_fails(tmp_path):
    contract = _contract()
    contract["acceptance"] = {"must_pass": []}
    contract_path = _write_json(tmp_path / "empty-must-pass.json", contract)
    manifest = _write_json(tmp_path / "manifest.json", _manifest())
    result = _run([
        "--build-contract", str(contract_path),
        "--deps", str(manifest),
    ])
    report = _report(result)
    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    assert "contract_must_pass_empty" in report["schema_errors"]
    assert report["reason"] == "contract_must_pass_empty"


def test_missing_acceptance_fails(tmp_path):
    contract = _contract()
    del contract["acceptance"]
    contract_path = _write_json(tmp_path / "missing-acceptance.json", contract)
    manifest = _write_json(tmp_path / "manifest.json", _manifest())
    result = _run([
        "--build-contract", str(contract_path),
        "--deps", str(manifest),
    ])
    report = _report(result)
    assert result.returncode == 1
    assert "contract_must_pass_empty" in report["schema_errors"]


def test_empty_must_pass_fails_without_manifest(tmp_path):
    contract = _contract()
    contract["acceptance"] = {"must_pass": []}
    contract_path = _write_json(tmp_path / "empty-no-manifest.json", contract)
    result = _run(["--build-contract", str(contract_path)])
    report = _report(result)
    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    assert report["reason"] == "contract_must_pass_empty"


def test_unresolved_must_pass_check_fails(tmp_path):
    contract = _contract()
    contract["acceptance"] = {"must_pass": ["tags_exist"]}
    contract["tags"] = {"applies": [], "reads": []}
    contract_path = _write_json(tmp_path / "unresolved-check.json", contract)
    manifest = _write_json(tmp_path / "manifest.json", _manifest())
    result = _run([
        "--build-contract", str(contract_path),
        "--deps", str(manifest),
    ])
    report = _report(result)
    assert result.returncode == 1
    assert "must_pass_check_unresolved:tags_exist" in report["schema_errors"]


def test_unknown_must_pass_check_fails(tmp_path):
    contract = _contract()
    contract["acceptance"] = {"must_pass": ["not_a_real_check"]}
    contract_path = _write_json(tmp_path / "unknown-check.json", contract)
    manifest = _write_json(tmp_path / "manifest.json", _manifest())
    result = _run([
        "--build-contract", str(contract_path),
        "--deps", str(manifest),
    ])
    report = _report(result)
    assert result.returncode == 1
    assert "unknown_must_pass_check:not_a_real_check" in report["schema_errors"]

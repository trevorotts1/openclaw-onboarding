"""S44-47: `workflows build --from-automation-build` refuses to write without a verified PLAN MODE record.

PLAN MODE (the client's publish and re-entry answers, minted by the approval flow) used to be
checked only after the build, by qc-built-workflow.sh. The build command now demands the run file
and verifies it BEFORE any client is created, so the rule has an enforcement point ahead of the write.

Mock-only: no network, no credentials. Run:
    python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_build_requires_plan_mode.py -q
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel import gohighlevel_cli as cli_mod  # noqa: E402
from cli_anything.gohighlevel.gohighlevel_cli import cli  # noqa: E402
from cli_anything.gohighlevel.utils import workflow_builder as wb  # noqa: E402

_spec = importlib.util.spec_from_file_location("wp07_build_from_automation", str(HERE / "test_build_from_automation.py"))
_base = importlib.util.module_from_spec(_spec)
sys.modules["wp07_build_from_automation"] = _base
_spec.loader.exec_module(_base)
ready_document, LOC = _base.ready_document, _base.LOC

REFUSAL = "REFUSED: PLAN MODE record missing or unverified"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for key, value in {"CAF_DATA_DIR": str(tmp_path), "CAF_ALLOWED_LOCATION_IDS": LOC,
                       "CAF_APPROVAL_TOKEN": "t", "GHL_API_KEY": "fake-pit-token",
                       "GHL_LOCATION_ID": LOC}.items():
        monkeypatch.setenv(key, value)
    for key in ("CAF_DRY_RUN", "CAF_BUILD_JOURNAL", "MISSION_CONTROL_URL", "MC_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)


class Authority:
    """The approval authority: mints exactly one plan approval."""
    calls: list = []

    @classmethod
    def verify(cls, approval_id, kind, plan_hash, scope, **kw):
        cls.calls.append((approval_id, kind, plan_hash, tuple(scope)))
        if (approval_id, kind, plan_hash) != ("appr-good-0001", "launch_plan_build", "abcd1234"):
            raise RuntimeError("APPROVAL-NOT-FROM-AUTHORITY")
        if not set(scope) <= {"publish:DRAFT", "reentry:ONCE"}:
            raise RuntimeError("APPROVAL-SCOPE")
        return {"ok": True}


def _plan_mode(tmp_path, **override):
    record = {"approval_id": "appr-good-0001", "plan_hash": "abcd1234",
              "publish_intent": "DRAFT", "re_entry": "ONCE", "build_model": "build-model-a"}
    record.update(override)
    path = tmp_path / "plan-mode.json"
    path.write_text(json.dumps(record))
    return path


def _build(doc, tmp_path, *extra, authority=Authority):
    """Invoke a live (non-dry-run) launch build; a client being created is a test failure on refusal."""
    created = []

    def client(*a, **k):
        created.append(1)
        return object()

    class Builder:
        def __init__(self, client, v4=None):
            pass

        def build(self, campaign, folder_name=None, folder_id=None, *, journal=None, browser_executor=None):
            return {"errors": []}

        def format_summary(self):
            return "ok"

    with patch.object(wb, "CampaignBuilder", Builder), \
            patch.object(wb, "resolve_browser_executor", return_value=object()), \
            patch.object(cli_mod, "_approval_record", return_value=authority), \
            patch.object(cli_mod, "_get_internal_client", client), \
            patch.object(cli_mod, "_get_public_v4", return_value=(None, "off")):
        result = CliRunner().invoke(cli, [
            "--experimental", "--json", "--location-id", LOC, "workflows", "build",
            "--from-automation-build", str(doc), "--journal", str(tmp_path / "j.jsonl"), *extra])
    return result, created


def test_build_without_plan_mode_file_is_refused_before_any_client(tmp_path):
    doc = ready_document(tmp_path)
    result, created = _build(doc, tmp_path)
    assert result.exit_code == 1, result.output
    assert REFUSAL in result.output and "plan_mode_file_absent" in result.output
    assert created == [], "the internal client must not be created when PLAN MODE is unverified"
    assert not (tmp_path / "j.jsonl").exists()


def test_plan_mode_path_that_does_not_exist_is_refused(tmp_path):
    result, created = _build(ready_document(tmp_path), tmp_path, "--plan-mode-file", str(tmp_path / "nope.json"))
    assert result.exit_code == 1 and REFUSAL in result.output and created == []


@pytest.mark.parametrize("override,reason", [
    ({"approval_id": "appr-invented-99"}, "approval_not_verified"),
    ({"plan_hash": "ffff"}, "approval_not_verified"),
    ({"re_entry": "ALLOW-MULTIPLE"}, "approval_not_verified"),   # scope the record does not cover
    ({"publish_intent": "LIVE"}, "approval_not_verified"),
    ({"re_entry": ""}, "plan_mode_file_malformed"),
    ({"publish_intent": "maybe"}, "plan_mode_answers_invalid"),
])
def test_unverified_or_malformed_plan_mode_file_is_refused(tmp_path, override, reason):
    path = _plan_mode(tmp_path, **override)
    result, created = _build(ready_document(tmp_path), tmp_path, "--plan-mode-file", str(path))
    assert result.exit_code == 1, result.output
    assert REFUSAL in result.output and reason in result.output
    assert created == []


def test_self_written_file_fails_against_the_real_verifier(tmp_path):
    """No mocks on the authority: a file the AI wrote itself cannot be confirmed (Command Center unreachable)."""
    path = _plan_mode(tmp_path)
    created = []
    with patch.object(cli_mod, "_get_internal_client", lambda *a, **k: created.append(1) or object()):
        result = CliRunner().invoke(cli, [
            "--experimental", "--json", "--location-id", LOC, "workflows", "build",
            "--from-automation-build", str(ready_document(tmp_path)),
            "--journal", str(tmp_path / "j.jsonl"), "--plan-mode-file", str(path)])
    assert result.exit_code == 1 and REFUSAL in result.output
    assert "approval_not_verified" in result.output and created == []


def test_verified_plan_mode_file_lets_the_build_run_with_both_answers_in_scope(tmp_path):
    Authority.calls.clear()
    path = _plan_mode(tmp_path, publish_intent="draft", re_entry="once")
    result, created = _build(ready_document(tmp_path), tmp_path, "--plan-mode-file", str(path))
    assert result.exit_code == 0, result.output
    assert created == [1]
    assert Authority.calls == [("appr-good-0001", "launch_plan_build", "abcd1234",
                                ("publish:DRAFT", "reentry:ONCE"))]


def test_dry_run_still_needs_no_plan_mode_file(tmp_path):
    doc = ready_document(tmp_path)
    with patch.object(cli_mod, "_get_internal_client", side_effect=AssertionError("no client")):
        result = CliRunner().invoke(cli, ["--json", "--location-id", LOC, "workflows", "build",
                                          "--from-automation-build", str(doc),
                                          "--journal", str(tmp_path / "j.jsonl"), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["dry_run"] is True


@pytest.mark.parametrize("text,reason", [
    ("{not json", "plan_mode_file_unreadable"),
    ("", "plan_mode_file_unreadable"),
    ("[1, 2]", "plan_mode_file_malformed"),
    ('"approval_id"', "plan_mode_file_malformed"),
    ("null", "plan_mode_file_malformed"),
])
def test_plan_mode_file_that_is_not_a_json_object_is_refused_with_its_reason(tmp_path, text, reason):
    path = tmp_path / "plan-mode.json"
    path.write_text(text)
    result, created = _build(ready_document(tmp_path), tmp_path, "--plan-mode-file", str(path))
    assert result.exit_code == 1, result.output
    assert REFUSAL in result.output and reason in result.output
    assert created == [] and not (tmp_path / "j.jsonl").exists()


@pytest.mark.parametrize("field", ["approval_id", "plan_hash", "publish_intent", "re_entry"])
@pytest.mark.parametrize("value", [None, 7, True, "", "   "])
def test_each_plan_mode_field_must_be_a_non_empty_string(tmp_path, field, value):
    path = _plan_mode(tmp_path, **{field: value})
    result, created = _build(ready_document(tmp_path), tmp_path, "--plan-mode-file", str(path))
    assert result.exit_code == 1, result.output
    assert REFUSAL in result.output and "plan_mode_file_malformed" in result.output
    assert created == []


def test_a_plan_mode_file_missing_a_field_is_refused(tmp_path):
    path = _plan_mode(tmp_path)
    record = json.loads(path.read_text())
    del record["plan_hash"]
    path.write_text(json.dumps(record))
    result, created = _build(ready_document(tmp_path), tmp_path, "--plan-mode-file", str(path))
    assert result.exit_code == 1 and "plan_mode_file_malformed" in result.output and created == []


def test_the_refusal_is_written_to_stderr_and_names_the_next_step(tmp_path):
    result, _created = _build(ready_document(tmp_path), tmp_path)
    assert result.exit_code == 1
    assert REFUSAL in result.stderr and "plan_mode_file_absent" in result.stderr
    assert "Step 0.5" in result.stderr and "--plan-mode-file" in result.stderr

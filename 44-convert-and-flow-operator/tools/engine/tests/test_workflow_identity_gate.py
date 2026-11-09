"""Test pre-write workflow identity refusals and zero-HTTP guarantees."""
import os, sys

_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

from cli_anything.gohighlevel.utils import workflow_builder as wb
from cli_anything.gohighlevel.utils import workflow_identity as wi


class ZeroCallClient:
    def __init__(self):
        self.location_id = "SANDBOX_LOC_001"
        self.calls = []
        self.call_count = 0

    def request(self, method, path, body=None, workflow_name="", **kw):
        self.calls.append((method, path, body))
        self.call_count += 1
        raise AssertionError(
            f"HTTP request issued before the identity gate: {method} {path}"
        )

    def create_location_tag(self, tag, workflow_name=""):
        self.calls.append(("CREATE_TAG", tag, None))
        self.call_count += 1
        raise AssertionError("tag write issued before the identity gate")


def _configure_env(monkeypatch, tmp_path):
    for key, value in {
        "CAF_DATA_DIR": str(tmp_path),
        "CAF_ALLOWED_LOCATION_IDS": "SANDBOX_LOC_001",
        "CAF_APPROVAL_TOKEN": "test-token",
        "GHL_FIREBASE_REFRESH_TOKEN": "sandbox-token",
        "CAF_STEP_BACKOFF_MS": "0",
        "CAF_INTERNAL_STEP_BACKOFF_MS": "0",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CAF_DRY_RUN", raising=False)
    monkeypatch.setenv("CAF_INTERNAL_MAX_WORKERS", "1")


def _build(monkeypatch, tmp_path, templates, name="Gate WF"):
    _configure_env(monkeypatch, tmp_path)
    client = ZeroCallClient()
    stats = wb.CampaignBuilder(client).build(
        {"w1": {"name": name, "templates": templates}},
        "caf-build",
    )
    return stats, client


def _assert_refused_without_http(stats, client, *expected):
    assert client.call_count == 0
    assert client.calls == []
    assert stats["errors"]
    errors = " ".join(stats["errors"]).lower()
    for substring in expected:
        assert substring.lower() in errors, (
            f"Expected {substring!r} in refusal errors: {errors}"
        )


def test_duplicate_node_id_refused_before_any_http(monkeypatch, tmp_path):
    stats, client = _build(monkeypatch, tmp_path, [
        {"id": "a", "type": "sms", "name": "A"},
        {"id": "a", "type": "workflow_goal", "name": "B"},
    ])
    _assert_refused_without_http(stats, client, "duplicate")


def test_dangling_authored_target_refused_before_any_http(monkeypatch, tmp_path):
    stats, client = _build(monkeypatch, tmp_path, [
        {"id": "a", "type": "sms", "name": "A", "next": "ghost"},
        {"id": "b", "type": "workflow_goal", "name": "B"},
    ])
    _assert_refused_without_http(stats, client, "ghost", "refusing")


def test_two_roots_refused_before_any_http(monkeypatch, tmp_path):
    stats, client = _build(monkeypatch, tmp_path, [
        {"id": "a", "type": "sms", "name": "A", "parentKey": None},
        {"id": "b", "type": "workflow_goal", "name": "B", "parentKey": None},
    ])
    _assert_refused_without_http(stats, client, "root")


def test_malformed_if_else_branches_refused_before_any_http(monkeypatch, tmp_path):
    stats, client = _build(monkeypatch, tmp_path, [
        {
            "id": "if1",
            "type": "if_else",
            "name": "C",
            "branches": {"true": "then1"},
        },
        {"id": "then1", "type": "sms", "name": "T"},
    ])
    _assert_refused_without_http(stats, client, "if_else", "refusing")


def test_parent_key_not_found_refused_before_any_http(monkeypatch, tmp_path):
    stats, client = _build(monkeypatch, tmp_path, [
        {"id": "a", "type": "sms", "name": "A", "parentKey": None},
        {
            "id": "b",
            "type": "workflow_goal",
            "name": "B",
            "parentKey": "missing",
        },
    ])
    _assert_refused_without_http(stats, client, "parent")


def test_parent_cycle_refused_before_any_http(monkeypatch, tmp_path):
    stats, client = _build(monkeypatch, tmp_path, [
        {"id": "a", "type": "sms", "name": "A", "parentKey": "b"},
        {"id": "b", "type": "workflow_goal", "name": "B", "parentKey": "a"},
    ])
    _assert_refused_without_http(stats, client, "cycle")


def test_unauthored_if_else_still_refused_with_unlinked_message(
    monkeypatch, tmp_path
):
    stats, client = _build(monkeypatch, tmp_path, [
        {"id": "b1", "type": "if_else", "name": "Cond"},
        {"id": "n2", "type": "workflow_goal", "name": "End"},
    ])
    _assert_refused_without_http(stats, client, "branch node", "refusing")


def test_authored_branch_plan_is_not_refused():
    plan = [
        {
            "id": "if1",
            "type": "if_else",
            "name": "Cond",
            "branches": {"true": "then1", "false": "else1"},
        },
        {
            "id": "then1",
            "type": "sms",
            "name": "Then",
            "parentKey": "if1",
            "next": "after",
        },
        {
            "id": "else1",
            "type": "sms",
            "name": "Else",
            "parentKey": "if1",
        },
        {
            "id": "after",
            "type": "workflow_goal",
            "name": "After",
            "parentKey": "then1",
        },
    ]
    assert wi.plan_identity_refusals(
        {"w1": {"name": "OK", "templates": plan}}
    ) == []


def test_refusal_tuple_shape_matches_build_refusal_path():
    refusals = wi.plan_identity_refusals({
        "w1": {
            "name": "Dup",
            "templates": [
                {"id": "a", "type": "sms", "name": "A"},
                {"id": "a", "type": "workflow_goal", "name": "B"},
            ],
        },
    })
    assert refusals
    term = refusals[0]
    assert isinstance(term, tuple) and len(term) == 6
    assert term[0] == "w1"
    assert term[1] is None
    assert term[2] is False
    assert term[3] is False
    assert term[4] is None
    assert isinstance(term[5], str)
    assert "refusing to build" in term[5]


def test_flat_linear_plan_is_not_refused():
    plan = [
        {"id": "a", "type": "sms", "name": "A"},
        {"id": "b", "type": "sms", "name": "B"},
        {"id": "c", "type": "workflow_goal", "name": "C"},
    ]
    assert wi.plan_identity_refusals(
        {"w1": {"name": "Flat", "templates": plan}}
    ) == []

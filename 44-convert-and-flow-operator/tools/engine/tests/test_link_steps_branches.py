"""Lock down three defects: linearised branches, authored links overwritten,
and branch nodes with no targets reaching the API.
"""
import os, sys
from pathlib import Path

_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

from cli_anything.gohighlevel.utils import workflow_builder as wb


class FakeClient:
    def __init__(self):
        self.location_id = "SANDBOX_LOC_001"
        self.calls = []
        self.call_count = 0

    def request(self, method, path, body=None, workflow_name="", **_kw):
        self.calls.append((method, path, body))
        self.call_count += 1
        if method == "GET" and path.endswith("/tags"):
            return [{"id": "TAG-T", "name": "t"}]
        if method == "GET" and path.endswith((
            "/custom-fields", "/custom-values", "/calendars", "/pipelines"
        )):
            return {"items": []}
        if method == "GET" and path == f"/workflow/{self.location_id}":
            return {"workflows": [], "folders": []}
        if method == "GET" and path == f"/workflow/{self.location_id}/WF1":
            return {
                "id": "WF1", "name": "Branchy", "version": 2, "meta": {},
                "workflowData": {"templates": []},
            }
        if method == "POST" and path.endswith("/trigger"):
            return {"id": "TRG1"}
        if method == "POST" and path == f"/workflow/{self.location_id}":
            if body and body.get("type") == "directory":
                return {"id": "FOLDER1", "name": body["name"]}
            return {"id": "WF1"}
        if method == "GET":
            return {"workflows": [], "folders": []}
        if method == "PUT":
            return {"id": "WF1"}
        return {"id": "FOLDER1", "name": "caf-build"}

    def create_location_tag(self, tag, workflow_name=""):
        self.calls.append(("CREATE_TAG", tag, None))
        self.call_count += 1
        return {"id": "TAG1"}


def _branch_plan():
    return [
        {"id": "if1", "type": "if_else", "name": "Cond",
         "branches": {"true": "then1", "false": "else1"}},
        {"id": "then1", "type": "sms", "name": "Then",
         "parentKey": "if1", "next": "after"},
        {"id": "else1", "type": "sms", "name": "Else",
         "parentKey": "if1"},
        {"id": "after", "type": "workflow_goal", "name": "After",
         "parentKey": "then1"},
    ]


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


def test_authored_links_survive_link_steps():
    plan = _branch_plan()
    linked, unlinked = wb.link_steps(plan)
    by_id = {step["id"]: step for step in linked}
    assert unlinked == [], "authored branch targets must prevent false unlinked refusal"
    assert by_id["else1"]["parentKey"] == "if1", "authored parentKey must prevent orphan defect"
    assert by_id["then1"]["next"] == "after", "authored next must not be overwritten"
    assert by_id["if1"]["branches"] == {"true": "then1", "false": "else1"}, "branch edges must not be linearised"
    assert [step["order"] for step in linked] == [0, 1, 2, 3], "input order must remain stable"


def test_untargeted_branch_is_refused_by_linker():
    plan = [
        {"id": "b1", "type": "if_else", "name": "Cond"},
        {"id": "n2", "type": "workflow_goal", "name": "End"},
    ]
    linked, unlinked = wb.link_steps(plan)
    assert unlinked == ["b1"], "branch without authored targets must be reported unlinked"
    assert linked[0].get("next") in (None,), "branch without targets must not get linear next"
    assert linked[0].get("parentKey") is None, "branch without targets must not get inferred parent"
    flat, flat_unlinked = wb.link_steps([
        {"id": "a", "type": "sms", "name": "A"},
        {"id": "b", "type": "workflow_goal", "name": "B"},
    ])
    assert flat_unlinked == [], "ordinary flat plan must not trigger branch refusal"
    assert flat[0]["next"] == "b" and flat[0]["parentKey"] is None, "flat-chain linking must remain unchanged"
    assert flat[1]["next"] is None and flat[1]["parentKey"] == "a", "flat-chain terminal links must remain unchanged"


def test_build_refuses_untargeted_branch_without_writes(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    client = FakeClient()
    campaign = {"w1": {
        "name": "Branchy",
        "templates": [
            {"id": "b1", "type": "if_else", "name": "Cond"},
            {"id": "n2", "type": "workflow_goal", "name": "End"},
        ],
    }}
    stats = wb.CampaignBuilder(client).build(campaign, "caf-build")
    assert stats["errors"], "untargeted branch reaching API must produce build error"
    assert any("branch node" in error.lower() and "refusing" in error.lower()
               for error in stats["errors"]), "branch node refusal reason must be surfaced"
    assert not any(method == "POST" and path == f"/workflow/{client.location_id}"
                   and isinstance(body, dict) and "parentId" in body
                   for method, path, body in client.calls), "untargeted branch must not create the workflow"
    assert not any(method == "PUT" for method, _, _ in client.calls), "untargeted branch must issue no writes"


def test_authored_branch_build_preserves_trigger_entrance(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    client = FakeClient()
    campaign = {"w1": {
        "name": "Branchy", "tag": "t",
        "templates": _branch_plan(),
    }}
    stats = wb.CampaignBuilder(client).build(campaign, "caf-build")
    assert stats["errors"] == [], "fully authored branch graph must build without refusal"
    step_puts = [
        body for method, path, body in client.calls
        if method == "PUT" and isinstance(body, dict)
        and isinstance(body.get("workflowData"), dict)
    ]
    assert step_puts, "branch graph must reach workflow step-save PUT"
    saved = step_puts[0]["workflowData"]["templates"]
    by_name = {step["name"]: step for step in saved}
    cond = by_name["Cond"]
    then_node = by_name["Then"]
    else_node = by_name["Else"]
    assert cond["branches"] == {
        "true": then_node["id"],
        "false": else_node["id"],
    }, "saved graph must preserve branch edges using normalized ids"
    assert else_node["parentKey"] == cond["id"], "saved graph must preserve authored branch parent, never then branch"
    assert cond.get("next") is None, "branch node must not lose else edge through single next pointer"
    trigger_puts = [
        body for method, path, body in client.calls
        if method == "PUT" and "/trigger/" in path and isinstance(body, dict)
    ]
    assert trigger_puts, "trigger entrance must be linked before graph sync"
    first_id = saved[0]["id"]
    assert trigger_puts[0].get("targetActionId") == first_id, "trigger entrance must target first saved action UUID"
    sync_puts = [
        body for method, path, body in client.calls
        if method == "PUT" and isinstance(body, dict) and "newTriggers" in body
    ]
    assert sync_puts and sync_puts[0]["newTriggers"], "trigger sync must resend trigger object"
    assert sync_puts[0]["newTriggers"][0].get("targetActionId") == first_id, "re-sent trigger must retain same UUID-minted entrance link"
    assert sync_puts[0]["newTriggers"][0].get("targetActionId") == trigger_puts[0].get("targetActionId"), "trigger PUT and sync must target identical action id"


def test_branch_body_never_chains_into_sibling_body():
    linked, unlinked = wb.link_steps(_branch_plan())
    by_id = {step["id"]: step for step in linked}
    assert by_id["else1"]["next"] is None
    assert "next" in by_id["else1"]
    assert by_id["then1"]["next"] == "after"
    assert by_id["if1"]["branches"] == {"true": "then1", "false": "else1"}
    assert unlinked == []

    linked, unlinked = wb.link_steps([
        {"id": "if1", "type": "if_else", "name": "C",
         "branches": {"true": "then1", "false": "else1"}},
        {"id": "then1", "type": "sms", "name": "T"},
        {"id": "else1", "type": "sms", "name": "E"},
        {"id": "join", "type": "workflow_goal", "name": "J", "parentKey": None},
    ])
    by_id = {step["id"]: step for step in linked}
    assert by_id["then1"]["next"] is None
    assert by_id["else1"]["next"] is None
    assert by_id["if1"]["branches"] == {"true": "then1", "false": "else1"}
    assert unlinked == []

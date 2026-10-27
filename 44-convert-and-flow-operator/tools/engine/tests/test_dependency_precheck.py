"""Test declared-dependency pre-check refusal, uncertainty, and scope."""
import os
import sys

_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

from cli_anything.gohighlevel.utils import workflow_builder as wb


class FakeClient:
    def __init__(self, location_id="LOC1"):
        self.location_id = location_id
        self.calls = []
        self.call_count = 0
        self.tags_response = []

    def request(self, method, path, body=None, workflow_name="", **_kw):
        self.calls.append((method, path, body))
        self.call_count += 1
        if method == "GET" and path == f"/workflow/{self.location_id}":
            return {"workflows": [], "folders": []}
        if method == "GET" and path == f"/workflow/{self.location_id}/tags":
            return self.tags_response
        if method == "GET" and path.endswith((
            "/custom-fields", "/custom-values", "/calendars", "/pipelines"
        )):
            return {"items": []}
        if method == "POST" and path == f"/workflow/{self.location_id}/trigger":
            return {"id": "TRG1"}
        if method == "POST" and path == f"/workflow/{self.location_id}":
            return {"id": "FOLDER1" if body and body.get("type") == "directory" else "WF1"}
        if method == "GET" and path == f"/workflow/{self.location_id}/WF1":
            return {
                "id": "WF1", "name": "N", "version": 2,
                "workflowData": {"templates": []}, "meta": {},
            }
        if method == "PUT":
            return {"id": "WF1"}
        return {"id": "TRG1"}

    def create_location_tag(self, tag, workflow_name=""):
        self.calls.append(("CREATE_TAG", tag, None))
        self.call_count += 1
        return {"id": "TAG1"}


class RaisingTagsClient(FakeClient):
    def request(self, method, path, body=None, workflow_name="", **_kw):
        if method == "GET" and path == f"/workflow/{self.location_id}/tags":
            self.calls.append((method, path, body))
            self.call_count += 1
            raise RuntimeError("tags GET failed")
        return super().request(method, path, body, workflow_name, **_kw)


def _plan(dependencies=None):
    workflow = {
        "name": "N",
        "templates": [{"id": "a", "type": "sms", "name": "A"}],
    }
    if dependencies is not None:
        workflow["dependencies"] = dependencies
    return {"w1": workflow}


def _configure_env(monkeypatch, tmp_path):
    for key, value in {
        "CAF_DATA_DIR": str(tmp_path),
        "CAF_ALLOWED_LOCATION_IDS": "LOC1",
        "CAF_APPROVAL_TOKEN": "t",
        "GHL_FIREBASE_REFRESH_TOKEN": "t",
        "CAF_STEP_BACKOFF_MS": "0",
        "CAF_INTERNAL_STEP_BACKOFF_MS": "0",
        "CAF_INTERNAL_MAX_WORKERS": "1",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CAF_DRY_RUN", raising=False)


def _assert_refused_without_writes(stats, client, dependency_name):
    assert any(
        "dependency pre-check failed" in error and dependency_name in error
        and "no workflow create was issued." in error
        for error in stats["errors"]
    ), "unverified dependency must refuse with actionable reason"
    assert stats["precheck"]["N"]["unverified"], (
        "unverified dependency GET must record unverified declarations"
    )
    assert stats["precheck"]["N"]["missing"] == [], (
        "unverified dependencies must not be classified as missing"
    )
    assert not any(
        method == "POST" and path == "/workflow/LOC1"
        and isinstance(body, dict) and "parentId" in body
        for method, path, body in client.calls
    ), "refusal must prevent workflow creation"
    assert not any(
        method == "PUT" and isinstance(body, dict) and "workflowData" in body
        for method, _, body in client.calls
    ), "refusal must prevent step-save writes"
    assert not any(
        method == "CREATE_TAG" for method, _, _ in client.calls
    ), "refusal must prevent tag creation"
    assert not any(
        method == "POST" and path == "/workflow/LOC1/trigger"
        for method, path, _ in client.calls
    ), "refusal must prevent trigger creation"


def test_missing_declared_tag_refuses_before_create(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    client = FakeClient()
    client.tags_response = [{"id": "T1", "name": "other"}]

    stats = wb.CampaignBuilder(client).build(
        _plan({"tags": ["ZHC-missing"]}), "caf-build"
    )

    assert any(
        "dependency pre-check failed" in error and "ZHC-missing" in error
        and "no workflow create was issued." in error
        for error in stats["errors"]
    ), "missing declared dependency must refuse with actionable reason"
    assert stats["precheck"]["N"]["missing"], (
        "missing declared dependency must be recorded"
    )
    assert not any(
        method == "POST" and path == "/workflow/LOC1"
        and isinstance(body, dict) and "parentId" in body
        for method, path, body in client.calls
    ), "missing declared dependency must prevent workflow creation"
    assert not any(
        method == "PUT" and isinstance(body, dict) and "workflowData" in body
        for method, _, body in client.calls
    ), "missing declared dependency must prevent step-save writes"
    assert not any(
        method == "CREATE_TAG" for method, _, _ in client.calls
    ), "missing declared dependency must prevent tag creation"
    assert not any(
        method == "POST" and path == "/workflow/LOC1/trigger"
        for method, path, _ in client.calls
    ), "missing declared dependency must prevent trigger creation"


def test_plan_cannot_grant_itself_a_missing_dep_bypass(monkeypatch, tmp_path):
    """The plan is the thing being gated, so a key inside it is not approval.

    `create_if_missing` used to be read straight off the workflow definition,
    so an author could ship a plan that unlocked its own dependency gate. The
    bypass is gone; the key must now be inert.
    """
    _configure_env(monkeypatch, tmp_path)
    client = FakeClient()
    client.tags_response = [{"id": "T1", "name": "other"}]

    plan = _plan({"tags": ["ZHC-missing"]})
    plan["w1"]["create_if_missing"] = True

    stats = wb.CampaignBuilder(client).build(plan, "caf-build")

    assert any(
        "dependency pre-check failed" in error and "ZHC-missing" in error
        for error in stats["errors"]
    ), "a plan-supplied create_if_missing must not authorise a write"
    assert not any(
        method == "POST" and path == "/workflow/LOC1"
        and isinstance(body, dict) and "parentId" in body
        for method, path, body in client.calls
    ), "self-granted bypass must still prevent workflow creation"
    assert not any(
        method == "PUT" and isinstance(body, dict) and "workflowData" in body
        for method, _, body in client.calls
    ), "self-granted bypass must still prevent step-save writes"


def test_no_bypass_parameter_remains_on_the_precheck():
    """A bypass flag on the function is the same fail-open wearing a hat."""
    import inspect

    assert "create_if_missing" not in inspect.signature(
        wb.precheck_dependencies
    ).parameters, "precheck_dependencies must carry no bypass parameter"
    assert "create_if_missing" not in inspect.signature(
        wb.CampaignBuilder.precheck
    ).parameters, "CampaignBuilder.precheck must carry no bypass parameter"


def test_unverified_read_refuses(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    client = FakeClient()
    client.tags_response = {"_error": True, "message": "404"}

    stats = wb.CampaignBuilder(client).build(
        _plan({"tags": ["ZHC-unknown"]}), "caf-build"
    )

    _assert_refused_without_writes(stats, client, "ZHC-unknown")


def test_unverified_transport_exception_refuses(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    client = RaisingTagsClient()

    stats = wb.CampaignBuilder(client).build(
        _plan({"tags": ["ZHC-unknown"]}), "caf-build"
    )

    _assert_refused_without_writes(stats, client, "ZHC-unknown")


def test_unverified_none_response_refuses(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    client = FakeClient()
    client.tags_response = None

    stats = wb.CampaignBuilder(client).build(
        _plan({"tags": ["ZHC-unknown"]}), "caf-build"
    )

    _assert_refused_without_writes(stats, client, "ZHC-unknown")


def test_present_dependency_builds(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    client = FakeClient()
    client.tags_response = [{"id": "T9", "name": "ZHC-present"}]

    stats = wb.CampaignBuilder(client).build(
        _plan({"tags": ["ZHC-present"]}), "caf-build"
    )

    assert "ZHC-present" in [
        item["name"] for item in stats["precheck"]["N"]["present"]
    ], "existing declared dependency must be recorded as present"
    assert stats["precheck"]["N"]["missing"] == []
    assert stats["precheck"]["N"]["unverified"] == []
    assert not any(
        "dependency pre-check failed" in error for error in stats["errors"]
    ), "present declared dependency must not trigger refusal"


def test_no_declared_dependency_means_no_precheck_call(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    client = FakeClient()

    wb.CampaignBuilder(client).build(_plan(), "caf-build")

    assert not any(
        method == "GET" and path.endswith("/tags")
        for method, path, _ in client.calls
    ), "workflow without declared dependencies must skip dependency pre-check"

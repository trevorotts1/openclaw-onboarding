"""No folder may be created on a build that then refuses.

The folder POST used to fire before the declared-dependency pre-check, so a
build that refused still left a folder behind in the client's GHL account.
These tests count the ACTUAL requests the client receives: an exit code or a
stats field cannot see a write that already happened.
"""
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
        self.calls.append((method, path, body, workflow_name))
        self.call_count += 1
        if method == "GET" and path == f"/workflow/{self.location_id}":
            return {"workflows": [], "folders": []}
        if method == "GET" and path == f"/workflow/{self.location_id}/tags":
            return self.tags_response
        if method == "GET" and path.endswith((
            "/custom-fields", "/custom-values", "/calendars", "/pipelines"
        )):
            return {"items": []}
        if method == "POST" and path == f"/workflow/{self.location_id}":
            return {"id": "FOLDER1" if body and body.get("type") == "directory" else "WF1"}
        if method == "POST" and path == f"/workflow/{self.location_id}/trigger":
            return {"id": "TRG1"}
        if method == "GET" and path == f"/workflow/{self.location_id}/WF1":
            return {"id": "WF1", "name": "N", "version": 2,
                    "workflowData": {"templates": []}, "meta": {}}
        return {"id": "X1"}

    def create_location_tag(self, tag, workflow_name=""):
        self.calls.append(("CREATE_TAG", tag, None, workflow_name))
        self.call_count += 1
        return {"id": "TAG1"}


def _folder_posts(client):
    return [
        (method, path, body)
        for method, path, body, _name in client.calls
        if method == "POST" and path == "/workflow/LOC1"
        and isinstance(body, dict) and body.get("type") == "directory"
    ]


def _plan(dependencies):
    return {"w1": {
        "name": "N",
        "templates": [{"id": "a", "type": "sms", "name": "A"}],
        "dependencies": dependencies,
    }}


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


def test_refused_precheck_issues_no_folder_post(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    client = FakeClient()
    client.tags_response = [{"id": "T1", "name": "other"}]

    stats = wb.CampaignBuilder(client).build(
        _plan({"tags": ["ZHC-missing"]}), "caf-build"
    )

    assert any(
        "dependency pre-check failed" in error and "ZHC-missing" in error
        for error in stats["errors"]
    ), "missing declared dependency must still refuse the build"
    assert _folder_posts(client) == [], (
        "a refused build must not create a folder; folder POST(s) issued: "
        f"{_folder_posts(client)}"
    )


def test_passing_precheck_still_creates_the_folder(monkeypatch, tmp_path):
    """Control: proves the assertion above can see a folder POST at all."""
    _configure_env(monkeypatch, tmp_path)
    client = FakeClient()
    client.tags_response = [{"id": "T9", "name": "ZHC-present"}]

    wb.CampaignBuilder(client).build(_plan({"tags": ["ZHC-present"]}), "caf-build")

    assert len(_folder_posts(client)) == 1, (
        "a build that passes the pre-check must still create its folder"
    )

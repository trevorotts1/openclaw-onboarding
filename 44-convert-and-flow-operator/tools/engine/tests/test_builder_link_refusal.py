import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RECORDED = []
ROOT = Path(__file__).resolve().parent.parent
BUILDERS = [
    "consulti-nurture-builder.py",
    "post-purchase-nurture-builder.py",
    "wf1-course-interest-builder.py",
    "wf5-ht-interest-builder.py",
    "wf6-post-call-sales-builder.py",
]


class RecordingClient:
    location_id = "LOC001"

    def __init__(self, *args, **kwargs):
        self.writes = []
        RECORDED.append(self)

    def request(self, method, path, body=None, **kwargs):
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            self.writes.append((method, path))
        return {}

    def get(self, *args, **kwargs):
        return self.request("GET", *args, **kwargs)

    def post(self, *args, **kwargs):
        return self.request("POST", *args, **kwargs)

    def put(self, *args, **kwargs):
        return self.request("PUT", *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.request("DELETE", *args, **kwargs)

    def create_location_tag(self, *args, **kwargs):
        return self.request("POST", "/location/tags", *args, **kwargs)


def loader(name):
    path = ROOT / "builders" / name
    module_name = f"_test_builder_{path.stem.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def setup_email_builder(module, tmp_path):
    module.REVISED_DIR = tmp_path
    for filename, *_ in module.EMAILS:
        (tmp_path / filename).write_text("fixture")
    module.parse_email_file = lambda path: {"subject": "Test", "body": "Test"}


def setup_wf1(module, tmp_path):
    module.parse_sequence_file = lambda path: [
        SimpleNamespace(
            day=i, code=f"E{i + 1}", title="Test",
            subject_a="Test", body_md="Test",
        )
        for i in range(10)
    ]


def setup_wf5(module, tmp_path):
    module.parse_sequence_file = lambda path: [
        SimpleNamespace(
            code=code, kind="sms" if code == "SMS" else "email",
            title="Test", body_md="Test", subject_a="Test",
        )
        for code in ["E1", "SMS", "E2", "E3", "E4", "E5"]
    ]


def setup_wf6(module, tmp_path):
    codes = [f"A{i}" for i in range(1, 7)]
    codes += [f"B{i}" for i in range(1, 7)]
    codes += [f"C{i}" for i in range(1, 6)]
    module.parse_sequence_file = lambda path: [
        SimpleNamespace(
            code=code, index=i, day=i, title="Test",
            subject_a="Test", body_md="Test",
        )
        for i, code in enumerate(codes)
    ]


SETUPS = {
    "consulti-nurture-builder.py": setup_email_builder,
    "post-purchase-nurture-builder.py": setup_email_builder,
    "wf1-course-interest-builder.py": setup_wf1,
    "wf5-ht-interest-builder.py": setup_wf5,
    "wf6-post-call-sales-builder.py": setup_wf6,
}


@pytest.mark.parametrize("name", BUILDERS)
def test_builder_refuses_unwired_branches_without_http_writes(
    name, tmp_path, monkeypatch
):
    RECORDED.clear()
    module = loader(name)
    SETUPS[name](module, tmp_path)

    from cli_anything.gohighlevel.utils import workflow_builder

    monkeypatch.setattr(
        workflow_builder, "link_steps",
        lambda steps: ([], ["branch_node_1"]),
    )
    monkeypatch.setattr(module, "InternalGHLClient", RecordingClient)
    monkeypatch.setattr(module, "TokenManager", RecordingClient)
    monkeypatch.setattr(sys, "argv", ["builder"])
    monkeypatch.setenv("GHL_LOCATION_ID", "LOC001")

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code not in (0, None)
    assert "branch_node_1" in str(exc.value)
    assert not any(client.writes for client in RECORDED)

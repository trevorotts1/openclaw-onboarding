from __future__ import annotations

import importlib.util
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[2]
MODULE_PATH = SKILL_DIR / "scripts" / "ghl_template.py"
SPEC = SKILL_DIR / "config" / "ghl-template.json"

module_spec = importlib.util.spec_from_file_location("podcast_ghl_template", MODULE_PATH)
ghl_template = importlib.util.module_from_spec(module_spec)
assert module_spec and module_spec.loader
module_spec.loader.exec_module(ghl_template)


class FakeClient:
    def __init__(self):
        self.fields = []
        self.values = []
        self.tags = []

    def list_fields(self):
        return list(self.fields)

    def create_field(self, item):
        live = {
            "id": "field-%d" % (len(self.fields) + 1),
            "name": item["name"],
            "fieldKey": ghl_template.expected_field_key(item["name"]),
            "dataType": item["data_type"],
            "picklistOptions": list(item.get("options") or []),
        }
        self.fields.append(live)
        return live

    def list_values(self):
        return list(self.values)

    def create_value(self, item):
        live = {
            "id": "value-%d" % (len(self.values) + 1),
            "name": item["name"],
            "value": item["value"],
        }
        self.values.append(live)
        return live

    def list_tags(self):
        return list(self.tags)

    def create_tag(self, name):
        live = {"id": "tag-%d" % (len(self.tags) + 1), "name": name}
        self.tags.append(live)
        return live


def test_spec_is_exact_and_complete():
    spec = ghl_template.load_spec(SPEC)
    assert len(spec["custom_fields"]) == 28
    assert len(spec["custom_values"]) == 6
    assert len(spec["tags"]) == 2
    names = {item["name"] for item in spec["custom_fields"]}
    assert "podcast_survey__additional_info" in names
    assert "podcast_survey_additional_info" not in names


def test_style_picklists_are_pinned():
    spec = ghl_template.load_spec(SPEC)
    fields = {item["name"]: item for item in spec["custom_fields"]}
    interview = fields["podcast_survey_writing_style"]
    personal = fields["select_your_presentation_style_personal_podcast"]
    assert interview["data_type"] == "SINGLE_OPTIONS"
    assert len(interview["options"]) == 4
    assert personal["options"] == ["Counterintuitive", "Passionate"]


def test_create_or_verify_is_idempotent():
    spec = ghl_template.load_spec(SPEC)
    client = FakeClient()
    first = ghl_template.apply_fields(client, spec)
    second = ghl_template.apply_fields(client, spec)
    assert len(first["created"]) == 28
    assert len(second["created"]) == 0
    assert len(second["verified"]) == 28
    assert len(client.fields) == 28


def test_version_stamp_is_deferred_then_created_last():
    spec = ghl_template.load_spec(SPEC)
    client = FakeClient()
    first = ghl_template.apply_values(client, spec, stamp_version=False)
    assert len(first["created"]) == 5
    assert first["deferred"] == ["podcast_snapshot_version"]
    second = ghl_template.apply_values(client, spec, stamp_version=True)
    assert second["created"] == ["podcast_snapshot_version"]
    assert len(client.values) == 6


def test_verification_rejects_field_key_drift():
    spec = ghl_template.load_spec(SPEC)
    client = FakeClient()
    ghl_template.apply_fields(client, spec)
    ghl_template.apply_values(client, spec, stamp_version=True)
    ghl_template.apply_tags(client, spec)
    client.fields[0]["fieldKey"] += "_wrong"
    try:
        ghl_template.verify_inventory(client, spec, allow_unstamped=False)
    except ghl_template.MismatchError:
        pass
    else:
        raise AssertionError("field-key drift must fail verification")

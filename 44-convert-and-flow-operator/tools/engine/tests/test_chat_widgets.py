"""Focused offline tests for WF31 chat widgets (B16, IG-WIDGET-01..03).

No network: the adapter facade is exercised through a recording fake.  Every
value is synthetic.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

_ENGINE = Path(__file__).resolve().parents[1]
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

from cli_anything.gohighlevel.public import chat_widgets as cw  # noqa: E402

SNIPPET = (
    '<script src="https://widgets.example.test/loader.js" '
    'data-widget-id="wid_0001"></script>'
)


def _embed(**overrides):
    payload = {
        "widget_id": "wid_0001",
        "script_url": "https://widgets.example.test/loader.js",
        "snippet": SNIPPET,
        "provenance": "captured_ui",
        "evidence_ref": "evidence/WF31/embed-capture.json",
    }
    payload.update(overrides)
    return cw.EmbedInstruction(**payload)


def _page():
    return {
        "sections": [{"id": "section_1", "elements": [{"id": "el_1"}]}],
        "trackingCode": {"head": "<!-- keep -->", "footerCode": ""},
        "popups": [],
    }


# ---------------------------------------------------------------------------
# B16 / IG-WIDGET-01: write allowlist and read enum separation
# ---------------------------------------------------------------------------

def test_create_accepts_only_the_two_write_types():
    for chat_type in cw.CREATE_CHAT_TYPES:
        body = cw.build_create_body(
            location_id="loc_test", name="Support", chat_type=chat_type, version=2
        )
        assert body["chatType"] == chat_type
        assert body["version"] == 2


@pytest.mark.parametrize(
    "read_type",
    [name for name in cw.READ_CHAT_TYPES if name not in cw.CREATE_CHAT_TYPES],
)
def test_create_rejects_every_type_outside_the_write_allowlist(read_type):
    with pytest.raises(cw.WidgetTypeNotWritable) as caught:
        cw.build_create_body(
            location_id="loc_test", name="Support", chat_type=read_type, version=2
        )
    assert caught.value.rule == "read_enum_is_not_a_write_enum"


def test_read_enum_is_never_promoted_from_settings():
    body = cw.build_create_body(
        location_id="loc_test",
        name="Support",
        chat_type="liveChat",
        version=2,
        settings={"chatType": "waChat", "allInOneChatTypes": ["waChat"]},
    )
    assert body["chatType"] == "liveChat"
    assert body["settings"]["chatType"] == "waChat"


# ---------------------------------------------------------------------------
# B16 / IG-WIDGET-02: numeric config version and the widget `_id`
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["v3", "2", 2.0, True, None])
def test_config_version_must_be_a_number_not_an_http_version(bad):
    with pytest.raises(cw.WidgetSchemaError) as caught:
        cw.build_create_body(
            location_id="loc_test", name="Support", chat_type="liveChat", version=bad
        )
    assert caught.value.rule == "config_version_must_be_number"


def test_widget_id_is_underscore_id_and_never_universal_id():
    assert cw.extract_widget_id({"_id": "wid_0001"}) == "wid_0001"
    assert cw.extract_widget_id({"widget": {"_id": "wid_0002"}}) == "wid_0002"
    with pytest.raises(cw.WidgetSchemaError) as caught:
        cw.extract_widget_id({"id": "wid_0001"})
    assert caught.value.rule == "widget_identifier_missing"


def test_widget_list_requires_underscore_id_on_every_item():
    records = cw.parse_widget_list({"widgets": [{"_id": "a"}, {"_id": "b"}]})
    assert [record.widget_id for record in records] == ["a", "b"]
    with pytest.raises(cw.WidgetSchemaError):
        cw.parse_widget_list({"widgets": [{"id": "a"}]})


# ---------------------------------------------------------------------------
# B16 / IG-WIDGET-03: one install across global and page scope
# ---------------------------------------------------------------------------

def test_page_install_preserves_design_and_writes_tracking_code_only():
    page = _page()
    plan = cw.plan_page_install(page, _embed())
    assert plan.page_data["sections"] == page["sections"]
    assert plan.page_data["trackingCode"]["head"] == "<!-- keep -->"
    assert SNIPPET in plan.page_data["trackingCode"]["footerCode"]
    assert page["trackingCode"]["footerCode"] == ""
    assert cw.verify_install(plan.page_data, _embed())


def test_second_page_install_is_refused():
    plan = cw.plan_page_install(_page(), _embed())
    with pytest.raises(cw.DuplicateEmbed) as caught:
        cw.plan_page_install(plan.page_data, _embed())
    assert caught.value.rule == "widget_already_installed"


def test_page_install_is_refused_when_global_already_has_the_widget():
    with pytest.raises(cw.DuplicateEmbed):
        cw.plan_page_install(_page(), _embed(), global_snippets=[SNIPPET])


def test_global_install_is_refused_when_page_already_has_the_widget():
    page = cw.plan_page_install(_page(), _embed()).page_data
    with pytest.raises(cw.DuplicateEmbed):
        cw.plan_global_install([], _embed(), page_data=page)


def test_global_install_adds_exactly_one_snippet():
    updated, plan = cw.plan_global_install(["<!-- existing -->"], _embed())
    assert updated == ["<!-- existing -->", SNIPPET]
    assert plan.occurrence.scope == "global"
    assert plan.page_data == {}


def test_embed_without_provenance_or_evidence_is_refused():
    with pytest.raises(cw.EmbedInstructionError):
        _embed(provenance="made_up")
    with pytest.raises(cw.EmbedInstructionError):
        _embed(evidence_ref="")


def test_embed_cannot_be_an_html_form():
    with pytest.raises(cw.EmbedInstructionError) as caught:
        _embed(
            snippet=(
                '<form action="https://widgets.example.test/loader.js">'
                "wid_0001</form>"
            )
        )
    assert caught.value.rule in ("snippet_not_script_or_iframe", "snippet_is_an_html_form")


# ---------------------------------------------------------------------------
# rendered checks are required in full
# ---------------------------------------------------------------------------

def test_rendered_checks_require_every_named_check():
    all_true = {name: True for name in cw.RENDER_CHECKS}
    assert cw.evaluate_rendered_checks(
        "wid_0001", all_true, evidence_ref="evidence/render.json"
    ).passed
    missing = dict(all_true)
    missing.pop("mobile_display")
    result = cw.evaluate_rendered_checks(
        "wid_0001", missing, evidence_ref="evidence/render.json"
    )
    assert not result.passed
    assert "mobile_display" in result.unverified


# ---------------------------------------------------------------------------
# adapter facade: body reaches the adapter, `_id` comes back
# ---------------------------------------------------------------------------

class _FakeAdapter:
    def __init__(self) -> None:
        self.calls = []

    def call(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(status="ok", error=None, http_status=201)


class _FakeTransport:
    def __init__(self, body):
        self.last_response = types.SimpleNamespace(
            body=json.dumps(body).encode("utf-8")
        )


class _Tenant:
    location_id = "loc_test"


def test_create_through_adapter_builds_body_and_reads_underscore_id():
    adapter = _FakeAdapter()
    public = cw.ChatWidgetsPublic(adapter, _FakeTransport({"_id": "wid_created"}))
    widget_id, result = public.create_widget(
        _Tenant(),
        location_id="loc_test",
        name="Support",
        chat_type="emailChat",
        version=2,
        idempotency_key="gxo_chat-widgets-create-0123456789abcdef0123456789abcdef",
        readback=object(),
    )
    assert widget_id == "wid_created"
    call = adapter.calls[0]
    assert call["operation_id"] == cw.WIDGET_OPERATIONS["create"]
    assert call["body"]["version"] == 2
    assert call["body"]["chatType"] == "emailChat"
    assert "Version" not in call["body"]


def test_create_refuses_read_type_before_calling_the_adapter():
    adapter = _FakeAdapter()
    public = cw.ChatWidgetsPublic(adapter, _FakeTransport({"_id": "x"}))
    with pytest.raises(cw.WidgetTypeNotWritable):
        public.create_widget(
            _Tenant(),
            location_id="loc_test",
            name="Support",
            chat_type="waChat",
            version=2,
            idempotency_key="gxo_chat-widgets-create-0123456789abcdef0123456789abcdef",
            readback=object(),
        )
    assert adapter.calls == []


def test_create_without_underscore_id_is_a_schema_failure():
    adapter = _FakeAdapter()
    public = cw.ChatWidgetsPublic(adapter, _FakeTransport({"id": "wid_created"}))
    with pytest.raises(cw.WidgetSchemaError):
        public.create_widget(
            _Tenant(),
            location_id="loc_test",
            name="Support",
            chat_type="liveChat",
            version=2,
            idempotency_key="gxo_chat-widgets-create-0123456789abcdef0123456789abcdef",
            readback=object(),
        )

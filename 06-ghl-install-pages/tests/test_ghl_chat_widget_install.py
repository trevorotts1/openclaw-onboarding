"""Offline tests for the Skill 6 chat-widget installer (WF31).

Covers duplicate-embed prevention across global/page scope, design preservation,
rollback, and the inbox/responder seam that a visible bubble must never satisfy.
"""

from __future__ import annotations

import copy
import os
import sys

import pytest

_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"
)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_chat_widget_install as install  # noqa: E402

SNIPPET = (
    '<script src="https://widgets.example.test/loader.js" '
    'data-widget-id="wid_0001"></script>'
)
EMBED = {
    "widget_id": "wid_0001",
    "script_url": "https://widgets.example.test/loader.js",
    "snippet": SNIPPET,
    "provenance": "captured_ui",
    "evidence_ref": "evidence/WF31/embed-capture.json",
}


def _page():
    return {
        "sections": [
            {
                "id": "section_1",
                "elements": [
                    {"id": "row_1", "extra": {"customCode": {"value": {"rawCustomCode": "<p>Hi</p>"}}}}
                ],
            }
        ],
        "trackingCode": {"head": "", "footerCode": "<!-- existing footer -->"},
        "popups": [],
    }


def test_page_plan_preserves_design_and_rolls_back_byte_identically():
    page = _page()
    plan = install.plan_install(page, EMBED, scope="page")
    assert plan["page_data"]["sections"] == page["sections"]
    assert plan["page_data"]["trackingCode"]["head"] == ""
    assert SNIPPET in plan["page_data"]["trackingCode"]["footerCode"]
    assert install.rollback_blob(plan) == page


def test_page_install_refuses_a_second_embed_on_the_same_page():
    first = install.plan_install(_page(), EMBED, scope="page")
    with pytest.raises(install.InstallerError) as caught:
        install.plan_install(first["page_data"], EMBED, scope="page")
    assert "widget_already_installed" in str(caught.value)


def test_page_install_refuses_when_global_scope_already_has_the_widget():
    with pytest.raises(install.InstallerError):
        install.plan_install(_page(), EMBED, scope="page", global_snippets=[SNIPPET])


def test_global_install_refuses_when_page_scope_already_has_the_widget():
    page_plan = install.plan_install(_page(), EMBED, scope="page")
    with pytest.raises(install.InstallerError):
        install.plan_install(
            page_plan["page_data"], EMBED, scope="global", global_snippets=[]
        )


def test_global_install_returns_the_page_blob_unchanged():
    page = _page()
    plan = install.plan_install(page, EMBED, scope="global", global_snippets=[])
    assert plan["global_snippets"] == [SNIPPET]
    assert plan["page_data"] == page


def test_inventory_reads_both_scopes_without_guessing_identity():
    plan = install.plan_install(_page(), EMBED, scope="page")
    found = install.inventory_embeds(
        plan["page_data"], global_snippets=[SNIPPET]
    )
    scopes = {item["scope"] for item in found}
    assert scopes == {"global", "page"}
    assert all(item["widget_id"] == "wid_0001" for item in found)


def test_save_readback_requires_single_embed_and_unchanged_design():
    page = _page()
    plan = install.plan_install(page, EMBED, scope="page")
    good = install.verify_saved(plan, plan["page_data"])
    assert good["verified"] is True
    changed = copy.deepcopy(plan["page_data"])
    changed["sections"][0]["id"] = "rewritten"
    assert install.verify_saved(plan, changed)["verified"] is False


def test_fabricated_html_form_embed_is_refused():
    bad = dict(EMBED)
    bad["snippet"] = (
        '<form action="https://widgets.example.test/loader.js">wid_0001</form>'
    )
    with pytest.raises(install.InstallerError):
        install.plan_install(_page(), bad, scope="page")


def test_rendered_checks_require_mobile_and_desktop_proof():
    checks = {name: True for name in install.widget_api().RENDER_CHECKS}
    assert install.verify_rendered(
        "wid_0001", checks, evidence_ref="evidence/render.json"
    )["passed"]
    checks["mobile_display"] = False
    assert not install.verify_rendered(
        "wid_0001", checks, evidence_ref="evidence/render.json"
    )["passed"]


# ---------------------------------------------------------------------------
# B17 / IG-WIDGET-04: inbox and responder, never a bubble
# ---------------------------------------------------------------------------

def _conversation(**overrides):
    payload = {
        "widget_id": "wid_0001",
        "location_id": "loc_test",
        "thread_id": "thread_0001",
        "inbox_id": "inbox_0001",
        "responder_kind": "ai",
        "responder_id": "bot_0001",
        "messages": [
            {"direction": "inbound", "body": "WF31 test marker", "message_id": "m1"},
            {"direction": "outbound", "body": "How can I help?", "message_id": "m2"},
        ],
        "visible_bubble_observed": True,
    }
    payload.update(overrides)
    return payload


def test_visible_bubble_alone_cannot_pass_conversation_delivery():
    result = install.verify_conversation(
        _conversation(thread_id="", inbox_id="", responder_id="", messages=[]),
        expected_widget_id="wid_0001",
        expected_location_id="loc_test",
        expected_responder_kind="ai",
    )
    assert result["passed"] is False
    assert "thread_id_present" in result["failed"]
    assert "inbox_id_present" in result["failed"]
    assert "responder_id_present" in result["failed"]


def test_conversation_reaches_intended_inbox_and_responder():
    result = install.verify_conversation(
        _conversation(),
        expected_widget_id="wid_0001",
        expected_location_id="loc_test",
        expected_responder_kind="ai",
    )
    assert result["passed"] is True
    assert result["checks"]["inbox_id_present"]
    assert result["checks"]["responder_kind_matches"]


def test_wrong_responder_kind_fails_even_with_a_thread():
    result = install.verify_conversation(
        _conversation(responder_kind="human"),
        expected_widget_id="wid_0001",
        expected_location_id="loc_test",
        expected_responder_kind="ai",
    )
    assert result["passed"] is False
    assert "responder_kind_matches" in result["failed"]


def test_handoff_and_after_hours_are_separate_required_proofs():
    base = _conversation()
    missing = install.verify_conversation(
        base,
        expected_widget_id="wid_0001",
        expected_location_id="loc_test",
        expected_responder_kind="ai",
        require_handoff=True,
        require_after_hours=True,
    )
    assert missing["passed"] is False
    assert "handoff_verified" in missing["failed"]
    assert "after_hours_verified" in missing["failed"]

    complete = install.verify_conversation(
        _conversation(
            handoff_target="human:agent_7",
            handoff_verified=True,
            after_hours_verified=True,
        ),
        expected_widget_id="wid_0001",
        expected_location_id="loc_test",
        expected_responder_kind="ai",
        require_handoff=True,
        require_after_hours=True,
    )
    assert complete["passed"] is True

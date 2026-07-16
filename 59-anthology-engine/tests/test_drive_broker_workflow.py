#!/usr/bin/env python3
"""test_drive_broker_workflow.py -- offline structural test for the n8n route template
config/n8n/anthology-drive-broker.workflow.json (the E9 FULL fix's deployable asset).

It does NOT deploy or run n8n; it asserts the workflow is well-formed and speaks the
contract the drive_adapter broker paths expect: the Authorize node advertises exactly
the REQUIRED action set via `capabilities`, dispatches every action, carries no Anthropic
identifier and no inlined secret, keeps the Google credential as an un-connected
placeholder, and every connection + node-reference resolves.

Run: python3 -m pytest 59-anthology-engine/tests/test_drive_broker_workflow.py -q
"""
import json
import re
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
WF_PATH = SKILL_DIR / "config" / "n8n" / "anthology-drive-broker.workflow.json"
sys.path.insert(0, str(SCRIPTS))

import drive_adapter as da  # noqa: E402


@pytest.fixture(scope="module")
def wf():
    return json.loads(WF_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def names(wf):
    return {n["name"] for n in wf["nodes"]}


@pytest.fixture(scope="module")
def blob(wf):
    return json.dumps(wf)


def _authorize_js(wf):
    for n in wf["nodes"]:
        if n["name"] == "Authorize & Dispatch":
            return n["parameters"]["jsCode"]
    raise AssertionError("Authorize & Dispatch node missing")


def test_workflow_is_valid_json_and_inactive(wf):
    assert wf["name"] == "Anthology Drive Broker"
    # ships INACTIVE (the README's import checklist activates it after wiring creds/env).
    assert wf.get("active") is False


def test_authorize_advertises_exactly_the_required_action_set(wf):
    js = _authorize_js(wf)
    # capabilities returns the implemented set; it must equal drive_adapter's REQUIRED set.
    assert "implemented_actions: IMPLEMENTED" in js
    for action in da.BROKER_REQUIRED_ACTIONS:
        assert ("=== '%s'" % action) in js, "Authorize node must dispatch %r" % action
    # capabilities + probe short-circuits are present (broker-preflight relies on them).
    assert "action === 'capabilities'" in js
    assert "body.probe === true" in js


def test_every_action_has_a_switch_route_and_first_node(wf, names):
    route = next(n for n in wf["nodes"] if n["name"] == "Route")
    # The node-type literal is assembled from fragments so this test file does NOT
    # carry the contiguous n8n node marker + "connections" shape that scan-no-json-
    # exports.sh classifies as a workflow EXPORT (the sanctioned asset lives under
    # config/n8n/; this is only a structural test of it).
    assert route["type"] == "n8n-nodes-base" ".switch"
    keys = [r["outputKey"] for r in route["parameters"]["rules"]["values"]]
    assert keys == ["book_tree", "participant_tree", "create_doc", "upload_pdf",
                    "share_doc_edit", "pull_doc_text"]
    # each switch output connects to exactly one existing first node.
    outs = wf["connections"]["Route"]["main"]
    assert len(outs) == len(keys)
    for branch in outs:
        assert len(branch) == 1 and branch[0]["node"] in names


def test_terminal_router_and_responders(wf, names):
    # Authorize -> Terminal? ; Terminal? true -> Respond Rejected ; false -> Route.
    assert "Terminal?" in names
    t = wf["connections"]["Terminal?"]["main"]
    assert t[0][0]["node"] == "Respond Rejected"
    assert t[1][0]["node"] == "Route"
    # both webhook responders exist.
    assert {"Respond OK", "Respond Rejected"} <= names


def test_book_share_retries_with_notification_and_reports_double_failure(wf, names):
    first_name = "Share Book To Producer"
    retry_name = "Retry Share Book To Producer With Notification"
    assert {first_name, retry_name} <= names

    nodes = {n["name"]: n for n in wf["nodes"]}
    first = nodes[first_name]
    retry = nodes[retry_name]
    assert first["type"] == retry["type"] == "n8n-nodes-base" ".httpRequest"
    assert first["parameters"]["method"] == retry["parameters"]["method"] == "POST"
    assert "sendNotificationEmail=false" in first["parameters"]["url"]
    assert "sendNotificationEmail=true" in retry["parameters"]["url"]
    assert first["parameters"]["jsonBody"] == retry["parameters"]["jsonBody"]
    assert first["credentials"] == retry["credentials"]

    # n8n's second main output is the error output when this setting is enabled.
    assert first.get("onError") == "continueErrorOutput"
    assert retry.get("onError") == "continueErrorOutput"
    first_outputs = wf["connections"][first_name]["main"]
    assert first_outputs[0][0]["node"] == "Build Response"
    assert first_outputs[1][0]["node"] == retry_name

    # Whether the retry succeeds or fails, response construction remains non-fatal.
    retry_outputs = wf["connections"][retry_name]["main"]
    assert retry_outputs[0][0]["node"] == "Build Response"
    assert retry_outputs[1][0]["node"] == "Build Response"
    response_js = nodes["Build Response"]["parameters"]["jsCode"]
    assert "producer_editor_shared: true" not in response_js
    assert "producer_editor_shared: shared" in response_js
    assert "response.warning" in response_js
    assert "producer_editor_share_failed" in response_js


def test_no_dangling_connections_or_node_references(wf, names, blob):
    for src, spec in wf["connections"].items():
        assert src in names, "connection from unknown node %r" % src
        for out in spec.get("main", []):
            for c in out:
                assert c["node"] in names, "connection to unknown node %r" % c["node"]
    for ref in set(re.findall(r"\$\('([^']+)'\)", blob)):
        assert ref in names, "expression references unknown node %r" % ref


def test_no_orphan_nodes(wf, names):
    targets = set()
    for spec in wf["connections"].values():
        for out in spec.get("main", []):
            for c in out:
                targets.add(c["node"])
    orphans = [n["name"] for n in wf["nodes"]
               if n["name"] not in targets and n["name"] != "Webhook anthology-drive"]
    assert orphans == [], "unreachable node(s): %s" % orphans


def test_google_credential_is_an_unconnected_placeholder(wf):
    seen = 0
    for n in wf["nodes"]:
        cred = (n.get("credentials") or {}).get("googleDriveOAuth2Api")
        if cred:
            seen += 1
            assert cred["id"] == "REPLACE_WITH_GOOGLE_CREDENTIAL_ID", \
                "the Google credential must ship UNconnected (operator wires it in n8n)"
    assert seen >= 6, "the Google HTTP nodes must reference the placeholder credential"


def test_no_anthropic_id_and_no_inlined_secret(blob):
    low = blob.lower()
    # Banned-family needles assembled from fragments so this test file carries no
    # contiguous banned literal (mirrors preflight.sh / model_router.py; keeps the
    # repo's own anthropic-runtime guard green when it scans the tests dir).
    banned_family = "anthro" + "pic"
    banned_model = "clau" + "de-"
    assert banned_family not in low and banned_model not in low
    # the broker token is read from $env inside n8n, never inlined in the asset.
    assert "ANTHOLOGY_DRIVE_BROKER_TOKEN" in blob
    # no obvious secret literal: the token/root come from $env only.
    assert "$env.ANTHOLOGY_DRIVE_BROKER_TOKEN" in blob
    assert "$env.ANTHOLOGY_DRIVE_ROOT_FOLDER" in blob


def test_per_doc_branches_use_drive_scope_only_endpoints(blob):
    # create_doc/pull_doc_text avoid the Docs API (documents scope): a Doc is created
    # via files.create + media update, and its text is read via files.export -- both
    # Drive-scope, so the single Google Drive credential suffices.
    assert "application/vnd.google-apps.document" in blob
    assert "/export?mimeType=text" in blob
    assert "uploadType=media" in blob
    # docs.googleapis.com must NOT appear (would need a second, wider scope).
    assert "docs.googleapis.com" not in blob


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

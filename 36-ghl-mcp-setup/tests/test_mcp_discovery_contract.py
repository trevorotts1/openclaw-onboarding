"""WF15 / A19 + IG-PROJECT-09 documentation contract checks.

These tests assert externally meaningful documentation behavior, not the presence of a
banner string:

* the four documented MCP tools are the only catalog and are taught in a fixed order;
* discovery evidence binds operation -> connection -> location -> scopes -> schema version;
* a no-match is a catalog result, never a capability verdict;
* the MCP client URL stays on /v2 (no invented /v3 or /mcp/projects server);
* OAuth is the MCP credential; the location PIT is the REST credential;
* a worker without injected tools uses the shared CLI;
* single-location vs bulk connection availability is distinguished;
* Projects beta / Projects MCP discovery is separate from the Workflows beta;
* the onboarding authorization profiles cover the fourteen families with honest states;
* the retired community MCP stays retired and no new token creator appears.

Run: python3 -m pytest -q 36-ghl-mcp-setup/tests/test_mcp_discovery_contract.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parent

FOUR_TOOLS = [
    "list_locations",
    "search_operations",
    "describe_operation",
    "execute_operation",
]

FAMILIES = [
    "courses",
    "course_assessments",
    "course_offers_and_enrollment",
    "workflow_authoring",
    "workflow_validation",
    "workflow_logs_and_statistics",
    "meeting_rooms",
    "native_voice_ai",
    "native_conversation_ai",
    "agent_studio_flow_agents",
    "knowledge_bases",
    "chat_widgets",
    "projects",
    "marketing_quiz_builder",
]

NEGATION = (
    "never",
    "do not",
    "don't",
    "not a",
    "no ",
    "does not",
    "there is no",
    "cannot",
    "must not",
)


def read(name: str) -> str:
    path = SKILL_DIR / name
    assert path.is_file(), f"missing owned file: {path}"
    return path.read_text(encoding="utf-8")


def paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def section(text: str, heading: str) -> str:
    """Return the body of one markdown H2/H3 section up to the next heading of any level."""
    start = text.find(heading)
    assert start != -1, f"missing section: {heading}"
    after = text[start + len(heading):]
    nxt = re.search(r"^#{2,3} ", after, re.MULTILINE)
    return after[: nxt.start()] if nxt else after


def test_a19_documented_four_tool_catalog_is_the_only_catalog() -> None:
    skill = read("SKILL.md")
    instructions = read("INSTRUCTIONS.md")
    full = read("ghl-mcp-setup-full.md")
    for doc_name, doc in (
        ("SKILL.md", skill),
        ("INSTRUCTIONS.md", instructions),
        ("ghl-mcp-setup-full.md", full),
    ):
        for tool in FOUR_TOOLS:
            assert tool in doc, f"{doc_name} never names the documented tool {tool}"
    # The legacy JSON-RPC names must be labeled unverified, not taught as the current catalog.
    assert "`search` and `fetch` are legacy names" in skill
    assert "UNVERIFIED" in instructions


def test_a19_discovery_order_is_explicit_and_ordered() -> None:
    body = section(read("SKILL.md"), "### Operation discovery")
    positions = [body.index(tool) for tool in FOUR_TOOLS]
    assert positions == sorted(positions), f"discovery order is not {FOUR_TOOLS}: {positions}"


def test_a19_evidence_binding_covers_connection_location_scopes_schema() -> None:
    body = section(read("SKILL.md"), "### Operation discovery")
    for requirement in (
        "authenticated connection identity",
        "location_id",
        "granted scopes",
        "schema/contract version",
        "capture time",
    ):
        assert requirement in body, f"evidence binding omits {requirement!r}"


def test_a19_no_match_is_a_catalog_result_not_a_capability_verdict() -> None:
    for name in ("SKILL.md", "INSTRUCTIONS.md", "GHL-LOOKUP-SOP.md", "EXAMPLES.md"):
        doc = read(name)
        lowered = doc.lower()
        assert "no-match" in lowered or "no match" in lowered, f"{name} has no no-match semantics"
        assert "catalog result" in lowered, f"{name} does not call a no-match a catalog result"
        assert "never proof" in lowered or "not proof" in lowered, (
            f"{name} does not forbid reading a no-match as nonexistence"
        )


def test_a19_invented_mcp_endpoints_appear_only_inside_negations() -> None:
    forbidden = ("/mcp/projects", "/mcp/.../v3")
    for name in ("SKILL.md", "INSTRUCTIONS.md", "GHL-LOOKUP-SOP.md", "EXAMPLES.md", "ghl-mcp-setup-full.md"):
        for para in paragraphs(read(name)):
            for needle in forbidden:
                if needle in para:
                    flat = " ".join(para.lower().split())
                    assert any(token in flat for token in NEGATION), (
                        f"{name} teaches {needle} without forbidding it: {para[:200]!r}"
                    )
    # And the documented suffix is asserted positively.
    assert "`/v2`" in read("SKILL.md")


def test_a19_no_global_version_literal_is_taught() -> None:
    forbidden = [
        "Always include Version header: 2021-07-28",
        "Version header 2021-07-28 is MANDATORY",
        "mandatory `Version: 2021-07-28` header on every GHL API request",
        "Version: 2021-07-28 in API calls",
    ]
    for rel in (
        "36-ghl-mcp-setup/SKILL.md",
        "36-ghl-mcp-setup/INSTRUCTIONS.md",
        "36-ghl-mcp-setup/GHL-LOOKUP-SOP.md",
        "36-ghl-mcp-setup/ghl-mcp-setup-full.md",
        "05-ghl-setup/CORE_UPDATES.md",
        "05-ghl-setup/QC.md",
        "05-ghl-setup/INSTALL.md",
        "05-ghl-setup/INSTRUCTIONS.md",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, f"{rel} still teaches a global Version literal: {phrase!r}"
    # The replacement rule must be present in the version-authority documents.
    for name in ("GHL-LOOKUP-SOP.md", "ghl-mcp-setup-full.md"):
        doc = read(name)
        assert "per operation" in doc.lower(), f"{name} lost the per-operation Version rule"


def test_a19_worker_without_tools_uses_shared_cli_and_never_mcp_names() -> None:
    for name in ("SKILL.md", "INSTRUCTIONS.md", "GHL-LOOKUP-SOP.md"):
        doc = read(name)
        flat = " ".join(doc.lower().split())
        assert "no mcp tool injection" in flat or "no injected mcp tools" in flat, (
            f"{name} does not state that workers receive no MCP tools"
        )
        assert "caf" in doc, f"{name} does not name the shared CLI route"
    for para in paragraphs(read("SKILL.md")):
        if "ghl-mcp__*" in para:
            flat = " ".join(para.lower().split())
            assert any(token in flat for token in NEGATION), (
                "SKILL.md names ghl-mcp__* without forbidding it in a worker"
            )


def test_a19_single_location_and_bulk_connection_are_distinguished() -> None:
    skill = " ".join(read("SKILL.md").lower().split())
    instructions = " ".join(read("INSTRUCTIONS.md").lower().split())
    full = " ".join(read("ghl-mcp-setup-full.md").lower().split())
    for doc_name, doc in (("SKILL.md", skill), ("INSTRUCTIONS.md", instructions), ("full", full)):
        assert "single-location" in doc, f"{doc_name} omits the single-location default"
        assert "bulk" in doc, f"{doc_name} omits agency-wide bulk availability"
        assert "separate" in doc, f"{doc_name} does not separate bulk from the default"


def test_ig_project_09_projects_discovery_binds_evidence_and_keeps_beta_separate() -> None:
    examples = read("EXAMPLES.md")
    block = section(examples, "### Projects discovery")
    assert "search_operations" in block and "describe_operation" in block
    assert "no-match" in block.lower() or "no match" in block.lower()
    assert "/v2" in block
    assert "does not enable Projects" in block or "never enables Projects" in block

    record = section(examples, "## Discovery evidence")
    for field in (
        '"connection_id"',
        '"location_id"',
        '"operation_id"',
        '"granted_scopes"',
        '"operation_schema_version"',
        '"captured_at"',
    ):
        assert field in record, f"discovery evidence template omits {field}"

    skill = read("SKILL.md")
    assert "does not enable Projects" in skill or "never enables Projects" in skill


def test_onboarding_authorization_profiles_cover_fourteen_families_honestly() -> None:
    data = json.loads(read("PREREQS.json"))
    profiles = data["authorization_profiles"]
    assert profiles["schema"] == "onboarding-authorization-profile.v1"
    assert profiles["derivation"] == "operation-derived"

    layers = profiles["enabled_layers"]
    assert set(layers) == {
        "repository_support",
        "client_installation",
        "account_availability",
        "operational_activation",
    }, "the four meanings of enabled are not the four required layers"

    assert profiles["authorization_states"] == [
        "installed",
        "configured",
        "available",
        "authorized",
        "tested",
        "active",
        "blocked",
    ]

    listed = [p["family"] for p in profiles["profiles"]]
    assert listed == FAMILIES, f"profile families drifted: {listed}"

    for profile in profiles["profiles"]:
        assert profile["discovery"]["discovered_operation_ids"] == [], (
            f"{profile['family']} claims discovered operations without an evidence record"
        )
        assert profile["discovery"]["discovery_state"] == "not_run", (
            f"{profile['family']} claims a discovery run that did not happen"
        )
        assert profile["authorization_state"] == "unverified", (
            f"{profile['family']} claims authorization without an evidence record"
        )
        for layer in layers:
            assert layer in profile["enabled_layers"], (
                f"{profile['family']} omits the {layer} layer"
            )
        assert profile["owner_lane"].startswith("WF"), (
            f"{profile['family']} has no owning lane"
        )


def test_onboarding_profiles_never_fabricate_operation_ids() -> None:
    profiles = json.loads(read("PREREQS.json"))["authorization_profiles"]
    operation_id_shape = re.compile(r"^[a-z][a-z0-9_]*\.[a-z]")
    for profile in profiles["profiles"]:
        for intent in profile["discovery"]["query_intents"]:
            assert not operation_id_shape.match(intent), (
                f"{profile['family']} invents an operation id '{intent}' from a REST-shaped slug"
            )
    rule = profiles["discovery_rule"]
    assert "search_operations" in rule and "describe_operation" in rule
    assert "never proof" in rule


def test_retired_community_mcp_stays_retired() -> None:
    for name in ("SKILL.md", "INSTRUCTIONS.md", "EXAMPLES.md", "QC.md"):
        doc = read(name)
        assert "ghl-community-mcp" in doc
        assert "RETIRED" in doc or "retired" in doc
    for para in paragraphs(read("INSTRUCTIONS.md")):
        low = " ".join(para.lower().split())
        if "community" in low and any(verb in low for verb in ("install", "restart", "probe", "rebuild")):
            assert any(token in low for token in NEGATION), (
                f"INSTRUCTIONS.md teaches a community-MCP action without forbidding it: {para[:200]!r}"
            )


def test_no_new_token_creator_is_introduced() -> None:
    skill = read("SKILL.md").lower()
    full = read("ghl-mcp-setup-full.md").lower()
    assert "no token creator" in skill or "no new token creator" in skill
    assert "no token creator" in full or "no new token creator" in full


def test_qc_documents_every_discovery_obligation() -> None:
    qc = read("QC.md")
    for needle in (
        "Discovery follows the documented order",
        "bound to the authenticated connection",
        "catalog result for (connection, location, date)",
        "`/mcp/.../v3` and no `/mcp/projects`",
        "never presented as an equivalent MCP auth path",
        "Single-location connection vs agency-wide bulk",
        "Workflows beta form is never treated as enabling Projects",
        "shared REST CLI (`caf`) with no MCP tool injection",
        "fourteen families, the four meanings of enabled",
        "No new token creator is introduced",
    ):
        assert needle in qc, f"QC.md lost the obligation: {needle!r}"

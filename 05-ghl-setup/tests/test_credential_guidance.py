"""WF15 credential/setup guidance checks for Skill 05.

Skill 05 is the credential foundation. These tests keep it consistent with the WF15
contract:

* the Version header is selected PER OPERATION, never one global literal;
* the location PIT is the public REST credential and is not an MCP credential;
* the official MCP is OAuth with four documented tools;
* the retired community MCP is not presented as a route;
* the documented REST wrapper does not hardcode a global Version literal.

Run: python3 -m pytest -q 05-ghl-setup/tests/test_credential_guidance.py
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]

GLOBAL_VERSION_CLAIMS = [
    "Always include Version header: 2021-07-28",
    "Version header 2021-07-28 is MANDATORY",
    "mandatory `Version: 2021-07-28` header on every GHL API request",
    "Version: 2021-07-28 in API calls",
    "Required header: Version: 2021-07-28",
    "verify the Version header is exactly: 2021-07-28",
]


def read(name: str) -> str:
    path = SKILL_DIR / name
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def test_every_guidance_file_states_the_per_operation_version_rule() -> None:
    for name in ("CORE_UPDATES.md", "QC.md", "INSTALL.md", "INSTRUCTIONS.md"):
        doc = read(name)
        lowered = " ".join(doc.lower().split())
        assert "per operation" in lowered, f"{name} lost the per-operation Version rule"
        assert "one documented value" in lowered, (
            f"{name} no longer says 2021-07-28 is one documented value"
        )


def test_no_global_version_claim_remains() -> None:
    for name in ("SKILL.md", "CORE_UPDATES.md", "QC.md", "INSTALL.md", "INSTRUCTIONS.md"):
        doc = read(name)
        for claim in GLOBAL_VERSION_CLAIMS:
            assert claim not in doc, f"{name} still teaches a global Version literal: {claim!r}"


def test_mcp_credential_class_is_separate_from_the_rest_pit() -> None:
    core = read("CORE_UPDATES.md")
    instructions = read("INSTRUCTIONS.md")
    for name, doc in (("CORE_UPDATES.md", core), ("INSTRUCTIONS.md", instructions)):
        assert "OAuth" in doc, f"{name} does not state that the official MCP uses OAuth"
        assert "PIT" in doc, f"{name} does not name the location PIT"
        assert "community" in doc.lower() and "retired" in doc.lower(), (
            f"{name} does not record the community MCP retirement"
        )
    # The PIT is the REST credential, stated by this skill's own guidance.
    plain = re.sub(r"[*`_]", "", instructions)
    pit_is_rest = ("public REST" in plain or "REST credential" in plain)
    assert pit_is_rest, "INSTRUCTIONS.md no longer identifies the PIT as the REST credential"
    assert "never send the pit to an mcp endpoint" in " ".join(plain.lower().split()) or (
        "never send the pit to an mcp endpoint" in " ".join(core.lower().split())
    )


def test_community_mcp_is_never_presented_as_a_route() -> None:
    instructions = read("INSTRUCTIONS.md")
    flat = " ".join(instructions.lower().split())
    assert "community ghl mcp" in flat
    assert "retired" in flat
    assert "prefer the official ghl mcp and community ghl mcp" not in flat
    # It may only be mentioned alongside the retirement/negation.
    for para in instructions.split("\n\n"):
        low = " ".join(para.lower().split())
        if "community ghl mcp" in low:
            assert any(token in low for token in ("retired", "not a route", "never", "do not")), (
                f"INSTRUCTIONS.md mentions the community MCP without retiring it: {para[:200]!r}"
            )


def test_rest_wrapper_does_not_hardcode_a_global_version() -> None:
    instructions = read("INSTRUCTIONS.md")
    start = instructions.find("ghl_request() {")
    assert start != -1, "the documented ghl_request wrapper is missing"
    end = instructions.find("\n}", start)
    assert end != -1, "the documented ghl_request wrapper is not closed"
    body = instructions[start:end]
    assert 'Version:' not in body, (
        "ghl_request hardcodes a Version header; the caller must supply the per-operation literal"
    )
    assert 'Authorization: Bearer $GHL_TOKEN' in body

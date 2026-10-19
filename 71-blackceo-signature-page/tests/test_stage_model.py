#!/usr/bin/env python3
"""Stage-model reconciliation pin (S71-09).

The stage model lives in ONE place: references/stage-contract.json (the
manifest). Every surface that enumerates, validates, or reports stages
must state the same model:

- FIFTEEN stage IDs, in the manifest's stage_order;
- the last, automation-wiring, is conditional: required only when the
  intake records publish_target "ghl" and automation_scope "workflows";
  when it does not apply, the gate records it not_applicable in state
  and REPORT.md, citing the intake values (never silently absent).

This module loads the manifest and asserts the enumerating surfaces
agree with it. If a surface drifts (a stage added, dropped, renamed,
or the conditional dropped), this test fails by name.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REFERENCES = ROOT / "references"

EXPECTED_ORDER = [
    "intake",
    "copy",
    "font-action-plan",
    "desktop-wireframe",
    "mobile-tablet",
    "visual-mockup",
    "image-inventory-prompts",
    "image-generation-qc",
    "image-map-upload",
    "design-board",
    "final-mockups",
    "responsive-html",
    "ghl-install-test",
    "publish-verify",
    "automation-wiring",
]
CONDITIONAL_STAGE = "automation-wiring"
CONDITIONAL_RULE = ('intake.publish_target == "ghl" and '
                    'intake.automation_scope == "workflows"')
BROWSER_STAGES = ("ghl-install-test", "publish-verify", "automation-wiring")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def manifest():
    return json.loads(
        (REFERENCES / "stage-contract.json").read_text(encoding="utf-8"))


def test_manifest_model():
    contract = manifest()
    assert contract["stage_order"] == EXPECTED_ORDER, contract["stage_order"]
    aw = contract["stages"][CONDITIONAL_STAGE]
    assert aw["conditional"]["required_when"] == CONDITIONAL_RULE
    for sid, entry in contract["stages"].items():
        if sid != CONDITIONAL_STAGE:
            assert "conditional" not in entry, f"{sid} unexpectedly conditional"
    for sid in BROWSER_STAGES:
        assert contract["stages"][sid].get("uses_browser") is True, sid
    print("PASS manifest: 15 stages in order; automation-wiring conditional "
          "on ghl + workflows; browser stages flagged")


def test_skill_md():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(
        r"Stage IDs \(canonical, from `references/stage-contract\.json`\):"
        r"\s*\n\s*`([^`]+)`", text)
    assert m, "SKILL.md stage-ID enumeration not found"
    ids = [s.strip() for s in m.group(1).split(",")]
    assert ids == manifest()["stage_order"], ids
    assert "FIFTEEN stage IDs" in text
    assert 'publish_target: "ghl"' in text
    assert 'automation_scope: "workflows"' in text
    assert "not_applicable" in text
    print("PASS SKILL.md: enumeration equals stage_order; conditional stated")


def test_artifact_contracts():
    text = (REFERENCES / "artifact-contracts.md").read_text(encoding="utf-8")
    assert "The workflow has FIFTEEN stage IDs" in text
    section = text.split("## Workflow-state JSON", 1)[1]
    block = section.split("```json", 1)[1].split("```", 1)[0]
    state = json.loads(block)
    assert list(state["stages"].keys()) == manifest()["stage_order"]
    print("PASS artifact-contracts.md: FIFTEEN stated; workflow-state "
          "example carries every stage in order")


def test_validate_state():
    vs = load_module("validate_state", SCRIPTS / "validate_state.py")
    order = manifest()["stage_order"]
    assert list(vs.ORDER) == order, vs.ORDER

    def full_state(ids):
        return {
            "page_version": "standard",
            "current_stage": ids[-1],
            "stages": {sid: {"status": "ready", "attempts": 0}
                       for sid in ids},
        }

    # Behavioral pin: a complete 15-stage state validates; the same state
    # minus automation-wiring is rejected as missing the stage (the old
    # hardcoded 13-stage list accepted it and rejected the 14-stage one).
    assert vs.validate(full_state(order)) == []
    errs = vs.validate(full_state(order[:-1]))
    assert any("Missing stages: automation-wiring" in e for e in errs), errs
    print("PASS validate_state.py: ORDER derived from the manifest; a state "
          "without automation-wiring is rejected")


def test_fixtures():
    order = set(manifest()["stage_order"])
    for name in ("state-valid.json", "state-invalid.json"):
        data = json.loads(
            (ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))
        assert set(data["stages"].keys()) == order, name
    print("PASS fixtures: state-valid.json and state-invalid.json carry "
          "all 15 stages")


def stage_enums(node, out):
    if isinstance(node, dict):
        enum = node.get("enum")
        if isinstance(enum, list) and "intake" in enum:
            out.append(set(enum))
        for value in node.values():
            stage_enums(value, out)
    elif isinstance(node, list):
        for value in node:
            stage_enums(value, out)


def test_schemas():
    order = set(manifest()["stage_order"])
    for name in ("report-json.schema.json", "run-events.schema.json"):
        schema = json.loads((REFERENCES / name).read_text(encoding="utf-8"))
        enums = []
        stage_enums(schema, enums)
        assert enums, f"{name}: no stage enum found"
        for enum in enums:
            assert enum == order, (name, enum)
    print("PASS schemas: report-json and run-events stage enums equal "
          "stage_order")


def test_stage_gate():
    gate = load_module("stage_gate", SCRIPTS / "stage_gate.py")
    assert list(gate.ORDER) == manifest()["stage_order"]
    src = (SCRIPTS / "stage_gate.py").read_text(encoding="utf-8")
    assert "when its contract entry lands" not in src
    print("PASS stage_gate.py: ORDER loaded from the manifest; no stale "
          "pre-landing wording")


def test_swarm_plan():
    text = (REFERENCES / "swarm-plan.md").read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines()
            if ln.startswith("| automation-wiring |")]
    assert rows, "swarm-plan per-stage table has no automation-wiring row"
    assert "not_applicable" in rows[0]
    print("PASS swarm-plan.md: per-stage table carries the conditional stage")


def test_browser_hygiene_doc():
    text = (REFERENCES / "browser-hygiene.md").read_text(encoding="utf-8")
    assert "when that stage's contract entry lands" not in text
    section = text.split("## Which stages are browser-using", 1)[1]
    section = section.split("\n## ", 1)[0]
    for sid in BROWSER_STAGES:
        assert f"`{sid}`" in section, sid
    print("PASS browser-hygiene.md: browser-using stages match the "
          "contract flags")


def test_pointer_readme_flow():
    path = (ROOT / "repo-integration" / "universal-sops" /
            "signature-page-craft" / "README.md")
    text = path.read_text(encoding="utf-8")
    flow = [ln for ln in text.splitlines() if ln.startswith("`intake ->")]
    assert flow and "automation-wiring" in flow[0]
    print("PASS signature-page-craft README: production flow ends with "
          "the conditional automation-wiring step")


def main():
    tests = [
        test_manifest_model,
        test_skill_md,
        test_artifact_contracts,
        test_validate_state,
        test_fixtures,
        test_schemas,
        test_stage_gate,
        test_swarm_plan,
        test_browser_hygiene_doc,
        test_pointer_readme_flow,
    ]
    for test in tests:
        test()
    print(f"PASS: stage model pinned across {len(tests)} surfaces")
    return 0


if __name__ == "__main__":
    sys.exit(main())

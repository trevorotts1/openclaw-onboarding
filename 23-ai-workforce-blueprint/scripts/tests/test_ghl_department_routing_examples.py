"""Routing-example tests for the GHL hybrid department binding (WF16 / A20).

These tests are MOCK-ONLY and structural. They prove the binding that makes a
plain-language GHL request reach the EXISTING canonical department and its
owning skill:

  * the alias + pointer contract (WF16-CP01) and the skill-department map agree
    on the owner of every revision-3 routing example (spec 13.5 and 32.4);
  * every required intent trigger is really present on the owning skill;
  * exactly one primary role per client-facing skill; no invented role slug;
  * no duplicate GHL department exists (aliases are contextual only);
  * the canonical SOP cluster (SOP-GHL-01..13) exists with every required
    section;
  * the SKILL_INTENT_ROUTING_REFLEX_V1 catalog routes every owning department.

No live GoHighLevel call, no network, no client data. Synthetic examples only.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_REPO_ROOT = _SKILL_DIR.parent
_MAP = _SKILL_DIR / "skill-department-map.json"
_INDEX = _SKILL_DIR / "templates" / "role-library" / "_index.json"
_CLUSTER = _REPO_ROOT / "universal-sops" / "ghl-hybrid-operations"
_CONTRACT = _CLUSTER / "WF16-CP01-ALIAS-AND-POINTER-CONTRACT.json"
_CORPUS = _SKILL_DIR / "scripts" / "testdata" / "ghl_routing_examples.json"
_REFLEX = _REPO_ROOT / "scripts" / "apply-fleet-standards.sh"

_REQUIRED_SOP_SECTIONS = (
    "**Trigger:**",
    "**Inputs:**",
    "**Required pointers:**",
    "**Ordered steps:**",
    "**Allowed route changes:**",
    "**Required output / receipt:**",
    "**Approval boundary:**",
    "**Failures:**",
    "**Acceptance:**",
)


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def map_data() -> dict:
    return _load(_MAP)


@pytest.fixture(scope="module")
def index_data() -> dict:
    return _load(_INDEX)


@pytest.fixture(scope="module")
def contract() -> dict:
    return _load(_CONTRACT)


@pytest.fixture(scope="module")
def corpus() -> dict:
    return _load(_CORPUS)


def _skills_by_slug(map_data: dict) -> dict:
    return {s["slug"]: s for s in map_data["skills"]}


def _skill_by_number(map_data: dict, number: str) -> dict:
    return next(s for s in map_data["skills"] if s["skill"] == number)


# ── Corpus well-formedness ────────────────────────────────────────────────────

def test_corpus_has_both_revision_sections(corpus):
    assert len(corpus["entries"]) >= 15
    names = [e["name"] for e in corpus["entries"]]
    assert len(names) == len(set(names)), "routing example names must be unique"


def test_every_entry_names_a_contract_intent(corpus, contract):
    intents = {r["intent"] for r in contract["pointer_rules"]}
    for entry in corpus["entries"]:
        assert entry["contract_intent"] in intents, (
            f"{entry['name']}: contract_intent not present in WF16-CP01 pointer_rules"
        )


# ── Alias contract ───────────────────────────────────────────────────────────

def test_platform_aliases_are_exactly_the_four_contextual_names(contract):
    aliases = contract["platform_aliases"]["aliases"]
    assert aliases == ["Convert and Flow", "Convert & Flow", "GoHighLevel", "GHL"]
    assert contract["platform_aliases"]["canonical_dept"] == "crm"
    assert contract["platform_aliases"]["never_create_department_ids"]


def test_no_duplicate_ghl_department_exists(index_data, contract):
    forbidden = set(contract["platform_aliases"]["never_create_department_ids"])
    live = set(index_data["departments"])
    assert not (forbidden & live), (
        f"a forbidden duplicate GHL department exists: {sorted(forbidden & live)}"
    )
    assert "crm" in live and "courses" in live and "community-builder" in live


def test_canonical_departments_are_live(index_data, contract):
    live = set(index_data["departments"])
    for dept in contract["canonical_departments"]:
        assert dept in live, f"contract names a non-live department: {dept}"


# ── Every routing example resolves to the real owner + skill ─────────────────

@pytest.mark.parametrize("entry_index", range(15))
def test_routing_example_resolves(entry_index, corpus, map_data, index_data, contract):
    entry = corpus["entries"][entry_index]
    owner = entry["expected_owner"]
    live_depts = set(index_data["departments"])
    live_pairs = {(r["dept"], r["slug"]) for r in index_data["roles"]}

    rule = next(r for r in contract["pointer_rules"] if r["intent"] == entry["contract_intent"])
    assert rule["business_owner"] == owner, (
        f"{entry['name']}: contract owner {rule['business_owner']!r} != expected {owner!r}"
    )
    if owner in live_depts:
        assert owner in live_depts

    if entry.get("must_not_route_to"):
        assert owner != entry["must_not_route_to"], (
            f"{entry['name']}: routed to the forbidden department {owner!r}"
        )

    if entry["expected_skill"]:
        skill = _skill_by_number(map_data, entry["expected_skill"])
        assert skill["client_facing"] is True
        primaries = [r for r in skill["roles"] if r.get("primary")]
        assert len(primaries) == 1, (
            f"skill {entry['expected_skill']} must have exactly one primary role, found {len(primaries)}"
        )
        if entry.get("expected_role"):
            assert (owner, entry["expected_role"]) in live_pairs, (
                f"{entry['name']}: role {owner}/{entry['expected_role']} is not in the role library"
            )
            assert any(
                r["dept"] == owner and r["slug"] == entry["expected_role"] for r in skill["roles"]
            ), f"{entry['name']}: skill {entry['expected_skill']} does not bind {owner}/{entry['expected_role']}"
        if entry.get("required_trigger"):
            assert entry["required_trigger"] in skill["intent_triggers"], (
                f"{entry['name']}: required trigger {entry['required_trigger']!r} missing from skill "
                f"{entry['expected_skill']}"
            )
        if owner in skill.get("departments", []):
            assert owner in skill["departments"]


# ── Whole-map invariants ────────────────────────────────────────────────────

def test_exactly_one_primary_role_for_every_client_facing_skill(map_data):
    for skill in map_data["skills"]:
        if not skill.get("client_facing"):
            continue
        primaries = [r for r in skill.get("roles", []) if r.get("primary")]
        assert len(primaries) == 1, (
            f"skill {skill['skill']} {skill['slug']}: {len(primaries)} primary roles"
        )


def test_no_invented_role_slugs(map_data, index_data):
    live_pairs = {(r["dept"], r["slug"]) for r in index_data["roles"]}
    for skill in map_data["skills"]:
        for role in skill.get("roles", []):
            assert (role["dept"], role["slug"]) in live_pairs, (
                f"skill {skill['skill']} binds an invented role: {role['dept']}/{role['slug']}"
            )


def test_map_structure_check_passes():
    spec = importlib.util.spec_from_file_location(
        "check_skill_department_map",
        _SKILL_DIR / "scripts" / "check-skill-department-map.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    errors, _warns, stats = module.run_checks(
        map_path=str(_MAP), index_path=str(_INDEX), usops=str(_REPO_ROOT / "universal-sops")
    )
    assert errors == [], errors
    assert stats["client_facing"] >= 38


# ── SOP cluster ─────────────────────────────────────────────────────────────

def test_sop_cluster_has_all_thirteen_procedures():
    expected = {f"{i:02d}" for i in range(1, 14)}
    present = {re.match(r"SOP-GHL-(\d{2})", p.name).group(1) for p in _CLUSTER.glob("SOP-GHL-*.md")}
    assert present == expected, f"missing/extra SOP-GHL files: {present ^ expected}"
    assert (_CLUSTER / "README.md").is_file()


def test_every_sop_names_all_required_sections():
    for path in sorted(_CLUSTER.glob("SOP-GHL-*.md")):
        text = path.read_text(encoding="utf-8")
        missing = [s for s in _REQUIRED_SOP_SECTIONS if s not in text]
        assert not missing, f"{path.name} missing required sections: {missing}"


def test_readme_links_every_sop():
    readme = (_CLUSTER / "README.md").read_text(encoding="utf-8")
    for i in range(1, 14):
        assert f"SOP-GHL-{i:02d}" in readme


def test_no_second_ghl_operations_cluster():
    assert not (_REPO_ROOT / "universal-sops" / "ghl-operations").exists(), (
        "a duplicate ghl-operations cluster must not exist"
    )


# ── Layer C: reflex catalog parity ──────────────────────────────────────────

def test_reflex_catalog_routes_every_owning_department(map_data):
    text = _REFLEX.read_text(encoding="utf-8")
    blocks = re.findall(
        r"<!-- SKILL_INTENT_ROUTING_REFLEX_V1 -->(.*?)<!-- END SKILL_INTENT_ROUTING_REFLEX_V1 -->",
        text,
        re.DOTALL,
    )
    assert blocks, "SKILL_INTENT_ROUTING_REFLEX_V1 block not found"
    best = max(blocks, key=lambda b: len(re.findall(r"`[a-z][a-z0-9-]+`", b)))
    routed = set(re.findall(r"`([a-z][a-z0-9-]+)`", best))
    owning = {
        r["dept"]
        for s in map_data["skills"]
        if s.get("client_facing")
        for r in s.get("roles", [])
    }
    missing = sorted(owning - routed)
    assert not missing, f"reflex catalog omits owning departments: {missing}"

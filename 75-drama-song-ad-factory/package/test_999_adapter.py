#!/usr/bin/env python3
"""Focused tests for the 999 package adapter (S75-T30 / S75-A30).

One test per clause of the row, plus the two layout modes and the fail-closed
cases. Every mutation happens in a temporary directory: no file in this tree is
written, no box is touched, no network is used.

Run: python3 package/test_999_adapter.py
 or: python3 -m pytest -q package/test_999_adapter.py
"""
import contextlib
import importlib.util
import json
import os
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)

_SCADAPTER = importlib.util.spec_from_file_location(
    "n999_adapter_under_test", os.path.join(HERE, "999_adapter.py"))
A = importlib.util.module_from_spec(_SCADAPTER)
_SCADAPTER.loader.exec_module(A)

FIXTURE_REL = os.path.join("tests", "fixtures", "999_entrypoints.json")


def _clause(envelope, clause_id):
    for clause in envelope["clauses"]:
        if clause["id"] == clause_id:
            return clause
    raise AssertionError("clause %r absent from %r"
                         % (clause_id, [c["id"] for c in envelope["clauses"]]))


@contextlib.contextmanager
def _temp_999_root():
    """A real 999 layout: <tmp>/.claude/skills/drama-song-ad-factory."""
    base = tempfile.mkdtemp(prefix="s75t30-999-")
    try:
        root = os.path.join(base, ".claude", "skills", "drama-song-ad-factory")
        os.makedirs(os.path.join(root, "package"))
        os.makedirs(os.path.join(root, "tests", "fixtures"))
        os.makedirs(os.path.join(root, "scripts"))
        for name in ("claude-code", "claude-nine"):
            adapter_dir = os.path.join(root, "adapters", name)
            os.makedirs(adapter_dir)
            with open(os.path.join(adapter_dir, "README.md"), "w",
                      encoding="utf-8") as fh:
                fh.write("# %s adapter\n" % name)
        shutil.copytree(os.path.join(SKILL_ROOT, "scripts", "core"),
                        os.path.join(root, "scripts", "core"))
        for name in ("999_adapter.py", "999-manifest.json"):
            shutil.copy2(os.path.join(HERE, name),
                         os.path.join(root, "package", name))
        shutil.copy2(os.path.join(SKILL_ROOT, FIXTURE_REL),
                     os.path.join(root, FIXTURE_REL))
        yield root
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _rewrite_fixture(root, mutate):
    path = os.path.join(root, FIXTURE_REL)
    with open(path, encoding="utf-8") as fh:
        fixture = json.load(fh)
    mutate(fixture)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(fixture, fh)


# ---------------------------------------------------------------------------
# same product requirements, through the accepted seam
# ---------------------------------------------------------------------------

def test_source_layout_resolves_through_seam():
    resolved = A.resolve()
    assert resolved["ok"], resolved["problems"]
    assert resolved["layout"] == "source"
    assert resolved["flavor"] == A.FLAVOR
    assert resolved["seam"] == "package_flavor_adapter.resolve"
    assert resolved["package_differences"]["skill_root_anchor"] == A.N999_SUFFIX
    assert resolved["package_differences"]["character_approval_module"] is None


def test_manifest_package_differences_match_the_seam():
    import sys
    sys.path.insert(0, os.path.join(SKILL_ROOT, "scripts", "core"))
    try:
        import package_flavor_adapter as seam
    finally:
        sys.path.remove(os.path.join(SKILL_ROOT, "scripts", "core"))
    declared = A.load_manifest()["package_differences"]["values"]
    resolved = seam.resolve(seam.N999)
    assert {k: declared[k] for k in seam.PACKAGE_DIFFERENCES} == {
        k: resolved[k] for k in seam.PACKAGE_DIFFERENCES}


def test_requirement_set_is_the_shared_product_set():
    ids = tuple(r["id"] for r in A.load_manifest()["product_requirements"])
    assert ids == A.REQUIREMENT_IDS
    # The same set the primary flavour is held to: order, gates, Notion, 18
    # styles, approvals, parity, paid compatibility.
    assert len(ids) == 7


def test_requirement_probes_hold_at_this_head():
    result = A.requirements()
    assert result["ok"], result["problems"]
    probed = [row for row in result["rows"] if row.get("probe")]
    assert probed, "no requirement was actually probed"
    for row in probed:
        assert row["probe"]["pass"], (row["id"], row["probe"])


def test_absent_requirements_name_the_unit_that_owes_them():
    rows = {r["id"]: r for r in A.requirements()["rows"]}
    gaps = {g["carrier"]: g["owed_by"] for g in rows["notion"]["absent"]}
    assert gaps["scripts/core/character_library/notion_store.py"] == "S75-T15"
    assert gaps["scripts/core/character_library/migration.py"] == "S75-T17"
    paid = rows["paid_compatibility"]["absent"]
    assert [g["owed_by"] for g in paid] == ["S75-T28"]
    assert rows["paid_compatibility"]["state"] == "absent"


def test_stale_absent_declaration_fails_closed():
    with _temp_999_root() as root:
        assert A.requirements(root)["ok"]
        carrier = os.path.join(root, "scripts", "core", "character_library",
                               "notion_store.py")
        with open(carrier, "w", encoding="utf-8") as fh:
            fh.write("# planted: this carrier is declared absent\n")
        result = A.requirements(root)
        assert result["ok"] is False
        assert any("notion_store.py absent but" in p and "is present" in p
                   for p in result["problems"]), result["problems"]


# ---------------------------------------------------------------------------
# its own adapters, never the primary flavour's internal path
# ---------------------------------------------------------------------------

def test_own_adapters_source_mode_does_not_touch_the_primary_path():
    result = A.own_adapters()
    assert result["ok"], result["problems"]
    assert result["layout"] == "source"
    assert os.path.isfile(os.path.join(SKILL_ROOT, A.PRIMARY_WRAPPER))


def test_own_adapters_999_layout_requires_its_native_adapters():
    with _temp_999_root() as root:
        result = A.own_adapters(root)
        assert result["ok"], result["problems"]
        assert result["layout"] == "999"


def test_own_adapters_999_layout_refuses_the_primary_wrapper():
    with _temp_999_root() as root:
        wrapper = os.path.join(root, A.PRIMARY_WRAPPER)
        with open(wrapper, "w", encoding="utf-8") as fh:
            fh.write("# planted primary wrapper\n")
        result = A.own_adapters(root)
        assert result["ok"] is False
        assert any("primary wrapper" in p for p in result["problems"])


def test_own_adapters_refuses_importing_the_primary_adapter():
    with _temp_999_root() as root:
        target = os.path.join(root, "package", "999_adapter.py")
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\nimport onboarding_adapter  # planted shortcut\n")
        result = A.own_adapters(root)
        assert result["ok"] is False
        assert any("imports the primary adapter module" in p
                   for p in result["problems"]), result["problems"]


def test_own_adapters_999_layout_refuses_a_fixture_row_through_the_wrapper():
    with _temp_999_root() as root:
        def mutate(fixture):
            fixture["entrypoints"].append({
                "id": "routes-through-primary-wrapper",
                "kind": "run",
                "argv": ["{python}", "scripts/openclaw_adapter.py", "preflight"],
                "cwd": "{skill_root}",
                "advertised_in": ["test"],
                "expect": {"exit_code": 0},
                "observed": {"exit_code": 0},
            })
        _rewrite_fixture(root, mutate)
        result = A.own_adapters(root)
        assert result["ok"] is False
        assert any("primary wrapper" in p for p in result["problems"])


# ---------------------------------------------------------------------------
# no unsupported commands, no placeholder ellipses, no missing steps
# ---------------------------------------------------------------------------

def test_unsupported_command_is_refused():
    with _temp_999_root() as root:
        assert not A.entrypoints(root)["unsupported"]

        def mutate(fixture):
            fixture["entrypoints"].append({
                "id": "advertises-an-unimplemented-command",
                "kind": "reachable",
                "argv": ["{python}", "scripts/core/intake_preflight/factory.py",
                         "production-hold", "--help"],
                "cwd": "{skill_root}",
                "advertised_in": ["test"],
                "expect": {"exit_code": 0},
                "observed": {"exit_code": 0},
            })
        _rewrite_fixture(root, mutate)
        steps = A.entrypoints(root)
        assert steps["unsupported"], steps
        assert "production-hold" in steps["unsupported"][0]
        assert _clause(A.check(root), "no_unsupported_commands")["ok"] is False


def test_placeholder_ellipsis_is_refused():
    with _temp_999_root() as root:
        def mutate(fixture):
            fixture["entrypoints"].append({
                "id": "ellipsis-step",
                "kind": "run",
                "argv": ["{python}", "package/999_adapter.py", "..."],
                "cwd": "{skill_root}",
                "advertised_in": ["test"],
                "expect": {"exit_code": 0},
                "observed": {"exit_code": 0},
            })
        _rewrite_fixture(root, mutate)
        steps = A.entrypoints(root)
        assert steps["placeholders"], steps
        assert _clause(A.check(root), "no_placeholder_ellipses")["ok"] is False


def test_missing_advertised_script_is_refused():
    with _temp_999_root() as root:
        def mutate(fixture):
            for row in fixture["entrypoints"]:
                if row["id"] == "package-entrypoints":
                    row["argv"] = ["{python}", "package/absent_adapter.py",
                                   "entrypoints"]
        _rewrite_fixture(root, mutate)
        steps = A.entrypoints(root)
        assert steps["missing"], steps
        assert any("does not exist" in p for p in steps["missing"])
        assert _clause(A.check(root), "no_missing_advertised_steps")["ok"] is False


def test_observed_exit_code_must_match_the_declared_one():
    with _temp_999_root() as root:
        def mutate(fixture):
            for row in fixture["entrypoints"]:
                if row["id"] == "control-cli-preflight":
                    row["observed"]["exit_code"] = 0
        _rewrite_fixture(root, mutate)
        steps = A.entrypoints(root)
        assert any("does not match expected" in p for p in steps["missing"]), steps


# ---------------------------------------------------------------------------
# end to end
# ---------------------------------------------------------------------------

def test_check_passes_in_the_source_tree():
    envelope = A.check()
    assert envelope["ok"], [c["id"] for c in envelope["clauses"] if not c["ok"]]
    assert envelope["layout"] == "source"
    assert [c["id"] for c in envelope["clauses"]] == [
        "same_product_requirements", "own_adapters", "no_unsupported_commands",
        "no_placeholder_ellipses", "no_missing_advertised_steps"]


def test_check_passes_in_a_999_layout():
    with _temp_999_root() as root:
        envelope = A.check(root)
        assert envelope["ok"], [c["id"] for c in envelope["clauses"] if not c["ok"]]
        assert envelope["layout"] == "999"


def test_every_advertised_step_actually_executes():
    ran = A.run_entrypoints()
    assert ran["ok"], ran["problems"]
    assert ran["executed"] == len(A.load_fixture()["entrypoints"]) + len(
        A.load_fixture()["checks"])
    assert all(row["exit_code"] == row["expected"] for row in ran["observed"])


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - standalone runner
            failures += 1
            print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc))
        else:
            print("ok   %s" % name)
    print("\n%d passed, %d failed, %d total"
          % (len(tests) - failures, failures, len(tests)))
    raise SystemExit(1 if failures else 0)

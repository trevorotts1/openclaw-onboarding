#!/usr/bin/env python3
"""Focused tests for the 999 package adapter (S75-T30 / S75-A30).

One test per clause of the row, plus the fail-closed cases and the negative
controls that prove each clause can go red. Every mutation happens in a
temporary directory: no file in this tree is written, no box is touched, no
network is used.

Run: python3 package/test_999_adapter.py
 or: python3 -m pytest -q package/test_999_adapter.py
"""
import contextlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(SKILL_ROOT)

_SCADAPTER = importlib.util.spec_from_file_location(
    "n999_adapter_under_test", os.path.join(HERE, "999_adapter.py"))
A = importlib.util.module_from_spec(_SCADAPTER)
_SCADAPTER.loader.exec_module(A)

FIXTURE_REL = os.path.join("tests", "fixtures", "999_entrypoints.json")
PRIMARY_REL = os.path.join("tests", "fixtures", "primary-flavour-manifest.json")
REGISTRY_REL = os.path.join("74-kie-live-adapter", "references",
                            "kie-model-registry.json")


def _clause(envelope, clause_id):
    for clause in envelope["clauses"]:
        if clause["id"] == clause_id:
            return clause
    raise AssertionError("clause %r absent from %r"
                         % (clause_id, [c["id"] for c in envelope["clauses"]]))


def _clauses(envelope):
    return {c["id"]: c["ok"] for c in envelope["clauses"]}


def _seed_registry(base):
    """The sibling skill's live KIE registry, so card steps can prove models."""
    target = os.path.join(base, "74-kie-live-adapter", "references")
    os.makedirs(target, exist_ok=True)
    source = os.path.join(REPO_ROOT, REGISTRY_REL)
    if os.path.isfile(source):
        shutil.copy2(source, target)


@contextlib.contextmanager
def _temp_999_root():
    """A real 999 layout: <tmp>/.claude/skills/drama-song-ad-factory.

    The whole skill tree is copied, minus the primary wrapper the 999 flavour
    forbids, plus the two native adapter READMEs the 999 layout requires.
    """
    base = tempfile.mkdtemp(prefix="s75t30-999-")
    try:
        root = os.path.join(base, ".claude", "skills", "drama-song-ad-factory")
        shutil.copytree(SKILL_ROOT, root,
                        ignore=shutil.ignore_patterns("__pycache__",
                                                      "openclaw_adapter.py"))
        for name in ("claude-code", "claude-nine"):
            adapter_dir = os.path.join(root, "adapters", name)
            os.makedirs(adapter_dir)
            with open(os.path.join(adapter_dir, "README.md"), "w",
                      encoding="utf-8") as fh:
                fh.write("# %s adapter\n" % name)
        _seed_registry(base)
        yield root
    finally:
        shutil.rmtree(base, ignore_errors=True)


@contextlib.contextmanager
def _source_copy(tag="source"):
    """A throwaway copy of the source tree, for out-of-process checks."""
    base = tempfile.mkdtemp(prefix="s75t30-%s-" % tag)
    try:
        root = os.path.join(base, "75-drama-song-ad-factory")
        shutil.copytree(SKILL_ROOT, root,
                        ignore=shutil.ignore_patterns("__pycache__"))
        _seed_registry(base)
        yield root
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _run_check(root):
    """Run the advertised check in a FRESH process and parse its receipt."""
    proc = subprocess.run([sys.executable, "package/999_adapter.py", "check"],
                          cwd=root, capture_output=True, text=True, timeout=900)
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        raise AssertionError("check printed no JSON: rc=%d stderr=%r"
                             % (proc.returncode, proc.stderr[-400:]))
    return proc.returncode, payload


def _rewrite_fixture(root, mutate):
    path = os.path.join(root, FIXTURE_REL)
    with open(path, encoding="utf-8") as fh:
        fixture = json.load(fh)
    mutate(fixture)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(fixture, fh)


def _rewrite_manifest(root, mutate):
    path = os.path.join(root, "package", "999-manifest.json")
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    mutate(manifest)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)


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
    """The set is read from the primary flavour's manifest, not from a literal.

    Round 1 asserted the 999 manifest equalled a tuple defined in the module
    under test -- a tautology that could never notice a dropped requirement.
    This reads the primary manifest bytes from the tree, verifies the pinned
    digest, and requires every primary clause to be present.
    """
    primary_ids, problems = A.primary_requirement_ids()
    assert not problems, problems
    assert primary_ids == [
        "artifact_order", "cast_world_script_gates", "notion", "styles_18",
        "flavor_parity", "emergency_fixes_read_only", "entrypoint_reachability"]

    declared = [r["id"] for r in A.load_manifest()["product_requirements"]]
    dropped = [i for i in primary_ids if i not in declared]
    assert not dropped, "the 999 set dropped primary clause(s) %s" % dropped

    result = A.requirements()
    assert result["ok"], result["problems"]
    assert result["primary_clause_ids"] == primary_ids
    assert result["declared_additions"] == ["approval_ordering",
                                            "paid_compatibility"]


def test_primary_manifest_digest_is_pinned():
    manifest = A.load_manifest()
    path = os.path.join(SKILL_ROOT, manifest["primary_flavour"]["path"])
    assert A._sha256(path) == manifest["primary_flavour"]["sha256"]
    # A tampered copy fails closed rather than silently redefining the set.
    with _source_copy("primary") as root:
        path = os.path.join(root, PRIMARY_REL)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["clauses"].pop("entrypoint_reachability")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        rc, payload = _run_check(root)
        assert rc == 1
        assert _clauses(payload)["same_product_requirements"] is False
        problems = payload["clauses"][0]["detail"]["requirements"]["problems"]
        assert any("sha256" in p for p in problems), problems


def test_requirement_probes_hold_at_this_head():
    result = A.requirements()
    assert result["ok"], result["problems"]
    probed = [row for row in result["rows"] if row.get("probe")]
    assert len(probed) >= 7, "only %d requirements probed" % len(probed)
    for row in probed:
        assert row["probe"]["pass"], (row["id"], row["probe"])


def test_every_declared_carrier_is_loaded_by_its_probe():
    """Each declared carrier module must be imported by the probe, not on disk."""
    manifest = A.load_manifest()
    rows = {r["id"]: r for r in A.requirements()["rows"]}
    checked = 0
    for row in manifest["product_requirements"]:
        modules = row.get("carrier_modules") or []
        if not modules:
            continue
        loaded = set(rows[row["id"]]["probe"].get("loaded_modules") or [])
        assert set(modules) <= loaded, (row["id"], modules, sorted(loaded))
        checked += 1
    assert checked >= 4, "no carrier load was actually asserted"


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
        assert result["entrypoint"] == A.ENTRYPOINT_REL


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


def test_false_unsupported_claim_is_refused():
    """A step claimed unsupported that really runs must fail, not pass (P6)."""
    with _source_copy("exclusion") as root:
        def mutate(fixture):
            fixture["excluded_steps"].append({
                "id": "claims-final-recap-is-missing",
                "argv": ["{python}", "scripts/core/intake_preflight/factory.py",
                         "final-recap", "--help"],
                "reason": "claimed: final-recap is not implemented here",
                "observed": {"exit_code": 2,
                             "error": "invalid choice: 'final-recap'"},
            })
        _rewrite_fixture(root, mutate)
        rc, payload = _run_check(root)
        assert rc == 1
        assert _clauses(payload)["no_unsupported_commands"] is False, _clauses(
            payload)


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


def test_placeholder_outside_argv_is_refused():
    """P4: an ellipsis in a non-argv advertised field must be caught."""
    with _source_copy("ellipsis") as root:
        def mutate(fixture):
            fixture["entrypoints"][0]["note"] = (
                "rest of the step is described here ... and so on")
        _rewrite_fixture(root, mutate)
        rc, payload = _run_check(root)
        assert rc == 1
        assert _clauses(payload)["no_placeholder_ellipses"] is False
        detail = _clause(payload, "no_placeholder_ellipses")["detail"]
        assert any("note" in p for p in detail["problems"]), detail["problems"]


def test_method_plan_surface_is_read_and_executed():
    """C4: the SPEC defect lives in method_plan.py, which round 1 never read."""
    steps = A.entrypoints()["method_plan"]
    assert steps["pass"], steps
    assert steps["validate_outcome"] == "rejected"
    assert steps["gate_count"] == 6
    assert steps["teaching_rows"] == 12
    assert not steps["placeholders"]

    with _source_copy("methodplan") as root:
        target = os.path.join(root, "scripts", "core", "method_plan",
                              "method_plan.py")
        with open(target, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace("def validate(blueprint, method):",
                            "def validate_removed(blueprint, method):")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)
        rc, payload = _run_check(root)
        assert rc == 1
        detail = _clause(payload, "no_placeholder_ellipses")["detail"]
        assert "validate" in detail["method_plan"]["missing_steps"], detail
        assert detail["method_plan"]["pass"] is False


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
                if row["id"] == "next-run-dir":
                    row["observed"]["exit_code"] = 0
        _rewrite_fixture(root, mutate)
        steps = A.entrypoints(root)
        assert any("does not match expected" in p for p in steps["missing"]), steps


def test_fabricated_exit_code_fails_under_the_advertised_check():
    """P3: recorded==declared==99 for a step that really exits 0 must go red."""
    with _source_copy("fabricated") as root:
        def mutate(fixture):
            for row in fixture["entrypoints"]:
                if row["id"] == "card-client-dir":
                    row["expect"]["exit_code"] = 99
                    row["observed"]["exit_code"] = 99
        _rewrite_fixture(root, mutate)
        rc, payload = _run_check(root)
        assert rc == 1
        assert _clauses(payload)["no_missing_advertised_steps"] is False
        detail = _clause(payload, "no_missing_advertised_steps")["detail"]
        assert any("card-client-dir exited 0" in p for p in detail["problems"])


def test_wrong_citation_is_refused():
    with _source_copy("citation") as root:
        def mutate(fixture):
            fixture["entrypoints"][0]["advertised_in"] = [
                "SKILL.md:296 'The control CLI (one entrypoint)'"]
        _rewrite_fixture(root, mutate)
        rc, payload = _run_check(root)
        assert rc == 1
        assert _clauses(payload)["no_missing_advertised_steps"] is False
        detail = _clause(payload, "no_missing_advertised_steps")["detail"]
        assert any("is not on SKILL.md line 296" in p
                   for p in detail["problems"]), detail["problems"]


# ---------------------------------------------------------------------------
# entrypoint reachability: the 999 entrypoint must LOAD the carriers
# ---------------------------------------------------------------------------

def test_entrypoint_reachability_is_green_and_controlled():
    reach = A.reachability()
    assert reach["ok"], reach["problems"]
    assert reach["entrypoint"] == A.ENTRYPOINT_REL
    assert sorted(reach["runtime_loaded"]) == sorted(reach["targets"])
    assert [c["reached"] for c in reach["controls"]] == [True, True]
    # The held control CLI is reported, not claimed.
    assert reach["factory_closure_targets"], reach
    assert "HELD" in reach["factory_not_claimed"]


def test_breaking_entrypoint_routing_turns_reachability_red():
    with _source_copy("routing") as root:
        target = os.path.join(root, A.ENTRYPOINT_REL)
        with open(target, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace(
            "from character_library import sync_protocol  # noqa: E402\n", "")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)
        rc, payload = _run_check(root)
        assert rc == 1
        assert _clauses(payload)["entrypoint_reachability"] is False
        detail = _clause(payload, "entrypoint_reachability")["detail"]
        assert "character_library.sync_protocol" in detail["unreachable"] or any(
            "character_library.sync_protocol" in p for p in detail["problems"])


def test_gutting_any_declared_carrier_turns_the_check_red():
    carriers = ("scripts/core/character_bible/identity.py",
                "scripts/core/character_library/notion_adapter.py",
                "scripts/core/character_library/sync_protocol.py",
                "scripts/core/music_styles/catalog.py",
                "scripts/core/story_first_contracts.py")
    for rel in carriers:
        with _source_copy("gut") as root:
            with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
                fh.write("raise ImportError('gutted by negative control')\n")
            rc, payload = _run_check(root)
            assert rc == 1, "%s: check stayed green" % rel
            assert _clauses(payload)["same_product_requirements"] is False, rel
            assert _clauses(payload)["entrypoint_reachability"] is False, rel


def test_gutting_the_entrypoint_turns_reachability_red():
    with _source_copy("entrypoint-gut") as root:
        with open(os.path.join(root, A.ENTRYPOINT_REL), "w",
                  encoding="utf-8") as fh:
            fh.write("raise ImportError('gutted entrypoint')\n")
        rc, payload = _run_check(root)
        assert rc == 1
        assert _clauses(payload)["entrypoint_reachability"] is False
        assert _clauses(payload)["no_missing_advertised_steps"] is False


# ---------------------------------------------------------------------------
# emergency fixes stay read-only
# ---------------------------------------------------------------------------

def test_emergency_fixes_clause_reports_held_files_and_stays_read_only():
    clause = _clause(A.check(), "emergency_fixes_read_only")
    assert clause["ok"], clause["detail"]
    digests = {h["path"]: h.get("sha256")
               for h in clause["detail"]["held_files"]}
    assert digests["scripts/core/intake_preflight/factory.py"]
    assert digests["scripts/core/character_bible/character_approval.py"]

    with _source_copy("mutation") as root:
        with open(os.path.join(root, "package", "999_adapter.py"), "a",
                  encoding="utf-8") as fh:
            fh.write('\nopen("scripts/core/method_plan/method_plan.py", "w")\n')
        rc, payload = _run_check(root)
        assert rc == 1
        assert _clauses(payload)["emergency_fixes_read_only"] is False


# ---------------------------------------------------------------------------
# end to end
# ---------------------------------------------------------------------------

def test_check_passes_in_the_source_tree():
    envelope = A.check()
    assert envelope["ok"], [(c["id"], c["detail"])
                            for c in envelope["clauses"] if not c["ok"]]
    assert envelope["layout"] == "source"
    assert [c["id"] for c in envelope["clauses"]] == [
        "same_product_requirements", "own_adapters", "entrypoint_reachability",
        "emergency_fixes_read_only", "no_unsupported_commands",
        "no_placeholder_ellipses", "no_missing_advertised_steps"]


def test_check_passes_in_a_999_layout():
    with _temp_999_root() as root:
        envelope = A.check(root)
        assert envelope["ok"], [(c["id"], c["detail"])
                                for c in envelope["clauses"] if not c["ok"]]
        assert envelope["layout"] == "999"


def test_every_advertised_step_actually_executes():
    ran = A.run_entrypoints()
    assert ran["ok"], ran["problems"]
    assert ran["executed"] == len(A.load_fixture()["entrypoints"]) + len(
        A.load_fixture()["checks"])
    assert all(row["exit_code"] == row["expected"] for row in ran["observed"])


def test_the_advertised_check_executes_rather_than_compares_records():
    envelope = A.check()
    assert envelope["executes_advertised_steps"] is True
    detail = _clause(envelope, "no_missing_advertised_steps")["detail"]
    assert detail["executed"] > 0
    assert len(detail["observed"]) == detail["executed"]


def test_no_real_999_layout_is_claimed():
    """State the limit: adapters/ does not exist in this repository."""
    assert not os.path.isdir(os.path.join(SKILL_ROOT, "adapters"))
    manifest = A.load_manifest()
    assert any("UNPROVEN" in note for note in manifest["not_claimed"])


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

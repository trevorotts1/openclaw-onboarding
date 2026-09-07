#!/usr/bin/env python3
"""
test_dept_scripts_suffix_coverage.py — FIX-DELIVERY-04 regression gate.

WHAT BROKE (four times, the same way)
─────────────────────────────────────
A department's runtime assets reach a client box through an ALLOWLIST of file
suffixes (create_role_workspaces._CANONICAL_SCRIPT_SUFFIXES /
_ADDITIVE_SCRIPT_SUFFIXES). Every writer -- scaffold_department(),
refresh-dept-scripts.py, refresh-dept-intake.py -- and the post-write verifier
verify_scripts_materialization() all `continue` past any suffix not in those
tuples. So an asset type nobody remembered to add is not merely undelivered:
it is UNDETECTABLE, because the verifier skips it too and still reports
"ok=1 failed_inscope=0".

That has now happened to .js (GAP-DELIVERY-JS), .tpl (GAP-DELIVERY-TPL), .md
and .template (GAP-DELIVERY-MD-TEMPLATE), and .yaml (GAP-DELIVERY-YAML --
presentation_job/providers.yaml, the rate-governor config, which meant
governor.py silently fell back to its in-code _DEFAULTS on EVERY client box:
deepseek throttled to rps 1.0/max_inflight 50 instead of 5.0/400, and zai
RAISED to 50 in-flight against a real ceiling of 10).

WHAT THIS FILE ENFORCES
───────────────────────
test_no_unclassified_suffix    -- THE CLASS. Walks the real role-library
                                  scripts/ trees with the copier's own walk and
                                  fails if any suffix present there is in
                                  neither fleet-owned, nor box-owned, nor the
                                  explicit "deliberately not delivered" list.
                                  A fifth silent drop cannot merge.
test_providers_yaml_*          -- THE INSTANCE. Proves providers.yaml actually
                                  lands in a freshly materialized department,
                                  and that the verifier FAILS when it is
                                  removed (the check discriminates -- it is not
                                  a tautology that passes on an empty tree).

Read-only against the repo; all writes go to pytest tmp_path.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import create_role_workspaces as crw  # noqa: E402

LIBRARY_ROOT = _HERE.parent / "templates" / "role-library"


def _load_refresh_dept_scripts():
    """Import refresh-dept-scripts.py by path (hyphens => not importable by name)."""
    path = _HERE / "refresh-dept-scripts.py"
    spec = importlib.util.spec_from_file_location("refresh_dept_scripts", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _library_depts_with_scripts():
    return [d for d in sorted(LIBRARY_ROOT.iterdir())
            if d.is_dir() and not d.name.startswith(".") and (d / "scripts").is_dir()]


# ───────────────────────────── THE CLASS ─────────────────────────────────────

def test_library_actually_has_scripts_trees_to_scan():
    """Control for test_no_unclassified_suffix.

    A coverage gate over an empty set passes vacuously. This proves the scan
    has real input, so a green result from the gate below is a fact about the
    suffix policy and not an artifact of walking nothing.
    """
    depts = _library_depts_with_scripts()
    assert depts, f"no role-library department ships a scripts/ dir under {LIBRARY_ROOT}"
    total = sum(1 for d in depts for _ in crw._iter_scripts_tree_files(d / "scripts"))
    assert total > 50, f"expected a substantial scripts corpus, walked only {total} file(s)"


def test_no_unclassified_suffix():
    """Every suffix the role library ships under a dept scripts/ tree must be
    classified by exactly one of the three policy buckets.

    Failing here does NOT necessarily mean something is broken -- it means a new
    asset type appeared and a human must decide whether it is fleet-owned
    (_CANONICAL_SCRIPT_SUFFIXES), box-owned/additive (_ADDITIVE_SCRIPT_SUFFIXES),
    or deliberately not shipped (_NON_DELIVERED_SCRIPT_SUFFIXES). Making that
    decision explicit is the whole point: the four historical drops all happened
    because the default for an unclassified suffix was a silent `continue`.
    """
    # getattr fallback: on a tree predating FIX-DELIVERY-04 the third bucket does
    # not exist. Degrade to a readable assertion naming the unclassified
    # suffixes rather than an AttributeError that hides the diagnosis.
    classified = (set(crw._CANONICAL_SCRIPT_SUFFIXES)
                  | set(crw._ADDITIVE_SCRIPT_SUFFIXES)
                  | set(getattr(crw, "_NON_DELIVERED_SCRIPT_SUFFIXES", ())))
    unclassified = {}
    for dept in _library_depts_with_scripts():
        for rel, src in crw._iter_scripts_tree_files(dept / "scripts"):
            if src.suffix not in classified:
                unclassified.setdefault(src.suffix, []).append(f"{dept.name}/scripts/{rel}")
    assert not unclassified, (
        "Unclassified suffix(es) in a role-library scripts/ tree. These files are "
        "silently NOT delivered to any materialized department, and "
        "verify_scripts_materialization() cannot see them either:\n"
        + "\n".join(f"  {suf}: {', '.join(paths)}" for suf, paths in sorted(unclassified.items()))
        + "\n\nClassify each suffix in create_role_workspaces.py as fleet-owned "
          "(_CANONICAL_SCRIPT_SUFFIXES), box-owned (_ADDITIVE_SCRIPT_SUFFIXES), or "
          "deliberately-not-delivered (_NON_DELIVERED_SCRIPT_SUFFIXES)."
    )


def test_buckets_are_disjoint():
    """A suffix in two buckets makes delivery order-dependent (the additive
    check runs first, so a fleet-owned file would become missing-only and stop
    refreshing). Cheap invariant, catches a careless future edit."""
    can = set(crw._CANONICAL_SCRIPT_SUFFIXES)
    add = set(crw._ADDITIVE_SCRIPT_SUFFIXES)
    non = set(getattr(crw, "_NON_DELIVERED_SCRIPT_SUFFIXES", ()))
    assert not (can & add), f"suffix in BOTH canonical and additive: {can & add}"
    assert not (can & non), f"suffix in BOTH canonical and not-delivered: {can & non}"
    assert not (add & non), f"suffix in BOTH additive and not-delivered: {add & non}"


# ──────────────────────────── THE INSTANCE ───────────────────────────────────

PROVIDERS_REL = Path("presentation_job/providers.yaml")


def _materialize_presentations(tmp_path):
    """Run the real refresh-dept-scripts.py mirror into a scratch workspace.

    NEVER touches ~/.openclaw: --workspace and --library are both explicit and
    both under tmp_path / the repo.
    """
    ws = tmp_path / "workspace"
    dept_dir = ws / "departments" / "presentations"
    dept_dir.mkdir(parents=True)
    mod = _load_refresh_dept_scripts()
    rc = mod.main(["--workspace", str(ws), "--library", str(LIBRARY_ROOT), "--apply"])
    return ws, dept_dir, rc


def test_providers_yaml_is_shipped_by_the_library():
    """Guards the premise of the two tests below."""
    src = LIBRARY_ROOT / "presentations" / "scripts" / PROVIDERS_REL
    assert src.is_file(), f"library no longer ships {src}"


def test_providers_yaml_reaches_a_materialized_department(tmp_path):
    """FIX-DELIVERY-04 regression: the governor's config must actually arrive,
    byte-identical, in a freshly materialized department."""
    ws, dept_dir, rc = _materialize_presentations(tmp_path)
    dest = dept_dir / "scripts" / PROVIDERS_REL
    assert dest.is_file(), (
        f"providers.yaml did NOT reach the materialized department at {dest}. "
        "governor.py would silently fall back to its in-code _DEFAULTS for every provider."
    )
    src = LIBRARY_ROOT / "presentations" / "scripts" / PROVIDERS_REL
    assert (hashlib.sha256(dest.read_bytes()).hexdigest()
            == hashlib.sha256(src.read_bytes()).hexdigest()), \
        "providers.yaml reached the department but does not match the library bytes"
    assert rc == 0, f"mirror reported failure rc={rc}"


def test_governor_reads_the_materialized_copy_not_defaults(tmp_path):
    """End-to-end: load governor.py FROM the materialized department and prove
    it returns the YAML ceilings rather than _DEFAULTS.

    This is the check that would have caught the live defect. Asserting the file
    merely exists is weaker -- it cannot tell a delivered config apart from one
    the governor ignores.
    """
    _ws, dept_dir, _rc = _materialize_presentations(tmp_path)
    gov_path = dept_dir / "scripts" / "presentation_job" / "governor.py"
    assert gov_path.is_file(), "governor.py itself did not materialize (control failed)"

    spec = importlib.util.spec_from_file_location("_materialized_governor", gov_path)
    gov = importlib.util.module_from_spec(spec)
    # Register before exec: governor.py defines a @dataclass, and on Python
    # 3.14 dataclasses resolves ClassVar annotations via
    # sys.modules[cls.__module__].__dict__ -- which raises AttributeError if the
    # module was exec'd without ever being registered.
    sys.modules[spec.name] = gov
    try:
        spec.loader.exec_module(gov)
    finally:
        sys.modules.pop(spec.name, None)

    deepseek = gov.provider_config("deepseek")
    defaults = gov._DEFAULTS
    assert deepseek["max_inflight"] != defaults["max_inflight"], (
        "governor fell back to _DEFAULTS -- providers.yaml was not read from the "
        f"materialized department (got max_inflight={deepseek['max_inflight']})"
    )
    assert deepseek["max_inflight"] == 400, deepseek
    assert deepseek["rps"] == 5.0, deepseek


def test_verifier_fails_when_a_delivered_asset_is_removed(tmp_path):
    """THE DISCRIMINATION PROOF for this whole file.

    Delete providers.yaml from the materialized department and require
    verify_scripts_materialization() to NAME it. Before FIX-DELIVERY-04 this
    returned [] -- the verifier skipped .yaml exactly like the copier did, which
    is why the gap survived every roll while the roll reported success.
    """
    _ws, dept_dir, _rc = _materialize_presentations(tmp_path)
    lib_scripts = LIBRARY_ROOT / "presentations" / "scripts"
    target = dept_dir / "scripts"

    clean = crw.verify_scripts_materialization(lib_scripts, target)
    assert clean == [], f"expected a clean verify after materialization, got {clean[:5]}"

    (target / PROVIDERS_REL).unlink()
    problems = crw.verify_scripts_materialization(lib_scripts, target)
    named = [p for p in problems if p["path"] == str(PROVIDERS_REL)]
    assert named, (
        "verify_scripts_materialization() did NOT report the deleted providers.yaml. "
        "The suffix is not covered by the canonical set, so the verifier is blind to it "
        f"(problems reported: {problems})"
    )
    assert named[0]["issue"] == "missing", named


def test_removed_asset_is_re_delivered_on_the_next_roll(tmp_path):
    """A box that lost the file must self-heal on the next unconditional roll."""
    _ws, dept_dir, _rc = _materialize_presentations(tmp_path)
    dest = dept_dir / "scripts" / PROVIDERS_REL
    dest.unlink()
    assert not dest.exists()

    mod = _load_refresh_dept_scripts()
    ws2 = dept_dir.parent.parent
    rc = mod.main(["--workspace", str(ws2), "--library", str(LIBRARY_ROOT), "--apply"])
    assert dest.is_file(), "second roll did not restore providers.yaml"
    assert rc == 0, f"second roll reported rc={rc}"


# ─────────────────── F18: .json ownership under scripts/ ────────────────────
#
# The FIRST four drops were suffixes nobody classified. F18 is the inverted
# form of the same mistake: `.json` classified TOO BROADLY. Treating the whole
# suffix as box-owned meant every engine-data .json the library ships
# (model_catalog.json — the router's alias + pricing catalog; ocr-deps.json;
# slides.schema.json; structure/*.json) was copied missing-only, NEVER
# refreshed, and — because verify_scripts_materialization() skipped .json too —
# never checked either. A box that got a copy on day one kept it forever while
# every roll printed "DEPT_SCRIPTS_STATUS ok=1 failed_inscope=0".
#
# Measured on pristine origin/main before the fix: materialize presentations,
# overwrite the delivered model_catalog.json with {"stale": true}, re-roll ->
# rc 0, "0 file(s) copied, 12 client-local .json override(s) preserved", the
# file still {"stale": true}, and verify_scripts_materialization() reported
# ZERO problems. Control on the same instrument in the same run: tampering
# governor.py WAS named by the verifier (hash-mismatch) and WAS repaired by
# the next roll — so the negative was a fact about .json, not a broken probe.

ENGINE_JSON_REL = Path("presentation_job/model_catalog.json")


def test_engine_json_is_shipped_by_the_library():
    """Control for the tests below: the instance file must actually exist."""
    src = LIBRARY_ROOT / "presentations" / "scripts" / ENGINE_JSON_REL
    assert src.is_file(), f"library no longer ships {src}"


def test_no_box_owned_json_basename_is_actually_under_a_scripts_tree():
    """_BOX_OWNED_JSON_BASENAMES is a forward-compat carve-out, not a
    description of today's tree.

    capacity_override.json and resource_profile.json resolve to
    `<department>/config/` (capacity.department_config_dir()), which no writer
    in this repo walks. If one of them ever appears under a role-library
    scripts/ tree this fires, so whoever added it re-reads the policy instead
    of silently gaining a file no roll can refresh. The control is
    test_engine_json_is_shipped_by_the_library: the same walk DOES find real
    .json, so an empty result here is a fact about the allowlist and not an
    artifact of walking nothing.
    """
    found = {}
    for dept in _library_depts_with_scripts():
        for rel, _src in crw._iter_scripts_tree_files(dept / "scripts"):
            if Path(rel).name in crw._BOX_OWNED_JSON_BASENAMES:
                found.setdefault(Path(rel).name, []).append(f"{dept.name}/scripts/{rel}")
    assert not found, (
        "A basename on the box-owned allowlist now ships under a role-library "
        f"scripts/ tree: {found}. It would be delivered missing-only and never "
        "refreshed. Confirm that is intended, or move the file to the "
        "department's config/ dir where the per-box overrides actually live."
    )


def test_engine_json_is_classified_as_mirror_not_box_owned():
    """Unit level: the ONE ownership authority must call engine data
    fleet-owned, and must still protect the genuinely per-box basenames."""
    assert crw.script_asset_policy(ENGINE_JSON_REL) == crw.POLICY_MIRROR
    assert crw.script_asset_policy("presentation-deps.json") == crw.POLICY_MIRROR
    assert crw.script_asset_policy("structure/vsl_structure.json") == crw.POLICY_MIRROR
    # Discrimination: the allowlist must still carve out the real overrides.
    assert crw.script_asset_policy("capacity_override.json") == crw.POLICY_BOX_OWNED
    assert crw.script_asset_policy("config/resource_profile.json") == crw.POLICY_BOX_OWNED
    # The other two buckets are unchanged.
    assert crw.script_asset_policy("presentation_job/governor.py") == crw.POLICY_MIRROR
    assert crw.script_asset_policy("build_deck.py.headtest") == crw.POLICY_SKIP


def test_test_time_artifact_dir_is_never_delivered():
    """`working/` is a gitignored TEST-TIME artifact dir, not a deliverable.

    .gitignore names it outright ("emitted at test time by test_preflight.py
    ... regenerated in CI, never committed"), and read_slice.py writes
    working/checkpoints/read_slice_truncations.json RELATIVE TO CWD — so it
    appears in the library tree on any machine that runs the presentations
    suite from that directory (never on a clean clone, hence never on a client
    box). Before F18 it was shipped-once-and-ignored because .json was
    box-owned; making .json mirror would have promoted a mutable counter file
    to "overwritten every roll and required byte-identical by the verifier".
    """
    assert crw.script_asset_policy(
        "working/checkpoints/read_slice_truncations.json") == crw.POLICY_SKIP
    assert crw.script_asset_policy("working/anything.py") == crw.POLICY_SKIP
    # Discrimination: only a DIRECTORY component named `working` is skipped —
    # a file called working.json, or a real nested package, still delivers.
    assert crw.script_asset_policy("working.json") == crw.POLICY_MIRROR
    assert crw.script_asset_policy("presentation_job/dispatcher.py") == crw.POLICY_MIRROR


def test_per_box_runtime_json_is_not_reported_as_a_stray(tmp_path):
    """The stamp gate must keep tolerating a scripts/ .json the library never
    shipped.

    F18's claim is "REFRESH what the library ships", not "the box may hold no
    json of its own". A materialized department accumulates runtime json
    (read_slice.py's counter is today's example); calling every one of them
    "stray-not-in-library" would fail healthy boxes for a fix about staleness.
    The control is the second half of
    test_stamp_gate_enforces_engine_json_but_not_the_intake_banks: a json the
    library DOES ship is still named when it diverges, so this tolerance is
    scoped, not blanket.
    """
    _ws, dept_dir, _rc = _materialize_presentations(tmp_path)
    lib_dept = LIBRARY_ROOT / "presentations"
    stray = dept_dir / "scripts" / "runtime_state_written_by_the_engine.json"
    stray.write_text('{"runs": 3}\n', encoding="utf-8")

    problems, count = crw.verify_dept_scripts_stamp(dept_dir, lib_dept)
    assert count > 0, "control failed: the stamp gate walked zero files"
    assert not [p for p in problems if p["path"].endswith(stray.name)], (
        f"a per-box runtime .json was reported as a problem: {problems[:5]}")

    # Control on the same instrument: a per-box .py with no library counterpart
    # IS still a stray, so the tolerance above is about .json and not about the
    # gate having stopped discriminating.
    stray_py = dept_dir / "scripts" / "runtime_state_written_by_the_engine.py"
    stray_py.write_text("# not from the library\n", encoding="utf-8")
    problems2, _ = crw.verify_dept_scripts_stamp(dept_dir, lib_dept)
    assert [p for p in problems2 if p["path"].endswith(stray_py.name)
            and p["issue"] == "stray-not-in-library"], problems2


def test_stale_engine_json_is_refreshed_by_the_next_roll(tmp_path):
    """THE REGRESSION. A box whose model_catalog.json has drifted must be
    repaired by an ordinary roll.

    On pristine origin/main this fails: the roll reports rc 0 and "12
    client-local .json override(s) preserved" while the file keeps its stale
    bytes forever.
    """
    _ws, dept_dir, _rc = _materialize_presentations(tmp_path)
    dest = dept_dir / "scripts" / ENGINE_JSON_REL
    src = LIBRARY_ROOT / "presentations" / "scripts" / ENGINE_JSON_REL
    assert dest.is_file(), "control failed: model_catalog.json never materialized at all"

    dest.write_text('{"stale": true}\n', encoding="utf-8")
    mod = _load_refresh_dept_scripts()
    ws2 = dept_dir.parent.parent
    rc = mod.main(["--workspace", str(ws2), "--library", str(LIBRARY_ROOT), "--apply"])

    assert (hashlib.sha256(dest.read_bytes()).hexdigest()
            == hashlib.sha256(src.read_bytes()).hexdigest()), (
        "a stale model_catalog.json survived a full roll — the engine keeps "
        "running on last year's model aliases and prices while the roll still "
        "reports success. This is the providers.yaml defect in .json form."
    )
    assert rc == 0, f"roll reported rc={rc}"


def test_verifier_names_a_diverged_engine_json(tmp_path):
    """THE DISCRIMINATION PROOF. verify_scripts_materialization() must see it.

    Delivering the file but leaving the verifier blind would be half a fix: the
    roll would repair drift it can never report. On pristine origin/main this
    returns [] — .json was skipped by the verifier exactly like by the copier.
    """
    _ws, dept_dir, _rc = _materialize_presentations(tmp_path)
    lib_scripts = LIBRARY_ROOT / "presentations" / "scripts"
    target = dept_dir / "scripts"

    clean = crw.verify_scripts_materialization(lib_scripts, target)
    assert clean == [], f"expected a clean verify after materialization, got {clean[:5]}"

    (target / ENGINE_JSON_REL).write_text('{"tampered": true}\n', encoding="utf-8")
    problems = crw.verify_scripts_materialization(lib_scripts, target)
    named = [p for p in problems if p["path"] == str(ENGINE_JSON_REL)]
    assert named, (
        "verify_scripts_materialization() did NOT report the tampered "
        f"model_catalog.json (problems reported: {problems})"
    )
    assert named[0]["issue"] == "hash-mismatch", named

    (target / ENGINE_JSON_REL).unlink()
    missing = crw.verify_scripts_materialization(lib_scripts, target)
    assert [p for p in missing if p["path"] == str(ENGINE_JSON_REL)
            and p["issue"] == "missing"], missing


def test_stamp_gate_enforces_engine_json_but_not_the_intake_banks(tmp_path):
    """The FIX 66 content stamp must inherit the same ownership answer.

    The intake tree keeps its own policy (refresh-dept-intake.py owns it): the
    provenance-gated question banks stay box-owned. Both halves are asserted
    together so a future edit cannot fix one by breaking the other.
    """
    _ws, dept_dir, _rc = _materialize_presentations(tmp_path)
    lib_dept = LIBRARY_ROOT / "presentations"

    assert crw._dept_stamp_is_box_owned(
        f"scripts/{ENGINE_JSON_REL.as_posix()}", ".json") is False
    assert crw._dept_stamp_is_box_owned(
        "scripts/capacity_override.json", ".json") is True
    assert crw._dept_stamp_is_box_owned(
        "intake/deck-intake-questions.json", ".json") is True

    # End to end through the real gate.
    (dept_dir / "scripts" / ENGINE_JSON_REL).write_text(
        '{"tampered": true}\n', encoding="utf-8")
    problems, count = crw.verify_dept_scripts_stamp(dept_dir, lib_dept)
    assert count > 0, "control failed: the stamp gate walked zero files"
    named = [p for p in problems
             if p["path"] == f"scripts/{ENGINE_JSON_REL.as_posix()}"]
    assert named, (
        "the FIX 66 stamp gate did not name a hand-edited model_catalog.json "
        f"(problems: {problems[:5]})"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

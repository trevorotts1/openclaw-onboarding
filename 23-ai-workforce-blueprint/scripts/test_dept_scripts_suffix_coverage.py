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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

#!/usr/bin/env python3
"""
test_scan_roles.py — proves scan_roles_and_sops() inventory is layout-agnostic,
filters infra dirs and non-role docs, and handles de-numbering correctly.

Each `test_*` function is a thin pytest-visible wrapper around a `_check_*`
helper that does the actual work and returns a `fails` list; the wrapper
asserts the list empty so a broken guard FAILS under pytest, not only under
`python3 <file>`. `main()` calls the `_check_*` helpers directly so
script-mode aggregation / exit-code behavior is unchanged.

Run:  python3 test_scan_roles.py
Exit: 0 = all assertions passed; 1 = a failure occurred.
"""
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Point at the script under test (same directory).
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sync_check


def _check_repo_flat_layout():
    """Repo layout: flat *.md files, no directories with how-to.md."""
    fails = []
    tmp = Path(tempfile.mkdtemp(prefix="test_scan_roles_repo_"))
    try:
        (tmp / "sops").mkdir()
        # 00-START-HERE + 5 non-role docs + 6 real roles
        (tmp / "00-START-HERE.md").write_text("index")
        for name in ["BUILDER-PROMPT", "IDENTITY", "SOUL", "TOOLS", "how-to-use-this-department"]:
            (tmp / f"{name}.md").write_text("scaffold")
        for slug in ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]:
            (tmp / f"{slug}.md").write_text("role")

        with (
            patch.object(sync_check, "PRES_DIR", tmp),
            patch.object(sync_check, "SOPS_DIR", tmp / "sops"),
        ):
            role_stems, sop_files = sync_check.scan_roles_and_sops()

        # 00-START-HERE excluded, 5 non-role docs excluded -> 6 remaining
        if len(role_stems) != 6:
            fails.append(f"REPO-FLAT: expected 6 role stems, got {len(role_stems)}: {sorted(role_stems)}")
        if "00-START-HERE" in role_stems:
            fails.append("REPO-FLAT: 00-START-HERE leaked into role_stems")
        for nd in sync_check._NON_ROLE_DOCS:
            if nd in role_stems:
                fails.append(f"REPO-FLAT: non-role doc {nd!r} leaked into role_stems")
        for slug in ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]:
            if slug not in role_stems:
                fails.append(f"REPO-FLAT: real role {slug!r} missing from role_stems")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fails


def test_repo_flat_layout():
    fails = _check_repo_flat_layout()
    assert not fails, "\n".join(fails)


def _check_deployed_dir_layout():
    """Deployed department layout: <NN->?<slug>/how-to.md for roles, infra filtered."""
    fails = []
    tmp = Path(tempfile.mkdtemp(prefix="test_scan_roles_deployed_"))
    try:
        (tmp / "sops").mkdir()
        # Numbered role dirs
        for numbered in [("01-alpha", "alpha"), ("24-beta", "beta")]:
            d = tmp / numbered[0]
            d.mkdir()
            (d / "how-to.md").write_text("role content")
        # Bare role dirs
        for bare in ["gamma", "delta"]:
            d = tmp / bare
            d.mkdir()
            (d / "how-to.md").write_text("role content")
        # Infra dirs with how-to.md
        for infra in ["scripts", "sops", "memory", "working", ".openclaw"]:
            d = tmp / infra
            d.mkdir(exist_ok=True)
            (d / "how-to.md").write_text("infra content")
        # Broken symlink how-to.md (should not count)
        broken_dir = tmp / "broken-role"
        broken_dir.mkdir()
        (broken_dir / "how-to.md").symlink_to("/nonexistent/path/how-to.md")

        with (
            patch.object(sync_check, "PRES_DIR", tmp),
            patch.object(sync_check, "SOPS_DIR", tmp / "sops"),
        ):
            role_stems, sop_files = sync_check.scan_roles_and_sops()

        # 4 real roles: alpha, beta, gamma, delta
        if len(role_stems) != 4:
            fails.append(f"DEPLOYED: expected 4 role stems, got {len(role_stems)}: {sorted(role_stems)}")
        for infra in sync_check._INFRA_DIRS:
            if infra in role_stems:
                fails.append(f"DEPLOYED: infra dir {infra!r} leaked into role_stems")
        for slug in ["alpha", "beta", "gamma", "delta"]:
            if slug not in role_stems:
                fails.append(f"DEPLOYED: real role {slug!r} missing from role_stems")
        if "broken-role" in role_stems:
            fails.append("DEPLOYED: broken-symlink role leaked into role_stems (dangling how-to.md)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fails


def test_deployed_dir_layout():
    fails = _check_deployed_dir_layout()
    assert not fails, "\n".join(fails)


def _check_denumbering_anchor():
    """De-numbering regex is anchored ^\\d\\d-, not \\d+-."""
    fails = []
    tmp = Path(tempfile.mkdtemp(prefix="test_scan_roles_denum_"))
    try:
        (tmp / "sops").mkdir()
        (tmp / "01-intro").mkdir()
        ((tmp / "01-intro") / "how-to.md").write_text("role")
        (tmp / "123-slug").mkdir()
        ((tmp / "123-slug") / "how-to.md").write_text("role")

        with (
            patch.object(sync_check, "PRES_DIR", tmp),
            patch.object(sync_check, "SOPS_DIR", tmp / "sops"),
        ):
            role_stems, sop_files = sync_check.scan_roles_and_sops()

        # 01-intro -> intro (de-numbered)
        if "intro" not in role_stems:
            fails.append(f"DENUM: expected 'intro' (from 01-intro), got: {sorted(role_stems)}")
        if "01-intro" in role_stems:
            fails.append("DENUM: raw '01-intro' not stripped of prefix")
        # 123-slug stays as 123-slug (three digits, not matched by ^\\d\\d-)
        if "123-slug" not in role_stems:
            fails.append(f"DENUM: expected '123-slug' (three-digit prefix not stripped), got: {sorted(role_stems)}")
        if "slug" in role_stems:
            fails.append("DENUM: '123-slug' was incorrectly de-numbered to 'slug'")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fails


def test_denumbering_anchor():
    fails = _check_denumbering_anchor()
    assert not fails, "\n".join(fails)


def _check_flat_and_dir_together():
    """Both flat *.md and directory roles coexist in the same layout."""
    fails = []
    tmp = Path(tempfile.mkdtemp(prefix="test_scan_roles_mixed_"))
    try:
        (tmp / "sops").mkdir()
        (tmp / "flat-only.md").write_text("role")
        (tmp / "05-numbered").mkdir()
        ((tmp / "05-numbered") / "how-to.md").write_text("role")
        # Same slug in both flat and dir form (should dedupe via set)
        (tmp / "dupe.md").write_text("role")
        (tmp / "dupe").mkdir()
        ((tmp / "dupe") / "how-to.md").write_text("role")

        with (
            patch.object(sync_check, "PRES_DIR", tmp),
            patch.object(sync_check, "SOPS_DIR", tmp / "sops"),
        ):
            role_stems, sop_files = sync_check.scan_roles_and_sops()

        if len(role_stems) != 3:
            fails.append(f"MIXED: expected 3 role stems, got {len(role_stems)}: {sorted(role_stems)}")
        for expected in ["flat-only", "numbered", "dupe"]:
            if expected not in role_stems:
                fails.append(f"MIXED: {expected!r} missing from role_stems")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fails


def test_flat_and_dir_together():
    fails = _check_flat_and_dir_together()
    assert not fails, "\n".join(fails)


def _check_symlink_followed_dir():
    """d.is_dir() follows symlinks; a symlinked role directory counts."""
    fails = []
    tmp = Path(tempfile.mkdtemp(prefix="test_scan_roles_symlink_"))
    try:
        (tmp / "sops").mkdir()
        real_dir = tmp / "real-role"
        real_dir.mkdir()
        (real_dir / "how-to.md").write_text("role")
        link_dir = tmp / "link-role"
        link_dir.symlink_to(real_dir)

        with (
            patch.object(sync_check, "PRES_DIR", tmp),
            patch.object(sync_check, "SOPS_DIR", tmp / "sops"),
        ):
            role_stems, sop_files = sync_check.scan_roles_and_sops()

        if "real-role" not in role_stems:
            fails.append(f"SYMLINK: real-role missing from role_stems, got: {sorted(role_stems)}")
        if "link-role" not in role_stems:
            fails.append(f"SYMLINK: link-role (symlinked dir) missing from role_stems, got: {sorted(role_stems)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fails


def test_symlink_followed_dir():
    fails = _check_symlink_followed_dir()
    assert not fails, "\n".join(fails)


def _check_module_constants_exist():
    """Prove _INFRA_DIRS and _NON_ROLE_DOCS exist with correct types and values."""
    fails = []
    if not hasattr(sync_check, "_INFRA_DIRS"):
        fails.append("CONST: _INFRA_DIRS missing from sync_check module")
    elif not isinstance(sync_check._INFRA_DIRS, set):
        fails.append(f"CONST: _INFRA_DIRS is {type(sync_check._INFRA_DIRS).__name__}, expected set")
    else:
        expected_infra = {"scripts", "sops", "memory", "working", ".openclaw"}
        if sync_check._INFRA_DIRS != expected_infra:
            fails.append(f"CONST: _INFRA_DIRS is {sync_check._INFRA_DIRS}, expected {expected_infra}")

    if not hasattr(sync_check, "_NON_ROLE_DOCS"):
        fails.append("CONST: _NON_ROLE_DOCS missing from sync_check module")
    elif not isinstance(sync_check._NON_ROLE_DOCS, set):
        fails.append(f"CONST: _NON_ROLE_DOCS is {type(sync_check._NON_ROLE_DOCS).__name__}, expected set")
    else:
        expected_docs = {"BUILDER-PROMPT", "IDENTITY", "SOUL", "TOOLS", "how-to-use-this-department"}
        if sync_check._NON_ROLE_DOCS != expected_docs:
            fails.append(f"CONST: _NON_ROLE_DOCS is {sync_check._NON_ROLE_DOCS}, expected {expected_docs}")
    return fails


def test_module_constants_exist():
    fails = _check_module_constants_exist()
    assert not fails, "\n".join(fails)


def _check_mutation_proof_non_role_docs_removal():
    """Prove the _NON_ROLE_DOCS guard is effective. Monkey-patch it to empty set;
    the five non-role docs should then appear in role_stems."""
    fails = []
    tmp = Path(tempfile.mkdtemp(prefix="test_scan_roles_mutation_"))
    try:
        (tmp / "sops").mkdir()
        (tmp / "00-START-HERE.md").write_text("index")
        for name in ["BUILDER-PROMPT", "IDENTITY", "SOUL", "TOOLS", "how-to-use-this-department"]:
            (tmp / f"{name}.md").write_text("scaffold")
        (tmp / "real-role.md").write_text("role")

        original_non_role = getattr(sync_check, "_NON_ROLE_DOCS", None)
        try:
            sync_check._NON_ROLE_DOCS = set()
            with (
                patch.object(sync_check, "PRES_DIR", tmp),
                patch.object(sync_check, "SOPS_DIR", tmp / "sops"),
            ):
                role_stems, sop_files = sync_check.scan_roles_and_sops()
        finally:
            if original_non_role is not None:
                sync_check._NON_ROLE_DOCS = original_non_role

        leaked = role_stems & {"BUILDER-PROMPT", "IDENTITY", "SOUL", "TOOLS", "how-to-use-this-department"}
        if not leaked:
            fails.append("MUTATION-NRD: clearing _NON_ROLE_DOCS did not leak any non-role docs — guard is ineffective")
        elif len(leaked) != 5:
            fails.append(f"MUTATION-NRD: expected all 5 non-role docs to leak, got {len(leaked)}: {sorted(leaked)}")
        if "real-role" not in role_stems:
            fails.append("MUTATION-NRD: real-role was lost when guard was cleared")

        print(f"  mutation-NRD: 5 leaked={len(leaked)} real-role={'OK' if 'real-role' in role_stems else 'MISSING'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fails


def test_mutation_proof_non_role_docs_removal():
    fails = _check_mutation_proof_non_role_docs_removal()
    assert not fails, "\n".join(fails)


def _check_mutation_proof_infra_dirs_removal():
    """Prove the _INFRA_DIRS guard is effective. Monkey-patch it to empty set;
    infra dirs with how-to.md should then appear in role_stems."""
    fails = []
    tmp = Path(tempfile.mkdtemp(prefix="test_scan_roles_infra_mut_"))
    try:
        (tmp / "sops").mkdir()
        (tmp / "real-role").mkdir()
        ((tmp / "real-role") / "how-to.md").write_text("role")
        for infra in ["scripts", "sops", "memory", "working"]:
            d = tmp / infra
            d.mkdir(exist_ok=True)
            (d / "how-to.md").write_text("infra")

        original_infra = getattr(sync_check, "_INFRA_DIRS", None)
        try:
            sync_check._INFRA_DIRS = set()
            with (
                patch.object(sync_check, "PRES_DIR", tmp),
                patch.object(sync_check, "SOPS_DIR", tmp / "sops"),
            ):
                role_stems, sop_files = sync_check.scan_roles_and_sops()
        finally:
            if original_infra is not None:
                sync_check._INFRA_DIRS = original_infra

        leaked = role_stems & {"scripts", "sops", "memory", "working"}
        if not leaked:
            fails.append("MUTATION-INFRA: clearing _INFRA_DIRS did not leak any infra dirs")
        if "real-role" not in role_stems:
            fails.append("MUTATION-INFRA: real-role was lost when guard was cleared")

        print(f"  mutation-INFRA: leaked={len(leaked)} real-role={'OK' if 'real-role' in role_stems else 'MISSING'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fails


def test_mutation_proof_infra_dirs_removal():
    fails = _check_mutation_proof_infra_dirs_removal()
    assert not fails, "\n".join(fails)


def main():
    test_groups = [
        ("module constants", _check_module_constants_exist),
        ("repo flat layout", _check_repo_flat_layout),
        ("deployed dir layout", _check_deployed_dir_layout),
        ("de-numbering anchor", _check_denumbering_anchor),
        ("mixed flat+dir layout", _check_flat_and_dir_together),
        ("symlink followed dir", _check_symlink_followed_dir),
        ("mutation: non-role docs", _check_mutation_proof_non_role_docs_removal),
        ("mutation: infra dirs", _check_mutation_proof_infra_dirs_removal),
    ]

    all_failures = []
    for name, fn in test_groups:
        print(f"  {name}... ", end="")
        sys.stdout.flush()
        f = fn()
        if f:
            print("FAIL")
            all_failures.extend(f)
        else:
            print("PASS")

    if all_failures:
        print(f"\n--- {len(all_failures)} FAILURE(S) ---")
        for f in all_failures:
            print(f"  FAIL: {f}")
        sys.exit(1)
    else:
        print(f"\nAll {len(test_groups)} test groups passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()

"""F24 — kie_generate.py duplicate + box variant: the hash-lock must exist and BITE.

THE DEFECT
----------
`kie_generate.py` ships from two repo trees under one filename:

    canonical  23-ai-workforce-blueprint/templates/role-library/presentations/scripts/
    mirror     23-ai-workforce-blueprint/templates/presentation-render/

694 lines vs 613. BOTH copies carry a prose "LOCKSTEP NOTE" instructing the next
editor to "keep their LOGIC identical when editing either" -- and nothing graded
that, so the role-library copy's own docstring now records the drift it caused
("the presentation-render twin has NOT yet received that port"). Same disease as
the 8 disagreeing SOPs and the diverging drift-gate scripts: two artifacts under
one name, each internally consistent, disagreeing with each other, no comparator.

THE MIRROR COPY IS LIVE, NOT RETIRED
------------------------------------
06-ghl-install-pages/tools/ghl_media.py resolves `_KIE_GENERATE_RELPATH` straight
at the mirror copy and shells it from `generate_images()`. Deleting or
quarantining it breaks GHL media upload. So the fix is a HASH-LOCK -- pin both
copies at their exact bytes -- never a deletion.

WHAT THIS FILE PROVES
---------------------
Not that the gate file exists (a file is not a gate), but that it DISCRIMINATES:
it must go red when either copy is edited, red when the Skill-06 dependency
target disappears, and green only at the recorded baseline. Every mutation below
is made on a scratch copy of the repo layout -- the real tree is never touched.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CANONICAL_TREE = "23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
MIRROR_TREE = "23-ai-workforce-blueprint/templates/presentation-render"
CHECKER_REL = "scripts/check-shared-script-drift.py"
REGISTRY_REL = "scripts/shared-script-authority.json"
GATE_SH_REL = "scripts/ci/presentations-drift-gates.sh"
GHL_MEDIA_REL = "06-ghl-install-pages/tools/ghl_media.py"


def _repo_root() -> Path:
    cur = Path(__file__).resolve()
    for candidate in cur.parents:
        if (candidate / CANONICAL_TREE).is_dir() and (candidate / MIRROR_TREE).is_dir():
            return candidate
    raise AssertionError(
        "repo root not found walking up from "
        f"{cur} — needed both {CANONICAL_TREE}/ and {MIRROR_TREE}/"
    )


REPO = _repo_root()
CHECKER = REPO / CHECKER_REL
CANONICAL_KIE = REPO / CANONICAL_TREE / "kie_generate.py"
MIRROR_KIE = REPO / MIRROR_TREE / "kie_generate.py"


def _run_checker(*args, repo_root=None):
    argv = [sys.executable, str(CHECKER), *args]
    if repo_root is not None:
        argv += ["--repo-root", str(repo_root)]
    return subprocess.run(argv, capture_output=True, text=True, timeout=180)


def _scratch_repo(tmp_path: Path) -> Path:
    """A minimal copy of the real repo layout the gate reads. Never the real tree."""
    root = tmp_path / "repo"
    (root / CANONICAL_TREE).mkdir(parents=True)
    (root / MIRROR_TREE).mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / GHL_MEDIA_REL).parent.mkdir(parents=True)

    for name in ("kie_generate.py", "slides.schema.json"):
        shutil.copy2(REPO / CANONICAL_TREE / name, root / CANONICAL_TREE / name)
        shutil.copy2(REPO / MIRROR_TREE / name, root / MIRROR_TREE / name)
    shutil.copy2(REPO / GHL_MEDIA_REL, root / GHL_MEDIA_REL)
    shutil.copy2(REPO / REGISTRY_REL, root / REGISTRY_REL)
    return root


# ---------------------------------------------------------------------------
# 1. The instrument must exist and must still discriminate (known-good control).
# ---------------------------------------------------------------------------
def test_hashlock_checker_exists():
    assert CHECKER.is_file(), (
        f"F24 hash-lock checker missing at {CHECKER_REL} — the two kie_generate.py "
        "copies are ungated and free to drift again."
    )


def test_hashlock_checker_self_test_discriminates():
    """A green --check is worthless if the checker cannot tell drift from no-drift."""
    proc = _run_checker("--self-test")
    assert proc.returncode == 0, (
        "check-shared-script-drift.py --self-test did not pass — the checker no "
        f"longer discriminates.\nrc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )
    assert "SELFTEST_PASS" in proc.stdout, proc.stdout


# ---------------------------------------------------------------------------
# 2. The lock is actually recorded, on BOTH copies, at their real bytes.
# ---------------------------------------------------------------------------
def test_registry_pins_both_kie_generate_copies_at_their_real_bytes():
    import hashlib

    registry_path = REPO / REGISTRY_REL
    assert registry_path.is_file(), f"{REGISTRY_REL} missing — nothing is pinned."
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    canonical_rel = f"{CANONICAL_TREE}/kie_generate.py"
    mirror_rel = f"{MIRROR_TREE}/kie_generate.py"
    matches = [
        w for w in registry.get("waivers", [])
        if w.get("canonical_path") == canonical_rel and w.get("mirror_path") == mirror_rel
    ]
    assert len(matches) == 1, (
        f"expected exactly one pinned pair for kie_generate.py, found {len(matches)} "
        f"in {REGISTRY_REL}"
    )
    w = matches[0]
    assert w["canonical_sha256"] == hashlib.sha256(CANONICAL_KIE.read_bytes()).hexdigest(), (
        "the pinned canonical sha does not match the bytes on disk — the lock is stale"
    )
    assert w["mirror_sha256"] == hashlib.sha256(MIRROR_KIE.read_bytes()).hexdigest(), (
        "the pinned mirror sha does not match the bytes on disk — the lock is stale"
    )
    assert w["canonical_sha256"] != w["mirror_sha256"], (
        "the two copies are byte-identical, so this waiver is dead weight — remove it "
        "with --record rather than leaving a pin nothing needs"
    )


def test_gate_is_green_at_the_recorded_baseline():
    proc = _run_checker("--check")
    assert proc.returncode == 0, (
        "the hash-lock gate is red at HEAD.\n"
        f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )


# ---------------------------------------------------------------------------
# 3. MUTATION PROOF — the lock must BITE on either side.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("side,rel", [
    ("mirror", f"{MIRROR_TREE}/kie_generate.py"),
    ("canonical", f"{CANONICAL_TREE}/kie_generate.py"),
])
def test_editing_either_kie_generate_copy_trips_the_lock(tmp_path, side, rel):
    root = _scratch_repo(tmp_path)
    clean = _run_checker("--check", repo_root=root)
    assert clean.returncode == 0, (
        "control failed: the untouched scratch copy is already red, so a red result "
        f"below would prove nothing.\n{clean.stdout}\n{clean.stderr}"
    )

    target = root / rel
    target.write_text(
        target.read_text(encoding="utf-8") + "\n# F24 mutation probe\n", encoding="utf-8")
    dirty = _run_checker("--check", repo_root=root)
    assert dirty.returncode == 1, (
        f"editing the {side} kie_generate.py did NOT trip the hash-lock — the two "
        f"copies can drift again exactly as they already did.\n"
        f"rc={dirty.returncode}\n{dirty.stdout}\n{dirty.stderr}"
    )
    assert "STALE PIN" in dirty.stderr, dirty.stderr


def test_deleting_the_mirror_copy_trips_the_live_dependency_check(tmp_path):
    """Quarantining the mirror copy breaks GHL media upload — it must fail LOUDLY."""
    root = _scratch_repo(tmp_path)
    (root / MIRROR_TREE / "kie_generate.py").unlink()
    proc = _run_checker("--check", repo_root=root)
    assert proc.returncode == 1, (
        "deleting the mirror kie_generate.py passed the gate — nothing would warn "
        "that ghl_media.kie_generate_path() now raises FileNotFoundError and GHL "
        f"media upload is dead.\nrc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )
    assert "LIVE DEPENDENCY BROKEN" in proc.stderr, proc.stderr


# ---------------------------------------------------------------------------
# 4. The reality the lock is built on, asserted independently of the checker.
# ---------------------------------------------------------------------------
def test_ghl_media_still_shells_the_mirror_copy():
    """If Skill 06 ever repoints, CHECK A's premise moves and must be re-derived."""
    import ast
    import os

    consumer = REPO / GHL_MEDIA_REL
    assert consumer.is_file(), f"{GHL_MEDIA_REL} not found"
    tree = ast.parse(consumer.read_text(encoding="utf-8"))
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_KIE_GENERATE_RELPATH" for t in node.targets
        ):
            call = node.value
            assert isinstance(call, ast.Call), "_KIE_GENERATE_RELPATH is no longer an os.path.join(...)"
            found = os.path.join(*[a.value for a in call.args])
    assert found is not None, (
        "_KIE_GENERATE_RELPATH is gone from ghl_media.py — the Skill-06 dependency "
        "this lock protects can no longer be located statically"
    )
    resolved = Path(os.path.normpath(consumer.parent / found)).resolve()
    assert resolved == MIRROR_KIE.resolve(), (
        f"ghl_media.py resolves {resolved}, not the mirror copy {MIRROR_KIE} — the "
        "hash-lock is now guarding a file Skill 06 does not run"
    )
    assert resolved.is_file(), "the Skill-06 generator target does not exist on disk"


# ---------------------------------------------------------------------------
# 5. The gate must be WIRED, not merely written.
# ---------------------------------------------------------------------------
def test_ci_drift_gates_script_runs_the_hashlock_checker():
    gate_sh = REPO / GATE_SH_REL
    assert gate_sh.is_file(), f"{GATE_SH_REL} not found"
    text = gate_sh.read_text(encoding="utf-8")
    assert CHECKER_REL in text, (
        f"{GATE_SH_REL} never invokes {CHECKER_REL} — the hash-lock exists but no CI "
        "gate runs it, which is how the LOCKSTEP NOTE became decorative in the first place"
    )
    assert "--self-test" in text, (
        f"{GATE_SH_REL} runs the checker without proving it still discriminates first"
    )


def test_ci_workflow_fires_on_the_files_the_gate_grades():
    wf = REPO / ".github/workflows/presentations-drift-gates.yml"
    assert wf.is_file(), "presentations-drift-gates.yml not found"
    text = wf.read_text(encoding="utf-8")
    for needed in (CHECKER_REL, REGISTRY_REL, MIRROR_TREE, GHL_MEDIA_REL):
        assert needed in text, (
            f"{needed} is not in the workflow's path filter — a PR touching it would "
            "not fire the job that grades it (the same blind spot already measured "
            "for GATE 6 and GATE 7)"
        )

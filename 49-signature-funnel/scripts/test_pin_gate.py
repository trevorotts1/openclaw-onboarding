# -*- coding: utf-8 -*-
"""Focused tests for scripts/pin_gate.py - the checks behind .github/workflows/sf-prover-pin-gate.yml.

Each test asserts the EXACT failure string of Document 3 lines 1546-1576, because the gate's contract is
the message an engineer reads at 3 AM. Nothing here mints, writes or reseals the pin.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
import front_door  # noqa: E402
import pin_gate  # noqa: E402

REPO = _HERE.parents[2]
PIN = REPO / pin_gate.PIN_REL


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------- the one composition

def test_the_helper_imports_the_writer_instead_of_retyping_the_rules():
    """A second composition is the defect this file exists to prevent."""
    assert pin_gate.fd is front_door
    assert "pin_files" in pin_gate._composed.__code__.co_names  # the writer's list, imported
    assert pin_gate.fd._PIN_SPEC is front_door._PIN_SPEC       # the writer's rules, imported
    for private_list in ("_PIN_RULES", "PIN_GLOBS", "COMPOSITION"):
        assert not hasattr(pin_gate, private_list), f"a second composition appeared: {private_list}"
    for writer in ("write_pin", "mint_pin_ci", "_write_pin_file"):
        assert not hasattr(pin_gate, writer), f"the gate may not write the pin: {writer}"


def test_composition_matches_the_writer_on_this_checkout():
    composed = pin_gate._composed()
    names = [n for n, _ in composed]
    assert names == [n for n, _ in front_door.pin_files(pin_gate.SKILL_DIR)]
    assert len(names) == len(set(names))
    assert not [n for n in names if "/71-" in n or n.startswith("71/")]


# ---------------------------------------------------------------- pin-shape

def test_shape_passes_on_the_real_artifact(capsys):
    assert pin_gate.check_shape() == 0
    assert "PIN-SHAPE OK: one sha256 line" in capsys.readouterr().out


@pytest.mark.parametrize("body,expected", [
    ("a" * 64 + "\n" + "b" * 64 + "\n",
     "PIN-SHAPE: 49-signature-funnel/scripts/SF-PROVER-PIN.sha256 must contain exactly one sha256 line; found 2 lines"),
    ("\n\n", "PIN-SHAPE: 49-signature-funnel/scripts/SF-PROVER-PIN.sha256 must contain exactly one sha256 line; found 0 lines"),
    ("A" * 64 + "\n", "PIN-SHAPE: value is not 64 lowercase hex characters: " + "A" * 64),
    ("abc\n", "PIN-SHAPE: value is not 64 lowercase hex characters: abc"),
])
def test_shape_refuses_a_changed_artifact(tmp_path, capsys, body, expected):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / front_door.PIN_NAME).write_text(body)
    assert pin_gate.check_shape(tmp_path) == 1
    assert expected in capsys.readouterr().out


# ---------------------------------------------------------------- pin-coverage

def test_coverage_is_clean_in_both_directions_on_this_checkout(capsys):
    assert pin_gate.check_coverage() == 0
    out = capsys.readouterr().out
    assert "PIN-COVERAGE OK:" in out and "both directions clean" in out
    assert "PIN-COVERAGE MISSING" not in out and "PIN-COVERAGE EXTRA" not in out


@pytest.mark.parametrize("key,rel,matches", [
    ("83", "launcher_core/launch_bridge.py", True),
    ("83", "launcher_core/check_rules/image_qc.py", False),   # a rule is a directory + basename glob
    ("49", "examples/golden-daybreak/build_golden.py", False),
    ("49", "scripts/vendor/page-request.schema.json", True),
    ("49", "scripts/test_front_door.py", True),               # excluded by _is_test, not by a rule miss
    ("launch", "design/tokens/colors.json", False),           # composed trees are top level only
])
def test_a_rule_is_a_directory_plus_a_basename_glob(key, rel, matches):
    assert bool(pin_gate._match_rules(key, rel)) is matches


def test_coverage_reports_a_file_that_escaped_the_composition(monkeypatch, capsys):
    """The MISSING direction is live: a rule-named file the composition drops is named, not skipped."""
    real = front_door.pin_files
    dropped = "49/scripts/front_door.py"
    monkeypatch.setattr(front_door, "pin_files",
                        lambda sd=None: [(n, p) for n, p in real(sd) if n != dropped])
    assert pin_gate.check_coverage() == 1
    out = capsys.readouterr().out
    assert ("PIN-COVERAGE MISSING: 49-signature-funnel/scripts/front_door.py matches scripts/*.py but is "
            "not in the pin composition") in out


def test_coverage_reports_a_composed_file_that_matches_no_rule(monkeypatch, capsys):
    """The EXTRA direction is live: a hand-added composition entry matches no launch-path rule."""
    real = front_door.pin_files
    monkeypatch.setattr(front_door, "pin_files",
                        lambda sd=None: real(sd) + [("49/examples/stray.py", pin_gate.SKILL_DIR)] )
    assert pin_gate.check_coverage() == 1
    out = capsys.readouterr().out
    assert ("PIN-COVERAGE EXTRA: 49-signature-funnel/examples/stray.py is in the pin composition but "
            "matches no launch-path rule") in out


# ---------------------------------------------------------------- pin-digest

def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def test_digest_never_writes_the_pin_and_names_the_drifted_file(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    scripts = repo / "49-signature-funnel" / "scripts"
    scripts.mkdir(parents=True)
    thing = scripts / "thing.py"
    thing.write_text("v1\n")
    pin = scripts / front_door.PIN_NAME
    pin.write_text("0" * 64 + "\n")
    _git(["init", "-q"], repo)
    _git(["add", "-A"], repo)
    _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "baseline"], repo)
    before = pin.read_bytes()
    thing.write_text("v2\n")

    monkeypatch.setattr(pin_gate, "REPO_ROOT", repo)
    monkeypatch.setattr(pin_gate, "PIN_REL", "49-signature-funnel/scripts/SF-PROVER-PIN.sha256")
    monkeypatch.setattr(front_door, "pin_files",
                        lambda skill_dir=None: [("49/scripts/thing.py",
                                                 Path(skill_dir) / "scripts" / "thing.py")])
    monkeypatch.setattr(front_door, "compute_pin", lambda *a, **k: "f" * 64)

    assert pin_gate.check_digest(repo / "49-signature-funnel") == 1
    out = capsys.readouterr().out
    assert "PIN-DIGEST MISMATCH: expected " + "0" * 64 + \
           " from 49-signature-funnel/scripts/SF-PROVER-PIN.sha256, computed " + "f" * 64 in out
    assert f"PIN-DIGEST DRIFTED FILE: 49-signature-funnel/scripts/thing.py  expected {_sha('v1\n')}  " \
           f"actual {_sha('v2\n')}" in out
    assert pin.read_bytes() == before, "the digest job must never write the pin"


def test_digest_reports_an_unresolvable_baseline(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / "49-signature-funnel" / "scripts").mkdir(parents=True)
    _git(["init", "-q"], repo)  # no commit: nothing ever modified the pin
    monkeypatch.setattr(pin_gate, "REPO_ROOT", repo)
    monkeypatch.setattr(front_door, "compute_pin", lambda *a, **k: "f" * 64)
    (repo / "49-signature-funnel" / "scripts" / front_door.PIN_NAME).write_text("0" * 64 + "\n")
    assert pin_gate.check_digest(repo / "49-signature-funnel") == 1
    assert "PIN-DIGEST NO BASELINE: cannot resolve the commit that last modified the pin; " \
           "run the authorised re-mint" in capsys.readouterr().out


# ---------------------------------------------------------------- pin-scope-vouched

def test_scope_enforces_branch_a_and_names_every_gap(capsys):
    rc = pin_gate.check_scope()
    out = capsys.readouterr().out
    gaps = [ln for ln in out.splitlines() if ln.startswith("PIN-SCOPE GAP: ")]
    assert rc == 1 and gaps, "Branch A is expected red on this tree until the composition is widened"
    assert all(ln.endswith("or narrow the claim as FIX-16 Branch B requires.") for ln in gaps)
    assert any("71-blackceo-signature-page/scripts/copy_forms.py" in ln for ln in gaps)
    assert any("71-blackceo-signature-page/references/copy-specs/roles/checkout.json" in ln for ln in gaps)
    assert f"PIN-SCOPE: {len(gaps)} behaviour file(s) outside the composition" in out


@pytest.mark.parametrize("path,matches", [
    ("71-x/scripts/copy_forms.py", True),
    ("a/b/c/page_role.py", True),
    ("a/b/copy_forms.pyc", False),
    ("71-x/references/copy-specs/roles/checkout.json", True),
    ("71-x/references/copy-specs/standard-v6.json", True),
    ("71-x/references/copy-specs/README.md", False),
])
def test_scope_glob_semantics(path, matches):
    assert any(pin_gate._glob_re(g).match(path) for g in pin_gate.SCOPE_GLOBS) is matches


# ---------------------------------------------------------------- suite

@pytest.mark.parametrize("text,expected", [
    ("205 failed, 550 passed, 1 warning, 43 subtests passed in 12.3s", {"failed": 205, "passed": 550}),
    ("672 passed in 3.1s", {"passed": 672}),
    ("1 error, 671 passed, 3 skipped in 9s", {"error": 1, "passed": 671, "skipped": 3}),
    ("2 errors in 1s", {"error": 2}),
])
def test_suite_summary_counts(text, expected):
    counts = pin_gate._counts(text)
    assert {k: counts[k] for k in expected} == expected


def test_suite_refuses_an_unidentifiable_runner(tmp_path, capsys):
    rc = pin_gate.check_suite(tmp_path)  # no 83-black-friday-launcher here: pytest collects nothing
    assert rc == 2
    assert "SUITE RUNNER UNKNOWN: pytest is unavailable or collected nothing; identify the repository's " \
           "runner and pin it in this job before the gate can pass" in capsys.readouterr().out


def test_suite_expected_count_is_the_documented_baseline():
    assert pin_gate.EXPECTED_COLLECTED == 672
    assert pin_gate.SUITE_TARGET == "83-black-friday-launcher"


# ---------------------------------------------------------------- the workflow itself

GATE_YML = REPO / ".github" / "workflows" / "sf-prover-pin-gate.yml"
AUTHORITY_YML = REPO / ".github" / "workflows" / "sf-prover-pin-authority.yml"
SIX_JOBS = ("pin-digest", "pin-shape", "pin-coverage", "pin-scope-vouched", "suite", "authority-guard")


def test_the_gate_declares_the_six_jobs_of_document_3_section_9():
    text = GATE_YML.read_text(encoding="utf-8")
    for job in SIX_JOBS:
        assert f"\n  {job}:\n" in text, f"job {job} is missing"
    assert text.count("\n  pin-") + text.count("\n  suite:") + text.count("\n  authority-guard:") == 6


def test_every_gate_job_calls_the_one_helper():
    text = GATE_YML.read_text(encoding="utf-8")
    calls = [ln.strip() for ln in text.splitlines()
             if ln.strip().startswith("python3 ") and "pin_gate.py" in ln]
    want = {"digest", "shape", "coverage", "scope", "suite"}
    assert len(calls) == 5, calls
    assert all(c.startswith("python3 49-signature-funnel/scripts/pin_gate.py ") for c in calls), calls
    assert {c.rsplit(" ", 1)[1] for c in calls} == want, calls
    assert "front_door.py" not in text, "a job must not reach past the helper into the writer's CLI"


def test_the_gate_has_the_four_declared_triggers():
    text = GATE_YML.read_text(encoding="utf-8")
    assert "workflow_call:" in text and "workflow_dispatch:" in text
    assert "types: [opened, synchronize, reopened]" in text
    assert "branches: [main]" in text and '"ghl-hybrid/**"' in text


def test_the_gate_carries_no_bypass_flag_or_environment_skip():
    for path in (GATE_YML, REPO / "49-signature-funnel" / "scripts" / "pin_gate.py"):
        text = path.read_text(encoding="utf-8")
        for bypass in ("continue-on-error", "|| true", "--no-verify", "SKIP_GATE", "ALLOW_RED"):
            assert bypass not in text, f"{path.name} would let a red gate pass: {bypass}"


def test_the_only_job_excluded_from_the_reusable_call_is_pin_digest():
    text = GATE_YML.read_text(encoding="utf-8")
    excluded = [block.split("\n")[0].strip() for block in text.split("\n  ") if "github.event_name != 'workflow_call'" in block]
    assert len(excluded) == 1, excluded
    block = text.split("\n  pin-digest:\n", 1)[1].split("\n  pin-shape:\n", 1)[0]
    assert "github.event_name != 'workflow_call'" in block


def test_the_authority_workflow_declares_the_gate_and_keeps_verify_and_mint():
    text = AUTHORITY_YML.read_text(encoding="utf-8")
    assert "\n  gate:\n" in text and "uses: ./.github/workflows/sf-prover-pin-gate.yml" in text
    mint = text.split("\n  mint:\n", 1)[1]
    assert "needs: [gate]" in mint, "the mint must depend on the gate"
    assert "mint-pin --ci" in mint and "git push origin" in mint, "the mint job must stay intact"
    verify = text.split("\n  verify:\n", 1)[1].split("\n  gate:\n", 1)[0]
    assert "hashpin" in verify and "bypass-scan" in verify, "the verify job must stay intact"


def test_the_authority_guard_prints_the_exact_refusal():
    assert ("PIN-AUTHORITY REFUSED: gate job failed; a re-mint over red bytes is a forgery") in \
        (REPO / "49-signature-funnel" / "scripts" / "pin_gate.py").read_text(encoding="utf-8") or \
        ("PIN-AUTHORITY REFUSED: gate job failed; a re-mint over red bytes is a forgery") in GATE_YML.read_text(encoding="utf-8")

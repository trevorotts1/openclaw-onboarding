#!/usr/bin/env python3
"""test_f23_drift_gate_pr_paths.py -- F23: the drift-gate job must FIRE on a
pull request that touches any path its own gates read.

`.github/workflows/presentations-drift-gates.yml` already carries an
`on.pull_request` trigger (the review note that said it had "no PR trigger" was
wrong -- see the note in section 14 of the review, marked "Not re-verified").
What it did NOT carry was a path filter that covers everything the job reads.
A `paths:` filter is fail-OPEN by construction: a PR touching a file the filter
does not name does not run the job at all, so every gate that grades that file
is silently skipped and the drift merges green.

Measured on ea331f82a (2026-09-06) with the same matcher this test uses: of the
323 repo files the job's own gates read, 257 were not matched by any entry in
the filter -- among them `build_deck.py` (the engine verify.sh runs), the
FIX-14/18/19 self-test scripts, all 16 duplicate-SOP files GATE 6 compares, the
GATE 6 waiver registry, and `role-library/_index.json`.

This test derives the governed set MECHANICALLY from what the gates do, rather
than from a hand-kept list that would rot the moment a gate grows a new input:

  GATE 1 / GATE 3  `cp -R "$SCRIPTS_DIR/."` into a temp tree and import
                   `presentation_job.phases` out of it -- the whole engine
                   scripts dir is the import surface, not five named files.
                   51-signature-presentation/verify.sh, which this job also
                   runs, resolves its ENGINE (build_deck.py), sync_check.py and
                   the FIX-14/18/19 self-test scripts out of that same dir.
  GATE 6           `scripts/check-duplicate-sop-drift.py` rglobs BOTH trees --
                   every `role-library/<dept>/sops/*.md` against every
                   `universal-sops/**/*.md` with the same basename -- and grades
                   each pair against `scripts/duplicate-sop-authority.json`.
                   A new file on EITHER side can create a violating pair, so the
                   filter has to cover the scan roots, not just today's pairs.
  verify.sh        `register-library-additions.py --check` reads
                   `role-library/_index.json`; the FIX-19 leg does a live sliced
                   read of `sops/qc-specialist-presentations-sops.md` and
                   asserts `total_bytes > 100_000`.

Nothing here asserts the job PASSES -- it is red on main for an unrelated
reason. It asserts only that a PR touching a governed file makes the job RUN.

Flat file inside tests/, manages its own import path -- matching every sibling
in this directory.
"""
from __future__ import annotations

import os
import pathlib
import re

import pytest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO = SCRIPTS
for _ in range(8):
    if (REPO / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json").is_file():
        break
    REPO = REPO.parent

WORKFLOW = REPO / ".github" / "workflows" / "presentations-drift-gates.yml"
GATE_SCRIPT = REPO / "scripts" / "ci" / "presentations-drift-gates.sh"
VERIFY_SH = REPO / "51-signature-presentation" / "verify.sh"
DEPT_REL = "23-ai-workforce-blueprint/templates/role-library/presentations"
ROLE_LIBRARY = REPO / "23-ai-workforce-blueprint" / "templates" / "role-library"
UNIVERSAL_SOPS = REPO / "universal-sops"


# ---------------------------------------------------------------------------
# the filter, parsed; and a GitHub-path-filter matcher
# ---------------------------------------------------------------------------
def _pull_request_paths() -> list[str]:
    """The literal `on.pull_request.paths:` list, in file order.

    Hand-parsed rather than via PyYAML: the suite must not grow a third-party
    dependency to check a CI trigger, and the block is a flat scalar list.
    """
    lines = WORKFLOW.read_text(encoding="utf-8").split("\n")
    i = 0
    while i < len(lines) and lines[i].strip() != "pull_request:":
        i += 1
    assert i < len(lines), (
        "presentations-drift-gates.yml has NO `pull_request:` trigger -- every "
        "drift gate in it is push-only and cannot block a PR."
    )
    pr_indent = len(lines[i]) - len(lines[i].lstrip())
    # find `paths:` INSIDE the pull_request block (indented deeper than it)
    i += 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            i += 1
            continue
        if len(line) - len(line.lstrip()) <= pr_indent:
            i = len(lines)  # left the block without finding paths:
            break
        if stripped == "paths:":
            break
        i += 1
    assert i < len(lines), (
        "`pull_request:` carries no `paths:` block -- the job fires on every PR, "
        "which is not what this test grades; re-derive before trusting it."
    )
    out: list[str] = []
    for line in lines[i + 1:]:
        stripped = line.strip()
        if stripped.startswith("- "):
            out.append(stripped[2:].strip().strip('"').strip("'"))
        elif stripped == "" or stripped.startswith("#"):
            continue
        else:
            break
    return out


def _to_regex(pattern: str) -> re.Pattern:
    """GitHub path-filter glob -> regex.

    `**` matches any characters INCLUDING `/`; `*` matches any character except
    `/`; `?` matches one non-`/` character; everything else is literal.
    """
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile("^" + out + "$")


@pytest.fixture(scope="module")
def matcher():
    pats = _pull_request_paths()
    regs = [(p, _to_regex(p)) for p in pats]

    def fires_on(repo_rel_path: str) -> bool:
        return any(rx.match(repo_rel_path) for _, rx in regs)

    fires_on.patterns = pats  # type: ignore[attr-defined]
    return fires_on


def _report(kind: str, misses: list[str]) -> str:
    shown = "\n  ".join(misses[:12])
    more = "" if len(misses) <= 12 else f"\n  ... and {len(misses) - 12} more"
    return (
        f"{len(misses)} {kind} are NOT matched by any "
        f"on.pull_request.paths entry -- a PR touching one of them does not run "
        f"the job, so the gate that grades it cannot block the change:\n  "
        f"{shown}{more}"
    )


# ===========================================================================
# 0. the instrument itself must discriminate
# ===========================================================================
class TestMatcherIsNotARubberStamp:
    def test_workflow_and_gate_script_exist(self):
        assert WORKFLOW.is_file(), f"missing {WORKFLOW}"
        assert GATE_SCRIPT.is_file(), f"missing {GATE_SCRIPT}"
        assert VERIFY_SH.is_file(), f"missing {VERIFY_SH}"

    def test_filter_is_non_empty(self, matcher):
        assert len(matcher.patterns) >= 10, matcher.patterns

    def test_known_governed_file_matches(self, matcher):
        # positive control: the workflow lists itself, and has since it was written
        assert matcher(".github/workflows/presentations-drift-gates.yml")

    def test_ungoverned_file_does_not_match(self, matcher):
        # negative control: if these matched, "covered" would mean nothing
        for path in ("CHANGELOG.md", "README.md", "package.json"):
            assert not matcher(path), (
                f"{path} matches the drift-gate path filter -- the filter (or "
                f"this matcher) is too broad to prove anything."
            )

    def test_push_trigger_survives(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert "push:" in text and "branches: [main]" in text, (
            "the push-on-main trigger is gone -- the job would no longer run "
            "post-merge either."
        )


# ===========================================================================
# 1. GATE 1 / GATE 3 / verify.sh: the WHOLE engine scripts dir
# ===========================================================================
class TestEngineScriptsDirCovered:
    def test_gates_really_copy_the_whole_scripts_dir(self):
        """Pin the premise, so this class fails loudly if the gates stop doing it."""
        src = GATE_SCRIPT.read_text(encoding="utf-8")
        assert 'SCRIPTS_DIR="' + DEPT_REL + '/scripts"' in src
        assert src.count('cp -R "$SCRIPTS_DIR/."') >= 2, (
            "GATE 1 and GATE 3 no longer copy the whole scripts dir -- re-derive "
            "the governed set before trusting this test."
        )

    def test_every_engine_script_file_fires_the_job(self, matcher):
        root = REPO / DEPT_REL / "scripts"
        assert root.is_dir(), f"missing {root}"
        misses = []
        seen = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                rel = str(pathlib.Path(dirpath, name).relative_to(REPO))
                seen += 1
                if not matcher(rel):
                    misses.append(rel)
        assert seen > 100, f"only {seen} files walked -- the walk is broken, not the filter"
        assert not misses, _report("engine scripts-dir files", sorted(misses))

    @pytest.mark.parametrize("name", [
        "build_deck.py",            # verify.sh ENGINE + engine wire-presence gate
        "check_agent_env.py",       # verify.sh FIX-14 --self-test
        "tool_schema_validator.py",  # verify.sh FIX-18 --self-test
        "read_slice.py",            # verify.sh FIX-19 --self-test + live sliced read
        "sync_check.py",            # GATE 5 + verify.sh lockstep leg
    ])
    def test_named_verify_sh_inputs_fire_the_job(self, matcher, name):
        rel = f"{DEPT_REL}/scripts/{name}"
        assert (REPO / rel).is_file(), f"missing {rel}"
        assert matcher(rel)


# ===========================================================================
# 2. GATE 6: both duplicate-SOP scan roots, not just today's pairs
# ===========================================================================
def _duplicate_sop_pairs() -> list[tuple[str, str]]:
    """Replicates check-duplicate-sop-drift.collect_pairs: same basename on both
    sides, across EVERY department that ships a sops/ dir."""
    universal: dict[str, list[pathlib.Path]] = {}
    for path in sorted(UNIVERSAL_SOPS.rglob("*.md")):
        universal.setdefault(path.name, []).append(path)
    pairs = []
    for dept in sorted(p for p in ROLE_LIBRARY.iterdir() if p.is_dir()):
        sops = dept / "sops"
        if not sops.is_dir():
            continue
        for path in sorted(sops.rglob("*.md")):
            for peer in universal.get(path.name, []):
                pairs.append((str(path.relative_to(REPO)), str(peer.relative_to(REPO))))
    return pairs


class TestDuplicateSopGateCovered:
    def test_pairs_exist_at_all(self):
        # control: if this is empty, the two tests below prove nothing
        assert _duplicate_sop_pairs(), (
            "no duplicate-SOP pairs found -- collect_pairs replication is broken"
        )

    def test_every_paired_sop_fires_the_job(self, matcher):
        misses = sorted({p for pair in _duplicate_sop_pairs() for p in pair
                         if not matcher(p)})
        assert not misses, _report("GATE 6 duplicate-SOP files", misses)

    def test_waiver_registry_fires_the_job(self, matcher):
        rel = "scripts/duplicate-sop-authority.json"
        assert (REPO / rel).is_file(), f"missing {rel}"
        assert matcher(rel), (
            "GATE 6's waiver registry is outside the filter -- a PR that deletes "
            "a waiver flips the gate to FAILED without running it."
        )

    def test_scan_roots_are_covered_not_just_todays_files(self, matcher):
        """A NEW .md on either side can create a violating pair, so the filter
        must cover the roots the gate rglobs -- every dept's sops/ dir and the
        whole universal-sops tree."""
        depts = sorted(p.name for p in ROLE_LIBRARY.iterdir() if (p / "sops").is_dir())
        assert len(depts) >= 5, depts  # control: the scan really is multi-department
        misses = []
        for dept in depts:
            probe = (f"23-ai-workforce-blueprint/templates/role-library/"
                     f"{dept}/sops/PROBE-NEW-SOP.md")
            if not matcher(probe):
                misses.append(probe)
        for probe in ("universal-sops/presentation-slide-craft/PROBE-NEW-SOP.md",
                      "universal-sops/PROBE-NEW-PACK/PROBE-NEW-SOP.md"):
            if not matcher(probe):
                misses.append(probe)
        assert not misses, _report("GATE 6 scan-root probes", misses)


# ===========================================================================
# 3. verify.sh inputs that live outside 51-signature-presentation/
# ===========================================================================
class TestVerifyShExternalInputsCovered:
    def test_role_library_index_fires_the_job(self, matcher):
        src = VERIFY_SH.read_text(encoding="utf-8")
        assert "register-library-additions.py" in src and "--check" in src, (
            "verify.sh no longer runs register-library-additions.py --check -- "
            "re-derive this input."
        )
        rel = "23-ai-workforce-blueprint/templates/role-library/_index.json"
        assert (REPO / rel).is_file(), f"missing {rel}"
        assert matcher(rel), (
            "_index.json is the single machine source of truth register --check "
            "grades, and a PR editing it does not run the job."
        )

    def test_fix19_live_read_target_fires_the_job(self, matcher):
        src = VERIFY_SH.read_text(encoding="utf-8")
        target = "qc-specialist-presentations-sops.md"
        assert target in src, (
            "verify.sh no longer reads " + target + " -- re-derive this input."
        )
        rel = f"{DEPT_REL}/sops/{target}"
        assert (REPO / rel).is_file(), f"missing {rel}"
        assert matcher(rel), (
            "verify.sh asserts total_bytes > 100_000 on this SOP; a PR that "
            "shrinks it fails the job -- but does not run it."
        )


# ===========================================================================
# 4. the inputs the filter already named stay named (no silent narrowing)
# ===========================================================================
class TestExistingCoverageNotWeakened:
    @pytest.mark.parametrize("rel", [
        "scripts/ci/presentations-drift-gates.sh",
        "scripts/ci/phase_doc_sync.py",
        "scripts/check-duplicate-sop-drift.py",
        "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json",
        "universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt",
        "universal-sops/_content-manifest.json",
        "universal-sops/presentation-slide-craft/SOP-SLIDE-05-PROCESS-MANIFEST.md",
        f"{DEPT_REL}/00-START-HERE.md",
        f"{DEPT_REL}/DEPARTMENT-COUNTS-CANONICAL.md",
        f"{DEPT_REL}/director-of-presentations.md",
        f"{DEPT_REL}/pptx-assembly-specialist.md",
        f"{DEPT_REL}/slide-image-creator.md",
        f"{DEPT_REL}/qc-specialist-prompt-presentations.md",
        "23-ai-workforce-blueprint/scripts/register-library-additions.py",
        "51-signature-presentation/verify.sh",
        ".github/workflows/presentations-drift-gates.yml",
    ])
    def test_previously_covered_path_still_fires(self, matcher, rel):
        assert (REPO / rel).is_file(), f"missing {rel} (path list is stale)"
        assert matcher(rel)

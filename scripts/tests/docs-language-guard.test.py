#!/usr/bin/env python3
"""Unit tests for scripts/check-docs-language.py — the U92 (X/U-X2) docs-language
CI guard that locks in U91's verified scrub of the operator-banned coded term.

Every fixture repo here is a disposable, hermetic `git init` sandbox under
tmp_path — never the real repo's own history — so these tests are reproducible
regardless of which commit happens to be HEAD^1 in the real onboarding repo at
run time. Proves the three behaviors the unit's own acceptance bar names:
  1. passes when a diff introduces no new occurrence of the term (incl. the
     no-doc-files-changed and single-commit-repo edge cases);
  2. FAILS on an injected brand-new, unexplained occurrence;
  3. still passes when the term appears ONLY inside an allowlisted legacy
     filename citation or an allowlisted vendor literal — and (bonus
     coverage) the "same line resurfacing from history" carve-out, while
     proving none of the three carve-outs over-allows a genuinely new stray
     occurrence riding alongside an allowed one.

Run:
    python3 scripts/tests/docs-language-guard.test.py
    or: pytest scripts/tests/docs-language-guard.test.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "check-docs-language.py"
_ALLOWLIST = _REPO_ROOT / "scripts" / "docs-language-allowlist.json"

_ALLOWLIST_DATA = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))
TERM = _ALLOWLIST_DATA["term"]

# vendor_literals is EMPTY by default in the real allowlist (U91's scrub
# found zero surviving vendor-literal citations in v2 — see that file's own
# $comment). The vendor-literal carve-out mechanism therefore cannot be
# exercised against the real allowlist; tests that need a populated
# vendor_literals entry build a disposable, hermetic FIXTURE allowlist
# (see `_write_fixture_allowlist` below) instead of depending on real
# repo content — a real allowlist entry could grow, shrink, or be reworded
# for legitimate reasons without that being this guard-mechanism test's
# business.
_FIXTURE_VENDOR_LITERAL = f"acme-widgets@{TERM}"  # narrow, npm-dist-tag-shaped, never a natural-English phrase

# legacy_filenames is now EMPTY in the real allowlist too: it shipped at 6, and
# both owning units landed their renames on 2026-07-16 (U30/B-U16's four,
# U93/X-U-X3's two), spending the carve-out. This constant used to be read live
# out of the real allowlist (`entries[0]["path"]`) — which coupled this
# guard-MECHANISM suite to transient repo content and made the whole module fail
# at import (IndexError on an empty list) the moment the last rename landed,
# i.e. exactly when the guard was working as designed. The legacy-filename
# carve-out is therefore exercised the same hermetic way the vendor-literal one
# already is, per this file's own doctrine above: a disposable FIXTURE entry, so
# the mechanism stays under test forever even though no real legacy filename
# remains.
_FIXTURE_LEGACY_FILENAME = f"99-fixture-skill/scripts/run-{TERM}-probe.sh"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    cmd = [
        "git",
        "-c", "user.name=U92 Test Bot",
        "-c", "user.email=u92-test@example.invalid",
        "-c", "commit.gpgsign=false",
        "-C", str(repo),
        *args,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {args} failed: {res.stderr}")
    return res


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    return repo


def _write(repo: Path, rel: str, content: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _write_fixture_allowlist(tmp_path: Path, *, vendor_literals: list[str] | None = None,
                              legacy_filenames: list[str] | None = None) -> Path:
    """A disposable, hermetic allowlist JSON — same shape as the real repo
    allowlist but with caller-controlled vendor_literals / legacy_filenames
    lists, so BOTH carve-out mechanisms can be tested without depending on
    (or requiring) real, currently-populated allowlist content. Both lists
    are empty in the real allowlist today, so neither carve-out could be
    exercised against it."""
    path = tmp_path / "fixture-allowlist.json"
    path.write_text(json.dumps({
        "term": TERM,
        "legacy_filenames": {
            "entries": [{"path": p, "owner": "FIXTURE"} for p in (legacy_filenames or [])]
        },
        "vendor_literals": {"entries": vendor_literals or []},
    }), encoding="utf-8")
    return path


def _run_guard(repo: Path, base_ref: str | None = None,
                allowlist: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable, str(_SCRIPT),
        "--repo-root", str(repo),
        "--allowlist", str(allowlist or _ALLOWLIST),
    ]
    if base_ref:
        cmd += ["--base-ref", base_ref]
    return subprocess.run(cmd, capture_output=True, text=True)


class TestPassesWithNoNewOccurrence(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _init_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_changed_doc_files_passes(self):
        _write(self.repo, "tool.py", "print('hello')\n")
        _commit(self.repo, "base")
        _write(self.repo, "tool.py", f"print('hello')\nprint('{TERM} raw in code, not a doc')\n")
        _commit(self.repo, "change a non-doc file only")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("0 changed doc file", res.stdout)

    def test_changed_doc_with_no_new_occurrence_passes(self):
        _write(self.repo, "README.md", "# Title\n\nOriginal line.\n")
        _commit(self.repo, "base")
        _write(self.repo, "README.md", "# Title\n\nOriginal line.\n\nA brand-new, clean line.\n")
        _commit(self.repo, "add clean content")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("PASS", res.stdout)

    def test_single_commit_repo_nothing_to_diff_passes(self):
        _write(self.repo, "README.md", f"mentions {TERM} but there is no prior commit to diff\n")
        _commit(self.repo, "only commit")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_scope_ignores_non_doc_extensions(self):
        """A raw new occurrence in a .py file must NOT be flagged — the guard
        only ever scans *.md/*.mdx/*.rst/*.txt."""
        _write(self.repo, "tool.py", "x = 1\n")
        _commit(self.repo, "base")
        _write(self.repo, "tool.py", f"x = 1\ny = '{TERM}'  # brand new, unexplained, but not a doc\n")
        _commit(self.repo, "add raw term to a .py file")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


class TestFailsOnInjectedOccurrence(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _init_repo(Path(self._tmp.name))
        _write(self.repo, "README.md", "# Title\n\nOriginal line.\n")
        _commit(self.repo, "base")

    def tearDown(self):
        self._tmp.cleanup()

    def test_fails_on_new_unexplained_occurrence(self):
        _write(self.repo, "README.md",
               f"# Title\n\nOriginal line.\n\nThis new sentence uses the retired {TERM} word directly.\n")
        _commit(self.repo, "inject a new unexplained occurrence")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("README.md", res.stdout)
        self.assertIn("NEW unexplained occurrence", res.stdout)

    def test_failure_message_names_the_exact_added_line_number(self):
        _write(self.repo, "README.md",
               "# Title\n\nOriginal line.\n\npadding one\npadding two\n"
               f"line six has the retired {TERM} word\n")
        _commit(self.repo, "inject at a known line number")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("README.md:7:", res.stdout)

    def test_fails_in_a_second_doc_file_type(self):
        _write(self.repo, "docs/notes.txt", f"a fresh {TERM} mention in a .txt file\n")
        _commit(self.repo, "inject into a .txt doc")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("notes.txt", res.stdout)


class TestAllowlistCarveouts(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _init_repo(Path(self._tmp.name))
        _write(self.repo, "README.md", "# Title\n\nOriginal line.\n")
        _commit(self.repo, "base")

    def tearDown(self):
        self._tmp.cleanup()

    def test_passes_when_only_legacy_filename_cited(self):
        """Exercises the legacy_filenames carve-out mechanism itself via a
        hermetic FIXTURE allowlist (the real allowlist now ships this list
        empty — both owning rename units landed — see
        TestAllowlistFileItselfIsValid's exact-0 pin)."""
        fixture_allowlist = _write_fixture_allowlist(
            Path(self._tmp.name), legacy_filenames=[_FIXTURE_LEGACY_FILENAME]
        )
        _write(self.repo, "README.md",
               "# Title\n\nOriginal line.\n\n"
               f"See `{_FIXTURE_LEGACY_FILENAME}` for the scheduled drift check (rename pending).\n")
        _commit(self.repo, "cite a legacy filename")

        res = _run_guard(self.repo, allowlist=fixture_allowlist)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_passes_when_only_vendor_literal_cited(self):
        """Exercises the vendor_literals carve-out mechanism itself via a
        hermetic FIXTURE allowlist (the real allowlist ships this list empty
        by default — see TestVendorLiteralsEmptyByDefault below)."""
        fixture_allowlist = _write_fixture_allowlist(
            Path(self._tmp.name), vendor_literals=[_FIXTURE_VENDOR_LITERAL]
        )
        _write(self.repo, "README.md",
               "# Title\n\nOriginal line.\n\n"
               f"Upstream publishes a pre-release under {_FIXTURE_VENDOR_LITERAL}, a name we do not own.\n")
        _commit(self.repo, "cite a vendor literal")

        res = _run_guard(self.repo, allowlist=fixture_allowlist)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_stray_occurrence_alongside_allowed_filename_still_fails(self):
        """The subtraction must be span-precise: an allowed filename citation on
        a line does NOT amnesty an extra, separate, unexplained mention on that
        same line."""
        fixture_allowlist = _write_fixture_allowlist(
            Path(self._tmp.name), legacy_filenames=[_FIXTURE_LEGACY_FILENAME]
        )
        _write(self.repo, "README.md",
               "# Title\n\nOriginal line.\n\n"
               f"See `{_FIXTURE_LEGACY_FILENAME}`, and also this unrelated {TERM} usage.\n")
        _commit(self.repo, "legacy filename plus a stray extra occurrence")

        res = _run_guard(self.repo, allowlist=fixture_allowlist)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)

    def test_stray_occurrence_alongside_vendor_literal_still_fails(self):
        """Same span-precision requirement for the vendor_literals carve-out:
        an allowed vendor-literal citation does NOT amnesty a separate,
        unexplained mention on the same line."""
        fixture_allowlist = _write_fixture_allowlist(
            Path(self._tmp.name), vendor_literals=[_FIXTURE_VENDOR_LITERAL]
        )
        _write(self.repo, "README.md",
               "# Title\n\nOriginal line.\n\n"
               f"Upstream ships {_FIXTURE_VENDOR_LITERAL}, and separately this unrelated {TERM} usage.\n")
        _commit(self.repo, "vendor literal plus a stray extra occurrence")

        res = _run_guard(self.repo, allowlist=fixture_allowlist)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)

    def test_qc_reported_bypass_phrase_no_longer_silently_passes(self):
        """Regression for the QC finding: the real allowlist previously
        shipped 'canary channel release' as a vendor_literals entry — a
        natural-English phrase broad enough that ordinary new operator
        doctrine prose could organically contain it, silently amnestying a
        genuinely new occurrence (reproduced: this exact sentence used to
        exit 0). Runs against the REAL (default) allowlist, not a fixture,
        to pin that the shipped file no longer carries this or any other
        bypass phrase."""
        _write(self.repo, "README.md",
               "# Title\n\nOriginal line.\n\n"
               f"Our fleet does a {TERM} channel release to the operator box before clients.\n")
        _commit(self.repo, "reproduce the QC-reported bypass sentence")

        res = _run_guard(self.repo)  # default (real, shipped) allowlist
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)


class TestHistoryCarveout(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _init_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_passes_when_line_resurfaces_verbatim_from_history(self):
        historical_line = f"the historical CHANGELOG note about the old {TERM} probe"
        _write(self.repo, "CHANGELOG.md", f"# Changelog\n\n{historical_line}\n")
        _commit(self.repo, "base carries the historical line")

        # Simulate a file move/reflow: the exact same line resurfaces as an
        # "added" line in a different doc file.
        _write(self.repo, "docs/ARCHIVE.md", f"Moved note:\n\n{historical_line}\n")
        _commit(self.repo, "move the historical line into a new file")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_a_similar_but_non_identical_new_line_still_fails(self):
        historical_line = f"the historical CHANGELOG note about the old {TERM} probe"
        _write(self.repo, "CHANGELOG.md", f"# Changelog\n\n{historical_line}\n")
        _commit(self.repo, "base carries the historical line")

        _write(self.repo, "docs/ARCHIVE.md",
               f"A materially different new sentence that also names the {TERM} word.\n")
        _commit(self.repo, "add a non-identical new line")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)

    def test_version_marker_only_roll_of_historical_term_line_passes(self):
        """U92 producer-fix regression: a pre-existing term-bearing doc line
        whose ONLY change vs history is an inline version marker being rolled
        (exactly what scripts/bump-version.sh does to a historical
        '**NOTE (vX.Y.Z)**' README release line during the version-bump ripple)
        is NOT new writing — carve-out (a) masks dotted version tokens on both
        sides before comparing, so it PASSES. Without the mask this line is
        byte-different from history and was flagged (the bug this unit fixed:
        its own guard went RED on README.md:20/README.md:22 under the bump)."""
        historical = (
            f"> **NOTE (v20.0.39) - chore(release): the old {TERM} probe "
            f"shipped in the v17.0.26 train, tag pushed before the PR.**"
        )
        _write(self.repo, "README.md", f"# Title\n\n{historical}\n")
        _commit(self.repo, "base carries the term-bearing NOTE line at v20.0.39")

        # A version bump rolls BOTH the (v20.0.39) marker and the inline v17.0.26
        # citation; nothing else on the line changes.
        rolled = (
            f"> **NOTE (v20.0.40) - chore(release): the old {TERM} probe "
            f"shipped in the v17.0.26 train, tag pushed before the PR.**"
        )
        _write(self.repo, "README.md", f"# Title\n\n{rolled}\n")
        _commit(self.repo, "version bump rolls the inline markers on the historical line")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


class TestCLIWiring(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _init_repo(Path(self._tmp.name))
        _write(self.repo, "README.md", "# Title\n")
        _commit(self.repo, "base")

    def tearDown(self):
        self._tmp.cleanup()

    def test_unresolvable_base_ref_errors_cleanly(self):
        res = _run_guard(self.repo, base_ref="not-a-real-ref-xyz")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("ERROR", res.stderr)

    def test_allowlist_file_itself_is_valid_json_with_required_keys(self):
        self.assertIn("term", _ALLOWLIST_DATA)
        self.assertIn("legacy_filenames", _ALLOWLIST_DATA)
        self.assertIn("vendor_literals", _ALLOWLIST_DATA)
        # This list only ever SHRINKS as each owning unit lands its rename,
        # and never grows (see the $comment doctrine above). It shipped at 6
        # (4 U30-owned + 2 U93-owned). U30/B-U16 removed its 4 and U93/X-U-X3
        # removed its 2, both on 2026-07-16 -- so the carve-out is now spent
        # and the list is EMPTY. Pinned as an exact 0 rather than a >=0 floor,
        # which would assert nothing at all: with every owning unit landed,
        # the live invariant worth guarding is that no entry ever comes BACK
        # (a re-added legacy filename would silently re-amnesty the retired
        # term in new doc prose).
        self.assertEqual(len(_ALLOWLIST_DATA["legacy_filenames"]["entries"]), 0)

    def test_vendor_literals_empty_by_default(self):
        """Pins the allowlist's own stated default (its $comment: 'Empty by
        default in this repo ... U91's scrub found zero surviving
        vendor-literal citations'). A previous version of this file shipped
        three pre-populated entries — including the natural-English phrase
        'canary channel release', broad enough to silently amnesty genuinely
        new prose (see TestAllowlistCarveouts.
        test_qc_reported_bypass_phrase_no_longer_silently_passes) — directly
        contradicting that stated default. This assertion fails loudly the
        next time someone reintroduces a pre-populated entry without also
        updating the $comment and reasoning through whether it is a narrow,
        genuinely-cited literal rather than a broad phrase."""
        self.assertEqual(_ALLOWLIST_DATA["vendor_literals"]["entries"], [])


class TestHunkBodyNeverReparsedAsHeader(unittest.TestCase):
    """Regression for the QC finding: iter_added_lines() must bound
    hunk-body consumption to the header/body split established by the
    '@@ -a,b +c,d @@' line, never re-pattern-match '+++ '/'--- '/'@@'
    against hunk-BODY content. Without that split, a new doc line whose
    content begins with '++ ' is rendered by git as '+++ <content>' inside
    the hunk body (indistinguishable, by prefix alone, from a genuine
    '+++ b/<path>' new-file header) and was being silently skipped instead
    of scanned."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _init_repo(Path(self._tmp.name))
        _write(self.repo, "README.md", "# Title\n\nOriginal line.\n")
        _commit(self.repo, "base")

    def tearDown(self):
        self._tmp.cleanup()

    def test_added_line_starting_with_double_plus_is_not_swallowed_as_a_header(self):
        _write(self.repo, "README.md",
               f"# Title\n\nOriginal line.\n\n++ {TERM} team ships this weekend\n")
        _commit(self.repo, "inject a line that begins with '++ '")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("README.md", res.stdout)
        self.assertIn("NEW unexplained occurrence", res.stdout)

    def test_added_line_starting_with_triple_plus_is_not_swallowed_as_a_header(self):
        """One more '+' of diff-marker ambiguity than the minimal repro,
        proving the fix isn't a special case pinned to exactly two."""
        _write(self.repo, "README.md",
               f"# Title\n\nOriginal line.\n\n+++ {TERM} again, three pluses this time\n")
        _commit(self.repo, "inject a line that begins with '+++ '")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("README.md", res.stdout)

    def test_second_hunk_in_same_file_still_correctly_scanned(self):
        """A '++'-prefixed added line sits in the file's FIRST hunk; a
        genuinely new line sits in a SECOND, separate hunk far below. Proves
        the header/body state resets correctly at each new '@@' without
        losing track of `current_file`."""
        base_lines = ["line %d" % i for i in range(1, 21)]
        _write(self.repo, "README.md", "\n".join(base_lines) + "\n")
        _commit(self.repo, "20-line base")

        edited = list(base_lines)
        edited[0] = f"++ {TERM} injected near the top"
        edited[19] = f"a second, separate {TERM} occurrence near the bottom"
        _write(self.repo, "README.md", "\n".join(edited) + "\n")
        _commit(self.repo, "edit two far-apart lines, two separate hunks")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        # Both occurrences must be reported — not just the one that happens
        # to follow a clean header parse.
        self.assertEqual(res.stdout.count(f"README.md:"), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

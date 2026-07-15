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
LEGACY_FILENAME = _ALLOWLIST_DATA["legacy_filenames"]["entries"][0]["path"]
VENDOR_LITERAL = _ALLOWLIST_DATA["vendor_literals"]["entries"][0]


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


def _run_guard(repo: Path, base_ref: str | None = None) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable, str(_SCRIPT),
        "--repo-root", str(repo),
        "--allowlist", str(_ALLOWLIST),
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
        _write(self.repo, "README.md",
               "# Title\n\nOriginal line.\n\n"
               f"See `{LEGACY_FILENAME}` for the scheduled drift check (rename pending).\n")
        _commit(self.repo, "cite a legacy filename")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_passes_when_only_vendor_literal_cited(self):
        _write(self.repo, "README.md",
               "# Title\n\nOriginal line.\n\n"
               f"Upstream publishes a pre-release under {VENDOR_LITERAL}, a name we do not own.\n")
        _commit(self.repo, "cite a vendor literal")

        res = _run_guard(self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_stray_occurrence_alongside_allowed_filename_still_fails(self):
        """The subtraction must be span-precise: an allowed filename citation on
        a line does NOT amnesty an extra, separate, unexplained mention on that
        same line."""
        _write(self.repo, "README.md",
               "# Title\n\nOriginal line.\n\n"
               f"See `{LEGACY_FILENAME}`, and also this unrelated {TERM} usage.\n")
        _commit(self.repo, "legacy filename plus a stray extra occurrence")

        res = _run_guard(self.repo)
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
        self.assertGreaterEqual(len(_ALLOWLIST_DATA["legacy_filenames"]["entries"]), 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)

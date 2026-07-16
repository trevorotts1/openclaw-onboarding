#!/usr/bin/env python3
"""Unit tests for scripts/verify-master-spec-scrub.py — the U91 (X/U-X1)
whole-document verification run that confirms MASTER SPEC v2 X.1.2's binary
scrub target: a case-insensitive search of the fully assembled spec finds the
retired term only in the LANGUAGE CONFORMANCE header's defining sentence plus
annotated legacy-filename/vendor-literal citations.

Every fixture spec file here is a disposable temp file under tmp_path/a
unittest TemporaryDirectory — never the real, 552KB local master spec (never
committed to this repo; U91's script takes its path as a CLI argument for
exactly this reason). Proves the behaviors the unit's own acceptance bar
names:
  1. PASSES a clean document: term appears once in the LANGUAGE CONFORMANCE
     header window (the defining sentence) and once inside an allowlisted
     legacy-filename citation, nowhere else.
  2. FAILS on a genuinely new, unexplained stray occurrence elsewhere in the
     document.
  3. FAILS when the term is spelled out a SECOND time near/after the header
     marker — "defined once" is enforced, not just "defined at least once".
  4. FAILS (by default) when no defining-sentence occurrence exists at all;
     PASSES that same input with --no-require-defining-sentence.
  5. The legacy-filename/vendor-literal carve-outs never amnesty a genuinely
     new stray occurrence riding on the same line as an allowed citation.
  6. CLI-level exit codes (0 / 1 / 2) match the documented contract, incl.
     the missing-file and bad-allowlist error paths.

Run:
    python3 scripts/tests/test_verify_master_spec_scrub.py
    or: pytest scripts/tests/test_verify_master_spec_scrub.py
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
_SCRIPT = _REPO_ROOT / "scripts" / "verify-master-spec-scrub.py"
_ALLOWLIST = _REPO_ROOT / "scripts" / "docs-language-allowlist.json"

_ALLOWLIST_DATA = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))
TERM = _ALLOWLIST_DATA["term"]
LEGACY_FILENAME = _ALLOWLIST_DATA["legacy_filenames"]["entries"][0]["path"]

# vendor_literals is empty by default in the real allowlist (same reason
# noted in the U92 test suite) — tests that need a populated entry build a
# disposable fixture allowlist instead of depending on real repo content.
_FIXTURE_VENDOR_LITERAL = f"acme-widgets@{TERM}"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def _write_spec(tmp_dir: Path, name: str, content: str) -> Path:
    p = tmp_dir / name
    p.write_text(content, encoding="utf-8")
    return p


def _write_fixture_allowlist(tmp_dir: Path, vendor_literals: list[str]) -> Path:
    data = {
        "term": TERM,
        "legacy_filenames": {"entries": [{"path": LEGACY_FILENAME, "owner": "TEST"}]},
        "vendor_literals": {"entries": vendor_literals},
    }
    p = tmp_dir / "fixture-allowlist.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class VerifyMasterSpecScrubTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- 1. clean document: defining sentence + legacy citation, PASS -------

    def test_clean_document_passes(self):
        spec = _write_spec(
            self.tmp_dir,
            "clean.md",
            "\n".join(
                [
                    "# Some Spec",
                    "",
                    "## LANGUAGE CONFORMANCE",
                    "",
                    f'The term "{TERM}" is retired operator-banned coded language.',
                    "",
                    "## Elsewhere",
                    "",
                    f"See `{LEGACY_FILENAME}` (legacy filename; rename tracked).",
                    "Plain prose with no banned words at all.",
                ]
            ),
        )
        res = _run("--spec-path", str(spec))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("PASS", res.stdout)
        self.assertIn("defining sentence: 1 line", res.stdout)
        self.assertIn("legacy filename / vendor literal citations: 1 line", res.stdout)
        self.assertIn("UNEXPLAINED (violations): 0 line", res.stdout)

    # -- 2. a genuinely new stray occurrence elsewhere, FAIL -----------------

    def test_stray_occurrence_fails(self):
        spec = _write_spec(
            self.tmp_dir,
            "violation.md",
            "\n".join(
                [
                    "## LANGUAGE CONFORMANCE",
                    "",
                    f'The term "{TERM}" is retired operator-banned coded language.',
                    "",
                    "## Much later, unrelated section",
                    "",
                    f"We should run a quick {TERM} check before shipping.",
                ]
            ),
        )
        res = _run("--spec-path", str(spec))
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("FAIL", res.stdout)
        self.assertIn("UNEXPLAINED (violations): 1 line", res.stdout)
        self.assertIn("quick", res.stdout)  # the stray line itself is echoed

    # -- 3. "defined once" is enforced, a second raw spell-out FAILS ---------

    def test_second_defining_style_occurrence_fails(self):
        spec = _write_spec(
            self.tmp_dir,
            "double-defining.md",
            "\n".join(
                [
                    "## LANGUAGE CONFORMANCE",
                    "",
                    f'The term "{TERM}" is retired operator-banned coded language.',
                    f'To be clear, "{TERM}" must never be used again.',
                ]
            ),
        )
        res = _run("--spec-path", str(spec))
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("defining sentence: 1 line", res.stdout)
        self.assertIn("UNEXPLAINED (violations): 1 line", res.stdout)

    # -- 4. require/skip the defining-sentence requirement -------------------

    def test_missing_defining_sentence_fails_by_default(self):
        spec = _write_spec(
            self.tmp_dir,
            "no-header.md",
            f"See `{LEGACY_FILENAME}` (legacy filename; rename tracked).\n",
        )
        res = _run("--spec-path", str(spec))
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("WARNING: no defining-sentence occurrence found", res.stdout)

    def test_missing_defining_sentence_passes_when_not_required(self):
        spec = _write_spec(
            self.tmp_dir,
            "no-header.md",
            f"See `{LEGACY_FILENAME}` (legacy filename; rename tracked).\n",
        )
        res = _run("--spec-path", str(spec), "--no-require-defining-sentence")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("PASS", res.stdout)

    # -- 5. carve-outs never amnesty a stray occurrence on the same line -----

    def test_legacy_citation_does_not_amnesty_stray_on_same_line(self):
        spec = _write_spec(
            self.tmp_dir,
            "same-line.md",
            "\n".join(
                [
                    "## LANGUAGE CONFORMANCE",
                    "",
                    f'The term "{TERM}" is retired operator-banned coded language.',
                    "",
                    f"See `{LEGACY_FILENAME}` and also run a {TERM} manually — both on one line.",
                ]
            ),
        )
        res = _run("--spec-path", str(spec))
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("UNEXPLAINED (violations): 1 line", res.stdout)
        self.assertIn("both on one line", res.stdout)

    def test_vendor_literal_carve_out_and_no_over_amnesty(self):
        allowlist = _write_fixture_allowlist(
            self.tmp_dir, vendor_literals=[_FIXTURE_VENDOR_LITERAL]
        )
        spec = _write_spec(
            self.tmp_dir,
            "vendor.md",
            "\n".join(
                [
                    "## LANGUAGE CONFORMANCE",
                    "",
                    f'The term "{TERM}" is retired operator-banned coded language.',
                    "",
                    f"The npm dist-tag `{_FIXTURE_VENDOR_LITERAL}` is a vendor literal, quoted as-is.",
                    f"But this separate {TERM} mention is genuinely new prose.",
                ]
            ),
        )
        res = _run("--spec-path", str(spec), "--allowlist", str(allowlist))
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("legacy filename / vendor literal citations: 1 line", res.stdout)
        self.assertIn("UNEXPLAINED (violations): 1 line", res.stdout)
        self.assertIn("genuinely new prose", res.stdout)

    # -- 6. CLI-level error paths ---------------------------------------------

    def test_missing_spec_file_exits_2(self):
        res = _run("--spec-path", str(self.tmp_dir / "does-not-exist.md"))
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("spec file not found", res.stderr)

    def test_bad_allowlist_exits_2(self):
        spec = _write_spec(self.tmp_dir, "irrelevant.md", "no banned words here\n")
        bad_allowlist = self.tmp_dir / "bad.json"
        bad_allowlist.write_text("{not valid json", encoding="utf-8")
        res = _run("--spec-path", str(spec), "--allowlist", str(bad_allowlist))
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("could not load allowlist", res.stderr)

    def test_no_occurrences_at_all_fails_default_requires_defining_sentence(self):
        spec = _write_spec(self.tmp_dir, "clean-empty.md", "Nothing to see here.\n")
        res = _run("--spec-path", str(spec))
        # zero occurrences of the term anywhere, incl. no defining sentence,
        # still fails the default "must define it once" requirement.
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        res2 = _run("--spec-path", str(spec), "--no-require-defining-sentence")
        self.assertEqual(res2.returncode, 0, res2.stdout + res2.stderr)

    # -- 7. basename-only citations of a tracked legacy filename -------------

    def test_legacy_filename_basename_alone_is_recognized(self):
        basename = Path(LEGACY_FILENAME).name
        self.assertNotEqual(basename, LEGACY_FILENAME, "fixture needs a nested legacy path")
        spec = _write_spec(
            self.tmp_dir,
            "basename.md",
            "\n".join(
                [
                    "## LANGUAGE CONFORMANCE",
                    "",
                    f'The term "{TERM}" is retired operator-banned coded language.',
                    "",
                    f"Elsewhere, cited by basename alone: `{basename}` (rename tracked).",
                ]
            ),
        )
        res = _run("--spec-path", str(spec))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("legacy filename / vendor literal citations: 1 line", res.stdout)

    def test_basename_match_does_not_amnesty_a_genuinely_different_stray(self):
        basename = Path(LEGACY_FILENAME).name
        spec = _write_spec(
            self.tmp_dir,
            "basename-plus-stray.md",
            "\n".join(
                [
                    "## LANGUAGE CONFORMANCE",
                    "",
                    f'The term "{TERM}" is retired operator-banned coded language.',
                    "",
                    f"Cited: `{basename}` (fine), but this later, unrelated "
                    f"paragraph also runs a {TERM} for no annotated reason.",
                ]
            ),
        )
        res = _run("--spec-path", str(spec))
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("UNEXPLAINED (violations): 1 line", res.stdout)

    # -- 8. the U91-owned extra-citations supplement --------------------------

    def test_extra_citations_file_recognizes_cross_repo_legacy_filename(self):
        cross_repo_filename = f"scripts/reset-{TERM}.sh"
        extra = self.tmp_dir / "extra-citations.json"
        extra.write_text(
            json.dumps(
                {
                    "legacy_filenames": {
                        "entries": [
                            {
                                "path": cross_repo_filename,
                                "repo": "some-other-repo",
                                "owner": "TEST",
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        spec = _write_spec(
            self.tmp_dir,
            "cross-repo.md",
            "\n".join(
                [
                    "## LANGUAGE CONFORMANCE",
                    "",
                    f'The term "{TERM}" is retired operator-banned coded language.',
                    "",
                    f"The other repo still ships `{cross_repo_filename}` "
                    "(legacy filename, rename tracked separately).",
                ]
            ),
        )
        # Without the extra-citations file: FAILS (not in the ONB allowlist).
        res_without = _run(
            "--spec-path", str(spec), "--extra-citations", str(self.tmp_dir / "nonexistent.json")
        )
        self.assertEqual(res_without.returncode, 1, res_without.stdout + res_without.stderr)

        # With it: PASSES.
        res_with = _run("--spec-path", str(spec), "--extra-citations", str(extra))
        self.assertEqual(res_with.returncode, 0, res_with.stdout + res_with.stderr)

    def test_missing_extra_citations_file_is_not_an_error(self):
        spec = _write_spec(
            self.tmp_dir,
            "no-extra.md",
            f'## LANGUAGE CONFORMANCE\n\nThe term "{TERM}" is retired operator-banned '
            "coded language.\n",
        )
        res = _run(
            "--spec-path", str(spec),
            "--extra-citations", str(self.tmp_dir / "does-not-exist.json"),
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_malformed_extra_citations_file_exits_2(self):
        spec = _write_spec(self.tmp_dir, "irrelevant2.md", "no banned words here\n")
        bad_extra = self.tmp_dir / "bad-extra.json"
        bad_extra.write_text("{not valid json", encoding="utf-8")
        res = _run("--spec-path", str(spec), "--extra-citations", str(bad_extra))
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("could not load extra-citations", res.stderr)


if __name__ == "__main__":
    unittest.main()

"""Pins for the sub-clauses of the SOP read receipt and interface-pin code that a clause-by-clause
mutation sweep (issue 35, 22) showed no other test reached.

Each test names the clause it holds. Every one runs the same with SKILL83_SESSION unset or set,
because each sets or clears the variable itself. Stdlib only: python3 -m unittest.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher_core import cli, dependencies  # noqa: E402
from test_sop_dependency_receipt import _DROP, _fixture, _receipt  # noqa: E402

ENV = dependencies.SOP_SESSION_ENV


def _verdict(**over):
    with tempfile.TemporaryDirectory() as tmp:
        sop, skill, entry = _fixture(Path(tmp))
        _receipt(skill, hashlib.sha256(sop.read_bytes()).hexdigest(), **over)
        with mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill):
            return dependencies._present(entry, Path(tmp))


class SessionComparisonTests(unittest.TestCase):
    def test_the_assembling_session_variable_is_named_skill83_session(self):
        self.assertEqual(ENV, "SKILL83_SESSION")
        with mock.patch.dict(os.environ, {"SKILL83_SESSION": "reader-1"}):
            self.assertIn("assembling session", _verdict()["evidence"])

    def test_the_comparison_trims_the_variable_and_the_reader_and_is_exact_in_case(self):
        with mock.patch.dict(os.environ, {ENV: "  reader-1  "}):
            self.assertIn("assembling session", _verdict()["evidence"])
        with mock.patch.dict(os.environ, {ENV: "reader-1"}):
            self.assertIn("assembling session", _verdict(reader_session="  reader-1 ")["evidence"])
        with mock.patch.dict(os.environ, {ENV: "READER-1"}):
            self.assertEqual(_verdict()["status"], "present")  # session ids are exact strings
        with mock.patch.dict(os.environ, {ENV: "reader-1"}):
            self.assertEqual(_verdict(reader_session="READER-1")["status"], "present")

    def test_a_section_count_must_be_an_integer_not_an_equal_float(self):
        for odd in (1.0, "1", [1], None):
            self.assertEqual(_verdict(sections=odd)["status"], "missing", odd)

    def test_a_read_date_may_carry_a_time_of_day(self):
        stamp = datetime.date.today().isoformat() + "T08:30:00+00:00"
        self.assertEqual(_verdict(read_at=stamp)["status"], "present")

    def test_a_refusal_tells_the_reader_the_command_that_regenerates_the_receipt(self):
        why = _verdict(read_in_full=False)["evidence"]
        self.assertIn("cli sop-ack sop-test --session <id> --sections <n>", why)
        self.assertIn("does not prove reading: read_in_full is not true", why)


def _done(returncode=0, stdout=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


class LastCommitDateTests(unittest.TestCase):
    def _date(self, *runs):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(dependencies.subprocess, "run", side_effect=list(runs)):
            return dependencies._last_commit_date(Path(tmp) / "a.md")

    GOOD_LOG = _done(0, "2026-11-01T12:00:00+00:00\n")

    def test_git_history_is_used_only_when_git_says_the_clone_is_complete(self):
        self.assertEqual(self._date(_done(0, "false\n"), self.GOOD_LOG), datetime.date(2026, 11, 1))
        self.assertIsNone(self._date(_done(0, "true\n"), self.GOOD_LOG))
        self.assertIsNone(self._date(_done(1, "false\n"), self.GOOD_LOG))
        self.assertIsNone(self._date(_done(0, "maybe\n"), self.GOOD_LOG))
        self.assertIsNone(self._date(_done(0, ""), self.GOOD_LOG))

    def test_a_failed_or_empty_log_gives_no_date(self):
        self.assertIsNone(self._date(_done(0, "false\n"), _done(1, "2026-11-01T12:00:00+00:00\n")))
        self.assertIsNone(self._date(_done(0, "false\n"), _done(0, "")))
        self.assertIsNone(self._date(_done(0, "false\n"), _done(0, "not a date at all\n")))

    def test_no_git_or_a_hung_git_gives_no_date(self):
        self.assertIsNone(self._date(OSError("no git")))
        self.assertIsNone(self._date(_done(0, "false\n"), subprocess.TimeoutExpired("git", 30)))

    def test_the_date_is_the_files_own_committer_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "a.md").write_text("# a\n", encoding="utf-8")
            (folder / "b.md").write_text("# b\n", encoding="utf-8")

            def git(day, author_day, *argv):
                env = {**os.environ, "GIT_COMMITTER_DATE": f"{day}T12:00:00+00:00",
                       "GIT_AUTHOR_DATE": f"{author_day}T12:00:00+00:00"}
                subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *argv],
                               cwd=folder, env=env, check=True, capture_output=True)
            git("2026-10-01", "2026-09-01", "init", "-q")
            git("2026-10-01", "2026-09-01", "add", "a.md")
            git("2026-10-01", "2026-09-01", "commit", "-q", "-m", "a")
            git("2026-10-20", "2026-10-20", "add", "b.md")
            git("2026-10-20", "2026-10-20", "commit", "-q", "-m", "b")
            self.assertEqual(dependencies._last_commit_date(folder / "a.md"), datetime.date(2026, 10, 1))
            self.assertEqual(dependencies._last_commit_date(folder / "b.md"), datetime.date(2026, 10, 20))
            (folder / "c.md").write_text("# c\n", encoding="utf-8")  # untracked
            self.assertIsNone(dependencies._last_commit_date(folder / "c.md"))


class HeadingCountTests(unittest.TestCase):
    def _count(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.md"
            path.write_text(text, encoding="utf-8")
            return dependencies.sop_heading_count(path)

    def test_what_is_and_is_not_a_heading(self):
        cases = [("#nospace\n", 0), ("####### seven\n", 0), ("###### six\n", 1), ("##### five\n", 1),
                 ("   # three spaces\n", 1), ("    # four spaces\n", 0), ("### a\n# b\n", 2), ("# a\n\n## b\n", 2)]
        for text, want in cases:
            self.assertEqual(self._count(text), want, text)

    def test_what_is_and_is_not_a_code_fence(self):
        cases = [("~~~\n# hidden\n~~~\n# shown\n", 1), ("   ```\n# hidden\n   ```\n# shown\n", 1),
                 ("    ```\n# real\n", 1), ("```\n# hidden\n```\n# shown\n", 1), ("```\n# never closed\n", 0)]
        for text, want in cases:
            self.assertEqual(self._count(text), want, text)

    def test_an_unreadable_file_has_no_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(dependencies.sop_heading_count(Path(tmp) / "absent.md"))


class AckSelectionTests(unittest.TestCase):
    def _ack(self, tmp, entries=None, which="sop-test", session="reader-2", sections=1, **kw):
        sop, skill, entry = _fixture(Path(tmp))
        entry.update(kw.pop("entry_over", {}))
        with mock.patch.dict(os.environ, {ENV: kw.pop("env", "")}), \
                mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill), \
                mock.patch.object(dependencies, "load_manifest", return_value={"entries": entries or [entry]}):
            return skill, sop, dependencies.ack_sop(which, session, sections, Path(tmp), **kw)

    def test_a_sop_is_named_by_id_path_or_stem_with_spaces_ignored(self):
        for which in ("sop-test", "sops/SOP-TEST.md", "SOP-TEST", "  sop-test  "):
            with tempfile.TemporaryDirectory() as tmp:
                _skill, _sop, done = self._ack(tmp, which=which)
                self.assertEqual(done["sop"], "sops/SOP-TEST.md", which)

    def test_two_matching_sops_are_refused_and_a_non_sop_row_with_the_name_is_ignored(self):
        row = {"id": "sop-test", "kind": "sop", "ref": "sops/SOP-TEST.md", "required": False}
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(dependencies.DependencyError) as caught:
            self._ack(tmp, entries=[row, dict(row)])
        self.assertIn("matches 2 declared SOPs", str(caught.exception))
        with tempfile.TemporaryDirectory() as tmp:
            other = {"id": "sop-test", "kind": "shared_utils", "ref": "sops/SOP-TEST.md", "required": False}
            self._ack(tmp, entries=[other, row])

    def test_the_assembling_session_is_matched_after_trimming(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(dependencies.DependencyError) as caught:
            self._ack(tmp, env="  reader-2 ")
        self.assertIn("assembling session", str(caught.exception))

    def test_a_missing_sop_file_is_refused_as_absent_not_as_a_count_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            sop.unlink()
            with mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill), \
                    mock.patch.object(dependencies, "load_manifest", return_value={"entries": [entry]}), \
                    self.assertRaises(dependencies.DependencyError) as caught:
                dependencies.ack_sop("sop-test", "reader-2", 1, Path(tmp))
            self.assertIn("is absent", str(caught.exception))

    def test_a_sop_path_that_does_not_resolve_is_refused_as_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            with mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill), \
                    mock.patch.object(dependencies, "load_manifest", return_value={"entries": [entry]}), \
                    mock.patch.object(dependencies, "_resolve", return_value=(None, "no such ref")), \
                    self.assertRaises(dependencies.DependencyError) as caught:
                dependencies.ack_sop("sop-test", "reader-2", 1, Path(tmp))
            self.assertIn("is absent (no such ref)", str(caught.exception))

    def test_a_file_whose_headings_cannot_be_counted_is_never_acknowledged_with_no_count(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(dependencies, "sop_heading_count", return_value=None), \
                self.assertRaises(dependencies.DependencyError) as caught:
            self._ack(tmp, sections=None)
        self.assertIn("does not match the heading count", str(caught.exception))

    def test_the_read_date_is_the_one_given_else_today_and_the_receipt_path_is_the_declared_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill, _sop, done = self._ack(tmp, today=datetime.date(2026, 1, 2),
                                          entry_over={"receipt": "receipts/custom/own.json"})
            self.assertEqual(done["record"]["read_at"], "2026-01-02")
            self.assertTrue((skill / "receipts" / "custom" / "own.json").is_file())
            self.assertFalse((skill / dependencies.SOP_RECEIPT_DIR / "SOP-TEST.json").exists())
        with tempfile.TemporaryDirectory() as tmp:
            _skill, _sop, done = self._ack(tmp)
            self.assertEqual(done["record"]["read_at"], datetime.date.today().isoformat())


class InterfacePinTests(unittest.TestCase):
    def _tree(self, tmp, names=("scripts/b.py", "scripts/c.py", "scripts/a.py"), version="1.0.0"):
        tree = Path(tmp) / "tree"
        for i, rel in enumerate(names):
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
        (tree / "skill-version.txt").write_text(version + "\n", encoding="utf-8")
        entry = {"id": "tree-fixture", "kind": "skill_tree", "ref": "99-fixture", "min_version": "1.0.0",
                 "required": True,
                 "interface_sha256": {rel: dependencies._sha256_file(tree / rel) for rel in names}}  # not in sorted order
        return tree, entry

    def _present(self, tree, entry):
        with mock.patch.object(dependencies, "_resolve", return_value=(tree, None)):
            return dependencies._present(entry, tree.parent)

    def test_a_version_below_the_floor_is_refused_even_when_every_pinned_file_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, entry = self._tree(tmp, version="0.9.0")
            self.assertEqual(self._present(tree, entry)["status"], "missing")

    def test_a_drift_refusal_still_reports_each_pinned_file_in_sorted_order_with_both_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, entry = self._tree(tmp)
            (tree / "scripts" / "b.py").write_text("changed\n", encoding="utf-8")
            result = self._present(tree, entry)
            self.assertEqual(result["status"], "missing")
            shown = result["interfaces"]
            self.assertEqual([h["file"] for h in shown], ["scripts/a.py", "scripts/b.py", "scripts/c.py"])
            self.assertEqual(shown[0]["expected"], shown[0]["observed"])
            self.assertNotEqual(shown[1]["expected"], shown[1]["observed"])
            self.assertEqual(shown[1]["observed"], dependencies._sha256_file(tree / "scripts" / "b.py"))
            self.assertIn("interface drift in scripts/b.py (changed)", result["evidence"])
            self.assertNotIn("scripts/a.py", result["evidence"])

    def test_the_tree_is_resolved_as_a_skill_tree_when_re_stamping(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, entry = self._tree(tmp)
            manifest = Path(tmp) / "dependencies.json"
            manifest.write_text(json.dumps({"entries": [entry]}, indent=2), encoding="utf-8")
            seen = []

            def resolve(ref, root, kind=""):
                seen.append(kind)
                return tree, None
            with mock.patch.object(dependencies, "MANIFEST", manifest), mock.patch.object(dependencies, "_resolve", resolve):
                dependencies.stamp_interfaces(Path(tmp))
            self.assertEqual(seen, ["skill_tree"])

    def test_re_stamping_refuses_an_unresolvable_tree_and_a_missing_pinned_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, entry = self._tree(tmp)
            manifest = Path(tmp) / "dependencies.json"
            manifest.write_text(json.dumps({"entries": [entry]}, indent=2), encoding="utf-8")
            with mock.patch.object(dependencies, "MANIFEST", manifest):
                with mock.patch.object(dependencies, "_resolve", return_value=(None, "no such tree")), \
                        self.assertRaises(dependencies.DependencyError) as caught:
                    dependencies.stamp_interfaces(Path(tmp))
                self.assertIn("cannot re-stamp tree-fixture: no such tree", str(caught.exception))
                (tree / "scripts" / "a.py").unlink()
                with mock.patch.object(dependencies, "_resolve", return_value=(tree, None)), \
                        self.assertRaises(dependencies.DependencyError) as caught:
                    dependencies.stamp_interfaces(Path(tmp))
                self.assertIn("scripts/a.py is absent", str(caught.exception))
            self.assertEqual(manifest.read_text(encoding="utf-8"), json.dumps({"entries": [entry]}, indent=2))

    def test_re_stamping_one_moved_file_leaves_another_file_with_the_same_hash_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp) / "tree"
            (tree / "scripts").mkdir(parents=True)
            for name in ("a.py", "b.py"):
                (tree / "scripts" / name).write_text("same\n", encoding="utf-8")
            same = dependencies._sha256_file(tree / "scripts" / "a.py")
            entry = {"id": "t", "kind": "skill_tree", "ref": "99-fixture", "min_version": "1.0.0", "required": True,
                     "interface_sha256": {"scripts/a.py": same, "scripts/b.py": same}}
            manifest = Path(tmp) / "dependencies.json"
            manifest.write_text(json.dumps({"entries": [entry]}, indent=2), encoding="utf-8")
            (tree / "scripts" / "b.py").write_text("moved\n", encoding="utf-8")
            with mock.patch.object(dependencies, "MANIFEST", manifest), \
                    mock.patch.object(dependencies, "_resolve", return_value=(tree, None)):
                self.assertEqual(dependencies.stamp_interfaces(Path(tmp)), ["99-fixture/scripts/b.py"])
            pins = json.loads(manifest.read_text(encoding="utf-8"))["entries"][0]["interface_sha256"]
            self.assertEqual(pins["scripts/a.py"], same)
            self.assertEqual(pins["scripts/b.py"], dependencies._sha256_file(tree / "scripts" / "b.py"))


class CliStampAndAckTests(unittest.TestCase):
    def _main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_dependencies_stamp_interfaces_re_stamps_a_copy_and_reports_each_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "dependencies.json"
            real = json.loads(dependencies.MANIFEST.read_text(encoding="utf-8"))
            tree_entry = next(e for e in real["entries"] if e.get("interface_sha256"))
            rel, good = next(iter(tree_entry["interface_sha256"].items()))
            text = dependencies.MANIFEST.read_text(encoding="utf-8")
            copy.write_text(text, encoding="utf-8")
            with mock.patch.object(dependencies, "MANIFEST", copy):
                code, out, _err = self._main(["dependencies", "--stamp-interfaces"])
                self.assertEqual((code, out.splitlines()[0]), (0, "0 interface hash(es) re-stamped"))
                self.assertEqual(copy.read_text(encoding="utf-8"), text)
                copy.write_text(text.replace(good, "f" * 64), encoding="utf-8")
                code, out, _err = self._main(["dependencies", "--stamp-interfaces"])
                self.assertEqual(code, 0)
                self.assertEqual(out.splitlines()[0], "1 interface hash(es) re-stamped")
                self.assertIn(f"  {tree_entry['ref']}/{rel}", out.splitlines())
                self.assertEqual(copy.read_text(encoding="utf-8"), text)
            self.assertIn(good, dependencies.MANIFEST.read_text(encoding="utf-8"))  # the real manifest was never written

    def test_dependencies_stamp_interfaces_exits_2_with_the_reason_when_it_cannot(self):
        err = dependencies.DependencyError("cannot re-stamp tree-x: gone")
        with mock.patch.object(dependencies, "stamp_interfaces", side_effect=err):
            code, out, errors = self._main(["dependencies", "--stamp-interfaces"])
        self.assertEqual(code, 2)
        self.assertIn("FAIL cannot re-stamp tree-x: gone", errors)
        self.assertEqual(out, "")

    def test_dependencies_prints_the_expected_hash_before_the_observed_one_when_a_pin_drifted(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "dependencies.json"
            text = dependencies.MANIFEST.read_text(encoding="utf-8")
            entry = next(e for e in json.loads(text)["entries"] if e.get("interface_sha256"))
            rel, good = next(iter(entry["interface_sha256"].items()))
            copy.write_text(text.replace(good, "e" * 64), encoding="utf-8")
            with mock.patch.object(dependencies, "MANIFEST", copy):
                _code, out, _err = self._main(["dependencies", "--mode", "assemble"])
        line = next(ln for ln in out.splitlines() if f"interface {rel} " in ln and "e" * 64 in ln)
        self.assertEqual(line.strip(), f"interface {rel} expected sha256={'e' * 64} observed sha256={good}")

    def test_sop_ack_prints_the_receipt_path_and_the_section_count_and_refuses_with_a_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            with mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill), \
                    mock.patch.object(dependencies, "load_manifest", return_value={"entries": [entry]}):
                base = ["sop-ack", "sop-test", "--session", "reader-2", "--root", tmp]
                code, out, errors = self._main(base + ["--sections", "1"])
                self.assertEqual(code, 0, errors)
                self.assertIn("OK read receipt written:", out)
                self.assertIn("sops/SOP-TEST.md has 1 section headings (matches --sections)", out)
                code, out, errors = self._main(base + ["--sections", "4"])
                self.assertEqual((code, out), (2, ""))
                self.assertIn("FAIL AF-LAUNCH-SOP-ACK", errors)
                self.assertNotIn("has 1", errors + out)
                with self.assertRaises(SystemExit):  # --session is required by the parser
                    self._main(["sop-ack", "sop-test", "--root", tmp, "--sections", "1"])

    def test_sop_ack_never_starts_a_runtime_package_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            with mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill), \
                    mock.patch.object(dependencies, "load_manifest", return_value={"entries": [entry]}), \
                    mock.patch.object(dependencies, "ensure_runtime_packages") as install:
                code, _out, errors = self._main(["sop-ack", "sop-test", "--session", "reader-2", "--root", tmp,
                                                 "--sections", "1"])
            self.assertEqual(code, 0, errors)
            install.assert_not_called()

    def test_sop_ack_without_sections_is_refused_even_for_a_file_with_no_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            sop.write_text("no headings here\n", encoding="utf-8")
            with mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill), \
                    mock.patch.object(dependencies, "load_manifest", return_value={"entries": [entry]}):
                code, _out, errors = self._main(["sop-ack", "sop-test", "--session", "reader-2", "--root", tmp])
                self.assertEqual(code, 2, errors)
                self.assertFalse(list((skill / dependencies.SOP_RECEIPT_DIR).glob("*.json")))
                code, _out, errors = self._main(["sop-ack", "sop-test", "--session", "reader-2", "--root", tmp,
                                                 "--sections", "0"])
                self.assertEqual(code, 0, errors)  # counting zero headings and saying so is a real read


if __name__ == "__main__":
    unittest.main()

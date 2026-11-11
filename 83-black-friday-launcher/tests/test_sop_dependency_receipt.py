"""A declared SOP is a dependency only when its read receipt matches the file AND proves reading.

C5: dependencies.json carries `sop` entries; dependencies._present requires a
read receipt per declared SOP and refuses a missing, stale or mis-named one.
Issue 35: a sha256 match proves the file is unchanged, not that anyone opened it, so a receipt
also needs read_in_full, a reader session that is not the assembling one, the heading count of the
file, and a read date that is not before the SOP's last commit. `cli sop-ack` is the only writer.
"""

from __future__ import annotations

import datetime
import hashlib
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

from launcher_core import dependencies  # noqa: E402


def _fixture(tmp: Path):
    sop = tmp / "sops" / "SOP-TEST.md"
    sop.parent.mkdir(parents=True)
    sop.write_text("# SOP TEST\n\nread me\n", encoding="utf-8")
    skill = tmp / "skill"
    (skill / dependencies.SOP_RECEIPT_DIR).mkdir(parents=True)
    entry = {"id": "sop-test", "kind": "sop", "ref": "sops/SOP-TEST.md",
             "required": False}
    return sop, skill, entry


def _receipt(skill: Path, digest: str = "", sop_name: str = "sops/SOP-TEST.md", **over) -> None:
    record = {"sop": sop_name, "sha256": digest, "read_at": datetime.date.today().isoformat(),
              "read_in_full": True, "reader_session": "reader-1", "sections": 1}  # the fixture SOP has one heading
    record.update(over)
    for key in [k for k, v in record.items() if v is _DROP]:
        del record[key]
    (skill / dependencies.SOP_RECEIPT_DIR / "SOP-TEST.json").write_text(json.dumps(record), encoding="utf-8")


_DROP = object()


class SopReadReceiptTests(unittest.TestCase):
    def _present(self, root: Path, entry: dict, skill: Path) -> dict:
        with mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill):
            return dependencies._present(entry, root)

    def test_missing_receipt_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _sop, skill, entry = _fixture(Path(tmp))
            result = self._present(Path(tmp), entry, skill)
        self.assertEqual(result["status"], "missing", result["evidence"])
        self.assertIn("no read receipt", result["evidence"])

    def test_matching_receipt_is_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            _receipt(skill, hashlib.sha256(sop.read_bytes()).hexdigest())
            result = self._present(Path(tmp), entry, skill)
        self.assertEqual(result["status"], "present", result["evidence"])
        self.assertIn("receipt=", result["evidence"])

    def test_stale_receipt_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _sop, skill, entry = _fixture(Path(tmp))
            _receipt(skill, "0" * 64)
            result = self._present(Path(tmp), entry, skill)
        self.assertEqual(result["status"], "missing", result["evidence"])
        self.assertIn("is stale", result["evidence"])

    def test_receipt_naming_another_sop_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            _receipt(skill, hashlib.sha256(sop.read_bytes()).hexdigest(),
                     sop_name="sops/SOP-OTHER.md")
            result = self._present(Path(tmp), entry, skill)
        self.assertEqual(result["status"], "missing", result["evidence"])
        self.assertIn("names", result["evidence"])

    def _verdict(self, **over) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            _receipt(skill, hashlib.sha256(sop.read_bytes()).hexdigest(), **over)
            return self._present(Path(tmp), entry, skill)

    def test_a_receipt_that_does_not_say_it_was_read_in_full_is_refused(self):
        for over in ({"read_in_full": False}, {"read_in_full": _DROP}, {"read_in_full": "true"}):
            result = self._verdict(**over)
            self.assertEqual(result["status"], "missing", (over, result["evidence"]))
            self.assertIn("read_in_full", result["evidence"])

    def test_a_receipt_with_no_reader_session_is_refused(self):
        for over in ({"reader_session": _DROP}, {"reader_session": "  "}):
            result = self._verdict(**over)
            self.assertEqual(result["status"], "missing", (over, result["evidence"]))
            self.assertIn("reader_session", result["evidence"])

    def test_a_receipt_with_no_reader_session_is_refused_while_an_assembling_session_is_set(self):
        """With SKILL83_SESSION set, an empty reader differs from the assembling session, so only the
        absent-reader line refuses it (unset, the assembling-session branch would also catch it)."""
        with mock.patch.dict(os.environ, {dependencies.SOP_SESSION_ENV: "asm-1"}):
            for over in ({"reader_session": _DROP}, {"reader_session": "  "}, {"reader_session": ""}):
                result = self._verdict(**over)
                self.assertEqual(result["status"], "missing", (over, result["evidence"]))
                self.assertIn("reader_session is absent", result["evidence"])
                self.assertNotIn("assembling session", result["evidence"])
            self.assertEqual(self._verdict()["status"], "present")  # a real reader still passes

    def test_the_assembling_session_cannot_be_its_own_reader(self):
        with mock.patch.dict(os.environ, {dependencies.SOP_SESSION_ENV: "reader-1"}):
            result = self._verdict()
        self.assertEqual(result["status"], "missing", result["evidence"])
        self.assertIn("assembling session", result["evidence"])
        with mock.patch.dict(os.environ, {dependencies.SOP_SESSION_ENV: "someone-else"}):
            self.assertEqual(self._verdict()["status"], "present")

    def test_a_section_count_that_is_not_the_files_is_refused(self):
        for over in ({"sections": 2}, {"sections": _DROP}, {"sections": "1"}, {"sections": True}):
            result = self._verdict(**over)
            self.assertEqual(result["status"], "missing", (over, result["evidence"]))
            self.assertIn("heading count", result["evidence"])

    def test_a_read_date_that_is_absent_or_in_the_future_is_refused(self):
        future = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
        for over in ({"read_at": _DROP}, {"read_at": "yesterday"}, {"read_at": future}):
            result = self._verdict(**over)
            self.assertEqual(result["status"], "missing", (over, result["evidence"]))
            self.assertIn("read_at", result["evidence"])

    def test_the_heading_count_ignores_headings_inside_a_code_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            sop = Path(tmp) / "s.md"
            sop.write_text("# One\n\n```\n# not a heading\n```\n\n## Two\nplain # text\n", encoding="utf-8")
            self.assertEqual(dependencies.sop_heading_count(sop), 2)
            self.assertIsNone(dependencies.sop_heading_count(Path(tmp) / "absent.md"))

    def _commit_sop(self, tmp: Path, sop: Path, day: str) -> None:
        env = {**os.environ, "GIT_COMMITTER_DATE": f"{day}T12:00:00+00:00", "GIT_AUTHOR_DATE": f"{day}T12:00:00+00:00"}
        for argv in (["init", "-q"], ["add", sop.name],
                     ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "sop"]):
            subprocess.run(["git", *argv], cwd=sop.parent, env=env, check=True, capture_output=True)

    def test_a_read_dated_before_the_sops_last_commit_is_stale(self):
        """Commit 2026-11-10: 8 days before is refused, 7 and 6 days before are accepted, after is accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            self._commit_sop(Path(tmp), sop, "2026-11-10")
            digest = hashlib.sha256(sop.read_bytes()).hexdigest()
            verdicts = {}
            for read_at in ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-10"):
                _receipt(skill, digest, read_at=read_at)
                verdicts[read_at] = self._present(Path(tmp), entry, skill)
        self.assertEqual(verdicts["2026-11-02"]["status"], "missing", verdicts["2026-11-02"]["evidence"])  # 8 days
        self.assertIn("more than 7 days before the SOP's last commit", verdicts["2026-11-02"]["evidence"])
        for read_at in ("2026-11-03", "2026-11-04", "2026-11-10"):  # 7 days, 6 days, the day of the commit
            self.assertEqual(verdicts[read_at]["status"], "present", (read_at, verdicts[read_at]["evidence"]))
        self.assertNotIn("unverifiable", verdicts["2026-11-04"]["evidence"])

    def test_a_shallow_clone_cannot_date_a_sop_so_only_the_date_test_is_skipped(self):
        shallow = subprocess.CompletedProcess([], 0, stdout="true\n", stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            self._commit_sop(Path(tmp), sop, "2026-11-01")
            digest = hashlib.sha256(sop.read_bytes()).hexdigest()
            self.assertEqual(dependencies._last_commit_date(sop), datetime.date(2026, 11, 1))
            with mock.patch.object(dependencies.subprocess, "run", return_value=shallow):
                self.assertIsNone(dependencies._last_commit_date(sop))
                _receipt(skill, digest, read_at="2020-01-01")  # would be refused by the date test
                skipped = self._present(Path(tmp), entry, skill)
                self.assertEqual(skipped["status"], "present", skipped["evidence"])
                self.assertIn("date test unverifiable", skipped["evidence"])
                # every other proof still refuses
                for over in ({"read_in_full": False}, {"reader_session": _DROP}, {"sections": 9}):
                    _receipt(skill, digest, **over)
                    self.assertEqual(self._present(Path(tmp), entry, skill)["status"], "missing", over)

    def _ack(self, tmp: Path, sections, session="reader-2", **kw):
        sop, skill, entry = _fixture(tmp)
        with mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill), \
                mock.patch.object(dependencies, "load_manifest", return_value={"entries": [entry]}):
            return skill, entry, dependencies.ack_sop(kw.get("which", "sop-test"), session, sections, tmp)

    def test_sop_ack_writes_a_receipt_the_dependency_check_accepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill, entry, done = self._ack(Path(tmp), 1)
            self.assertEqual(done["sections"], 1)
            self.assertEqual(done["record"]["reader_session"], "reader-2")
            self.assertTrue(done["record"]["read_in_full"])
            self.assertEqual(self._present(Path(tmp), entry, skill)["status"], "present")

    def test_sop_ack_refuses_a_wrong_or_missing_count_and_writes_nothing(self):
        for sections in (2, 0, None):
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(dependencies.DependencyError) as caught:
                self._ack(Path(tmp), sections)
            self.assertIn("does not match the heading count", str(caught.exception))
            self.assertNotIn("has 1", str(caught.exception))  # the true count is never handed over in a refusal
            self.assertFalse(list((Path(tmp) / "skill" / dependencies.SOP_RECEIPT_DIR).glob("*.json")))

    def test_sop_ack_refuses_the_assembling_session_an_unknown_sop_and_a_blank_session(self):
        with mock.patch.dict(os.environ, {dependencies.SOP_SESSION_ENV: "reader-2"}), \
                tempfile.TemporaryDirectory() as tmp, self.assertRaises(dependencies.DependencyError):
            self._ack(Path(tmp), 1)
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(dependencies.DependencyError):
            self._ack(Path(tmp), 1, which="sop-nope")
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(dependencies.DependencyError):
            self._ack(Path(tmp), 1, session=" ")

    def test_sop_ack_refuses_a_blank_session_while_an_assembling_session_is_set(self):
        """With SKILL83_SESSION set, a blank --session differs from it, so only the blank-session line refuses."""
        with mock.patch.dict(os.environ, {dependencies.SOP_SESSION_ENV: "asm-1"}):
            for blank in ("", " ", None):
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaises(dependencies.DependencyError) as caught:
                        self._ack(Path(tmp), 1, session=blank)
                    self.assertIn("--session is required", str(caught.exception))
                    self.assertFalse(list((Path(tmp) / "skill" / dependencies.SOP_RECEIPT_DIR).glob("*.json")))
            with tempfile.TemporaryDirectory() as tmp:  # a real reader still writes one
                skill, _entry, done = self._ack(Path(tmp), 1, session="reader-9")
                self.assertEqual(done["record"]["reader_session"], "reader-9")

    def test_the_sop_ack_command_exits_2_on_a_mismatch_and_0_on_a_match(self):
        from launcher_core import cli
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            with mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill), \
                    mock.patch.object(dependencies, "load_manifest", return_value={"entries": [entry]}):
                base = ["sop-ack", "sop-test", "--session", "reader-2", "--root", tmp]
                self.assertEqual(cli.main(base + ["--sections", "5"]), 2)
                self.assertEqual(cli.main(base), 2)
                self.assertEqual(cli.main(base + ["--sections", "1"]), 0)

    def test_every_declared_sop_in_the_real_manifest_is_present(self):
        entries = [e for e in dependencies.load_manifest()["entries"]
                   if e.get("kind") == "sop"]
        self.assertTrue(entries, "the manifest declares no sop entry")
        for entry in entries:
            result = dependencies._present(entry, dependencies._repo_root())
            self.assertEqual(result["status"], "present",
                             f'{entry["id"]}: {result["evidence"]}')


if __name__ == "__main__":
    unittest.main()

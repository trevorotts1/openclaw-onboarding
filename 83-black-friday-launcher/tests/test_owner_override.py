"""SWB-094: the owner override for a client delivery with no page designs.

The refusal "designs are never waived for a client delivery" stays for every caller. The only exception is
a record signed with the operator key. Every positive test here has a negative twin run on the same
instrument: the same package, the same check, with the one thing that makes it valid taken away.
"""

from __future__ import annotations

import copy
import json
import os
import secrets
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher_core import checks, owner_override, package  # noqa: E402
from launcher_core.cli import build_parser  # noqa: E402
import test_check_rules as tcr  # noqa: E402

PLAN = "a" * 64
WORDS = ["I can bypass any thing I want", "finish ALL THE WORK NOW"]


class KeyCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.keydir = Path(self.tmp.name)
        self.key = self.keydir / "operator.key"
        self.key.write_text(secrets.token_hex(32) + "\n", encoding="utf-8")
        self.key.chmod(0o600)
        patcher = mock.patch.dict(os.environ, {"SF_OPERATOR_KEY_FILE": str(self.key)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self, plan=PLAN, **kw):
        return owner_override.mint(plan, kw.pop("scope", owner_override.SCOPE_PAGE_DESIGNS),
                                   kw.pop("words", WORDS), note=kw.pop("note", "test"))


class MintAndVerifyTests(KeyCase):
    def test_a_minted_record_verifies_and_never_carries_the_key(self):
        rec = self.record()
        self.assertEqual(owner_override.verify(rec, PLAN), [])
        self.assertNotIn(self.key.read_text().strip(), json.dumps(rec))
        self.assertEqual(len(rec["signature"]), 64)
        entry = owner_override.accept(rec, PLAN)
        self.assertEqual(entry["marker"], "OWNER OVERRIDE")
        self.assertIs(entry["verified"], True)

    def test_minting_needs_the_operator_key(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("SF_OPERATOR_KEY_FILE")
            with self.assertRaises(ValueError) as ctx:
                self.record()
        self.assertIn("no operator key", str(ctx.exception))

    def test_a_key_that_is_group_readable_is_refused(self):
        self.key.chmod(0o640)
        with self.assertRaises(ValueError):
            self.record()

    def test_a_short_key_is_refused(self):
        self.key.write_text("short\n", encoding="utf-8")
        self.key.chmod(stat.S_IRUSR | stat.S_IWUSR)
        with self.assertRaises(ValueError):
            self.record()

    def test_minting_refuses_no_words_a_bad_scope_and_a_bad_hash(self):
        for kw in ({"words": []}, {"words": ["  "]}, {"scope": "everything"}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.record(**kw)
        with self.assertRaises(ValueError):
            owner_override.mint("short", owner_override.SCOPE_PAGE_DESIGNS, WORDS)

    def test_every_edit_after_signing_breaks_the_signature(self):
        rec = self.record()
        for field, value in (("plan_hash", "b" * 64), ("owner_words", ["something else"]),
                             ("scope", "other"), ("note", "changed"), ("written_at", "2020-01-01T00:00:00Z"),
                             ("granted_by", "someone")):
            with self.subTest(field=field):
                bad = copy.deepcopy(rec)
                bad[field] = value
                self.assertNotEqual(owner_override.verify(bad, PLAN), [])

    def test_a_record_for_another_plan_or_scope_or_with_no_signature_is_refused(self):
        rec = self.record()
        self.assertTrue(any("another plan hash" in f for f in owner_override.verify(rec, "c" * 64)))
        self.assertTrue(any("scope" in f for f in owner_override.verify(rec, PLAN, "other")))
        unsigned = {k: v for k, v in rec.items() if k != "signature"}
        self.assertIn("the record is unsigned", owner_override.verify(unsigned, PLAN))
        forged = dict(rec, signature="0" * 64)
        self.assertTrue(any("does not match" in f for f in owner_override.verify(forged, PLAN)))
        for junk in (None, [], "x", {}):
            self.assertNotEqual(owner_override.verify(junk, PLAN), [])

    def test_a_record_signed_with_another_key_is_refused(self):
        rec = self.record()
        self.key.write_text(secrets.token_hex(32) + "\n", encoding="utf-8")
        self.key.chmod(0o600)
        self.assertTrue(any("does not match" in f for f in owner_override.verify(rec, PLAN)))

    def test_nothing_verifies_without_the_key(self):
        rec = self.record()
        with mock.patch.dict(os.environ):
            os.environ.pop("SF_OPERATOR_KEY_FILE")
            fails = owner_override.verify(rec, PLAN)
        self.assertTrue(any("operator key" in f for f in fails), fails)

    def test_the_cli_writes_a_signed_record_and_prints_no_key(self):
        out = self.keydir / "override.json"
        args = build_parser().parse_args(["owner-override", "--plan-hash", PLAN, "--owner-word", WORDS[0],
                                          "--out", str(out)])
        with mock.patch("builtins.print") as printed:
            self.assertEqual(args.fn(args), 0)
        self.assertEqual(owner_override.verify(json.loads(out.read_text()), PLAN), [])
        self.assertNotIn(self.key.read_text().strip(), str(printed.call_args_list))
        with self.assertRaises(Exception):  # a second write over the same file is refused
            args.fn(args)


class PackageWaiverStillRefusedTests(KeyCase):
    def test_the_client_delivery_waiver_refusal_is_unchanged_for_a_plain_waiver(self):
        waiver = tcr.verified_design_waiver(PLAN)
        with self.assertRaises(package.PackageError) as ctx:
            package._verify_design_waiver(waiver, PLAN, test_only=False)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ASSEMBLE-DESIGN-WAIVER")
        self.assertEqual(package._verify_design_waiver(waiver, PLAN, test_only=True)["approval_ref"],
                         "APPR-WAIVE-TEST")


class PaidOverrideTests(tcr.PaidPackageTests, KeyCase):
    """A client delivery (test_only false) assembled with the override, then re-checked."""

    for _name in dir(tcr.PaidPackageTests):  # the inherited tests are not re-run here: only this class's own
        if _name.startswith("test_") and _name != "test_only":
            locals()[_name] = None
    del _name

    def setUp(self):
        KeyCase.setUp(self)  # the key first, so the base setUp's patches sit inside the same environment
        tcr.PaidPackageTests.setUp(self)

    def plan_hash(self):
        return self.normalized["approval"]["hash"]

    def overridden(self, **over):
        rec = owner_override.mint(self.plan_hash(), owner_override.SCOPE_PAGE_DESIGNS, WORDS, note="test")
        rec.update(over)
        return rec

    def test_a_client_delivery_without_the_override_is_still_refused(self):
        with self.assertRaises(package.PackageError) as ctx:
            self.build(require_designs=False)  # PackageCase supplies a plain design_waiver
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ASSEMBLE-DESIGN-WAIVER")

    def test_a_tampered_or_foreign_override_is_refused_by_assemble(self):
        for name, rec in (("other plan", self.overridden(plan_hash="d" * 64)),
                          ("edited words", self.overridden(owner_words=["not what was signed"])),
                          ("unsigned", {k: v for k, v in self.overridden().items() if k != "signature"}),
                          ("forged signature", self.overridden(signature="1" * 64))):
            with self.subTest(name=name), self.assertRaises(package.PackageError) as ctx:
                self.build(require_designs=False, name="refused-" + name.replace(" ", "-"), owner_override=rec)
            self.assertEqual(ctx.exception.code, owner_override.CODE)

    def test_no_key_means_no_override_at_assemble(self):
        rec = self.overridden()
        with mock.patch.dict(os.environ):
            os.environ.pop("SF_OPERATOR_KEY_FILE")
            with self.assertRaises(package.PackageError) as ctx:
                self.build(require_designs=False, name="nokey", owner_override=rec)
        self.assertEqual(ctx.exception.code, owner_override.CODE)

    def test_a_signed_override_assembles_with_a_loud_marker_and_the_check_re_verifies_it(self):
        rec = self.overridden()
        built, root = self.build(require_designs=False, name="overridden", owner_override=rec)
        for record in (built["manifest"], built["receipt"]):
            self.assertIn("OWNER OVERRIDE", record["delivery_label"])
            self.assertEqual(record["owner_override"]["marker"], "OWNER OVERRIDE")
            self.assertEqual(record["owner_override"]["signature"], rec["signature"])
        self.assertIs(built["manifest"]["test_only"], False)
        label, fails = checks._design_level(built["manifest"], root, None)
        self.assertEqual(fails, [])
        self.assertIn("OWNER OVERRIDE", label)

    def test_the_check_refuses_a_manifest_whose_override_was_edited_or_cannot_be_verified(self):
        built, root = self.build(require_designs=False, name="overridden-2", owner_override=self.overridden())
        manifest = built["manifest"]
        for name, edit in (("words", lambda m: m["owner_override"].update(owner_words=["edited"])),
                           ("plan", lambda m: m.update(approved_plan_hash="e" * 64)),
                           ("signature", lambda m: m["owner_override"].update(signature="2" * 64)),
                           ("dropped, label kept", lambda m: m.update(owner_override=None))):
            with self.subTest(name=name):
                bad = copy.deepcopy(manifest)
                edit(bad)
                _, fails = checks._design_level(bad, root, None)
                self.assertTrue(fails, name)
        with mock.patch.dict(os.environ):
            os.environ.pop("SF_OPERATOR_KEY_FILE")
            _, fails = checks._design_level(manifest, root, None)
        self.assertTrue(any("operator key" in f for f in fails), fails)

    def test_an_override_never_loosens_the_refusal_for_a_manifest_that_has_none(self):
        built, root = self.build(require_designs=False, name="overridden-3", owner_override=self.overridden())
        stripped = copy.deepcopy(built["manifest"])
        stripped.pop("owner_override")
        stripped["design_waiver"] = None
        label, fails = checks._design_level(stripped, root, None)
        self.assertIn("designs are never waived for a client delivery", " ".join(fails))


if __name__ == "__main__":
    unittest.main()

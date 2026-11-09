#!/usr/bin/env python3
"""F21 item 11 — Skill 74's durable data root is the ONE shared resolver's answer.

The defect this pins: the adapter built its cache and receipt paths from
``os.path.join(home, ".openclaw", ...)`` while a separate ``DATA_OC_ROOT`` constant named
``/data/.openclaw``. Two computations, one run: on a Docker/VPS box HOME is the image's
temporary layer, so paid-job receipts landed somewhere a recreate wipes, and the mode file
was looked for in a different root than the one the state was written to.

Proven here:
  * the layout comes from shared-utils/durable-data-root.sh (the file Skill 46's
    data-root.js executes), so both modules of the callback route see the same root;
  * receipts are EVIDENCE and live under the durable root, not the prunable cache;
  * an unresolvable root is NAMED (health), never silently replaced by a guess;
  * existing receipts at the old path are reported and NOT moved (migration is F24's).
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import kie_live_adapter as K  # noqa: E402


class DurableDataRoot(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = self._t.name
        self.addCleanup(self._t.cleanup)

    def env(self, **extra):
        env = {"HOME": os.path.join(self.root, "home"), "OPENCLAW_DATA_ROOT": self.root,
               "KIE_API_KEY": "fake-key-SENTINEL"}
        env.update(extra)
        os.makedirs(env["HOME"], exist_ok=True)
        return env

    def test_layout_comes_from_the_shared_resolver(self):
        layout = K.resolve_durable_layout(self.env(), scope="client-alpha")
        self.assertEqual(layout["root"], self.root)
        state = os.path.join(self.root, "data", "kie-jobs", "client-alpha")
        self.assertEqual(layout["state_dir"], state)
        for name in ("registry", "index", "done", "receipts"):
            self.assertEqual(layout[name], os.path.join(state, name), name)
        self.assertTrue(layout["resolver"].endswith("durable-data-root.sh"), layout["resolver"])

    def test_scope_must_be_one_path_segment(self):
        with self.assertRaises(K.KieError) as ctx:
            K.resolve_durable_layout(self.env(), scope="../../etc")
        self.assertEqual(ctx.exception.code, "data_root_unresolved")

    def test_adapter_writes_receipts_under_the_durable_root(self):
        a = K.Adapter(env=self.env())
        self.assertEqual(a.data_root, self.root)
        self.assertEqual(a.rdir, os.path.join(self.root, "data", "kie-jobs",
                                              K.DURABLE_SCOPE, "receipts"))
        a.receipt("unit-probe", note="f21-item-11")
        written = os.listdir(a.rdir)
        self.assertEqual(len(written), 1, written)
        with open(os.path.join(a.rdir, written[0]), encoding="utf-8") as fh:
            self.assertIn("unit-probe", fh.read())
        # The cache is the OTHER durable location and stays under <root>/cache: one root,
        # two derived locations, no second computation of $HOME.
        self.assertEqual(a.cache, os.path.join(self.root, "cache", "kie-live-adapter"))

    def test_health_reports_the_root_and_the_evidence_dir(self):
        a = K.Adapter(env=self.env())
        a.key = ""  # no network call: health reports paths first
        data = a.cmd_health()["data"]
        self.assertEqual(data["data_root"], self.root)
        self.assertEqual(data["receipts_dir"], a.rdir)
        self.assertTrue(str(data["data_root_resolver"]).endswith("durable-data-root.sh"))
        self.assertIsNone(data["data_root_warning"])

    def test_unresolvable_root_is_named_not_guessed(self):
        env = {"HOME": os.path.join(self.root, "empty-home")}
        os.makedirs(env["HOME"], exist_ok=True)
        a = K.Adapter(env=env)
        self.assertIsNone(a.data_root)
        self.assertIn("durable data root unresolved", a.data_root_warning)
        # No layout -> the old location, unchanged, so nothing silently moves.
        self.assertEqual(a.rdir, os.path.join(env["HOME"], ".openclaw", "cache",
                                              "kie-live-adapter", "receipts"))

    def test_legacy_receipts_are_reported_and_never_moved(self):
        home = os.path.join(self.root, "home")
        legacy = os.path.join(home, ".openclaw", "cache", "kie-live-adapter", "receipts")
        os.makedirs(legacy)
        kept = os.path.join(legacy, "20260101.jsonl")
        with open(kept, "w", encoding="utf-8") as fh:
            fh.write('{"event":"older"}\n')
        a = K.Adapter(env=self.env())
        self.assertTrue(os.path.isfile(kept), "the earlier receipt file was NOT moved or deleted")
        self.assertIn(legacy, a.migration_note)
        self.assertIn(a.rdir, a.migration_note)
        self.assertEqual(os.listdir(a.rdir) if os.path.isdir(a.rdir) else [], [],
                         "nothing was copied into the new location either")

    def test_resolver_is_the_only_authority_for_the_cache_too(self):
        layout = K.resolve_durable_layout(self.env())
        a = K.Adapter(env=self.env())
        self.assertEqual(a.cache, layout["cache"])
        # The removed constant must stay removed: a second hard-coded root is the defect.
        self.assertFalse(hasattr(K, "DATA_OC_ROOT"),
                         "DATA_OC_ROOT is back: the root must come from the resolver only")


if __name__ == "__main__":
    unittest.main()

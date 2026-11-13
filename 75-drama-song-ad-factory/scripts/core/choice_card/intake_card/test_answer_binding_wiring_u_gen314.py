"""U-GEN314 (finding S75-018, audit row C05): the snapshot-checked answer
reader is wired into production.

Before this unit ``answer_binding.bind_run`` had no caller anywhere in the
tree, so a resumed run with the old three-choice answers had nothing that read
its saved MUSIC answer through its own frozen question snapshot. Every test
here fails on that tree:

* the production import and the ``bind_run`` call site do not exist;
* the read-only production admission (``inspect_intake``, the one gate every
  resumed run passes) admits a session whose saved music record no longer
  matches its own definition digest.

No provider, model, media or client-send call: the session is driven through
the real intake API with offline replies.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CORE = HERE.parent.parent
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import production_process
from music_styles import catalog
from test_production_process import confirmed_run


class AnswerBindingWiredTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="u-gen314-")
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "run"

    # -- the check that proves the wiring exists ---------------------------
    def test_the_production_import_and_the_bind_run_call_site_exist(self):
        source = Path(production_process.__file__).read_text(encoding="utf-8")
        imports, calls = [], []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module == "choice_card.intake_card":
                for alias in node.names:
                    if alias.name == "answer_binding":
                        imports.append("%s:%d import answer_binding from %s"
                                       % (production_process.__file__, node.lineno,
                                          node.module))
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                if name == "bind_run":
                    calls.append("%s:%d call bind_run(...)"
                                 % (production_process.__file__, node.lineno))
        for line in imports + calls:
            print(line)
        self.assertEqual(len(imports), 1, "exactly one production import of answer_binding")
        self.assertEqual(len(calls), 1, "exactly one production call site of bind_run")

    # -- the resumed run resolves its style through the frozen snapshot ----
    def _confirmed(self):
        rid = confirmed_run(self.run)
        path = self.run / "control" / "intake-session.json"
        return rid, path, json.loads(path.read_text(encoding="utf-8"))

    def test_a_matching_snapshot_resolves_the_frozen_catalog_style(self):
        _, _, state = self._confirmed()
        record = state["answer_records"]["music"]
        label = record["option"]["label"]
        expected = [sid for sid in catalog.STYLE_IDS
                    if catalog.CATALOG[sid]["label"] == label]
        self.assertEqual(len(expected), 1, "the card offers one catalog row per label")

        admitted = production_process.inspect_intake(self.run)
        self.assertTrue(admitted["ok"], admitted)
        style = admitted["music_style"]
        self.assertEqual(style["style_id"], expected[0])
        self.assertEqual(style["style_label"], label)
        self.assertEqual(style["catalog_revision"], catalog.CATALOG_REVISION)
        self.assertEqual(style["definition_digest"], record["definition_digest"])
        self.assertEqual(style["question_digest"], record["question_digest"])
        self.assertEqual(style["number_shown"], record["option"]["number_shown"])
        self.assertTrue(style["production_fact"])
        self.assertFalse(style["test_only"])

    def test_a_changed_definition_digest_refuses_the_resumed_run(self):
        _, path, state = self._confirmed()
        record = state["answer_records"]["music"]
        record["definition_digest"] = "0" * 64
        path.write_text(json.dumps(state), encoding="utf-8")

        admitted = production_process.inspect_intake(self.run)
        self.assertFalse(admitted["ok"], admitted)
        self.assertEqual(admitted["reason_code"], "BINDING_DEFINITION_DIGEST_MISMATCH")


if __name__ == "__main__":
    unittest.main()

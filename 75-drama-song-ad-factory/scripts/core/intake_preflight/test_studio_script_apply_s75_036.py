#!/usr/bin/env python3
"""S75-036: a Studio script approval is applied WITH its provenance.

The page records who answered, when, for which version, and the exact
presentation digest it showed. `factory.py next` used to read only the answer
value, so the approval path lost that provenance. This file proves:

  * a published script and a matching Studio answer -> ONE `next` approves the
    script in-process, and the recorded approvals name source `studio`, the run
    id, and a source reference built from `<order>/<stage>/<version>/<digest>`;
  * an answer whose presentation digest does not match what this run published
    is refused, and the script stage stays waiting with no approval recorded;
  * an answer for a version this run never published is refused the same way.

stdlib only: no pytest import (CI runs every test_*.py under scripts/core with
bare python3 and a fresh empty HOME). Every test is a zero-argument `test_*`
function with plain asserts, so the SAME file runs both ways:

  python3 75-drama-song-ad-factory/scripts/core/intake_preflight/test_studio_script_apply_s75_036.py
  python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/intake_preflight

No network, no provider, no openclaw binary; writes only under a temp dir.
"""
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent

for _p in (str(CORE), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from intake_preflight import factory as F                       # noqa: E402
from script_approval import script_approval as approval         # noqa: E402
from test_production_process import (confirmed_run, complete_stage,  # noqa: E402
                                     write_json)


class FakeStudio:
    """The approvals_bridge seam, stubbed with the REAL record shape.

    `answer_item` returns the same fields the shipped bridge returns: value,
    who, when, version and the presentation digest. `_item_digest` is the
    bridge's own canonicalisation, so the publish record and the answer bind
    the same bytes.
    """

    def __init__(self):
        self.published = []
        self.answer = None

    @staticmethod
    def _item_digest(item):
        canonical = {"stage": item.get("stage"), "version": item.get("version"),
                     "text": item.get("text"), "choices": item.get("choices") or []}
        raw = json.dumps(canonical, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def publish(self, base_url, key, order_id, stage, version, text, choices, files):
        item = {"stage": stage, "version": version, "text": text,
                "choices": list(choices), "files": []}
        self.published.append(item)
        self.answer = None
        return item

    def answer_item(self, base_url, key, order_id, stage, version):
        record = self.answer
        if not record or record.get("stage") != stage or record.get("version") != version:
            return None
        return dict(record)


class StudioScriptApply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="studio-script-apply-")
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "run"
        self.run_id = confirmed_run(self.run)
        for stage in ("research", "creative-strategy", "script-lyrics"):
            complete_stage(self.run, stage)
        shutil.copyfile(CORE / "story_arc" / "fixtures" / "valid.json",
                        self.run / "creative" / "story.json")
        shutil.copyfile(CORE / "lyric_writer" / "fixtures" / "campaign.json",
                        self.run / "creative" / "lyrics.json")
        self.doc = {"title": "The Climb",
                    "story": [["The world", ["She runs a small shop."]]],
                    "sheet": [{"tag": "Intro", "lines": ["One closed door."]},
                              {"tag": "Hook 1", "lines": ["I am not sma-a-all",
                                                          "I ne-ever wa-a-as"]}]}
        self.doc["lyrics"] = "\n".join(line for part in self.doc["sheet"]
                                       for line in part["lines"])
        write_json(self.run / "creative" / "script.json", self.doc)
        write_json(self.run / "control" / "studio-order.json",
                   {"order_id": "o-1", "client_id": "c-1", "title": "T",
                    "base_url": "https://studio.example"})
        self.studio = FakeStudio()
        saved = (F._approvals_bridge, F._studio_key)
        F._approvals_bridge = lambda: self.studio
        F._studio_key = lambda: "test-key"

        def restore():
            F._approvals_bridge, F._studio_key = saved
        self.addCleanup(restore)

    def cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = F.main(list(args))
        return code, json.loads(out.getvalue())

    def present(self):
        """First `next`: the script is published to the page, run waits."""
        code, env = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 2, env)
        self.assertEqual(env["reason_code"], "SCRIPT_AWAITING_APPROVAL", env)
        self.assertEqual([item["stage"] for item in self.studio.published], ["script"])
        digest = FakeStudio._item_digest(self.studio.published[-1])
        stored = json.loads((self.run / "control" / "studio-publish.json")
                            .read_text("utf-8"))
        self.assertEqual(stored["script"]["1"], digest)
        return env, digest

    def answer(self, value="Approve both", digest=None):
        published = self.studio.published[-1]
        self.studio.answer = {
            "stage": "script", "version": published["version"],
            "question": published["text"], "choices": published["choices"],
            "value": value, "by": "link", "at": 1794531000,
            "digest": digest or FakeStudio._item_digest(published)}

    def test_matching_digest_approves_in_process_with_studio_provenance(self):
        _, digest = self.present()
        self.assertEqual(approval.record_for(self.run)["status"], "pending")
        self.answer()
        code, env = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 0, env)
        self.assertEqual(env["reason_code"], "script-approved", env)
        record = approval.record_for(self.run)
        self.assertEqual(record["status"], "approved")
        self.assertEqual({event["source"] for event in record["approvals"]}, {"studio"})
        self.assertEqual({event["source_ref"] for event in record["approvals"]},
                         {"o-1/script/1/%s" % digest})
        self.assertEqual({str(event["run_id"]) for event in record["approvals"]},
                         {str(self.run_id)})

    def test_mismatched_digest_is_refused_and_the_stage_stays_waiting(self):
        _, published = self.present()
        self.answer(digest="0" * 64)
        code, env = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 2, env)
        self.assertEqual(env["outcome"], "waiting", env)
        self.assertEqual(env["reason_code"], "studio-presentation-mismatch", env)
        self.assertEqual(env["data"]["published_digest"], published, env)
        record = approval.record_for(self.run)
        self.assertEqual(record["approvals"], [])
        self.assertNotEqual(record["status"], "approved")

    def test_an_unpublished_version_is_never_approved(self):
        self.present()
        self.answer()
        (self.run / "control" / "studio-publish.json").write_text("{}", "utf-8")
        code, env = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 2, env)
        self.assertEqual(env["outcome"], "waiting", env)
        self.assertEqual(env["reason_code"], "studio-presentation-unverified", env)
        self.assertEqual(approval.record_for(self.run)["approvals"], [])


if __name__ == "__main__":
    unittest.main()

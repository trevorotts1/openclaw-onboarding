"""SWB-021 regressions: browser-only steps stay out of the API step save, the
true step-save refusal is surfaced, and a journalled empty shell is resumed.

Synthetic-local only: the L07 fake provider client, no network, no
credentials, no live sends and no mutations. Run:
    python3 tools/engine/tests/test_swb021_browser_only_save.py
"""

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import test_workflow_builder_l07 as l07  # noqa: E402
from cli_anything.gohighlevel.utils import launch_step_compiler as lsc  # noqa: E402
from cli_anything.gohighlevel.utils import workflow_builder as wb  # noqa: E402

LOC = l07.LOC
REFUSAL = ('{"errorMessage":"Action validation failed: wait (x-until): '
           'Type has an invalid value \\"until_date\\". Please choose a valid type"}')


class StrictProvider(l07.FakeClient):
    """Rejects a step save the way GoHighLevel does: the WHOLE graph fails on
    one action whose type it does not know, or whose id is not a UUID."""

    def request(self, method, path, body=None, workflow_name=None):
        if (method == "PUT" and path.startswith("/workflow/%s/" % LOC)
                and "/trigger/" not in path and body and "workflowData" in body):
            for step in body["workflowData"]["templates"]:
                attrs = step.get("attributes") or {}
                if attrs.get("type") == "until_date" or not wb._is_uuid(step.get("id")):
                    self.call_count += 1
                    self.calls.append((method, path, copy.deepcopy(body)))
                    return {"_error": True, "http_code": 400, "code": 400,
                            "message": REFUSAL}
        return super().request(method, path, body, workflow_name)


def _with_until_step(campaign):
    """Put the compiler's own wait-until-date step in front of the 2nd email
    of the first workflow, exactly as launch_step_compiler._apply_absolute does."""
    key = next(iter(campaign))
    wf = campaign[key]
    steps = wf["templates"]
    emails = [s for s in steps if s.get("type") == "email"]
    target = emails[1]
    ledger = "%s#wait_until_date#%s" % (wf["unit_key"], target["id"])
    until = lsc._until_step("%s-until" % target["id"], "2026-11-27T09:00:00-05:00",
                            "America/New_York", ledger)
    prev = next(s for s in steps if s.get("next") == target["id"])
    until.update(next=target["id"], parentKey=prev["id"])
    prev["next"] = until["id"]
    target["parentKey"] = until["id"]
    steps.insert(steps.index(target), until)
    wf.setdefault("browser_steps", []).append(
        {"kind": "managed_browser_step", "action": "wait_until_date",
         "unit_key": wf["unit_key"], "status": "pending", "step_id": target["id"],
         "at": "2026-11-27T09:00:00-05:00", "ledger_id": ledger,
         "wait_step_id": until["id"]})
    return key, until, target


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="swb021-"))
        self._env = {k: os.environ.get(k) for k in ("CAF_DATA_DIR", "CAF_DRAFT_ONLY")}
        os.environ["CAF_DATA_DIR"] = str(self.temp / "data")
        os.environ["CAF_DRAFT_ONLY"] = "true"
        self.campaign = wb.compile_launch_builds(l07.synthetic_document())
        self.journal = wb.BuildJournal(self.temp / "journal.jsonl")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class BrowserOnlyStepsStayOutOfTheApiSave(_Base):
    def test_until_date_step_is_not_sent_and_the_rest_saves(self):
        key, until, target = _with_until_step(self.campaign)
        client = StrictProvider()
        stats = wb.CampaignBuilder(client).build(
            self.campaign, folder_name="Synthetic", journal=self.journal)
        self.assertEqual(stats["errors"], [], stats["errors"])
        saves = [c for c in client.calls if c[0] == "PUT" and c[2]
                 and "workflowData" in c[2]]
        self.assertTrue(saves)
        for _m, _p, body in saves:
            types = [(s.get("attributes") or {}).get("type")
                     for s in body["workflowData"]["templates"]]
            self.assertNotIn("until_date", types, "a browser-only step rode the API save")
        # the remaining chain is re-joined around the removed step
        wf_id = stats["workflow_ids"][key]
        saved = client.workflows[wf_id]["templates"]
        by_id = {s["id"]: s for s in saved}
        target_saved = next(s for s in saved if s.get("name") == target["name"])
        parent = by_id[target_saved["parentKey"]]
        self.assertEqual(parent.get("next"), target_saved["id"])
        self.assertTrue(all(isinstance(s.get("order"), int) for s in saved))
        # the removed step is recorded and its ledger row stays owed
        excluded = stats["browser_only_excluded"][key]
        self.assertEqual([e["ledger_id"] for e in excluded],
                         [until["attributes"]["ledger_id"]])
        owed = stats["browser_steps"]["requested"]
        self.assertIn(until["attributes"]["ledger_id"], [r["ledger_id"] for r in owed])
        self.assertNotIn(until["attributes"]["ledger_id"], stats["browser_steps"]["completed"])
        self.assertTrue(all(item["ok"] for item in stats["readback"].values()))

    def test_split_rejoins_branch_targets(self):
        steps = [
            {"id": "a", "type": "email", "next": "w"},
            {"id": "w", "type": "wait", "rail": "managed_browser", "parentKey": "a",
             "next": "g", "attributes": {"type": "until_date", "ledger_id": "L1"}},
            {"id": "g", "type": "if_else", "parentKey": "w",
             "branches": {"true": "w2", "false": "c"}},
            {"id": "w2", "type": "wait", "parentKey": "g", "next": "b",
             "attributes": {"type": "event_relative", "rail": "managed_browser",
                            "ledger_id": "L2"}},
            {"id": "b", "type": "sms", "parentKey": "w2", "next": "c"},
            {"id": "c", "type": "workflow_goal", "parentKey": "b"},
        ]
        kept, removed = wb.split_browser_only_steps(steps)
        self.assertEqual([s["id"] for s in kept], ["a", "g", "b", "c"])
        by_id = {s["id"]: s for s in kept}
        self.assertEqual(by_id["a"]["next"], "g")
        self.assertEqual(by_id["g"]["parentKey"], "a")
        self.assertEqual(by_id["g"]["branches"], {"true": "b", "false": "c"})
        self.assertEqual(by_id["b"]["parentKey"], "g")
        self.assertEqual([r["ledger_id"] for r in removed], ["L1", "L2"])
        self.assertEqual(steps[1]["id"], "w", "input was mutated")


class TrueSaveErrorIsSurfaced(_Base):
    def test_step_save_refusal_is_not_replaced_by_the_reentry_readback(self):
        key = next(iter(self.campaign))
        self.campaign[key]["allow_reentry"] = False  # provider reports no settings
        client = StrictProvider()
        # Force the refusal: an unknown action type the provider rejects.
        self.campaign[key]["templates"][0]["attributes"]["type"] = "until_date"
        stats = wb.CampaignBuilder(client).build(
            self.campaign, folder_name="Synthetic", journal=self.journal)
        joined = "\n".join(stats["errors"])
        self.assertIn("step-save PUT failed (HTTP 400)", joined)
        self.assertIn("Type has an invalid value", joined)
        mine = [e for e in stats["errors"] if self.campaign[key]["name"] in e]
        self.assertTrue(mine and "step-save PUT failed" in mine[0], mine)

    def test_transport_keeps_the_whole_validation_message(self):
        from cli_anything.gohighlevel.internal import transport as tr
        long_body = ('{"errorMessage":"Action validation failed: '
                     + "x" * 400 + ' THE-END"}')

        class Resp:
            status_code = 400
            content = long_body.encode()
            headers = {}

        original = tr.requests.request
        tr.requests.request = lambda *a, **k: Resp()
        try:
            transport = tr.InternalTransport.__new__(tr.InternalTransport)
            transport._call_count = 0
            out = transport._do_request("PUT", "/workflow/L/W", {"a": 1}, "synthetic")
        finally:
            tr.requests.request = original
        self.assertEqual(out["http_code"], 400)
        self.assertTrue(out["message"].endswith('THE-END"}'), out["message"][-40:])


class JournalledEmptyShellIsResumed(_Base):
    def test_empty_shell_from_a_refused_save_is_resumed_not_duplicated(self):
        key, _until, _target = _with_until_step(self.campaign)
        wf_def = self.campaign[key]
        client = l07.FakeClient()
        # The state SWB-018 left: a shell created, its save refused, empty.
        shell_id = "wf-shell"
        client.workflows[shell_id] = {"name": wf_def["name"], "parentId": None,
                                      "templates": [], "version": 1}
        for phase, status in (("create", "ok"), ("save", "failed"),
                              ("reentry", "unknown")):
            self.journal.append(unit_key=wf_def["unit_key"], name=wf_def["name"],
                                remote_id=shell_id, phase=phase, status=status,
                                expected_hash="0" * 64)
        stats = wb.CampaignBuilder(client).build(
            self.campaign, folder_name="Synthetic", journal=self.journal)
        self.assertEqual(stats["errors"], [], stats["errors"])
        self.assertEqual(stats["workflow_ids"][key], shell_id)
        named = [w for w in client.workflows.values() if w["name"] == wf_def["name"]]
        self.assertEqual(len(named), 1, "the shell was duplicated")
        self.assertTrue(client.workflows[shell_id]["templates"])
        self.assertIn(wf_def["name"], stats["resumed"])
        phases = [(e["phase"], e["status"]) for e in self.journal.entries()
                  if e.get("remote_id") == shell_id]
        self.assertIn(("reconcile", "resume_empty_shell"), phases)
        self.assertIn(("readback", "ok"), phases)

    def test_non_empty_mismatch_is_still_a_preserved_human_edit(self):
        key = next(iter(self.campaign))
        wf_def = self.campaign[key]
        client = l07.FakeClient()
        client.workflows["wf-human"] = {"name": wf_def["name"], "parentId": None,
                                        "templates": [{"id": "h", "type": "email",
                                                       "attributes": {}}], "version": 1}
        for phase, status in (("create", "ok"), ("save", "failed")):
            self.journal.append(unit_key=wf_def["unit_key"], name=wf_def["name"],
                                remote_id="wf-human", phase=phase, status=status,
                                expected_hash="0" * 64)
        stats = wb.CampaignBuilder(client).build(
            self.campaign, folder_name="Synthetic", journal=self.journal)
        self.assertTrue(any("human edit" in e.lower() for e in stats["errors"]))
        self.assertEqual(len(client.workflows["wf-human"]["templates"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

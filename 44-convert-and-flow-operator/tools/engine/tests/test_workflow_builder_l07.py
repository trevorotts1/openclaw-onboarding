"""L07 (UL-010) provider compiler / journal / readback regressions.

Synthetic-local only: a local fake provider client, no network, no credentials,
no live sends and no mutations. Run:
    python3 tools/engine/tests/test_workflow_builder_l07.py
"""

import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
TOOLS = ENGINE.parent
SKILL = TOOLS.parent
REPO = SKILL.parent
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel.utils import workflow_builder as wb  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "launch_c_plan_reader",
    SKILL / "automation-templates" / "launch-c" / "plan_reader.py")
plan_reader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_reader)

LOC = "SYNTHETIC_LOCATION"
CALENDAR = {
    "launch_at": "2026-11-03T12:00:00-05:00",
    "doors_open_at": "2026-11-03T09:00:00-05:00",
    "doors_close_at": "2026-11-10T23:59:00-05:00",
    "timezone": "America/New_York",
}
NOW = "2026-11-01T00:00:00-05:00"


class FakeClient:
    """Local stand-in for the private rail; no network, no credentials."""

    location_id = LOC

    def __init__(self):
        self.call_count = 0
        self.calls = []
        self.workflows = {}
        self.folders = {}
        self.triggers = {}
        self._next = 1
        self.fail_create = False
        self.create_without_response = False
        self.fail_workflow_read = False
        # Simulate a provider that ignores the enrolment field (readback absent).
        self.drop_allow_multiple = False

    def _id(self, prefix):
        value = "%s-%d" % (prefix, self._next)
        self._next += 1
        return value

    def request(self, method, path, body=None, workflow_name=None):
        self.call_count += 1
        self.calls.append((method, path, copy.deepcopy(body)))
        body = body or {}
        if method == "GET" and path == "/workflow/%s" % LOC:
            items = []
            for folder_id, folder in self.folders.items():
                items.append({"id": folder_id, "_id": folder_id,
                              "name": folder["name"], "type": "directory"})
            for wf_id, wf in self.workflows.items():
                items.append({"id": wf_id, "_id": wf_id, "name": wf["name"],
                              "type": "workflow", "parentId": wf.get("parentId")})
            return items
        if method == "POST" and path == "/workflow/%s" % LOC:
            if body.get("type") == "directory":
                folder_id = self._id("folder")
                self.folders[folder_id] = {"name": body["name"]}
                return {"id": folder_id}
            if self.fail_create:
                return None
            wf_id = self._id("wf")
            self.workflows[wf_id] = {
                "name": body["name"], "parentId": body.get("parentId"),
                "templates": [], "version": 1,
            }
            # The provider keeps the top-level settings fields it was sent
            # (enrolment = allowMultiple) — the stand-in must too, or the
            # enrolment readback would be untestable.
            for field in ("allowMultiple",):
                if field in body:
                    self.workflows[wf_id][field] = body[field]
            if self.create_without_response:
                return None
            return {"id": wf_id}
        if method == "POST" and path.endswith("/trigger"):
            trigger_id = self._id("trig")
            self.triggers[trigger_id] = copy.deepcopy(body)
            return {"id": trigger_id}
        if method == "PUT" and "/trigger/" in path:
            return {"ok": True}
        if method == "PUT" and path.startswith("/workflow/%s/" % LOC):
            wf_id = path.rsplit("/", 1)[1]
            wf = self.workflows.get(wf_id)
            if not wf:
                return {"_error": True, "http_code": 404}
            if "workflowData" in body:
                wf["templates"] = body["workflowData"]["templates"]
            if "version" in body:
                wf["version"] = body["version"]
            for field in ("allowMultiple",):
                if field in body:
                    wf[field] = body[field]
            return {"ok": True}
        if method == "GET" and path.startswith("/workflow/%s/" % LOC):
            if self.fail_workflow_read:
                return {"_error": True, "http_code": 503}
            wf_id = path.rsplit("/", 1)[1]
            wf = self.workflows.get(wf_id)
            if not wf:
                return {"_error": True, "http_code": 404}
            document = {"workflowData": {"templates": wf["templates"]},
                        "version": wf.get("version", 1), "meta": {}}
            # Mirror the live document: settings are TOP-LEVEL fields, and
            # allowMultiple is omitted when it was never sent (the honest
            # "provider did not report it" case).
            if "allowMultiple" in wf and not self.drop_allow_multiple:
                document["allowMultiple"] = wf["allowMultiple"]
            return document
        return {"_error": True, "http_code": 404}

    def create_location_tag(self, tag, workflow_name=None):
        self.calls.append(("TAG", tag, None))


def _build_plan(seq_id, count):
    templates = [
        {"id": "e%d" % index, "type": "email", "name": "Email %d" % index,
         "attributes": {"subject": "synthetic %d" % index,
                        "body": "<p>synthetic</p>", "html": "<p>synthetic</p>",
                        "fromName": "Synthetic Sender", "conditions": []}}
        for index in range(count)
    ]
    return {
        "folder": "Synthetic Drafts",
        "_meta": {"sequence_id": seq_id, "draft_only": True,
                  "deploy_mode": "draft-only",
                  # what a Skill 50 build plan carries; the reader supplies none of it
                  "enrollment_conditions": copy.deepcopy(plan_reader.DEFAULT_ENROLLMENT_CONDITIONS),
                  "lifecycle": copy.deepcopy(plan_reader.DEFAULT_LIFECYCLE),
                  "sender_config_refs": copy.deepcopy(plan_reader.DEFAULT_SENDER)},
        seq_id: {"name": "%s (DRAFT)" % seq_id, "tag": "launch:%s" % seq_id,
                 "status": "draft", "templates": templates},
    }


def synthetic_document():
    """Run the real launch-c reader over synthetic files, then compile."""
    launch_plan = {
        "schema_version": "1.0.0",
        "launch_id": "l07-build",
        "a2p_ready": False,
        "conversation_ai": {"requested": False, "mode": "none"},
        "offer": {"name": "Synthetic", "price_usd": 1, "currency": "USD",
                  "payment_plans": False},
        "launch_calendar": dict(CALENDAR),
        "pages": [{"id": "page_landing", "kind": "landing",
                   "url": "https://example.test", "waits_for": []}],
        "email_sequences": [
            {"id": "email_pre_launch", "kind": "pre_launch", "provider": "skill50",
             "email_count": 2, "draft_only": True, "waits_for": []},
            {"id": "email_welcome_access", "kind": "welcome_access",
             "provider": "skill50", "email_count": 2, "draft_only": True,
             "waits_for": []},
        ],
        "text_sets": [],
        "automations": [
            {"id": "auto_pre_launch", "family": "pre_launch", "template": "launch-a/launch-a-prelaunch-window",
             "build_rail": "skill44_engine", "draft_only": True,
             "trigger": {"type": "tag_added"},
             "waits_for": ["email_pre_launch", "page_landing"]},
            {"id": "auto_post_sale", "family": "post_sale", "template": "launch-b/launch-post-sale-purchase",
             "build_rail": "skill44_engine", "draft_only": True,
             "trigger": {"type": "payment_succeeded"},
             "waits_for": ["email_welcome_access", "page_landing"]},
        ],
    }
    temp = Path(tempfile.mkdtemp(prefix="l07-build-"))
    plan_path = temp / "plan.json"
    plan_path.write_text(json.dumps(launch_plan))
    argv = ["--launch-plan", str(plan_path), "--out", str(temp / "out.json"),
            "--now", NOW]
    for seq_id, count in (("email_pre_launch", 2), ("email_welcome_access", 2)):
        path = temp / ("%s.json" % seq_id)
        path.write_text(json.dumps(_build_plan(seq_id, count)))
        argv += ["--build-plan", str(path)]
    assert plan_reader.main(argv) == 0
    return json.loads((temp / "out.json").read_text())


def full_launch_document():
    """Reader over a launch plan that also carries non-email automations."""
    launch_plan = {
        "schema_version": "1.0.0",
        "launch_id": "l07-full",
        "a2p_ready": False,
        "conversation_ai": {"requested": False, "mode": "none"},
        "offer": {"name": "Synthetic", "price_usd": 1, "currency": "USD",
                  "payment_plans": False},
        "launch_calendar": dict(CALENDAR),
        "pages": [{"id": "page_landing", "kind": "landing",
                   "url": "https://example.test", "waits_for": []}],
        "email_sequences": [
            {"id": "email_pre_launch", "kind": "pre_launch", "provider": "skill50",
             "email_count": 2, "draft_only": True, "waits_for": []},
            {"id": "email_welcome_access", "kind": "welcome_access",
             "provider": "skill50", "email_count": 2, "draft_only": True,
             "waits_for": []},
        ],
        "text_sets": [],
        "automations": [
            {"id": "auto_pre_launch", "family": "pre_launch", "template": "launch-a/launch-a-prelaunch-window",
             "build_rail": "skill44_engine", "draft_only": True,
             "trigger": {"type": "tag_added"},
             "waits_for": ["email_pre_launch", "page_landing"]},
            {"id": "auto_post_sale", "family": "post_sale", "template": "launch-b/launch-post-sale-purchase",
             "build_rail": "skill44_engine", "draft_only": True,
             "trigger": {"type": "payment_succeeded"},
             "waits_for": ["email_welcome_access", "page_landing"]},
            {"id": "auto_cart_recovery", "family": "abandoned_checkout",
             "template": "launch-b/abandoned-checkout-recovery", "build_rail": "skill44_engine", "draft_only": True,
             "trigger": {"type": "checkout_abandoned"},
             "waits_for": ["page_landing"]},
            {"id": "auto_cart_followup", "family": "abandoned_checkout",
             "template": "launch-b/abandoned-checkout-recovery", "build_rail": "skill44_engine", "draft_only": True,
             "trigger": {"type": "tag_added"},
             "waits_for": ["auto_cart_recovery", "email_pre_launch"]},
        ],
    }
    temp = Path(tempfile.mkdtemp(prefix="l07-full-"))
    plan_path = temp / "plan.json"
    plan_path.write_text(json.dumps(launch_plan))
    argv = ["--launch-plan", str(plan_path), "--out", str(temp / "out.json"),
            "--now", NOW]
    for seq_id, count in (("email_pre_launch", 2), ("email_welcome_access", 2)):
        path = temp / ("%s.json" % seq_id)
        path.write_text(json.dumps(_build_plan(seq_id, count)))
        argv += ["--build-plan", str(path)]
    rc = plan_reader.main(argv)  # exits 4 once any build is blocked; out.json is still written
    assert rc in (0, 4), rc
    return json.loads((temp / "out.json").read_text())


class CompileTests(unittest.TestCase):
    def test_provider_native_conditions_and_settings(self):
        document = synthetic_document()
        campaign = wb.compile_launch_builds(document)
        self.assertEqual(len(campaign), 2)
        pre = next(wf for key, wf in campaign.items() if "pre_launch" in key)
        access = next(wf for key, wf in campaign.items() if "welcome" in key)
        self.assertTrue(pre["promotional"])
        self.assertFalse(access["promotional"])
        # Date-anchored sends now carry an installed wait-until-date step, so
        # the guard assertions apply to the email actions, not to every node.
        for step in pre["templates"]:
            if step.get("type") != "email":
                continue
            ids = {condition["id"] for condition in step["attributes"]["conditions"]}
            self.assertIn(wb.GUARD_UNSUBSCRIBED, ids)
            self.assertIn(wb.GUARD_PURCHASE, ids)
            self.assertIn(wb.GUARD_CLOSE, ids)
            self.assertTrue(step["attributes"]["marketing"])
        for step in access["templates"]:
            if step.get("type") != "email":
                continue
            ids = {condition["id"] for condition in step["attributes"]["conditions"]}
            self.assertIn(wb.GUARD_UNSUBSCRIBED, ids)
            self.assertNotIn(wb.GUARD_PURCHASE, ids,
                             "a purchase must never cancel entitled access")
        self.assertEqual(pre["settings"]["senderProfileRef"], "sender-config:default")
        self.assertTrue(pre["settings"]["marketing"])
        self.assertFalse(access["settings"]["marketing"])
        self.assertTrue(pre["settings"]["suppression"]["stopOnUnsubscribe"])
        self.assertTrue(pre["settings"]["suppression"]["stopOnVerifiedPurchase"])
        self.assertFalse(access["settings"]["suppression"]["stopOnVerifiedPurchase"])
        trigger_fields = {c.get("field") for c in pre["trigger_conditions"]}
        self.assertIn("tagsAdded", trigger_fields)
        self.assertTrue(any(str(field).startswith("enroll_") for field in trigger_fields))

    def test_missing_guards_block_compile(self):
        document = synthetic_document()
        build = next(b for b in document["builds"] if b["id"] == "auto_pre_launch")
        stripped = dict(build)
        stripped["lifecycle"] = {}
        result = wb.compile_launch_builds({"draft_only": True, "builds": [stripped]})
        self.assertEqual(dict(result), {})
        self.assertEqual([r["code"] for r in result.refusals], ["MISSING-GUARDS"])

    def test_build_plan_without_lifecycle_is_blocked_by_the_reader_and_refused_here(self):
        # Issue 26: the reader no longer injects a lifecycle. A build plan that carries
        # none yields a blocked build, and compile_launch_builds(require_ready=True)
        # refuses it instead of compiling guards the reader invented.
        temp = Path(tempfile.mkdtemp(prefix="l07-nolife-"))
        plan = {
            "schema_version": "1.0.0", "launch_id": "l07-nolife", "a2p_ready": False,
            "conversation_ai": {"requested": False, "mode": "none"},
            "offer": {"name": "Synthetic", "price_usd": 1, "currency": "USD",
                      "payment_plans": False},
            "launch_calendar": dict(CALENDAR),
            "pages": [{"id": "page_landing", "kind": "landing",
                       "url": "https://example.test", "waits_for": []}],
            "email_sequences": [{"id": "email_pre_launch", "kind": "pre_launch",
                                 "provider": "skill50", "email_count": 2,
                                 "draft_only": True, "waits_for": []}],
            "text_sets": [],
            "automations": [{"id": "auto_pre_launch", "family": "pre_launch",
                             "template": "launch-a/launch-a-prelaunch-window",
                             "build_rail": "skill44_engine", "draft_only": True,
                             "trigger": {"type": "tag_added"},
                             "waits_for": ["email_pre_launch"]}],
        }
        bare = _build_plan("email_pre_launch", 2)
        for key in ("lifecycle", "enrollment_conditions", "sender_config_refs"):
            del bare["_meta"][key]
        (temp / "plan.json").write_text(json.dumps(plan))
        (temp / "bare.json").write_text(json.dumps(bare))
        rc = plan_reader.main(["--launch-plan", str(temp / "plan.json"), "--out",
                               str(temp / "out.json"), "--build-plan", str(temp / "bare.json"),
                               "--now", NOW])
        self.assertEqual(rc, 4)
        document = json.loads((temp / "out.json").read_text())
        build = document["builds"][0]
        self.assertEqual(build["state"], "blocked")
        self.assertIsNone(build["lifecycle_source"])
        for name in ("lifecycle", "eligibility", "sender"):
            self.assertIn(name, build["blocked_by"])
        result = wb.compile_launch_builds(document, require_ready=True)
        self.assertEqual(dict(result), {})
        self.assertEqual([r["code"] for r in result.refusals], ["BUILD-BLOCKED"])
        self.assertIn("lifecycle", result.refusals[0]["detail"]["blocked_by"])

    def test_lifecycle_the_build_plan_carried_is_stamped_build_plan(self):
        for build in synthetic_document()["builds"]:
            self.assertEqual(build["lifecycle_source"], "build_plan")

    def test_blocked_build_refuses_compile(self):
        document = synthetic_document()
        build = dict(document["builds"][0])
        build["state"] = "blocked"
        build["blocked_by"] = ["email_count:email_pre_launch"]
        result = wb.compile_launch_builds({"draft_only": True, "builds": [build]})
        self.assertEqual(dict(result), {})
        self.assertEqual([r["code"] for r in result.refusals], ["BUILD-BLOCKED"])

    def test_ready_build_with_blocked_by_is_refused_by_both_compile_paths(self):
        # State alone must not clear a build: a "ready" build that still lists a blocker
        # is refused by compile_automation_build and by compile_launch_builds alike.
        build = copy.deepcopy(synthetic_document()["builds"][0])
        build["state"] = "ready"
        build["blocked_by"] = ["lifecycle"]
        with self.assertRaises(wb.WorkflowCompileError) as raised:
            wb.compile_automation_build(build)
        self.assertEqual(raised.exception.code, "BUILD-BLOCKED")
        self.assertEqual(raised.exception.detail["blocked_by"], ["lifecycle"])
        result = wb.compile_launch_builds({"draft_only": True, "builds": [build]})
        self.assertEqual(dict(result), {})
        self.assertEqual([r["code"] for r in result.refusals], ["BUILD-BLOCKED"])
        self.assertEqual(result.refusals[0]["detail"]["blocked_by"], ["lifecycle"])

    def test_compile_settings_marketing_follows_promotional(self):
        kw = dict(sender={}, lifecycle={}, phase=None, close_at=None)
        self.assertIs(wb.compile_settings(promotional=True, **kw)["marketing"], True)
        self.assertIs(wb.compile_settings(promotional=False, **kw)["marketing"], False)

    def test_full_launch_plan_refuses_per_build_instead_of_raising(self):
        document = full_launch_document()
        result = wb.compile_launch_builds(document)  # must not raise
        refused = {r["id"]: r for r in result.refusals}
        compiled_units = {wf.get("source_unit") for wf in result.values()}
        for build in document["builds"]:
            # no build vanishes: it is either refused or compiled
            self.assertTrue(build["id"] in refused or build["id"] in compiled_units,
                            build["id"])
            if build["state"] == "ready" and not build["workflows"]:
                self.assertEqual(refused[build["id"]]["code"], wb.NO_BUILDABLE_WORKFLOW)
                self.assertEqual(refused[build["id"]]["reason"], wb.NO_BUILDABLE_WORKFLOW)
            if "no_buildable_workflow" in (build.get("blocked_by") or []):
                self.assertEqual(refused[build["id"]]["code"], "BUILD-BLOCKED")
        for build_id in ("auto_pre_launch", "auto_post_sale"):
            self.assertNotIn(build_id, refused)
            self.assertIn(build_id, compiled_units)
        self.assertTrue(result.refusals)
        for refusal in result.refusals:
            self.assertEqual(refusal["state"], "blocked")

    def test_ready_build_with_zero_workflows_is_refused_blocked(self):
        builds = synthetic_document()["builds"]
        intact = next(b for b in builds if b["id"] == "auto_post_sale")
        stripped = copy.deepcopy(next(b for b in builds if b["id"] == "auto_pre_launch"))
        stripped.update(workflows=[], state="ready", blocked_by=[])
        result = wb.compile_launch_builds(
            {"draft_only": True, "builds": [stripped, copy.deepcopy(intact)]})
        self.assertEqual(len(result.refusals), 1)
        refusal = result.refusals[0]
        self.assertEqual(refusal["id"], "auto_pre_launch")
        self.assertEqual(refusal["code"], wb.NO_BUILDABLE_WORKFLOW)
        self.assertEqual(refusal["reason"], wb.NO_BUILDABLE_WORKFLOW)
        self.assertEqual(refusal["state"], "blocked")
        self.assertTrue(result)  # the intact build still compiled
        self.assertEqual({wf.get("source_unit") for wf in result.values()},
                         {"auto_post_sale"})

    def test_refusals_surface_as_build_errors(self):
        campaign = wb.compile_launch_builds(full_launch_document())
        client = FakeClient()
        stats = wb.CampaignBuilder(client).build(campaign, folder_name="Synthetic")
        self.assertTrue(any(wb.NO_BUILDABLE_WORKFLOW in e for e in stats["errors"]),
                        stats["errors"])

    def test_declared_dependency_must_exist(self):
        campaign = {
            "a": {"name": "A", "templates": [wb.email_step("E", "s", "b")],
                  "unit_key": "u/a", "depends_on": ["missing"], "requires": []},
        }
        errors = wb._contract_errors(campaign)
        self.assertTrue(any("unknown workflow" in error for error in errors), errors)

    def test_approved_send_date_reaches_saved_templates(self):
        def with_open(open_at, launch_at):
            document = synthetic_document()
            plan = {
                "schema_version": "1.0.0",
                "launch_id": "l07-build",
                "a2p_ready": False,
                "conversation_ai": {"requested": False, "mode": "none"},
                "offer": {"name": "Synthetic", "price_usd": 1,
                          "currency": "USD", "payment_plans": False},
                "launch_calendar": {
                    "launch_at": launch_at,
                    "doors_open_at": open_at,
                    "doors_close_at": "2026-11-10T23:59:00-05:00",
                    "timezone": "America/New_York",
                },
                "pages": [{"id": "page_landing", "kind": "landing",
                           "url": "https://example.test", "waits_for": []}],
                "email_sequences": [
                    {"id": "email_pre_launch", "kind": "pre_launch",
                     "provider": "skill50", "email_count": 2,
                     "draft_only": True, "waits_for": []},
                ],
                "text_sets": [],
                "automations": [
                    {"id": "auto_pre_launch", "family": "pre_launch",
                     "template": "launch-a/launch-a-prelaunch-window", "build_rail": "skill44_engine",
                     "draft_only": True, "trigger": {"type": "tag_added"},
                     "waits_for": ["email_pre_launch", "page_landing"]},
                ],
            }
            temp = Path(tempfile.mkdtemp(prefix="l07-date-"))
            plan_path = temp / "plan.json"
            plan_path.write_text(json.dumps(plan))
            seq = {"folder": "F",
                   "_meta": {
                       "sequence_id": "email_pre_launch",
                       # what a Skill 50 build plan carries; the reader supplies none of it
                       "enrollment_conditions": copy.deepcopy(plan_reader.DEFAULT_ENROLLMENT_CONDITIONS),
                       "lifecycle": copy.deepcopy(plan_reader.DEFAULT_LIFECYCLE),
                       "sender_config_refs": copy.deepcopy(plan_reader.DEFAULT_SENDER)},
                   "email_pre_launch": {
                       "name": "pre", "status": "draft",
                       "templates": [
                           {"id": "e0", "type": "email", "name": "E0",
                            "attributes": {"subject": "s", "body": "<p>b</p>",
                                           "html": "<p>b</p>",
                                           "fromName": "n"}},
                           {"id": "w0", "type": "wait", "name": "Wait",
                            "attributes": {"type": "time", "startAfter": {
                                "type": "days", "value": 1, "when": "after"}}},
                           {"id": "e1", "type": "email", "name": "E1",
                            "attributes": {"subject": "s", "body": "<p>b</p>",
                                           "html": "<p>b</p>",
                                           "fromName": "n"}},
                       ]}}
            seq_path = temp / "pre.json"
            seq_path.write_text(json.dumps(seq))
            out = temp / "out.json"
            rc = plan_reader.main([
                "--launch-plan", str(plan_path),
                "--build-plan", str(seq_path),
                "--out", str(out), "--now", NOW])
            self.assertEqual(rc, 0)
            return wb.compile_launch_builds(
                json.loads(out.read_text()))

        early = with_open("2026-11-03T09:00:00-05:00",
                          "2026-11-03T12:00:00-05:00")
        late = with_open("2026-11-05T09:00:00-05:00",
                         "2026-11-05T12:00:00-05:00")
        key_early = next(k for k in early if "pre_launch" in k)
        key_late = next(k for k in late if "pre_launch" in k)
        sched = {t["id"]: t["attributes"].get("schedule")
                 for t in early[key_early]["templates"]
                 if t.get("type") == "email"}
        self.assertTrue(all(sched.values()),
                        "every saved email template carries its compiled send date")
        self.assertNotEqual(
            [t["attributes"]["schedule"]["at"]
             for t in early[key_early]["templates"]
             if t.get("type") == "email"],
            [t["attributes"]["schedule"]["at"]
             for t in late[key_late]["templates"]
             if t.get("type") == "email"],
            "an approved send-date shift must move the saved workflow")


class JournalBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="l07-journal-"))
        self._old_data = os.environ.get("CAF_DATA_DIR")
        self._old_draft = os.environ.get("CAF_DRAFT_ONLY")
        os.environ["CAF_DATA_DIR"] = str(self.temp / "data")
        os.environ["CAF_DRAFT_ONLY"] = "true"
        self.document = synthetic_document()
        self.campaign = wb.compile_launch_builds(self.document)
        self.journal_path = self.temp / "journal.jsonl"
        self.journal = wb.BuildJournal(self.journal_path)

    def tearDown(self):
        if self._old_data is None:
            os.environ.pop("CAF_DATA_DIR", None)
        else:
            os.environ["CAF_DATA_DIR"] = self._old_data
        if self._old_draft is None:
            os.environ.pop("CAF_DRAFT_ONLY", None)
        else:
            os.environ["CAF_DRAFT_ONLY"] = self._old_draft

    def test_build_journals_hashes_and_readback(self):
        client = FakeClient()
        builder = wb.CampaignBuilder(client)
        stats = builder.build(self.campaign, folder_name="Synthetic", journal=self.journal)
        self.assertEqual(stats["errors"], [], stats["errors"])
        self.assertEqual(stats["workflows_created"], 2)
        self.assertTrue(all(item["ok"] for item in stats["readback"].values()))
        entries = self.journal.entries()
        phases = {entry["phase"] for entry in entries}
        self.assertTrue({"create", "save", "readback"} <= phases, phases)
        for entry in entries:
            self.assertTrue(entry.get("unit_key"))
            if entry["phase"] == "readback" and entry["status"] == "ok":
                self.assertEqual(len(entry["expected_hash"]), 64)
                self.assertEqual(entry["expected_hash"], entry["readback_hash"])
        self.assertTrue(stats["workflow_ids"])

    def test_resume_adopts_saved_graph_and_creates_nothing(self):
        client = FakeClient()
        wb.CampaignBuilder(client).build(self.campaign, folder_name="Synthetic",
                                         journal=self.journal)
        creates_before = len([c for c in client.calls
                              if c[0] == "POST" and c[1] == "/workflow/%s" % LOC
                              and (c[2] or {}).get("type") != "directory"])
        writer_calls_before = len([c for c in client.calls if c[0] in ("POST", "PUT")])
        second = wb.CampaignBuilder(client).build(
            self.campaign, folder_name="Synthetic", journal=self.journal)
        self.assertEqual(second["errors"], [], second["errors"])
        creates_after = len([c for c in client.calls
                             if c[0] == "POST" and c[1] == "/workflow/%s" % LOC
                             and (c[2] or {}).get("type") != "directory"])
        writer_calls_after = len([c for c in client.calls if c[0] in ("POST", "PUT")])
        self.assertEqual(creates_after, creates_before, "resume created a duplicate workflow")
        self.assertEqual(writer_calls_after, writer_calls_before,
                         "resume overwrote a saved graph")
        self.assertEqual(second["workflows_created"], 0)
        self.assertEqual(second["workflows_reused"], 2)

    def test_human_edit_is_preserved(self):
        client = FakeClient()
        wb.CampaignBuilder(client).build(self.campaign, folder_name="Synthetic",
                                         journal=self.journal)
        for wf in client.workflows.values():
            if wf["templates"]:
                wf["templates"][0]["attributes"]["subject"] = "HUMAN EDIT"
        writer_calls_before = len([c for c in client.calls if c[0] in ("POST", "PUT")])
        second = wb.CampaignBuilder(client).build(
            self.campaign, folder_name="Synthetic", journal=self.journal)
        writer_calls_after = len([c for c in client.calls if c[0] in ("POST", "PUT")])
        self.assertEqual(writer_calls_after, writer_calls_before,
                         "a human edit was overwritten")
        self.assertTrue(any("human edit" in error.lower() for error in second["errors"]),
                        second["errors"])
        self.assertTrue(second["needs_reconcile"] or second["errors"])

    def test_unknown_create_outcome_is_journalled_and_never_duplicated(self):
        client = FakeClient()
        client.create_without_response = True
        first = wb.CampaignBuilder(client).build(
            self.campaign, folder_name="Synthetic", journal=self.journal)
        self.assertTrue(first["errors"])
        self.assertTrue(first["needs_reconcile"])
        entries = [e for e in self.journal.entries()
                   if e["phase"] == "create" and e["status"] == "unknown_outcome"]
        self.assertTrue(entries)
        self.assertTrue(all(entry["remote_id"] is None for entry in entries))

        # The provider DID create the workflow; the next run must not duplicate it.
        client.create_without_response = False
        creates_before = len(client.workflows)
        second = wb.CampaignBuilder(client).build(
            self.campaign, folder_name="Synthetic", journal=self.journal)
        self.assertEqual(len(client.workflows), creates_before,
                         "an uncertain create was retried into a duplicate")
        self.assertTrue(second["errors"])

    def test_unreadable_readback_fails_closed(self):
        client = FakeClient()
        original = client.request

        def flaky(method, path, body=None, workflow_name=None):
            if method == "GET" and path.startswith("/workflow/%s/" % LOC):
                client.call_count += 1
                client.calls.append((method, path, None))
                return {"_error": True, "http_code": 503}
            return original(method, path, body, workflow_name)

        client.request = flaky
        stats = wb.CampaignBuilder(client).build(
            self.campaign, folder_name="Synthetic", journal=self.journal)
        self.assertTrue(stats["needs_reconcile"])
        self.assertTrue(any("readback" in error.lower() for error in stats["errors"]),
                        stats["errors"])
        self.assertFalse(any(item.get("ok") for item in stats["readback"].values()))


class EnrollmentTests(unittest.TestCase):
    """F05 / BLD-015: enrolment is applied natively and proven by readback.

    The native control is the TOP-LEVEL boolean ``allowMultiple`` on the
    workflow document (captured read-only on the operator account; see
    evidence/F05-capability.json). ``applied`` comes from the observed value,
    never from the request.
    """

    def _campaign(self, enrollment):
        document = synthetic_document()
        build = next(b for b in document["builds"] if b["id"] == "auto_pre_launch")
        build["settings"] = {"enrollment": enrollment}
        build["allow_enrollment"] = enrollment
        return wb.compile_launch_builds(document)

    def _key(self, campaign):
        return next(k for k in campaign if "pre_launch" in k)

    def _create_call(self, client, campaign, key):
        name = campaign[key]["name"]
        return next(
            c for c in client.calls
            if c[0] == "POST" and c[1] == "/workflow/%s" % LOC
            and (c[2] or {}).get("name") == name)

    def test_successive_is_applied_and_proven_by_readback(self):
        campaign = self._campaign("successive")
        key = self._key(campaign)
        client = FakeClient()
        builder = wb.CampaignBuilder(client)
        stats = builder.build(campaign, folder_name="Synthetic")
        self.assertEqual(stats["errors"], [], stats["errors"])
        record = stats["enrollment"][key]
        self.assertEqual(record["native_field"], "allowMultiple")
        self.assertTrue(record["requested"])
        self.assertIs(record["observed"], True)
        self.assertIs(record["applied"], True)
        self.assertIs(campaign[key]["enrollment"]["applied"], True)
        self.assertIs(self._create_call(client, campaign, key)[2]["allowMultiple"], True)
        summary = builder.format_summary()
        self.assertIn("observed=True", summary)
        self.assertIn("applied=True", summary)

    def test_single_is_applied_as_false(self):
        campaign = self._campaign("single")
        key = self._key(campaign)
        client = FakeClient()
        stats = wb.CampaignBuilder(client).build(campaign, folder_name="Synthetic")
        self.assertEqual(stats["errors"], [], stats["errors"])
        self.assertIs(stats["enrollment"][key]["requested"], False)
        self.assertIs(stats["enrollment"][key]["observed"], False)
        self.assertIs(stats["enrollment"][key]["applied"], True)
        self.assertIs(self._create_call(client, campaign, key)[2]["allowMultiple"], False)

    def test_unreported_readback_is_never_reported_applied(self):
        campaign = self._campaign("successive")
        key = self._key(campaign)
        client = FakeClient()
        client.drop_allow_multiple = True  # provider ignored the field
        stats = wb.CampaignBuilder(client).build(campaign, folder_name="Synthetic")
        record = stats["enrollment"][key]
        self.assertIsNone(record["observed"])
        self.assertIs(record["applied"], False)
        self.assertIs(campaign[key]["enrollment"]["applied"], False)
        self.assertTrue(any("NOT proven applied" in e for e in stats["errors"]),
                        stats["errors"])

    def test_undeclared_enrollment_sends_no_native_field(self):
        campaign = wb.compile_launch_builds(synthetic_document())
        key = self._key(campaign)
        self.assertIsNone(campaign[key]["allow_multiple"])
        client = FakeClient()
        stats = wb.CampaignBuilder(client).build(campaign, folder_name="Synthetic")
        self.assertEqual(stats["errors"], [], stats["errors"])
        self.assertNotIn("enrollment", stats)
        creates = [c for c in client.calls
                   if c[0] == "POST" and c[1] == "/workflow/%s" % LOC
                   and (c[2] or {}).get("type") != "directory"]
        self.assertTrue(creates)
        self.assertTrue(all("allowMultiple" not in (c[2] or {}) for c in creates))


if __name__ == "__main__":
    unittest.main(verbosity=2)

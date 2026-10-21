"""L03 authority checks: unit expansion, result envelope, durable progress.

Run: python3 shared-utils/signature_launch/scheduler/test_model.py
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCH = HERE.parent
ROOT = HERE.parents[2]
SHARED = ROOT / "shared-utils"
CONTRACT = ROOT / "shared-utils" / "signature_launch_contract"
CONTRACT_FIXTURES = CONTRACT / "fixtures"
LOCAL = HERE / "fixtures"
PROGRESS_FILE = LAUNCH / "progress.py"

for path in (str(HERE), str(LAUNCH), str(SHARED)):
    if path not in sys.path:
        sys.path.insert(0, path)

import model  # noqa: E402
import progress  # noqa: E402
import scheduler  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_package():
    """package.py uses a relative import; import it as its real package."""
    import signature_launch.package as package
    return package


def local(name):
    return json.loads((LOCAL / name).read_text(encoding="utf-8"))


def contract(name):
    return json.loads((CONTRACT_FIXTURES / name).read_text(encoding="utf-8"))


def fixture_progress(name):
    return json.loads((LOCAL / "progress" / name).read_text(encoding="utf-8"))


class ExpansionTests(unittest.TestCase):
    def test_scheduler_and_progress_expand_the_same_units(self):
        plans = [contract(p.name) for p in sorted(CONTRACT_FIXTURES.glob("*.json"))]
        plans += [local("plan_ai_on.json"), local("plan_ai_off.json"),
                  local("plan_stall.json"), local("plan_empty.json")]
        for plan in plans:
            index = scheduler.unit_index(plan)
            launch_id, units = progress.units_from_plan(plan)
            self.assertEqual(launch_id, plan["launch_id"])
            self.assertEqual([u["id"] for u in units], list(index))
            for unit in units:
                self.assertEqual(unit["kind"], index[unit["id"]]["kind"])
                self.assertEqual(unit["waits_for"], index[unit["id"]]["waits_for"])

    def test_duplicate_and_dangling_ids_fail_closed(self):
        plan = local("plan_ai_off.json")
        plan["pages"].append({"id": "page_landing", "kind": "other", "url": None,
                              "waits_for": []})
        with self.assertRaises(model.ExpansionError):
            model.expand_plan(plan)

        plan = local("plan_ai_off.json")
        plan["email_sequences"][0]["waits_for"] = ["does_not_exist"]
        with self.assertRaises(model.ExpansionError):
            model.expand_plan(plan)

    def test_requested_ai_configuration_is_not_reply_wiring(self):
        on = model.expand_plan(local("plan_ai_on.json"))["ai"]
        self.assertTrue(on["requested_config"]["requested"])
        self.assertEqual(on["requested_config"]["mode"], "faq")
        self.assertEqual(on["reply_wiring"]["units"], ["auto_ai_reply"])
        self.assertTrue(on["consistent"])

        off = model.expand_plan(local("plan_ai_off.json"))["ai"]
        self.assertFalse(off["requested_config"]["requested"])
        self.assertFalse(off["reply_wiring"]["wired"])

        plan = local("plan_ai_off.json")
        plan["conversation_ai"] = {"requested": True, "mode": "none"}
        bad = model.expand_plan(plan)["ai"]
        self.assertFalse(bad["consistent"])
        self.assertIn("conversation_ai requested with no mode", bad["problems"])

    def test_empty_plan_is_explicitly_empty(self):
        expanded = model.expand_plan(local("plan_empty.json"))
        self.assertTrue(expanded["empty"])
        self.assertEqual(expanded["units"], [])
        self.assertEqual(expanded["order"], [])


class EnvelopeTests(unittest.TestCase):
    def test_statuses_and_aliases(self):
        self.assertEqual(model.canonical_status("done"), model.VERIFIED_SUCCESS)
        self.assertEqual(model.canonical_status("FAILED"), model.FAILED)
        self.assertEqual(model.canonical_status("awaiting fact"), model.AWAITING_FACTS)
        self.assertEqual(model.canonical_status("dropped"), model.DROPPED)
        self.assertIsNone(model.canonical_status("banana"))

        unknown = model.normalize_result({"status": "banana"})
        self.assertEqual(unknown["status"], model.FAILED)
        self.assertIn("unknown result status", unknown["detail"])

    def test_verified_success_cannot_be_claimed_unverified(self):
        result = model.envelope(model.VERIFIED_SUCCESS, verified=False)
        self.assertEqual(result["status"], model.FAILED)
        self.assertFalse(model.satisfies_dependency(result))

    def test_only_success_and_drop_satisfy_a_dependency(self):
        success = model.envelope(model.VERIFIED_SUCCESS)
        self.assertTrue(model.satisfies_dependency(success))
        self.assertTrue(model.satisfies_dependency({"status": "dropped"}))
        for status in (model.FAILED, model.BLOCKED, model.AWAITING_FACTS):
            self.assertFalse(model.satisfies_dependency({"status": status}), status)
        self.assertFalse(model.satisfies_dependency({"ok": False, "error": "no"}))
        self.assertFalse(model.satisfies_dependency({"status": "verified_success",
                                                     "verified": False}))
        self.assertTrue(model.satisfies_dependency("plain legacy return"))

    def test_awaiting_facts_carries_the_missing_facts(self):
        result = model.normalize_result({
            "status": "awaiting_facts",
            "missing_facts": ["sender_name", "reply_to_email"],
            "detail": "two answers are missing",
        })
        self.assertEqual(result["missing_facts"], ["sender_name", "reply_to_email"])
        self.assertTrue(result["retryable"])
        self.assertFalse(model.satisfies_dependency(result))

    def test_persisted_and_surface_mappings_agree(self):
        for status, state in model.PERSISTED_STATE.items():
            self.assertIn(state, progress.STATES)
            self.assertIn(model.UI_STATE[state], {"queued", "working", "done", "failed", "blocked"})
            self.assertIn(model.PACKAGE_STATUS[status], {"done", "failed", "blocked"})
        self.assertEqual(model.PACKAGE_STATUS[model.AWAITING_FACTS], "blocked")
        self.assertEqual(model.PACKAGE_STATUS[model.DROPPED], "done")


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.path = self.dir / "progress.json"
        self.record = progress.new_progress(local("plan_stall.json"))

    def test_claim_requires_a_claimable_unit(self):
        refused = progress.claim(self.record, "page_sales", "owner-a")
        self.assertFalse(refused["claimed"])
        self.assertIn("dependencies unresolved", refused["reason"])

        claimed = progress.claim(self.record, "page_landing", "owner-a")
        self.assertTrue(claimed["claimed"])
        self.assertNotIn("page_landing", progress.ready(self.record))
        self.assertIn("page_landing", progress.ready_to_start(self.record)["running"])
        self.assertFalse(progress.claim(self.record, "page_landing", "owner-b")["claimed"])

    def test_returned_failure_never_unlocks_dependents(self):
        progress.claim(self.record, "page_landing", "owner-a")
        progress.complete(self.record, "page_landing",
                          {"status": "failed", "detail": "synthetic timeout"},
                          owner="owner-a")
        self.assertEqual(self.record["units"]["page_landing"]["state"], "failed")
        self.assertNotIn("page_sales", progress.ready(self.record))
        self.assertIn("page_landing", progress.ready_to_start(self.record)["retry"])

    def test_awaiting_facts_blocks_until_answers_arrive(self):
        progress.claim(self.record, "text_doors", "owner-b")
        progress.complete(self.record, "text_doors", {
            "status": "awaiting_facts",
            "missing_facts": ["sender_name"],
            "detail": "sender name missing"}, owner="owner-b")
        unit = self.record["units"]["text_doors"]
        self.assertEqual(unit["state"], "blocked")
        self.assertEqual(unit["missing_facts"], ["sender_name"])
        self.assertIn("text_doors", progress.ready_to_start(self.record)["awaiting_facts"])
        self.assertFalse(progress.claim(self.record, "text_doors", "owner-c")["claimed"])
        self.assertNotIn("auto_opt_in", progress.ready(self.record))

    def test_expired_lease_can_be_reclaimed_but_not_an_unleased_run(self):
        now = progress._parse_time(progress._now())
        progress.claim(self.record, "page_landing", "owner-a",
                       ttl_seconds=1, now=now)
        later = now + timedelta(seconds=30)
        reclaimed = progress.claim(self.record, "page_landing", "owner-b", now=later)
        self.assertTrue(reclaimed["claimed"])
        self.assertEqual(reclaimed["previous_owner"], "owner-a")

        legacy = progress.new_progress(local("plan_stall.json"))
        legacy["units"]["page_landing"]["state"] = "running"
        legacy["units"]["page_landing"]["owner"] = None
        legacy["units"]["page_landing"]["lease_expires_at"] = None
        refused = progress.claim(legacy, "page_landing", "owner-c")
        self.assertFalse(refused["claimed"])
        self.assertIn("without a lease", refused["reason"])

    def test_concurrent_resume_claims_exactly_one_owner(self):
        plan_path = self.dir / "plan.json"
        plan_path.write_text(json.dumps(local("plan_ai_off.json")), encoding="utf-8")
        file_path = self.dir / "concurrent.json"
        subprocess.run([sys.executable, str(PROGRESS_FILE), "init", "--plan",
                        str(plan_path), "--file", str(file_path)],
                       check=True, capture_output=True, text=True)
        command = [sys.executable, str(PROGRESS_FILE), "claim", "--file", str(file_path),
                   "--unit", "page_landing"]
        first = subprocess.Popen(command + ["--owner", "owner-a"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(command + ["--owner", "owner-b"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out_a, err_a = first.communicate(timeout=30)
        out_b, err_b = second.communicate(timeout=30)
        self.assertEqual((first.returncode, second.returncode), (0, 0), (err_a, err_b))
        decisions = [json.loads(out_a), json.loads(out_b)]
        claimed = [d for d in decisions if d.get("claimed")]
        self.assertEqual(len(claimed), 1, decisions)
        self.assertEqual(progress.load(file_path)["units"]["page_landing"]["state"], "running")

    def test_restart_preserves_paid_success_without_duplicate_generation(self):
        progress.claim(self.record, "page_landing", "owner-a")
        progress.complete(self.record, "page_landing", model.envelope(
            model.VERIFIED_SUCCESS, detail="paid build", artifacts=["artifacts/landing.html"]),
            owner="owner-a")
        self.record["units"]["page_landing"]["charged"] = True
        progress.save(self.record, self.path)
        restored = progress.load(self.path)
        unit = restored["units"]["page_landing"]
        attempts = unit["attempts"]
        self.assertTrue(unit["charged"])
        self.assertEqual(unit["state"], "done")

        def never(_path, _uid):
            raise AssertionError("a done unit must never be re-verified or rebuilt")

        report = progress.recover_report(restored, verify=never)
        self.assertEqual(report["recovered"], [])
        self.assertEqual(restored["units"]["page_landing"]["attempts"], attempts)
        self.assertFalse(progress.claim(restored, "page_landing", "owner-b")["claimed"])

    def test_recovery_requires_non_empty_verified_artifacts(self):
        artifact = self.dir / "artifact.html"
        progress.claim(self.record, "page_landing", "owner-a")
        progress.mark(self.record, "page_landing", "failed", owner="owner-a")
        self.record["units"]["page_landing"]["artifact"] = str(artifact)

        artifact.write_text("", encoding="utf-8")
        report = progress.recover_report(self.record)
        self.assertEqual(report["rejected"][0]["unit"], "page_landing")
        self.assertEqual(self.record["units"]["page_landing"]["state"], "failed")

        artifact.write_text("built bytes", encoding="utf-8")
        def l04_verifier(path, uid):
            # Stand-in for L04's receipt verifier (read-only contract):
            # existing bytes are not proof; a receipt must validate.
            return False, "receipt hash mismatch"

        report = progress.recover_report(self.record, verify=l04_verifier)
        self.assertEqual(report["rejected"][0]["unit"], "page_landing")
        self.assertEqual(self.record["units"]["page_landing"]["state"], "failed")

        report = progress.recover_report(self.record)
        self.assertEqual(report["recovered"], ["page_landing"])
        self.assertEqual(self.record["units"]["page_landing"]["state"], "done")

    def test_live_lease_is_never_recovered(self):
        artifact = self.dir / "live.html"
        artifact.write_text("built", encoding="utf-8")
        self.record["units"]["page_landing"]["state"] = "running"
        self.record["units"]["page_landing"]["owner"] = "owner-a"
        self.record["units"]["page_landing"]["lease_expires_at"] = (
            progress._parse_time(progress._now()) + timedelta(hours=1)).isoformat()
        self.record["units"]["page_landing"]["artifact"] = str(artifact)
        report = progress.recover_report(self.record)
        self.assertEqual(report["skipped"][0]["unit"], "page_landing")
        self.assertEqual(self.record["units"]["page_landing"]["state"], "running")

    def test_stall_persists_partial_results_and_causal_blockers(self):
        progress.claim(self.record, "page_landing", "owner-a")
        progress.complete(self.record, "page_landing",
                          {"status": "failed", "detail": "synthetic timeout"},
                          owner="owner-a")
        progress.save(self.record, self.path)
        restored = progress.load(self.path)
        self.assertEqual(restored["units"]["page_landing"]["state"], "failed")
        self.assertIn("page_sales", restored["stall"])
        self.assertIn("page_landing", restored["stall"]["page_sales"][0]["detail"])
        self.assertEqual(restored["counts"]["retryable"], 1)
        self.assertEqual(restored["percent"], 0.0)

    def test_empty_progress_is_explicitly_empty(self):
        record = progress.new_progress(local("plan_empty.json"))
        self.assertEqual(record["units"], {})
        progress.save(record, self.path)
        restored = progress.load(self.path)
        self.assertTrue(restored["empty"])
        self.assertEqual(restored["counts"]["empty"], 1)
        self.assertEqual(restored["percent"], 0.0)
        self.assertEqual(progress.ready(restored), [])
        self.assertEqual(progress.ready_to_start(restored)["ready"], [])

    def test_wrong_owner_cannot_complete_or_release(self):
        progress.claim(self.record, "page_landing", "owner-a")
        with self.assertRaises(progress.ProgressError):
            progress.complete(self.record, "page_landing", {"status": "verified_success"},
                              owner="owner-b")
        self.assertFalse(progress.release(self.record, "page_landing", "owner-b")["released"])
        self.assertTrue(progress.release(self.record, "page_landing", "owner-a")["released"])
        self.assertEqual(self.record["units"]["page_landing"]["state"], "pending")


class SurfaceAgreementTests(unittest.TestCase):
    def test_mappings_cover_package_and_ui_vocabularies(self):
        # package.py uses a relative import, so import it as its package.
        package = _load_package()
        # UI module's own state list instead of importing it as a package.
        ui = _load("sl_progress_report",
                   SHARED / "signature_launch" / "experience" / "progress_report.py")
        for state in progress.STATES:
            self.assertIn(model.UI_STATE[state], ("queued", "working", "done", "failed", "blocked"))
        self.assertTrue(set(("done", "failed", "blocked")).issubset(set(ui.FINISHED)))
        self.assertIn("run_units", dir(package))

    def test_package_record_agrees_with_the_envelope_mapping(self):
        package = _load_package()
        plan = local("plan_ai_off.json")
        units = {uid: {} for uid in scheduler.unit_index(plan)}
        clean = package.build_package(
            units, lambda uid, payload: {"status": "verified_success", "verified": True})
        self.assertEqual(clean["status"], "done")
        self.assertEqual(clean["counts"]["total"], len(units))

        def boom(uid, payload):
            if uid == "page_landing":
                raise RuntimeError("synthetic refusal")
            return "ok"

        broken = package.build_package(units, boom)
        self.assertEqual(broken["status"], "failed")
        self.assertEqual(broken["counts"]["total"], len(units))
        self.assertEqual(model.PACKAGE_STATUS[model.FAILED], broken["status"])

    def test_ui_table_agrees_with_persisted_states(self):
        ui = _load("sl_progress_report_ui",
                   SHARED / "signature_launch" / "experience" / "progress_report.py")
        record = progress.new_progress(local("plan_stall.json"))
        rows = [{"page_key": uid, "state": model.UI_STATE[unit["state"]]}
                for uid, unit in record["units"].items()]
        text = ui.table(rows)
        self.assertIn("%d of %d pages finished" % (0, len(rows)), text)
        self.assertIn("queued", text)

    def test_empty_plan_agrees_across_surfaces(self):
        plan = local("plan_empty.json")
        report = scheduler.run_all(plan, lambda uid, entry: uid)
        self.assertTrue(report["empty"] and report["complete"])

        record = progress.new_progress(plan)
        with tempfile.TemporaryDirectory() as tmp:
            progress.save(record, Path(tmp) / "empty.json")
        self.assertEqual(record["percent"], 0.0)
        self.assertEqual(record["counts"]["total"], 0)

        ui = _load("sl_progress_report_empty",
                   SHARED / "signature_launch" / "experience" / "progress_report.py")
        self.assertIn("0 of 0 pages finished", ui.table([]))
        self.assertEqual(model.PACKAGE_STATUS[model.VERIFIED_SUCCESS], "done")

    def test_ai_on_and_off_agree_across_screens(self):
        for name in ("plan_ai_on.json", "plan_ai_off.json"):
            plan = local(name)
            ai = scheduler.ai_state(plan)
            record = progress.new_progress(plan)
            reply_units = [uid for uid, unit in record["units"].items()
                           if uid == "auto_ai_reply"]
            self.assertEqual(bool(reply_units), ai["reply_wiring"]["wired"])
            self.assertEqual(ai["requested_config"]["requested"],
                             plan["conversation_ai"]["requested"])
            waves = scheduler.schedule_waves(plan)
            self.assertEqual(sorted(u for wave in waves for u in wave),
                             sorted(record["units"]))


class ContractConsumptionTests(unittest.TestCase):
    """Read L01/L02/L04 contracts read-only; never edit them."""

    def test_l02_planner_output_drives_this_lane(self):
        scripts = ROOT / "49-signature-funnel" / "scripts"
        self.assertTrue((scripts / "launch_plan.py").is_file())
        sys.path.insert(0, str(scripts))
        try:
            launch_plan = _load("l03_l02_launch_plan", scripts / "launch_plan.py")
        finally:
            sys.path.remove(str(scripts))
        launch = {
            "launch_id": "demo-2026-11", "journey_mode": "single_simple",
            "extras": {"upsell_1": False, "downsell_1": False, "upsell_2": False},
            "offers": [{"slot": "main", "display_name": "Demo Offer",
                        "prices": [{"amount_minor": 49700, "currency": "USD",
                                    "approval_status": "approved"}]}],
        }
        answers = {
            "launch.launch_at": "2026-11-03T12:00:00-05:00",
            "launch.doors_open_at": "2026-11-03T09:00:00-05:00",
            "launch.doors_close_at": "2026-11-10T23:59:00-05:00",
            "launch.timezone": "America/New_York",
            "launch.channels": ["email"], "launch.a2p_ready": False,
            "launch.conversation_ai": True, "launch.conversation_ai_mode": "faq",
            "launch.sender_name": "Synthetic Sender",
            "launch.reply_to_email": "reply@example.invalid",
            "launch.access_delivery": True, "launch.payment_plans": False,
            "launch.landing_url": "https://example.invalid/landing",
            "launch.sales_page_url": "https://example.invalid/sales",
            "launch.checkout_url": "https://example.invalid/order",
            "launch.thank_you_url": "https://example.invalid/thanks",
        }
        built = launch_plan.build_launch_plan(launch, answers)
        self.assertEqual(built["state"], "ready", built.get("missing"))
        plan = built["plan"]
        scheduler.validate_plan(plan)
        ai = scheduler.ai_state(plan)
        self.assertTrue(ai["requested_config"]["requested"])
        self.assertIn("auto_ai_reply", ai["reply_wiring"]["units"])
        self.assertIn("auto_ai_reply", scheduler.unit_index(plan))
        launch_id, units = progress.units_from_plan(plan)
        self.assertEqual(launch_id, plan["launch_id"])
        self.assertEqual(sorted(u["id"] for u in units), sorted(scheduler.unit_index(plan)))
        report = scheduler.run_all(
            plan, lambda uid, entry: {"status": "verified_success", "verified": True})
        self.assertTrue(report["complete"])
        self.assertIn("auto_ai_reply", report["completed"])

    def test_l01_session_contract_is_consumed_read_only(self):
        contract_path = LAUNCH / "session_contract.json"
        if not contract_path.is_file():
            self.skipTest("L01 session contract not merged into this branch yet")
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        answers = {entry["id"]: entry for entry in contract["launch_answers"]}
        self.assertIn("conversation_ai", answers)
        self.assertIn("unknown", contract["states"])
        self.assertIn("recommended_unapproved", contract["states"])
        on = model.expand_plan(local("plan_ai_on.json"))["ai"]
        off = model.expand_plan(local("plan_ai_off.json"))["ai"]
        # The L01 rule: requested true requires a real mode; a default is not approval.
        self.assertTrue(on["consistent"] and on["requested_config"]["requested"])
        self.assertTrue(off["consistent"] and not off["requested_config"]["requested"])
        self.assertTrue(answers["conversation_ai"]["never_default"] is False)

    def test_l04_receipt_contract_is_consumed_read_only(self):
        receipt = ROOT / "83-black-friday-launcher" / "receipt.schema.json"
        if not receipt.is_file():
            self.skipTest("L04 receipt schema not merged into this branch yet")
        schema = json.loads(receipt.read_text(encoding="utf-8"))
        proof = schema["definitions"]["unit_receipt"]["properties"]["proof"]
        self.assertEqual(set(proof["required"]),
                         {"authored", "draft_installed", "tested", "live_verified"})
        self.assertEqual(schema["definitions"]["unit_receipt"]["properties"]["status"]
                         ["enum"], ["authored", "draft_delivered", "locally_verified",
                                    "installed_test_verified", "ready_for_activation",
                                    "live_verified"])
        # Our envelope never claims live verification from a synthetic local run.
        result = model.envelope(model.VERIFIED_SUCCESS, detail="synthetic local")
        self.assertFalse(any(key == "live_verified" for key in result))


class ProducerFixtureTests(unittest.TestCase):
    def test_progress_fixtures_are_actual_producer_output(self):
        generator = _load("l03_fixture_generator", HERE / "make_progress_fixtures.py")
        for name, builder in sorted(generator.BUILDERS.items()):
            path = LOCAL / "progress" / name
            self.assertTrue(path.is_file(), name)
            expected = generator.render(name, builder)
            self.assertEqual(path.read_text(encoding="utf-8"), expected, name)
            record = progress.load(path)
            self.assertTrue(record["launch_id"].startswith("l03-"))
            for uid, unit in record["units"].items():
                self.assertIn("state", unit)
                self.assertIn("waits_for", unit)

    def test_l12_fixture_vocabulary_is_complete(self):
        on = fixture_progress("progress-ai-on.json")
        self.assertEqual(on["counts"]["running"], 1)
        self.assertIn("verified_success",
                      {u["result"]["status"] for u in on["units"].values()
                       if u.get("result")})
        stalled = fixture_progress("progress-stalled.json")
        self.assertTrue(stalled["stall"])
        self.assertEqual(stalled["counts"]["awaiting_facts"], 1)
        empty = fixture_progress("progress-empty.json")
        self.assertTrue(empty["empty"])
        self.assertEqual(empty["percent"], 0.0)


if __name__ == "__main__":
    unittest.main()

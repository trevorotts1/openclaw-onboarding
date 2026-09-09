#!/usr/bin/env python3
"""PRES-006 — the box-side mirror may not drift, and the configuration_pending
lifecycle behaves as the TODO specifies.

Run: python3 -m pytest test/test_pres006_canonical_paths.py -q
   (or: python3 test/test_pres006_canonical_paths.py)

Part 1 — MIRROR PINNING. bridge/intake_writer.py carries a stdlib-only mirror
of the canonical field-path contract (the JS source of truth is
schema/intake_fields.js; schema/intake_fields.json is the GENERATED JSON
projection the Python side can read). This file fails the build if the mirror
stops matching the projection — canonical paths, the REQUIRED set, the legacy
aliases and the booleanish normalization.

Part 2 — MISSING vs ANSWERED-NO. A "no"/"false" answer is a REAL answer and
never counts as missing; only absent/None/blank does.

Part 3 — MIGRATION. Move / redundant-fold / contradiction-refusal /
newer-version refusal.

Part 4 — configuration_pending (the optional resource-plan tier): omitted tier
stays pending (never declined, never answered, never locked), already
configured independent routes proceed, the event carries the missing field +
provider + scoped resume link + next action, and the events file is
append-only (later answers ADD records; nothing is overwritten — exactly
"unblocks once, without an ask-once lock or an other-provider overwrite").
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "bridge"))

import intake_writer as iw  # noqa: E402

CONTRACT_JSON = APP / "schema" / "intake_fields.json"


def _complete_answers() -> dict:
    return {
        "presentation_type": "from_scratch",
        "offer_name": "The Momentum Method",
        "named_methodology": "The Three-Move Pipeline",
        "transformation_promise": "stuck -> closing",
        "time_to_result": "8 weeks",
        "audience": "women entrepreneurs, 35-55",
        "cta_action": "book a call",
        "tone": "Inspirational",
        "final_price": "$497",
        "speech_speed_preference": "default",
        "want_sales_checkout": "yes",
        "want_vsl_page": "no",
        "client_notes": "",
    }


# ===========================================================================
# Part 1 — the mirror is pinned to the generated contract projection
# ===========================================================================

class TestMirrorMatchesTheGeneratedContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))

    def test_projection_exists_and_is_current(self):
        # gen_ui_questions.mjs --check is the JS-side drift gate; here we only
        # assert the projection itself is present and version-consistent.
        self.assertEqual(self.contract["version"], iw.INTAKE_CONTRACT_VERSION)

    def test_every_canonical_path_matches_the_contract(self):
        contract_paths = {f["id"]: f["canonical_path"] for f in self.contract["fields"]}
        self.assertEqual(iw.CANONICAL_FIELD_PATHS, contract_paths)

    def test_the_required_set_matches_the_contract(self):
        self.assertEqual(
            sorted(iw.REQUIRED_CANONICAL_FIELDS),
            sorted(self.contract["required_fields"]))

    def test_legacy_aliases_match_the_contract(self):
        for f in self.contract["fields"]:
            aliases = f.get("legacy_aliases") or []
            if f["id"] in iw.LEGACY_ALIASES:
                self.assertEqual(
                    list(iw.LEGACY_ALIASES[f["id"]]), aliases,
                    f"LEGACY_ALIASES[{f['id']!r}] drifted from the contract")
            else:
                self.assertEqual(aliases, [],
                                 f"contract declares aliases for {f['id']!r} "
                                 "the Python mirror does not migrate")

    def test_booleanish_normalization_matches_the_contract(self):
        self.assertEqual(
            iw._LEGACY_BOOLEAN_NORMALIZATION,
            self.contract["migration"]["boolean_normalization"])

    def test_no_independent_required_copies_exist_in_the_workers(self):
        # The Workers import schema/intake_contract.js — the hand-copied
        # REQUIRED_BRIEF_FIELDS arrays are gone from both src/index.js files.
        for worker in ("worker/src/index.js", "deployed-r2/src/index.js"):
            src = (APP / worker).read_text(encoding="utf-8")
            self.assertNotIn("const REQUIRED_BRIEF_FIELDS", src, worker)
            self.assertIn("../schema/intake_contract.js", src.replace("\\", "/"), worker)


# ===========================================================================
# Part 2 — false/no distinguished from missing
# ===========================================================================

class TestFalseVersusMissing(unittest.TestCase):
    def _intake(self) -> dict:
        intake = iw.assemble_intake({"answers": dict(_complete_answers())}, run_id="P6")
        # Mirror the real write path: the writers migrate BEFORE the gate
        # (assemble_intake's answers-routing is legacy-shaped and migration
        # moves presentation_type to its canonical home).
        iw.migrate_intake(intake)
        return intake

    def test_a_no_answer_satisfies_the_gate(self):
        intake = self._intake()
        intake["pre_presentation_capture"]["WANT_SALES_CHECKOUT"] = "no"
        intake["pre_presentation_capture"]["SALES_CHECKOUT_DECLINED_REASON"] = "we only need the deck"
        intake["pre_presentation_capture"]["WANT_VSL_PAGE"] = False  # booleanish no
        self.assertEqual(iw.validate_intake_completeness(intake), [])

    def test_absent_and_blank_are_missing_and_named(self):
        intake = self._intake()
        del intake["deck_brief"]["OFFER_NAME"]
        intake["pre_presentation_capture"]["WANT_VSL_PAGE"] = ""
        missing = iw.validate_intake_completeness(intake)
        self.assertIn("deck_brief.OFFER_NAME", missing)
        self.assertIn("pre_presentation_capture.WANT_VSL_PAGE", missing)
        self.assertNotIn("pre_presentation_capture.WANT_SALES_CHECKOUT", missing)

    def test_validate_and_migrate_raises_naming_the_missing(self):
        intake = {"schema_version": 2, "deck_brief": {}, "pre_presentation_capture": {}}
        with self.assertRaises(iw.IntakeIncompleteError) as ctx:
            iw.validate_and_migrate(intake)
        msg = str(ctx.exception)
        self.assertIn("missing", msg)
        self.assertIn("pre_presentation_capture.WANT_SALES_CHECKOUT", msg)


# ===========================================================================
# Part 3 — version-aware legacy migration
# ===========================================================================

class TestMigration(unittest.TestCase):
    def test_legacy_deck_brief_flags_move_home(self):
        intake = {
            "deck_brief": {"WANT_SALES_CHECKOUT": "yes", "WANT_VSL_PAGE": "no",
                           "PRESENTATION_TYPE": "from_scratch",
                           "OFFER_NAME": "X", "NAMED_METHODOLOGY": "M",
                           "TRANSFORMATION_PROMISE": "T", "TIME_TO_RESULT": "8w",
                           "AUDIENCE": "A", "CTA_ACTION": "C", "TONE": "Tone",
                           "FINAL_PRICE": "$1"},
            "pre_presentation_capture": {},
            "intake": {"speech_speed_preference": "default"},
            "answers": {},
        }
        iw.migrate_intake(intake)
        self.assertEqual(intake["pre_presentation_capture"]["WANT_SALES_CHECKOUT"], "yes")
        self.assertEqual(intake["pre_presentation_capture"]["WANT_VSL_PAGE"], "no")
        self.assertEqual(intake["pre_presentation_capture"]["PRESENTATION_TYPE"], "from_scratch")
        self.assertNotIn("WANT_SALES_CHECKOUT", intake["deck_brief"])
        self.assertEqual(intake["schema_version"], iw.INTAKE_CONTRACT_VERSION)

    def test_booleanish_true_normalizes_to_yes(self):
        intake = {"deck_brief": {"WANT_SALES_CHECKOUT": True}, "pre_presentation_capture": {}}
        iw.migrate_intake(intake)
        self.assertEqual(intake["pre_presentation_capture"]["WANT_SALES_CHECKOUT"], "yes")

    def test_contradiction_refuses_naming_both_values(self):
        intake = {"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes"},
                  "deck_brief": {"WANT_SALES_CHECKOUT": "no"}}
        with self.assertRaises(iw.ContractMigrationError) as ctx:
            iw.migrate_intake(intake)
        msg = str(ctx.exception)
        self.assertIn("migration refused", msg)
        self.assertIn("WANT_SALES_CHECKOUT", msg)
        self.assertIn("'yes'", msg)
        self.assertIn("'no'", msg)

    def test_newer_version_refuses_to_downgrade(self):
        with self.assertRaises(iw.ContractMigrationError) as ctx:
            iw.migrate_intake({"schema_version": 99})
        self.assertIn("newer", str(ctx.exception))

    def test_current_version_passes_through(self):
        intake = {"schema_version": iw.INTAKE_CONTRACT_VERSION, "deck_brief": {}}
        out = iw.migrate_intake(intake)
        self.assertIs(out, intake)


# ===========================================================================
# Part 4 — configuration_pending (the optional tier)
# ===========================================================================

class TestConfigurationPending(unittest.TestCase):
    PENDING = [{"id": "resource_plan", "provider": "kimi"}]

    def test_omitted_tier_is_pending_never_declined_never_answered(self):
        intake = iw.assemble_intake({"answers": dict(_complete_answers())}, run_id="P6")
        intake["pending_providers"] = self.PENDING
        pending = iw.pending_configurations(intake)
        self.assertTrue(pending)
        for rec in pending:
            self.assertEqual(rec["state"], "configuration_pending")
            self.assertNotEqual(rec["state"], "declined")
            self.assertNotEqual(rec["state"], "answered")
        # ...and the omission never wrote a resource-plan answer of any kind.
        self.assertIsNone(iw.read_canonical(intake, "pre_presentation_capture.RESOURCE_PLAN"))

    def test_event_carries_field_provider_resume_link_next_action(self):
        intake = iw.assemble_intake({"answers": dict(_complete_answers())}, run_id="P6")
        intake["pending_providers"] = self.PENDING
        intake["intake_session_id"] = "pres-p6"
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "runs" / "pres-p6"
            events = iw.emit_configuration_pending_events(run_dir, intake, "pres-p6")
            self.assertTrue(events)
            ev = events[0]
            self.assertEqual(ev["event"], "configuration_pending")
            self.assertEqual(ev["missing_field"], "resource_plan")
            self.assertEqual(ev["provider"], "kimi")
            self.assertIn("/s/pres-p6", ev["resume_url"])
            self.assertNotIn("admin", ev["resume_url"].lower())
            self.assertIn("NOT blocked", ev["next_action"])
            on_disk = (run_dir / "working/events/configuration_events.jsonl").read_text(
                encoding="utf-8").strip().splitlines()
            self.assertTrue(on_disk)
            self.assertEqual(json.loads(on_disk[0])["event"], "configuration_pending")

    def test_resume_link_uses_the_configured_base(self):
        with unittest.mock.patch.dict("os.environ",
                                      {"PRESENTATION_INTAKE_BASE_URL": "https://intake.example.com"}):
            self.assertEqual(iw._resume_url("s1"), "https://intake.example.com/s/s1")

    def test_already_configured_routes_proceed_and_stay_untouched(self):
        intake = iw.assemble_intake({"answers": dict(_complete_answers())}, run_id="P6")
        intake["pending_providers"] = self.PENDING
        intake["pre_presentation_capture"]["RUN_MODE"] = "ultra"  # an already-configured axis
        intake["pre_presentation_capture"]["WORKHORSE_MODEL"] = "kimi-k2@kimi"
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "runs" / "pres-p6"
            events = iw.emit_configuration_pending_events(run_dir, intake, "pres-p6")
            # Only the UNSTATED subfields are pending — the configured ones are
            # never "pending", never overwritten, and no other provider's plan
            # is invented.
            fields = {e["field"] for e in events}
            self.assertNotIn("pre_presentation_capture.RUN_MODE", fields)
            self.assertNotIn("pre_presentation_capture.WORKHORSE_MODEL", fields)
            self.assertEqual(intake["pre_presentation_capture"]["RUN_MODE"], "ultra")

    def test_a_later_real_tier_answer_unblocks_exactly_once(self):
        # Same session: first pass emits the pending event; the client then
        # answers the tier for real; a re-emission finds NOTHING left pending —
        # the events file shows pending-then-resolved without any duplicate
        # ask, lock, or default being written.
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "runs" / "pres-p6"
            run_dir.mkdir(parents=True, exist_ok=True)

            intake1 = iw.assemble_intake({"answers": dict(_complete_answers())}, run_id="P6")
            intake1["pending_providers"] = self.PENDING
            events1 = iw.emit_configuration_pending_events(run_dir, intake1, "pres-p6")
            self.assertTrue(events1)

            # The real answer arrives for the SAME provider (no ask-once lock —
            # the answer writes the value; nothing else is staged).
            intake2 = iw.assemble_intake({"answers": dict(_complete_answers())}, run_id="P6")
            intake2["pre_presentation_capture"]["RESOURCE_PLAN"] = "standard"
            events2 = iw.emit_configuration_pending_events(run_dir, intake2, "pres-p6")
            self.assertEqual(events2, [], "a resolved configuration must not re-emit")

            on_disk = [json.loads(line) for line in
                       (run_dir / "working/events/configuration_events.jsonl")
                       .read_text(encoding="utf-8").strip().splitlines()]
            # One event per still-unstated subfield for the owed provider
            # (all six plan subfields were unstated), and NOTHING further
            # after the real answer: pending-then-resolved, emitted once.
            self.assertEqual(len(on_disk),
                             len(iw._RESOURCE_PLAN_CONFIG_FIELDS))
            self.assertTrue(all(e["event"] == "configuration_pending" for e in on_disk))
            self.assertEqual(iw.read_canonical(intake2, "pre_presentation_capture.RESOURCE_PLAN"),
                             "standard")  # ...and the real answer landed, once.

    def test_no_pending_providers_means_nothing_invented(self):
        intake = iw.assemble_intake({"answers": dict(_complete_answers())}, run_id="P6")
        self.assertEqual(iw.pending_configurations(intake), [])


import unittest.mock  # noqa: E402  (used by TestConfigurationPending)

if __name__ == "__main__":
    unittest.main(verbosity=2)

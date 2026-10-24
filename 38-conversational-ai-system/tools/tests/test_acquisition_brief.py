#!/usr/bin/env python3
"""Tests for acquisition_brief.py (T-06, guided discovery).

The suite proves the doctrine, not just the plumbing: known facts are never
asked again, the next-question set is the minimal ordered remainder, an
interrupted interview resumes on the same question, and an unknown fact is
recorded as missing instead of being silently defaulted.

Run from the skill root:
  python3 -m unittest discover -s tools/tests -p 'test_*.py'
or:
  python3 tools/tests/test_acquisition_brief.py
"""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import acquisition_brief as ab  # noqa: E402

FIXED_NOW = datetime.datetime(
    2026, 10, 24, 12, 0, 0, 0, tzinfo=datetime.timezone.utc
)
FIXED_ISO = "2026-10-24T12:00:00.000000+00:00"

REQUIRED_IDS = [spec.fact_id for spec in ab.FACT_SPECS if spec.required]
OPTIONAL_IDS = [spec.fact_id for spec in ab.FACT_SPECS if not spec.required]
ALL_IDS = [spec.fact_id for spec in ab.FACT_SPECS]

SIX_KNOWN = [
    "business.legal_name",
    "business.what_you_do",
    "offers.primary_offer",
    "offers.price_range",
    "audience.primary_audience",
    "audience.audience_pain",
]


def fixed_clock():
    return FIXED_NOW


def new_brief(directory, name="brief.json", clock=fixed_clock):
    return ab.AcquisitionBrief(os.path.join(directory, name), clock=clock)


def answer_all_required(brief):
    for fact_id in REQUIRED_IDS:
        brief.answer(fact_id, "value for " + fact_id)


class ProvenanceTests(unittest.TestCase):
    def test_every_fact_carries_provenance_and_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            client = brief.record_fact(
                "business.legal_name",
                "Acme Ltd",
                provenance=ab.PROVENANCE_CLIENT_STATED,
            )
            discovered = brief.record_fact(
                "channels.owned_channels",
                "Instagram and email",
                provenance=ab.PROVENANCE_DISCOVERED,
                source="public profile audit",
            )
            assumed = brief.record_fact(
                "geography.service_area",
                "Greater Austin",
                provenance=ab.PROVENANCE_ASSUMED,
            )

            self.assertEqual(client.provenance, "client_stated")
            self.assertEqual(discovered.provenance, "discovered")
            self.assertEqual(assumed.provenance, "assumed")
            for fact in (client, discovered, assumed):
                self.assertEqual(fact.recorded_at, FIXED_ISO)
            self.assertEqual(discovered.source, "public profile audit")
            self.assertTrue(client.trusted)
            self.assertFalse(assumed.trusted)

            reloaded = new_brief(directory)
            stored = reloaded.require("business.legal_name")
            self.assertEqual(stored.value, "Acme Ltd")
            self.assertEqual(stored.provenance, "client_stated")
            self.assertEqual(stored.recorded_at, FIXED_ISO)

    def test_invalid_provenance_value_and_fact_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            with self.assertRaises(ab.InvalidFactError):
                brief.record_fact(
                    "business.legal_name", "Acme", provenance="made_up"
                )
            with self.assertRaises(ab.InvalidFactError):
                brief.record_fact(
                    "business.legal_name",
                    "   ",
                    provenance=ab.PROVENANCE_CLIENT_STATED,
                )
            with self.assertRaises(ab.InvalidFactError):
                brief.record_fact(
                    "business.legal_name",
                    42,
                    provenance=ab.PROVENANCE_CLIENT_STATED,
                )
            with self.assertRaises(ab.UnknownFactError):
                brief.record_fact(
                    "business.favourite_colour",
                    "blue",
                    provenance=ab.PROVENANCE_CLIENT_STATED,
                )


class KnownFactReuseTests(unittest.TestCase):
    def test_six_known_facts_are_never_asked_again(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            for fact_id in SIX_KNOWN:
                brief.answer(fact_id, "known " + fact_id)

            questions = brief.next_questions()
            asked_ids = [question.fact_id for question in questions]

            self.assertEqual(len(asked_ids), len(REQUIRED_IDS) - 6)
            self.assertFalse(set(asked_ids) & set(SIX_KNOWN))
            self.assertEqual(set(asked_ids), set(REQUIRED_IDS) - set(SIX_KNOWN))
            self.assertTrue(all(question.required for question in questions))

    def test_known_optional_fact_is_not_asked_even_when_optionals_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.answer("business.differentiator", "Only studio with a kiln")
            questions = brief.next_questions(include_optional=True)
            self.assertNotIn(
                "business.differentiator",
                [question.fact_id for question in questions],
            )


class MissingFactOnlySelectionTests(unittest.TestCase):
    def test_question_set_is_ordered_and_minimal(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            questions = brief.next_questions()

            self.assertEqual(len(questions), len(REQUIRED_IDS))
            priorities = [question.priority for question in questions]
            self.assertEqual(priorities, sorted(priorities))
            self.assertEqual(
                {question.fact_id for question in questions}, set(REQUIRED_IDS)
            )
            self.assertFalse(
                {question.fact_id for question in questions} & set(OPTIONAL_IDS)
            )

    def test_selection_stops_when_brief_is_sufficient(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            self.assertFalse(brief.is_sufficient())
            answer_all_required(brief)

            self.assertTrue(brief.is_sufficient())
            self.assertEqual(brief.next_questions(), [])
            self.assertEqual(brief.start_interview()["status"], "sufficient")
            self.assertIsNone(brief.ask_next())

            optional = [q.fact_id for q in brief.next_questions(include_optional=True)]
            self.assertEqual(set(optional), set(OPTIONAL_IDS))

    def test_assumed_fact_raises_a_confirmation_question_and_blocks_sufficiency(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            for fact_id in REQUIRED_IDS:
                brief.answer(fact_id, "value " + fact_id)
            brief.record_fact(
                "geography.service_area",
                "Greater Austin",
                provenance=ab.PROVENANCE_ASSUMED,
            )

            self.assertFalse(brief.is_sufficient())
            confirmations = [
                q for q in brief.next_questions() if q.kind == "confirm"
            ]
            self.assertEqual(
                [q.fact_id for q in confirmations], ["geography.service_area"]
            )
            blockers = brief.planning_blockers()
            self.assertIn(
                {
                    "kind": "unconfirmed_assumption",
                    "fact_id": "geography.service_area",
                    "reason": "recorded as assumed",
                },
                blockers,
            )

            brief.answer(
                "geography.service_area",
                "Greater Austin",
                provenance=ab.PROVENANCE_CLIENT_STATED,
            )
            self.assertTrue(brief.is_sufficient())
            self.assertEqual(brief.next_questions(), [])


class ResumeTests(unittest.TestCase):
    def test_interrupted_interview_resumes_on_the_same_question(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            first = ab.AcquisitionBrief(path, clock=fixed_clock)
            first.start_interview()
            first.answer("business.legal_name", "Acme Ltd")
            first.answer("business.what_you_do", "We sell wheels")
            pending = first.ask_next()
            self.assertIsNotNone(pending)

            # Simulate a killed process: no close(), no cleanup, new object.
            resumed = ab.AcquisitionBrief(path, clock=fixed_clock)
            state = resumed.resume()

            self.assertEqual(state["pending_question"]["fact_id"], pending.fact_id)
            self.assertEqual(
                state["known_fact_ids"],
                ["business.legal_name", "business.what_you_do"],
            )
            self.assertEqual(
                resumed.next_questions()[0].fact_id, pending.fact_id
            )
            self.assertEqual(
                resumed.ask_next().fact_id, pending.fact_id
            )
            asked_events = [
                event
                for event in resumed._state["interview"]["events"]
                if event.get("event") == "question_asked"
            ]
            self.assertEqual(len(asked_events), 1)

            resumed.answer(pending.fact_id, "answered after resume")
            self.assertNotEqual(
                resumed.ask_next().fact_id, pending.fact_id
            )

    def test_abrupt_process_exit_loses_no_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            child = (
                "import os, sys\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "import acquisition_brief as ab\n"
                "brief = ab.AcquisitionBrief(sys.argv[2])\n"
                "brief.answer('business.legal_name', 'Acme Ltd')\n"
                "question = brief.ask_next()\n"
                "sys.stdout.write(question.fact_id)\n"
                "sys.stdout.flush()\n"
                "os._exit(0)\n"
            )
            completed = subprocess.run(
                [sys.executable, "-c", child, str(TOOLS_DIR), path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            pending_fact_id = completed.stdout.strip()

            resumed = ab.AcquisitionBrief(path, clock=fixed_clock)
            self.assertEqual(
                resumed.require("business.legal_name").value, "Acme Ltd"
            )
            self.assertEqual(
                resumed.resume()["pending_question"]["fact_id"], pending_fact_id
            )

    def test_repeated_answer_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.answer("business.legal_name", "Acme Ltd")
            events_after_first = len(brief._state["interview"]["events"])
            brief.answer("business.legal_name", "Acme Ltd")

            self.assertEqual(
                len(brief._state["interview"]["events"]), events_after_first
            )
            self.assertEqual(brief.known_fact_ids(), ["business.legal_name"])

    def test_orphan_temp_file_does_not_corrupt_load(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.answer("business.legal_name", "Acme Ltd")
            with open(
                os.path.join(directory, ".brief.json.dead.tmp"), "w"
            ) as handle:
                handle.write('{"half": ')
            reloaded = new_brief(directory)
            self.assertEqual(
                reloaded.require("business.legal_name").value, "Acme Ltd"
            )
            leftovers = [
                name
                for name in os.listdir(directory)
                if name.startswith(".brief.json.") and name.endswith(".tmp")
            ]
            self.assertEqual(len(leftovers), 1)  # only the one we planted


class NoRepeatQuestionTests(unittest.TestCase):
    def test_answered_questions_are_never_offered_again(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            asked = []
            while True:
                question = brief.ask_next()
                if question is None:
                    break
                self.assertNotIn(question.fact_id, asked)
                asked.append(question.fact_id)
                brief.answer(question.fact_id, "answer " + question.fact_id)

            self.assertEqual(set(asked), set(REQUIRED_IDS))
            self.assertEqual(brief.next_questions(), [])
            self.assertEqual(brief.ask_next(), None)

    def test_asking_twice_without_answering_repeats_the_same_question_only(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            first = brief.ask_next()
            second = brief.ask_next()
            self.assertEqual(first.fact_id, second.fact_id)
            asked_events = [
                event
                for event in brief._state["interview"]["events"]
                if event.get("event") == "question_asked"
            ]
            self.assertEqual(len(asked_events), 1)


class NothingInventedTests(unittest.TestCase):
    def test_unanswered_fact_has_no_value_anywhere(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            brief = ab.AcquisitionBrief(path, clock=fixed_clock)
            brief.start_interview()
            brief.ask_next()

            self.assertIsNone(brief.get("audience.primary_audience"))
            with self.assertRaises(ab.MissingFactError):
                brief.require("audience.primary_audience")

            with open(path, "r", encoding="utf-8") as handle:
                document = json.load(handle)
            self.assertNotIn("audience.primary_audience", document["facts"])
            snapshot = brief.snapshot()
            self.assertIn(
                "audience.primary_audience", snapshot["unanswered_fact_ids"]
            )
            self.assertNotIn(
                "audience.primary_audience",
                json.dumps(snapshot["sections"]),
            )

    def test_unknown_fact_is_recorded_as_missing_not_defaulted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            brief = ab.AcquisitionBrief(path, clock=fixed_clock)
            brief.mark_missing(
                "seasonality.upcoming_season", "client does not track seasons"
            )

            self.assertIsNone(brief.get("seasonality.upcoming_season"))
            self.assertEqual(
                brief.unresolved_fact_ids(), ["seasonality.upcoming_season"]
            )
            self.assertFalse(brief.is_sufficient())
            self.assertNotIn(
                "seasonality.upcoming_season",
                [q.fact_id for q in brief.next_questions()],
            )
            blockers = brief.planning_blockers()
            self.assertIn(
                {
                    "kind": "missing_fact",
                    "fact_id": "seasonality.upcoming_season",
                    "reason": "client does not track seasons",
                },
                blockers,
            )

            with open(path, "r", encoding="utf-8") as handle:
                raw = handle.read()
            document = json.loads(raw)
            self.assertNotIn("seasonality.upcoming_season", document["facts"])
            self.assertNotIn('"unknown"', raw.lower())
            self.assertNotIn('"n/a"', raw.lower())

    def test_marking_a_recorded_fact_missing_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.answer("business.legal_name", "Acme Ltd")
            with self.assertRaises(ab.InvalidFactError):
                brief.mark_missing("business.legal_name", "forgotten")


class AssetRegistryTests(unittest.TestCase):
    def test_registry_records_have_missing_and_must_prepare(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            initial = brief.asset_report()
            self.assertEqual(set(initial["unassessed"]), set(ab.ASSET_KINDS))
            self.assertEqual(initial["must_prepare"], [])
            self.assertEqual(initial["missing"], [])
            self.assertFalse(brief.is_campaign_ready())

            brief.assess_asset(
                "logo", ab.ASSET_PRESENT, detail="brand/logo.png"
            )
            brief.assess_asset(
                "photos",
                ab.ASSET_ABSENT,
                detail="no original photography",
            )
            brief.assess_asset(
                "testimonials",
                ab.ASSET_ABSENT,
                detail="no written reviews yet",
            )
            report = brief.asset_report()

            self.assertEqual(
                [entry["kind"] for entry in report["present"]], ["logo"]
            )
            self.assertEqual(
                [entry["kind"] for entry in report["missing"]],
                ["photos", "testimonials"],
            )
            self.assertEqual(report["must_prepare"], ["photos"])
            self.assertEqual(
                [entry["kind"] for entry in report["optional_missing"]],
                ["testimonials"],
            )
            self.assertNotIn("photos", report["unassessed"])
            self.assertIn("offer_documents", report["unassessed"])

    def test_unassessed_asset_is_not_treated_as_missing_or_preparable(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.assess_asset("logo", ab.ASSET_PRESENT)
            report = brief.asset_report()
            self.assertNotIn("photos", report["must_prepare"])
            self.assertIn("photos", report["unassessed"])
            blockers = brief.planning_blockers()
            self.assertIn(
                {"kind": "asset_unassessed", "fact_id": "photos", "reason": ""},
                blockers,
            )

    def test_registry_rejects_unknown_kind_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            with self.assertRaises(ab.UnknownAssetError):
                brief.assess_asset("hologram", ab.ASSET_PRESENT)
            with self.assertRaises(ab.InvalidFactError):
                brief.assess_asset("logo", "maybe")

    def test_registry_generates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.assess_asset("logo", ab.ASSET_ABSENT, detail="none yet")
            report = brief.asset_report()
            self.assertEqual(report["must_prepare"], ["logo"])
            # The registry records state only; preparation belongs to T-07.
            for forbidden in (
                "generate_asset",
                "create_asset",
                "prepare_asset",
                "render_asset",
            ):
                self.assertFalse(hasattr(brief, forbidden))
                self.assertFalse(hasattr(ab, forbidden))


class DurabilityTests(unittest.TestCase):
    def test_corrupt_brief_fails_loudly_and_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            broken = '{"schema": "skill38.acquisition_brief.v1", "facts": '
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(broken)

            with self.assertRaises(ab.BriefCorruptError):
                ab.AcquisitionBrief(path, clock=fixed_clock)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), broken)

    def test_save_leaves_no_temporary_file_behind(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.answer("business.legal_name", "Acme Ltd")
            leftovers = [
                name for name in os.listdir(directory) if name.endswith(".tmp")
            ]
            self.assertEqual(leftovers, [])

    def test_snapshot_covers_every_section(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            snapshot = brief.snapshot()
            self.assertEqual(
                set(ab.SECTION_ORDER),
                {
                    "business",
                    "offers",
                    "audience",
                    "proof",
                    "constraints",
                    "channels",
                    "geography",
                    "seasonality",
                },
            )
            self.assertEqual(
                list(snapshot["sections"].keys()), list(ab.SECTION_ORDER)
            )
            self.assertEqual(len(snapshot["unanswered_fact_ids"]), len(ALL_IDS))
            self.assertFalse(snapshot["is_sufficient"])
            self.assertFalse(snapshot["is_campaign_ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Tests for asset_registry.py (T-07, asset inventory and preparation).

The suite proves doctrine, not just plumbing: a client with nothing is blocked
with an explicit list, a complete set passes, a missing asset never becomes a
placeholder, an unprovenanced claim is refused, and the registry round-trips
and is idempotent across two separate processes.

Run from the skill root:
  python3 -m unittest discover -s tools/tests -p 'test_*.py'
or:
  python3 tools/tests/test_asset_registry.py
"""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import acquisition_brief as ab  # noqa: E402
import asset_registry as ar  # noqa: E402

FIXED_NOW = datetime.datetime(
    2026, 10, 24, 12, 0, 0, 0, tzinfo=datetime.timezone.utc
)

REQUIRED_KINDS = [kind for kind in ar.ASSET_KINDS if kind in ar.REQUIRED_FOR_CAMPAIGN]
OPTIONAL_KINDS = [kind for kind in ar.ASSET_KINDS if kind not in ar.REQUIRED_FOR_CAMPAIGN]


def fixed_clock():
    return FIXED_NOW


def new_brief(directory):
    return ab.AcquisitionBrief(os.path.join(directory, "brief.json"), clock=fixed_clock)


def new_registry(directory, *, brief=None, name="assets.json", clock=fixed_clock):
    return ar.AssetRegistry(os.path.join(directory, name), brief=brief, clock=clock)


def evidence_file(directory, name="evidence.txt"):
    """A real file on disk, so a path-shaped evidence pointer is a real one."""
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("real evidence\n")
    return path


GENUINE_URL = "https://assets.acme-brand.com/brand/logo.png"


def record_complete_set(registry, *, testimonial=True):
    directory = os.path.dirname(registry.path)
    for kind in REQUIRED_KINDS:
        if kind == "testimonials" and not testimonial:
            continue
        registry.record_present(
            kind,
            source=ar.SOURCE_CLIENT_PROVIDED,
            evidence=evidence_file(directory, "%s.txt" % kind),
            detail="client supplied %s" % kind,
        )


class NoAssetsTests(unittest.TestCase):
    def test_fresh_registry_is_blocked_with_an_explicit_list(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            readiness = registry.campaign_readiness()

            self.assertFalse(readiness["sufficient"])
            self.assertFalse(registry.is_campaign_ready())
            self.assertEqual(
                [item["kind"] for item in readiness["blockers"]], REQUIRED_KINDS
            )
            self.assertEqual(
                {item["state"] for item in readiness["blockers"]}, {"unassessed"}
            )
            self.assertIn("NOT sufficient", readiness["plain"])
            for kind in REQUIRED_KINDS:
                self.assertIn(kind, readiness["plain"])

    def test_every_missing_kind_is_named_and_worklisted(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            for kind in ar.ASSET_KINDS:
                registry.record_missing(kind, "client has nothing for %s" % kind)

            readiness = registry.campaign_readiness()
            self.assertFalse(readiness["sufficient"])
            self.assertEqual(
                [item["kind"] for item in readiness["blockers"]], REQUIRED_KINDS
            )
            self.assertEqual(
                {item["state"] for item in readiness["blockers"]}, {"must_prepare"}
            )

            worklist = registry.preparation_worklist()
            self.assertEqual([item["kind"] for item in worklist], REQUIRED_KINDS)
            self.assertEqual(readiness["worklist_count"], len(worklist))

    def test_optional_absence_does_not_block(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            record_complete_set(registry)
            for kind in OPTIONAL_KINDS:
                registry.record_missing(kind, "not available")

            readiness = registry.campaign_readiness()
            self.assertTrue(readiness["sufficient"], readiness["plain"])
            self.assertEqual(readiness["blockers"], [])


class CompleteSetTests(unittest.TestCase):
    def test_complete_set_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            record_complete_set(registry)

            readiness = registry.campaign_readiness()
            self.assertTrue(readiness["sufficient"], readiness["plain"])
            self.assertTrue(registry.is_campaign_ready())
            self.assertEqual(readiness["blockers"], [])
            self.assertEqual(readiness["worklist_count"], 0)
            self.assertEqual(registry.preparation_worklist(), [])
            self.assertIn("sufficient", readiness["plain"])
            self.assertEqual(
                sorted(readiness["ready_kinds"]), sorted(REQUIRED_KINDS)
            )
            for kind in REQUIRED_KINDS:
                self.assertEqual(registry.require_ready(kind)["kind"], kind)

    def test_one_missing_required_kind_blocks_the_rest(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            record_complete_set(registry, testimonial=False)
            registry.record_missing("testimonials", "no published reviews yet")

            readiness = registry.campaign_readiness()
            self.assertFalse(readiness["sufficient"])
            self.assertEqual(
                readiness["blockers"],
                [
                    {
                        "kind": "testimonials",
                        "state": "must_prepare",
                        "reason": "no published reviews yet",
                    }
                ],
            )
            self.assertEqual(len(readiness["ready_kinds"]), len(REQUIRED_KINDS) - 1)


class NoPlaceholderTests(unittest.TestCase):
    def test_missing_asset_never_becomes_a_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            record = registry.record_missing("logo", "client has no logo file")

            self.assertEqual(record["readiness"], "missing")
            self.assertEqual(record["source"], "must_prepare")
            self.assertIsNone(record["evidence"])
            self.assertIsNone(record["detail"])
            for forbidden in ("value", "path", "url", "placeholder", "content"):
                self.assertNotIn(forbidden, record)

            entry = registry.classify()["logo"]
            self.assertEqual(entry["readiness"], "must_prepare")
            self.assertIsNone(entry["evidence"])
            self.assertIsNone(entry["detail"])

            with self.assertRaises(ar.MissingAssetError):
                registry.require_ready("logo")
            self.assertFalse(registry.campaign_readiness()["sufficient"])

            dumped = json.dumps(registry.snapshot(), sort_keys=True)
            self.assertNotIn("logo.png", dumped)
            self.assertNotIn("placeholder", dumped.lower())

    def test_unassessed_is_never_reported_as_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            entry = registry.classify()["photos"]
            self.assertEqual(entry["readiness"], "unassessed")
            self.assertIsNone(entry["source"])
            self.assertFalse(entry["on_worklist"])
            self.assertEqual(registry.preparation_worklist(), [])

    def test_request_preparation_refuses_unassessed_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            with self.assertRaises(ar.MissingAssetError):
                registry.request_preparation("video")

    def test_request_preparation_puts_optional_missing_on_worklist(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            registry.record_missing("video", "no footage yet")
            self.assertEqual(registry.preparation_worklist(), [])
            registry.request_preparation("video")
            worklist = registry.preparation_worklist()
            self.assertEqual([item["kind"] for item in worklist], ["video"])
            self.assertFalse(worklist[0]["required_for_campaign"])
            # Idempotent: a second request is a no-op.
            registry.request_preparation("video")
            self.assertEqual(len(registry.preparation_worklist()), 1)


class ProvenanceTests(unittest.TestCase):
    def test_present_claim_without_source_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            named = "the client's brand pack"
            with self.assertRaises(ar.UnprovenancedClaimError):
                registry.record_present("logo", source=None, evidence=named)
            with self.assertRaises(ar.UnprovenancedClaimError):
                registry.record_present(
                    "logo", source=ar.SOURCE_MUST_PREPARE, evidence=named
                )
            with self.assertRaises(ar.UnprovenancedClaimError):
                registry.record_present(
                    "logo", source=ab.PROVENANCE_ASSUMED, evidence=named
                )

    def test_present_claim_without_evidence_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            for evidence in ("", "   ", None):
                with self.assertRaises(ar.UnprovenancedClaimError):
                    registry.record_present(
                        "logo",
                        source=ar.SOURCE_CLIENT_PROVIDED,
                        evidence=evidence,
                    )

    def test_missing_claim_needs_a_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            with self.assertRaises(ar.InvalidClaimError):
                registry.record_missing("logo", "  ")

    def test_link_to_untrusted_fact_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.record_fact(
                "proof.proof_assets",
                "five-star reviews on Google",
                provenance=ab.PROVENANCE_ASSUMED,
            )
            registry = new_registry(directory, brief=brief)
            registry.record_present(
                "testimonials",
                source=ar.SOURCE_CLIENT_PROVIDED,
                evidence=evidence_file(directory, "testimonials.txt"),
            )
            with self.assertRaises(ar.UntrustedProvenanceError):
                registry.link_to_brief_fact("testimonials", "proof.proof_assets")

    def test_link_to_unanswered_or_unknown_fact_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            registry = new_registry(directory, brief=brief)
            registry.record_present(
                "testimonials",
                source=ar.SOURCE_CLIENT_PROVIDED,
                evidence=evidence_file(directory, "testimonials.txt"),
            )
            with self.assertRaises(ar.UnknownBriefFactError):
                registry.link_to_brief_fact("testimonials", "proof.invented_fact")
            with self.assertRaises(ar.UntrustedProvenanceError):
                registry.link_to_brief_fact("testimonials", "proof.proof_assets")

    def test_link_to_a_missing_asset_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.record_fact(
                "proof.proof_assets",
                "five-star reviews on Google",
                provenance=ab.PROVENANCE_CLIENT_STATED,
            )
            registry = new_registry(directory, brief=brief)
            registry.record_missing("testimonials", "no reviews yet")
            with self.assertRaises(ar.MissingAssetError):
                registry.link_to_brief_fact("testimonials", "proof.proof_assets")

    def test_sync_from_brief_refuses_an_unprovenanced_present_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.assess_asset("logo", ab.ASSET_PRESENT, detail="/clients/logo.png")
            registry = new_registry(directory, brief=brief)
            with self.assertRaises(ar.UntrustedProvenanceError):
                registry.sync_from_brief()
            self.assertEqual(registry.classify()["logo"]["readiness"], "unassessed")


class WorklistTests(unittest.TestCase):
    def test_worklist_names_the_deliverable_and_its_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            registry.record_missing("logo", "client has no logo file")
            entry = registry.preparation_worklist()[0]

            self.assertEqual(
                set(entry),
                {
                    "kind",
                    "deliverable",
                    "inputs",
                    "blocked_on_inputs",
                    "status",
                    "required_for_campaign",
                    "reason",
                },
            )
            self.assertEqual(entry["kind"], "logo")
            self.assertIn("logo lockup", entry["deliverable"])
            self.assertEqual(entry["status"], "awaiting_inputs")
            self.assertEqual(entry["reason"], "client has no logo file")
            self.assertEqual(
                entry["blocked_on_inputs"],
                [item.label for item in ar.PREPARATION_SPECS["logo"].inputs],
            )

    def test_worklist_input_is_satisfied_by_a_trusted_brief_fact(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.record_fact(
                "business.legal_name",
                "Acme Ltd",
                provenance=ab.PROVENANCE_CLIENT_STATED,
            )
            registry = new_registry(directory, brief=brief)
            registry.record_missing("logo", "client has no logo file")

            entry = registry.preparation_worklist()[0]
            inputs = {item["label"]: item for item in entry["inputs"]}
            name_input = inputs["business legal or trading name"]
            self.assertTrue(name_input["satisfied"])
            self.assertEqual(name_input["satisfied_by"], "brief:business.legal_name")
            self.assertNotIn("business legal or trading name", entry["blocked_on_inputs"])
            self.assertEqual(ar.PREPARATION_SPECS["logo"].kind, "logo")

    def test_an_assumed_fact_does_not_satisfy_a_worklist_input(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.record_fact(
                "business.legal_name",
                "Acme Ltd",
                provenance=ab.PROVENANCE_ASSUMED,
            )
            registry = new_registry(directory, brief=brief)
            registry.record_missing("logo", "client has no logo file")
            entry = registry.preparation_worklist()[0]
            self.assertIn("business legal or trading name", entry["blocked_on_inputs"])

    def test_supplied_input_requires_evidence_and_closes_the_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            registry.record_missing("logo", "client has no logo file")
            with self.assertRaises(ar.UnprovenancedClaimError):
                registry.supply_input("logo", "brand colours, if any", evidence="")
            with self.assertRaises(ar.InvalidClaimError):
                registry.supply_input("logo", "not an input", evidence="/x")

            registry.supply_input(
                "logo", "brand colours, if any", evidence="/brand/palette.txt"
            )
            entry = registry.preparation_worklist()[0]
            inputs = {item["label"]: item for item in entry["inputs"]}
            self.assertTrue(inputs["brand colours, if any"]["satisfied"])
            self.assertNotIn("brand colours, if any", entry["blocked_on_inputs"])

    def test_mark_ready_requires_a_real_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            registry.record_missing("logo", "client has no logo file")
            with self.assertRaises(ar.UnprovenancedClaimError):
                registry.mark_ready("logo", evidence=os.path.join(directory, "no.png"))

            real = evidence_file(directory, "logo.png")
            record = registry.mark_ready("logo", evidence=real)
            self.assertEqual(record["readiness"], "ready")
            self.assertEqual(record["evidence"], real)
            # A prepared asset is never relabelled as the client's own work.
            self.assertEqual(record["source"], ar.SOURCE_PREPARED)


class IntegrationTests(unittest.TestCase):
    def test_registry_kinds_cover_the_acquisition_brief(self):
        self.assertTrue(set(ab.ASSET_KINDS) <= set(ar.ASSET_KINDS))
        self.assertTrue(
            set(ab.ASSET_REQUIRED_FOR_CAMPAIGN) <= ar.REQUIRED_FOR_CAMPAIGN
        )

    def test_sync_from_brief_imports_present_and_absent_assessments(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.assess_asset(
                "logo",
                ab.ASSET_PRESENT,
                detail=evidence_file(directory, "logo.png"),
                source=ab.PROVENANCE_CLIENT_STATED,
            )
            brief.assess_asset(
                "photos",
                ab.ASSET_PRESENT,
                detail="https://assets.acme-brand.com/gallery",
                source=ab.PROVENANCE_DISCOVERED,
            )
            brief.assess_asset(
                "links", ab.ASSET_ABSENT, detail="no booking page yet"
            )
            registry = new_registry(directory, brief=brief)

            counts = registry.sync_from_brief()
            self.assertEqual(counts, {"imported": 2, "missing": 1})

            classification = registry.classify()
            self.assertEqual(classification["logo"]["readiness"], "ready")
            self.assertEqual(
                classification["logo"]["source"], ar.SOURCE_CLIENT_PROVIDED
            )
            self.assertEqual(
                classification["photos"]["source"], ar.SOURCE_DISCOVERED
            )
            self.assertEqual(classification["links"]["readiness"], "must_prepare")
            self.assertEqual(classification["links"]["reason"], "no booking page yet")

    def test_link_defaults_join_present_assets_to_brief_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.record_fact(
                "proof.proof_assets",
                "five-star Google reviews",
                provenance=ab.PROVENANCE_CLIENT_STATED,
            )
            brief.record_fact(
                "offers.primary_offer",
                "six-week coaching block",
                provenance=ab.PROVENANCE_CLIENT_STATED,
            )
            registry = new_registry(directory, brief=brief)
            testimonial_evidence = evidence_file(directory, "testimonials.txt")
            registry.record_present(
                "testimonials",
                source=ar.SOURCE_CLIENT_PROVIDED,
                evidence=testimonial_evidence,
            )
            registry.record_present(
                "offer_documents",
                source=ar.SOURCE_CLIENT_PROVIDED,
                evidence=evidence_file(directory, "offer.pdf"),
            )
            registry.record_present(
                "logo",
                source=ar.SOURCE_CLIENT_PROVIDED,
                evidence=evidence_file(directory, "logo.png"),
            )

            links = registry.link_defaults()
            self.assertEqual(
                sorted(link["kind"] for link in links),
                ["offer_documents", "testimonials"],
            )
            classification = registry.classify()
            self.assertEqual(
                classification["testimonials"]["linked_fact_id"],
                "proof.proof_assets",
            )
            self.assertIsNone(classification["logo"]["linked_fact_id"])
            # The fact's own value is never copied over the asset evidence.
            self.assertEqual(
                registry.snapshot()["assets"]["testimonials"]["evidence"],
                testimonial_evidence,
            )

    def test_link_defaults_refuses_an_assumed_fact(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.record_fact(
                "proof.proof_assets",
                "probably has reviews",
                provenance=ab.PROVENANCE_ASSUMED,
            )
            registry = new_registry(directory, brief=brief)
            registry.record_present(
                "testimonials",
                source=ar.SOURCE_CLIENT_PROVIDED,
                evidence=evidence_file(directory, "testimonials.txt"),
            )
            with self.assertRaises(ar.UntrustedProvenanceError):
                registry.link_defaults()


class PersistenceTests(unittest.TestCase):
    def test_round_trip_preserves_the_whole_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            record_complete_set(registry, testimonial=False)
            registry.record_missing("testimonials", "no published reviews yet")

            reloaded = new_registry(directory)
            self.assertEqual(reloaded.snapshot()["assets"], registry.snapshot()["assets"])
            self.assertEqual(
                reloaded.snapshot()["preparation_worklist"],
                registry.snapshot()["preparation_worklist"],
            )
            self.assertEqual(
                reloaded.snapshot()["readiness"], registry.snapshot()["readiness"]
            )

    def test_repeated_operations_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            logo_evidence = evidence_file(directory, "logo.png")
            registry.record_present(
                "logo",
                source=ar.SOURCE_CLIENT_PROVIDED,
                evidence=logo_evidence,
                detail="brand pack",
            )
            registry.record_missing("photos", "no usable photos")
            path = registry.path
            with open(path, "r", encoding="utf-8") as handle:
                before = handle.read()

            registry.record_present(
                "logo",
                source=ar.SOURCE_CLIENT_PROVIDED,
                evidence=logo_evidence,
                detail="brand pack",
            )
            registry.record_missing("photos", "no usable photos")
            with open(path, "r", encoding="utf-8") as handle:
                after = handle.read()

            self.assertEqual(before, after)
            self.assertEqual(len(registry._state["events"]), 2)

    def test_two_separate_processes_produce_identical_bytes(self):
        child = r"""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, sys.argv[1])
import asset_registry as ar

clock = lambda: datetime(2026, 10, 24, 12, 0, 0, 0, tzinfo=timezone.utc)
registry = ar.AssetRegistry(sys.argv[2], clock=clock)
evidence = os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), "logo-evidence.txt")
with open(evidence, "w", encoding="utf-8") as handle:
    handle.write("PNG")
registry.record_present("logo", source=ar.SOURCE_CLIENT_PROVIDED,
                        evidence=evidence, detail="brand pack")
registry.record_missing("photos", "no usable photos")
registry.supply_input("logo", "brand colours, if any", evidence="/brand/palette.txt")
print(registry.campaign_readiness()["sufficient"])
"""
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "assets.json")
            outputs = []
            for _ in range(2):
                completed = subprocess.run(
                    [sys.executable, "-c", child, str(TOOLS_DIR), path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                outputs.append(completed.stdout.strip())
                with open(path, "r", encoding="utf-8") as handle:
                    outputs.append(handle.read())

            self.assertEqual(outputs[0], "False")
            self.assertEqual(outputs[2], "False")
            self.assertEqual(outputs[1], outputs[3], "second process changed state")

    def test_two_concurrent_processes_both_keep_their_writes(self):
        child = r"""
import os, sys, time
from datetime import datetime, timezone
sys.path.insert(0, sys.argv[1])
import asset_registry as ar

clock = lambda: datetime.now(timezone.utc)
registry = ar.AssetRegistry(sys.argv[2], clock=clock)
directory = os.path.dirname(os.path.abspath(sys.argv[2]))
kind = sys.argv[3]
for index in range(10):
    evidence = os.path.join(directory, "%s-%d.txt" % (kind, index))
    with open(evidence, "w", encoding="utf-8") as handle:
        handle.write("PNG")
    registry.record_present(kind, source=ar.SOURCE_DISCOVERED, evidence=evidence)
    time.sleep(0.02)
"""
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "assets.json")
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", child, str(TOOLS_DIR), path, kind],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for kind in ("logo", "photos")
            ]
            for process in processes:
                stdout, stderr = process.communicate(timeout=60)
                self.assertEqual(process.returncode, 0, stderr)

            registry = new_registry(directory)
            classification = registry.classify()
            self.assertEqual(classification["logo"]["readiness"], "ready")
            self.assertEqual(classification["photos"]["readiness"], "ready")

    def test_a_corrupt_registry_fails_loudly_and_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "assets.json")
            broken = "{not json"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(broken)

            with self.assertRaises(ar.RegistryCorruptError):
                ar.AssetRegistry(path, clock=fixed_clock)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), broken)

    def test_save_leaves_no_temporary_file_behind(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            registry.record_present(
                "logo",
                source=ar.SOURCE_CLIENT_PROVIDED,
                evidence=evidence_file(directory, "logo.png"),
            )
            leftovers = [
                name for name in os.listdir(directory) if name.endswith(".tmp")
            ]
            self.assertEqual(leftovers, [])

    def test_snapshot_covers_every_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            snapshot = registry.snapshot()
            self.assertEqual(list(snapshot["assets"].keys()), list(ar.ASSET_KINDS))
            self.assertEqual(
                {entry["readiness"] for entry in snapshot["assets"].values()},
                {"unassessed"},
            )
            self.assertFalse(snapshot["readiness"]["sufficient"])
            self.assertEqual(snapshot["preparation_worklist"], [])
            self.assertFalse(snapshot["brief_attached"])


class EvidenceShapeTests(unittest.TestCase):
    """Every refused pointer shape, each with a known-good control.

    The literal attacks: a string containing "://" was accepted as proof, and
    `https://invented.invalid/nope.png` was accepted as a link. Both are now
    refused. The achievable bar is shape, not reachability: a URL is checked
    offline for being a real http/https URL naming a host that could exist.
    """

    FABRICATED_URLS = (
        "totally://made.up",
        "://",
        "ftp://files.acme-brand.com/logo.png",
        "https:logo.png",
        "https://no-dot-host/logo.png",
        "https://invented.invalid/nope.png",
        "https://assets.example.com/logo.png",
    )

    FABRICATED_PATHS = (
        "/no/such/directory/pb045-evidence.png",
        "pb045-evidence.png",
        "./pb045-evidence.png",
        "~/pb045-evidence.png",
    )

    BLANK_NAMELESS_AND_NON_STRINGS = (
        "",
        "   ",
        "\t\n",
        "!!!",
        "---",
        None,
        7,
        3.5,
        b"bytes",
        ["x"],
        {"evidence": "x"},
    )

    def assert_refused(self, registry, bad):
        with self.assertRaises(ar.UnprovenancedClaimError):
            registry.mark_ready("logo", evidence=bad)
        with self.assertRaises(ar.UnprovenancedClaimError):
            registry.record_present(
                "logo", source=ar.SOURCE_CLIENT_PROVIDED, evidence=bad
            )
        self.assertEqual(registry.classify()["logo"]["readiness"], "unassessed")

    def test_url_shaped_fabrications_are_refused(self):
        for bad in self.FABRICATED_URLS:
            with self.subTest(evidence=bad):
                with tempfile.TemporaryDirectory() as directory:
                    self.assert_refused(new_registry(directory), bad)

    def test_a_genuine_url_is_the_accepted_url_control(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            record = registry.mark_ready("logo", evidence=GENUINE_URL)
            self.assertEqual(record["readiness"], "ready")
            self.assertEqual(record["evidence"], GENUINE_URL)
            self.assertEqual(record["source"], ar.SOURCE_PREPARED)

    def test_paths_that_name_nothing_are_refused(self):
        for bad in self.FABRICATED_PATHS:
            with self.subTest(evidence=bad):
                with tempfile.TemporaryDirectory() as directory:
                    self.assert_refused(new_registry(directory), bad)

    def test_an_existing_file_is_the_accepted_path_control(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            real = evidence_file(directory, "pb045-real.png")
            record = registry.mark_ready("logo", evidence=real)
            self.assertEqual(record["readiness"], "ready")
            self.assertEqual(record["evidence"], real)
            self.assertEqual(record["source"], ar.SOURCE_PREPARED)

    def test_blank_nameless_and_non_string_evidence_is_refused(self):
        for bad in self.BLANK_NAMELESS_AND_NON_STRINGS:
            with self.subTest(evidence=bad):
                with tempfile.TemporaryDirectory() as directory:
                    self.assert_refused(new_registry(directory), bad)

    def test_a_named_source_is_the_accepted_named_control(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            named = "the client's shared Google Drive folder"
            record = registry.record_present(
                "logo", source=ar.SOURCE_CLIENT_PROVIDED, evidence=named
            )
            self.assertEqual(record["readiness"], "ready")
            self.assertEqual(record["evidence"], named)
            self.assertEqual(record["source"], ar.SOURCE_CLIENT_PROVIDED)

            # A prepared asset is pointed at, never merely named.
            registry.record_missing("photos", "no usable photos")
            with self.assertRaises(ar.UnprovenancedClaimError):
                registry.mark_ready("photos", evidence="the photo studio's contact")

    def test_a_refused_pointer_never_promotes_the_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = new_registry(directory)
            registry.record_missing("logo", "client has no logo file")
            for bad in (
                "totally://made.up",
                "https://invented.invalid/nope.png",
                "/no/such/directory/pb045-evidence.png",
            ):
                with self.subTest(evidence=bad):
                    with self.assertRaises(ar.UnprovenancedClaimError):
                        registry.mark_ready("logo", evidence=bad)

            entry = registry.classify()["logo"]
            self.assertEqual(entry["readiness"], "must_prepare")
            self.assertIsNone(entry["evidence"])
            self.assertIsNone(registry.snapshot()["assets"]["logo"]["evidence"])
            self.assertFalse(registry.is_campaign_ready())
            self.assertEqual(
                [
                    item["kind"]
                    for item in registry.campaign_readiness()["blockers"]
                ],
                REQUIRED_KINDS,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

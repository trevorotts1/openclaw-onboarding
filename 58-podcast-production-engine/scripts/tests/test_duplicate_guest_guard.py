#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: duplicate-guest / release gates
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network, no live DB: throwaway file DBs and the real
# shipped schema. Covers the client-safety near-miss in which a guest whose
# episode had ALREADY been published was queued a second time and sat one step
# from re-publishing to a live client feed.
#
# The three holes proved here:
#   1. `submission_fingerprint` holds TWO hash formats (the webhook job_key and
#      the local content sha256). The byte-comparison dedup could not see the
#      same guest stored the other way; guest identity is now compared instead,
#      on a canonical form so spelling and punctuation cannot defeat it.
#   2. A rescue/activation proof advances a REAL job (SOP-PODCAST-07 Section 3)
#      and left no marker, so a test-advanced job looked organic.
#   3. A research package that admits it had no transcript could reach publish.
#
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_duplicate_guest_guard.py
# =============================================================================
"""Deterministic tests for the duplicate-guest and publish release gates."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "podcast_state.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("podcast_state", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PS = _load_module()

#: Named literally, NOT via PS, so the harness still runs against a build
#: that lacks the fix -- the CLI cases must then fail on BEHAVIOUR (a job
#: that publishes when it must not), never on a missing attribute.
RELEASE_ENV = "PODCAST_OPERATOR_RELEASE"


class CanonicalGuestIdTests(unittest.TestCase):
    """Identity must survive case and punctuation, or the guard is byte-equality
    wearing a different hat."""

    def test_case_and_punctuation_fold_to_one_identity(self):
        forms = [
            "MayaRandleGuest01",
            "mayarandleguest01",
            "MAYARANDLEGUEST01",
            "maya-randle-guest-01",
            "Maya_Randle_Guest_01",
            " MayaRandleGuest01 ",
        ]
        canon = {PS.canonical_guest_id(f) for f in forms}
        self.assertEqual(canon, {"mayarandleguest01"},
                         "all spellings of one contact identifier must canonicalize together")

    def test_distinct_guests_stay_distinct(self):
        self.assertNotEqual(PS.canonical_guest_id("MayaRandleGuest01"),
                            PS.canonical_guest_id("MayaRandleGuest02"))

    def test_empty_contact_is_not_an_identity(self):
        self.assertEqual(PS.canonical_guest_id(None), "")
        self.assertEqual(PS.canonical_guest_id("   "), "")


class _DbCase(unittest.TestCase):
    """Throwaway file DB carrying the real shipped schema."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="podcast-guest-guard-")
        self.db = os.path.join(self.tmp, "state.db")
        self.env = dict(os.environ)
        self.env["PODCAST_DB_PATH"] = self.db
        # Never let an operator release leak in from the ambient environment.
        self.env.pop(RELEASE_ENV, None)
        self.conn = sqlite3.connect(self.db)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(PS.SCHEMA)
        self.conn.commit()

    def _insert_job(self, job_id, contact_id, fingerprint, status="received",
                    client_id="thesoftgirlera", permalink=None, published_at=None,
                    mode="interview_style_podcast"):
        self.conn.execute(
            "INSERT INTO podcast_jobs (job_id, client_id, location_id, contact_id, "
            "submission_fingerprint, mode, style, status, podbean_permalink, "
            "publish_timestamp) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job_id, client_id, "loc", contact_id, fingerprint, mode, "vulnerable",
             status, permalink, published_at),
        )
        self.conn.commit()

    def _event(self, job_id, note):
        self.conn.execute(
            "INSERT INTO podcast_job_events (job_id, at, from_status, to_status, note) "
            "VALUES (?,?,?,?,?)",
            (job_id, "2026-08-30T12:00:00Z", "received", "researching", note),
        )
        self.conn.commit()

    def _payload(self, job_id, payload):
        self.conn.execute(
            "INSERT INTO podcast_job_payloads (job_id, payload_json, stored_at) "
            "VALUES (?,?,?)",
            (job_id, json.dumps(payload), "2026-08-30T12:00:00Z"),
        )
        self.conn.commit()

    def _artifact(self, job_id, kind, content):
        self.conn.execute(
            "INSERT INTO podcast_step_artifacts (job_id, step, kind, sha256, content_json) "
            "VALUES (?,?,?,?,?)",
            (job_id, "4", kind, "deadbeef", json.dumps(content)),
        )
        self.conn.commit()

    def _row(self, job_id):
        return self.conn.execute(
            "SELECT * FROM podcast_jobs WHERE job_id = ?", (job_id,)).fetchone()


class PublishedGuestLookupTests(_DbCase):
    """THE REGRESSION CASE: one contact identifier, two fingerprint formats,
    one already published. The second must be seen as the same guest."""

    # The real shapes. The webhook stores its canonical job_key; the CLI path
    # stores a local sha256 over a narrower field set. Same guest, and the two
    # values can never be equal because they hash different things.
    WEBHOOK_JOB_KEY = "pd-MayaRandleGuest01-20260820-a1b2c3d4"
    LOCAL_SHA256 = "9f2c" + "0" * 60

    def test_two_fingerprint_formats_same_guest_is_still_one_guest(self):
        self.assertNotEqual(self.WEBHOOK_JOB_KEY, self.LOCAL_SHA256,
                            "fixture must use genuinely different fingerprint formats")
        self._insert_job("pj_published", "MayaRandleGuest01", self.WEBHOOK_JOB_KEY,
                         status="complete",
                         permalink="https://example.invalid/e/already-published/",
                         published_at="2026-08-20T15:00:00Z")
        self._insert_job("pj_queued", "MayaRandleGuest01", self.LOCAL_SHA256,
                         status="received")

        prior = PS.published_jobs_for_guest(self.conn, "thesoftgirlera",
                                            "MayaRandleGuest01",
                                            exclude_job_id="pj_queued")
        self.assertEqual([r["job_id"] for r in prior], ["pj_published"],
                         "the already-published episode for this guest must be found "
                         "even though the two fingerprints differ in FORMAT")

    def test_lookup_matches_across_spellings_of_the_contact_id(self):
        self._insert_job("pj_published", "MayaRandleGuest01", self.WEBHOOK_JOB_KEY,
                         status="complete", published_at="2026-08-20T15:00:00Z")
        for spelling in ("mayarandleguest01", "maya-randle-guest-01", "MAYARANDLEGUEST01"):
            prior = PS.published_jobs_for_guest(self.conn, "thesoftgirlera", spelling)
            self.assertEqual([r["job_id"] for r in prior], ["pj_published"],
                             "spelling %r must resolve to the same guest" % spelling)

    def test_permalink_alone_counts_as_published(self):
        # A job holding a live permalink is published even if status lags behind.
        self._insert_job("pj_pub", "MayaRandleGuest01", "fp-a", status="publishing",
                         permalink="https://example.invalid/e/live/")
        self.assertEqual(
            [r["job_id"] for r in PS.published_jobs_for_guest(
                self.conn, "thesoftgirlera", "MayaRandleGuest01")],
            ["pj_pub"])

    def test_unpublished_sibling_is_not_a_block(self):
        self._insert_job("pj_a", "MayaRandleGuest01", "fp-a", status="received")
        self._insert_job("pj_b", "MayaRandleGuest01", "fp-b", status="writing")
        self.assertEqual(
            PS.published_jobs_for_guest(self.conn, "thesoftgirlera",
                                        "MayaRandleGuest01", exclude_job_id="pj_b"),
            [], "a guest with no PUBLISHED episode must not be blocked")

    def test_other_clients_are_never_consulted(self):
        self._insert_job("pj_other", "MayaRandleGuest01", "fp-x", status="complete",
                         client_id="a-different-client",
                         published_at="2026-08-20T15:00:00Z")
        self.assertEqual(
            PS.published_jobs_for_guest(self.conn, "thesoftgirlera", "MayaRandleGuest01"),
            [], "client isolation: another client's episode is not this client's duplicate")


class RescueAdvanceDetectionTests(_DbCase):
    def test_historical_free_text_rescue_label_is_detected(self):
        # The exact shape recorded on 2026-08-30. A forward-only structured
        # marker would miss this, which is the whole point.
        self._insert_job("pj_queued", "MayaRandleGuest01", "fp-a")
        self._event("pj_queued", "SOP-PODCAST-07 activation rescue proof")
        found = PS.rescue_advance_notes(self.conn, "pj_queued")
        self.assertTrue(found, "a job force-advanced by the rescue path must be identifiable")
        self.assertIn("SOP-PODCAST-07", found[0])

    def test_canonical_marker_is_detected(self):
        self._insert_job("pj_queued", "MayaRandleGuest01", "fp-a")
        self._event("pj_queued", PS.RESCUE_ADVANCE_MARKER)
        self.assertTrue(PS.rescue_advance_notes(self.conn, "pj_queued"))

    def test_ordinary_production_notes_are_not_flagged(self):
        self._insert_job("pj_clean", "SomeoneElse01", "fp-b")
        for note in ("job created from intake payload",
                     "credit restored; resumed from queue",
                     "required-outputs WAIVED via --force-waiver [reason: x]: y",
                     "receipt complete: step=12.5 action=show-notes"):
            self._event("pj_clean", note)
        self.assertEqual(PS.rescue_advance_notes(self.conn, "pj_clean"), [],
                         "normal pipeline notes must not read as a rescue advance")


class SourceMaterialTests(_DbCase):
    def test_package_admitting_no_transcript_is_absent(self):
        self._insert_job("pj_queued", "MayaRandleGuest01", "fp-a")
        self._artifact("pj_queued", "research-package", {
            "topic": "enterprise AI procurement",
            "citations": ["Klarna", "Morgan Stanley"],
            "note": "No raw interview transcript was provided for this guest.",
        })
        verdict, detail = PS.source_material_verdict(self.conn, "pj_queued")
        self.assertEqual(verdict, "absent")
        self.assertIn("research-package", detail)

    def test_package_with_real_source_is_not_flagged(self):
        self._insert_job("pj_ok", "Guest02", "fp-b")
        self._artifact("pj_ok", "research-package", {
            "topic": "burnout", "transcript_excerpts": ["I quit at 29 ..."]})
        self._payload("pj_ok", {"q1_answer": "I quit my job at 29."})
        verdict, _ = PS.source_material_verdict(self.conn, "pj_ok")
        self.assertEqual(verdict, "present")

    def test_missing_evidence_is_unknown_not_absent(self):
        # Negative-result discipline: no evidence is not evidence of absence,
        # and UNKNOWN must never block.
        self._insert_job("pj_bare", "Guest03", "fp-c")
        verdict, _ = PS.source_material_verdict(self.conn, "pj_bare")
        self.assertEqual(verdict, "unknown")


class ReleaseGateTests(_DbCase):
    """assert_release_gates is the one chokepoint advance AND resume route through."""

    def _published_plus_queued(self):
        self._insert_job("pj_published", "MayaRandleGuest01",
                         "pd-MayaRandleGuest01-20260820-a1b2c3d4", status="complete",
                         permalink="https://example.invalid/e/already-published/",
                         published_at="2026-08-20T15:00:00Z")
        self._insert_job("pj_queued", "MayaRandleGuest01", "9f2c" + "0" * 60,
                         status="producing_audio")

    def test_publish_ward_transition_is_blocked_for_a_duplicate_guest(self):
        self._published_plus_queued()
        with self.assertRaises(PS.WriterRefused) as ctx:
            PS.assert_release_gates(self.conn, "pj_queued",
                                    self._row("pj_queued"), "publishing")
        self.assertIn("ALREADY PUBLISHED", str(ctx.exception))

    def test_every_publish_ward_status_is_gated(self):
        self._published_plus_queued()
        for target in ("publishing", "enrolling", "complete"):
            with self.assertRaises(PS.WriterRefused):
                PS.assert_release_gates(self.conn, "pj_queued",
                                        self._row("pj_queued"), target)

    def test_earlier_production_stages_are_not_gated(self):
        self._published_plus_queued()
        for target in ("researching", "writing", "in_qc", "generating_art",
                       "producing_audio"):
            self.assertEqual(
                PS.assert_release_gates(self.conn, "pj_queued",
                                        self._row("pj_queued"), target), [],
                "a blocked job must still be workable up to the publish step")

    def test_rescue_advanced_job_is_blocked_on_its_own(self):
        self._insert_job("pj_rescued", "SoloGuest09", "fp-z", status="producing_audio")
        self._event("pj_rescued", "SOP-PODCAST-07 activation rescue proof")
        with self.assertRaises(PS.WriterRefused) as ctx:
            PS.assert_release_gates(self.conn, "pj_rescued",
                                    self._row("pj_rescued"), "publishing")
        self.assertIn("FORCE-ADVANCED", str(ctx.exception))

    def test_no_source_material_is_blocked_on_its_own(self):
        self._insert_job("pj_nosrc", "SoloGuest10", "fp-y", status="producing_audio")
        self._artifact("pj_nosrc", "research-package",
                       {"note": "no raw interview transcript was provided"})
        with self.assertRaises(PS.WriterRefused) as ctx:
            PS.assert_release_gates(self.conn, "pj_nosrc",
                                    self._row("pj_nosrc"), "publishing")
        self.assertIn("NO source material", str(ctx.exception))

    def test_clean_job_passes_the_gates(self):
        self._insert_job("pj_clean", "FreshGuest11", "fp-w", status="producing_audio")
        self.assertEqual(
            PS.assert_release_gates(self.conn, "pj_clean",
                                    self._row("pj_clean"), "publishing"), [])

    def test_release_is_per_job_and_must_name_the_job(self):
        self._published_plus_queued()
        row = self._row("pj_queued")
        # A release naming a DIFFERENT job does not lift this job's gate.
        os.environ[RELEASE_ENV] = "pj_some_other_job"
        try:
            with self.assertRaises(PS.WriterRefused):
                PS.assert_release_gates(self.conn, "pj_queued", row, "publishing")
            # A blanket truthy value is NOT a release either.
            os.environ[RELEASE_ENV] = "1"
            with self.assertRaises(PS.WriterRefused):
                PS.assert_release_gates(self.conn, "pj_queued", row, "publishing")
            # Naming THIS job releases it, and returns the findings for audit.
            os.environ[RELEASE_ENV] = "pj_queued"
            overridden = PS.assert_release_gates(self.conn, "pj_queued", row, "publishing")
            self.assertTrue(overridden, "an override must hand back findings to audit")
        finally:
            os.environ.pop(RELEASE_ENV, None)


class CliEndToEndTests(_DbCase):
    """Exit codes and audit rows through the real CLI, the way callers use it."""

    def _ps(self, *args, env=None):
        return subprocess.run([sys.executable, str(_SCRIPT), *args],
                              capture_output=True, text=True, timeout=60,
                              env=env or self.env)

    def _payload_file(self, body):
        path = os.path.join(self.tmp, "payload.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(body))
        return path

    def test_create_refuses_a_second_submission_for_a_published_guest(self):
        self._insert_job("pj_published", "MayaRandleGuest01",
                         "pd-MayaRandleGuest01-20260820-a1b2c3d4", status="complete",
                         permalink="https://example.invalid/e/already-published/",
                         published_at="2026-08-20T15:00:00Z")
        payload = self._payload_file({"q1_answer": "a completely different answer"})
        # Different job_key => a DIFFERENT fingerprint => the byte-comparison
        # idempotency check cannot see it. The guest identity must.
        res = self._ps("create", "--client-id", "thesoftgirlera", "--location-id", "loc",
                       "--contact-id", "MayaRandleGuest01",
                       "--mode", "interview_style_podcast", "--style", "vulnerable",
                       "--payload-file", payload, "--job-key", "a-brand-new-job-key")
        self.assertEqual(res.returncode, 4, res.stderr)
        self.assertIn("ALREADY PUBLISHED", res.stderr)
        count = self.conn.execute("SELECT count(*) FROM podcast_jobs").fetchone()[0]
        self.assertEqual(count, 1, "the refused submission must not have been created")

    def test_create_still_works_for_a_guest_with_no_published_episode(self):
        payload = self._payload_file({"q1_answer": "first time on the show"})
        res = self._ps("create", "--client-id", "thesoftgirlera", "--location-id", "loc",
                       "--contact-id", "BrandNewGuest77",
                       "--mode", "interview_style_podcast", "--style", "vulnerable",
                       "--payload-file", payload, "--job-key", "k-new")
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_advance_to_publishing_refused_with_exit_4(self):
        self._insert_job("pj_published", "MayaRandleGuest01", "pd-maya-20260820",
                         status="complete",
                         permalink="https://example.invalid/e/already-published/",
                         published_at="2026-08-20T15:00:00Z")
        self._insert_job("pj_queued", "MayaRandleGuest01", "9f2c" + "0" * 60,
                         status="producing_audio")
        res = self._ps("advance", "--job-id", "pj_queued", "--to", "publishing")
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        self.assertIn("ALREADY PUBLISHED", res.stderr)
        self.assertEqual(self._row("pj_queued")["status"], "producing_audio",
                         "a refused advance must not move the job")

    def test_resume_into_publishing_is_gated_too(self):
        # A held job resumes DIRECTLY to its resume_stage. That path had no gate.
        self._insert_job("pj_published", "MayaRandleGuest01", "pd-maya-20260820",
                         status="complete",
                         permalink="https://example.invalid/e/already-published/",
                         published_at="2026-08-20T15:00:00Z")
        self._insert_job("pj_held", "MayaRandleGuest01", "9f2c" + "0" * 60,
                         status="queued_credit_out")
        self.conn.execute(
            "UPDATE podcast_jobs SET resume_stage = 'publishing', queue_state = 'held' "
            "WHERE job_id = 'pj_held'")
        self.conn.commit()
        res = self._ps("resume", "--job-id", "pj_held")
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        self.assertEqual(self._row("pj_held")["status"], "queued_credit_out",
                         "a refused resume must leave the job held")

    def test_rescue_proof_flag_stamps_a_durable_marker(self):
        payload = self._payload_file({"q1_answer": "real submission"})
        self.assertEqual(
            self._ps("create", "--client-id", "thesoftgirlera", "--location-id", "loc",
                     "--contact-id", "ProofGuest01", "--mode", "interview_style_podcast",
                     "--style", "vulnerable", "--payload-file", payload,
                     "--job-key", "k-proof").returncode, 0)
        jid = self.conn.execute(
            "SELECT job_id FROM podcast_jobs WHERE contact_id = 'ProofGuest01'"
        ).fetchone()[0]
        res = self._ps("advance", "--job-id", jid, "--to", "researching", "--rescue-proof")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(PS.rescue_advance_notes(self.conn, jid),
                        "--rescue-proof must leave a durable, detectable marker")

    def test_named_release_lets_a_blocked_advance_through_and_audits_it(self):
        self._insert_job("pj_published", "MayaRandleGuest01", "pd-maya-20260820",
                         status="complete",
                         permalink="https://example.invalid/e/already-published/",
                         published_at="2026-08-20T15:00:00Z")
        self._insert_job("pj_queued", "MayaRandleGuest01", "9f2c" + "0" * 60,
                         status="producing_audio")
        env = dict(self.env)
        env[RELEASE_ENV] = "pj_queued"
        res = self._ps("advance", "--job-id", "pj_queued", "--to", "publishing", env=env)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        audited = self.conn.execute(
            "SELECT count(*) FROM podcast_job_events WHERE note LIKE '%OVERRIDDEN%'"
        ).fetchone()[0]
        self.assertGreaterEqual(audited, 1, "a hand-lifted gate must never be silent")


if __name__ == "__main__":
    unittest.main()

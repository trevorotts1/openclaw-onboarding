#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: required-outputs advance gate (E7)
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network, no live DB: an in-memory schema for the gate
# unit tests and a throwaway file DB for the CLI end-to-end. Proves a producing
# stage cannot advance past a missing deliverable, that the gate is preset/mode
# aware (document-only and non-publishing presets are never falsely blocked),
# and that --force-waiver overrides the gate AND records an audit event.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_required_outputs.py
# =============================================================================
"""Deterministic tests for the required-outputs advance gate (E7)."""

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


def _row(status, mode="interview_style_podcast", **outputs):
    """Build a real sqlite3.Row from the shipped schema so check_transition sees
    exactly the runtime column set."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(PS.SCHEMA)
    conn.execute(
        "INSERT INTO podcast_jobs (job_id, client_id, location_id, contact_id, "
        "submission_fingerprint, mode, style, status) "
        "VALUES ('j','c','l','ct','fp',?,?,?)",
        (mode, "vulnerable", status),
    )
    for col, val in outputs.items():
        conn.execute("UPDATE podcast_jobs SET %s = ? WHERE job_id = 'j'" % col, (val,))
    return conn.execute("SELECT * FROM podcast_jobs WHERE job_id = 'j'").fetchone()


class GateUnitTests(unittest.TestCase):
    # -- preset flag resolution --------------------------------------------
    def test_mode_default_preset(self):
        self.assertEqual(PS.resolve_preset(None, "j", "interview_style_podcast"), "interview")
        self.assertEqual(PS.resolve_preset(None, "j", "personal_podcast_style"), "solo")

    def test_gate_produces_media_excludes_document_preset(self):
        self.assertTrue(PS._gate_satisfied("produces_media", PS.preset_flags("interview")))
        self.assertFalse(PS._gate_satisfied("produces_media", PS.preset_flags("season_strategy")))

    def test_book_teaser_gate_is_strict_true(self):
        # solo -> False; interview -> True; asset pack -> conditional string (not strict).
        self.assertTrue(PS._gate_satisfied("book_teaser", PS.preset_flags("interview")))
        self.assertFalse(PS._gate_satisfied("book_teaser", PS.preset_flags("solo")))
        self.assertFalse(PS._gate_satisfied("book_teaser", PS.preset_flags("episode_asset_pack")))

    # -- the gate blocks / passes on the producing transitions -------------
    def test_publish_transition_requires_audio_and_permalink(self):
        row = _row("publishing")  # interview, no outputs set
        missing = PS.missing_required_outputs(
            row, "publishing", "enrolling", PS.preset_flags("interview"))
        self.assertIn("mp3_media_url", missing)
        self.assertIn("podbean_permalink", missing)
        with self.assertRaises(PS.MissingRequiredOutputError):
            PS.check_transition(row, "enrolling", preset="interview")

    def test_publish_transition_passes_when_artifacts_present(self):
        row = _row("publishing", mp3_media_url="https://x/a.mp3",
                   episode_package_url="https://x/pkg",
                   podbean_permalink="https://pb/ep", book_teaser_url="https://x/t.pdf")
        # Must not raise.
        PS.check_transition(row, "enrolling", preset="interview")

    def test_complete_transition_backstops_core_deliverables(self):
        row = _row("enrolling", mp3_media_url="https://x/a.mp3",
                   episode_package_url="https://x/pkg", podbean_permalink="https://pb/ep",
                   cover_image_url="https://x/c.png")  # episode_title still missing
        with self.assertRaises(PS.MissingRequiredOutputError):
            PS.check_transition(row, "complete", preset="interview")
        row2 = _row("enrolling", mp3_media_url="https://x/a.mp3",
                    episode_package_url="https://x/pkg", podbean_permalink="https://pb/ep",
                    cover_image_url="https://x/c.png", episode_title="An Episode")
        PS.check_transition(row2, "complete", preset="interview")

    def test_art_transition_requires_cover(self):
        row = _row("generating_art")
        with self.assertRaises(PS.MissingRequiredOutputError):
            PS.check_transition(row, "producing_audio", preset="interview")
        row2 = _row("generating_art", cover_image_url="https://x/c.png")
        PS.check_transition(row2, "producing_audio", preset="interview")

    # -- preset/mode awareness: no false blocks ----------------------------
    def test_season_strategy_never_blocked(self):
        # Document-only preset: every producing transition passes with zero outputs.
        for frm, to in (("generating_art", "producing_audio"),
                        ("publishing", "enrolling"),
                        ("enrolling", "complete")):
            row = _row(frm, mode="interview_style_podcast")
            PS.check_transition(row, to, preset="season_strategy")

    def test_asset_pack_requires_media_not_permalink(self):
        # store_media True -> mp3+package required; publish_podbean False -> no permalink.
        row = _row("publishing")
        missing = PS.missing_required_outputs(
            row, "publishing", "enrolling", PS.preset_flags("episode_asset_pack"))
        self.assertIn("mp3_media_url", missing)
        self.assertIn("episode_package_url", missing)
        self.assertNotIn("podbean_permalink", missing)
        self.assertNotIn("book_teaser_url", missing)

    # -- the waiver escape -------------------------------------------------
    def test_force_waiver_suppresses_the_gate(self):
        row = _row("publishing")
        # Without waiver -> raises; with waiver -> returns.
        with self.assertRaises(PS.MissingRequiredOutputError):
            PS.check_transition(row, "enrolling", preset="interview", waiver=False)
        PS.check_transition(row, "enrolling", preset="interview", waiver=True)

    # -- non-producing transitions are untouched by the gate ---------------
    def test_hold_and_qc_loop_unaffected(self):
        PS.check_transition(_row("writing"), "queued_credit_out")  # hold path
        # QC revision loop needs no outputs.
        PS.check_transition(_row("in_qc"), "writing", preset="interview")


class GateCliEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="podcast-e7-")
        self.db = os.path.join(self.tmp, "state.db")
        self.payload = os.path.join(self.tmp, "payload.json")
        with open(self.payload, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"preset": "interview"}))
        self.env = dict(os.environ)
        self.env["PODCAST_DB_PATH"] = self.db

    def _ps(self, *args):
        return subprocess.run([sys.executable, str(_SCRIPT), *args],
                              capture_output=True, text=True, timeout=30, env=self.env)

    def test_cli_blocks_then_waives_with_audit(self):
        self._ps("create", "--client-id", "c", "--location-id", "l", "--contact-id", "ct",
                 "--mode", "interview_style_podcast", "--style", "vulnerable",
                 "--payload-file", self.payload, "--job-key", "k")
        jid = sqlite3.connect(self.db).execute(
            "SELECT job_id FROM podcast_jobs").fetchone()[0]
        for st in ("researching", "writing", "in_qc", "generating_art"):
            self.assertEqual(self._ps("advance", "--job-id", jid, "--to", st).returncode, 0)
        self._ps("output", "--job-id", jid, "--field", "cover_image_url", "--value", "https://x/c.png")
        self.assertEqual(self._ps("advance", "--job-id", jid, "--to", "producing_audio").returncode, 0)
        self.assertEqual(self._ps("advance", "--job-id", jid, "--to", "publishing").returncode, 0)

        blocked = self._ps("advance", "--job-id", jid, "--to", "enrolling")
        self.assertEqual(blocked.returncode, 3)
        self.assertIn("not yet recorded", blocked.stderr.lower())

        waived = self._ps("advance", "--job-id", jid, "--to", "enrolling", "--force-waiver")
        self.assertEqual(waived.returncode, 0)

        events = sqlite3.connect(self.db).execute(
            "SELECT count(*) FROM podcast_job_events WHERE note LIKE '%WAIVED%'").fetchone()[0]
        self.assertGreaterEqual(events, 1)


if __name__ == "__main__":
    unittest.main()

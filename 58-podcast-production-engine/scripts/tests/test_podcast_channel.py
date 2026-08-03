#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: two-show channel selector tests
# -----------------------------------------------------------------------------
# Stdlib unittest only. Fully offline: resolution runs against injected env
# dicts and the CLI runs as a subprocess with a controlled environment, so
# nothing leaves the box and no real credential is touched. Proves:
#   1. Mode normalization (canonical values plus the human forms the mapper
#      accepts at intake; non-modes refused).
#   2. SHOW_SLUG derivation (uppercase, underscore separated).
#   3. Channel selection BY MODE: personal reads PODBEAN_PODCAST_ID,
#      interview reads PODBEAN_PODCAST_ID_<SHOW_SLUG>.
#   4. The NO-FALLBACK guarantee: a missing interview channel never borrows
#      PODBEAN_PODCAST_ID, a missing personal channel never borrows a show
#      channel; the failure message names the exact missing env var.
#   5. A pre-resolved payload podcast_id wins as-is (controller precedence).
#   6. CLI contract: --check exit codes and label-only output, --print-var
#      prints the env var name only, default mode prints the resolved id.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_podcast_channel.py
# =============================================================================
"""Deterministic tests for the two-show mode-to-channel selector."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "podcast_channel.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("podcast_channel", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pc = _load_module()


def _run_cli(args, env_extra=None):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(_SCRIPT)] + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class TestModeNormalization(unittest.TestCase):
    def test_canonical_values_pass_through(self):
        self.assertEqual(pc.normalize_mode("personal_podcast_style"), "personal_podcast_style")
        self.assertEqual(pc.normalize_mode("interview_style_podcast"), "interview_style_podcast")

    def test_human_forms_accepted_case_insensitively(self):
        self.assertEqual(pc.normalize_mode("Personal"), "personal_podcast_style")
        self.assertEqual(pc.normalize_mode("Personal Podcast"), "personal_podcast_style")
        self.assertEqual(pc.normalize_mode("Interview"), "interview_style_podcast")
        self.assertEqual(pc.normalize_mode("Interview Style Podcast"), "interview_style_podcast")
        self.assertEqual(pc.normalize_mode("  interview   style podcast "), "interview_style_podcast")

    def test_non_modes_refused(self):
        for bad in ("season_strategy", "episode_asset_pack", "documentary", "", "   "):
            with self.assertRaises(pc.UnknownModeError, msg=repr(bad)):
                pc.normalize_mode(bad)

    def test_none_refused(self):
        with self.assertRaises(pc.UnknownModeError):
            pc.normalize_mode(None)


class TestShowSlug(unittest.TestCase):
    def test_upper_snake_case(self):
        self.assertEqual(pc.show_slug("Soft Girl Era"), "SOFT_GIRL_ERA")
        self.assertEqual(pc.show_slug("soft girl era"), "SOFT_GIRL_ERA")

    def test_punctuation_collapses_to_single_underscore(self):
        self.assertEqual(pc.show_slug("The Morning: Show!"), "THE_MORNING_SHOW")
        self.assertEqual(pc.show_slug("A & B's Pod"), "A_B_S_POD")

    def test_surrounding_noise_dropped(self):
        self.assertEqual(pc.show_slug("  --Soft Girl Era--  "), "SOFT_GIRL_ERA")

    def test_empty_gives_empty(self):
        self.assertEqual(pc.show_slug(""), "")
        self.assertEqual(pc.show_slug("!!!"), "")


class TestChannelEnvKey(unittest.TestCase):
    def test_personal_mode_uses_default_channel(self):
        self.assertEqual(pc.channel_env_key("personal_podcast_style"), "PODBEAN_PODCAST_ID")
        self.assertEqual(pc.channel_env_key("Solo"), "PODBEAN_PODCAST_ID")

    def test_interview_mode_uses_show_slug_var(self):
        key = pc.channel_env_key("interview_style_podcast", "Soft Girl Era")
        self.assertEqual(key, "PODBEAN_PODCAST_ID_SOFT_GIRL_ERA")

    def test_explicit_slug_accepted(self):
        key = pc.channel_env_key("interview_style_podcast", "SOFT_GIRL_ERA")
        self.assertEqual(key, "PODBEAN_PODCAST_ID_SOFT_GIRL_ERA")

    def test_interview_without_show_refused(self):
        with self.assertRaises(pc.UnknownShowError):
            pc.channel_env_key("interview_style_podcast", "")

    def test_unknown_mode_refused(self):
        with self.assertRaises(pc.UnknownModeError):
            pc.channel_env_key("season_strategy", "anything")


class TestResolveChannel(unittest.TestCase):
    def test_personal_mode_reads_default_channel(self):
        env = {"PODBEAN_PODCAST_ID": "chan-personal"}
        channel, key = pc.resolve_channel("personal_podcast_style", env=env)
        self.assertEqual(channel, "chan-personal")
        self.assertEqual(key, "PODBEAN_PODCAST_ID")

    def test_interview_mode_reads_show_channel(self):
        env = {
            "PODBEAN_PODCAST_ID": "chan-personal",
            "PODBEAN_PODCAST_ID_SOFT_GIRL_ERA": "chan-interview",
        }
        channel, key = pc.resolve_channel("interview_style_podcast", "Soft Girl Era", env=env)
        self.assertEqual(channel, "chan-interview")
        self.assertEqual(key, "PODBEAN_PODCAST_ID_SOFT_GIRL_ERA")

    def test_interview_missing_channel_never_borrows_personal(self):
        # The whole point of the no-fallback guarantee: the personal channel
        # is SET, but interview mode must refuse rather than publish the guest
        # episode to the personal show.
        env = {"PODBEAN_PODCAST_ID": "chan-personal"}
        with self.assertRaises(pc.ChannelError) as ctx:
            pc.resolve_channel("interview_style_podcast", "Soft Girl Era", env=env)
        self.assertIn("PODBEAN_PODCAST_ID_SOFT_GIRL_ERA", str(ctx.exception))
        self.assertNotIn("chan-personal", str(ctx.exception))

    def test_personal_missing_channel_never_borrows_show_channel(self):
        env = {"PODBEAN_PODCAST_ID_SOFT_GIRL_ERA": "chan-interview"}
        with self.assertRaises(pc.ChannelError) as ctx:
            pc.resolve_channel("personal_podcast_style", env=env)
        self.assertIn("PODBEAN_PODCAST_ID", str(ctx.exception))

    def test_empty_env_value_treated_as_missing(self):
        env = {"PODBEAN_PODCAST_ID": "   "}
        with self.assertRaises(pc.ChannelError):
            pc.resolve_channel("personal_podcast_style", env=env)

    def test_payload_podcast_id_wins_as_is(self):
        env = {"PODBEAN_PODCAST_ID": "chan-env"}
        channel, key = pc.resolve_channel(
            "personal_podcast_style", env=env, payload_podcast_id="chan-from-payload"
        )
        self.assertEqual(channel, "chan-from-payload")
        self.assertEqual(key, "PODBEAN_PODCAST_ID")

    def test_resolution_is_mode_specific_for_same_box(self):
        # A fully provisioned two-show box resolves a DIFFERENT channel per
        # mode; that is exactly what the publish step needs so the n8n
        # multi-row roster gate (channel-preferred selection) picks the right
        # show row.
        env = {
            "PODBEAN_PODCAST_ID": "chan-personal",
            "PODBEAN_PODCAST_ID_SOFT_GIRL_ERA": "chan-interview",
        }
        personal, _ = pc.resolve_channel("personal", env=env)
        interview, _ = pc.resolve_channel("interview", "Soft Girl Era", env=env)
        self.assertEqual(personal, "chan-personal")
        self.assertEqual(interview, "chan-interview")
        self.assertNotEqual(personal, interview)


class TestCli(unittest.TestCase):
    def test_check_ok_is_exit_zero_and_says_set(self):
        res = _run_cli(
            ["--mode", "personal", "--check"],
            {"PODBEAN_PODCAST_ID": "chan-personal"},
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("PODBEAN_PODCAST_ID is SET", res.stdout)
        # The value itself must never leak from a probe.
        self.assertNotIn("chan-personal", res.stdout)
        self.assertNotIn("chan-personal", res.stderr)

    def test_check_missing_is_exit_one_naming_the_env_var(self):
        res = _run_cli(
            ["--mode", "interview", "--show-name", "Soft Girl Era", "--check"],
            {"PODBEAN_PODCAST_ID": "chan-personal"},
        )
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("PODBEAN_PODCAST_ID_SOFT_GIRL_ERA", res.stderr)
        # No cross-show borrowing: the diagnosis names only the missing var.
        self.assertNotIn("chan-personal", res.stderr)

    def test_default_invocation_prints_resolved_channel(self):
        res = _run_cli(
            ["--mode", "interview", "--show-name", "Soft Girl Era"],
            {"PODBEAN_PODCAST_ID_SOFT_GIRL_ERA": "chan-interview"},
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "chan-interview")

    def test_print_var_emits_label_only(self):
        res = _run_cli(
            ["--mode", "interview", "--show-name", "Soft Girl Era", "--print-var"],
            {},  # no channel env at all: label probe must still succeed
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "PODBEAN_PODCAST_ID_SOFT_GIRL_ERA")

    def test_explicit_show_slug_flag_wins(self):
        res = _run_cli(
            ["--mode", "interview", "--show-slug", "SOFT_GIRL_ERA", "--print-var"],
            {},
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "PODBEAN_PODCAST_ID_SOFT_GIRL_ERA")

    def test_payload_podcast_id_override(self):
        res = _run_cli(
            ["--mode", "personal", "--payload-podcast-id", "chan-override", "--check"],
            {},  # env empty: the explicit payload value must win
        )
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_unknown_mode_refused_by_cli(self):
        res = _run_cli(["--mode", "season_strategy", "--check"], {})
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)


class TestFleetGuards(unittest.TestCase):
    def test_no_em_dash_in_source(self):
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("\u2014", text)

    def test_no_triple_backtick_fences_in_source(self):
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("`" * 3, text)

    def test_env_contract_matches_skill_convention(self):
        # The exact label names are the contract with SOP-PODCAST-02 (2.5),
        # SKILL.md, and podbean_publish.sh; pin them here so a rename cannot
        # slip past review.
        self.assertEqual(pc.DEFAULT_CHANNEL_ENV, "PODBEAN_PODCAST_ID")
        self.assertEqual(pc.MODE_ENV_KEY["personal_podcast_style"], "PODBEAN_PODCAST_ID")
        self.assertEqual(
            pc.MODE_ENV_KEY["interview_style_podcast"], "PODBEAN_PODCAST_ID_<SHOW_SLUG>"
        )


if __name__ == "__main__":
    unittest.main()

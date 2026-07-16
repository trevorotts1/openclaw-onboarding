#!/usr/bin/env python3
"""Unit tests for winner_harvest.py — A-U11 (master unit U11): winner-harvest
flywheel: >=9.0 outputs -> operator-approved card -> CLIENT-LOCAL exemplar
library. stdlib only, no network, no key, no live Command Center board.

Proves the master-spec v2 A.10 A-U11 binary acceptance, verbatim:
  (a) a >=9.0 fixture output produces exactly ONE approval card, idempotent
      across repeated sweeps.
  (b) no candidate enters the library without an approved card (a guard
      test asserts the write is card-gated).
  (c) the library path resolves inside the client workspace and a test
      asserts it is NOT under the repo tree.
  (d) a two-client fixture proves zero cross-client visibility.

  python3 -m unittest shared-utils/test_winner_harvest.py
  (or)  python3 shared-utils/test_winner_harvest.py
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winner_harvest as wh  # noqa: E402
import exemplar_injection as exi  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _candidate(client_id, slug, *, score=9.4, task_id="task-1",
               deliverable_type="lead", skill="06-ghl-install-pages"):
    return {
        "client_id": client_id, "skill": skill,
        "deliverable_type": deliverable_type, "slug": slug, "qc_score": score,
        "source_task_id": task_id,
        "gold_output_text": f"# {slug}\n\nHero copy for {client_id} / {slug}.",
        "why_good_text": "Clean close, on-register, converts.",
    }


class TestAcceptanceAIdempotentSingleCard(unittest.TestCase):
    """(a) a >=9.0 fixture output produces exactly ONE approval card,
    idempotent across repeated sweeps."""

    def test_repeated_sweeps_never_duplicate_the_card(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand = _candidate("client-a", "optin-1")
            for _ in range(5):
                wh.run_harvest_sweep(ws, [cand])
            ledger_path = os.path.join(ws, "client-a", "routing", "harvest-cards.json")
            with open(ledger_path, encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual(len(doc["cards"]), 1)

    def test_propose_harvest_card_returns_the_same_record_object(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand = _candidate("client-a", "optin-2")
            first = wh.propose_harvest_card(ws, cand)
            second = wh.propose_harvest_card(ws, cand)
            self.assertEqual(first["card_id"], second["card_id"])
            self.assertEqual(first["candidate_id"], second["candidate_id"])

    def test_below_threshold_candidate_proposes_no_card(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            low = _candidate("client-a", "weak-optin", score=8.9)
            result = wh.run_harvest_sweep(ws, [low])
            self.assertEqual(result["proposed"], [])
            self.assertIn("weak-optin", result["below_threshold"])
            self.assertFalse(os.path.isfile(
                os.path.join(ws, "client-a", "routing", "harvest-cards.json")))

    def test_exactly_at_threshold_is_eligible(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            at_floor = _candidate("client-a", "floor-optin", score=wh.HARVEST_THRESHOLD)
            result = wh.run_harvest_sweep(ws, [at_floor])
            self.assertEqual(len(result["proposed"]), 1)


class TestAcceptanceBCardGatedWrite(unittest.TestCase):
    """(b) no candidate enters the library without an approved card (a
    guard test asserts the write is card-gated)."""

    def test_harvest_refused_with_no_card_at_all(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand = _candidate("client-a", "no-card-optin")
            result = wh.harvest_into_library(ws, cand, None)
            self.assertFalse(result["harvested"])
            self.assertEqual(result["reason"], "card_not_approved")
            pack_dir = wh.library_dir_for_candidate(ws, cand)
            self.assertFalse(os.path.isdir(pack_dir))

    def test_harvest_refused_while_card_is_pending(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand = _candidate("client-a", "pending-optin")
            card = wh.propose_harvest_card(ws, cand)
            self.assertEqual(card["status"], "pending_approval")
            result = wh.harvest_into_library(ws, cand, card)
            self.assertFalse(result["harvested"])
            self.assertEqual(result["reason"], "card_not_approved")
            pack_dir = wh.library_dir_for_candidate(ws, cand)
            self.assertTrue(not os.path.isdir(pack_dir) or not os.listdir(pack_dir))

    def test_harvest_succeeds_only_after_explicit_approval(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand = _candidate("client-a", "approved-optin")
            card = wh.propose_harvest_card(ws, cand)
            approved = wh.approve_card(ws, "client-a", card["card_id"],
                                        approved_by="trevor-fixture")
            self.assertTrue(wh.is_card_approved(approved))
            result = wh.harvest_into_library(ws, cand, approved)
            self.assertTrue(result["harvested"])
            pack_dir = wh.library_dir_for_candidate(ws, cand)
            for fname in ("gold-output.md", "WHY-GOOD.md", "provenance.json"):
                self.assertTrue(os.path.isfile(os.path.join(pack_dir, fname)))

    def test_harvest_refused_on_a_mismatched_approved_card(self):
        # An approved card for a DIFFERENT candidate must never authorize
        # writing THIS candidate's output — the gate checks candidate
        # identity, not just "some approved card was handed in".
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand_a = _candidate("client-a", "real-optin")
            cand_b = _candidate("client-a", "other-optin", task_id="task-other")
            card_b = wh.propose_harvest_card(ws, cand_b)
            approved_b = wh.approve_card(ws, "client-a", card_b["card_id"],
                                          approved_by="trevor-fixture")
            result = wh.harvest_into_library(ws, cand_a, approved_b)
            self.assertFalse(result["harvested"])
            self.assertEqual(result["reason"], "card_candidate_mismatch")

    def test_empty_gold_output_is_never_harvested_even_when_approved(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand = _candidate("client-a", "empty-optin")
            cand["gold_output_text"] = "   "
            card = wh.propose_harvest_card(ws, cand)
            approved = wh.approve_card(ws, "client-a", card["card_id"],
                                        approved_by="trevor-fixture")
            result = wh.harvest_into_library(ws, cand, approved)
            self.assertFalse(result["harvested"])
            self.assertEqual(result["reason"], "empty_gold_output")

    def test_approve_card_never_fabricates_a_card_that_was_not_proposed(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            result = wh.approve_card(ws, "client-a", "harvest-doesnotexist",
                                      approved_by="trevor-fixture")
            self.assertIsNone(result)


class TestAcceptanceCLibraryOutsideRepoTree(unittest.TestCase):
    """(c) the library path resolves inside the client workspace and a test
    asserts it is NOT under the repo tree."""

    def test_library_path_not_under_repo_tree_caller_supplied_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand = _candidate("client-a", "path-check-optin")
            pack_dir = wh.library_dir_for_candidate(ws, cand)
            repo_real = os.path.realpath(_REPO_ROOT)
            pack_real = os.path.realpath(pack_dir)
            self.assertFalse(pack_real.startswith(repo_real + os.sep))
            self.assertTrue(pack_real.startswith(os.path.realpath(ws) + os.sep))

    def test_default_resolution_also_stays_outside_repo_tree(self):
        with tempfile.TemporaryDirectory() as fake_home:
            base = wh.resolve_workspace_base({"HOME": fake_home})
            repo_real = os.path.realpath(_REPO_ROOT)
            self.assertFalse(os.path.realpath(base).startswith(repo_real + os.sep))
            self.assertTrue(base.startswith(fake_home))

    def test_explicit_env_override_takes_precedence_over_home(self):
        base = wh.resolve_workspace_base(
            {"HOME": "/should/not/win", "CLIENT_WORKSPACE_BASE_DIR": "/explicit/base"})
        self.assertEqual(base, "/explicit/base")

    def test_no_home_no_override_resolves_empty_never_a_repo_fallback(self):
        base = wh.resolve_workspace_base({})
        self.assertEqual(base, "")


class TestAcceptanceDZeroCrossClientVisibility(unittest.TestCase):
    """(d) a two-client fixture proves zero cross-client visibility."""

    def _harvest_for(self, ws, client_id, slug):
        cand = _candidate(client_id, slug, task_id=f"task-{client_id}")
        card = wh.propose_harvest_card(ws, cand)
        approved = wh.approve_card(ws, client_id, card["card_id"], approved_by="op")
        result = wh.harvest_into_library(ws, cand, approved)
        self.assertTrue(result["harvested"])
        return cand, card, result["pack_dir"]

    def test_two_clients_same_slug_land_in_disjoint_directories(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            _, _, pack_a = self._harvest_for(ws, "client-alpha", "shared-slug-name")
            _, _, pack_b = self._harvest_for(ws, "client-beta", "shared-slug-name")
            self.assertNotEqual(os.path.realpath(pack_a), os.path.realpath(pack_b))

    def test_ledgers_never_cross_reference_the_other_clients_cards(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            _, card_a, _ = self._harvest_for(ws, "client-alpha", "slug-x")
            _, card_b, _ = self._harvest_for(ws, "client-beta", "slug-y")

            ledger_a = wh._load_ledger(ws, "client-alpha")
            ledger_b = wh._load_ledger(ws, "client-beta")
            ids_a = {c["card_id"] for c in ledger_a["cards"]}
            ids_b = {c["card_id"] for c in ledger_b["cards"]}
            self.assertNotIn(card_b["card_id"], ids_a)
            self.assertNotIn(card_a["card_id"], ids_b)

    def test_beta_client_id_never_appears_in_alphas_on_disk_files(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            _, _, pack_a = self._harvest_for(ws, "client-alpha", "slug-x")
            self._harvest_for(ws, "client-beta", "slug-y")

            for fname in ("gold-output.md", "WHY-GOOD.md", "provenance.json"):
                with open(os.path.join(pack_a, fname), encoding="utf-8") as f:
                    text = f.read()
                self.assertNotIn("client-beta", text)

    def test_candidate_id_is_client_scoped(self):
        # Two candidates identical in EVERY field except client_id must never
        # compute the same candidate id. The id is what harvest_into_library's
        # gate compares, so an id collision across clients would let one
        # client's approval authorize another client's write.
        a = _candidate("client-alpha", "same-slug", task_id="same-task")
        b = _candidate("client-beta", "same-slug", task_id="same-task")
        self.assertNotEqual(wh.candidate_id(a), wh.candidate_id(b))

    def test_another_clients_approved_card_never_authorizes_this_clients_write(self):
        # The sharpest edge of acceptance (d): alpha's operator approval,
        # handed in for beta's otherwise-identical candidate, must be refused
        # and must leave beta's library untouched.
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand_a = _candidate("client-alpha", "same-slug", task_id="same-task")
            cand_b = _candidate("client-beta", "same-slug", task_id="same-task")
            card_a = wh.propose_harvest_card(ws, cand_a)
            approved_a = wh.approve_card(ws, "client-alpha", card_a["card_id"],
                                          approved_by="op")
            self.assertTrue(wh.is_card_approved(approved_a))

            result = wh.harvest_into_library(ws, cand_b, approved_a)
            self.assertFalse(result["harvested"])
            self.assertEqual(result["reason"], "card_candidate_mismatch")
            self.assertFalse(os.path.isdir(wh.library_dir_for_candidate(ws, cand_b)))

    def test_alphas_library_listing_never_includes_a_beta_entry(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            self._harvest_for(ws, "client-alpha", "slug-x")
            self._harvest_for(ws, "client-beta", "slug-y")

            alpha_skill_dir = os.path.join(ws, "client-alpha", "06-ghl-install-pages")
            packs = exi.discover_packs(alpha_skill_dir, deliverable_type="lead")
            slugs = {p["slug"] for p in packs}
            self.assertIn("slug-x", slugs)
            self.assertNotIn("slug-y", slugs)


class TestFlywheelClosesTheLoopIntoExemplarInjection(unittest.TestCase):
    """The harvested pack is not just files on disk — it round-trips through
    the EXACT same discovery/selection/injection-block code A-U9 already
    ships, proving the flywheel actually closes (a client's own winner
    becomes that SAME client's next calibration exemplar) with zero new
    discovery code."""

    def test_harvested_pack_is_discoverable_and_injectable(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand = _candidate("client-alpha", "flywheel-optin", score=9.7)
            card = wh.propose_harvest_card(ws, cand)
            approved = wh.approve_card(ws, "client-alpha", card["card_id"],
                                        approved_by="op")
            wh.harvest_into_library(ws, cand, approved)

            skill_dir = os.path.join(ws, "client-alpha", "06-ghl-install-pages")
            selected = exi.select_exemplars(skill_dir, "lead")
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]["slug"], "flywheel-optin")

            block = exi.build_injection_block(selected)
            self.assertIsNotNone(block)
            self.assertIn("CALIBRATION ONLY", block)
            self.assertIn(cand["gold_output_text"].splitlines()[-1], block)


class TestRevertPosture(unittest.TestCase):
    """REVERT: one flag, no code revert; client-local library directories
    are untouched by flipping it."""

    def test_flag_off_is_a_clean_noop_nothing_written(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            os.environ[wh.ENV_FLAG] = "0"
            try:
                cand = _candidate("client-gamma", "revert-optin")
                result = wh.run_harvest_sweep(ws, [cand])
                self.assertFalse(result["enabled"])
                self.assertEqual(result["harvested"], [])
                self.assertFalse(os.path.isfile(
                    os.path.join(ws, "client-gamma", "routing", "harvest-cards.json")))
            finally:
                os.environ.pop(wh.ENV_FLAG, None)

    def test_flag_off_does_not_touch_a_library_harvested_while_on(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            cand = _candidate("client-gamma", "already-harvested-optin")
            card = wh.propose_harvest_card(ws, cand)
            approved = wh.approve_card(ws, "client-gamma", card["card_id"],
                                        approved_by="op")
            wh.harvest_into_library(ws, cand, approved)
            pack_dir = wh.library_dir_for_candidate(ws, cand)
            with open(os.path.join(pack_dir, "gold-output.md"), encoding="utf-8") as f:
                before = f.read()

            os.environ[wh.ENV_FLAG] = "0"
            try:
                wh.run_harvest_sweep(ws, [cand])
            finally:
                os.environ.pop(wh.ENV_FLAG, None)

            with open(os.path.join(pack_dir, "gold-output.md"), encoding="utf-8") as f:
                after = f.read()
            self.assertEqual(before, after)


class TestIdentityValidation(unittest.TestCase):
    """A candidate missing an identity field is a caller bug (never silently
    absorbed into the wrong client's tree)."""

    def test_missing_client_id_raises(self):
        cand = _candidate("client-a", "some-slug")
        del cand["client_id"]
        with self.assertRaises(ValueError):
            wh.candidate_id(cand)

    def test_sweep_records_identity_errors_and_continues(self):
        with tempfile.TemporaryDirectory() as td:
            ws = os.path.join(td, "workspaces")
            bad = _candidate("client-a", "bad-slug")
            del bad["skill"]
            good = _candidate("client-a", "good-slug")
            result = wh.run_harvest_sweep(ws, [bad, good])
            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(len(result["proposed"]), 1)


if __name__ == "__main__":
    unittest.main()

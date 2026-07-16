#!/usr/bin/env python3
"""tests/unit/u10-anti-copy-guard.test.py — U10 (A-U10, master-spec v2 A.9):
Anti-copy guard — deterministic similarity ceiling vs injected exemplars,
key-free, hard-miss.

Proves the master-spec v2 A.10 A-U10 binary acceptance, verbatim:

  (a) a copy-through fixture (an exemplar with cosmetic edits) is
      hard-failed by the guard.
  (b) a genuinely fresh fixture on the same topic passes.
  (c) the guard runs with NO network/key on a bare checkout
      (dependency-free test).
  (d) the ceiling value is asserted by a Continuous-Integration guard so it
      cannot drift silently.

(a) and (b) are proven twice: once directly against ``anti_copy_guard.py``
(the deterministic core), and once wired end-to-end through
``fab_qc.grade()`` / ``fab_qc.load_inputs_from_evidence()`` against the REAL
shipped A-U9 exemplar (``06-ghl-install-pages/exemplars/lead/
clarity-call-optin/gold-output.md``) via a real ``routing/
exemplar-injection.json`` receipt — proving the guard is genuinely wired
into "the fab-QC hard-miss family" (the A.9 build text), not merely a
standalone module nothing calls.

Run:
    python3 tests/unit/u10-anti-copy-guard.test.py
    or: pytest tests/unit/u10-anti-copy-guard.test.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent            # tests/unit/
_REPO_ROOT = _HERE.parent.parent         # repo root
_SHARED = _REPO_ROOT / "shared-utils"
_REAL_EXEMPLAR = (_REPO_ROOT / "06-ghl-install-pages" / "exemplars" / "lead"
                  / "clarity-call-optin" / "gold-output.md")

assert _SHARED.is_dir(), f"shared-utils not found at {_SHARED}"
assert _REAL_EXEMPLAR.is_file(), f"shipped A-U9 exemplar not found at {_REAL_EXEMPLAR}"

sys.path.insert(0, str(_SHARED))


def _load(modname: str):
    spec = importlib.util.spec_from_file_location(modname, _SHARED / f"{modname}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod           # required so @dataclass resolves cls.__module__
    spec.loader.exec_module(mod)
    return mod


acg = _load("anti_copy_guard")
fab_qc = _load("fab_qc")

# (c) dependency-free proof: the module's own import list is stdlib-only.
_STDLIB_ONLY_IMPORTS = {"__future__", "json", "os", "re", "time", "typing", "argparse", "sys"}

with open(_REAL_EXEMPLAR, encoding="utf-8") as _f:
    _REAL_EXEMPLAR_TEXT = _f.read()

# The exemplar's own hero + sub-head paragraph, cosmetically edited: swapped
# nouns ("Discovery" for "Clarity", "current" for "existing", "stuff" for
# "things", "messages" for "questions", "consultants" for "coaches"), one
# clause reordered, punctuation touched — exactly what a copy-through writer
# who "lightly reworded" the exemplar would ship.
_COPY_THROUGH_TEXT = (
    "Stop Guessing Which Offer To Build Next Right Now\n\n"
    "A free 20-minute Discovery Call where we map the one offer your current "
    "audience is already asking you for — so you stop building stuff nobody "
    "asked for and start building the thing they will actually pay for.\n\n"
    "You already have the raw material: the DMs, the comments, the \"how do I "
    "work with you\" messages piling up in your inbox. Most consultants never "
    "go back and read them as a pattern. We do. In twenty minutes, we hand "
    "you the pattern."
)

# A genuinely fresh lead-magnet optin on the identical topic (audience
# messages -> named offer), same rough length, zero shared phrasing.
_FRESH_TEXT = (
    "Your Best Clients Already Told You What To Sell\n\n"
    "Book a complimentary fifteen-minute Momentum Session and we will dig "
    "through the questions your community keeps sending you, then hand back "
    "the exact program idea hiding inside them, so your next launch is built "
    "on proof instead of a guess.\n\n"
    "Think about every reply, comment, and inbox message you have received "
    "this quarter. Buried in there is a pattern almost nobody stops to name. "
    "That is our entire job on this call: name it, then hand it back to you "
    "in plain, usable words."
)


class TestAcceptanceCDependencyFree(unittest.TestCase):
    """(c) the guard runs with NO network/key on a bare checkout
    (dependency-free test)."""

    def test_module_imports_stdlib_only(self):
        src = (_SHARED / "anti_copy_guard.py").read_text(encoding="utf-8")
        top_level_imports = [
            line.split()[1].split(".")[0]
            for line in src.splitlines()
            if line.startswith("import ") or line.startswith("from ")
        ]
        for name in top_level_imports:
            self.assertIn(
                name, _STDLIB_ONLY_IMPORTS,
                f"anti_copy_guard.py imports non-stdlib module {name!r} — "
                "acceptance (c) requires zero dependencies")

    def test_no_env_key_or_network_required_to_run(self):
        # A clean environment (no *_API_KEY / *_TOKEN of any kind) still
        # produces a correct, deterministic verdict.
        env_backup = dict(os.environ)
        try:
            for k in list(os.environ):
                if "KEY" in k.upper() or "TOKEN" in k.upper() or "SECRET" in k.upper():
                    os.environ.pop(k, None)
            pack = {"exemplar_id": "fixture/dep-free", "text": _REAL_EXEMPLAR_TEXT}
            result = acg.anti_copy_check([_COPY_THROUGH_TEXT], [pack])
            self.assertTrue(result["hard_miss"])
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_same_box_same_result_deterministic(self):
        pack = {"exemplar_id": "fixture/det", "text": _REAL_EXEMPLAR_TEXT}
        r1 = acg.anti_copy_check([_COPY_THROUGH_TEXT], [pack])
        r2 = acg.anti_copy_check([_COPY_THROUGH_TEXT], [pack])
        self.assertEqual(r1, r2)


class TestAcceptanceDCeilingLockedByCI(unittest.TestCase):
    """(d) the ceiling value is asserted by a Continuous-Integration guard
    so it cannot drift silently. This test IS that assertion — it runs in
    CI on every push/PR touching shared-utils/anti_copy_guard.py (see
    .github/workflows/u10-anti-copy-guard.yml) and fails the build the
    moment SIMILARITY_CEILING (or the shingle size the calibration in the
    module docstring depends on) changes without a matching, reviewed
    change to this file."""

    def test_similarity_ceiling_is_the_calibrated_locked_value(self):
        self.assertEqual(
            acg.SIMILARITY_CEILING, 0.55,
            "SIMILARITY_CEILING drifted from its calibrated value (0.55) — "
            "update this assertion ONLY with a deliberate, reviewed "
            "recalibration, never as a side effect of an unrelated change")

    def test_shingle_size_is_the_calibrated_locked_value(self):
        self.assertEqual(acg.CHAR_SHINGLE_K, 5)

    def test_ceiling_is_a_real_fraction_never_zero_or_one(self):
        # A guard rail against a future edit that quietly turns the ceiling
        # into a no-op (>= 1.0 = nothing ever breaches) or a false-positive
        # machine (<= 0.0 = everything breaches).
        self.assertGreater(acg.SIMILARITY_CEILING, 0.0)
        self.assertLess(acg.SIMILARITY_CEILING, 1.0)

    def test_calibration_gap_holds_against_the_real_shipped_exemplar(self):
        # Re-derives the calibration proof from the module docstring against
        # the ACTUAL on-disk exemplar (not a hand-copied snippet) — if a
        # future edit to the shipped gold-output.md narrows the real
        # copy-through/fresh gap below the ceiling on either side, this
        # fails loudly instead of the guard silently going blind.
        copy_through_sim = acg.similarity(_COPY_THROUGH_TEXT, _REAL_EXEMPLAR_TEXT)["max"]
        fresh_sim = acg.similarity(_FRESH_TEXT, _REAL_EXEMPLAR_TEXT)["max"]
        self.assertGreater(copy_through_sim, acg.SIMILARITY_CEILING,
                            "copy-through fixture no longer clears the ceiling")
        self.assertLess(fresh_sim, acg.SIMILARITY_CEILING,
                         "fresh fixture no longer stays under the ceiling")


class TestAcceptanceACopyThroughHardFails(unittest.TestCase):
    """(a) a copy-through fixture (an exemplar with cosmetic edits) is
    hard-failed by the guard."""

    def test_standalone_guard_hard_fails_the_copy_through_fixture(self):
        pack = {"exemplar_id": "06-ghl-install-pages/lead/clarity-call-optin",
                "text": _REAL_EXEMPLAR_TEXT}
        result = acg.anti_copy_check([_COPY_THROUGH_TEXT], [pack])
        self.assertTrue(result["hard_miss"])
        self.assertEqual(result["breached_exemplars"],
                          ["06-ghl-install-pages/lead/clarity-call-optin"])

    def test_wired_into_fab_qc_grade_hard_misses_naming_anti_copy(self):
        inp = _minimal_fab_qc_input(_COPY_THROUGH_TEXT)
        r = fab_qc.grade(inp)
        self.assertFalse(r["passed"], r)
        self.assertIn("D-anti-copy Anti-copy guard", r["hard_misses"])

    def test_end_to_end_via_load_inputs_from_evidence_real_receipt(self):
        # Builds a REAL evidence tree: A-U9's own exemplar-injection.json
        # shape, naming the ACTUAL shipped exemplar id, plus a fab-artifact
        # whose copy is the copy-through fixture — proving the resolver in
        # fab_qc.load_inputs_from_evidence finds the real on-disk exemplar
        # and the guard fires from a genuine evidence-tree read, not a
        # hand-assembled inp dict.
        with tempfile.TemporaryDirectory() as td:
            routing = os.path.join(td, "routing")
            os.makedirs(routing, exist_ok=True)
            with open(os.path.join(routing, "exemplar-injection.json"), "w") as f:
                json.dump({"injections": [{
                    "page": "Optin", "deliverable_type": "lead", "injected": True,
                    "exemplars": [{
                        "exemplar_id": "06-ghl-install-pages/lead/clarity-call-optin",
                        "skill": "06-ghl-install-pages", "deliverable_type": "lead",
                        "slug": "clarity-call-optin", "content_hash": "sha256:irrelevant",
                    }],
                }]}, f)
            build_dir = os.path.join(td, "build")
            os.makedirs(build_dir, exist_ok=True)
            with open(os.path.join(build_dir, "fab-artifact.json"), "w") as f:
                json.dump({"pages": [{"copy": {"hero": _COPY_THROUGH_TEXT}}]}, f)

            resolved = fab_qc._load_exemplar_packs_from_receipt(td)
            self.assertEqual(len(resolved), 1)
            self.assertTrue(os.path.isfile(resolved[0]["gold_output_path"]))

            inp = fab_qc.load_inputs_from_evidence(td, "funnel")
            self.assertEqual(len(inp["exemplar_packs"]), 1)
            inp["match_decision"] = {"flex_decision": "CREATE_NEW"}
            inp["verify"] = {"overall_pass": True, "pages": [{"status": 200}]}
            inp["persona_log"] = "selected_persona: net-new persona chosen"
            r = fab_qc.grade(inp)
            self.assertIn("D-anti-copy Anti-copy guard", r["hard_misses"])
            self.assertFalse(r["passed"], r)


class TestAcceptanceBFreshFixturePasses(unittest.TestCase):
    """(b) a genuinely fresh fixture on the same topic passes."""

    def test_standalone_guard_passes_the_fresh_fixture(self):
        pack = {"exemplar_id": "06-ghl-install-pages/lead/clarity-call-optin",
                "text": _REAL_EXEMPLAR_TEXT}
        result = acg.anti_copy_check([_FRESH_TEXT], [pack])
        self.assertFalse(result["hard_miss"])
        self.assertEqual(result["breached_exemplars"], [])

    def test_wired_into_fab_qc_grade_does_not_hard_miss_anti_copy(self):
        inp = _minimal_fab_qc_input(_FRESH_TEXT)
        r = fab_qc.grade(inp)
        self.assertNotIn("D-anti-copy Anti-copy guard", r["hard_misses"], r)


class TestDegradeAndRevertPosture(unittest.TestCase):
    """No exemplar packs / flag off -> clean no-op, byte-identical to
    pre-A-U10 fab_qc behavior. REVERT: one flag, no code revert."""

    def test_no_exemplar_packs_is_byte_identical_to_pre_u10_grade(self):
        with_key_absent = _minimal_fab_qc_input(_COPY_THROUGH_TEXT)
        with_key_absent.pop("exemplar_packs", None)
        with_key_empty = _minimal_fab_qc_input(_COPY_THROUGH_TEXT)
        with_key_empty["exemplar_packs"] = []
        r1 = fab_qc.grade(with_key_absent)
        r2 = fab_qc.grade(with_key_empty)
        self.assertEqual(r1, r2)
        self.assertNotIn("D-anti-copy Anti-copy guard", r1["hard_misses"])

    def test_flag_off_reverts_to_no_op_without_a_code_change(self):
        os.environ["ANTI_COPY_GUARD_ENABLED"] = "0"
        try:
            inp = _minimal_fab_qc_input(_COPY_THROUGH_TEXT)
            r = fab_qc.grade(inp)
            self.assertNotIn("D-anti-copy Anti-copy guard", r["hard_misses"], r)
        finally:
            os.environ.pop("ANTI_COPY_GUARD_ENABLED", None)

    def test_weights_still_sum_to_100_unaffected_by_the_new_hard_miss_dim(self):
        # The anti-copy dim carries weight 0 — it must never perturb the
        # canonical six-dimension weighted score.
        self.assertEqual(sum(fab_qc.W.values()), 100)
        inp = _minimal_fab_qc_input(_COPY_THROUGH_TEXT)
        r = fab_qc.grade(inp)
        anti_copy_dim = next(d for d in r["dimensions"]
                              if d["name"] == "D-anti-copy Anti-copy guard")
        self.assertEqual(anti_copy_dim["weight"], 0)
        self.assertEqual(anti_copy_dim["earned"], 0.0)


def _minimal_fab_qc_input(hero_text: str) -> dict:
    """A minimal, otherwise-passing funnel `inp` (mirrors fab-qc.test.py's own
    _faithful_funnel fixture) with `exemplar_packs` wired so ONLY the
    anti-copy guard's own verdict is under test — every other dimension
    passes regardless of which hero_text fixture is supplied."""
    return {
        "kind": "funnel",
        "match_decision": {"flex_decision": "CREATE_NEW", "intent_mode": "HANDS_OFF_DO_IT_ALL"},
        "template": None,
        "artifact": {"pages": [{"page_id": "p1", "copy": {"hero": hero_text}}]},
        "verify": {"overall_pass": True, "pages": [{"status": 200}]},
        "persona_log": "selected_persona: net-new persona chosen",
        "exemplar_packs": [{"exemplar_id": "06-ghl-install-pages/lead/clarity-call-optin",
                            "text": _REAL_EXEMPLAR_TEXT}],
    }


if __name__ == "__main__":
    unittest.main(verbosity=2)

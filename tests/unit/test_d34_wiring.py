#!/usr/bin/env python3
"""D34 production wiring tests (JEV spec 1.1, s 3.6/14.8/17.3-17.4, A53/A59/A62/A63).

The D34 unit shipped the mode-preservation + cohort-validator modules with
ZERO production callers (QC FAIL_FOR_FINAL_ACCEPTANCE, R1_unconnected_helpers).
These tests prove the wiring, not the helpers: each wired production call
site is exercised end-to-end and the D34 verdict must CHANGE BEHAVIOUR —
emit no traffic, refuse a promotion, or gate the shipped core — never
merely be logged.

Wired call sites:
  1. shared-utils/decision_engine/ladder/ladder.py::DirectFirstLadder.run()
     — configured mode decides the effective path (3.6/A62/A63). off/legacy/
     shadow must produce ZERO JEV traffic: no credential resolution, no
     reservation, no direct/OpenRouter send.
  2. install.sh / update-skills.sh D27 core-presence loops
     — decision_engine/modes/*.py must be present or the decision core is
     reported incomplete (update-skills.sh withholds the version stamp).
  3. shared-utils/decision_engine_train/train.py::promote()
     — cross-repo release cohort (14.8/A53): a half-promoted pair must not
     activate.

Run: python3 -m pytest tests/unit/test_d34_wiring.py -q
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
_MODES_PY = _SHARED / "decision_engine" / "modes" / "modes.py"
_COHORT_PY = _SHARED / "decision_engine" / "modes" / "cohort.py"
_LADDER_PY = _SHARED / "decision_engine" / "ladder" / "ladder.py"
_TRAIN_PY = _SHARED / "decision_engine_train" / "train.py"

sys.path.insert(0, str(_SHARED))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


modes = _load("d34w_modes", _MODES_PY)
cohort = _load("d34w_cohort", _COHORT_PY)
ladder = _load("d34w_ladder", _LADDER_PY)
train = _load("d34w_train", _TRAIN_PY)
_TS, _ORO, _CR = ladder._load_providers()

_CALLS = None


def _ok(payload=None):
    out = {"outcome": "ok", "attempts": 1,
           "estimated_cost": 0.0, "actual_cost": 0.0}
    if payload is not None:
        out["payload"] = payload
    return out


def _creds(direct=True, openrouter=True):
    return {"direct": SimpleNamespace(configured=bool(direct)),
            "openrouter": SimpleNamespace(configured=bool(openrouter))}


def _good_select_payload():
    return {"model": _TS.TYPESAFE_MODEL, "judgments": [{
        "question_id": "q1", "type": "select", "answer": "a",
        "probabilities": {"a": 0.7, "b": 0.3}}]}


def _select_specs():
    return {"q1": {"type": "select", "candidates": ["a", "b"],
                   "prob_keys": ["a", "b"]}}


def make_ladder(**kw):
    """Real DirectFirstLadder with injected fakes; counts every remote touch."""
    calls = {"direct": [], "openrouter": [], "resolve": [], "policy": []}

    def _direct(*, body, api_key, timeout_ms, http_post=None):
        calls["direct"].append({"timeout_ms": timeout_ms})
        return _ok(_good_select_payload())

    def _router(*, state, questions, expected, candidates=(), api_key=None,
                key_env=None, timeout_s=2.5, transport=None):
        calls["openrouter"].append({"timeout_s": timeout_s})
        return _ok({"model": _ORO.REQUESTED_MODEL, "judgments": []})

    def _resolve(*a):
        calls["resolve"].append(True)
        return _creds()

    def _policy(provider, purpose="decide"):
        calls["policy"].append(provider)
        return {"spend_ok": True, "transmit_ok": True,
                "reason": "standing-policy"}

    lad = ladder.DirectFirstLadder(
        resolve_credentials=kw.pop("resolve", _resolve),
        direct_call=_direct, openrouter_call=_router,
        policy_fn=_policy, **kw)
    return lad, calls


def _good_receipt(sha):
    return {"sha": sha, "verdict": "PASS", "reviewer": "sonnet-qc-1",
            "reviewer_route": train.INDEPENDENT_ROUTE}


def _passing_results():
    return {"checks": [{"name": "unit", "status": "pass"},
                       {"name": "integration", "status": "pass"}]}


def _promote_ready(repo="onb", sha="a"):
    state = train.new_state()
    train.enqueue(state, repo, "D01", sha, _good_receipt(sha))
    tick = train.tick(state, repo, 900, owner="t:%s" % repo)
    bid = tick["batch_id"]
    train.record_tests(state, repo, bid, "int-1", _passing_results())
    train.attach_integration_qc(state, repo, bid, "sonnet-qc-1",
                                train.INDEPENDENT_ROUTE, "PASS")
    return state, repo, bid


class LadderModeGate(unittest.TestCase):
    """Call site 1: ladder.py::DirectFirstLadder.run()."""

    def _run(self, mode, **kw):
        lad, calls = make_ladder()
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=[{"id": "q1", "type": "select"}],
                          keys={}, config={"configuredMode": mode}, **kw)
        return verdict, calls

    def test_off_emits_zero_jev_traffic(self):
        verdict, calls = self._run("off")
        self.assertEqual(calls["direct"], [])
        self.assertEqual(calls["openrouter"], [])
        self.assertEqual(calls["policy"], [])
        self.assertEqual(calls["resolve"], [])
        self.assertEqual(verdict["decision_source"], "no_jev")
        self.assertEqual(verdict["mode"]["effectivePath"], "no_jev")
        self.assertEqual(verdict["mode"]["skipReason"], "mode_off")
        self.assertEqual(
            [s["skip_reason"] for s in verdict["stages"][:2]],
            ["mode_off", "mode_off"])

    def test_legacy_emits_zero_jev_traffic(self):
        verdict, calls = self._run("legacy")
        self.assertEqual(calls["direct"], [])
        self.assertEqual(calls["openrouter"], [])
        self.assertEqual(calls["policy"], [])
        self.assertEqual(calls["resolve"], [])
        self.assertEqual(verdict["decision_source"], "no_jev")
        self.assertEqual(verdict["mode"]["skipReason"], "mode_legacy")

    def test_legacy_and_off_agree_on_normalized_no_jev(self):
        """A62: off/legacy share ONE improved no-JEV engine.

        The no-JEV DECISION (``decision_source`` + fallback payload) must
        be equivalent across both modes; only the typed mode reason may
        differ. Timing/provenance telemetry is not part of the decision.
        D34's ``decisions_equivalent`` is the authority on label-independent
        equality.
        """
        def _decision(verdict):
            fb = verdict.get("fallback")
            if isinstance(fb, dict):
                fb = {k: v for k, v in fb.items() if k != "stage_skips"}
            return {"decision_source": verdict["decision_source"],
                    "ok": verdict["ok"], "fallback": fb}

        off, _ = self._run("off")
        legacy, _ = self._run("legacy")
        self.assertEqual(off["decision_source"], "no_jev")
        self.assertEqual(legacy["decision_source"], "no_jev")
        self.assertTrue(modes.decisions_equivalent(
            _decision(off), _decision(legacy)))
        self.assertFalse(modes.decisions_equivalent(
            _decision(off),
            {"decision_source": "no_jev", "ok": True,
             "fallback": {"outcome": "different"}}))
        self.assertNotEqual(off["mode"]["skipReason"],
                            legacy["mode"]["skipReason"])
        self.assertEqual(off["mode"]["skipReason"], modes.REASON_MODE_OFF)
        self.assertEqual(legacy["mode"]["skipReason"],
                         modes.REASON_MODE_LEGACY)

    def test_shadow_never_makes_an_authoritative_send(self):
        verdict, calls = self._run("shadow")
        self.assertEqual(calls["direct"], [])
        self.assertEqual(calls["openrouter"], [])
        self.assertEqual(verdict["decision_source"], "no_jev")
        self.assertEqual(verdict["mode"]["skipReason"],
                         "mode_shadow_authoritative_no_jev")
        with self.assertRaises(modes.ShadowCommitError):
            modes.refuse_shadow_commit(verdict)

    def test_auto_with_permission_still_reaches_direct(self):
        verdict, calls = self._run("auto")
        self.assertEqual(len(calls["direct"]), 1)
        self.assertEqual(verdict["decision_source"], "typesafe_direct")
        self.assertEqual(verdict["mode"]["effectivePath"], "jev")
        self.assertEqual(verdict["mode"]["skipReason"], "eligible")

    def test_unapproved_auto_reports_true_no_jev_path(self):
        """A59/A63: denial is typed, never mislabeled missing credentials."""
        verdict, calls = self._run(
            "auto", mode_permissions=lambda: {"spend_ok": False,
                                              "transmit_ok": True})
        self.assertEqual(calls["direct"], [])
        self.assertEqual(calls["openrouter"], [])
        self.assertEqual(calls["policy"], [])
        self.assertEqual(verdict["mode"]["skipReason"], "not_authorized")
        self.assertEqual(
            [s["skip_reason"] for s in verdict["stages"][:2]],
            ["not_authorized", "not_authorized"])
        self.assertNotIn("credential", json.dumps(verdict["mode"]))

    def test_auto_transmit_denied_reports_data_not_permitted(self):
        verdict, calls = self._run(
            "auto", mode_permissions=lambda: {"spend_ok": True,
                                              "transmit_ok": False})
        self.assertEqual(calls["direct"], [])
        self.assertEqual(verdict["mode"]["skipReason"], "data_not_permitted")

    def test_missing_config_stays_auto(self):
        """No config supplied => auto, exactly the pre-wiring behaviour."""
        lad, calls = make_ladder()
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=[{"id": "q1", "type": "select"}],
                          keys={})
        self.assertEqual(verdict["mode"]["configuredMode"], "auto")
        self.assertEqual(len(calls["direct"]), 1)

    def test_unknown_mode_fails_loudly(self):
        lad, calls = make_ladder()
        with self.assertRaises(ValueError):
            lad.run(company_id="acme", state={"s": 1},
                    questions=[{"id": "q1", "type": "select"}],
                    keys={}, config={"configuredMode": "turbo"})
        self.assertEqual(calls["direct"], [])


class InstallerCorePresence(unittest.TestCase):
    """Call site 2: install.sh / update-skills.sh decision-core lists."""

    _MODES_ENTRIES = (
        '"decision_engine/modes/__init__.py"',
        '"decision_engine/modes/modes.py"',
        '"decision_engine/modes/cohort.py"',
    )

    def _assert_listed(self, name):
        src = (_REPO_ROOT / name).read_text(encoding="utf-8")
        for entry in self._MODES_ENTRIES:
            self.assertIn(entry, src, "%s: %s missing" % (name, entry))
        # Each entry must sit INSIDE the presence loop, not merely exist in
        # the file (a prose mention must not pass). The loop opens with
        # `for _D27_REL in` and closes at its `done`.
        loop_at = src.find("for _D27_REL in")
        self.assertGreater(loop_at, 0, "%s: no _D27_REL loop" % name)
        done_at = src.find("done", loop_at)
        self.assertGreater(done_at, loop_at, name)
        body = src[loop_at:done_at]
        for entry in self._MODES_ENTRIES:
            self.assertIn(entry, body, "%s: %s outside the loop" % (name, entry))
        for var in ("_D27_MISSING", "_D27_CORE_MISSING"):
            if '%s="${%s} ${_D27_REL}"' % (var, var) in body:
                return
        self.fail("%s: presence loop does not record the missing entry" % name)

    def test_install_sh_lists_modes_files(self):
        self._assert_listed("install.sh")

    def test_update_skills_sh_lists_modes_files(self):
        self._assert_listed("update-skills.sh")

    def test_modes_files_actually_exist_on_disk(self):
        for rel in self._MODES_ENTRIES:
            path = _REPO_ROOT / "shared-utils" / rel.strip('"')
            self.assertTrue(path.is_file(), rel)

    def test_updater_stamp_gate_still_gated_on_sharedutils_status(self):
        """Missing core entries must still be able to withhold the stamp."""
        src = (_REPO_ROOT / "update-skills.sh").read_text(encoding="utf-8")
        self.assertIn('_SHAREDUTILS_STATUS="fail"', src)
        self.assertIn('if [ "${_SHAREDUTILS_STATUS:-ok}" != "ok" ]; then', src)


class TrainCohortGate(unittest.TestCase):
    """Call site 3: train.py::promote() cross-repo cohort (14.8/A53)."""

    ONB = "a" * 40
    CC = "b" * 40

    def _cohort(self, **kw):
        base = {"onb_sha": self.ONB, "cc_sha": self.CC,
                "onb_version": "v25.1.86", "cc_version": "v7.4.1",
                "contract": "jev-1.1"}
        base.update(kw)
        return base

    def test_half_promoted_new_new_pair_refuses_activation(self):
        state, repo, bid = _promote_ready()
        with self.assertRaisesRegex(ValueError, "half-promoted"):
            train.promote(state, repo, bid, "main-2",
                          cohort=self._cohort(), pairing="new_new")
        self.assertIsNone(state["batches"]["%s/%s" % (repo, bid)]
                          .get("promotion"))

    def test_new_new_without_handshake_refuses(self):
        state, repo, bid = _promote_ready()
        with self.assertRaisesRegex(ValueError, "handshake_failed"):
            train.promote(state, repo, bid, "main-2",
                          cohort=self._cohort(), pairing="new_new",
                          handshake_ok=False)

    def test_exact_tested_pair_with_handshake_activates(self):
        state, repo, bid = _promote_ready()
        m = train.promote(state, repo, bid, "main-2",
                          cohort=self._cohort(), pairing="new_new",
                          handshake_ok=True)
        rec = m["promotion"]["cohort"]
        self.assertTrue(rec["checked"])
        self.assertEqual(rec["behavior"], "full_contract")
        self.assertEqual(rec["capability"], "decision_ready")
        self.assertTrue(rec["exact_match"])
        self.assertEqual(state["windows"][repo]["last_outcome"], "promoted")

    def test_untested_sha_pair_is_not_the_tested_pair(self):
        state, repo, bid = _promote_ready()
        with self.assertRaisesRegex(ValueError, "untested_pair"):
            train.promote(
                state, repo, bid, "main-2",
                cohort=self._cohort(tested_pairs=[("c" * 40, "d" * 40)]),
                pairing="new_new", handshake_ok=True)

    def test_new_cc_old_onb_promotes_compat_fallback_with_truthful_state(self):
        state, repo, bid = _promote_ready(repo="cc")
        m = train.promote(state, repo, bid, "main-2",
                          cohort=self._cohort(), pairing="new_old",
                          handshake_ok=False)
        rec = m["promotion"]["cohort"]
        self.assertEqual(rec["behavior"], "compat_fallback")
        self.assertEqual(rec["capability"], "jev_not_configured")
        self.assertEqual(rec["reason"], "old_command_center_legacy_output")

    def test_old_onb_new_cc_promotes_compat_fallback(self):
        state, repo, bid = _promote_ready()
        m = train.promote(state, repo, bid, "main-2",
                          cohort=self._cohort(), pairing="old_new")
        rec = m["promotion"]["cohort"]
        self.assertEqual(rec["behavior"], "compat_fallback")
        self.assertEqual(rec["capability"], "core_unavailable_incompatible")
        self.assertEqual(rec["reason"], "old_onboarding_no_jev_fallback")

    def test_invalid_cohort_manifest_refuses(self):
        state, repo, bid = _promote_ready()
        with self.assertRaisesRegex(ValueError, "cohort manifest invalid"):
            train.promote(state, repo, bid, "main-2",
                          cohort=self._cohort(onb_sha="not-a-sha"),
                          pairing="new_new", handshake_ok=True)

    def test_absent_cohort_records_unchecked_not_silent(self):
        state, repo, bid = _promote_ready()
        m = train.promote(state, repo, bid, "main-2")
        self.assertEqual(m["promotion"]["cohort"],
                         {"checked": False, "reason": "no_cohort_manifest"})

    def test_force_push_still_never_permitted(self):
        state, repo, bid = _promote_ready()
        with self.assertRaisesRegex(ValueError, "force-push"):
            train.promote(state, repo, bid, "main-3", force_push=True,
                          cohort=self._cohort(), pairing="new_new",
                          handshake_ok=True)


class WiredToRealModules(unittest.TestCase):
    """Each wired call site loads the REAL D34 module by file — never a copy."""

    def test_ladder_loads_real_modes_module(self):
        loaded = ladder._load_modes()
        self.assertEqual(Path(loaded.__file__).resolve(), _MODES_PY.resolve())
        # Same SOURCE FILE, not a reimplementation (the test holds its own
        # import of the same path, so object identity is not the check).
        self.assertEqual(
            Path(loaded.resolve_effective_path.__code__.co_filename)
            .resolve(), _MODES_PY.resolve())
        self.assertEqual(
            Path(loaded.jev_traffic_permitted.__code__.co_filename)
            .resolve(), _MODES_PY.resolve())

    def test_train_loads_real_cohort_module(self):
        loaded = train._load_cohort()
        self.assertEqual(Path(loaded.__file__).resolve(),
                         _COHORT_PY.resolve())
        self.assertEqual(
            Path(loaded.evaluate_pairing.__code__.co_filename).resolve(),
            _COHORT_PY.resolve())
        self.assertEqual(
            Path(loaded.validate_cohort.__code__.co_filename).resolve(),
            _COHORT_PY.resolve())

    def test_no_second_engine_defined_in_wired_files(self):
        """The wired files must not define their own mode/cohort logic."""
        for path in (_LADDER_PY, _TRAIN_PY):
            src = path.read_text(encoding="utf-8")
            for forbidden in ("def preserve_explicit_mode",
                              "def resolve_effective_path",
                              "def validate_cohort",
                              "def evaluate_pairing",
                              "MODES = ("):
                self.assertNotIn(forbidden, src,
                                 "%s defines %s" % (path.name, forbidden))

    def test_wired_files_reference_the_real_module_path(self):
        ladder_src = _LADDER_PY.read_text(encoding="utf-8")
        self.assertIn('"modes" / "modes.py"', ladder_src)
        train_src = _TRAIN_PY.read_text(encoding="utf-8")
        self.assertIn('"modes" / "cohort.py"', train_src)


if __name__ == "__main__":
    unittest.main()

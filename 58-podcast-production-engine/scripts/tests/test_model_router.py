#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: runtime model router (E6)
# -----------------------------------------------------------------------------
# Stdlib unittest only. Fully offline: the HTTP transport and every side-channel
# (meter / hold / alert / substitution) are injected, so nothing leaves the box
# and no credential value is ever read or printed. Proves tier resolution from
# the shipped config/models.json, the deny gate (config tokens + Anthropic-shape
# backstop, refused at call time never as a substitution), env-label credential
# resolution, chain advance on retryable failures with substitution marking,
# credit-out recovery vs. exhaustion HOLD + single deduped alert, and the budget
# ceiling block.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_model_router.py
# =============================================================================
"""Deterministic tests for the runtime model router (E6)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "model_router.py"


def _load_module():
    import sys
    spec = importlib.util.spec_from_file_location("model_router", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so the @dataclass definitions can resolve their own
    # module under `from __future__ import annotations`.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


MR = _load_module()

# Dummy credentials so every configured lane resolves SET (never real secrets).
for _k in ("OLLAMA_API_KEY", "OLLAMA_CLOUD_API_KEY", "OPENROUTER_API_KEY",
           "GEMINI_API_KEY", "GOOGLE_API_KEY"):
    os.environ.setdefault(_k, "dummy-not-a-real-secret")

BLOCK, _PATH = MR.load_models_config()
CONTENT = MR.resolve_tier(BLOCK, MR.CONTENT_TIER)
JUDGE = MR.resolve_tier(BLOCK, MR.JUDGE_TIER)
DENY = MR.deny_patterns_of(BLOCK)


def _router(transport, **kw):
    kw.setdefault("pre_meter", lambda *a, **k: None)
    kw.setdefault("post_meter", lambda *a, **k: None)
    kw.setdefault("hold_fn", lambda *a, **k: None)
    kw.setdefault("alert_fn", lambda *a, **k: None)
    kw.setdefault("substitution_fn", lambda *a, **k: None)
    return MR.ModelRouter(config_block=BLOCK, transport=transport, **kw)


class ConfigAndDeny(unittest.TestCase):
    def test_shipped_config_validates(self):
        MR.validate_config(BLOCK)  # must not raise

    def test_deny_patterns_present(self):
        self.assertTrue(DENY, "deny_patterns must be armed")

    def test_deny_catches_family_tokens(self):
        self.assertTrue(MR.is_denied("vendor-opus-preview", DENY))
        self.assertTrue(MR.is_denied("x-sonnet-3", DENY))
        self.assertTrue(MR.is_denied("y-haiku", DENY))

    def test_deny_catches_anthropic_shape_even_without_config_tokens(self):
        shape = MR._C + "-x9"  # assembled so this file carries no banned literal
        self.assertTrue(MR.is_denied(shape, []))

    def test_deny_passes_real_ids(self):
        self.assertFalse(MR.is_denied(CONTENT[0]["model"], DENY))
        self.assertFalse(MR.is_denied("glm-5.2:cloud", DENY))

    def test_denied_config_fails_closed_at_construction(self):
        import json
        poisoned = json.loads(json.dumps(BLOCK))
        poisoned["models"][MR.CONTENT_TIER][0]["model"] = "vendor-opus-9"
        with self.assertRaises(MR.DenyPatternRefusal):
            MR.ModelRouter(config_block=poisoned)

    def test_content_first_is_ollama_cloud_last_is_gemini(self):
        self.assertEqual(CONTENT[0]["provider"], "ollama-cloud")
        self.assertEqual(CONTENT[-1]["provider"], "gemini")

    def test_judge_first_differs_from_content_first(self):
        self.assertNotEqual(JUDGE[0]["model"], CONTENT[0]["model"])


class Routing(unittest.TestCase):
    def test_primary_success_no_substitution(self):
        tr = MR._ScriptedTransport([MR._ok_response(CONTENT[0]["model"], "body")])
        res = _router(tr).route(MR.CONTENT_TIER, [{"role": "user", "content": "hi"}],
                                {"client": "c", "job_id": "j"})
        self.assertEqual(res.model_used, CONTENT[0]["model"])
        self.assertEqual(res.priority, CONTENT[0]["priority"])
        self.assertFalse(res.substituted)
        self.assertEqual(res.text, "body")

    def test_rate_limit_advances_and_marks_substitution(self):
        subs = []
        tr = MR._ScriptedTransport([MR._err_response(429, "rate limited"),
                                    MR._ok_response(CONTENT[1]["model"])])
        res = _router(tr, substitution_fn=lambda *a: subs.append(a)).route(
            MR.CONTENT_TIER, [{"role": "user", "content": "x"}], {"client": "c", "job_id": "j"})
        self.assertEqual(res.provider, CONTENT[1]["provider"])
        self.assertTrue(res.substituted)
        self.assertEqual(len(subs), 1)
        self.assertTrue(any(d["class"] == "rate_limit" for d in res.degradations))

    def test_credit_out_recovers_on_fallback_no_hold(self):
        holds, alerts = [], []
        tr = MR._ScriptedTransport([MR._err_response(402, "insufficient credits"),
                                    MR._ok_response(CONTENT[1]["model"])])
        res = _router(tr, hold_fn=lambda *a: holds.append(a),
                      alert_fn=lambda *a: alerts.append(a)).route(
            MR.CONTENT_TIER, [{"role": "user", "content": "x"}], {"client": "c", "job_id": "j"})
        self.assertEqual(res.provider, CONTENT[1]["provider"])
        self.assertFalse(holds)
        self.assertFalse(alerts)

    def test_exhaustion_holds_and_alerts_once(self):
        holds, alerts = [], []
        script = [MR._err_response(429)] + \
                 [MR.ProviderError("p", MR.ErrorClass.TIMEOUT)] * (len(CONTENT) - 1)
        tr = MR._ScriptedTransport(script)
        router = _router(tr, hold_fn=lambda ctx, reason, tier: holds.append(reason),
                         alert_fn=lambda ctx, tier, reason: alerts.append(reason))
        with self.assertRaises(MR.ChainExhaustedHold) as cm:
            router.route(MR.CONTENT_TIER, [{"role": "user", "content": "x"}],
                         {"client": "c", "client_id": "c", "job_id": "j", "resume_stage": "writing"})
        self.assertEqual(cm.exception.reason, "chain_exhausted")
        self.assertEqual(holds, ["chain_exhausted"])
        self.assertEqual(len(alerts), 1)

    def test_all_credit_out_reason_is_credit_out(self):
        holds, alerts = [], []
        tr = MR._ScriptedTransport([MR._err_response(402, "insufficient credit")] * len(CONTENT))
        router = _router(tr, hold_fn=lambda ctx, reason, tier: holds.append(reason),
                         alert_fn=lambda ctx, tier, reason: alerts.append(reason))
        with self.assertRaises(MR.ChainExhaustedHold) as cm:
            router.route(MR.CONTENT_TIER, [{"role": "user", "content": "x"}],
                         {"client": "c", "client_id": "c", "job_id": "j"})
        self.assertEqual(cm.exception.reason, "credit_out")
        self.assertEqual(holds, ["credit_out"])
        self.assertEqual(len(alerts), 1)

    def test_hold_immediately_on_first_credit_out(self):
        tr = MR._ScriptedTransport([MR._err_response(402, "insufficient credit"),
                                    MR._ok_response(CONTENT[1]["model"])])
        router = _router(tr, hold_immediately_on_credit_out=True)
        with self.assertRaises(MR.ChainExhaustedHold):
            router.route(MR.CONTENT_TIER, [{"role": "user", "content": "x"}],
                         {"client": "c", "client_id": "c", "job_id": "j"})
        self.assertEqual(len(tr.calls), 1)  # never tried the fallback

    def test_budget_ceiling_blocks_before_any_call(self):
        def blocking_pre(*a, **k):
            raise MR.BudgetCeilingBlock("ceiling")
        tr = MR._ScriptedTransport([MR._ok_response(CONTENT[0]["model"])])
        router = MR.ModelRouter(config_block=BLOCK, transport=tr, pre_meter=blocking_pre,
                                post_meter=lambda *a: None, hold_fn=lambda *a: None,
                                alert_fn=lambda *a: None, substitution_fn=lambda *a: None)
        with self.assertRaises(MR.BudgetCeilingBlock):
            router.route(MR.CONTENT_TIER, [{"role": "user", "content": "x"}], {"client": "c"})
        self.assertEqual(tr.calls, [])  # transport never touched

    def test_unset_credential_link_is_skipped(self):
        saved = {k: os.environ.pop(k, None) for k in ("OLLAMA_API_KEY", "OLLAMA_CLOUD_API_KEY")}
        try:
            first_funded = next(l for l in CONTENT if l["provider"] != "ollama-cloud")
            tr = MR._ScriptedTransport([MR._ok_response(first_funded["model"])])
            res = _router(tr).route(MR.CONTENT_TIER, [{"role": "user", "content": "x"}],
                                    {"client": "c", "job_id": "j"})
            self.assertEqual(res.provider, first_funded["provider"])
            self.assertTrue(any(d.get("detail") == "credential NOT SET by label"
                                for d in res.degradations))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_echoed_denied_model_is_refused_after_response(self):
        # A provider that echoes a denied model id must be refused (exit-2 class),
        # not returned as an honest record.
        tr = MR._ScriptedTransport([MR._ok_response("sneaky-opus-echo")])
        with self.assertRaises(MR.DenyPatternRefusal):
            _router(tr).route(MR.CONTENT_TIER, [{"role": "user", "content": "x"}],
                              {"client": "c", "job_id": "j"})

    def test_unknown_tier_raises(self):
        with self.assertRaises(MR.UnknownTierError):
            MR.resolve_tier(BLOCK, "not-a-tier")


class Substitution(unittest.TestCase):
    def test_default_substitution_log_writes_spool(self):
        import json
        import tempfile
        state = tempfile.mkdtemp(prefix="podcast-sub-")
        MR.default_substitution_log(
            {"state_dir": state, "client": "c", "job_id": "j"},
            MR.CONTENT_TIER, 1, 3, "moonshotai/kimi-k2.6")
        spool = os.path.join(state, "substitutions", "substitutions.jsonl")
        self.assertTrue(os.path.exists(spool))
        with open(spool, encoding="utf-8") as fh:
            rec = json.loads(fh.readline())
        self.assertEqual(rec["used_priority"], 3)
        self.assertEqual(rec["model_used"], "moonshotai/kimi-k2.6")


class RealSideChannelScripts(unittest.TestCase):
    """Drive default_alert AND default_pre_meter against the engine's OWN shipped
    scripts (alert-dedup.py, podcast-cost-ledger.py) -- NOT injected noop mocks.

    A noop mock accepts any argv and any behaviour, which is exactly how (a) a
    wrong alert subcommand/flag (`notify --class ...` -- the engine's alert-dedup
    exposes only {raise,recover,flush-digest,status}, so `notify` exits 2 and the
    founder alert silently never reaches the gateway) and (b) an omitted
    hard-ceiling exit code (ledger exit 11 = llm_tokens_per_episode_hard) slip
    past an 'all green' run. These tests exercise the real CLIs so both defects
    fail loudly."""

    def setUp(self):
        self._state = tempfile.mkdtemp(prefix="podcast-real-sc-")
        self._saved = os.environ.get("PODCAST_ENGINE_STATE_DIR")
        os.environ["PODCAST_ENGINE_STATE_DIR"] = self._state

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("PODCAST_ENGINE_STATE_DIR", None)
        else:
            os.environ["PODCAST_ENGINE_STATE_DIR"] = self._saved

    @staticmethod
    def _capture_argv(fn, *args, **kw):
        """Call `fn`, intercepting the ONE subprocess.call it issues, and return
        the exact argv it built (without running it)."""
        captured = {}
        real_call = MR.subprocess.call

        def fake_call(argv, *a, **k):
            captured["argv"] = list(argv)
            return 0

        MR.subprocess.call = fake_call
        try:
            fn(*args, **kw)
        finally:
            MR.subprocess.call = real_call
        return captured.get("argv")

    def test_default_alert_argv_accepted_by_real_alert_dedup(self):
        argv = self._capture_argv(
            MR.default_alert,
            {"client": "unit-co", "episode_id": "ep-unit", "queue_service": "ollama_cloud"},
            MR.CONTENT_TIER, "credit_out")
        self.assertIsNotNone(argv, "default_alert must invoke alert-dedup.py")
        self.assertTrue(str(argv[1]).endswith("alert-dedup.py"), argv)
        self.assertEqual(argv[2], "raise",
                         "the only alert subcommand is `raise` (not `notify`)")
        # Run the REAL alert-dedup.py with default_alert's OWN argv (+ --dry-run so
        # the gateway is never touched). A wrong subcommand/flag => argparse exit 2
        # + 'invalid choice'/'unrecognized arguments' -- the silent-drop defect.
        proc = subprocess.run(argv + ["--dry-run"], capture_output=True, text=True, timeout=30)
        self.assertNotIn("invalid choice", proc.stderr.lower(), proc.stderr)
        self.assertNotIn("unrecognized arguments", proc.stderr.lower(), proc.stderr)
        self.assertEqual(proc.returncode, 0,
                         "real alert-dedup.py rejected default_alert's argv:\n%s" % proc.stderr)

    def test_default_pre_meter_blocks_on_real_ledger_hard_token_ceiling(self):
        ctx = {"client": "unit-co", "episode_id": "ep-unit"}
        # Under the shipped hard ceiling (llm_tokens_per_episode_hard=400000) a
        # small estimate proceeds: the REAL ledger exits 0, so NO block.
        MR.default_pre_meter(ctx, MR.CONTENT_TIER, "unit-model", 100)  # must NOT raise
        # A 500k-token estimate crosses the per-episode token ceiling: the REAL
        # ledger exits 11 -- the exact code the prior frozenset(10,13,14) omitted,
        # which fail-open silently overspent. The router must now block.
        with self.assertRaises(MR.BudgetCeilingBlock):
            MR.default_pre_meter(ctx, MR.CONTENT_TIER, "unit-model", 500000)

    def test_default_pre_meter_fails_closed_on_unrecognized_ledger_exit(self):
        # A ledger that returns an unrecognized non-proceed code must NOT fail
        # open: the router holds the spend rather than billing blind.
        ctx = {"client": "unit-co", "episode_id": "ep-unit"}
        real_call = MR.subprocess.call
        MR.subprocess.call = lambda *a, **k: 99  # unknown refuse code
        try:
            with self.assertRaises(MR.BudgetCeilingBlock):
                MR.default_pre_meter(ctx, MR.CONTENT_TIER, "unit-model", 100)
        finally:
            MR.subprocess.call = real_call

    def test_default_pre_meter_proceeds_on_soft_ceiling_exit(self):
        # EXIT_SOFT (2) is advisory: the call proceeds (no block).
        ctx = {"client": "unit-co", "episode_id": "ep-unit"}
        real_call = MR.subprocess.call
        MR.subprocess.call = lambda *a, **k: 2
        try:
            MR.default_pre_meter(ctx, MR.CONTENT_TIER, "unit-model", 100)  # must NOT raise
        finally:
            MR.subprocess.call = real_call


class ModuleSelfTest(unittest.TestCase):
    def test_module_self_test_passes(self):
        # The module's own in-process battery is the end-to-end proof.
        self.assertEqual(MR.self_test(), MR.EX_OK)


if __name__ == "__main__":
    unittest.main()

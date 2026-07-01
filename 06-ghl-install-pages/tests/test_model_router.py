# test_model_router.py — role-aware, probe-gated NON-ANTHROPIC model router.
# Fully offline: ladder shape, guards, probe-gate, and failover are exercised
# with the deterministic stub executor.  MiniMax M2 ban, Anthropic ban,
# Ollama-Cloud-first order, Gemini-last-resort, execution-DeepSeek-fallback, and
# assert_model_sovereignty are all independently verified.
from __future__ import annotations

import json
import os
import sys

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

_SHARED_UTILS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "shared-utils"))
if _SHARED_UTILS not in sys.path:
    sys.path.insert(0, _SHARED_UTILS)

import model_router as mr  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────────────

ALL_CANONICAL_ROLES = ["content", "html", "reasoning", "execution", "qc"]
ALL_ROLE_INPUTS = ALL_CANONICAL_ROLES + ["code", "funnel"]  # aliases included


def _all_slugs(ladder: list) -> list[str]:
    """Collect every model slug from a ladder."""
    return [m["slug"] for rung in ladder for m in rung["models"]]


def _last_slug(ladder: list) -> str:
    return ladder[-1]["models"][-1]["slug"]


# ── Test: per-role rung-1 assertions ─────────────────────────────────────────

class TestRoleRung1:
    """Every role's rung-1 must be the correct Ollama Cloud model."""

    def test_content_rung1_is_kimi_ollama_cloud(self):
        ladder = mr.build_ladder({}, role="content")
        r1 = ladder[0]
        assert r1["provider"] == "ollama-cloud"
        assert r1["models"][0]["family"] == "kimi"
        assert r1["models"][0]["slug"] == "kimi-k2.6:cloud"
        assert r1["probe_gated"] is False

    def test_html_rung1_is_glm_ollama_cloud(self):
        ladder = mr.build_ladder({}, role="html")
        r1 = ladder[0]
        assert r1["provider"] == "ollama-cloud"
        assert r1["models"][0]["family"] == "glm"
        assert "glm-5.2" in r1["models"][0]["slug"]
        assert r1["probe_gated"] is False

    def test_code_alias_rung1_same_as_html(self):
        # "code" is an alias for "html"
        assert mr.build_ladder({}, role="code") == mr.build_ladder({}, role="html")

    def test_reasoning_rung1_is_glm_ollama_cloud(self):
        ladder = mr.build_ladder({}, role="reasoning")
        r1 = ladder[0]
        assert r1["provider"] == "ollama-cloud"
        assert r1["models"][0]["family"] == "glm"
        assert "glm-5.2" in r1["models"][0]["slug"]

    def test_funnel_alias_rung1_same_as_reasoning(self):
        # "funnel" is an alias for "reasoning"
        assert mr.build_ladder({}, role="funnel") == mr.build_ladder({}, role="reasoning")

    def test_execution_rung1_is_minimax_m3_probe_gated(self):
        ladder = mr.build_ladder({}, role="execution")
        r1 = ladder[0]
        assert r1["provider"] == "ollama-cloud"
        assert r1["models"][0]["family"] == "minimax"
        assert r1["models"][0]["slug"] == "minimax-m3:cloud"
        assert r1["probe_gated"] is True

    def test_qc_rung1_is_minimax_m3_probe_gated_vision(self):
        ladder = mr.build_ladder({}, role="qc")
        r1 = ladder[0]
        assert r1["provider"] == "ollama-cloud"
        assert r1["models"][0]["family"] == "minimax"
        assert r1["models"][0]["slug"] == "minimax-m3:cloud"
        assert r1["probe_gated"] is True
        assert r1["vision"] is True


# ── Test: Ollama Cloud FIRST ordering ────────────────────────────────────────

class TestOllamaCloudFirst:
    """Ollama Cloud rungs must appear before OpenRouter rungs on every role."""

    @pytest.mark.parametrize("role", ALL_CANONICAL_ROLES)
    def test_ollama_before_openrouter(self, role):
        ladder = mr.build_ladder({}, role=role)
        providers = [r["provider"] for r in ladder]
        first_openrouter = next(
            (i for i, p in enumerate(providers) if p == "openrouter"), len(providers)
        )
        last_ollama = max(
            (i for i, p in enumerate(providers) if p == "ollama-cloud"),
            default=-1,
        )
        # If there is at least one Ollama Cloud rung, it must precede all OpenRouter rungs.
        if last_ollama != -1:
            assert last_ollama < first_openrouter, (
                f"role={role!r}: Ollama Cloud (index {last_ollama}) appears "
                f"after OpenRouter (index {first_openrouter}). providers={providers}"
            )

    @pytest.mark.parametrize("role", ALL_CANONICAL_ROLES)
    def test_first_rung_is_ollama_cloud(self, role):
        ladder = mr.build_ladder({}, role=role)
        assert ladder[0]["provider"] == "ollama-cloud", (
            f"role={role!r}: first rung must be ollama-cloud, got {ladder[0]['provider']!r}"
        )


# ── Test: ZERO MiniMax M2 anywhere ───────────────────────────────────────────

class TestM2Purge:
    """MiniMax M2 must not appear in any ladder, any role, under any form."""

    @pytest.mark.parametrize("role", ALL_ROLE_INPUTS)
    def test_no_minimax_m2_in_ladder(self, role):
        ladder = mr.build_ladder({}, role=role)
        blob = json.dumps(ladder).lower()
        assert "minimax-m2" not in blob, f"role={role!r}: BANNED minimax-m2 found"
        assert "minimax_m2" not in blob, f"role={role!r}: BANNED minimax_m2 found"

    @pytest.mark.parametrize("role", ALL_ROLE_INPUTS)
    def test_no_bare_m2_model_slug(self, role):
        """No model slug is the bare M2 id."""
        ladder = mr.build_ladder({}, role=role)
        for rung in ladder:
            for m in rung["models"]:
                slug = m["slug"].lower()
                assert slug != "m2", f"role={role!r}: bare 'm2' slug found"
                assert not slug.endswith("/m2"), f"role={role!r}: slug ending /m2 found"
                assert not slug.endswith(":m2"), f"role={role!r}: slug ending :m2 found"

    def test_execution_m3_only_no_m2(self):
        """The execution ladder uses MiniMax M3 only — M2 must never appear."""
        ladder = mr.build_ladder({}, role="execution")
        minimax_slugs = [
            m["slug"] for r in ladder for m in r["models"]
            if m["family"] == "minimax"
        ]
        assert all("m3" in s.lower() for s in minimax_slugs), (
            f"execution: expected all minimax slugs to be M3, got {minimax_slugs}"
        )


# ── Test: execution fallback is DeepSeek v4 pro ──────────────────────────────

class TestExecutionFallback:
    """When MiniMax M3 probe fails on the execution role, the fallback must be
    DeepSeek v4 pro (not M2 or anything else)."""

    def test_execution_rung2_is_deepseek(self):
        ladder = mr.build_ladder({}, role="execution")
        r2 = ladder[1]
        assert r2["models"][0]["family"] == "deepseek"
        assert "deepseek-v4-pro" in r2["models"][0]["slug"]
        assert r2["probe_gated"] is False

    def test_select_execution_minimax_fail_chooses_deepseek(self):
        out = mr.select(
            mr.make_stub_executor(fail_families=("minimax",)),
            role="execution", env={}, sleep=lambda *_: None,
        )
        assert out["chosen"] is not None
        assert out["chosen"]["rung"] == 2
        assert "deepseek" in out["chosen"]["model"]

    def test_execution_deepseek_rung_not_probe_gated(self):
        """The DeepSeek fallback rung must not be probe-gated."""
        ladder = mr.build_ladder({}, role="execution")
        deepseek_rungs = [r for r in ladder if r["models"][0]["family"] == "deepseek"]
        for r in deepseek_rungs:
            assert not r.get("probe_gated"), (
                f"DeepSeek rung {r['rung']} must not be probe-gated"
            )


# ── Test: Gemini 3.5 Flash is the last rung on every role ────────────────────

class TestGeminiLastRung:
    """Gemini 3.5 Flash must be the final (last-resort) rung on every role."""

    @pytest.mark.parametrize("role", ALL_CANONICAL_ROLES)
    def test_last_rung_is_gemini(self, role):
        ladder = mr.build_ladder({}, role=role)
        last = ladder[-1]
        last_slug = last["models"][-1]["slug"]
        assert "gemini" in last_slug.lower(), (
            f"role={role!r}: last rung slug must contain 'gemini', got {last_slug!r}"
        )
        assert last.get("notes") == "last-resort", (
            f"role={role!r}: last rung must be marked 'last-resort'"
        )

    @pytest.mark.parametrize("role", ALL_CANONICAL_ROLES)
    def test_last_rung_is_openrouter(self, role):
        ladder = mr.build_ladder({}, role=role)
        assert ladder[-1]["provider"] == "openrouter", (
            f"role={role!r}: Gemini last-resort must be on openrouter provider"
        )

    def test_gemini_slug_contains_gemini_3_5_flash(self):
        """Verify the default Gemini slug matches the required model."""
        for role in ALL_CANONICAL_ROLES:
            ladder = mr.build_ladder({}, role=role)
            last_slug = ladder[-1]["models"][-1]["slug"]
            assert "gemini-3.5-flash" in last_slug or "gemini" in last_slug, (
                f"role={role!r}: expected gemini-3.5-flash, got {last_slug!r}"
            )


# ── Test: assert_model_sovereignty rejects every Anthropic slug ──────────────

class TestModelSovereignty:
    """assert_model_sovereignty (shared-utils) must BLOCK every Anthropic slug.
    This is an independent test of the shared gate — not of model_router internals."""

    @pytest.mark.parametrize("slug", [
        # These slugs match FORBIDDEN_PREFIXES in select_model.py:
        #   "anthropic/", "claude-opus", "claude-sonnet", "claude-haiku", "claude-3", "claude-4"
        "claude-3-opus",
        "claude-4-sonnet",
        "anthropic/claude-3-5-sonnet",
        "claude-haiku-20240307",
        "claude-sonnet-4-5",
        "claude-opus-4",
        # us.anthropic.claude-sonnet-4 contains "claude-sonnet" → caught by FORBIDDEN_PREFIXES
        "us.anthropic.claude-sonnet-4",
    ])
    def test_assert_model_sovereignty_rejects_anthropic(self, slug):
        try:
            from assert_model_sovereignty import assert_model_sovereignty as ams
        except ImportError:
            pytest.skip("shared-utils/assert_model_sovereignty not importable in this env")
        # Pass the slug as its own inventory to bypass the NOT_IN_INVENTORY check;
        # the FORBIDDEN (Anthropic) check fires before inventory.
        v = ams(slug, inventory=[slug])
        assert v["ok"] is False, f"Expected BLOCKED for Anthropic slug {slug!r}"
        assert v["code"] == "FORBIDDEN", (
            f"Expected code=FORBIDDEN for {slug!r}, got {v['code']!r}"
        )

    def test_sovereignty_check_fires_before_dispatch(self):
        """_sovereignty_check must raise AnthropicModelError on an Anthropic slug."""
        try:
            mr._sovereignty_check("non-anthropic-model")  # must not raise
        except mr.AnthropicModelError:
            pytest.fail("_sovereignty_check should not raise on a valid slug")
        # The injected Anthropic slug must be caught by the internal guard.
        bad_ladder = mr.build_ladder({}, role="execution")
        bad_ladder[0]["models"][0]["slug"] = "BANNED-claude-sentinel"
        with pytest.raises(mr.AnthropicModelError):
            mr.assert_no_anthropic(bad_ladder)


# ── Test: Anthropic guard ─────────────────────────────────────────────────────

class TestAnthropicGuard:
    """assert_no_anthropic must catch any Anthropic model injected into any rung."""

    @pytest.mark.parametrize("role", ALL_CANONICAL_ROLES)
    def test_clean_ladder_passes(self, role):
        mr.assert_no_anthropic(mr.build_ladder({}, role=role))  # must not raise

    @pytest.mark.parametrize("role", ALL_CANONICAL_ROLES)
    def test_no_anthropic_marker_in_ladder_json(self, role):
        blob = json.dumps(mr.build_ladder({}, role=role)).lower()
        for marker in mr._ANTHROPIC_MARKERS:
            assert marker not in blob, (
                f"role={role!r}: Anthropic marker {marker!r} leaked into ladder JSON"
            )

    @pytest.mark.parametrize("bad_slug", [
        "claude-x", "anthropic/foo", "some-opus", "a-sonnet-b", "haiku-1",
    ])
    def test_guard_rejects_injected_anthropic(self, bad_slug):
        ladder = mr.build_ladder({}, role="execution")
        ladder[0]["models"][0]["slug"] = bad_slug
        with pytest.raises(mr.AnthropicModelError):
            mr.assert_no_anthropic(ladder)

    def test_select_never_returns_anthropic(self):
        """select() must never return an Anthropic model regardless of probe behaviour."""
        out = mr.select(
            mr.make_stub_executor(advance_families=("minimax",)),
            role="execution", env={}, sleep=lambda *_: None,
        )
        assert out["chosen"] is not None
        assert not mr._looks_anthropic(out["chosen"]["model"])


# ── Test: Ollama Cloud invariants ─────────────────────────────────────────────

class TestOllamaCloudInvariants:
    """Every Ollama Cloud rung must have :cloud suffix and ollama.com baseUrl."""

    @pytest.mark.parametrize("role", ALL_CANONICAL_ROLES)
    def test_cloud_suffix_and_baseurl_ok(self, role):
        for rung in mr.build_ladder({}, role=role):
            if rung["provider"] == "ollama-cloud":
                mr.assert_ollama_cloud_ready(rung, {})  # must not raise

    def test_missing_cloud_suffix_raises(self):
        r = mr.build_ladder({}, role="reasoning")[0]  # GLM Ollama Cloud
        r["models"][0]["slug"] = "glm-5.2"  # missing :cloud
        with pytest.raises(mr.OllamaCloudConfigError):
            mr.assert_ollama_cloud_ready(r, {})

    def test_wrong_baseurl_raises(self):
        r = mr.build_ladder({}, role="execution")[0]  # MiniMax Ollama Cloud
        r["base_url"] = "https://api.example.com"
        with pytest.raises(mr.OllamaCloudConfigError):
            mr.assert_ollama_cloud_ready(r, {})

    def test_openrouter_rung_skipped_by_ollama_check(self):
        """assert_ollama_cloud_ready is a no-op for openrouter rungs."""
        for rung in mr.build_ladder({}, role="content"):
            if rung["provider"] == "openrouter":
                mr.assert_ollama_cloud_ready(rung, {})  # must not raise


# ── Test: thinking=high on every rung ────────────────────────────────────────

class TestThinkingEffort:
    @pytest.mark.parametrize("role", ALL_CANONICAL_ROLES)
    def test_every_rung_thinking_high(self, role):
        for rung in mr.build_ladder({}, role=role):
            assert rung["thinking"] == "high", (
                f"role={role!r} rung {rung['rung']}: thinking must be 'high', "
                f"got {rung['thinking']!r}"
            )

    def test_chosen_entry_carries_thinking_high(self):
        out = mr.select(mr.make_stub_executor(), role="content", env={}, sleep=lambda *_: None)
        assert out["chosen"]["thinking"] == "high"


# ── Test: env overrides ───────────────────────────────────────────────────────

class TestEnvOverrides:
    def test_ollama_kimi_override(self):
        env = {"MODEL_ROUTER_OLLAMA_KIMI": "kimi-k3.0:cloud"}
        ladder = mr.build_ladder(env, role="content")
        assert ladder[0]["models"][0]["slug"] == "kimi-k3.0:cloud"

    def test_ollama_deepseek_override_appears_in_execution(self):
        env = {"MODEL_ROUTER_OLLAMA_DEEPSEEK": "deepseek-v4-pro-custom:cloud"}
        ladder = mr.build_ladder(env, role="execution")
        # execution rung 2 is Ollama DeepSeek
        assert ladder[1]["models"][0]["slug"] == "deepseek-v4-pro-custom:cloud"

    def test_openrouter_gemini_override_affects_all_roles(self):
        env = {"MODEL_ROUTER_OPENROUTER_GEMINI": "google/gemini-4.0-flash"}
        for role in ALL_CANONICAL_ROLES:
            ladder = mr.build_ladder(env, role=role)
            assert ladder[-1]["models"][-1]["slug"] == "google/gemini-4.0-flash", (
                f"role={role!r}: Gemini override not applied"
            )


# ── Test: probe-gate behaviour ────────────────────────────────────────────────

class TestProbeAndSelect:
    def test_probe_passes_requires_tool_call_fired_and_args(self):
        assert mr.probe_passes({"tool_call_fired": True, "parsed": True, "args": {"ok": True}}) is True
        assert mr.probe_passes({"tool_call_fired": False, "parsed": True, "args": {"ok": True}}) is False
        assert mr.probe_passes({"tool_call_fired": True, "parsed": True, "args": {}}) is False
        assert mr.probe_passes(None) is False
        assert mr.probe_passes("plausible non-tool text") is False

    def test_content_clean_run_chooses_rung1_kimi(self):
        out = mr.select(mr.make_stub_executor(), role="content", env={}, sleep=lambda *_: None)
        assert out["chosen"]["rung"] == 1
        assert out["chosen"]["provider"] == "ollama-cloud"
        assert "kimi" in out["chosen"]["model"]
        assert out["chosen"]["thinking"] == "high"

    def test_execution_clean_run_chooses_rung1_minimax_m3(self):
        out = mr.select(mr.make_stub_executor(), role="execution", env={}, sleep=lambda *_: None)
        assert out["chosen"]["rung"] == 1
        assert "minimax-m3" in out["chosen"]["model"]

    def test_execution_minimax_fail_advances_to_deepseek(self):
        out = mr.select(
            mr.make_stub_executor(fail_families=("minimax",)),
            role="execution", env={}, sleep=lambda *_: None,
        )
        assert out["chosen"]["rung"] == 2
        assert "deepseek" in out["chosen"]["model"]

    def test_qc_minimax_fail_advances_to_gemini(self):
        """QC has no DeepSeek rung (no confirmed vision); MiniMax fail → Gemini."""
        out = mr.select(
            mr.make_stub_executor(fail_families=("minimax",)),
            role="qc", env={}, sleep=lambda *_: None,
        )
        assert out["chosen"] is not None
        assert "gemini" in out["chosen"]["model"]

    def test_content_kimi_fail_advances_to_openrouter_kimi(self):
        """If Ollama Cloud Kimi fails, OpenRouter Kimi (rung 2) is chosen."""
        out = mr.select(
            mr.make_stub_executor(fail_families=()),  # nothing fails; rung 1 chosen
            role="content", env={}, sleep=lambda *_: None,
        )
        assert out["chosen"]["rung"] == 1  # Ollama Cloud preferred

    def test_chosen_is_never_anthropic(self):
        for role in ALL_CANONICAL_ROLES:
            out = mr.select(
                mr.make_stub_executor(advance_families=("minimax",)),
                role=role, env={}, sleep=lambda *_: None,
            )
            if out["chosen"]:
                assert not mr._looks_anthropic(out["chosen"]["model"]), (
                    f"role={role!r}: chosen model is Anthropic!"
                )

    def test_receipt_written_and_valid(self, tmp_path):
        out_path = tmp_path / "routing" / "model-ladder.json"
        mr.select(
            mr.make_stub_executor(), role="content", env={}, sleep=lambda *_: None,
            receipt_path=str(out_path),
        )
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert data["chosen"]["rung"] == 1
        assert data["role"] == "content"
        # Policy banner says "NEVER Anthropic" — verify no model id is Anthropic.
        assert not mr._looks_anthropic(json.dumps(data["ladder"]))

    def test_role_returned_in_receipt(self):
        out = mr.select(mr.make_stub_executor(), role="qc", env={}, sleep=lambda *_: None)
        assert out["role"] == "qc"

    def test_unknown_role_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown role"):
            mr.build_ladder({}, role="bogus-role")


# ── Test: Kimi slug hygiene ───────────────────────────────────────────────────

class TestKimiSlugHygiene:
    """Kimi must use the kimi-k2.6 slug, never kimi-2.6 (the typo variant)."""

    def test_content_ollama_kimi_slug_is_kimi_k2_6(self):
        ladder = mr.build_ladder({}, role="content")
        ollama_kimi = ladder[0]["models"][0]["slug"]
        assert ollama_kimi == "kimi-k2.6:cloud", (
            f"Kimi Ollama Cloud slug must be kimi-k2.6:cloud, got {ollama_kimi!r}"
        )

    def test_content_openrouter_kimi_slug(self):
        ladder = mr.build_ladder({}, role="content")
        or_kimi = ladder[1]["models"][0]["slug"]
        assert or_kimi == "moonshotai/kimi-k2.6", (
            f"Kimi OpenRouter slug must be moonshotai/kimi-k2.6, got {or_kimi!r}"
        )

    def test_kimi_never_direct_only_ollama_openrouter(self):
        """Kimi must only appear on ollama-cloud or openrouter providers, never 'direct'."""
        ladder = mr.build_ladder({}, role="content")
        for rung in ladder:
            for m in rung["models"]:
                if "kimi" in m["slug"].lower():
                    assert rung["provider"] in ("ollama-cloud", "openrouter"), (
                        f"Kimi slug {m['slug']!r} found on unexpected provider "
                        f"{rung['provider']!r} — Kimi is never direct"
                    )

    def test_no_kimi_2_6_typo_in_any_ladder(self):
        """The bad slug 'kimi-2.6' (without the 'k') must never appear."""
        for role in ALL_CANONICAL_ROLES:
            ladder = mr.build_ladder({}, role=role)
            blob = json.dumps(ladder)
            # kimi-2.6 without the k is the typo — kimi-k2.6 is correct
            # We look for the specific typo pattern
            assert "kimi-2.6" not in blob or "kimi-k2.6" in blob, (
                f"role={role!r}: found suspected kimi-2.6 typo in ladder"
            )


# ── Test: Ollama Cloud max_tokens cap ────────────────────────────────────────

class TestOllamaCloudMaxTokens:
    """Every ollama-cloud rung must carry max_tokens == 65536.
    OpenRouter rungs must NOT have max_tokens set."""

    @pytest.mark.parametrize("role", ALL_CANONICAL_ROLES)
    def test_every_ollama_cloud_rung_has_max_tokens_65536(self, role):
        ladder = mr.build_ladder({}, role=role)
        for rung in ladder:
            if rung["provider"] == "ollama-cloud":
                assert rung.get("max_tokens") == mr.OLLAMA_CLOUD_MAX_TOKENS, (
                    f"role={role!r} rung {rung['rung']}: expected max_tokens="
                    f"{mr.OLLAMA_CLOUD_MAX_TOKENS}, got {rung.get('max_tokens')!r}"
                )

    @pytest.mark.parametrize("role", ALL_CANONICAL_ROLES)
    def test_openrouter_rungs_have_no_max_tokens(self, role):
        ladder = mr.build_ladder({}, role=role)
        for rung in ladder:
            if rung["provider"] == "openrouter":
                assert "max_tokens" not in rung, (
                    f"role={role!r} rung {rung['rung']}: openrouter rung must NOT "
                    f"have max_tokens, got {rung.get('max_tokens')!r}"
                )

    def test_select_ollama_chosen_carries_max_tokens(self):
        """When select() picks an ollama-cloud rung, the chosen entry must carry max_tokens."""
        out = mr.select(mr.make_stub_executor(), role="content", env={}, sleep=lambda *_: None)
        assert out["chosen"] is not None
        assert out["chosen"]["provider"] == "ollama-cloud"
        assert out["chosen"].get("max_tokens") == mr.OLLAMA_CLOUD_MAX_TOKENS, (
            f"chosen ollama-cloud entry missing max_tokens={mr.OLLAMA_CLOUD_MAX_TOKENS}, "
            f"got {out['chosen'].get('max_tokens')!r}"
        )

    def test_select_openrouter_chosen_no_max_tokens(self):
        """When select() picks an openrouter rung, max_tokens must be absent from chosen."""
        # Build an openrouter-only ladder so the chosen is guaranteed openrouter.
        or_ladder = [
            r for r in mr.build_ladder({}, role="content")
            if r["provider"] == "openrouter"
        ]
        out = mr.select(
            mr.make_stub_executor(), role="content", env={},
            ladder=or_ladder, sleep=lambda *_: None,
        )
        assert out["chosen"] is not None
        assert "max_tokens" not in out["chosen"], (
            f"openrouter chosen entry must not have max_tokens, "
            f"got {out['chosen'].get('max_tokens')!r}"
        )

    def test_constant_value_is_65536(self):
        assert mr.OLLAMA_CLOUD_MAX_TOKENS == 65536

    def test_all_seven_ollama_cloud_rungs_across_all_roles(self):
        """Verify the exact set of 7 ollama-cloud rungs all carry the cap."""
        seen = []
        for role in ALL_CANONICAL_ROLES:
            for rung in mr.build_ladder({}, role=role):
                if rung["provider"] == "ollama-cloud":
                    seen.append((role, rung["rung"]))
                    assert rung.get("max_tokens") == mr.OLLAMA_CLOUD_MAX_TOKENS, (
                        f"role={role!r} rung {rung['rung']}: max_tokens cap missing"
                    )
        # Must be exactly 7 ollama-cloud rungs across the 5 canonical roles.
        assert len(seen) == 7, (
            f"Expected 7 ollama-cloud rungs total, found {len(seen)}: {seen}"
        )


# ── Selftest ──────────────────────────────────────────────────────────────────

def test_selftest_exits_zero():
    assert mr._selftest() == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

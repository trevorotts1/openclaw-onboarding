# test_model_router.py — role-aware, probe-gated NON-ANTHROPIC model router.
# Fully offline: client model resolution, guards, probe-gate, and failover are
# exercised with the deterministic stub executor. The router prescribes no
# model by name: every ladder comes from the client's own configured choice /
# default (MODEL_ROUTER_CHOICE / MODEL_ROUTER_DEFAULT). MiniMax M2 ban,
# Anthropic ban, resolution precedence, the unconfigured ask-the-client stop,
# and assert_model_sovereignty are all independently verified.
from __future__ import annotations

import json
import os
import sys

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import model_router as mr  # noqa: E402


ALL_ROLES = ("content", "html", "reasoning", "execution", "qc")

# A configured client box in test form: a neutral configured default on
# Ollama Cloud, and a choice-plus-default pair for precedence/failover checks.
DEFAULT_ENV = {"MODEL_ROUTER_DEFAULT": "client-default:cloud"}
CHOICE_ENV = {
    "MODEL_ROUTER_CHOICE": "client/choice-model",
    "MODEL_ROUTER_DEFAULT": "client-default:cloud",
}


def _all_slugs(ladder):
    return [m["slug"] for rung in ladder for m in rung["models"]]


def _no_sleep(*_):
    return None


# ── Build: every role resolves ──────────────────────────────────────────────


class TestBuildAllRoles:

    @pytest.mark.parametrize("role", sorted(mr._VALID_ROLES) + sorted(mr._ROLE_ALIASES))
    def test_builds_nonempty(self, role):
        assert mr.build_ladder(DEFAULT_ENV, role=role)

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_no_anthropic_in_ladder(self, role):
        for slug in _all_slugs(mr.build_ladder(DEFAULT_ENV, role=role)):
            low = slug.lower()
            assert "claude" not in low
            assert "anthropic" not in low

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_rung_shape_complete(self, role):
        for rung in mr.build_ladder(CHOICE_ENV, role=role):
            for key in ("rung", "role", "provider", "base_url", "thinking", "models"):
                assert key in rung, f"rung missing {key}: {rung}"
            assert rung["role"] == role
            assert rung["thinking"] == "high"
            assert rung["models"], "rung must carry at least one model"
            for m in rung["models"]:
                assert m["slug"]
                assert m["family"]

    def test_unknown_role_raises(self):
        with pytest.raises(ValueError):
            mr.build_ladder(DEFAULT_ENV, role="bogus")

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_ladder_is_exactly_the_configured_models(self, role):
        # The router prescribes nothing: with only a default configured, the
        # ladder is exactly that one model.
        assert _all_slugs(mr.build_ladder(DEFAULT_ENV, role=role)) == ["client-default:cloud"]


# ── Resolution: rung 1 is the client's model ────────────────────────────────


class TestClientResolutionRung1:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_rung1_is_configured_default_when_no_choice(self, role):
        r1 = mr.build_ladder(DEFAULT_ENV, role=role)[0]
        assert r1["models"][0]["slug"] == "client-default:cloud"
        assert r1.get("resolution") == "client-default"

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_rung1_is_client_choice_when_set(self, role):
        r1 = mr.build_ladder(CHOICE_ENV, role=role)[0]
        assert r1["models"][0]["slug"] == "client/choice-model"
        assert r1.get("resolution") == "client-choice"
        assert r1["provider"] == "openrouter"  # derived from the slug shape

    @pytest.mark.parametrize("role", ("execution", "qc"))
    def test_probe_gated_roles(self, role):
        assert mr.build_ladder(DEFAULT_ENV, role=role)[0].get("probe_gated") is True

    @pytest.mark.parametrize("role", ("content", "html", "reasoning"))
    def test_non_probe_gated_roles(self, role):
        assert not mr.build_ladder(DEFAULT_ENV, role=role)[0].get("probe_gated")

    def test_qc_rung1_is_vision(self):
        assert mr.build_ladder(DEFAULT_ENV, role="qc")[0].get("vision") is True

    def test_family_derives_from_client_slug(self):
        env = {"MODEL_ROUTER_DEFAULT": "acme/big-model-2:cloud"}
        r1 = mr.build_ladder(env, role="content")[0]
        assert r1["models"][0]["family"] == "big"
        assert r1["provider"] == "ollama-cloud"


class TestResolutionOrder:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_choice_rung_before_default_rung(self, role):
        ladder = mr.build_ladder(CHOICE_ENV, role=role)
        assert [(r["models"][0]["slug"], r.get("resolution")) for r in ladder] == [
            ("client/choice-model", "client-choice"),
            ("client-default:cloud", "client-default"),
        ]

    def test_choice_equal_to_default_dedupes(self):
        env = {"MODEL_ROUTER_CHOICE": "same-model:cloud",
               "MODEL_ROUTER_DEFAULT": "same-model:cloud"}
        assert len(mr.build_ladder(env, role="content")) == 1


class TestResolutionPrecedence:

    def test_role_choice_beats_global_choice(self):
        env = dict(CHOICE_ENV)
        env["MODEL_ROUTER_CHOICE_EXECUTION"] = "role-pick:cloud"
        assert mr.build_ladder(env, role="execution")[0]["models"][0]["slug"] == "role-pick:cloud"

    def test_global_choice_beats_role_default(self):
        env = {"MODEL_ROUTER_CHOICE": "global-pick",
               "MODEL_ROUTER_DEFAULT_EXECUTION": "role-default"}
        ladder = mr.build_ladder(env, role="execution")
        assert ladder[0]["models"][0]["slug"] == "global-pick"
        assert ladder[1]["models"][0]["slug"] == "role-default"

    def test_role_default_beats_global_default(self):
        env = {"MODEL_ROUTER_DEFAULT": "global-default",
               "MODEL_ROUTER_DEFAULT_QC": "qc-default:cloud"}
        assert mr.build_ladder(env, role="qc")[0]["models"][0]["slug"] == "qc-default:cloud"
        assert mr.build_ladder(env, role="content")[0]["models"][0]["slug"] == "global-default"

    def test_resolve_client_models_empty_when_unconfigured(self):
        assert mr.resolve_client_models({}, "execution") == []


# ── Unconfigured client: the ask-the-client stop ────────────────────────────


class TestUnconfiguredStops:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_build_ladder_raises(self, role):
        with pytest.raises(mr.ClientModelNotConfiguredError):
            mr.build_ladder({}, role=role)

    def test_stop_message_asks_the_client(self):
        with pytest.raises(mr.ClientModelNotConfiguredError) as excinfo:
            mr.build_ladder({}, role="qc")
        assert "Ask the client" in str(excinfo.value)
        assert "configured default model" in str(excinfo.value)

    def test_select_propagates_the_stop(self):
        with pytest.raises(mr.ClientModelNotConfiguredError):
            mr.select(mr.make_stub_executor(), role="content", env={}, sleep=_no_sleep)


# ── No prescribed model names ───────────────────────────────────────────────

# Names the router must never prescribe. They may only ever appear when the
# CLIENT configured them (see test_client_configured_slug_is_honored).
PRESCRIBED = ("kimi", "moonshot", "glm", "minimax", "gemini", "deepseek")


class TestNoPrescribedNames:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_no_prescribed_slugs_in_neutral_env(self, role):
        for slug in _all_slugs(mr.build_ladder(CHOICE_ENV, role=role)):
            low = slug.lower()
            assert not any(p in low for p in PRESCRIBED), slug

    def test_client_configured_slug_is_honored_verbatim(self):
        # A client may configure any model they want, including one the old
        # doctrine used to prescribe; the router routes THEIR choice.
        env = {"MODEL_ROUTER_CHOICE": "moonshotai/kimi-k2.6"}
        ladder = mr.build_ladder(env, role="content")
        assert ladder[0]["models"][0]["slug"] == "moonshotai/kimi-k2.6"
        assert ladder[0]["models"][0]["family"] == "kimi"
        assert ladder[0]["provider"] == "openrouter"


# ── MiniMax M2 purge (permanent ban) ────────────────────────────────────────


class TestM2Purge:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_no_minimax_m2_anywhere(self, role):
        blob = json.dumps(mr.build_ladder(CHOICE_ENV, role=role)).lower()
        assert "minimax-m2" not in blob
        assert "minimax_m2" not in blob

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_no_prescribed_minimax_at_all(self, role):
        for slug in _all_slugs(mr.build_ladder(CHOICE_ENV, role=role)):
            assert "minimax" not in slug.lower()


# ── Failover via select() ───────────────────────────────────────────────────


class TestResolutionFallback:
    """When the client's chosen model fails its probe, select() advances to
    the client's configured default; when nothing configured passes, it
    chooses nothing. There is no named fallback."""

    def test_execution_choice_probe_fail_advances_to_default(self):
        out = mr.select(mr.make_stub_executor(fail_families=("choice",)),
                        role="execution", env=CHOICE_ENV, sleep=_no_sleep)
        assert out["chosen"] is not None
        assert out["chosen"]["rung"] == 2
        assert out["chosen"]["model"] == "client-default:cloud"

    def test_execution_all_configured_fail_chooses_none(self):
        out = mr.select(mr.make_stub_executor(fail_families=("choice", "client")),
                        role="execution", env=CHOICE_ENV, sleep=_no_sleep)
        assert out["chosen"] is None

    def test_qc_probe_fail_chooses_none(self):
        out = mr.select(mr.make_stub_executor(fail_families=("client",)),
                        role="qc", env=DEFAULT_ENV, sleep=_no_sleep)
        assert out["chosen"] is None

    def test_content_rung1_chosen_on_clean_stub(self):
        out = mr.select(mr.make_stub_executor(), role="content",
                        env=DEFAULT_ENV, sleep=_no_sleep)
        assert out["chosen"]["model"] == "client-default:cloud"
        assert out["chosen"]["provider"] == "ollama-cloud"
        assert out["chosen"]["thinking"] == "high"


# ── Model sovereignty (shared-utils gate, stubbed when absent) ──────────────


class TestModelSovereignty:

    def _patch_sovereignty(self, monkeypatch, fn):
        # model_router binds the shared-utils gate as ``_ams``; the router's
        # _sovereignty_check raises AnthropicModelError on a FORBIDDEN verdict.
        monkeypatch.setattr(mr, "_ams", fn, raising=False)

    def test_sovereignty_called_per_slug(self, monkeypatch):
        seen = []

        def fake(slug, **kw):
            seen.append(slug)
            return {"code": "OK"}

        self._patch_sovereignty(monkeypatch, fake)
        ladder = mr.build_ladder(DEFAULT_ENV, role="content")
        mr.select(mr.make_stub_executor(), role="content",
                  env=DEFAULT_ENV, ladder=ladder, sleep=_no_sleep)
        assert "client-default:cloud" in seen

    def test_sovereignty_blocks_anthropic(self, monkeypatch):
        def blocker(slug, **kw):
            if "claude" in slug.lower():
                return {"code": "FORBIDDEN", "reason": "Anthropic blocked"}
            return {"code": "OK"}

        self._patch_sovereignty(monkeypatch, blocker)
        ladder = mr.build_ladder(DEFAULT_ENV, role="content")
        ladder[0]["models"][0]["slug"] = "BANNED-claude-sentinel"
        with pytest.raises(mr.AnthropicModelError):
            mr.select(mr.make_stub_executor(), role="content",
                      env=DEFAULT_ENV, ladder=ladder, sleep=_no_sleep)

    def test_sovereignty_blocks_free_literal(self, monkeypatch):
        def blocker(slug, **kw):
            if slug.strip().lower() == "openrouter/free":
                return {"code": "FORBIDDEN", "reason": "free literal blocked"}
            return {"code": "OK"}

        self._patch_sovereignty(monkeypatch, blocker)
        ladder = mr.build_ladder(DEFAULT_ENV, role="content")
        # Make rung 1 a well-formed OpenRouter rung carrying the free literal,
        # so the walk reaches the sovereignty gate instead of skipping the
        # rung on the Ollama Cloud invariants.
        ladder[0]["provider"] = "openrouter"
        ladder[0]["base_url"] = mr.OPENROUTER_BASE_URL
        ladder[0].pop("max_tokens", None)
        ladder[0]["models"][0]["slug"] = "openrouter/free"
        with pytest.raises(mr.AnthropicModelError):
            mr.select(mr.make_stub_executor(), role="content",
                      env=DEFAULT_ENV, ladder=ladder, sleep=_no_sleep)


# ── Anthropic guard ─────────────────────────────────────────────────────────


class TestAnthropicGuard:

    def test_injected_anthropic_slug_rejected(self):
        ladder = mr.build_ladder(DEFAULT_ENV, role="execution")
        ladder[0]["models"][0]["slug"] = "BANNED-claude-sentinel"
        with pytest.raises(mr.AnthropicModelError):
            mr.assert_no_anthropic(ladder)

    def test_configured_anthropic_default_rejected(self):
        with pytest.raises(mr.AnthropicModelError):
            mr.build_ladder({"MODEL_ROUTER_DEFAULT": "anthropic/claude-x"}, role="content")


# ── Ollama Cloud invariants ─────────────────────────────────────────────────


class TestOllamaCloudInvariants:

    def test_cloud_rungs_carry_suffix_and_base_url(self):
        for role in ALL_ROLES:
            for rung in mr.build_ladder(DEFAULT_ENV, role=role):
                if rung["provider"] == "ollama-cloud":
                    assert "ollama.com" in rung["base_url"]
                    for m in rung["models"]:
                        assert m["slug"].endswith(":cloud")

    def test_missing_cloud_suffix_raises(self):
        rung = dict(mr.build_ladder(DEFAULT_ENV, role="content")[0])
        rung["models"] = [dict(rung["models"][0], slug="client-default")]  # no :cloud
        with pytest.raises(mr.OllamaCloudConfigError):
            mr.assert_ollama_cloud_ready(rung, {})

    def test_wrong_base_url_raises(self):
        rung = dict(mr.build_ladder(DEFAULT_ENV, role="execution")[0])
        rung["base_url"] = "https://example.invalid"
        with pytest.raises(mr.OllamaCloudConfigError):
            mr.assert_ollama_cloud_ready(rung, {})


# ── thinking=high ───────────────────────────────────────────────────────────


class TestThinkingEffort:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_rung_high(self, role):
        for rung in mr.build_ladder(CHOICE_ENV, role=role):
            assert rung["thinking"] == "high"


# ── Probe gate + select receipts ────────────────────────────────────────────


class TestProbeAndSelect:

    def test_execution_clean_stub_picks_rung1(self):
        out = mr.select(mr.make_stub_executor(), role="execution",
                        env=CHOICE_ENV, sleep=_no_sleep)
        assert out["chosen"]["rung"] == 1
        assert out["chosen"]["model"] == "client/choice-model"

    def test_receipt_written_and_valid(self, tmp_path):
        receipt = tmp_path / "receipt.json"
        out = mr.select(mr.make_stub_executor(), role="content",
                        env=DEFAULT_ENV, sleep=_no_sleep,
                        receipt_path=str(receipt))
        assert receipt.exists()
        data = json.loads(receipt.read_text(encoding="utf-8"))
        assert data["chosen"]["model"] == "client-default:cloud"
        assert data["role"] == "content"
        assert data["ladder"], "receipt must embed the full ladder"
        assert "probe_results" in data
        assert out["chosen"]["model"] == "client-default:cloud"
        # The receipt policy names no prescribed model.
        assert "client's configured default model" in data["policy"]

    def test_probe_passes_semantics(self):
        good = {"tool_call_fired": True, "parsed": True, "args": {"ok": True}}
        assert mr.probe_passes(good) is True
        assert mr.probe_passes({"tool_call_fired": True}) is False  # unparsed
        assert mr.probe_passes({"tool_call_fired": True, "parsed": True,
                                "args": {"ok": False}}) is False
        assert mr.probe_passes({"tool_call_fired": False, "parsed": True,
                                "args": {"ok": True}}) is False
        assert mr.probe_passes({"text": "sure thing"}) is False
        assert mr.probe_passes(None) is False


# ── Ollama Cloud max_tokens cap (Ollama Cloud output-cap trap) ─────────────
# Every ollama-cloud rung MUST carry max_tokens == OLLAMA_CLOUD_MAX_TOKENS
# (65536, the live-measured API cap) and openrouter rungs MUST NOT inherit it.


class TestOllamaCloudMaxTokens:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_ollama_rung_carries_cap(self, role):
        for rung in mr.build_ladder(DEFAULT_ENV, role=role):
            if rung["provider"] == "ollama-cloud":
                assert rung.get("max_tokens") == mr.OLLAMA_CLOUD_MAX_TOKENS, (
                    f"{role} rung {rung['rung']} ollama-cloud rung missing "
                    f"max_tokens cap (Ollama Cloud output-cap trap)"
                )

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_openrouter_rungs_have_no_cap(self, role):
        env = {"MODEL_ROUTER_DEFAULT": "client/default-model"}
        for rung in mr.build_ladder(env, role=role):
            assert rung["provider"] == "openrouter"
            assert "max_tokens" not in rung, (
                f"{role} rung {rung['rung']} openrouter rung must not carry "
                f"max_tokens"
            )

    def test_total_ollama_rung_count_with_default_only(self):
        # With only a configured default, each role's ladder is exactly one
        # ollama-cloud rung: 5 roles, 5 capped rungs.
        count = sum(
            1
            for role in ALL_ROLES
            for rung in mr.build_ladder(DEFAULT_ENV, role=role)
            if rung["provider"] == "ollama-cloud"
        )
        assert count == 5

    def test_select_carries_cap_to_chosen(self):
        out = mr.select(mr.make_stub_executor(), role="content",
                        env=DEFAULT_ENV, sleep=_no_sleep)
        assert out["chosen"]["max_tokens"] == mr.OLLAMA_CLOUD_MAX_TOKENS

    def test_select_openrouter_chosen_has_no_cap(self):
        env = {"MODEL_ROUTER_DEFAULT": "client/default-model"}
        out = mr.select(mr.make_stub_executor(), role="content",
                        env=env, sleep=_no_sleep)
        assert out["chosen"]["provider"] == "openrouter"
        assert "max_tokens" not in out["chosen"]

    def test_constant_is_live_measured_cap(self):
        # 65536 = the live Ollama Cloud /api/chat output-token ceiling.
        assert mr.OLLAMA_CLOUD_MAX_TOKENS == 65536


# ── Self-test entry point ───────────────────────────────────────────────────


class TestSelftestEntryPoint:

    def test_selftest_exits_zero(self):
        import subprocess
        script = os.path.join(_TOOLS_DIR, "model_router.py")
        proc = subprocess.run(
            [sys.executable, script, "--selftest"],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

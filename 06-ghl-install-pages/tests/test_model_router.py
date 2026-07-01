# test_model_router.py — Area-4 probe-gated NON-ANTHROPIC model fallback ladder.
# Fully offline: the ladder, guards, probe-gate, and failover are exercised with
# the deterministic stub executor.
from __future__ import annotations

import json
import os
import sys

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import model_router as mr  # noqa: E402


class TestLadderShape:
    def test_six_rungs_ollama_cloud_before_openrouter(self):
        ladder = mr.build_ladder({})
        assert [r["rung"] for r in ladder] == [1, 2, 3, 4, 5, 6]
        assert [r["provider"] for r in ladder] == ["ollama-cloud"] * 3 + ["openrouter"] * 3

    def test_roles_minimax_deepseek_glm(self):
        ladder = mr.build_ladder({})
        assert ladder[0]["models"][0]["family"] == "minimax"
        assert ladder[0]["probe_gated"] is True
        assert ladder[1]["models"][0]["family"] == "deepseek"
        assert ladder[2]["models"][0]["family"] == "glm"

    def test_every_rung_thinking_high(self):
        for r in mr.build_ladder({}):
            assert r["thinking"] == "high"

    def test_slugs_overridable_via_env(self):
        env = {"MODEL_ROUTER_OLLAMA_DEEPSEEK": "deepseek-v4-pro-custom:cloud"}
        ladder = mr.build_ladder(env)
        assert ladder[1]["models"][0]["slug"] == "deepseek-v4-pro-custom:cloud"


class TestAnthropicGuard:
    def test_clean_ladder_passes(self):
        mr.assert_no_anthropic(mr.build_ladder({}))  # no raise

    def test_no_anthropic_marker_in_ladder_json(self):
        blob = json.dumps(mr.build_ladder({})).lower()
        for marker in mr._ANTHROPIC_MARKERS:
            assert marker not in blob

    @pytest.mark.parametrize("bad_slug", ["claude-x", "anthropic/foo", "some-opus", "a-sonnet-b", "haiku-1"])
    def test_guard_rejects_injected_anthropic(self, bad_slug):
        ladder = mr.build_ladder({})
        ladder[0]["models"][0]["slug"] = bad_slug
        with pytest.raises(mr.AnthropicModelError):
            mr.assert_no_anthropic(ladder)


class TestOllamaCloudInvariants:
    def test_cloud_suffix_and_baseurl_ok(self):
        for r in mr.build_ladder({})[:3]:
            mr.assert_ollama_cloud_ready(r, {})  # no raise

    def test_missing_cloud_suffix_raises(self):
        r = mr.build_ladder({})[1]
        r["models"][0]["slug"] = "deepseek-v4-pro"  # no :cloud
        with pytest.raises(mr.OllamaCloudConfigError):
            mr.assert_ollama_cloud_ready(r, {})

    def test_wrong_baseurl_raises(self):
        r = mr.build_ladder({})[0]
        r["base_url"] = "https://api.example.com"
        with pytest.raises(mr.OllamaCloudConfigError):
            mr.assert_ollama_cloud_ready(r, {})


class TestProbeAndSelect:
    def test_probe_passes_requires_tool_call(self):
        assert mr.probe_passes({"tool_call_fired": True, "parsed": True, "args": {"ok": True}}) is True
        assert mr.probe_passes({"tool_call_fired": False, "parsed": True, "args": {"ok": True}}) is False
        assert mr.probe_passes({"tool_call_fired": True, "parsed": True, "args": {}}) is False
        assert mr.probe_passes(None) is False
        assert mr.probe_passes("plausible non-tool text") is False

    def test_clean_run_chooses_rung1_minimax(self):
        out = mr.select(mr.make_stub_executor(), env={}, sleep=lambda *_: None)
        assert out["chosen"]["rung"] == 1
        assert out["chosen"]["provider"] == "ollama-cloud"
        assert out["chosen"]["thinking"] == "high"

    def test_minimax_probe_fail_advances_to_deepseek(self):
        out = mr.select(mr.make_stub_executor(fail_families=("minimax",)), env={}, sleep=lambda *_: None)
        assert out["chosen"]["rung"] == 2
        assert "deepseek" in out["chosen"]["model"]

    def test_chosen_is_never_anthropic(self):
        out = mr.select(mr.make_stub_executor(advance_families=("minimax",)), env={}, sleep=lambda *_: None)
        assert out["chosen"] is not None
        assert not mr._looks_anthropic(out["chosen"]["model"])

    def test_receipt_written_outside_skill_dir(self, tmp_path):
        out_path = tmp_path / "routing" / "model-ladder.json"
        mr.select(mr.make_stub_executor(), env={}, sleep=lambda *_: None, receipt_path=str(out_path))
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert data["chosen"]["rung"] == 1
        # The ladder block carries no Anthropic model id (the policy banner's
        # defensive "NEVER Anthropic" string is expected and is not a model).
        assert not mr._looks_anthropic(json.dumps(data["ladder"]))


def test_selftest_exits_zero():
    assert mr._selftest() == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

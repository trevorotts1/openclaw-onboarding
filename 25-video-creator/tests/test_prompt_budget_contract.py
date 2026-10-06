"""KIE prompt rule 12 before submit: the kieai provider refuses a prompt outside 95-100 percent of the model
max (hard floor 80 percent) and names the exact characters to add or cut. Hermetic: the real Skill 74 adapter
answers from its registry snapshot (no key, empty HOME); requests.post is a trap that must not be reached."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest

try:
    import requests as _requests  # noqa: F401
except ModuleNotFoundError:
    stub = ModuleType("requests")

    class RequestException(Exception):
        pass

    stub.RequestException = RequestException
    sys.modules["requests"] = stub

SCRIPTS = Path(os.environ.get("SKILL25_ROOT", Path(__file__).resolve().parents[1])) / "scripts"
MODEL = "gpt-image-2-5-sunburst-text-to-image"  # any KIE model with a maxLength; 20,000 in the registry snapshot
MAX = 20000


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("HOME", tempfile.mkdtemp())
    monkeypatch.delenv("KIE_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location("skill25_ai_providers_budget", SCRIPTS / "ai_providers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reached = []

    def trap(*args, **kwargs):
        reached.append(args)
        raise module.requests.RequestException("submit reached")

    monkeypatch.setattr(module.requests, "post", trap, raising=False)
    ai = module.AIProvider("kieai", {"kieai": {"api_key": "test-only-not-a-key"}})
    return ai, reached


def go(ai, n, **kw):
    return ai.generate_video("x" * n, model=MODEL, output=Path("unused.mp4"), **kw)


def test_79_percent_is_rejected_before_submit_with_chars_to_add(provider):
    ai, reached = provider
    with pytest.raises(ValueError, match="ADD at least 200"):
        go(ai, MAX * 79 // 100)
    assert reached == []


def test_101_percent_is_rejected_before_submit_with_chars_to_cut(provider):
    ai, reached = provider
    with pytest.raises(ValueError, match="CUT exactly 200"):
        go(ai, MAX * 101 // 100)
    assert reached == []


@pytest.mark.parametrize("pct", [95, 100])
def test_in_band_prompt_reaches_submit(provider, pct):
    ai, reached = provider
    with pytest.raises(RuntimeError, match="submit reached"):
        go(ai, MAX * pct // 100)
    assert len(reached) == 1


def test_no_model_id_means_unknown_limit_and_no_floor(provider):
    ai, reached = provider
    with pytest.raises(RuntimeError, match="submit reached"):
        ai.generate_video("short", output=Path("unused.mp4"))
    assert len(reached) == 1

"""Fix 6 (cost_unknown) — OpenRouter prices at $0.

THE DEFECT
OpenRouter-routed models were priced from the static catalog, which carried
no usable OpenRouter rate: they fell through to cost_unknown and were
treated as $0, so ultra launches could spend on unpriced routes.

THE FIX (three ordered changes, all in credit_preflight.py)
  1. `_alias_for_route` also matches entry["served_ids"][provider] == model,
     so an OpenRouter-served id resolves its catalog alias even when the
     alias's own "model" field spells a different id.
  2. Any OpenRouter route prices from the `pricing` field of OpenRouter's
     live model list (https://openrouter.ai/api/v1/models), cached for the
     run; the static catalog is only the fallback. This covers every
     OpenRouter model, including the client-selected one.
  3. An unpriceable phase on a PAID provider: ultra is BLOCKED before any
     spend (plain message naming the model); standard and economy keep the
     existing cost_unknown warning.

THE TESTS (per the fix order)
  - A mocked OpenRouter live-list response prices a route above $0.
  - An unpriceable paid ultra route parks before any paid call.
Plus: the served_ids alias match, and the catalog fallback when the live
list cannot be fetched.

`preflight` is PURE (module docstring: no sockets, no keys) -- there is no
paid-call seam inside it to fire. The blocked verdict (which main turns
into exit 1, refusing the launch) IS the park-before-spend; the tests
assert the verdict, the $0 estimate, and the model-naming message.

Flat file inside tests/, manages its own import path -- matching every
sibling here.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from urllib.error import URLError

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from presentation_job import credit_preflight as cp  # noqa: E402


def _routes():
    return {"phase1": {"route": {"provider": "deepseek-direct",
                                 "model": "no-such-model-xyz"}}}


def test_alias_for_route_matches_served_ids():
    """Change 1: the OpenRouter-served id resolves its catalog alias via
    served_ids even though the alias's own model field spells another id."""
    assert cp._alias_for_route({"provider": "openrouter",
                                "model": "z-ai/glm-5.3-flash"}) == "text.judge"
    assert cp._alias_for_route({"provider": "openrouter",
                                "model": "z-ai/glm-4.6v"}) == "vision.ocr"


class _FakeResp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_openrouter_live_list_prices_above_zero(monkeypatch):
    """Change 2 / MUST-TEST 1: a mocked live-list response prices the
    OpenRouter route above $0."""
    payload = {"data": [
        {"id": "z-ai/glm-5.3",
         "pricing": {"prompt": "0.0000006", "completion": "0.0000012"}},
        {"id": "openai/gpt-4o-mini",
         "pricing": {"prompt": "0.00000015", "completion": "0.0000006"}},
    ]}
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=10: _FakeResp(payload))
    cp._reset_openrouter_pricing_cache()
    try:
        rate = cp._rate_for({"provider": "openrouter", "model": "z-ai/glm-5.3"})
    finally:
        cp._reset_openrouter_pricing_cache()
    assert rate["status"] == "priced"
    assert rate["shape"] == "per_million_tokens"
    assert rate["per_million_tokens_in_usd"] > 0
    assert rate["per_million_tokens_out_usd"] > 0
    assert rate["rate_source"] == "openrouter live list"


def test_openrouter_falls_back_to_catalog(monkeypatch):
    """Change 2: when the live list cannot be fetched, the static catalog
    answers -- here via the served_ids alias (text.judge, $0.15/$0.60)."""
    def _boom(req, timeout=10):
        raise URLError("offline in test")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    cp._reset_openrouter_pricing_cache()
    try:
        rate = cp._rate_for({"provider": "openrouter",
                             "model": "z-ai/glm-5.3-flash"})
    finally:
        cp._reset_openrouter_pricing_cache()
    assert rate["status"] == "priced"
    assert rate["rate_source"] != "openrouter live list"
    assert rate["per_million_tokens_in_usd"] == 0.15
    assert rate["per_million_tokens_out_usd"] == 0.6


def test_unpriceable_paid_ultra_blocks_before_spend():
    """Change 3 / MUST-TEST 2: an unpriceable paid route in ultra is refused
    before any spend -- blocked verdict, $0 estimate, message names the
    model. preflight is pure, so the blocked verdict is the whole park."""
    v = cp.preflight("ultra", routes=_routes(),
                     balances={"deepseek-direct": 100.0},
                     measured_calls={"phase1": 3})
    assert v["verdict"] == "blocked"
    assert v["total_estimate_usd"] == 0.0
    assert v["downgrade_to"] is None  # a pricing problem is not a budget problem
    details = [b["detail"] for b in v["blocking"]]
    assert any("no-such-model-xyz" in d for d in details), details
    assert not any(w["code"] == cp.CODE_COST_UNKNOWN for w in v["warnings"])


def test_unpriceable_paid_standard_warns():
    """Change 3 control: standard keeps the existing cost_unknown warning
    and proceeds loudly."""
    v = cp.preflight("standard", routes=_routes(),
                     balances={"deepseek-direct": 100.0},
                     measured_calls={"phase1": 3})
    assert v["verdict"] == "proceed"
    assert not v["blocking"]
    assert any(w["code"] == cp.CODE_COST_UNKNOWN for w in v["warnings"])


def test_unpriceable_paid_economy_warns():
    """Change 3 control: economy behaves like standard."""
    v = cp.preflight("economy", routes=_routes(),
                     balances={"deepseek-direct": 100.0},
                     measured_calls={"phase1": 3})
    assert v["verdict"] == "proceed"
    assert not v["blocking"]
    assert any(w["code"] == cp.CODE_COST_UNKNOWN for w in v["warnings"])

"""FIX 61.4 regression: check_openrouter_model must return its 2-tuple.

THE DEFECT
credit_preflight.check_openrouter_model documents Returns (ok: bool,
reason: str), and both callers unpack two values:

  - presentation-intake-poll.sh (FIX 61.4 ultra-check block):
        ok, reason = cp.check_openrouter_model(str(or_model))
  - presentation_job/launcher.py (model-plan gate, ultra branch):
        _ok, _reason = _cp.check_openrouter_model(str(_or_model))

Every path honored the contract EXCEPT the success path: a declared model
that IS on the live list and is NOT retired fell through to a final line
that read literally `return True, ` (trailing comma, nothing after it),
which returns the 1-tuple (True,). A valid model therefore raised
ValueError ("not enough values to unpack") at both call sites: on the
launcher path the ultra launch failed at the pre-check precisely because
the model was fine, and on the poller path the run was counted REFUSED for
a spurious reason while the FIX 61.4 validation silently never validated.
Unknown and retired models returned proper 2-tuples and refused
correctly, which is why the bug only ever bit GOOD declarations.

THE FIX
The success path returns (True, "") like the no-model-declared path.

THE TESTS
  - A valid, non-retired model returns a 2-tuple and passes (the exact
    unpack both callers perform is exercised).
  - An unknown model refuses, naming the model.
  - A retired model refuses, naming the retirement.
  - A model whose expiration_date is still in the future passes.
  - EVERY path returns a tuple of length 2 (the contract pin).

The valid/unknown cases mock the live-list fetch (urllib.request.urlopen)
exactly like test_fix6_openrouter_pricing.py. The retired/future cases
patch the _openrouter_live_pricing seam directly, because the checker
consumes expiration_date from the live table entries while the fetcher
currently keeps only the pricing fields when it builds that table; the
table is supplied here in the shape the checker's docstring documents.

Flat file inside tests/, manages its own import path, matching every
sibling here. No network: every fetch is mocked or seamed.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from presentation_job import credit_preflight as cp  # noqa: E402

VALID_MODEL = "z-ai/glm-5.3"
UNKNOWN_MODEL = "no-such-vendor/no-such-model-xyz"


class _FakeResp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _mock_live_list(monkeypatch, model_ids):
    payload = {"data": [
        {"id": mid,
         "pricing": {"prompt": "0.0000006", "completion": "0.0000012"}}
        for mid in model_ids
    ]}
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=10: _FakeResp(payload))
    cp._reset_openrouter_pricing_cache()


def test_valid_model_returns_two_tuple_and_passes(monkeypatch):
    """The regression case: a declared model that is on the live list and
    not retired must return (True, "") as a real 2-tuple, so the two-value
    unpack both callers perform succeeds."""
    _mock_live_list(monkeypatch, [VALID_MODEL])
    try:
        result = cp.check_openrouter_model(VALID_MODEL)
    finally:
        cp._reset_openrouter_pricing_cache()
    assert isinstance(result, tuple) and len(result) == 2, result
    ok, reason = result  # the exact unpack the poller and launcher perform
    assert ok is True
    assert reason == ""


def test_unknown_model_refused(monkeypatch):
    """FIX 61.3: an unknown OpenRouter model refuses the ultra launch
    before any spend, with a reason naming the model."""
    _mock_live_list(monkeypatch, [VALID_MODEL])
    try:
        result = cp.check_openrouter_model(UNKNOWN_MODEL)
    finally:
        cp._reset_openrouter_pricing_cache()
    assert isinstance(result, tuple) and len(result) == 2, result
    ok, reason = result
    assert ok is False
    assert UNKNOWN_MODEL in reason
    assert "unknown" in reason


def test_retired_model_refused(monkeypatch):
    """FIX 61.3: a model whose expiration_date has passed is retired and
    refuses, even though it is still on the live list."""
    table = {VALID_MODEL: {"in_usd_per_mtok": 0.6,
                           "out_usd_per_mtok": 1.2,
                           "expiration_date": "2020-01-01T00:00:00Z"}}
    monkeypatch.setattr(cp, "_openrouter_live_pricing", lambda: table)
    ok, reason = cp.check_openrouter_model(VALID_MODEL)
    assert ok is False
    assert "retired" in reason
    assert VALID_MODEL in reason


def test_not_yet_retired_model_passes(monkeypatch):
    """Control for the retired case: an expiration_date in the future is
    not a retirement, and the success path still returns the 2-tuple."""
    table = {VALID_MODEL: {"in_usd_per_mtok": 0.6,
                           "out_usd_per_mtok": 1.2,
                           "expiration_date": "2999-01-01T00:00:00Z"}}
    monkeypatch.setattr(cp, "_openrouter_live_pricing", lambda: table)
    result = cp.check_openrouter_model(VALID_MODEL)
    assert isinstance(result, tuple) and len(result) == 2, result
    ok, reason = result
    assert ok is True
    assert reason == ""


def test_every_path_returns_two_tuple(monkeypatch):
    """The contract pin: no input class may fall off the (ok, reason)
    contract again -- no declaration, blank declaration, valid, unknown,
    retired, and an unparseable expiration_date (treated as not retired,
    never as a crash)."""
    _mock_live_list(monkeypatch, [VALID_MODEL])
    try:
        for model_id in ("", "   ", VALID_MODEL, UNKNOWN_MODEL):
            result = cp.check_openrouter_model(model_id)
            assert isinstance(result, tuple) and len(result) == 2, \
                (model_id, result)
    finally:
        cp._reset_openrouter_pricing_cache()
    table = {VALID_MODEL: {"in_usd_per_mtok": 0.6,
                           "out_usd_per_mtok": 1.2,
                           "expiration_date": "not-a-date"}}
    monkeypatch.setattr(cp, "_openrouter_live_pricing", lambda: table)
    result = cp.check_openrouter_model(VALID_MODEL)
    assert isinstance(result, tuple) and len(result) == 2, result
    assert result[0] is True

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
patch the _openrouter_live_pricing seam directly with the table in the
shape the checker's docstring documents.

B5 FOLLOW-ON (expiration_date plumbing): the seam-patched cases above
proved the CHECKER honors expiration_date, but the FETCHER used to drop
the field when it built the live table from the API payload, so the
retired branch was unreachable through the module's own fetch path.
_openrouter_live_pricing now carries each item's raw expiration_date
through (the same keep-the-raw-expiration pattern as
capacity._extract_model_pricing), and the last three tests below drive
the whole fetcher-to-checker path off a mocked API payload: expired
model refused, future expiration carried and passing, absent/null
expiration passing.

Flat file inside tests/, manages its own import path, matching every
sibling here. No network: every fetch is mocked or seamed.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# B5: the fetcher-to-checker path, end to end. These mock the API payload
# itself (urllib.request.urlopen), NOT the _openrouter_live_pricing seam,
# so they fail on the pre-plumbing fetcher: an entry built from the payload
# carried no expiration_date and the retired refusal could never fire.
# ---------------------------------------------------------------------------

def _mock_live_payload(monkeypatch, items):
    payload = {"data": items}
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=10: _FakeResp(payload))
    cp._reset_openrouter_pricing_cache()


def test_expired_model_refused_through_the_real_fetcher(monkeypatch):
    """A mocked API payload whose model carries a past expiration_date:
    the fetcher must carry the field into the live table and the checker
    must refuse the model as retired. Before the plumbing fix this exact
    payload passed, because the fetcher dropped expiration_date."""
    _mock_live_payload(monkeypatch, [
        {"id": VALID_MODEL,
         "pricing": {"prompt": "0.0000006", "completion": "0.0000012"},
         "expiration_date": "2020-01-01T00:00:00Z"},
    ])
    try:
        table = cp._openrouter_live_pricing()
        assert table[VALID_MODEL]["expiration_date"] == "2020-01-01T00:00:00Z"
        result = cp.check_openrouter_model(VALID_MODEL)
    finally:
        cp._reset_openrouter_pricing_cache()
    assert isinstance(result, tuple) and len(result) == 2, result
    ok, reason = result
    assert ok is False
    assert "retired" in reason
    assert VALID_MODEL in reason


def test_future_expiration_carried_and_passes_through_the_fetcher(monkeypatch):
    """Control for the expired case on the same path: a future
    expiration_date is carried into the table verbatim, the pricing fields
    survive beside it, and the model passes."""
    _mock_live_payload(monkeypatch, [
        {"id": VALID_MODEL,
         "pricing": {"prompt": "0.0000006", "completion": "0.0000012"},
         "expiration_date": "2999-01-01T00:00:00Z"},
    ])
    try:
        table = cp._openrouter_live_pricing()
        assert table[VALID_MODEL]["expiration_date"] == "2999-01-01T00:00:00Z"
        assert table[VALID_MODEL]["in_usd_per_mtok"] == pytest.approx(0.6)
        result = cp.check_openrouter_model(VALID_MODEL)
    finally:
        cp._reset_openrouter_pricing_cache()
    assert isinstance(result, tuple) and len(result) == 2, result
    ok, reason = result
    assert ok is True
    assert reason == ""


def test_absent_or_null_expiration_passes_through_the_fetcher(monkeypatch):
    """Most live models carry no expiration_date at all (or null): the
    fetcher must not invent one, and the checker treats the model as not
    retired."""
    _mock_live_payload(monkeypatch, [
        {"id": VALID_MODEL,
         "pricing": {"prompt": "0.0000006", "completion": "0.0000012"}},
        {"id": "z-ai/glm-5.3-flash",
         "pricing": {"prompt": "0.0000006", "completion": "0.0000012"},
         "expiration_date": None},
    ])
    try:
        table = cp._openrouter_live_pricing()
        assert table[VALID_MODEL].get("expiration_date") is None
        assert table["z-ai/glm-5.3-flash"].get("expiration_date") is None
        for mid in (VALID_MODEL, "z-ai/glm-5.3-flash"):
            result = cp.check_openrouter_model(mid)
            assert isinstance(result, tuple) and len(result) == 2, result
            assert result[0] is True, (mid, result)
    finally:
        cp._reset_openrouter_pricing_cache()

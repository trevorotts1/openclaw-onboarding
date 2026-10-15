#!/usr/bin/env python3
"""test_capacity_pricing_absent.py -- absent pricing is ABSENT, never 0.

The defect (surfaced by the FIX 31 stream, B40): capacity's
_extract_model_pricing zero-filled a catalog item that carried no
pricing blob, so an unpriced model arrived downstream with
prompt_per_million = completion_per_million = 0.0 -- indistinguishable
from a genuinely free model by key presence, and renderable as a
fabricated "$0" price. The fix represents an absent direction as
None. A pricing blob that IS present with a real "0" still extracts
as 0.0: None means the catalog said nothing, 0.0 means the catalog
said zero.

What is pinned here:
  (a) an unpriced catalog entry extracts as unpriced (None), never 0;
  (b) a priced entry extracts its real numbers unchanged, and a real
      zero stays a real 0.0 (distinct from absent);
  (c) each audited consumer of the extraction behaves on unpriced
      input as the B43 manifest names: the probe verdict carries the
      None fields through; the probe() surface never carries pricing
      at all; resource_profile.store_provider_probes persists no
      pricing; credit_preflight never read capacity's table (its own
      live-list parser represents unpriced as absence from its table);
  (d) FIX 31's freshness renderer (model_freshness, landed on the
      stacked PR #2049 branch) still renders its unpriced wording
      against the fixed extraction. That module is not on this base,
      so (d) skips here and runs for real in the combined tree (the
      B43 manifest records where).
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity as cap  # noqa: E402
from presentation_job import credit_preflight as cp  # noqa: E402
from presentation_job import resource_profile as rp  # noqa: E402

OR = "openrouter"


def _body(items) -> bytes:
    return json.dumps({"data": items}).encode()


# ---------------------------------------------------------------------------
# (a) unpriced extracts as unpriced, never 0
# ---------------------------------------------------------------------------
def test_unpriced_item_extracts_none_not_zero():
    out = cap._extract_model_pricing(_body([{"id": "vendor/model-a"}]))
    assert out["vendor/model-a"]["prompt_per_million"] is None
    assert out["vendor/model-a"]["completion_per_million"] is None


def test_null_and_empty_pricing_blobs_extract_none():
    out = cap._extract_model_pricing(_body([
        {"id": "m/null", "pricing": None},
        {"id": "m/empty", "pricing": {}},
        {"id": "m/nondict", "pricing": "n/a"},
    ]))
    for mid in ("m/null", "m/empty", "m/nondict"):
        assert out[mid]["prompt_per_million"] is None
        assert out[mid]["completion_per_million"] is None


def test_half_priced_item_marks_only_the_absent_direction():
    out = cap._extract_model_pricing(_body([
        {"id": "m/half", "pricing": {"prompt": "0.0000006"}},
        {"id": "m/nullhalf",
         "pricing": {"prompt": None, "completion": "0.0000012"}},
        {"id": "m/emptystr",
         "pricing": {"prompt": "", "completion": "0.0000012"}},
    ]))
    assert out["m/half"]["prompt_per_million"] == pytest.approx(0.6)
    assert out["m/half"]["completion_per_million"] is None
    assert out["m/nullhalf"]["prompt_per_million"] is None
    assert out["m/nullhalf"]["completion_per_million"] == pytest.approx(1.2)
    assert out["m/emptystr"]["prompt_per_million"] is None
    assert out["m/emptystr"]["completion_per_million"] == pytest.approx(1.2)


def test_unpriced_item_keeps_its_expiration_date():
    # The retired-model check reads expiration_date off the entry; an
    # unpriced-but-expiring model must not lose that signal.
    out = cap._extract_model_pricing(_body([
        {"id": "m/old", "expiration_date": "2020-01-01"},
    ]))
    assert out["m/old"]["expiration_date"] == "2020-01-01"
    assert out["m/old"]["prompt_per_million"] is None


def test_unparseable_pricing_keeps_the_skip_behavior():
    # Pre-existing behavior, unchanged: a present-but-unparseable price
    # yields NO entry at all (absent by omission), never a number.
    out = cap._extract_model_pricing(_body([
        {"id": "m/garbage", "pricing": {"prompt": "abc",
                                        "completion": "0.0000012"}},
        {"id": "m/fine", "pricing": {"prompt": "0.0000006",
                                     "completion": "0.0000012"}},
    ]))
    assert "m/garbage" not in out
    assert out["m/fine"]["prompt_per_million"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# (b) priced extracts its real numbers unchanged; a real zero stays zero
# ---------------------------------------------------------------------------
def test_priced_item_extracts_real_numbers_unchanged():
    out = cap._extract_model_pricing(_body([
        {"id": "m/priced", "pricing": {"prompt": "0.0000006",
                                       "completion": "0.0000012"}},
        {"id": "m/numeric", "pricing": {"prompt": 0.0000006,
                                        "completion": 0}},
    ]))
    assert out["m/priced"]["prompt_per_million"] == pytest.approx(0.6)
    assert out["m/priced"]["completion_per_million"] == pytest.approx(1.2)
    assert out["m/numeric"]["prompt_per_million"] == pytest.approx(0.6)
    assert out["m/numeric"]["completion_per_million"] == 0.0


def test_genuine_zero_price_is_zero_not_absent():
    # The distinction the representation exists to keep: a catalog blob
    # that says "0" extracts as 0.0, which is NOT None.
    out = cap._extract_model_pricing(_body([
        {"id": "m/free", "pricing": {"prompt": "0", "completion": "0"}},
    ]))
    entry = out["m/free"]
    assert entry["prompt_per_million"] is not None
    assert entry["completion_per_million"] is not None
    assert entry["prompt_per_million"] == 0.0
    assert entry["completion_per_million"] == 0.0


# ---------------------------------------------------------------------------
# (c) the audited consumers on unpriced input
# ---------------------------------------------------------------------------
_MIXED_BODY = _body([
    {"id": "vendor/priced", "pricing": {"prompt": "0.0000006",
                                        "completion": "0.0000012"}},
    {"id": "vendor/unpriced"},
])


def _stub_transport(url, key=None, timeout=8.0):
    return 200, _MIXED_BODY


def test_probe_verdict_carries_the_none_fields_through():
    verdict = cap.probe_one_provider(
        OR, transport=_stub_transport,
        env={"OPENROUTER_API_KEY": "sk-fake-presence-marker"})
    assert verdict["ok"] is True
    pricing = verdict["model_pricing"]
    assert pricing["vendor/unpriced"]["prompt_per_million"] is None
    assert pricing["vendor/unpriced"]["completion_per_million"] is None
    assert pricing["vendor/priced"]["prompt_per_million"] == pytest.approx(0.6)
    assert pricing["vendor/priced"]["completion_per_million"] \
        == pytest.approx(1.2)


def test_refresh_door_carries_the_same_table():
    cap._INVENTORY_SNAPSHOT.clear()
    try:
        result = cap.refresh_provider_inventory(
            providers=[OR], transport=_stub_transport, persist=False)
    finally:
        cap._INVENTORY_SNAPSHOT.clear()
    pricing = result["probes"][OR]["model_pricing"]
    assert pricing["vendor/unpriced"]["prompt_per_million"] is None
    assert pricing["vendor/priced"]["completion_per_million"] \
        == pytest.approx(1.2)


def test_probe_surface_never_carries_pricing(monkeypatch, tmp_path):
    monkeypatch.setattr(cap, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake-presence-marker")
    surface = cap.provider_probes_surface(transport=_stub_transport)
    assert surface["flag"] == "1"
    for row in surface["providers"]:
        assert set(row) == {"provider", "present", "key_source",
                            "probed", "ok", "model_count"}
    dumped = json.dumps(surface)
    assert "model_pricing" not in dumped
    assert "prompt_per_million" not in dumped


def test_store_provider_probes_persists_no_pricing(tmp_path):
    cfg = tmp_path / "cfg"
    probe_result = {
        "probed_at": "2026-10-14T00:00:00+00:00",
        "probes": {OR: {
            "present": True, "probed": True, "http_status": 200,
            "models": ["vendor/priced", "vendor/unpriced"],
            "model_pricing": {
                "vendor/priced": {"prompt_per_million": 0.6,
                                  "completion_per_million": 1.2},
                "vendor/unpriced": {"prompt_per_million": None,
                                    "completion_per_million": None},
            },
        }},
    }
    rp.store_provider_probes(probe_result, config_dir=cfg)
    prof = rp.load_profile(cfg)
    entry = prof["providers"][OR]
    assert entry["wired_models"] == ["vendor/priced", "vendor/unpriced"]
    dumped = json.dumps(prof)
    assert "model_pricing" not in dumped
    assert "prompt_per_million" not in dumped
    assert "completion_per_million" not in dumped


def test_credit_preflight_own_parser_represents_unpriced_as_absent(
        monkeypatch):
    # credit_preflight never consumed capacity's table: its own
    # live-list parser skips an item with no pricing blob, so the model
    # is ABSENT from its table (never 0.0), and check_openrouter_model
    # answers "unknown" for it. The capacity fix changes none of this;
    # this test pins that the consumer's behavior is what the B43
    # manifest names.
    body = _body([
        {"id": "priced/model", "pricing": {"prompt": "0.0000006",
                                           "completion": "0.0000012"}},
        {"id": "unpriced/model"},
    ])

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=0: _Resp(body))
    cp._reset_openrouter_pricing_cache()
    try:
        table = cp._openrouter_live_pricing()
        assert table["priced/model"]["in_usd_per_mtok"] == pytest.approx(0.6)
        assert table["priced/model"]["out_usd_per_mtok"] == pytest.approx(1.2)
        assert "unpriced/model" not in table
        ok, reason = cp.check_openrouter_model("unpriced/model")
        assert ok is False and "unknown" in reason
        # Index, not unpack: at this base the success return is the
        # pre-B3 shape; B3's branch (PR #2007) owns that repair.
        assert cp.check_openrouter_model("priced/model")[0] is True
    finally:
        cp._reset_openrouter_pricing_cache()


# ---------------------------------------------------------------------------
# (d) FIX 31's freshness renderer against the fixed extraction
# ---------------------------------------------------------------------------
def _offer(selected, successor):
    return {"provider": OR, "selected_model": selected,
            "successor_model": successor,
            "selected_source": "client-plan",
            "catalog_source": "live", "probed_at": None}


def test_freshness_renderer_unpriced_wording_against_fixed_extraction():
    try:
        from presentation_job import model_freshness as mf
    except ImportError:
        pytest.skip("model_freshness lands with PR #2049 (stacked FIX 31 "
                    "branch), not on this base; this test runs for real "
                    "in the combined tree recorded in the B43 manifest")
    sel, suc = "z-ai/glm-5.3-flash", "z-ai/glm-6-flash"
    # Successor unpriced (no blob): no price line, whatever the
    # selection's price.
    pricing = cap._extract_model_pricing(_body([
        {"id": sel, "pricing": {"prompt": "0.000000075",
                                "completion": "0.00000025"}},
        {"id": suc},
    ]))
    assert pricing[suc]["prompt_per_million"] is None
    text = mf.render_offer_text(_offer(sel, suc), pricing=pricing)
    assert "listed at" not in text
    # Selection unpriced, successor priced: same omission (the design
    # prices the line only when the reading prices BOTH models).
    pricing2 = cap._extract_model_pricing(_body([
        {"id": sel},
        {"id": suc, "pricing": {"prompt": "0.0000001",
                                "completion": "0.0000004"}},
    ]))
    text2 = mf.render_offer_text(_offer(sel, suc), pricing=pricing2)
    assert "listed at" not in text2
    # Both priced: the line renders with the real numbers.
    pricing3 = cap._extract_model_pricing(_body([
        {"id": sel, "pricing": {"prompt": "0.000000075",
                                "completion": "0.00000025"}},
        {"id": suc, "pricing": {"prompt": "0.0000001",
                                "completion": "0.0000004"}},
    ]))
    text3 = mf.render_offer_text(_offer(sel, suc), pricing=pricing3)
    assert "listed at $0.1 in / $0.4 out per million tokens" in text3
    assert "your current model is listed at $0.075 in / $0.25 out" in text3
    # Both genuinely zero-priced: extraction keeps 0.0 (not None), and
    # the renderer's all-zero defense still omits the line, unchanged.
    pricing4 = cap._extract_model_pricing(_body([
        {"id": sel, "pricing": {"prompt": "0", "completion": "0"}},
        {"id": suc, "pricing": {"prompt": "0", "completion": "0"}},
    ]))
    assert pricing4[sel]["prompt_per_million"] == 0.0
    assert pricing4[sel]["prompt_per_million"] is not None
    text4 = mf.render_offer_text(_offer(sel, suc), pricing=pricing4)
    assert "listed at" not in text4

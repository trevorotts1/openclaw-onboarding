"""Tests for U113 (E5-8; closes G6) — the unified browser->API->MCP
fallback-ladder acceptance across Skill 6 build surfaces.

Covers the unit's four BINARY acceptance criteria:
  (a) each build surface declares its ladder in one auditable place, and a
      test asserts the declared order;
  (b) forcing the primary rung to fail provably reaches the next rung
      (fault-injection, parametrized over every laddered surface);
  (c) every rung failure writes a taxonomy-tagged receipt, and ONLY an
      all-rungs-fail path yields a fail-closed PARKED card (never a silent
      success);
  (d) a surface that succeeds on a fallback rung records WHICH rung
      succeeded.

Plus the flag-gated overlay contract (revert = flip GHL_FALLBACK_LADDER back
off) and the anti-fabrication guards (unknown transport, unrecognized
taxonomy code, single-lane surfaces never get an invented second rung).

HERMETIC — no network, no browser, no GHL. Style + sys.path mirror the
sibling 06 tests (test_ghl_iframe_drag.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ── sys.path setup (mirrors the sibling 06 tests) ─────────────────────────────
_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ghl_fallback_ladder as fl  # noqa: E402
import cc_board  # noqa: E402

_LADDER_PATH = str(_TOOLS_DIR / "fallback-ladder.json")


# ---------------------------------------------------------------------------
# (a) declared order is auditable + asserted
# ---------------------------------------------------------------------------

EXPECTED_ORDERS = {
    "page": ("api", "browser", "mcp"),
    "form": ("mcp", "browser"),
    "survey": ("browser", "api"),
    "workflow": ("mcp", "browser"),
    "community": ("mcp", "browser"),
    "course": ("mcp", "browser"),
    "media": ("api", "mcp"),
}


@pytest.mark.parametrize("surface,expected", sorted(EXPECTED_ORDERS.items()))
def test_declared_order_matches_expected(surface, expected):
    assert fl.get_ladder(surface) == expected


def test_declared_surfaces_covers_every_expected_surface():
    assert set(fl.declared_surfaces()) == set(EXPECTED_ORDERS)


def test_funnel_alias_resolves_to_page_order():
    assert fl.get_ladder("funnel") == fl.get_ladder("page")


def test_media_ladder_excludes_browser_transport():
    # ghl_media.py: "NO browser control for media storage ... NEVER by
    # driving the page builder UI" — browser must be structurally absent,
    # not merely untested.
    assert "browser" not in fl.get_ladder("media")


def test_taxonomy_reuses_cc_board_single_source_of_truth():
    assert fl.TAXONOMY_TAGS == cc_board._CC_BLOCK_REASONS


def test_pipeline_is_honestly_not_laddered_not_fabricated():
    with pytest.raises(fl.SurfaceNotLadderedError) as exc_info:
        fl.get_ladder("pipeline")
    assert "pipeline" in str(exc_info.value)
    assert exc_info.value.reason  # a real, non-empty reason string


def test_unknown_surface_raises_config_error():
    with pytest.raises(fl.LadderConfigError):
        fl.get_ladder("nonexistent-surface-xyz")


# ---------------------------------------------------------------------------
# malformed-config validation (never silently accept a bad ladder file)
# ---------------------------------------------------------------------------

def _write_cfg(tmp_path, cfg: dict) -> str:
    p = tmp_path / "fallback-ladder.json"
    p.write_text(json.dumps(cfg))
    return str(p)


def test_validate_rejects_unknown_transport(tmp_path):
    cfg = {"surfaces": {"x": {"order": ["browser", "carrier-pigeon"]}}}
    path = _write_cfg(tmp_path, cfg)
    with pytest.raises(fl.LadderConfigError):
        fl.validate_ladder_file(path)


def test_validate_rejects_duplicate_transport_in_order(tmp_path):
    cfg = {"surfaces": {"x": {"order": ["browser", "browser"]}}}
    path = _write_cfg(tmp_path, cfg)
    with pytest.raises(fl.LadderConfigError):
        fl.validate_ladder_file(path)


def test_validate_rejects_single_rung_ladder(tmp_path):
    cfg = {"surfaces": {"x": {"order": ["browser"]}}}
    path = _write_cfg(tmp_path, cfg)
    with pytest.raises(fl.LadderConfigError):
        fl.validate_ladder_file(path)


def test_validate_rejects_surface_in_both_maps(tmp_path):
    cfg = {
        "surfaces": {"x": {"order": ["browser", "api"]}},
        "not_laddered": {"x": {"reason": "conflict"}},
    }
    path = _write_cfg(tmp_path, cfg)
    with pytest.raises(fl.LadderConfigError):
        fl.validate_ladder_file(path)


def test_validate_rejects_not_laddered_without_reason(tmp_path):
    cfg = {
        "surfaces": {"x": {"order": ["browser", "api"]}},
        "not_laddered": {"y": {}},
    }
    path = _write_cfg(tmp_path, cfg)
    with pytest.raises(fl.LadderConfigError):
        fl.validate_ladder_file(path)


def test_shipped_ladder_file_is_structurally_valid():
    # No exception == pass; this is the self-test also run by
    # `python3 tools/ghl_fallback_ladder.py`.
    fl.validate_ladder_file(_LADDER_PATH)


# ---------------------------------------------------------------------------
# rung callable helpers
# ---------------------------------------------------------------------------

class _Spy:
    """A rung callable that records whether it was invoked and returns a
    pre-programmed outcome."""

    def __init__(self, outcome: dict):
        self.outcome = outcome
        self.calls = 0

    def __call__(self) -> dict:
        self.calls += 1
        return self.outcome


def _fail(code: str, detail: str = "forced for test") -> dict:
    return {"ok": False, "code": code, "detail": detail}


def _succeed(detail: str = "") -> dict:
    return {"ok": True, "detail": detail}


# ---------------------------------------------------------------------------
# (b) fault injection: forcing the primary to fail reaches the next rung
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("surface", sorted(EXPECTED_ORDERS))
def test_fault_injection_reaches_next_rung_when_flag_on(surface, monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    order = fl.get_ladder(surface)
    rungs = {t: _Spy(_fail("SELECTOR-MISS")) for t in order}
    # succeed on the SECOND declared rung only
    rungs[order[1]] = _Spy(_succeed("reached via fallback"))

    result = fl.run_ladder(surface, rungs)

    assert rungs[order[0]].calls == 1, "primary rung must be attempted first"
    assert rungs[order[1]].calls == 1, "fallback rung must be reached after primary fails"
    assert result.ok is True
    assert result.succeeded_rung == order[1]
    assert result.attempts[0].transport == order[0]
    assert result.attempts[0].ok is False
    assert result.attempts[0].code == "SELECTOR-MISS"


# ---------------------------------------------------------------------------
# (c) taxonomy-tagged receipts + fail-closed PARKED only on all-rungs-fail
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("surface", sorted(EXPECTED_ORDERS))
def test_all_rungs_fail_is_fail_closed_parked(surface, monkeypatch, tmp_path):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    order = fl.get_ladder(surface)
    rungs = {t: _Spy(_fail("RATE-LIMIT")) for t in order}
    receipt_path = str(tmp_path / "receipt.json")

    result = fl.run_ladder(surface, rungs, receipt_path=receipt_path)

    assert result.ok is False
    assert result.decision == "PARKED"
    assert result.succeeded_rung is None
    assert len(result.attempts) == len(order)
    assert all(a.ok is False and a.code == "RATE-LIMIT" for a in result.attempts)
    for t in order:
        assert rungs[t].calls == 1, f"every declared rung must be attempted, {t} was not"

    with open(receipt_path) as fh:
        receipt = json.load(fh)
    assert receipt["decision"] == "PARKED"
    assert receipt["ok"] is False


def test_never_a_silent_success_when_a_prior_rung_failed(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    order = fl.get_ladder("page")  # ("api", "browser", "mcp")
    rungs = {
        "api": _Spy(_fail("AUTH-STOP")),
        "browser": _Spy(_fail("VERIFY-FAIL")),
        "mcp": _Spy(_succeed()),
    }
    result = fl.run_ladder("page", rungs)
    assert result.ok is True
    assert result.decision == "SUCCESS"
    # both prior failures are visible in the receipt, not swallowed
    codes = [a.code for a in result.attempts if not a.ok]
    assert codes == ["AUTH-STOP", "VERIFY-FAIL"]


# ---------------------------------------------------------------------------
# (d) success on a fallback rung records WHICH rung succeeded
# ---------------------------------------------------------------------------

def test_success_records_which_rung_in_receipt(monkeypatch, tmp_path):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    order = fl.get_ladder("form")  # ("mcp", "browser")
    rungs = {
        "mcp": _Spy(_fail("TOKEN-CONTEXT")),
        "browser": _Spy(_succeed("placed via drag")),
    }
    receipt_path = str(tmp_path / "receipt.json")
    result = fl.run_ladder("form", rungs, receipt_path=receipt_path)

    assert result.succeeded_rung == "browser"
    with open(receipt_path) as fh:
        receipt = json.load(fh)
    assert receipt["succeeded_rung"] == "browser"
    assert receipt["decision"] == "SUCCESS"
    assert receipt["attempts"][0]["transport"] == "mcp"
    assert receipt["attempts"][0]["code"] == "TOKEN-CONTEXT"


def test_primary_success_records_primary_as_succeeded_rung(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    order = fl.get_ladder("survey")  # ("browser", "api")
    rungs = {"browser": _Spy(_succeed()), "api": _Spy(_succeed())}
    result = fl.run_ladder("survey", rungs)
    assert result.succeeded_rung == "browser"
    assert rungs["api"].calls == 0, "no fallback rung should run once primary succeeds"


# ---------------------------------------------------------------------------
# flag-gated overlay: revert = flip GHL_FALLBACK_LADDER back off
# ---------------------------------------------------------------------------

def test_flag_off_by_default_short_circuits_to_primary_only(monkeypatch):
    monkeypatch.delenv(fl.FLAG_ENV, raising=False)
    order = fl.get_ladder("workflow")  # ("mcp", "browser")
    rungs = {"mcp": _Spy(_fail("SELECTOR-MISS")), "browser": _Spy(_succeed())}

    result = fl.run_ladder("workflow", rungs)

    assert rungs["mcp"].calls == 1
    assert rungs["browser"].calls == 0, "flag OFF must never reach the fallback rung"
    assert result.ok is False
    assert result.decision == "PARKED"
    assert result.ladder_active is False


def test_flag_explicitly_zero_also_stays_off(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "0")
    rungs = {"mcp": _Spy(_fail("SELECTOR-MISS")), "browser": _Spy(_succeed())}
    result = fl.run_ladder("workflow", rungs)
    assert rungs["browser"].calls == 0
    assert result.ladder_active is False


def test_flag_on_reaches_full_ladder(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    rungs = {"mcp": _Spy(_fail("SELECTOR-MISS")), "browser": _Spy(_succeed())}
    result = fl.run_ladder("workflow", rungs)
    assert rungs["browser"].calls == 1
    assert result.ok is True
    assert result.ladder_active is True


def test_ladder_enabled_reads_explicit_env_mapping_not_just_os_environ():
    assert fl.ladder_enabled({fl.FLAG_ENV: "1"}) is True
    assert fl.ladder_enabled({fl.FLAG_ENV: "yes"}) is True
    assert fl.ladder_enabled({fl.FLAG_ENV: "0"}) is False
    assert fl.ladder_enabled({}) is False


# ---------------------------------------------------------------------------
# anti-fabrication guards
# ---------------------------------------------------------------------------

def test_unrecognized_taxonomy_code_is_rejected_not_fabricated(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    rungs = {
        "api": _Spy(_fail("MADE-UP-CODE")),
        "browser": _Spy(_succeed()),
        "mcp": _Spy(_succeed()),
    }
    with pytest.raises(fl.LadderRungError):
        fl.run_ladder("page", rungs)


def test_missing_ok_key_is_rejected():
    def bad_rung():
        return {"detail": "forgot the ok key"}

    with pytest.raises(fl.LadderRungError):
        fl.run_ladder("survey", {"browser": bad_rung, "api": lambda: _succeed()})


def test_rung_that_raises_is_wrapped_not_swallowed(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")

    def exploding_rung():
        raise RuntimeError("boom")

    with pytest.raises(fl.LadderRungError):
        fl.run_ladder("survey", {"browser": exploding_rung, "api": lambda: _succeed()})


def test_missing_callable_for_declared_rung_raises_config_error(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    # 'survey' declares ("browser", "api") — only wire "browser"
    with pytest.raises(fl.LadderConfigError):
        fl.run_ladder("survey", {"browser": lambda: _fail("SELECTOR-MISS")})


def test_non_mapping_rung_return_is_rejected():
    with pytest.raises(fl.LadderRungError):
        fl.run_ladder("survey", {"browser": lambda: "not a dict", "api": lambda: _succeed()})


# ---------------------------------------------------------------------------
# CLI self-test entry point
# ---------------------------------------------------------------------------

def test_cli_selftest_exits_zero():
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / "ghl_fallback_ladder.py")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK: fallback-ladder.json is structurally valid" in proc.stdout

"""Tests for the unified browser->API->MCP fallback ladder across Skill 6 build
surfaces, and for its W3 connection 7 completion contract.

Covers the unit's four BINARY acceptance criteria, unchanged:
  (a) each build surface declares its ladder in one auditable place, and a
      test asserts the declared order;
  (b) forcing the primary rung to fail provably reaches the next rung
      (fault-injection, parametrized over every laddered surface);
  (c) every rung failure writes a taxonomy-tagged receipt, and ONLY an
      all-rungs-fail path yields a fail-closed PARKED card (never a silent
      success);
  (d) a surface that succeeds on a fallback rung records WHICH rung succeeded.

Plus the W3 connection 7 contract that replaced the old "any truthy ok" rule:
  * ok must be the BOOLEAN True;
  * a completion must ALSO report operation_complete=True for the SAME
    requested operation;
  * prerequisite_ready / partial are recorded, never allowed to complete;
  * browser completions need refreshed refs;
  * cleanup may not close everything nor release a session it did not own;
  * the run id / location / native object ids survive the fallback;
  * the ladder is ON by default and GHL_FALLBACK_LADDER=0 is the revert.

HERMETIC — no network, no browser, no GHL. Style + sys.path mirror the
sibling 06 tests.
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

#: The one requested operation every rung in these tests is answering for.
_OP = "form.create"


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
# operation -> surface mapping (W3 connection 7)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "operation,surface",
    [
        ("funnels.pages.autosave", "page"),
        ("forms.update", "form"),
        ("surveys.write", "survey"),
        ("workflows.private.create", "workflow"),
        ("media.upload", "media"),
    ],
)
def test_operation_resolves_to_its_declared_surface(operation, surface):
    assert fl.surface_for_operation(operation) == surface


def test_unknown_operation_gets_no_invented_surface():
    assert fl.surface_for_operation("community.create") is None
    assert fl.surface_for_operation("course.create") is None
    assert fl.surface_for_operation("nonsense") is None


def test_operation_capability_is_per_operation_not_a_blanket_claim():
    browser_only = fl.operation_capability(
        "funnels.pages.autosave", declared_transports=("browser",))
    assert browser_only["surface"] == "page"
    assert browser_only["operationComplete"] is False

    api_row = fl.operation_capability("media.upload", declared_transports=("api",))
    assert api_row["surface"] == "media"
    assert api_row["routedTransports"] == ["api"]
    assert api_row["browserRouteRequired"] is False


def test_unsupported_transport_requires_the_real_browser_route():
    # The API/MCP transport the caller declared is NOT on this ladder, so the
    # real browser rung is the route that must carry the operation.
    record = fl.operation_capability("forms.update", declared_transports=("api",))
    assert record["surface"] == "form"
    assert record["routedTransports"] == []
    assert record["unwiredTransports"] == ["api"]
    assert record["browserRouteRequired"] is True


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


def test_validate_rejects_prefix_to_an_undeclared_surface(tmp_path):
    cfg = {
        "surfaces": {"x": {"order": ["browser", "api"]}},
        "operation_prefixes": {"things": "not-a-surface"},
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


def _succeed(operation: str = _OP, detail: str = "") -> dict:
    """A REAL completion: boolean ok, this operation, refs refreshed."""
    return {
        "ok": True,
        "operation": operation,
        "operation_complete": True,
        "status": "operation_complete",
        "references_fresh": True,
        "detail": detail,
    }


def _prerequisite(operation: str = _OP) -> dict:
    return {
        "ok": True,
        "operation": operation,
        "operation_complete": False,
        "prerequisite_ready": True,
        "status": "prerequisite_ready",
    }


def _run(surface: str, rungs: dict, **kw):
    kw.setdefault("operation", _OP)
    return fl.run_ladder(surface, rungs, **kw)


# ---------------------------------------------------------------------------
# (b) fault injection: forcing the primary to fail reaches the next rung
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("surface", sorted(EXPECTED_ORDERS))
def test_fault_injection_reaches_next_rung_when_flag_on(surface, monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    order = fl.get_ladder(surface)
    rungs = {t: _Spy(_fail("SELECTOR-MISS")) for t in order}
    # succeed on the SECOND declared rung only
    rungs[order[1]] = _Spy(_succeed(detail="reached via fallback"))

    result = _run(surface, rungs)

    assert rungs[order[0]].calls == 1, "primary rung must be attempted first"
    assert rungs[order[1]].calls == 1, "fallback rung must be reached after primary fails"
    assert result.ok is True
    assert result.succeeded_rung == order[1]
    assert result.attempts[0].transport == order[0]
    assert result.attempts[0].ok is False
    assert result.attempts[0].code == "SELECTOR-MISS"


@pytest.mark.parametrize("surface", sorted(EXPECTED_ORDERS))
def test_fault_injection_also_applies_on_the_default_on_ladder(surface, monkeypatch):
    # W3 connection 7: the ladder is ON by default, so an unsupported first
    # transport reaches the next rung with NO flag set at all.
    monkeypatch.delenv(fl.FLAG_ENV, raising=False)
    order = fl.get_ladder(surface)
    rungs = {t: _Spy(_fail("SELECTOR-MISS")) for t in order}
    rungs[order[1]] = _Spy(_succeed(detail="reached by default"))

    result = _run(surface, rungs)

    assert result.ladder_active is True
    assert rungs[order[1]].calls == 1
    assert result.succeeded_rung == order[1]


# ---------------------------------------------------------------------------
# (c) taxonomy-tagged receipts + fail-closed PARKED only on all-rungs-fail
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("surface", sorted(EXPECTED_ORDERS))
def test_all_rungs_fail_is_fail_closed_parked(surface, monkeypatch, tmp_path):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    order = fl.get_ladder(surface)
    rungs = {t: _Spy(_fail("RATE-LIMIT")) for t in order}
    receipt_path = str(tmp_path / "receipt.json")

    result = _run(surface, rungs, receipt_path=receipt_path)

    assert result.ok is False
    assert result.decision == "PARKED"
    assert result.succeeded_rung is None
    assert result.incomplete_operation == _OP
    assert len(result.attempts) == len(order)
    assert all(a.ok is False and a.code == "RATE-LIMIT" for a in result.attempts)
    for t in order:
        assert rungs[t].calls == 1, f"every declared rung must be attempted, {t} was not"

    with open(receipt_path) as fh:
        receipt = json.load(fh)
    assert receipt["decision"] == "PARKED"
    assert receipt["ok"] is False
    assert receipt["operation"] == _OP
    assert receipt["incomplete_operation"] == _OP


def test_never_a_silent_success_when_a_prior_rung_failed(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    order = fl.get_ladder("page")  # ("api", "browser", "mcp")
    rungs = {
        "api": _Spy(_fail("AUTH-STOP")),
        "browser": _Spy(_fail("VERIFY-FAIL")),
        "mcp": _Spy(_succeed()),
    }
    result = _run("page", rungs)
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
        "browser": _Spy(_succeed(detail="placed via drag")),
    }
    receipt_path = str(tmp_path / "receipt.json")
    result = _run("form", rungs, receipt_path=receipt_path)

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
    result = _run("survey", rungs)
    assert result.succeeded_rung == "browser"
    assert rungs["api"].calls == 0, "no fallback rung should run once primary succeeds"


# ---------------------------------------------------------------------------
# PREREQUISITE-ONLY IS NOT COMPLETION (the load-bearing W3 connection 7 rule)
# ---------------------------------------------------------------------------

def test_prerequisite_ready_never_completes_the_operation(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    rungs = {"browser": _Spy(_prerequisite()), "api": _Spy(_fail("SELECTOR-MISS"))}
    result = _run("survey", rungs)

    assert result.ok is False
    assert result.decision == "PARKED"
    assert result.succeeded_rung is None
    assert result.prerequisite_rungs == ["browser"]
    assert result.incomplete_operation == _OP
    assert result.attempts[0].ok is False
    assert result.attempts[0].state == fl.STATE_PREREQUISITE
    assert result.attempts[0].prerequisite_ready is True


def test_prerequisite_rung_is_recorded_and_the_walk_continues(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    rungs = {"browser": _Spy(_prerequisite()), "api": _Spy(_succeed(detail="api did it"))}
    result = _run("survey", rungs)

    assert rungs["api"].calls == 1
    assert result.ok is True
    assert result.succeeded_rung == "api"
    assert result.prerequisite_rungs == ["browser"]
    assert result.incomplete_operation is None


def test_partial_is_distinct_from_prerequisite_ready(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    partial = {"ok": True, "operation": _OP, "operation_complete": False,
               "partial": True, "status": "partial"}
    result = _run("survey", {"browser": _Spy(partial), "api": _Spy(_fail("RATE-LIMIT"))})
    assert result.ok is False
    assert result.attempts[0].state == fl.STATE_PARTIAL
    assert result.attempts[0].prerequisite_ready is False
    assert result.attempts[0].partial is True


def test_ok_without_operation_complete_is_refused():
    incomplete_claim = {"ok": True, "operation": _OP}
    with pytest.raises(fl.LadderRungError):
        _run("survey", {"browser": lambda: incomplete_claim,
                        "api": lambda: _succeed()})


def test_truthy_non_boolean_ok_is_refused():
    for bad in ("false", "true", 1, 0, "yes"):
        with pytest.raises(fl.LadderRungError):
            _run("survey", {"browser": lambda b=bad: {
                "ok": b, "operation": _OP, "operation_complete": True,
                "references_fresh": True}, "api": lambda: _succeed()})


def test_completion_of_a_different_operation_is_refused():
    with pytest.raises(fl.LadderRungError):
        _run("survey", {"browser": lambda: _succeed("form.delete"),
                        "api": lambda: _succeed()})


def test_browser_completion_without_fresh_references_is_refused():
    stale = {"ok": True, "operation": _OP, "operation_complete": True,
             "status": "operation_complete"}
    with pytest.raises(fl.LadderRungError):
        _run("survey", {"browser": lambda: stale, "api": lambda: _succeed()})


def test_reused_references_are_refused():
    reused = dict(_succeed(), references_reused=True)
    with pytest.raises(fl.LadderRungError):
        _run("survey", {"browser": lambda: reused, "api": lambda: _succeed()})


# ---------------------------------------------------------------------------
# cleanup: release only what the rung owned, never everything
# ---------------------------------------------------------------------------

def test_cleanup_may_never_close_every_session():
    rung = dict(_succeed(), cleanup={"closed_all": True})
    with pytest.raises(fl.LadderRungError):
        _run("survey", {"browser": lambda: rung, "api": lambda: _succeed()})


def test_cleanup_may_not_release_a_session_it_did_not_own():
    rung = dict(_succeed(), owned_sessions=["page-1"],
                cleanup={"released": ["user-window-9"]})
    with pytest.raises(fl.LadderRungError):
        _run("survey", {"browser": lambda: rung, "api": lambda: _succeed()})


def test_owned_sessions_without_a_cleanup_record_are_refused():
    rung = dict(_succeed(), owned_sessions=["page-1"])
    with pytest.raises(fl.LadderRungError):
        _run("survey", {"browser": lambda: rung, "api": lambda: _succeed()})


def test_cleanup_of_its_own_session_is_recorded_on_the_result():
    rung = dict(_succeed(), owned_sessions=["page-1"],
                cleanup={"released": ["page-1"], "closed_all": False})
    result = _run("survey", {"browser": lambda: rung, "api": lambda: _succeed()})
    assert result.cleanup == [{"transport": "browser",
                               "released": ["page-1"], "closed_all": False}]


# ---------------------------------------------------------------------------
# the requested operation survives the fallback
# ---------------------------------------------------------------------------

def test_run_id_tenant_and_native_ids_are_preserved_across_rungs(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    seen = []

    def first(ctx):
        seen.append(("first", ctx.run_id, ctx.operation, ctx.incomplete_operation))
        return _fail("SELECTOR-MISS")

    def second(ctx):
        seen.append(("second", ctx.run_id, ctx.operation, ctx.incomplete_operation))
        return _succeed("funnels.pages.autosave")

    result = fl.run_ladder(
        "survey", {"browser": first, "api": second},
        operation="funnels.pages.autosave",
        location_id="loc-test",
        run_id="run-abc123",
        native_object_ids={"funnelId": "fn-9"},
    )

    assert result.ok is True
    run_ids = {entry[1] for entry in seen}
    operations = {entry[2] for entry in seen}
    assert run_ids == {"run-abc123"}
    assert operations == {"funnels.pages.autosave"}
    assert result.run_id == "run-abc123"
    assert result.native_object_ids == {"funnelId": "fn-9"}
    assert result.expected_location_id == "loc-test"
    # the failure is stamped as incomplete for the rung that follows it
    assert seen[1][3] is True


def test_run_ladder_requires_the_requested_operation():
    with pytest.raises(fl.LadderConfigError):
        fl.run_ladder("survey", {"browser": lambda: _succeed(),
                                 "api": lambda: _succeed()})


# ---------------------------------------------------------------------------
# flag: ON by default; GHL_FALLBACK_LADDER=0 is the documented revert
# ---------------------------------------------------------------------------

def test_ladder_is_on_by_default_and_reaches_the_full_ladder(monkeypatch):
    monkeypatch.delenv(fl.FLAG_ENV, raising=False)
    order = fl.get_ladder("workflow")  # ("mcp", "browser")
    rungs = {"mcp": _Spy(_fail("SELECTOR-MISS")), "browser": _Spy(_succeed())}

    result = _run("workflow", rungs)

    assert rungs["mcp"].calls == 1
    assert rungs["browser"].calls == 1, "default ON must reach the fallback rung"
    assert result.ok is True
    assert result.ladder_active is True


def test_flag_explicitly_zero_is_the_revert(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "0")
    rungs = {"mcp": _Spy(_fail("SELECTOR-MISS")), "browser": _Spy(_succeed())}
    result = _run("workflow", rungs)
    assert rungs["browser"].calls == 0
    assert result.ladder_active is False
    assert result.ok is False
    assert result.decision == "PARKED"


def test_flag_on_reaches_full_ladder(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    rungs = {"mcp": _Spy(_fail("SELECTOR-MISS")), "browser": _Spy(_succeed())}
    result = _run("workflow", rungs)
    assert rungs["browser"].calls == 1
    assert result.ok is True
    assert result.ladder_active is True


def test_ladder_enabled_reads_explicit_env_mapping_not_just_os_environ():
    assert fl.ladder_enabled({fl.FLAG_ENV: "1"}) is True
    assert fl.ladder_enabled({fl.FLAG_ENV: "yes"}) is True
    assert fl.ladder_enabled({fl.FLAG_ENV: "0"}) is False
    assert fl.ladder_enabled({fl.FLAG_ENV: "off"}) is False
    # default ON — an operator no longer has to remember a flag
    assert fl.ladder_enabled({}) is True


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
        _run("page", rungs)


def test_missing_ok_key_is_rejected():
    def bad_rung():
        return {"detail": "forgot the ok key"}

    with pytest.raises(fl.LadderRungError):
        _run("survey", {"browser": bad_rung, "api": lambda: _succeed()})


def test_rung_that_raises_is_wrapped_not_swallowed(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")

    def exploding_rung():
        raise RuntimeError("boom")

    with pytest.raises(fl.LadderRungError):
        _run("survey", {"browser": exploding_rung, "api": lambda: _succeed()})


def test_missing_callable_for_declared_rung_raises_config_error(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    # 'survey' declares ("browser", "api") — only wire "browser"
    with pytest.raises(fl.LadderConfigError):
        _run("survey", {"browser": lambda: _fail("SELECTOR-MISS")})


def test_non_mapping_rung_return_is_rejected():
    with pytest.raises(fl.LadderRungError):
        _run("survey", {"browser": lambda: "not a dict", "api": lambda: _succeed()})


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

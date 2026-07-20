"""test_persona_bundle_ladder.py — B-U8/U22 dedicated unit coverage for the
B-U1/U15 persona-bundle acquisition ladder (tools/persona_bundle_ladder.py).

WHY THIS FILE EXISTS
---------------------
persona_bundle_ladder.py has always shipped its own inline `__main__`
self-test (7 checks, exercised by running the module directly), but B-U1/U15
never had a file under `tests/` that pytest/CI discovers automatically, and
the cc/threaded rungs were only ever exercised with hand-inlined dict
literals, never FIXTURE PAYLOAD FILES a producer would actually receive.
B-U8/U22's own acceptance (spec L892) names this gap explicitly: "the B-U1
ladder tests (threaded/cc/local/absent x confirm states, with cc/threaded fed
from fixture payloads)". This file is that dedicated, CI-discovered suite.

MATRIX COVERED (source x confirm_state, 4x3 with the physically-impossible
cells excluded — `absent` only ever pairs with `n/a`):
              confirmed          pending (CC-connected -> hold)   pending (standalone -> degrade)
  threaded    test_threaded_confirmed   test_threaded_pending_holds        (n/a - threaded implies CC)
  cc          test_cc_confirmed         test_cc_pending_holds              (n/a - cc rung implies CC)
  local       test_local_confirmed      (n/a - local implies standalone)   test_local_pending_degrades
  absent      test_all_rungs_absent (confirm_state=n/a, the only legal pairing)

Every produced receipt is ALSO validated against the B-U8/U22
persona-bundle-receipt schema (shared-utils/persona_bundle_receipt_schema.py)
— not just hand-checked field by field — so a receipt that satisfies these
tests' own assertions but violates the schema's cross-field rules still
fails loudly.

Stdlib + pytest only. No network, no CC, no live selector run — the cc/local
rungs are injected via the ladder's own `cc_fetch=`/`selector_runner=`
callables (its documented test seam), fed from FIXTURE PAYLOAD FILES under
`tests/fixtures/persona-bundles/`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.normpath(os.path.join(_TESTS_DIR, "..", "tools"))
_REPO_ROOT = os.path.normpath(os.path.join(_TESTS_DIR, "..", ".."))
_SHARED_UTILS = os.path.join(_REPO_ROOT, "shared-utils")
_FIXTURES_DIR = os.path.join(_TESTS_DIR, "fixtures", "persona-bundles")

if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
if _SHARED_UTILS not in sys.path:
    sys.path.insert(0, _SHARED_UTILS)

import persona_bundle_ladder as ladder  # noqa: E402

_schema_spec = importlib.util.spec_from_file_location(
    "persona_bundle_receipt_schema", os.path.join(_SHARED_UTILS, "persona_bundle_receipt_schema.py"))
receipt_schema = importlib.util.module_from_spec(_schema_spec)
sys.modules["persona_bundle_receipt_schema"] = receipt_schema
_schema_spec.loader.exec_module(receipt_schema)


def _fixture(name: str) -> dict:
    path = os.path.join(_FIXTURES_DIR, name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _assert_schema_valid(receipt: dict) -> None:
    ok, errors = receipt_schema.validate_receipt(receipt)
    assert ok, f"receipt violates the B-U8/U22 schema: {errors}\nreceipt={receipt}"


@pytest.fixture
def evidence_root():
    with tempfile.TemporaryDirectory() as td:
        yield td


# --------------------------------------------------------------------------- #
# threaded rung — task['persona_bundle'] already supplied by the caller.
# --------------------------------------------------------------------------- #
def test_threaded_confirmed_wins_first_and_is_schema_valid(evidence_root):
    fixture = _fixture("threaded-confirmed.json")
    task = {"id": "t-threaded-confirmed", "persona_bundle": fixture}
    r = ladder.resolve_persona_bundle(task, evidence_root)
    assert r["source"] == "threaded"
    assert r["confirm_state"] == "confirmed"
    assert r["hold"] is False
    assert r["degradation"] is None
    assert r["voice_persona_id"] == "hormozi-100m-offers"
    assert r["topic_persona_id"] == "miller-building-storybrand"
    assert task["persona_bundle"]["voice_persona_id"] == "hormozi-100m-offers"
    assert os.path.isfile(os.path.join(evidence_root, "routing", "persona-bundle-receipt.json"))
    _assert_schema_valid(r)


def test_threaded_pending_confirm_on_cc_connected_run_holds(evidence_root):
    # threaded implies a CC-dispatched task (documented in
    # persona_bundle_ladder.py's own ladder docstring) -> pending MUST hold,
    # never degrade, never build silently.
    fixture = _fixture("threaded-pending.json")
    task = {"id": "t-threaded-pending", "persona_bundle": fixture}
    r = ladder.resolve_persona_bundle(task, evidence_root)
    assert r["source"] == "threaded"
    assert r["confirm_state"] == "pending"
    assert r["hold"] is True
    assert r["degradation"] is None
    _assert_schema_valid(r)


# --------------------------------------------------------------------------- #
# cc rung — a read-only fetch against the Command Center, injected via
# cc_fetch= (the ladder's documented test seam), fed from a FIXTURE payload.
# --------------------------------------------------------------------------- #
def test_cc_confirmed_from_fixture_payload(evidence_root):
    payload = _fixture("cc-fetch-confirmed.json")
    task = {"id": "t-cc-confirmed", "board_task_id": "cc-task-99"}
    r = ladder.resolve_persona_bundle(
        task, evidence_root,
        cc_fetch=lambda *_a, **_k: payload,
        selector_runner=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("local rung must not run when cc rung hits")),
    )
    assert r["source"] == "cc"
    assert r["confirm_state"] == "confirmed"
    assert r["hold"] is False
    assert r["voice_persona_id"] == "cialdini-influence"
    assert r["topic_persona_id"] == "hopkins-scientific-advertising"
    _assert_schema_valid(r)


def test_cc_pending_confirm_holds_never_degrades(evidence_root):
    # cc rung is by definition CC-connected -> pending MUST hold, same as
    # threaded, never the standalone degrade path.
    payload = _fixture("cc-fetch-pending.json")
    task = {"id": "t-cc-pending", "board_task_id": "cc-task-100"}
    r = ladder.resolve_persona_bundle(
        task, evidence_root, cc_fetch=lambda *_a, **_k: payload,
        selector_runner=lambda *_a, **_k: None,
    )
    assert r["source"] == "cc"
    assert r["confirm_state"] == "pending"
    assert r["hold"] is True
    assert r["degradation"] is None
    _assert_schema_valid(r)


def test_cc_fetch_unreachable_falls_through_to_local(evidence_root):
    # Fail-soft: an unreachable/not-yet-shipped CC endpoint falls through to
    # rung 3, never blocks the build (per the ladder's docstring).
    payload = _fixture("threaded-confirmed.json")  # reused as a local-rung payload
    task = {"id": "t-cc-unreachable", "board_task_id": "cc-task-101"}
    r = ladder.resolve_persona_bundle(
        task, evidence_root, cc_fetch=lambda *_a, **_k: None,
        selector_runner=lambda *_a, **_k: payload,
    )
    assert r["source"] == "local"
    _assert_schema_valid(r)


# --------------------------------------------------------------------------- #
# local rung — the IDENTICAL --blend engine invoked via selector_runner=.
# --------------------------------------------------------------------------- #
def test_local_confirmed(evidence_root):
    payload = _fixture("cc-fetch-confirmed.json")  # any confirmed shape works; local normalizes both
    task = {"id": "t-local-confirmed"}
    r = ladder.resolve_persona_bundle(
        task, evidence_root, cc_fetch=lambda *_a, **_k: None,
        selector_runner=lambda *_a, **_k: payload,
    )
    assert r["source"] == "local"
    assert r["confirm_state"] == "confirmed"
    assert r["hold"] is False
    assert r["degradation"] is None
    _assert_schema_valid(r)


def test_local_pending_confirm_on_standalone_run_degrades_never_holds(evidence_root):
    # local rung implies NO CC connection to hold against (no operator to
    # notify) -> pending MUST degrade to the neutral house voice, named in
    # the receipt, NEVER a silent hold that nobody will ever clear.
    payload = _fixture("cc-fetch-pending.json")
    task = {"id": "t-local-pending"}
    r = ladder.resolve_persona_bundle(
        task, evidence_root, cc_fetch=lambda *_a, **_k: None,
        selector_runner=lambda *_a, **_k: payload,
    )
    assert r["source"] == "local"
    assert r["confirm_state"] == "pending"
    assert r["hold"] is False
    assert r["degradation"] is not None
    assert "degraded" in r["degradation"].lower() or "house voice" in r["degradation"].lower()
    _assert_schema_valid(r)


# --------------------------------------------------------------------------- #
# absent rung — every rung fails; the only legal pairing is confirm_state=n/a.
# --------------------------------------------------------------------------- #
def test_all_rungs_absent_is_the_legacy_noop(evidence_root):
    task = {"id": "t-absent"}
    r = ladder.resolve_persona_bundle(
        task, evidence_root, cc_fetch=lambda *_a, **_k: None,
        selector_runner=lambda *_a, **_k: None,
    )
    assert r["source"] == "absent"
    assert r["confirm_state"] == "n/a"
    assert r["hold"] is False
    assert r["degradation"] is None
    assert r["voice_persona_id"] is None
    assert "persona_bundle" not in task  # absent -> never threaded onto the task
    _assert_schema_valid(r)


def test_default_posture_local_rung_disabled_without_env_flag(evidence_root):
    # GHL_PERSONA_BLEND_LOCAL unset -> rung 3 is a fast, deterministic no-op
    # even when a selector_runner IS supplied via the default resolver path
    # (proven here by NOT injecting selector_runner=, so the ladder's own
    # _default_selector_runner is exercised against an empty env).
    task = {"id": "t-default-posture"}
    r = ladder.resolve_persona_bundle(
        task, evidence_root, env={}, cc_fetch=lambda *_a, **_k: None)
    assert r["source"] == "absent"
    _assert_schema_valid(r)


# --------------------------------------------------------------------------- #
# every fixture payload file itself is well-formed JSON with the keys the
# _normalize_bundle() docstring promises each shape carries — catches a
# fixture bit-rotting independently of any test that merely consumes it.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fixture_name,required_keys", [
    ("threaded-confirmed.json", {"persona_id", "voice", "resolved_audience", "confirm_required", "task_personas"}),
    ("threaded-pending.json", {"persona_id", "voice", "resolved_audience", "confirm_required", "task_personas"}),
    ("cc-fetch-confirmed.json", {"voice_persona_id", "topic_persona_id", "confirm_required", "task_personas"}),
    ("cc-fetch-pending.json", {"voice_persona_id", "topic_persona_id", "confirm_required", "task_personas"}),
])
def test_fixture_payload_shape(fixture_name, required_keys):
    payload = _fixture(fixture_name)
    missing = required_keys - set(payload.keys())
    assert not missing, f"{fixture_name} is missing keys the ladder's normalizer expects: {missing}"


# --------------------------------------------------------------------------- #
# the module's own inline self-test (still the fastest smoke check) stays
# green on THIS tree too — run as a subprocess so a real __main__ execution
# is exercised, not just its functions imported.
# --------------------------------------------------------------------------- #
def test_module_self_test_still_passes():
    import subprocess
    proc = subprocess.run([sys.executable, os.path.join(_TOOLS_DIR, "persona_bundle_ladder.py")],
                           capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"persona_bundle_ladder.py --self-test (via __main__) failed:\n{proc.stdout}\n{proc.stderr}"
    assert "ALL PASSED" in proc.stdout


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

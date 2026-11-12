#!/usr/bin/env python3
"""The step gate's own proofs: the seven from selftest(), plus (h), (i) and (j).

(h) the contract's stage list equals batch_mode.batch.STAGES word for word
(i) a hand-written seal file with a made-up signature is refused
(j) `verify --through delivery` on a run with a gap names the first missing stage

Plain asserts, no framework: `python3 -B scripts/core/step_gate/test_step_gate.py`
prints one line per proof and exits 0 only when every proof holds.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.append(CORE)              # batch_mode, lyric_writer, master_length
if HERE not in sys.path:
    sys.path.insert(0, HERE)           # this module, ahead of the package wrapper

import step_gate as G


def _refused(code, fn, *a, **k):
    try:
        fn(*a, **k)
    except G.Refused as exc:
        return exc.code == code or code in exc.detail
    return False


def _two_stage_contract():
    return {"order": ["one", "two"], "stages": {
        "one": {"artifacts": [{"path": "a/one.json", "kind": "json", "min_bytes": 10,
                               "required_keys": ["lines"]}]},
        "two": {"artifacts": [{"path": "a/two.json", "kind": "json"}]}}}


def _run(base, contract=None):
    run = os.path.join(base, "run-1")
    os.makedirs(os.path.join(run, "a"))
    G.cmd_init(run)
    return run


def _write(run, rel, text):
    path = os.path.join(run, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# ---- the seven proofs from selftest() -------------------------------------
def test_stage_two_cannot_open_before_stage_one_is_sealed():
    contract = _two_stage_contract()
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        assert _refused("PREVIOUS_STAGE_NOT_PROVEN", G.cmd_open, run, "two", contract)


def test_an_empty_file_is_refused():
    contract = _two_stage_contract()
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        G.cmd_open(run, "one", contract)
        _write(run, "a/one.json", "{}")
        assert _refused("ARTIFACT_TOO_SMALL", G.cmd_seal, run, "one", "m", "c", contract)


def test_a_placeholder_file_is_refused():
    contract = _two_stage_contract()
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        G.cmd_open(run, "one", contract)
        _write(run, "a/one.json", json.dumps({"lines": ["TODO write me"]}))
        assert _refused("ARTIFACT_PLACEHOLDER", G.cmd_seal, run, "one", "m", "c", contract)


def test_maker_cannot_check_own_work():
    contract = _two_stage_contract()
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        G.cmd_open(run, "one", contract)
        _write(run, "a/one.json", json.dumps({"lines": ["a real line of the story"]}))
        assert _refused("MAKER_SELF_REVIEW", G.cmd_seal, run, "one", "Sam", "sam", contract)


def test_a_good_stage_seals_and_verifies():
    contract = _two_stage_contract()
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        G.cmd_open(run, "one", contract)
        _write(run, "a/one.json", json.dumps({"lines": ["a real line of the story"]}))
        G.cmd_seal(run, "one", "builder", "checker", contract)
        assert G.cmd_verify(run, contract, through="one")["proven_stages"] == ["one"]


def test_an_edited_seal_is_refused():
    contract = _two_stage_contract()
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        G.cmd_open(run, "one", contract)
        _write(run, "a/one.json", json.dumps({"lines": ["a real line of the story"]}))
        G.cmd_seal(run, "one", "builder", "checker", contract)
        seal_path = G._gate_file(run, "one", "seal")
        with open(seal_path, encoding="utf-8") as fh:
            forged = json.load(fh)
        forged["body"]["checker"] = "someone-else"
        _write(run, os.path.join("control", "gates", "one.seal.json"), json.dumps(forged))
        assert _refused("SEAL_SIGNATURE_INVALID", G.cmd_verify, run, contract, "one")


def test_an_artifact_edited_after_sealing_blocks_the_next_stage():
    contract = _two_stage_contract()
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        G.cmd_open(run, "one", contract)
        _write(run, "a/one.json", json.dumps({"lines": ["a real line of the story"]}))
        G.cmd_seal(run, "one", "builder", "checker", contract)
        _write(run, "a/one.json", json.dumps({"lines": ["changed after sealing, still valid JSON"]}))
        assert _refused("SEALED_ARTIFACT_CHANGED", G.cmd_open, run, "two", contract)


# ---- (h), (i), (j) --------------------------------------------------------
def test_contract_stage_list_equals_batch_stages():
    from batch_mode import batch as B
    contract = G.load_contract()
    assert contract["order"] == [slug for slug, _title in B.STAGES], (
        "stage_contracts.json order %r != batch_mode.batch.STAGES %r"
        % (contract["order"], [slug for slug, _title in B.STAGES]))


def test_hand_written_seal_with_a_made_up_signature_is_refused():
    contract = _two_stage_contract()
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        G.cmd_open(run, "one", contract)
        body = {"schema": G.SCHEMA, "stage": "one", "sealed_at": 0,
                "maker": "someone", "checker": "someone-else", "artifacts": [],
                "previous_stage": None, "previous_signature": ""}
        G._atomic_write(G._gate_file(run, "one", "seal"),
                        {"body": body, "signature": "0" * 64})
        assert _refused("SEAL_SIGNATURE_INVALID", G.cmd_verify, run, contract)


def test_verify_through_delivery_names_the_first_missing_stage():
    contract = G.load_contract()
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        try:
            G.cmd_verify(run, contract, through="delivery")
        except G.Refused as exc:
            assert exc.code == "CHAIN_INCOMPLETE", exc.code
            assert "research" in exc.detail, exc.detail
        else:
            raise AssertionError("verify passed a run with no seals")


# ---- the validator hook ---------------------------------------------------
def test_a_failing_validator_refuses_the_seal():
    contract = {"order": ["one"], "stages": {"one": {"artifacts": [
        {"path": "a/one.json", "kind": "json",
         "validator": "step_gate:validate_lyrics_artifact"}]}}}
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        G.cmd_open(run, "one", contract)
        _write(run, "a/one.json", json.dumps({"lines": "not a list of lines"}))
        assert _refused("ARTIFACT_INVALID", G.cmd_seal, run, "one", "m", "c", contract)


def test_an_unresolvable_validator_is_refused():
    contract = {"order": ["one"], "stages": {"one": {"artifacts": [
        {"path": "a/one.json", "kind": "json",
         "validator": "step_gate:no_such_validator_here"}]}}}
    with tempfile.TemporaryDirectory() as base:
        run = _run(base)
        G.cmd_open(run, "one", contract)
        _write(run, "a/one.json", json.dumps({"lines": ["a real line of the story"]}))
        assert _refused("ARTIFACT_INVALID", G.cmd_seal, run, "one", "m", "c", contract)


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:                      # noqa: BLE001 - report, do not hide
            failed += 1
            print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc))
        else:
            print("ok   %s" % name)
    print("%d proofs, %d failed" % (len(tests), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

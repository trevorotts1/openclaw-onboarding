#!/usr/bin/env python3
"""Regression test: script_writer's raw-response retention cap is a DECLARED gate (rule 12).

The cap (RAW_KEEP_CHARS) bounds the raw authored response kept for diagnosis. It is not a prompt
length, so it is declared in shared-utils/kie_prompt_gates.json (gate_modules + allowed_numeric) and
confirmed through the shared enforcer instead of standing as an undeclared band. Before that
declaration the fast guard scripts/ci/fast-guards.d/kie-prompt-enforcer-guard.sh failed on main with
"band-named constant holding a previously hard-coded prompt band: RAW_KEEP_CHARS".

The retention itself must stay byte-identical: the declared 20,000 still applies, and the kept raw
text is still the first 20,000 characters of the response.

Run: python3 scripts/core/test_script_writer_raw_keep_gate.py   (or pytest)
"""
import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import script_writer as W  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
GATES = REPO / "shared-utils" / "kie_prompt_gates.json"
RELPATH = "75-drama-song-ad-factory/scripts/core/script_writer.py"

def _decl():
    with open(GATES, encoding="utf-8") as fh:
        return json.load(fh)

def _request():
    return {"attempt": 1, "idempotency_key": "regression-raw-keep", "binding": {"requested": "fixture"}}

def _parsed(raw):
    authored = {"script": {"filler": "x" * 25000 if len(raw) > 20000 else "short"}}
    response = {"response_id": "regression-1", "raw_text": raw}
    return W.parse_response(_request(), response)["dispatch"]

def test_the_retention_cap_is_the_declared_20000():
    assert W.RAW_KEEP_CHARS == 20000, W.RAW_KEEP_CHARS
    assert W._raw_keep_chars() == 20000, W._raw_keep_chars()

def test_the_module_is_declared_as_a_gate_with_its_allowed_numeric():
    decl = _decl()
    assert RELPATH in decl["gate_modules"], RELPATH
    assert "RAW_KEEP_CHARS" in decl["allowed_numeric"].get(RELPATH, []), \
        decl["allowed_numeric"].get(RELPATH)

def test_a_long_response_keeps_exactly_the_declared_characters():
    raw = json.dumps({"script": {"filler": "x" * 25000}}, sort_keys=True)
    assert len(raw) > 20000, len(raw)
    dispatch = _parsed(raw)
    assert dispatch["raw_retained"] == raw[:20000]
    assert dispatch["raw_truncated"] is True
    assert dispatch["raw_bytes"] == len(raw.encode("utf-8"))

def test_a_short_response_is_kept_whole_and_untouched():
    raw = json.dumps({"script": {"filler": "short"}}, sort_keys=True)
    assert len(raw) <= 20000, len(raw)
    dispatch = _parsed(raw)
    assert dispatch["raw_retained"] == raw
    assert dispatch["raw_truncated"] is False

if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - standalone runner
            failures += 1
            print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc))
        else:
            print("ok   %s" % name)
    print("\n%d passed, %d failed, %d total" % (len(tests) - failures, failures, len(tests)))
    sys.exit(1 if failures else 0)

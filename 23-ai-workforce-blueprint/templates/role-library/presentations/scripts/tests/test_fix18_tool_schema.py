#!/usr/bin/env python3
"""
test_fix18_tool_schema.py — FIX-18 tool-schema hardening test (Error 10 / D17).

Proves the FIX-18 defense against the tool-call schema loop the 2026-08-06 E2E
logged (12x `args: must be object`, 3x `missing path` — the model serializing
tool args as a STRING instead of a JSON object, then re-emitting schema dumps):

  1. NORMALIZED SCHEMA HINT. A malformed tool call (string args, or a missing
     required key like `path`) gets the EXACT schema hint back (e.g.
     `write(path: string, content: string) — path is REQUIRED, not file`), never
     the raw "must be object" string.

  2. 5-STRIKE AF-TOOL-SCHEMA-LOOP EVENT. Five CONSECUTIVE malformed calls on the
     same tool write an AF-TOOL-SCHEMA-LOOP event to the run's
     working/checkpoints/tool_schema_events.json ledger; a SUCCESS between
     failures resets the streak (4 failures + 1 success + 4 failures = NO event);
     the event fires at exactly 5 and carries the consecutive count.

  3. RUNNER PHASE-0 ENFORCEMENT. run_signature_deck.phase0_preflight HARD-ABORTS
     (exit 4) when the run's ledger already carries an AF-TOOL-SCHEMA-LOOP event,
     and PROCEEDS past the tool-schema check when the ledger is empty (the
     known-good control — a check that fails both the looped and the clean case
     is a broken check).

  4. DOC-RULE LOCKSTEP. The validator's schema hint for `write` states `path is
     REQUIRED, not file` — the same durable rule the dept TOOLS.md / AGENTS.md
     documents (write takes path, never file; args are always a JSON object).

Pytest-native (each test_* uses assert) AND directly runnable
(`python3 tests/test_fix18_tool_schema.py`) via the main() wrapper below.

Run:  python3 tests/test_fix18_tool_schema.py     # direct
      python3 -m pytest tests/test_fix18_tool_schema.py -q
Exit: 0 = all assertions passed; 1 = a case failed.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import tool_schema_validator as tsv  # noqa: E402


# ---------------------------------------------------------------------------
# 1) NORMALIZED SCHEMA HINT
# ---------------------------------------------------------------------------
def test_string_args_are_malformed_for_every_tool():
    for tool in ("tool_call", "write", "read", "Edit", "Bash", "WebSearch",
                 "WebFetch", "unknown-tool"):
        r = tsv.validate_args(tool, '{"path": "/tmp/x"}')
        assert not r["ok"], f"{tool}: string args must FAIL, got ok=True"
        assert r["hint"], f"{tool}: malformed call must carry a hint"


def test_conformant_object_args_pass_known_good_control():
    good = [
        ("write", {"path": "/tmp/x", "content": "hi"}),
        ("read", {"path": "/tmp/x"}),
        ("Edit", {"file_path": "/tmp/x", "old_string": "a", "new_string": "b"}),
        ("Bash", {"command": "ls"}),
        ("WebSearch", {"query": "presentations"}),
        ("tool_call", {"name": "Bash", "arguments": {"command": "ls"}}),
    ]
    for tool, args in good:
        r = tsv.validate_args(tool, args)
        assert r["ok"], f"{tool}: conformant object args must PASS, got {r['error']!r}"


def test_path_file_trap_names_path():
    r = tsv.validate_args("write", {"file": "/tmp/x", "content": "hi"})
    assert not r["ok"], "write(file=...) must FAIL (the path/file trap)"
    assert "path" in r["error"], f"the failure must name path, got {r['error']!r}"


def test_hint_is_normalized_not_raw_must_be_object():
    r = tsv.validate_args("write", "bad")
    assert "path is REQUIRED" in r["hint"], (
        f"the write hint must state the schema, got {r['hint']!r}")
    r2 = tsv.validate_args("tool_call", "bad")
    assert "JSON OBJECT" in r2["hint"], (
        f"the tool_call hint must demand a JSON object, got {r2['hint']!r}")


# ---------------------------------------------------------------------------
# 2) 5-STRIKE AF-TOOL-SCHEMA-LOOP EVENT
# ---------------------------------------------------------------------------
def test_five_consecutive_failures_write_af_tool_schema_loop():
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td)
        loop_id = ""
        for _ in range(tsv.CONSECUTIVE_FAILURE_LIMIT):
            loop_id = tsv.record_malformed(run_dir, "write", '{"file": "x"}')
        assert loop_id, "5 consecutive failures must write the loop event id"
        events = tsv.active_loop_events(run_dir)
        assert len(events) == 1, f"expected exactly 1 loop event, got {len(events)}"
        ev = events[0]["event"]
        assert ev["code"] == tsv.AF_TOOL_SCHEMA_LOOP, ev
        assert events[0]["consecutive_failures"] == tsv.CONSECUTIVE_FAILURE_LIMIT, events[0]
        assert "write" in ev["message"], ev["message"]


def test_success_between_failures_resets_the_streak():
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td)
        for _ in range(4):
            tsv.record_malformed(run_dir, "Bash", "bad")
        tsv.record_ok(run_dir, "Bash")
        for _ in range(4):
            tsv.record_malformed(run_dir, "Bash", "bad")
        assert not tsv.active_loop_events(run_dir), (
            "a success between failures must reset the streak; 4+1+4 must NOT fire")


def test_event_fires_at_exactly_five_not_before():
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td)
        for i in range(1, tsv.CONSECUTIVE_FAILURE_LIMIT):
            tsv.record_malformed(run_dir, "Edit", "bad")
            assert not tsv.active_loop_events(run_dir), (
                f"no event expected before the {tsv.CONSECUTIVE_FAILURE_LIMIT}th failure, "
                f"fired at {i}")
        tsv.record_malformed(run_dir, "Edit", "bad")
        assert tsv.active_loop_events(run_dir), (
            f"the {tsv.CONSECUTIVE_FAILURE_LIMIT}th consecutive failure must fire")


def test_ledger_file_is_the_checkpoints_event_store():
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td)
        tsv.record_malformed(run_dir, "read", "bad")
        p = run_dir / "working" / "checkpoints" / "tool_schema_events.json"
        assert p.is_file(), f"ledger must be at working/checkpoints/tool_schema_events.json, got {p}"
        obj = json.loads(p.read_text())
        assert isinstance(obj, list) and len(obj) == 1, obj


# ---------------------------------------------------------------------------
# 3) RUNNER PHASE-0 ENFORCEMENT
# ---------------------------------------------------------------------------
def _mk_run_dir(prefix):
    root = Path(tempfile.mkdtemp(prefix=prefix))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (root / "slides.json").write_text(json.dumps([{"slide": 1}]))
    return root


def test_phase0_preflight_aborts_on_existing_loop_event():
    import run_signature_deck as rsd
    assert rsd._tool_schema is not None, "run_signature_deck must see tool_schema_validator"

    # Seed a 5-strike loop event into the run's ledger.
    root = _mk_run_dir("deck_fix18_loop_")
    try:
        for _ in range(tsv.CONSECUTIVE_FAILURE_LIMIT):
            tsv.record_malformed(root, "write", '{"file": "x"}')
        assert tsv.active_loop_events(root), "loop event must be present before the run"

        # Monkeypatch the env probe to PASS so the ONLY failing gate is FIX-18.
        import check_agent_env as cae
        orig = cae.probe
        try:
            def _good():
                return {"verdict": "PASS", "exit_code": 0, "missing": [], "unmanaged": []}
            cae.probe = _good
            try:
                rsd.phase0_preflight(root, root / "slides.json", platform_override="mac")
                raise AssertionError("a looped ledger must exit 4, but phase0_preflight returned")
            except SystemExit as e:
                assert e.code == 4, e.code
        finally:
            cae.probe = orig
    finally:
        shutil.rmtree(root)


def test_phase0_preflight_proceeds_when_ledger_clean():
    import run_signature_deck as rsd
    root = _mk_run_dir("deck_fix18_clean_")
    try:
        assert not tsv.active_loop_events(root), "clean ledger must be empty"
        import check_agent_env as cae
        orig = cae.probe
        try:
            def _good():
                return {"verdict": "PASS", "exit_code": 0, "missing": [], "unmanaged": []}
            cae.probe = _good
            try:
                rsd.phase0_preflight(root, root / "slides.json", platform_override="mac")
            except SystemExit as e:
                # A clean ledger must never exit 4 on the FIX-18 gate. (Other
                # phase-0 gates like Kie-balance may stop on a missing key, which
                # is NOT this test's assertion — we only require no exit-4 with
                # a clean ledger and a PASS env verdict.)
                assert e.code != 4, e.code
        finally:
            cae.probe = orig
    finally:
        shutil.rmtree(root)


# ---------------------------------------------------------------------------
# 4) DOC-RULE LOCKSTEP + CLI
# ---------------------------------------------------------------------------
def test_write_hint_states_the_durable_rule():
    hint = tsv.schema_hint("write")
    assert "path is REQUIRED, not file" in hint, hint


def test_cli_self_test_and_hint():
    r = subprocess.run([sys.executable, str(HERE / "tool_schema_validator.py"),
                        "--self-test"], capture_output=True, text=True, cwd=str(HERE))
    assert r.returncode == 0, r.stderr
    assert "SELF-TEST PASS" in r.stdout, r.stdout

    r = subprocess.run([sys.executable, str(HERE / "tool_schema_validator.py"),
                        "--hint", "write"], capture_output=True, text=True, cwd=str(HERE))
    assert r.returncode == 0, r.stderr
    assert "path is REQUIRED, not file" in r.stdout, r.stdout

    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td)
        for _ in range(tsv.CONSECUTIVE_FAILURE_LIMIT):
            subprocess.run([sys.executable, str(HERE / "tool_schema_validator.py"),
                            "--ledger", str(run_dir), "write", '{"file": "x"}'],
                           capture_output=True, text=True, cwd=str(HERE))
        r = subprocess.run([sys.executable, str(HERE / "tool_schema_validator.py"),
                            "--json"], capture_output=True, text=True, cwd=str(HERE))
        assert r.returncode == 0, r.stderr
        rep = json.loads(r.stdout)
        assert rep["passed"] is True, rep
        assert rep["af_code"] == tsv.AF_TOOL_SCHEMA_LOOP, rep


# ---------------------------------------------------------------------------
# Direct-run wrapper (pytest uses the test_* functions above).
# ---------------------------------------------------------------------------
def _run_all():
    failures = []
    for fn in (test_string_args_are_malformed_for_every_tool,
               test_conformant_object_args_pass_known_good_control,
               test_path_file_trap_names_path,
               test_hint_is_normalized_not_raw_must_be_object,
               test_five_consecutive_failures_write_af_tool_schema_loop,
               test_success_between_failures_resets_the_streak,
               test_event_fires_at_exactly_five_not_before,
               test_ledger_file_is_the_checkpoints_event_store,
               test_phase0_preflight_aborts_on_existing_loop_event,
               test_phase0_preflight_proceeds_when_ledger_clean,
               test_write_hint_states_the_durable_rule,
               test_cli_self_test_and_hint):
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, exc))
            print(f"  [FAIL] {fn.__name__}: {exc}")
    print("=" * 60)
    if failures:
        print("FIX-18 test: FAIL — %d case(s) failed" % len(failures))
        return 1
    print("FIX-18 test: PASS — hint, 5-strike event, streak reset, and phase-0 "
          "enforcement all green.")
    return 0


if __name__ == "__main__":
    sys.exit(_run_all())

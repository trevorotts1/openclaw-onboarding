#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tool_schema_validator.py — FIX-18 tool-schema hardening (Error 10 / D17).

The 2026-08-06 E2E session (task e738cff0) logged `8x Validation failed for tool
"tool_call": args: must be object`, `2x Missing required parameter: path`, and —
quantified in D17 — `12x args-must-be-object`, `3x missing path`. The model
serializes tool arguments as a STRING instead of an OBJECT and the harness
returned only the raw validation failure ("must be object"), so the model
guessed again and burned turns. Each schema failure costs a full retry cycle; on
a 20-slide build these accumulate into significant wall-clock time.

FIX-18's permanent defense is THIS validator. It is the harness-level corrective
prompt for malformed tool args, and it is a deterministic, offline, stdlib-only
probe that:

  1. NORMALIZED SCHEMA HINT. On a tool-args validation failure it returns the
     exact schema for the named tool (e.g. `write(path: string, content: string)
     — path is REQUIRED, not file`), NOT the raw "must be object" string, plus an
     explicit instruction to emit args as a JSON OBJECT (never a string) and NOT
     to re-emit the schema dump.

  2. 5-STRIKE LOOP ALERT (AF-TOOL-SCHEMA-LOOP). It maintains a per-task,
     consecutive-failure counter on disk. When a tool records its 5th
     CONSECUTIVE schema failure (no intervening success), the validator WRITES an
     AF-TOOL-SCHEMA-LOOP event to the run's checkpoint ledger — the same
     working/checkpoints/ event store the runner's other gates read — and the
     runner's phase-0 preflight HARD-ABORTS (exit 4) on a non-empty event so a
     looping model is stopped instead of silently burning turns.

  3. DOC-RULE LOCKSTEP. The durable rules this mitigates — `write` takes `path`,
     never `file`; tool args are ALWAYS a JSON object, never a string — are
     enforced as CONTENT in the validator's hint tables, so the hint the model
     receives is the same rule the dept TOOLS.md / AGENTS.md documents. A hint
     that only lived in prose and not in the validator would drift; here the
     validator IS the machine-readable rule.

WHAT THIS IS NOT: it does not run on the gateway itself (the OpenClaw gateway's
tool-validation layer is a separate runtime). It is the department engine's own
validator: the canonical runner probes it at Phase-0 (proving the validator is
installed and its fixture matrix passes) and the run-level event ledger records
any 5-strike loop the engine observed, so a schema loop that recurs across a
build is surfaced as AF-TOOL-SCHEMA-LOOP and stops the run.

EXIT CODES:
   0  all fixtures pass AND no AF-TOOL-SCHEMA-LOOP event present in the ledger
   2  a required check failed / bad invocation
   3  dependency unavailable (reserved; this validator is pure standard library)

DOCTRINE: offline, deterministic, never prints a value, reads the event ledger
only. The validator writes the AF-TOOL-SCHEMA-LOOP event ONLY when the 5th
consecutive failure occurs — a transient single malformed call is corrected by
the normalized hint, not by a build abort.

USAGE:
    python3 tool_schema_validator.py                     # self-test matrix, exit 0
    python3 tool_schema_validator.py --hint write        # print the schema hint
    python3 tool_schema_validator.py --validate write '{"path":"x"}'   # validate
    python3 tool_schema_validator.py --json              # machine-readable report
    python3 tool_schema_validator.py --ledger RUN_DIR --tool write --arg '..."  # record a malformed call against a run (returns the event id on the 5th consecutive failure, else '')
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

EXIT_OK = 0
EXIT_ERR = 1
EXIT_MISSING = 2
EXIT_DEP = 3

# The AF code this validator raises when 5 CONSECUTIVE schema failures trip.
AF_TOOL_SCHEMA_LOOP = "AF-TOOL-SCHEMA-LOOP"

# Consecutive-failure threshold before the loop alert fires.
CONSECUTIVE_FAILURE_LIMIT = 5

# ---------------------------------------------------------------------------
# THE SCHEMA HINT TABLE — the machine-readable rule set. Every entry is the
# normalized corrective hint a failing model receives, and the doc-rule lockstep
# (dept TOOLS.md / AGENTS.md) states these SAME rules as durable doctrine.
# ---------------------------------------------------------------------------
# For each tool: the canonical arg schema (name -> type) and the human hint.
# The hint is the EXACT string the validator returns — it must state the schema
# (not just "must be object") so the model can self-correct in one turn.
_SCHEMA_HINTS = {
    "write": (
        "write(path: string, content: string) — path is REQUIRED, not file; "
        "content is the full file body.",
        {"path": "string", "content": "string"},
    ),
    "read": (
        "read(path: string) — path is REQUIRED; optional offset/limit are integers.",
        {"path": "string", "offset": "integer", "limit": "integer"},
    ),
    "Edit": (
        "Edit(file_path: string, old_string: string, new_string: string) — "
        "file_path is REQUIRED, not file; all three arguments are strings.",
        {"file_path": "string", "old_string": "string", "new_string": "string"},
    ),
    "Bash": (
        "Bash(command: string) — command is REQUIRED; optional timeout is an "
        "integer (ms). description is a short human string.",
        {"command": "string", "description": "string", "timeout": "integer"},
    ),
    "WebSearch": (
        "WebSearch(query: string) — query is REQUIRED; optional "
        "allowed_domains/blocked_domains are arrays of strings.",
        {"query": "string", "allowed_domains": "array", "blocked_domains": "array"},
    ),
    "WebFetch": (
        "WebFetch(url: string, prompt: string) — url is REQUIRED.",
        {"url": "string", "prompt": "string"},
    ),
    "tool_call": (
        "tool_call(name: string, arguments: object) — arguments is a JSON OBJECT, "
        "never a string. Emit the args as a JSON object literal, not as a "
        "serialized string.",
        {"name": "string", "arguments": "object"},
    ),
}

# Every tool the dept engine documents. Unknown tools still get a generic hint
# that refuses a string-args dump and demands a JSON object.
_FALLBACK_HINT = (
    "Tool arguments are a JSON OBJECT, never a string. Emit the named tool's "
    "arguments as a JSON object literal ({} with key:value entries). Do NOT "
    "re-emit the schema dump; emit args as a JSON object."
)


def schema_hint(tool_name: str) -> str:
    """Return the normalized schema hint for a tool name (never the raw
    'must be object'). Unknown tools get the fallback object-demander."""
    entry = _SCHEMA_HINTS.get(tool_name)
    if entry is not None:
        return entry[0]
    return _FALLBACK_HINT


def validate_args(tool_name: str, args) -> dict:
    """Validate a tool call's args against the normalized schema.

    Returns a report dict:
      {ok, tool, hint, error}
    ok=True  -> args is a JSON-object-like mapping (dict), schema-conformant.
    ok=False -> args is malformed (a string, or a non-mapping, or a missing
                required key). The `hint` is the normalized corrective prompt.
    A STRING args value is ALWAYS malformed (the exact Error-10/D17 shape).
    """
    # The canonical failure: args serialized as a STRING instead of an object.
    if isinstance(args, str):
        hint = schema_hint(tool_name)
        return {"ok": False, "tool": tool_name, "hint": hint,
                "error": f"args must be object (got a string): {hint}"}
    if not isinstance(args, dict):
        hint = schema_hint(tool_name)
        return {"ok": False, "tool": tool_name, "hint": hint,
                "error": f"args must be object (got {type(args).__name__}): {hint}"}
    # Required-key enforcement for the known tools (path/file trap is the
    # flagship: `write`/`read`/`Edit` all REQUIRE path, never file).
    req = {"write": {"path"}, "read": {"path"}, "Edit": {"file_path"},
           "Bash": {"command"}, "WebSearch": {"query"}, "WebFetch": {"url"}}
    required = req.get(tool_name)
    if required:
        missing = [k for k in required if k not in args]
        if missing:
            hint = schema_hint(tool_name)
            return {"ok": False, "tool": tool_name, "hint": hint,
                    "error": f"missing required parameter: {missing[0]}. {hint}"}
    return {"ok": True, "tool": tool_name, "hint": schema_hint(tool_name),
            "error": ""}


# ---------------------------------------------------------------------------
# THE 5-STRIKE EVENT LEDGER
# ---------------------------------------------------------------------------
def _ledger_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "tool_schema_events.json"


def _load_events(run_dir: Path) -> list:
    p = _ledger_path(run_dir)
    if not p.exists():
        return []
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, list) else []
    except Exception:  # noqa: BLE001
        return []


def record_malformed(run_dir: Path, tool_name: str, arg_preview: str = "") -> str:
    """Record a CONSECUTIVE schema failure for a tool in a run's event ledger.

    The counter is per-run, per-tool, and CONSECUTIVE: a success (record_ok)
    between two failures resets the streak to zero. When a tool reaches
    CONSECUTIVE_FAILURE_LIMIT (5) consecutive failures, an AF-TOOL-SCHEMA-LOOP
    event is appended and the event id is returned; otherwise returns "".

    Never raises — a ledger that cannot be written drops the record and the
    event is simply not surfaced (the validator's own self-test still proves the
    fixture path, and the phase-0 preflight reads the event file fresh)."""
    events = _load_events(run_dir)
    loop_id = ""
    found = None
    for ev in events:
        if ev.get("tool") == tool_name and not ev.get("resolved"):
            found = ev
            break
    if found is None:
        found = {"tool": tool_name, "consecutive_failures": 0,
                 "resolved": False, "first_seen": _now()}
        events.append(found)
    found["consecutive_failures"] = int(found.get("consecutive_failures", 0)) + 1
    found["last_failure_ts"] = _now()
    if arg_preview:
        found["last_arg_preview"] = arg_preview[:120]
    if found["consecutive_failures"] >= CONSECUTIVE_FAILURE_LIMIT:
        loop_id = f"{tool_name}-{found['consecutive_failures']}"
        found["resolved"] = True
        found["event"] = {
            "code": AF_TOOL_SCHEMA_LOOP,
            "message": (f"{found['consecutive_failures']} consecutive schema "
                        f"failures on tool \"{tool_name}\". {schema_hint(tool_name)}"),
            "ts": _now(),
        }
    _write_events(run_dir, events)
    return loop_id


def record_ok(run_dir: Path, tool_name: str) -> None:
    """Record a SUCCESSFUL tool call for a tool, resetting its consecutive-failure
    streak (a single success breaks the loop)."""
    events = _load_events(run_dir)
    changed = False
    for ev in events:
        if ev.get("tool") == tool_name and not ev.get("resolved"):
            ev["consecutive_failures"] = 0
            ev["resolved"] = True  # mark the streak as ended by a success
            ev["resolved_by"] = "success"
            changed = True
    if changed:
        _write_events(run_dir, events)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_events(run_dir: Path, events: list) -> None:
    p = _ledger_path(run_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(events, indent=2))
    except Exception:  # noqa: BLE001
        pass


def active_loop_events(run_dir: Path) -> list:
    """Return every AF-TOOL-SCHEMA-LOOP event currently recorded (resolved or not).
    The runner's phase-0 preflight aborts when this is non-empty."""
    return [ev for ev in _load_events(run_dir) if ev.get("event")]


# ---------------------------------------------------------------------------
# SELF-TEST MATRIX (--self-test / bare run)
# ---------------------------------------------------------------------------
def self_test() -> list:
    """Run the validator's own fixture matrix. Returns a list of failure strings;
    empty = PASS. Every fixture is deterministic and offline.

    Known-good CONTROL: a conformant args object must validate OK — a validator
    that rejects good args is broken, and a PASS/FAIL split that lands exactly on
    the malformed boundary is a test of the class, not the validator."""
    failures = []

    # [A] String args are malformed for EVERY tool (the Error-10/D17 shape).
    for tool in ("tool_call", "write", "read", "Edit", "Bash", "WebSearch",
                 "WebFetch", "unknown-tool"):
        r = validate_args(tool, '{"path": "/tmp/x"}')
        if r["ok"]:
            failures.append(f"{tool}: string args must FAIL (ok was True)")

    # [B] Conformant object args PASS (the known-good control).
    good = [
        ("write", {"path": "/tmp/x", "content": "hi"}),
        ("read", {"path": "/tmp/x"}),
        ("Edit", {"file_path": "/tmp/x", "old_string": "a", "new_string": "b"}),
        ("Bash", {"command": "ls"}),
        ("WebSearch", {"query": "presentations"}),
        ("tool_call", {"name": "Bash", "arguments": {"command": "ls"}}),
    ]
    for tool, args in good:
        r = validate_args(tool, args)
        if not r["ok"]:
            failures.append(f"{tool}: conformant object args must PASS, got {r['error']!r}")

    # [C] The path/file trap: `write` with `file` and no `path` FAILS naming path.
    r = validate_args("write", {"file": "/tmp/x", "content": "hi"})
    if r["ok"] or "path" not in r["error"]:
        failures.append("write(file=...): must FAIL naming path (the path/file trap)")

    # [D] The normalized hint is present (never the raw 'must be object').
    r = validate_args("write", "bad")
    if "path is REQUIRED" not in r["hint"]:
        failures.append("write hint must state the schema (path is REQUIRED, not file)")

    # [E] 5 consecutive failures write the AF-TOOL-SCHEMA-LOOP event; a success
    # between failures resets the streak; the event fires exactly at 5.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td)
        loop_id = ""
        for i in range(1, CONSECUTIVE_FAILURE_LIMIT + 1):
            loop_id = record_malformed(run_dir, "write", '{"file": "x"}')
        if loop_id == "":
            failures.append("5 consecutive failures must write the AF-TOOL-SCHEMA-LOOP event")
        events = active_loop_events(run_dir)
        if not events or events[0]["event"]["code"] != AF_TOOL_SCHEMA_LOOP:
            failures.append("the 5th consecutive failure must record AF-TOOL-SCHEMA-LOOP")
        if events and CONSECUTIVE_FAILURE_LIMIT not in (
                events[0].get("consecutive_failures"),):
            failures.append("the event must record the consecutive_failures count")

        # A success resets the streak: 4 failures, 1 success, 4 failures -> NO event.
        td2 = Path(td) / "reset"
        td2.mkdir()
        for _ in range(4):
            record_malformed(td2, "Bash", "bad")
        record_ok(td2, "Bash")
        for _ in range(4):
            record_malformed(td2, "Bash", "bad")
        if active_loop_events(td2):
            failures.append("a success between failures must reset the streak (no event at 4+1+4)")

    return failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="FIX-18 tool-schema validator")
    ap.add_argument("--hint", metavar="TOOL", help="print the normalized schema hint")
    ap.add_argument("--validate", nargs=2, metavar=("TOOL", "ARGS_JSON"),
                    help="validate a JSON args blob for a tool")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--ledger", nargs=3, metavar=("RUN_DIR", "TOOL", "ARGS_JSON"),
                    help="record a malformed call against a run dir")
    ap.add_argument("--self-test", action="store_true",
                    help="force the full fixture matrix, exit 0 on pass")
    args = ap.parse_args(argv)

    if args.hint:
        print(schema_hint(args.hint))
        return EXIT_OK

    if args.validate:
        tool, raw = args.validate
        try:
            parsed = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            # A non-JSON blob is itself a string-args failure.
            parsed = raw
        rep = validate_args(tool, parsed)
        if args.json:
            print(json.dumps(rep, indent=2))
        else:
            if rep["ok"]:
                print(f"OK: {tool} args valid")
            else:
                print(f"INVALID: {rep['error']}")
        return EXIT_OK if rep["ok"] else EXIT_MISSING

    if args.ledger:
        run_dir, tool, raw = args.ledger
        try:
            parsed = json.loads(raw)
        except Exception:  # noqa: BLE001
            parsed = raw
        rep = validate_args(tool, parsed)
        loop_id = ""
        if not rep["ok"]:
            loop_id = record_malformed(Path(run_dir), tool, raw)
        else:
            record_ok(Path(run_dir), tool)
        if args.json:
            print(json.dumps({"loop_event": loop_id, **rep}, indent=2))
        else:
            if loop_id:
                print(f"AF-TOOL-SCHEMA-LOOP event: {loop_id}")
            elif rep["ok"]:
                print("OK: args valid; streak reset")
            else:
                print("malformed: hint returned")
        return EXIT_OK

    # Default / --self-test: run the full matrix.
    failures = self_test()
    report = {
        "validator": "tool_schema_validator",
        "fix": "FIX-18",
        "schema_tools": sorted(_SCHEMA_HINTS.keys()),
        "consecutive_failure_limit": CONSECUTIVE_FAILURE_LIMIT,
        "af_code": AF_TOOL_SCHEMA_LOOP,
        "passed": not failures,
        "failures": failures,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if not failures:
            print("=== tool_schema_validator: SELF-TEST PASS ===")
            print(f"schema tools: {len(_SCHEMA_HINTS)}; loop limit: "
                  f"{CONSECUTIVE_FAILURE_LIMIT}; af-code: {AF_TOOL_SCHEMA_LOOP}")
        else:
            print("=== tool_schema_validator: SELF-TEST FAIL ===", file=sys.stderr)
            for f in failures:
                print(f"  {f}", file=sys.stderr)
    return EXIT_OK if not failures else EXIT_MISSING


if __name__ == "__main__":
    sys.exit(main())

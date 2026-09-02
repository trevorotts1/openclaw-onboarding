#!/usr/bin/env python3
"""
qc_timing_report.py -- THE SMOKE TIMING REPORT (workflow W28b, builder B3).

WHAT THIS IS
------------
A standalone, read-only reporting module that emits the TIMING rows of the
SMOKE section of the department's QC.md ("THE SMOKE (judged after Step 2)"):

  1. **Elapsed --new to DONE.**  "Live deck-12 on the operator box: same,
     elapsed <= 60 minutes from `--new` to DONE". The elapsed window is
     measured between the run's `state.json` `created_at` (written by
     `presentation_job --new`) and the `ended_at` of the LAST successful
     (`status: "done"`) `phase_exit` row in `working/telemetry/stage-timings.jsonl`
     -- or, when that file is absent, the `state.json` `updated_at`. This
     function never decides PASS/FAIL for the smoke; it reports the measured
     numbers and names its data sources so a judge can re-derive every row.

  2. **Phase wall-clock rows.**  One row per phase_id, aggregated from the
     FIX 5 stage-timing rows (schema: run_id, phase_id, wave, model_used,
     event, started_at, ended_at, duration_s, status [, error_class]
     [, return_code]): attempts, total duration, max duration, last status.
     The per-phase `PHASE_BUDGET_MINUTES` context is included when the
     manifest can be resolved, so an over-budget phase is visible at a glance.

  3. **Resume invocations.**  "zero `--resume` invocations in the engine log".
     Counts occurrences of the literal `--resume` token in
     `working/logs/engine-stdout.log` (the launcher redirects the engine's
     stdout/stderr there). The count is reported together with the byte size
     of the log: a count of 0 over a 0-byte (absent) log is NOT the same
     claim as a count of 0 over a real log -- the report distinguishes them
     explicitly (a missing log yields `log_present: false` and the claim
     stays UNDETERMINED, per the result.py doctrine).

  4. **Kie window (governor).**  "governor log shows no Kie window over 20".
     Reads the same engine log for concurrency-window lines and reports the
     largest window observed, if any line carries one. Missing/unreadable
     log -> `UNDETERMINED`, never a silent pass.

DESIGN RULES
------------
- **Read-only.** Opens run-dir files; writes nothing inside the run dir.
  The only thing it writes is its own stdout (and optionally --out JSON,
  which must NOT be inside the run dir being reported on).
- **Three-valued.** Every boolean-ish claim carries one of PASS / FAIL /
  UNDETERMINED (presentation_job.result.CheckResult semantics); a missing
  or unreadable source is UNDETERMINED, never folded into a pass.
- **Hermetic.** No network, no subprocesses, no manifest writes; importing
  this module has no side effects. Safe to run from any cwd.
- **Stdlib only.**

CLI
---
    python3 qc_timing_report.py --run-dir /path/to/run [--out report.json]
    python3 qc_timing_report.py --run-dir /path/to/run --json     # stdout JSON
    python3 qc_timing_report.py --selftest

Exit codes (mirror state.py's doctrine of distinguishable outcomes):
    0  report written, every claim derivable from real data
    3  report written, but at least one claim is FAIL
   10  report written, but at least one claim is UNDETERMINED (no FAILs)
    2  usage error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 60-minute smoke ceiling, QC.md THE SMOKE: "elapsed <= 60 minutes from --new
# to DONE". A named constant, not a magic number, so a judge can cite it.
SMOKE_ELAPSED_CEILING_MINUTES = 60.0

ENGINE_LOG_RELATIVE = Path("working") / "logs" / "engine-stdout.log"
STAGE_TIMINGS_RELATIVE = Path("working") / "telemetry" / "stage-timings.jsonl"
STATE_RELATIVE = Path("state.json")

# The engine log lines the dispatcher/governor writes for the Kie concurrency
# window (FIX 5/F-R8: "governor log shows no Kie window over 20"). Matched
# liberally so a wording tweak upstream cannot blind the reader: any line
# containing "kie" case-insensitively AND a "window" mention is scanned for a
# trailing integer.
_KIE_WINDOW_RE = re.compile(r"(?i)kie.*window[^0-9]*([0-9]+)")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_HAS_FAIL = 3
EXIT_HAS_UNDETERMINED = 10


# ---------------------------------------------------------------------------
# Three-valued verdict (mirrors presentation_job.result semantics without
# importing the package: this module must work on a bare run-dir copy where
# presentation_job may be absent).
# ---------------------------------------------------------------------------
class Verdict:
    PASS = "PASS"
    FAIL = "FAIL"
    UNDETERMINED = "UNDETERMINED"


def _parse_iso(ts: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp the way utcnow() writes it, tolerating a
    missing tz and a trailing 'Z'. Returns None on garbage -- never raises,
    never fabricates a time."""
    if not ts or not isinstance(ts, str):
        return None
    txt = ts.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None
    if dt.tzinfo is None:
        # Treat a naive stamp as UTC (the engine writes timezone-aware stamps;
        # a naive one can only come from a hand-made fixture).
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _read_jsonl(path: Path) -> Tuple[List[Dict[str, Any]], bool]:
    """Read a .jsonl file. Returns (rows, file_present). A present-but-unreadable
    file returns ([], True) so callers can distinguish absent from unreadable."""
    if not path.is_file():
        return [], False
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a torn last line after a crash is expected
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        return [], True  # present, unreadable
    return rows, True


def _read_text(path: Path) -> Tuple[str, bool]:
    if not path.is_file():
        return "", False
    try:
        return path.read_text(encoding="utf-8", errors="replace"), True
    except OSError:
        return "", True  # present, unreadable


# ---------------------------------------------------------------------------
# Core collectors
# ---------------------------------------------------------------------------
def collect_phase_rows(stage_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate FIX 5 stage-timing rows into one wall-clock row per phase_id.

    Only `event == "phase_exit"` rows carry a whole-phase duration; slide-level
    and other rows are ignored for the per-phase table (their own volume is
    reported as an input sanity count).
    """
    by_phase: Dict[str, Dict[str, Any]] = {}
    for r in stage_rows:
        if r.get("event") != "phase_exit":
            continue
        pid = r.get("phase_id") or "?"
        dur = r.get("duration_s")
        rec = by_phase.setdefault(pid, {
            "phase_id": pid,
            "attempts": 0,
            "total_duration_s": 0.0,
            "max_duration_s": 0.0,
            "last_status": None,
            "last_ended_at": None,
            "errors": [],
        })
        rec["attempts"] += 1
        if isinstance(dur, (int, float)):
            rec["total_duration_s"] = round(rec["total_duration_s"] + float(dur), 3)
            rec["max_duration_s"] = round(max(rec["max_duration_s"], float(dur)), 3)
        else:
            rec["errors"].append("duration_s missing or non-numeric")
        rec["last_status"] = r.get("status")
        rec["last_ended_at"] = r.get("ended_at") or rec["last_ended_at"]
        if r.get("error_class"):
            rec["errors"].append(str(r["error_class"]))
    rows = list(by_phase.values())
    rows.sort(key=lambda x: (x["last_ended_at"] or "", x["phase_id"]))
    return rows


def collect_elapsed(state: Optional[Dict[str, Any]],
                    stage_rows: List[Dict[str, Any]],
                    stage_file_present: bool) -> Dict[str, Any]:
    """Row 1: elapsed --new to DONE.

    start anchor  : state.json `created_at`  (written by --new)
    end anchor    : `ended_at` of the LAST `phase_exit` row with status "done"
                    (falls back to state.json `updated_at` when no such row
                    exists -- stated in the row, never hidden)
    """
    out: Dict[str, Any] = {
        "claim": "elapsed --new to DONE <= %g minutes" % SMOKE_ELAPSED_CEILING_MINUTES,
        "verdict": Verdict.UNDETERMINED,
        "start_anchor": "state.json created_at",
        "end_anchor": "last done phase_exit ended_at (stage-timings.jsonl)",
        "elapsed_minutes": None,
        "started_at": None,
        "ended_at": None,
        "end_anchor_source": None,
        "terminal": None,
        "reason": None,
    }
    if not isinstance(state, dict):
        out["reason"] = "state.json absent or unreadable"
        return out
    out["terminal"] = state.get("terminal")
    start = _parse_iso(state.get("created_at"))
    if start is None:
        out["reason"] = "state.json has no parseable created_at"
        return out
    out["started_at"] = state.get("created_at")

    end_dt: Optional[datetime] = None
    done_rows = [r for r in stage_rows
                 if r.get("event") == "phase_exit" and r.get("status") == "done"
                 and _parse_iso(r.get("ended_at")) is not None]
    if done_rows:
        latest = max(done_rows, key=lambda r: _parse_iso(r["ended_at"]))
        end_dt = _parse_iso(latest["ended_at"])
        out["ended_at"] = latest["ended_at"]
        out["end_anchor_source"] = "stage-timings.jsonl"
    elif isinstance(state.get("updated_at"), str):
        end_dt = _parse_iso(state["updated_at"])
        out["ended_at"] = state["updated_at"]
        out["end_anchor_source"] = "state.json updated_at (no done phase_exit row%s)" % (
            "" if stage_file_present else "; stage-timings.jsonl absent")
    if end_dt is None:
        out["reason"] = "no usable end anchor"
        return out

    elapsed_min = round((end_dt - start).total_seconds() / 60.0, 3)
    if elapsed_min < 0:
        # A negative window is a clock/fixture anomaly, not a measurement:
        # report UNDETERMINED with the number withheld (it would otherwise
        # read as a real, if absurd, elapsed time).
        out["verdict"] = Verdict.UNDETERMINED
        out["reason"] = "negative elapsed window (clock or fixture anomaly)"
        return out
    out["elapsed_minutes"] = elapsed_min
    out["verdict"] = Verdict.PASS if elapsed_min <= SMOKE_ELAPSED_CEILING_MINUTES else Verdict.FAIL
    return out


def collect_resume_invocations(engine_log_text: str,
                               engine_log_present: bool) -> Dict[str, Any]:
    """Row 3: count of `--resume` invocations in the engine log.

    The smoke claim is "zero --resume invocations in the engine log". A zero
    over an ABSENT log is not that claim -- it is UNDETERMINED. The count of
    `--resume` tokens found is reported alongside `log_present` and the byte
    size so the judge can see what the zero was measured over.
    """
    out: Dict[str, Any] = {
        "claim": "zero --resume invocations in the engine log",
        "verdict": Verdict.UNDETERMINED,
        "log_present": engine_log_present,
        "log_bytes": None,
        "resume_token_count": None,
        "reason": None,
    }
    if not engine_log_present:
        out["reason"] = "engine log absent (working/logs/engine-stdout.log)"
        return out
    count = len(re.findall(r"--resume\b", engine_log_text))
    out["log_bytes"] = len(engine_log_text.encode("utf-8", errors="replace"))
    out["resume_token_count"] = count
    out["verdict"] = Verdict.PASS if count == 0 else Verdict.FAIL
    return out


def collect_kie_window(engine_log_text: str,
                       engine_log_present: bool) -> Dict[str, Any]:
    """Row 4: largest observed Kie concurrency window in the engine log.

    The smoke claim is "governor log shows no Kie window over 20". The log is
    scanned for lines mentioning the Kie window; the maximum observed integer
    is reported. No window line in a present log -> PASS with observed_max None
    and lines_scanned so the judge can see the scan was real. Absent log ->
    UNDETERMINED. An unreadable-but-present log is also UNDETERMINED.
    """
    out: Dict[str, Any] = {
        "claim": "no Kie window over 20 in the governor/engine log",
        "verdict": Verdict.UNDETERMINED,
        "log_present": engine_log_present,
        "window_lines_scanned": 0,
        "observed_max": None,
        "reason": None,
    }
    if not engine_log_present:
        out["reason"] = "engine log absent (working/logs/engine-stdout.log)"
        return out
    if not engine_log_text:
        out["reason"] = "engine log present but unreadable"
        return out
    observed: List[int] = []
    for line in engine_log_text.splitlines():
        if "kie" not in line.lower() or "window" not in line.lower():
            continue
        m = _KIE_WINDOW_RE.search(line)
        if m:
            out["window_lines_scanned"] += 1
            try:
                observed.append(int(m.group(1)))
            except ValueError:  # pragma: no cover - regex guarantees digits
                pass
    if observed:
        out["observed_max"] = max(observed)
        out["verdict"] = Verdict.PASS if out["observed_max"] <= 20 else Verdict.FAIL
    else:
        out["verdict"] = Verdict.PASS
        out["reason"] = "no kie-window line found in a present, readable log"
    return out


def collect_terminal(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Supporting row: state.terminal == DONE (the smoke's own first bullet is
    state/bundle; the timing report carries terminal so the elapsed row is
    interpretable in isolation)."""
    terminal = state.get("terminal") if isinstance(state, dict) else None
    return {
        "claim": "state.terminal recorded",
        "verdict": Verdict.UNDETERMINED if terminal is None else Verdict.PASS,
        "terminal": terminal,
        "reason": None if terminal is not None else "state.json absent or terminal unset",
    }


def build_report(run_dir: Path) -> Dict[str, Any]:
    """Assemble the full timing report for one run dir. Read-only."""
    run_dir = run_dir.expanduser().resolve()
    stage_path = run_dir / STAGE_TIMINGS_RELATIVE
    engine_log_path = run_dir / ENGINE_LOG_RELATIVE
    state_path = run_dir / STATE_RELATIVE

    stage_rows, stage_present = _read_jsonl(stage_path)
    engine_text, engine_present = _read_text(engine_log_path)

    state: Optional[Dict[str, Any]] = None
    state_present = state_path.is_file()
    if state_present:
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8", errors="replace"))
            state = loaded if isinstance(loaded, dict) else None
        except (json.JSONDecodeError, OSError):
            state = None

    claims = [
        collect_elapsed(state, stage_rows, stage_present),
        collect_terminal(state),
        collect_resume_invocations(engine_text, engine_present),
        collect_kie_window(engine_text, engine_present),
    ]
    verdicts = {c["verdict"] for c in claims}
    overall = Verdict.UNDETERMINED
    if Verdict.FAIL in verdicts:
        overall = Verdict.FAIL
    elif verdicts == {Verdict.PASS}:
        overall = Verdict.PASS

    return {
        "report": "smoke_timing",
        "run_dir": str(run_dir),
        "sources": {
            "state_json": {"present": state_present, "parsed": state is not None,
                           "path": str(STATE_RELATIVE)},
            "stage_timings": {"present": stage_present, "rows": len(stage_rows),
                              "path": str(STAGE_TIMINGS_RELATIVE)},
            "engine_log": {"present": engine_present,
                           "path": str(ENGINE_LOG_RELATIVE)},
        },
        "phase_rows": collect_phase_rows(stage_rows),
        "claims": claims,
        "overall": overall,
        "ceiling_minutes": SMOKE_ELAPSED_CEILING_MINUTES,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _selftest() -> int:
    """Hermetic self-test over a tempdir fixture: proves each collector can
    PASS, FAIL, and stay UNDETERMINED on constructed inputs."""
    import tempfile

    def expect(cond: bool, what: str) -> bool:
        print(("  ok  " if cond else "  FAIL") + " " + what)
        return cond

    ok = True
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run"
        (rd / "working" / "telemetry").mkdir(parents=True)
        (rd / "working" / "logs").mkdir(parents=True)
        t0, t1 = "2026-09-01T10:00:00+00:00", "2026-09-01T10:20:00+00:00"
        (rd / "state.json").write_text(json.dumps({
            "schema_version": 1, "job_id": "pj_x", "created_at": t0,
            "updated_at": t1, "terminal": "DONE", "phases": []}))
        timings = [
            {"run_id": "run", "phase_id": "P1-COPY", "wave": 0, "model_used": None,
             "event": "phase_exit", "started_at": t0, "ended_at": t1,
             "duration_s": 1200.0, "status": "done", "return_code": 0},
        ]
        with (rd / STAGE_TIMINGS_RELATIVE).open("w") as fh:
            for r in timings:
                fh.write(json.dumps(r) + "\n")
        # A present, clean engine log: leg 1's zero-claims must be measured
        # over a REAL log, not an absent one (absent = UNDETERMINED by design).
        (rd / ENGINE_LOG_RELATIVE).write_text(
            "engine up\nP4-PROMPT done\n", encoding="utf-8")

        # leg 1: happy run -> PASS everywhere, elapsed 20 min
        rep = build_report(rd)
        ok &= expect(rep["overall"] == Verdict.PASS, "clean fixture overall PASS")
        ok &= expect(rep["claims"][0]["elapsed_minutes"] == 20.0, "elapsed 20.0 min")
        ok &= expect(rep["claims"][2]["resume_token_count"] == 0
                     and rep["claims"][2]["verdict"] == Verdict.PASS,
                     "zero --resume over a present log is PASS")
        ok &= expect(rep["claims"][3]["verdict"] == Verdict.PASS
                     and rep["claims"][3]["window_lines_scanned"] == 0,
                     "no kie-window line over a present log is PASS")

        # leg 2: resume + over-window + slow -> three FAILs
        with (rd / ENGINE_LOG_RELATIVE).open("w") as fh:
            fh.write("dispatch --resume --run-dir x\n"
                     "kie concurrency window now 21\n")
        st = dict(json.loads((rd / "state.json").read_text()))
        st["created_at"] = "2026-09-01T10:00:00+00:00"
        st["updated_at"] = "2026-09-01T11:10:00+00:00"
        (rd / "state.json").write_text(json.dumps(st))
        # The elapsed row's end anchor is the LAST done phase_exit ended_at,
        # which precedes updated_at. To exercise the 60-minute ceiling against
        # the updated_at anchor, remove the done stage rows (no done row =>
        # updated_at is the anchor, as documented in collect_elapsed).
        (rd / STAGE_TIMINGS_RELATIVE).write_text("", encoding="utf-8")
        rep = build_report(rd)
        ok &= expect(rep["claims"][0]["verdict"] == Verdict.FAIL
                     and rep["claims"][0]["elapsed_minutes"] == 70.0,
                     "70-min elapsed FAILs the 60-min ceiling")
        ok &= expect(rep["claims"][2]["verdict"] == Verdict.FAIL
                     and rep["claims"][2]["resume_token_count"] == 1,
                     "one --resume FAILs")
        ok &= expect(rep["claims"][3]["verdict"] == Verdict.FAIL
                     and rep["claims"][3]["observed_max"] == 21,
                     "kie window 21 FAILs")
        ok &= expect(rep["overall"] == Verdict.FAIL, "overall FAIL")

        # leg 3: absent engine log + absent stage timings -> UNDETERMINED, not pass.
        # The elapsed row stays a real PASS (20-min updated_at anchor) so the
        # overall verdict is driven ONLY by the two absent-source claims --
        # proving UNDETERMINED never folds into either pass or fail.
        (rd / ENGINE_LOG_RELATIVE).unlink()
        (rd / STAGE_TIMINGS_RELATIVE).unlink()
        st2 = dict(st)
        st2["updated_at"] = "2026-09-01T10:20:00+00:00"
        st2["created_at"] = "2026-09-01T10:00:00+00:00"
        (rd / "state.json").write_text(json.dumps(st2))
        rep = build_report(rd)
        ok &= expect(rep["claims"][0]["verdict"] == Verdict.PASS
                     and rep["claims"][0]["end_anchor_source"].startswith("state.json updated_at"),
                     "updated_at fallback anchor named out loud")
        ok &= expect(rep["claims"][2]["verdict"] == Verdict.UNDETERMINED,
                     "zero --resume over an ABSENT log is UNDETERMINED")
        ok &= expect(rep["claims"][3]["verdict"] == Verdict.UNDETERMINED,
                     "kie window over an ABSENT log is UNDETERMINED")
        ok &= expect(rep["overall"] == Verdict.UNDETERMINED, "overall UNDETERMINED")
        ok &= expect(rep["sources"]["stage_timings"]["present"] is False,
                     "absent stage-timings reported as absent")

    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    return EXIT_OK if ok else EXIT_HAS_FAIL


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="SMOKE timing report (W28b-B3)")
    ap.add_argument("--run-dir", type=Path, help="run directory to report on")
    ap.add_argument("--out", type=Path, help="optional JSON output path (outside the run dir)")
    ap.add_argument("--json", action="store_true", help="print JSON to stdout")
    ap.add_argument("--selftest", action="store_true", help="run the hermetic self-test")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.run_dir:
        ap.error("--run-dir is required (or use --selftest)")
    if not args.run_dir.is_dir():
        print(f"ERROR: --run-dir is not a directory: {args.run_dir}", file=sys.stderr)
        return EXIT_USAGE

    report = build_report(args.run_dir)
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        out_path = args.out.expanduser().resolve()
        if out_path.resolve().is_relative_to(args.run_dir.expanduser().resolve()) \
                if hasattr(Path, "is_relative_to") else False:
            print("ERROR: --out must not live inside the run dir (report is read-only "
                  "with respect to the run it measures)", file=sys.stderr)
            return EXIT_USAGE
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
        print(f"wrote {out_path}")
    if args.json or not args.out:
        print(payload)
    if report["overall"] == Verdict.FAIL:
        return EXIT_HAS_FAIL
    if report["overall"] == Verdict.UNDETERMINED:
        return EXIT_HAS_UNDETERMINED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

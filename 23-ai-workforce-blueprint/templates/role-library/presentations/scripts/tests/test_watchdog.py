"""Tests for presentation_job watchdog (U016). No real sleeps, no network."""

from __future__ import annotations

import hashlib, json, os, re, shutil, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.watchdog import watchdog, _find_state_files
from presentation_job.state import EXIT_OK, EXIT_STALLED
from presentation_job.report import dispatch as report_dispatch


def _w(fd, phase, iv, age, budget=240, src="manifest_heartbeat_minutes",
       terminal=None, no_hb=False, bad_ts=False, jid=None):
    fd.mkdir(parents=True, exist_ok=True)
    if jid is None: jid = "pj_" + fd.name
    ts = "not-a-date" if bad_ts else (datetime.now(timezone.utc) - timedelta(minutes=age)).isoformat(timespec="seconds")
    hb = {"last_checkpoint_at": ts, "current_phase": phase,
          "interval_minutes": iv, "budget_minutes": budget, "interval_source": src}
    st = {"schema_version": 1, "job_id": jid, "run_dir": str(fd),
          "terminal": terminal, "current_phase": phase, "heartbeat": hb}
    if no_hb: st.pop("heartbeat")
    (fd / "state.json").write_text(json.dumps(st, indent=2))

def _sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def _run(root, **kw):
    import io
    buf = io.StringIO()
    try:
        old = sys.stdout; sys.stdout = buf
        rc = watchdog(root, **kw)
    finally: sys.stdout = old
    return rc, buf.getvalue()

# 1
def test_p4_render_12min_old_not_stalled(tmp_path):
    _w(tmp_path / "a", "P4-RENDER", 10, 12)
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert rc == EXIT_OK and "STALLED" not in out

# 2
def test_p4_render_20min_old_is_stalled(tmp_path):
    _w(tmp_path / "a", "P4-RENDER", 10, 20)
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "STALLED" in out and "threshold 15.0 min = interval 10 x grace 1.5" in out

# 3
def test_regression_no_budget_240_threshold(tmp_path):
    _w(tmp_path / "a", "P4-RENDER", 10, 20)
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "budget 240" not in out and "threshold 15.0" in out and "360" not in out

# 4
def test_phase_without_heartbeat_minutes_falls_back_to_budget(tmp_path):
    _w(tmp_path / "a", "P8.4-FISH-TAG", 15, 25, budget=15, src="phase_budget_fallback")
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "STALLED" in out and "interval source: phase_budget_fallback" in out

# 5
def test_pred_u016_no_interval_minutes_uses_budget_table(tmp_path):
    d = tmp_path / "a"; d.mkdir(parents=True)
    ts = (datetime.now(timezone.utc) - timedelta(minutes=400)).isoformat(timespec="seconds")
    (d/"state.json").write_text(json.dumps({"schema_version":1,"job_id":"pj_test","run_dir":str(d),"terminal":None,"current_phase":"P4-RENDER","heartbeat":{"last_checkpoint_at":ts,"current_phase":"P4-RENDER","budget_minutes":240}}))
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "STALLED" in out and "interval source: budget_table" in out

# 5b (HARDEN G3): an adversarial re-attack on the sync_check E3 fix proved that guarding
# only `interval <= 0` is NOT a range check. Setting interval_minutes to 999999999 (present,
# positive, so E3's original presence-and-positivity assertion passed it) reaches the
# watchdog and produced a ~1.5-BILLION-minute threshold (999999999 x grace 1.5) that never
# trips -- a job silent for 12 hours (720 min) read as perfectly healthy. This proves the
# watchdog now independently distrusts an out-of-range interval it finds on disk (defense in
# depth beyond Phase.heartbeat_interval_minutes refusing to ever write one) and falls back to
# the budget table exactly as it does for interval<=0.
def test_g3_insane_interval_minutes_falls_back_to_budget_not_blinded(tmp_path):
    _w(tmp_path / "a", "P-QC-AGGREGATE", 999999999, 720, budget=10)
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "STALLED" in out, (
        "a 12-hour-silent job with interval_minutes=999999999 must be caught, not read as "
        "healthy -- this is the exact HARDEN G3 bypass"
    )
    assert "interval source: budget_table" in out
    assert "1499999998" not in out, "the insane interval must never reach the threshold math"

def test_g3_interval_minutes_exactly_at_ceiling_still_trusted(tmp_path):
    # 240 == MAX_HEARTBEAT_INTERVAL_MINUTES (PHASE_BUDGET_MINUTES's own max) is a legitimate
    # value and must be trusted as-is, not silently swapped for the budget-table fallback.
    _w(tmp_path / "a", "P4-RENDER", 240, 400, src="manifest_heartbeat_minutes")
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "STALLED" in out and "interval source: manifest_heartbeat_minutes" in out
    assert "threshold 360.0" in out  # 240 x 1.5, the manifest value trusted unchanged

# 6
def test_unknown_phase_loud_default_fallback(tmp_path):
    d = tmp_path / "a"; d.mkdir(parents=True)
    ts = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat(timespec="seconds")
    (d/"state.json").write_text(json.dumps({"schema_version":1,"job_id":"pj_test","run_dir":str(d),"terminal":None,"current_phase":"P-INVENTED-PHASE","heartbeat":{"last_checkpoint_at":ts,"current_phase":"P-INVENTED-PHASE"}}))
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "STALLED" in out and "DEFAULT_20min_NO_ENTRY_FOR_P-INVENTED-PHASE" in out

# 7
def test_terminal_jobs_skipped(tmp_path):
    _w(tmp_path/"done","P4-RENDER",10,999,terminal="DONE")
    _w(tmp_path/"blocked","P4-RENDER",10,999,terminal="BLOCKED")
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "STALLED" not in out

# 8
def test_no_last_checkpoint_skipped_counted(tmp_path):
    _w(tmp_path/"a","P4-RENDER",10,20,no_hb=True)
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "STALLED" not in out and "without a heartbeat" in out

# 9
def test_malformed_timestamp_skipped_no_traceback(tmp_path):
    _w(tmp_path/"a","P4-RENDER",10,20,bad_ts=True)
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert rc == EXIT_OK and "STALLED" not in out and "unreadable timestamp" in out

# 10
def test_depth_3_found_only_with_depth_3(tmp_path):
    _w(tmp_path/"a"/"b"/"deep","P4-RENDER",10,40)
    rc1, out1 = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "STALLED" not in out1
    rc3, out3 = _run(tmp_path, grace_multiplier=1.5, scan_depth=3)
    assert "STALLED" in out3

# 11
def test_symlink_dedup(tmp_path):
    real = tmp_path/"real"/"a"; _w(real,"P4-RENDER",10,40)
    link = tmp_path/"link"; link.mkdir(); (link/"b").symlink_to(real)
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=3)
    assert out.count("STALLED") == 1

# 12
def test_default_exits_0_enforce_exits_5(tmp_path):
    _w(tmp_path/"a","P4-RENDER",10,40)
    rc_def, _ = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert rc_def == EXIT_OK
    rc_enf, _ = _run(tmp_path, grace_multiplier=1.5, scan_depth=1, enforce=True)
    assert rc_enf == EXIT_STALLED

# 13
def test_scanned_zero_prints_no_state_json_found(tmp_path):
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    assert "NO state.json found" in out and rc == EXIT_OK

# 14
def test_watchdog_never_writes_state_json(tmp_path):
    _w(tmp_path/"a","P4-RENDER",10,40)
    _w(tmp_path/"b","P4-RENDER",10,12)
    before = {str(p): _sha(p) for p in sorted(tmp_path.glob("*/state.json"))}
    _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    after = {str(p): _sha(p) for p in sorted(tmp_path.glob("*/state.json"))}
    assert before == after

# 15
def test_findings_jsonl_one_line_per_stall(tmp_path):
    _w(tmp_path/"a","P4-RENDER",10,40)
    _w(tmp_path/"b","P4-RENDER",10,50)
    _w(tmp_path/"c","P4-RENDER",10,12)
    _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    p = tmp_path/"watchdog-findings.jsonl"
    assert p.exists()
    lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        obj = json.loads(ln)
        assert "at" in obj and "phase" in obj and "threshold_minutes" in obj

# 16
def test_one_notification_per_scan(tmp_path, monkeypatch):
    _w(tmp_path/"a","P4-RENDER",10,40)
    _w(tmp_path/"b","P4-RENDER",10,50)
    _w(tmp_path/"c","P4-RENDER",10,60)
    log = tmp_path/"notify.log"
    # U069: PRESENTATION_NOTIFY_CMD is tokenised with shlex and run with
    # shell=False, so a raw shell redirect like "cat >> {log}" no longer
    # means anything -- ">>" and the path would just be literal argv tokens
    # to `cat`. Route the redirect through a real script instead (same
    # pattern as tests/test_report.py's notify scripts).
    ns = tmp_path/"notify.sh"
    ns.write_text(f"#!/bin/sh\ncat >> {log}\n")
    ns.chmod(0o755)
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
    _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    notify_lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
    n = sum(1 for ln in notify_lines if ln.strip().startswith('{'))
    assert n == 1

# 17
def test_counter_checksum(tmp_path):
    _w(tmp_path/"term","P4-RENDER",10,999,terminal="DONE")
    nh = tmp_path/"no_hb"; nh.mkdir()
    (nh/"state.json").write_text(json.dumps({"schema_version":1,"job_id":"pj_nh","run_dir":str(nh),"terminal":None,"current_phase":"P4-RENDER"}))
    bad = tmp_path/"bad_ts"; bad.mkdir()
    (bad/"state.json").write_text(json.dumps({"schema_version":1,"job_id":"pj_bad","run_dir":str(bad),"terminal":None,"current_phase":"P4-RENDER","heartbeat":{"last_checkpoint_at":"not-a-date","current_phase":"P4-RENDER","interval_minutes":10}}))
    _w(tmp_path/"healthy","P4-RENDER",10,12)
    _w(tmp_path/"stalled","P4-RENDER",10,40)
    rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    m = re.search(r"watchdog: scanned (\d+) state file\(s\).*?; (\d+) terminal, (\d+) without a heartbeat, (\d+) with an unreadable timestamp, (\d+) healthy, (\d+) stalled", out, re.S)
    assert m
    scanned, term, no_hb, bad_ts, healthy_n, stalled = (int(g) for g in m.groups())
    assert term + no_hb + bad_ts + healthy_n + stalled == scanned
    assert term == 1 and no_hb == 1 and bad_ts == 1 and healthy_n == 1 and stalled == 1
    shutil.rmtree(tmp_path/"bad_ts")
    rc2, out2 = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
    m2 = re.search(r"watchdog: scanned (\d+) state file\(s\).*?; (\d+) terminal, (\d+) without a heartbeat, (\d+) with an unreadable timestamp, (\d+) healthy, (\d+) stalled", out2, re.S)
    assert m2 and int(m2.group(1)) == 4 and int(m2.group(4)) == 0


# ---------------------------------------------------------------------------
# U069 bypass closure #2: report.py had TWO independent implementations of
# the PRESENTATION_NOTIFY_CMD transport -- Reporter._dispatch (fixed:
# shlex.split + shell=False) and a module-level dispatch() left on
# shell=True. watchdog.py imports and calls the module-level function
# directly (`from .report import dispatch`), so it stayed exploitable even
# though the class method was closed -- and __main__.cmd_sweep_undeliverable
# held a THIRD, independently hand-rolled subprocess.run(cmd, shell=True,
# ...) of its own. All three now route through the single report.dispatch()
# implementation. These tests drive a real command-substitution payload
# through report.dispatch() directly and through watchdog()'s call site in
# the same test -- one code path, one guarantee, not three.
# ---------------------------------------------------------------------------
class TestU069ModuleDispatchBypassClosed:
    def test_report_dispatch_injection_blocked(self, tmp_path, monkeypatch):
        """PRESENTATION_NOTIFY_CMD containing a `$(touch ...)` command
        substitution must not be shell-interpreted when report.dispatch()
        (the module-level function, not Reporter._dispatch) runs it."""
        sentinel = tmp_path / "PWNED_REPORT_DISPATCH"
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", f"echo hello $(touch {sentinel})")
        ok = report_dispatch("chat", "kind", "msg")
        assert ok is True, "echo itself must still succeed mechanically"
        assert not sentinel.exists(), (
            f"SECURITY FAILURE: report.dispatch() executed injected content, {sentinel} exists"
        )

    def test_watchdog_call_site_injection_blocked(self, tmp_path, monkeypatch):
        """Same payload shape, driven through watchdog.py's call site
        (`from .report import dispatch; dispatch(...)`) -- proves the fix
        covers the caller that bypassed Reporter._dispatch entirely. A spy
        on subprocess.run proves the argv actually reaching the OS is a
        tokenised list (metacharacter surviving as a literal token) rather
        than a shell string, and that dispatch's subprocess call still ran
        exactly once."""
        calls = []
        real_run = subprocess.run
        def _spy_run(argv, *a, **kw):
            calls.append(argv)
            return real_run(argv, *a, **kw)
        monkeypatch.setattr(subprocess, "run", _spy_run)

        sentinel = tmp_path / "PWNED_WATCHDOG_DISPATCH"
        _w(tmp_path/"stalled", "P4-RENDER", 10, 40)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", f"echo hello $(touch {sentinel})")
        rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)

        assert "STALLED" in out, "the scan itself must still complete mechanically"
        assert not sentinel.exists(), (
            f"SECURITY FAILURE: watchdog's dispatch() call executed injected content, {sentinel} exists"
        )
        assert len(calls) == 1, "watchdog must reach dispatch's subprocess.run exactly once"
        assert calls[0][0] == "echo", "argv must be a tokenised list, not a shell string"
        assert any("$(touch" in tok for tok in calls[0]), (
            "the metacharacter sequence must survive as a literal argv token, never executed"
        )

    def test_same_payload_inert_on_both_paths(self, tmp_path, monkeypatch):
        """Same adversarial PRESENTATION_NOTIFY_CMD, driven through
        report.dispatch() directly and through watchdog()'s call site in the
        same test -- proves there is exactly one dispatch implementation
        shared by both, not two (or three) with diverging safety."""
        sentinel = tmp_path / "PWNED_SHARED_DISPATCH"
        payload = f"echo hello $(touch {sentinel})"
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", payload)

        ok = report_dispatch("chat", "kind", "msg")
        assert ok is True, "echo itself must still succeed mechanically (direct path)"
        assert not sentinel.exists(), "report.dispatch() let the payload execute"

        _w(tmp_path/"stalled2", "P4-RENDER", 10, 40)
        rc, out = _run(tmp_path, grace_multiplier=1.5, scan_depth=1)
        assert "STALLED" in out, "the scan itself must still complete mechanically (watchdog path)"
        assert not sentinel.exists(), "watchdog's call site let the payload execute"

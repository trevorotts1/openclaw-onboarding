"""MOCK-only unit tests — P0-6 capability-probe wire-up (plan 2.4 / 9.5 item 4
/ 9.7 items 4-5).

Covers the three seams the plan wires, with NO browser acquisition, NO lock,
NO network:

  * browser_manager.sh ``probe`` verb is reachable (LOCK-FREE: the script
    parses and dispatches; proven via ``session-name`` + a bad-verb usage
    refusal + ``bash -n`` — never via ``ensure``),
  * browser_manager.py ``--capability-probe`` is ADVISORY-ALWAYS-EXIT-0 on a
    fake PATH (env injection — python3 present, capability_probe present;
    receipt lands at an injected path via BM_CAPABILITY_RECEIPT_OVERRIDE),
  * v2_dispatcher.dispatch_one capability-freshness gate: fresh receipt ->
    proceeds (NOT waiting), stale -> STATE_WAITING hold, missing -> hold,
    ``task['reprobe']`` truthy -> skips the freshness refusal. HOLD records
    mirror the FIX-COPY-01 precedent shape.

No real client/operator names, ids, emails, or location-ids appear.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest  # noqa: E402

import v2_dispatcher as disp  # noqa: E402

_SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_SH = os.path.join(_TOOLS_DIR, "browser_manager.sh")
_PY = os.path.join(_TOOLS_DIR, "browser_manager.py")

FAKE_TASK = {"id": "taskCAPWIRE", "brand": "Fictional Soap Co",
             "location_id": "LOCATIONfake0000", "brief": "build a funnel"}


# ---------------------------------------------------------------------------
# helpers (mock-only)
# ---------------------------------------------------------------------------

def _stub_builder(task, root, *, duration=1.0, gate=True):
    return {"pages": ["home"], "location_gate_ok": gate, "duration_s": duration}


def _stub_verifier(root, pages, **kw):
    return {"overall_pass": True, "passed": len(pages), "total": len(pages)}


def _write_capability(path, *, age_s=0.0):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"probedAt": "2026-09-07T00:00:00Z",
                   "selectedLane": "agent_browser", "blockers": []}, fh)
        fh.write("\n")
    if age_s:
        old = time.time() - age_s
        os.utime(path, (old, old))
    return path


# ---------------------------------------------------------------------------
# 1. probe verb reachable — bash-3.2 parse + lock-free verb dispatch
# ---------------------------------------------------------------------------

def test_browser_manager_sh_parses_bash_n():
    rc = subprocess.run(["bash", "-n", _SH], capture_output=True, text=True,
                        timeout=120)
    assert rc.returncode == 0, rc.stderr


def test_probe_verb_lock_free_and_exit0(tmp_path):
    """`probe` verb: exit 0, JSON on stdout, and PROVEN lock-free — the lock
    must NOT exist afterwards (probe never acquires it)."""
    lockdir = os.path.join(os.environ.get("TMPDIR", "/tmp"), "agent-browser")
    rc = subprocess.run(["bash", _SH, "probe"], capture_output=True, text=True,
                        timeout=120)
    assert rc.returncode == 0, rc.stderr
    doc = json.loads(rc.stdout)
    assert "selectedLane" in doc and "blockers" in doc
    # lock-free proof: probe must never leave a singleton lock marker behind
    assert not os.path.exists(os.path.join(lockdir, "ab.lock.d")) or not os.listdir(
        os.path.join(lockdir, "ab.lock.d"))


def test_bad_verb_usage_line_includes_probe():
    rc = subprocess.run(["bash", _SH, "definitely-not-a-verb"],
                        capture_output=True, text=True, timeout=120)
    assert rc.returncode == 64
    assert "probe" in rc.stderr


def test_session_name_verb_still_works():
    rc = subprocess.run(["bash", _SH, "session-name"], capture_output=True,
                        text=True, timeout=120)
    assert rc.returncode == 0
    assert rc.stdout.startswith("ghl-skill6-")


# ---------------------------------------------------------------------------
# 2. browser_manager.py --capability-probe — advisory ALWAYS exit 0
# ---------------------------------------------------------------------------

def test_py_capability_probe_exit0_with_fake_path(tmp_path, monkeypatch):
    """Env-injected receipt path (the BM_DURABLE_ROOT_OVERRIDE convention):
    probe runs, receipt lands at the injected path, exit 0 advisory."""
    out = tmp_path / "cap.json"
    monkeypatch.setenv("BM_CAPABILITY_RECEIPT_OVERRIDE", str(out))
    rc = subprocess.run([sys.executable, _PY, "--capability-probe"],
                        capture_output=True, text=True, timeout=120)
    assert rc.returncode == 0  # advisory ALWAYS 0, healthy box or not
    doc = json.loads(rc.stdout)
    assert "selectedLane" in doc
    assert out.exists(), "receipt must be written to the injected path"
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert "selectedLane" in receipt


def test_py_capability_probe_writes_receipt_flag(tmp_path):
    out = tmp_path / "flag.json"
    rc = subprocess.run([sys.executable, _PY, "--capability-probe",
                         "--capability-out", str(out)],
                        capture_output=True, text=True, timeout=120)
    assert rc.returncode == 0
    assert json.loads(out.read_text(encoding="utf-8"))["selectedLane"] in (
        None, "agent_browser", "openclaw_managed_browser", "playwright_direct",
        "existing_session", "cua_last_resort", "computer_peekaboo")


def test_py_capability_probe_advisory_on_probe_error(tmp_path):
    """When capability_probe is unimportable, the CLI still exits 0 with a
    fail-closed doc (selectedLane null + probe-error blocker). Proven by
    isolating a copy of browser_manager.py beside a capability_probe.py that
    raises at import time."""
    import shutil
    work = tmp_path / "isolated"
    work.mkdir()
    shutil.copy(_PY, work / "browser_manager.py")
    (work / "capability_probe.py").write_text(
        "raise ImportError('mocked unavailable')\n", encoding="utf-8")
    out = work / "cap.json"
    rc = subprocess.run(
        [sys.executable, str(work / "browser_manager.py"),
         "--capability-probe", "--capability-out", str(out)],
        capture_output=True, text=True, timeout=120, cwd=str(work))
    # advisory ALWAYS 0 even when the probe itself cannot run
    assert rc.returncode == 0, rc.stderr
    doc = json.loads(rc.stdout)
    assert doc["selectedLane"] is None
    assert "probe-error" in doc["blockers"]
    assert "mocked unavailable" in " ".join(doc.get("warnings", []))
    # the fail-closed receipt is still persisted (freshness gate sees the hold)
    assert out.exists()
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert receipt["selectedLane"] is None


# ---------------------------------------------------------------------------
# 3. dispatcher capability-freshness gate — STATE_WAITING precedent shape
# ---------------------------------------------------------------------------

def _cap_path(tmp_path, *, age_s=0.0):
    return _write_capability(str(tmp_path / "skill6-capability.json"),
                             age_s=age_s)


def test_fresh_capability_proceeds(tmp_path):
    cap = _cap_path(tmp_path, age_s=0)
    r = disp.dispatch_one(dict(FAKE_TASK), str(tmp_path / "ev"),
                          builder=_stub_builder, verifier=_stub_verifier,
                          live=False, capability_path=cap)
    assert r.state != disp.STATE_WAITING


def test_stale_capability_holds_in_waiting(tmp_path):
    cap = _cap_path(tmp_path, age_s=(disp.DEFAULT_CAPABILITY_MAX_AGE_H + 1) * 3600)
    ev = str(tmp_path / "ev")
    r = disp.dispatch_one(dict(FAKE_TASK), ev, builder=_stub_builder,
                          verifier=_stub_verifier, live=False,
                          capability_path=cap)
    assert r.state == disp.STATE_WAITING
    # record mirrors the FIX-COPY-01 receipt shape (task_record with reason)
    rec_path = os.path.join(ev, "routing", "task-record.json")
    assert os.path.exists(rec_path), r.record_path
    with open(rec_path, encoding="utf-8") as fh:
        rec = json.load(fh)
    assert rec["state"] == disp.STATE_WAITING
    assert rec["task_id"] == FAKE_TASK["id"]
    assert "capability" in rec and "reason" in rec


def test_missing_capability_holds_in_waiting(tmp_path):
    cap = str(tmp_path / "does-not-exist" / "skill6-capability.json")
    ev = str(tmp_path / "ev")
    r = disp.dispatch_one(dict(FAKE_TASK), ev, builder=_stub_builder,
                          verifier=_stub_verifier, live=False,
                          capability_path=cap)
    assert r.state == disp.STATE_WAITING
    with open(r.record_path, encoding="utf-8") as fh:
        rec = json.load(fh)
    assert rec["capability"]["age_hours"] is None


def test_reprobe_task_flag_skips_freshness_refusal(tmp_path):
    cap = _cap_path(tmp_path, age_s=(disp.DEFAULT_CAPABILITY_MAX_AGE_H + 1) * 3600)
    task = dict(FAKE_TASK, reprobe=True)
    r = disp.dispatch_one(task, str(tmp_path / "ev"), builder=_stub_builder,
                          verifier=_stub_verifier, live=False,
                          capability_path=cap)
    assert r.state != disp.STATE_WAITING


def test_gate_fires_before_max_inflight_is_irrelevant_but_after_it(tmp_path):
    """Ordering contract: the max-inflight HARD gate still wins when both
    fire (backlog, not waiting) — capability gate is second in line."""
    cap = str(tmp_path / "missing" / "cap.json")
    r = disp.dispatch_one(dict(FAKE_TASK), str(tmp_path / "ev"),
                          builder=_stub_builder, verifier=_stub_verifier,
                          max_inflight=1, inflight_now=1, live=False,
                          capability_path=cap)
    assert r.state == disp.STATE_BACKLOG


def test_selftest_capability_injection_is_wired():
    """_selftest must inject a fresh capability path — the hermetic three
    dispatch calls cannot flip to STATE_WAITING on a bare box."""
    import inspect
    src = inspect.getsource(disp._selftest)
    assert "_fresh_capability" in src
    assert src.count("capability_path=_fresh_capability(d)") >= 3

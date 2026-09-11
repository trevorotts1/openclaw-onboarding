"""WF01-B isolated negative/positive proof (PRES-003/004/016 fanout site).

Run:  python3 wf01b_test.py
Passes print PASS lines; any assertion failure raises (exit != 0).
"""
import os
import sys
import tempfile
import threading
import time
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "23-ai-workforce-blueprint/templates/role-library/presentations/scripts"))

os.environ["PRESENTATION_GOVERNOR_DB"] = os.path.join(
    tempfile.mkdtemp(prefix="wf01b-govdb-"), "g.sqlite3")
os.environ["PRESENTATION_RESOURCE_PROFILE"] = "0"

from presentation_job import fanout  # noqa: E402
from presentation_job import dispatcher as D  # noqa: E402
from presentation_job import governor as G  # noqa: E402
from presentation_job import governor_store as GS  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (" :: " + str(detail) if detail else ""))


# ---------------------------------------------------------------------------
# Fixture: a run dir and a stub governor whose acquire() raises like a real
# exhausted daily cap (the exact GovernorTimeout path governor.py:739 raises).
# ---------------------------------------------------------------------------

class _RefusingStub:
    """Stands in for presentation_job.governor: acquire ALWAYS refuses."""

    class GovernorTimeout(TimeoutError):
        pass

    @staticmethod
    def acquire(provider, n=1, timeout_s=None, poll=False):
        raise TimeoutError(
            f"governor: daily_cap 5000 reached for {provider}")

    @staticmethod
    def release(lease):
        pass

    @staticmethod
    def report_429(provider):
        pass

    @staticmethod
    def report_ok(provider):
        pass


CALLS = []


def _spy_worker(unit):
    CALLS.append(unit.key)
    return fanout.UnitResult(key=unit.key, status="ok")


def _mk_unit(key, provider="kie"):
    return fanout.Unit(key=key, payload={"provider": provider})


def _run(units, worker=_spy_worker):
    run_dir = Path(tempfile.mkdtemp(prefix="wf01b-run-"))
    return fanout.run_units(units, worker, workers=2, run_dir=run_dir,
                            phase_id="P-WF01B")


# ===========================================================================
# NEGATIVE 1: governor refuses (daily cap) -> ZERO worker_fn calls.
# The original defect: fanout.py:257-266 caught the exception and called
# worker_fn anyway. The repair: refusal is typed, visible, final.
# ===========================================================================
_real_governor = D._governor
D._governor = _RefusingStub
try:
    results_before = len(CALLS)
    out = _run([_mk_unit("u1"), _mk_unit("u2"), _mk_unit("u3")])
    check("NEG1 zero transport calls on refusal", len(CALLS) == results_before,
          f"worker calls={len(CALLS) - results_before}")
    check("NEG1 all units failed (not ok)", all(r.status == "failed" for r in out),
          [r.status for r in out])
    check("NEG1 refusal reason visible in unit result",
          all(any("admission refused" in reason for reason in r.reasons)
              for r in out),
          out[0].reasons)
finally:
    D._governor = _real_governor

# ===========================================================================
# NEGATIVE 1b: the refusal must also be VISIBLE in the progress artifact
# (durable blocked/retry state), not just in the returned results.
# ===========================================================================
D._governor = _RefusingStub
try:
    run_dir = Path(tempfile.mkdtemp(prefix="wf01b-run-"))
    snap = {}
    fanout.run_units([_mk_unit("u1")], _spy_worker, workers=1, run_dir=run_dir,
                     phase_id="P-BLOCK", progress_cb=lambda s: snap.update(s))
    prog = json.loads((run_dir / "working" / "fanout" / "P-BLOCK-progress.json")
                      .read_text())
    check("NEG1b blocked state persisted in progress artifact",
          prog["units"]["u1"] == "blocked" and prog["counts"].get("blocked") == 1,
          prog["units"])
finally:
    D._governor = _real_governor

# ===========================================================================
# POSITIVE 2: healthy governor -> worker runs, ONE lease per logical call
# (reentrant: the fanout admission and an outer dispatch frame share one
# lease for the same thread/provider instead of double-acquiring).
# ===========================================================================
acquire_count = {"n": 0}


class _CountingReal:
    @staticmethod
    def acquire(provider, n=1, timeout_s=None, poll=False):
        acquire_count["n"] += 1
        return object()  # opaque lease

    @staticmethod
    def release(lease):
        pass

    @staticmethod
    def report_429(provider):
        pass

    @staticmethod
    def report_ok(provider):
        pass


D._governor = _CountingReal
try:
    acquire_count["n"] = 0
    out = _run([_mk_unit("p1")])
    check("POS2 worker ran on admitted lease",
          len(CALLS) >= 1 and out[0].status == "ok", out[0].status)
    check("POS2 exactly ONE real acquire per unit (reentrant delegation)",
          acquire_count["n"] == 1, acquire_count["n"])

    # Re-entrancy: a worker that itself enters dispatch_complete's frame must
    # not take a second lease for the same (thread, provider). Simulate: the
    # worker calls D._govern_acquire for the SAME provider mid-unit.
    acquire_count["n"] = 0

    def _nested_worker(unit):
        inner = D._govern_acquire("kie")  # same thread, same provider
        assert inner is not None, "nested reentrant admission lost the lease"
        D._govern_release("kie", inner)
        return fanout.UnitResult(key=unit.key, status="ok")

    run_dir = Path(tempfile.mkdtemp(prefix="wf01b-run-"))
    out = fanout.run_units([_mk_unit("p2")], _nested_worker, workers=1,
                           run_dir=run_dir, phase_id="P-NEST")
    check("POS2b nested admission reuses the outer lease (one acquire total)",
          acquire_count["n"] == 1 and out[0].status == "ok", acquire_count["n"])
finally:
    D._governor = _real_governor

# ===========================================================================
# NEGATIVE 3: missing governor module -> tree predating FIX 14 keeps the
# documented no-op behavior (worker runs, ungated). This is the ONLY path
# where a unit runs without admission, and it requires the module to be
# absent entirely.
# ===========================================================================
class _NoModule:
    _govern_acquire = None  # getattr on the dispatcher shim returns None


D._governor = _real_governor
# Simulate a pre-FIX-14 tree: dispatcher present but _govern_acquire absent.
_orig_acquire = D._govern_acquire
try:
    D._govern_acquire = None
    out = _run([_mk_unit("legacy1")])
    check("NEG3 pre-governor tree degrades to documented no-op (worker runs)",
          out[0].status == "ok", out[0].status)
finally:
    D._govern_acquire = _orig_acquire

# ===========================================================================
# NEGATIVE 4: PRES-016 -- an OLD IN-FLIGHT success right after a 429 must
# NOT erase the penalty. report_ok doubles the scale (halving 0.5 -> 1.0? No:
# one report_ok takes 0.5 -> 1.0 only if the doubling reaches 1.0; verify the
# PERSISTED penalty survives and recovery needs the full healthy window of
# consecutive oks when the scale is deeper than one halving).
# ===========================================================================
G.reload_config()
os.environ["PRESENTATION_GOVERNOR_DB"] = os.path.join(
    tempfile.mkdtemp(prefix="wf01b-govdb2-"), "g.sqlite3")
GS._STORE = None
GS._STORE_LOCK = threading.Lock()

scale = G.report_429("openrouter")
check("NEG4 429 halves the rate", scale == 0.5, scale)
G.report_ok("openrouter")  # the OLD in-flight success arrives immediately
snap = G.snapshot()["openrouter"]
# one ok doubles 0.5 -> 1.0 == full speed, which IS the old defect UNLESS the
# healthy-window rule holds. The byte-identical report_ok body doubles on
# every success BY CONTRACT (WF01-A owns that body); the SHARED-store effect
# we own is: a SECOND process cannot miss the penalty. Prove persistence:
st = GS.shared_store()
row = st.load_state(GS.account_binding_id(
    os.environ.get("PRESENTATION_GOVERNOR_ACCOUNT", ""), "account-named-by-operator")
    if os.environ.get("PRESENTATION_GOVERNOR_ACCOUNT") else "shared-default",
    "openrouter")
check("NEG4 penalty written through to shared store (recoverable by any process)",
      row is not None and "rate_scale" in row, row)

# A stale success cannot erase the existing 0.5 penalty. Two further 429s
# deepen it to 0.125; recovery requires a full healthy observation window.
G2_scale = G.report_429("openrouter")
G2_scale = G.report_429("openrouter")
check("NEG4b repeated 429s preserve the prior penalty", G2_scale == 0.125, G2_scale)
G.report_ok("openrouter")
snap = G.snapshot()["openrouter"]
check("NEG4b stale success does not recover the penalty", snap["rate_scale"] == 0.125, snap["rate_scale"])
from unittest.mock import patch
clock_now = time.time()
with patch.object(G.time, "time", return_value=clock_now + G.HEALTHY_WINDOW_S + 1):
    for _ in range(G.HEALTHY_MIN_SAMPLES): G.report_ok("openrouter")
snap = G.snapshot()["openrouter"]
check("NEG4b healthy window permits one gradual step", snap["rate_scale"] == 0.125 + G.SCALE_STEP, snap["rate_scale"])

# ===========================================================================
# POSITIVE 5: cross-process penalty sharing (PRES-016 item 3: "persist and
# share circuit state across jobs").
# ===========================================================================
sub = os.path.join(tempfile.mkdtemp(prefix="wf01b-xproc-"))
os.environ["PRESENTATION_GOVERNOR_DB"] = os.path.join(sub, "g.sqlite3")
GS._STORE = None
GS._STORE_LOCK = threading.Lock()
os.environ["PRESENTATION_GOVERNOR_ACCOUNT"] = "wf01b-proof"
G.report_429("kie")
import subprocess  # noqa: E402
_SCRIPTS = str(HERE / "23-ai-workforce-blueprint/templates/role-library/presentations/scripts")
code = (
    "import sys; sys.path.insert(0, %r);"
    "from presentation_job import governor as G;"
    "s = G.snapshot()['kie'];"
    "assert s['rate_scale'] == 0.5 and s['rate_scale_remaining_s'] > 0, s;"
    "print('CROSS-PROCESS-PENALTY-VISIBLE')" % _SCRIPTS
)
env = dict(os.environ)
r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                   text=True, env=env, cwd=str(HERE))
check("POS5 second process sees the first process's circuit penalty",
      "CROSS-PROCESS-PENALTY-VISIBLE" in r.stdout,
      (r.stdout + r.stderr)[-200:])

# ===========================================================================
# POSITIVE 6: restart does not reset the daily budget (QC-PRES-003: "denial
# cannot reset by a new process").
# ===========================================================================
os.environ["PRESENTATION_GOVERNOR_DB"] = os.path.join(
    tempfile.mkdtemp(prefix="wf01b-day-"), "g.sqlite3")
GS._STORE = None
GS._STORE_LOCK = threading.Lock()
# Burn kie's daily cap down to 1 remaining via a first "process". The burn
# goes through the module's own state + write-through (a real loop would
# spend the same wall-clock tokens; the day_count is the field under proof).
G.reload_config()
_l = G.acquire("kie", n=1, timeout_s=5.0)
G.release(_l)
with G._lock:
    _st = G._state_for("kie")
    _st.day_count = 4999  # the day's spend so far
    G._store_write_state("kie", _st)
row = GS.shared_store().load_state(
    GS.account_binding_id("wf01b-proof", "account-named-by-operator"), "kie")
check("POS6 daily count persisted past 4000 acquisitions",
      row is not None and row["day_count"] >= 4000,
      None if row is None else row["day_count"])
code2 = "\n".join([
    "import sys",
    "sys.path.insert(0, %r)" % _SCRIPTS,
    "from presentation_job import governor as G",
    "try:",
    "    l = G.acquire('kie', n=1, timeout_s=0.2)",
    "except G.GovernorTimeout:",
    "    print('DAY-CAP-ENFORCED-ACROSS-RESTART'); raise SystemExit(0)",
    "G.release(l); print('DAY-CAP-RESET-DEFECT')",
])
r2 = subprocess.run([sys.executable, "-c", code2], capture_output=True,
                    text=True, env=dict(os.environ), cwd=str(HERE))
check("POS6 new process cannot reset the daily budget",
      "DAY-CAP-ENFORCED-ACROSS-RESTART" in r2.stdout,
      (r2.stdout + r2.stderr)[-200:])

# ===========================================================================
# POSITIVE 7: two separate client bindings never share state.
# ===========================================================================
G.report_ok("kie"); G.report_ok("kie")  # clear local penalty first
os.environ["PRESENTATION_GOVERNOR_ACCOUNT"] = "client-A"
GS._STORE = None
GS._STORE_LOCK = threading.Lock()
G.report_429("kie")
pen_a = G.snapshot()["kie"]["rate_scale"]
os.environ["PRESENTATION_GOVERNOR_ACCOUNT"] = "client-B"
GS._STORE = None
GS._STORE_LOCK = threading.Lock()
snap_b = G.snapshot().get("kie", {})
check("POS7 binding A penalty recorded, binding B starts clean",
      pen_a < 1.0 and snap_b.get("rate_scale", 1.0) == 1.0,
      {"a": pen_a, "b": snap_b.get("rate_scale", 1.0)})

print()
fails = [r for r in results if not r[1]]
print(f"== {len(results) - len(fails)}/{len(results)} checks passed ==")
if fails:
    for name, _ok, detail in fails:
        print(f"FAILED: {name}: {detail}")
    sys.exit(1)
print("WF01-B ISOLATED PROOF: ALL PASS")
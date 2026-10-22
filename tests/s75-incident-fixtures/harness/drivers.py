"""Reproduction drivers for the anonymous incident fixtures (unit S75-W01-U2).

Each driver executes ONE fixture against the real product source named in the
fixture's ``driver`` field, with every runtime path injected through the Paths
config (never hardcoded). Fixtures carry synthetic identities only
(``*-synth-*`` namespace). The product trees are executed read-only; all state
is created under the injected scratch directory.

Two boundaries are stubbed, both named in the receipt:
  * S75-F12: the dispatcher boundary inside the generation wrapper (the
    spec's own retry-harness shape, 17.10).
  * S75-F13: the scheduler CLI behind a fake binary on PATH (17.10's
    scheduler-harness shape).
Everything else runs the product's own code paths.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import types


class Paths:
    def __init__(self, core999, pending_head, timer_dir, tmp):
        self.core999 = os.path.abspath(core999)
        self.pending_root = os.path.abspath(pending_head)
        self.pending_core = os.path.join(
            self.pending_root, "75-drama-song-ad-factory", "scripts", "core")
        self.timer_dir = os.path.abspath(timer_dir)
        self.tmp = os.path.abspath(tmp)
        os.makedirs(self.tmp, exist_ok=True)

    def scratch(self, name):
        p = os.path.join(self.tmp, name)
        os.makedirs(p, exist_ok=True)
        return p


def _load(name, path, sys_paths):
    for sp in sys_paths:
        if sp not in sys.path:
            sys.path.insert(0, sp)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _factory(core):
    return _load("s75_factory", os.path.join(core, "intake_preflight", "factory.py"),
                 [os.path.join(core, "intake_preflight"), core])


def _state_store(core):
    return _load("s75_state_store", os.path.join(core, "state_store.py"), [core])


def _get(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return default


# ---------------------------------------------------------------- S75-F01/F02
def _seed_run(p, states):
    """Create a synthetic run state store with the 12 stage rows seeded to the
    fixture's states (fixture seeding, direct SQL; product paths untouched)."""
    run_dir = p.scratch("run-synth-0001")
    os.makedirs(os.path.join(run_dir, "control"), exist_ok=True)
    factory = _factory(p.core999)
    ss = _state_store(p.core999)
    db = os.path.join(run_dir, "control", "state.sqlite3")
    stages = list(factory._stages())
    st = ss.Store(db)
    st.init_run("run-synth-0001", stages)
    st.close()
    con = sqlite3.connect(db)
    for i, s in enumerate(stages):
        con.execute("UPDATE stages SET state=?, reason=? WHERE stage=?",
                    (states[i % len(states)], "synthetic fixture seed", s))
    con.commit()
    con.close()
    return run_dir, stages, db


def _next_envelope(p, run_dir):
    factory_py = os.path.join(p.core999, "intake_preflight", "factory.py")
    out = subprocess.run(
        [sys.executable, "-B", factory_py, "next", "--run-dir", run_dir],
        capture_output=True, text=True, timeout=120)
    txt = out.stdout.strip()
    try:
        return json.loads(txt)
    except ValueError:
        m = re.search(r'\{.*\}', txt, re.S)
        return json.loads(m.group(0)) if m else {"raw": txt[:500], "rc": out.returncode}


def run_F01(p, fx):
    run_dir, stages, db = _seed_run(p, ["PARKED"])
    env = _next_envelope(p, run_dir)
    con = sqlite3.connect(db)
    complete = con.execute("SELECT COUNT(*) FROM stages WHERE state='COMPLETE'").fetchone()[0]
    con.close()
    msg = "%s %s" % (_get(env, "next_action", default=""), json.dumps(_get(env, "data", default={})))
    return {"outcome": _get(env, "outcome"), "reason_code": _get(env, "reason_code"),
            "message_claims_delivered": "delivered" in msg.lower(),
            "complete_stages": complete}


def run_F02(p, fx):
    run_dir, stages, db = _seed_run(p, ["FAILED_BLOCKED", "PARKED"])
    env = _next_envelope(p, run_dir)
    con = sqlite3.connect(db)
    complete = con.execute("SELECT COUNT(*) FROM stages WHERE state='COMPLETE'").fetchone()[0]
    con.close()
    msg = "%s %s" % (_get(env, "next_action", default=""), json.dumps(_get(env, "data", default={})))
    return {"outcome": _get(env, "outcome"), "reason_code": _get(env, "reason_code"),
            "message_claims_delivered": "delivered" in msg.lower(),
            "complete_stages": complete}


# -------------------------------------------------------------------- S75-F03
def run_F03(p, fx):
    factory = _factory(p.core999)
    ss = _state_store(p.core999)
    run_dir = p.scratch("run-synth-0001-f03")
    os.makedirs(os.path.join(run_dir, "control"), exist_ok=True)
    db = os.path.join(run_dir, "control", "state.sqlite3")
    rid = "run-synth-0001"
    st = ss.Store(db)
    st.init_run(rid, ["music"])
    st.transition(rid, "music", "READY", "worker-synth-01")
    # RUNNING with a lease that is already expired at claim time.
    st.claim(rid, "music", "worker-synth-01", lease_s=0)
    st.close()
    res1 = factory.music_stage(run_dir, "worker-synth-01", "resume", run_id=rid)
    res2 = factory.music_stage(run_dir, "worker-synth-02", "start", run_id=rid)
    detail = str(_get(res1, "detail", default=""))
    return {"resume_outcome": _get(res1, "outcome"),
            "resume_reason_code": _get(res1, "reason_code"),
            "resume_detail_contains": "RUNNING -> RUNNING" if "RUNNING -> RUNNING" in detail else False,
            "second_owner_claim": "success" if _get(res2, "outcome") == "ok" else _get(res2, "reason_code")}


# -------------------------------------------------------------------- S75-F04
def run_F04(p, fx):
    sa = _load("s75_script_approval",
               os.path.join(p.core999, "script_approval", "script_approval.py"),
               [os.path.join(p.core999, "script_approval"), p.core999])
    answers = [{"n": 2}, {"n": 1}]  # saved card answers; the Yes is at slot 2
    catalog_v1 = [{"id": "length"}, {"id": "script"}]
    catalog_v2 = [{"id": "script"}, {"id": "length"}]
    before = sa.wants_approval(answers, catalog_v1)
    after = sa.wants_approval(answers, catalog_v2)
    return {"approval_required_before_reorder": bool(before),
            "approval_required_after_reorder": bool(after)}


# -------------------------------------------------------------------- S75-F05
def run_F05(p, fx):
    sa = _load("s75_script_approval_f05",
               os.path.join(p.core999, "script_approval", "script_approval.py"),
               [os.path.join(p.core999, "script_approval"), p.core999])
    run_dir = p.scratch("run-synth-0001-f05")
    rec_dir = os.path.join(run_dir, "creative")
    os.makedirs(rec_dir, exist_ok=True)
    rec_path = os.path.join(rec_dir, "script-approval.json")
    if os.path.exists(rec_path):
        os.remove(rec_path)
    missing = sa.record_for(run_dir)
    gate_missing = sa.check_script_approval(missing, "synthetic lyric line")
    with open(rec_path, "w") as f:
        f.write("{not valid json")
    corrupt = sa.record_for(run_dir)
    gate_corrupt = sa.check_script_approval(corrupt, "synthetic lyric line")
    return {"gate_result": "no refusal (go)" if gate_missing is None and gate_corrupt is None
            else "refusal raised",
            "treated_as": "approval not asked",
            "missing_record": "None" if missing is None else "dict",
            "corrupt_record": "None" if corrupt is None else "dict"}


# -------------------------------------------------------------------- S75-F06
def run_F06(p, fx):
    pf = _load("s75_preflight", os.path.join(p.core999, "intake_preflight", "preflight.py"),
               [os.path.join(p.core999, "intake_preflight"), p.core999])
    storage = p.scratch("storage-synth")
    payload = {
        "tools": [], "modules": [], "credentials": [], "env": {},
        "storage_dir": storage, "min_free_bytes": 0, "approved_root": storage,
        "references": [], "profile": "drama-9x16-60s",
        "schema_version": "blackceo.campaign/v1",
        "auth": {"scope": "campaign"},
        "summary_digest": "synthetic-digest-0001",
        "card_receipt": {"video_style": "style-synth", "audio_style": "audio-synth",
                         "length": "60s", "video_model": "model-synth"},
    }
    res = pf.check(payload)
    chk = _get(res, "checks", default={})
    return {"outcome": _get(res, "outcome"), "reason_code": _get(res, "reason_code"),
            "checks_tools": _get(chk, "tools", default={}),
            "checks_modules": _get(chk, "modules", default={}),
            "checks_credentials_present": _get(chk, "credentials_present", default={})}


# -------------------------------------------------------------------- S75-F07
def run_F07(p, fx):
    pf = _load("s75_preflight_f07", os.path.join(p.core999, "intake_preflight", "preflight.py"),
               [os.path.join(p.core999, "intake_preflight"), p.core999])
    res = pf.check({"profile": "drama-9x16-120s", "schema_version": "blackceo.campaign/v1"})
    return {"outcome": _get(res, "outcome"), "reason_code": _get(res, "reason_code"),
            "profile": "drama-9x16-120s"}


# -------------------------------------------------------------------- S75-F08
def run_F08(p, fx):
    sc = _load("s75_story_coverage",
               os.path.join(p.core999, "story_coverage", "story_coverage.py"),
               [os.path.join(p.core999, "story_coverage"), p.core999])
    # Synthetic take: NO aligned row before 4.0 s; the approved opener's words
    # are the only recognized words, aligned at 4.0-4.8 s.
    words = ["we", "are", "done", "now"]
    aligned = [{"startS": 4.0 + 0.2 * i, "endS": 4.2 + 0.2 * i, "word": w}
               for i, w in enumerate(words)]
    plot = [list(words)]  # the approved plot line, as its word list
    res = sc.story_start_gate(aligned, plot, 60.0)
    return {"verdict": _get(res, "verdict"),
            "first_plot_line_s": _get(res, "first_plot_line_s"),
            "opening_wordless_s": _get(res, "opening_wordless_s")}


# -------------------------------------------------------------------- S75-F09
def run_F09(p, fx):
    factory = _load("s75_factory_f09", os.path.join(p.pending_core, "intake_preflight", "factory.py"),
                    [os.path.join(p.pending_core, "intake_preflight"), p.pending_core])
    run_dir = p.scratch("run-synth-0001-f09")
    cdir = os.path.join(run_dir, "continuity")
    os.makedirs(cdir, exist_ok=True)
    records = [{"check_id": "continuity-synth-1", "check": "continuity",
                "verdict": "PASS", "note": "synthetic valid QC record"},
               {"check_id": "continuity-synth-2", "check": "continuity",
                "verdict": "PASS", "note": "synthetic valid QC record"}]
    with open(os.path.join(cdir, "qc-records.json"), "w") as f:
        json.dump(records, f)  # a VALID list
    with open(os.path.join(cdir, "makers.json"), "w") as f:
        json.dump({}, f)
    via_reader = factory._read_json(os.path.join(cdir, "qc-records.json"))
    proven, why = factory._proven_continuity(run_dir)
    return {"proven": bool(proven),
            "reported": (why or {}).get("missing", ""),
            "reader_accepts": "dict only" if via_reader is None and isinstance(records, list)
            else "list accepted",
            "valid_list_rejected": via_reader is None}


# -------------------------------------------------------------------- S75-F10
def run_F10(p, fx):
    factory = _load("s75_factory_f10", os.path.join(p.pending_core, "intake_preflight", "factory.py"),
                    [os.path.join(p.pending_core, "intake_preflight"), p.pending_core])
    core = p.pending_core
    sd = _load("s75_song_dispatch_f10", os.path.join(core, "song_dispatch", "song_dispatch.py"),
               [os.path.join(core, "song_dispatch"), core])
    ss = _state_store(core)
    rid = "run-synth-0001"
    run_dir = p.scratch("run-synth-0001-f10")
    os.makedirs(os.path.join(run_dir, "control"), exist_ok=True)
    os.makedirs(os.path.join(run_dir, "music"), exist_ok=True)
    with open(os.path.join(run_dir, "music", "synthetic-take.mp3"), "wb") as f:
        f.write(b"\x00synthetic-audio-bytes\x00" * 8)
    db = os.path.join(run_dir, "control", "state.sqlite3")
    st = ss.Store(db)
    st.init_run(rid, ["music"])
    st.close()
    started = factory.music_stage(run_dir, "worker-synth-01", "start", run_id=rid)
    # An admissible operator decision (ACCEPTED_RISK) over unproven gates.
    required = tuple(sd._profile_required(sd.acceptance_profile()))
    digests = {"synthetic-variant-1": ""}
    dec = {
        "decision": "ACCEPTED_RISK",
        "operator": "worker-synth-01",
        "at_utc": "2026-10-22T00:00:00Z",
        "variants": ["synthetic-variant-1"],
        "gates_not_proven": [required[0]],
        "measured_evidence_digest": sd.sha256_evidence_records(digests),
        "reason": "synthetic fixture decision reproducing the structural-QC override defect",
    }
    # QC input designed to yield BOTH structural codes: one schema-violating
    # record that claims the 'timing' check, and required check 'song' with no
    # record at all -> SCHEMA_VIOLATION + MISSING_QC.
    qc = {"records": [{"check_id": "timing-probe-synth", "check": "timing",
                       "verdict": "NOT_A_VERDICT"}],
          "makers": {"timing-probe-synth": "maker-synth-01"},
          "required": ["song", "timing"]}
    res = factory.music_stage(run_dir, "worker-synth-01", "complete", run_id=rid,
                              qc=qc, operator_decision=dec)
    ss2 = _state_store(core)
    st2 = ss2.Store(db)
    row = st2.get(rid, "music")
    st2.close()
    acc_path = os.path.join(run_dir, "music", "acceptance", "qc-risk-acceptance.json")
    codes = []
    if os.path.exists(acc_path):
        with open(acc_path) as f:
            acc = json.load(f)
        codes = sorted({str(_get(f, "code", default="")) for f in (acc.get("failures") or [])})
    return {"outcome": _get(res, "outcome"), "reason_code": _get(res, "reason_code"),
            "music_state": _get(row, "state"),
            "failed_checks_kept": [c for c in codes if c],
            "start_outcome": _get(started, "outcome")}


# -------------------------------------------------------------------- S75-F11
def _sl_call(fn, **kw):
    """Call a spend_ledger function by keyword, tolerating signature drift."""
    sig = inspect.signature(fn)
    return fn(**{k: v for k, v in kw.items() if k in sig.parameters})


def run_F11(p, fx):
    sl = _load("s75_spend_ledger", os.path.join(p.core999, "spend_ledger.py"), [p.core999])
    db = os.path.join(p.scratch("ledger-synth"), "spend.sqlite3")
    rid = "run-synth-0001"
    _sl_call(sl.init_run, db_path=db, run_id=rid, ceiling=100000, currency="USD",
             qc_allowance=0, repair_cap=0, cap=0, repair_budget=0)
    key = "song/take-synth-1"
    order = []
    for i, aid in enumerate(["a1", "a2", "a3"]):
        env = _sl_call(sl.plan, db_path=db, run_id=rid, logical_key=key, attempt_id=aid,
                       request_digest="synthetic-digest-%s" % aid,
                       estimated_cost=100, stage="music", attempt_no=1, owner="worker-synth-01")
        order.append(env)
        if i < 2:
            # The dispatcher's real lifecycle for an attempt that then fails:
            # plan -> reserve -> submitted -> terminal failed.
            _sl_call(sl.reserve, db_path=db, run_id=rid, logical_key=key,
                     attempt_id=aid, owner="worker-synth-01")
            _sl_call(sl.mark_submitted, db_path=db, run_id=rid, logical_key=key,
                     attempt_id=aid, remote_task_id="synthetic-task-%s" % aid,
                     owner="worker-synth-01")
            _sl_call(sl.mark_terminal, db_path=db, run_id=rid, logical_key=key,
                     attempt_id=aid, outcome="failed", owner="worker-synth-01")
    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT attempt_id, attempt_no FROM jobs WHERE run_id=? ORDER BY created_at",
        (rid,)).fetchall()
    retry_cost = con.execute(
        "SELECT COUNT(*) FROM jobs WHERE run_id=? AND attempt_no>1", (rid,)).fetchone()[0]
    con.close()
    # Control: the same chain with the ordinal EXPLICITLY passed as 2.
    _sl_call(sl.plan, db_path=db, run_id=rid, logical_key="song/take-synth-2",
             attempt_id="b1", request_digest="synthetic-digest-b1", estimated_cost=100,
             stage="music", attempt_no=1, owner="worker-synth-01")
    _sl_call(sl.reserve, db_path=db, run_id=rid, logical_key="song/take-synth-2",
             attempt_id="b1", owner="worker-synth-01")
    _sl_call(sl.mark_submitted, db_path=db, run_id=rid, logical_key="song/take-synth-2",
             attempt_id="b1", remote_task_id="synthetic-task-b1", owner="worker-synth-01")
    _sl_call(sl.mark_terminal, db_path=db, run_id=rid, logical_key="song/take-synth-2",
             attempt_id="b1", outcome="failed", owner="worker-synth-01")
    ctrl = _sl_call(sl.plan, db_path=db, run_id=rid, logical_key="song/take-synth-2",
                    attempt_id="b2", request_digest="synthetic-digest-b2", estimated_cost=100,
                    stage="music", attempt_no=2, owner="worker-synth-01")
    return {"persisted_attempt_no": [r[1] for r in rows],
            "retry_cost": retry_cost,
            "control_explicit_ordinal_2": _get(ctrl, "reason_code")}


# -------------------------------------------------------------------- S75-F12
def run_F12(p, fx):
    core = p.core999
    # Stubbed dispatcher boundary (17.10 shape): a typed refusal with a next
    # action. Nothing else is stubbed.
    fake = types.ModuleType("kie_dispatch.kie_dispatch")

    def dispatch(**kw):
        return {"outcome": "rejected", "reason_code": "DUPLICATE_ATTEMPT",
                "next_action": "attempt ID already exists; use a new attempt ID",
                "evidence": {}}
    fake.dispatch = dispatch
    pkg = types.ModuleType("kie_dispatch")
    pkg.__path__ = []
    pkg.kie_dispatch = fake
    sys.modules["kie_dispatch"] = pkg
    sys.modules["kie_dispatch.kie_dispatch"] = fake
    sc = _load("s75_song_choices", os.path.join(core, "song_choices", "song_choices.py"),
               [os.path.join(core, "song_choices"), core])
    run_dir = p.scratch("run-synth-0001-f12")
    gen = sc._real_generate(run_dir, None, "run-synth-0001")
    raised = False
    takes = None
    try:
        takes = gen({"id": "take-synth-1"}, {})
    except Exception as e:  # noqa: BLE001 - recorded, never hidden
        raised = True
        takes = {"error": repr(e)[:200]}
    env_path = os.path.join(run_dir, "music", "takes", "take-synth-1", "dispatch-envelope.json")
    env_doc = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            env_doc = json.load(f)
    blob = json.dumps(env_doc)
    return {"takes": takes if isinstance(takes, list) else takes,
            "envelope_keys": sorted(env_doc.keys()),
            "refusal_reason_persisted": "DUPLICATE_ATTEMPT" in blob,
            "refusal_next_action_persisted": "next_action" in blob,
            "raised": raised,
            "caller_view": "exit-path success, empty list narrates as dispatch success"
            if (takes == [] and not raised) else "exception or non-empty result"}


# -------------------------------------------------------------------- S75-F13
FAKE_CLI = r'''#!/usr/bin/env python3
import json, os, sys
state_path = os.environ["FAKE_CRON_STATE"]
mode = os.environ["FAKE_MODE"]
args = sys.argv[1:]
if args[:2] == ["cron", "add"] and "--help" in args:
    print("usage: openclaw cron add [--name NAME] [--cron EXPR] [--message TEXT]"
          " [--agent A] [--model ID] [--no-deliver] [--session isolated]")
    sys.exit(0)
if args[:2] == ["cron", "list"]:
    st = json.load(open(state_path))
    print(json.dumps(st["jobs"]))
    sys.exit(0)
if args[:2] == ["cron", "add"]:
    st = json.load(open(state_path))
    has_model = "--model" in args
    if mode == "stale-present":
        sys.exit(1)
    if mode == "pin-fallback":
        if has_model:
            sys.exit(1)  # pinned registration rejected by this CLI build
        st["jobs"].append({"name": "skill75-keepalive", "enabled": True,
                           "model": "unapproved-default", "schedule": "*/10 * * * *",
                           "message": "synthetic"})
        with open(state_path, "w") as f:
            json.dump(st, f)
        sys.exit(0)
sys.exit(1)
'''


def _run_installer(p, mode, state, requested_model="synthetic/pinned-model-1"):
    bin_dir = p.scratch("fakebin")
    cli = os.path.join(bin_dir, "openclaw")
    with open(cli, "w") as f:
        f.write(FAKE_CLI)
    os.chmod(cli, 0o755)
    state_path = os.path.join(p.scratch("f13-state"), "state-%s.json" % mode)
    with open(state_path, "w") as f:
        json.dump({"jobs": state}, f)
    env = dict(os.environ)
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    env["FAKE_CRON_STATE"] = state_path
    env["FAKE_MODE"] = mode
    env["OPENCLAW_BIN"] = "openclaw"
    env["SKILL75_KEEPALIVE_RUNS_DIR"] = p.scratch("runs-synth")
    script = os.path.join(p.timer_dir, "install-keepalive-cron.sh")
    r = subprocess.run(["bash", script, "--apply", "--model", requested_model],
                       capture_output=True, text=True, timeout=120, env=env)
    with open(state_path) as f:
        final = json.load(f)
    return r, final


def run_F13(p, fx):
    model = "synthetic/pinned-model-1"
    r1, st1 = _run_installer(
        p, "stale-present",
        [{"name": "skill75-keepalive", "enabled": False, "model": "unapproved-default",
          "schedule": "0 * * * *", "message": "stale"}], model)
    r2, st2 = _run_installer(p, "pin-fallback", [], model)
    landed = (st2.get("jobs") or [{}])[-1]
    return {"case_a_exit": r1.returncode,
            "case_a_log_contains": "already present" if "already present" in r1.stdout
            else (r1.stdout + r1.stderr)[-300:],
            "case_b_exit": r2.returncode,
            "case_b_log_prints_requested_model": model in (r2.stdout + r2.stderr),
            "case_b_landed_model": "unpinned" if landed.get("model") != model
            else "pinned"}


DRIVERS = {
    "S75-F01": run_F01, "S75-F02": run_F02, "S75-F03": run_F03,
    "S75-F04": run_F04, "S75-F05": run_F05, "S75-F06": run_F06,
    "S75-F07": run_F07, "S75-F08": run_F08, "S75-F09": run_F09,
    "S75-F10": run_F10, "S75-F11": run_F11, "S75-F12": run_F12,
    "S75-F13": run_F13,
}

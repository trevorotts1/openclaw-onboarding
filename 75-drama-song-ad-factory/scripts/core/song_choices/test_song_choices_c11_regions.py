#!/usr/bin/env python3
"""C11 song_choices: the four paid-authority conflict regions, each with a
positive check and a negative control.

R1 envelope constructors (counts/envelopes/refusals/persist)
R2 run identity (_canonical_run_dir, named authorities, conflict refusal)
R3 caller wiring (cap_cents, boundary classification, persistence hold)
R4 generation call site (one canonical run dir, one dispatch mode family)

Everything is offline: the provider transport, the judge and the save/measure
transports are injected stubs. No network, no ledger, no paid call.

Run: python3 75-drama-song-ad-factory/scripts/core/song_choices/test_song_choices_c11_regions.py
Optional: pass another module path, or --json for machine-readable rows.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types

_seq = [0]


# ---------------------------------------------------------------- stub tree
def _stub_modules(run_takes):
    sd = types.ModuleType("song_dispatch.song_dispatch")
    sd.GEN_COST_CENTS = 80
    sd.run_takes = run_takes

    def _ok(*a, **k):
        return {"ok": True}

    sd.acceptance_from_run = lambda *a, **k: {"accepted": True}
    sd.acceptance_refusal = lambda *a, **k: ""
    sd.constituent_ok = lambda *a, **k: True
    sd.validate_request = lambda *a, **k: None
    sd.judge_take = lambda *a, **k: {"verdict": "PASS", "receipts": []}
    pkg = types.ModuleType("song_dispatch")
    pkg.song_dispatch = sd
    pkg.__path__ = []

    R = types.ModuleType("suno_recipe")
    R.parse_lyrics = lambda text: [{"tag": "V", "delivery": "sung",
                                    "lines": ["hook line"]}] * 2

    ov = types.ModuleType("song_choices.overlap")
    ov.MIN_OVERLAP_S = 1.0
    ov.__getattr__ = lambda name: (lambda *a, **k: None)
    ov.receipts_from_results = lambda *a, **k: []
    ov.check_overlap = lambda *a, **k: []
    ovpkg = types.ModuleType("song_choices")
    ovpkg.overlap = ov
    ovpkg.__path__ = []

    sys.modules.update({"song_dispatch": pkg, "song_dispatch.song_dispatch": sd,
                        "suno_recipe": R, "song_choices": ovpkg,
                        "song_choices.overlap": ov})


def load(path, run_takes=None):
    """Import one module file under a unique name, stubs installed first."""
    _stub_modules(run_takes or (lambda *a, **k: {"verdict": "PASS",
                                                 "delivered": {"audio_path": "/x"},
                                                 "receipts": [], "receipt": {}}))
    _seq[0] += 1
    name = "c11song_%d" % _seq[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Gen:
    """A generate() stand-in: no attempt_envelopes unless the test sets them."""


def _take(path="/run/music/take.mp3"):
    return {"audio_path": path}


def _transport(calls, behaviour):
    def run_takes(req, plan, gen, measure, save, sw, ht, srp=None, **kw):
        calls.append(kw)
        return behaviour(gen, measure, save, kw)
    return run_takes


PASS_VERDICT = {"verdict": "PASS", "delivered": {"audio_path": "/run/music/ok.mp3"},
                "receipts": [{"gate": "lyrics", "verdict": "PASS"}], "receipt": {"id": "r"}}


# ---------------------------------------------------------------- region 1
REGION1 = "R1 envelope constructors (counts/envelopes/refusals/persist)"


def r1a_counts_typed(m, tmp):
    base = m.make_counts(planned=1)
    assert set(base) == set(m.COUNT_KEYS), "counts keys: %r" % (base,)
    assert all(base[k] == 0 for k in base if k != "planned"), base
    try:
        m.make_counts(bogus=1)
        raise AssertionError("unknown count key accepted")
    except m.ChoiceError:
        pass
    zero = m._counts_from_dispatch({}, {})
    assert (zero["submitted"], zero["acknowledged"], zero["billed"]) == (0, 0, 0), zero
    ev = {"accepted_submit_at": "2026-01-01T00:00:00Z", "task_id": "t1",
          "actual_cost": 0, "saved_paths": []}
    full = m._counts_from_dispatch({}, ev)
    assert (full["submitted"], full["acknowledged"],
            full["billed"]) == (1, 1, 1), full
    return "counts measured from evidence, 7 keys, unknown key refused"


def r1b_empty_take_is_error(m, tmp):
    env = m._finish_envelope(_Gen(), {"id": "polished-modern"},
                             {"receipts": []}, None, [])
    assert env["outcome"] == "error", env
    assert env["reason_code"] == "EMPTY_TAKE_LIST", env
    assert env["next_action"], env
    assert env["counts"]["delivered"] == 0, env
    return "empty take list -> error envelope EMPTY_TAKE_LIST"


def r1c_persist_fault_returns(m, tmp):
    run = tempfile.mkdtemp(dir=tmp)
    open(os.path.join(run, "music"), "w").close()      # obstruct the path
    env = m.attempt_envelope("v1", "a1", "error", m.make_counts(planned=1),
                             reason_code="X", next_action="y")
    path, err = m._persist_envelope(run, "v1", env)
    assert path == "" and err, (path, err)
    assert "Error" in err or "error" in err, err
    return "persistence fault returned, never raised: %s" % err.split(":")[0]


def r1d_save_failed_unknown_cost(m, tmp):
    fail = {"take": _take(), "error": RuntimeError("disk full")}
    env = m._save_failed_envelope(_Gen(), {"id": "v1"}, fail, [], 0)
    assert env["reason_code"] == "SONG_SAVE_FAILED", env
    ev = env["evidence"]
    assert ev["actual_cost"] is None, ev
    assert "ACTUAL_COST_UNREPORTED" in (ev.get("warnings") or []), ev
    assert env["counts"]["billed"] == 0, env
    assert ev["failed_operation"] == "save", ev
    assert ev["failing_audio_path"] == "/run/music/take.mp3", ev
    return "save failure holds the paid take, charge UNKNOWN not zero"


def r1e_measure_failed_named(m, tmp):
    fail = {"take": _take("/run/music/second.mp3"), "error": ValueError("bad wav")}
    env = m._operation_failed_envelope(_Gen(), {"id": "v1"}, fail, "measure",
                                       [{"receipt": 1}], 1)
    assert env["reason_code"] == "SONG_MEASURE_FAILED", env
    assert env["evidence"]["failed_operation"] == "measure", env
    assert env["counts"]["materialized"] == 1, env
    assert env["counts"]["evaluated"] == 1, env
    return "measure failure named measure, never save, dispatch facts kept"


# ---------------------------------------------------------------- region 2
REGION2 = "R2 run identity (_canonical_run_dir, named authorities, conflict)"


def r2a_canonical_run_dir(m, tmp):
    assert m._canonical_run_dir(None) is None
    assert m._canonical_run_dir("   ") is None
    target = tempfile.mkdtemp(dir=tmp)
    link = os.path.join(tmp, "link_%d" % _seq[0])
    os.symlink(target, link)
    assert m._canonical_run_dir(link) == os.path.realpath(target), \
        m._canonical_run_dir(link)
    return "blank -> None; symlinked run dir canonicalised"


def r2b_nested_authority_conflict(m, tmp):
    a = tempfile.mkdtemp(dir=tmp, prefix="A")
    b = tempfile.mkdtemp(dir=tmp, prefix="B")
    auth = m._run_dir_authorities({"run_dir": a, "input": {"run_dir": b}}, None)
    assert set(auth) == {"request.run_dir", "request.input.run_dir"}, auth
    conflict = m._run_dir_conflict(auth)
    assert conflict, "conflicting nested run_dir was masked"
    same = m._run_dir_authorities({"run_dir": a, "input": {"run_dir": a}}, a)
    assert set(same) == {"--run-dir", "request.run_dir", "request.input.run_dir"}, same
    assert m._run_dir_conflict(same) == "", same
    return "nested input.run_dir cannot be masked by top-level run_dir"


def r2c_identity_refusal_before_generation(m, tmp):
    a = tempfile.mkdtemp(dir=tmp, prefix="A")
    b = tempfile.mkdtemp(dir=tmp, prefix="B")
    called = []

    def gen(*x, **k):
        called.append(1)
        return []

    try:
        m.one_variant(1, {"id": "v1"}, {}, {}, gen, lambda t: None,
                      lambda v, t, r: True, "", "hook",
                      envelope_run_dir=a, run_dir=b)
    except m.ChoiceError as exc:
        assert "differs from the run identity" in str(exc), str(exc)
        assert not called, "generation ran despite an identity fork"
        return "envelope/run identity fork refused BEFORE any generation"
    raise AssertionError("divergent run identity accepted")


# ---------------------------------------------------------------- region 3
REGION3 = "R3 caller wiring (cap_cents, boundary classification, persistence)"


def _run_one(m, tmp, behaviour, save=None):
    calls = []

    def _save(variant, take, rc):
        if save:
            return save(take)
        return True

    run = tempfile.mkdtemp(dir=tmp, prefix="run")
    m._SD.run_takes = _transport(calls, behaviour)
    out = m.one_variant(1, {"id": "polished-modern", "label": "Polished Modern"},
                        {}, {}, lambda v, rq: [_take()], lambda t: {"ok": 1},
                        _save, "", "hook line",
                        envelope_run_dir=run, run_dir=run)
    return out, calls, run


def r3a_cap_cents(m, tmp):
    out, calls, run = _run_one(m, tmp,
                               lambda g, me, s, kw: PASS_VERDICT)
    assert calls and calls[0].get("cap_cents") == m._SD.GEN_COST_CENTS, calls
    assert out["status"] == "PASS", out
    assert out["receipts"] == PASS_VERDICT["receipts"], out
    return "run_takes called with cap_cents=%d; success result carries the judge receipts" % m._SD.GEN_COST_CENTS


def r3b_save_failure_holds_take(m, tmp):
    def behaviour(g, me, s, kw):
        s(_take(), {"verdict": "PASS"})
        return PASS_VERDICT
    out, calls, run = _run_one(m, tmp, behaviour,
                               save=lambda t: (_ for _ in ()).throw(OSError("disk full")))
    assert out["status"] == "SAVE_FAILED", out
    assert out["heard"] and out["heard"]["audio_path"].endswith("take.mp3"), out
    assert out["envelope"]["reason_code"] == "SONG_SAVE_FAILED", out["envelope"]
    envp = os.path.join(run, "music", "takes", "polished-modern",
                        "dispatch-envelope.json")
    assert os.path.isfile(envp), envp
    return "save failure -> SAVE_FAILED with the paid take held and persisted"


def r3c_persist_fault_keeps_hold(m, tmp):
    def behaviour(g, me, s, kw):
        s(_take(), {"verdict": "PASS"})
        return PASS_VERDICT
    run_check = {}

    def save(t):
        raise OSError("disk full")
    # obstruct the envelope path before the run
    def patched(m2, tmp2):
        pass
    out, calls, run = _run_one(m, tmp, behaviour, save=save)
    # obstruct music/ AFTER the run dir exists but BEFORE the envelope writes:
    # re-drive with a run dir whose music/ is a file
    run2 = tempfile.mkdtemp(dir=tmp, prefix="runfault")
    open(os.path.join(run2, "music"), "w").close()
    m._SD.run_takes = _transport([], behaviour)
    out2 = m.one_variant(1, {"id": "polished-modern"}, {}, {},
                         lambda v, rq: [_take()], lambda t: {"ok": 1},
                         lambda v, t, r: (_ for _ in ()).throw(OSError("disk full")),
                         "", "hook line", envelope_run_dir=run2, run_dir=run2)
    assert out2["status"] == "SAVE_FAILED", out2
    assert out2["heard"], out2
    assert out2["persistence_error"], out2
    assert out2["envelope"]["reason_code"] == "SONG_SAVE_FAILED", out2["envelope"]
    return "an obstructed envelope path cannot discard the paid-task hold"


def r3d_measure_failure_not_save(m, tmp):
    def behaviour(g, me, s, kw):
        s(_take("/run/music/first.mp3"), {"verdict": "PASS"})   # earlier take saved
        me(_take("/run/music/second.mp3"))                      # second track fails
        return PASS_VERDICT

    def _meas(t):
        raise ValueError("bad wav")

    run = tempfile.mkdtemp(dir=tmp, prefix="run")
    m._SD.run_takes = _transport([], behaviour)
    out = m.one_variant(1, {"id": "polished-modern"}, {}, {},
                        lambda v, rq: [_take()], _meas,
                        lambda v, t, r: True, "", "hook line",
                        envelope_run_dir=run, run_dir=run)
    assert out["status"] == "MEASURE_FAILED", out
    assert out["envelope"]["reason_code"] == "SONG_MEASURE_FAILED", out["envelope"]
    return "second-track measure failure is MEASURE_FAILED, not SAVE_FAILED"


def r3e_refused_classification(m, tmp):
    def behaviour(g, me, s, kw):
        raise RuntimeError("provider exploded: quota")
    out, calls, run = _run_one(m, tmp, behaviour)
    assert out["status"] == "REFUSED", out
    assert out["envelope"]["outcome"] == "error", out["envelope"]
    assert out["envelope"]["reason_code"], out["envelope"]
    assert out["counts"]["billed"] == 0, out
    return "an unclassified transport failure -> REFUSED, no bill claimed"


# ---------------------------------------------------------------- region 4
REGION4 = "R4 generation call site (envelope_run_dir/run_dir, one mode family)"


def _args(run, request, variant=None, unit_id=None):
    return types.SimpleNamespace(run_dir=run, request=request, variant=variant,
                                 unit_id=unit_id, ledger=None, run_id="r1")


def _wire(m, request):
    rows = [({"id": uid, "label": uid}, {"_style_id": "s"}) for uid in m.UNIT_IDS]
    m.build_requests = lambda *a, **k: rows
    m._sheet_lyric_words = lambda spec: "words"
    m._hook_text = lambda spec: "hook line"
    m._load_request = lambda path, cli_run_dir=None: {
        "style_id": "s", "sheet": [{"tag": "V", "delivery": "sung", "lines": ["hook line"]}] * 2,
        "sheet_text": "x", "client_text": "", "title": "t", "length_s": 30,
        "vocal_gender": "f", "hook_plan": {}, "pace_plan": {},
        "run_authorities": m._run_dir_authorities({"run_dir": None}, cli_run_dir)}


def r4a_identity_threaded(m, tmp):
    run = tempfile.mkdtemp(dir=tmp, prefix="run")
    _wire(m, None)
    seen = []
    m.generate_choices = lambda reqs, **kw: (seen.append(kw) or [{"attempts": 1}] * 3)
    out = m.cmd_generate(_args(run, "/nonexistent.json"),
                         measure=lambda t: {"ok": 1}, save=lambda v, t, r: True)
    canon = os.path.realpath(run)
    assert seen, "generate_choices never called"
    assert seen[0].get("envelope_run_dir") == canon, seen[0].keys()
    assert seen[0].get("run_dir") == canon, seen[0].keys()
    modefile = os.path.join(canon, "music", "dispatch-mode.json")
    assert os.path.isfile(modefile), modefile
    doc = json.load(open(modefile))
    assert doc == {"mode": "umbrella", "family": "umbrella"}, doc
    assert out["dispatched"] == 3, out
    return "cmd_generate threads ONE canonical run dir to the generation call site"


def r4b_mode_family(m, tmp):
    run = tempfile.mkdtemp(dir=tmp, prefix="run")
    _wire(m, None)
    m.generate_choices = lambda reqs, **kw: [{"attempts": 1}] * 3
    m.run_unit = lambda reqs, **kw: [{"attempts": 1}]
    _io = dict(measure=lambda t: {"ok": 1}, save=lambda v, t, r: True)
    m.cmd_generate(_args(run, "/nonexistent.json"), **_io)     # umbrella first
    try:
        m.cmd_generate(_args(run, "/nonexistent.json", unit_id="WW-001"), **_io)
        raise AssertionError("umbrella + unit on one run accepted (9-generation risk)")
    except m.ChoiceError as exc:
        assert "mode family" in str(exc), str(exc)
    run2 = tempfile.mkdtemp(dir=tmp, prefix="run")
    for uid in ("WW-001", "WW-002", "WW-003"):                 # documented 3-unit flow
        m.cmd_generate(_args(run2, "/nonexistent.json", unit_id=uid), **_io)
    doc = json.load(open(os.path.join(os.path.realpath(run2), "music",
                                      "dispatch-mode.json")))
    assert doc["family"] == "unit", doc
    return "one family per run: units 1-3 allowed, umbrella+unit refused"


CHECKS = [
    (REGION1, r1a_counts_typed), (REGION1, r1b_empty_take_is_error),
    (REGION1, r1c_persist_fault_returns), (REGION1, r1d_save_failed_unknown_cost),
    (REGION1, r1e_measure_failed_named),
    (REGION2, r2a_canonical_run_dir), (REGION2, r2b_nested_authority_conflict),
    (REGION2, r2c_identity_refusal_before_generation),
    (REGION3, r3a_cap_cents), (REGION3, r3b_save_failure_holds_take),
    (REGION3, r3c_persist_fault_keeps_hold), (REGION3, r3d_measure_failure_not_save),
    (REGION3, r3e_refused_classification),
    (REGION4, r4a_identity_threaded), (REGION4, r4b_mode_family),
]


def run_all(path):
    tmp = tempfile.mkdtemp(prefix="c11-")
    rows = []
    try:
        for region, fn in CHECKS:
            tmpc = tempfile.mkdtemp(dir=tmp)
            try:
                m = load(path)
                detail = fn(m, tmpc)
                rows.append({"region": region, "check": fn.__name__,
                             "pass": True, "detail": detail})
            except Exception as exc:                       # noqa: BLE001
                rows.append({"region": region, "check": fn.__name__,
                             "pass": False,
                             "detail": "%s: %s" % (type(exc).__name__, exc)})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rows


def _target(argv):
    for arg in argv[1:]:
        if not arg.startswith("-"):
            return arg
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "song_choices.py")


def main(argv):
    path = _target(argv)
    rows = run_all(path)
    ok = sum(1 for r in rows if r["pass"])
    if "--json" in argv:
        print(json.dumps({"module": path, "pass": ok, "total": len(rows),
                          "rows": rows}, indent=1))
    else:
        for r in rows:
            print("%s %-34s %s" % ("PASS" if r["pass"] else "FAIL",
                                   r["check"], r["detail"]))
        print("%d/%d" % (ok, len(rows)))
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""S75-018 (U-GEN319 C5): ONE status vocabulary for every version the module
produces, and every consumer honours it.

Each status ``one_variant`` can write is driven through ``deliver_choices`` and
must land in exactly one of three places:

  OFFERED   the take is on the pick surface;
  HEARD     the take is presented for LISTENING and the one fork question;
  REFUSED   the client-facing refusal NAMES what happened to that version.

None is silently dropped. The case that matters most is a paid task HELD FOR
RESUME: it is never reported as a run that made no song.

The expectation table below is keyed by the module's own ``STATUSES`` tuple, so
a status added to the producer without a home here fails this file loudly.

Everything is offline: the provider transport, the judge, the save and measure
transports and the ffmpeg runner are injected stubs. No network, no spend.

Run: python3 75-drama-song-ad-factory/scripts/core/song_choices/test_song_choices_s75_018_status.py
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import types

_seq = [0]

#: Where each status must land, and the words a plain-English refusal has to
#: use for it. These words are the TEST'S OWN, not the module's table.
EXPECT = {
    "PASS": ("offered", ()),
    "FAILED": ("heard", ()),
    "HELD": ("refused", ("held", "resume")),
    "SAVE_FAILED": ("refused", ("saving",)),
    "MEASURE_FAILED": ("refused", ("measur",)),
    "REFUSED": ("refused", ("refused",)),
}

#: The refusal the module raised BEFORE S75-018: it named nothing.
GENERIC_REFUSAL = "no song version passed every required song gate; nothing to offer"


def _stub_modules():
    sd = types.ModuleType("song_dispatch.song_dispatch")
    sd.GEN_COST_CENTS = 80
    sd.NOT_CONSTITUENT_REASON = "no constituent-evidence receipt"
    sd.acceptance_from_run = lambda *a, **k: {"accepted": True}
    sd.acceptance_refusal = lambda *a, **k: ""
    sd.constituent_ok = lambda rec: (True, "")
    pkg = types.ModuleType("song_dispatch")
    pkg.song_dispatch = sd
    pkg.__path__ = []

    R = types.ModuleType("suno_recipe")
    R.parse_lyrics = lambda text: []

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


def load(path):
    """Import one module file under a unique name, stubs installed first."""
    _stub_modules()
    _seq[0] += 1
    name = "s75018_%d" % _seq[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _take(tmp, n):
    p = os.path.join(tmp, "take-%d.mp3" % n)
    with open(p, "wb") as f:
        f.write(b"ID3fake-mp3-bytes")
    return {"audio_path": p, "duration_s": 88.0}


def _result(tmp, n, status):
    """ONE produced version in ``status``. A status with no take carries the
    paid take on ``heard`` where the producer does (SAVE_FAILED)."""
    take = heard = None
    if status in ("PASS", "FAILED"):
        take = _take(tmp, n)
    elif status == "SAVE_FAILED":
        heard = _take(tmp, n)
    return {"n": n, "variant": {"id": "variant-%d" % n, "label": "LABEL %d" % n,
                                "description": "description %d" % n},
            "status": status, "take": take, "heard": heard,
            "concerns": ["hook: FAIL - the hook never lands"] if status == "FAILED" else [],
            "receipt": {"schema": "constituent-evidence/1", "accepted": True}
            if take else None,
            "receipts": [], "attempt": 1, "attempts": 1}


def drive(m, tmp, status):
    """Push three versions in ``status`` through deliver_choices. Returns
    ``{status, where, text}`` -- ``where`` is offered, heard or refused."""
    results = [_result(tmp, n, status) for n in (1, 2, 3)]
    run, deliv = os.path.join(tmp, "run"), os.path.join(tmp, "D")
    os.makedirs(deliv, exist_ok=True)
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink):
            msg = m.deliver_choices(results, deliv, run, runner=lambda argv: None)
    except m.ChoiceError as exc:
        return {"status": status, "where": "refused", "text": str(exc)}
    with open(os.path.join(run, "song-choices", "state.json"), encoding="utf-8") as f:
        st = json.load(f)
    where = "offered" if st.get("offered") else "heard" if st.get("failure_fork") else "dropped"
    return {"status": status, "where": where, "text": msg}


def check_one(m, tmp, status):
    want_where, want_words = EXPECT[status]
    got = drive(m, tmp, status)
    assert got["where"] == want_where, \
        "%s landed in %r, not %r: %s" % (status, got["where"], want_where, got["text"])
    if want_where == "refused":
        assert got["text"] != GENERIC_REFUSAL, \
            "%s is NAMED, not dropped into the generic refusal: %r" % (status, got["text"])
        for n in ("1", "2", "3"):
            assert n in got["text"], \
                "%s refusal never names version %s: %r" % (status, n, got["text"])
        assert "version 1, 2, 3" in got["text"], \
            "%s refusal must name every version: %r" % (status, got["text"])
        low = got["text"].lower()
        for word in want_words:
            assert word in low, \
                "%s refusal never says %r: %r" % (status, word, got["text"])
    return "%s -> %s" % (status, got["where"])


def run_all(path):
    tmp = tempfile.mkdtemp(prefix="s75018-")
    rows = []
    try:
        m = load(path)
        # The expectation table and the producer's vocabulary are the SAME set:
        # a new status with no home here fails, never goes untested.
        assert set(m.STATUSES) == set(EXPECT), \
            ("the producer's statuses %r and this test's %r disagree"
             % (sorted(m.STATUSES), sorted(EXPECT)))
        for status in m.STATUSES:
            tmpc = tempfile.mkdtemp(dir=tmp)
            try:
                rows.append({"status": status, "pass": True,
                             "detail": check_one(load(path), tmpc, status)})
            except Exception as exc:                       # noqa: BLE001
                rows.append({"status": status, "pass": False,
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


def show(path, tmp):
    """The loud-refusal check: per status, the client-facing text and the list
    the result landed in."""
    m = load(path)
    for status in m.STATUSES:
        tmpc = tempfile.mkdtemp(dir=tmp)
        got = drive(m, tmpc, status)
        print("%-15s -> %-8s | %s" % (status, got["where"],
                                      got["text"].replace("\n", " / ")))


def main(argv):
    path = _target(argv)
    if "--text" in argv:
        tmp = tempfile.mkdtemp(prefix="s75018-")
        try:
            show(path, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return 0
    rows = run_all(path)
    ok = sum(1 for r in rows if r["pass"])
    if "--json" in argv:
        print(json.dumps({"module": path, "pass": ok, "total": len(rows),
                          "rows": rows}, indent=1))
    else:
        for r in rows:
            print("%s %-16s %s" % ("PASS" if r["pass"] else "FAIL",
                                   r["status"], r["detail"]))
        print("%d/%d" % (ok, len(rows)))
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

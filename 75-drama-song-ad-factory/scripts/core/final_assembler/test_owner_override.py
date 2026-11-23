#!/usr/bin/env python3
"""SOV-001 owner override: the reader and the decision helper. $0, no ffmpeg.

The owner (Trevor) decides: a SIGNED ``control/owner-override.json`` exempts
exactly the two OVERRIDE_SITES, and the assembler discloses every use on the
receipt. Everything else -- missing, unreadable, half-written, unsigned, an
empty site list -- reads as None, so the gates keep their full floor.

Run: python3 final_assembler/test_owner_override.py   (or via pytest)
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A           # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def _run(tmp, rec=None, raw=None):
    """One run dir with control/owner-override.json written from rec or raw."""
    ctl = os.path.join(tmp, "control")
    os.makedirs(ctl, exist_ok=True)
    if rec is not None:
        with open(os.path.join(ctl, A.OVERRIDE_FILE), "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
    elif raw is not None:
        with open(os.path.join(ctl, A.OVERRIDE_FILE), "w", encoding="utf-8") as fh:
            fh.write(raw)
    return tmp

SIGNED = {"signed_by": "Trevor", "signature": "sov-001-2026-11-21",
          "who": "Trevor", "at": "2026-11-21T10:00:00-05:00",
          "sites": ["lipsync_evidence", "dup_frames"]}

def test_sites_constant():
    check("sites-exact", A.OVERRIDE_SITES == ("lipsync_evidence", "dup_frames"),
          repr(A.OVERRIDE_SITES))

def test_reader_fails_closed():
    tmp = tempfile.mkdtemp(prefix="/tmp/sov001-lane-")
    try:
        # no run_dir, no control dir, no file
        check("none-no-run-dir", A.owner_override(None) is None)
        check("none-no-control", A.owner_override(os.path.join(tmp, "absent")) is None)
        os.makedirs(os.path.join(tmp, "a", "control"))
        check("none-no-file", A.owner_override(os.path.join(tmp, "a")) is None)
        # half-written JSON
        t = _run(os.path.join(tmp, "b"), raw='{"signed_by": "Trevor", "sign')
        check("none-half-written", A.owner_override(t) is None)
        # not a JSON object
        t = _run(os.path.join(tmp, "c"), raw="[]")
        check("none-not-object", A.owner_override(t) is None)
        # signed by someone else
        rec = dict(SIGNED, signed_by="owner")
        check("none-signed-by-owner",
              A.owner_override(_run(os.path.join(tmp, "d"), rec)) is None)
        # whitespace-only signature
        rec = dict(SIGNED, signature="   ")
        check("none-blank-signature",
              A.owner_override(_run(os.path.join(tmp, "e"), rec)) is None)
        rec = dict(SIGNED, signature=None)
        check("none-missing-signature",
              A.owner_override(_run(os.path.join(tmp, "f"), rec)) is None)
        # empty / non-list / non-string sites
        check("none-empty-sites",
              A.owner_override(_run(os.path.join(tmp, "g"),
                                    dict(SIGNED, sites=[]))) is None)
        check("none-sites-not-list",
              A.owner_override(_run(os.path.join(tmp, "h"),
                                    dict(SIGNED, sites="dup_frames"))) is None)
        check("none-sites-blank-strings",
              A.owner_override(_run(os.path.join(tmp, "i"),
                                    dict(SIGNED, sites=["  ", 7]))) is None)
        # missing / blank who and at
        check("none-no-who",
              A.owner_override(_run(os.path.join(tmp, "j"),
                                    dict(SIGNED, who=""))) is None)
        check("none-no-at",
              A.owner_override(_run(os.path.join(tmp, "k"),
                                    dict(SIGNED, at="  "))) is None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def test_reader_accepts_signed_record():
    tmp = tempfile.mkdtemp(prefix="/tmp/sov001-lane-")
    try:
        rec = A.owner_override(_run(tmp, SIGNED))
        check("signed-record-returned",
              rec == {"who": "Trevor", "at": "2026-11-21T10:00:00-05:00",
                      "sites": ["lipsync_evidence", "dup_frames"]}, repr(rec))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def test_unknown_site_ignored():
    tmp = tempfile.mkdtemp(prefix="/tmp/sov001-lane-")
    try:
        rec = A.owner_override(_run(
            tmp, dict(SIGNED, sites=["motion", "dup_frames", "crop", 7])))
        check("unknown-site-dropped",
              rec is not None and rec["sites"] == ["dup_frames"], repr(rec))
        # unknown site alone grants nothing on any real gate
        check("unknown-site-grants-nothing",
              A._override_row({"who": "T", "at": "now", "sites": []},
                              "motion", "CLIP_LOW_MOTION", "d") is None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def test_override_row_pure():
    rec = {"who": "Trevor", "at": "2026-11-21T10:00:00-05:00",
           "sites": ["dup_frames"]}
    row = A._override_row(rec, "dup_frames", "TIMELINE_DUP_FRAMES", "3.4%")
    check("row-shape", row == {"site": "dup_frames",
                               "code": "TIMELINE_DUP_FRAMES",
                               "detail": "3.4%", "who": "Trevor",
                               "at": "2026-11-21T10:00:00-05:00"}, repr(row))
    check("row-site-not-listed",
          A._override_row(rec, "lipsync_evidence", "X", "d") is None)
    check("row-unknown-site",
          A._override_row({"who": "T", "at": "a",
                           "sites": ["motion"]}, "motion", "X", "d") is None)
    check("row-no-record", A._override_row(None, "dup_frames", "X", "d") is None)
    check("row-empty-record", A._override_row({}, "dup_frames", "X", "d") is None)

def main():
    for fn in (test_sites_constant, test_reader_fails_closed,
               test_reader_accepts_signed_record, test_unknown_site_ignored,
               test_override_row_pure):
        fn()
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all SOV-001 owner override checks passed")
    return 0

def test_sov001_suite_passes():
    test_sites_constant()
    test_reader_fails_closed()
    test_reader_accepts_signed_record()
    test_unknown_site_ignored()
    test_override_row_pure()
    assert not FAILS, FAILS

if __name__ == "__main__":
    sys.exit(main())

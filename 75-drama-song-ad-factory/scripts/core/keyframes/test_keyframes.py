#!/usr/bin/env python3
"""S75-A27 tests: keyframes follow the timed continuity record.

Done when: keyframes are derived from the timed continuity record in its own
order (one per shot, carrying that shot's window and lines), and generation is
REFUSED when the continuity record is missing, empty, out of order, overlapping
or malformed -- never silently sorted or invented. stdlib only, $0, no provider.

Run: python3 scripts/core/keyframes/test_keyframes.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import keyframes.keyframes as K                       # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def refuse(code, fn, *a, **kw):
    """(True, message) when fn raises KeyframeError with `code`."""
    try:
        fn(*a, **kw)
    except K.KeyframeError as e:
        return (e.code == code), "%s got %s: %s" % (code, e.code, e)
    return False, "%s: nothing refused" % code


#: A timed continuity record in song order: the shot after the song's own
#: measured line windows. Windows are contiguous, each naming its line.
CONTINUITY = {"shots": [
    {"shot_id": "S01", "song_start": 0.0, "song_end": 4.5,
     "shows_line_ids": ["L1"], "lyric_line_ids": ["L1"]},
    {"shot_id": "S02", "song_start": 4.5, "song_end": 9.0,
     "shows_line_ids": ["L2"], "lyric_line_ids": ["L2"]},
    {"shot_id": "S03", "song_start": 9.0, "song_end": 14.25,
     "shows_line_ids": ["L3"], "lyric_line_ids": ["L3"]},
]}


def test_one_keyframe_per_shot_in_continuity_order():
    m = K.build_manifest(CONTINUITY, run_id="run-1")
    check("A27-1 shot_count equals continuity shot count", m["shot_count"] == 3,
          m["shot_count"])
    check("A27-2 keyframe order is the continuity order",
          [r["shot_id"] for r in m["keyframes"]] == ["S01", "S02", "S03"],
          [r["shot_id"] for r in m["keyframes"]])
    check("A27-3 windows are carried, not invented",
          [(r["start_s"], r["end_s"]) for r in m["keyframes"]]
          == [(0.0, 4.5), (4.5, 9.0), (9.0, 14.25)])
    check("A27-4 every keyframe names the line its shot shows",
          [r["line_ids"] for r in m["keyframes"]] == [["L1"], ["L2"], ["L3"]])
    check("A27-5 indexes are 1..n in order",
          [r["index"] for r in m["keyframes"]] == [1, 2, 3])
    check("A27-6 nothing is marked generated before a provider call",
          all(r["status"] == "planned" for r in m["keyframes"]))
    check("A27-7 stage id is keyframes/<shot-set-digest>",
          m["id"] == "keyframes/" + m["shot_set_digest"]
          and len(m["shot_set_digest"]) == 64)


def test_digest_is_order_sensitive_and_stable():
    a = K.build_manifest(CONTINUITY)
    b = K.build_manifest({"shots": [
        {"shot_id": "S01", "song_start": 0.0, "song_end": 5.0,
         "shows_line_ids": ["L1"]},
        {"shot_id": "S02", "song_start": 5.0, "song_end": 9.0,
         "shows_line_ids": ["L2"]}]})
    check("A27-8 same record gives the same shot-set digest",
          a["shot_set_digest"] == K.build_manifest(CONTINUITY)["shot_set_digest"])
    check("A27-9 a different timed shot set is a different digest",
          a["shot_set_digest"] != b["shot_set_digest"])
    ok, why = refuse(K.CONTINUITY_UNORDERED, K.build_manifest,
                     {"shots": list(reversed(CONTINUITY["shots"]))})
    check("A27-9b a reversed record is refused, never silently sorted", ok, why)


def test_refuses_missing_continuity():
    for label, record in (("None", None), ("no shots key", {}),
                          ("empty shots", {"shots": []}),
                          ("bare empty list", []),
                          ("not a record", "shots")):
        ok, why = refuse(K.CONTINUITY_MISSING, K.build_manifest, record)
        check("A27-10 refuses %s continuity (%s)" % (label if label != "None" else "absent", K.CONTINUITY_MISSING), ok, why)


def test_refuses_unordered_continuity():
    back = {"shots": [
        {"shot_id": "S02", "song_start": 4.5, "song_end": 9.0},
        {"shot_id": "S01", "song_start": 0.0, "song_end": 4.5}]}
    ok, why = refuse(K.CONTINUITY_UNORDERED, K.build_manifest, back)
    check("A27-11 refuses shots out of time order", ok, why)
    overlap = {"shots": [
        {"shot_id": "S01", "song_start": 0.0, "song_end": 5.0},
        {"shot_id": "S02", "song_start": 4.5, "song_end": 9.0}]}
    ok, why = refuse(K.CONTINUITY_UNORDERED, K.build_manifest, overlap)
    check("A27-12 refuses overlapping shot windows", ok, why)
    backwards = {"shots": [
        {"shot_id": "S01", "song_start": 4.0, "song_end": 1.0}]}
    ok, why = refuse(K.CONTINUITY_UNORDERED, K.build_manifest, backwards)
    check("A27-13 refuses a window that runs backwards", ok, why)


def test_refuses_bad_shape():
    no_id = {"shots": [{"song_start": 0.0, "song_end": 1.0}]}
    ok, why = refuse(K.CONTINUITY_SHAPE, K.build_manifest, no_id)
    check("A27-14 refuses a shot with no shot_id", ok, why)
    bad_num = {"shots": [{"shot_id": "S01", "song_start": "0",
                          "song_end": 1.0}]}
    ok, why = refuse(K.CONTINUITY_SHAPE, K.build_manifest, bad_num)
    check("A27-15 refuses a non-numeric window", ok, why)
    dup = {"shots": [
        {"shot_id": "S01", "song_start": 0.0, "song_end": 1.0},
        {"shot_id": "S01", "song_start": 1.0, "song_end": 2.0}]}
    ok, why = refuse(K.CONTINUITY_DUPLICATE_SHOT, K.build_manifest, dup)
    check("A27-16 refuses a repeated shot_id", ok, why)


def test_manifest_round_trip_and_cli():
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "keyframes", "manifest.json")
        m = K.build_manifest(CONTINUITY, run_id="run-1")
        K.write_manifest(out, m)
        check("A27-17 manifest lands at keyframes/manifest.json",
              os.path.isfile(out))
        check("A27-18 written manifest reads back identical",
              K.load_manifest(out) == m)
        bad = os.path.join(td, "no-continuity.json")
        with open(bad, "w", encoding="utf-8") as f:
            json.dump({"shots": []}, f)
        rc = K.main(["build", "--continuity", bad, "--out",
                     os.path.join(td, "x", "manifest.json")])
        check("A27-19 CLI exits 2 on a record with no timed shots", rc == 2, rc)
        check("A27-20 CLI wrote nothing for a refused record",
              not os.path.exists(os.path.join(td, "x", "manifest.json")))
        good = os.path.join(td, "continuity.json")
        with open(good, "w", encoding="utf-8") as f:
            json.dump(CONTINUITY, f)
        rc = K.main(["build", "--continuity", good, "--out", out])
        check("A27-21 CLI builds the manifest from the record", rc == 0, rc)


def test_run():
    test_one_keyframe_per_shot_in_continuity_order()
    test_digest_is_order_sensitive_and_stable()
    test_refuses_missing_continuity()
    test_refuses_unordered_continuity()
    test_refuses_bad_shape()
    test_manifest_round_trip_and_cli()


if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS 21/21" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)

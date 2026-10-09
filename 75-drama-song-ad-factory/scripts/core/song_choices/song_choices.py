#!/usr/bin/env python3
"""song_choices: SONG APPROVAL, three labelled songs and the pick gate (FU-SONG-APPROVAL).

Trevor 2026-10-09: add an audio approval gate like the storyboard one. When the
client answers Yes to the SONG APPROVAL card question:

  1. build_requests()    three Suno requests for the SAME lyric sheet, one per
                         arrangement variant (data table: variants.json), each
                         checked by song_dispatch.validate_request before spend;
  2. generate_choices()  the three run IN PARALLEL; each take is judged by
                         song_dispatch.judge_take (lyrics, hook, voice rules);
                         a version that fails is regenerated once, then reported;
  3. deliver_choices()   SONG-CHOICES/ in the delivery folder: "N - LABEL
                         (description).mp3" with the title tag set to the same
                         label (ffmpeg -c copy), plus README.txt;
  4. record_pick()       the client's 1, 2 or 3; the picked file becomes the song;
  5. refusal() /         NO picture timing, paid video, image or lip-sync job
     dispatch_refusal()  runs until the pick is recorded. A missing or damaged
                         pick blocks; nothing ever defaults.

State lives in <run>/song-choices/ (state.json, pick.json). No state file means
the client answered No: behaviour is exactly as before (one song, no wait).
stdlib only; generate/measure/save/runner are injected, so no network here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from song_dispatch import song_dispatch as _SD   # noqa: E402
from suno_recipe import suno_recipe as _R         # noqa: E402

TOOL_NAME = "song_choices"
DIRNAME = "SONG-CHOICES"
BANNED_WORDS = ("choir", "reverb", "echo", "rap", "spoken", "speak", "acapella")
EXTRA_GENERATIONS = 2          # the card pays for 2 more songs than the single-song run
_TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "variants.json")


class ChoiceError(ValueError):
    """A loud refusal: nothing was spent or delivered on the broken path."""


def variants_for(style_id):
    """The three variants for a music style (data table). Fails closed."""
    with open(_TABLE, encoding="utf-8") as f:
        rows = json.load(f).get(str(style_id))
    if not rows or len(rows) != 3:
        raise ChoiceError("no three-variant set for music style %r in variants.json" % (style_id,))
    for r in rows:
        low = r["clause"].lower()
        bad = [w for w in BANNED_WORDS if re.search(r"\b%s" % w, low)]
        if bad or len(r["clause"]) > 140:
            raise ChoiceError("variant %r clause breaks the style rules: %s" % (r["id"], bad or "too long"))
    return rows


def extra_cost_cents():
    """What the Yes answer adds to the song line: two more generations."""
    return EXTRA_GENERATIONS * _SD.GEN_COST_CENTS


def build_requests(style_id, sheet, client_text, title, length_s, vocal_gender="f", **kw):
    """[(variant, request)] x3: the style's own request plus the variant clause.
    Every request must pass song_dispatch.validate_request or none is sent."""
    out = []
    for v in variants_for(style_id):
        req = _R.build_request(style_id, sheet, client_text, title, length_s, vocal_gender, **kw)
        req = dict(req, style=req["style"].rstrip() + " " + v["clause"].rstrip(".") + ".")
        errs = _SD.validate_request(req, style_id, client_text)
        if errs:
            raise ChoiceError("variant %s request refused before spend: %s" % (v["id"], "; ".join(errs)))
        out.append((v, req))
    return out


def generate_choices(requests, plan, generate, measure, save, script_words, hook_text,
                     spoken_range_pct=None, **kw):
    """Run the three variants in parallel. generate(variant, request) -> takes;
    measure(take) -> measured fields; save(variant, take, receipt) keeps the stem.
    One generation per attempt; a FAIL is regenerated ONCE, then reported.
    Returns [{n, variant, status PASS|FLAG|FAILED, take, attempts, receipts}]."""
    def one(n, v, req):
        receipts, got = [], None
        for attempt in (1, 2):
            r = _SD.run_takes(req, plan, lambda rq: generate(v, rq), measure,
                              lambda t, rc: save(v, t, rc), script_words, hook_text,
                              spoken_range_pct, cap_cents=_SD.GEN_COST_CENTS, **kw)
            receipts += r["receipts"]
            if r["verdict"] != "FAIL":
                got = r
                break
        return {"n": n, "variant": v, "status": got["verdict"] if got else "FAILED",
                "take": got["delivered"] if got else None, "attempts": attempt, "receipts": receipts}

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(one, i, v, rq) for i, (v, rq) in enumerate(requests, 1)]
        return [f.result() for f in futs]


def _safe(s):
    return re.sub(r'[\\/:*?"<>|]', "-", s)


def _mmss(sec):
    sec = int(round(float(sec)))
    return "%d:%02d" % (sec // 60, sec % 60)


def _run_ffmpeg(argv):
    subprocess.run(argv, check=True, capture_output=True)


def deliver_choices(results, delivery_dir, run_dir, runner=_run_ffmpeg):
    """Write SONG-CHOICES/ and the offered list into state.json. Returns the
    client message. Zero good versions raises (fail closed)."""
    good = [r for r in results if r["status"] != "FAILED" and r["take"]]
    if not good:
        raise ChoiceError("no song version passed the song checks; nothing to offer")
    folder = os.path.join(delivery_dir, DIRNAME)
    os.makedirs(folder, exist_ok=True)
    offered, lines = {}, []
    for r in good:
        v, take = r["variant"], r["take"]
        label = "%d - %s (%s)" % (r["n"], v["label"], v["description"])
        dst = os.path.join(folder, _safe(label) + ".mp3")
        runner(["ffmpeg", "-y", "-i", take["audio_path"], "-c", "copy",
                "-metadata", "title=" + label, dst])
        dur = _mmss(take.get("duration_s", 0))
        lines.append("%s - %s - %s" % (label.split(" (")[0], dur, v["description"]))
        offered[str(r["n"])] = {"label": label, "file": dst, "duration": dur, "take": take}
    with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    st = _state(run_dir) or {"required": True}
    st.update(required=True, offered=offered)
    _write(run_dir, "state.json", st)
    return client_message(offered, [r["n"] for r in results if r["status"] == "FAILED"])


def client_message(offered, failed=()):
    nums = sorted(int(n) for n in offered)
    rows = ["%d. %s - %s" % (n, offered[str(n)]["label"].split(" - ", 1)[1], offered[str(n)]["duration"])
            for n in nums]
    pick = "%s or %d" % (", ".join(map(str, nums[:-1])), nums[-1]) if len(nums) > 1 else str(nums[0])
    msg = ["Your song is ready in %d versions. They are in the %s folder:" % (len(nums), DIRNAME), ""] + rows
    if failed:
        msg += ["", "Version %s did not pass my song checks after a second try, so I left it out."
                % ", ".join(map(str, failed))]
    return "\n".join(msg + ["", "Reply %s to pick your song. Nothing else is made until you pick." % pick])


# ---- state and the gate -------------------------------------------------

def _path(run_dir, name):
    return os.path.join(run_dir, "song-choices", name)


def _write(run_dir, name, data):
    os.makedirs(os.path.join(run_dir, "song-choices"), exist_ok=True)
    with open(_path(run_dir, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def _state(run_dir):
    p = _path(run_dir, "state.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def init(run_dir, required):
    """Record the card answer. Call once when the card is approved."""
    _write(run_dir, "state.json", {"required": bool(required), "offered": {}})


def _sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def picked_song(run_dir):
    return os.path.join(run_dir, "music", "picked-song.mp3")


def record_pick(run_dir, reply):
    """The client's 1, 2 or 3. Anything not offered is refused; returns the label."""
    st = _state(run_dir)
    if not st or not st.get("required"):
        raise ChoiceError("this run did not ask for song choices")
    n = str(reply).strip()
    o = (st.get("offered") or {}).get(n)
    if not o or not os.path.isfile(o["file"]):
        raise ChoiceError("%r is not one of the offered songs %s" % (reply, sorted(st.get("offered") or {})))
    os.makedirs(os.path.join(run_dir, "music"), exist_ok=True)
    shutil.copyfile(o["file"], picked_song(run_dir))
    _write(run_dir, "pick.json", {"pick": int(n), "label": o["label"], "sha256": _sha(picked_song(run_dir)),
                                  "take": o.get("take")})
    return o["label"]


def refusal(run_dir):
    """None when work may go on; else the refusal. No state file = answered No."""
    try:
        st = _state(run_dir)
    except (OSError, ValueError):
        return _refuse("the song-choices state is unreadable; fix it before anything is spent")
    if st is None or not st.get("required"):
        return None
    try:
        with open(_path(run_dir, "pick.json"), encoding="utf-8") as f:
            pick = json.load(f)
        ok = os.path.isfile(picked_song(run_dir)) and _sha(picked_song(run_dir)) == pick["sha256"]
    except (OSError, ValueError, KeyError):
        ok = False
    if not ok:
        return _refuse("the client has not picked a song yet (or the picked file is missing or changed)")
    return None


def _refuse(why):
    return {"reason_code": "SONG_PICK_MISSING", "detail": why,
            "next_action": "Send the client the three songs and wait for their pick (1, 2 or 3). "
                           "No picture timing, video, image or lip-sync job starts before it."}


def dispatch_refusal(is_music_job, run_dir):
    """kie_dispatch seam: the song stage itself may run; everything else waits."""
    return None if is_music_job else refusal(run_dir)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Song choices: init the card answer, record the pick, check the gate.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--run-dir", required=True)
    i.add_argument("--required", choices=("yes", "no"), required=True)
    p = sub.add_parser("pick")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--reply", required=True)
    c = sub.add_parser("check")
    c.add_argument("--run-dir", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "init":
            init(a.run_dir, a.required == "yes")
        elif a.cmd == "pick":
            print("Picked: " + record_pick(a.run_dir, a.reply))
        else:
            r = refusal(a.run_dir)
            if r:
                print(json.dumps(r, indent=2))
                return 5
            print("ok")
    except ChoiceError as e:
        print("REFUSED: %s" % e, file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

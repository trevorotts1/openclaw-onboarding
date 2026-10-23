#!/usr/bin/env python3
"""sc12_image_typed_preview.py — acceptance row SC-12 (image-typed previews).

required_result (SCENARIO-MATRIX.json, verbatim):
    "NEGATIVE: an image-typed preview is never presented as audio/video; type is
     validated before presentation and a mismatch is refused with a named error"

Proves, against the tree under test:
  * a real PNG whose bytes are given a video extension is refused by the
    delivery gate with a named code — the content is read, not the extension;
  * the same bytes under an audio extension are refused the same way;
  * require_delivery_audio fails closed on the image-typed file;
  * the gate still ACCEPTS a real AAC-LC 48 kHz faststart file, so the two
    refusals above are type validation and not a blanket refusal;
  * the storyboard presentation carries the same PNG as an IMAGE and never as
    audio, and the image bytes are untouched by the presentation.

Stdlib + ffmpeg/ffprobe (the gate shells to them). Exit 2 when the tools are
absent: the row cannot be measured without them and is never claimed.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  selftest    re-run the scenario under deliberate fixture defects and REQUIRE
              the named assertions to turn RED (proves the harness can fail)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc12"
TITLE = "image-typed previews are never presented as audio/video"

def storyboard_fixture(run_dir, extra_shot=False):
    png = H.tiny_png(Path(run_dir) / "fixtures" / "shot-1.png")
    shots = [{"shot_id": "s1", "song_start": 0, "song_end": 5}]
    contracts = {"s1": {"lyric_text": "I built this",
                        "viewer_understanding": "she owns what she built",
                        "character_action": "stands tall at the counter",
                        "visible_emotion": "proud"}}
    stills = {"s1": png}
    if extra_shot:
        shots.append({"shot_id": "s2", "song_start": 5, "song_end": 10})
        contracts["s2"] = dict(contracts["s1"])
        stills["s2"] = H.tiny_png(Path(run_dir) / "fixtures" / "shot-2.png")
    H.write_json(Path(run_dir) / "storyboard" / "shot-list.json", {"shots": shots})
    H.write_json(Path(run_dir) / "storyboard" / "contracts.json", contracts)
    H.write_json(Path(run_dir) / "storyboard" / "stills.json", stills)
    return png

def scenario(core, muts=frozenset()):
    DA = H.load_file(core / "delivery_audio.py", "sc12_delivery_audio")
    AR = H.load_pkg(core, "storyboard_director.approval_runner")
    c = H.Checks(ROW, TITLE)
    print("SC-12 %s — tree %s%s"
          % (TITLE, core,
             (" [defect: %s]" % ",".join(sorted(muts))) if muts else ""))

    with H.Scratch() as run_dir:
        png = storyboard_fixture(run_dir, extra_shot="extra_shot" in muts)
        png_sha = H.sha256_file(png)

        as_video = Path(run_dir) / "fixtures" / "still-as-song.mp4"
        as_audio = Path(run_dir) / "fixtures" / "still-as-song.m4a"
        if "audio_bytes_instead_of_image" in muts:
            audio = H.aac_take(Path(run_dir) / "fixtures" / "take.mp4", 2)
            shutil.copyfile(str(audio), str(as_video))
            shutil.copyfile(str(audio), str(as_audio))
        else:
            shutil.copyfile(str(png), str(as_video))
            shutil.copyfile(str(png), str(as_audio))

        for path, label in ((as_video, "video"), (as_audio, "audio")):
            res = DA.check_delivery_audio(str(path))
            c.check("sc12:image-typed-as-%s-refused" % label,
                    res.get("ok") is False
                    and res.get("reason_code") == DA.NO_AUDIO
                    and path.name in str(res.get("reason")),
                    "code=%s detail=%s"
                    % (res.get("reason_code"), str(res.get("reason"))[:140]))

        refused = None
        try:
            DA.require_delivery_audio(str(as_video))
        except DA.DeliveryAudioRefused as exc:
            refused = exc.code
        c.check("sc12:require-audio-fails-closed-on-image",
                refused == DA.NO_AUDIO,
                "raised code=%s" % (refused,))

        # control: the same gate accepts a real audio file, so the refusals
        # above are about the type and not about the gate refusing everything.
        real = Path(run_dir) / "fixtures" / "real-song.mp4"
        if "control_is_image" in muts:
            H.tiny_png(real)
        else:
            H.aac_take(real, 2)
        good = DA.check_delivery_audio(real)
        c.check("sc12:real-audio-still-accepted",
                good.get("ok") is True
                and good.get("reason_code") == "DELIVERY_AUDIO_OK"
                and good.get("codec") == "aac",
                "code=%s codec=%s" % (good.get("reason_code"),
                                      good.get("codec")))

        # presentation: the still goes out as an image, never as audio
        sent = []

        def send(message, images):
            sent.append((message, list(images or [])))

        AR.run(str(run_dir), send=send)
        presented = sent[0][1] if sent else []
        # approval_runner sends images as [(shot number, file path)]
        names = [(n, Path(p).name) for n, p in presented]
        c.check("sc12:preview-presented-as-image",
                len(sent) == 1 and len(presented) == 1
                and presented[0][0] == 1
                and Path(presented[0][1]).name == "shot-1.png",
                "sends=%d images=%s" % (len(sent), names))
        c.check("sc12:presented-image-bytes-unchanged",
                H.sha256_file(png) == png_sha,
                "sha256 %s before, %s after"
                % (png_sha[:12], H.sha256_file(png)[:12]))

    return c

# --------------------------------------------------------------------------
# selftest — deliberate fixture defects must turn the named assertions RED
# --------------------------------------------------------------------------
# ``sc12:presented-image-bytes-unchanged`` has no working mutation: the only
# way to turn it red is to rewrite the very file the assertion hashes, which
# proves nothing about the product. It is left out rather than faked.
MUTATIONS = {
    "audio_bytes_instead_of_image": [
        "sc12:image-typed-as-video-refused",
        "sc12:image-typed-as-audio-refused",
        "sc12:require-audio-fails-closed-on-image",
    ],
    "control_is_image": [
        "sc12:real-audio-still-accepted",
    ],
    "extra_shot": [
        "sc12:preview-presented-as-image",
    ],
}

def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and bool(failed)
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good else "DID NOT FAIL AS EXPECTED",
                 failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s" % ("harness fails on all %d defects" % len(MUTATIONS)
                             if ok else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    selftest_mode = bool(argv) and argv[0] == "selftest"
    args = H.add_args(
        description="sc12 selftest" if selftest_mode else __doc__
    ).parse_args(argv[1:] if selftest_mode else argv)
    core = H.resolve_core(args)
    if not H.have_tools("ffprobe", "ffmpeg"):
        print("TOOLING: ffprobe and ffmpeg are required by the delivery-audio "
              "gate this row measures")
        return 2
    if selftest_mode:
        return selftest(core)
    return scenario(core).finish(args.out)

if __name__ == "__main__":
    sys.exit(main())

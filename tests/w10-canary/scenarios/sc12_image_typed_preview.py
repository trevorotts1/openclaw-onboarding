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
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc12"
TITLE = "image-typed previews are never presented as audio/video"

def storyboard_fixture(run_dir):
    png = H.tiny_png(Path(run_dir) / "fixtures" / "shot-1.png")
    H.write_json(Path(run_dir) / "storyboard" / "shot-list.json",
                 {"shots": [{"shot_id": "s1", "song_start": 0, "song_end": 5}]})
    H.write_json(Path(run_dir) / "storyboard" / "contracts.json",
                 {"s1": {"lyric_text": "I built this",
                         "viewer_understanding": "she owns what she built",
                         "character_action": "stands tall at the counter",
                         "visible_emotion": "proud"}})
    H.write_json(Path(run_dir) / "storyboard" / "stills.json", {"s1": png})
    return png

def main(argv=None):
    args = H.add_args(description=__doc__).parse_args(argv)
    core = H.resolve_core(args)
    if not H.have_tools("ffprobe", "ffmpeg"):
        print("TOOLING: ffprobe and ffmpeg are required by the delivery-audio "
              "gate this row measures")
        return 2

    DA = H.load_file(core / "delivery_audio.py", "sc12_delivery_audio")
    AR = H.load_pkg(core, "storyboard_director.approval_runner")
    c = H.Checks(ROW, TITLE)
    print("SC-12 %s — tree %s" % (TITLE, core))

    with H.Scratch() as run_dir:
        png = storyboard_fixture(run_dir)
        png_sha = H.sha256_file(png)

        as_video = Path(run_dir) / "fixtures" / "still-as-song.mp4"
        as_audio = Path(run_dir) / "fixtures" / "still-as-song.m4a"
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
        real = H.aac_take(Path(run_dir) / "fixtures" / "real-song.mp4", 2)
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

        return c.finish(args.out)

if __name__ == "__main__":
    sys.exit(main())

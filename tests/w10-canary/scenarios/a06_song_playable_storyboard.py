#!/usr/bin/env python3
"""a06_song_playable_storyboard.py — acceptance row A06 (weight 7).

Condition (tests/w10-canary/receipt-mapping.json, row A06, verbatim):
    "playable song + storyboard delivery/resume proofs (S75-W10-U1)"

Proves, against the tree under test:

  playable song
    * the delivery-audio gate NEVER passes a file it cannot decode as AAC
      (unreadable / no-audio is refused by name, not waved through);
    * require_delivery_audio fails closed with the named code;
    * the delivered-master mux argv is AAC-LC 48 kHz with +faststart — the
      exact properties that make the song play on QuickTime and every social
      platform;
    * a passing gate returns its receipt (the gate is not a blanket refusal).

  storyboard delivery / resume
    * the first pass presents the cards once and the delivery gate stays shut;
    * the client's approval opens the gate and sends nothing further;
    * a RESUME of an approved storyboard re-sends nothing (idempotent) and
      returns the existing continuation;
    * changing a still after approval closes the gate again.

The one assertion that needs a real produced song file is supplied through
--audio (a paid-provider artifact). Without it the runner prints BLOCKED_A11
and exits 4 — it never fakes that pass. Every other check runs locally.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "a06"
TITLE = "playable song + storyboard delivery/resume"


def storyboard_fixture(run_dir):
    """One approved-able shot: shot list, card contract, reference still."""
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
    ap = H.add_args(description=__doc__)
    ap.add_argument("--audio", default=None,
                    help="a real produced song file (paid-provider artifact) "
                         "for the playable-song assertion")
    args = ap.parse_args(argv)
    core = H.resolve_core(args)

    DA = H.load_file(core / "delivery_audio.py", "a06_delivery_audio")
    AR = H.load_pkg(core, "storyboard_director.approval_runner")

    c = H.Checks(ROW, TITLE)
    print("A06 %s — tree %s" % (TITLE, core))

    with H.Scratch() as run_dir:
        # ---- playable song: the gate must refuse what it cannot decode -----
        not_audio = Path(run_dir) / "fixtures" / "not-a-song.mp4"
        not_audio.parent.mkdir(parents=True, exist_ok=True)
        not_audio.write_bytes(b"this is not an muxed audio/video file\n")
        res = DA.check_delivery_audio(str(not_audio))
        c.check("a06:audio-gate-refuses-undecodable-file",
                res.get("ok") is False
                and res.get("reason_code") in (DA.UNREADABLE, DA.NO_AUDIO,
                                               DA.BAD_CODEC, DA.BAD_RATE,
                                               DA.NO_FASTSTART),
                "code=%s" % res.get("reason_code"))

        refused = None
        try:
            DA.require_delivery_audio(str(not_audio))
        except DA.DeliveryAudioRefused as exc:
            refused = exc.code
        c.check("a06:require-audio-fails-closed", bool(refused), "code=%s" % refused)

        c.check("a06:delivery-mux-is-aac-lc-48k-faststart",
                "-c:a" in DA.AUDIO_OUT_ARGS
                and "aac" in DA.AUDIO_OUT_ARGS
                and "aac_low" in DA.AUDIO_OUT_ARGS
                and "48000" in DA.AUDIO_OUT_ARGS
                and "+faststart" in DA.FASTSTART_ARGS,
                "audio_args=%s" % DA.AUDIO_OUT_ARGS)

        good = {"ok": True, "reason_code": "DELIVERY_AUDIO_OK",
                "reason": "aac-lc 48 kHz faststart", "codec": "aac",
                "mean_db": -16.0}
        got = DA.require_delivery_audio("injected", gate=lambda _p: dict(good))
        c.check("a06:passing-gate-returns-its-receipt",
                got.get("ok") is True and got.get("codec") == "aac",
                "reason_code=%s" % got.get("reason_code"))

        # ---- storyboard delivery / resume ---------------------------------
        storyboard_fixture(run_dir)
        sent = []

        def send(message, images):
            sent.append((message, list(images or [])))

        first = AR.run(str(run_dir), send=send)
        c.check("a06:storyboard-first-pass-presents-once",
                first.get("action") == "waiting" and len(sent) == 1,
                "action=%s sends=%d" % (first.get("action"), len(sent)))
        c.check("a06:storyboard-gate-shut-before-approval",
                AR.gate_open(str(run_dir)) is False,
                "gate_open=%s" % AR.gate_open(str(run_dir)))

        approved = AR.run(str(run_dir), send=send, reply="approve")
        c.check("a06:storyboard-approval-opens-delivery",
                approved.get("action") == "approved"
                and approved.get("message_sent") is False
                and AR.gate_open(str(run_dir)) is True,
                "action=%s gate_open=%s"
                % (approved.get("action"), AR.gate_open(str(run_dir))))

        before = len(sent)
        resumed = AR.run(str(run_dir), send=send)
        c.check("a06:storyboard-resume-resends-nothing",
                resumed.get("action") == "approved"
                and resumed.get("message_sent") is False
                and len(sent) == before,
                "action=%s new_sends=%d"
                % (resumed.get("action"), len(sent) - before))

        # a still regenerated after approval must close the gate again
        png = Path(run_dir) / "fixtures" / "shot-1.png"
        png.write_bytes(png.read_bytes() + b"\x00")
        c.check("a06:storyboard-still-change-closes-delivery",
                AR.gate_open(str(run_dir)) is False,
                "gate_open=%s" % AR.gate_open(str(run_dir)))

        failed = c.failed()
        if failed:
            return c.finish(args.out)
        if not args.audio:
            c.summary()
            return H.blocked(
                "a real produced song file is required to prove the delivered "
                "song is playable (AAC-LC 48 kHz faststart). Pass --audio <file>. "
                "Producing it needs a paid provider run outside this unit.")

        real = DA.check_delivery_audio(args.audio)
        c.check("a06:playable-song-accepted-by-delivery-gate",
                real.get("ok") is True,
                "code=%s reason=%s" % (real.get("reason_code"),
                                       str(real.get("reason"))[:160]))
        return c.finish(args.out)


if __name__ == "__main__":
    sys.exit(main())

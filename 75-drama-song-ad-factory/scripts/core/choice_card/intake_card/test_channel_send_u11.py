#!/usr/bin/env python3
"""U11: channel-neutral send + requested-only device notice.

Checks, on the entrypoint and never on wording:

  (a) a send through app, terminal and storyboard reaches the SAME code path:
      each ``CHANNEL_SEND[c].func is send`` and each still builds the existing
      ``openclaw message send`` argv;
  (b) an UNREQUESTED device notice sends NOTHING -- with a negative control
      (the requested case) that proves the check can fail;
  (c) the existing gate still denies the denied case with a real non-zero exit;
  (d) one nudge, then silence: a second requested notice on the same run is a no-op.

Run: python3 core/choice_card/intake_card/test_channel_send_u11.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import channel_send as CS  # noqa: E402

SCRIPT = os.path.join(HERE, "channel_send.py")
OPENCLAW = ["openclaw", "message", "send", "--channel", "telegram", "--target"]


def _cli(*args):
    return subprocess.run([sys.executable, SCRIPT] + list(args),
                          capture_output=True, text=True)


def _unpicked_run():
    """A run that asked for song choices but has no pick yet -> the gate refuses."""
    run_dir = tempfile.mkdtemp()
    d = os.path.join(run_dir, "song-choices")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"required": True, "offered": {}}, f)
    return run_dir


def test_all_three_channels_share_one_entrypoint():
    for c in ("app", "terminal", "storyboard"):
        assert c in CS.CHANNEL_SEND
        assert CS.CHANNEL_SEND[c].func is CS.send, c      # the SAME function object


def test_send_through_each_channel_builds_the_existing_argv():
    seen = []
    for c in ("app", "terminal", "storyboard"):
        argv = CS.CHANNEL_SEND[c]("555", "hello", sink=seen.append)
        assert argv[:6] == OPENCLAW, (c, argv[:6])          # existing sender, not a new one
        assert argv[6] == "555" and argv[8] == "hello"
    assert len(seen) == 3                                   # every channel actually delivered


def test_media_reach_every_channel_through_the_one_path():
    seen = []
    CS.CHANNEL_SEND["storyboard"]("555", "shot 1", media=["/tmp/a.png"], sink=seen.append)
    assert seen[0].count("--media") == 1 and "/tmp/a.png" in seen[0]


def test_unrequested_device_notice_sends_nothing():
    sent = []
    argv = CS.device_notice("555", "your video is ready", requested=False, sink=sent.append)
    assert argv is None
    assert sent == [], sent                                # NO notice


def test_negative_control_requested_notice_does_send():
    """If the requested-only guard were removed, the check above would fail."""
    sent = []
    argv = CS.device_notice("555", "your video is ready", requested=True, sink=sent.append)
    assert argv is not None and len(sent) == 1, sent
    assert sent[0][:6] == OPENCLAW


def test_one_nudge_then_silence():
    run_dir = tempfile.mkdtemp()
    sent = []
    first = CS.device_notice("555", "nudge", requested=True, run_dir=run_dir, sink=sent.append)
    second = CS.device_notice("555", "nudge", requested=True, run_dir=run_dir, sink=sent.append)
    assert first is not None and second is None
    assert len(sent) == 1, sent                            # one nudge, then silence


def test_gate_denies_and_sends_nothing():
    sent = []
    try:
        CS.send("terminal", "555", "hi", sink=sent.append,
                gate=lambda _: {"reason_code": "SONG_PICK_MISSING", "detail": "no pick yet"})
    except CS.SendRefused as e:
        assert "no pick yet" in str(e), e
    else:
        raise AssertionError("a refusing gate did not stop the send")
    assert sent == [], sent


def test_unknown_channel_is_refused():
    try:
        CS.send("email", "555", "hi", sink=lambda a: None)
    except CS.ChannelError:
        pass
    else:
        raise AssertionError("an unknown channel was accepted")


def test_existing_gate_denies_the_denied_case_with_nonzero_exit():
    run_dir = _unpicked_run()
    p = _cli("send", "--channel", "app", "--target", "555", "--message", "hi",
             "--run-dir", run_dir)
    assert p.returncode != 0, (p.returncode, p.stdout)
    assert p.returncode == CS.REFUSED_EXIT, p.returncode
    assert "REFUSED" in p.stderr, p.stderr
    assert p.stdout.strip() == "", p.stdout                # nothing was sent


def test_cli_unrequested_notice_exits_zero_and_sends_nothing():
    p = _cli("notice", "--target", "555", "--message", "hi")
    assert p.returncode == 0, (p.returncode, p.stderr)
    assert "no notice sent" in p.stdout, p.stdout


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print("ALL PASS" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)

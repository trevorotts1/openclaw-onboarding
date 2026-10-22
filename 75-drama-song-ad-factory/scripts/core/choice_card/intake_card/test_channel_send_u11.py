#!/usr/bin/env python3
"""W03-U1: transport-spy counterexample + honest delivery states (D06, D07).

Checks, on the entrypoint and never on wording:

  (a) COUNTEREXAMPLE (D06): app/terminal/storyboard captures contain NO
      hardcoded telegram channel -- the captured channel always EQUALS the
      resolved origin channel (telegram appears only for a telegram-origin run,
      and then with the correct authenticated bot/account, chat and thread);
  (b) D07: no message is claimed sent without a channel receipt -- a sink that
      returns no receipt leaves the piece ``uncertain``, never ``sent``;
  (c) the no-target case stays ``action-required`` and repairing the
      destination resumes actual delivery;
  (d) the existing contract stands: shared entrypoint identity, gate refusal
      before anything is built, requested-only device notice, one nudge then
      silence, unknown channel refused, real non-zero gate exit.

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
from choice_card.intake_card import delivery_outbox as DO  # noqa: E402

SCRIPT = os.path.join(HERE, "channel_send.py")
OPENCLAW_PREFIX = ["openclaw", "message", "send", "--channel"]
SURFACES = ("app", "terminal", "storyboard")


def _cli(*args):
    return subprocess.run([sys.executable, SCRIPT] + list(args),
                          capture_output=True, text=True)


def _run_with_origin(origin):
    run_dir = tempfile.mkdtemp()
    if origin:
        DO.save_origin(run_dir, origin)
    return run_dir


def _unpicked_run():
    """A run that asked for song choices but has no pick yet -> the gate refuses."""
    run_dir = tempfile.mkdtemp()
    d = os.path.join(run_dir, "song-choices")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"required": True, "offered": {}}, f)
    return run_dir


def _channel_of(payload):
    """The channel a captured transport payload names (argv or terminal record)."""
    if isinstance(payload, dict):
        return payload.get("display", "")
    return payload[payload.index("--channel") + 1]


def test_all_three_channels_share_one_entrypoint():
    for c in SURFACES:
        assert c in CS.CHANNEL_SEND
        assert CS.CHANNEL_SEND[c].func is CS.send, c      # the SAME function object


def test_transport_spy_counterexample_no_hardcoded_telegram():
    """The D06 counterexample: for every surface and every origin channel, the
    capture names the RESOLVED channel. Telegram never appears except on a
    telegram-origin run."""
    for origin_channel in ("telegram", "app", "terminal"):
        for surface in SURFACES:
            run = _run_with_origin({"channel": origin_channel,
                                    "conversation_id": "conv-1"})
            seen = []
            CS.CHANNEL_SEND[surface]("ignored", "hello",
                                     sink=lambda p: seen.append(p) or {"message_id": "m"},
                                     run_dir=run)
            assert len(seen) == 1, (surface, origin_channel, seen)
            got = _channel_of(seen[0])
            assert got == origin_channel, (surface, origin_channel, got)
            flat = json.dumps(seen[0], sort_keys=True) if isinstance(seen[0], dict) \
                else " ".join(seen[0])
            if origin_channel != "telegram":
                assert "telegram" not in flat, (surface, origin_channel, flat)


def test_telegram_origin_resolves_account_chat_and_thread():
    run = _run_with_origin({"channel": "telegram", "account_id": "bot-7",
                            "conversation_id": "777", "thread_id": "t-9"})
    seen = []
    CS.CHANNEL_SEND["storyboard"]("ignored", "shot 1", media=[],
                                  sink=lambda p: seen.append(p) or {"message_id": "m"},
                                  run_dir=run)
    argv = seen[0]
    assert argv[:4] == OPENCLAW_PREFIX and argv[4] == "telegram", argv
    assert argv[argv.index("--target") + 1] == "777"          # the run's own chat
    assert argv[argv.index("--account") + 1] == "bot-7"       # authenticated bot
    assert argv[argv.index("--thread-id") + 1] == "t-9"       # forum thread


def test_app_origin_returns_to_the_app_conversation():
    run = _run_with_origin({"channel": "app", "conversation_id": "conv-42"})
    seen = []
    CS.CHANNEL_SEND["app"]("ignored", "hello",
                           sink=lambda p: seen.append(p) or {"message_id": "m"},
                           run_dir=run)
    argv = seen[0]
    assert argv[4] == "app" and argv[argv.index("--target") + 1] == "conv-42", argv
    assert "telegram" not in " ".join(argv)


def test_terminal_origin_uses_host_display_with_playback_evidence():
    run = _run_with_origin({"channel": "terminal", "conversation_id": "tty-1"})
    seen = []
    CS.CHANNEL_SEND["storyboard"]("ignored", "here is the take",
                                  media=[os.path.join(HERE, "ai_models.json")],
                                  sink=lambda p: seen.append(p) or {"displayed": True},
                                  run_dir=run)
    assert all(isinstance(r, dict) and r["display"] == "terminal" for r in seen), seen
    text_rec = next(r for r in seen if r.get("text"))
    art_rec = next(r for r in seen if r.get("artifacts"))
    assert text_rec["text"] == "here is the take"
    assert art_rec["artifacts"], art_rec                   # the actual artifact display
    for art in art_rec["artifacts"]:
        assert art["display"] in ("inline", "path-reference"), art
        lim = art["playback_limits"]
        assert lim.get("evidence"), art                    # explicit evidence, always
        if art["display"] == "path-reference":
            assert lim.get("playable") is False or lim.get("inline") is False, art
    ev = text_rec["playback_evidence"]
    assert "no audio output" in ev["audio"]["evidence"], ev  # playback limits spelled out


def test_no_receipt_is_uncertain_never_sent():
    """D07: a dispatch without a channel receipt is never claimed sent."""
    run = _run_with_origin({"channel": "app", "conversation_id": "c-1"})
    CS.CHANNEL_SEND["app"]("ignored", "hello", sink=lambda p: None, run_dir=run)
    pieces = DO.Outbox(run).pieces()
    assert len(pieces) == 1 and pieces[0]["state"] == DO.UNCERTAIN, pieces
    assert pieces[0]["receipt"] is None                       # NO sent claim
    # negative control: with a receipt the SAME call IS sent
    run2 = _run_with_origin({"channel": "app", "conversation_id": "c-2"})
    CS.CHANNEL_SEND["app"]("ignored", "hello",
                           sink=lambda p: {"message_id": "m-1"}, run_dir=run2)
    p2 = DO.Outbox(run2).pieces()
    assert len(p2) == 1 and p2[0]["state"] == DO.SENT and \
        p2[0]["receipt"] == {"message_id": "m-1"}, p2


def test_no_target_stays_action_required_and_repair_resumes_delivery():
    run = tempfile.mkdtemp()                                  # no origin, no target
    ret = CS.CHANNEL_SEND["app"]("", "hello", sink=lambda p: {"message_id": "m"},
                                 run_dir=run)
    assert ret is None, ret                                   # nothing claimed dispatched
    out = DO.Outbox(run)
    pieces = out.pieces()
    assert pieces and all(p["state"] == DO.ACTION_REQUIRED for p in pieces), pieces
    assert all(p.get("receipt") is None for p in pieces)
    # repair of the destination resumes ACTUAL delivery
    rec = DO.save_origin(run, {"channel": "telegram", "account_id": "bot-1",
                               "conversation_id": "999"})
    moved = out.redestinate(rec)
    assert moved and all(p["state"] == DO.QUEUED for p in moved), moved
    run_res = out.resume(lambda p: {"message_id": "m-9", "piece": p["piece_id"]})
    assert run_res["sent"] == [p["piece_id"] for p in moved], run_res
    assert all(p.get("receipt") for p in DO.Outbox(run).pieces())


def test_unrequested_device_notice_sends_nothing():
    sent = []
    argv = CS.device_notice("555", "your video is ready", requested=False, sink=sent.append)
    assert argv is None
    assert sent == [], sent                                # NO notice


def test_requested_notice_records_sent_only_with_receipt():
    sent = []
    argv = CS.device_notice("555", "your video is ready", requested=True, sink=sent.append)
    assert argv is not None and len(sent) == 1, sent
    assert sent[0][:4] == OPENCLAW_PREFIX
    run = tempfile.mkdtemp()
    CS.device_notice("555", "nudge", requested=True, run_dir=run,
                     sink=lambda p: {"message_id": "m-1"})
    rec = json.load(open(os.path.join(run, "control", "device-notice.json")))
    assert rec["sent"] is True and rec["receipt"] == {"message_id": "m-1"}, rec
    # without a receipt the notice is dispatched but NEVER claimed sent
    run2 = tempfile.mkdtemp()
    CS.device_notice("555", "nudge", requested=True, run_dir=run2, sink=lambda p: None)
    rec2 = json.load(open(os.path.join(run2, "control", "device-notice.json")))
    assert rec2["sent"] is False and rec2["state"] == DO.UNCERTAIN, rec2


def test_one_nudge_then_silence():
    run_dir = tempfile.mkdtemp()
    sent = []
    first = CS.device_notice("555", "nudge", requested=True, run_dir=run_dir,
                             sink=sent.append)
    second = CS.device_notice("555", "nudge", requested=True, run_dir=run_dir,
                              sink=sent.append)
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

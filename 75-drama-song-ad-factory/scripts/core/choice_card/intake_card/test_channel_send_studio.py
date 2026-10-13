#!/usr/bin/env python3
"""W1-box-bridge-U4: channel_send gains the ``studio`` channel.

Checks, on the entrypoint and never on wording:

  (a) ``studio`` is a channel and shares the ONE send entrypoint;
  (b) a studio send publishes through ``approvals_bridge.publish`` with the
      order id and base URL from the run's ``control/studio-order.json``, the
      key from the bridge's own lookup, and the stage/version/text/choices/files
      passed through unchanged;
  (c) a run WITHOUT a studio order is refused LOUDLY (ChannelError) with a
      negative control proving the same call succeeds when the file exists;
  (d) the existing gate still stops a studio send before anything is published;
  (e) an unknown channel is still refused.

The publish transport is injected (stub) so nothing is ever sent.

Run: python3 core/choice_card/intake_card/test_channel_send_studio.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import channel_send as CS  # noqa: E402

ORDER = {"order_id": "o-1", "client_id": "c-9", "title": "Drama video",
         "base_url": "https://studio.example.test"}


def _studio_run():
    run_dir = tempfile.mkdtemp()
    os.makedirs(os.path.join(run_dir, "control"), exist_ok=True)
    with open(os.path.join(run_dir, "control", "studio-order.json"), "w", encoding="utf-8") as f:
        json.dump(ORDER, f)
    return run_dir


class _FakeBridge:
    """Stands in for shared-bridge: a recording publish + a fixed key lookup."""

    def __init__(self):
        self.calls = []

    def publish(self, base_url, key, order_id, stage, version, text, choices, files):
        self.calls.append({"base_url": base_url, "key": key, "order_id": order_id,
                           "stage": stage, "version": version, "text": text,
                           "choices": choices, "files": files})
        return {"stage": stage, "version": version, "answer": None}


def test_studio_is_a_channel_and_shares_the_one_entrypoint():
    assert "studio" in CS.CHANNELS
    assert CS.CHANNEL_SEND["studio"].func is CS.send, CS.CHANNEL_SEND["studio"]


def test_studio_send_publishes_with_run_order_and_bridge_key():
    bridge = _FakeBridge()
    orig_publish, orig_key = CS._bridge_publish, CS._bridge_key
    CS._bridge_publish, CS._bridge_key = lambda: bridge.publish, lambda: "test-key-not-real"
    try:
        run_dir = _studio_run()
        item = CS.send("studio", run_dir=run_dir, stage="song", version=2,
                       text="pick one", choices=[{"n": 1, "label": "A"}],
                       files=["/tmp/a.mp3"], sink=None)
    finally:
        CS._bridge_publish, CS._bridge_key = orig_publish, orig_key
    assert len(bridge.calls) == 1, bridge.calls
    call = bridge.calls[0]
    assert call["base_url"] == ORDER["base_url"]
    assert call["order_id"] == ORDER["order_id"]
    assert call["key"] == "test-key-not-real"          # the bridge's lookup, not env glue here
    assert call["stage"] == "song" and call["version"] == 2
    assert call["text"] == "pick one"
    assert call["choices"] == [{"n": 1, "label": "A"}]
    assert call["files"] == ["/tmp/a.mp3"]
    assert item == {"stage": "song", "version": 2, "answer": None}


def test_sink_is_the_publish_transport():
    """The injected sink receives the publish call -- the negative control for
    (b): without it the real approvals_bridge would be imported."""
    bridge = _FakeBridge()
    run_dir = _studio_run()
    CS.CHANNEL_SEND["studio"](run_dir=run_dir, stage="script", version=1,
                              text="script v1", sink=bridge.publish)
    assert len(bridge.calls) == 1, bridge.calls
    assert bridge.calls[0]["stage"] == "script"


def test_no_studio_order_is_refused_loud():
    run_dir = tempfile.mkdtemp()          # no control/studio-order.json at all
    try:
        CS.send("studio", run_dir=run_dir, stage="script", version=1, text="t",
                sink=lambda *a: None)
    except CS.ChannelError as e:
        assert "studio order" in str(e), e
    else:
        raise AssertionError("a run without a studio order published")


def test_negative_control_same_call_works_when_the_file_exists():
    """If the refusal above were removed, this (the same call on a studio run)
    would fail; if this fails, the refusal check is broken, not the channel."""
    bridge = _FakeBridge()
    run_dir = _studio_run()
    CS.send("studio", run_dir=run_dir, stage="script", version=1, text="t",
            sink=bridge.publish)
    assert len(bridge.calls) == 1


def test_broken_order_file_is_refused():
    for body in ("not json", "{}", '{"order_id": "o-1"}'):  # missing base_url too
        run_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(run_dir, "control"), exist_ok=True)
        with open(os.path.join(run_dir, "control", "studio-order.json"), "w", encoding="utf-8") as f:
            f.write(body)
        try:
            CS.send("studio", run_dir=run_dir, stage="script", version=1, text="t",
                    sink=lambda *a: None)
        except CS.ChannelError:
            pass
        else:
            raise AssertionError("a broken studio-order.json published: %r" % body)


def test_gate_still_stops_a_studio_send():
    bridge = _FakeBridge()
    run_dir = _studio_run()
    try:
        CS.send("studio", run_dir=run_dir, stage="song", version=1, text="t",
                sink=bridge.publish,
                gate=lambda _: {"reason_code": "SONG_PICK_MISSING", "detail": "no pick yet"})
    except CS.SendRefused as e:
        assert "no pick yet" in str(e), e
    else:
        raise AssertionError("a refusing gate did not stop the studio publish")
    assert bridge.calls == [], bridge.calls            # nothing published


def test_unknown_channel_is_still_refused():
    try:
        CS.send("email", "555", "hi", sink=lambda a: None)
    except CS.ChannelError:
        pass
    else:
        raise AssertionError("an unknown channel was accepted")


def test_app_channel_never_touches_the_studio():
    """A normal-channel send on the SAME run dir stays a Telegram argv send."""
    seen = []
    run_dir = _studio_run()
    argv = CS.send("app", "555", "hi", sink=seen.append, run_dir=run_dir)
    assert argv[:4] == ["openclaw", "message", "send", "--channel"], argv
    assert len(seen) == 1


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

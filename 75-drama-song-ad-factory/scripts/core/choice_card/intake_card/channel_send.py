#!/usr/bin/env python3
"""channel_send: ONE channel-neutral send path (U11).

app, terminal and storyboard are delivery CHANNELS, not three senders: each is
``send()`` bound to its own name, so all three reach the SAME code path and the
send rules can never drift between them::

    from choice_card.intake_card import channel_send as CS
    CS.CHANNEL_SEND["app"].func is CS.send          # True
    CS.CHANNEL_SEND["terminal"].func is CS.send     # True
    CS.CHANNEL_SEND["storyboard"].func is CS.send   # True

Delivery reuses the skill's EXISTING send (``intake_card.openclaw_send_argv`` --
the same ``openclaw message send`` argv the choice card and the storyboard
approval runner already build) and the existing gates: pass ``gate=`` a callable
that returns a refusal dict (e.g. ``song_pick_gate``, which is
``song_choices.refusal``) and a refusal STOPS the send with a non-zero exit. No
gate is re-implemented, weakened or bypassed.

``device_notice()`` is the only notice sent to the client's device and it
happens ONLY when requested (``requested=True``). Unsolicited -> nothing is
sent. One nudge, then silence: with a run_dir the nudge is recorded and every
later call is a no-op, so the client is never spammed.

Stdlib only. The sink is injected (default: run the argv), so tests send
nowhere.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import subprocess
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

CHANNELS = ("app", "terminal", "storyboard")
#: The device notice rides the app channel (the device is where the client reads it).
NOTICE_CHANNEL = "app"
#: Refused send: the same exit code the skill's existing gates already use.
REFUSED_EXIT = 5


class ChannelError(ValueError):
    """An unknown channel name. Loud, never a silent send on a wrong channel."""


class SendRefused(Exception):
    """The gate refused the send; nothing was sent. ``refusal`` is the gate's dict."""

    def __init__(self, refusal):
        super().__init__(_refusal_text(refusal))
        self.refusal = refusal


def _refusal_text(refusal):
    if isinstance(refusal, dict):
        return refusal.get("detail") or refusal.get("reason_code") or json.dumps(refusal)
    return str(refusal)


def _run_send(argv):
    subprocess.run(argv, check=True, capture_output=True)


def _require_channel(channel):
    if channel not in CHANNELS:
        raise ChannelError("unknown channel %r; channels are %s" % (channel, ", ".join(CHANNELS)))


def song_pick_gate(run_dir):
    """The EXISTING send gate, reused: ``song_choices.refusal``. None when the
    client has picked (nothing blocks), else its refusal dict."""
    from song_choices import song_choices as SC   # noqa: PLC0415
    return SC.refusal(run_dir)


def send(channel, target, text, media=(), sink=None, gate=None, gate_input=None):
    """THE channel-neutral send. Runs the gate FIRST (a refusal raises
    :class:`SendRefused` before anything is built or sent), then builds the
    existing openclaw argv and hands it to the sink (default: run it).
    Returns the argv."""
    _require_channel(channel)
    if gate is not None:
        refusal = gate(gate_input)
        if refusal:
            raise SendRefused(refusal)
    from choice_card.intake_card import intake_card as IC   # noqa: PLC0415
    argv = IC.openclaw_send_argv(target, text, media=list(media))
    (sink or _run_send)(argv)
    return argv


#: channel name -> send() bound to that channel. Every adapter shares one function.
CHANNEL_SEND = {c: functools.partial(send, c) for c in CHANNELS}


def _notice_path(run_dir):
    return os.path.join(run_dir, "control", "device-notice.json")


def _already_noticed(run_dir):
    try:
        with open(_notice_path(run_dir), encoding="utf-8") as f:
            return bool(json.load(f).get("sent"))
    except (OSError, ValueError):
        return False


def _record_notice(run_dir):
    os.makedirs(os.path.join(run_dir, "control"), exist_ok=True)
    with open(_notice_path(run_dir), "w", encoding="utf-8") as f:
        json.dump({"sent": True}, f, indent=2, sort_keys=True)


def device_notice(target, text, requested=False, run_dir=None, sink=None):
    """A notice to the client's device, ONLY when requested.

    ``requested`` False -> NO notice is sent; returns None (never unsolicited).
    With a run_dir, the one nudge is recorded and every later call is silent
    (one nudge, then silence). Returns the argv when it sends, else None."""
    if not requested:
        return None
    if run_dir and _already_noticed(run_dir):
        return None
    argv = CHANNEL_SEND[NOTICE_CHANNEL](target, text, sink=sink)
    if run_dir:
        _record_notice(run_dir)
    return argv


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="One channel-neutral send path for app, terminal and storyboard.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("--channel", choices=CHANNELS, required=True)
    s.add_argument("--target", required=True)
    s.add_argument("--message", required=True)
    s.add_argument("--media", action="append", default=[])
    s.add_argument("--run-dir", default="",
                   help="consult the existing song-pick gate before sending")
    n = sub.add_parser("notice")
    n.add_argument("--target", required=True)
    n.add_argument("--message", required=True)
    n.add_argument("--run-dir", default="")
    n.add_argument("--requested", action="store_true",
                   help="the client asked for the notice; without it NOTHING is sent")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "send":
            gate = song_pick_gate if a.run_dir else None
            print(json.dumps(send(a.channel, a.target, a.message, media=a.media,
                                  gate=gate, gate_input=a.run_dir)))
        else:
            nargv = device_notice(a.target, a.message, requested=a.requested,
                                  run_dir=a.run_dir or None)
            print(json.dumps(nargv) if nargv else
                  "no notice sent (not requested, or already sent)")
    except SendRefused as e:
        sys.stderr.write("REFUSED: %s\n" % e)
        return REFUSED_EXIT
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

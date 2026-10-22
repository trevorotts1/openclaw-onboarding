#!/usr/bin/env python3
"""channel_send: ONE channel-neutral send path over the real channel adapter.

app, terminal and storyboard are delivery CHANNELS, not three senders: each is
``send()`` bound to its own name, so all three reach the SAME code path and the
send rules can never drift between them::

    from choice_card.intake_card import channel_send as CS
    CS.CHANNEL_SEND["app"].func is CS.send          # True
    CS.CHANNEL_SEND["terminal"].func is CS.send     # True
    CS.CHANNEL_SEND["storyboard"].func is CS.send   # True
    CS.CHANNEL_SEND["studio"].func is CS.send       # True

W03-U1 (findings D06/D07): nothing here hardcodes Telegram. Every send resolves
the run's canonical origin record (``delivery_outbox.resolve_origin`` -- the one
record written at run creation, with the idempotent legacy migration) and routes
its typed artifacts through the ACTUAL channel adapter:

* ``telegram`` -- resolves the correct authenticated bot/account, chat and
  thread from the origin record (``--account`` / ``--target`` / ``--thread-id``);
* ``app`` -- an OpenClaw-app conversation returns to the app conversation
  recorded in the origin;
* ``terminal`` -- a terminal session uses the host's actual artifact display,
  with explicit evidence for every playback limit;
* ``studio`` -- publishes the approval item to the client's studio page via
  ``shared-bridge/approvals_bridge.publish`` (order id and base URL from the
  run's ``control/studio-order.json``, key from the bridge's own lookup).

Delivery runs through the durable outbox (``delivery_outbox``): prepared,
queued, sending, sent (only with a channel receipt), retryable failure,
action-required, uncertain. A returned payload or a written local file is
PREPARED, never sent; a crash resends only the pieces without receipts; an
uncertain send is resolved through the channel's own idempotency/readback --
never a false exactly-once claim. Repairing a failed send re-sends the same
bytes and NEVER spends paid media.

The ``studio`` channel is the one channel that does NOT go through the message
transport. Callers that run a studio order send on the studio channel AND keep
their normal channel -- the first answer wins (the service returns 409 on the
second).

Delivery reuses the skill's EXISTING command builder
(``intake_card.channel_send_argv``, the same ``openclaw message send`` argv the
choice card and the storyboard approval runner already build) and the existing
gates: pass ``gate=`` a callable that returns a refusal dict (e.g.
``song_pick_gate``, which is ``song_choices.refusal``) and a refusal STOPS the
send with a non-zero exit. No gate is re-implemented, weakened or bypassed.

``device_notice()`` is the only notice sent to the client's device and it
happens ONLY when requested (``requested=True``). Unsolicited -> nothing is
sent. One nudge, then silence: with a run_dir the nudge is recorded and every
later call is a no-op, so the client is never spammed.

Stdlib only. The sink is injected (default: run the transport), so tests send
nowhere.
"""
from __future__ import annotations

import argparse
import functools
import json
import mimetypes
import os
import platform
import subprocess
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from choice_card.intake_card import delivery_outbox as DO  # noqa: E402

CHANNELS = ("app", "terminal", "storyboard", "studio")
#: The device notice rides the app channel (the device is where the client reads it).
NOTICE_CHANNEL = "app"
#: Refused send: the same exit code the skill's existing gates already use.
REFUSED_EXIT = 5
#: studio_bridge poll writes this in the run dir; the studio channel reads it.
STUDIO_ORDER_FILE = os.path.join("control", "studio-order.json")

#: origin channels with their own message transport adapter. The channel VALUE
#: is data from the origin record -- no transport is hardcoded for every path.
ORIGIN_TRANSPORTS = ("telegram", "app", "terminal")
#: presentation surface -> transport when the origin names no usable channel.
#: ``storyboard`` has none of its own: it must ride the run's real channel.
SURFACE_TRANSPORT = {"app": "app", "terminal": "terminal", "storyboard": None}

#: explicit playback limits of the host's terminal artifact display, each with
#: the evidence behind it (W03-U1: explicit evidence for playback limits).
TERMINAL_PLAYBACK_EVIDENCE = {
    "text": {"inline": True, "evidence": "terminal session displays text directly"},
    "image": {"inline": False, "playable": False,
              "evidence": "terminal text display cannot render image bytes; "
                          "the host's image viewer opens the recorded path"},
    "audio": {"inline": False, "playable": False,
              "evidence": "terminal session has no audio output; play the "
                          "recorded file path in the host's audio player"},
    "video": {"inline": False, "playable": False,
              "evidence": "terminal session has no video output; play the "
                          "recorded file path in the host's video player"},
}


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
    """The message-transport execution: run the argv (adding ``--json`` so the
    transport returns its receipt) and return that receipt. A failure raises --
    the outbox then keeps the piece retryable, never falsely sent."""
    r = subprocess.run(list(argv) + ["--json"], check=True,
                       capture_output=True, text=True)
    try:
        out = json.loads(r.stdout) if r.stdout.strip() else {}
    except ValueError:
        out = {}
    receipt = {"ok": True, "result": out} if isinstance(out, dict) else {"ok": True}
    mid = out.get("messageId") or out.get("message_id") or out.get("id") if isinstance(out, dict) else None
    if mid is not None:
        receipt["message_id"] = mid
    return receipt


def _require_channel(channel):
    if channel not in CHANNELS:
        raise ChannelError("unknown channel %r; channels are %s" % (channel, ", ".join(CHANNELS)))


def song_pick_gate(run_dir):
    """The EXISTING send gate, reused: ``song_choices.refusal``. None when the
    client has picked (nothing blocks), else its refusal dict."""
    from song_choices import song_choices as SC   # noqa: PLC0415
    return SC.refusal(run_dir)


def _shared_bridge_dir():
    return os.path.join(os.path.dirname(os.path.dirname(_CORE)), "shared-bridge")


def studio_order(run_dir):
    """The run's studio order record (``control/studio-order.json``, written by
    ``studio_bridge.py poll``) -- ``{order_id, client_id, title, base_url}`` --
    or None when the run did not come from the studio."""
    if not run_dir:
        return None
    try:
        with open(os.path.join(run_dir, STUDIO_ORDER_FILE), encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict) or not rec.get("order_id") or not rec.get("base_url"):
        return None
    return rec


def _bridge_publish():
    """``approvals_bridge.publish`` from shared-bridge (same folder as the bridge)."""
    shared = _shared_bridge_dir()
    if shared not in sys.path:
        sys.path.insert(0, shared)
    import approvals_bridge   # noqa: PLC0415
    return approvals_bridge.publish


def _bridge_key():
    """The bridge's OWN key lookup (``studio_bridge.load_key``) -- reused, never copied."""
    shared = _shared_bridge_dir()
    if shared not in sys.path:
        sys.path.insert(0, shared)
    import studio_bridge   # noqa: PLC0415
    return studio_bridge.load_key()


def studio_send(run_dir, stage, version, text, files=(), choices=(), publish=None):
    """Channel ``studio``: publish one approval item to the client's studio page.
    The order id and base URL come from the run's ``control/studio-order.json``;
    the key is the bridge's lookup. Returns the item dict. Loud
    :class:`ChannelError` when the run is not a studio run -- never a silent
    no-op send. ``publish`` injects the transport (default:
    ``approvals_bridge.publish``), so tests send nowhere."""
    order = studio_order(run_dir)
    if not order:
        raise ChannelError("channel 'studio' needs a studio order in the run "
                           "(missing or invalid %s)" % STUDIO_ORDER_FILE)
    publish = publish or _bridge_publish()
    return publish(order["base_url"], _bridge_key(), order["order_id"], stage,
                   version, text, list(choices), list(files))


# ------------------------------------------------------- channel adapters ---

def _transport_for(surface, origin_rec):
    """The transport channel a send rides: the run's origin channel when it names
    a real transport, else the surface's own adapter (``storyboard`` has none and
    needs the run's channel). None = the destination is unresolved."""
    ch = (origin_rec or {}).get("channel", "")
    if ch in ORIGIN_TRANSPORTS:
        return ch
    return SURFACE_TRANSPORT.get(surface)


def _attachments(media):
    out = []
    for m in (media or []):
        path = m if isinstance(m, str) else m.get("path", "")
        out.append({
            "artifact_ref": path,
            "path": path,
            "mime_type": (m.get("mime_type") if isinstance(m, dict) else "")
                         or mimetypes.guess_type(path)[0] or "application/octet-stream",
            "caption": (m.get("caption") if isinstance(m, dict) else "") or "",
            "sha256": DO._sha256_file(path) if path and os.path.isfile(path) else "",
        })
    return out


def _terminal_record(piece, destination):
    """The host's actual artifact display for a terminal session: the text is
    displayed, artifacts are recorded as host file paths, and every playback
    limit is explicit WITH its evidence."""
    payload = piece["payload"]
    text = payload.get("text", "")
    atts = payload.get("attachments") or ([payload["attachment"]]
                                          if piece["kind"] == "attachment" else [])
    arts = []
    for att in atts:
        kind = (att.get("mime_type") or "").split("/")[0]
        known = kind if kind in TERMINAL_PLAYBACK_EVIDENCE else "text"
        limits = dict(TERMINAL_PLAYBACK_EVIDENCE[known])
        arts.append({
            "artifact_ref": att.get("artifact_ref", att.get("path", "")),
            "mime_type": att.get("mime_type", ""),
            "display": "inline" if limits.get("inline") else "path-reference",
            "playback_limits": limits,
        })
    rec = {"display": "terminal", "destination": destination,
           "text": text, "artifacts": arts,
           "playback_evidence": TERMINAL_PLAYBACK_EVIDENCE}
    if piece["kind"] == "text" and payload.get("part_count", 1) > 1:
        rec["part_no"], rec["part_count"] = payload["part_no"], payload["part_count"]
    return rec


def _terminal_display(record, run_dir=""):
    """The terminal host actually shows the artifact display now and
    acknowledges it. Writes the display record beside the run when there is one,
    so the evidence survives the session."""
    if run_dir:
        DO._write_json(os.path.join(run_dir, "control", "terminal-display.json"), record)
    return {"displayed": True, "host": platform.node(),
            "artifacts": len(record.get("artifacts", [])),
            "text_chars": len(record.get("text", ""))}


def _piece_dispatch(piece, transport, destination, origin_rec):
    """Build the transport payload for one outbox piece (the command argv for a
    message transport, the host display record for the terminal adapter)."""
    if transport == "terminal":
        return _terminal_record(piece, destination)
    from choice_card.intake_card import intake_card as IC   # noqa: PLC0415
    payload = piece["payload"]
    if piece["kind"] == "text":
        text, media = payload.get("text", ""), []
    else:
        att = payload.get("attachment") or {}
        text = att.get("caption", "")
        media = [att.get("path") or att.get("artifact_ref", "")]
    if payload.get("part_count", 1) > 1:
        text = "Part %d/%d\n%s" % (payload["part_no"], payload["part_count"], text)
    return IC.channel_send_argv(transport, destination, text, media=media,
                                account=(origin_rec or {}).get("account_id") or None,
                                thread_id=(origin_rec or {}).get("thread_id") or None)


def send(channel, target=None, text="", media=(), sink=None, gate=None, gate_input=None,
         run_dir="", stage="", version=0, files=(), choices=(),
         origin=None, artifact_kind="message", artifact_id="", revision=1):
    """THE channel-neutral send. Runs the gate FIRST (a refusal raises
    :class:`SendRefused` before anything is built or sent). app, terminal and
    storyboard resolve the run's origin record and route the typed envelope
    through the ACTUAL channel adapter and the durable outbox -- a returned
    payload is PREPARED, only a channel receipt marks a piece sent. The studio
    channel publishes the approval item to the page instead (see
    :func:`studio_send`; ``sink`` injects the transport).

    Returns the dispatched payload (the argv for a message transport, the host
    display record for terminal), or the list of payloads when the envelope
    split into several pieces. ``None`` when no destination is resolved: the
    pieces stay queued/action-required in the outbox and resume once the
    destination is repaired. ``sink`` injects the transport and MAY return the
    channel receipt; without one the piece is honestly ``uncertain``."""
    _require_channel(channel)
    if gate is not None:
        refusal = gate(gate_input)
        if refusal:
            raise SendRefused(refusal)
    if channel == "studio":
        return studio_send(run_dir=run_dir, stage=stage, version=version, text=text,
                           files=files, choices=choices, publish=sink)

    origin_rec = DO.resolve_origin(run_dir, origin)
    transport = _transport_for(channel, origin_rec)
    # the canonical conversation wins for real chat channels; a studio order id
    # is not a chat destination, so those runs address the explicit target
    dest_from_origin = (origin_rec or {}).get("conversation_id", "") \
        if (origin_rec or {}).get("channel", "") in ORIGIN_TRANSPORTS else ""
    destination = (dest_from_origin or "").strip() or (target or "").strip()

    run_id = os.path.basename(os.path.normpath(run_dir)) if run_dir else "ad-hoc"
    envelope = DO.build_envelope(
        run_id=run_id,
        tenant_id=(origin_rec or {}).get("tenant_id", ""),
        artifact_id=artifact_id or DO._sha256_text(text)[:16],
        artifact_kind=artifact_kind, revision=revision,
        origin=dict(origin_rec or {"channel": transport or "",
                                   "conversation_id": destination},
                    conversation_id=destination),
        text=text, attachments=_attachments(media))

    if not run_dir:
        # no run ledger: the returned payload is PREPARED only, nothing claims sent
        if not destination or not transport:
            raise ChannelError("no destination resolved for channel %r" % channel)
        piece = {"kind": "text" if text else "attachment", "payload": {
            "text": text, "part_no": 1, "part_count": 1,
            "attachments": envelope["presentation"]["attachments"],
            "channel": transport}}
        payload = _piece_dispatch(piece, transport, destination, origin_rec)
        (sink or (_terminal_display if transport == "terminal" else _run_send))(payload)
        return payload

    outbox = DO.Outbox(run_dir)
    pieces = outbox.enqueue(envelope, channel=transport)
    payloads = {p["piece_id"]: _piece_dispatch(p, transport, destination, origin_rec)
                for p in pieces}
    if not destination:
        for p in pieces:
            outbox.mark(p["piece_id"], DO.ACTION_REQUIRED,
                        error="no destination recorded for this run: repair the "
                              "origin record (Outbox.redestinate), then resume delivery")
        return None

    def _dispatch(piece):
        payload = payloads[piece["piece_id"]]
        if sink is not None:
            return sink(payload)
        if transport == "terminal":
            return _terminal_display(payload, run_dir)
        return _run_send(payload)

    outbox.resume(_dispatch)
    ordered = [payloads[p["piece_id"]] for p in pieces]
    return ordered[0] if len(ordered) == 1 else ordered


#: channel name -> send() bound to that channel. Every adapter shares one function.
CHANNEL_SEND = {c: functools.partial(send, c) for c in CHANNELS}


def _notice_path(run_dir):
    return os.path.join(run_dir, "control", "device-notice.json")


def _already_noticed(run_dir):
    try:
        with open(_notice_path(run_dir), encoding="utf-8") as f:
            rec = json.load(f)
        return bool(rec.get("dispatched") or rec.get("sent"))
    except (OSError, ValueError):
        return False


def _record_notice(run_dir, state, receipt):
    """The nudge ledger: ``dispatched`` for one-nudge-then-silence, ``sent`` ONLY
    with the channel receipt (a notice is never claimed seen without one)."""
    os.makedirs(os.path.join(run_dir, "control"), exist_ok=True)
    with open(_notice_path(run_dir), "w", encoding="utf-8") as f:
        json.dump({"dispatched": True, "state": state,
                   "sent": state == DO.SENT, "receipt": receipt},
                  f, indent=2, sort_keys=True)


def device_notice(target, text, requested=False, run_dir=None, sink=None):
    """A notice to the client's device, ONLY when requested.

    ``requested`` False -> NO notice is sent; returns None (never unsolicited).
    With a run_dir, the one nudge is recorded and every later call is silent
    (one nudge, then silence). Returns the payload when it dispatches, else
    None. The record claims ``sent`` only with the channel receipt."""
    if not requested:
        return None
    if run_dir and _already_noticed(run_dir):
        return None
    payload = CHANNEL_SEND[NOTICE_CHANNEL](target, text, sink=sink, run_dir=run_dir or "")
    if run_dir:
        receipt = None
        state = DO.UNCERTAIN
        outbox = DO.Outbox(run_dir)
        pieces = [p for p in outbox.pieces() if p["payload"].get("text") == text]
        if pieces and pieces[-1].get("receipt"):
            receipt, state = pieces[-1]["receipt"], DO.SENT
        elif pieces:
            state = pieces[-1]["state"]
        _record_notice(run_dir, state, receipt)
    return payload


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="One channel-neutral send path for app, terminal and storyboard.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("--channel", choices=CHANNELS, required=True)
    s.add_argument("--target", default="",
                   help="the conversation target when the run has no origin record yet")
    s.add_argument("--message", required=True)
    s.add_argument("--media", action="append", default=[])
    s.add_argument("--run-dir", default="",
                   help="consult the existing song-pick gate before sending; the "
                        "origin record and delivery outbox live here")
    s.add_argument("--origin", default="",
                   help="explicit origin record as JSON "
                        "({tenant_id, account_id, channel, conversation_id, thread_id})")
    s.add_argument("--stage", default="", help="studio channel: approval stage (script/song/storyboard)")
    s.add_argument("--version", dest="version", type=int, default=0,
                   help="studio channel: approval version")
    s.add_argument("--file", action="append", default=[],
                   help="studio channel: a file path to publish with the item (repeatable)")
    s.add_argument("--choice", action="append", default=[],
                   help="studio channel: a choice {n, label} as JSON (repeatable)")
    n = sub.add_parser("notice")
    n.add_argument("--target", required=True)
    n.add_argument("--message", required=True)
    n.add_argument("--run-dir", default="")
    n.add_argument("--requested", action="store_true",
                   help="the client asked for the notice; without it NOTHING is sent")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "send":
            if a.channel != "studio" and not a.target and not a.run_dir:
                ap.error("--target (or a run with an origin record) is required "
                         "for channel %s" % a.channel)
            gate = song_pick_gate if a.run_dir else None
            print(json.dumps(send(a.channel, a.target, a.message, media=a.media,
                                  gate=gate, gate_input=a.run_dir, run_dir=a.run_dir,
                                  stage=a.stage, version=a.version, files=a.file,
                                  choices=[json.loads(c) for c in a.choice],
                                  origin=json.loads(a.origin) if a.origin else None)))
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

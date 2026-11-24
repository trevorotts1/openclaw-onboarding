"""3D.7 client delivery checklist (N-56).

Before anything is sent to a client, every one of these is true AND
recorded. ``evaluate(record)`` answers the six items from the delivery
record and refuses (``pass`` False) when any is not recorded true:

  1. the master passed the delivery check (audio present, full length, not
     silent -- N-33);
  2. the shared-drive link is "anyone with the link can edit", read back
     from the drive after it was set;
  3. the message text was passed to the sending tool from a file, never
     typed inline;
  4. every channel id is confirmed against the client's own records;
  5. a fix replaces the file behind the existing link; the link never
     changes;
  6. no client's file, link or channel is used for another client.

Each row carries its 3J level for the receipt; item 1 is MAJOR item 14, the
rest are MEDIUM at most. The checklist still refuses until all six are true
(3D.7 is binding). Stdlib only.
"""
from __future__ import annotations

from pathlib import Path

from delivery_checklist import severity as SEV

TOOL_NAME = "client_delivery_checklist"
TOOL_VERSION = "1.0.0"

MASTER = "MASTER_CHECK"
LINK = "SHARE_LINK"
MESSAGE = "MESSAGE_FROM_FILE"
CHANNELS = "CHANNELS_CONFIRMED"
REPLACE = "SAME_LINK_REPLACED"
CROSS = "NO_COPY_ACROSS_CLIENTS"
ITEMS = (MASTER, LINK, MESSAGE, CHANNELS, REPLACE, CROSS)

CLIENT_MASTER_NOT_PASS = "CLIENT_MASTER_NOT_PASS"
CLIENT_LINK_NOT_EDITABLE = "CLIENT_LINK_NOT_EDITABLE"
CLIENT_LINK_NOT_READ_BACK = "CLIENT_LINK_NOT_READ_BACK"
CLIENT_MESSAGE_INLINE = "CLIENT_MESSAGE_TYPED_INLINE"
CLIENT_MESSAGE_FILE_MISSING = "CLIENT_MESSAGE_FILE_MISSING"
CLIENT_CHANNEL_UNCONFIRMED = "CLIENT_CHANNEL_UNCONFIRMED"
CLIENT_LINK_CHANGED = "CLIENT_LINK_CHANGED"
CLIENT_CROSS_CLIENT = "CLIENT_CROSS_CLIENT"

def _row(item, ok, code, detail, level=None):
    return {"item": item, "ok": bool(ok),
            "severity": level or (SEV.MAJOR if item == MASTER else SEV.MEDIUM),
            "code": None if ok else code, "detail": detail}

def _item_master(record):
    got = record.get("master_check")
    verdict = (got or {}).get("verdict") if isinstance(got, dict) else got
    return _row(MASTER, verdict == "PASS", CLIENT_MASTER_NOT_PASS,
                "delivery check verdict is %r" % (verdict,))

def _item_link(record):
    link = record.get("share_link")
    link = link if isinstance(link, dict) else {}
    read_back = link.get("read_back")
    read_back = read_back if isinstance(read_back, dict) else {}
    if link.get("can_edit") is not True:
        return _row(LINK, False, CLIENT_LINK_NOT_EDITABLE,
                    "link is not set to anyone-with-the-link-can-edit")
    if read_back.get("can_edit") is not True \
            or read_back.get("url") != link.get("url"):
        return _row(LINK, False, CLIENT_LINK_NOT_READ_BACK,
                    "the edit setting was not read back from the drive")
    return _row(LINK, True, None, "edit link read back from the drive")

def _item_message(record):
    message = record.get("message")
    message = message if isinstance(message, dict) else {}
    if message.get("inline_text"):
        return _row(MESSAGE, False, CLIENT_MESSAGE_INLINE,
                    "message text was typed inline, not passed from a file")
    path = message.get("file")
    if not (isinstance(path, str) and path and Path(path).is_file()):
        return _row(MESSAGE, False, CLIENT_MESSAGE_FILE_MISSING,
                    "no message file was passed to the sending tool")
    return _row(MESSAGE, True, None, "message passed from %s" % path)

def _item_channels(record):
    channels = record.get("channels") or []
    bad = [c for c in channels
           if not (isinstance(c, dict) and c.get("confirmed") is True)]
    if not channels or bad:
        return _row(CHANNELS, False, CLIENT_CHANNEL_UNCONFIRMED,
                    "%d channel id(s) unconfirmed" % (len(bad) or 1))
    return _row(CHANNELS, True, None,
                "%d channel id(s) confirmed" % len(channels))

def _item_replace(record):
    replace = record.get("replace")
    replace = replace if isinstance(replace, dict) else {}
    if replace.get("same_link") is not True or \
            replace.get("url") != (record.get("share_link") or {}).get("url"):
        return _row(REPLACE, False, CLIENT_LINK_CHANGED,
                    "a fix did not replace the file behind the same link")
    return _row(REPLACE, True, None, "fix replaces the file behind the link")

def _item_cross(record):
    client = record.get("client_id")
    used = list(record.get("uses") or [])
    bad = [u for u in used
           if not (isinstance(u, dict) and client
                   and u.get("client_id") == client)]
    if not client or bad:
        return _row(CROSS, False, CLIENT_CROSS_CLIENT,
                    "%d item(s) belong to another client or have no client"
                    % (len(bad) or 1))
    return _row(CROSS, True, None,
                "every file, link and channel belongs to the one client")

def evaluate(record):
    """The six-item checklist. ``pass`` only when all six are recorded true.

    Returns {"pass", "rows", "medium", "major", "verdict"}; every row keeps
    its level so the receipt lists each MEDIUM.
    """
    record = record if isinstance(record, dict) else {}
    rows = [_item_master(record), _item_link(record), _item_message(record),
            _item_channels(record), _item_replace(record),
            _item_cross(record)]
    failing = [r for r in rows if not r["ok"]]
    return {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "pass": not failing, "verdict": "PASS" if not failing else "FAIL",
            "rows": rows,
            "major": [r for r in rows if r["severity"] == SEV.MAJOR],
            "medium": [r for r in failing if r["severity"] == SEV.MEDIUM],
            "detail": "; ".join("%s: %s" % (r["code"], r["detail"])
                                for r in failing) or "all six recorded true"}

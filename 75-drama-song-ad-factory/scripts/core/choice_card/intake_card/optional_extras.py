#!/usr/bin/env python3
"""optional_extras: the U10 version-2 OPTIONAL extras (Telegram button / card
link / measurement view), native fields first, OFF by default.

Joint plan section 5, row **U10 extras** — verbatim scope: *"Optional Telegram
button/card link/measurement view, native fields first"*. Version table line
832: *"Optional web push U20 and optional U10 extras: Telegram button, Open in
Drama Studio card link, measurement view ... none blocks version 0"*.

This unit only ADDS an optional surface on top of the existing message, card
and status patterns. It never re-implements one:

* **Telegram button** — the native Bot API field, ``reply_markup`` with an
  ``inline_keyboard`` of one ``{text, url}`` button, appended to the payload
  the existing message pattern already builds (``intake_card.telegram_payload``).
* **Card link** — one ``Open in Drama Studio: <url>`` line appended to the
  card text the existing card pattern renders; the URL is read from the
  card's OWN native ``studio_url`` field first, the environment only as a
  fallback.
* **Measurement view** — a compact text view over the status counts a caller
  ALREADY has (the existing status pattern). It adds no store, no page, no
  scheduler and no network call; it renders existing counts or nothing.

Everything defaults OFF. :func:`extras_enabled` is true only for the exact
on-values ``"true"`` / ``"1"`` (unset, empty, ``"false"``, ``"yes"``, ``"TRUE"``
all stay off). With extras off every function returns its input UNCHANGED and
nothing is added, so the required version-0 delivery — the client-owned
GHL-first verified video link (``mini-app/video-link-delivery``) and every
required message/card/status path — is byte-identical. This module imports
nothing from that path and touches no credential.

A caller that DEMANDS an extra while extras are off gets a refusal with the
named code :data:`DISABLED_CODE` and zero side effects (never a silent send).

Stdlib only. No network.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

#: The one switch. OFF unless the exact on-values below are set.
EXTRAS_ENV = "DS_EXTRAS_ENABLED"
#: Where the Drama Studio link comes from when the card carries no native field.
STUDIO_URL_ENV = "DS_STUDIO_URL"
#: Named refusal code, same shape U20 uses for its own optional surface.
DISABLED_CODE = "AF-DS-EXTRAS-DISABLED"
#: The exact on-values; everything else is OFF.
ON_VALUES = ("true", "1")

CARD_LINK_LABEL = "Open in Drama Studio"
BUTTON_LABEL = "Open in Drama Studio"
#: Refused exit code, the same non-zero exit the skill's other gates use.
REFUSED_EXIT = 4

class ExtrasRefused(Exception):
    """A caller demanded an extra while extras are OFF; nothing was added."""

    def __init__(self, refusal):
        super().__init__(refusal["detail"])
        self.refusal = refusal

def extras_enabled(env=None):
    """True only for the exact on-values ``"true"`` / ``"1"``.

    Unset, empty, ``"false"``, ``"yes"``, ``"TRUE"`` and anything else stay
    OFF. The value is read verbatim (no strip, no case-fold), the same
    discipline U20's ``pushEnabled`` uses.
    """
    env = os.environ if env is None else env
    return env.get(EXTRAS_ENV) in ON_VALUES

def extras_refusal(feature):
    """The named refusal for a demanded-but-off extra."""
    return {"code": DISABLED_CODE, "feature": feature,
            "detail": ("%s is off (%s is not one of %s); nothing was added"
                       % (feature, EXTRAS_ENV, "/".join(ON_VALUES)))}

def studio_url(card=None, env=None):
    """The Drama Studio URL: the card's own native ``studio_url`` first, the
    environment second, else None. Never invented."""
    url = (card or {}).get("studio_url")
    if url:
        return str(url)
    env = os.environ if env is None else env
    return env.get(STUDIO_URL_ENV) or None

def telegram_button(payload, url, label=BUTTON_LABEL, *, enabled=None,
                    env=None, require=False):
    """The existing message payload with the NATIVE Telegram button field.

    ``payload`` is what the message pattern already built (e.g.
    ``intake_card.telegram_payload(...)`` -> ``{"chat_id", "text"}``). With
    extras ON the native ``reply_markup.inline_keyboard`` field is added as a
    copy; with extras OFF (the default) the payload is returned unchanged.
    ``require=True`` refuses instead of returning when extras are off.
    """
    if not (extras_enabled(env) if enabled is None else bool(enabled)):
        if require:
            raise ExtrasRefused(extras_refusal("telegram button"))
        return dict(payload)
    if not url:            # extras ON but no URL: no button, never invented
        return dict(payload)
    out = dict(payload)
    out["reply_markup"] = {"inline_keyboard": [[{"text": str(label),
                                                "url": str(url)}]]}
    return out

def card_link(card, text, *, enabled=None, env=None, require=False,
              url=None):
    """The card text with one optional ``Open in Drama Studio`` line.

    The URL is the card's native ``studio_url`` first (see :func:`studio_url`).
    With extras OFF the text is returned unchanged; when ON but no URL is known
    the text is ALSO returned unchanged — a link is never invented.
    """
    if not (extras_enabled(env) if enabled is None else bool(enabled)):
        if require:
            raise ExtrasRefused(extras_refusal("card link"))
        return text
    link = url or studio_url(card, env)
    if not link:
        return text
    return "%s\n%s: %s" % (text, CARD_LINK_LABEL, link)

def measurement_view(status_counts, *, enabled=None, env=None, require=False,
                     release=None):
    """A compact view over status counts the caller ALREADY has, or None.

    ``status_counts`` is the existing status pattern's own mapping
    (``{"delivered": 3, "running": 1}``). With extras OFF this returns None
    (nothing is added, the existing status display is untouched); with extras
    ON it returns one line per status plus a total, derived only from the
    counts handed in. It reads no store and creates no page or dashboard.
    """
    if not (extras_enabled(env) if enabled is None else bool(enabled)):
        if require:
            raise ExtrasRefused(extras_refusal("measurement view"))
        return None
    counts = dict(status_counts or {})
    lines = ["Drama Studio status%s" % (" (%s)" % release if release else "")]
    total = 0
    for name in sorted(counts):
        try:
            n = int(counts[name])
        except (TypeError, ValueError):
            n = 0
        total += n
        lines.append("  %-12s %d" % (name + ":", n))
    lines.append("  %-12s %d" % ("total:", total))
    return "\n".join(lines)

def _message_module():
    """The EXISTING message pattern's module (``intake_card``), imported the
    way this file is reached (package, package-qualified, or a direct run)."""
    try:
        from . import intake_card as IC           # package-relative
        return IC
    except ImportError:
        try:
            from choice_card.intake_card import intake_card as IC  # core on path
            return IC
        except ImportError:
            import intake_card as IC               # direct run: own dir on path
            return IC

def _payload(args, env):
    """The CLI's one JSON object: envelope + the optional pieces."""
    enabled = extras_enabled(env)
    out = {"format": "optional-extras", "enabled": enabled,
           "unit": "U10-extras"}
    try:
        if args.command == "telegram":
            IC = _message_module()
            base = IC.telegram_payload(args.target, args.message)
            out["telegram"] = telegram_button(
                base, args.url or studio_url(None, env), args.label,
                enabled=enabled, require=args.require)
        elif args.command == "card":
            card = {}
            if args.card_json:
                card = json.loads(args.card_json)
            out["card_text"] = card_link(card, args.text, enabled=enabled,
                                         require=args.require, url=args.url)
        elif args.command == "measurement":
            counts = json.loads(args.counts or "{}")
            out["view"] = measurement_view(counts, enabled=enabled,
                                           require=args.require,
                                           release=args.release)
    except ExtrasRefused as e:
        return e.refusal, REFUSED_EXIT
    return out, 0

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Optional U10 extras (Telegram button / card link / "
                    "measurement view); OFF by default.")
    sub = ap.add_subparsers(dest="command", required=True)
    t = sub.add_parser("telegram")
    t.add_argument("--target", required=True)
    t.add_argument("--message", required=True)
    t.add_argument("--url", default=None, help="default: $%s" % STUDIO_URL_ENV)
    t.add_argument("--label", default=BUTTON_LABEL)
    t.add_argument("--require", action="store_true")
    c = sub.add_parser("card")
    c.add_argument("--text", required=True)
    c.add_argument("--card-json", default=None)
    c.add_argument("--url", default=None)
    c.add_argument("--require", action="store_true")
    m = sub.add_parser("measurement")
    m.add_argument("--counts", default=None, help="JSON status counts")
    m.add_argument("--release", default=None)
    m.add_argument("--require", action="store_true")
    args = ap.parse_args(argv)
    try:
        out, rc = _payload(args, os.environ)
    except Exception as e:                     # loud, never a half object
        sys.stderr.write("optional_extras: %s\n" % e)
        return 1
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return rc

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""profile_capability.py — T-22 operator CLI for the honest capability
declaration and the assisted placement contract.

Every answer comes from ONE source:
  35-social-media-planner/config/profile-capabilities.json

Usage:
  profile_capability.py capabilities [--channel CHANNEL] [--account-type TYPE]
  profile_capability.py request --channel facebook --account-type personal \
      --action post --placement placement.json [--unattended]
  profile_capability.py confirm --package package.json --operator "Trevor Otts" \
      [--confirmed-at ISO8601] [--out confirmed.json]
  profile_capability.py status --package package.json [--out status.json]
  profile_capability.py guard --record record.json

Exit codes:
  0  success / assisted placement prepared
  1  capability or usage error
  3  refused (unattended request on an assisted/unavailable capability)
  4  untruthful publication claim (guard failure)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.join(_HERE, "..", "..", "shared-utils")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import personal_profile_capability as ppc  # noqa: E402


def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _emit(data, out: str | None) -> None:
    text = json.dumps(data, indent=2, sort_keys=True)
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)


def _capabilities(args) -> int:
    summary = ppc.capability_summary()
    rows = summary["records"]
    if args.channel:
        rows = [r for r in rows if r["channel"] == args.channel.lower()]
    if args.account_type:
        rows = [r for r in rows if r["account_type"] == args.account_type.lower()]
    summary["records"] = rows
    summary["count"] = len(rows)
    _emit(summary, args.out)
    return 0


def _request(args) -> int:
    placement = _load_json(args.placement) if args.placement else None
    result = ppc.request_placement(
        args.channel,
        args.account_type,
        action=args.action,
        placement=placement,
        unattended=args.unattended,
    )
    _emit(result, args.out)
    return 3 if result.get("refused") else 0


def _confirm(args) -> int:
    package = _load_json(args.package)
    confirmed = ppc.record_operator_confirmation(
        package,
        args.operator,
        confirmed_at=args.confirmed_at,
        evidence=args.evidence,
    )
    _emit(ppc.status_surface(confirmed), args.out)
    return 0


def _status(args) -> int:
    _emit(ppc.status_surface(_load_json(args.package)), args.out)
    return 0


def _guard(args) -> int:
    try:
        ppc.assert_truthful_publication(_load_json(args.record))
    except ppc.UntruthfulPublication as exc:
        _emit({"ok": False, "guard": "untruthful-publication", "error": str(exc)}, args.out)
        return 4
    _emit({"ok": True, "guard": "untruthful-publication"}, args.out)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="write the JSON result to this path too")
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capabilities")
    cap.add_argument("--channel")
    cap.add_argument("--account-type")
    cap.set_defaults(func=_capabilities)

    req = sub.add_parser("request")
    req.add_argument("--channel", required=True)
    req.add_argument("--account-type", required=True)
    req.add_argument("--action", default="post")
    req.add_argument("--placement", help="JSON file with text, asset, keyword, cta, timing")
    req.add_argument("--unattended", action="store_true")
    req.set_defaults(func=_request)

    confirm = sub.add_parser("confirm")
    confirm.add_argument("--package", required=True)
    confirm.add_argument("--operator", required=True)
    confirm.add_argument("--confirmed-at")
    confirm.add_argument("--evidence")
    confirm.set_defaults(func=_confirm)

    status = sub.add_parser("status")
    status.add_argument("--package", required=True)
    status.set_defaults(func=_status)

    guard = sub.add_parser("guard")
    guard.add_argument("--record", required=True)
    guard.set_defaults(func=_guard)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ppc.UntruthfulPublication as exc:
        _emit({"ok": False, "error": str(exc)}, args.out)
        return 4
    except ppc.CapabilityError as exc:
        _emit({"ok": False, "error": str(exc)}, args.out)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

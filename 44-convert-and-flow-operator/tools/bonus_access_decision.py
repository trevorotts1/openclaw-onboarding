#!/usr/bin/env python3
"""bonus_access_decision.py — T-14 operator CLI for the bonus capability decision.

Every answer comes from ONE source:
  shared-utils/bonus/access_capability.py

This is the production call site for that module: without it the decision had
no consumer outside its own tests, so a green suite proved nothing about code
any operator could reach.

Usage:
  bonus_access_decision.py decision
  bonus_access_decision.py route
  bonus_access_decision.py evidence
  bonus_access_decision.py inventory-routes
  bonus_access_decision.py request [--assisted]
  bonus_access_decision.py plan --original-ready|--original-blocked --reason TEXT
  bonus_access_decision.py member-state --credential-state STATE --resource-authorized|--resource-denied

  bonus_access_decision.py access-authorize --member ID --identity S --grant S --credential S --sms S --resource S [--reason DIM=TEXT]
  bonus_access_decision.py access-bind --state F --member ID --channel sms|email --handle H
  bonus_access_decision.py access-fail --state F --member ID --dimension D --reason TEXT --channel sms|email --handle H
  bonus_access_decision.py access-defer --state F --member ID --email H
  bonus_access_decision.py access-resume --state F --channel sms|email --handle H --via sms_return|email

The access-* commands are the production call site for the T-15 adapter
(shared-utils/bonus/access_adapter.py): five separate authorizations, failed-step
resume, return access and email-later kept on the same member. The adapter's
ledger is in memory by design, so these commands own durability in the --state
JSON file and replay it through the adapter's public API on every invocation.
No vendor operation lives there either: T-14's decision is BLOCKED for every
automated route and the supported path is assisted.

Exit codes:
  0  success
  1  capability or usage error
  3  refused (unattended grant requested; the supported route is assisted)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, "..", "..", "shared-utils"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from bonus import access_capability as ac  # noqa: E402
from bonus import access_adapter as aa  # noqa: E402


def _emit(data) -> int:
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bonus membership/access capability decision (T-14).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("decision", help="the full machine-readable decision document")
    sub.add_parser("route", help="the supported route and the blocked steps")
    sub.add_parser("evidence", help="per-step state, provenance and missing evidence")
    sub.add_parser("inventory-routes", help="membership routes the shared GHL inventory offers")

    request = sub.add_parser("request", help="resolve a bonus access request")
    request.add_argument("--assisted", action="store_true",
                         help="ask for the assisted/operator route instead of an unattended grant")

    plan = sub.add_parser("plan", help="plan the original gift and the optional bonus lanes")
    ready = plan.add_mutually_exclusive_group(required=True)
    ready.add_argument("--original-ready", dest="original_ready", action="store_true")
    ready.add_argument("--original-blocked", dest="original_ready", action="store_false")
    plan.add_argument("--reason", default="", help="the original lane's own reason when not ready")
    plan.add_argument("--no-bonus", dest="bonus_requested", action="store_false")

    member = sub.add_parser("member-state", help="keep the credential and the resource apart")
    member.add_argument("--credential-state", required=True,
                        choices=list(ac.CREDENTIAL_STATES))
    resource = member.add_mutually_exclusive_group(required=True)
    resource.add_argument("--resource-authorized", action="store_true")
    resource.add_argument("--resource-denied", dest="resource_authorized", action="store_false")

    # -- T-15 access adapter plumbing ---------------------------------
    def _ledger_load(path):
        ledger = aa.AccessLedger()
        doc = {"bindings": [], "failures": [], "deferred": []}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            for key in doc:
                doc[key] = list(loaded.get(key, []))
            for row in doc["bindings"]:
                ledger.bind(member_id=row["member_id"], channel=row["channel"],
                            handle=row["handle"])
            for row in doc["failures"]:
                ledger.record_failed_step(member_id=row["member_id"],
                                          dimension=row["dimension"],
                                          reason=row["reason"],
                                          channel=row["channel"],
                                          handle=row["handle"])
            for row in doc["deferred"]:
                ledger.defer_to_email(member_id=row["member_id"], handle=row["handle"])
        return ledger, doc

    def _ledger_save(path, doc):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")

    access_auth = sub.add_parser("access-authorize",
                                 help="T-15: five separate authorizations for one member")
    access_auth.add_argument("--member", required=True)
    for _dim in aa.DIMENSIONS:
        access_auth.add_argument(f"--{_dim}", required=True,
                                 choices=[aa.AUTHORIZED, aa.DENIED, aa.UNVERIFIED])
    access_auth.add_argument("--reason", action="append", default=[], metavar="DIM=TEXT",
                             help="per-dimension reason, repeatable; never borrowed across dimensions")

    access_bind = sub.add_parser("access-bind",
                                 help="T-15: bind one channel handle to one member")
    access_bind.add_argument("--state", required=True, help="caller-owned JSON state file")
    access_bind.add_argument("--member", required=True)
    access_bind.add_argument("--channel", required=True, choices=list(aa.CHANNELS))
    access_bind.add_argument("--handle", required=True)

    access_fail = sub.add_parser("access-fail",
                                 help="T-15: record the failed step for a bound member")
    access_fail.add_argument("--state", required=True)
    access_fail.add_argument("--member", required=True)
    access_fail.add_argument("--dimension", required=True, choices=list(aa.DIMENSIONS))
    access_fail.add_argument("--reason", required=True)
    access_fail.add_argument("--channel", required=True, choices=list(aa.CHANNELS))
    access_fail.add_argument("--handle", required=True)

    access_defer = sub.add_parser("access-defer",
                                  help="T-15: email-later for the SAME member")
    access_defer.add_argument("--state", required=True)
    access_defer.add_argument("--member", required=True)
    access_defer.add_argument("--email", required=True)

    access_resume = sub.add_parser("access-resume",
                                   help="T-15: return access, resuming the failed step")
    access_resume.add_argument("--state", required=True)
    access_resume.add_argument("--channel", required=True, choices=list(aa.CHANNELS))
    access_resume.add_argument("--handle", required=True)
    access_resume.add_argument("--via", required=True, choices=list(aa.RETURN_VIAS))

    args = parser.parse_args(argv)

    try:
        if args.command == "decision":
            return _emit(ac.decision_document())
        if args.command == "route":
            return _emit(ac.supported_route())
        if args.command == "evidence":
            return _emit({
                "steps": ac.capability_evidence(),
                "blocked_steps": ac.blocked_steps(),
                "missing_evidence": ac.missing_evidence(),
            })
        if args.command == "inventory-routes":
            return _emit({"memberships": ac.membership_inventory_routes()})
        if args.command == "request":
            answer = ac.request_bonus_access(unattended=not args.assisted)
            _emit(answer)
            return 0 if answer.get("granted") or not answer.get("refused") else 3
        if args.command == "plan":
            plan_value = ac.plan_fulfillment(
                original_ready=args.original_ready,
                original_reason=args.reason,
                bonus_requested=args.bonus_requested,
            )
            ac.assert_original_not_gated_by_bonus(plan_value)
            return _emit(plan_value)
        if args.command == "member-state":
            return _emit(ac.resolve_member_state(
                credential_state=args.credential_state,
                resource_authorized=args.resource_authorized,
            ))
        if args.command == "access-authorize":
            reasons = {}
            for item in args.reason:
                dim, sep, text = item.partition("=")
                if not sep:
                    raise aa.AccessAdapterError("--reason takes DIM=TEXT")
                reasons[dim] = text
            answer = aa.authorize(
                member_id=args.member,
                states={d: getattr(args, d) for d in aa.DIMENSIONS},
                reasons=reasons or None,
            )
            return _emit(answer.as_dict())
        if args.command in ("access-bind", "access-fail", "access-defer", "access-resume"):
            ledger, doc = _ledger_load(args.state)
            if args.command == "access-bind":
                out = ledger.bind(member_id=args.member, channel=args.channel,
                                  handle=args.handle)
                doc["bindings"].append({"member_id": args.member,
                                        "channel": args.channel,
                                        "handle": args.handle})
            elif args.command == "access-fail":
                out = ledger.record_failed_step(member_id=args.member,
                                                dimension=args.dimension,
                                                reason=args.reason,
                                                channel=args.channel,
                                                handle=args.handle)
                doc["failures"].append({"member_id": args.member,
                                        "dimension": args.dimension,
                                        "reason": args.reason,
                                        "channel": args.channel,
                                        "handle": args.handle})
            elif args.command == "access-defer":
                out = ledger.defer_to_email(member_id=args.member, handle=args.email)
                doc["deferred"].append({"member_id": args.member, "handle": args.email})
            else:
                out = ledger.resume(channel=args.channel, handle=args.handle, via=args.via)
            _ledger_save(args.state, doc)
            return _emit(out)
    except (ac.BonusCapabilityError, aa.AccessAdapterError) as exc:
        print(json.dumps({"error": str(exc), "error_type": type(exc).__name__}, indent=2))
        return 1

    parser.error(f"unknown command {args.command!r}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

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
    except ac.BonusCapabilityError as exc:
        print(json.dumps({"error": str(exc), "error_type": type(exc).__name__}, indent=2))
        return 1

    parser.error(f"unknown command {args.command!r}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

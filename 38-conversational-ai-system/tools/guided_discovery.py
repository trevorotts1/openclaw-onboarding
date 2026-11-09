#!/usr/bin/env python3
"""Operator entry point for guided business, audience and offer discovery (T-06).

``acquisition_brief.py`` owns the brief, the interview and the binding contract;
it is a library with no entry point. This file is the production driver that
reaches those flows from the command line, and the one place outside the
library where the binding API is called: ``require_owner`` before anything is
read as plannable, and ``bind_owner`` / ``bind_approval`` / ``bind_capacity`` /
``bind_claims`` when the accountable owner answers. A refusal from the library
is printed and exits non-zero; nothing is guessed at or defaulted.

Run:
  python3 tools/guided_discovery.py <brief.json> next
  python3 tools/guided_discovery.py <brief.json> answer <fact_id> <value>
      [--provenance client_stated|discovered|assumed] [--source TEXT]
  python3 tools/guided_discovery.py <brief.json> bind owner <json-fields>
  python3 tools/guided_discovery.py <brief.json> bind approval <json-fields>
  python3 tools/guided_discovery.py <brief.json> bind capacity <json-fields>
  python3 tools/guided_discovery.py <brief.json> bind claims <json-fields>
  python3 tools/guided_discovery.py <brief.json> status
  python3 tools/guided_discovery.py <brief.json> ready

``<json-fields>`` is a JSON object literal (or ``@path`` for a file). Exit codes:
0 ok, 1 refused/invalid, 2 usage. Python 3 standard library only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import acquisition_brief as ab  # noqa: E402

BIND_COMMANDS = ("owner", "approval", "capacity", "claims")
PROVENANCES = (ab.PROVENANCE_CLIENT_STATED, ab.PROVENANCE_DISCOVERED, ab.PROVENANCE_ASSUMED)


def _usage() -> int:
    print(
        "usage: guided_discovery.py <brief.json> "
        "next|answer <fact_id> <value> [--provenance P] [--source S]|"
        "bind owner|approval|capacity|claims <json-fields>|status|ready"
    )
    return 2


def _json_fields(raw: str) -> dict:
    if raw.startswith("@"):
        with open(raw[1:], encoding="utf-8") as handle:
            text = handle.read()
    else:
        text = raw
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise ab.BindingError("fields are not valid JSON: %s" % exc)
    if not isinstance(value, dict):
        raise ab.BindingError("fields must be a JSON object of named fields")
    return value


def _bind(brief: ab.AcquisitionBrief, kind: str, fields: dict):
    if kind == "owner":
        return brief.bind_owner(
            fields.get("owner_id"),
            fields.get("name"),
            email=fields.get("email"),
            role=fields.get("role", "owner"),
            tenant_id=fields.get("tenant_id"),
        )
    if kind == "approval":
        return brief.bind_approval(
            fields.get("approved_by"),
            scope=fields.get("scope"),
            approved_at=fields.get("approved_at"),
        )
    if kind == "capacity":
        return brief.bind_capacity(
            fields.get("declared_by"),
            monthly_new_customers=fields.get("monthly_new_customers"),
            fulfilment_lead_days=fields.get("fulfilment_lead_days"),
            notes=fields.get("notes"),
        )
    return brief.bind_claims(fields.get("approved_by"), fields.get("claims"))


def main(argv) -> int:
    if len(argv) < 3:
        return _usage()
    path, command = argv[1], argv[2]
    rest = argv[3:]
    try:
        brief = ab.AcquisitionBrief(path)
        if command == "next":
            question = brief.ask_next()
            if question is None:
                for item in brief.next_binding_questions():
                    print(json.dumps(item.as_dict(), sort_keys=True))
                return 0
            print(json.dumps(question.as_dict(), sort_keys=True))
            return 0
        if command == "answer":
            if len(rest) < 2:
                return _usage()
            provenance = ab.PROVENANCE_CLIENT_STATED
            source = None
            tail = list(rest[2:])
            while tail:
                flag = tail.pop(0)
                if flag == "--provenance" and tail:
                    provenance = tail.pop(0)
                elif flag == "--source" and tail:
                    source = tail.pop(0)
                else:
                    return _usage()
            if provenance not in PROVENANCES:
                raise ab.BindingError("%r is not a provenance" % provenance)
            brief.answer(rest[0], rest[1], provenance=provenance, source=source)
            print("recorded %s" % rest[0])
            return 0
        if command == "bind":
            if len(rest) != 2 or rest[0] not in BIND_COMMANDS:
                return _usage()
            _bind(brief, rest[0], _json_fields(rest[1]))
            print("bound %s" % rest[0])
            return 0
        if command == "status":
            print(json.dumps(brief.status(), indent=2, sort_keys=True))
            return 0
        if command == "ready":
            owner = brief.require_owner()
            blockers = brief.planning_blockers()
            print(json.dumps({"owner": owner.as_dict(), "blockers": blockers}, indent=2, sort_keys=True))
            return 0 if brief.is_campaign_ready() else 1
        return _usage()
    except ab.OwnerConflictError as exc:
        print("OwnerConflictError: %s" % exc, file=sys.stderr)
        return 1
    except ab.BriefError as exc:
        print("%s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""JEV 1.1 CLI bridge -- shared-utils/decision-engine.py (spec 1.1 ss 2.2/2.3).

The spec's own released file plan names this path (line 196:
``shared-utils/decision-engine.py  # NEW CLI bridge``; line 1057 lists it with
``shared-utils/decision_engine/`` as the canonical new decision capability).
This file is the thin CC-facing front end over that package: ONE process per
evaluation (spec 2.3 -- no per-candidate spawn), ONE JSON request on stdin,
ONE JSON response on stdout. Stdlib only, reads/writes no state, needs no key,
touches no assignment.

Wire contract, byte-compatible with CC src/lib/decision-engine/
(bridge.ts / capability.ts / contract.ts, CC v7.6.68+):

  --capability   prints {"schemaVersion": "1.1.0"} and exits 0. The CC probe
                 requires a non-empty schemaVersion whose major matches.
  --evaluate     reads ONE DecisionRequest JSON from stdin:
                   {schemaVersion, configRevision, taskId, taskDescription,
                    department?}
                 and prints one DecisionResponse JSON:
                   {schemaVersion, configRevision,
                    recommendation: {roleId, confidence, rationale},
                    evaluatedAt}
                 - configRevision is echoed VERBATIM (CC assertRevisionEcho
                   treats absence or mismatch as IncompatibleRevision).
                 - No forbidden assignment key is ever emitted (CC
                   assertAssignmentReadOnly rejects assignment/dispatch/board/
                   task_card/persona_pin/status_transition/column shapes):
                   assignment-read-only by construction.
                 - Any failure: one-line typed message on stderr, rc != 0
                   (CC surfaces it as typed BridgeFailedError; 2 = usage or
                   bad request, 3 = installed core/packs unusable).

Honest evaluation scope (v1): the CC wire carries taskId / taskDescription /
department only, and this core deliberately ships NO role library (spec 6.2:
builders consume caller-supplied authoritative roster data). So the bridge
classifies the message against the RELEASED policy packs (D03 validators +
fixture lookup -- real offline judgments the packs support) and answers
recommendation roleId = none_suitable (profiles.NONE_SUITABLE, spec 6.3) with
the measured reasons in the rationale rather than inventing a role. Callers
keep their existing no-JEV selection path untouched (spec 3.6/9.8).

ponytail: caller-roster-driven rank_roles/accept_role scoring lands here when
a roster rides the wire; the refusal is the truthful v1, not a stub.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BRIDGE_SCHEMA_VERSION = "1.1.0"  # tracks CC contract.ts DECISION_SCHEMA_VERSION

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))  # resolve the sibling decision_engine/ package

try:  # fail-closed: a box without the canonical core must never answer
    from decision_engine import policies as _policies
    from decision_engine.profiles import NONE_SUITABLE as _NONE_SUITABLE
    _CORE_ERROR: str | None = None
except Exception as exc:  # noqa: BLE001
    _policies = None
    _NONE_SUITABLE = "none_suitable"
    _CORE_ERROR = f"{type(exc).__name__}: {exc}"


def _major(version) -> str | None:
    if not isinstance(version, str):
        return None
    head = version.strip().split(".", 1)[0]
    return head if head.isdigit() else None


def _utc_now() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _capability() -> int:
    if _policies is None:
        print(
            "decision-engine: canonical core unusable beside this bridge: "
            f"{_CORE_ERROR}",
            file=sys.stderr,
        )
        return 3
    print(json.dumps({"schemaVersion": BRIDGE_SCHEMA_VERSION}))
    return 0


def _evaluate() -> int:
    if _policies is None:
        print(
            "decision-engine: canonical core unusable beside this bridge: "
            f"{_CORE_ERROR}",
            file=sys.stderr,
        )
        return 3
    try:
        request = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        print("decision-engine: stdin is not one JSON request", file=sys.stderr)
        return 2
    if not isinstance(request, dict):
        print("decision-engine: request must be a JSON object", file=sys.stderr)
        return 2
    if _major(request.get("schemaVersion")) != _major(BRIDGE_SCHEMA_VERSION):
        print(
            "decision-engine: incompatible request schemaVersion "
            f"{request.get('schemaVersion')!r} (bridge accepts major "
            f"{_major(BRIDGE_SCHEMA_VERSION)})",
            file=sys.stderr,
        )
        return 2
    task = request.get("taskDescription")
    if not isinstance(task, str) or not task.strip():
        print(
            "decision-engine: 'taskDescription' must be a non-empty string",
            file=sys.stderr,
        )
        return 2
    department = request.get("department")
    if department is not None and (
        not isinstance(department, str) or not department.strip()
    ):
        print(
            "decision-engine: 'department' must be a non-empty string when present",
            file=sys.stderr,
        )
        return 2

    try:
        packs = _policies.iter_packs()
    except Exception as exc:  # noqa: BLE001
        print(
            f"decision-engine: released policy packs unreadable: {exc}",
            file=sys.stderr,
        )
        return 3
    problems = [
        f"{name}: {'; '.join(errors)}"
        for name, pack in packs
        for ok, errors in [_policies.validate_pack(pack)]
        if not ok
    ]
    if problems:
        print(
            "decision-engine: released policy pack(s) invalid: "
            f"{' | '.join(problems)}",
            file=sys.stderr,
        )
        return 3

    intent = _policies.fixture_lookup(task, [pack for _, pack in packs])
    all_departments = sorted(
        {d for _, pack in packs for d in (pack.get("departments") or [])}
    )
    parts = [
        "assignment-read-only evaluation (spec 2.2); this core ships no role "
        "library (spec 6.2) and the CC wire carries no roster, so no role is "
        "accepted and the caller keeps its existing no-JEV selection path "
        "(spec 3.6/9.8)."
    ]
    if intent:
        parts.append(f"released-pack intent match for this message: {intent}.")
    else:
        parts.append("no released-pack fixture match for this message.")
    if department:
        covering = [
            name for name, pack in packs if department in (pack.get("departments") or [])
        ]
        if covering:
            parts.append(
                f"department {department!r} covered by released pack(s): "
                f"{', '.join(covering)}."
            )
        else:
            parts.append(
                f"department {department!r} is not in the released packs "
                f"(known: {', '.join(all_departments)})."
            )

    response = {
        "schemaVersion": BRIDGE_SCHEMA_VERSION,
        "configRevision": request.get("configRevision"),
        "recommendation": {
            "roleId": _NONE_SUITABLE,
            "confidence": 0.0,
            "rationale": " ".join(parts),
        },
        "evaluatedAt": _utc_now(),
    }
    print(json.dumps(response, ensure_ascii=False))
    return 0


def main(argv) -> int:
    if "--capability" in argv:
        return _capability()
    if "--evaluate" in argv:
        return _evaluate()
    print("usage: decision-engine.py [--capability] [--evaluate]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

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

Live decision (additive, schema stays "1.1.0"): the response keeps every
original field byte-for-byte -- including recommendation.roleId =
none_suitable (profiles.NONE_SUITABLE, spec 6.3), because this core still
ships NO role library (spec 6.2) and the wire still carries no roster, so
no ROLE is ever accepted. What is now decided live is the MESSAGE: `intent`
(one of the 7 CC intents -- exact released-pack fixture match, then a
normalized-fixture match, then the stdlib `_heuristic_intent` heuristic,
never a role/roster judgment) and `route` (answer / route-to-department /
none, with the department picked from an optional caller-supplied
`departments` catalog or the standard-floor mandatory departments, falling
back to `general-task` when nothing clears the lexical threshold). Callers
keep their existing no-JEV selection path for ROLE assignment untouched
(spec 3.6/9.8); only intent/department routing is new here.

ponytail: caller-roster-driven rank_roles/accept_role scoring lands here when
a roster rides the wire for ROLE selection; the refusal is the truthful v1,
not a stub.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BRIDGE_SCHEMA_VERSION = "1.1.0"  # tracks CC contract.ts DECISION_SCHEMA_VERSION

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))  # resolve the sibling decision_engine/ package

try:  # fail-closed: a box without the canonical core must never answer
    from decision_engine import fallback as _fallback
    from decision_engine import policies as _policies
    from decision_engine import profiles as _profiles
    from decision_engine.profiles import NONE_SUITABLE as _NONE_SUITABLE
    _CORE_ERROR: str | None = None
except Exception as exc:  # noqa: BLE001
    _fallback = None
    _policies = None
    _profiles = None
    _NONE_SUITABLE = "none_suitable"
    _CORE_ERROR = f"{type(exc).__name__}: {exc}"

# --- C2/CONTRACT: live intent + route (additive; BRIDGE_SCHEMA_VERSION 1.1.0) ---

# Spec 4.1 / D03 pack INTENT_ENUM mirror (kept local so this module has no
# hard runtime dependency beyond the fail-closed core import above).
_INTENT_ANSWER = ("answer_only", "social_conversation")
_INTENT_ROUTE = ("task_request", "mixed_answer_and_task")
_INTENT_NONE = ("existing_task_control", "clarification_response", "unresolved")

# ROUTE_THRESHOLD is the department-fit cutoff for the ranking below.
# ponytail: lexical overlap is a ceiling, not a semantic judgment -- the
# upgrade path is embeddings or the LLM ladder, not a bigger stopword list.
ROUTE_THRESHOLD = 0.34

_EXCLUDED_DEPARTMENT_SLUGS = frozenset(
    {"general-task", "dept-general-task", "general", "master-orchestrator", "ceo", "default"}
)

_ROUTE_STOPWORDS = frozenset(
    "a an the to for of and or in on at with about me my our we you your i it "
    "this that please can could would will is are be do does some any from by "
    "up so just need want".split()
)

_GREETING_PHRASES = frozenset(
    {
        "thanks", "thank you", "thx", "ty", "hi", "hello", "hey",
        "good morning", "good afternoon", "good evening",
        "ok", "okay", "got it", "great", "cool",
    }
)

# Words that lead a clause but are never themselves an imperative task verb
# (pronouns/articles, wh-words, aux-words, and the answer-lead verbs), used
# only to decide whether a clause OPENS with a task instruction (rule b).
_NON_TASK_LEAD_WORDS = frozenset(
    {
        "i", "you", "he", "she", "it", "we", "they",
        "the", "a", "an", "this", "that", "these", "those",
        "what", "why", "how", "when", "where", "who", "which",
        "is", "are", "does", "do", "did", "should", "will", "would", "has", "have",
        "can", "could",
        "explain", "tell", "describe", "clarify",
        "thanks", "thank", "hi", "hello", "hey", "ok", "okay", "good", "great",
        "cool", "got",
    }
)

_QUOTE_SPAN_RE = re.compile(r"'[^']*'|\"[^\"]*\"|‘[^’]*’|“[^”]*”")
_TRAILING_PUNCT_RE = re.compile(r"[.!?,]+$")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!;])\s+")
_WH_LEAD_RE = re.compile(r"^(what|why|how|when|where|who|which)\b")
_EXPLAIN_LEAD_RE = re.compile(r"^(explain|tell me|describe|clarify)\b")
_CAN_COULD_WOULD_EXPLAIN_RE = re.compile(
    r"^(can|could|would)\s+you\s+(explain|tell|describe|clarify)\b"
)
_AUX_LEAD_QUESTION_RE = re.compile(
    r"^(is|are|does|do|did|should|will|would|has|have|can i|could i)\b.*\?\s*$"
)
_LEAD_VERB_RE = re.compile(r"^([a-z']+)")
_YOU_VERB_RE = re.compile(r"^(can|could|would|will)\s+you\s+([a-z']+)")


def _heuristic_intent(text: str) -> str:
    """Stdlib lexical fallback intent classifier (never returns 'unresolved').

    Runs on a lowered copy of ``text`` with quoted spans ('..', "..", curly
    quotes) removed, so a quoted instruction inside a question ("what does
    'do it' mean?") never contaminates the lead-pattern check below.
    """
    lowered = text.lower()
    stripped = _QUOTE_SPAN_RE.sub(" ", lowered)
    stripped = " ".join(stripped.split())

    # a) the whole message is a greeting or thanks.
    bare = _TRAILING_PUNCT_RE.sub("", stripped).strip()
    if bare in _GREETING_PHRASES:
        return "social_conversation"

    # b) a task clause plus an "explain why" style ask -> mixed.
    has_explain_why = (
        "explain why" in stripped or "tell me why" in stripped or "and explain" in stripped
    )
    if has_explain_why and _has_task_clause(stripped):
        return "mixed_answer_and_task"

    # c) wh-lead / explain-lead / can-you-explain / aux-lead-ending-in-? ->
    # answer_only. Checked per clause so a quote-stripped remark like
    # "the client wrote, ; what does that mean?" still matches on its
    # trailing question clause.
    for clause in _CLAUSE_SPLIT_RE.split(stripped):
        clause = clause.strip()
        if not clause:
            continue
        if (
            _WH_LEAD_RE.match(clause)
            or _EXPLAIN_LEAD_RE.match(clause)
            or _CAN_COULD_WOULD_EXPLAIN_RE.match(clause)
            or _AUX_LEAD_QUESTION_RE.match(clause)
        ):
            return "answer_only"

    # d) anything else -> task_request (work is never silently dropped).
    return "task_request"


def _has_task_clause(normalized: str) -> bool:
    if re.search(r"\bplease\b", normalized):
        return True
    lead = _LEAD_VERB_RE.match(normalized)
    if lead and lead.group(1) not in _NON_TASK_LEAD_WORDS:
        return True
    you_verb = _YOU_VERB_RE.match(normalized)
    if you_verb and you_verb.group(2) not in ("explain", "tell", "describe", "clarify"):
        return True
    return False


_TRAILING_SENTENCE_PUNCT_RE = re.compile(r"[.!?]+$")


def _normalize_for_fixture_match(text: str) -> str:
    """casefold + collapse whitespace + strip trailing .!? (spec: step 2)."""
    norm = " ".join(text.casefold().split())
    return _TRAILING_SENTENCE_PUNCT_RE.sub("", norm)


def _route_query(task: str) -> str:
    tokens = [t for t in re.findall(r"[a-z0-9]+", task.lower()) if t not in _ROUTE_STOPWORDS]
    return " ".join(tokens)


def _standard_floor_catalog() -> list[dict]:
    """Mandatory-department text catalog, read defensively (never raises)."""
    naming_map_path = _HERE.parent / "23-ai-workforce-blueprint" / "department-naming-map.json"
    role_index_path = (
        _HERE.parent / "23-ai-workforce-blueprint" / "templates" / "role-library" / "_index.json"
    )
    try:
        mandatory = json.loads(naming_map_path.read_text(encoding="utf-8")).get("mandatory")
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(mandatory, dict) or not mandatory:
        return []
    role_departments: dict = {}
    try:
        role_index = json.loads(role_index_path.read_text(encoding="utf-8"))
        candidate = role_index.get("departments")
        if isinstance(candidate, dict):
            role_departments = candidate
    except Exception:  # noqa: BLE001
        pass

    entries = []
    for slug, info in mandatory.items():
        if not isinstance(slug, str) or slug.lower() in _EXCLUDED_DEPARTMENT_SLUGS:
            continue
        if not isinstance(info, dict):
            continue
        display_name = info.get("display_name") or ""
        one_liner = info.get("one_liner") or ""
        roles: list[str] = []
        dept_roles = role_departments.get(slug)
        if isinstance(dept_roles, dict):
            roles = [r for r in (dept_roles.get("roles") or []) if isinstance(r, str)]
        text = " ".join([display_name, one_liner, " ".join(roles)])
        entries.append({"slug": slug, "text": text})
    return entries


def _resolve_route_department(
    task: str, department_requested: str | None, catalog_entries: list[dict]
) -> tuple[str, float, bool]:
    """Returns (department_slug, confidence, fallback). Never raises."""
    try:
        if department_requested:
            wanted = department_requested.strip().lower()
            for entry in catalog_entries:
                if entry["slug"].lower() == wanted:
                    return entry["slug"], 1.0, False
        if not catalog_entries:
            return "general-task", 0.0, True
        query = _route_query(task)
        if not query:
            return "general-task", 0.0, True
        ranking = _fallback.select(
            [{"id": e["slug"], "text": e["text"], "topics": []} for e in catalog_entries],
            query,
        )["ranking"]
        suitability = {r["id"]: r["score"] for r in ranking}
        pick = _profiles.resolve_department_selection(suitability, threshold=ROUTE_THRESHOLD)
        if pick == _NONE_SUITABLE:
            top_score = ranking[0]["score"] if ranking else 0.0
            return "general-task", float(top_score), True
        return pick, float(suitability.get(pick, 0.0)), False
    except Exception:  # noqa: BLE001 -- routing must never turn into rc != 0
        return "general-task", 0.0, True


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
    departments = request.get("departments")
    request_catalog: list[dict] | None = None
    if departments is not None:
        if not isinstance(departments, list):
            print(
                "decision-engine: 'departments' must be a list when present",
                file=sys.stderr,
            )
            return 2
        request_catalog = []
        for i, dept in enumerate(departments):
            if not isinstance(dept, dict):
                print(f"decision-engine: 'departments[{i}]' must be an object", file=sys.stderr)
                return 2
            slug = dept.get("slug")
            if not isinstance(slug, str) or not slug.strip():
                print(
                    f"decision-engine: 'departments[{i}].slug' must be a non-empty string",
                    file=sys.stderr,
                )
                return 2
            name = dept.get("name")
            if name is not None and not isinstance(name, str):
                print(
                    f"decision-engine: 'departments[{i}].name' must be a string when present",
                    file=sys.stderr,
                )
                return 2
            description = dept.get("description")
            if description is not None and not isinstance(description, str):
                print(
                    f"decision-engine: 'departments[{i}].description' must be a string "
                    "when present",
                    file=sys.stderr,
                )
                return 2
            keywords = dept.get("keywords")
            if keywords is not None and (
                not isinstance(keywords, list) or any(not isinstance(k, str) for k in keywords)
            ):
                print(
                    f"decision-engine: 'departments[{i}].keywords' must be a list of "
                    "strings when present",
                    file=sys.stderr,
                )
                return 2
            request_catalog.append(
                {
                    "slug": slug,
                    "text": " ".join([name or "", description or "", " ".join(keywords or [])]),
                }
            )

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

    exact_intent = _policies.fixture_lookup(task, [pack for _, pack in packs])
    all_departments = sorted(
        {d for _, pack in packs for d in (pack.get("departments") or [])}
    )
    parts = [
        "assignment-read-only evaluation (spec 2.2); this core ships no role "
        "library (spec 6.2) and the CC wire carries no roster, so no role is "
        "accepted and the caller keeps its existing no-JEV selection path "
        "(spec 3.6/9.8)."
    ]
    if exact_intent:
        parts.append(f"released-pack intent match for this message: {exact_intent}.")
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

    # C2/CONTRACT: live intent, in order -- exact fixture, normalized fixture,
    # then the stdlib heuristic (never returns 'unresolved').
    if exact_intent:
        intent = exact_intent
        intent_source = "fixture"
    else:
        normalized_hit = None
        normalized_task = _normalize_for_fixture_match(task)
        for _, pack in packs:
            for fixture in pack.get("fixtures") or []:
                if not isinstance(fixture, dict):
                    continue
                message = fixture.get("message")
                if isinstance(message, str) and _normalize_for_fixture_match(message) == normalized_task:
                    normalized_hit = fixture.get("expected_intent")
                    break
            if normalized_hit:
                break
        if normalized_hit:
            intent = normalized_hit
            intent_source = "fixture"
        else:
            intent = _heuristic_intent(task)
            intent_source = "heuristic"

    # CATALOG: request.departments when non-empty, else the standard floor.
    if request_catalog:
        catalog_entries = [
            e for e in request_catalog if e["slug"].lower() not in _EXCLUDED_DEPARTMENT_SLUGS
        ]
        catalog_label = "request"
    else:
        catalog_entries = _standard_floor_catalog()
        catalog_label = "standard-floor" if catalog_entries else "empty"

    route = {
        "action": "none",
        "department": None,
        "confidence": 0.0,
        "fallback": False,
        "catalog": catalog_label,
    }
    if intent in _INTENT_ANSWER:
        route["action"] = "answer"
    elif intent in _INTENT_ROUTE:
        route["action"] = "route"
        dept, conf, fb = _resolve_route_department(task, department, catalog_entries)
        route["department"] = dept
        route["confidence"] = conf
        route["fallback"] = fb
    # else: existing_task_control / clarification_response / unresolved ->
    # stays action 'none', department None (the caller's existing handling).

    response = {
        "schemaVersion": BRIDGE_SCHEMA_VERSION,
        "configRevision": request.get("configRevision"),
        "recommendation": {
            "roleId": _NONE_SUITABLE,
            "confidence": 0.0,
            "rationale": " ".join(parts),
        },
        "evaluatedAt": _utc_now(),
        "intent": intent,
        "intentSource": intent_source,
        "route": route,
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

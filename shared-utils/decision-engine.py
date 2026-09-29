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

# Whole-clause social phrases: a clause that is ONLY one of these (after
# leading filler is stripped) is FILLER. "thank them with a gift card" is
# not "thank you", so it is not in here.
_SOCIAL_PHRASES = frozenset(
    {
        "thanks", "thank you", "thanks so much", "thank you so much", "thanks a lot",
        "thx", "ty", "much appreciated", "appreciate it", "cheers",
        "hi", "hello", "hey", "hi there", "hello there", "hey there",
        "good morning", "good afternoon", "good evening",
        "ok", "okay", "got it", "great", "cool", "sounds good", "perfect", "awesome", "nice",
        "no worries", "no problem", "all good", "love it", "that works", "works for me",
        "thanks again", "thank you again", "appreciate you", "great job", "good job",
        "well done", "nice work", "great work", "amazing", "wonderful", "fantastic",
        "see you tomorrow", "talk soon", "talk later", "have a good one", "have a great day",
    }
)
# JGT-301: social closers shaped "that's perfect" / "this is really helpful".
_SOCIAL_CLOSER_RE = re.compile(
    r"^(?:that'?s|that is|this is|it'?s|it is|looks|sounds|you'?re|you are)\s+"
    r"(?:(?:so|really|just|very|absolutely|super|all)\s+)?"
    r"(?:perfect|great|awesome|amazing|fantastic|wonderful|excellent|good|fine|"
    r"helpful|brilliant|lovely|beautiful|exactly right|the best|a lifesaver)$"
)

# (a) Throwaway lead phrases stripped from the front of every clause, even
# when comma/colon/period-joined ("Just curious, why ...", "So what ...").
_FILLER_LEAD_RE = re.compile(
    r"^(?:just curious|quick question|quick q|real quick|one thing|one more thing|"
    r"question|honestly|by the way|btw|i was wondering|i wonder|curious|"
    r"so|hmm+|um+|uh+|well|ok|okay|alright|hey|hi|hello|please|also|anyway|actually|oh)"
    r"(?:\s*[,.:;!\-—]+\s*|\s+|$)"
)
# JGT-301: a single-quote span opens and closes at a word edge, so the
# apostrophes in "what's ... it's" are not read as a quote (that ate the task
# between them); an inner "don't" apostrophe stays inside the span.
_QUOTE_SPAN_RE = re.compile(
    r"(?<![a-z0-9])'(?:[^']|'(?=[a-z]))*'(?![a-z0-9])|\"[^\"]*\"|‘[^’]*’|“[^”]*”"
)
_EDGE_PUNCT_RE = re.compile(r"^[\s,.:;!?\-]+|[\s,.:;!?\-]+$")
# (b) clause boundaries: after . ! ? ; (terminal punctuation stays on the
# clause), on newlines, and on a sequencing ", then" / "and then"
# ("Explain the pricing, then update the page" carries a task).
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|\s*\n+\s*|,\s*(?:and\s+)?then\s+|\s+and\s+then\s+")
_ANSWER_VERBS = ("explain", "tell", "describe", "clarify")
# (d) polite request: "can/could/would/will you <verb>" is ACTION unless the
# verb is an answer verb (explain/tell/describe/clarify).
_POLITE_REQUEST_RE = re.compile(
    r"^(?:can|could|would|will)\s+(?:you|we|someone|somebody)\s+"
    r"(?:please\s+|kindly\s+|possibly\s+|just\s+|quickly\s+|also\s+)?([a-z']+)"
)
# 'when you get a chance' / 'when the invoice arrives' is a subordinate
# lead, not a question: 'when' leads a question only when no subject follows.
_WH_LEAD_RE = re.compile(
    r"^(?:what|why|how|where|who|whom|whose|which|"
    r"when(?!\s+(?:i|you|we|they|he|she|it|the|a|an|my|our|your|this|that|everyone)\b))\b"
)
_EXPLAIN_LEAD_RE = re.compile(r"^(?:explain|tell me|describe|clarify)\b")
# is/are/does/... are never imperatives; do/have/has can be ("Do a
# competitor analysis", "Have Jordan do it"), so they lead a question only
# when a subject pronoun follows.
_AUX_LEAD_RE = re.compile(
    r"^(?:is|are|was|were|does|did|can|could|would|will|should|shall|may|might|"
    r"(?:do|have|has)\s+(?:i|you|we|they|he|she|it)\b)\b"
)
# Neutral clauses: a negative constraint ("Do not build anything yet.") or
# reported speech whose quote was stripped ("The client wrote, ;"). They
# are neither a question nor an action on their own.
_CONSTRAINT_RE = re.compile(r"^(?:do not|don't|dont)\s+(?!forget\b|miss\b|skip\b|let\b)")
_REPORTED_SPEECH_RE = re.compile(
    r"\b(?:wrote|said|says|asked|asks|writes|replied|texted|emailed|mentioned|told me)$"
)
_EXPLAIN_WHY_RE = re.compile(r"\b(?:explain why|tell me why|and explain)\b")

# --- JGT-301: soft segment boundaries inside one sentence ---
# A comma, or a bare and/but/also/then, starts a NEW segment only when the
# text after it starts a clause (see _starts_segment); otherwise it is a noun
# list ('red, blue and green') and stays one segment.
_SOFT_BOUNDARY_RE = re.compile(
    r",\s*(?:(?:and|but|also|so|or)\s+)?(?:then\s+)?|\s+(?:and|but|also)\s+(?:then\s+)?|\s+then\s+"
)
# Conditional/subordinate lead: attaches to its neighbour, never an ACTION alone.
_CONDITIONAL_LEAD_RE = re.compile(
    r"^(?:if|unless|once|whenever|when|as soon as|in case|assuming|provided)\b"
)
# ponytail: a verb lexicon, not a POS tagger. A listed verb followed by one
# more non-conjunction word starts a segment; a noun that is also a verb
# ('email draft') can over-split into an extra card, the lesser harm (the
# BIAS rule). Upgrade path is a real tagger, not a longer list.
_ACTION_VERBS = frozenset(
    """add adjust approve archive arrange ask assign audit book bring build buy call
    cancel change chase check clean clear close collect confirm contact copy create
    delete deploy design do draft drop edit email enable disable export file fill find
    finish fix follow forward get give go handle help hire import install invite invoice
    let lock look make merge message migrate move notify onboard open order organize pay
    ping plan post prepare print publish pull push put raise reach rebook reconcile
    record refund reject remind remove rename renew reorder repair reply reschedule
    reset resend respond restart restore revert review revoke roll run save schedule
    send set share ship sign start stop submit switch take text translate unlock update
    upgrade upload verify write""".split()
)
_STRUCTURAL_VERB_RE = re.compile(
    r"^(?!(?:the|a|an|my|our|your|his|her|their|its|this|that|these|those|all|any|some|"
    r"every|each|no|i|you|we|they|he|she|it|and|or|of|in|on|at|for|with|to|from|by)\b)"
    r"[a-z]+(?:\s+(?:back|up|out|off|over|down|in|on|through|forward|along|around|away|ahead))?"
    r"\s+(?:the|a|an|my|our|your|his|her|their|its|this|that|these|those|it|them|him|me|us|"
    r"everyone|everybody|everything)\b"
)
# 'how do I reset my password and change my email?' -- the tail shares the
# head's question frame, so action verbs do not split it off.
_SHARED_FRAME_RE = re.compile(
    r"^(?:(?:how|what|where|which|when)\s+to|(?:how|what|why|where|when|which|who)\b"
    r"(?:\s+[a-z']+){0,2}?\s+(?:do|does|did|can|could|should|would|will|shall|may|might|must)"
    r"\s+(?:i|we|you|they|he|she|one|someone))\b"
)


_POLITE_HEAD_RE = re.compile(r"^(?:can|could|would|will)\s+(?:you|we|someone|somebody)(?:\s+please)?$")


def _strip_filler(clause: str) -> str:
    prev = None
    while prev != clause:
        prev = clause
        clause = _FILLER_LEAD_RE.sub("", clause, count=1)
    return clause


def _is_social(bare: str) -> bool:
    return bare in _SOCIAL_PHRASES or bool(_SOCIAL_CLOSER_RE.match(bare))


def _starts_segment(tail: str, shared_frame: bool) -> bool:
    """Does the text after a soft boundary start a new clause?"""
    bare = _EDGE_PUNCT_RE.sub("", tail)
    if not bare:
        return False
    if (
        _is_social(re.split(r"\s*[,.!?;]", bare, maxsplit=1)[0])
        or _WH_LEAD_RE.match(bare)
        or _AUX_LEAD_RE.match(bare)
        or _CONDITIONAL_LEAD_RE.match(bare)
        or re.match(r"(?:please|don't|do not|let's)\b", bare)
    ):
        return True
    if shared_frame:
        return False
    words = bare.split()
    if words[0] in _ACTION_VERBS and len(words) > 1 and words[1] not in ("and", "or"):
        return True
    return bool(_STRUCTURAL_VERB_RE.match(bare))


def _segments(sentence: str) -> list[str]:
    """Split one sentence on soft boundaries that start a new clause."""
    head = _EDGE_PUNCT_RE.sub("", _strip_filler(sentence.strip()))
    shared_frame = sentence.rstrip().endswith("?") and bool(_SHARED_FRAME_RE.match(head))
    out, start = [], 0
    for m in _SOFT_BOUNDARY_RE.finditer(sentence):
        if _POLITE_HEAD_RE.match(_strip_filler(sentence[start:m.start()].strip())):
            continue  # 'can you also rebook ...' is one polite request
        if _starts_segment(sentence[m.end():], shared_frame):
            out.append(sentence[start:m.start()])
            start = m.end()
    out.append(sentence[start:])
    return [s for s in out if s.strip()]


def _classify_clause(clause: str, *, continuation: bool = False, grouped: bool = False) -> str:
    """One segment -> 'question' | 'filler' | 'neutral' | 'action'.

    continuation: split off a sentence after a soft boundary, so the
    sentence's trailing '?' is not its own (BIAS: '... and roll back if it
    broke anything?' is an ACTION). grouped: it has sibling segments, so a
    conditional lead ('if you have time') attaches to them."""
    body = _strip_filler(clause.strip())
    bare = _EDGE_PUNCT_RE.sub("", body)
    if not bare or _is_social(bare) or _is_social(_EDGE_PUNCT_RE.sub("", clause)):
        return "filler"
    if grouped and _CONDITIONAL_LEAD_RE.match(bare) and not _WH_LEAD_RE.match(bare):
        return "neutral"
    polite = _POLITE_REQUEST_RE.match(bare)
    if polite:
        return "question" if polite.group(1) in _ANSWER_VERBS else "action"
    if (
        (not continuation and body.rstrip().endswith("?"))
        or _WH_LEAD_RE.match(bare)
        or _EXPLAIN_LEAD_RE.match(bare)
        or _AUX_LEAD_RE.match(bare)
    ):
        return "question"
    if _CONSTRAINT_RE.match(bare) or _REPORTED_SPEECH_RE.search(bare):
        return "neutral"
    return "action"


def _heuristic_intent(text: str) -> str:
    """Stdlib lexical fallback intent classifier (never returns 'unresolved').

    INVERSION: a clause is ACTION unless it is provably a QUESTION or FILLER,
    so an unknown verb ("refund", "chase", "reconcile") is never dropped to
    an answer (contract C2/C4: unsure means task). Quoted spans are removed
    first so a quoted instruction inside a question ("what does 'do it'
    mean?") is not read as a live instruction.
    """
    stripped = _QUOTE_SPAN_RE.sub(" ", text.lower())
    kinds = []
    for sentence in _CLAUSE_SPLIT_RE.split(stripped):
        segs = _segments(sentence) if sentence.strip() else []
        kinds += [
            _classify_clause(s, continuation=i > 0, grouped=len(segs) > 1)
            for i, s in enumerate(segs)
        ]
    if "action" in kinds:
        if "question" in kinds or _EXPLAIN_WHY_RE.search(stripped):
            return "mixed_answer_and_task"
        return "task_request"
    if "question" in kinds:
        return "answer_only"
    if kinds and all(k == "filler" for k in kinds):
        return "social_conversation"
    return "task_request"


_TRAILING_SENTENCE_PUNCT_RE = re.compile(r"[.!?]+$")


def _normalize_for_fixture_match(text: str) -> str:
    """casefold + collapse whitespace + strip trailing .!? (spec: step 2)."""
    norm = " ".join(text.casefold().split())
    return _TRAILING_SENTENCE_PUNCT_RE.sub("", norm)


def _stem(token: str) -> str:
    """Light stemmer so 'invoice'/'invoices'/'invoicing' share one token.
    ponytail: suffix stripping, not Porter -- add a real stemmer only if a
    mismatch shows up in live routing."""
    if len(token) > 4 and token.endswith("ies"):
        token = token[:-3] + "y"
    elif len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
    elif len(token) > 4 and token.endswith("ed"):
        token = token[:-2]
    elif len(token) > 2 and token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    if len(token) > 3 and token.endswith("e"):
        token = token[:-1]
    if len(token) > 3 and token[-1] == token[-2] and token[-1] not in "ls":
        token = token[:-1]
    return token


def _stem_text(text: str) -> str:
    return " ".join(_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()))


def _route_query(task: str) -> str:
    tokens = [t for t in re.findall(r"[a-z0-9]+", task.lower()) if t not in _ROUTE_STOPWORDS]
    return " ".join(_stem(t) for t in tokens)


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


def _domain_boosted_suitability(
    query_tokens: list[str], catalog_entries: list[dict], suitability: dict[str, float]
) -> dict[str, float]:
    """Boost a department whose OWN vocabulary contains a rare query token.

    ``_lexical_rank``'s score is overlap / len(query tokens), so one strong
    domain keyword ("invoice") drowns in an otherwise generic query ("send
    ... to the client") and never clears ROUTE_THRESHOLD. Here each query
    token is weighted by 1/df (df = how many catalog entries' vocabulary
    contain it), so a token that names exactly one department's domain
    counts for far more than a token every department shares (or none do --
    a token in no entry's vocabulary carries no signal and is dropped, so
    nonsense queries still fall through to general-task).
    ponytail: document-frequency-over-catalog is the ceiling, not semantic
    similarity -- the upgrade path is embeddings, not a bigger weight table.
    """
    vocab_by_slug = {
        e["slug"]: set(re.findall(r"[a-z0-9]+", e["text"].lower())) for e in catalog_entries
    }
    domain_tokens = {t for t in query_tokens if any(t in v for v in vocab_by_slug.values())}
    if not domain_tokens:
        return suitability
    weights = {t: 1.0 / sum(1 for v in vocab_by_slug.values() if t in v) for t in domain_tokens}
    total_weight = sum(weights.values())
    boosted = dict(suitability)
    for slug, vocab in vocab_by_slug.items():
        matched_weight = sum(w for t, w in weights.items() if t in vocab)
        if matched_weight <= 0:
            continue
        boosted[slug] = max(boosted.get(slug, 0.0), matched_weight / total_weight)
    return boosted


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
        catalog_entries = [{"slug": e["slug"], "text": _stem_text(e["text"])} for e in catalog_entries]
        ranking = _fallback.select(
            [{"id": e["slug"], "text": e["text"], "topics": []} for e in catalog_entries],
            query,
        )["ranking"]
        suitability = {r["id"]: r["score"] for r in ranking}
        suitability = _domain_boosted_suitability(query.split(), catalog_entries, suitability)
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

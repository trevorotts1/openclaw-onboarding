#!/usr/bin/env python3
"""Guided business, audience and offer discovery for Skill 38 (T-06).

The install-time identity collector is WORKFORCE-shaped: it knows the client's
name and business name and nothing a 30-day campaign needs. This module is the
acquisition front door: one persistent brief covering business, offers,
audience, proof, constraints, channels, geography and seasonality, plus the
client's real asset inventory.

Doctrine, enforced in code:

  * every fact carries provenance (client_stated, discovered, assumed) and a
    recording timestamp;
  * a recorded fact is never asked again; the next-question set contains only
    facts that are genuinely unanswered, ordered and minimal;
  * an assumed fact is never treated as knowledge: it raises a confirmation
    question and blocks campaign readiness until a person confirms it;
  * a fact nobody knows is recorded as missing, never defaulted, and blocks
    campaign readiness instead of being replaced with a plausible value;
  * the interview persists after every answer with an atomic replace, so an
    interrupted interview resumes at the same unanswered question with no
    data loss and no repeated questions;
  * the asset registry records only what the client reports having. It never
    creates, invents, or writes an asset; preparing assets is T-07's job.

Python 3 standard library only.
"""

from __future__ import annotations

import dataclasses
import datetime as _datetime
import json
import os
import tempfile
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SCHEMA = "skill38.acquisition_brief.v1"

PROVENANCE_CLIENT_STATED = "client_stated"
PROVENANCE_DISCOVERED = "discovered"
PROVENANCE_ASSUMED = "assumed"
PROVENANCES = (
    PROVENANCE_CLIENT_STATED,
    PROVENANCE_DISCOVERED,
    PROVENANCE_ASSUMED,
)
# Provenance that may satisfy the brief on its own. An assumption is recorded,
# but it is a question to confirm, never a fact to plan from.
TRUSTED_PROVENANCES = (PROVENANCE_CLIENT_STATED, PROVENANCE_DISCOVERED)

INTERVIEW_NOT_STARTED = "not_started"
INTERVIEW_IN_PROGRESS = "in_progress"
INTERVIEW_BLOCKED = "blocked"
INTERVIEW_SUFFICIENT = "sufficient"

ASSET_PRESENT = "present"
ASSET_ABSENT = "absent"
ASSET_STATUSES = (ASSET_PRESENT, ASSET_ABSENT)

ASSET_KINDS = (
    "logo",
    "photos",
    "testimonials",
    "offer_documents",
    "links",
)
ASSET_REQUIRED_FOR_CAMPAIGN = frozenset(
    {"logo", "photos", "offer_documents", "links"}
)


class BriefError(Exception):
    """Base class for acquisition brief failures."""


class UnknownFactError(BriefError):
    """The requested fact id is not part of the acquisition brief."""


class UnknownAssetError(BriefError):
    """The requested asset kind is not part of the asset registry."""


class InvalidFactError(BriefError):
    """A fact value, provenance, or status failed validation."""


class MissingFactError(BriefError):
    """A required fact was asked for as if it had a value, but it is unanswered."""


class BriefCorruptError(BriefError):
    """The brief file exists but cannot be read as a valid brief."""


@dataclasses.dataclass(frozen=True)
class FactSpec:
    """One question the acquisition brief can hold an answer to."""

    section: str
    key: str
    question: str
    required: bool
    priority: int

    @property
    def fact_id(self) -> str:
        return "%s.%s" % (self.section, self.key)


def _spec(
    section: str, key: str, question: str, required: bool, priority: int
) -> FactSpec:
    return FactSpec(
        section=section,
        key=key,
        question=question,
        required=required,
        priority=priority,
    )


# Ordered by priority. Required facts are the minimal set a 30-day campaign
# plan needs; optional facts improve the plan but never block it.
FACT_SPECS: Tuple[FactSpec, ...] = (
    _spec(
        "business",
        "legal_name",
        "What is the legal or trading name of the business?",
        True,
        10,
    ),
    _spec(
        "business",
        "what_you_do",
        "In one sentence, what does the business sell, and to whom?",
        True,
        20,
    ),
    _spec(
        "business",
        "differentiator",
        "What makes the business different from its closest competitor?",
        False,
        30,
    ),
    _spec(
        "offers",
        "primary_offer",
        "What is the main offer a brand-new customer buys first?",
        True,
        40,
    ),
    _spec(
        "offers",
        "price_range",
        "What does that main offer cost?",
        True,
        50,
    ),
    _spec(
        "offers",
        "secondary_offers",
        "What else can an existing customer buy after the first offer?",
        False,
        60,
    ),
    _spec(
        "audience",
        "primary_audience",
        "Who is the single best-fit customer for the main offer?",
        True,
        70,
    ),
    _spec(
        "audience",
        "audience_pain",
        "What problem is that customer trying to solve when they buy?",
        True,
        80,
    ),
    _spec(
        "audience",
        "audience_channels",
        "Where does that customer already spend their attention?",
        False,
        90,
    ),
    _spec(
        "proof",
        "proof_assets",
        "What proof exists today: reviews, results, credentials or case studies?",
        True,
        100,
    ),
    _spec(
        "constraints",
        "budget",
        "What monthly budget is available for the 30-day campaign?",
        True,
        110,
    ),
    _spec(
        "constraints",
        "compliance_constraints",
        "Are there legal, licensing or platform restrictions the campaign must respect?",
        False,
        120,
    ),
    _spec(
        "channels",
        "owned_channels",
        "Which accounts and channels does the business already control?",
        True,
        130,
    ),
    _spec(
        "channels",
        "channel_access",
        "Does the business hold admin access to those accounts?",
        True,
        140,
    ),
    _spec(
        "geography",
        "service_area",
        "Where does the business serve customers?",
        True,
        150,
    ),
    _spec(
        "geography",
        "service_limits",
        "Which areas or customers are explicitly out of scope?",
        False,
        160,
    ),
    _spec(
        "seasonality",
        "upcoming_season",
        "Which dates or seasons affect the next 30 days?",
        True,
        170,
    ),
    _spec(
        "seasonality",
        "slow_season",
        "When is demand lowest during the year?",
        False,
        180,
    ),
)

FACT_SPECS_BY_ID: Dict[str, FactSpec] = {spec.fact_id: spec for spec in FACT_SPECS}
SECTION_ORDER: Tuple[str, ...] = tuple(
    dict.fromkeys(spec.section for spec in FACT_SPECS)
)


@dataclasses.dataclass(frozen=True)
class Question:
    """A next question. `kind` is "missing" or the confirmation of an assumption."""

    fact_id: str
    section: str
    key: str
    text: str
    required: bool
    priority: int
    kind: str = "missing"

    def as_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Fact:
    """A recorded fact with the provenance a campaign planner needs."""

    fact_id: str
    section: str
    key: str
    value: str
    provenance: str
    recorded_at: str
    source: Optional[str] = None

    @property
    def trusted(self) -> bool:
        return self.provenance in TRUSTED_PROVENANCES

    def as_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def _utc_now() -> _datetime.datetime:
    return _datetime.datetime.now(_datetime.timezone.utc)


def _iso(moment: _datetime.datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_datetime.timezone.utc)
    return moment.astimezone(_datetime.timezone.utc).isoformat(
        timespec="microseconds"
    )


class AcquisitionBrief:
    """Persistent brief plus its guided interview and asset registry.

    All state lives in one JSON document written by atomic replace. Readers
    never see a half-written file; an interrupted writer leaves the previous
    valid document in place.
    """

    def __init__(
        self,
        path: str,
        *,
        clock: Optional[Callable[[], _datetime.datetime]] = None,
    ) -> None:
        self.path = os.path.abspath(path)
        self._clock = clock or _utc_now
        self._state: Dict[str, Any] = self._empty_state()
        self.load()

    # ---------------------------------------------------------------- state

    def _empty_state(self) -> Dict[str, Any]:
        now = _iso(self._clock())
        return {
            "schema": SCHEMA,
            "created_at": now,
            "updated_at": now,
            "facts": {},
            "unresolved": {},
            "interview": {
                "session_id": None,
                "status": INTERVIEW_NOT_STARTED,
                "started_at": None,
                "pending_fact_id": None,
                "events": [],
            },
            "assets": {},
        }

    def _now(self) -> str:
        return _iso(self._clock())

    def load(self) -> "AcquisitionBrief":
        if not os.path.exists(self.path):
            return self
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, ValueError) as exc:
            raise BriefCorruptError(
                "cannot read acquisition brief at %s: %s" % (self.path, exc)
            ) from exc
        if not isinstance(document, dict):
            raise BriefCorruptError(
                "acquisition brief at %s is not a JSON object" % self.path
            )
        if document.get("schema") != SCHEMA:
            raise BriefCorruptError(
                "acquisition brief at %s has schema %r, expected %r"
                % (self.path, document.get("schema"), SCHEMA)
            )
        for key in ("facts", "unresolved", "interview", "assets"):
            if not isinstance(document.get(key), dict):
                raise BriefCorruptError(
                    "acquisition brief at %s is missing %r" % (self.path, key)
                )
        self._state = document
        return self

    def save(self) -> None:
        """Atomically persist. A crash leaves the previous document intact."""
        self._state["updated_at"] = self._now()
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix="." + os.path.basename(self.path) + ".",
            suffix=".tmp",
            dir=directory,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    self._state,
                    handle,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        self._fsync_directory(directory)

    @staticmethod
    def _fsync_directory(directory: str) -> None:
        try:
            descriptor = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)

    # ---------------------------------------------------------------- facts

    def _fact_spec(self, fact_id: str) -> FactSpec:
        spec = FACT_SPECS_BY_ID.get(fact_id)
        if spec is None:
            raise UnknownFactError(
                "%r is not a fact in the acquisition brief" % (fact_id,)
            )
        return spec

    @staticmethod
    def _clean_value(value: Any) -> str:
        if not isinstance(value, str):
            raise InvalidFactError("a fact value must be a string")
        cleaned = value.strip()
        if not cleaned:
            raise InvalidFactError("a fact value must not be empty")
        return cleaned

    @staticmethod
    def _check_provenance(provenance: Any) -> str:
        if provenance not in PROVENANCES:
            raise InvalidFactError(
                "provenance must be one of %s, got %r"
                % (", ".join(PROVENANCES), provenance)
            )
        return provenance

    def _append_event(self, event: Dict[str, Any]) -> None:
        event = dict(event)
        event.setdefault("at", self._now())
        self._state["interview"]["events"].append(event)

    def record_fact(
        self,
        fact_id: str,
        value: Any,
        *,
        provenance: str,
        source: Optional[str] = None,
        save: bool = True,
    ) -> Fact:
        """Record a fact a person or a source actually supplied.

        Re-recording the identical value and provenance is an idempotent no-op:
        no duplicate event, no changed timestamp. Nothing here supplies a
        default value for an absent fact.
        """
        spec = self._fact_spec(fact_id)
        cleaned = self._clean_value(value)
        provenance = self._check_provenance(provenance)
        if source is not None and not isinstance(source, str):
            raise InvalidFactError("source must be a string or None")

        facts = self._state["facts"]
        existing = facts.get(fact_id)
        if (
            isinstance(existing, dict)
            and existing.get("value") == cleaned
            and existing.get("provenance") == provenance
            and existing.get("source") == source
        ):
            return self._as_fact(spec, existing)

        recorded_at = self._now()
        facts[fact_id] = {
            "value": cleaned,
            "provenance": provenance,
            "recorded_at": recorded_at,
            "source": source,
        }
        self._state["unresolved"].pop(fact_id, None)
        self._append_event(
            {
                "event": "fact_recorded" if existing is None else "fact_updated",
                "fact_id": fact_id,
                "provenance": provenance,
                "recorded_at": recorded_at,
            }
        )
        interview = self._state["interview"]
        if interview.get("pending_fact_id") == fact_id:
            interview["pending_fact_id"] = None
        if save:
            self.save()
        return self._as_fact(spec, facts[fact_id])

    @staticmethod
    def _as_fact(spec: FactSpec, record: Dict[str, Any]) -> Fact:
        return Fact(
            fact_id=spec.fact_id,
            section=spec.section,
            key=spec.key,
            value=record.get("value"),
            provenance=record.get("provenance"),
            recorded_at=record.get("recorded_at"),
            source=record.get("source"),
        )

    def mark_missing(self, fact_id: str, reason: str) -> None:
        """Record that nobody knows this fact.

        The fact stays absent: no value is written, no default is supplied. A
        required missing fact blocks campaign readiness, and the question is
        not asked again.
        """
        spec = self._fact_spec(fact_id)
        if fact_id in self._state["facts"]:
            raise InvalidFactError(
                "%s already has a recorded value; clear it before marking it missing"
                % fact_id
            )
        cleaned = self._clean_value(reason)
        self._state["unresolved"][fact_id] = {
            "reason": cleaned,
            "recorded_at": self._now(),
        }
        self._append_event(
            {"event": "fact_marked_missing", "fact_id": fact_id, "reason": cleaned}
        )
        if self._state["interview"].get("pending_fact_id") == fact_id:
            self._state["interview"]["pending_fact_id"] = None
        self.save()

    def get(self, fact_id: str) -> Optional[Fact]:
        """Return the recorded fact, or None when it is unanswered.

        None means "not known". It is never a substitute value.
        """
        spec = self._fact_spec(fact_id)
        record = self._state["facts"].get(fact_id)
        return self._as_fact(spec, record) if record else None

    def require(self, fact_id: str) -> Fact:
        """Return a fact or fail loudly. There is no fallback value."""
        fact = self.get(fact_id)
        if fact is None:
            raise MissingFactError(
                "%s has no recorded value; record it from a real source first"
                % fact_id
            )
        return fact

    def known_fact_ids(self) -> List[str]:
        return [spec.fact_id for spec in FACT_SPECS if spec.fact_id in self._state["facts"]]

    def unresolved_fact_ids(self) -> List[str]:
        unresolved = self._state["unresolved"]
        return [spec.fact_id for spec in FACT_SPECS if spec.fact_id in unresolved]

    def assumptions(self) -> List[Fact]:
        return [
            self._as_fact(spec, self._state["facts"][spec.fact_id])
            for spec in FACT_SPECS
            if self._state["facts"].get(spec.fact_id, {}).get("provenance")
            == PROVENANCE_ASSUMED
        ]

    def facts_by_section(self) -> Dict[str, Dict[str, Fact]]:
        grouped: Dict[str, Dict[str, Fact]] = {section: {} for section in SECTION_ORDER}
        for spec in FACT_SPECS:
            record = self._state["facts"].get(spec.fact_id)
            if record:
                grouped.setdefault(spec.section, {})[spec.key] = self._as_fact(
                    spec, record
                )
        return grouped

    # ------------------------------------------------------------ questions

    def _unanswered(self, *, include_optional: bool) -> List[FactSpec]:
        unanswered: List[FactSpec] = []
        for spec in FACT_SPECS:
            if not include_optional and not spec.required:
                continue
            if spec.fact_id in self._state["facts"]:
                continue
            if spec.fact_id in self._state["unresolved"]:
                continue
            unanswered.append(spec)
        unanswered.sort(key=lambda item: (item.priority, item.fact_id))
        return unanswered

    def _unconfirmed_assumptions(self) -> List[FactSpec]:
        candidates: List[FactSpec] = []
        for spec in FACT_SPECS:
            record = self._state["facts"].get(spec.fact_id, {})
            if record.get("provenance") == PROVENANCE_ASSUMED:
                candidates.append(spec)
        candidates.sort(key=lambda item: (item.priority, item.fact_id))
        return candidates

    def next_questions(
        self, *, include_optional: bool = False, limit: Optional[int] = None
    ) -> List[Question]:
        """Minimal ordered next-question set.

        Empty when the brief is sufficient for a campaign plan. Facts already
        recorded are never included; an assumed fact appears once as a
        confirmation, not as an open question.
        """
        questions: List[Question] = []
        for spec in self._unanswered(include_optional=include_optional):
            questions.append(
                Question(
                    fact_id=spec.fact_id,
                    section=spec.section,
                    key=spec.key,
                    text=spec.question,
                    required=spec.required,
                    priority=spec.priority,
                    kind="missing",
                )
            )
        for spec in self._unconfirmed_assumptions():
            if not include_optional and not spec.required:
                continue
            questions.append(
                Question(
                    fact_id=spec.fact_id,
                    section=spec.section,
                    key=spec.key,
                    text="Please confirm: " + spec.question,
                    required=spec.required,
                    priority=spec.priority,
                    kind="confirm",
                )
            )
        questions.sort(key=lambda item: (item.priority, item.kind, item.fact_id))
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must not be negative")
            questions = questions[:limit]
        return questions

    def is_sufficient(self) -> bool:
        """True only when every required fact is known and trusted."""
        for spec in FACT_SPECS:
            if not spec.required:
                continue
            record = self._state["facts"].get(spec.fact_id)
            if not record:
                return False
            if record.get("provenance") not in TRUSTED_PROVENANCES:
                return False
        return True

    # ------------------------------------------------------------ interview

    def start_interview(self) -> Dict[str, Any]:
        """Begin (or resume) the interview. Never resets recorded work."""
        interview = self._state["interview"]
        if interview.get("session_id") is None:
            interview["session_id"] = uuid.uuid4().hex
            interview["started_at"] = self._now()
            self._append_event(
                {"event": "interview_started", "session_id": interview["session_id"]}
            )
        interview["status"] = self._interview_status()
        self.save()
        return self.status()

    def _interview_status(self) -> str:
        interview = self._state["interview"]
        if interview.get("session_id") is None:
            return INTERVIEW_NOT_STARTED
        if self.is_sufficient():
            return INTERVIEW_SUFFICIENT
        if not self.next_questions():
            # Every required fact is either answered or explicitly missing,
            # and no assumption is waiting for confirmation.
            return INTERVIEW_BLOCKED
        return INTERVIEW_IN_PROGRESS

    def ask_next(self) -> Optional[Question]:
        """Return the question to ask now and persist it as pending.

        Calling this twice without an answer returns the same question, never
        a second copy.
        """
        interview = self._state["interview"]
        if interview.get("session_id") is None:
            self.start_interview()
            interview = self._state["interview"]

        pending_id = interview.get("pending_fact_id")
        if pending_id:
            pending = self._pending_question(pending_id)
            if pending is not None:
                return pending

        questions = self.next_questions()
        if not questions:
            interview["pending_fact_id"] = None
            interview["status"] = self._interview_status()
            self.save()
            return None

        question = questions[0]
        interview["pending_fact_id"] = question.fact_id
        interview["status"] = self._interview_status()
        events = interview["events"]
        already_asked = any(
            event.get("event") == "question_asked"
            and event.get("fact_id") == question.fact_id
            and event.get("kind") == question.kind
            for event in events
        )
        if not already_asked:
            self._append_event(
                {
                    "event": "question_asked",
                    "fact_id": question.fact_id,
                    "kind": question.kind,
                }
            )
        self.save()
        return question

    def _pending_question(self, fact_id: str) -> Optional[Question]:
        spec = FACT_SPECS_BY_ID.get(fact_id)
        if spec is None:
            return None
        record = self._state["facts"].get(fact_id)
        if record is None and fact_id not in self._state["unresolved"]:
            return Question(
                fact_id=spec.fact_id,
                section=spec.section,
                key=spec.key,
                text=spec.question,
                required=spec.required,
                priority=spec.priority,
                kind="missing",
            )
        if record and record.get("provenance") == PROVENANCE_ASSUMED:
            return Question(
                fact_id=spec.fact_id,
                section=spec.section,
                key=spec.key,
                text="Please confirm: " + spec.question,
                required=spec.required,
                priority=spec.priority,
                kind="confirm",
            )
        return None

    def answer(
        self,
        fact_id: str,
        value: Any,
        *,
        provenance: str = PROVENANCE_CLIENT_STATED,
        source: Optional[str] = None,
    ) -> Fact:
        """Answer the pending (or named) question and persist immediately."""
        if self._state["interview"].get("session_id") is None:
            self.start_interview()
        before = self.get(fact_id)
        fact = self.record_fact(
            fact_id, value, provenance=provenance, source=source, save=False
        )
        unchanged = (
            before is not None
            and before.value == fact.value
            and before.provenance == fact.provenance
            and before.source == fact.source
        )
        interview = self._state["interview"]
        if interview.get("pending_fact_id") == fact_id:
            interview["pending_fact_id"] = None
        interview["status"] = self._interview_status()
        if not unchanged:
            self._append_event(
                {
                    "event": "question_answered",
                    "fact_id": fact_id,
                    "provenance": provenance,
                }
            )
        self.save()
        return fact

    def resume(self) -> Dict[str, Any]:
        """What an interrupted interview must show on reopen."""
        interview = self._state["interview"]
        pending = None
        pending_id = interview.get("pending_fact_id")
        if pending_id:
            pending = self._pending_question(pending_id)
        if pending is None:
            questions = self.next_questions()
            pending = questions[0] if questions else None
        return {
            "session_id": interview.get("session_id"),
            "status": self._interview_status(),
            "pending_question": pending.as_dict() if pending else None,
            "known_fact_ids": self.known_fact_ids(),
            "unresolved_fact_ids": self.unresolved_fact_ids(),
            "assumption_fact_ids": [fact.fact_id for fact in self.assumptions()],
        }

    def status(self) -> Dict[str, Any]:
        interview = self._state["interview"]
        return {
            "schema": SCHEMA,
            "path": self.path,
            "session_id": interview.get("session_id"),
            "status": self._interview_status(),
            "is_sufficient": self.is_sufficient(),
            "known_count": len(self.known_fact_ids()),
            "required_count": sum(1 for spec in FACT_SPECS if spec.required),
            "unresolved_count": len(self.unresolved_fact_ids()),
            "assumption_count": len(self.assumptions()),
            "next_question_count": len(self.next_questions()),
        }

    # ---------------------------------------------------------------- assets

    def assess_asset(
        self,
        kind: str,
        status: str,
        *,
        detail: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record whether the client has an asset kind. Never creates one.

        `detail` is a pointer (a path, a link, or the reason it is absent), not
        asset content. An unassessed kind stays unknown: it is never assumed
        present or absent.
        """
        if kind not in ASSET_KINDS:
            raise UnknownAssetError(
                "%r is not an asset kind; expected one of %s"
                % (kind, ", ".join(ASSET_KINDS))
            )
        if status not in ASSET_STATUSES:
            raise InvalidFactError(
                "asset status must be one of %s, got %r"
                % (", ".join(ASSET_STATUSES), status)
            )
        if detail is not None and not isinstance(detail, str):
            raise InvalidFactError("asset detail must be a string or None")
        if source is not None and source not in PROVENANCES:
            raise InvalidFactError("asset source must be a provenance or None")

        record = {
            "kind": kind,
            "status": status,
            "detail": detail,
            "source": source,
            "recorded_at": self._now(),
            "required_for_campaign": kind in ASSET_REQUIRED_FOR_CAMPAIGN,
        }
        self._state["assets"][kind] = record
        self._append_event(
            {"event": "asset_assessed", "kind": kind, "status": status}
        )
        self.save()
        return dict(record)

    def asset_report(self) -> Dict[str, List[Any]]:
        """Present, confirmed-missing, must-prepare, and unassessed assets.

        must_prepare is the hand-off to T-07: required kinds the client has
        confirmed they do not have. Unassessed kinds are never moved into
        missing or must_prepare, because that would be inventing an answer.
        """
        report: Dict[str, List[Any]] = {
            "present": [],
            "missing": [],
            "must_prepare": [],
            "unassessed": [],
            "optional_missing": [],
        }
        for kind in ASSET_KINDS:
            record = self._state["assets"].get(kind)
            required = kind in ASSET_REQUIRED_FOR_CAMPAIGN
            if record is None:
                report["unassessed"].append(kind)
                continue
            entry = {
                "kind": kind,
                "detail": record.get("detail"),
                "source": record.get("source"),
                "recorded_at": record.get("recorded_at"),
                "required_for_campaign": required,
            }
            if record.get("status") == ASSET_PRESENT:
                report["present"].append(entry)
            elif required:
                report["missing"].append(entry)
                report["must_prepare"].append(kind)
            else:
                report["optional_missing"].append(entry)
        return report

    # ------------------------------------------------------------- readiness

    def planning_blockers(self) -> List[Dict[str, str]]:
        """Everything that stops a 30-day campaign plan, named exactly."""
        blockers: List[Dict[str, str]] = []
        for spec in FACT_SPECS:
            if not spec.required:
                continue
            record = self._state["facts"].get(spec.fact_id)
            if record is None:
                if spec.fact_id in self._state["unresolved"]:
                    blockers.append(
                        {
                            "kind": "missing_fact",
                            "fact_id": spec.fact_id,
                            "reason": self._state["unresolved"][spec.fact_id].get(
                                "reason", ""
                            ),
                        }
                    )
                else:
                    blockers.append(
                        {"kind": "unanswered_fact", "fact_id": spec.fact_id, "reason": ""}
                    )
            elif record.get("provenance") == PROVENANCE_ASSUMED:
                blockers.append(
                    {
                        "kind": "unconfirmed_assumption",
                        "fact_id": spec.fact_id,
                        "reason": "recorded as assumed",
                    }
                )
        assets = self.asset_report()
        for kind in assets["must_prepare"]:
            blockers.append(
                {"kind": "asset_must_prepare", "fact_id": kind, "reason": ""}
            )
        for kind in assets["unassessed"]:
            if kind in ASSET_REQUIRED_FOR_CAMPAIGN:
                blockers.append(
                    {"kind": "asset_unassessed", "fact_id": kind, "reason": ""}
                )
        return blockers

    def is_campaign_ready(self) -> bool:
        return not self.planning_blockers()

    # -------------------------------------------------------------- snapshot

    def snapshot(self) -> Dict[str, Any]:
        """Complete planner-facing view. Absent facts appear only as missing."""
        return {
            "schema": SCHEMA,
            "sections": {
                section: {
                    key: fact.as_dict() for key, fact in facts.items()
                }
                for section, facts in self.facts_by_section().items()
            },
            "unanswered_fact_ids": [
                spec.fact_id
                for spec in FACT_SPECS
                if spec.fact_id not in self._state["facts"]
                and spec.fact_id not in self._state["unresolved"]
            ],
            "unresolved": dict(self._state["unresolved"]),
            "assumptions": [fact.as_dict() for fact in self.assumptions()],
            "assets": self.asset_report(),
            "next_questions": [
                question.as_dict() for question in self.next_questions()
            ],
            "is_sufficient": self.is_sufficient(),
            "is_campaign_ready": self.is_campaign_ready(),
            "planning_blockers": self.planning_blockers(),
            "status": self.status(),
        }

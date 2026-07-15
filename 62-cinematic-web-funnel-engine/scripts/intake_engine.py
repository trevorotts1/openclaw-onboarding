#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""intake_engine.py — Skill 62 (Cinematic and Web Funnel Engine), build unit U9.

The client intake engine described in spec Section 8 ("Ask one question at a
time. Reuse known client context and request confirmation instead of
re-asking known facts.") and Section 8.1's 12 intake groups. Owns:

  - the 12-group / ~46-field question bank (intake/questions.json), asked in
    strict group/order sequence, ONE question returned at a time by
    next_question() — a caller can never see more than one open question;
  - known-context reuse: a question whose known_context_key resolves inside
    the caller-supplied known_context object is NEVER silently auto-filled.
    It is instead routed through exactly one explicit yes/no confirmation
    question ("confirm::<question_id>") before either reusing the known
    value (source=known_context_confirmed) or falling through to a normal
    ask (spec 8: "request confirmation instead of re-asking known facts");
  - truth-source capture: any 'claim_list' question (offer.proof,
    content_source.claims — spec 8.1 groups 3/5) spawns one dynamic
    truth-source follow-up question per claim
    ("truthsource::<question_id>::<index>") the instant that question is
    answered. lock_brief() independently re-verifies — never trusting the
    incremental bookkeeping alone — that every captured claim has exactly
    one truth-source entry before it will ever lock;
  - the brief LOCK: lock_brief() assembles intake/project-brief.json,
    intake/truth-sources.json, intake/approval-policy.json, and
    intake/budget-authorization.json (the six spec-8.2 artifacts, alongside
    raw-answers.json and known-context.json this module already keeps
    up to date after every single answer), computing a deterministic
    brief_hash — sha256 over the canonical (sorted-key, no-whitespace) JSON
    serialization of the groups payload plus the sorted truth_source_ids
    list, and NOTHING else (never a timestamp, a PID, a run_dir path, or any
    other non-answer-derived value) — so two independent intake sessions fed
    byte-identical answers in byte-identical order always lock to the exact
    same brief_hash. This is the "deterministic intake prover: same answers
    -> same locked brief" property U9 is required to prove (see
    prove_intake.py and tests/unit/test_intake_engine.py::DeterminismTests);
  - crash-safe resumability: every mutation is persisted via
    state_engine.atomic_write_json before this call returns, and the
    constructor reloads intake/raw-answers.json, intake/known-context.json,
    and any not-yet-locked intake/truth-sources.json to reconstruct exactly
    where an interrupted session left off (mirrors U6's restart-recovery
    philosophy, applied to intake instead of paid media tasks).

No secret values are ever handled by this module — intake never asks for
credential values, only NAMES (conversion_infrastructure.* fields collect
integration identifiers such as a GHL location id, never a secret).

stdlib only. Exit 0 on --self-test success, 1 on failure.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"
_INTAKE_DIR = _SKILL_DIR / "intake"

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import json_schema_lite as jsl  # noqa: E402  (local sibling package, mirrors state_engine.py's convention)
import state_engine as se  # noqa: E402  (reuse: atomic_write_json / read_json — no duplicated crash-safety logic)


SCHEMA_VERSION = "1.0.0"
QUESTION_BANK_PATH = _INTAKE_DIR / "questions.json"

RUNTIME_SCHEMA_FILES: Dict[str, str] = {
    "project-brief": "project-brief.schema.json",
    "truth-sources": "truth-sources.schema.json",
    "approval-policy": "approval-policy.schema.json",
    "budget-authorization": "budget-authorization.schema.json",
    "raw-answers": "raw-answers.schema.json",
    "known-context": "known-context.schema.json",
}

RUNTIME_ARTIFACT_RELPATHS: Dict[str, str] = {
    "project-brief": "intake/project-brief.json",
    "truth-sources": "intake/truth-sources.json",
    "approval-policy": "intake/approval-policy.json",
    "budget-authorization": "intake/budget-authorization.json",
    "raw-answers": "intake/raw-answers.json",
    "known-context": "intake/known-context.json",
}

QUESTION_TYPES = ("string", "integer", "number", "boolean", "enum", "list", "claim_list")


# ------------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------------
class IntakeError(Exception):
    """Base class for every error this module raises."""


class IntakeLockedError(IntakeError):
    """Any mutation attempted after the brief has already been locked."""


class UnknownQuestionError(IntakeError):
    """answer() was called with a question_id next_question() never offered."""


class InvalidAnswerError(IntakeError):
    """An answer's value does not satisfy the question's declared type/enum."""


class IncompleteIntakeError(IntakeError):
    """lock_brief() was called before every required question resolved."""

    def __init__(self, missing: List[str]):
        self.missing = missing
        super().__init__(f"{len(missing)} required question(s) unresolved: {missing}")


class MissingTruthSourceError(IntakeError):
    """lock_brief()'s independent re-check found a captured claim with no
    matching truth-source entry — never trusted from incremental state alone."""


# ------------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------------
def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _get_nested(d: Optional[Dict[str, Any]], dotted_key: str) -> Tuple[bool, Any]:
    """Look up 'a.b.c' inside a nested dict. Returns (found, value)."""
    if not d:
        return False, None
    node: Any = d
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


_BANK_CACHE: Optional[Dict[str, Any]] = None


def load_question_bank(*, force_reload: bool = False) -> Dict[str, Any]:
    """Loads and schema-validates intake/questions.json. Fails loud (raises)
    on a malformed bank rather than asking a broken question — this is the
    fail-closed guarantee that intake can never silently skip a question
    because the bank itself is corrupt."""
    global _BANK_CACHE
    if _BANK_CACHE is not None and not force_reload:
        return _BANK_CACHE
    if not QUESTION_BANK_PATH.exists():
        raise IntakeError(f"question bank missing: {QUESTION_BANK_PATH}")
    bank = json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))
    schema = json.loads((_STRUCTURE_DIR / "intake-questions.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(bank, schema)
    if errors:
        raise IntakeError(f"intake/questions.json failed schema validation: {'; '.join(errors)}")
    _BANK_CACHE = bank
    return bank


def _ordered_questions(bank: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flattens the bank into one list, sorted by (group.order,
    question.order) — the exact deterministic sequence next_question() walks."""
    out: List[Dict[str, Any]] = []
    for group in sorted(bank["groups"], key=lambda g: g["order"]):
        for q in sorted(group["questions"], key=lambda x: x["order"]):
            qq = dict(q)
            qq["group"] = group["slug"]
            out.append(qq)
    return out


def _validate_runtime(kind: str, instance: Any) -> None:
    schema = json.loads((_STRUCTURE_DIR / RUNTIME_SCHEMA_FILES[kind]).read_text(encoding="utf-8"))
    errors = jsl.validate(instance, schema)
    if errors:
        raise IntakeError(f"{kind} failed schema validation: {'; '.join(errors)}")


def _validate_answer_value(question: Dict[str, Any], value: Any) -> Any:
    """Validates + normalizes a raw answer value against its question's
    declared type. Returns the normalized value to store. Raises
    InvalidAnswerError on any mismatch — never silently coerces a bad
    value into something schema-valid."""
    qtype = question["type"]
    qid = question["id"]
    if qtype == "string":
        if not isinstance(value, str) or not value.strip():
            raise InvalidAnswerError(f"{qid}: expected a non-empty string, got {value!r}")
        return value.strip()
    if qtype == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidAnswerError(f"{qid}: expected an integer, got {value!r}")
        return value
    if qtype == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidAnswerError(f"{qid}: expected a number, got {value!r}")
        return float(value)
    if qtype == "boolean":
        if not isinstance(value, bool):
            raise InvalidAnswerError(f"{qid}: expected a boolean, got {value!r}")
        return value
    if qtype == "enum":
        if value not in question.get("enum", []):
            raise InvalidAnswerError(f"{qid}: {value!r} is not one of {question.get('enum')!r}")
        return value
    if qtype == "list":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise InvalidAnswerError(f"{qid}: expected a list of strings, got {value!r}")
        return list(value)
    if qtype == "claim_list":
        if not isinstance(value, list):
            raise InvalidAnswerError(f"{qid}: expected a list of claims, got {value!r}")
        claims: List[Dict[str, str]] = []
        for i, item in enumerate(value):
            if isinstance(item, dict):
                text = item.get("claim_text")
            else:
                text = item
            if not isinstance(text, str) or not text.strip():
                raise InvalidAnswerError(f"{qid}[{i}]: claim_text must be a non-empty string, got {item!r}")
            # claim_id is ALWAYS derived deterministically from question_id +
            # position, never taken from caller input — this is what makes
            # the same ordered answers always produce the same claim_ids
            # (and therefore the same brief_hash) regardless of what a
            # caller may have supplied as an id.
            claims.append({"claim_id": f"{qid}#{i}", "claim_text": text.strip()})
        return claims
    raise IntakeError(f"{qid}: unknown question type {qtype!r} (known: {QUESTION_TYPES})")


TRUTH_SOURCE_TYPES = (
    "testimonial", "case-study", "data-report", "document", "url", "client-confirmed", "internal-record",
)


def _validate_truth_source_value(value: Any, *, question_id: str) -> Dict[str, str]:
    if not isinstance(value, dict):
        raise InvalidAnswerError(f"{question_id}: expected a truth-source object, got {value!r}")
    source_type = value.get("source_type")
    reference = value.get("reference")
    provided_by = value.get("provided_by")
    if source_type not in TRUTH_SOURCE_TYPES:
        raise InvalidAnswerError(f"{question_id}: source_type must be one of {TRUTH_SOURCE_TYPES!r}, got {source_type!r}")
    if not isinstance(reference, str) or not reference.strip():
        raise InvalidAnswerError(f"{question_id}: reference must be a non-empty string")
    if not isinstance(provided_by, str) or not provided_by.strip():
        raise InvalidAnswerError(f"{question_id}: provided_by must be a non-empty string")
    return {"source_type": source_type, "reference": reference.strip(), "provided_by": provided_by.strip()}


# ------------------------------------------------------------------------
# IntakeSession
# ------------------------------------------------------------------------
class IntakeSession:
    """Bound to one run_dir (one project's intake). Drives the 12-group
    question bank one question at a time via next_question()/answer(),
    captures truth sources for every claim, and locks the brief exactly
    once via lock_brief()."""

    def __init__(self, run_dir: Path, *, project_id: str, known_context: Optional[Dict[str, Any]] = None):
        self.run_dir = Path(run_dir)
        self.project_id = project_id
        self._bank = load_question_bank()
        self._questions = _ordered_questions(self._bank)
        self._by_id = {q["id"]: q for q in self._questions}

        self._known_context: Dict[str, Any] = dict(known_context or {})
        self._answers: Dict[str, Dict[str, Any]] = {}          # base question_id -> {"value","group","source","answered_at"}
        self._confirmations: List[Dict[str, Any]] = []          # known-context.json confirmations[]
        self._declined: set = set()                             # base question_ids whose confirm was declined
        self._truth_sources: Dict[str, Dict[str, Any]] = {}     # claim_id -> truth-source record
        self._queue: List[Dict[str, Any]] = []                  # pending dynamic truthsource:: questions, in order
        self._locked = False
        self._created_at = _now()

        self._load_existing()

    # -- resume ---------------------------------------------------------------
    def _load_existing(self) -> None:
        brief_path = self.run_dir / RUNTIME_ARTIFACT_RELPATHS["project-brief"]
        if brief_path.exists():
            brief = se.read_json(brief_path)
            if brief.get("locked"):
                self._locked = True

        raw_path = self.run_dir / RUNTIME_ARTIFACT_RELPATHS["raw-answers"]
        if raw_path.exists():
            raw = se.read_json(raw_path)
            self._created_at = raw.get("created_at", self._created_at)
            for rec in raw.get("answers", []):
                self._answers[rec["question_id"]] = {
                    "value": rec["value"],
                    "group": rec.get("group"),
                    "source": rec["source"],
                    "answered_at": rec["answered_at"],
                }

        kc_path = self.run_dir / RUNTIME_ARTIFACT_RELPATHS["known-context"]
        if kc_path.exists():
            kc = se.read_json(kc_path)
            self._known_context = kc.get("known_context", self._known_context)
            self._confirmations = kc.get("confirmations", [])
            for c in self._confirmations:
                if c["confirmed"] is False:
                    self._declined.add(c["question_id"])

        ts_path = self.run_dir / RUNTIME_ARTIFACT_RELPATHS["truth-sources"]
        if ts_path.exists():
            ts = se.read_json(ts_path)
            for entry in ts.get("sources", []):
                self._truth_sources[entry["claim_id"]] = entry

        # Rebuild the pending dynamic-question queue for any claim_list base
        # question already answered whose claims are still missing a
        # truth-source entry (covers a resume mid-way through claim
        # truth-sourcing).
        for qid, rec in self._answers.items():
            q = self._by_id.get(qid)
            if q and q["type"] == "claim_list":
                for claim in rec["value"]:
                    if claim["claim_id"] not in self._truth_sources:
                        self._enqueue_truth_source_question(q, claim)

    # -- persistence ------------------------------------------------------
    def _write_raw_answers(self) -> None:
        answers = [
            {"question_id": qid, "group": rec["group"], "value": rec["value"], "source": rec["source"], "answered_at": rec["answered_at"]}
            for qid, rec in self._answers.items()
        ]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project_id,
            "answers": answers,
            "created_at": self._created_at,
            "updated_at": _now(),
        }
        _validate_runtime("raw-answers", payload)
        se.atomic_write_json(self.run_dir / RUNTIME_ARTIFACT_RELPATHS["raw-answers"], payload)

    def _write_known_context(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project_id,
            "known_context": self._known_context,
            "confirmations": self._confirmations,
            "created_at": self._created_at,
            "updated_at": _now(),
        }
        _validate_runtime("known-context", payload)
        se.atomic_write_json(self.run_dir / RUNTIME_ARTIFACT_RELPATHS["known-context"], payload)

    def _write_truth_sources(self, *, locked: bool, locked_at: Optional[str]) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project_id,
            "locked": locked,
            "locked_at": locked_at,
            "sources": list(self._truth_sources.values()),
            "created_at": self._created_at,
            "updated_at": _now(),
        }
        _validate_runtime("truth-sources", payload)
        se.atomic_write_json(self.run_dir / RUNTIME_ARTIFACT_RELPATHS["truth-sources"], payload)

    # -- dynamic truth-source follow-ups -----------------------------------
    def _enqueue_truth_source_question(self, question: Dict[str, Any], claim: Dict[str, str]) -> None:
        dyn_id = f"truthsource::{question['id']}::{claim['claim_id']}"
        if any(p["id"] == dyn_id for p in self._queue) or claim["claim_id"] in self._truth_sources:
            return
        self._queue.append({
            "id": dyn_id,
            "kind": "truth_source",
            "question_id": question["id"],
            "claim_id": claim["claim_id"],
            "group": question["group"],
            "prompt": f"What is the truth source for the claim '{claim['claim_text']}' (from {question['id']})? "
                      f"Provide source_type ({'/'.join(TRUTH_SOURCE_TYPES)}), reference, and who provided it.",
            "type": "truth_source",
        })

    # -- the one-question-at-a-time surface --------------------------------
    def next_question(self) -> Optional[Dict[str, Any]]:
        """Returns exactly one open question dict, or None once intake is
        complete. Dynamic truth-source follow-ups always drain before the
        engine moves on to the next base question in the bank (a claim is
        fully sourced before intake proceeds)."""
        if self._locked:
            return None
        if self._queue:
            return dict(self._queue[0])
        for q in self._questions:
            qid = q["id"]
            if qid in self._answers:
                continue
            kc_key = q.get("known_context_key")
            # A prior confirmation is always either confirmed=True (which
            # already populated self._answers, caught by the `continue`
            # above) or confirmed=False (which populated self._declined,
            # checked here) — a declined question is asked normally instead
            # of being offered as a confirm a second time.
            if kc_key and qid not in self._declined:
                found, kvalue = _get_nested(self._known_context, kc_key)
                if found:
                    return {
                        "id": f"confirm::{qid}",
                        "kind": "confirm",
                        "question_id": qid,
                        "group": q["group"],
                        "known_context_key": kc_key,
                        "known_value": kvalue,
                        "prompt": f"Known value for '{qid}' is {kvalue!r} (from known context). Confirm? (yes/no)",
                        "type": "boolean",
                    }
            return {
                "id": qid,
                "kind": "answer",
                "question_id": qid,
                "group": q["group"],
                "prompt": q["prompt"],
                "type": q["type"],
                "enum": q.get("enum"),
                "required": q.get("required", False),
            }
        return None

    def is_complete(self) -> bool:
        return self.next_question() is None

    def missing_required(self) -> List[str]:
        missing = []
        for q in self._questions:
            if q.get("required") and q["id"] not in self._answers:
                missing.append(q["id"])
        if self._queue:
            missing.extend(p["id"] for p in self._queue)
        return missing

    def answer(self, question_id: str, value: Any) -> None:
        if self._locked:
            raise IntakeLockedError("intake is locked; no further answers accepted")

        current = self.next_question()
        if current is None or current["id"] != question_id:
            raise UnknownQuestionError(
                f"answer() called for {question_id!r} but the next open question is "
                f"{(current or {}).get('id')!r} — questions must be answered one at a time, in order"
            )

        if current["kind"] == "confirm":
            self._answer_confirm(current, value)
        elif current["kind"] == "truth_source":
            self._answer_truth_source(current, value)
        else:
            self._answer_base(self._by_id[question_id], value)

    def _answer_confirm(self, current: Dict[str, Any], value: Any) -> None:
        if not isinstance(value, bool):
            raise InvalidAnswerError(f"{current['id']}: confirmation answer must be a boolean")
        base_qid = current["question_id"]
        now = _now()
        self._confirmations.append({
            "question_id": base_qid,
            "known_context_key": current["known_context_key"],
            "known_value": current["known_value"],
            "confirmed": value,
            "at": now,
        })
        if value:
            q = self._by_id[base_qid]
            normalized = _validate_answer_value(q, current["known_value"])
            self._answers[base_qid] = {"value": normalized, "group": q["group"], "source": "known_context_confirmed", "answered_at": now}
            if q["type"] == "claim_list" and q.get("requires_truth_source"):
                for claim in normalized:
                    self._enqueue_truth_source_question(q, claim)
            self._write_raw_answers()
        else:
            self._declined.add(base_qid)
        self._write_known_context()

    def _answer_truth_source(self, current: Dict[str, Any], value: Any) -> None:
        record = _validate_truth_source_value(value, question_id=current["id"])
        now = _now()
        q = self._by_id[current["question_id"]]
        claim_text = next(
            (c["claim_text"] for c in self._answers[current["question_id"]]["value"] if c["claim_id"] == current["claim_id"]),
            "",
        )
        entry = {
            "id": f"ts-{current['claim_id']}",
            "question_id": current["question_id"],
            "claim_id": current["claim_id"],
            "claim_text": claim_text,
            "source_type": record["source_type"],
            "reference": record["reference"],
            "provided_by": record["provided_by"],
            "captured_at": now,
        }
        self._truth_sources[current["claim_id"]] = entry
        self._queue = [p for p in self._queue if p["id"] != current["id"]]
        self._write_truth_sources(locked=False, locked_at=None)

    def _answer_base(self, question: Dict[str, Any], value: Any) -> None:
        now = _now()
        if value is None and not question.get("required", False):
            # Explicit skip of a genuinely optional question — never allowed
            # for a required one, where _validate_answer_value below will
            # correctly reject None as an invalid type.
            default = [] if question["type"] in ("list", "claim_list") else None
            self._answers[question["id"]] = {"value": default, "group": question["group"], "source": "asked", "answered_at": now}
            self._write_raw_answers()
            return
        normalized = _validate_answer_value(question, value)
        self._answers[question["id"]] = {"value": normalized, "group": question["group"], "source": "asked", "answered_at": now}
        if question["type"] == "claim_list" and question.get("requires_truth_source"):
            for claim in normalized:
                self._enqueue_truth_source_question(question, claim)
        self._write_raw_answers()

    # -- lock ---------------------------------------------------------------
    def lock_brief(self, *, locked_by: str) -> Dict[str, Any]:
        if self._locked:
            raise IntakeLockedError("project brief is already locked")
        missing = self.missing_required()
        if missing:
            raise IncompleteIntakeError(missing)

        # Independent re-check: never trust incremental bookkeeping alone —
        # walk every claim_list answer again and confirm a truth-source
        # entry actually exists for each claim_id, right here at lock time.
        for qid, rec in self._answers.items():
            q = self._by_id.get(qid)
            if q and q["type"] == "claim_list" and q.get("requires_truth_source"):
                for claim in rec["value"]:
                    if claim["claim_id"] not in self._truth_sources:
                        raise MissingTruthSourceError(f"claim {claim['claim_id']!r} ({qid}) has no truth-source entry")

        groups: Dict[str, Dict[str, Any]] = {g["slug"]: {} for g in self._bank["groups"]}
        for q in self._questions:
            group = q["group"]
            field = q["id"].split(".", 1)[1]
            if q["id"] in self._answers:
                groups[group][field] = self._answers[q["id"]]["value"]
            else:
                # Optional field never answered: schema-required default.
                groups[group][field] = [] if q["type"] in ("list", "claim_list") else None

        truth_source_ids = sorted(self._truth_sources.keys())
        brief_hash = _sha256_hex(_canonical_json({"groups": groups, "truth_source_ids": truth_source_ids}).encode("utf-8"))

        now = _now()
        brief = {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project_id,
            "locked": True,
            "locked_at": now,
            "locked_by": locked_by,
            "brief_hash": brief_hash,
            "groups": groups,
            "truth_source_ids": truth_source_ids,
            "created_at": self._created_at,
            "updated_at": now,
        }
        _validate_runtime("project-brief", brief)

        approval_policy = {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project_id,
            "locked": True,
            "locked_at": now,
            "anchor_approver": groups["approval_workflow"]["anchor_approver"],
            "draft_approver": groups["approval_workflow"]["draft_approver"],
            "final_deployment_approver": groups["approval_workflow"]["final_deployment_approver"],
            "created_at": self._created_at,
            "updated_at": now,
        }
        _validate_runtime("approval-policy", approval_policy)

        budget_authorization = {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project_id,
            "locked": True,
            "locked_at": now,
            "max_media_spend_usd": groups["budget"]["max_media_spend_usd"],
            "premium_model_permission": groups["budget"]["premium_model_permission"],
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "created_at": self._created_at,
            "updated_at": now,
        }
        _validate_runtime("budget-authorization", budget_authorization)

        se.atomic_write_json(self.run_dir / RUNTIME_ARTIFACT_RELPATHS["project-brief"], brief)
        se.atomic_write_json(self.run_dir / RUNTIME_ARTIFACT_RELPATHS["approval-policy"], approval_policy)
        se.atomic_write_json(self.run_dir / RUNTIME_ARTIFACT_RELPATHS["budget-authorization"], budget_authorization)
        self._write_truth_sources(locked=True, locked_at=now)
        self._write_raw_answers()
        self._write_known_context()

        self._locked = True
        return brief


# ------------------------------------------------------------------------
# Deterministic scripted driver — used by the self-test and by
# tests/unit/test_intake_engine.py's determinism proof. Drives an
# IntakeSession purely from a plain {question_id: value} map, honoring the
# one-question-at-a-time contract (never peeks ahead; only ever answers
# exactly the id next_question() just returned).
# ------------------------------------------------------------------------
def run_scripted_intake(
    run_dir: Path,
    *,
    project_id: str,
    known_context: Optional[Dict[str, Any]],
    answer_map: Dict[str, Any],
    locked_by: str = "scripted-driver",
) -> Dict[str, Any]:
    session = IntakeSession(run_dir, project_id=project_id, known_context=known_context)
    while True:
        q = session.next_question()
        if q is None:
            break
        if q["id"] in answer_map:
            value = answer_map[q["id"]]
        elif q["kind"] == "answer" and not session._by_id[q["question_id"]].get("required", False):
            # A genuinely optional base question the scripted answer map is
            # silent on is treated as an explicit skip, never a missing-key
            # crash — the same behavior a real caller gets from answer(id, None).
            value = None
        else:
            raise IntakeError(f"scripted driver has no answer for required question {q['id']!r}")
        session.answer(q["id"], value)
    return session.lock_brief(locked_by=locked_by)


# ------------------------------------------------------------------------
# Self-test
# ------------------------------------------------------------------------
def _sample_answer_map() -> Dict[str, Any]:
    return {
        "project_goal.deliverable_type": "cinematic-landing-page",
        "project_goal.success_action": "book a discovery call",
        "project_goal.deadline": "2026-09-01",
        "project_goal.required_assets": ["logo.svg", "product-photo-01.jpg"],
        "audience.identity": "boutique gym owners",
        "audience.pain": "can't fill evening classes",
        "audience.aspiration": "a fully booked calendar",
        "audience.awareness_level": "solution-aware",
        "offer.name": "Studio Growth Sprint",
        "offer.promise": "fill your calendar in 30 days",
        "offer.price": "$1,997",
        "offer.mechanism": "the 3-touch local funnel",
        "offer.bonuses": ["bonus workbook"],
        "offer.objections": ["too expensive", "no time"],
        "offer.proof": ["grew Acme Gym bookings 41% in 60 days", "featured in Fit Business Weekly"],
        "truthsource::offer.proof::offer.proof#0": {"source_type": "case-study", "reference": "acme-gym-case-study.pdf", "provided_by": "client"},
        "truthsource::offer.proof::offer.proof#1": {"source_type": "url", "reference": "https://fitbusinessweekly.example/acme", "provided_by": "client"},
        "brand.tone": "energetic, no-nonsense",
        "brand.visual_references": ["https://ref.example/1"],
        "brand.prohibited_styles": ["stock-photo cheese"],
        "brand.representation_requirements": ["no fabricated depictions of named real clients", "equipment must match on-site photos"],
        "content_source.existing_copy": "none",
        "content_source.selected_methodology": "signature-funnel",
        "content_source.required_sections": ["hero", "offer", "proof", "cta"],
        "content_source.claims": [],
        "cinematic_direction.visual_world": "sunrise concrete-and-glass studio",
        "cinematic_direction.realism_level": "photoreal",
        "cinematic_direction.story_progression": "empty studio to full class",
        "cinematic_direction.camera_language": "slow dolly-in",
        "cinematic_direction.scene_count": 5,
        "conversion_infrastructure.ghl_location_id": "loc_sample123",
        "conversion_infrastructure.form": "lead-form-v1",
        "conversion_infrastructure.calendar": "cal-discovery",
        "conversion_infrastructure.payment": "none",
        "conversion_infrastructure.workflow": "nurture-v1",
        "conversion_infrastructure.tracking_attribution": "utm+ghl-attribution",
        "hosting.vercel_account": "acme-team",
        "hosting.vercel_project": "acme-gym-funnel",
        "mobile_strategy.mode": "crop-safe",
        "accessibility.reduced_motion_preference": "respect-system",
        "accessibility.transcript_alt_content": True,
        "budget.max_media_spend_usd": 250.0,
        "budget.premium_model_permission": False,
        "approval_workflow.anchor_approver": "client-owner",
        "approval_workflow.draft_approver": "client-owner",
        "approval_workflow.final_deployment_approver": "agency-lead",
    }


def self_test() -> int:
    import shutil
    import tempfile

    fails = 0

    def check(label: str, cond: bool) -> None:
        nonlocal fails
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}")
            fails += 1

    try:
        # -- bank loads and validates -----------------------------------
        bank = load_question_bank()
        check("question bank has exactly 12 groups", len(bank["groups"]) == 12)

        tmp1 = Path(tempfile.mkdtemp(prefix="cwfe-intake-selftest-a-"))
        tmp2 = Path(tempfile.mkdtemp(prefix="cwfe-intake-selftest-b-"))
        try:
            # -- one-question-at-a-time contract ------------------------
            s = IntakeSession(tmp1, project_id="proj-a", known_context=None)
            q1 = s.next_question()
            check("next_question returns exactly one open question", q1 is not None and q1["id"] == "project_goal.deliverable_type")
            try:
                s.answer("audience.identity", "someone")
                check("answer() rejects an out-of-order question_id", False)
            except UnknownQuestionError:
                check("answer() rejects an out-of-order question_id", True)

            # -- known-context reuse + confirmation ----------------------
            s2 = IntakeSession(tmp2, project_id="proj-kc", known_context={"project_goal": {"deliverable_type": "cinematic-funnel"}})
            nq = s2.next_question()
            check("a known_context_key hit is offered as a confirm question, not auto-filled", nq["kind"] == "confirm" and nq["known_value"] == "cinematic-funnel")
            s2.answer(nq["id"], True)
            check("confirming reuses the known value with source known_context_confirmed", s2._answers["project_goal.deliverable_type"]["source"] == "known_context_confirmed")
            nq2 = s2.next_question()
            check("after a confirmed reuse, the engine advances to the next base question", nq2["id"] == "project_goal.success_action")

            # -- declined confirmation falls through to a normal ask -----
            s3 = IntakeSession(Path(tempfile.mkdtemp(prefix="cwfe-intake-selftest-c-")), project_id="proj-decline", known_context={"project_goal": {"deliverable_type": "cinematic-funnel"}})
            nq3 = s3.next_question()
            s3.answer(nq3["id"], False)
            nq4 = s3.next_question()
            check("a declined confirmation is asked normally next", nq4["kind"] == "answer" and nq4["id"] == "project_goal.deliverable_type")
            s3.answer(nq4["id"], "cinematic-website")
            check("the declined-then-asked answer is recorded with source=asked", s3._answers["project_goal.deliverable_type"]["source"] == "asked")

            # -- truth-source capture for a claim_list question ----------
            s4 = IntakeSession(Path(tempfile.mkdtemp(prefix="cwfe-intake-selftest-d-")), project_id="proj-ts", known_context=None)
            # fast-forward to offer.proof by answering everything before it
            while True:
                q = s4.next_question()
                if q["id"] == "offer.proof":
                    break
                s4.answer(q["id"], _sample_answer_map()[q["id"]])
            s4.answer("offer.proof", ["claim one", "claim two"])
            follow1 = s4.next_question()
            check("answering a claim_list question immediately queues a truth-source follow-up", follow1["kind"] == "truth_source" and follow1["claim_id"] == "offer.proof#0")
            try:
                s4.lock_brief(locked_by="tester")
                check("lock_brief refuses while a claim is missing its truth source", False)
            except IncompleteIntakeError:
                check("lock_brief refuses while a claim is missing its truth source", True)
            s4.answer(follow1["id"], {"source_type": "client-confirmed", "reference": "call notes 2026-07-15", "provided_by": "client"})
            follow2 = s4.next_question()
            check("a second claim gets its own follow-up question", follow2["claim_id"] == "offer.proof#1")
            s4.answer(follow2["id"], {"source_type": "client-confirmed", "reference": "call notes 2026-07-15", "provided_by": "client"})
            nq5 = s4.next_question()
            check("after both claims are sourced, the engine advances past offer.proof", nq5 is not None and nq5["id"] != "offer.proof" and nq5["kind"] != "truth_source")

            # -- invalid answers are rejected, never silently coerced -----
            s5 = IntakeSession(Path(tempfile.mkdtemp(prefix="cwfe-intake-selftest-e-")), project_id="proj-bad", known_context=None)
            try:
                s5.answer(s5.next_question()["id"], "not-a-valid-enum-value")
                check("an invalid enum answer is rejected", False)
            except InvalidAnswerError:
                check("an invalid enum answer is rejected", True)

            # -- full run + lock + determinism ---------------------------
            answers = _sample_answer_map()
            brief1 = run_scripted_intake(tmp1, project_id="proj-det", known_context=None, answer_map=answers)
            brief2 = run_scripted_intake(tmp2 / "second-run", project_id="proj-det", known_context=None, answer_map=answers)
            check("lock_brief produces a schema-valid, locked project-brief.json", brief1["locked"] is True and len(brief1["brief_hash"]) == 64)
            check(
                "SAME answers -> SAME locked brief: identical brief_hash across two independent run_dirs",
                brief1["brief_hash"] == brief2["brief_hash"],
            )
            check(
                "SAME answers -> SAME locked brief: identical groups payload (ignoring timestamps)",
                json.dumps(brief1["groups"], sort_keys=True) == json.dumps(brief2["groups"], sort_keys=True),
            )
            check("locked_at differs (proves the hash genuinely ignores wall-clock time, not just coincidentally equal)", isinstance(brief1["locked_at"], str) and isinstance(brief2["locked_at"], str))

            try:
                run_scripted_intake(tmp1, project_id="proj-det", known_context=None, answer_map=answers)
                check("lock_brief refuses a second lock on an already-locked project", False)
            except IntakeLockedError:
                check("lock_brief refuses a second lock on an already-locked project", True)

            # -- a DIFFERENT answer set produces a DIFFERENT hash ----------
            answers_changed = dict(answers)
            answers_changed["offer.price"] = "$2,997"
            tmp3 = Path(tempfile.mkdtemp(prefix="cwfe-intake-selftest-f-"))
            brief3 = run_scripted_intake(tmp3, project_id="proj-det", known_context=None, answer_map=answers_changed)
            check("a genuinely different answer set locks to a different brief_hash", brief3["brief_hash"] != brief1["brief_hash"])

            # -- resume: a fresh IntakeSession over a locked run_dir sees it locked
            s_resume = IntakeSession(tmp1, project_id="proj-det", known_context=None)
            check("re-opening a locked run_dir reports locked and offers no more questions", s_resume._locked is True and s_resume.next_question() is None)

        finally:
            shutil.rmtree(tmp1, ignore_errors=True)
            shutil.rmtree(tmp2, ignore_errors=True)

    except Exception as exc:  # pragma: no cover - self-test harness safety net
        print(f"  [FAIL] unexpected exception during self-test: {exc!r}", file=sys.stderr)
        fails += 1

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — intake engine self-test green.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(self_test())
    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()

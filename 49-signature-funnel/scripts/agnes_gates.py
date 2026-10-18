#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agnes_gates.py -- per-request gates for the Agnes dispatch layer.

A24 Leg 4, build lane B (items G-03, G-04, G-05, G-06, G-11 of the
S71/S49 A24 dispatch contract, rooms/S63/work/a24-support/
S71-S49-A24-DISPATCH-CONTRACT.md). The merged Skill 63 modules are
composable, not turnkey: they evaluate policies, resolve models,
validate payloads, and build receipts as separate pieces, and the
dispatch layer must thread state between them. This module is the
gate layer the orchestrator (agnes_orchestrator.py, a sibling lane)
calls, in the contract section 3 order:

  1. resolve the model              (resolve_model.py, core lane)
  2. load the model record and      translate_cap()          (G-05)
     translate its cap record
  3. evaluate the named policy      evaluate_policy_gate()   (G-04,
     before spend, with the            plus the evaluated half
     caller-supplied truthful          of G-03)
     elements_present set
  4. resolve the governing          resolve_governing_citation()
     registry citation                 (G-03 citation half)
  5. ratio gate against the         check_ratio_authority()  (G-06)
     validation-time authority

and, across the whole run, retain the full model Resolution in
dispatch metadata (DispatchMetadata, G-11): provenance lives in
dispatch metadata only, never in the provider payload and never
in the Agnes receipt, whose schema has no provenance field.

Post-Q1 citation form (G-03): the Q1 ruling (MAIN, 2026-10-17,
under Trevor's Decision 1) superseded the dispatch contract's
policy-choice premise. There is no prompt_policy_id selector and
no policy ID to select per request: dispatch carries the ONE
governing policy, the KIE rule-12 band, whose registry identity
is the entry kie-rule-12-band in the registry of record
(shared-utils/signature_launch/domain/prompt-policy-registry.json).
The gate therefore exposes two distinct values and never confuses
them:

  - PolicyGateOutcome.receipt_policy_id: the evaluated Skill 63
    evaluator's PolicyResult.policy_id, to be passed EXPLICITLY
    to provider_receipt.build_agnes_receipt(prompt_policy_id=...)
    so the receipt builder's default can never mask a missing
    value (contract section 6.1, surviving form).
  - GoverningCitation: the band entry resolved by policy_id plus
    entry_hash, the citation the Q11 budget decision carries
    (map section 4 citation rule: policy_id AND entry_hash).

Every gate fails closed: a malformed cap record, an invalid or
mismatched policy evaluation, an unresolvable citation, or a
ratio disagreement stops the dispatch before spend, by raising
the named exception below. Nothing in this module sends, spends,
or touches the network.

Stdlib only. Exit codes for the optional CLI self-check: 0 ok,
2 gate failure (as in the adapter's validation convention).
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
_SUBSTRATE_DIR = _REPO_ROOT / "63-agnes-image" / "scripts"
if str(_SUBSTRATE_DIR) not in sys.path:
    sys.path.insert(0, str(_SUBSTRATE_DIR))

import launch_prompt_policy  # noqa: E402
import resolve_model as _resolve_model_module  # noqa: E402
import validate_payload as _validate_payload_module  # noqa: E402
from launch_prompt_policy import CapInfo, PolicyResult  # noqa: E402
from resolve_model import Resolution, ResolutionError  # noqa: E402

__all__ = [
    "CapInfo",
    "PolicyResult",
    "Resolution",
    "ResolutionError",
    "GateError",
    "MalformedCapRecord",
    "PolicyEvaluationStop",
    "CitationResolutionError",
    "RatioDisagreement",
    "GoverningCitation",
    "PolicyGateOutcome",
    "RatioGateOutcome",
    "DispatchMetadata",
    "GOVERNING_POLICY_ID",
    "default_models_path",
    "default_registry_path",
    "load_model_record",
    "translate_cap",
    "evaluate_policy_gate",
    "resolve_governing_citation",
    "check_ratio_authority",
]

# The one governing policy's registry identity (post-Q1 citation
# form). This is a registry policy_id, not one of the Skill 63
# evaluator constants; the evaluator constants are referenced from
# launch_prompt_policy directly and are never aliased here
# (contract section 11.1).
GOVERNING_POLICY_ID = "kie-rule-12-band"


def default_models_path() -> Path:
    return _REPO_ROOT / "63-agnes-image" / "models.json"


def default_registry_path() -> Path:
    return (_REPO_ROOT / "shared-utils" / "signature_launch" / "domain"
            / "prompt-policy-registry.json")


# ---------------------------------------------------------------------------
# Gate exceptions: every stop is named and carries its evidence.
# ---------------------------------------------------------------------------

class GateError(ValueError):
    """Base class for every dispatch-layer gate stop."""


class MalformedCapRecord(GateError):
    """G-05: the selected model's cap record cannot be translated
    into a well-formed CapInfo. Fail closed before spend."""


class PolicyEvaluationStop(GateError):
    """G-03/G-04: the named policy evaluated invalid, or the
    evaluator result's policy_id differs from the named policy,
    or the named policy is not an evaluator this layer can run.
    Carries the PolicyResult when one exists so the caller can
    preserve errors and note in the run record."""

    def __init__(self, message: str, result: Optional[PolicyResult] = None):
        super().__init__(message)
        self.result = result


class CitationResolutionError(GateError):
    """G-03: the governing registry citation cannot be resolved
    by id plus entry hash against the registry of record."""


class RatioDisagreement(GateError):
    """G-06: ratio sources disagree, or the requested ratio is
    unsupported by the validation-time authority. The message
    names the ratio, the selected model, and the sources."""


# ---------------------------------------------------------------------------
# Model record loading (contract section 11.2: select by canonical ID).
# ---------------------------------------------------------------------------

def load_model_record(model_id: str,
                      models_path: Optional[Path] = None) -> dict:
    """Read models.json fresh and return the record whose
    canonical_model_id is model_id. Reading at call time is the
    point: the record is the validation-time authority for the
    cap translation (G-05) and the ratio gate (G-06), never a
    copy cached by this layer."""
    path = Path(models_path) if models_path else default_models_path()
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GateError(f"cannot read model registry {path}: {exc}") from exc
    for entry in entries:
        if isinstance(entry, dict) and entry.get("canonical_model_id") == model_id:
            return entry
    raise GateError(
        f"no models.json record carries canonical_model_id {model_id!r} "
        f"(read from {path})")


# ---------------------------------------------------------------------------
# G-05: cap record translated into CapInfo, fail closed.
# ---------------------------------------------------------------------------

# Registry/display vocabulary (models.json cap_status) to the code
# vocabulary CapInfo.status accepts (contract section 6.3). The
# registry string must never reach the evaluator untranslated: the
# evaluator treats "NOT_PUBLISHED" as an unknown status.
_CAP_STATUS_TRANSLATION = {
    "NOT_PUBLISHED": "not_published",
    "PUBLISHED": "published",
    "OWNER_OBSERVED": "owner_observed",
    # Already-code forms pass through unchanged.
    "not_published": "not_published",
    "published": "published",
    "owner_observed": "owner_observed",
}

# Which models.json field carries the number for each enforced
# status. Status and number are a mandatory pair (contract 6.3).
_CAP_NUMBER_FIELD = {
    "published": "vendor_hard_cap_chars",
    "owner_observed": "owner_observed_cap_chars",
}


def translate_cap(record: dict) -> CapInfo:
    """Translate one model's models.json cap record into CapInfo.

    Current records (cap_status NOT_PUBLISHED, both numbers null)
    yield CapInfo(status="not_published", chars=None): no ceiling
    is invented and length stays telemetry. For an enforced cap
    (published or owner-observed) the status and its number are a
    mandatory pair: a status without its number, a number without
    an enforced status, or an unrecognized status is a malformed
    cap record and fails closed here, before spend, rather than
    falling through to the evaluator's unknown-status branch.
    """
    model_id = record.get("canonical_model_id", "<unknown model>")
    raw_status = record.get("cap_status")
    if raw_status not in _CAP_STATUS_TRANSLATION:
        raise MalformedCapRecord(
            f"malformed cap record for {model_id}: cap_status "
            f"{raw_status!r} is not a recognized cap status; "
            f"fail closed before spend")
    status = _CAP_STATUS_TRANSLATION[raw_status]
    if status == "not_published":
        stray = [f for f in ("vendor_hard_cap_chars",
                             "owner_observed_cap_chars")
                 if record.get(f) is not None]
        if stray:
            raise MalformedCapRecord(
                f"malformed cap record for {model_id}: cap_status "
                f"NOT_PUBLISHED carries cap number(s) in {stray}; "
                f"status and number contradict each other; "
                f"fail closed before spend")
        return CapInfo(status="not_published", chars=None)
    number_field = _CAP_NUMBER_FIELD[status]
    chars = record.get(number_field)
    if chars is None:
        raise MalformedCapRecord(
            f"malformed cap record for {model_id}: cap_status "
            f"{raw_status!r} (code status {status!r}) has no number "
            f"in {number_field}; status and number are a mandatory "
            f"pair for an enforced cap; fail closed before spend")
    if not isinstance(chars, int) or isinstance(chars, bool) or chars <= 0:
        raise MalformedCapRecord(
            f"malformed cap record for {model_id}: {number_field} "
            f"is {chars!r}, not a positive integer character cap; "
            f"fail closed before spend")
    return CapInfo(status=status, chars=chars)


# ---------------------------------------------------------------------------
# G-04 + the evaluated half of G-03: the policy evaluation gate.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PolicyGateOutcome:
    """What the policy gate hands onward: the evaluated result,
    the effective named policy, the exact elements the caller
    supplied (recorded, never inferred), and the cap the
    evaluation ran under."""
    result: PolicyResult
    named_policy: str
    elements_supplied: tuple
    cap: CapInfo

    @property
    def receipt_policy_id(self) -> str:
        """The value the orchestrator passes explicitly to
        build_agnes_receipt(prompt_policy_id=...): the evaluated
        result's own policy_id, never the receipt builder's
        default (G-03, contract section 6.1)."""
        return self.result.policy_id


def evaluate_policy_gate(*, prompt: str,
                         elements_present: Iterable[str],
                         named_policy: Optional[str],
                         cap: CapInfo) -> PolicyGateOutcome:
    """Evaluate the named policy before spend (contract steps 2
    and 5 of section 3; checklist 11.2).

    named_policy is the policy the request names; None means the
    launch default. Launch runs use the launch evaluator unless
    the request explicitly names the legacy band (contract
    section 6.4). The elements_present set is consumed exactly
    as the page/dispatch layer supplied it (G-04): this gate
    records the supplied set verbatim and never inspects the
    prompt prose to infer elements.

    Stops (PolicyEvaluationStop, carrying the PolicyResult):
    the result is invalid (errors and note preserved on the
    result), the result's policy_id differs from the named
    policy, or the named policy is not one of the two Skill 63
    evaluator IDs.
    """
    supplied = tuple(sorted(set(elements_present)))
    effective = named_policy or launch_prompt_policy.LAUNCH_POLICY_ID
    if effective == launch_prompt_policy.LAUNCH_POLICY_ID:
        result = launch_prompt_policy.evaluate_launch_policy(
            prompt, set(supplied), cap)
    elif effective == launch_prompt_policy.LEGACY_POLICY_ID:
        result = launch_prompt_policy.evaluate_legacy_house_band(prompt)
    else:
        raise PolicyEvaluationStop(
            f"named policy {effective!r} is not a Skill 63 evaluator "
            f"this dispatch layer can run; fail closed before spend")
    if result.policy_id != effective:
        raise PolicyEvaluationStop(
            f"policy mismatch: the request named {effective!r} but "
            f"the evaluator result carries {result.policy_id!r}; "
            f"stop before spend", result=result)
    if not result.valid:
        raise PolicyEvaluationStop(
            f"policy {result.policy_id!r} evaluated invalid: "
            f"{result.errors}", result=result)
    return PolicyGateOutcome(result=result, named_policy=effective,
                             elements_supplied=supplied, cap=cap)


# ---------------------------------------------------------------------------
# G-03, citation half: the governing registry citation.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GoverningCitation:
    """The resolved governing citation: the band entry's
    policy_id and its verified entry_hash, plus where it was
    resolved from. This is the citation the Q11 budget decision
    carries (policy_id AND registry_entry_hash)."""
    policy_id: str
    entry_hash: str
    registry_path: str


def _entry_hash(entry: dict) -> str:
    """Q13 entry hash: SHA-256 over the entry serialized as
    canonical JSON (keys sorted, comma and colon separators,
    UTF-8), with the entry_hash field itself excluded. The same
    computation collect_launch_receipts.py performs."""
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def resolve_governing_citation(
        registry_path: Optional[Path] = None,
        policy_id: str = GOVERNING_POLICY_ID) -> GoverningCitation:
    """Resolve the governing band entry against the registry of
    record by id plus entry hash, failing closed when it cannot
    be resolved: registry unreadable, no entry with that id, the
    entry not active, or the stored entry_hash not recomputing
    from the entry's own bytes (a tampered or stale registry)."""
    path = Path(registry_path) if registry_path else default_registry_path()
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CitationResolutionError(
            f"governing citation cannot be resolved: registry of "
            f"record {path} is unreadable ({exc}); fail closed") from exc
    entries = registry.get("entries") if isinstance(registry, dict) else None
    if not isinstance(entries, list):
        raise CitationResolutionError(
            f"governing citation cannot be resolved: {path} carries "
            f"no entries list; fail closed")
    for entry in entries:
        if isinstance(entry, dict) and entry.get("policy_id") == policy_id:
            if entry.get("entry_status") != "active":
                raise CitationResolutionError(
                    f"governing citation cannot be resolved: entry "
                    f"{policy_id!r} in {path} has entry_status "
                    f"{entry.get('entry_status')!r}, not 'active'; "
                    f"only active entries may be resolved by a new "
                    f"run; fail closed")
            stored = entry.get("entry_hash")
            recomputed = _entry_hash(entry)
            if stored != recomputed:
                raise CitationResolutionError(
                    f"governing citation cannot be resolved: entry "
                    f"{policy_id!r} in {path} stores entry_hash "
                    f"{stored!r} but its own bytes recompute to "
                    f"{recomputed!r}; fail closed")
            return GoverningCitation(policy_id=policy_id,
                                     entry_hash=recomputed,
                                     registry_path=str(path))
    raise CitationResolutionError(
        f"governing citation cannot be resolved: no entry with "
        f"policy_id {policy_id!r} exists in the registry of record "
        f"{path}; fail closed")


# ---------------------------------------------------------------------------
# G-06: ratio authority read at validation time, fail closed.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RatioGateOutcome:
    """The validation-time ratio authority for the selected
    model, and the requested ratio checked against it (None when
    the request carries no ratio, which is not a disagreement)."""
    model_id: str
    authority: tuple
    requested_ratio: Optional[str]


def check_ratio_authority(*, model_id: str, record: dict,
                          requested_ratio: Optional[str] = None,
                          registry_snapshot: Optional[Iterable[str]] = None
                          ) -> RatioGateOutcome:
    """Read the selected model's aspect_ratios from its
    models.json record (loaded fresh by load_model_record) as
    the authority, and fail closed BY NAME on any disagreement
    between that field, the adapter validator's RATIOS literal,
    the record's own dimension_table keys (contract section 8.2
    cross-check), and a registry snapshot when one is supplied.

    The failure names the differing ratio(s), the selected
    model, and the disagreeing sources. An unsupported requested
    ratio fails the same way: it is never remapped, swapped,
    inferred, or silently dropped. A request with no ratio is
    not a disagreement (ratio is optional in the validator).
    """
    authority = record.get("aspect_ratios")
    if not isinstance(authority, list) or not authority:
        raise RatioDisagreement(
            f"ratio authority missing for model {model_id}: the "
            f"models.json record carries no aspect_ratios list; "
            f"fail closed before dispatch")
    authority_set = set(authority)
    validator_set = set(_validate_payload_module.RATIOS)
    if authority_set != validator_set:
        only_authority = sorted(authority_set - validator_set)
        only_validator = sorted(validator_set - authority_set)
        raise RatioDisagreement(
            f"ratio disagreement for model {model_id}: "
            f"models.json aspect_ratios and validate_payload.RATIOS "
            f"disagree; only in models.json aspect_ratios: "
            f"{only_authority}; only in validate_payload.RATIOS: "
            f"{only_validator}; fail closed by name before dispatch "
            f"and refer the disagreement to S63")
    dimension_table = record.get("dimension_table")
    if isinstance(dimension_table, dict):
        table_set = set(dimension_table.keys())
        if table_set != authority_set:
            raise RatioDisagreement(
                f"ratio disagreement for model {model_id}: the "
                f"record's dimension_table keys and its "
                f"aspect_ratios disagree; only in dimension_table: "
                f"{sorted(table_set - authority_set)}; only in "
                f"aspect_ratios: {sorted(authority_set - table_set)}; "
                f"fail closed by name before dispatch and refer "
                f"the disagreement to S63")
    if registry_snapshot is not None:
        snapshot_set = set(registry_snapshot)
        if snapshot_set != authority_set:
            raise RatioDisagreement(
                f"ratio disagreement for model {model_id}: the "
                f"registry snapshot and models.json aspect_ratios "
                f"disagree; only in the registry snapshot: "
                f"{sorted(snapshot_set - authority_set)}; only in "
                f"models.json aspect_ratios: "
                f"{sorted(authority_set - snapshot_set)}; fail "
                f"closed by name before dispatch")
    if requested_ratio is not None and requested_ratio not in authority_set:
        raise RatioDisagreement(
            f"unsupported ratio {requested_ratio!r} for model "
            f"{model_id}: the validation-time authority "
            f"(models.json aspect_ratios) carries "
            f"{sorted(authority_set)}; the ratio is not remapped, "
            f"swapped, inferred, or dropped; fail closed by name "
            f"before dispatch")
    return RatioGateOutcome(model_id=model_id,
                            authority=tuple(authority),
                            requested_ratio=requested_ratio)


# ---------------------------------------------------------------------------
# G-11: full Resolution provenance retained in dispatch metadata.
# ---------------------------------------------------------------------------

@dataclass
class DispatchMetadata:
    """S71/S49 dispatch metadata for one run: where the full
    Resolution, the evaluated PolicyResult, the preflight cost
    status, the fingerprint, and this layer's gate outcomes are
    retained (contract section 11.1). Provenance lives here
    only: it is never added to the provider payload and never
    forced into the Agnes receipt, whose schema has no
    provenance field (G-11). The orchestrator fills the fields
    its own steps own (cost_status, fingerprint); the gates fill
    theirs through the attach methods."""
    resolution: Optional[Resolution] = None
    policy_outcome: Optional[PolicyGateOutcome] = None
    citation: Optional[GoverningCitation] = None
    ratio_outcome: Optional[RatioGateOutcome] = None
    cost_status: Optional[str] = None
    fingerprint: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def retain_resolution(self, resolution: Resolution) -> "DispatchMetadata":
        self.resolution = resolution
        return self

    def attach_policy(self, outcome: PolicyGateOutcome) -> "DispatchMetadata":
        self.policy_outcome = outcome
        return self

    def attach_citation(self, citation: GoverningCitation) -> "DispatchMetadata":
        self.citation = citation
        return self

    def attach_ratio(self, outcome: RatioGateOutcome) -> "DispatchMetadata":
        self.ratio_outcome = outcome
        return self

    def to_record(self) -> dict:
        """A JSON-safe run-record view of the retained metadata,
        including the full Resolution provenance (G-11) and the
        governing citation (G-03)."""
        record: dict = {}
        if self.resolution is not None:
            record["resolution"] = {
                "model_id": self.resolution.model_id,
                "role": self.resolution.role,
                "provenance": self.resolution.provenance,
                "requested": self.resolution.requested,
            }
        if self.policy_outcome is not None:
            result = self.policy_outcome.result
            record["policy"] = {
                "named_policy": self.policy_outcome.named_policy,
                "policy_id": result.policy_id,
                "valid": result.valid,
                "char_count": result.char_count,
                "missing_elements": list(result.missing_elements),
                "errors": list(result.errors),
                "note": result.note,
                "elements_supplied": list(self.policy_outcome.elements_supplied),
                "cap": {"status": self.policy_outcome.cap.status,
                        "chars": self.policy_outcome.cap.chars},
            }
        if self.citation is not None:
            record["governing_citation"] = {
                "policy_id": self.citation.policy_id,
                "entry_hash": self.citation.entry_hash,
                "registry_path": self.citation.registry_path,
            }
        if self.ratio_outcome is not None:
            record["ratio_authority"] = {
                "model_id": self.ratio_outcome.model_id,
                "aspect_ratios": list(self.ratio_outcome.authority),
                "requested_ratio": self.ratio_outcome.requested_ratio,
            }
        if self.cost_status is not None:
            record["cost_status"] = self.cost_status
        if self.fingerprint is not None:
            record["fingerprint"] = self.fingerprint
        if self.extra:
            record["extra"] = dict(self.extra)
        return record


def _self_check() -> int:
    """Deterministic smoke check of the gates against the real
    substrate and the registry of record. The full evidence suite
    is test_agnes_gates.py; this is the module's own quick proof
    that the wiring resolves."""
    record = load_model_record("agnes-image-2.5-flash")
    cap = translate_cap(record)
    assert cap == CapInfo(status="not_published", chars=None), cap
    citation = resolve_governing_citation()
    assert citation.policy_id == GOVERNING_POLICY_ID, citation
    outcome = check_ratio_authority(
        model_id="agnes-image-2.5-flash", record=record,
        requested_ratio="16:9")
    assert "16:9" in outcome.authority
    print("agnes_gates.py --self-check: PASS "
          f"(cap {cap.status}/{cap.chars}, citation "
          f"{citation.policy_id} entry_hash {citation.entry_hash[:16]}..., "
          f"ratios {len(outcome.authority)})")
    return 0


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        try:
            sys.exit(_self_check())
        except GateError as exc:
            print(f"agnes_gates.py --self-check: FAIL ({exc})",
                  file=sys.stderr)
            sys.exit(2)
    print("agnes_gates.py: import this module from the dispatch layer, "
          "or run with --self-check.")

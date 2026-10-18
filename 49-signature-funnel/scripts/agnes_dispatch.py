#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agnes_dispatch.py -- the assembled A24 Leg 4 dispatch layer: the
composition root that wires the three Leg 4 build lanes into one
dispatch path for the Skill 63 Agnes image adapter (S71/S49 dispatch
layer).

The three lanes were built in parallel against hand-off contracts;
this module is where they meet, and it is the only place they meet:

- agnes_orchestrator.py (lane A, G-01/G-02/G-08/G-09/G-10/G-12):
  the contract section 3 sequence through the transport outcome.
  Its GateHooks are injected behaviour; this module supplies them.
- agnes_gates.py (lane B, G-03/G-04/G-05/G-06/G-11): the per-request
  gates. `make_gate_hooks()` adapts them to the orchestrator's
  GateHooks surface (see "Gate adapter" below).
- agnes_response.py (lane C, G-07/G-13/G-14/G-15): the outcome and
  response layer. `run_dispatch()` hands it every SendResult body
  and consults it on every AmbiguousOutcome (see "Outcome wiring").

Gate adapter (wiring items 1 and 5 of the assembly):

- evaluate_policy(ctx): retains the full Resolution in the run's
  DispatchMetadata (G-11), loads the selected model's models.json
  record fresh and translates its cap record (G-05), then calls
  evaluate_policy_gate() with the caller-supplied truthful
  elements_present set captured at composition time (G-04; the set
  is the page/dispatch layer's input, supplied by whoever calls
  run_dispatch, exactly as the contract requires). On success it
  attaches the PolicyGateOutcome to the metadata, resolves the
  governing registry citation (G-03 citation half) and attaches it
  too, then returns the evaluated PolicyResult the orchestrator's
  hook contract requires. When the gates stop with a
  PolicyEvaluationStop carrying its PolicyResult (an invalid
  evaluation, or a named/result mismatch), the adapter returns
  that result and the orchestrator stops on it itself with
  PolicyRefused, so both layers' stop semantics hold and the
  errors and note stay preserved on the carried result; a stop
  carrying no result (a named policy this layer cannot run)
  propagates unchanged. A citation that cannot be resolved raises
  CitationResolutionError here, before payload, fingerprint,
  preflight, or spend: the citation gate fails closed.
- check_ratios(ctx): loads the model record fresh (the
  validation-time authority, G-06) and calls
  check_ratio_authority() for the selected model and the request's
  ratio. A RatioDisagreement is returned to the orchestrator as
  its one-item error list, which the orchestrator raises as
  PayloadRefused before fingerprint, preflight, and spend; a
  clean outcome is attached to the metadata and an empty list is
  returned. Without this wiring G-06 would rest only on the
  adapter payload gate's own ratio literal; with it, the
  authority is models.json read at validation time.

Outcome wiring (wiring items 2 and 3):

- On a SendResult, run_dispatch() calls
  agnes_response.process_success_body() with the raw body, the
  resolved requested model, the prompt, the output path, the run
  directory, and the dispatch fingerprint, so the completed result
  lands in the run's result store (G-13). The policy citation
  passed is the gates' PolicyGateOutcome.receipt_policy_id (the
  evaluated PolicyResult.policy_id exposed by the gate for
  exactly this passage, G-03), never the receipt builder's
  default; the response layer requires it and passes it verbatim
  to build_agnes_receipt(), then runs validate_receipt().
- On AmbiguousOutcome, run_dispatch() consults
  agnes_response.resolve_ambiguous_outcome() with the exception's
  request fingerprint and returns its verdict in the composed
  result: a stored completed result is the dispatch outcome, or
  the duplicate-cost disclosure stands with resubmission a
  separate bounded decision. Nothing resubmits automatically.
  Every other transport outcome (AuthStopped, RateLimited,
  TransportError, CredentialsMissing, BudgetBlocked) propagates
  to the caller unchanged, with the orchestrator's attempt audit
  and run record attached, for the caller's section 11.3 routing.

G-15 placement (wiring item 4): the reference URLs a request
carries ride in extra_body.image and enter the provider payload
verbatim at payload build (contract step 3). The composed entry
point checks them with agnes_response.check_reference_url()
before dispatch() begins, so a non-public-HTTPS reference URL
fails closed by name before resolution, policy, payload
validation, or spend, and the adapter validator's syntactic
http-or-https acceptance is never relied on for a reference URL.
Entries in Data-URI form (data:image/...;base64,...) are not URLs
and are outside this check; the adapter payload gate's own data
format validation governs them. This placement is the assembly's
recorded reading of the contract's "apply the G-15 check at the
payload stage" (B-38 step 7), under lane C's strict reading that
A24 requires public HTTPS for reference URLs (Gap G-G, flagged
for SWARM at the Leg 4 check).

One run record (wiring item 5): run_dispatch() passes ONE dict as
the run record to dispatch(), to process_success_body(), and to
resolve_ambiguous_outcome(). The orchestrator writes its keys
(resolution, policy fields, payload_warnings, fingerprint,
cost_status, attempts, terminal) into it; the response layer
appends its structured events under "response_events"; and the
composition adds "dispatch_metadata" holding the gates'
DispatchMetadata.to_record() view (full Resolution with
provenance, the policy outcome with the supplied elements and the
cap, the governing citation, the ratio authority, and the cost
status and fingerprint the orchestrator threaded). Field mapping
between the two shapes: the orchestrator's record["resolution"]
and the metadata's record["resolution"] carry the same four
fields (model_id, role, provenance, requested) serialized from
the same Resolution object, which the metadata retains by
reference; record["policy_id"]/["policy_valid"] are the
orchestrator's summary of the same PolicyResult the metadata
retains in full under "policy"; record["fingerprint"] and
record["cost_status"] equal the metadata's slots, which the
composition fills from the DispatchOutcome (or, on the ambiguous
path, from the exception's fingerprint and the record's threaded
cost status). No field either layer produces is dropped.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import agnes_gates as gates  # noqa: E402
import agnes_orchestrator as orch  # noqa: E402
import agnes_response as resp  # noqa: E402
import transport  # noqa: E402  (substrate; agnes_orchestrator put it on sys.path)

__all__ = [
    "ComposedDispatchResult",
    "make_gate_hooks",
    "check_request_reference_urls",
    "run_dispatch",
]


# ---------------------------------------------------------------------------
# Wiring item 1 (and the metadata half of item 5): the gate hooks.
# ---------------------------------------------------------------------------

def make_gate_hooks(*, elements_present, metadata: gates.DispatchMetadata,
                    models_path=None, registry_path=None) -> orch.GateHooks:
    """Build the orchestrator's GateHooks from agnes_gates.

    elements_present is the caller-supplied truthful element set
    (G-04): captured here, consumed verbatim by the policy gate,
    never inferred from the prompt. metadata is the run's
    DispatchMetadata (G-11); the hooks retain the Resolution, the
    policy outcome, the governing citation, and the ratio outcome
    into it as the run proceeds.
    """
    supplied_elements = tuple(elements_present)

    def evaluate_policy(ctx: orch.GateContext) -> orch.PolicyResult:
        metadata.retain_resolution(ctx.resolution)
        record = gates.load_model_record(ctx.resolution.model_id,
                                         models_path)
        cap = gates.translate_cap(record)
        try:
            outcome = gates.evaluate_policy_gate(
                prompt=ctx.request.prompt,
                elements_present=supplied_elements,
                named_policy=ctx.request.named_policy_id,
                cap=cap,
            )
        except gates.PolicyEvaluationStop as exc:
            if exc.result is not None:
                # The orchestrator stops on the returned result
                # itself (invalid, or named/result mismatch) with
                # PolicyRefused; the errors and note ride the
                # carried result. Nothing proceeds toward spend.
                return exc.result
            raise
        metadata.attach_policy(outcome)
        citation = gates.resolve_governing_citation(registry_path)
        metadata.attach_citation(citation)
        return outcome.result

    def check_ratios(ctx: orch.GateContext) -> list:
        record = gates.load_model_record(ctx.resolution.model_id,
                                         models_path)
        try:
            outcome = gates.check_ratio_authority(
                model_id=ctx.resolution.model_id,
                record=record,
                requested_ratio=ctx.request.ratio,
            )
        except gates.RatioDisagreement as exc:
            return [str(exc)]
        metadata.attach_ratio(outcome)
        return []

    return orch.GateHooks(evaluate_policy=evaluate_policy,
                          check_ratios=check_ratios)


# ---------------------------------------------------------------------------
# Wiring item 4: the G-15 reference-URL check (placement documented
# in the module docstring).
# ---------------------------------------------------------------------------

def check_request_reference_urls(request: orch.DispatchRequest) -> list:
    """Apply the dispatch layer's public-HTTPS check (G-15) to the
    reference URLs the request carries in extra_body.image, the
    field whose entries enter the provider payload verbatim.
    Data-URI entries are not URLs and pass through to the adapter
    payload gate's own data format validation. Raises
    agnes_response.ReferenceUrlError naming the failure."""
    extra = request.extra_body or {}
    images = extra.get("image") or []
    checked = []
    for entry in images:
        if isinstance(entry, str) and entry.startswith("data:"):
            checked.append(entry)
            continue
        checked.append(resp.check_reference_url(entry))
    return checked


# ---------------------------------------------------------------------------
# Wiring items 2, 3, and 5: the composed dispatch.
# ---------------------------------------------------------------------------

@dataclass
class ComposedDispatchResult:
    """The composed layer's result for one run.

    Exactly one of response / ambiguous is set: response when the
    dispatch reached a persisted, receipted result; ambiguous when
    transport raised AmbiguousOutcome and the G-13 check answered
    (outcome is None there: transport produced no SendResult).
    metadata and run_record are the one agreed run record pair
    (wiring item 5).
    """

    outcome: Optional[orch.DispatchOutcome]
    response: Optional[dict]
    ambiguous: Optional[dict]
    metadata: gates.DispatchMetadata
    run_record: dict


def _finish_metadata(metadata: gates.DispatchMetadata,
                     record: dict,
                     outcome: Optional[orch.DispatchOutcome]) -> None:
    """Fill the metadata's orchestrator-owned slots and render the
    metadata view into the one run record (wiring item 5)."""
    if outcome is not None:
        metadata.cost_status = outcome.cost_status
        metadata.fingerprint = outcome.fingerprint
    else:
        if metadata.fingerprint is None:
            metadata.fingerprint = record.get("fingerprint")
        if metadata.cost_status is None:
            metadata.cost_status = record.get("cost_status")
    record["dispatch_metadata"] = metadata.to_record()


def run_dispatch(request: orch.DispatchRequest, *,
                 elements_present,
                 output_path,
                 run_dir,
                 sender=None,
                 env: Optional[dict] = None,
                 sleeper=None,
                 fetcher=None,
                 models_path=None,
                 registry_path=None,
                 run_record: Optional[dict] = None
                 ) -> ComposedDispatchResult:
    """Run one full dispatch through the assembled layer.

    elements_present is the page/dispatch layer's truthful element
    set for this prompt (G-04), supplied by the caller. output_path
    is where the persisted image lands; run_dir holds the run's
    result store (G-13). sender, env, and sleeper pass to the
    orchestrator: tests inject a fake sender, an environment dict,
    and a recording sleeper; production builds the concrete HTTP
    sender, reads the real environment, and sleeps for real.
    fetcher passes to the response layer for URL-form images.

    Returns a ComposedDispatchResult. Transport outcomes other
    than AmbiguousOutcome propagate unchanged (see the module
    docstring); gate stops (PolicyRefused, PayloadRefused, and the
    gates' named GateError subclasses) likewise propagate before
    spend.
    """
    record = run_record if run_record is not None else {}
    metadata = gates.DispatchMetadata()
    hooks = make_gate_hooks(elements_present=elements_present,
                            metadata=metadata,
                            models_path=models_path,
                            registry_path=registry_path)
    # G-15, at the payload stage: the reference URLs enter the
    # payload verbatim from extra_body.image, so they are checked
    # before dispatch begins and the adapter's syntactic URL
    # acceptance is never relied on for them.
    check_request_reference_urls(request)
    try:
        outcome = orch.dispatch(request, hooks=hooks, sender=sender,
                                env=env, sleeper=sleeper,
                                run_record=record)
    except transport.AmbiguousOutcome as exc:
        resolution = resp.resolve_ambiguous_outcome(
            run_dir, exc.request_fingerprint, run_record=record)
        _finish_metadata(metadata, record, None)
        return ComposedDispatchResult(
            outcome=None, response=None, ambiguous=resolution,
            metadata=metadata, run_record=record)
    _finish_metadata(metadata, record, outcome)
    receipt_policy_id = (
        metadata.policy_outcome.receipt_policy_id
        if metadata.policy_outcome is not None
        else outcome.policy_result.policy_id)
    response = resp.process_success_body(
        outcome.send_result.body,
        requested_model_id=outcome.resolution.model_id,
        prompt=request.prompt,
        prompt_policy_id=receipt_policy_id,
        output_path=output_path,
        run_dir=run_dir,
        fingerprint=outcome.fingerprint,
        fetcher=fetcher,
        run_record=record,
    )
    return ComposedDispatchResult(
        outcome=outcome, response=response, ambiguous=None,
        metadata=metadata, run_record=record)

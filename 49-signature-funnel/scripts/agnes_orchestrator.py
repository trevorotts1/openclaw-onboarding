#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agnes_orchestrator.py: the A24 Leg 4 dispatch-layer orchestrator core
for the Skill 63 Agnes image adapter (S71/S49 dispatch layer).

The merged Skill 63 modules (PR #2157, `63-agnes-image/scripts/`) are
composable, not turnkey: they supply model resolution, prompt-policy
evaluation, payload validation, transport policy, and receipt
construction as separate modules, and no end-to-end dispatch function.
This module is the orchestrator the dispatch contract
(rooms/S63/work/a24-support/S71-S49-A24-DISPATCH-CONTRACT.md) requires
the caller to build. It performs the contract section 3 sequence in
order and owns the core items G-01, G-02, G-08, G-09, G-10, and G-12:

- G-01: the orchestrator itself, plus a concrete HTTP sender meeting
  the section 5.2 sender contract (see `make_http_sender`).
- G-02: `preflight()` is always called before `send_with_policy()`,
  and its exact returned cost status is threaded into the send. The
  send function's "verified" default is never relied on: control flow
  reaches the send only after preflight returns, so the sender is
  provably not invoked when preflight raises.
- G-08: a sender-level attempt recorder wraps the sender and keeps a
  credential-free audit record of every invocation, including the
  failed attempts transport's failure exceptions do not carry.
- G-09: production injects a real sleeper (`time.sleep`). This module
  always passes an explicit sleeper to `send_with_policy()`; the
  transport no-op default is never used through this layer.
- G-10: the stable request fingerprint is defined and documented
  below (see `request_fingerprint`).
- G-12: the dispatch-layer exception policy for non-timeout sender
  exceptions is defined below (see "Exception policy").

Sibling Leg 4 modules, built in parallel and wired in at assembly,
own the remaining items: agnes_gates.py owns G-03 (policy citation
threading), G-04 (truthful elements_present), G-05 (cap translation),
G-06 (ratio authority), and G-11 (Resolution provenance retention);
agnes_response.py owns G-07 (provider-actual model confirmation),
G-13 (existing-result check), G-14 (response parse/persist/measure,
then receipt), and G-15 (dispatch-layer URL policy). This module
exposes the hand-off points they consume: the `Resolution`, the
evaluated `PolicyResult`, the request fingerprint, the threaded
`cost_status`, the exact payload sent, the payload warnings, the
attempt audit, and the returned `SendResult` (whose raw body is lane
C's input; transport success alone is not a receipt).

Gate hooks: policy evaluation and the ratio-authority check belong
to the gates lane, so `dispatch()` takes them as injected callables
(`GateHooks`). This module enforces the sequence around them: it
stops before spend when the evaluated policy is invalid, and it
stops when the request envelope names a policy whose ID differs from
the evaluated `PolicyResult.policy_id` (the stop rule of contract
section 6.1 and checklist 11.2; the citation form itself is G-03,
owned by the gates lane, under the post-Q1 citation reading: the one
governing policy is cited, never selected among policies).

Fingerprint algorithm (G-10; dispatch-contract section 10.3 item 1
leaves the choice to this layer; this is the definition of record):
the fingerprint is the lowercase hex SHA-256 of the canonical JSON
serialization of the exact provider payload dict that is passed to
`send_with_policy()` and to the sender. Canonical JSON means
`json.dumps(payload, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)` encoded as UTF-8: keys sorted recursively, no
insignificant whitespace, non-ASCII carried as UTF-8. The payload
contains only JSON-native values by construction. The fingerprint
excludes the credential (which is never in the payload), headers,
the endpoint, budget/cost data, and dispatch metadata. The same
payload therefore yields the same fingerprint in every process and
every run: no salt, no process-dependent hashing. The same value is
passed to `preflight()`, to `send_with_policy()`, retained in the
run record, and used for any ambiguity investigation (G-13, lane C).

Attempt-retention format (G-08; contract section 10.3 item 6 leaves
the format to this layer; this is the definition of record): the
attempt audit is a list of JSON-serializable dicts, one per sender
invocation, in invocation order:

    {"attempt": <1-based int within this dispatch call>,
     "fingerprint": <the dispatch fingerprint>,
     "outcome": "http_<status>" | "timeout" | "exception",
     "exception_kind": None | "construction" | "network"
                       | "parsing" | "persistence" | "unclassified",
     "exception_type": None | <exception class name>,
     "detail": <short scrubbed message, may be "">}

No record ever contains the credential value, an Authorization
header, or the request body; the fingerprint identifies the request.
The audit lives on the returned `DispatchOutcome` on success and is
attached to any exception `dispatch()` re-raises (attributes
`attempt_audit` and `dispatch_run_record`), because transport's
failure exceptions carry no attempts list. Callers may serialize the
audit into their own run-record file verbatim.

Exception policy (G-12): transport defines behaviour only for
`TimeoutError` from a sender (converted to `AmbiguousOutcome`). For
every other sender exception this layer's policy is: fail closed,
attempt no retry at this layer, infer neither provider success nor
provider failure nor retry safety, and name the failure in the run
record by kind. The concrete HTTP sender raises only members of the
`SenderError` taxonomy below (`SenderConstructionError` for
construction failures such as an unusable endpoint, `SenderNetworkError`
for network failures); a foreign sender's exception that is neither a
`TimeoutError` nor a `SenderError` is wrapped in `SenderNetworkError`
(kind "network") with the original chained, after being recorded with
kind "unclassified". A `SenderError` propagates unchanged. Parsing
and persistence failures arise in the response layer (lane C); the
taxonomy kinds "parsing" and "persistence" are reserved here so lane
C raises under the same policy and the same record format.

Credentials: the sender reads the `AGNES_AI_API_KEY` value (or the
verified approved alias named by `key_env`) from the environment at
call time and injects it as an Authorization header on the HTTP
request object only. The value never appears in the provider payload
dict, the fingerprint, the attempt audit, the run record, a receipt,
or an error raised by this module. Presence is all preflight checks;
this module never logs the value.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# Mirror the import pattern landed Skill 63 consumers use (see
# 63-agnes-image/tests/test_transport.py): put the adapter's scripts
# directory on sys.path and import the modules by their bare names.
_AGNES_SCRIPTS = Path(__file__).resolve().parents[2] / "63-agnes-image" / "scripts"
if str(_AGNES_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_AGNES_SCRIPTS))

import launch_prompt_policy as policy_mod  # noqa: E402
import resolve_model as resolver  # noqa: E402
import transport  # noqa: E402
import validate_payload  # noqa: E402

PolicyResult = policy_mod.PolicyResult
Resolution = resolver.Resolution

#: The production sleeper (G-09). Tests inject a recording fake.
PRODUCTION_SLEEPER = time.sleep

#: Default per-attempt HTTP timeout for the concrete sender. Generation
#: calls are slow; the value is a caller-tunable default, not a policy.
DEFAULT_HTTP_TIMEOUT_SECONDS = 180.0


# ---------------------------------------------------------------------------
# Dispatch-layer exceptions
# ---------------------------------------------------------------------------

class DispatchError(RuntimeError):
    """Base for refusals raised by this dispatch layer itself."""


class PolicyRefused(DispatchError):
    """The evaluated prompt policy is invalid, or the request envelope
    names a policy that differs from the evaluated result. Raised
    before fingerprint, preflight, and spend."""

    def __init__(self, message: str, policy_result: Optional[PolicyResult] = None):
        super().__init__(message)
        self.policy_result = policy_result


class PayloadRefused(DispatchError):
    """The built payload failed the adapter payload gate
    (`validate_payload_data`) or the gates lane's ratio check. Raised
    before fingerprint, preflight, and spend."""

    def __init__(self, message: str, errors: list):
        super().__init__(message)
        self.errors = list(errors)


class SenderError(DispatchError):
    """Base for sender exceptions outside transport's taxonomy (G-12).

    `kind` is one of "construction", "network", "parsing",
    "persistence" and is what the run record names."""

    kind = "unclassified"

    def __init__(self, message: str, *, kind: Optional[str] = None):
        super().__init__(message)
        if kind is not None:
            self.kind = kind


class SenderConstructionError(SenderError):
    """The sender could not be constructed or configured (for example
    an unusable endpoint). No provider request was made."""

    kind = "construction"


class SenderNetworkError(SenderError):
    """A network-level failure outside transport's timeout handling
    (connection, TLS, read failures, or a wrapped foreign exception).
    Never evidence that a retry is safe."""

    kind = "network"


# ---------------------------------------------------------------------------
# Request envelope and hand-off types
# ---------------------------------------------------------------------------

@dataclass
class DispatchRequest:
    """The dispatch layer's request envelope.

    The S49 envelope field names are not fixed by the merged Skill 63
    sources (contract section 10.3 item 4); these names are this
    layer's choice and are the hand-off surface for the sibling lanes.
    """

    prompt: str
    size: str
    model_request: Optional[str] = None
    stored: bool = False
    stored_provenance: Optional[str] = None
    ratio: Optional[str] = None
    extra_body: Optional[dict] = None
    return_base64: Optional[bool] = None
    tags: Optional[list] = None
    named_policy_id: Optional[str] = None
    budget: Optional[transport.Budget] = None
    estimated_cost_usd: Optional[float] = None
    key_env: str = transport.DEFAULT_KEY_ENV


@dataclass
class GateContext:
    """What the gates lane's hooks receive. `payload` is None during
    policy evaluation (contract step 2) and set before the ratio
    check (validation time)."""

    request: DispatchRequest
    resolution: Resolution
    payload: Optional[dict] = None


@dataclass
class GateHooks:
    """Injected gates-lane behaviour (agnes_gates.py at assembly).

    evaluate_policy(ctx) -> PolicyResult: evaluate the policy the
    request names (post-Q1 citation form: the one governing policy)
    and return the evaluated result.
    check_ratios(ctx) -> list of error strings: the G-06 ratio
    authority check; an empty list means no disagreement. Optional;
    when None, no ratio-authority check runs at this layer and the
    adapter payload gate's own ratio literal is the only ratio check
    (the assembly wiring supplies the hook; see the build record).
    """

    evaluate_policy: Callable[[GateContext], PolicyResult]
    check_ratios: Optional[Callable[[GateContext], list]] = None


@dataclass
class DispatchOutcome:
    """The successful hand-off bundle for the response lane (lane C)
    and for the caller's run record."""

    resolution: Resolution
    policy_result: PolicyResult
    payload: dict
    payload_warnings: list
    fingerprint: str
    cost_status: str
    send_result: transport.SendResult
    attempt_audit: list
    run_record: dict


# ---------------------------------------------------------------------------
# G-10: the stable request fingerprint
# ---------------------------------------------------------------------------

def canonical_request_bytes(payload: dict) -> bytes:
    """The canonical serialization the fingerprint and the concrete
    sender's request body both use (see the module docstring)."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def request_fingerprint(payload: dict) -> str:
    """G-10: SHA-256 hex of the canonical serialization of the exact
    dispatch payload. Defined and documented in the module docstring;
    stable across processes and runs for the same payload."""
    return hashlib.sha256(canonical_request_bytes(payload)).hexdigest()


# ---------------------------------------------------------------------------
# G-08: sender-level attempt recording
# ---------------------------------------------------------------------------

class AttemptRecorder:
    """Wraps a sender and records every invocation in the G-08 audit
    format (module docstring), then applies the G-12 exception policy
    to non-timeout exceptions. `TimeoutError` is re-raised untouched
    so transport converts it to `AmbiguousOutcome`."""

    def __init__(self, sender, fingerprint: str, audit: Optional[list] = None):
        self._sender = sender
        self._fingerprint = fingerprint
        # The audit list is written in place, so a caller-supplied sink
        # holds every record even when the send raises (G-08).
        self.audit: list = audit if audit is not None else []

    def __call__(self, request: dict):
        number = len(self.audit) + 1
        record = {
            "attempt": number,
            "fingerprint": self._fingerprint,
            "outcome": None,
            "exception_kind": None,
            "exception_type": None,
            "detail": "",
        }
        try:
            status, body = self._sender(request)
        except TimeoutError:
            record["outcome"] = "timeout"
            record["exception_type"] = "TimeoutError"
            self.audit.append(record)
            raise
        except SenderError as exc:
            record["outcome"] = "exception"
            record["exception_kind"] = exc.kind
            record["exception_type"] = type(exc).__name__
            record["detail"] = str(exc)[:200]
            self.audit.append(record)
            raise
        except Exception as exc:  # G-12: fail closed, wrap, no inference.
            record["outcome"] = "exception"
            record["exception_kind"] = "unclassified"
            record["exception_type"] = type(exc).__name__
            record["detail"] = str(exc)[:200]
            self.audit.append(record)
            raise SenderNetworkError(
                f"sender raised {type(exc).__name__} outside the transport "
                "taxonomy; dispatch fails closed and infers neither provider "
                "success nor retry safety from it"
            ) from exc
        record["outcome"] = f"http_{status}"
        self.audit.append(record)
        return status, body


# ---------------------------------------------------------------------------
# G-01: the concrete HTTP sender
# ---------------------------------------------------------------------------

def make_http_sender(*, env: Optional[dict] = None,
                     key_env: str = transport.DEFAULT_KEY_ENV,
                     endpoint: str = transport.ENDPOINT,
                     timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
                     opener=None):
    """Build the concrete sender meeting the contract section 5.2
    sender contract:

    - one invocation performs exactly one HTTP attempt and returns
      (status, raw body bytes); HTTP error statuses are returned, not
      raised, so transport's retry matrix sees them;
    - raises TimeoutError on a transport timeout;
    - owns the endpoint, method, serialization, headers, and
      credential injection: the credential is read from the
      environment at call time and set as an Authorization header on
      the HTTP request object only; it is never placed in the request
      dict, never logged, and never embedded in an error;
    - never mutates the request dict: the body is serialized from a
      canonical copy, so transport's retries reuse identical bytes.

    `opener` is injectable for offline tests; production uses
    urllib.request.urlopen. No code path in the test suite calls the
    real opener.
    """
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise SenderConstructionError(
            f"sender endpoint must be an https URL, got {endpoint!r}"
        )
    open_fn = opener if opener is not None else urllib.request.urlopen

    def sender(request: dict):
        source = os.environ if env is None else env
        value = source.get(key_env)
        if not value or not str(value).strip():
            # Preflight normally raises this first; fail closed in the
            # same taxonomy if a sender is ever invoked directly.
            raise transport.CredentialsMissing(
                f"credential '{key_env}' is not present in the environment; "
                "stopping before any request (presence checked only, "
                "value never read out)"
            )
        body = canonical_request_bytes(request)
        http_request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {value}",
            },
        )
        try:
            with open_fn(http_request, timeout=timeout_seconds) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            # An HTTP response was received; transport owns the policy
            # for its status. Return it like any other response.
            return exc.code, exc.read()
        except TimeoutError:
            raise
        except socket.timeout as exc:
            raise TimeoutError(str(exc) or "provider request timed out") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, (TimeoutError, socket.timeout)) or \
                    "timed out" in str(reason).lower():
                raise TimeoutError(str(reason)) from exc
            raise SenderNetworkError(
                f"network failure before a provider response: {reason}"
            ) from exc
        except OSError as exc:
            raise SenderNetworkError(
                f"network failure before a provider response: {exc}"
            ) from exc

    return sender


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------

def build_payload(request: DispatchRequest, resolution: Resolution) -> dict:
    """Contract step 3: build the provider payload from the resolver's
    canonical model_id only, never the caller's original string."""
    payload: dict = {
        "model": resolution.model_id,
        "prompt": request.prompt,
        "size": request.size,
    }
    if request.ratio is not None:
        payload["ratio"] = request.ratio
    if request.extra_body is not None:
        payload["extra_body"] = request.extra_body
    if request.return_base64 is not None:
        payload["return_base64"] = request.return_base64
    if request.tags is not None:
        payload["tags"] = request.tags
    return payload


def dispatch(request: DispatchRequest, *, hooks: GateHooks,
             sender=None, env: Optional[dict] = None,
             sleeper=None,
             run_record: Optional[dict] = None) -> DispatchOutcome:
    """Run one Agnes dispatch through the contract section 3 sequence
    up to the transport outcome, in order:

    1. resolve the model (live or stored-config resolution);
    2. evaluate the named prompt policy through the gates hook and
       stop before spend if it is invalid or names a different policy
       than the request envelope;
    3. build the payload from the canonical model_id;
    4. validate the payload with the adapter gate and the gates
       lane's ratio-authority hook; stop on any error;
    5. compute the stable fingerprint (G-10);
    6. run preflight() and capture its exact cost status (G-02);
    7. send through send_with_policy() with the recording-wrapped
       concrete sender, the same fingerprint, the threaded cost
       status, and an explicit sleeper (G-01, G-08, G-09).

    Response handling after a SendResult (parse, persist, measure,
    receipt) is lane C's, consuming the returned DispatchOutcome.
    On AmbiguousOutcome the exception carries the fingerprint per
    transport, plus this layer's attempt audit and run record; the
    existing-result check before any resubmission decision is G-13
    (lane C). Nothing here resubmits automatically.

    `sleeper=None` selects the production sleeper (time.sleep);
    tests inject a recording fake. `sender=None` builds the concrete
    HTTP sender; tests inject a fake sender and never touch the
    network.
    """
    record = run_record if run_record is not None else {}
    record.setdefault("attempts", [])
    audit_sink: list = record["attempts"]
    try:
        # Step 1: resolve. ResolutionError propagates by design
        # (checklist 11.2: reject; never fall back to the default).
        if request.stored:
            resolution = resolver.resolve_stored_config(
                request.model_request, request.stored_provenance)
        else:
            resolution = resolver.resolve_model(request.model_request)
        record["resolution"] = {
            "model_id": resolution.model_id,
            "role": resolution.role,
            "provenance": resolution.provenance,
            "requested": resolution.requested,
        }

        # Step 2: evaluate the named policy before spend.
        ctx = GateContext(request=request, resolution=resolution)
        policy_result = hooks.evaluate_policy(ctx)
        record["policy_id"] = policy_result.policy_id
        record["policy_valid"] = policy_result.valid
        if not policy_result.valid:
            record["policy_errors"] = list(policy_result.errors)
            record["policy_note"] = policy_result.note
            raise PolicyRefused(
                "prompt policy evaluation failed before spend: "
                + "; ".join(policy_result.errors),
                policy_result,
            )
        if request.named_policy_id is not None and \
                request.named_policy_id != policy_result.policy_id:
            raise PolicyRefused(
                f"request names policy {request.named_policy_id!r} but the "
                f"evaluator returned {policy_result.policy_id!r}; stopping "
                "on the mismatch (contract section 6.1)",
                policy_result,
            )

        # Steps 3 and 4: build and validate the payload.
        payload = build_payload(request, resolution)
        ctx.payload = payload
        is_valid, _exit_code, errors, warnings = \
            validate_payload.validate_payload_data(payload)
        if not is_valid:
            raise PayloadRefused(
                "payload failed the adapter payload gate", errors)
        if hooks.check_ratios is not None:
            ratio_errors = hooks.check_ratios(ctx)
            if ratio_errors:
                raise PayloadRefused(
                    "ratio authority check failed closed by name",
                    ratio_errors)
        record["payload_warnings"] = list(warnings)

        # Step 5: fingerprint (G-10).
        fingerprint = request_fingerprint(payload)
        record["fingerprint"] = fingerprint

        # Step 6: preflight first (G-02). If this raises, the sender
        # below is never constructed into a call: control flow is the
        # proof, and the section 11.5 tests assert sender count 0.
        cost_status = transport.preflight(
            fingerprint,
            env=env,
            key_env=request.key_env,
            budget=request.budget,
            estimated_cost_usd=request.estimated_cost_usd,
        )
        record["cost_status"] = cost_status

        # Step 7: send, with the audit wrapper (G-08), the threaded
        # cost status (never the default), and an explicit sleeper
        # (G-09: production time.sleep unless a fake is injected).
        raw_sender = sender if sender is not None else make_http_sender(
            env=env, key_env=request.key_env)
        recorder = AttemptRecorder(raw_sender, fingerprint, audit=audit_sink)
        result = transport.send_with_policy(
            recorder,
            payload,
            request_fingerprint=fingerprint,
            cost_status=cost_status,
            sleeper=PRODUCTION_SLEEPER if sleeper is None else sleeper,
        )
        record["terminal"] = "send_result"
        return DispatchOutcome(
            resolution=resolution,
            policy_result=policy_result,
            payload=payload,
            payload_warnings=list(warnings),
            fingerprint=fingerprint,
            cost_status=cost_status,
            send_result=result,
            attempt_audit=list(recorder.audit),
            run_record=record,
        )
    except BaseException as exc:
        record.setdefault("terminal", type(exc).__name__)
        # Make the audit and the run record reachable from the failure
        # path: transport's failure exceptions carry no attempts list
        # (G-08), so this layer attaches its own.
        try:
            exc.attempt_audit = list(audit_sink)  # type: ignore[attr-defined]
            exc.dispatch_run_record = record  # type: ignore[attr-defined]
        except Exception:
            pass
        raise


__all__ = [
    "DispatchError",
    "PolicyRefused",
    "PayloadRefused",
    "SenderError",
    "SenderConstructionError",
    "SenderNetworkError",
    "DispatchRequest",
    "GateContext",
    "GateHooks",
    "DispatchOutcome",
    "AttemptRecorder",
    "PRODUCTION_SLEEPER",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "canonical_request_bytes",
    "request_fingerprint",
    "make_http_sender",
    "build_payload",
    "dispatch",
]

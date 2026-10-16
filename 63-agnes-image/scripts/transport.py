"""transport.py -- Agnes image transport policy (spec 15 sections 5 and 8).

This module owns HOW a generation request may be sent, never the call
itself: the actual HTTP attempt is injected as `sender`, so the policy is
fully testable offline and no code path here performs network I/O.

Rules enforced:
- Credentials: the client's own AGNES_AI_API_KEY (or a verified approved
  alias name) is read from the environment at call time. Only its
  PRESENCE is ever reported; the value is never logged, returned, or
  embedded in errors. A missing credential stops before any request.
  Never substitute a different account's credential.
- Budget: before any paid attempt, an estimate is checked against the
  approved remaining budget. Unknown pricing marks the cost UNVERIFIED
  and blocks unless the caller explicitly allows unverified cost
  (spec: verify current account terms or mark cost unverified).
- 401/403: stop. Credential or permission problem; retrying does not fix
  it and endless retry is forbidden.
- 429: bounded backoff (max 3 retries, exponential, capped), per-account.
- 5xx: bounded retry (max 2).
- Timeout after submission: AMBIGUOUS. The provider may already hold a
  result (and the charge). This module raises AmbiguousOutcome and never
  resubmits on its own; the caller must check for an existing result
  first, disclose the cost risk, and only then decide on a bounded retry.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

ENDPOINT = "https://apihub.agnes-ai.com/v1/images/generations"
DEFAULT_KEY_ENV = "AGNES_AI_API_KEY"

MAX_429_RETRIES = 3
MAX_5XX_RETRIES = 2
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 30.0


class TransportError(RuntimeError):
    pass


class CredentialsMissing(TransportError):
    pass


class BudgetBlocked(TransportError):
    pass


class AuthStopped(TransportError):
    """401/403: stop and resolve credentials/permissions; do not retry."""


class RateLimited(TransportError):
    """429 persisted past the bounded backoff budget."""


class AmbiguousOutcome(TransportError):
    """A timeout after submission: remote outcome unknown.

    Carries the request fingerprint so the caller can check for an
    existing provider result before any resubmission decision.
    """

    def __init__(self, message: str, request_fingerprint: str):
        super().__init__(message)
        self.request_fingerprint = request_fingerprint


@dataclass
class Budget:
    approved_remaining_usd: float
    allow_unverified_cost: bool = False


@dataclass
class Attempt:
    number: int
    outcome: str  # "ok" | "http_<status>" | "timeout"
    detail: str = ""


@dataclass
class SendResult:
    status: int
    body: bytes
    attempts: list[Attempt] = field(default_factory=list)
    cost_status: str = "verified"  # "verified" | "unverified"


def credential_present(env: dict | None = None, key_env: str = DEFAULT_KEY_ENV) -> bool:
    """Presence only. The value is never read into a log, error, or result."""
    source = os.environ if env is None else env
    value = source.get(key_env)
    return bool(value and str(value).strip())


def preflight(payload_fingerprint: str, *, env: dict | None = None,
              key_env: str = DEFAULT_KEY_ENV, budget: Budget | None = None,
              estimated_cost_usd: float | None = None) -> str:
    """Run before ANY paid attempt. Returns the cost status.

    Raises CredentialsMissing or BudgetBlocked before a request exists.
    """
    if not credential_present(env, key_env):
        raise CredentialsMissing(
            f"credential '{key_env}' is not present in the environment; "
            "stopping before any request (presence checked only, value never read out)"
        )
    if budget is None:
        raise BudgetBlocked("no approved budget supplied; paid generation is not authorized")
    if estimated_cost_usd is None:
        if not budget.allow_unverified_cost:
            raise BudgetBlocked(
                "current account pricing is unverified and unverified cost is not "
                "allowed for this call; verify account terms first or mark the "
                "cost unverified explicitly"
            )
        return "unverified"
    if estimated_cost_usd > budget.approved_remaining_usd:
        raise BudgetBlocked(
            f"estimated cost {estimated_cost_usd} exceeds approved remaining "
            f"budget {budget.approved_remaining_usd}"
        )
    return "verified"


def send_with_policy(sender, request: dict, *, request_fingerprint: str,
                     cost_status: str = "verified",
                     sleeper=lambda seconds: None) -> SendResult:
    """Send one generation request under the bounded-retry policy.

    `sender(request) -> (status:int, body:bytes)` performs exactly one
    HTTP attempt and raises TimeoutError on a transport timeout.
    `sleeper(seconds)` is injected so tests never really sleep.
    """
    attempts: list[Attempt] = []
    retries_429 = 0
    retries_5xx = 0
    number = 0
    while True:
        number += 1
        try:
            status, body = sender(request)
        except TimeoutError as exc:
            attempts.append(Attempt(number, "timeout", str(exc)))
            raise AmbiguousOutcome(
                "timeout after submission: the provider may already hold a "
                "result for this request; check for an existing result "
                "before any resubmission and disclose the cost risk",
                request_fingerprint,
            ) from exc
        attempts.append(Attempt(number, "ok" if status == 200 else f"http_{status}"))
        if status == 200:
            return SendResult(status=status, body=body, attempts=attempts,
                              cost_status=cost_status)
        if status in (401, 403):
            raise AuthStopped(
                f"provider returned {status}: credentials or permissions; "
                "stopping without retry"
            )
        if status == 429:
            if retries_429 >= MAX_429_RETRIES:
                raise RateLimited("429 persisted past the bounded backoff budget")
            delay = min(BACKOFF_BASE_SECONDS * (2 ** retries_429), BACKOFF_CAP_SECONDS)
            retries_429 += 1
            sleeper(delay)
            continue
        if 500 <= status <= 599:
            if retries_5xx >= MAX_5XX_RETRIES:
                raise TransportError(f"provider {status} persisted past the bounded retry budget")
            retries_5xx += 1
            sleeper(min(BACKOFF_BASE_SECONDS * retries_5xx, BACKOFF_CAP_SECONDS))
            continue
        raise TransportError(f"provider returned {status}: request problem; not retrying")

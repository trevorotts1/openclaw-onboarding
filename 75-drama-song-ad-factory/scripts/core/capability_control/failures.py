"""Account failure normalization and the shared account breaker (D30/D31).

Hard quota, credit, account-suspension and authorization failures are kept
separate from temporary throttling and transient service errors. A shared
provider/account breaker suppresses queued launches to the known unavailable
route and exposes ONE actionable event instead of a swarm of identical
failures. Retry-at times come from authoritative responses or an explicit
bounded policy — never an invented short reset for a monthly cap. Deterministic
observation/report scheduling continues while model-powered work is suppressed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

HARD_KINDS = ("CREDIT_EXHAUSTED", "HARD_QUOTA", "ACCOUNT_SUSPENDED", "AUTHORIZATION_FAILURE")
THROTTLE_KIND = "THROTTLED"
TRANSIENT_KIND = "TRANSIENT_SERVICE_ERROR"

_MONTHLY_WORDS = ("monthly", "per month", "billing period", "cycle limit", "cap resets")
_CREDIT_WORDS = ("credit", "insufficient balance", "out of funds", "payment required", "quota exceeded", "usage limit")
_SUSPEND_WORDS = ("suspended", "deactivated", "banned", "account closed", "terminated")
_AUTHZ_WORDS = ("unauthorized", "invalid api key", "invalid x-api-key", "forbidden", "authentication")


@dataclass
class Failure:
    kind: str
    retry_at: Optional[float]  # epoch seconds, or None when unknown
    retry_at_source: str  # "authoritative" | "bounded_policy" | "none"
    hard: bool
    detail: str
    envelope: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "retry_at": self.retry_at,
            "retry_at_source": self.retry_at_source,
            "hard": self.hard,
            "detail": self.detail,
        }


@dataclass
class BoundedPolicy:
    """Explicit bounded retry policy. Deliberately explicit: no default short
    reset exists for a hard cap. `hard_failure_retry_after_s=None` means a hard
    failure with no authoritative retry-at waits for an operator/authoritative
    signal — never an invented short reset for a monthly cap."""

    throttle_max_retry_after_s: int = 120
    transient_max_retry_after_s: int = 300
    hard_failure_retry_after_s: Optional[float] = None


def _first_word_hit(text: str, words) -> Optional[str]:
    low = (text or "").lower()
    for w in words:
        if w in low:
            return w
    return None


def _authoritative_retry_at(envelope: Dict[str, Any], now: float) -> Optional[float]:
    headers = envelope.get("headers") or {}
    for key in ("retry-after", "Retry-After", "x-ratelimit-reset", "X-RateLimit-Reset-Requests"):
        if key in headers:
            raw = str(headers[key]).strip()
            try:
                secs = float(raw)
                if secs >= 0:
                    return now + secs
            except ValueError:
                pass
    body = envelope.get("body") or {}
    for key in ("retry_at", "reset_at", "retryAfter"):
        val = body.get(key) if isinstance(body, dict) else None
        if isinstance(val, (int, float)):
            return float(val) if val > 1e9 else now + float(val)
    return None


def classify(envelope: Dict[str, Any], policy: Optional[BoundedPolicy] = None,
             now: Optional[float] = None) -> Failure:
    """Normalize one provider/account failure envelope into a typed failure."""
    policy = policy or BoundedPolicy()
    now = time.time() if now is None else now
    status = envelope.get("status")
    body = envelope.get("body") if isinstance(envelope.get("body"), dict) else {}
    text = " ".join(str(x) for x in (
        envelope.get("message"), body.get("error"), body.get("message"), body.get("code"),
        (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else None,
    ) if x)
    retry_at = _authoritative_retry_at(envelope, now)
    source = "authoritative" if retry_at is not None else "none"

    kind: str
    hard = False
    if _first_word_hit(text, _SUSPEND_WORDS):
        kind, hard = "ACCOUNT_SUSPENDED", True
    elif status in (401, 403) or _first_word_hit(text, _AUTHZ_WORDS):
        kind, hard = "AUTHORIZATION_FAILURE", True
    elif status == 402 or _first_word_hit(text, _CREDIT_WORDS):
        if _first_word_hit(text, _MONTHLY_WORDS):
            kind, hard = "HARD_QUOTA", True  # monthly cap: hard, no short reset
        else:
            kind, hard = "CREDIT_EXHAUSTED", True
    elif status == 429 or _first_word_hit(text, _MONTHLY_WORDS):
        if _first_word_hit(text, _MONTHLY_WORDS):
            kind, hard = "HARD_QUOTA", True
        elif retry_at is not None and retry_at - now <= policy.throttle_max_retry_after_s:
            kind, hard = THROTTLE_KIND, False
        elif retry_at is None and _first_word_hit(text, ("too many requests", "rate limit", "throttl")):
            kind, hard = THROTTLE_KIND, False
        else:
            kind, hard = "HARD_QUOTA", True
    elif status in (500, 502, 503, 504) or _first_word_hit(text, ("timeout", "connection", "temporarily unavailable", "try again")):
        kind, hard = TRANSIENT_KIND, False
    else:
        kind, hard = TRANSIENT_KIND, False

    if retry_at is None:
        if kind == THROTTLE_KIND:
            retry_at = now + policy.throttle_max_retry_after_s
            source = "bounded_policy"
        elif kind == TRANSIENT_KIND:
            retry_at = now + policy.transient_max_retry_after_s
            source = "bounded_policy"
        elif hard and policy.hard_failure_retry_after_s is not None:
            retry_at = now + policy.hard_failure_retry_after_s
            source = "bounded_policy"
        # else: retry_at stays None ("none") — no invented short reset for a hard cap.
    return Failure(kind=kind, retry_at=retry_at, retry_at_source=source, hard=hard,
                   detail=text[:300], envelope=envelope)


@dataclass
class BreakerEvent:
    event_id: str
    account: str
    kind: str
    retry_at: Optional[float]
    retry_at_source: str
    action: str
    first_seen: float
    status: str = "open"

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class AccountBreaker:
    """Shared provider/account breaker: one actionable event, not a swarm.

    Queued model-powered launches to the known-unavailable route are
    suppressed while open. Deterministic observation/report scheduling always
    continues. Completed outputs are preserved: the breaker never touches them.
    """

    def __init__(self, policy: Optional[BoundedPolicy] = None, now_fn=time.time):
        self.policy = policy or BoundedPolicy()
        self._now = now_fn
        self._open: Dict[str, BreakerEvent] = {}
        self._suppressed: Dict[str, int] = {}
        self.events: List[BreakerEvent] = []

    # ---- admission --------------------------------------------------
    def admit(self, account: str) -> bool:
        ev = self._open.get(account)
        if ev is None:
            return True
        if ev.retry_at is not None and self._now() >= ev.retry_at:
            return True  # policy window elapsed: retry allowed once
        self._suppressed[account] = self._suppressed.get(account, 0) + 1
        return False

    def deterministic_admit(self) -> bool:
        """Deterministic observation/report scheduling never blocks."""
        return True

    # ---- failure intake --------------------------------------------
    def record_failure(self, account: str, envelope: Dict[str, Any]) -> Optional[BreakerEvent]:
        failure = classify(envelope, self.policy, now=self._now())
        if not failure.hard:
            return None  # throttling/transient never open the shared breaker
        ev = self._open.get(account)
        if ev is not None:
            # same open breaker: update the one event, never a second one
            if failure.retry_at is not None and (ev.retry_at is None or failure.retry_at > ev.retry_at):
                ev.retry_at = failure.retry_at
                ev.retry_at_source = failure.retry_at_source
            return None
        ev = BreakerEvent(
            event_id="breaker-%s-%d" % (account, int(self._now())),
            account=account,
            kind=failure.kind,
            retry_at=failure.retry_at,
            retry_at_source=failure.retry_at_source,
            action=self._action_for(failure),
            first_seen=self._now(),
        )
        self._open[account] = ev
        self.events.append(ev)
        return ev  # exactly one actionable event per opening

    def _action_for(self, failure: Failure) -> str:
        if failure.kind == "AUTHORIZATION_FAILURE":
            return "operator: repair account authorization for this route; queued launches stay suppressed"
        if failure.kind == "ACCOUNT_SUSPENDED":
            return "operator: account suspended — resolve with the provider; no automatic retry"
        if failure.kind == "CREDIT_EXHAUSTED":
            return "operator: add credits to the account; queued launches stay suppressed until then"
        if failure.retry_at is None:
            return "operator: hard cap with no authoritative reset — no invented retry; awaiting provider-declared reset or operator action"
        return "operator: hard cap; resume at the authoritative retry-at %s" % failure.retry_at

    # ---- lifecycle --------------------------------------------------
    def close(self, account: str) -> Optional[BreakerEvent]:
        ev = self._open.pop(account, None)
        if ev is None:
            return None
        ev.status = "closed"
        return ev

    def is_open(self, account: str) -> bool:
        ev = self._open.get(account)
        return ev is not None and not (ev.retry_at is not None and self._now() >= ev.retry_at)

    def suppressed_count(self, account: str) -> int:
        return self._suppressed.get(account, 0)

    def open_events(self) -> List[BreakerEvent]:
        return [e for e in self.events if e.status == "open"]

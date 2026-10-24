#!/usr/bin/env python3
"""GHL recipe transport runners (stream W2, assignment W2-U2).

Runs ordered delivery recipes across the real transports using the W2A
operation contracts (shared-utils/ghl/capability_inventory.py) as the ONLY
source of route truth. This module never invents endpoints, payloads or route
order: every dispatch is aimed at a Capability from the W2A inventory, selected
through its select_route/require_route ladders.

Binding rules enforced here (GHL-DELIVERY-SPEC.md "Operation choice" and the
W2A CONTRACTS block):
  * Record route/location/target/readback for every operation (CONTRACTS
    "uncertain_outcome"). Every StepRecord carries them.
  * Reconcile an uncertain result BEFORE retrying. A mutation whose outcome is
    uncertain (timeout, mid-flight connection loss, 5xx) is read back first:
    effect present -> done (no retry); effect proven absent -> exactly one
    bounded retry; reconcile inconclusive -> UNRESOLVED for the operator.
    A blind retry of an uncertain mutation never happens.
  * Bounded backoff on provider limits: 429 -> exponential backoff, prefer
    Retry-After, cap ci.MAX_429_RETRIES; 5xx/timeout -> one retry (ci.MAX_
    5XX_RETRIES), then report. No unbounded loop exists in this module.
  * Never switch tools to bypass a denial. A 401/403 on a route is terminal for
    the whole ladder; the runner raises RouteDenied and does not try the next
    transport. Ladder fall-through happens only when a transport is not
    configured (availability), never after a denial or a payload rejection.
  * A missing credential blocks with the exact fix -- never a silent 401.
  * Report exact HTTP status and body to the operator (operator_report),
    nothing to the client (client_summary).

Planned but intentionally NOT here (add when the caller exists): a bulk-work
pre-flight of X-RateLimit-Daily-Remaining (CONTRACTS "rate_limits" probe) and
live captures -- live verification needs a bundled owner approval naming test
location, temporary objects and operations, so the REST adapter below is real
code proven only against the offline checks; live behavior is UNVERIFIED and
is never claimed as done.

Runnable check:
    python3 shared-utils/ghl/recipe_transport.py
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:  # package context (shared-utils/ghl/__init__.py)
    from . import capability_inventory as ci
except ImportError:  # direct script execution
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import capability_inventory as ci

# --------------------------------------------------------------------------
# Bounded backoff (contract: "Bounded backoff on provider limits")
# --------------------------------------------------------------------------

BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 60.0
OPERATOR_BODY_LIMIT = 2000

CREDENTIAL_FIX = (
    "REST transport needs the location PIT: set GOHIGHLEVEL_API_KEY "
    "(capability_inventory auth_separation: 'REST uses the location PIT "
    "(GOHIGHLEVEL_API_KEY and aliases)'). A missing credential blocks with this "
    "exact fix -- never a silent 401."
)


class AttemptStatus(Enum):
    """What one dispatch attempt means for retry safety."""

    OK = "ok"
    RATE_LIMITED = "rate_limited"        # provider limit: never processed, back off
    DENIED = "denied"                    # 401/403: terminal, never switch tools
    DEFINITE_FAILURE = "definite_failure"  # rejected: no side effect, no retry
    SAFE_RETRYABLE = "safe_retryable"    # provably no side effect: retry bounded
    UNCERTAIN = "uncertain"              # write MAY have landed: reconcile first


class ReconcileVerdict(Enum):
    APPLIED = "applied"
    NOT_APPLIED = "not_applied"
    INDETERMINATE = "indeterminate"


class FinalStatus(Enum):
    OK = "ok"
    OK_RECONCILED = "ok_reconciled_applied"
    OK_UNVERIFIED = "ok_unverified_readback"
    FAILED_DEFINITE = "failed_definite"
    FAILED_DENIED = "failed_denied_terminal"
    FAILED_RATE_LIMITED = "failed_rate_limit_exhausted"
    FAILED_TRANSIENT = "failed_transient_exhausted"
    FAILED_READBACK_MISMATCH = "failed_readback_mismatch"
    UNRESOLVED = "unresolved_needs_operator"


class RecipeError(Exception):
    """Contract violation or unrecoverable transport problem."""


class TransportUnavailable(RecipeError):
    """No configured executor for any candidate route (availability only)."""


class CredentialError(RecipeError):
    """Missing credential: blocked with the exact fix, never a silent 401."""


class RouteDenied(RecipeError):
    """Provider denial: terminal. Never switch tools to bypass it."""

    def __init__(self, message: str, *, record: Optional["StepRecord"] = None):
        super().__init__(message)
        self.record = record


# --------------------------------------------------------------------------
# Requests, attempts, records (every record carries route/location/target/readback)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OperationRequest:
    """One recipe step: the exact operation class plus its real identity."""

    op_class: ci.OpClass
    location: str
    target: str
    resource: str = ""
    surface: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    path_params: Dict[str, str] = field(default_factory=dict)
    query: Dict[str, str] = field(default_factory=dict)
    expected: Dict[str, Any] = field(default_factory=dict)
    dynamic_confirmed: bool = False
    version: str = ""  # per-operation REST Version override (Ver column)
    probe: Optional[Callable[..., Tuple[ReconcileVerdict, str]]] = None


@dataclass(frozen=True)
class AttemptResult:
    """What an executor saw. sent=False means the request provably never left."""

    status: str  # "ok" | "http_error" | "timeout" | "connection_error"
    http_status: Optional[int] = None
    body: str = ""
    data: Optional[Dict[str, Any]] = None
    sent: Optional[bool] = None
    retry_after: Optional[str] = None
    error: str = ""


@dataclass
class AttemptRecord:
    n: int
    status: AttemptStatus
    http_status: Optional[int]
    sent: Optional[bool]
    body: str  # exact body for the operator
    backoff_delay: Optional[float] = None
    retry_after: Optional[str] = None
    reconciled_before_retry: Optional[str] = None


@dataclass
class StepRecord:
    op_class: str
    resource: str
    location: str
    target: str
    capability_id: str
    route: str
    transport: str
    readback_required: bool
    attempts: List[AttemptRecord] = field(default_factory=list)
    reconcile_events: List[Tuple[str, str]] = field(default_factory=list)
    readback: str = "not_in_contract"
    skipped: List[str] = field(default_factory=list)
    final: FinalStatus = FinalStatus.UNRESOLVED
    operator_notes: List[str] = field(default_factory=list)

    def operator_report(self) -> str:
        """Operator view: exact HTTP status and body, verbose."""
        lines = [
            f"route={self.route} capability={self.capability_id} "
            f"transport={self.transport} location={self.location} target={self.target}",
            f"readback_required={self.readback_required} readback={self.readback} final={self.final.value}",
        ]
        for a in self.attempts:
            lines.append(
                f"  attempt {a.n}: {a.status.value} http={a.http_status} sent={a.sent} "
                f"backoff={a.backoff_delay} retry_after={a.retry_after}"
            )
            lines.append(f"    body: {a.body[:OPERATOR_BODY_LIMIT]}")
        for verdict, detail in self.reconcile_events:
            lines.append(f"  reconcile: {verdict} ({detail})")
        for note in self.operator_notes:
            lines.append(f"  note: {note}")
        return "\n".join(lines)

    def client_summary(self) -> str:
        """Client view: outcome only. No status codes, no bodies, ever."""
        if self.final is FinalStatus.OK:
            return "operation completed."
        if self.final is FinalStatus.OK_RECONCILED:
            return "operation completed after confirmation."
        if self.final is FinalStatus.OK_UNVERIFIED:
            return "operation completed; verification pending."
        return "operation needs operator attention."


@dataclass
class RecipeResult:
    steps: List[StepRecord] = field(default_factory=list)

    def all_ok(self) -> bool:
        return all(s.final in (FinalStatus.OK, FinalStatus.OK_RECONCILED) for s in self.steps)


# --------------------------------------------------------------------------
# Classification and bounded backoff
# --------------------------------------------------------------------------


def classify(res: AttemptResult, op_class: ci.OpClass) -> AttemptStatus:
    """One attempt -> retry safety, honoring read-vs-write asymmetry.

    Read/list support never implies create/edit support, and a read has no side
    effect, so a read timeout is safely retryable while a write timeout is
    UNCERTAIN until reconciled.
    """
    if res.status == "ok":
        return AttemptStatus.OK
    if res.http_status == 429:
        return AttemptStatus.RATE_LIMITED
    if res.http_status in (401, 403):
        return AttemptStatus.DENIED
    writing = op_class in ci.WRITE_CLASSES
    if res.status == "http_error" and res.http_status is not None:
        if res.http_status in (408, 500, 502, 503, 504):
            return AttemptStatus.UNCERTAIN if writing else AttemptStatus.SAFE_RETRYABLE
        if 400 <= res.http_status < 500:
            return AttemptStatus.DEFINITE_FAILURE
        return AttemptStatus.UNCERTAIN if writing else AttemptStatus.SAFE_RETRYABLE
    # timeout / connection_error / unparseable response
    if writing and res.sent is not False:
        return AttemptStatus.UNCERTAIN
    return AttemptStatus.SAFE_RETRYABLE


def compute_backoff(retry_index: int, retry_after: Optional[str] = None) -> float:
    """Bounded backoff: prefer Retry-After, else exponential, always capped."""
    if retry_after:
        try:
            v = float(retry_after.strip())
        except ValueError:
            v = None  # non-numeric (HTTP-date): fall back to exponential
        if v is not None and v >= 0:
            return min(v, BACKOFF_CAP_SECONDS)
    return min(BACKOFF_BASE_SECONDS * (2 ** retry_index), BACKOFF_CAP_SECONDS)


# --------------------------------------------------------------------------
# Executors (pluggable; the runner never bypasses one for a denial)
# --------------------------------------------------------------------------


class ScriptedExecutor:
    """Deterministic executor for checks: hands out scripted results in order."""

    def __init__(self, results: Sequence[AttemptResult], log: Optional[List[str]] = None):
        self._results = list(results)
        self.log: List[str] = log if log is not None else []
        self.calls: List[str] = []

    def dispatch(self, cap: ci.Capability, req: OperationRequest) -> AttemptResult:
        self.calls.append(cap.capability_id)
        self.log.append("dispatch:" + cap.capability_id)
        if not self._results:
            raise AssertionError("scripted executor exhausted")
        return self._results.pop(0)


def scripted_probe(log: List[str], outcomes: Sequence[Tuple[ReconcileVerdict, str]]):
    """Deterministic reconcile/readback probe for checks."""
    queue = list(outcomes)

    def probe(req: OperationRequest, res: AttemptResult, purpose: str):
        log.append("probe:" + purpose)
        if not queue:
            raise AssertionError("scripted probe exhausted")
        return queue.pop(0)

    return probe


class RestExecutor:
    """Verified documented API adapter (public REST + PIT).

    Requests are built ONLY from contract routes: verb and path come from the
    W2A Capability.route string, path placeholders are filled from
    req.path_params and a missing value is an error -- a placeholder is never
    invented. No live call happens without a token; the token never reaches a
    log or an exception message.
    """

    def __init__(self, token: str = "", timeout: float = 30.0):
        self._token = token
        self._timeout = timeout

    def dispatch(self, cap: ci.Capability, req: OperationRequest) -> AttemptResult:
        if not self._token:
            raise CredentialError(CREDENTIAL_FIX)
        verb, _, path = cap.route.partition(" ")
        missing = []
        for name in re.findall(r"\{(\w+)\}", path):
            if name in req.path_params:
                path = path.replace("{" + name + "}", str(req.path_params[name]))
            else:
                missing.append(name)
        if missing:
            raise RecipeError(
                f"{cap.capability_id}: missing path params {missing} -- never invent values"
            )
        url = ci.REST_BASE + path
        if req.query:
            url += "?" + urllib.parse.urlencode(req.query)
        headers = {
            "Authorization": "Bearer " + self._token,
            "Version": req.version or ci.REST_VERSION_HEADER.split(":", 1)[1].strip(),
        }
        body = None
        if req.payload:
            body = json.dumps(req.payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=verb)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return AttemptResult(
                    "ok", http_status=getattr(resp, "status", None) or resp.getcode(),
                    body=raw, data=_json_dict(raw), sent=True,
                )
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            return AttemptResult(
                "http_error", http_status=exc.code, body=raw, sent=True,
                retry_after=(exc.headers.get("Retry-After") if exc.headers else None),
            )
        except socket.timeout:
            return AttemptResult("timeout", sent=None, error="request timed out")
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, socket.timeout):
                return AttemptResult("timeout", sent=None, error=str(exc))
            sent = False if isinstance(reason, (socket.gaierror, ConnectionRefusedError)) else None
            return AttemptResult("connection_error", sent=sent, error=str(exc))
        except (ConnectionError, OSError) as exc:
            return AttemptResult("connection_error", sent=None, error=str(exc))


def _json_dict(raw: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def make_readback_probe(
    executor: Any,
    read_cap: ci.Capability,
    params_fn: Callable[[OperationRequest, AttemptResult], Dict[str, str]],
):
    """Real readback/reconcile probe on a READ/LIST contract route.

    Reads never route through the browser, and the route must be a read class
    in the W2A inventory (exact membership only).
    """
    if read_cap.transport is ci.Transport.MANAGED_BROWSER:
        raise RecipeError("reads never route to the managed browser")
    if not (ci.supports(read_cap, ci.OpClass.READ) or ci.supports(read_cap, ci.OpClass.LIST)):
        raise RecipeError(f"{read_cap.capability_id} is not a read route")

    def probe(req: OperationRequest, res: AttemptResult, purpose: str):
        read_req = OperationRequest(
            op_class=ci.OpClass.READ,
            location=req.location,
            target=req.target,
            resource=read_cap.resource,
            path_params=params_fn(req, res),
            expected=req.expected,
        )
        out = executor.dispatch(read_cap, read_req)
        st = classify(out, ci.OpClass.READ)
        if st is AttemptStatus.OK:
            data = out.data or {}
            if req.expected:
                if all(data.get(k) == v for k, v in req.expected.items()):
                    return ReconcileVerdict.APPLIED, "readback matches expected fields"
                return ReconcileVerdict.NOT_APPLIED, "readback differs from expected fields"
            return ReconcileVerdict.APPLIED, "record read back"
        if out.http_status == 404:
            return ReconcileVerdict.NOT_APPLIED, "record absent on readback"
        return ReconcileVerdict.INDETERMINATE, f"readback inconclusive (http={out.http_status})"

    return probe


# --------------------------------------------------------------------------
# The runner
# --------------------------------------------------------------------------


class RecipeRunner:
    """Recipe transport runner over the W2A operation contracts."""

    def __init__(
        self,
        executors: Dict[ci.Transport, Any],
        *,
        probe: Optional[Callable[..., Tuple[ReconcileVerdict, str]]] = None,
        sleep: Callable[[float], None] = time.sleep,
        approval_ref: str = "",
    ):
        for transport in executors:
            if transport is ci.Transport.COMMUNITY_MCP:
                raise ValueError(
                    "community MCP is RETIRED -- never a route "
                    "(capability_inventory TRANSPORT_STATUS)"
                )
            if transport is ci.Transport.CUA and not approval_ref:
                raise ValueError(
                    "CUA is approval-gated: pass approval_ref from a bundled owner "
                    "approval naming test location, temporary objects and operations"
                )
        self._executors = dict(executors)
        self._probe = probe
        self._sleep = sleep

    # -- public API --------------------------------------------------------

    def run_step(self, req: OperationRequest) -> StepRecord:
        if not req.location or not req.target:
            raise RecipeError(
                "every operation records route/location/target/readback: "
                "location and target are required"
            )
        candidates = ci.select_route(
            req.op_class,
            resource=req.resource or None,
            surface=req.surface,
            dynamic_confirmed=req.dynamic_confirmed,
        )
        if not candidates:
            # canonical contract error: reports "incomplete, never as done"
            ci.require_route(
                req.op_class,
                resource=req.resource or None,
                surface=req.surface,
                dynamic_confirmed=req.dynamic_confirmed,
            )
        skipped: List[str] = []
        for cap in candidates:
            executor = self._executors.get(cap.transport)
            if executor is None:
                skipped.append(cap.transport.value)  # availability fall-through ONLY
                continue
            return self._execute(cap, executor, req, skipped)
        raise TransportUnavailable(
            "no configured executor for any candidate route; "
            f"skipped={skipped} candidates={[c.capability_id for c in candidates]}"
        )

    def run_recipe(
        self, requests: Sequence[OperationRequest], *, stop_on_error: bool = True
    ) -> RecipeResult:
        result = RecipeResult()
        for req in requests:
            rec = self.run_step(req)  # RouteDenied propagates with its record
            result.steps.append(rec)
            if stop_on_error and rec.final not in (FinalStatus.OK, FinalStatus.OK_RECONCILED):
                break
        return result

    # -- internals ---------------------------------------------------------

    def _execute(
        self, cap: ci.Capability, executor: Any, req: OperationRequest, skipped: List[str]
    ) -> StepRecord:
        rec = StepRecord(
            op_class=req.op_class.value,
            resource=req.resource,
            location=req.location,
            target=req.target,
            capability_id=cap.capability_id,
            route=cap.route,
            transport=cap.transport.value,
            readback_required=bool(cap.readback and req.op_class in ci.WRITE_CLASSES),
            skipped=skipped,
        )
        max_attempts = 1 + ci.MAX_429_RETRIES + ci.MAX_5XX_RETRIES
        n429 = 0
        n5xx = 0
        n = 0
        while True:
            n += 1
            if n > max_attempts:
                raise AssertionError(f"attempt bound violated: {n} > {max_attempts}")
            out = executor.dispatch(cap, req)
            st = classify(out, req.op_class)
            arec = AttemptRecord(
                n=n, status=st, http_status=out.http_status, sent=out.sent,
                body=out.body, retry_after=out.retry_after,
            )
            rec.attempts.append(arec)

            if st is AttemptStatus.OK:
                break

            if st is AttemptStatus.DENIED:
                rec.final = FinalStatus.FAILED_DENIED
                rec.operator_notes.append(
                    "denied by provider -- terminal; never switch tools to bypass a denial"
                )
                raise RouteDenied(
                    f"route denied (http={out.http_status}) on {cap.route}: "
                    f"{out.body[:200]!r} -- never switch tools to bypass a denial",
                    record=rec,
                )

            if st is AttemptStatus.DEFINITE_FAILURE:
                rec.final = FinalStatus.FAILED_DEFINITE
                rec.operator_notes.append(
                    "definite rejection (no side effect expected) -- not retried"
                )
                return rec

            if st is AttemptStatus.RATE_LIMITED:
                if n429 >= ci.MAX_429_RETRIES:
                    rec.final = FinalStatus.FAILED_RATE_LIMITED
                    rec.operator_notes.append(
                        f"bounded: cap {ci.MAX_429_RETRIES} retries on provider limits"
                    )
                    return rec
                delay = compute_backoff(n429, out.retry_after)
                n429 += 1
                arec.backoff_delay = delay
                self._sleep(delay)
                continue

            if st is AttemptStatus.SAFE_RETRYABLE:
                if n5xx >= ci.MAX_5XX_RETRIES:
                    rec.final = FinalStatus.FAILED_TRANSIENT
                    rec.operator_notes.append(
                        f"bounded: {ci.MAX_5XX_RETRIES} retry on 5xx/timeout, then report"
                    )
                    return rec
                delay = compute_backoff(n5xx, out.retry_after)
                n5xx += 1
                arec.backoff_delay = delay
                self._sleep(delay)
                continue

            # UNCERTAIN: the write may have landed. Reconcile BEFORE any retry.
            verdict, detail = self._reconcile(req, out, rec)
            arec.reconciled_before_retry = verdict.value
            if verdict is ReconcileVerdict.APPLIED:
                rec.readback = "confirmed"
                rec.final = FinalStatus.OK_RECONCILED
                rec.operator_notes.append(
                    "uncertain outcome reconciled: effect confirmed landed; no retry"
                )
                return rec
            if verdict is ReconcileVerdict.INDETERMINATE:
                rec.final = FinalStatus.UNRESOLVED
                rec.operator_notes.append(
                    "reconcile inconclusive -- never blind-retry an uncertain "
                    "mutation; operator decision required"
                )
                return rec
            # NOT_APPLIED: retry is now proven safe, and still bounded.
            if n5xx >= ci.MAX_5XX_RETRIES:
                rec.final = FinalStatus.FAILED_TRANSIENT
                rec.operator_notes.append(
                    "reconciled absent, retry budget exhausted -- reported, not silently retried"
                )
                return rec
            delay = compute_backoff(n5xx, out.retry_after)
            n5xx += 1
            arec.backoff_delay = delay
            self._sleep(delay)

        # success: contract "readback" -- read the record back after every write
        if rec.readback_required:
            probe = req.probe or self._probe
            if probe is None:
                rec.readback = "not_performed"
                rec.final = FinalStatus.OK_UNVERIFIED
                rec.operator_notes.append(
                    "contract demands readback; no probe configured -- "
                    "reported incomplete, never as done"
                )
                return rec
            verdict, detail = probe(req, out, "readback")
            rec.reconcile_events.append((verdict.value, detail))
            if verdict is ReconcileVerdict.APPLIED:
                rec.readback = "confirmed"
                rec.final = FinalStatus.OK
            elif verdict is ReconcileVerdict.NOT_APPLIED:
                rec.readback = "mismatch"
                rec.final = FinalStatus.FAILED_READBACK_MISMATCH
                rec.operator_notes.append(
                    "readback mismatch: intended change not confirmed -- operator attention"
                )
            else:
                rec.readback = "indeterminate"
                rec.final = FinalStatus.OK_UNVERIFIED
                rec.operator_notes.append("readback inconclusive -- reported unverified")
            return rec
        rec.readback = "not_in_contract"
        rec.final = FinalStatus.OK
        return rec

    def _reconcile(
        self, req: OperationRequest, out: AttemptResult, rec: StepRecord
    ) -> Tuple[ReconcileVerdict, str]:
        probe = req.probe or self._probe
        if probe is None:
            detail = (
                "no probe configured -- cannot reconcile an uncertain outcome; "
                "never blind-retry"
            )
            rec.reconcile_events.append((ReconcileVerdict.INDETERMINATE.value, detail))
            return ReconcileVerdict.INDETERMINATE, detail
        verdict, detail = probe(req, out, "reconcile")
        rec.reconcile_events.append((verdict.value, detail))
        return verdict, detail


# --------------------------------------------------------------------------
# Runnable check (assert-based self-check; offline, no live calls)
# --------------------------------------------------------------------------


def self_check() -> None:
    def req(op: ci.OpClass, **kw: Any) -> OperationRequest:
        kw.setdefault("location", "loc_1")
        kw.setdefault("target", "target_1")
        return OperationRequest(op_class=op, **kw)

    def runner(results: Sequence[AttemptResult], outcomes=(), *, transports=(ci.Transport.PUBLIC_REST,),
               expected_log=None, expected_sleeps=None, approval_ref=""):
        log: List[str] = []
        sleeps: List[float] = []
        ex = ScriptedExecutor(results, log=log)
        probe = scripted_probe(log, outcomes) if outcomes else None
        r = RecipeRunner({t: ex for t in transports}, probe=probe,
                         sleep=sleeps.append, approval_ref=approval_ref)
        return r, ex, log, sleeps

    # 0. The W2A contracts this runner consumes are real and in force.
    assert ci.validate_inventory() == [], "W2A inventory must validate clean"
    assert ci.MAX_429_RETRIES == 3 and ci.MAX_5XX_RETRIES == 1, "contract lock"
    assert "Reconcile an uncertain result before retrying" in ci.CONTRACTS["uncertain_outcome"]
    assert "cap 3 retries" in ci.CONTRACTS["rate_limits"]
    assert compute_backoff(0) == 1.0
    assert compute_backoff(10) == BACKOFF_CAP_SECONDS  # backoff is bounded
    assert compute_backoff(0, "7") == 7.0  # Retry-After preferred
    assert compute_backoff(0, "9999") == BACKOFF_CAP_SECONDS  # even Retry-After is capped

    # 1. Uncertain mutation -> reconcile BEFORE retry -> effect landed -> done, no retry.
    r, ex, log, sleeps = runner(
        [AttemptResult("timeout", sent=None)],
        [(ReconcileVerdict.APPLIED, "effect visible on readback")],
    )
    rec = r.run_step(req(ci.OpClass.CREATE, resource="contacts", payload={"name": "x"}))
    assert rec.final is FinalStatus.OK_RECONCILED, rec.final
    assert len(rec.attempts) == 1, "reconciled-as-applied must NOT retry"
    assert log == ["dispatch:contacts.create", "probe:reconcile"], log
    assert rec.readback == "confirmed"
    assert rec.attempts[0].reconciled_before_retry == "applied"

    # 2. Uncertain mutation -> reconcile proves absent -> exactly one bounded retry.
    r, ex, log, sleeps = runner(
        [AttemptResult("timeout", sent=None),
         AttemptResult("ok", http_status=201, body='{"id":"c1"}', data={"id": "c1"}, sent=True)],
        [(ReconcileVerdict.NOT_APPLIED, "record absent"), (ReconcileVerdict.APPLIED, "ok")],
    )
    rec = r.run_step(req(ci.OpClass.CREATE, resource="contacts", payload={}))
    assert rec.final is FinalStatus.OK, rec.final
    assert len(rec.attempts) == 2
    assert rec.attempts[0].reconciled_before_retry == "not_applied"  # verdict gated the retry
    assert rec.attempts[1].reconciled_before_retry is None  # success needs no retry gate
    assert log == ["dispatch:contacts.create", "probe:reconcile",
                   "dispatch:contacts.create", "probe:readback"], \
        "reconcile MUST precede the retry (and readback follow success)"

    # 3. Uncertain mutation -> reconcile indeterminate -> UNRESOLVED, never blind retry.
    r, ex, log, sleeps = runner(
        [AttemptResult("timeout", sent=None)],
        [(ReconcileVerdict.INDETERMINATE, "readback inconclusive")],
    )
    rec = r.run_step(req(ci.OpClass.CREATE, resource="contacts", payload={}))
    assert rec.final is FinalStatus.UNRESOLVED, rec.final
    assert len(rec.attempts) == 1, "indeterminate reconcile must block the retry"
    assert log == ["dispatch:contacts.create", "probe:reconcile"], log

    # 4. Read timeout: no side effect possible -> safe bounded retry, no probe needed.
    r, ex, log, sleeps = runner(
        [AttemptResult("timeout", sent=None), AttemptResult("ok", http_status=200, body="{}", data={})]
    )
    rec = r.run_step(req(ci.OpClass.READ, resource="contacts"))
    assert rec.final is FinalStatus.OK and len(rec.attempts) == 2
    assert rec.reconcile_events == [] and rec.readback == "not_in_contract"

    # 5. 429 honors Retry-After, then succeeds.
    r, ex, log, sleeps = runner(
        [AttemptResult("http_error", http_status=429, body="slow down", retry_after="7", sent=True),
         AttemptResult("ok", http_status=200, body="{}", data={})]
    )
    rec = r.run_step(req(ci.OpClass.READ, resource="contacts"))
    assert rec.final is FinalStatus.OK and sleeps == [7.0], sleeps

    # 6. 429 storm: capped at MAX_429_RETRIES with bounded exponential backoff.
    r, ex, log, sleeps = runner(
        [AttemptResult("http_error", http_status=429, body="limit", sent=True)] * 8
    )
    rec = r.run_step(req(ci.OpClass.READ, resource="contacts"))
    assert rec.final is FinalStatus.FAILED_RATE_LIMITED, rec.final
    assert len(rec.attempts) == 1 + ci.MAX_429_RETRIES
    assert sleeps == [1.0, 2.0, 4.0], sleeps  # exponential, capped
    assert all(s <= BACKOFF_CAP_SECONDS for s in sleeps)

    # 7. Denial is terminal: no ladder switch to bypass it; operator gets the body.
    log2: List[str] = []
    ex_rest = ScriptedExecutor(
        [AttemptResult("http_error", http_status=403,
                       body="insufficient permissions SECRET_MARK", sent=True)], log=log2)
    ex_browser = ScriptedExecutor([], log=log2)
    r = RecipeRunner({ci.Transport.PUBLIC_REST: ex_rest,
                      ci.Transport.MANAGED_BROWSER: ex_browser}, sleep=lambda s: None)
    try:
        r.run_step(req(ci.OpClass.EDIT, payload={}))  # all resources -> ladder has a 2nd rung
    except RouteDenied as exc:
        denied = exc.record
    else:
        raise AssertionError("denial must raise RouteDenied")
    assert denied is not None and denied.final is FinalStatus.FAILED_DENIED
    assert ex_browser.calls == [], "never switch tools to bypass a denial"
    assert "SECRET_MARK" in denied.operator_report() and "403" in denied.operator_report()
    assert "SECRET_MARK" not in denied.client_summary() and "403" not in denied.client_summary()

    # 8. No verified route -> the W2A contract error: incomplete, never as done.
    try:
        r.run_step(req(ci.OpClass.CREATE, resource="products", payload={}))
    except ci.UnsupportedOperation as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("products create must be refused (W2A: reported incomplete)")

    # 9. Write contract demands readback; without a probe it is never claimed done.
    r, ex, log, sleeps = runner([AttemptResult("ok", http_status=201, body='{"id":"c1"}', data={"id": "c1"}, sent=True)])
    rec = r.run_step(req(ci.OpClass.CREATE, resource="contacts", payload={}))
    assert rec.final is FinalStatus.OK_UNVERIFIED and rec.readback == "not_performed"

    # 10. Readback mismatch -> flagged for the operator, not success.
    r, ex, log, sleeps = runner(
        [AttemptResult("ok", http_status=201, body='{"id":"c1"}', data={"id": "c1"}, sent=True)],
        [(ReconcileVerdict.NOT_APPLIED, "field did not land")],
    )
    rec = r.run_step(req(ci.OpClass.CREATE, resource="contacts", payload={}))
    assert rec.final is FinalStatus.FAILED_READBACK_MISMATCH and rec.readback == "mismatch"

    # 11. Missing credential blocks with the exact fix -- never a silent 401.
    try:
        RestExecutor(token="").dispatch(
            next(c for c in ci.OPERATIONS if c.capability_id == "contacts.get"),
            req(ci.OpClass.READ, resource="contacts", path_params={"contactId": "c1"}),
        )
    except CredentialError as exc:
        assert "GOHIGHLEVEL_API_KEY" in str(exc) and "never a silent 401" in str(exc)
    else:
        raise AssertionError("missing credential must block with the exact fix")

    # 12. Interleaved provider limits + uncertain writes stay inside one bound.
    r, ex, log, sleeps = runner(
        [AttemptResult("http_error", http_status=429, body="limit", sent=True),
         AttemptResult("timeout", sent=None),
         AttemptResult("http_error", http_status=429, body="limit", sent=True),
         AttemptResult("timeout", sent=None),
         AttemptResult("ok", http_status=200, body="{}", data={})],
        [(ReconcileVerdict.NOT_APPLIED, "absent"), (ReconcileVerdict.NOT_APPLIED, "absent")],
    )
    rec = r.run_step(req(ci.OpClass.CREATE, resource="contacts", payload={}))
    assert len(rec.attempts) <= 1 + ci.MAX_429_RETRIES + ci.MAX_5XX_RETRIES
    assert rec.final is FinalStatus.FAILED_TRANSIENT
    assert all(a.reconciled_before_retry != "indeterminate" for a in rec.attempts)

    # 13. Every record carries route/location/target/readback (contract "uncertain_outcome").
    assert rec.route.startswith("POST /") and rec.location == "loc_1" and rec.target == "target_1"
    assert rec.readback in {"not_in_contract", "confirmed", "mismatch", "indeterminate", "not_performed"}

    # 14. Retirement and approval gates hold at construction.
    try:
        RecipeRunner({ci.Transport.COMMUNITY_MCP: ex})
    except ValueError as exc:
        assert "RETIRED" in str(exc)
    else:
        raise AssertionError("retired community MCP must never register")
    try:
        RecipeRunner({ci.Transport.CUA: ex})
    except ValueError as exc:
        assert "approval" in str(exc)
    else:
        raise AssertionError("CUA must require a bundled approval")
    RecipeRunner({ci.Transport.CUA: ex}, approval_ref="owner-approval-2026-10-23")

    # 15. Availability fall-through only: unconfigured rung is skipped and recorded.
    r, ex, log, sleeps = runner(
        [AttemptResult("ok", http_status=200, body="{}", data={})],
        transports=(ci.Transport.MANAGED_BROWSER,),
    )
    rec = r.run_step(req(ci.OpClass.EDIT, payload={}))  # full ladder: REST rung unconfigured
    assert rec.transport == "managed_browser" and "public_rest" in rec.skipped, rec

    # 16. Real readback probe (W2A read route): presence/absence/inconclusive.
    read_cap = next(c for c in ci.OPERATIONS if c.capability_id == "contacts.get")
    params_fn = lambda q, s: {"contactId": (s.data or {}).get("id", "")}  # noqa: E731
    ex_read = ScriptedExecutor(
        [AttemptResult("ok", http_status=200, body="{}", data={"id": "c1", "email": "a@b"}, sent=True)])
    probe = make_readback_probe(ex_read, read_cap, params_fn)
    v, _ = probe(req(ci.OpClass.CREATE, resource="contacts", expected={"email": "a@b"}),
                 AttemptResult("ok", data={"id": "c1"}), "readback")
    assert v is ReconcileVerdict.APPLIED
    ex_read = ScriptedExecutor(
        [AttemptResult("ok", http_status=200, body="{}", data={"id": "c1", "email": "zzz"}, sent=True)])
    probe = make_readback_probe(ex_read, read_cap, params_fn)
    v, _ = probe(req(ci.OpClass.CREATE, resource="contacts", expected={"email": "a@b"}),
                 AttemptResult("ok", data={"id": "c1"}), "readback")
    assert v is ReconcileVerdict.NOT_APPLIED
    ex_read = ScriptedExecutor([AttemptResult("http_error", http_status=404, body="not found", sent=True)])
    probe = make_readback_probe(ex_read, read_cap, params_fn)
    v, _ = probe(req(ci.OpClass.CREATE, resource="contacts"),
                 AttemptResult("ok", data={"id": "c1"}), "readback")
    assert v is ReconcileVerdict.NOT_APPLIED
    ex_read = ScriptedExecutor([AttemptResult("http_error", http_status=500, body="boom", sent=True)])
    probe = make_readback_probe(ex_read, read_cap, params_fn)
    v, _ = probe(req(ci.OpClass.CREATE, resource="contacts"),
                 AttemptResult("ok", data={"id": "c1"}), "readback")
    assert v is ReconcileVerdict.INDETERMINATE
    try:
        make_readback_probe(ex_read, next(c for c in ci.OPERATIONS if c.capability_id == "browser.page_content"),
                            params_fn)
    except RecipeError:
        pass
    else:
        raise AssertionError("readback probe must refuse a non-read route")

    # 17. Recipe runner: stops the recipe on failure, reports per step.
    recipe = RecipeRunner(
        {ci.Transport.PUBLIC_REST: _SeqExecutor([
            [AttemptResult("ok", http_status=200, body="{}", data={})],
            [AttemptResult("http_error", http_status=400, body="bad", sent=True)],
            [AttemptResult("ok", http_status=200, body="{}", data={})],
        ])}
    )
    out = recipe.run_recipe([req(ci.OpClass.READ, resource="contacts"),
                            req(ci.OpClass.READ, resource="contacts"),
                            req(ci.OpClass.READ, resource="contacts")])
    assert len(out.steps) == 2 and out.steps[1].final is FinalStatus.FAILED_DEFINITE
    assert not out.all_ok()


class _SeqExecutor:
    """Per-step scripted executor for recipe-level checks."""

    def __init__(self, per_step: Sequence[Sequence[AttemptResult]]):
        self._per_step = [list(s) for s in per_step]
        self._i = 0

    def dispatch(self, cap: ci.Capability, req: OperationRequest) -> AttemptResult:
        results = self._per_step[self._i]
        self._i += 1
        return results.pop(0)


if __name__ == "__main__":
    self_check()
    print("recipe_transport self-check: PASS")
    print(f"  contract source: capability_inventory ({len(ci.OPERATIONS)} routes)")
    print(f"  attempt bound: {1 + ci.MAX_429_RETRIES + ci.MAX_5XX_RETRIES} "
          f"(1 + {ci.MAX_429_RETRIES}x429 + {ci.MAX_5XX_RETRIES}x5xx/timeout)")
    print(f"  backoff: exponential base {BACKOFF_BASE_SECONDS}s cap {BACKOFF_CAP_SECONDS}s, Retry-After preferred")
    print("  reconciliation: uncertain mutations read back before any retry; "
          "inconclusive => unresolved, never blind retry")

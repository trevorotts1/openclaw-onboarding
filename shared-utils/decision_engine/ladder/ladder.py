#!/usr/bin/env python3
"""D07 direct-first ladder (JEV spec 1.1, sections 3.1/3.5/3.6/3.8).

Orchestrates the REAL provider modules — D04 ``typesafe_direct``, D05
``openrouter_decisions``, D06 ``credential_resolver`` — never reimplements
them. Stdlib only. No network at import. No disk reads. No process
environment reads or writes. No key material ever appears in results or logs.

Order (3.1): usable direct credential -> usable OpenRouter credential ->
no-JEV fallback hook. Order is among *eligible* routes only: a stage is
skipped with a typed reason when its credential is absent, its circuit is
open, its permissions deny, or the root budget is gone.

Budgets (3.5/3.6): one RootDeadline stamped at ladder entry. Every stage
receives remaining budget only; nothing extends the root expiry. At most
one direct attempt plus one OpenRouter attempt per run; provider-level
retries inside a stage report their attempt counts and consume the SAME
accounting (no nested retry multiplication).

Permissions (3.8): caller-supplied policy answers spend/transmit per
remote call. Reservation happens BEFORE send, a policy recheck happens at
the send boundary, reconcile happens after. Nothing gate-related runs
inside the network call. ``not_authorized`` / ``data_not_permitted`` /
``budget_exhausted`` are recorded separately from technical errors.

Callers inject fakes for offline tests; defaults wire the real modules.
"""

from __future__ import annotations

import time
from pathlib import Path

# ── skip reasons (typed provenance per stage) ──────────────────────────
SKIP_NO_CREDENTIAL = "no_credential"
SKIP_NOT_AUTHORIZED = "not_authorized"
SKIP_DATA_NOT_PERMITTED = "data_not_permitted"
SKIP_BUDGET_EXHAUSTED = "budget_exhausted"
SKIP_ROOT_DEADLINE = "root_deadline_expired"
SKIP_CIRCUIT_OPEN = "circuit_open"
SKIP_TECHNICAL_UNAVAILABLE = "technical_unavailable"

PROVIDER_DIRECT = "typesafe_direct"
PROVIDER_OPENROUTER = "openrouter"

__all__ = [
    "SKIP_NO_CREDENTIAL",
    "SKIP_NOT_AUTHORIZED",
    "SKIP_DATA_NOT_PERMITTED",
    "SKIP_BUDGET_EXHAUSTED",
    "SKIP_ROOT_DEADLINE",
    "SKIP_CIRCUIT_OPEN",
    "SKIP_TECHNICAL_UNAVAILABLE",
    "PROVIDER_DIRECT",
    "PROVIDER_OPENROUTER",
    "RootDeadline",
    "AttemptAccounting",
    "CircuitBreaker",
    "PermissionsGate",
    "DirectFirstLadder",
]


def _load_providers():
    """Return (typesafe_direct, openrouter_decisions, credential_resolver).

    Package import first; file-location fallback when ladder.py is loaded
    standalone (offline test convention). Both paths load the REAL D04/D05/
    D06 modules — nothing here reimplements transport, validation, or
    credential scoping.
    """
    try:
        from ..providers import credential_resolver as _cr
        from ..providers import openrouter_decisions as _or
        from ..providers import typesafe_direct as _ts
        return _ts, _or, _cr
    except ImportError:
        pass
    import importlib.util
    import sys
    prov_dir = Path(__file__).resolve().parent.parent / "providers"
    loaded = []
    for mod_name, fname in (
        ("d07_typesafe_direct", "typesafe_direct.py"),
        ("d07_openrouter_decisions", "openrouter_decisions.py"),
        ("d07_credential_resolver", "credential_resolver.py"),
    ):
        existing = sys.modules.get(mod_name)
        if existing is not None:
            loaded.append(existing)
            continue
        spec = importlib.util.spec_from_file_location(
            mod_name, prov_dir / fname)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        loaded.append(module)
    return loaded[0], loaded[1], loaded[2]


# ── RootDeadline ───────────────────────────────────────────────────────
class RootDeadline:
    """One monotonic root budget stamped at ladder entry (spec 3.5.1/3.5.2).

    ``clock`` returns seconds like ``time.monotonic`` (inject a fake for
    tests). There is deliberately NO extend/reset method: slow calls,
    restarts, and failovers never grant fresh budget.
    """

    def __init__(self, budget_ms, *, clock=None, start_s=None,
                 settlement_reserve_ms=0):
        self._clock = clock or time.monotonic
        self.start_s = float(start_s) if start_s is not None else float(
            self._clock())
        self.budget_ms = float(budget_ms)
        self.expiry_s = self.start_s + self.budget_ms / 1000.0
        self.settlement_reserve_ms = float(settlement_reserve_ms)

    @property
    def expiry_ms(self):
        return self.expiry_s * 1000.0

    def now_s(self):
        return float(self._clock())

    def remaining_ms(self):
        return self.expiry_s * 1000.0 - self.now_s() * 1000.0

    def expired(self):
        return self.remaining_ms() <= 0

    def send_budget_ms(self, op_limit_ms=None, stage_remaining_ms=None):
        """Smallest of remaining-root-minus-reserve, op limit, stage left."""
        cands = [self.remaining_ms() - self.settlement_reserve_ms]
        if op_limit_ms is not None:
            cands.append(float(op_limit_ms))
        if stage_remaining_ms is not None:
            cands.append(float(stage_remaining_ms))
        return max(0.0, min(cands))


# ── AttemptAccounting ──────────────────────────────────────────────────
class AttemptAccounting:
    """Per-stage attempt counts + estimated/actual cost accumulation.

    Every underlying attempt — including a provider-level retry inside one
    stage — is recorded here against the SAME totals, so nested retries
    cannot multiply the budget.
    """

    def __init__(self):
        self.attempts: dict = {}
        self.estimated_cost = 0.0
        self.actual_cost = 0.0

    def record(self, stage, attempts=1, estimated=0.0, actual=0.0):
        self.attempts[stage] = self.attempts.get(stage, 0) + int(attempts)
        self.estimated_cost += float(estimated)
        self.actual_cost += float(actual)
        return self.attempts[stage]

    def total_attempts(self):
        return sum(self.attempts.values())

    def summary(self):
        return {
            "attempts": dict(self.attempts),
            "total_attempts": self.total_attempts(),
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
        }


# ── CircuitBreaker ─────────────────────────────────────────────────────
class CircuitBreaker:
    """Per-provider failure threshold with cooldown + single half-open probe.

    ``clock`` returns seconds like ``time.monotonic``. After
    ``failure_threshold`` failures the provider opens: ``allow`` returns
    False without calling it. Once ``cooldown_ms`` elapses, exactly ONE
    half-open probe is allowed; it closes on success, re-opens on failure.
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(self, failure_threshold=3, cooldown_ms=60000, clock=None):
        self.failure_threshold = int(failure_threshold)
        self.cooldown_ms = float(cooldown_ms)
        self._clock = clock or time.monotonic
        self._failures: dict = {}
        self._opened_at: dict = {}
        self._probe_in_flight: dict = {}

    def _now_ms(self):
        return float(self._clock()) * 1000.0

    def state_of(self, provider):
        if provider in self._opened_at:
            if self._now_ms() - self._opened_at[provider] >= self.cooldown_ms:
                return self.STATE_HALF_OPEN
            return self.STATE_OPEN
        return self.STATE_CLOSED

    def allow(self, provider):
        """True when the provider may be called now (consumes the probe)."""
        state = self.state_of(provider)
        if state == self.STATE_CLOSED:
            return True
        if state == self.STATE_OPEN:
            return False
        # Half-open: exactly one probe until it resolves.
        if self._probe_in_flight.get(provider):
            return False
        self._probe_in_flight[provider] = True
        return True

    def record_success(self, provider):
        self._failures.pop(provider, None)
        self._opened_at.pop(provider, None)
        self._probe_in_flight.pop(provider, None)

    def record_failure(self, provider):
        count = self._failures.get(provider, 0) + 1
        self._failures[provider] = count
        self._probe_in_flight.pop(provider, None)
        if count >= self.failure_threshold:
            self._opened_at[provider] = self._now_ms()


# ── PermissionsGate ────────────────────────────────────────────────────
class PermissionsGate:
    """Caller-supplied spend/transmit policy + reserve/reconcile hooks.

    ``policy_fn(provider, purpose)`` returns e.g.
    ``{"spend_ok": bool, "transmit_ok": bool, "reason": str}``.
    Default denies everything (fail-closed). Never raises: a broken policy
    denies rather than permits.
    """

    def __init__(self, policy_fn=None, reserve_fn=None, reconcile_fn=None):
        self._policy = policy_fn or (
            lambda provider, purpose: {
                "spend_ok": False, "transmit_ok": False,
                "reason": "no_policy"})
        self._reserve = reserve_fn or (
            lambda provider, estimate: {
                "reservation": None, "estimated": estimate})
        self._reconcile = reconcile_fn or (
            lambda provider, reservation, actual: None)

    def check(self, provider, purpose="decide"):
        try:
            perms = dict(self._policy(provider, purpose))
        except Exception:
            perms = {"spend_ok": False, "transmit_ok": False,
                     "reason": "policy_error"}
        return {
            "spend_ok": bool(perms.get("spend_ok")),
            "transmit_ok": bool(perms.get("transmit_ok")),
            "reason": perms.get("reason"),
        }

    @staticmethod
    def decide_skip(perms):
        """Map a denied permission check to its typed skip reason."""
        if not perms["spend_ok"]:
            if perms.get("reason") == "budget":
                return SKIP_BUDGET_EXHAUSTED
            return SKIP_NOT_AUTHORIZED
        if not perms["transmit_ok"]:
            return SKIP_DATA_NOT_PERMITTED
        return None

    def reserve(self, provider, estimate):
        try:
            return self._reserve(provider, estimate)
        except Exception:
            return {"reservation": None, "estimated": estimate,
                    "error": "reserve_failed"}

    def reconcile(self, provider, reservation, actual):
        try:
            self._reconcile(provider, reservation, actual)
        except Exception:
            pass


# ── default wiring: REAL D04/D05/D06 ───────────────────────────────────
def _default_resolve(company_id, stores, context):
    _, _, cr = _load_providers()
    return cr.resolve_company_credentials(company_id, stores, context)


def _default_direct_call(*, body, api_key, timeout_ms, http_post=None):
    ts, _, _ = _load_providers()
    return ts.post_decisions(body, api_key=api_key,
                             timeout_s=timeout_ms / 1000.0,
                             http_post=http_post)


def _default_openrouter_call(*, state, questions, expected, candidates=(),
                             api_key=None, key_env=None, timeout_s=2.5,
                             transport=None):
    _, oro, _ = _load_providers()
    outcome, detail = oro.send_decisions(
        state, questions, expected, api_key=api_key, env=key_env,
        allowed_candidates=candidates, transport=transport,
        timeout=timeout_s)
    result = {"outcome": outcome, "attempts": 1,
              "estimated_cost": 0.0, "actual_cost": 0.0, "detail": detail}
    if outcome == "ok":
        result["payload"] = detail
    return result


def _default_no_jev_fallback(summary):
    skips = [s.get("skip_reason") for s in summary.get("stages", [])]
    return {"decision_source": "no_jev", "ok": True,
            "outcome": "no_jev_fallback",
            "detail": "no eligible JEV route; deterministic local fallback",
            "stage_skips": skips}


def _as_result(raw):
    """Normalize a sender return to the accounting dict shape."""
    if not isinstance(raw, dict):
        return {"outcome": "transport_error", "attempts": 1,
                "estimated_cost": 0.0, "actual_cost": 0.0,
                "detail": "sender returned non-object"}
    out = dict(raw)
    try:
        out["attempts"] = max(1, int(out.get("attempts", 1)))
    except (TypeError, ValueError):
        out["attempts"] = 1
    for key in ("estimated_cost", "actual_cost"):
        try:
            out[key] = float(out.get(key, 0.0))
        except (TypeError, ValueError):
            out[key] = 0.0
    out.setdefault("outcome", "transport_error")
    return out


def _status_configured(status):
    if status is None:
        return False
    configured = getattr(status, "configured", None)
    if configured is not None:
        return bool(configured)
    if isinstance(status, dict):
        return status.get("state") == "configured" or bool(
            status.get("configured"))
    return False


# ── DirectFirstLadder ──────────────────────────────────────────────────
class DirectFirstLadder:
    """Authorized direct-first ladder over the real D04/D05/D06 modules.

    At most one direct attempt plus one OpenRouter attempt per run; the
    no-JEV fallback hook runs last. Every remote stage flows through the
    permissions gate (check -> reserve -> recheck -> send -> reconcile)
    and shares the single root deadline and attempt accounting.
    """

    def __init__(self, *, resolve_credentials=None, direct_call=None,
                 openrouter_call=None, no_jev_fallback=None,
                 policy_fn=None, reserve_fn=None, reconcile_fn=None,
                 clock=None, circuit=None, failure_threshold=3,
                 cooldown_ms=60000, max_total_attempts=2,
                 root_budget_ms=300000, stage_budget_ms=6000,
                 provider_timeout_ms=2500, settlement_reserve_ms=2000):
        self._resolve = resolve_credentials or _default_resolve
        self._direct = direct_call or _default_direct_call
        self._openrouter = openrouter_call or _default_openrouter_call
        self._fallback = no_jev_fallback or _default_no_jev_fallback
        self._gate = PermissionsGate(policy_fn, reserve_fn, reconcile_fn)
        self._clock = clock or time.monotonic
        self._circuit = circuit or CircuitBreaker(
            failure_threshold, cooldown_ms, clock=self._clock)
        self.max_total_attempts = int(max_total_attempts)
        self.root_budget_ms = float(root_budget_ms)
        self.stage_budget_ms = float(stage_budget_ms)
        self.provider_timeout_ms = float(provider_timeout_ms)
        self.settlement_reserve_ms = float(settlement_reserve_ms)

    @property
    def circuit(self):
        return self._circuit

    def _stage_record(self, stage, provider, outcome, skip_reason=None,
                      attempts=0, timeout_ms=None, remaining_ms=None):
        record = {"stage": stage, "provider": provider, "outcome": outcome,
                  "skip_reason": skip_reason, "attempts": attempts}
        if timeout_ms is not None:
            record["timeout_ms"] = timeout_ms
        if remaining_ms is not None:
            record["remaining_ms_at_entry"] = remaining_ms
        return record

    def _run_provider(self, *, provider, cred_status, send, accounting,
                      root, stage_start_s, purpose, order_log):
        """One gated provider stage. Returns (stage_record, result-or-False)."""
        remaining = root.remaining_ms()
        if root.expired():
            return self._stage_record(provider, provider, "skipped",
                                      SKIP_ROOT_DEADLINE, 0, None,
                                      remaining), False
        if accounting.total_attempts() >= self.max_total_attempts:
            return self._stage_record(provider, provider, "skipped",
                                      SKIP_BUDGET_EXHAUSTED, 0, None,
                                      remaining), False
        if not _status_configured(cred_status):
            order_log.append("skip:%s:%s" % (provider, SKIP_NO_CREDENTIAL))
            return self._stage_record(provider, provider, "skipped",
                                      SKIP_NO_CREDENTIAL, 0, None,
                                      remaining), False
        if not self._circuit.allow(provider):
            order_log.append("skip:%s:%s" % (provider, SKIP_CIRCUIT_OPEN))
            return self._stage_record(provider, provider, "skipped",
                                      SKIP_CIRCUIT_OPEN, 0, None,
                                      remaining), False
        perms = self._gate.check(provider, purpose)
        order_log.append("policy_check:%s" % provider)
        skip = self._gate.decide_skip(perms)
        if skip is not None:
            order_log.append("skip:%s:%s" % (provider, skip))
            return self._stage_record(provider, provider, "skipped",
                                      skip, 0, None, remaining), False
        reservation = self._gate.reserve(provider, 1.0)
        order_log.append("reserve:%s" % provider)
        # Recheck at the send boundary; reservation already held, no DB
        # transaction spans the network call below.
        perms2 = self._gate.check(provider, purpose)
        order_log.append("policy_recheck:%s" % provider)
        skip2 = self._gate.decide_skip(perms2)
        if skip2 is not None:
            self._gate.reconcile(provider, reservation, 0.0)
            order_log.append("reconcile:%s" % provider)
            order_log.append("skip:%s:%s" % (provider, skip2))
            return self._stage_record(provider, provider, "skipped",
                                      skip2, 0, None, remaining), False
        elapsed_stage = (float(self._clock()) - stage_start_s) * 1000.0
        stage_left = self.stage_budget_ms - elapsed_stage
        timeout_ms = root.send_budget_ms(self.provider_timeout_ms,
                                         stage_left)
        order_log.append("send:%s" % provider)
        try:
            raw = send(timeout_ms)
        except (ValueError, TypeError):
            raise  # caller-shaped request defect; handled as defect, never sent
        except Exception as exc:
            raw = {"outcome": "transport_error", "attempts": 1,
                   "detail": "%s: %s" % (type(exc).__name__, exc)}
        self._gate.reconcile(provider, reservation, 1.0)
        order_log.append("reconcile:%s" % provider)
        result = _as_result(raw)
        accounting.record(provider, result["attempts"],
                          result["estimated_cost"], result["actual_cost"])
        return self._stage_record(provider, provider, result["outcome"],
                                  None, result["attempts"], timeout_ms,
                                  remaining), result

    def run(self, *, company_id, stores=(), context=None, state=None,
            questions=None, keys=None, direct_specs=None,
            openrouter_expected=None, openrouter_candidates=(),
            purpose="decide", order_log=None, direct_http=None,
            openrouter_transport=None, root_deadline=None,
            no_jev_fallback=None):
        """Run direct -> OpenRouter -> no-JEV. Never raises on data.

        ``keys`` maps credential names to caller-supplied values (resolved
        through the REAL D04/D05 key resolvers; never read from disk or
        environment here). ``direct_http`` / ``openrouter_transport`` inject
        fake transports for offline tests. Returns typed provenance; key
        material never appears in it.
        """
        ts, oro, _ = _load_providers()
        log = order_log if order_log is not None else []
        accounting = AttemptAccounting()
        root = root_deadline or RootDeadline(
            self.root_budget_ms, clock=self._clock,
            settlement_reserve_ms=self.settlement_reserve_ms)
        stage_start_s = float(self._clock())
        stages = []

        key_map = dict(keys or {})
        try:
            creds = self._resolve(company_id, stores, context or {})
        except Exception as exc:
            creds = {}
            stages.append(self._stage_record(
                "credentials", "none", "transport_error",
                SKIP_TECHNICAL_UNAVAILABLE, 0, None, root.remaining_ms()))
            log.append("skip:credentials:resolver_error:%s"
                       % type(exc).__name__)
        direct_status = (creds or {}).get("direct")
        or_status = (creds or {}).get("openrouter")

        # ── stage 1: direct (D04) ──
        def _send_direct(timeout_ms):
            body = ts.build_request(state or {}, list(questions or []))
            resolved = ts.resolve_direct_key(key_map)
            return self._direct(body=body, api_key=resolved.get("value"),
                                timeout_ms=timeout_ms,
                                http_post=direct_http)

        try:
            record, result = self._run_provider(
                provider=PROVIDER_DIRECT, cred_status=direct_status,
                send=_send_direct, accounting=accounting, root=root,
                stage_start_s=stage_start_s, purpose=purpose,
                order_log=log)
        except (ValueError, TypeError) as exc:
            # Caller-shaped request defect (e.g. bad question shape): the
            # stage is unusable, not a transport failure. Never sent.
            record, result = self._stage_record(
                PROVIDER_DIRECT, PROVIDER_DIRECT, "integration_defect",
                SKIP_TECHNICAL_UNAVAILABLE, 0, None,
                root.remaining_ms()), None
            log.append("skip:%s:request_defect" % PROVIDER_DIRECT)
        stages.append(record)
        if isinstance(result, dict) and result.get("outcome") == "ok":
            payload = result.get("payload")
            if direct_specs is None:
                self._circuit.record_success(PROVIDER_DIRECT)
                return self._verdict(PROVIDER_DIRECT, True, stages,
                                     accounting, root)
            ok, _, _ = ts.normalize_response(payload or {}, direct_specs)
            if ok:
                self._circuit.record_success(PROVIDER_DIRECT)
                return self._verdict(PROVIDER_DIRECT, True, stages,
                                     accounting, root)
            self._circuit.record_failure(PROVIDER_DIRECT)
            stages[-1]["outcome"] = "invalid_response"
        elif isinstance(result, dict):
            self._circuit.record_failure(PROVIDER_DIRECT)

        # ── stage 2: OpenRouter (D05) ──
        def _send_openrouter(timeout_ms):
            key, _ = oro.resolve_key(None, key_map)
            return self._openrouter(
                state=state or {}, questions=list(questions or []),
                expected=openrouter_expected or [],
                candidates=tuple(openrouter_candidates or ()),
                api_key=key, key_env=key_map,
                timeout_s=timeout_ms / 1000.0,
                transport=openrouter_transport)

        record, result = self._run_provider(
            provider=PROVIDER_OPENROUTER, cred_status=or_status,
            send=_send_openrouter, accounting=accounting, root=root,
            stage_start_s=stage_start_s, purpose=purpose, order_log=log)
        stages.append(record)
        if isinstance(result, dict) and result.get("outcome") == "ok":
            self._circuit.record_success(PROVIDER_OPENROUTER)
            return self._verdict(PROVIDER_OPENROUTER, True, stages,
                                 accounting, root)
        if isinstance(result, dict):
            self._circuit.record_failure(PROVIDER_OPENROUTER)

        # ── stage 3: no-JEV fallback hook (local, always permitted) ──
        fallback = no_jev_fallback or self._fallback
        try:
            dunk = fallback({"stages": stages,
                             "accounting": accounting.summary(),
                             "expired": root.expired()})
        except Exception as exc:
            dunk = {"decision_source": "no_jev", "ok": False,
                    "outcome": "fallback_error",
                    "detail": type(exc).__name__}
        if not isinstance(dunk, dict):
            dunk = {"decision_source": "no_jev", "ok": False,
                    "outcome": "fallback_error",
                    "detail": "fallback returned non-object"}
        dunk.setdefault("decision_source", "no_jev")
        stages.append(self._stage_record(
            "no_jev", "no_jev", dunk.get("outcome", "no_jev_fallback"),
            SKIP_ROOT_DEADLINE if root.expired() else None, 0, None,
            root.remaining_ms()))
        verdict = self._verdict("no_jev", bool(dunk.get("ok")), stages,
                                accounting, root)
        verdict["fallback"] = {k: v for k, v in dunk.items()
                               if k != "decision_source"}
        return verdict

    def _verdict(self, source, ok, stages, accounting, root):
        return {"decision_source": source, "ok": bool(ok), "stages": stages,
                "accounting": accounting.summary(),
                "root": {"budget_ms": self.root_budget_ms,
                         "remaining_ms": root.remaining_ms(),
                         "expired": root.expired(),
                         "expiry_ms": root.expiry_ms}}

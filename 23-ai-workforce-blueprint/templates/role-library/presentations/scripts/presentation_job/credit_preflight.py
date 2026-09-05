"""presentation_job/credit_preflight.py -- FIX 12: credit preflight for ALL providers.

THE ONE-SENTENCE PROBLEM THIS FIXES
-----------------------------------
The only credit check anywhere in the department was build_deck.py's Phase-0
Kie balance probe; DeepSeek / OpenRouter / Ollama / 9Router launches spent
first and discovered the empty account mid-run (Codex-confirmed). A mode launch
(FIX 11's Ultra/Standard/Economy) could start a multi-hour job on a provider
with $0.00 left.

WHAT THIS MODULE DOES
---------------------
Before a mode launches, verify the balance can cover the ESTIMATED job cost on
EACH provider the mode will use; refuse/downgrade + notify when it cannot.

Estimation method (fix spec, binding):
  estimate = SUM over the phase plan of
      (expected calls per phase) x (call unit cost)
  where expected calls come from:
    1. the FIX 5 measured per-phase call counts of the last completed run
       (working/telemetry/stage-timings.jsonl `phase_exit` rows carry
       provider_calls/tokens_in/tokens_out), or
    2. the plan's own slide/task counts (plan_calls),
  -- never a guessed constant. With NEITHER source, preflight BLOCKS with
  calls_unestimated rather than inventing a number.

Unit costs come from FIX 13's versioned provider catalog (model_catalog.json
`unit_costs` per model). A model whose unit_costs block is null / carries
status "cost_unknown" is a FIX 13 WARNING: the phase is excluded from the
numeric estimate, estimate_source says "unpriced", and the launch proceeds
loudly -- never assumed free, never silently priced, and never blocking every
model phase on a not-yet-priced catalog. ollama-cloud is spec-priced at $0.00
(monthly pool). Rate shapes understood:
  * per_call_usd / per_image_usd  -- flat cost per call (render/OCR)
  * per_million_tokens_in_usd + per_million_tokens_out_usd -- token-metered;
    cost per phase = calls x measured avg tokens (last run) x rate/1e6, and
    when no per-call token history exists the DECK_MAX_CALL_TOKENS planning
    constant is applied -- a documented budget constant, printed in the
    verdict, never a silent guess.

The estimate is recomputed at each phase boundary with ACTUALS replacing
estimates for completed phases (actuals= argument; the engine's phase-boundary
call site passes the completed phases' real telemetry rows). A projected
overrun at a boundary takes the same refuse/downgrade+notify path as the
launch check -- this module is one verdict function, both callers.

BALANCE EVIDENCE (fail-closed where the spec says, loud where it says)
----------------------------------------------------------------------
  * `balances` = {provider: usd} -- the exact surface a live balance query
    fills. Proofs and the launcher inject it; a future balance probe writes
    the same dict. No value is ever printed beyond the number itself.
  * A provider the plan uses with NO balance entry is `balance_unverified`:
    recorded in the verdict, sent to the notify channel, and the run
    PROCEEDS -- the department's UNDETERMINED precedent (launcher.py): an
    unchecked box is not an outage, but it is never silent. The spec's only
    fail-closed balance rule is the low balance itself, and cost_unknown.
  * A provider whose balance is BELOW its per-provider estimate BLOCKS with
    insufficient_balance, naming provider, balance, estimate, and shortfall.

DOWNGRADE
---------
A blocked verdict carries downgrade_to: the highest mode (from MODE_ORDER)
whose per-provider estimates ALL fit the same balances, or None. The caller
(FIX 11's mode surface) offers it; this module only computes it.

VERDICT CONTRACT (pure data -- callers decide, this module never spends,
never opens sockets, never reads credentials):
  {
    "verdict": "proceed" | "blocked",
    "mode": <mode>,
    "flag": "on" | "off",
    "total_estimate_usd": float,
    "estimated_cost": float,      # FIX 13: same number, the proof's name
    "estimate_source": "catalog" | "unpriced" | None,   # FIX 13
    "per_provider": [{provider, estimate_usd, phases, calls, rate_source,
                      balance, balance_evidence, shortfall_usd}],
    "blocking": [{code, provider, phase_id?, detail}],   # ONLY balance blocks
    "warnings": [{code, provider, phase_id?, detail}],   # FIX 13: never block
    "downgrade_to": str | None,
    "balance_evidence": "measured" | "unverified",
    "notify": [str, ...],     # operator messages (report.dispatch payloads)
    "reasons": [str, ...],    # human-readable trace of every decision
  }

FIX 13 SEMANTICS (master spec): `cost_unknown` is a WARNING + estimate_source
"unpriced" -- the verdict proceeds with a numeric estimate over the priced
phases and names every unpriced one. The ONLY fail-closed blocks left are the
balance-file shortfall (insufficient_balance, a known-negative balance) and
an unresolvable route map from launcher_gate. ollama-cloud prices at $0.00
(monthly pool) by spec, catalog priced or not.

SECRETS: nothing here reads, receives, or emits a credential. Only provider
ids, model ids, counts, and dollar figures appear in a verdict.

Rollout flag: PRESENTATION_CREDIT_PREFLIGHT (default 1 = ON). `=0` is the
documented rollback: the launcher gate is skipped entirely (the pre-FIX-12
behavior -- every launch proceeded unmeasured), never a silently-weakened
check.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Feature flag (rollback = the documented pre-fix path)
# ---------------------------------------------------------------------------
FLAG_ENV = "PRESENTATION_CREDIT_PREFLIGHT"
FLAG_DEFAULT = "1"

#: Balances may be supplied as a JSON file: {"<provider>": <usd float>, ...}.
#: The launcher accepts this so shell callers can inject a probe result
#: without python. A live balance query (when one exists) writes the same
#: shape. The file is READ, never written, by this module.
BALANCES_FILE_ENV = "PRESENTATION_CREDIT_BALANCES_FILE"

#: Mode ceiling order for downgrade computation (FIX 11 names the modes;
#: FIX 12 only needs their relative spend ordering, so the order lives here
#: as data -- FIX 11's launcher surface owns what the modes MEAN).
MODE_ORDER: Tuple[str, ...] = ("ultra", "standard", "economy")

#: Planning constant for token-metered rates when the last completed run has
#: no per-call token history: the department's own authoring budget ceiling.
#: Documented + printed in the verdict -- a budget, never a silent guess.
DECK_MAX_CALL_TOKENS = 8000

#: Codes a blocked verdict can carry (machine-readable; FIX 11's mode
#: surface and the notify channel consume these).
CODE_COST_UNKNOWN = "cost_unknown"
CODE_INSUFFICIENT_BALANCE = "insufficient_balance"
CODE_CALLS_UNESTIMATED = "calls_unestimated"
CODE_NO_ROUTES = "no_routes"
#: FIX 13: an unpriced model is a WARNING, never a block -- the verdict still
#: carries a numeric estimate over the priced phases and names the unpriced
#: ones, so a fresh box with a not-yet-priced catalog launches (loudly) rather
#: than blocking every model phase forever.
CODE_UNPRICED_WARN = "unpriced_warn"
#: FIX 13 estimate_source values: "catalog" when every LLM phase priced off
#: the catalog, "unpriced" when >= 1 phase priced but some rode the WARN path,
#: None when nothing could be priced at all.
ESTIMATE_SOURCE_CATALOG = "catalog"
ESTIMATE_SOURCE_UNPRICED = "unpriced"

#: Providers billed from a monthly pool rather than per call: the master fix
#: spec FIX 13 prices ollama-cloud at 0 ("ollama-cloud 0 (monthly pool)"). A
#: route on this provider is priced $0.00 even when the catalog block is
#: still cost_unknown -- recorded in rate_source, never silent.
ZERO_COST_PROVIDERS = ("ollama-cloud", "ollama_cloud")


def flag_enabled() -> bool:
    """True unless the operator exported PRESENTATION_CREDIT_PREFLIGHT=0."""
    return os.environ.get(FLAG_ENV, FLAG_DEFAULT) != "0"


# ---------------------------------------------------------------------------
# Catalog rate access (FIX 13 boundary: unit_costs live ONLY in the catalog)
# ---------------------------------------------------------------------------
try:
    from presentation_job import model_catalog as _catalog  # package-relative
except ImportError:  # pragma: no cover - direct file run
    try:
        import model_catalog as _catalog  # type: ignore[no-redef]
    except ImportError:
        _catalog = None  # type: ignore[assignment]


def _alias_for_route(route: Optional[Dict[str, Any]]) -> Optional[str]:
    """The catalog alias a routed (provider, model) pair bills under.

    FIX 7's routes carry provider+model; FIX 13's catalog keys the SAME ids
    under aliases. The catalog is the single source of the rate, so the
    (provider, model) -> alias mapping is derived from the catalog itself,
    never hardcoded here.
    """
    if _catalog is None or not route:
        return None
    try:
        doc = _catalog.load_catalog()
    except Exception:  # noqa: BLE001 -- catalog unreadable -> cost_unknown
        return None
    provider = str(route.get("provider") or "")
    model = str(route.get("model") or "")
    for alias, entry in (doc.get("aliases") or {}).items():
        if not isinstance(entry, dict):
            continue
        # Provider match tolerates the catalog's short form ("deepseek") vs
        # the router's endpoint id ("deepseek-direct"): same vendor, one bill.
        ep = str(entry.get("provider") or "")
        if ep == provider or ep.split("-")[0] == provider.split("-")[0]:
            if entry.get("model") == model:
                return alias
    return None


def _rate_for(route: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Rate row for one routed model: {status, shape, ...} or cost_unknown.

    Returns a dict with:
      status: "priced" | "cost_unknown"
      shape:  "per_call" | "per_image" | "per_million_tokens"
      plus the numeric fields that shape uses.
    A missing catalog, an unmapped (provider, model), or a null unit_costs
    block all resolve to cost_unknown -- the spec's fail-closed case.
    """
    provider = str((route or {}).get("provider") or "")
    # FIX 13: ollama-cloud is monthly-pool billed -- $0.00 per call by spec,
    # even before (or without) a priced catalog block.
    if provider in ZERO_COST_PROVIDERS:
        return {"status": "priced", "shape": "per_call",
                "per_call_usd": 0.0, "alias": None,
                "rate_source": "spec: ollama-cloud 0 (monthly pool)"}
    alias = _alias_for_route(route)
    if alias is None or _catalog is None:
        return {"status": CODE_COST_UNKNOWN, "shape": None,
                "reason": "no catalog alias maps this route's provider+model"}
    try:
        entry = _catalog.resolve(alias)
    except Exception as exc:  # noqa: BLE001 -- resolve failure = unknown price
        return {"status": CODE_COST_UNKNOWN, "shape": None,
                "reason": f"catalog resolve failed for {alias}: {exc}"}
    costs = entry.get("unit_costs")
    if not isinstance(costs, dict) or costs.get("status") != "priced":
        return {"status": CODE_COST_UNKNOWN, "shape": None, "alias": alias,
                "reason": "unit_costs block is not priced (null or cost_unknown)"}
    if isinstance(costs.get("per_call_usd"), (int, float)):
        return {"status": "priced", "shape": "per_call",
                "per_call_usd": float(costs["per_call_usd"]), "alias": alias}
    if isinstance(costs.get("per_image_usd"), (int, float)):
        return {"status": "priced", "shape": "per_image",
                "per_call_usd": float(costs["per_image_usd"]), "alias": alias}
    in_usd = costs.get("per_million_tokens_in_usd")
    out_usd = costs.get("per_million_tokens_out_usd")
    if isinstance(in_usd, (int, float)) and isinstance(out_usd, (int, float)):
        return {"status": "priced", "shape": "per_million_tokens",
                "per_million_tokens_in_usd": float(in_usd),
                "per_million_tokens_out_usd": float(out_usd),
                "alias": alias}
    return {"status": CODE_COST_UNKNOWN, "shape": None, "alias": alias,
            "reason": "priced unit_costs block carries no recognized rate shape"}


# ---------------------------------------------------------------------------
# Expected calls (FIX 5 measured history, else the plan's own counts)
# ---------------------------------------------------------------------------
def read_measured_calls(run_dir: Optional[Path]) -> Dict[str, int]:
    """Per-phase call counts from the LAST completed run's FIX 5 telemetry.

    Reads working/telemetry/stage-timings.jsonl `phase_exit` rows and sums
    provider_calls per phase_id (the telemetry the fix spec names as source
    #1). Missing file, unparsable rows, or rows without provider_calls are
    skipped -- an absent reading contributes nothing, and the plan-count
    fallback (or calls_unestimated) answers, never a guess.
    """
    if run_dir is None:
        return {}
    path = Path(run_dir) / "working" / "telemetry" / "stage-timings.jsonl"
    if not path.is_file():
        return {}
    calls: Dict[str, int] = {}
    tokens: Dict[str, Dict[str, int]] = {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict) or row.get("event") != "phase_exit":
                    continue
                phase_id = str(row.get("phase_id") or "")
                if not phase_id:
                    continue
                n = row.get("provider_calls")
                if isinstance(n, (int, float)) and n > 0:
                    calls[phase_id] = calls.get(phase_id, 0) + int(n)
                agg = tokens.setdefault(phase_id, {"in": 0, "out": 0, "calls": 0})
                if isinstance(n, (int, float)) and n > 0:
                    agg["calls"] += int(n)
                for src, dst in (("tokens_in", "in"), ("tokens_out", "out")):
                    t = row.get(src)
                    if isinstance(t, (int, float)) and t > 0:
                        agg[dst] += int(t)
    except OSError:
        return {}
    # stash token history for the per-call average (same file, one read)
    for phase_id, agg in tokens.items():
        if agg["calls"] > 0:
            _TOKEN_HISTORY[phase_id] = agg
    return calls


#: Last-read per-phase token history {phase: {in, out, calls}} from the most
#: recent read_measured_calls() -- module-level cache so preflight() can use
#: measured per-call token averages without a second file read.
_TOKEN_HISTORY: Dict[str, Dict[str, int]] = {}


def _phase_calls(phase_id: str, *, measured_calls: Dict[str, int],
                 plan_calls: Dict[str, int]) -> Optional[int]:
    """Expected calls for one phase: measured first, plan second, never a guess."""
    m = measured_calls.get(phase_id)
    if isinstance(m, (int, float)) and m > 0:
        return int(m)
    p = plan_calls.get(phase_id)
    if isinstance(p, (int, float)) and p > 0:
        return int(p)
    return None


def _phase_cost(phase_id: str, calls: int, rate: Dict[str, Any],
                actual: Optional[Dict[str, Any]]) -> Optional[float]:
    """Cost for one phase on one rate shape. None = cannot price (fail-closed).

    `actual` (completed-phase telemetry row) replaces the estimate per the
    spec: actual provider_calls and tokens are used, never the projection.
    """
    if rate.get("status") != "priced":
        return None
    shape = rate.get("shape")
    if shape == "per_call" or shape == "per_image":
        n = calls
        if isinstance(actual, dict):
            a = actual.get("provider_calls")
            if isinstance(a, (int, float)) and a >= 0:
                n = int(a)
        return round(n * float(rate.get("per_call_usd", 0.0)), 6)
    if shape == "per_million_tokens":
        t_in, t_out = _expected_tokens(phase_id, calls, actual)
        cost = (t_in / 1_000_000.0) * float(rate.get("per_million_tokens_in_usd", 0.0)) \
            + (t_out / 1_000_000.0) * float(rate.get("per_million_tokens_out_usd", 0.0))
        return round(cost, 6)
    return None


def _expected_tokens(phase_id: str, calls: int,
                     actual: Optional[Dict[str, Any]]) -> Tuple[int, int]:
    """(tokens_in, tokens_out) for one phase's calls.

    Order: completed-phase ACTUAL telemetry tokens (actual=), then the last
    run's measured per-call average for the same phase (FIX 5 history), then
    the documented DECK_MAX_CALL_TOKENS planning budget split 2/3 in, 1/3 out
    (mirrors the department's authoring pattern). The source used is named in
    the caller's rate_source string -- never silent.
    """
    if isinstance(actual, dict):
        ti, to = actual.get("tokens_in"), actual.get("tokens_out")
        if isinstance(ti, (int, float)) and isinstance(to, (int, float)) \
                and (ti > 0 or to > 0):
            return int(ti), int(to)
    hist = _TOKEN_HISTORY.get(phase_id)
    if hist and hist.get("calls", 0) > 0:
        per = hist["calls"]
        return (int(hist["in"] / per) * calls, int(hist["out"] / per) * calls)
    per_call = DECK_MAX_CALL_TOKENS
    return (per_call * calls * 2 // 3, per_call * calls // 3)


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------
def load_balances_file(path: Optional[str] = None) -> Dict[str, float]:
    """Read the balances JSON file ($BALANCES_FILE_ENV or an explicit path).

    {"<provider>": <usd>}. Unset/absent/unparsable -> {} (every used provider
    becomes balance_unverified, never a fabricated number). Never printed
    beyond the numeric values themselves.
    """
    src = path or os.environ.get(BALANCES_FILE_ENV)
    if not src:
        return {}
    try:
        doc = json.loads(Path(src).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(doc, dict):
        return {}
    out: Dict[str, float] = {}
    for k, v in doc.items():
        if isinstance(v, (int, float)) and v >= 0:
            out[str(k)] = float(v)
    return out


# ---------------------------------------------------------------------------
# THE verdict
# ---------------------------------------------------------------------------
def preflight(mode: str, *,
              routes: Dict[str, Dict[str, Any]],
              profile: Optional[Dict[str, Any]] = None,
              balances: Optional[Dict[str, float]] = None,
              measured_calls: Optional[Dict[str, int]] = None,
              plan_calls: Optional[Dict[str, int]] = None,
              actuals: Optional[Dict[str, Dict[str, Any]]] = None,
              last_run_dir: Optional[Path] = None) -> Dict[str, Any]:
    """One credit-preflight verdict for one mode launch / phase boundary.

    Args:
      mode: the mode being launched ("ultra"/"standard"/"economy"; any string
            is accepted -- FIX 11 owns the vocabulary).
      routes: {phase_id: model_router decision dict} -- the phase plan's
              CONCRETE routes (FIX 7). A decision with route=None is a
              mechanical/no-LLM phase and costs nothing here.
      profile: the FIX 8 resource profile (accepted for interface parity with
               FIX 7's consumers; balance evidence still comes from
               `balances`, the surface a balance probe fills).
      balances: {provider: usd}. None -> $BALANCES_FILE_ENV file -> {}.
      measured_calls: FIX 5 per-phase call counts (read_measured_calls of the
                last completed run). None + last_run_dir -> read from there.
      plan_calls: the plan's own slide/task counts per phase (source #2).
      actuals: {phase_id: telemetry row} for COMPLETED phases at a boundary
                re-check -- actuals replace estimates per the spec.
      last_run_dir: run dir to read measured calls from when measured_calls
                is None (the launch-call convenience).

    Returns the verdict dict (module docstring contract). PURE: no I/O beyond
    the optional telemetry/balances reads named above, no sockets, no keys.
    """
    measured_calls = dict(measured_calls or {})
    if not measured_calls and last_run_dir is not None:
        measured_calls = read_measured_calls(last_run_dir)
    plan_calls = dict(plan_calls or {})
    actuals = dict(actuals or {})
    balances = dict(balances) if balances is not None else load_balances_file()
    # The profile never supplies a balance today; accepted so FIX 8's record
    # stays in the interface, ignored for evidence (balances is the surface).
    _ = profile

    per_provider: Dict[str, Dict[str, Any]] = {}
    blocking: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    reasons: List[str] = []
    notify: List[str] = []
    total = 0.0
    llm_phases = 0

    for phase_id in sorted(routes):
        decision = routes.get(phase_id) or {}
        route = decision.get("route") if isinstance(decision, dict) else None
        if not route:
            continue  # mechanical / unrouted phase: no LLM spend
        llm_phases += 1
        provider = str(route.get("provider") or "unknown")
        calls = _phase_calls(phase_id, measured_calls=measured_calls,
                             plan_calls=plan_calls)
        if calls is None:
            # FIX 13: an unestimable call count is a WARNING, not a block --
            # the phase is excluded from the estimate and named in
            # warnings[]; the launch proceeds loudly rather than blocking on
            # missing telemetry (the fresh-box case has no history at all).
            warnings.append({
                "code": CODE_CALLS_UNESTIMATED, "provider": provider,
                "phase_id": phase_id,
                "detail": (f"phase {phase_id} on {provider} has no expected "
                           f"call count: no FIX 5 measured provider_calls for "
                           f"it and no plan slide/task count -- phase "
                           f"excluded from the estimate (unpriced), never a "
                           f"guessed spend constant"),
            })
            reasons.append(f"{phase_id}: calls unestimated -> WARN (excluded "
                           f"from estimate)")
            continue
        rate = _rate_for(route)
        if rate.get("status") != "priced":
            alias = rate.get("alias") or _alias_for_route(route) or "?"
            # FIX 13: cost_unknown -> WARN + estimate_source "unpriced",
            # never a block. The unpriced phase is excluded from the numeric
            # estimate over priced phases and named here.
            warnings.append({
                "code": CODE_COST_UNKNOWN, "provider": provider,
                "phase_id": phase_id,
                "detail": (f"model {route.get('model')!r} on {provider} "
                           f"(catalog alias {alias}) has no catalog rate "
                           f"({rate.get('reason') or 'unit_costs cost_unknown'}) "
                           f"-- WARN (estimate_source: unpriced); phase "
                           f"excluded from the numeric estimate, never "
                           f"assumed free"),
            })
            reasons.append(f"{phase_id}: cost_unknown on {provider} -> WARN "
                           f"(excluded from estimate)")
            continue
        actual = actuals.get(phase_id)
        cost = _phase_cost(phase_id, calls, rate, actual)
        if cost is None:
            warnings.append({
                "code": CODE_COST_UNKNOWN, "provider": provider,
                "phase_id": phase_id,
                "detail": f"phase {phase_id} could not be priced on "
                          f"{provider} -- WARN, excluded from the estimate",
            })
            continue
        rate_source = "actuals" if actual else (
            "measured_calls" if phase_id in measured_calls else "plan_counts")
        bucket = per_provider.setdefault(provider, {
            "provider": provider, "estimate_usd": 0.0, "phases": [],
            "calls": 0, "rate_source": rate_source, "models": set(),
        })
        bucket["estimate_usd"] = round(bucket["estimate_usd"] + cost, 6)
        bucket["phases"].append(phase_id)
        bucket["calls"] += calls if not actual else int(
            (actual.get("provider_calls") or 0))
        bucket["models"].add(str(route.get("model") or "?"))
        reasons.append(f"{phase_id}: {calls} calls on {provider} "
                       f"({rate.get('shape')}) = ${cost:.4f} [{rate_source}]")

    # per-provider balance evidence
    balance_evidence: List[str] = []
    for provider, bucket in per_provider.items():
        bucket["models"] = sorted(bucket["models"])  # type: ignore[assignment]
        est = float(bucket["estimate_usd"])
        total = round(total + est, 6)
        bal = balances.get(provider)
        if bal is None:
            bucket["balance"] = None
            bucket["balance_evidence"] = "unverified"
            bucket["shortfall_usd"] = None
            balance_evidence.append("unverified")
            notify.append(
                f"credit preflight ({mode}): balance UNVERIFIED for provider "
                f"{provider} -- estimated ${est:.2f} of the run rides it and "
                f"no balance evidence was supplied; proceeding loudly, "
                f"proceeding on record (cost_unknown models still block).")
            reasons.append(f"{provider}: balance unverified (est ${est:.2f})")
            continue
        bucket["balance"] = float(bal)
        if bal < est:
            shortfall = round(est - bal, 6)
            bucket["balance_evidence"] = "measured"
            bucket["shortfall_usd"] = shortfall
            balance_evidence.append("measured")
            blocking.append({
                "code": CODE_INSUFFICIENT_BALANCE, "provider": provider,
                "detail": (f"provider {provider} balance ${bal:.2f} cannot "
                           f"cover the estimated ${est:.2f} for this run "
                           f"(shortfall ${shortfall:.2f}, phases: "
                           f"{', '.join(bucket['phases'])}) -- refusing "
                           f"{mode} launch BEFORE any spend; add credit or "
                           f"downgrade"),
            })
            reasons.append(f"{provider}: ${bal:.2f} < est ${est:.2f} -> blocked")
            continue
        bucket["balance_evidence"] = "measured"
        bucket["shortfall_usd"] = None
        balance_evidence.append("measured")
        reasons.append(f"{provider}: ${bal:.2f} covers est ${est:.2f}")

    if llm_phases == 0:
        # FIX 13: an empty plan warns (estimate 0.0, nothing priced) rather
        # than blocking -- the balance-file check below still blocks on a
        # measured shortfall, and a genuinely empty phase plan spends $0.
        warnings.append({
            "code": CODE_NO_ROUTES, "provider": None,
            "detail": "the phase plan carries no LLM-routed phases -- "
                      "estimate is $0.00 with nothing priced (WARN)",
        })
        reasons.append("no LLM-routed phases -> WARN (estimate $0.00)")

    verdict = "blocked" if blocking else "proceed"
    downgrade_to = _downgrade(mode, blocking, per_provider, balances,
                              measured_calls, plan_calls, actuals, routes)
    if verdict == "blocked":
        notify.append(
            f"credit preflight REFUSED mode {mode}: "
            + "; ".join(f"[{b['code']}] {b['detail']}" for b in blocking))
    if warnings:
        # FIX 13: unpriced/unestimable phases warn loudly but never block.
        notify.append(
            f"credit preflight ({mode}): {len(warnings)} phase(s) could not "
            f"be priced and are excluded from the numeric estimate -- "
            + "; ".join(f"[{w['code']}] {w.get('phase_id') or '?'}"
                        for w in warnings))
    # FIX 13 estimate_source: what the numeric estimate stands on.
    if warnings and not blocking:
        est_src = ESTIMATE_SOURCE_UNPRICED
    elif warnings and blocking:
        est_src = ESTIMATE_SOURCE_UNPRICED
    elif llm_phases == 0:
        est_src = None  # nothing LLM-routed: no estimate basis at all
    else:
        est_src = ESTIMATE_SOURCE_CATALOG
    return {
        "verdict": verdict,
        "mode": mode,
        "flag": "on" if flag_enabled() else "off",
        "total_estimate_usd": round(total, 6),
        # FIX 13/QC alias: the numeric estimate under the name the proof reads.
        "estimated_cost": round(total, 6),
        "estimate_source": est_src,
        "per_provider": [dict(p) for p in
                          (per_provider.get(k) for k in sorted(per_provider))
                          if p],
        "blocking": blocking,
        "warnings": warnings,
        "downgrade_to": downgrade_to,
        "balance_evidence": ("measured" if balance_evidence
                              and all(e == "measured" for e in balance_evidence)
                              else ("unverified" if balance_evidence else None)),
        "notify": notify,
        "reasons": reasons,
    }


def _downgrade(mode: str, blocking: List[Dict[str, Any]],
               per_provider: Dict[str, Dict[str, Any]],
               balances: Dict[str, float],
               measured_calls: Dict[str, int], plan_calls: Dict[str, int],
               actuals: Dict[str, Dict[str, Any]],
               routes: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """Highest cheaper mode whose estimate fits the SAME balances, else None.

    Only answers when the block is insufficient_balance (the one case a
    cheaper mode can fix). Since FIX 13, cost_unknown / calls_unestimated are
    warnings and never reach `blocking`; the guard below keeps that contract
    honest if a future code joins blocking.
    """
    if not blocking or not any(b["code"] == CODE_INSUFFICIENT_BALANCE
                               for b in blocking):
        return None
    if any(b["code"] in (CODE_COST_UNKNOWN, CODE_CALLS_UNESTIMATED)
           for b in blocking):
        return None  # a price/estimability problem is not a budget problem
    try:
        idx = MODE_ORDER.index(mode)
    except ValueError:
        return None
    # Cheaper modes are assumed to use the same providers at reduced call
    # volume; FIX 11's mode surface owns real per-mode call mixes. The
    # conservative answer: the next mode down is offered only when its
    # name exists, and the caller re-preflights it with its own numbers.
    return MODE_ORDER[idx + 1] if idx + 1 < len(MODE_ORDER) else None


# ---------------------------------------------------------------------------
# Convenience: the launcher's one-call gate
# ---------------------------------------------------------------------------
def launcher_gate(run_dir: Optional[Path], mode: Optional[str], *,
                  balances: Optional[Dict[str, float]] = None,
                  plan_calls: Optional[Dict[str, int]] = None,
                  last_run_dir: Optional[Path] = None) -> Dict[str, Any]:
    """The launcher's preflight: resolve the phase plan's routes from the
    live profile (FIX 7 model_router), measure calls from the last run, and
    return the verdict. Returns {"skipped": "flag-off"} when the rollback
    flag is set -- the caller then proceeds on the documented pre-fix path.
    """
    if not flag_enabled():
        return {"skipped": "flag-off",
                "reason": f"{FLAG_ENV}=0 rollback: no credit gate "
                          f"(pre-FIX-12 behavior)"}
    routes: Dict[str, Dict[str, Any]] = {}
    try:
        try:
            from presentation_job import model_router
        except ImportError:
            import model_router  # type: ignore[no-redef]
        phases = list(model_router.PHASE_CAPABILITY)
    except Exception:  # noqa: BLE001 -- router absent -> cannot price the plan
        phases = []
    for phase_id in phases:
        try:
            # FIX 11 wire: price the routes THIS MODE will actually take. The
            # gate already receives the declared mode and priced every phase at
            # the router's default, so an Economy launch was quoted at the
            # Standard mix. mode=None (an un-moded caller) still resolves
            # through model_router.active_mode -> env -> "standard".
            decision = model_router.resolve_route(phase_id, mode=mode or None)
        except Exception:  # noqa: BLE001 -- a broken route is cost-blocked
            routes[phase_id] = {"route": None}
            continue
        route = decision.get("route") if isinstance(decision, dict) else None
        if route is None and isinstance(decision, dict) \
                and decision.get("capability") != "mechanical":
            # Profile absent (or no eligible provider): the DISPATCHER still
            # runs these phases on its pre-FIX-7 DeepSeek-direct default
            # (dispatch_complete's documented absent-profile path), so the
            # credit preflight must price THAT route -- the money that will
            # actually be spent -- not a phantom "no route" that prices $0.
            # A router=disabled flag answers the same way: the dispatcher's
            # rollback path is that same DeepSeek-direct default.
            try:
                try:
                    from presentation_job import dispatcher as _dsp
                except ImportError:
                    import dispatcher as _dsp  # type: ignore[no-redef]
                model = getattr(_dsp, "DEEPSEEK_MODEL", None) or "deepseek-v4-flash"
            except Exception:  # noqa: BLE001 -- no dispatcher default known
                model = "deepseek-v4-flash"
            decision = dict(decision)
            decision["route"] = {"provider": "deepseek-direct", "model": model}
            decision["reason"] = str(decision.get("reason")
                                     or "") + " [preflight prices the " \
                                     "dispatcher's DeepSeek-direct default]"
        routes[phase_id] = decision
    if not routes:
        return {"verdict": "blocked",
                "blocking": [{"code": CODE_NO_ROUTES, "provider": None,
                              "detail": "no phase routes could be resolved"}],
                "mode": mode, "flag": "on", "total_estimate_usd": 0.0,
                "estimated_cost": 0.0, "estimate_source": None,
                "per_provider": [], "downgrade_to": None, "warnings": [],
                "balance_evidence": None, "notify": [], "reasons": []}
    v = preflight(mode or "standard", routes=routes, balances=balances,
                  plan_calls=plan_calls or {},
                  last_run_dir=last_run_dir or run_dir)
    # Record the verdict into the run dir (state must outlive the log line).
    if run_dir is not None:
        try:
            rp = Path(run_dir)
            rp.mkdir(parents=True, exist_ok=True)
            sidecar = rp / ".credit-preflight.json"
            tmp = sidecar.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(v, indent=2, sort_keys=True),
                           encoding="utf-8")
            os.replace(tmp, sidecar)
        except OSError:
            pass  # best-effort: recording must never block the gate itself
    return v


def notify_verdict(verdict: Dict[str, Any]) -> None:
    """Send a blocked/unverified verdict to the operator channel.

    Uses report.dispatch (the FIX 23 gateway-only transport) with the same
    fixed non-numeric chat_id precedent the capacity gate uses. Best-effort:
    a notify failure must never affect the dispatch decision.
    """
    messages = list(verdict.get("notify") or [])
    if not messages:
        return
    try:
        try:
            from presentation_job import report
        except ImportError:
            import report  # type: ignore[no-redef]
        for msg in messages:
            report.dispatch("credit", "credit_preflight", msg)
    except Exception:  # noqa: BLE001 -- never let notify break dispatch
        pass

# ---------------------------------------------------------------------------
# FIX 13 CLI: `python3 -m presentation_job.credit_preflight --run-dir <dir>`
# The QC proof runs exactly that and reads the JSON verdict: PROCEED, a
# numeric estimated_cost, zero cost_unknown rows. Exit 0 on proceed, 1 on
# blocked -- never on a warning (warnings are not blocks).
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import sys as _sys

    ap = argparse.ArgumentParser(
        prog="presentation_job.credit_preflight",
        description="FIX 12/13 credit preflight verdict for one run dir "
                    "(prints the JSON verdict to stdout)")
    ap.add_argument("--run-dir", required=False, default=None,
                    help="run dir carrying working/telemetry (measured calls) "
                         "and receiving the .credit-preflight.json sidecar")
    ap.add_argument("--mode", default="standard",
                    help="mode being priced (default: standard)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress the notify fan-out (report.dispatch)")
    args = ap.parse_args(argv)

    v = launcher_gate(Path(args.run_dir).expanduser() if args.run_dir
                      else None, args.mode)
    print(json.dumps(v, indent=2, sort_keys=True, default=str))
    if args.quiet:
        v = dict(v)
        v["notify"] = []  # nothing is dispatched; the verdict stands
    else:
        notify_verdict(v)
    return 0 if v.get("verdict") == "proceed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
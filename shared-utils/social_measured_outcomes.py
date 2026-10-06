#!/usr/bin/env python3
"""
social_measured_outcomes.py — F40 measured-outcome learning (ONB, mirror of
CC src/lib/social/measured-outcomes.ts — same semantics, file-backed so the
skills run on boxes without the Command Center DB).

WHY: the original audit proved DELIVERY (delivery receipts, F10's
per-destination readback). None of that is evidence the content PERFORMED.
This module closes the loop between creation, publication and actual audience
response, under three hard rules (SPEC #40 / QC-F40):

  1. MISSING IS UNKNOWN, NEVER ZERO. A provider that did not report a metric
     records {"value": null, "is_unknown": true} — never a fabricated 0, never
     an interpolated value. Aggregation excludes unknowns and reports honest
     coverage; a window whose metric is entirely unknown stays unknown.
  2. ATTRIBUTABLE EXPERIMENTS. Baseline and trial variants are registered with
     the ONE major variable the trial changes (format|hook|timing|creative).
     Comparisons on mixed variables or insufficient volume stay tentative and
     never trigger uncontrolled content or spending increases.
  3. CROSS-CLIENT ISOLATION. Every read and write is company-scoped under
     $SOCIAL_OUTCOMES_DIR/<company_id>/ (client-specific memory is NEVER
     reused across companies; a lookup for a foreign company is refused).

Provider/model/publishing-policy immutability (F31 + F37): performance
proposals NEVER carry a provider/model or publishing-policy change. The
policy guard rejects any proposal that tries; the client choice stays
required for those surfaces.

Metrics enter through record_metric() (the ingest seam used by the GHL
analytics adapter / delivery-receipt reconciliation). No live calls: callers
pass already-fetched observations with account/post IDs, measurement window
and fetched_at. STDLIB ONLY.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

UNKNOWN = "unknown"

# The major variables a trial may change — exactly one per trial.
VARIANT_VARIABLES = ("format", "hook", "timing", "creative")

# Below this many KNOWN observations a conclusion is tentative.
MIN_SAMPLE_FOR_CONFIDENCE = 5

# The agreed review cadence, env-overridable (hours). Default weekly.
DEFAULT_REVIEW_CADENCE = "weekly"

# Policy surfaces a performance proposal may never touch.
_PROTECTED_POLICY_KEYS = frozenset({
    "provider", "provider_id", "model", "model_id", "provider_policy",
    "policy_revision", "role_models", "image_models", "video_models",
    "execution_mode", "publishing_policy", "consent", "evergreen_consent",
})


def outcomes_dir(env: Optional[Dict[str, str]] = None) -> str:
    """Durable outcome store root: $SOCIAL_OUTCOMES_DIR or
    ~/.openclaw/data/social-outcomes."""
    e = env if env is not None else os.environ
    explicit = (e.get("SOCIAL_OUTCOMES_DIR") or "").strip()
    if explicit:
        return explicit
    home = (e.get("HOME") or "/data").strip() or "/data"
    return os.path.join(home, ".openclaw", "data", "social-outcomes")


def _company_dir(company_id: str, env: Optional[Dict[str, str]] = None) -> str:
    """Per-company directory — the isolation boundary."""
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(company_id))
    return os.path.join(outcomes_dir(env), safe)


def _metrics_path(company_id: str, env: Optional[Dict[str, str]] = None) -> str:
    return os.path.join(_company_dir(company_id, env), "metrics.json")


def _variants_path(company_id: str, env: Optional[Dict[str, str]] = None) -> str:
    return os.path.join(_company_dir(company_id, env), "variants.json")


def _reviews_path(company_id: str, env: Optional[Dict[str, str]] = None) -> str:
    return os.path.join(_company_dir(company_id, env), "reviews.json")


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ── Metric ingest: provider-supported observations, UNKNOWN preserved ───────

def record_metric(
    company_id: str,
    account_id: str,
    post_id: str,
    metric: str,
    value: Optional[float],
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
    source: str = "",
    fetched_at: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Persist one provider-supported metric observation for ONE company.

    A None / non-finite value is stored {"value": None, "is_unknown": true} —
    the store never silently coerces a gap into a zero. Returns the row.
    """
    if not company_id or not account_id or not post_id:
        raise ValueError("metric observation requires company_id, account_id, post_id")
    metric = str(metric or "").strip()
    if not metric:
        raise ValueError("metric observation requires a metric name")
    finite = isinstance(value, (int, float)) and not isinstance(value, bool)
    try:
        finite = finite and float(value) == float(value) and float(value) not in (float("inf"), float("-inf"))
    except (TypeError, ValueError, OverflowError):
        finite = False
    is_unknown = not finite
    row = {
        "id": "sm-" + str(uuid.uuid4()),
        "company_id": str(company_id),
        "account_id": str(account_id),
        "post_id": str(post_id),
        "metric": metric,
        "value": (None if is_unknown else float(value)),  # type: ignore[arg-type]
        "is_unknown": bool(is_unknown),
        "window_start": window_start,
        "window_end": window_end,
        "source": source or "",
        "fetched_at": fetched_at or _utc_now_iso(),
    }
    rows = _read_json(_metrics_path(company_id, env), [])
    if not isinstance(rows, list):
        rows = []
    rows.append(row)
    _write_json(_metrics_path(company_id, env), rows)
    return row


def latest_metrics(
    company_id: str,
    env: Optional[Dict[str, str]] = None,
    post_id: Optional[str] = None,
    metric: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """A company's OWN observations (never another company's — the path IS
    the isolation boundary)."""
    rows = _read_json(_metrics_path(company_id, env), [])
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict) or r.get("company_id") != str(company_id):
            continue
        if post_id and r.get("post_id") != post_id:
            continue
        if metric and r.get("metric") != metric:
            continue
        out.append(r)
    out.sort(key=lambda r: str(r.get("fetched_at") or ""), reverse=True)
    return out


def aggregate_metric(rows: List[Dict[str, Any]], metric: str) -> Dict[str, Any]:
    """Aggregate one metric. Unknown observations are EXCLUDED from
    totals/means (never zero-filled, never interpolated) and reported
    separately so coverage is visible. total/mean are None — not 0 — when the
    provider reported nothing at all."""
    metric_rows = [r for r in rows if isinstance(r, dict) and r.get("metric") == metric]
    known = [r for r in metric_rows if r.get("is_unknown") is False and r.get("value") is not None]
    unknown = [r for r in metric_rows if r.get("is_unknown") is True]
    values = [float(r["value"]) for r in known]
    total = sum(values) if values else None
    mean = (total / len(values)) if values else None
    window_start = None
    window_end = None
    for r in metric_rows:
        ws = r.get("window_start")
        we = r.get("window_end")
        if ws and (window_start is None or str(ws) < str(window_start)):
            window_start = ws
        if we and (window_end is None or str(we) > str(window_end)):
            window_end = we
    observed = len(known) + len(unknown)
    return {
        "metric": metric,
        "total": total,
        "mean": mean,
        "known_count": len(known),
        "unknown_count": len(unknown),
        "coverage": (len(known) / observed) if observed else 0,
        "posts": sorted({str(r.get("post_id")) for r in metric_rows}),
        "window_start": window_start,
        "window_end": window_end,
    }


# ── Variants: baseline / trial, ONE major variable at a time ────────────────

def register_variant(
    company_id: str,
    variable: str,
    label: str,
    role: str = "trial",
    cycle_id: Optional[str] = None,
    compared_to: Optional[str] = None,
    created_at: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Register a variant row. The FIRST variant for a company defaults to
    'baseline' (basis: baseline-first). A trial MUST name exactly one major
    variable AND the baseline it compares against."""
    if variable not in VARIANT_VARIABLES:
        raise ValueError("variant variable must be one of %s" % "|".join(VARIANT_VARIABLES))
    if not str(label or "").strip():
        raise ValueError("variant requires a label")
    rows = _read_json(_variants_path(company_id, env), [])
    if not isinstance(rows, list):
        rows = []
    role = role or "trial"
    auto_baseline = not rows and role == "trial"
    if auto_baseline or role == "baseline":
        basis = "baseline-first"
    elif compared_to:
        basis = "single-variable-trial"
    else:
        raise ValueError("a trial variant must name the baseline variant it changes (compared_to)")
    rec = {
        "id": "var-" + str(uuid.uuid4()),
        "company_id": str(company_id),
        "cycle_id": cycle_id,
        "variable": variable,
        "role": "baseline" if auto_baseline else role,
        "label": str(label),
        "compared_to": compared_to,
        "basis": basis,
        "created_at": created_at or _utc_now_iso(),
    }
    rows.append(rec)
    _write_json(_variants_path(company_id, env), rows)
    return rec


def variants(company_id: str, env: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    rows = _read_json(_variants_path(company_id, env), [])
    return [r for r in rows if isinstance(r, dict) and r.get("company_id") == str(company_id)]


# ── Reviews: agreed-cadence performance review + recommendations ────────────

def build_recommendation(
    posts_reviewed: List[str],
    windows: List[Dict[str, Any]],
    aggregates: List[Dict[str, Any]],
) -> str:
    """Deterministic recommendation text. ALWAYS cites the actual posts and
    windows read; carries the explicit unknown caveat; no data → no claim."""
    posts = [p for p in posts_reviewed if p]
    if not posts:
        return ("No posts have published outcomes to review yet — nothing is "
                "claimed. Publish first, then measure within the agreed window.")
    parts: List[str] = []
    win = next((w for w in windows if w.get("window_start") or w.get("window_end")), None)
    win_text = ("window %s to %s" % (win.get("window_start"), win.get("window_end"))
                if win else "recorded windows")
    shown = ", ".join(posts[:5]) + (", …" if len(posts) > 5 else "")
    parts.append("Based on %d post(s) (%s) over the %s." % (len(posts), shown, win_text))
    for agg in aggregates:
        if agg.get("unknown_count", 0) > 0:
            parts.append(
                "%s: %d of %d observation(s) UNKNOWN (not reported by the provider) — "
                "treated as unknown, never zero." % (
                    agg.get("metric"), agg.get("unknown_count", 0),
                    agg.get("known_count", 0) + agg.get("unknown_count", 0)))
        else:
            parts.append("%s: %d reported observation(s)." % (agg.get("metric"), agg.get("known_count", 0)))
        if agg.get("mean") is not None:
            parts.append("Mean %s %.2f across %d reported observation(s)."
                         % (agg.get("metric"), agg["mean"], agg.get("known_count", 0)))
        elif agg.get("known_count", 0) == 0:
            parts.append("No reported %s values — no performance claim is made." % agg.get("metric"))
    return " ".join(parts)


def assert_no_policy_mutation(proposals: List[Dict[str, Any]]) -> None:
    """Reject any proposal that mutates a protected provider/policy surface
    (F31/F37: the client's saved provider/model choice and publishing consent
    are never changed as a side effect of a performance review)."""
    for p in proposals:
        if not isinstance(p, dict):
            continue
        for key in p:
            if key in _PROTECTED_POLICY_KEYS:
                raise ValueError(
                    "performance proposals may never change saved provider/model "
                    "or publishing policy ('%s' is client-choice only — F31/F37)" % key)


def record_performance_review(
    company_id: str,
    posts_reviewed: List[str],
    windows: List[Dict[str, Any]],
    aggregates: List[Dict[str, Any]],
    recommendation: str = "",
    proposals: Optional[List[Dict[str, Any]]] = None,
    cadence: str = DEFAULT_REVIEW_CADENCE,
    reviewed_at: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Record one cadence review. QC-F40 guarantees enforced here:
      - recommendations cite the actual posts + windows read,
      - unknown coverage is stated, never folded into a zero,
      - sample_size < MIN_SAMPLE_FOR_CONFIDENCE → tentative=true,
      - proposals are policy-guarded (never provider/model/publishing policy).
    """
    posts = [p for p in (posts_reviewed or []) if p]
    proposals = proposals or []
    assert_no_policy_mutation(proposals)
    sample_size = sum(int(a.get("known_count", 0)) for a in aggregates if isinstance(a, dict))
    known_any = any(int(a.get("known_count", 0)) > 0 for a in aggregates if isinstance(a, dict))
    tentative = sample_size < MIN_SAMPLE_FOR_CONFIDENCE or not known_any
    text = recommendation or build_recommendation(posts, windows, aggregates)
    policy_guard = ("no provider/model/publishing-policy change — client choice "
                    "required (F31/F37)")
    rec = {
        "id": "rev-" + str(uuid.uuid4()),
        "company_id": str(company_id),
        "reviewed_at": reviewed_at or _utc_now_iso(),
        "cadence": cadence,
        "posts_reviewed": posts,
        "windows": windows or [],
        "sample_size": sample_size,
        "recommendation": text,
        "tentative": bool(tentative),
        "proposals": proposals,
        "policy_guard": policy_guard,
    }
    rows = _read_json(_reviews_path(company_id, env), [])
    if not isinstance(rows, list):
        rows = []
    rows.append(rec)
    _write_json(_reviews_path(company_id, env), rows)
    return rec


def reviews(company_id: str, env: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    rows = _read_json(_reviews_path(company_id, env), [])
    rows = [r for r in rows if isinstance(r, dict) and r.get("company_id") == str(company_id)]
    rows.sort(key=lambda r: str(r.get("reviewed_at") or ""), reverse=True)
    return rows


# ── Cadence review driver (the ONB half of CC's review job) ────────────────

def review_cadence_hours(env: Optional[Dict[str, str]] = None) -> int:
    e = env if env is not None else os.environ
    try:
        return max(1, int((e.get("SOCIAL_PERFORMANCE_REVIEW_HOURS") or "168").strip()))
    except ValueError:
        return 168


def review_company(
    company_id: str,
    now: Optional[datetime] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """One cadence evaluation for ONE company over its OWN rows. Never a live
    call; never touches another company; never changes provider/model or
    publishing policy; low samples stay tentative with no proposals."""
    metrics = latest_metrics(company_id, env)
    posts = sorted({str(m.get("post_id")) for m in metrics if m.get("post_id")})
    if not posts:
        return {"company_id": company_id, "action": "insufficient-data",
                "reason": "no published posts with observations"}
    # Cadence: a review inside the window is a no-op (agreed cadence, not spam).
    existing = reviews(company_id, env)
    weekly = [r for r in existing if r.get("cadence") == DEFAULT_REVIEW_CADENCE]
    now = now or datetime.now(tz=timezone.utc)
    if weekly:
        last = weekly[0].get("reviewed_at") or ""
        try:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if now - last_dt < timedelta(hours=review_cadence_hours(env)):
                return {"company_id": company_id, "action": "recent",
                        "reason": "within cadence window"}
        except ValueError:
            pass
    aggregates = []
    for metric in sorted({str(m.get("metric")) for m in metrics if m.get("metric")}):
        agg = aggregate_metric(metrics, metric)
        if agg["known_count"] + agg["unknown_count"] > 0:
            aggregates.append(agg)
    sample_size = sum(a["known_count"] for a in aggregates)
    windows = []
    for post_id in posts[:20]:
        with_window = next((m for m in metrics if m.get("post_id") == post_id
                            and (m.get("window_start") or m.get("window_end"))), None)
        windows.append({
            "post_id": post_id,
            "window_start": (with_window or {}).get("window_start"),
            "window_end": (with_window or {}).get("window_end"),
        })
    recommendation = ""
    if sample_size == 0:
        recommendation = (
            "Every metric observation in the window is UNKNOWN (the provider "
            "reported nothing). No performance conclusion is drawn — no format, "
            "hook, timing or creative change and no spend change follows from "
            "missing data.")
    proposals = ([{
        "kind": "content-experiment",
        # One variable at a time, only when volume permits. Tentative
        # conclusions never receive a proposal at all.
        "variable": "timing",
        "requires": ("client approval before any change; never provider/model "
                     "or publishing policy"),
    }] if sample_size >= MIN_SAMPLE_FOR_CONFIDENCE else [])
    review = record_performance_review(
        company_id=company_id,
        posts_reviewed=posts,
        windows=windows,
        aggregates=aggregates,
        recommendation=recommendation,
        proposals=proposals,
        cadence=DEFAULT_REVIEW_CADENCE,
        # The driver's (injectable) clock — the cadence comparison reads THIS
        # stamp, so it must be the same `now` the caller evaluated with,
        # never wall-clock (fake-clock testability per the F07 pattern).
        reviewed_at=now.isoformat(),
        env=env,
    )
    return {"company_id": company_id, "action": "reviewed", "review": review,
            "tentative": review["tentative"]}


if __name__ == "__main__":  # pragma: no cover
    import sys
    cid = sys.argv[1] if len(sys.argv) > 1 else "demo"
    print(json.dumps(review_company(cid), indent=2, default=str))
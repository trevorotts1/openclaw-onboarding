"""The intake decision on every delivery (design/webhook-design.md Section 3.3).

Ties the mapper, job-key, and ledger together into the fast, deterministic handler
the webhook route runs. No language model, no Model Context Protocol. The handler
does only: map, tenant-check, dedup-claim, persist, and (on a genuinely new job)
fire the durable flow via the on_accept callback. The HTTP response means
"durably recorded," never "produced."

Response contract:
  accepted            -> {"status": "accepted", "job": <job_key>}
  duplicate           -> {"status": "duplicate", "job": <job_key>}
  accepted-incomplete -> {"status": "accepted-incomplete", "job": <job_key|None>, "missing": [...]}
  quarantine          -> {"status": "quarantine"}

A duplicate is a 200 success on purpose: returning an error would make well-behaved
upstreams retry forever.
"""

from __future__ import annotations

from .job_key import compute_job_key
from .mapper import map_payload


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "y")


def intake(raw, tenant_location_id, ledger, on_accept=None, aliases=None,
           test_contact_id=None, style_transparency_slot=None):
    """Process one webhook delivery. Returns the response dict plus side effects.

    on_accept(job_key, canonical, record) is invoked exactly once per genuinely new
    job (the durable-flow trigger). It is NOT invoked for duplicates, quarantines,
    or needs_input records, so a redelivery never starts a second production run.
    """
    result = map_payload(raw, tenant_location_id, aliases=aliases,
                         style_transparency_slot=style_transparency_slot)

    if result.status == "quarantine":
        # nothing is claimed; the raw payload would be quarantined and the operator alerted
        return {"status": "quarantine", "alerts": result.alerts}

    # Both accepted and accepted-incomplete need a job key; it requires contact_id.
    contact_id = str(result.canonical.get("contact_id", "")).strip()
    if contact_id == "":
        # cannot dedup without a person anchor; hold for operator, never guess a key
        return {"status": "accepted-incomplete", "job": None,
                "missing": result.missing or ["contact_id"], "alerts": result.alerts}

    job_key = compute_job_key(result.canonical)

    if result.status == "accepted-incomplete":
        record = ledger.read(job_key)
        if record is None:
            ledger.claim(job_key, result.canonical, state="needs_input")
        return {"status": "accepted-incomplete", "job": job_key,
                "missing": result.missing, "alerts": result.alerts}

    # result.status == "accepted"
    is_test = _is_truthy(result.canonical.get("_test")) and (
        test_contact_id is not None and contact_id == test_contact_id
    )
    claim_state = "test" if is_test else "received"

    existing = ledger.read(job_key)
    if existing is None:
        record = ledger.claim(job_key, result.canonical, state=claim_state)
        if record is None:
            # lost the exclusive-create race to a concurrent identical delivery
            ledger.touch_duplicate(job_key)
            return {"status": "duplicate", "job": job_key}
        if on_accept is not None:
            on_accept(job_key, result.canonical, record)
        return {"status": "accepted", "job": job_key}

    if existing.get("state") == "failed":
        # a redelivery after a three-strike failure re-runs ONLY on an operator-sanctioned
        # retry flag; otherwise it is a duplicate, so an upstream retry storm cannot hammer
        # a failed job (Section 3.3).
        if _is_truthy(result.canonical.get("retry")):
            record = ledger.set_state(job_key, "received")
            ledger.touch_duplicate(job_key)
            if on_accept is not None:
                on_accept(job_key, result.canonical, record)
            return {"status": "accepted", "job": job_key}
        ledger.touch_duplicate(job_key)
        return {"status": "duplicate", "job": job_key}

    # any state except failed: increment delivery_count, do nothing else
    ledger.touch_duplicate(job_key)
    return {"status": "duplicate", "job": job_key}

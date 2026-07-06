"""Tests for the credit-out queue mechanics (W1.27, PRD Section 5, furnace G6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import credit_queue as cq


def _now():
    return datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)


# --- insufficient-credits detection -----------------------------------------


@pytest.mark.parametrize(
    "error,code,expected",
    [
        (None, 402, True),
        ("HTTP 402 Payment Required", None, True),
        ("Insufficient credits to complete this request", None, True),
        ("insufficient_quota: you have run out", None, True),
        ("Your account balance is too low", None, True),
        ("Please top up your wallet", None, True),
        ("wallet is empty", None, True),
        ("out of credits remaining", None, True),
        ("quota exceeded for this key", None, True),
        ("500 Internal Server Error", None, False),
        ("rate limit exceeded, retry after 30s", None, False),
        ("", None, False),
        (None, 200, False),
    ],
)
def test_is_insufficient_credits(error, code, expected):
    assert cq.is_insufficient_credits(error, code) is expected


# --- pure age / deadline logic ----------------------------------------------


def test_compute_deadline_is_60_days():
    queued = "2026-05-01T00:00:00+00:00"
    deadline = cq.compute_deadline(queued)
    assert deadline.startswith("2026-06-30")


def test_age_and_ageout_boundary():
    now = _now()
    q59 = cq._iso(now - timedelta(days=59))
    q60 = cq._iso(now - timedelta(days=60))
    assert cq.is_aged_out(q59, now) is False
    assert cq.is_aged_out(q60, now) is True
    assert cq.days_until_ageout(q60, now) == 0


def test_normalize_stage_bridges_vocabularies():
    assert cq.normalize_stage("qc") == "in_qc"
    assert cq.normalize_stage("art") == "generating_art"
    assert cq.normalize_stage("audio") == "producing_audio"
    assert cq.normalize_stage("writing") == "writing"


def test_is_resumable_stage():
    assert cq.is_resumable_stage("qc") is True
    assert cq.is_resumable_stage("writing") is True
    assert cq.is_resumable_stage("complete") is False
    assert cq.is_resumable_stage("failed") is False


def test_select_aged_out_and_drainable():
    now = _now()
    jobs = [
        cq.HeldJob("a", "c1", "fish_audio", cq._iso(now - timedelta(days=61)), "producing_audio"),
        cq.HeldJob("b", "c1", "kie_ai", cq._iso(now - timedelta(days=10)), "generating_art"),
        cq.HeldJob("c", "c1", "fish_audio", cq._iso(now - timedelta(days=5)), "producing_audio"),
    ]
    aged = cq.select_aged_out(jobs, now)
    assert [j.job_id for j in aged] == ["a"]
    drain = cq.select_drainable(jobs, ["fish_audio"])
    assert {j.job_id for j in drain} == {"a", "c"}


# --- orchestrator over the in-memory backend --------------------------------


def _queue():
    alerts = []

    def hook(client, service, cls, msg, affected):
        alerts.append((client, service, cls, affected))

    q = cq.CreditQueue(backend=cq.MemoryBackend(), alert_hook=hook)
    return q, alerts


def test_hold_preserves_payload_and_state_and_alerts_once():
    q, alerts = _queue()
    payload = {"contact_id": "x", "answers": {"q1": "a"}}
    partial = {"draft": "written so far"}
    res = q.hold("job1", "c1", "fish_audio", "producing_audio", payload, partial, now=_now())
    assert res["action"] == "held"
    assert res["service"] == "fish_audio"
    assert res["resume_stage"] == "producing_audio"
    assert res["queue_deadline"].startswith("2026-09-04")
    # payload + partial retained for resume
    assert q.backend.payloads["job1"]["payload_json"] == payload
    assert q.backend.payloads["job1"]["partial_state_json"] == partial
    # exactly one first-occurrence alert, operator-side, class insufficient_credits
    assert len(alerts) == 1
    assert alerts[0][2] == cq.INSUFFICIENT_CREDITS_CLASS


def test_hold_rejects_unknown_service_and_terminal_resume_stage():
    q, _ = _queue()
    with pytest.raises(ValueError):
        q.hold("j", "c1", "not_a_service", "writing")
    with pytest.raises(ValueError):
        q.hold("j", "c1", "fish_audio", "complete")


def test_resume_returns_job_to_resume_stage_and_retains_payload():
    q, _ = _queue()
    q.hold("job1", "c1", "fish_audio", "producing_audio", {"p": 1}, {"s": 2}, now=_now())
    q.resume("job1")
    job = q.backend.jobs["job1"]
    assert job["queue_state"] == "resumed"
    assert job["status"] == "producing_audio"
    # payload + partial state survive resume so the pipeline continues where it left off
    assert q.backend.payloads["job1"]["partial_state_json"] == {"s": 2}


def test_age_check_ages_out_past_60_days_and_purges_payload():
    q, alerts = _queue()
    now = _now()
    # a stale hold, planted directly at 61 days old
    old = cq._iso(now - timedelta(days=61))
    q.backend.hold("stale", "c1", "kie_ai", "generating_art", old, {"p": 1}, {"s": 2})
    summary = q.age_check_and_drain(now=now)
    assert summary["aged_out"] == ["stale"]
    assert q.backend.jobs["stale"]["queue_state"] == "aged_out"
    assert q.backend.jobs["stale"]["status"] == "failed"
    assert "stale" not in q.backend.payloads
    assert any(a[2] == "queue_aged_out" for a in alerts)


def test_age_check_drains_restored_service_only():
    q, alerts = _queue()
    now = _now()
    q.hold("fish1", "c1", "fish_audio", "producing_audio", now=now)
    q.hold("kie1", "c1", "kie_ai", "generating_art", now=now)
    summary = q.age_check_and_drain(restored_services=["fish_audio"], now=now)
    assert summary["resumed"] == ["fish1"]
    assert q.backend.jobs["fish1"]["queue_state"] == "resumed"
    assert q.backend.jobs["kie1"]["queue_state"] == "held"  # not restored, stays held
    assert any(a[2] == "service_restored" and a[1] == "fish_audio" for a in alerts)


def test_aged_out_job_is_not_also_drained():
    q, _ = _queue()
    now = _now()
    old = cq._iso(now - timedelta(days=61))
    q.backend.hold("both", "c1", "fish_audio", "producing_audio", old, {"p": 1}, None)
    summary = q.age_check_and_drain(restored_services=["fish_audio"], now=now)
    assert summary["aged_out"] == ["both"]
    assert summary["resumed"] == []  # dropped, never resumed


def test_redact_scrubs_secrets_and_contacts():
    dirty = "token pit-abc123 for jane@doe.com Bearer sk-XYZ call +1 415 555 2671"
    clean = cq.redact(dirty)
    assert "pit-abc123" not in clean
    assert "jane@doe.com" not in clean
    assert "sk-XYZ" not in clean
    assert "[REDACTED]" in clean

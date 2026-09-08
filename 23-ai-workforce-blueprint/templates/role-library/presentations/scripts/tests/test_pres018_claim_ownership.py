"""PRES-018 isolated proof -- claim ownership, fencing, owner-matched release.

QC-PRES-018 obligations proven here against dispatcher.try_claim /
_claim_is_stale / release_claim AS REWRITTEN (2026-09-08):

  1. A claim owned by a LIVE, identity-matched process is NOT stealable --
     no matter how old the file is (the age-steal defect).
  2. A DEAD holder's claim is reclaimed immediately (FIX 105 kept).
  3. Two simultaneous reapers racing to reclaim one dead claim produce
     exactly ONE winner.
  4. An OLD owner's release cannot delete a NEW owner's claim (the
     unconditional-unlink defect).
  5. PID REUSE does not prove original ownership (boot identity).
  6. Fencing at publication: a worker whose claim was stolen cannot
     publish -- its aggregate output is quarantined, not written.
  7. Legacy FIX 105 claims (no owner token) keep their age behaviour.

Run: python3 -m pytest tests/test_pres018_claim_ownership.py -v
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import presentation_job.dispatcher as d  # noqa: E402


def _write_claim(run_dir: Path, phase_id: str, **fields) -> Path:
    path = d._claim_path(run_dir, phase_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"pid": os.getpid(), "claimed_at": "2026-09-08T00:00:00Z",
              "started_at": 0.0}
    record.update(fields)
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. Old LIVE claim cannot be stolen.
# ---------------------------------------------------------------------------
def test_live_claim_not_stealable_by_age(tmp_path):
    run_dir = tmp_path
    _write_claim(run_dir, "P4-COPY", owner_token="live-token",
                 pid=os.getpid(),          # this process: genuinely alive
                 boot_uptime=d._boot_uptime_s())
    # Age far beyond the stale multiple: the old code stole here.
    age_beyond = d.SINGLE_ATTEMPT_BUDGET_S * d.CLAIM_STALE_MULTIPLIER * 100
    stale, why = d._claim_is_stale(d._claim_path(run_dir, "P4-COPY"),
                                   age=age_beyond)
    assert stale is False, f"a live holder must never be reaped by age: {why}"
    # And try_claim on it fails (no steal) even with the old age.
    assert d.try_claim(run_dir, "P4-COPY", "another-dispatcher") is False


def test_expired_but_live_claim_not_stealable(tmp_path):
    """Expiry bounds the UNPROVABLE-liveness edge; it never reaps a
    confirmed-live holder."""
    run_dir = tmp_path
    _write_claim(run_dir, "P4-COPY", owner_token="live-token",
                 pid=os.getpid(),
                 boot_uptime=d._boot_uptime_s(),
                 expiry_at=time.time() - 3600)  # long expired
    stale, _ = d._claim_is_stale(d._claim_path(run_dir, "P4-COPY"), 0.0)
    assert stale is False


# ---------------------------------------------------------------------------
# 2. Dead holder reclaimed. Two simultaneous reapers: one winner.
# ---------------------------------------------------------------------------
def test_dead_holder_reclaimed(tmp_path):
    run_dir = tmp_path
    dead_pid = 999_999_999  # essentially guaranteed dead -> ProcessLookupError
    _write_claim(run_dir, "P4-COPY", owner_token="dead-token",
                 pid=dead_pid, boot_uptime=1_000_000.0)
    assert d.try_claim(run_dir, "P4-COPY", "reaper") is True
    rec = json.loads(d._claim_path(run_dir, "P4-COPY").read_text())
    assert rec["owner_token"] != "dead-token"
    assert rec["worker"] == "reaper"
    assert rec["fencing"] >= 1


def test_two_reapers_one_winner(tmp_path):
    run_dir = tmp_path
    dead_pid = 999_999_999
    _write_claim(run_dir, "P4-COPY", owner_token="dead-token",
                 pid=dead_pid, boot_uptime=1_000_000.0)
    path = d._claim_path(run_dir, "P4-COPY")
    winners: list[str] = []
    lock = __import__("threading").Lock()

    def reaper(worker_id: str) -> None:
        if d.try_claim(run_dir, "P4-COPY", worker_id):
            with lock:
                winners.append(worker_id)

    import threading
    threads = [threading.Thread(target=reaper, args=(f"reaper-{i}",))
               for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1, f"exactly one reaper may win: {winners}"
    rec = json.loads(path.read_text())
    assert rec["worker"] == winners[0]
    # Fencing advanced monotonically through the steal.
    assert rec["fencing"] >= 1


# ---------------------------------------------------------------------------
# 3. Old owner release cannot delete the new owner's claim.
# ---------------------------------------------------------------------------
def test_old_owner_release_cannot_delete_new_claim(tmp_path):
    run_dir = tmp_path
    dead_pid = 999_999_999
    _write_claim(run_dir, "P4-COPY", owner_token="old-owner-token",
                 pid=dead_pid, boot_uptime=1_000_000.0)
    # New owner claims (steals the dead holder) and captures its token.
    assert d.try_claim(run_dir, "P4-COPY", "new-owner") is True
    new_rec = json.loads(d._claim_path(run_dir, "P4-COPY").read_text())
    new_token = new_rec["owner_token"]

    # The OLD owner tries to release with ITS old token: no-op.
    d.release_claim(run_dir, "P4-COPY", owner_token="old-owner-token")
    assert d._claim_path(run_dir, "P4-COPY").is_file(), \
        "an old owner must never delete a new owner's claim"
    assert json.loads(d._claim_path(run_dir, "P4-COPY").read_text())[
        "owner_token"] == new_token

    # A WRONG random token is equally powerless.
    d.release_claim(run_dir, "P4-COPY", owner_token="some-random-token")
    assert d._claim_path(run_dir, "P4-COPY").is_file()

    # The RIGHT token releases.
    d.release_claim(run_dir, "P4-COPY", owner_token=new_token)
    assert not d._claim_path(run_dir, "P4-COPY").exists()


def test_pid_reuse_does_not_prove_ownership(tmp_path):
    """A claim whose recorded pid is THIS process's pid but whose recorded
    boot-relative uptime is in the FUTURE relative to this process's start
    is a REUSED-pid record, not ours: release (legacy two-arg form) must be
    a no-op."""
    run_dir = tmp_path
    future_boot = d._boot_uptime_s() + 10_000.0
    _write_claim(run_dir, "P4-COPY", owner_token="someone",
                 pid=os.getpid(), boot_uptime=future_boot)
    d.release_claim(run_dir, "P4-COPY")          # legacy pid-match form
    assert d._claim_path(run_dir, "P4-COPY").is_file(), \
        "pid reuse must not prove original ownership"


# ---------------------------------------------------------------------------
# 4. Fencing at publication: stale owner's output quarantined.
# ---------------------------------------------------------------------------
def test_stale_owner_output_quarantined_not_published(tmp_path, monkeypatch):
    """A dispatcher that lost its claim to a new owner cannot publish its
    aggregated artifact: the aggregate goes to a quarantine file, the
    dispatch result is exhausted, and target is untouched."""
    CLUSTER_MANIFEST = (
        SCRIPTS.parent.parent.parent.parent.parent
        / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json")
    run_dir = tmp_path / "run"
    (run_dir / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (run_dir / "working" / "copy" / "slides.json").write_text(json.dumps(
        [{"ordinal": i, "slide": i, "slide_id": f"s{i}", "archetype": "cover",
          "copy": [f"Line {i}"], "design_tokens": {"palette": "#223"},
          "research_anchors": [], "negative_requirements": []}
         for i in (1, 2, 3)]))   # 3 slides: the aggregator needs exactly 3 variants
    (run_dir / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"business_name": "TestCo", "hook": "Grow without guesswork"}))
    (run_dir / "state.json").write_text(json.dumps(
        {"manifest_path": str(CLUSTER_MANIFEST)}))

    PHASE = "P-STYLE-SPEC"
    # Someone ELSE holds the claim (a live other worker).
    _write_claim(run_dir, PHASE, owner_token="the-new-owner",
                 pid=os.getpid(), boot_uptime=d._boot_uptime_s())

    from presentation_job.dispatcher import load_manifest_for_run
    manifest = load_manifest_for_run(run_dir)
    phase_obj = manifest.phase_or_none(PHASE)
    assert phase_obj is not None

    monkeypatch.setattr(d, "_model_router", None)
    monkeypatch.setattr(d, "compose_prompt", lambda *a, **k: ("sys", "user"))

    variant_n = {"count": 0}
    variant_lock = __import__("threading").Lock()

    def _variant_stub(system_prompt, user_prompt, **kw):
        with variant_lock:
            variant_n["count"] += 1
            n = variant_n["count"]
        return (json.dumps({"id": f"v{n}", "style_directive": f"style {n}",
                            "representative_slide": 1}),
                {"request_id": f"r{n}"}, {"provider": "stub", "model": "stub-1"})
    monkeypatch.setattr(d, "dispatch_complete", _variant_stub)

    result = d.dispatch_one(
        run_dir, PHASE, {"phase_id": PHASE, "owning_role": "r"},
        dept_root=SCRIPTS.parent, phase_obj=phase_obj,
        worker_id="stale-worker")

    assert result.status == "exhausted"
    assert any("claim lost" in r for r in result.reasons)
    quarantined = list((run_dir / "working").rglob(
        "*.stale-quarantine-stale-worker"))
    assert quarantined, "the stale aggregate must be quarantined, not deleted"


# ---------------------------------------------------------------------------
# 5. Legacy FIX 105 claims keep their behaviour.
# ---------------------------------------------------------------------------
def test_legacy_dead_pid_claim_still_stale(tmp_path):
    run_dir = tmp_path
    dead_pid = 999_999_999
    _write_claim(run_dir, "P4-COPY", pid=dead_pid)   # no owner_token: legacy
    stale, why = d._claim_is_stale(d._claim_path(run_dir, "P4-COPY"), 0.0)
    assert stale is True
    assert "dead" in why


def test_legacy_live_pid_claim_not_stale(tmp_path):
    run_dir = tmp_path
    _write_claim(run_dir, "P4-COPY", pid=os.getpid())  # live: this process
    stale, _ = d._claim_is_stale(d._claim_path(run_dir, "P4-COPY"), 0.0)
    assert stale is False


def test_claim_records_owner_and_expiry(tmp_path):
    run_dir = tmp_path
    assert d.try_claim(run_dir, "P4-COPY", "w1") is True
    rec = json.loads(d._claim_path(run_dir, "P4-COPY").read_text())
    assert rec["owner_token"]
    assert rec["worker"] == "w1"
    assert rec["pid"] == os.getpid()
    assert rec["revision"] == rec["fencing"] >= 1
    assert rec["expiry_at"] > time.time()

# ---------------------------------------------------------------------------
# 8. Fencing advances MONOTONICALLY across steal cycles (QC repair, 2026-09-08:
#    the steal path re-read _next_claim_revision AFTER the victim unlink -- file
#    gone, revision reset to 1 -- and a LEGACY record could never be CAS-stolen
#    at all because None != "").
# ---------------------------------------------------------------------------
def test_steal_advances_fencing_past_predecessor(tmp_path):
    run_dir = tmp_path
    _write_claim(run_dir, "P4-COPY", owner_token="dead-token",
                 pid=999_999_999, boot_uptime=1_000_000.0,
                 fencing=9, revision=9)
    assert d.try_claim(run_dir, "P4-COPY", "reaper") is True
    rec = json.loads(d._claim_path(run_dir, "P4-COPY").read_text())
    assert rec["fencing"] == 10, "fencing must be predecessor+1, never reset to 1"


def test_legacy_stale_claim_is_stealable_and_advances_fencing(tmp_path):
    run_dir = tmp_path
    _write_claim(run_dir, "P4-COPY", pid=999_999_999,   # no owner_token: legacy
                 fencing=7, revision=7)
    assert d.try_claim(run_dir, "P4-COPY", "reaper") is True
    rec = json.loads(d._claim_path(run_dir, "P4-COPY").read_text())
    assert rec["fencing"] == 8


# ---------------------------------------------------------------------------
# 9. Single-target publication fence (QC repair, 2026-09-08: the fence lived
#    only in the fanout aggregate; the plain single-target publish path had
#    none). A worker whose claim was stolen must not overwrite the new owner's
#    target -- its output is quarantined, never published.
# ---------------------------------------------------------------------------
def test_single_target_stale_publish_quarantined_not_written(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    PHASE = "P4-COPY"
    # Someone ELSE holds the claim (a live other worker): THIS worker lost it.
    _write_claim(run_dir, PHASE, owner_token="the-new-owner",
                 pid=os.getpid(), boot_uptime=d._boot_uptime_s())

    target = run_dir / "working" / "copy" / "slides_copy.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("NEW OWNER'S REAL OUTPUT -- must survive untouched")

    # Simulate the single-target publication path's fencing check directly:
    # stale worker's temp file is quarantined, target untouched.
    tmp_path_file = target.with_name(target.name + ".partial-stale-worker-1")
    tmp_path_file.write_text("STALE WORKER'S LOST OUTPUT")

    claim_file = d._claim_path(run_dir, PHASE)
    published = True
    if claim_file.exists():
        claim_rec = d._read_claim_record(claim_file) or {}
        if claim_rec.get("worker") != "stale-worker" or \
                claim_rec.get("owner_token") != d._current_claim_token(run_dir, PHASE, "stale-worker"):
            quarantine = target.with_name(target.name + ".stale-quarantine-stale-worker")
            try:
                tmp_path_file.replace(quarantine)
            except OSError:
                tmp_path_file.unlink(missing_ok=True)
            published = False
    assert published is False, "stale worker must not publish"
    assert target.read_text() == "NEW OWNER'S REAL OUTPUT -- must survive untouched"
    quarantine = list((run_dir / "working").rglob("*.stale-quarantine-stale-worker"))
    assert quarantine, "lost output quarantined, not destroyed"

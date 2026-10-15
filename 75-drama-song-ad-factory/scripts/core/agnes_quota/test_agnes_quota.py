#!/usr/bin/env python3
"""W1-agnes-core-U2 acceptance: agnes_quota daily limits, whole-run admission,
402 day, rollover, release-on-failure and the agnes-progress.json record.

Stdlib + pytest only. Every ledger goes to a throwaway file through
DSAF_AGNES_QUOTA_DB, so the operator's real ledger is never touched and no
network call happens anywhere.

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/agnes_quota
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:
    # CI's "Skill 75 empty-home test suite" runs `python3 <this file>` with a
    # fresh empty HOME BEFORE the pytest step installs pytest, so a bare
    # module-level `import pytest` is a red build there (skill 75 rule: no
    # module-level pytest import under scripts/core). Direct runs never execute
    # this suite -- it is pytest-driven -- and the required "Skill 75 pytest
    # collection + run" step installs pytest and runs every test below for real.
    if __name__ != "__main__":
        raise
    print("note: pytest not installed - agnes_quota suite runs under "
          "python3 -m pytest (Skill 75 pytest collection + run step)")
    sys.exit(0)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from agnes_quota import agnes_quota as Q  # noqa: E402

DAY1 = datetime(2026, 10, 13, 10, 0, 0, tzinfo=timezone.utc)
DAY2 = DAY1 + timedelta(days=1)

FIELDS = ("clips_total", "clips_done", "in_flight", "waiting_reason",
          "next_continue_utc", "eta_minutes_low", "eta_minutes_high",
          "updated_utc")


@pytest.fixture
def env(tmp_path):
    """A private ledger file; HOME points inside the test dir too."""
    return {"DSAF_AGNES_QUOTA_DB": str(tmp_path / "agnes-quota.sqlite3"),
            "HOME": str(tmp_path / "home")}


# --- platform path (SPEC A12) -------------------------------------------------

def test_state_path_env_override_wins(tmp_path):
    got = Q.state_path({"DSAF_AGNES_QUOTA_DB": "/x/q.sqlite3",
                        "HOME": "/home/node"})
    assert str(got) == "/x/q.sqlite3"


def test_state_path_platform_rows(tmp_path):
    home = str(tmp_path)
    assert str(Q.state_path({"HOME": "/data"})) == \
        "/data/.openclaw/drama-runs/.agnes-quota.sqlite3"
    assert str(Q.state_path({"HOME": "/home/node"})) == \
        "/home/node/.openclaw/drama-runs/.agnes-quota.sqlite3"
    assert str(Q.state_path({"HOME": home, "OPENCLAW_HOME": home})) == \
        home + "/.openclaw/drama-runs/.agnes-quota.sqlite3"
    assert str(Q.state_path({"HOME": home})) == \
        home + "/.drama-song-ad-factory/agnes-quota.sqlite3"


def test_limits_and_env_override():
    assert Q.LIMITS == {"video": 500, "image": 4000}
    assert Q.limits({}) == {"video": 500, "image": 4000}
    assert Q.limits({"AGNES_DAILY_VIDEO_SECONDS": "120"})["video"] == 120
    assert Q.limits({"AGNES_DAILY_IMAGES": "7"})["image"] == 7


# --- whole-run admission (SPEC A5.3) -----------------------------------------

def test_thirty_clips_on_an_empty_day_fit(env):
    res = Q.fits_today(30, DAY1, env=env)
    assert res["fits"] is True
    assert res["video_seconds"] == 300
    assert res["allowance_seconds"] == 360     # 300 s x 1.2
    assert res["remaining_video_seconds"] == 500
    assert res["waiting_reason"] is None


def test_thirty_clips_after_200_used_wait_whole_for_the_reset(env):
    Q.reserve("video", 200, "run-1", env=env, now=DAY1)
    assert Q.remaining("video", DAY1, env=env) == 300

    res = Q.fits_today(30, DAY1, env=env)
    assert res["fits"] is False
    assert res["allowance_seconds"] == 360
    # No split: the whole run waits for the next 00:00 UTC.
    assert res["waiting_reason"] == "agnes-quota-next-day"
    assert res["next_continue_utc"] == "2026-10-14T00:00:00Z"
    # Nothing partial was taken for today.
    assert Q.remaining("video", DAY1, env=env) == 300


def test_five_minute_cap_refuses_a_seven_minute_run():
    assert Q.AGNES_MAX_DELIVERED_S == 298
    assert Q.check_length(298) == 298.0
    with pytest.raises(Q.QuotaError) as exc:
        Q.check_length(420)            # 7 minutes
    assert exc.value.code == "AGNES_LENGTH_CAP"
    with pytest.raises(Q.QuotaError) as exc:
        Q.check_length(300)            # a raw 5 minutes, not chosen - 2
    assert exc.value.code == "AGNES_LENGTH_CAP"


# --- the vendor 402 and the rollover -----------------------------------------

def test_402_zeroes_only_that_utc_day(env):
    Q.record_vendor_402(DAY1, env=env)
    assert Q.remaining("video", DAY1, env=env) == 0
    assert Q.remaining("image", DAY1, env=env) == 0
    with pytest.raises(Q.QuotaError) as exc:
        Q.reserve("video", 1, "run-2", env=env, now=DAY1)
    assert exc.value.code == "AGNES_QUOTA_EXHAUSTED"
    assert Q.fits_today(1, DAY1, env=env)["fits"] is False

    # The next UTC day is untouched.
    assert Q.remaining("video", DAY2, env=env) == 500
    assert Q.fits_today(30, DAY2, env=env)["fits"] is True


def test_rollover_frees_quota(env):
    Q.reserve("video", 450, "run-3", env=env, now=DAY1)
    assert Q.remaining("video", DAY1, env=env) == 50
    assert Q.fits_today(30, DAY1, env=env)["fits"] is False
    assert Q.remaining("video", DAY2, env=env) == 500
    assert Q.fits_today(30, DAY2, env=env)["fits"] is True


def test_failed_job_releases_its_seconds(env):
    row = Q.reserve("video", 100, "run-4", "seg-1", env=env, now=DAY1)
    assert Q.remaining("video", DAY1, env=env) == 400
    assert Q.settle(row, ok=False, env=env) is True
    assert Q.remaining("video", DAY1, env=env) == 500
    assert Q.settle(row, ok=False, env=env) is False   # already closed

    kept = Q.reserve("video", 100, "run-4", "seg-2", env=env, now=DAY1)
    assert Q.settle(kept, ok=True, env=env) is True
    assert Q.remaining("video", DAY1, env=env) == 400


def test_image_day_and_short_reserve_refused(env):
    Q.reserve("image", 4000, "run-5", env=env, now=DAY1)
    assert Q.remaining("image", DAY1, env=env) == 0
    with pytest.raises(Q.QuotaError) as exc:
        Q.reserve("image", 1, "run-5", env=env, now=DAY1)
    assert exc.value.code == "AGNES_QUOTA_EXHAUSTED"
    with pytest.raises(Q.QuotaError):
        Q.reserve("video", 501, "run-5", env=env, now=DAY1)


# --- the background-job progress file (SPEC A11) ------------------------------

def test_progress_has_every_field_and_the_12_of_30_eta(tmp_path):
    rec = Q.progress(tmp_path, 30, 12, in_flight=2, now=DAY1)
    assert tuple(rec) == FIELDS
    assert rec["clips_total"] == 30
    assert rec["clips_done"] == 12
    assert rec["in_flight"] == 2
    assert rec["waiting_reason"] is None
    assert rec["next_continue_utc"] is None
    # 18 clips left = 9 rounds of 2 x 11-13 min.
    assert rec["eta_minutes_low"] == 9 * 11 == 99
    assert rec["eta_minutes_high"] == 9 * 13 == 117
    assert rec["updated_utc"] == "2026-10-13T10:00:00Z"

    path = tmp_path / "control" / Q.PROGRESS_NAME
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == rec
    # Atomic write: the temp file lived in the same folder and is gone.
    leftovers = [p.name for p in (tmp_path / "control").iterdir()]
    assert leftovers == [Q.PROGRESS_NAME]


def test_progress_waiting_and_full_run_eta(tmp_path):
    rec = Q.progress(tmp_path, 30, 30, now=DAY1)
    assert rec["eta_minutes_low"] == 0
    assert rec["eta_minutes_high"] == 0

    rec = Q.progress(tmp_path, 30, 0, waiting_reason="agnes-quota-next-day",
                     next_continue_utc="2026-10-14T00:00:00Z", now=DAY1)
    assert rec["waiting_reason"] == "agnes-quota-next-day"
    assert rec["next_continue_utc"] == "2026-10-14T00:00:00Z"
    assert rec["eta_minutes_low"] == 15 * 11
    assert rec["eta_minutes_high"] == 15 * 13

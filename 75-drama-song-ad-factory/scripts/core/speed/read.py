#!/usr/bin/env python3
"""speed.read: N-92 smarter sending and reading, as callable run-path helpers.

Row N-92 (section 9): a job's status is read by its expected finish time, not
on a fixed timer; the clip length asked for is the shot plus 1 second unless a
camera move needs more (rule H8); every uploaded link is checked the moment
before a burst. Numbers come from ``references/speed-limits.json``; this module
is pure (no clock unless a ``now`` is passed, no sleep, no network, no spend),
so a run loop calls it each tick and the dispatcher calls the link check once
before a burst.

The sibling ``speed.speed`` module already defines the same three rules; this
module is the standalone run-path surface so the run loop and ``kie_dispatch``
have one small import that does not drag in the whole speed package. It reads
the limits file directly (fallback below) rather than importing a sibling, so
it is green on its own.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

TOOL_NAME = "speed.read"
TOOL_VERSION = "1.0.0"

#: references/speed-limits.json sits three levels above this file
#: (scripts/core/speed/read.py -> skill root -> references/).
SPEED_LIMITS_PATH = Path(__file__).resolve().parents[3] / "references" / "speed-limits.json"

#: Fallback mirrors references/speed-limits.json; a missing or unreadable file
#: falls back to these, never to zero.
_DEFAULT = {
    "clip_length": {"shot_plus_seconds": 1, "camera_move_extra_seconds": 2},
    "upload_freshness_hours": 23,
    "read_floors_seconds": {"picture": 40, "nine_picture": 240},
}

#: Request fields that carry a picture/audio link the paid job will fetch.
_LINK_FIELDS = frozenset({
    "first_frame", "first_frame_url", "first_frame_image_url",
    "last_frame", "last_frame_url", "last_frame_image_url",
    "image_url", "image_urls", "audio_url",
})


def load_limits(path=None):
    """The speed limits dict; the JSON file when readable, else the fallback."""
    p = Path(path or SPEED_LIMITS_PATH)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    merged = dict(_DEFAULT)
    merged.update(data)
    return merged


def clip_seconds_for(shot_seconds, camera_move=False, limits=None):
    """N-92 / rule H8: ask for the shot plus 1 s; a camera move may need more."""
    lim = limits if isinstance(limits, dict) else load_limits()
    cl = lim.get("clip_length") or {}
    try:
        base = float(shot_seconds)
        plus = float(cl.get("shot_plus_seconds") or 1)
        extra = float(cl.get("camera_move_extra_seconds") or 2)
    except (TypeError, ValueError):
        return None
    return base + plus + (extra if camera_move else 0.0)


def read_is_due(expected_finish_at, now, job_kind=None, limits=None):
    """N-92: read a job's status at its expected finish, never before its floor.

    A picture is not read before 40 s and a nine-picture job not before 240 s
    (plan 10B item 4). Unreadable times are not due: the caller keeps its last
    known plan rather than reading blindly.
    """
    lim = limits if isinstance(limits, dict) else load_limits()
    floors = lim.get("read_floors_seconds") or _DEFAULT["read_floors_seconds"]
    try:
        due_at = float(expected_finish_at)
        t = float(now)
    except (TypeError, ValueError):
        return False
    floor = float(floors.get(str(job_kind or "").lower(), 0) or 0)
    return t >= max(due_at, floor)


def link_is_fresh(created_at_epoch, now_epoch, limits=None):
    """N-92 / F-QM-7: an uploaded link younger than 23 hours, else re-upload."""
    lim = limits if isinstance(limits, dict) else load_limits()
    try:
        hours = float(lim.get("upload_freshness_hours") or 23)
        born = float(created_at_epoch)
        now = float(now_epoch)
    except (TypeError, ValueError):
        return False
    return 0 <= now - born <= hours * 3600.0


def _job_links(job):
    """Yield every (field, url) link a job's request asks the provider to fetch."""
    request = job.get("request") if isinstance(job, dict) else None
    inp = request.get("input") if isinstance(request, dict) else None
    if not isinstance(inp, dict):
        return
    for field, value in sorted(inp.items()):
        if field not in _LINK_FIELDS:
            continue
        if isinstance(value, str) and value.strip():
            yield field, value.strip()
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str) and item.strip():
                    yield "%s[%d]" % (field, i), item.strip()


def preburst_link_refusal(jobs, *, now_epoch=None, upload_times=None,
                          limits=None):
    """N-92: check every uploaded link the moment before a burst.

    Refuses (returns a dict with ok=False and a code) when a picture link is
    not on KIE's own upload service (UPLOAD_NOT_KIE) or when a link's recorded
    upload time is older than the freshness window (UPLOAD_LINK_STALE: upload
    it again before paying). Returns None when every link is clean.

    upload_times: {url: created_at_epoch}; a link with no recorded time is
    treated as fresh here (its host check still applies) because the epoch is
    stamped by upload_storyboard_frame, not inferred from a URL.
    """
    lim = limits if isinstance(limits, dict) else load_limits()
    times = upload_times if isinstance(upload_times, dict) else {}
    check_host = _host_checker()
    for job in (jobs or []):
        key = (job or {}).get("logical_key") if isinstance(job, dict) else None
        for field, url in _job_links(job):
            if check_host is not None:
                hit = check_host(url)
                if hit is not None:
                    return {"ok": False, "code": hit.get("code", "UPLOAD_NOT_KIE"),
                            "logical_key": key, "field": field,
                            "detail": hit.get("detail", "non-KIE picture link")}
            born = times.get(url)
            if born is not None and now_epoch is not None \
                    and not link_is_fresh(born, now_epoch, lim):
                return {"ok": False, "code": "UPLOAD_LINK_STALE",
                        "logical_key": key, "field": field,
                        "detail": "this uploaded link is older than %s h; "
                                  "upload the approved still again before the "
                                  "burst" % lim.get("upload_freshness_hours", 23)}
    return None


def read_order(jobs, now, limits=None):
    """N-92: the jobs whose status is due now, soonest expected finish first.

    Pure: no reads are performed, no job is dropped. A job with no expected
    finish is never returned as due (a caller reads it only by its floor).
    """
    lim = limits if isinstance(limits, dict) else load_limits()
    due = []
    for job in (jobs or []):
        if not isinstance(job, dict):
            continue
        if read_is_due(job.get("expected_finish_at"), now,
                       job.get("job_kind") or job.get("kind"), lim):
            due.append(job)
    due.sort(key=lambda j: float(j.get("expected_finish_at") or 0))
    return due


def _host_checker():
    """never_again.check_upload_host when importable, else a local fallback."""
    core = str(Path(__file__).resolve().parents[1])
    if core not in os.sys.path:
        os.sys.path.insert(0, core)
    try:
        import never_again
        return never_again.check_upload_host
    except Exception:  # noqa: BLE001 - a missing guard must not pass a foreign host
        return _local_host_check


def _local_host_check(url):
    from urllib.parse import urlparse
    try:
        host = (urlparse(url or "").hostname or "").lower().rstrip(".")
    except ValueError:
        return {"ok": False, "code": "UPLOAD_NOT_KIE",
                "detail": "unparseable upload link; refuse"}
    # The one host list lives in kie_dispatch/upload_hosts.py (the F14 scanner
    # allows a KIE host literal only inside kie_dispatch/). Fail closed when it
    # will not import: an empty list refuses every link.
    try:
        from kie_dispatch.upload_hosts import is_kie_upload
    except ImportError:
        return {"ok": False, "code": "UPLOAD_NOT_KIE",
                "detail": "upload host guard unavailable; refuse"}
    return None if is_kie_upload(url) else {
        "ok": False, "code": "UPLOAD_NOT_KIE",
        "detail": "upload host %r is not a KIE upload host; refuse the "
                  "non-KIE picture" % host}


if __name__ == "__main__":  # self-check
    assert clip_seconds_for(6) == 7.0
    assert clip_seconds_for(6, camera_move=True) == 9.0
    assert read_is_due(100, 39, "picture") is False     # below the 40 s floor
    assert read_is_due(100, 100, "picture") is True
    assert read_is_due(100, 39, "h3_image_to_video") is False
    assert read_is_due(100, 100, "h3_image_to_video") is True
    assert link_is_fresh(0, 3600) is True
    assert link_is_fresh(0, 23 * 3600 + 1) is False
    # A KIE link is built from the one host list (this module may not carry a
    # KIE host literal outside kie_dispatch/): scheme + host of its first entry.
    _core = str(Path(__file__).resolve().parents[1])
    if _core not in os.sys.path:
        os.sys.path.insert(0, _core)
    from kie_dispatch.upload_hosts import KIE_UPLOAD_HOSTS as _KIE_HOSTS
    assert preburst_link_refusal(
        [{"logical_key": "a", "request": {"input":
          {"first_frame_url": "https://" + _KIE_HOSTS[0] + "/x.png"}}}]) is None
    bad = preburst_link_refusal(
        [{"logical_key": "b", "request": {"input":
          {"image_url": "https://assets.example.com/ghl.png"}}}])
    assert bad and bad["code"] == "UPLOAD_NOT_KIE", bad
    jobs = [{"expected_finish_at": 300, "kind": "h3"},
            {"expected_finish_at": 200, "kind": "h3"}]
    assert [j["expected_finish_at"] for j in read_order(jobs, 400)] == [200, 300]
    print("speed.read self-check OK")

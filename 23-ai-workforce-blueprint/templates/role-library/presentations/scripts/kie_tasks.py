#!/usr/bin/env python3
"""kie_tasks.py — PRES-032 shared resumable KIE task lifecycle.

One lifecycle for every KIE collateral path (kie_generate.py CLI, the VSL hero
render, the sales/checkout hero renders). Previously each path forked its own
rate/submit/poll logic:

  * kie_generate.py kept submitted task IDs in memory only (``task_map``) —
    a restart re-paid every createTask call;
  * it slept one fixed 5-minute wait, then polled tasks SERIALLY — a slow
    first task held every ready download/QC behind it;
  * sales_checkout_builder.py reused any >51200-byte PNG after a failed
    subprocess, unbound to the current prompt revision.

This module fixes all three with a single resumable state machine shared by
every caller (never a forked copy):

  submitted -> running -> provider_complete -> downloaded -> verified
  (plus terminal: failed_*, timeout, superseded)

RATE LOGIC IS SHARED, NOT FORKED. Two layers:

1. Wave spacing (always on): at most 20 createTask submits per rolling
   10 s window — the documented KIE ceiling (``providers.yaml`` ``kie``
   row: 20 submits / 10 s burst, max_inflight 100, daily cap 5000). The
   pre-PRES-032 CLI spaced waves the same way; this lifecycle keeps that
   bound instead of firing N back-to-back POSTs for an N-slide deck.
2. Governor leases (opt-in): pass ``governor="auto"`` (or set
   ``KIE_TASKS_USE_GOVERNOR=1``) and every createTask POST acquires the
   canonical deck-renderer governor (``presentation_job.governor``) with
   ``poll=False`` and every recordInfo GET with ``poll=True``, reporting
   ok/429 through the same seam ``build_deck.py`` uses — fail-soft to
   unthrottled on any governor error. Default is a no-op twin so offline
   tests stay deterministic and never touch global governor state.

Standard library only. No network, no model catalog, no prompt gate imports —
callers inject transport callables so tests run fully offline.
"""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

STATE_VERSION = 1
STATE_FILENAME = "kie_tasks.json"

STATES = (
    "submitted",
    "running",
    "provider_complete",
    "downloaded",
    "verified",
)

TERMINAL_FAILURE_KINDS = (
    "auth_error",        # 401/403 — permanent, never retried
    "rate_exhausted",    # bounded 429 streak exceeded
    "submit_failed",     # non-retryable submit error (bounded: recorded, not looped)
    "provider_failed",   # fail/failed/error/cancelled terminal state
    "no_url",            # provider success with empty resultUrls
    "malformed",         # resultJson unparseable / not a PNG
    "download_failed",   # bounded download retries exhausted
    "verify_failed",     # aspect/dims/OCR gate rejected the bytes
    "timeout",           # deadline passed with no terminal state — NOT resubmitted
    "superseded",        # a newer spec revision replaced this record
)

NON_RETRYABLE_SUBMIT_MARKERS = ("401", "403", "AuthError", "auth")


class FatalAuth(Exception):
    """A 401/403 hit during submit: every remaining submit would fail
    identically, so the run aborts instead of burning the wave budget."""


# ---------------------------------------------------------------------------
# Spec identity — a render may be reused only for its exact spec revision
# ---------------------------------------------------------------------------

def build_spec(*, prompt, mode="t2i", model=None, aspect_ratio="16:9",
               resolution="2K", copy=None, input_urls=None):
    """The full identity of one render request. ``model`` may be None when the
    caller cannot resolve the catalog (both sides then agree on None)."""
    if copy is None:
        copy_hash = None
    elif isinstance(copy, str):
        copy_hash = hashlib.sha256(copy.encode("utf-8")).hexdigest()
    else:
        copy_hash = hashlib.sha256(
            json.dumps(copy, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "prompt_sha256": hashlib.sha256(str(prompt).encode("utf-8")).hexdigest(),
        "mode": str(mode or "t2i").lower(),
        "model": model,
        "aspect_ratio": str(aspect_ratio or "16:9"),
        "resolution": str(resolution or "2K"),
        "copy_sha256": copy_hash,
        "input_urls": list(input_urls or []),
    }


def spec_hash(spec):
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Atomic state store
# ---------------------------------------------------------------------------

def state_path(state_dir):
    return Path(state_dir) / STATE_FILENAME


def _atomic_write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(tmp, str(path))
    except Exception:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_state(state_dir):
    p = state_path(state_dir)
    if not p.is_file():
        return {"version": STATE_VERSION, "tasks": {}}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"version": STATE_VERSION, "tasks": {}}
    if not isinstance(obj, dict) or not isinstance(obj.get("tasks"), dict):
        return {"version": STATE_VERSION, "tasks": {}}
    return obj


def _save_state(state_dir, obj):
    _atomic_write_text(state_path(state_dir),
                       json.dumps(obj, indent=2, sort_keys=True))


def _now_iso():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Governor seam — opt-in via governor="auto" (or KIE_TASKS_USE_GOVERNOR=1).
# Uses the SAME seam build_deck.py uses — acquire(poll=...) / report_ok /
# report_429 — fail-soft to unthrottled on any governor error. Default is a
# no-op twin so offline tests stay deterministic and never touch the global
# governor state (its token/timeout/deadline counters are wall-clock based
# and do not honor injected sleep/clock fakes).
# ---------------------------------------------------------------------------

GOVERNOR_PROVIDER = "kie"
GOVERNOR_ACQUIRE_TIMEOUT_S = 90.0

# Documented KIE ceiling (providers.yaml ``kie`` row): at most 20 createTask
# submits per rolling 10 s window. The pre-PRES-032 CLI already spaced waves
# this way; the lifecycle keeps the bound so an N-slide deck never fires N
# back-to-back POSTs. Pure wave spacing — no governor needed.
SUBMIT_WAVE_CAP = 20
SUBMIT_WAVE_WINDOW_S = 10.0


def _import_governor(scripts_dir=None):
    try:
        from presentation_job import governor as _g  # noqa: PLC0415
        return _g
    except Exception:  # noqa: BLE001 — legacy checkout without governor.py
        pass
    try:
        import importlib.util as _ilu
        here = Path(scripts_dir) if scripts_dir else Path(__file__).resolve().parent
        cand = None
        probe = here
        for _ in range(6):
            if (probe / "presentation_job" / "governor.py").is_file():
                cand = probe / "presentation_job" / "governor.py"
                break
            probe = probe.parent
        if cand is None:
            return None
        spec = _ilu.spec_from_file_location("_kie_tasks_governor", str(cand))
        if not spec or not spec.loader:
            return None
        import sys as _sys
        mod = _ilu.module_from_spec(spec)
        _sys.modules.setdefault("_kie_tasks_governor", mod)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 — still fail-soft
        return None


class _NoopGovernor:
    @staticmethod
    def acquire(provider=None, n=1, timeout_s=None, poll=False):
        return None

    @staticmethod
    def release(lease):
        return None

    @staticmethod
    def report_429(provider):
        return 0.5

    @staticmethod
    def report_ok(provider):
        return None


def governor_for(scripts_dir=None):
    """The canonical kie governor, or a no-op twin when it is absent."""
    return _import_governor(scripts_dir) or _NoopGovernor()


def _resolve_governor(governor, scripts_dir=None):
    """Normalize the ``governor`` run() argument to (module, enabled).

    ``governor=None`` (default) -> no-op twin, disabled. ``"auto"`` ->
    canonical governor, enabled when importable (still fail-soft per call).
    An explicit module object is used as-is and enabled only when
    KIE_TASKS_USE_GOVERNOR=1, so a directly-passed module never surprises
    offline callers."""
    if governor is None:
        return _NoopGovernor(), False
    if governor == "auto":
        mod = governor_for(scripts_dir)
        return mod, not isinstance(mod, _NoopGovernor)
    if isinstance(governor, _NoopGovernor):
        return governor, False
    enabled = bool(os.environ.get("KIE_TASKS_USE_GOVERNOR", "").strip().lower()
                   in ("1", "on", "true", "yes"))
    return governor, enabled


def _gov_acquire(gov, enabled, *, poll):
    if not enabled:
        return None
    try:
        return gov.acquire(GOVERNOR_PROVIDER, n=1,
                           timeout_s=GOVERNOR_ACQUIRE_TIMEOUT_S, poll=poll)
    except Exception:  # noqa: BLE001 — never let the limiter block the render
        return None


def _gov_release(gov, enabled, lease):
    if not enabled or lease is None:
        return
    try:
        gov.release(lease)
    except Exception:  # noqa: BLE001 — release must never raise into the run
        pass


def _gov_report(gov, enabled, kind):
    if not enabled:
        return
    try:
        if kind == "429":
            gov.report_429(GOVERNOR_PROVIDER)
        elif kind == "ok":
            gov.report_ok(GOVERNOR_PROVIDER)
    except Exception:  # noqa: BLE001 — telemetry must never raise
        pass


# ---------------------------------------------------------------------------
# Task records
# ---------------------------------------------------------------------------

def _new_record(*, slide, spec, run_id, artifact_id, task_id, now):
    return {
        "slide": slide,
        "spec_hash": spec_hash(spec),
        "spec": spec,
        "run_id": run_id,
        "artifact_id": artifact_id,
        "task_id": task_id,
        "state": "submitted",
        "error": None,
        "error_kind": None,
        "polls": 0,
        "rate429_streak": 0,
        "download_attempts": 0,
        "result_url": None,
        "sha256": None,
        "width": None,
        "height": None,
        "ocr": None,
        "submitted_at": now,
        "last_poll_at": None,
        "next_poll_at": None,
        "deadline_at": None,
        "updated_at": now,
    }


def _touch(record, **fields):
    record.update(fields)
    record["updated_at"] = _now_iso()
    return record


# ---------------------------------------------------------------------------
# Reuse gate — an existing PNG counts only for its exact spec + QC evidence
# ---------------------------------------------------------------------------

PNG_MAGIC = b"\x89PNG"
REUSE_MIN_BYTES = 51200


def sidecar_path_for(png_path):
    return Path(str(png_path) + ".qc.json")


def render_reuse_ok(png_path, expected_spec_hash, *, min_bytes=REUSE_MIN_BYTES):
    """True only when the PNG exists, is a real non-trivial PNG, AND its
    sidecar records the exact expected spec hash with a verified QC stamp.
    A legacy PNG with no sidecar (or a stale hash) is REJECTED — existence
    alone never counts (PRES-032 acceptance 3)."""
    p = Path(png_path)
    if not p.is_file():
        return False
    try:
        if p.stat().st_size < min_bytes:
            return False
        with open(p, "rb") as f:
            if f.read(4) != PNG_MAGIC:
                return False
    except OSError:
        return False
    sc = sidecar_path_for(p)
    if not sc.is_file():
        return False
    try:
        evidence = json.loads(sc.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    return (evidence.get("spec_hash") == expected_spec_hash
            and evidence.get("verified") is True
            and evidence.get("sha256") == _sha256_file(p))


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sidecar(png_path, *, spec, sha256, width=None, height=None, ocr=None):
    evidence = {
        "spec_hash": spec_hash(spec),
        "sha256": sha256,
        "width": width,
        "height": height,
        "ocr": ocr,
        "verified": True,
        "verified_at": _now_iso(),
    }
    _atomic_write_text(sidecar_path_for(png_path), json.dumps(evidence, indent=2))
    return evidence


# ---------------------------------------------------------------------------
# The resumable run
# ---------------------------------------------------------------------------

def _is_auth_error(exc):
    name = type(exc).__name__
    text = f"{name} {exc}"
    return name == "AuthError" or any(
        marker in text for marker in ("401", "403", "Permanent auth failure"))


def _is_rate_limited(exc):
    return type(exc).__name__ == "RateLimited" or "429" in str(exc)


def run(tasks, *, state_dir, run_id, artifact_id, poll_once,
        download, verify, out_dir=None, create=None, poll_interval_s=10.0,
        deadline_s=900.0, max_429_streak=15, max_download_attempts=3,
        max_submit_429_streak=15, on_event=None, sleep=None, clock=None,
        governor=None, scripts_dir=None, submit_wave_cap=SUBMIT_WAVE_CAP,
        submit_wave_window_s=SUBMIT_WAVE_WINDOW_S):
    """Submit (only missing/revised work) then round-robin poll every task.

    ``tasks``: list of ``{"slide", "spec", "submit"(), "out_path",
    "force_resubmit"=False}`` where ``submit()`` returns a taskId (raising
    AuthError / RateLimited / Exception) and ``poll_once(task_id)`` returns
    ``{"state", "result_url"}`` (raising on terminal provider failure).
    ``download(url, tmp_path)`` writes bytes; ``verify(tmp_path, slide)``
    returns ``{"width","height","ocr"}`` or raises.

    A ready task is downloaded + verified + promoted INSIDE the same poll
    pass that observed its success — never held behind a slower sibling.
    Every outcome is bounded: timeouts and failures are recorded terminal and
    never silently resubmitted.

    Rate sharing: at most ``submit_wave_cap`` submits per rolling
    ``submit_wave_window_s`` window (the KIE 20/10s ceiling) always holds.
    Shared governor leases are opt-in via ``governor="auto"`` (or
    KIE_TASKS_USE_GOVERNOR=1): createTask POSTs acquire with poll=False and
    recordInfo GETs with poll=True through the canonical
    ``presentation_job.governor`` seam build_deck.py uses, fail-soft to
    unthrottled. Default is lease-free so unit tests using injected
    sleep/clock fakes stay deterministic.
    """
    sleep = sleep or time.sleep
    clock = clock or time.time
    started = clock()
    global_deadline = started + deadline_s
    gov, gov_enabled = _resolve_governor(governor, scripts_dir)
    submit_times = []  # clock() stamps of createTask POSTs (wave spacing)

    store = load_state(state_dir)
    records = store.get("tasks", {})

    def emit(kind, slide, **extra):
        if on_event is not None:
            try:
                on_event({"kind": kind, "slide": slide, **extra})
            except Exception:  # noqa: BLE001 — telemetry never breaks the run
                pass

    completed = []
    failed = []
    create_calls = 0
    resumed_without_create = 0

    # ---- Phase A: reconcile state, submit only missing or revised work ----
    pending = {}
    for task in tasks:
        slide = str(task["slide"])
        spec = task["spec"]
        want = spec_hash(spec)
        rec = records.get(slide)
        out_path = Path(task["out_path"] if "out_path" in task
                         else Path(out_dir) / f"{slide}.png")

        if (rec and rec.get("spec_hash") == want and rec.get("task_id")
                and not task.get("force_resubmit")):
            if rec.get("state") == "verified" and render_reuse_ok(out_path, want):
                completed.append({"slide": slide, "file": str(out_path),
                                  "taskId": rec.get("task_id"), "resumed": True})
                resumed_without_create += 1
                emit("reused", slide, task_id=rec.get("task_id"))
                continue
            if rec.get("state") in ("submitted", "running", "provider_complete",
                                    "downloaded"):
                # Crash-after-create resume: poll the KNOWN task id, zero new
                # createTask calls (PRES-032 acceptance 1).
                pending[slide] = (task, rec, out_path)
                resumed_without_create += 1
                _touch(rec, state="running", next_poll_at=_now_iso(),
                       deadline_at=_now_iso())
                emit("resumed", slide, task_id=rec.get("task_id"))
                continue
            # Otherwise (verified-but-unreusable bytes, or an old terminal
            # failure with a matching spec): fall through to exactly one
            # fresh submit — the new record replaces the old one, never a
            # silent carry-over and never an unbounded loop.
        if rec and rec.get("task_id") and rec.get("spec_hash") != want:
            _touch(rec, state="superseded",
                   error="spec revised; old task id retired, submitting fresh")
            emit("superseded", slide, old_task_id=rec.get("task_id"))

        # Fresh (or intentionally revised) submit — persisted ATOMICALLY the
        # moment createTask answers, before any poll/download.
        now_iso = _now_iso()
        submit_streak = 0
        while True:
            try:
                # Wave spacing (always on): hold the KIE 20-submits/10s
                # ceiling across this run's POSTs. Uses the injected clock/
                # sleep so offline tests stay deterministic.
                if submit_wave_cap and submit_wave_cap > 0:
                    now_t = clock()
                    submit_times[:] = [
                        t for t in submit_times
                        if now_t - t < submit_wave_window_s]
                    if len(submit_times) >= submit_wave_cap:
                        sleep(submit_wave_window_s - (now_t - submit_times[0]))
                        now_t = clock()
                        submit_times[:] = [
                            t for t in submit_times
                            if now_t - t < submit_wave_window_s]
                lease = _gov_acquire(gov, gov_enabled, poll=False)
                try:
                    task_id = task["submit"]()
                finally:
                    _gov_release(gov, gov_enabled, lease)
                _gov_report(gov, gov_enabled, "ok")
                submit_times.append(clock())
                break
            except Exception as exc:  # noqa: BLE001 — classified below
                if _is_auth_error(exc):
                    rec_new = _new_record(
                        slide=slide, spec=spec, run_id=run_id,
                        artifact_id=artifact_id, task_id="", now=now_iso)
                    _touch(rec_new, state="failed", error=str(exc),
                           error_kind="auth_error")
                    records[slide] = rec_new
                    failed.append({"slide": slide, "error": str(exc),
                                   "error_kind": "auth_error"})
                    emit("failed", slide, error_kind="auth_error")
                    # Earlier pending records stay resumable (known task ids);
                    # the run aborts now, the caller fixes the key and resumes.
                    _save_state(state_dir, store)
                    raise FatalAuth(
                        f"slide {slide}: permanent auth failure — aborting run, "
                        f"no re-submit ({exc})") from exc
                if _is_rate_limited(exc):
                    submit_streak += 1
                    if submit_streak >= max_submit_429_streak:
                        rec_new = _new_record(
                            slide=slide, spec=spec, run_id=run_id,
                            artifact_id=artifact_id, task_id="", now=now_iso)
                        _touch(rec_new, state="failed", error=str(exc),
                               error_kind="rate_exhausted")
                        records[slide] = rec_new
                        failed.append({"slide": slide, "error": str(exc),
                                       "error_kind": "rate_exhausted"})
                        emit("failed", slide, error_kind="rate_exhausted")
                        task_id = None
                        break
                    emit("submit_429", slide, streak=submit_streak)
                    sleep(poll_interval_s)
                    continue
                rec_new = _new_record(
                    slide=slide, spec=spec, run_id=run_id,
                    artifact_id=artifact_id, task_id="", now=now_iso)
                _touch(rec_new, state="failed", error=str(exc),
                       error_kind="submit_failed")
                records[slide] = rec_new
                failed.append({"slide": slide, "error": str(exc),
                               "error_kind": "submit_failed"})
                emit("failed", slide, error_kind="submit_failed")
                task_id = None
                break
        if task_id is None:
            continue
        create_calls += 1
        rec = _new_record(slide=slide, spec=spec, run_id=run_id,
                          artifact_id=artifact_id, task_id=task_id, now=now_iso)
        _touch(rec, state="submitted", deadline_at=_now_iso())
        records[slide] = rec
        _save_state(state_dir, store)  # atomic persist on create response
        pending[slide] = (task, rec, out_path)
        emit("submitted", slide, task_id=task_id)

    _save_state(state_dir, store)

    # ---- Phase B: round-robin poll; immediate download/QC per ready task ----
    while pending:
        if clock() >= global_deadline:
            for slide, (_, rec, _) in list(pending.items()):
                _touch(rec, state="timeout",
                       error=f"global deadline {deadline_s:.0f}s reached "
                             "with no terminal state — NOT resubmitted",
                       error_kind="timeout")
                failed.append({"slide": slide, "error": rec["error"],
                               "error_kind": "timeout"})
                emit("failed", slide, error_kind="timeout")
            pending.clear()
            break

        done_this_pass = []
        for slide, (task, rec, out_path) in list(pending.items()):
            task_id = rec.get("task_id")
            rec["polls"] = int(rec.get("polls") or 0) + 1
            _touch(rec, state="running", last_poll_at=_now_iso(),
                   next_poll_at=_now_iso())
            try:
                lease = _gov_acquire(gov, gov_enabled, poll=True)
                try:
                    status = poll_once(task_id)
                finally:
                    _gov_release(gov, gov_enabled, lease)
                _gov_report(gov, gov_enabled, "ok")
            except Exception as exc:  # noqa: BLE001
                if _is_auth_error(exc):
                    _gov_report(gov, gov_enabled, "ok")
                    _touch(rec, state="failed", error=str(exc),
                           error_kind="auth_error")
                    failed.append({"slide": slide, "error": str(exc),
                                   "error_kind": "auth_error"})
                    emit("failed", slide, error_kind="auth_error")
                    done_this_pass.append(slide)
                    continue
                if _is_rate_limited(exc):
                    _gov_report(gov, gov_enabled, "429")
                    rec["rate429_streak"] = int(rec.get("rate429_streak") or 0) + 1
                    if rec["rate429_streak"] >= max_429_streak:
                        _touch(rec, state="failed", error=str(exc),
                               error_kind="rate_exhausted")
                        failed.append({"slide": slide, "error": str(exc),
                                       "error_kind": "rate_exhausted"})
                        emit("failed", slide, error_kind="rate_exhausted")
                        done_this_pass.append(slide)
                    else:
                        emit("poll_429", slide,
                             streak=rec["rate429_streak"])
                    continue
                _touch(rec, state="failed", error=str(exc),
                       error_kind="provider_failed")
                failed.append({"slide": slide, "error": str(exc),
                               "error_kind": "provider_failed"})
                emit("failed", slide, error_kind="provider_failed")
                done_this_pass.append(slide)
                continue

            state = str((status or {}).get("state", "")).lower()
            result_url = (status or {}).get("result_url")
            if state != "success":
                emit("in_flight", slide, state=state, polls=rec["polls"])
                continue

            # Provider-complete: download + verify + promote IMMEDIATELY in
            # this pass (a fast task never waits for a slow sibling).
            _touch(rec, state="provider_complete", result_url=result_url)
            if not result_url:
                _touch(rec, state="failed",
                       error="provider success with empty resultUrls",
                       error_kind="no_url")
                failed.append({"slide": slide,
                               "error": "provider success with empty resultUrls",
                               "error_kind": "no_url"})
                emit("failed", slide, error_kind="no_url")
                done_this_pass.append(slide)
                continue

            tmp_path = out_path.parent / (out_path.name + ".part")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            ok_download = False
            last_dl_err = None
            for _ in range(max(1, max_download_attempts)):
                rec["download_attempts"] = int(rec.get("download_attempts") or 0) + 1
                try:
                    download(result_url, tmp_path)
                    ok_download = True
                    break
                except Exception as exc:  # noqa: BLE001 — bounded retry
                    last_dl_err = exc
                    emit("download_retry", slide, error=str(exc))
            if not ok_download:
                _touch(rec, state="failed",
                       error=f"download failed after "
                             f"{rec['download_attempts']} attempt(s): {last_dl_err}",
                       error_kind="download_failed")
                failed.append({"slide": slide, "error": rec["error"],
                               "error_kind": "download_failed"})
                emit("failed", slide, error_kind="download_failed")
                done_this_pass.append(slide)
                continue
            _touch(rec, state="downloaded")

            try:
                with open(tmp_path, "rb") as f:
                    magic = f.read(4)
                if magic != PNG_MAGIC:
                    raise ValueError("not a PNG (bad magic bytes)")
                verdict = verify(tmp_path, slide) or {}
                sha = _sha256_file(tmp_path)
                os.replace(str(tmp_path), str(out_path))
                width = (verdict or {}).get("width")
                height = (verdict or {}).get("height")
                write_sidecar(out_path, spec=rec["spec"], sha256=sha,
                              width=width, height=height,
                              ocr=(verdict or {}).get("ocr"))
            except Exception as exc:  # noqa: BLE001 — a bad image fails one slide
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                msg = str(exc)
                _touch(rec, state="failed", error=msg,
                       error_kind="malformed"
                       if ("magic" in msg or "PNG" in msg)
                       else "verify_failed")
                failed.append({"slide": slide, "error": str(exc),
                               "error_kind": rec["error_kind"]})
                emit("failed", slide, error_kind=rec["error_kind"])
                done_this_pass.append(slide)
                continue

            _touch(rec, state="verified", sha256=sha, width=width,
                   height=height, ocr=(verdict or {}).get("ocr"))
            completed.append({"slide": slide, "file": str(out_path),
                              "taskId": task_id})
            emit("verified", slide, task_id=task_id, file=str(out_path))
            done_this_pass.append(slide)

        for slide in done_this_pass:
            pending.pop(slide, None)
        _save_state(state_dir, store)

        if pending:
            if clock() >= global_deadline:
                continue
            emit("pass_wait", slide="*", pending=sorted(pending))
            sleep(poll_interval_s)

    _save_state(state_dir, store)
    return {"completed": completed, "failed": failed,
            "create_calls": create_calls,
            "resumed_without_create": resumed_without_create}

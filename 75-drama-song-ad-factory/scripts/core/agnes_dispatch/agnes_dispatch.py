#!/usr/bin/env python3
"""agnes_dispatch: the ONE Agnes door (SPEC A4). stdlib only.

Agnes is covered by the client's own subscription, so there is no dollar spend
to gate and no Skill 74 route (LEDGER 13:18). This module is the only code
that calls Agnes. Every gate is IMPORTED from ``kie_dispatch`` (never copied),
every job gets a ``spend_ledger`` row at cost 0 plus an ``agnes_quota`` row,
and the key reaches the request header through ``agnes_access.key_value()``
only - never stdout, a log, a receipt, a ledger or a test output (SPEC A3).

Gate order, before any network call (BUILD-PLAN W1-agnes-core-U1)::

    _find_placeholder -> onscreen_text_refusal -> check_storyboard_approval
    (video) -> _song_pick_refusal -> check_script_approval_gate ->
    card_gate_refusal -> agnes.answer == "yes" (else AGNES_NOT_CHOSEN) ->
    prompt band 5,000-20,000 (video) -> seconds "10" -> key -> agnes_quota.reserve

Video facts (RESEARCH 2-4, trial A 2026-10-13): model ``agnes-video-2.5-flash``,
mode ``keyframe``, ``first_frame``, ``seconds "10"`` fixed, ``size "720P"``,
``aspect_ratio``, no ``n``; AT MOST 2 video jobs in flight per key pool (file
lock in the quota folder); 503 ``video_queue_full`` and 429 back off and
resubmit (never counted as submitted), each at most 6 tries, then the door
fails by name (``AGNES_QUEUE_FULL`` / ``AGNES_RATE_LIMITED``); polls are never
faster than 15 s; 402 = ``AGNES_QUOTA_EXHAUSTED`` and the rest of the UTC day
is recorded exhausted; 401/403 = ``AGNES_KEY_REFUSED``; a failed task =
``AGNES_TASK_FAILED`` with the vendor message; a job whose state is still
unknown after the wait budget is POLLED, never resubmitted.

The envelope, the exit codes and the ledger helpers are ``kie_dispatch``'s own
(imported). The HTTP transport, the clock and the sleeper are injectable, so
no test ever reaches ``apihub.agnes-ai.com``.

The quota contract (S75-049): ``agnes_quota.reserve`` answers with the ledger
row id or raises ``QuotaError``; the door keeps that row id to the end of the
job and closes it with ``settle(row_id, outcome, seconds_used)`` on success
and on failure (a failed clip releases its seconds). The slot folder is
resolved BEFORE any reservation, so a pool that cannot be found refuses the
job with nothing held.

``fcntl`` and ``os.kill`` sit behind two small helpers (S75-049 step 6): on
Windows this Agnes path names ``AGNES_PLATFORM_UNSUPPORTED`` at import and
stops; every other part of the skill imports and runs. Whether Skill 75
supports Windows is decision D-14.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import spend_ledger as L  # noqa: E402  (sibling module in the same core/ tree)

#: The imported seams. Nothing here is re-implemented: the gate chain, the
#: envelope and the ledger settle/unknown helpers all come from the KIE door so
#: there is exactly one copy of each rule.
from kie_dispatch.kie_dispatch import (  # noqa: E402
    EXIT,
    _WAIT_S,
    _find_placeholder,
    _hold_unknown,
    _settle,
    _song_pick_refusal,
    card_gate_refusal,
    check_script_approval_gate,
    check_storyboard_approval,
    envelope,
    onscreen_text_refusal,
)

TOOL_NAME = "agnes_dispatch"
VIDEO_MODEL = "agnes-video-2.5-flash"
IMAGE_MODEL = "agnes-image-2.5-flash"
MODE_KEYFRAME = "keyframe"
VIDEO_SECONDS = "10"
VIDEO_SIZE = "720P"
DEFAULT_ASPECT_RATIO = "9:16"

API_BASE = "https://apihub.agnes-ai.com"
VIDEO_ENDPOINT = API_BASE + "/v1/videos"
IMAGE_ENDPOINT = API_BASE + "/v1/images/generations"

#: Decided prompt band, LEDGER 14:11 (5,000-20,000 characters per video prompt).
PROMPT_MIN_CHARS = 5000
PROMPT_MAX_CHARS = 20000
#: Trial A: 4 s polling from two threads drew "too many video status queries".
POLL_MIN_S = 15
#: Trial A: two accepted together, a third got 503/429 (SPEC A4.4).
MAX_VIDEO_IN_FLIGHT = 2
#: SPEC A4.4: 503 -> 60 s, 120 s, then every 120 s; 429 backs off and resubmits.
BACKOFF_FIRST_S = 60
BACKOFF_EVERY_S = 120
#: S75-049 step 5: at most this many tries per platform refusal, then fail by
#: name instead of waiting forever.
MAX_503_TRIES = 6
MAX_429_TRIES = 6
AGNES_QUEUE_FULL = "AGNES_QUEUE_FULL"
AGNES_RATE_LIMITED = "AGNES_RATE_LIMITED"
#: The name the Agnes path raises on Windows (S75-049 step 6); D-14 decides
#: whether Skill 75 supports Windows at all.
AGNES_PLATFORM_UNSUPPORTED = "AGNES_PLATFORM_UNSUPPORTED"


class PlatformUnsupported(RuntimeError):
    """The Agnes path's own limit, named at import (S75-049 step 6)."""

    code = AGNES_PLATFORM_UNSUPPORTED


def _platform_fcntl():
    """``fcntl`` behind one helper: POSIX file locks are not on Windows.

    On Windows importing this Agnes path raises ``AGNES_PLATFORM_UNSUPPORTED``
    and stops; the rest of the skill is unaffected (amendment 1: the guard
    only names the limit).
    """
    if os.name == "nt":
        raise PlatformUnsupported(
            AGNES_PLATFORM_UNSUPPORTED + ": the Agnes door needs POSIX file "
            "locks (fcntl) and signal-0 liveness checks; this path does not "
            "run on Windows (decision D-14 decides whether it ever will).")
    import fcntl  # noqa: PLC0415 - POSIX only, imported where it is used
    return fcntl


FCNTL = _platform_fcntl()


def _pid_alive(pid):
    """Is ``pid`` alive? ``os.kill(pid, 0)`` behind one helper (S75-049)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:                      # alive, other user
        return True
    return True


# ---------------------------------------------------------------------------
# transport (injectable; the default is the only HTTP code in this module)

def default_transport(method, url, key, body):
    """One HTTP call -> (status:int, payload:dict|bytes). Never logs the key.

    ``DOWNLOAD`` answers with raw bytes; every other method answers with the
    parsed JSON body (or a truncated ``raw`` string when the body is not JSON).
    """
    data = json.dumps(body).encode("utf-8") if isinstance(body, dict) else None
    req = urllib.request.Request(url, data=data, method=str(method or "GET"))
    req.add_header("Authorization", "Bearer %s" % key)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw, status = resp.read(), int(resp.getcode() or 200)
    except urllib.error.HTTPError as exc:            # 4xx/5xx still answer
        try:
            raw = exc.read()
        except Exception:                            # noqa: BLE001
            raw = b""
        status = int(exc.code)
    if str(method or "").upper() == "DOWNLOAD":
        return status, raw
    try:
        return status, json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        return status, {"raw": raw[:400].decode("utf-8", "replace")}


def _transport(transport):
    return transport or default_transport


# ---------------------------------------------------------------------------
# small helpers

def _safe(name):
    """A file-safe form of a logical key / attempt id (never a path)."""
    return re.sub(r"[^A-Za-z0-9._]+", "-", str(name or "job")).strip("-") or "job"


def _ids(run_id, logical_key, attempt_id):
    return {"run_id": run_id, "logical_key": logical_key,
            "attempt_id": attempt_id}


def _env(ids, outcome, reason, next_action, evidence=None, state_version=0):
    """One envelope, in the shape kie_dispatch.envelope builds (imported)."""
    return envelope("agnes_dispatch", outcome, reason, next_action,
                    run_id=ids["run_id"], logical_key=ids["logical_key"],
                    attempt_id=ids["attempt_id"], evidence=evidence or {},
                    state_version=state_version)


def agnes_answer(request):
    """-> ``"yes"`` / ``"no"`` / None: the run's recorded AGNES answer (A2).

    Read wherever the card receipt may carry it; the door never detects a
    subscriber itself. An absent answer is NOT a yes (AGNES_NOT_CHOSEN).
    """
    req = request if isinstance(request, dict) else {}
    run_state = req.get("run_state")
    run_state = run_state if isinstance(run_state, dict) else {}
    holders = (req, run_state)
    blocks = [req.get("agnes"), run_state.get("agnes")]
    for holder in holders:
        receipt = holder.get("card_receipt")
        if isinstance(receipt, dict):
            blocks.append(receipt.get("agnes"))
    for block in blocks:
        if isinstance(block, dict):
            value = block.get("answer")
            if value is None:
                value = block.get("subscriber")
            if value is not None and str(value).strip():
                return str(value).strip().lower()
        elif isinstance(block, str) and block.strip():
            return block.strip().lower()
    return None


def _prompt_verdict(prompt, kind):
    """-> (refusal_envelope|None, verdict) for the band LEDGER 14:11 set.

    Video only (SPEC A4.6): over 20,000 refuses before sending, under 5,000
    FLAGS and continues (the segment facts expand the prompt - never padding).
    """
    if kind != "video":
        return None, "PASS"
    chars = len(prompt or "")
    if chars > PROMPT_MAX_CHARS:
        return ("reject", "AGNES_PROMPT_OVER_BAND",
                "the video prompt is %d characters and the decided band tops "
                "out at %d; cut it before sending - nothing was reserved and "
                "nothing was sent" % (chars, PROMPT_MAX_CHARS)), "REFUSE"
    if chars < PROMPT_MIN_CHARS:
        return None, "FLAG"
    return None, "PASS"


def _backoff_s(retry):
    """SPEC A4.4: 60 s, then 120 s, then every 120 s."""
    return BACKOFF_FIRST_S if retry <= 1 else BACKOFF_EVERY_S


def _vendor_code(payload):
    """The vendor's own error code/message, never invented here."""
    if not isinstance(payload, dict):
        return "", ""
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("code") or ""), str(err.get("message") or "")
    if isinstance(err, str):
        return "", err
    return str(payload.get("code") or ""), str(payload.get("message")
                                                or payload.get("detail") or "")


# ---------------------------------------------------------------------------
# gates (all imported; none re-implemented)

def _gate_request(kind, request):
    """The request as the imported gates read it (model + request_kind)."""
    gate_req = dict(request) if isinstance(request, dict) else {}
    gate_req["model"] = VIDEO_MODEL if kind == "video" else IMAGE_MODEL
    if kind == "video":
        gate_req["request_kind"] = "video"
    return gate_req


def gate_chain(kind, request, prompt, save_dir, run_dir, ids):
    """The imported gate chain in BUILD-PLAN order. -> None when all open."""
    model = VIDEO_MODEL if kind == "video" else IMAGE_MODEL
    gate_req = _gate_request(kind, request)

    # 1. F10: no unfilled placeholder reaches Agnes.
    ph = _find_placeholder(dict(gate_req, prompt=prompt or ""))
    if ph:
        return _env(ids, "rejected", "REQUEST_PLACEHOLDER",
                    "fill the placeholder at %s (%r) and dispatch again; "
                    "nothing was reserved and nothing was sent" % (ph[0], ph[1]),
                    evidence={"placeholder_path": ph[0],
                              "placeholder_token": ph[1], "generated": False})

    # 2. U8: a paid job may not print a string nobody checked.
    onscreen = onscreen_text_refusal(model, gate_req)
    if onscreen is not None:
        return _env(ids, "rejected", "ONSCREEN_TEXT_NOT_CHECKED",
                    str(onscreen) + " Nothing was reserved and nothing was "
                    "sent.", evidence={"generated": False})

    # 3. F6: no animation before the storyboard is approved (video only).
    if kind == "video":
        sb = check_storyboard_approval(None, None, gate_req)
        if sb:
            return _env(ids, "rejected",
                        sb.get("reason_code") or "STORYBOARD_NOT_APPROVED",
                        str(sb.get("detail") or "")
                        + " (directive 14.1: approve the storyboard and pass "
                          "adversarial review first)",
                        evidence={"gate": sb.get("gate"), "generated": False})

    # 4. SONG APPROVAL: nothing moves before the client's pick is recorded.
    song = _song_pick_refusal(model, run_dir)
    if song:
        return _env(ids, "rejected", song.get("reason_code") or "SONG_PICK_MISSING",
                    "%s %s" % (song.get("detail") or "", song.get("next_action") or ""),
                    evidence={"generated": False})

    # 5. SCRIPT APPROVAL: a music job waits for the client's script approval.
    script = check_script_approval_gate(model, gate_req, save_dir)
    if script:
        return _env(ids, "rejected",
                    script.get("reason_code") or "SCRIPT_APPROVAL_MISSING",
                    str(script.get("detail") or script),
                    evidence={"generated": False})

    # 6. F15: no paid job on an unanswered card.
    card = card_gate_refusal(gate_req)
    if card is not None:
        return _env(ids, "waiting", card.get("reason_code") or "CARD_UNANSWERED",
                    card.get("next_action") or "",
                    evidence={"missing_card_fields": card.get("missing") or [],
                              "generated": False})

    # 7. SPEC A2/A4: the door runs only for a run whose answer is "yes".
    if agnes_answer(gate_req) != "yes":
        return _env(ids, "rejected", "AGNES_NOT_CHOSEN",
                    "this run's card record does not carry agnes.answer = "
                    "\"yes\"; the Agnes path is opt-in, so no Agnes job starts. "
                    "Answer the AGNES question on the choice card first.",
                    evidence={"agnes_answer": agnes_answer(gate_req),
                              "generated": False})
    return None


# ---------------------------------------------------------------------------
# key + quota (the two seams other units own; injectable for the tests)

def resolve_key(key=None):
    """The key, through ``agnes_access.key_value()`` and nowhere else (A3).

    ``None`` means "look it up"; an empty answer is a missing key. The value
    is returned in memory only and is never written anywhere by this module.
    """
    if key is not None:
        return key if str(key).strip() else None
    try:
        import agnes_access  # noqa: PLC0415 - lazy: built by unit U3
    except Exception:        # noqa: BLE001 - no access module, no key
        return None
    try:
        value = agnes_access.key_value()
    except Exception:        # noqa: BLE001 - a broken lookup is a missing key
        return None
    return value if value and str(value).strip() else None


def _quota_module(quota):
    """The bound quota module: the injected one, else the skill's own.

    Resolving it here (never inside ``quota_admission``'s local name) is what
    lets the caller carry the row id to the end of the job and close it with
    ``settle`` (S75-049).
    """
    if quota is not None:
        return quota
    try:
        import agnes_quota as module  # noqa: PLC0415 - built by unit U2
    except Exception:                # noqa: BLE001 - no quota module, no quota
        return None
    return module


def quota_admission(quota, kind, units, run_id, logical_key, ids):
    """The one quota gate the plan names: ``agnes_quota.reserve`` (A5.3).

    -> ``(row_id, None)`` when admitted, ``(None, refusal_envelope)`` otherwise.
    ``reserve`` answers with the ledger row id; the caller keeps it for the end
    of the job and closes it with ``settle``. A ``QuotaError`` comes back as
    ITS OWN code and message, never as "could not be called" (S75-049).
    """
    if quota is None:
        return None, _env(ids, "error", "agnes-quota-unavailable",
                          "the Agnes quota tracker (scripts/core/agnes_quota) is "
                          "not importable, so no quota row can be written; "
                          "install the skill's quota module before any Agnes job.",
                          evidence={"generated": False})
    try:
        answer = quota.reserve(kind=kind, units=units, run_id=run_id,
                               logical_key=logical_key)
    except Exception as exc:              # noqa: BLE001 - never guess a signature
        code = str(getattr(exc, "code", "") or "")
        if code:
            outcome = ("waiting" if code == "AGNES_QUOTA_EXHAUSTED"
                       else "rejected")
            return None, _env(ids, outcome, code, str(exc),
                              evidence={"generated": False, "quota_code": code})
        return None, _env(ids, "error", "agnes-quota-unavailable",
                          "agnes_quota.reserve(%s) could not be called (%s: %s); "
                          "nothing was reserved and nothing was sent."
                          % (", ".join(("kind=%r" % kind, "units=%r" % units,
                                        "run_id=%r" % run_id,
                                        "logical_key=%r" % logical_key)),
                             type(exc).__name__, exc),
                          evidence={"generated": False})
    if isinstance(answer, dict):
        if str(answer.get("outcome") or "").lower() == "ok":
            row = answer.get("row_id", answer.get("id"))
            return (int(row) if isinstance(row, int) else None), None
        return None, _env(ids, answer.get("outcome") or "waiting",
                          answer.get("reason_code") or "agnes-quota-unavailable",
                          answer.get("next_action")
                          or "the Agnes quota tracker did not admit this job; a "
                             "run is never split across days (SPEC A5.3).",
                          evidence={"generated": False})
    if isinstance(answer, bool):
        if answer:
            return None, None
        return None, _env(ids, "waiting", "agnes-quota-next-day",
                          "today's Agnes seconds are used up; the run waits "
                          "whole for the next 00:00 UTC reset (SPEC A5.3).",
                          evidence={"generated": False})
    if isinstance(answer, int):           # the shipped contract: the row id
        return int(answer), None
    return None, _env(ids, "error", "agnes-quota-unavailable",
                      "agnes_quota.reserve answered %r; the contract is the "
                      "ledger row id (S75-049), so nothing was reserved and "
                      "nothing was sent." % (answer,),
                      evidence={"generated": False})


def quota_pool_dir(quota, pool_dir=None):
    """The folder the two-slot file lock lives in: the quota folder (A4.4).

    The argument wins; otherwise the folder ``agnes_quota.state_path`` already
    defines. Resolved BEFORE any reservation, so a folder that cannot be found
    refuses the job with nothing held (S75-049 step 3).
    """
    if pool_dir:
        return pool_dir
    module = _quota_module(quota)
    state_path = getattr(module, "state_path", None)
    if not callable(state_path):
        return None
    try:
        resolved = str(state_path())
    except Exception:            # noqa: BLE001 - unresolvable is unresolvable
        return None
    return os.path.dirname(os.path.abspath(resolved)) or None


def _record_vendor_402(quota):
    """A vendor 402 writes the rest of the UTC day as exhausted (S75-049).

    ``agnes_quota.record_vendor_402`` marks the day so every later ``reserve``
    refuses until the 00:00 UTC reset. -> the day, or None.
    """
    record = getattr(quota, "record_vendor_402", None)
    if not callable(record):
        return None
    try:
        return record()
    except Exception:                    # noqa: BLE001 - the 402 still stands
        return None


def _close_quota(quota, row_id, outcome, seconds_used=None):
    """Close this job's quota reservation (S75-049 step 2).

    ``outcome`` is ``"succeeded"``, ``"failed"`` or ``"cancelled"``; a failed
    or cancelled clip releases its seconds. ``None`` leaves the row reserved
    (the job's state is still unknown). Never raises: a row this call cannot
    close stays reserved and the reconciler sees it.
    """
    if row_id is None or outcome is None:
        return None
    settle = getattr(quota, "settle", None)
    if not callable(settle):
        return None
    try:
        return settle(int(row_id), outcome, seconds_used)
    except Exception:                    # noqa: BLE001 - never breaks the door
        return None


# ---------------------------------------------------------------------------
# the 2-in-flight slot pool (file lock, shared across lanes and processes)

def _slot_free(path):
    """True when the slot file is absent or its holder process is gone."""
    if not os.path.exists(path):
        return True
    try:
        with open(path, encoding="utf-8") as fh:
            holder = json.load(fh)
    except (OSError, ValueError):
        return True
    pid = holder.get("pid")
    if not isinstance(pid, int):
        return True                              # unreadable claim: reclaim
    if pid == os.getpid():
        return False                             # held by this very process
    return not _pid_alive(pid)                   # holder died: reclaim


def _claim_slot(pool_dir):
    """-> the claimed slot path, or None when both slots are held."""
    os.makedirs(pool_dir, exist_ok=True)
    lock_path = os.path.join(pool_dir, "agnes-video-slots.lock")
    with open(lock_path, "a+") as lock:
        FCNTL.flock(lock.fileno(), FCNTL.LOCK_EX)
        try:
            for i in range(MAX_VIDEO_IN_FLIGHT):
                path = os.path.join(pool_dir, "agnes-video-slot-%d.json" % i)
                if not _slot_free(path):
                    continue
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump({"pid": os.getpid(), "at": int(time.time())}, fh)
                return path
        finally:
            FCNTL.flock(lock.fileno(), FCNTL.LOCK_UN)
    return None


def _release_slot(path):
    if path:
        try:
            os.unlink(path)
        except OSError:
            pass


@contextmanager
def video_slot(pool_dir, sleep):
    """At most MAX_VIDEO_IN_FLIGHT video jobs in flight per key pool."""
    while True:
        slot = _claim_slot(pool_dir)
        if slot:
            break
        sleep(POLL_MIN_S)
    try:
        yield
    finally:
        _release_slot(slot)


# ---------------------------------------------------------------------------
# receipts, downloads

def prompt_receipt(save_dir, ids, run_id, prompt, digest, verdict):
    """The prompt receipt qc_gate.prompt_compliance_rows matches per row.

    Written once per ledger job (logical_key + attempt_id + prompt sha256 +
    a PASS/FLAG verdict), atomically, into the run's working folder.
    """
    os.makedirs(save_dir, exist_ok=True)
    record = {"run_id": run_id,
              "logical_key": ids["logical_key"],
              "attempt_id": ids["attempt_id"],
              "request_digest": digest,
              "prompt_sha256": hashlib.sha256(
                  (prompt or "").encode("utf-8")).hexdigest(),
              "chars": len(prompt or ""),
              "check": {"verdict": verdict},
              "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime())}
    name = "%s.%s.prompt-receipt.json" % (_safe(ids["logical_key"]),
                                          _safe(ids["attempt_id"]))
    path = os.path.join(save_dir, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return path, record


def _save(save_dir, logical_key, ext, data):
    """Write the downloaded bytes and return (path, sha256)."""
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, _safe(logical_key) + ext)
    with open(path, "wb") as fh:
        fh.write(data)
    return path, hashlib.sha256(data).hexdigest()


def _download(transport, key, url):
    """-> (path-ready bytes, sha256) or (None, error envelope pieces)."""
    status, payload = transport("DOWNLOAD", url, key, None)
    if status != 200 or not isinstance(payload, (bytes, bytearray)) \
            or not payload:
        return None, status, payload
    return bytes(payload), None, None


# ---------------------------------------------------------------------------
# one job through the door

def _settle_job(ledger_db, ids, owner, job_state, final, task_id=""):
    """spend_ledger row at cost 0 - kie_dispatch's own settle (never copied)."""
    return _settle(ledger_db, ids["run_id"], ids["logical_key"],
                   ids["attempt_id"], owner, job_state, final, 0,
                   task_id=task_id, provider_ref="agnes",
                   evidence_ref=task_id or "")


def _vendor_stop(ids, status, payload, ledger_db, owner, job_state, quota=None):
    """402 / 401 / 403 / anything else the vendor names, before any submit.

    A 402 also records the rest of the UTC day exhausted in the quota ledger
    (S75-049 step 4), so no later submit is attempted that day.
    """
    code, message = _vendor_code(payload)
    known = status in (402, 401, 403)
    evidence = {"http_status": status, "vendor_code": code,
                "vendor_message": message, "generated": False,
                "submitted": False}
    if status == 402:
        reason = "AGNES_QUOTA_EXHAUSTED"
        action = ("Agnes answered 402 (Token Plan quota exhausted) before the "
                  "job was created: nothing was submitted. Offer the fallback "
                  "question (SPEC A10) or wait for the next 00:00 UTC reset.")
        day = _record_vendor_402(quota)
        evidence["quota_state"] = str(
            getattr(quota, "EXHAUSTED_UNTIL_RESET", "exhausted_until_reset"))
        evidence["quota_day"] = day
    elif status in (401, 403):
        reason = "AGNES_KEY_REFUSED"
        action = ("Agnes answered %d for this key: the key is missing, expired "
                  "or not allowed. Nothing was submitted - check "
                  "`agnes_access status` (SPEC A3)." % status)
    else:
        reason = code or "agnes-create-failed"
        action = ("Agnes answered HTTP %d%s: nothing was sent blindly; read the "
                  "vendor message and decide (SPEC A4.6 reports a 400 by name)."
                  % (status, " / %s" % code if code else ""))
    settle = _settle_job(ledger_db, ids, owner, job_state, "failed")
    return _env(ids, "rejected" if known else "error", reason, action,
                evidence=evidence,
                state_version=settle.get("state_version", 0))


def _create_video(body, transport, key, sleep):
    """POST until Agnes accepts, then return (video_id, evidence).

    503 and 429 are platform refusals: not created, not charged, never counted
    as submitted. Each backs off with the existing schedule and is retried at
    most MAX_503_TRIES / MAX_429_TRIES times; after that the door fails by
    name (S75-049 step 5) instead of waiting forever.
    """
    tries = {503: 0, 429: 0}
    total_wait = 0.0
    while True:
        status, payload = transport("POST", VIDEO_ENDPOINT, key, body)
        if status == 200:
            video_id = str(payload.get("video_id") or payload.get("task_id") or "")
            if not video_id:
                return None, {"error": "agnes-result-missing",
                              "http_status": status,
                              "retries": sum(tries.values())}
            return video_id, {"retries": sum(tries.values()),
                              "queue_full_wait_s": int(total_wait)}
        if status not in (503, 429):
            return None, {"status": status, "payload": payload}
        tries[status] += 1
        cap = MAX_503_TRIES if status == 503 else MAX_429_TRIES
        if tries[status] > cap:
            code = AGNES_QUEUE_FULL if status == 503 else AGNES_RATE_LIMITED
            return None, {"error": code, "http_status": status,
                          "tries": tries[status]}
        wait = _backoff_s(tries[status])
        total_wait += wait
        sleep(wait)


def _poll(video_id, transport, key, sleep, clock, poll_s, timeout_s):
    """Poll one accepted job -> (payload, polls, verdict).

    Verdicts: 200 (finished), 402 / 401 / 403 (the vendor's own answer),
    ``"failed"`` (the task failed) or ``"unknown"`` (payload None: the job's
    state is still unknown after the wait budget). Never faster than
    POLL_MIN_S per job, and an unreadable answer POLLS, never resubmits.
    """
    url = "%s/agnesapi?video_id=%s&model_name=%s" % (API_BASE, video_id,
                                                     VIDEO_MODEL)
    poll_s = max(POLL_MIN_S, int(poll_s or POLL_MIN_S))
    started = clock()
    last = None
    polls = 0
    while True:
        if last is not None:
            wait = poll_s - (clock() - last)
            if wait > 0:
                sleep(wait)
        status, payload = transport("GET", url, key, None)
        polls += 1
        last = clock()
        if status in (402, 401, 403):
            return payload, polls, status
        if status == 200:
            state = str((payload or {}).get("status") or "").lower()
            if state == "failed":
                return payload, polls, "failed"
            if state in ("completed", "success", "succeeded", "done"):
                return payload, polls, 200
        if clock() - started >= timeout_s:
            return None, polls, "unknown"


# ---------------------------------------------------------------------------
# public API

def dispatch_video(request, *, save_dir, ledger_db, run_id, logical_key,
                   attempt_id, prompt="", seconds=None,
                   aspect_ratio=None, first_frame=None, poll_s=POLL_MIN_S,
                   timeout_s=None, run_dir=None, pool_dir=None, quota=None,
                   key=None, transport=None, sleep=time.sleep,
                   clock=time.monotonic, owner="agnes-dispatch", stage=None):
    """One fixed 10-second Agnes video clip -> one envelope. Never raises."""
    ids = _ids(run_id, logical_key, attempt_id)
    stage = stage or "agnes-video"
    send = dict(request) if isinstance(request, dict) else {}
    run_dir = run_dir or os.path.dirname(os.path.abspath(str(ledger_db)))

    refused = gate_chain("video", request, prompt, save_dir, run_dir, ids)
    if refused is not None:
        return refused

    verdict_refusal, verdict = _prompt_verdict(prompt, "video")
    if verdict_refusal is not None:
        _kind, reason, action = verdict_refusal
        return _env(ids, "rejected", reason, action,
                    evidence={"prompt_chars": len(prompt or ""),
                              "band": [PROMPT_MIN_CHARS, PROMPT_MAX_CHARS],
                              "generated": False})

    # Fixed 10-second clips (A5): the door never sends another value.
    if seconds is None:
        seconds = send.get("seconds", VIDEO_SECONDS)
    if str(seconds) != VIDEO_SECONDS:
        return _env(ids, "rejected", "AGNES_SECONDS_NOT_10",
                    "this door only makes fixed %s-second clips (SPEC A5); "
                    "seconds %r was refused locally - nothing was reserved and "
                    "nothing was sent." % (VIDEO_SECONDS, seconds),
                    evidence={"seconds": seconds, "generated": False})

    secrets_key = resolve_key(key)
    if not secrets_key:
        return _env(ids, "rejected", "AGNES_KEY_MISSING",
                    "the client said Yes but no Agnes key was found; show the "
                    "fallback question (SPEC A3/A10). Nothing was reserved.",
                    evidence={"generated": False})

    quota = _quota_module(quota)
    if quota is None:
        return _env(ids, "error", "agnes-quota-unavailable",
                    "the Agnes quota tracker (scripts/core/agnes_quota) is not "
                    "importable, so no quota row can be written; install the "
                    "skill's quota module before any Agnes job.",
                    evidence={"generated": False})

    # S75-049 step 3: the slot folder is resolved BEFORE any reservation, so a
    # pool that cannot be found refuses the job with nothing held.
    pool = quota_pool_dir(quota, pool_dir)
    if not pool:
        return _env(ids, "error", "agnes-quota-unavailable",
                    "the quota folder that holds the two in-flight video slots "
                    "could not be resolved (agnes_quota.state_path); nothing "
                    "was reserved and nothing was sent.",
                    evidence={"generated": False})

    row_id, refused = quota_admission(quota, "video", 10, run_id, logical_key,
                                      ids)
    if refused is not None:
        return refused

    digest = L.digest_request({"request": send, "prompt": prompt or ""})
    planned = L.plan(ledger_db, run_id, logical_key, attempt_id, digest, 0,
                     stage=stage, owner=owner)
    if planned["outcome"] != "ok":
        _close_quota(quota, row_id, "failed", int(VIDEO_SECONDS))
        return _env(ids, planned["outcome"], planned["reason_code"],
                    planned.get("next_action", ""),
                    state_version=planned.get("state_version", 0))
    reserved = L.reserve(ledger_db, run_id, logical_key, attempt_id, owner=owner)
    if reserved["outcome"] != "ok":
        _close_quota(quota, row_id, "failed", int(VIDEO_SECONDS))
        return _env(ids, reserved["outcome"], reserved["reason_code"],
                    reserved.get("next_action", ""),
                    state_version=reserved.get("state_version", 0))
    job_state = "reserved"
    # S75-049 step 2: the reservation is closed on every terminal path below -
    # success keeps its seconds, a failure or a cancel releases them, and a
    # hold leaves the row reserved because the job's state is still unknown.
    quota_outcome = "failed"
    quota_seconds = int(VIDEO_SECONDS)

    try:
        receipt_path, _record = prompt_receipt(save_dir, ids, run_id, prompt,
                                               digest, verdict)
        frame = first_frame
        if frame is None:
            frame = send.get("first_frame")
            if frame is None and isinstance(send.get("input"), dict):
                frame = send["input"].get("first_frame")
        body = {"model": VIDEO_MODEL, "prompt": prompt or "",
                "mode": MODE_KEYFRAME, "seconds": str(seconds),
                "size": VIDEO_SIZE,
                "aspect_ratio": str(aspect_ratio or send.get("aspect_ratio")
                                    or DEFAULT_ASPECT_RATIO)}
        if frame:
            body["first_frame"] = frame

        with video_slot(pool, sleep):
            send_one = _transport(transport)
            made, info = _create_video(body, send_one, secrets_key, sleep)
            if made is None:
                if "status" in info:
                    return _vendor_stop(ids, info["status"], info.get("payload"),
                                        ledger_db, owner, job_state,
                                        quota=quota)
                if info.get("error") in (AGNES_QUEUE_FULL, AGNES_RATE_LIMITED):
                    settle = _settle_job(ledger_db, ids, owner, job_state,
                                         "failed")
                    return _env(ids, "error", info["error"],
                                "Agnes answered HTTP %s every time: %d tries, "
                                "then the door stopped. Nothing was submitted "
                                "and nothing was charged; retry the segment "
                                "later (SPEC A4.4)."
                                % (info.get("http_status"), info.get("tries", 0)),
                                evidence={"http_status": info.get("http_status"),
                                          "tries": info.get("tries", 0),
                                          "generated": False, "submitted": False},
                                state_version=settle.get("state_version", 0))
                # Accepted, but the answer carried no id: the job is unknown.
                quota_outcome = None      # a reserved row is never guess-settled
                hold = _hold_unknown(ledger_db, run_id, logical_key, attempt_id,
                                     owner, {"stage": "create",
                                             "http_status": info.get("http_status"),
                                             "error": info.get("error")})
                hold["command"] = TOOL_NAME
                return hold
            sub = L.mark_submitted(ledger_db, run_id, logical_key, attempt_id,
                                   made, owner=owner)
            if sub.get("outcome") == "ok":
                job_state = "submitted"

            payload, polls, verdict_code = _poll(
                made, send_one, secrets_key, sleep, clock, poll_s,
                timeout_s or _WAIT_S["video"])
            if verdict_code == "unknown":
                quota_outcome = None      # the job may still exist: no settle
                hold = _hold_unknown(ledger_db, run_id, logical_key, attempt_id,
                                     owner, {"stage": "poll", "task_id": made,
                                             "remote_task_id": made,
                                             "polls": polls,
                                             "wait_timeout_s":
                                                 timeout_s or _WAIT_S["video"],
                                             "timed_out": True})
                hold["command"] = TOOL_NAME
                return hold
            if verdict_code in (402, 401, 403):
                return _vendor_stop(ids, verdict_code, payload, ledger_db,
                                    owner, job_state, quota=quota)
            if verdict_code == "failed":
                code, message = _vendor_code(payload)
                settle = _settle_job(ledger_db, ids, owner, job_state, "failed",
                                     task_id=made)
                return _env(ids, "rejected", "AGNES_TASK_FAILED",
                            "Agnes reported the task failed: %s. Nothing was "
                            "retried - a failed segment goes to the fallback "
                            "question after two failures (SPEC A4.5/A10)."
                            % (message or code or "no vendor message"),
                            evidence={"task_id": made, "vendor_code": code,
                                      "vendor_message": message,
                                      "generated": False},
                            state_version=settle.get("state_version", 0))

            meta = payload.get("metadata") if isinstance(payload.get("metadata"),
                                                         dict) else {}
            url = meta.get("url") or payload.get("url")
            if not url:
                settle = _settle_job(ledger_db, ids, owner, job_state, "failed",
                                     task_id=made)
                return _env(ids, "error", "agnes-result-missing",
                            "Agnes reported %s but no video URL came back; "
                            "nothing was downloaded." % payload.get("status"),
                            evidence={"task_id": made, "generated": False},
                            state_version=settle.get("state_version", 0))
            data, dl_status, _dl_payload = _download(send_one, secrets_key, url)
            if data is None:
                settle = _settle_job(ledger_db, ids, owner, job_state, "failed",
                                     task_id=made)
                return _env(ids, "error", "agnes-result-missing",
                            "the finished clip could not be downloaded (HTTP "
                            "%s); nothing was saved." % dl_status,
                            evidence={"task_id": made, "url": url,
                                      "generated": False},
                            state_version=settle.get("state_version", 0))
            path, sha = _save(save_dir, logical_key, ".mp4", data)
            settle = _settle_job(ledger_db, ids, owner, job_state, "succeeded",
                                 task_id=made)
            if settle["outcome"] not in ("ok", "parked"):
                return _env(ids, settle["outcome"],
                            settle.get("reason_code", "ledger-settle-failed"),
                            settle.get("next_action", ""),
                            evidence={"task_id": made, "saved_paths": [path]},
                            state_version=settle.get("state_version", 0))
            quota_outcome = "succeeded"
            return _env(
                ids, "ok", "AGNES_VIDEO_OK",
                "the clip is saved; record the receipt and let the frame/text "
                "QC read it back.",
                evidence={"generated": True, "model": VIDEO_MODEL,
                          "seconds": VIDEO_SECONDS,
                          "aspect_ratio": body["aspect_ratio"],
                          "task_id": made, "saved_paths": [path], "sha256": sha,
                          "polls": polls, "actual_cost": 0,
                          "warnings": ["PROMPT_UNDER_BAND"] if verdict == "FLAG"
                          else [],
                          "prompt_chars": len(prompt or ""),
                          "prompt_verdict": verdict,
                          "prompt_receipt": receipt_path,
                          "retries": info.get("retries", 0),
                          "queue_full_wait_s": info.get("queue_full_wait_s", 0),
                          "wait_timeout_s": timeout_s or _WAIT_S["video"]},
                state_version=settle.get("state_version", 0))
    except Exception as exc:                      # noqa: BLE001 - never raises
        settle = _settle_job(ledger_db, ids, owner, job_state, "failed")
        return _env(ids, "error", "dispatch-internal-error",
                    "%s: %s" % (type(exc).__name__, str(exc)[:300]),
                    evidence={"generated": False},
                    state_version=settle.get("state_version", 0))
    finally:
        _close_quota(quota, row_id, quota_outcome, quota_seconds)


def dispatch_image(request, *, save_dir, ledger_db, run_id, logical_key,
                   attempt_id, prompt="", aspect_ratio=None, size="2K",
                   images=None, timeout_s=None, run_dir=None, quota=None,
                   key=None, transport=None, sleep=time.sleep,
                   clock=time.monotonic, owner="agnes-dispatch", stage=None):
    """One Agnes Image 2.5 Flash still -> one envelope. Never raises."""
    ids = _ids(run_id, logical_key, attempt_id)
    stage = stage or "agnes-image"
    send = dict(request) if isinstance(request, dict) else {}
    run_dir = run_dir or os.path.dirname(os.path.abspath(str(ledger_db)))

    refused = gate_chain("image", request, prompt, save_dir, run_dir, ids)
    if refused is not None:
        return refused

    secrets_key = resolve_key(key)
    if not secrets_key:
        return _env(ids, "rejected", "AGNES_KEY_MISSING",
                    "the client said Yes but no Agnes key was found; show the "
                    "fallback question (SPEC A3/A10). Nothing was reserved.",
                    evidence={"generated": False})

    quota = _quota_module(quota)
    if quota is None:
        return _env(ids, "error", "agnes-quota-unavailable",
                    "the Agnes quota tracker (scripts/core/agnes_quota) is not "
                    "importable, so no quota row can be written; install the "
                    "skill's quota module before any Agnes job.",
                    evidence={"generated": False})

    row_id, refused = quota_admission(quota, "image", 1, run_id, logical_key,
                                      ids)
    if refused is not None:
        return refused

    digest = L.digest_request({"request": send, "prompt": prompt or ""})
    planned = L.plan(ledger_db, run_id, logical_key, attempt_id, digest, 0,
                     stage=stage, owner=owner)
    if planned["outcome"] != "ok":
        _close_quota(quota, row_id, "failed")
        return _env(ids, planned["outcome"], planned["reason_code"],
                    planned.get("next_action", ""),
                    state_version=planned.get("state_version", 0))
    reserved = L.reserve(ledger_db, run_id, logical_key, attempt_id, owner=owner)
    if reserved["outcome"] != "ok":
        _close_quota(quota, row_id, "failed")
        return _env(ids, reserved["outcome"], reserved["reason_code"],
                    reserved.get("next_action", ""),
                    state_version=reserved.get("state_version", 0))
    job_state = "reserved"
    quota_outcome = "failed"      # every early exit releases the still's unit

    try:
        receipt_path, _record = prompt_receipt(save_dir, ids, run_id, prompt,
                                               digest, "PASS")
        body = {"model": IMAGE_MODEL, "prompt": prompt or "",
                "size": str(size),
                "ratio": str(aspect_ratio or send.get("aspect_ratio")
                             or DEFAULT_ASPECT_RATIO)}
        refs = images if images is not None else send.get("image")
        if refs:
            body["image"] = refs if isinstance(refs, list) else [refs]

        transport = _transport(transport)
        status, payload = transport("POST", IMAGE_ENDPOINT, secrets_key, body)
        if status != 200:
            return _vendor_stop(ids, status, payload, ledger_db, owner,
                                job_state, quota=quota)
        rows = payload.get("data") if isinstance(payload.get("data"), list) else []
        row = rows[0] if rows and isinstance(rows[0], dict) else {}
        b64 = row.get("b64_json")
        if b64:
            try:
                data = base64.b64decode(b64)
            except Exception:                      # noqa: BLE001
                data = None
        else:
            url = row.get("url")
            data = None
            if url:
                data, _st, _pl = _download(transport, secrets_key, url)
        if not data:
            settle = _settle_job(ledger_db, ids, owner, job_state, "failed")
            return _env(ids, "error", "agnes-result-missing",
                        "Agnes answered 200 but carried no image bytes; "
                        "nothing was saved.",
                        evidence={"generated": False},
                        state_version=settle.get("state_version", 0))
        path, sha = _save(save_dir, logical_key, ".png", data)
        settle = _settle_job(ledger_db, ids, owner, job_state, "succeeded")
        if settle["outcome"] not in ("ok", "parked"):
            return _env(ids, settle["outcome"],
                        settle.get("reason_code", "ledger-settle-failed"),
                        settle.get("next_action", ""),
                        evidence={"saved_paths": [path]},
                        state_version=settle.get("state_version", 0))
        quota_outcome = "succeeded"
        return _env(ids, "ok", "AGNES_IMAGE_OK",
                    "the still is saved; use it as the segment's first_frame.",
                    evidence={"generated": True, "model": IMAGE_MODEL,
                              "size": body["size"], "ratio": body["ratio"],
                              "saved_paths": [path], "sha256": sha,
                              "actual_cost": 0, "warnings": [],
                              "prompt_chars": len(prompt or ""),
                              "prompt_verdict": "PASS",
                              "prompt_receipt": receipt_path},
                    state_version=settle.get("state_version", 0))
    except Exception as exc:                      # noqa: BLE001 - never raises
        settle = _settle_job(ledger_db, ids, owner, job_state, "failed")
        return _env(ids, "error", "dispatch-internal-error",
                    "%s: %s" % (type(exc).__name__, str(exc)[:300]),
                    evidence={"generated": False},
                    state_version=settle.get("state_version", 0))
    finally:
        _close_quota(quota, row_id, quota_outcome)


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="agnes_dispatch.py",
        description="The one Agnes door: imported gates -> quota -> create -> "
                    "poll (>= 15 s) -> download at cost 0. Prints one envelope.")
    subs = ap.add_subparsers(dest="cmd", required=True)
    for name, help_text in (("image", "One Agnes Image 2.5 Flash still."),
                            ("video", "One fixed 10-second Agnes video clip.")):
        x = subs.add_parser(name, help=help_text)
        x.add_argument("--request", required=True, help="Request JSON path.")
        x.add_argument("--save-dir", required=True)
        x.add_argument("--ledger", required=True, help="spend_ledger SQLite path.")
        x.add_argument("--run-id", required=True)
        x.add_argument("--logical-key", required=True)
        x.add_argument("--attempt-id", required=True)
        x.add_argument("--prompt", default=None)
        x.add_argument("--prompt-file", default=None)
        x.add_argument("--aspect-ratio", default=None)
        x.add_argument("--run-dir", default=None)
        x.add_argument("--stage", default=None)
        if name == "video":
            x.add_argument("--seconds", default=VIDEO_SECONDS,
                           help="Must be %s: any other value is refused "
                                "locally." % VIDEO_SECONDS)
            x.add_argument("--poll-s", type=int, default=POLL_MIN_S,
                           help="Poll interval in seconds (never under %d)."
                                % POLL_MIN_S)
            x.add_argument("--first-frame", default=None)
            x.add_argument("--pool-dir", default=None,
                           help="The quota folder that holds the 2 in-flight "
                                "video slots.")
    args = ap.parse_args(argv)

    with open(args.request, encoding="utf-8") as fh:
        request = json.load(fh)
    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8") as fh:
            prompt = fh.read()
    else:
        prompt = args.prompt or ""

    common = dict(save_dir=args.save_dir, ledger_db=args.ledger,
                  run_id=args.run_id, logical_key=args.logical_key,
                  attempt_id=args.attempt_id, prompt=prompt,
                  aspect_ratio=args.aspect_ratio, run_dir=args.run_dir,
                  stage=args.stage)
    if args.cmd == "video":
        env = dispatch_video(request, seconds=args.seconds,
                             first_frame=args.first_frame, poll_s=args.poll_s,
                             pool_dir=args.pool_dir, **common)
    else:
        env = dispatch_image(request, **common)
    json.dump(env, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return EXIT_OUTCOME.get(env["outcome"], 1)


if __name__ == "__main__":
    sys.exit(main())

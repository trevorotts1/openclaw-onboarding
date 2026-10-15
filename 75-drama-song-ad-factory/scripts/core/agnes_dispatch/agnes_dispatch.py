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
resubmit (never counted as submitted), 30 minutes of continuous 503 reports
``AGNES_QUEUE_FULL`` loudly and keeps waiting; polls are never faster than
15 s; 402 = ``AGNES_QUOTA_EXHAUSTED``; 401/403 = ``AGNES_KEY_REFUSED``; a
failed task = ``AGNES_TASK_FAILED`` with the vendor message; a job whose state
is still unknown after the wait budget is POLLED, never resubmitted.

The envelope, the exit codes and the ledger helpers are ``kie_dispatch``'s own
(imported). The HTTP transport, the clock and the sleeper are injectable, so
no test ever reaches ``apihub.agnes-ai.com``.

ponytail: ``agnes_quota.reserve`` is called as
``reserve(kind=, units=, run_id=, logical_key=)`` - the row SPEC A5.3 spells
out - because unit W1-agnes-core-U2 ships that module in the SAME release
group and no exact signature is written down. A quota module that cannot be
bound stops the door before any network call (``agnes-quota-unavailable``);
reconcile the one call at batch merge if U2 spells it differently.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
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
#: envelope, the ledger settle/unknown helpers and the loud reporter all come
#: from the KIE door so there is exactly one copy of each rule.
from kie_dispatch.kie_dispatch import (  # noqa: E402
    EXIT,
    _WAIT_S,
    _find_placeholder,
    _hold_unknown,
    _loud,
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
QUEUE_FULL_REPORT_S = 30 * 60


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


def _loud_queue_full(clock, state):
    """Report AGNES_QUEUE_FULL once per continuous 503 run, then keep waiting."""
    if state["reported"]:
        return
    state["reported"] = True
    _loud("warn", "AGNES_QUEUE_FULL",
          "Agnes has answered 503 video_queue_full for %d minutes; the job is "
          "NOT submitted and NOT dropped. The run keeps waiting and resubmitting; "
          "it never switches provider by itself."
          % int((clock() - state["since"]) // 60))


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


def quota_admission(quota, kind, units, run_id, logical_key, ids):
    """The one quota gate the plan names: ``agnes_quota.reserve`` (A5.3).

    -> None when admitted, else the refusal envelope. A missing or unbindable
    quota module stops the door before any network call; a quota answer that
    says "not today" comes back as that answer (never silently ignored).
    """
    if quota is None:
        try:
            import agnes_quota as quota  # noqa: PLC0415 - built by unit U2
        except Exception:                # noqa: BLE001
            return _env(ids, "error", "agnes-quota-unavailable",
                        "the Agnes quota tracker (scripts/core/agnes_quota) is "
                        "not importable, so no quota row can be written; "
                        "install the skill's quota module before any Agnes job.",
                        evidence={"generated": False})
    try:
        answer = quota.reserve(kind=kind, units=units, run_id=run_id,
                               logical_key=logical_key)
    except Exception as exc:              # noqa: BLE001 - never guess a signature
        return _env(ids, "error", "agnes-quota-unavailable",
                    "agnes_quota.reserve(%s) could not be called (%s: %s); "
                    "nothing was reserved and nothing was sent."
                    % (", ".join(("kind=%r" % kind, "units=%r" % units,
                                  "run_id=%r" % run_id,
                                  "logical_key=%r" % logical_key)),
                       type(exc).__name__, exc),
                    evidence={"generated": False})
    if isinstance(answer, dict):
        if str(answer.get("outcome") or "").lower() == "ok":
            return None
        return _env(ids, answer.get("outcome") or "waiting",
                    answer.get("reason_code") or "agnes-quota-unavailable",
                    answer.get("next_action")
                    or "the Agnes quota tracker did not admit this job; a run "
                       "is never split across days (SPEC A5.3).",
                    evidence={"generated": False})
    if answer is False:
        return _env(ids, "waiting", "agnes-quota-next-day",
                    "today's Agnes seconds are used up; the run waits whole for "
                    "the next 00:00 UTC reset (SPEC A5.3).",
                    evidence={"generated": False})
    return None


def quota_pool_dir(quota, pool_dir=None):
    """The folder the two-slot file lock lives in: the quota folder (A4.4)."""
    if pool_dir:
        return pool_dir
    state_path = getattr(quota, "state_path", None)
    if callable(state_path):
        return os.path.dirname(os.path.abspath(str(state_path())))
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
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True                              # holder died: reclaim
    except PermissionError:                      # alive, other user
        return False
    return False                                 # holder alive


def _claim_slot(pool_dir):
    """-> the claimed slot path, or None when both slots are held."""
    os.makedirs(pool_dir, exist_ok=True)
    lock_path = os.path.join(pool_dir, "agnes-video-slots.lock")
    with open(lock_path, "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            for i in range(MAX_VIDEO_IN_FLIGHT):
                path = os.path.join(pool_dir, "agnes-video-slot-%d.json" % i)
                if not _slot_free(path):
                    continue
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump({"pid": os.getpid(), "at": int(time.time())}, fh)
                return path
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
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


def _vendor_stop(ids, status, payload, ledger_db, owner, job_state):
    """402 / 401 / 403 / anything else the vendor names, before any submit."""
    code, message = _vendor_code(payload)
    known = status in (402, 401, 403)
    if status == 402:
        reason = "AGNES_QUOTA_EXHAUSTED"
        action = ("Agnes answered 402 (Token Plan quota exhausted) before the "
                  "job was created: nothing was submitted. Offer the fallback "
                  "question (SPEC A10) or wait for the next 00:00 UTC reset.")
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
                evidence={"http_status": status, "vendor_code": code,
                          "vendor_message": message, "generated": False,
                          "submitted": False},
                state_version=settle.get("state_version", 0))


def _create_video(body, transport, key, sleep, clock):
    """POST until Agnes accepts, then return (video_id, evidence).

    503 and 429 are platform refusals: not created, not charged, never counted
    as submitted - back off and resubmit, forever if need be.
    """
    retry = 0
    queue = {"since": None, "reported": False}
    total_wait = 0.0
    while True:
        status, payload = transport("POST", VIDEO_ENDPOINT, key, body)
        if status == 200:
            video_id = str(payload.get("video_id") or payload.get("task_id") or "")
            if not video_id:
                return None, {"error": "agnes-result-missing",
                              "http_status": status, "retries": retry}
            return video_id, {"retries": retry,
                              "queue_full_wait_s": int(total_wait)}
        if status == 503:
            if queue["since"] is None:
                queue["since"] = clock()
                queue["reported"] = False
            elif clock() - queue["since"] >= QUEUE_FULL_REPORT_S:
                _loud_queue_full(clock, queue)
        else:
            queue["since"] = None
            queue["reported"] = False
        if status not in (503, 429):
            return None, {"status": status, "payload": payload}
        retry += 1
        wait = _backoff_s(retry)
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

    refused = quota_admission(quota, "video", 10, run_id, logical_key, ids)
    if refused is not None:
        return refused
    pool = quota_pool_dir(quota, pool_dir)
    if not pool:
        return _env(ids, "error", "agnes-quota-unavailable",
                    "the quota folder that holds the two in-flight video slots "
                    "could not be resolved (agnes_quota.state_path); nothing "
                    "was sent.", evidence={"generated": False})

    digest = L.digest_request({"request": send, "prompt": prompt or ""})
    planned = L.plan(ledger_db, run_id, logical_key, attempt_id, digest, 0,
                     stage=stage, owner=owner)
    if planned["outcome"] != "ok":
        return _env(ids, planned["outcome"], planned["reason_code"],
                    planned.get("next_action", ""),
                    state_version=planned.get("state_version", 0))
    reserved = L.reserve(ledger_db, run_id, logical_key, attempt_id, owner=owner)
    if reserved["outcome"] != "ok":
        return _env(ids, reserved["outcome"], reserved["reason_code"],
                    reserved.get("next_action", ""),
                    state_version=reserved.get("state_version", 0))
    job_state = "reserved"

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
            made, info = _create_video(body, send_one, secrets_key, sleep,
                                       clock)
            if made is None:
                if "status" in info:
                    return _vendor_stop(ids, info["status"], info.get("payload"),
                                        ledger_db, owner, job_state)
                # Accepted, but the answer carried no id: the job is unknown.
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
                                    owner, job_state)
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

    refused = quota_admission(quota, "image", 1, run_id, logical_key, ids)
    if refused is not None:
        return refused

    digest = L.digest_request({"request": send, "prompt": prompt or ""})
    planned = L.plan(ledger_db, run_id, logical_key, attempt_id, digest, 0,
                     stage=stage, owner=owner)
    if planned["outcome"] != "ok":
        return _env(ids, planned["outcome"], planned["reason_code"],
                    planned.get("next_action", ""),
                    state_version=planned.get("state_version", 0))
    reserved = L.reserve(ledger_db, run_id, logical_key, attempt_id, owner=owner)
    if reserved["outcome"] != "ok":
        return _env(ids, reserved["outcome"], reserved["reason_code"],
                    reserved.get("next_action", ""),
                    state_version=reserved.get("state_version", 0))
    job_state = "reserved"

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
            return _vendor_stop(ids, status, payload, ledger_db, owner, job_state)
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

#!/usr/bin/env python3
"""KIE dispatch: plan section 5.4 stage driver. stdlib only.

Stage order (never reordered, never partially skipped):

  0. placeholder check   request JSON may carry no unfilled placeholder (F10);
                         refused before the ledger or Skill 74 is touched
  1. ledger reserve      ``spend_ledger.plan`` + ``reserve`` (directive 18/24.4)
  2. Skill 74 health     read ``adapter_mode``; only ``active`` continues
  3. Skill 74 preflight  balance must cover price x 1.30
  4. prompt-budget check exit 4 = over max, exit 3 = under floor
  5. submit/wait/save    Skill 74 ``submit`` (task id persisted immediately),
                         ``wait`` with a modality budget (video 1200 / music
                         600 / image 300, or request["timeout"]), outer
                         subprocess W+120 so the inner wait always returns
                         first, then ``save`` files on success
  6. ledger reconcile    succeeded/failed settle; unknown retains reservation

Shadow / off: stop **before the approval card**. The client is told generation
is not switched on. There is no fallback to a private KIE client and no second
transport - Skill 74 is the one KIE path - and a skip is recorded as
*not generated*: the reservation is released at zero cost, never settled as a
generation.

Unknown: a wait timeout (``state`` running plus ``error.code`` timeout), an
unparsable submit/wait answer, or an exception raised while either was in
flight, marks the reservation ``unknown`` and STOPS - with the remote task id
already stored when submit produced one. No retry, no resubmit; reconcile from
provider records or operator evidence first.

F10 (manual 02): a request whose JSON still carries an unfilled placeholder
(``{{``, ``}}``, ``<TODO``, ``<PLACEHOLDER`` - any case - or the bare tokens
``TODO``, ``PLACEHOLDER``, ``KEYFRAME:`` from the Kiesett incident) is refused
at submission with reason ``REQUEST_PLACEHOLDER`` before anything is reserved
or sent. Any failed task is reported within one poll: the wait path fails on
the FIRST poll answer reading ``fail`` (stage evidence row + ``failure_poll``
in the envelope), never after retries or silent skips.

This module carries no HTTP client of its own: the adapter path comes from
``KIE_LIVE_ADAPTER_PATH`` or a search relative to this file, and every call is
one ``subprocess`` of ``kie_live_adapter.py`` (injectable as ``runner`` so the
tests never touch the network or the ledger of a real run).

Exit codes (EXIT): ok 0, error 1, waiting 3, parked 4, rejected 5.
Output: a single JSON object (the envelope) on stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import load_governor as _LG  # noqa: E402  (core/ is on sys.path just above)

import spend_ledger as L  # noqa: E402  (sibling module in the same core/ tree)
import kie_dispatch.model_lock as ML  # noqa: E402  (F14 video-model lock)

#: FU-U7 final-payload prompt caps (plan E.1). Soft import like the F15 seam
#: below: when the module is missing, a video or avatar job is refused
#: fail-closed (there is no prompt cap without the table); image, music and
#: other jobs keep their own gates either way.
try:
    import prompt_limits as _PL  # noqa: E402 (sibling module in the same core/ tree)
except Exception:  # noqa: BLE001 - the gate below stays fail-closed without it
    _PL = None

#: F15 card gate (Critical, owner order 2026-10-08): dispatch refuses ANY
#: paid job for a run whose state lacks all four choice-card answers. The
#: import is soft -- the module must keep working when style_defaults is not
#: importable -- and the local fail-closed copy below keeps the gate shut.
try:
    from style_defaults import card_gate as _CG  # noqa: E402
except Exception:  # noqa: BLE001 - gate stays fail-closed without the module
    _CG = None

#: The exposed gate for W-F-U16: whoever holds the run state calls
#: ``card_gate_refusal(run_state)`` and refuses any paid job when it returns
#: non-None. Run state is read from ``request["card_receipt"]`` (the
#: recorded receipt block from style_defaults.card_gate.answered_stamped)
#: or from ``request["run_state"]["card_receipt"]``.
def _onscreen_strings(request):
    """U8: every on-screen string a paid job would print, from the request.

    The shot plan carries them as ``on_screen_text`` (a string, a list of
    strings, or ``[{"text": ...}]``) on the request itself or under the
    request's ``shot`` block. Other fields the plan already gates for
    spelling (lyrics, end card) are read the same way so one receipt covers
    the whole job.
    """
    req = request if isinstance(request, dict) else {}
    out = []

    def collect(value):
        if isinstance(value, str):
            if value.strip():
                out.append(value)
        elif isinstance(value, dict):
            collect(value.get("text"))
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    for source in (req, req.get("shot"), req.get("shot_plan"),
                   req.get("generation")):
        if isinstance(source, dict):
            collect(source.get("on_screen_text"))
    return out


def onscreen_text_refusal(model, request):
    """U8 ONSCREEN_TEXT_NOT_CHECKED: a paid job may not print a string
    nobody checked. Fail-closed -- an unchecked keyframe/video whose request
    carries on-screen text is refused before the ledger, and a request with
    no on-screen text at all passes untouched.

    The receipt is the exact strings that were checked, in
    ``onscreen_text_checked`` (string or list, request-level or beside the
    shot). A string on the job that is not in the receipt refuses -- a
    receipt for a different string is not a receipt for this one.
    """
    texts = _onscreen_strings(request)
    if not texts:
        return None
    req = request if isinstance(request, dict) else {}
    checked = []
    for source in (req, req.get("shot"), req.get("shot_plan")):
        if isinstance(source, dict):
            value = source.get("onscreen_text_checked")
            if isinstance(value, str):
                checked.append(value)
            elif isinstance(value, (list, tuple)):
                checked.extend(x.get("text", "") if isinstance(x, dict) else str(x)
                               for x in value)
    checked = {c.strip() for c in checked if isinstance(c, str) and c.strip()}
    missing = [t for t in texts if t.strip() not in checked]
    if not missing:
        return None
    return ("on-screen text %r is not in the checked receipt for this job "
            "(%s); spell-check it and record it in "
            "`onscreen_text_checked` before any paid job -- exact copy is "
            "never left to the model"
            % (missing[0], "no strings checked" if not checked
               else "%d checked" % len(checked)))


def _loud(kind, code, detail):
    """Named, visible failure/warning that reaches the receipt (loud_failure.py)."""
    import os as _os, sys as _sys
    d = _os.path.dirname(_os.path.abspath(__file__))
    while d != _os.path.dirname(d) and not _os.path.exists(_os.path.join(d, "loud_failure.py")):
        d = _os.path.dirname(d)
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import loud_failure
    getattr(loud_failure, kind)(code, detail)


def card_gate_refusal(request):
    """-> None when the card is answered and stamped, else the refusal dict
    with reason CARD_UNANSWERED. Fail-closed: no receipt is unanswered."""
    req = request if isinstance(request, dict) else {}
    record = req.get("card_receipt")
    if not isinstance(record, dict):
        rs = req.get("run_state")
        record = rs.get("card_receipt") if isinstance(rs, dict) else None
        if not isinstance(record, dict) and isinstance(rs, dict):
            inner = rs.get("card") or rs.get("choice_card")
            record = inner if isinstance(inner, dict) else None
    if _CG is not None:
        ok, refusal = _CG.gate_run_state(record)
        return refusal if not ok else None
    if not isinstance(record, dict):
        return {"reason_code": "CARD_UNANSWERED",
                "missing": ["video_style", "audio_style", "length",
                            "video_model"],
                "next_action": "Show the choice card and record all four "
                               "answers (video style, audio style, length, "
                               "video model), with who and when, before any "
                               "paid job."}
    missing = [f for f in ("video_style", "audio_style", "length", "video_model")
               if record.get(f) is None
               or (isinstance(record.get(f), str) and not record.get(f).strip())]
    if missing:
        return {"reason_code": "CARD_UNANSWERED", "missing": missing,
                "next_action": "Show the choice card and record all four "
                               "answers before any paid job."}
    return None

try:  # F4: no automatic Suno sound effects (audio_c3/sfx_off)
    import audio_c3.sfx_off as _sfx_off  # noqa: E402
except ImportError:  # pragma: no cover - flat script path
    from audio_c3 import sfx_off as _sfx_off  # type: ignore # noqa: E402

try:  # F2: whole-track retakes only in F1 mode (audio_c3/soundtrack)
    import audio_c3.soundtrack as _SND  # noqa: E402
except ImportError:  # pragma: no cover - flat script path
    from audio_c3 import soundtrack as _SND  # type: ignore # noqa: E402

PARTIAL_SUNO_JOB = "PARTIAL_SUNO_JOB"

def suno_job_refusal(request):
    """F2 intake seam: [] when a Suno job may go, else the refusal reasons.

    Fires only for a run in F1 mode -- the request itself carries the F1
    soundtrack stamp (``generate_soundtrack_request`` output) or carries
    ``request["run_receipt"]``, the run's receipt with the recorded stamp
    (``record_soundtrack`` output). A run with no stamp is untouched (F2
    constrains F1-mode runs only).

    The job row is ``request["suno_job"]`` when given; without it, the
    F1-stamped request IS the one full-track generation. A partial shape
    (a per-line slice, a spoken-take patch, a second bed) refuses
    ``PARTIAL_SUNO_JOB`` here, before any ledger row or Skill 74 call.
    """
    req = request if isinstance(request, dict) else {}
    receipt = req.get("run_receipt")
    if not isinstance(receipt, dict):
        rs = req.get("run_state")
        receipt = rs.get("run_receipt") if isinstance(rs, dict) else None
    if not isinstance(receipt, dict):
        receipt = req
    block = receipt.get("soundtrack") \
        if isinstance(receipt, dict) else None
    if not isinstance(block, dict) or block.get("mode") != _SND.TRACK_MODE:
        return []
    job = req.get("suno_job")
    if not isinstance(job, dict):
        job = {"kind": _SND.FULL_TRACK_KIND}
    return _SND.refuse_partial_suno_job(receipt, job)


def lipsync_picture_refusal(model, request):
    """LPG001/LPG002 hard block: a lip-sync job (kling ai-avatar, infinitalk)
    needs a PASS or ACCEPT_WITH_FLAG picture-gate receipt for the exact bytes
    (sha256) of request["lipsync_image_path"], AND request["input"]["image_url"] must be the
    upload of those exact bytes (picture_gate.upload_measured).
    -> None (not lip-sync, or all bound) else the refusal text. Fail-closed:
    a missing path, receipt, binding, or an unimportable gate is a refusal."""
    if not any(c in str(model or "").lower() for c in ("ai-avatar", "infinitalk")):
        return None
    req = request if isinstance(request, dict) else {}
    try:
        lg = str(Path(__file__).resolve().parents[1] / "lip_sync" / "lip_gate")
        if lg not in sys.path:
            sys.path.insert(0, lg)
        import picture_gate as _PG
        _PG.require_receipt(req.get("lipsync_image_path"),
                            req.get("lipsync_receipt_dir"))
        inp = req.get("input") if isinstance(req.get("input"), dict) else {}
        _PG.require_upload_bound(req["lipsync_image_path"], inp.get("image_url"),
                                 req.get("lipsync_receipt_dir"))
    except Exception as exc:                                # noqa: BLE001
        return str(exc) or type(exc).__name__
    return None

def book_shot_refusal(model, request):
    """FU-U10: a BOOK video job needs the contract, or it does not dispatch.

    A request whose shot kind is "book" on a video model must carry
    (a) the approved book PLAN hash -- a book job that carries NO
    ``book_plan_sha256`` is REFUSED with BOOK_PLAN_NOT_APPROVED (U11's
    producer writes the field, so the requirement is ACTIVE: the dormant
    period U10 shipped for ended when the producer landed); and
    (b) a start frame MADE FROM the cover file -- request["book_start_frame"]
    (or request["start_frame"]) naming a path whose sha256 equals the cover
    sha256 carried by the same request (request["book_cover_sha256"]) or
    computed from request["book_cover_path"].

    -> None when not a book job or the contract holds, else the refusal dict
    with reason BOOK_PLAN_NOT_APPROVED (plan side) or
    BOOK_SHOT_NOT_CONTRACTED (start frame side). Fail-closed: an unreadable
    start frame, a missing cover reference, a missing or mismatched plan
    hash, or a start frame made from other bytes refuses. Never touches the
    LIPSYNC_* seams: a lip-sync model is not a book shot entry point.
    """
    req = request if isinstance(request, dict) else {}
    kind = req.get("shot_kind") or req.get("kind")
    if not isinstance(kind, str) or kind.strip().lower() != "book":
        return None
    if not (req.get("request_kind") == "video" or _is_menu_video(model)
            or _modality(model) == "video"):
        return None
    # (a) plan hash: U11's producer writes book_plan_sha256, so the
    # requirement is ACTIVE. Missing, empty, or mismatched -> refused.
    approved = req.get("approved_book_plan_sha256")
    carried = req.get("book_plan_sha256")
    if not carried:
        return {"reason_code": "BOOK_PLAN_NOT_APPROVED",
                "detail": "no book_plan_sha256: the book plan has not been "
                          "approved for this job",
                "next_action": "Hash the approved book plan "
                               "(book_shot.plan_sha256) and carry it as "
                               "book_plan_sha256 alongside "
                               "approved_book_plan_sha256, then resubmit."}
    if not approved or str(carried) != str(approved):
        return {"reason_code": "BOOK_PLAN_NOT_APPROVED",
                "detail": "book_plan_sha256 does not match the approved "
                          "plan (carried %s, approved %s)"
                          % (_short(carried), _short(approved)),
                "next_action": "The plan changed after approval. Re-approve "
                               "the current plan and carry its hash, then "
                               "resubmit."}
    missing = []
    # (b) the start frame must be made from the cover file, byte for byte.
    frame = req.get("book_start_frame") or req.get("start_frame")
    cover_sha = req.get("book_cover_sha256")
    if not cover_sha and req.get("book_cover_path"):
        cover_sha = _sha256_path(req.get("book_cover_path"))
    if not frame:
        missing.append("no start frame made from the cover file "
                       "(book_start_frame)")
    elif not cover_sha:
        missing.append("no cover sha256 to bind the start frame to "
                       "(book_cover_sha256 or book_cover_path)")
    else:
        fsha = _sha256_path(frame)
        if fsha is None:
            missing.append("start frame unreadable: %s" % frame)
        elif fsha != cover_sha:
            # A frame made from the cover may be composited (the cover sitting
            # in a scene), so an exact byte match is not required -- but a
            # frame that shares nothing with the cover is an invented cover.
            if not _frame_shows_cover(frame, req.get("book_cover_path")):
                missing.append("start frame is not made from the cover file")
    if missing:
        return {"reason_code": "BOOK_SHOT_NOT_CONTRACTED",
                "detail": "; ".join(missing),
                "next_action": "Build the book shot from the contract: a "
                               "start frame made from the client's cover file "
                               "(book_shot.prompt_blocks + image_model_blocks), "
                               "then resubmit."}
    return None

def _short(value, n=12):
    """A hash prefix for a refusal message. Never the secret, never a file."""
    s = str(value or "")
    return (s[:n] + "...") if len(s) > n else (s or "none")

def _sha256_path(path):
    if not path or not os.path.isfile(str(path)):
        return None
    h = hashlib.sha256()
    try:
        with open(str(path), "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()

def _frame_shows_cover(frame_path, cover_path):
    """True when the frame contains the cover file (ORB inliers).

    Composites are expected, so this is the measured test -- never a naming
    convention. A missing cv2 or an unreadable file is False (fail closed)."""
    if not cover_path:
        return False
    try:
        import book_shot as _BS
        import cv2 as _cv2
        img = _cv2.imread(str(frame_path))
        if img is None:
            return False
        m = _BS.detect_cover(img, str(cover_path))
        return bool(m["cover_hits"])
    except Exception:                                       # noqa: BLE001
        return False

TOOL_NAME = "kie_dispatch"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.kie-dispatch/envelope/v1"
EXIT = {"ok": 0, "error": 1, "waiting": 3, "parked": 4, "rejected": 5}


#: U15b: the models whose prompts come from the template assembler
#: (prompt_templates.assemble_h3). An H3 video job must carry the prompt
#: receipt for the exact prompt bytes; the keyframe image path is unchanged.
TEMPLATED_VIDEO_PREFIXES = ("minimax-h3/",)


def prompt_templated_refusal(model, request, prompt):
    """U15b: -> None when the H3 prompt carries a matching PASS receipt.

    Refuses ``PROMPT_NOT_TEMPLATED`` when the prompt's sha256 has no receipt
    (a hand-written or stale prompt may never be paid for) or when the
    matching receipt's check says REFUSE or TRIM (the assembler's own band
    verdict: REFUSE is over the hard max, TRIM is over the target max).
    The receipt is the dict ``prompt_templates.receipt()`` wrote, carried as
    ``request["prompt_receipt"]`` (or ``prompt_receipts`` list, or inside
    ``request["run_state"]``). Non-H3 models return None: kling/ai-avatar
    jobs are unchanged by this unit.
    """
    if not str(model or "").startswith(TEMPLATED_VIDEO_PREFIXES):
        return None
    req = request if isinstance(request, dict) else {}
    rec = req.get("prompt_receipt")
    if rec is None:
        rec = req.get("prompt_receipts")
    if rec is None:
        rs = req.get("run_state")
        if isinstance(rs, dict):
            rec = rs.get("prompt_receipt") or rs.get("prompt_receipts")
    if rec is None:
        return {"reason_code": "PROMPT_NOT_TEMPLATED",
                "detail": "the %s prompt carries no prompt receipt; assemble "
                          "it through prompt_templates.assemble_h3 and pass "
                          "receipt() as request['prompt_receipt']" % model}
    recs = rec if isinstance(rec, list) else [rec]
    text = prompt if isinstance(prompt, str) else ""
    import hashlib as _hashlib
    sha = _hashlib.sha256(text.encode("utf-8")).hexdigest()
    match = None
    for r in recs:
        if isinstance(r, dict) and r.get("prompt_sha256") == sha:
            match = r
            break
    if match is None:
        return {"reason_code": "PROMPT_NOT_TEMPLATED",
                "detail": "no receipt matches the sha256 of the prompt being "
                          "paid for (%s...); the prompt changed after it was "
                          "assembled - re-assemble and re-receipt" % sha[:12]}
    verdict = (match.get("check") or {}).get("verdict") \
        if isinstance(match.get("check"), dict) else match.get("verdict")
    if isinstance(verdict, str) and verdict.upper() in ("REFUSE", "TRIM"):
        return {"reason_code": "PROMPT_NOT_TEMPLATED",
                "detail": "the matching receipt's verdict is %s: %s"
                          % (verdict.upper(),
                             "; ".join((match.get("check") or {}).get(
                                 "reasons", []) or []))}
    return None


def final_payload_cap_refusal(model, request, is_video):
    """U15b/U6: measure the FINAL payload just before spend. -> None or dict.

    Runs U6's ``prompt_limits.check_request`` (the 67 catalog caps for video,
    the 68 catalog for Suno) over the payload as it stands at submit time,
    after every mutation. An over-cap field refuses with the field, chars,
    cap, source and status; nothing is ever truncated.
    """
    if not is_video:
        return None
    try:
        import prompt_limits as _PL
    except ImportError as exc:                          # pragma: no cover
        return {"reason_code": "PROMPT_LIMIT_UNAVAILABLE",
                "detail": "prompt_limits.py is not importable (%s); a paid "
                          "job never runs without the final-payload cap "
                          "check" % exc}
    # U15a's catalog resolver knows the 999 tree keeps the 67/68 catalogs
    # under installer-registration/helpers/ (U6's own ancestor walk cannot
    # see them from there). Hand prompt_limits the path; the reading itself
    # still happens in prompt_limits.
    catalog = None
    try:
        if str(model).startswith(("suno", "ai-music-api")):
            catalog = _templates_catalog("audio")
        else:
            catalog = _templates_catalog("video")
    except Exception:                                   # noqa: BLE001
        catalog = None
    try:
        _PL.check_request(model, request, models_path=catalog)
    except _PL.PromptLimitError as exc:
        return {"reason_code": exc.code if exc.code else "PROMPT_OVER_CAP",
                "detail": str(exc)}
    except Exception as exc:                            # noqa: BLE001
        return {"reason_code": "PROMPT_LIMIT_UNAVAILABLE",
                "detail": "the final-payload cap check could not run "
                          "(%s: %s); a paid job never runs unchecked"
                          % (type(exc).__name__, exc)}
    return None


def _templates_catalog(kind):
    """The 67/68 catalog path via U15a's resolver, or None to let U6 walk."""
    try:
        core = str(Path(__file__).resolve().parents[1])
        if core not in sys.path:
            sys.path.insert(0, core)
        import prompt_templates as _PT
        return _PT.catalog_path(kind)
    except Exception:                                   # noqa: BLE001
        return None

ADAPTER_SKILL = "74-kie-live-adapter"
ADAPTER_SCRIPT = "kie_live_adapter.py"
ADAPTER_RELS = (
    ("74-kie-live-adapter", "scripts", "kie_live_adapter.py"),
    ("onboarding", "74-kie-live-adapter", "scripts", "kie_live_adapter.py"),
    ("skills", "74-kie-live-adapter", "scripts", "kie_live_adapter.py"),
    (".claude", "skills", "74-kie-live-adapter", "scripts", "kie_live_adapter.py"),
    ("installer-registration", "helpers", "74-kie-live-adapter",
     "scripts", "kie_live_adapter.py"),
    ("999-setup", "installer-registration", "helpers", "74-kie-live-adapter",
     "scripts", "kie_live_adapter.py"),
)

# Adapter states that mean "generation produced output".
RUN_OK = "success"
RUN_SKIPPED = "skipped"
RUN_FAILED = "fail"
RUN_PENDING = ("queued", "running")

# Outer wait budget per modality (manual C2). request["timeout"] wins.
_WAIT_S = {"video": 1200, "music": 600, "image": 300}
_VIDEO_CUES = ("video", "veo", "kling", "seedance", "hailuo", "pixverse",
               "runway", "wan2", "i2v", "t2v")
_MUSIC_CUES = ("music", "suno", "audio", "tts", "speech", "elevenlabs",
               "voice")

# F10 placeholder tokens. Case-insensitive: {{ }} and the bracketed TODO /
# PLACEHOLDER markers a template leaves behind. Case-sensitive: the bare
# Kiesett-incident tokens, so ordinary prose ("todo list", "Keyframe: 12")
# never trips them. The bare "<" is deliberately excluded - real prompts
# contain "<" as prose every day.
_PLACEHOLDER_CI = ("{{", "}}", "<todo", "<placeholder")
_PLACEHOLDER_CS = ("TODO", "PLACEHOLDER", "KEYFRAME:")


def _walk_str_leaves(obj, path=""):
    """Every string leaf of request JSON with its JSON path."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_str_leaves(v, "%s/%s" % (path, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_str_leaves(v, "%s[%d]" % (path, i))
    elif isinstance(obj, str):
        yield path, obj


def _find_placeholder(request):
    """First unfilled placeholder in a request payload -> (path, token), or
    None. Scans the whole request (model/timeout included), not just input -
    a template can hide in any field."""
    for path, value in _walk_str_leaves(request):
        low = value.lower()
        for tok in _PLACEHOLDER_CI:
            if tok in low:
                return path, tok
        for tok in _PLACEHOLDER_CS:
            if tok in value:
                return path, tok
    return None


def _registry_entry(model, adapter=None):
    """Skill 74 registry row for model, or None. Path is relative to adapter."""
    path = adapter or resolve_adapter()
    if not path:
        return None
    reg = (Path(path).resolve().parent.parent / "references"
           / "kie-model-registry.json")
    try:
        data = json.loads(Path(reg).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _loud("warn", "KIE_REGISTRY_UNREADABLE", "%s: %r" % (reg, exc))
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return None
    for m in models:
        if isinstance(m, dict) and m.get("id") == model:
            return m
    return None


def _modality(model, adapter=None):
    entry = _registry_entry(model, adapter)
    if entry:
        ttypes = " ".join(entry.get("taskType") or []).lower()
        if "video" in ttypes:
            return "video"
        if "music" in ttypes or "audio" in ttypes or "speech" in ttypes:
            return "music"
        if "image" in ttypes:
            return "image"
    mid = (model or "").lower()
    if any(c in mid for c in _VIDEO_CUES):
        return "video"
    if any(c in mid for c in _MUSIC_CUES):
        return "music"
    return "image"


def _wait_budget_s(request, model, adapter=None):
    """W for Skill 74 wait; the outer subprocess runs with W+120."""
    t = request.get("timeout") if isinstance(request, dict) else None
    if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0:
        return int(t)
    return _WAIT_S[_modality(model, adapter)]


def _record_stage_evidence(db, run_id, logical_key, attempt_id, stage,
                           status="fail", task_id="", error=None,
                           adapter_state=""):
    """Dispatch evidence for the resolver (events kind='dispatch'). Best-effort."""
    payload = {"stage": stage, "adapter_state": adapter_state,
               "error": error or {}, "task_id": task_id or None,
               "remote_task_id": task_id or None}
    try:
        conn = sqlite3.connect(db, timeout=10)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO events("
                "run_id,logical_key,attempt_id,kind,provider_event_id,"
                "provider_seq,status,payload_json,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, logical_key, attempt_id, "dispatch", stage, 0, status,
                 json.dumps(payload, sort_keys=True), L._now_iso()))
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:                               # noqa: BLE001
        _loud("fail", "DISPATCH_EVENT_NOT_RECORDED",
              "ledger dispatch row for %s not written: %r" % (logical_key, exc))


def submit_all_ready(jobs, max_concurrency=None, *, ledger=None,
                     runner=None, timeout=300):
    """Part F F5: submit EVERY ready job in ONE pass. Returns a receipt dict.

    A job is 'ready' when its model, request, estimated_cost and every input
    path are present. All ready jobs go out together - the owner rule: 17
    clips at once; no 'test batch first' unless the owner orders one. The
    stage order callers follow stays reference images -> keyframes -> clips;
    this is the single clips pass at the end of that order.

    jobs: each a dict with a unique logical_key, the exact model id (this
          module never picks one), a request dict, an estimated_cost and
          input paths under 'inputs' (a path or a list; every one must
          exist on disk). submit_all_ready never invents a missing field -
          an incomplete job is excluded and NAMED in the receipt.
    ledger: optional spend_ledger DB passed through to each dispatch() so
          every submit lands reserve/reconcile rows; run/logical/attempt
          ids come from the job itself (job['request_ids'] or defaults).
    max_concurrency: None means submit all ready jobs at once. A positive
          int NAMES the provider cap: at most that many run in flight, and
          the receipt says the cap bound the pass (max_at_once and
          capped_by). 0, negative or a non-int is refused in the receipt,
          never treated as unlimited.

    Receipt (always a plain dict, never an exception):
      {submitted, excluded: [{logical_key, reason}], max_at_once,
       capped_by, envelopes, errors, submission_errors}
    All keys always present, on every path, so callers can read one shape.
    """
    if max_concurrency is not None and (
            not isinstance(max_concurrency, int)
            or isinstance(max_concurrency, bool) or max_concurrency <= 0):
        return _receipt(outcome="rejected",
                        reason="max_concurrency must be a positive int or "
                               "None (got %r)" % (max_concurrency,))
    ready, excluded = [], []
    jobs = jobs if isinstance(jobs, list) else ([] if jobs is None
                                                else list(jobs))
    for j in jobs:
        key = (j or {}).get("logical_key") if isinstance(j, dict) else None
        key = key or "unnamed-job"
        try:
            reason = _not_ready_reason(j)
        except Exception as e:                              # noqa: BLE001
            reason = "bad-input-spec: %s" % str(e)[:160]
        if reason:
            excluded.append({"logical_key": key, "reason": reason})
        else:
            ready.append(j)

    cap = None
    if max_concurrency is not None and len(ready) > max_concurrency:
        cap = max_concurrency

    envelopes, errors, sub_errs = [], [], []
    ok_count = 0
    if ready:
        pool = ThreadPoolExecutor(max_workers=(cap or len(ready)))
        try:
            futs = {pool.submit(_one_submit, j, ledger, timeout): j
                    for j in ready}
            for fu in as_completed(futs):
                env, j = fu.result()
                envelopes.append(env)
                if env["outcome"] == "ok":
                    ok_count += 1
                else:
                    sub_errs.append(
                        {"logical_key": j["logical_key"],
                         "outcome": env["outcome"],
                         "reason_code": env["reason_code"]})
        finally:
            pool.shutdown(wait=True)

    # The pass takes every ready job in one go; when a cap binds, the receipt
    # names it and max_at_once records the cap, not the ready count.
    return _receipt(excluded=excluded, submitted=ok_count,
                    max_at_once=(cap if cap is not None else len(ready)),
                    capped_by=cap,
                    envelopes=envelopes, errors=errors,
                    submission_errors=sub_errs)


def _receipt(excluded=None, submitted=0, max_at_once=0, capped_by=None,
             envelopes=None, errors=None, submission_errors=None,
             outcome=None, reason=None):
    """One receipt shape everywhere; optional rejected marker."""
    rec = {"submitted": submitted, "excluded": list(excluded or []),
           "max_at_once": max_at_once, "capped_by": capped_by,
           "envelopes": list(envelopes or []), "errors": list(errors or []),
           "submission_errors": list(submission_errors or [])}
    if outcome:
        rec["outcome"] = outcome
        rec["reason"] = reason
    return rec


def _not_ready_reason(job):
    """'' when ready to submit; the exclusion reason otherwise."""
    if not isinstance(job, dict):
        return "not-a-dict"
    if not job.get("model"):
        return "no-model"
    if not job.get("request"):
        return "no-request"
    cost = job.get("estimated_cost")
    if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
        return "no-estimated-cost"
    spec = job.get("inputs")
    paths = ([spec] if isinstance(spec, (str, os.PathLike))
             else list(spec if spec is not None else []))
    for p in paths:
        if not isinstance(p, (str, os.PathLike)) or not str(p).strip():
            return "bad-input-spec"
        if not os.path.exists(p):
            return "inputs-missing: %s" % str(p)
    return ""


def _one_submit(job, ledger, timeout):
    """One ready job through dispatch(); returns (envelope, job).

    Wraps job['request_ids'] (run_id/logical_key/attempt_id - defaults
    'run-all-ready'/'batch-n'/'att-n') so a caller controls its ledger rows.
    No exception ever escapes; an exception becomes an 'error' envelope.
    """
    rid = (job.get("request_ids") or {}) if isinstance(job, dict) else {}
    ids = {
        "run_id": rid.get("run_id") or "run-all-ready",
        "logical_key": rid.get("logical_key") or job.get("logical_key")
        or "batch-job",
        "attempt_id": rid.get("attempt_id") or ""
    }
    if not ids["attempt_id"]:
        # One attempt per job inside the pass; logical key keeps rows apart.
        ids["attempt_id"] = "att-" + ids["logical_key"]
    try:
        env = dispatch(
            model=job["model"], request=job["request"],
            save_dir=job.get("save_dir")
            or job.get("request", {}).get("save_dir") or tempfile.gettempdir(),
            ledger_db=ledger or ":memory:",
            run_id=ids["run_id"], logical_key=ids["logical_key"],
            attempt_id=ids["attempt_id"],
            estimated_cost=job["estimated_cost"],
            prompt=job.get("prompt", ""),
            units=job.get("units", 1), stage=job.get("stage", "kie"),
            owner=job.get("owner", "kie-dispatch"),
            adapter_path=job.get("adapter_path"), runner=job.get("runner"),
            timeout=timeout,
            state_store=job.get("state_store"))   # F14: run-state lock store
        return env, job
    except Exception as e:                                  # noqa: BLE001
        return envelope("dispatch", "error", "SUBMIT_ALL_READY-EXCEPTION",
                        str(e)[:300]), job


class DispatchError(Exception):
    """Carries a machine reason code; never escapes dispatch()."""


def envelope(command, outcome, reason_code, next_action="", run_id="",
             logical_key="", attempt_id="", evidence=None, state_version=0):
    return {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION, "command": command,
            "run_id": run_id, "logical_key": logical_key,
            "attempt_id": attempt_id, "outcome": outcome,
            "reason_code": reason_code, "next_action": next_action,
            "evidence": evidence or {}, "state_version": state_version}


def resolve_adapter(explicit=None):
    """Path to Skill 74's entrypoint, or None. Never a hard-coded user path."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    env = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    if env:
        return env if os.path.isfile(env) else None
    start = Path(__file__).resolve()
    for parent in (start,) + tuple(start.parents):
        for rel in ADAPTER_RELS:
            cand = parent.joinpath(*rel)
            if cand.is_file():
                return str(cand)
    return None


# Skill 74 commands that create a NEW KIE generation task (image, video, lip-sync,
# music, extend all go through submit). Everything else is a read.
GENERATION_CMDS = frozenset({"submit", "create", "generate", "extend"})


def make_runner(timeout=300):
    """Real Skill 74 subprocess. The tests never use this."""
    def _run(argv):
        def once():
            r = subprocess.run([sys.executable] + list(argv),
                               capture_output=True, text=True, timeout=timeout,
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            return r.returncode, r.stdout
        # Load governor: only NEW generation requests (submit) draw from the
        # 20-per-10-s bucket; health/preflight/wait/save use the gentle poll
        # limiter. A 429 means the job did not run: back off and resubmit.
        cmd = str(argv[1]) if len(argv) > 1 else ""
        return _LG.kie_request(once, label=" ".join(str(a) for a in argv[1:4]),
                               generation=cmd in GENERATION_CMDS)
    return _run


def _call(runner, adapter, args):
    """One Skill 74 command -> (rc, parsed_or_None, raw). No exception escapes."""
    try:
        rc, out = runner([adapter] + list(args))
    except _LG.KieRateLimitError as e:
        # 429 retries exhausted: the job did NOT run. Say so, never "unknown".
        return -1, {"state": "rate_limited",
                    "error": {"code": "KIE_RATE_LIMITED", "message": str(e)}}, str(e)
    except Exception as e:                                  # noqa: BLE001
        return -1, None, "runner-error: %s" % e
    rc = rc if isinstance(rc, int) else -1
    if isinstance(out, (dict, list)):                       # already parsed
        try:
            return rc, out, json.dumps(out, sort_keys=True, default=str)
        except Exception:                                   # noqa: BLE001
            return rc, None, ""
    try:
        return rc, json.loads(out), out
    except Exception:                                       # noqa: BLE001
        return rc, None, out if isinstance(out, str) else str(out)


def _settle(db, run_id, logical_key, attempt_id, owner, job_state, final,
            actual_cost, task_id="", provider_ref="", evidence_ref=""):
    """reserved/submitted -> succeeded|failed -> reconciled. Zero on not-generated."""
    st = job_state
    if st == "reserved":
        if task_id:
            sub = L.mark_submitted(db, run_id, logical_key, attempt_id,
                                   task_id, owner=owner)
            if sub["outcome"] == "ok":
                st = "submitted"
        if st == "reserved":
            can = L.cancel(db, run_id, logical_key, attempt_id, owner=owner)
            if can["outcome"] == "ok":
                st = "unknown"
    if st in ("submitted", "unknown"):
        term = L.mark_terminal(db, run_id, logical_key, attempt_id, final,
                               owner=owner)
        if term["outcome"] != "ok":
            return term
    return L.reconcile(db, run_id, logical_key, attempt_id, final, actual_cost,
                       provider_ref=provider_ref, evidence_ref=evidence_ref,
                       owner=owner)


def _hold_unknown(db, run_id, logical_key, attempt_id, owner, extra):
    """Retain the reservation and stop. Never retry from here."""
    unk = L.mark_unknown(db, run_id, logical_key, attempt_id, owner=owner)
    ev = dict(extra)
    ev.update({"retries": 0, "resubmitted": False, "disposition": "unknown"})
    return envelope(
        "dispatch", "waiting", "unknown-outcome-no-retry",
        "reconcile via provider records or operator evidence before any retry; "
        "do not auto-resubmit",
        run_id=run_id, logical_key=logical_key, attempt_id=attempt_id,
        evidence=ev, state_version=unk.get("state_version", 0))


def _is_menu_video(model, _registry_probe=None):
    """True when model is a price-menu video family member (F14 lock scope)."""
    for pat in ML.ALLOWED_VIDEO_MODELS:
        if ML.matches_family(model, pat):
            return True
    return False

def _video_scope(model):
    """True for the locked lip-sync avatar and the price-menu video families.
    Those are the jobs whose prompt caps this skill owns; every other model
    (off-menu ids, image/music jobs) keeps its own gate and defers to F14 and
    the Skill 74 adapter budget."""
    return ML.is_locked_lipsync(model) or _is_menu_video(model)

def prompt_cap_rows(model, request):
    """FU-U7: (refusal-or-None, measured rows) for the FINAL video/avatar payload.

    The plan E.1 caps: MiniMax H3 7,000; Hailuo 2,000; Kling 2.5 Turbo /
    2.6 i2v 2,500; Kling 3.0 / 3.0 Omni 3,072; the locked avatar 2,500
    (UNVERIFIED, from the skill-75 override table). check_request measures
    EVERY text field of the payload the dispatcher is about to send, so the
    check lands after every upstream mutation (kling_prompt, the ending
    append, a retake rewrite) and before any spend.

    Fail closed on a known cap: a field over it refuses (PROMPT_OVER_CAP)
    naming field, characters, cap, source and status - nothing reserved,
    nothing sent, and the text is NEVER truncated. With no prompt-cap table
    at all a paid video/avatar job refuses (PROMPT_LIMIT_UNAVAILABLE). A
    model neither the catalogs nor the overrides hold is left to F14 (every
    off-menu model refuses MODEL_NOT_ON_MENU there) and to the Skill 74
    adapter's own prompt-budget step - no cap is invented for it here.
    """
    if _PL is None:
        if not _video_scope(model):
            return None, []
        return ({"reason_code": "PROMPT_LIMIT_UNAVAILABLE",
                 "next_action": ("the skill-75 prompt-cap table (prompt_limits) "
                                 "is not importable, so no paid video/avatar "
                                 "job can be measured; reinstall Skill 75 and "
                                 "dispatch again. Nothing was reserved and "
                                 "nothing was sent."),
                 "evidence": {"generated": False, "field": "prompt",
                              "chars": None, "cap": None,
                              "cap_source": "skill-75 prompt_limits.py "
                                            "(not importable)",
                              "cap_status": "UNAVAILABLE"}}, [])
    try:
        return None, _PL.check_request(model, request)["measured"]
    except _PL.PromptLimitError as e:
        if e.code == "PROMPT_LIMIT_NO_CATALOG":
            return None, []       # no cap to enforce; F14 + adapter budget stand
        return ({"reason_code": e.code,
                 "next_action": ("%s. Rewrite the final payload to fit cap %s "
                                 "(%s) and dispatch again; nothing was reserved "
                                 "and nothing was sent, and the prompt was NOT "
                                 "truncated." % (e, e.cap, e.status)),
                 "evidence": {"generated": False, "field": e.field,
                              "chars": e.chars, "cap": e.cap,
                              "cap_source": e.source,
                              "cap_status": e.status}}, [])

# ---- F6: no animation before storyboard approval -------------------------
try:
    import storyboard_director as _SD                     # sibling core/ pkg
except ImportError as _e:
    if "storyboard_director" not in str(_e):
        raise
    _SD = None


def check_storyboard_approval(shots, review, request=None):
    """Part F F6 shot-generation entry check. Returns the refusal dict or
    None.

    A video job (the animation stage) for a shot plan must come through
    directive 14.1's gate: every shot storyboard_approved AND the
    adversarial review passed. Callers pass the run's bound shot list and
    the recorded review result via request["storyboard"] =
    {"shots": [...], "review": {...}}; anything missing or malformed
    refuses (fail-closed: a run with no approval record cannot animate).
    Non-video jobs (music/image) are untouched.
    """
    if _SD is None:
        return {"reason_code": "storyboard-gate-unavailable",
                "detail": "storyboard_director not importable; refusing "
                          "fail-closed"}
    req = request if isinstance(request, dict) else {}
    if req.get("request_kind") != "video" and _modality(req.get("model")) != "video":
        return None
    sb = (request or {}).get("storyboard")
    if not isinstance(sb, dict) or not isinstance(sb.get("shots"), list) \
            or not sb["shots"]:
        return {"reason_code": "STORYBOARD_NOT_APPROVED",
                "detail": "no storyboard record in the request; a run cannot "
                          "animate before storyboard approval is recorded"}
    gate = _SD.video_spend_allowed(sb["shots"], sb.get("review"))
    if not gate.get("allowed"):
        return {"reason_code": "STORYBOARD_NOT_APPROVED",
                "detail": gate.get("reason_code", "storyboard-gate-closed"),
                "gate": gate}
    return None


def _song_pick_refusal(model, run_dir):
    """SONG APPROVAL seam (song_choices.refusal); a broken gate refuses."""
    try:
        from song_choices import song_choices as _sc
        return _sc.dispatch_refusal(_modality(model) == "music", run_dir)
    except Exception as exc:  # noqa: BLE001 - a gate that cannot run never opens
        return {"reason_code": "SONG_GATE_BROKEN", "detail": "song gate failed: %r." % (exc,),
                "next_action": "Fix the song-choices gate before any paid job."}


def dispatch(*, model, request, save_dir, ledger_db, run_id, logical_key,
             attempt_id, estimated_cost, prompt="", units=1, stage="kie",
             owner="kie-dispatch", adapter_path=None, runner=None,
             timeout=300, state_store=None, video_job=None):
    """Run the plan 5.4 pipeline once. Returns one envelope; never raises.

    F14 video-model lock: video jobs (video_job=True, or a video model on
    price-menu.md) must match the model locked at the choice card
    (state_store + run_id). No lock recorded -> refused fail-closed
    (VIDEO_MODEL_LOCK_MISSING); a different model -> VIDEO_MODEL_MISMATCH.
    Every model, video or not, must be on price-menu.md (MODEL_NOT_ON_MENU).

    FU-U7 prompt caps (plan E.1): before ANY other gate, the FINAL payload is
    measured against the per-model caps (H3 7,000; Hailuo 2,000; Kling 2.5
    Turbo 2,500; Kling 3.0 / 3.0 Omni 3,072; the locked avatar 2,500). An
    over-cap field refuses PROMPT_OVER_CAP with field, chars, cap, source and
    status; nothing is reserved, nothing is sent, nothing is truncated.
    """
    # ---- 0. FU-U7 prompt caps (final payload, before any spend) -----------
    # The request IS the final payload here: every upstream mutation
    # (kling_prompt, the clean-ending append, a retake rewrite) has already
    # happened before dispatch is called. Nothing below may spend until the
    # caps pass; the refusal and the ok receipt both carry the cap and status.
    cap_refusal, prompt_caps = prompt_cap_rows(model, request)
    if cap_refusal is not None:
        return envelope("dispatch", "rejected", cap_refusal["reason_code"],
                        cap_refusal["next_action"],
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id,
                        evidence=cap_refusal["evidence"])

    # ---- 0. F14 model lock (before any ledger row) ------------------------
    # Scope: VIDEO jobs only. A video model must be on price-menu.md
    # (seedance-1.5-pro included) and must equal the card-locked choice.
    # The locked lip-sync model (kling/ai-avatar-standard) is not a menu video
    # model: it skips the video lock and is held to the picture gate below.
    is_video = (not ML.is_locked_lipsync(model)
                and (bool(video_job) or _is_menu_video(model)
                     or _modality(model) == "video"))
    locked = None
    if is_video:
        try:
            ML.assert_allowed(model)
        except ML.ModelLockError as e:
            return envelope("dispatch", "rejected", e.reason,
                            "the allowed video models are exactly the models "
                            "on price-menu.md (seedance-1.5-pro included). "
                            "Take the refusal to the owner.",
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id)
        locked = ML.read_locked_model(state_store, run_id)
        if not locked:
            return envelope(
                "dispatch", "rejected", "VIDEO_MODEL_LOCK_MISSING",
                "no video model is locked for this run; show and answer the "
                "choice card first (default MiniMax H3 768P) - never "
                "dispatch an un-locked video job",
                run_id=run_id, logical_key=logical_key,
                attempt_id=attempt_id)
        from choice_card.video_models import video_models as _VM  # client's pick -> resolution/tier
        request = _VM.apply_locked_choice(request, locked)
        if not ML.matches_family(model, locked):
            return envelope(
                "dispatch", "rejected", "VIDEO_MODEL_MISMATCH",
                "the card locked %s for this run; %s differs. Ask the owner "
                "to re-lock at the choice card, never substitute here."
                % (locked, model),
                run_id=run_id, logical_key=logical_key,
                attempt_id=attempt_id,
                evidence={"locked_model": locked, "requested_model": model})
    pic = lipsync_picture_refusal(model, request)
    if pic is not None:                     # LPG001: no paid lip-sync on an ungated picture
        return envelope("dispatch", "rejected", "LIPSYNC_PICTURE_NOT_GATED",
                        pic + " Nothing was reserved and nothing was sent.",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id, evidence={"generated": False})
    onscreen = onscreen_text_refusal(model, request)
    if onscreen is not None:                # U8: no paid job prints an unchecked string
        return envelope("dispatch", "rejected", "ONSCREEN_TEXT_NOT_CHECKED",
                        onscreen + " Nothing was reserved and nothing was sent.",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id, evidence={"generated": False})
    book = book_shot_refusal(model, request)      # FU-U10: book job contract
    if book is not None:
        return envelope("dispatch", "rejected", book["reason_code"],
                        book["detail"] + " " + book["next_action"],
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id, evidence={"generated": False})
    if not model:
        return envelope("dispatch", "rejected", "MODEL_REQUIRED",
                        "name the model id; this module never picks one",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    refusal = card_gate_refusal(request)
    if refusal is not None:                 # F15: no paid job on an unanswered card
        return envelope("dispatch", "waiting", refusal["reason_code"],
                        refusal.get("next_action", ""),
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id,
                        evidence={"missing_card_fields": refusal["missing"],
                                  "generated": False})

    # F4 gate: a Suno sound-effects job is refused unless the request itself
    # carries the run's explicit manual order (``sound_effects: [...]``).
    # The catalog's suno-sounds surface is NEVER auto-queued: default runs
    # make zero sound-effect jobs (manual Part F F4).
    request_orders_sfx = _sfx_off.sfx_ordered(request)
    if _sfx_off._is_sfx_job({"model": model, "route": model,
                             "endpoint": (request or {}).get("endpoint", "")}) \
            and not request_orders_sfx:
        return envelope("dispatch", "rejected", "SFX_JOB_NOT_ORDERED",
                        "no automatic Suno sound effects: a default run "
                        "makes zero sound-effect jobs; carry "
                        "`sound_effects: [...]` in the run config for an "
                        "explicit manual order (manual Part F F4)",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    if not isinstance(estimated_cost, int) or estimated_cost < 0:
        return envelope("dispatch", "rejected", "UNKNOWN_PRICE",
                        "record an estimated cost before dispatch",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    # F2 intake seam: a run in F1 mode takes whole tracks only. A partial
    # slice/patch job refuses PARTIAL_SUNO_JOB here, before the ledger row
    # and before any Skill 74 call. Runs with no F1 soundtrack stamp are
    # untouched.
    f2_reasons = suno_job_refusal(request)
    if f2_reasons:
        return envelope("dispatch", "rejected", PARTIAL_SUNO_JOB,
                        "whole-track retakes only in F1 mode: one full-track "
                        "generation or ONE whole-track retake of a failed "
                        "take; a slice/patch job is refused (manual Part F "
                        "F2). Nothing was reserved and nothing was sent.",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id,
                        evidence={"intake_errors": f2_reasons,
                                  "generated": False})
    # F6: a run cannot animate before storyboard approval is recorded.
    sb_refusal = check_storyboard_approval(None, None, request)
    if sb_refusal:
        return envelope("dispatch", "rejected", sb_refusal["reason_code"],
                        sb_refusal.get("detail", "")
                        + " (directive 14.1: approve the storyboard and pass "
                          "adversarial review first)",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id,
                        evidence={"gate": sb_refusal.get("gate"),
                                  "generated": False})
    # SONG APPROVAL: no picture, video or lip-sync job before the client's song
    # pick is recorded (only the song stage itself may run). Fail closed.
    song_hold = _song_pick_refusal(model, os.path.dirname(os.path.abspath(str(ledger_db))))
    if song_hold:
        return envelope("dispatch", "rejected", song_hold["reason_code"],
                        song_hold["detail"] + " " + song_hold["next_action"],
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id, evidence={"generated": False})
    # U15b: an H3 prompt must be assembled and receipted (PROMPT_NOT_TEMPLATED)
    # and the FINAL payload must be re-measured against its cap, both BEFORE
    # any ledger row or paid call. Nothing reserved, nothing sent.
    tpl_refusal = prompt_templated_refusal(model, request, prompt)
    if tpl_refusal:
        return envelope("dispatch", "rejected", tpl_refusal["reason_code"],
                        tpl_refusal["detail"]
                        + " Nothing was reserved and nothing was sent.",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id,
                        evidence={"generated": False, "gate": "U15b"})
    cap_refusal = final_payload_cap_refusal(model, request, is_video)
    if cap_refusal:
        return envelope("dispatch", "rejected", cap_refusal["reason_code"],
                        cap_refusal["detail"]
                        + " Nothing was reserved and nothing was sent.",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id,
                        evidence={"generated": False,
                                  "gate": "final-payload-cap"})
    # ---- 0. placeholder check (F10) ---------------------------------------
    # Before the ledger: a refused request reserves nothing and calls nothing.
    ph = _find_placeholder(request)
    if ph:
        return envelope(
            "dispatch", "rejected", "REQUEST_PLACEHOLDER",
            "fill the placeholder at %s (%r) in the request file and dispatch "
            "again; nothing was reserved and nothing was sent" % (ph[0], ph[1]),
            run_id=run_id, logical_key=logical_key, attempt_id=attempt_id,
            evidence={"placeholder_path": ph[0], "placeholder_token": ph[1],
                      "generated": False})
    run = runner or make_runner(timeout)

    # ---- 1. ledger reserve -------------------------------------------------
    digest = L.digest_request(request)
    pl = L.plan(ledger_db, run_id, logical_key, attempt_id, digest,
                estimated_cost, stage=stage, owner=owner)
    if pl["outcome"] != "ok":
        return envelope("dispatch", pl["outcome"], pl["reason_code"],
                        pl.get("next_action", ""), run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id,
                        state_version=pl.get("state_version", 0))
    rs = L.reserve(ledger_db, run_id, logical_key, attempt_id, owner=owner)
    if rs["outcome"] != "ok":
        return envelope("dispatch", rs["outcome"], rs["reason_code"],
                        rs.get("next_action", ""), run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id,
                        state_version=rs.get("state_version", 0))
    job_state = "reserved"

    def stop(outcome, reason, next_action, evidence, final="failed", cost=0,
             settle=True):
        """Leave the ledger clean and return the envelope."""
        if settle:
            rec = _settle(ledger_db, run_id, logical_key, attempt_id, owner,
                          job_state, final, cost)
            if rec["outcome"] not in ("ok", "parked"):
                outcome, reason = "error", "ledger-settle-failed"
                next_action = rec.get("next_action", "") or next_action
                evidence = dict(evidence or {}, ledger=rec)
        return envelope("dispatch", outcome, reason, next_action,
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id, evidence=evidence or {},
                        state_version=rec.get("state_version", 0)
                        if settle else rs.get("state_version", 0))

    # ---- 2. Skill 74 health (mode) ----------------------------------------
    adapter = resolve_adapter(adapter_path)
    if not adapter:
        return stop("error", "adapter-not-found",
                    "install Skill 74 (%s); there is no private KIE client"
                    % ADAPTER_SKILL,
                    {"skill": ADAPTER_SKILL, "generated": False})
    h_rc, h, h_raw = _call(run, adapter, ["health", "--json"])
    if h is None:
        return stop("error", "adapter-health-unreadable",
                    "Skill 74 health did not answer JSON; do not dispatch",
                    {"rc": h_rc, "raw": (h_raw or "")[-400:],
                     "generated": False})
    mode = h.get("adapter_mode")
    if mode not in ("off", "shadow", "active"):
        return stop("error", "adapter-mode-unknown",
                    "Skill 74 reported no usable mode; do not dispatch",
                    {"adapter_mode": mode, "generated": False})
    if mode != "active":
        return stop(
            "waiting", "generation-not-switched-on",
            "tell the client generation is not switched on; nothing was "
            "generated and no approval card exists. Activate Skill 74 "
            "(mode=active) before dispatching again.",
            {"adapter_mode": mode, "generated": False,
             "approval_card": None, "fallback_used": False,
             "disposition": "not-generated",
             "client_message": "Generation is not switched on for this "
                               "client yet - nothing has been generated."})

    # ---- 3. Skill 74 preflight --------------------------------------------
    p_rc, p, p_raw = _call(run, adapter,
                           ["preflight", "--model", model,
                            "--units", str(units), "--json"])
    if p is None:
        return stop("error", "preflight-unreadable",
                    "Skill 74 preflight did not answer JSON; do not dispatch",
                    {"rc": p_rc, "raw": (p_raw or "")[-400:],
                     "generated": False})
    p_data = p.get("data") or {}
    p_err = p.get("error") or {}
    shortfall = p_data.get("shortfall")
    if p.get("state") == "fail" or p_data.get("ok") is False:
        reason = ("preflight-shortfall"
                  if p_err.get("code") == "insufficient_credits"
                  or shortfall is not None else "preflight-failed")
        return stop(
            "rejected", reason,
            "top up the balance so it covers price x 1.30, then retry with a "
            "new attempt id; nothing was generated",
            {"adapter_state": p.get("state"), "code": p_err.get("code"),
             "shortfall": shortfall, "data": p_data, "generated": False})

    # ---- 4. prompt-budget --check -----------------------------------------
    tmp = tempfile.mkdtemp(prefix="kie-dispatch-")
    try:
        prompt_file = os.path.join(tmp, "prompt.txt")
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt or "")
        b_rc, b, b_raw = _call(run, adapter,
                               ["prompt-budget", "--model", model, "--check",
                                "--prompt-file", prompt_file, "--json"])
        if b is None:
            return stop("rejected", "prompt-budget-unreadable",
                        "Skill 74 prompt-budget did not answer JSON; do not "
                        "dispatch",
                        {"exit_code": b_rc, "raw": (b_raw or "")[-400:],
                         "generated": False})
        if b_rc == 4 or (b.get("data") or {}).get("status") == "ABOVE_MAX":
            d = b.get("data") or {}
            return stop("rejected", "prompt-over-max",
                        "cut %s characters from the prompt (max %s) and recheck"
                        % (d.get("cut", "?"), d.get("max", "?")),
                        {"exit_code": b_rc, "data": d, "generated": False})
        if b_rc == 3 or (b.get("data") or {}).get("status") == "BELOW_FLOOR":
            d = b.get("data") or {}
            return stop("rejected", "prompt-below-floor",
                        "add %s characters to the prompt (floor %s) and recheck"
                        % (d.get("add_to_floor", "?"), d.get("floor", "?")),
                        {"exit_code": b_rc, "data": d, "generated": False})
        if b_rc != 0:
            return stop("rejected", "prompt-budget-failed",
                        "Skill 74 prompt-budget refused the prompt; fix it "
                        "before dispatch",
                        {"exit_code": b_rc, "raw": (b_raw or "")[-400:],
                         "generated": False})

        # ---- 5. submit / wait / save ---------------------------------------
        # Split of the old single `run` call (manual C2): the outer subprocess
        # timer used to fire before Skill 74's own wait, so a long video left
        # an unknown row with no task id and the resolver zero-settled spend.
        req_file = os.path.join(tmp, "request.json")
        with open(req_file, "w", encoding="utf-8") as f:
            json.dump(request, f, sort_keys=True)
        os.makedirs(save_dir, exist_ok=True)

        wait_s = _wait_budget_s(request, model, adapter)
        # Injected runners (tests) already stand in for Skill 74; the real
        # wait subprocess gets W+120 so the inner wait always returns first.
        wait_run = run if runner is not None else make_runner(wait_s + 120)

        def _unknown_at(stage, extra, task=""):
            ev = {"stage": stage, "wait_timeout_s": wait_s}
            ev.update(extra)
            if task:
                ev["task_id"] = task
                ev["remote_task_id"] = task
            return _hold_unknown(ledger_db, run_id, logical_key, attempt_id,
                                 owner, ev)

        # (1) submit --------------------------------------------------------
        try:
            s_rc, s, s_raw = _call(run, adapter,
                                   ["submit", "--request", req_file, "--json"])
        except Exception as e:                              # pragma: no cover
            return _unknown_at("submit", {"error": str(e)})
        if s is None:
            return _unknown_at("submit",
                               {"rc": s_rc, "raw": (s_raw or "")[-400:]})

        s_state = s.get("state")
        if s_state == "rate_limited":
            return stop(
                "waiting", "kie-rate-limited-not-submitted",
                "KIE answered HTTP 429 to every retry for job %s: it did NOT run "
                "and is not queued. Not submitted, not dropped; resubmit it."
                % logical_key,
                {"stage": "submit", "error": s.get("error"), "generated": False,
                 "disposition": "not-submitted", "job": logical_key},
                final="failed", cost=0)
        task_id = s.get("task_id") or ""
        s_err = s.get("error") if isinstance(s.get("error"), dict) else {}

        if s_state == RUN_SKIPPED:
            return stop(
                "waiting", "generation-skipped-not-generated",
                "Skill 74 skipped the submit; skipped is not generated. Do not "
                "fall back to a private KIE client - activate mode=active.",
                {"stage": "submit", "adapter_state": s_state,
                 "generated": False, "approval_card": None,
                 "fallback_used": False, "disposition": "not-generated"})
        if s_state == RUN_FAILED:
            # Definite submit error: settle now. Never leave an unknown row
            # that the resolver could zero-settle without asking KIE.
            credits = s.get("credits_consumed")
            cost = (int(credits) if isinstance(credits, (int, float))
                    and not isinstance(credits, bool) else 0)
            _record_stage_evidence(
                ledger_db, run_id, logical_key, attempt_id, "submit",
                status="fail", task_id=task_id, error=s_err,
                adapter_state=s_state)
            if is_video:
                # F14: no automatic fallback for video. Settle, then stop and
                # ask the owner with the next approved option and its price.
                return stop(
                    "waiting", "VIDEO_MODEL_DOWN",
                    "the locked video model did not submit (definite submit "
                    "error: %s); nothing was generated. No automatic "
                    "fallback - ask the owner with the next approved option "
                    "from price-menu.md and its price."
                    % (s_err.get("code") or "unknown"),
                    {"stage": "submit", "adapter_state": s_state,
                     "error": s_err, "task_id": task_id or None,
                     "actual_cost": cost, "generated": False,
                     "locked_model": locked,
                     "next_approved_options": ML.ALLOWED_VIDEO_MODELS},
                    final="failed", cost=cost)
            return stop(
                "rejected", "kie-submit-failed",
                "Skill 74 submit refused the job (%s); nothing was generated"
                % (s_err.get("code") or "unknown"),
                {"stage": "submit", "adapter_state": s_state, "error": s_err,
                 "task_id": task_id or None, "actual_cost": cost,
                 "generated": False},
                final="failed", cost=cost)

        if s_state == RUN_OK and not task_id:
            # Sync family already finished inside submit; no pollable id.
            task_id = "sync-" + L.digest_request(request)[:12]

        if task_id:
            sub = L.mark_submitted(ledger_db, run_id, logical_key, attempt_id,
                                   task_id, owner=owner)
            if sub.get("outcome") == "ok":
                job_state = "submitted"
        elif s_state in RUN_PENDING:
            return _unknown_at("submit",
                               {"adapter_state": s_state,
                                "remote_task_id": None})
        elif s_state != RUN_OK:
            return _unknown_at(
                "submit",
                {"adapter_state": s_state, "task_id": task_id or None,
                 "remote_task_id": task_id or None,
                 "known_states": [RUN_OK, RUN_FAILED, RUN_SKIPPED]
                 + list(RUN_PENDING)})

        # (2) wait (async only; sync submit already answered) ---------------
        src = s
        if s_state in RUN_PENDING:
            try:
                w_rc, wj, w_raw = _call(
                    wait_run, adapter,
                    ["wait", "--task-id", task_id,
                     "--timeout", str(wait_s), "--json"])
            except Exception as e:                          # pragma: no cover
                return _unknown_at("wait", {"error": str(e)}, task_id)
            if wj is None:
                return _unknown_at("wait",
                                   {"rc": w_rc, "raw": (w_raw or "")[-400:]},
                                   task_id)
            w_state = wj.get("state")
            w_err = wj.get("error") if isinstance(wj.get("error"), dict) else {}
            task_id = wj.get("task_id") or task_id
            if w_state == RUN_FAILED:
                credits = wj.get("credits_consumed")
                cost = (int(credits) if isinstance(credits, (int, float))
                        and not isinstance(credits, bool) else 0)
                # F10: a failed task is reported within ONE poll - this poll.
                # The evidence row and the rejected envelope carry the task id,
                # the outcome and the receipt, and the ledger settles failed
                # immediately; no further polling, no silent skip.
                _record_stage_evidence(
                    ledger_db, run_id, logical_key, attempt_id, "wait",
                    status="fail", task_id=task_id, error=w_err,
                    adapter_state=w_state)
                return stop(
                    "rejected", "kie-run-failed",
                    "Skill 74 reported a failed run (%s); reconcile the "
                    "charge, then retry with a new attempt id"
                    % (w_err.get("code") or "unknown"),
                    {"stage": "wait", "adapter_state": w_state, "error": w_err,
                     "task_id": task_id, "actual_cost": cost,
                     "failure_poll": 1, "generated": False},
                    final="failed", cost=cost)
            if w_state != RUN_OK:
                # wait timeout (running + error.code == timeout) and any other
                # non-terminal answer: hold unknown WITH the task id so the
                # resolver queries KIE instead of settling at zero.
                return _unknown_at(
                    "wait",
                    {"adapter_state": w_state, "error": w_err,
                     "wait_timeout_s": wait_s,
                     "timed_out": (w_state == "running"
                                   and w_err.get("code") == "timeout")},
                    task_id)
            src = wj

        # (3) save ----------------------------------------------------------
        try:
            v_rc, v, v_raw = _call(run, adapter,
                                   ["save", "--task-id", task_id,
                                    "--save-dir", save_dir, "--json"])
        except Exception as e:                              # pragma: no cover
            v, v_raw, v_rc = None, str(e), -1
        saved = (v.get("saved_paths") or []) if isinstance(v, dict) else []
        credits = src.get("credits_consumed")
        if isinstance(credits, (int, float)) and not isinstance(credits, bool):
            actual = int(credits)
            warn = []
        else:
            actual = int(estimated_cost)
            warn = ["ACTUAL_COST_UNREPORTED"]
        if not saved:
            warn.append("SAVE_FAILED")

        rec = _settle(ledger_db, run_id, logical_key, attempt_id, owner,
                      job_state, "succeeded", actual, task_id=task_id,
                      provider_ref="kie", evidence_ref=task_id)
        if rec["outcome"] not in ("ok", "parked"):
            return envelope("dispatch", rec["outcome"],
                            rec.get("reason_code", "ledger-settle-failed"),
                            rec.get("next_action", ""),
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id,
                            evidence={"task_id": task_id,
                                      "saved_paths": saved},
                            state_version=rec.get("state_version", 0))
        return envelope(
            "dispatch", "ok", "KIE_DISPATCH_OK",
            "files saved before the links expire; record the receipt",
            run_id=run_id, logical_key=logical_key, attempt_id=attempt_id,
            evidence={"adapter_mode": mode, "generated": True,
                      "task_id": task_id,
                      "saved_paths": saved,
                      "credits_consumed": credits,
                      "actual_cost": actual, "warnings": warn,
                      "wait_timeout_s": wait_s, "retries": 0,
                      "prompt_caps": prompt_caps},
            state_version=rec.get("state_version", 0))
    except Exception as e:                                  # noqa: BLE001
        return stop("error", "dispatch-internal-error",
                    str(e)[:300], {"error": str(e)[:300], "generated": False})
    finally:
        try:
            for name in os.listdir(tmp):
                os.unlink(os.path.join(tmp, name))
            os.rmdir(tmp)
        except OSError as exc:
            _loud("warn", "TMP_CLEANUP_FAILED", "%s: %r" % (tmp, exc))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="kie_dispatch.py",
        description="Plan 5.4 KIE dispatch: reserve -> Skill 74 health -> "
                    "preflight -> prompt-budget -> submit/wait/save -> reconcile.")
    d = ap.add_subparsers(dest="cmd", required=True)
    x = d.add_parser("dispatch", help="Run one reserved KIE generation.")
    x.add_argument("--model", required=True, help="Exact model id (never picked here).")
    x.add_argument("--request", required=True, help="Skill 74 req.json path.")
    x.add_argument("--save-dir", required=True)
    x.add_argument("--ledger", required=True, help="spend_ledger SQLite path.")
    x.add_argument("--run-id", required=True)
    x.add_argument("--logical-key", required=True)
    x.add_argument("--attempt-id", required=True)
    x.add_argument("--cost", type=int, required=True,
                   help="Estimated cost in ledger units, recorded before dispatch.")
    x.add_argument("--units", type=int, default=1)
    x.add_argument("--prompt", default=None)
    x.add_argument("--prompt-file", default=None)
    x.add_argument("--stage", default="kie")
    x.add_argument("--owner", default="kie-dispatch")
    x.add_argument("--adapter", default=None,
                   help="Path to kie_live_adapter.py (default: search).")
    x.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args(argv)

    if a.cmd == "dispatch":
        with open(a.request, encoding="utf-8") as f:
            request = json.load(f)
        if a.prompt_file:
            if a.prompt_file == "-":
                prompt = sys.stdin.read()
            else:
                with open(a.prompt_file, encoding="utf-8") as f:
                    prompt = f.read()
        else:
            prompt = a.prompt or ""
        env = dispatch(model=a.model, request=request, save_dir=a.save_dir,
                       ledger_db=a.ledger, run_id=a.run_id,
                       logical_key=a.logical_key, attempt_id=a.attempt_id,
                       estimated_cost=a.cost, prompt=prompt, units=a.units,
                       stage=a.stage, owner=a.owner, adapter_path=a.adapter,
                       timeout=a.timeout)
        json.dump(env, sys.stdout, indent=2, sort_keys=True, default=str)
        sys.stdout.write("\n")
        return EXIT[env["outcome"]]
    return 1


if __name__ == "__main__":
    sys.exit(main())

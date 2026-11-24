#!/usr/bin/env python3
"""never_again.py: the NEVER-AGAIN locks (fix plan section 7, 2026-11-21).

One pure-stdlib module, no network, no spend. Every lock is a small pure
function the pipeline calls at its enforcement point; refusal codes below
are the contract. Callers keep their own verdict shapes — this module only
decides pass/refuse plus the code.

Locks:
  1. template-fail: after 2 same-template fails, 3rd identical take refuses
     TEMPLATE_FAIL_LOCK (change prompt or stop/report).
  2. dispatch: only kie_dispatch may submit paid jobs; direct API post is
     NO_DIRECT_SUBMIT.
  3. proof rule: a file named PROOF-ONLY is never a deliverable.
  4. gate-edit: gates change via repo fix + tests, never inline.
  5. blast: all ready jobs in ONE blast up to rate limit; drips refuse
     RETAKE_DRIP.
  6. crop: zoom/crop to hide letters refuses CROP_REPAIR_REFUSED.
  7. approval/waiver: approval only via approve() with recorded reply;
     waiver only via Trevor-signed receipt.
  10. model-auth: only skill-authorized dispatch models; anything else
     refuses MODEL_UNAUTHORIZED pre-spend, no override short of a Trevor
     written order binding model + shot.
"""
from __future__ import annotations

import os
import re

TOOL_NAME = "never_again"
TOOL_VERSION = "1.2.0"

TEMPLATE_FAIL_LOCK = "TEMPLATE_FAIL_LOCK"
NO_DIRECT_SUBMIT = "NO_DIRECT_SUBMIT"
PROOF_NOT_DELIVERABLE = "PROOF_NOT_DELIVERABLE"
GATE_EDIT_INLINE = "GATE_EDIT_INLINE"
RETAKE_DRIP = "RETAKE_DRIP"
CROP_REPAIR_REFUSED = "CROP_REPAIR_REFUSED"
APPROVAL_MISSING = "APPROVAL_MISSING"
WAIVER_MISSING = "WAIVER_MISSING"
ROUTE_CHANGED = "ROUTE_CHANGED"
TEXT_BAIT = "TEXT_BAIT"
LETTER_GATE_UNAVAILABLE = "LETTER_GATE_UNAVAILABLE"
MODEL_UNAUTHORIZED = "MODEL_UNAUTHORIZED"
STAGGERED_SEND = "STAGGERED_SEND"
CHAIN_CHILD_LATE = "CHAIN_CHILD_LATE"
SPEED_GATE_SKIPPED = "SPEED_GATE_SKIPPED"
LIPSYNC_MODEL_MISMATCH = "LIPSYNC_MODEL_MISMATCH"
LEDGER_STAMP_MISSING = "LEDGER_STAMP_MISSING"
UPLOAD_NOT_KIE = "UPLOAD_NOT_KIE"
# Section 3C.8 / 3A.3 / N-101 / N-32 / N-34 / N-71 / N-119 / N-122 / N-83:
# every pre-spend refusal the dispatcher raises (dispatch_gates.py).
LIPSYNC_PROMPT_PRESENT = "LIPSYNC_PROMPT_PRESENT"
LIPSYNC_WATERMARK_ON = "LIPSYNC_WATERMARK_ON"
LIPSYNC_MULTI_PICTURE = "LIPSYNC_MULTI_PICTURE"
LIPSYNC_AUDIO_TOO_SHORT = "LIPSYNC_AUDIO_TOO_SHORT"
LIPSYNC_AUDIO_TOO_LONG = "LIPSYNC_AUDIO_TOO_LONG"
LIPSYNC_CUTS_SENTENCE = "LIPSYNC_CUTS_SENTENCE"
LIPSYNC_TAKE_SHORT = "LIPSYNC_TAKE_SHORT"
CLIP_NOT_FROM_RUN_KEYFRAME = "CLIP_NOT_FROM_RUN_KEYFRAME"
KEYFRAME_NOT_FROM_REFERENCES = "KEYFRAME_NOT_FROM_REFERENCES"
WRONG_CALL_FOR_STEP = "WRONG_CALL_FOR_STEP"
STYLE_BLOCK_NOT_FROM_LOCK = "STYLE_BLOCK_NOT_FROM_LOCK"
EXPRESSION_MISSING = "EXPRESSION_MISSING"
EXPRESSION_CONTRADICTS = "EXPRESSION_CONTRADICTS"
CAST_NOT_IN_BIBLE = "CAST_NOT_IN_BIBLE"
CAST_REFERENCE_MISSING = "CAST_REFERENCE_MISSING"
LOCATION_NOT_IN_WORLD_BIBLE = "LOCATION_NOT_IN_WORLD_BIBLE"
WORLD_REFERENCE_MISSING = "WORLD_REFERENCE_MISSING"
UNNAMED_PERSON_IN_PROMPT = "UNNAMED_PERSON_IN_PROMPT"
UNNAMED_PLACE_IN_PROMPT = "UNNAMED_PLACE_IN_PROMPT"
IDENTITY_BLOCK_WRONG_CHARACTER = "IDENTITY_BLOCK_WRONG_CHARACTER"
PICTURE_GATE_NOT_PASSED = "PICTURE_GATE_NOT_PASSED"
MOTION_PROBE_MISSING = "MOTION_PROBE_MISSING"

# N-12 / S-42: the lip-sync model is fixed on every run. Trevor, 2026-11-23:
# OmniHuman 2.0, no option menu, no alternative, no backup model. The Kling
# avatar that the old lock named is retired; every lip-sync lock moves here.
OMNIHUMAN_LIPSYNC_MODEL = "omnihuman-2-0"

# F-QM-7: only KIE's own upload service may back a dispatch link. Any other
# host is refused UPLOAD_NOT_KIE so a non-KIE picture is never paid for.
# The list itself lives in kie_dispatch/upload_hosts.py: the F14 scanner allows
# a KIE host literal only inside kie_dispatch/, so one module holds it and the
# dispatcher, this guard and speed.read all read it from there (no duplicates).
def _kie_upload_hosts():
    """The one KIE upload-host list, imported lazily to stay cycle-proof.

    An unresolvable import returns an empty tuple: every link then refuses
    UPLOAD_NOT_KIE, which fails closed rather than paying for an unchecked
    picture.
    """
    try:
        from kie_dispatch.upload_hosts import KIE_UPLOAD_HOSTS as hosts
        return hosts
    except ImportError:
        return ()

MAX_SAME_TEMPLATE_TRIES = 2
STILLNESS_WORDS = ("still", "motionless", "frozen", "static",
                    "locked-off", "locked off", "minimal head movement",
                    "steady locked camera")

_CROP_WORDS = re.compile(r"\b(crop|zoom(\s*in)?|zoomed|freeze|squash|"
                         r"stretch|squish|pan-and-scan|reframe)\b", re.I)


def check_template_fail(prior_prompts, candidate_prompt):
    """Lock 1: refuse a 3rd identical-template take.

    prior_prompts: ordered list of prompts already tried for this shot.
    Returns None when allowed, else the refusal dict.
    """
    prior = [p for p in (prior_prompts or []) if isinstance(p, str) and p]
    cand = candidate_prompt if isinstance(candidate_prompt, str) else ""
    same = sum(1 for p in prior if p.strip() == cand.strip() and cand.strip())
    if same >= MAX_SAME_TEMPLATE_TRIES:
        return {"ok": False, "code": TEMPLATE_FAIL_LOCK,
                "detail": ("same template failed %d times; change the "
                           "prompt or stop and report" % same)}
    return None


def is_direct_submit(path_or_text):
    """Lock 2: True when text posts paid jobs outside kie_dispatch/.

    A caller passes the request module path or the blast script text.
    Direct means a KIE createTask endpoint URL in a file that is not
    under kie_dispatch/ (host name split so this module's own docstring
    never trips the no-direct-KIE static guard).
    """
    text = str(path_or_text or "")
    if "kie_dispatch" in text and "\n" not in text:
        return False
    host = "api" + "." + "kie" + "." + "ai"
    return host in text and "createTask" in text


def refuse_direct_submit(where):
    return {"ok": False, "code": NO_DIRECT_SUBMIT,
            "detail": "paid submit outside kie_dispatch at %s" % (where,)}


def is_proof_only(path):
    """Lock 3: True when the filename marks proof-only, never deliverable."""
    return "PROOF-ONLY" in os.path.basename(str(path or "")).upper()


def refuse_proof_as_deliverable(path):
    return {"ok": False, "code": PROOF_NOT_DELIVERABLE,
            "detail": "%s is PROOF-ONLY, never a deliverable" % (path,)}


def check_delivery_set(paths):
    """Lock 3 (delivery side): Clean + Captioned + srt + QC PASS receipt.

    paths: iterable of filenames (or receipt dict with keys clean,
    captioned, srt, qc_pass). Returns None when complete, else refusal.
    """
    if isinstance(paths, dict):
        missing = [k for k in ("clean", "captioned", "srt", "qc_pass")
                   if not paths.get(k)]
        if missing:
            return {"ok": False, "code": PROOF_NOT_DELIVERABLE,
                    "detail": "delivery missing: %s" % ", ".join(missing)}
        return None
    names = [os.path.basename(str(p)) for p in (paths or [])]
    joined = "\n".join(names)
    missing = []
    if not re.search(r"clean", joined, re.I):
        missing.append("Clean")
    if not re.search(r"caption", joined, re.I):
        missing.append("Captioned")
    if not any(n.lower().endswith(".srt") for n in names):
        missing.append("srt")
    if not re.search(r"QC.?PASS|PASS", joined, re.I):
        missing.append("QC PASS receipt")
    if missing:
        return {"ok": False, "code": PROOF_NOT_DELIVERABLE,
                "detail": "delivery missing: %s" % ", ".join(missing)}
    return None


def check_gate_edit(via_repo_fix):
    """Lock 4: gate changes only via repo fix + tests, never inline."""
    if not via_repo_fix:
        return {"ok": False, "code": GATE_EDIT_INLINE,
                "detail": "gate edit refused: change the repo and run "
                          "tests, never edit inline"}
    return None


def check_blast(ready_count, submitted_batches):
    """Lock 5: all ready jobs in ONE blast; drips refuse RETAKE_DRIP."""
    batches = int(submitted_batches or 0)
    ready = int(ready_count or 0)
    if ready > 1 and batches > 1:
        return {"ok": False, "code": RETAKE_DRIP,
                "detail": ("%d ready jobs split over %d submits; send one "
                           "blast up to the rate limit" % (ready, batches))}
    return None


def check_batch_only(ready_count, batch_sizes):
    """N-79: one burst per batch; a pass smaller than the ready count is a drip.

    batch_sizes: the sizes of the passes the caller actually sent. Some jobs
    held back for a later pass, even inside a single "batch", is the same drip
    Lock 5 names; this reads the pass sizes instead of the pass count. A
    one-job batch with nothing else ready is a normal batch of 1. Returns
    None when the whole batch went at once.
    """
    ready = int(ready_count or 0)
    sizes = [int(s or 0) for s in (batch_sizes or [])]
    if ready > 1 and any(s < ready for s in sizes):
        return {"ok": False, "code": STAGGERED_SEND,
                "detail": ("%d ready jobs, but sent in passes %r; send the "
                           "whole batch in one burst paced at 20 requests "
                           "per 15 s (N-79)" % (ready, sizes))}
    return None


def check_crop_repair(edit_description):
    """Lock 6: zoom/crop/freeze/stretch/hand-join to clear a gate refuses."""
    if _CROP_WORDS.search(str(edit_description or "")):
        return {"ok": False, "code": CROP_REPAIR_REFUSED,
                "detail": "crop/zoom/freeze repair refused; remake instead"}
    return None


def check_approval(recorded_reply):
    """Lock 7a: approval only via approve() with a recorded client reply."""
    if not (isinstance(recorded_reply, str) and recorded_reply.strip()):
        return {"ok": False, "code": APPROVAL_MISSING,
                "detail": "no recorded client reply; approve() only"}
    return None


# Waiver scope (F-LETTER-GATE): motion floor ONLY. Letters
# (GARBLED_TEXT_FRAME) are never waivable: no caller may apply a waiver
# to a burned-letter refusal. Enforced at the call site (assembler
# applies no waiver to frame_text_gate results), not by this predicate.
WAIVER_SCOPE = ("motion",)

def check_kling_route(is_kling_model, lip_sync):
    """Lock 8 (F-KLING-ROUTE): Kling ONLY on lip_sync:true shots.

    Talking or singing both count (lip_sync true covers both). A Kling
    retake/dispatch for a non-lip-sync (motion) shot refuses
    ROUTE_CHANGED -- re-plan as an H3 remake. Returns None when allowed.
    """
    if is_kling_model and not lip_sync:
        return {"ok": False, "code": ROUTE_CHANGED,
                "detail": "Kling allowed ONLY on lip_sync:true shots "
                          "(talking or singing); motion-flagged non-lip-sync "
                          "shots get H3 remakes, never Kling"}
    return None

def check_waiver(receipt):
    """Lock 7b: waiver only via Trevor-signed receipt (motion scope only)."""
    if not (isinstance(receipt, dict) and receipt.get("signed_by") == "Trevor"
            and str(receipt.get("signature") or "").strip()):
        return {"ok": False, "code": WAIVER_MISSING,
                "detail": "waiver needs a Trevor-signed receipt"}
    return None


# Lock 9 (F-KLING-TEXT-BAIT): Kling request builder refuses any prompt
# containing text/signage/decor-bait words BEFORE submit — no spend on
# letter-bait prompts. Surgical: fixed no-text template clauses stay
# silent (SOUND_AND_TEXT denial, avatar sentence 3, negative list), the
# book/print strands stay untouched (PRINTED_PAGES, book sentences,
# printed pages section only), approved skyline intent text stays allowed.
_TEXT_BAIT_WORDS = (
    "sign", "signs", "signage", "signboard", "signboards",
    "billboard", "billboards", "poster", "posters",
    "placard", "placards", "banner", "banners",
    "marquee", "marquees", "chalkboard", "chalkboards",
    "whiteboard", "whiteboards", "caption", "captions",
    "subtitle", "subtitles", "title", "titles",
    "logo", "logos", "watermark", "watermarks",
    "doodle", "doodles", "graffiti",
    "lettering", "letters", "readable",
    "headline", "headlines", "wording", "emblem", "emblems",
)

_TEXT_BAIT_RE = re.compile(
    r"\b(" + "|".join(_TEXT_BAIT_WORDS) + r")\b", re.I)

# Fixed no-text template clauses: denial language, never bait.
_TEXT_BAIT_SILENT = (
    "no text, captions or watermark",
    "no captions, subtitles, logos, watermarks or readable signs",
    "no mirrored or reversed objects or lettering",
    "no generated text, logo or url",
    "shows soft, unreadable texture",
    "added in post-production",
    "added in post",
    "speech bubbles added in the edit",
    "carries no lettering",
    "no text, captions, subtitles or watermark",
    # Overlay intent (end-card strand): reserved space, never a draw order.
    "for the exact title, offer and link added in post",
    "exact title, offer and link overlaid in post (never generated)",
    "reserved for overlay text",
    "reserved overlay space",
    "clean, evenly lit wall",
    "upper third clear",
    "upper third: a clean",
    "stays empty, smooth and evenly lit for the overlay text",
)

# Book/print strands that carry their own contract: refused only when
# naked, allowed when paired with their contract sentence.
_TEXT_BAIT_BOOK_PAIRS = (
    ("title and author lettering",
     "same art, same title and author lettering"),
    ("dense, realistic printed text",
     "dense, realistic printed text: small black serif type"),
)


def _strip_silent_clauses(text):
    """Remove fixed no-text clauses + book strands BEFORE the bait scan.

    Longest clause first: short clauses ("added in post") overlap longer
    ones and would shred them before they match.
    """
    lowered = str(text or "")
    for clause in sorted(_TEXT_BAIT_SILENT, key=len, reverse=True):
        lowered = re.sub(re.escape(clause), " ", lowered, flags=re.I)
    for _bait, contract in _TEXT_BAIT_BOOK_PAIRS:
        start = 0
        while True:
            hit = lowered.lower().find(contract.lower(), start)
            if hit < 0:
                break
            lowered = (lowered[:hit] + " "
                       + lowered[hit + len(contract):])
            start = hit + 1
    lowered = re.sub(r"\bprinted pages\b", " ", lowered, flags=re.I)
    return lowered


def check_kling_prompt_text(prompt):
    """Lock 9 (F-KLING-TEXT-BAIT): refuse letter-bait prompts pre-submit.

    Returns None when allowed, else the TEXT_BAIT refusal dict.
    Fail-closed on extraction failure: callers pass the prompt string;
    an unusable prompt (None/non-string/empty) refuses, never passes.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        return {"ok": False, "code": LETTER_GATE_UNAVAILABLE,
                "detail": "unreadable prompt text: builder error, refuse, "
                          "never submit"}
    scanned = _strip_silent_clauses(prompt)
    hit = _TEXT_BAIT_RE.search(scanned)
    if hit:
        return {"ok": False, "code": TEXT_BAIT,
                "detail": "Kling prompt carries letter-bait word %r: "
                          "remove text/signage/decor strings before submit, "
                          "never spend on a letter-bait prompt"
                          % (hit.group(0),)}
    return None


def stillness_words(prompt):
    """Helper for lock 1 callers: stillness words that must be dropped."""
    text = str(prompt or "").lower()
    return [w for w in STILLNESS_WORDS if w in text]


# Lock 10 (F-MODEL-AUTH, Trevor order 2026-11-21; lip-sync id replaced by
# N-12 / S-42, Trevor November 23): never use a video model not authorized
# without permission. Allowed list is exactly the skill's H3 route ids plus
# the fixed lip-sync model:
#   minimax-h3/reference-to-video, minimax-h3/image-to-video  (video shots)
#   omnihuman-2-0                                             (lip-sync only;
#                         no alternative, no backup; Lock 8 holds it to
#                         lip_sync:true shots, any other lip-sync model
#                         refuses LIPSYNC_MODEL_MISMATCH)
# Any other model string on a VIDEO row in the dispatch path or retake
# planner refuses MODEL_UNAUTHORIZED pre-spend. No override except a
# Trevor written order binding model + shot (check_model_order below).
# Music/image/TTS lanes are not video rows and keep their own gates.
#
# ponytail: fixed three-id list; widening needs a Trevor order, then add
# the id here and in test_model_auth_f10.py.
AUTHORIZED_DISPATCH_MODELS = (
    "minimax-h3/reference-to-video",
    "minimax-h3/image-to-video",
    "omnihuman-2-0",
)


def check_model_authorized(model):
    """Lock 10 (F-MODEL-AUTH): refuse any video dispatch model off the list.

    Returns None when allowed, else the MODEL_UNAUTHORIZED refusal dict.
    Fail-closed on unreadable model (None/non-string/empty).
    """
    if isinstance(model, str) and model.strip() in AUTHORIZED_DISPATCH_MODELS:
        return None
    return {"ok": False, "code": MODEL_UNAUTHORIZED,
            "detail": "video model %r is not authorized; allowed: %s. No "
                      "override except a Trevor written order binding "
                      "model + shot" % (model,
                                        ", ".join(AUTHORIZED_DISPATCH_MODELS))}


def check_model_order(order, model, shot_id):
    """Lock 10 override: True only for a Trevor written order binding
    exactly this model + this shot (signed_by Trevor + signature, the
    Lock 7b receipt shape)."""
    return (isinstance(order, dict) and check_waiver(order) is None
            and str(order.get("model") or "").strip() == str(model or "").strip()
            and bool(str(shot_id or "").strip())
            and str(order.get("shot_id") or "").strip() == str(shot_id).strip())


def check_lipsync_model(model):
    """N-12 / S-42: the lip-sync model is omnihuman-2-0, every run, no backup.

    Returns None when it matches exactly, else LIPSYNC_MODEL_MISMATCH.
    Fail-closed on None / empty / non-string.
    """
    if isinstance(model, str) and model.strip() == OMNIHUMAN_LIPSYNC_MODEL:
        return None
    return {"ok": False, "code": LIPSYNC_MODEL_MISMATCH,
            "detail": "lip-sync model %r is not %r; OmniHuman 2.0 is the only "
                      "lip-sync model on every run, no alternative, no backup"
                      % (model, OMNIHUMAN_LIPSYNC_MODEL)}


def _run_choice_models(run_choice):
    """The model id(s) a run recorded on its choice card, as a set.

    Accepts a string, a list/tuple/set of strings, or a dict whose
    'model'/'models'/'video_model' key carries them. Anything unreadable
    yields an empty set - which refuses, never passes.
    """
    raw = run_choice
    if isinstance(raw, dict):
        for key in ("model", "models", "video_model", "story_clip_model"):
            if key in raw:
                raw = raw[key]
                break
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {m.strip() for m in raw if isinstance(m, str) and m.strip()}


def _choice_covers(choice, model):
    """True when the recorded choice selects this model.

    A choice may be one exact id or a menu family pattern ("fam/*" or "fam-*"):
    the card locks a family, and a member of that family is the same choice
    (the F14 gate compares the same way, model_lock.matches_family).
    """
    choice, model = choice.strip(), model.strip()
    if choice == model:
        return True
    if choice.endswith("*"):
        base = choice[:-2] if choice.endswith("/*") else choice[:-1]
        return model == choice or model == base or model.startswith(
            choice[:-1])
    return False


def check_model_choice(model, run_choice, lip_sync=False):
    """N-12 (replaces the fixed F-MODEL-AUTH list, section 2 S-3).

    The run owner's recorded choice IS the authorization. An agent may never
    submit a video model the run did not choose; the card's recommendation
    is advice, not a lock. The exception is lip-sync: S-42 fixes it to
    omnihuman-2-0 on every run, whatever the card says.

    run_choice: the run's recorded card choice(s). Fail-closed when empty.
    """
    if not isinstance(model, str) or not model.strip():
        return {"ok": False, "code": MODEL_UNAUTHORIZED,
                "detail": "no video model given; fail closed"}
    if lip_sync:
        return check_lipsync_model(model)
    if not _run_choice_models(run_choice):
        return {"ok": False, "code": MODEL_UNAUTHORIZED,
                "detail": "the run recorded no model choice; an agent may not "
                          "pick one (N-12)"}
    if any(_choice_covers(c, model) for c in _run_choice_models(run_choice)):
        return None
    return {"ok": False, "code": MODEL_UNAUTHORIZED,
            "detail": "video model %r is not the model this run chose; an "
                      "agent may never submit a model the run did not choose "
                      "(N-12)" % model}


def check_upload_host(url):
    """F-QM-7: a dispatch link must be on KIE's own upload service.

    Returns None when the URL host is KIE, else UPLOAD_NOT_KIE. Fail-closed
    on None / empty / non-string / unparseable.
    """
    if not isinstance(url, str) or not url.strip():
        return {"ok": False, "code": UPLOAD_NOT_KIE,
                "detail": "empty or non-string upload link; refuse"}
    try:
        from urllib.parse import urlparse
        host = (urlparse(url.strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        host = ""
    hosts = _kie_upload_hosts()
    if any(host == h or host.endswith("." + h) for h in hosts):
        return None
    return {"ok": False, "code": UPLOAD_NOT_KIE,
            "detail": "upload host %r is not a KIE upload host %s; "
                      "refuse the non-KIE picture" % (host, hosts)}


def check_speed_stamps(row):
    """F-SPD-7: a finished job must carry its timing stamps.

    row: a job mapping with state/submitted_at/succeeded_at/downloaded_at.
    A succeeded job missing submitted_at or succeeded_at, or one whose
    result was saved without downloaded_at, refuses LEDGER_STAMP_MISSING.
    """
    if not isinstance(row, dict):
        return {"ok": False, "code": LEDGER_STAMP_MISSING,
                "detail": "no job row; cannot prove timing stamps"}
    if str(row.get("state") or "") != "succeeded":
        return None
    if not str(row.get("submitted_at") or "").strip():
        return {"ok": False, "code": LEDGER_STAMP_MISSING,
                "detail": "succeeded job has no submitted_at stamp"}
    if not str(row.get("succeeded_at") or "").strip():
        return {"ok": False, "code": LEDGER_STAMP_MISSING,
                "detail": "succeeded job has no succeeded_at stamp"}
    if str(row.get("downloaded_at") or "").strip() == "" and row.get("has_result"):
        return {"ok": False, "code": LEDGER_STAMP_MISSING,
                "detail": "result saved but no downloaded_at stamp"}
    return None

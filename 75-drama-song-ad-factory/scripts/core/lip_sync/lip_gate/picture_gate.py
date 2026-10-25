"""picture_gate.py: measured close-up gate + sha256 receipt (LPG001, LPG002, LPG003).

Why: the 30-Day Reset close-up (face 28% of frame, smile 0.62) and the Perfect
Daughter close-up (face 34%, teeth, roll -7.8 deg) went to paid Kling lip-sync
unmeasured. The check existed on paper only. Now:

  gate_picture(path)   measure -> the free face-crop ladder when a close-up
                       shows 0 faces (trial C) -> ONE free local crop if the
                       face is too small -> up to MAX_PAID_REGENS paid
                       regenerations for a FAIL a crop cannot fix -> receipt
                       per picture tried -> refuse.
                       no_smile=True (wired method / Agnes runs; inert until
                       then) adds the teeth-smile remake hook: a smiling
                       close-up is remade for free up to MAX_REMAKES times and
                       is NEVER sent to lip-sync smiling.
  make_regenerate()    the default paid regeneration: gpt-image-2
                       image-to-image from the 3D character, dispatched
                       through kie_dispatch (ledger + cap + load_governor).
  upload_measured()    uploads the exact measured bytes (hashed at upload
                       time, refused on mismatch) and binds the URL to them.
  require_receipt()    the kie_dispatch hard block: no PASS / ACCEPT_WITH_FLAG
                       receipt for the exact bytes (sha256), or an image_url
                       that is not the bound upload of those bytes = no paid
                       lip-sync job.

LPG003 loosened the rules (Trevor: "loosen the checks so it's not as strict").
Three verdicts: PASS, ACCEPT_WITH_FLAG (goes to Kling, flags are written to the
receipt), FAIL (refused). FAIL is for clear problems only: face count not 1, a
tiny face, a side profile, a strong tilt, a wide-open mouth, a very soft image.
Smile, teeth, a smaller face, a mild tilt or turn are FLAGS, never a paid
regeneration on their own. Calibrated on the Trevor-approved Kiesett version 2
and the client's lip-sync pictures (the table is in the PR body).

Trevor 2026-10-13, one exception to that loosening and only for a lip-sync
shot: a smiling picture is NEVER sent to lip-sync. A run that wires the hook
passes no_smile=True (and remake=, free on the Agnes path / a cheap still on
the KIE path); the picture is remade up to MAX_REMAKES times and refused
LIPSYNC_SOURCE_SMILING for a human pick after that. Without no_smile every
other shot keeps today's behaviour: a smile is a flag and goes through.

Fail closed everywhere: mediapipe missing, face model missing, unreadable image,
0 or 2+ faces, any number over a FAIL limit -> verdict FAIL / refusal.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time

try:
    from . import picture_measure as PM
except ImportError:                    # script import (tests run from here)
    import picture_measure as PM

try:
    from . import attempt_ceiling as _AC
except ImportError:                    # script import
    import attempt_ceiling as _AC

def _ceiling():
    """The L4.4 attempt-ceiling module (same package); a missing module is
    never a stop: no ceiling check runs (picture_gate's own caps still hold)."""
    return _AC

TOOL_NAME = "lipsync_picture_gate"
SCHEMA = "blackceo.lipsync-picture-receipt/v1"

# ============================================================================
# ONE constants block. Same names, same values in onboarding and 999-setup.
# FAIL limits (clear problems). Calibration, approved pictures (min / max):
#   face height 21.4 / 26.7 %   roll |10.5| .. |14.8| deg   yaw |0.145| max
#   smile 0.00 .. 0.82   lip gap 0.00 .. 3.55 %   jawOpen 0.001 max
#   sharpness 119.8 .. 541.9 (photos)
# ============================================================================
REQUIRED_FACE_COUNT = 1
MIN_FACE_HEIGHT_PCT = 20.0      # FAIL under this: forehead(10)-chin(152) as % of frame height
MAX_FACE_HEIGHT_PCT = None      # no upper limit unless proven needed
MAX_ABS_ROLL_DEG = 20.0         # FAIL over this (strong tilt)
MAX_ABS_YAW = 0.25              # FAIL over this (side profile)
MAX_JAW_OPEN = 0.30             # FAIL over this (wide-open mouth)
MIN_SHARPNESS = 60.0            # FAIL under this (very soft). Laplacian variance, face crop 256 px wide
# FLAG limits: the picture goes through as ACCEPT_WITH_FLAG, never a paid regen
FLAG_FACE_HEIGHT_PCT = 25.0     # under this: flag (small face)
FLAG_ABS_ROLL_DEG = 5.0
FLAG_ABS_YAW = 0.12
FLAG_SMILE = 0.60
FLAG_JAW_OPEN = 0.15
FLAG_LIP_GAP_PCT = 1.0          # lip gap / face height (the teeth check)
FLAG_SHARPNESS = 100.0
CROP_TARGET_FACE_PCT = 38.0     # the free crop aims here
MAX_FREE_CROPS = 1              # one free local crop for a too-small face
# Free face-crop ladder, rung by rung, BEFORE any paid regeneration: 0 faces on
# the full frame (trial C: a 2K cartoon close-up) but the same picture ACCEPTed
# as a 1040-px upper-centre 9:16 crop of 1472. Widths are of the frame width,
# each cut 9:16 with its top edge in the upper third (upper_centre_crop).
CROP_LADDER_WIDTHS = (0.70, 0.60, 0.80)
MAX_PAID_REGENS = 2             # Trevor's 2-try rule, then refuse
MAX_REMAKES = 3                 # teeth-smile remake tries, then a human pick
SMILING_CODE = "LIPSYNC_SOURCE_SMILING"
SMILING_FLAGS = frozenset({"SMILE"})   # a smile with or without visible teeth
REGEN_MODEL = "gpt-image-2-image-to-image"
REGEN_PROMPT = "neutral expression, lips closed, facing camera, head level"
# ============================================================================

PASS, FLAGGED, FAIL = "PASS", "ACCEPT_WITH_FLAG", "FAIL"
ACCEPTED = (PASS, FLAGGED)           # verdicts that may go to paid lip-sync

# a FAIL with one of these is the gate itself being broken, not the picture:
# no crop, no paid regeneration, just refuse.
NO_REGEN_CODES = frozenset({"GATE_UNAVAILABLE", "MEASURE_ERROR", "UNMEASURED"})

REFUSED = "LIPSYNC_PICTURE_NOT_GATED"


class LipsyncPictureNotGated(Exception):
    """kie_dispatch refuses the paid lip-sync job. .reason is the full text."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def check_numbers(n):
    """Pure rules. n = picture_measure.measure() dict -> (fails, flags), each a
    list of (code, text). Any fail = FAIL; no fail but a flag = ACCEPT_WITH_FLAG."""
    fails, flags = [], []
    c = n.get("face_count")
    if c != REQUIRED_FACE_COUNT:
        return [("FACE_COUNT", "%s faces found; exactly %d is required"
                 % (c, REQUIRED_FACE_COUNT))], flags

    def num(key):
        v = n.get(key)
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and v == v
        if not ok:
            fails.append(("UNMEASURED", "%s not measured" % key))
        return v if ok else None

    def rule(code, key, label, bad, flag, absolute=False, below=False):
        """bad / flag = limits (None = off). above the limit fails, below=True: under."""
        v = num(key)
        if v is None:
            return
        x = abs(v) if absolute else v
        over = (lambda lim: x < lim) if below else (lambda lim: x > lim)
        if bad is not None and over(bad):
            fails.append((code, "%s %s is %s the limit %s" % (
                label, v, "under" if below else "over", bad)))
        elif flag is not None and over(flag):
            flags.append((code, "%s %s is %s the flag line %s" % (
                label, v, "under" if below else "over", flag)))

    rule("FACE_SIZE", "face_h_pct", "face height %", MIN_FACE_HEIGHT_PCT,
         FLAG_FACE_HEIGHT_PCT, below=True)
    v = n.get("face_h_pct")
    if MAX_FACE_HEIGHT_PCT is not None and isinstance(v, (int, float)) and v > MAX_FACE_HEIGHT_PCT:
        fails.append(("FACE_SIZE", "face is %s%% of frame height; at most %g%%"
                      % (v, MAX_FACE_HEIGHT_PCT)))
    rule("HEAD_ROLL", "roll_deg", "head roll deg", MAX_ABS_ROLL_DEG, FLAG_ABS_ROLL_DEG, True)
    rule("HEAD_YAW", "yaw_proxy", "yaw proxy", MAX_ABS_YAW, FLAG_ABS_YAW, True)
    rule("MOUTH_OPEN", "jaw_open", "jawOpen blendshape", MAX_JAW_OPEN, FLAG_JAW_OPEN)
    rule("SMILE", "smile", "smile blendshape", None, FLAG_SMILE)
    rule("TEETH", "inner_gap_pct", "lip gap % of face height", None, FLAG_LIP_GAP_PCT)
    rule("SOFT", "sharp_face_256", "sharpness", MIN_SHARPNESS, FLAG_SHARPNESS, below=True)
    return fails, flags


def write_receipt(path, sha, verdict, numbers, reasons, flags, attempts, receipt_dir):
    os.makedirs(receipt_dir, exist_ok=True)
    rec = {"schema": SCHEMA, "tool": TOOL_NAME, "image": os.path.abspath(path),
           "sha256": sha, "verdict": verdict, "numbers": numbers,
           "reasons": [list(x) for x in reasons], "flags": [list(x) for x in flags],
           "attempts": attempts,
           "limits": {"face_count": REQUIRED_FACE_COUNT,
                      "face_h_pct_min": MIN_FACE_HEIGHT_PCT,
                      "face_h_pct_max": MAX_FACE_HEIGHT_PCT,
                      "roll_deg_abs": MAX_ABS_ROLL_DEG, "yaw_abs": MAX_ABS_YAW,
                      "jaw_open": MAX_JAW_OPEN, "sharpness_min": MIN_SHARPNESS,
                      "flag_face_h_pct": FLAG_FACE_HEIGHT_PCT,
                      "flag_roll_deg_abs": FLAG_ABS_ROLL_DEG, "flag_yaw_abs": FLAG_ABS_YAW,
                      "flag_smile": FLAG_SMILE, "flag_jaw_open": FLAG_JAW_OPEN,
                      "flag_lip_gap_pct": FLAG_LIP_GAP_PCT,
                      "flag_sharpness": FLAG_SHARPNESS},
           "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    p = os.path.join(receipt_dir, sha + ".json")
    with open(p, "w") as f:
        json.dump(rec, f, indent=1, sort_keys=True)
    return rec


def default_receipt_dir(path):
    return os.path.join(os.path.dirname(os.path.abspath(path)), ".lipgate")


def upper_centre_crop(path, out_path, width_frac):
    """One rung of the free face-crop ladder: a 9:16 crop of `width_frac` of the
    frame width, horizontally centred, its top edge at the upper third of the
    slack so the head end of the frame survives. Returns out_path, or None when
    the source cannot hold such a crop (never pads or invents pixels, and None
    when OpenCV is missing: the ladder simply runs out)."""
    try:
        import cv2
    except Exception:
        return None
    img = cv2.imread(path)
    if img is None:
        return None
    H, W = img.shape[:2]
    cw = int(round(W * width_frac))
    ch = int(round(cw * 16.0 / 9.0))                        # 9:16, like crop_to_face
    if cw < 1 or ch < 1 or ch > H:
        return None
    left, top = (W - cw) // 2, (H - ch) // 3
    return out_path if cv2.imwrite(out_path, img[top:top + ch, left:left + cw]) else None




def _measure_all(cur, measure):
    """-> (numbers, fails, flags)"""
    try:
        nums = measure(cur)
        fails, flags = check_numbers(nums)
        return nums, fails, flags
    except PM.PictureGateUnavailable as exc:
        return {}, [("GATE_UNAVAILABLE", str(exc))], []
    except Exception as exc:                               # fail closed
        return {}, [("MEASURE_ERROR", "%s: %s" % (type(exc).__name__, exc))], []


def gate_picture(path, receipt_dir=None, measure=None, crop=None,
                 regenerate=None, max_regens=MAX_PAID_REGENS,
                 ladder=None, no_smile=False, remake=None, max_remakes=MAX_REMAKES):
    """Measure one close-up; fix it; write a receipt per picture tried.
    Returns {"verdict", "image", "sha256", "numbers", "reasons", "flags",
    "attempts"} for the FINAL picture (its path is "image"; use it, not the
    input). verdict is PASS, ACCEPT_WITH_FLAG (flags listed, still goes to
    Kling) or FAIL.

    Auto-fix, only for a FAIL, in this order:
      0. The free face-crop ladder when the picture shows 0 faces: up to
         len(CROP_LADDER_WIDTHS) upper-centre 9:16 crops, before any paid
         regeneration. The crop that passes is the returned "image", so
         upload_measured() binds those exact bytes.
      1. ONE free local crop (MAX_FREE_CROPS) when the face is too small.
      2. Up to MAX_PAID_REGENS paid regenerations for any other FAIL a crop
         cannot fix. regenerate(path, prompt) -> new_path. Use
         make_regenerate(): it goes through kie_dispatch (ledger, author cap,
         load_governor.kie_request). None = no paid fix.
      3. Then refuse (verdict FAIL).
    A flag (teeth, small face, mild tilt) never triggers a crop or a paid
    regeneration.

    no_smile=True (Trevor 2026-10-13; the wired method / Agnes runs; inert
    until then) adds the teeth-smile hook for the lip-sync SHOT ONLY: a close-up
    whose smile flag is raised is remade up to max_remakes times through
    remake(path, prompt) -> new_path (free on the Agnes path, a cheap still on
    the KIE path; use REGEN_PROMPT, new seed) and is NEVER accepted smiling.
    No remake callable, or still smiling after max_remakes tries, = verdict
    FAIL with LIPSYNC_SOURCE_SMILING for a human pick.
    measure(path) -> numbers        default picture_measure.measure
    crop(path, out) -> out|None     default picture_measure.crop_to_face (free)
    ladder(path, out, width) -> out|None   default upper_centre_crop (free)
    """
    measure = measure or PM.measure
    crop = crop or (lambda p, o: PM.crop_to_face(p, o, CROP_TARGET_FACE_PCT))
    ladder = ladder or upper_centre_crop
    rdir = receipt_dir or default_receipt_dir(path)
    root = os.path.splitext(path)[0]                # rung names never nest
    attempts, cur, crops, regens, remakes, rung = [], path, 0, 0, 0, 0
    while True:
        sha = sha256_file(cur)
        nums, reasons, flags = _measure_all(cur, measure)
        codes = {c for c, _ in reasons}
        smiling = no_smile and bool({c for c, _ in flags} & SMILING_FLAGS)
        verdict = FAIL if reasons else FLAGGED if flags else PASS
        refused_smile = False
        if smiling and verdict in ACCEPTED:
            if remake is None or remakes >= max_remakes:
                refused_smile = True                         # never a smiling face
                why = ("no remake callable" if remake is None else
                       "still smiling after %d remakes" % max_remakes)
                reasons = reasons + [(SMILING_CODE,
                                      "smiling close-up is not sent to lip-sync "
                                      "(%s); pick a neutral picture" % why)]
                verdict = FAIL
        attempts.append({"image": cur, "sha256": sha, "numbers": nums,
                         "verdict": verdict, "reasons": [list(x) for x in reasons],
                         "flags": [list(x) for x in flags]})
        rec = write_receipt(cur, sha, verdict, nums, reasons, flags, attempts, rdir)
        if refused_smile:
            return dict(rec, image=cur)
        if smiling and verdict in ACCEPTED:                  # free remake, capped
            remakes += 1
            try:
                cur = remake(cur, REGEN_PROMPT)
            except Exception as exc:                         # refuse, loudly
                reasons = reasons + [("REMAKE_FAILED", "%s: %s" % (type(exc).__name__, exc))]
                attempts = attempts + [dict(attempts[-1], verdict=FAIL,
                                            reasons=[list(x) for x in reasons])]
                return dict(write_receipt(cur, sha, FAIL, nums, reasons, flags,
                                          attempts, rdir), image=cur)
            continue
        if verdict in ACCEPTED or codes & NO_REGEN_CODES:
            return dict(rec, image=cur)
        if nums.get("face_count") == 0 and rung < len(CROP_LADDER_WIDTHS):
            rung += 1                                        # free, local, capped
            out = root + "-ladder%d.png" % rung
            try:
                made = ladder(cur, out, CROP_LADDER_WIDTHS[rung - 1])
            except Exception:                                # next rung
                made = None
            if made:
                cur = made
                continue
        small = "FACE_SIZE" in codes and nums.get("face_h_pct", 100) < MIN_FACE_HEIGHT_PCT
        if small and crops < MAX_FREE_CROPS:
            crops += 1                                      # free, local, once
            out = os.path.splitext(cur)[0] + "-crop.png"
            try:
                made = crop(cur, out)
            except Exception:                               # cannot crop: no free fix
                made = None
            if made:
                cur = made
                continue
        if regenerate is None or regens >= max_regens:
            return dict(rec, image=cur)
        # L4.4 (v2.9.73): the attempt ceiling over THIS call's history —
        # three consecutive identical structural failures stop before the
        # next paid regeneration, with the cause named. picture_gate's own
        # regens cap (2) plus this ceiling keeps any single call bounded;
        # the cross-call guard (the caller's attempt history) is
        # attempt_ceiling.ceiling_check on the receipts on disk.
        ceil = _ceiling().ceiling_check(attempts)
        if ceil.get("stop"):
            reasons = reasons + [(ceil["cause"], ceil["message"])]
            return dict(write_receipt(cur, sha, FAIL, nums, reasons, flags,
                                      attempts, rdir), image=cur,
                    ceiling=ceil)
        regens += 1                                          # paid, capped
        try:
            cur = regenerate(cur, REGEN_PROMPT)
        except Exception as exc:                             # refuse, loudly
            rec = dict(rec, image=cur, reasons=rec["reasons"] + [
                ["REGEN_FAILED", "%s: %s" % (type(exc).__name__, exc)]])
            return rec


def require_receipt(path, receipt_dir=None):
    """The dispatcher block. Returns the receipt, or raises
    LipsyncPictureNotGated naming exactly what is wrong."""
    if not isinstance(path, str) or not path or not os.path.isfile(path):
        raise LipsyncPictureNotGated(
            "%s: lip-sync source picture is not a readable local file (%r); "
            "run gate_picture() on it first" % (REFUSED, path))
    sha = sha256_file(path)
    rp = os.path.join(receipt_dir or default_receipt_dir(path), sha + ".json")
    try:
        with open(rp) as f:
            rec = json.load(f)
    except (OSError, ValueError):
        raise LipsyncPictureNotGated(
            "%s: no gate receipt for %s (sha256 %s); measure it with "
            "gate_picture() before any paid lip-sync job" % (REFUSED, path, sha[:12]))
    if (rec.get("sha256") != sha or rec.get("verdict") not in ACCEPTED
            or check_numbers(rec.get("numbers") or {})[0]):
        raise LipsyncPictureNotGated(
            "%s: receipt for %s is %s, not PASS or ACCEPT_WITH_FLAG (%s)" % (
                REFUSED, path, rec.get("verdict"),
                "; ".join("%s: %s" % tuple(x) for x in rec.get("reasons", []))))
    return rec


# --- bind the upload to the measured bytes ----------------------------------

def _binding_path(sha, receipt_dir):
    return os.path.join(receipt_dir, sha + ".upload.json")


def upload_measured(path, uploader=None, receipt_dir=None):
    """Upload the EXACT measured picture and bind the URL to its sha256.
    The bytes are copied once to a private file, hashed at that moment, and the
    copy is what gets uploaded; a hash that differs from the receipt
    refuses. uploader(file) -> https URL (default: adapter_uploader()).
    Returns the URL to put in the Kling request as input.image_url."""
    rec = require_receipt(path, receipt_dir)
    rdir = receipt_dir or default_receipt_dir(path)
    tmp = tempfile.mkdtemp(prefix="lipgate-up-")
    try:
        copy = os.path.join(tmp, os.path.basename(path))
        shutil.copyfile(path, copy)
        got = sha256_file(copy)
        if got != rec["sha256"]:
            raise LipsyncPictureNotGated(
                "%s: the file changed between measuring and upload (receipt "
                "sha256 %s, upload sha256 %s); re-run gate_picture()"
                % (REFUSED, rec["sha256"][:12], got[:12]))
        url = (uploader or adapter_uploader())(copy)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not isinstance(url, str) or not url.startswith("http"):
        raise LipsyncPictureNotGated("%s: upload returned no URL (%r)" % (REFUSED, url))
    with open(_binding_path(got, rdir), "w") as f:
        json.dump({"sha256": got, "url": url}, f)
    return url


def require_upload_bound(path, url, receipt_dir=None):
    """The image URL in the Kling request must be the upload of `path`'s exact
    bytes. Raises LipsyncPictureNotGated otherwise."""
    sha = sha256_file(path)
    try:
        with open(_binding_path(sha, receipt_dir or default_receipt_dir(path))) as f:
            b = json.load(f)
    except (OSError, ValueError):
        b = {}
    if b.get("sha256") != sha or not url or b.get("url") != url:
        raise LipsyncPictureNotGated(
            "%s: image_url %r is not the upload of the measured file %s "
            "(sha256 %s); send the URL returned by upload_measured()"
            % (REFUSED, url, path, sha[:12]))


# --- default transport: skill 74 through kie_dispatch / load_governor -------

def _dispatch():
    import kie_dispatch.kie_dispatch as D    # core/ is on sys.path via PM
    return D


def adapter_uploader(adapter_path=None, runner=None):
    """uploader(file) -> URL through skill 74 `upload`. The runner is
    kie_dispatch.make_runner(), i.e. load_governor.kie_request."""
    def up(file):
        D = _dispatch()
        adapter = D.resolve_adapter(adapter_path)
        if not adapter:
            raise RuntimeError("skill 74 (74-kie-live-adapter) not found; cannot upload")
        rc, j, raw = D._call(runner or D.make_runner(), adapter,
                             ["upload", "--file", file,
                              "--upload-path", "lipsync/in", "--json"])
        url = ((j or {}).get("data") or {}).get("download_url") if isinstance(j, dict) else None
        if not url:
            raise RuntimeError("upload failed rc=%s: %s" % (rc, (raw or "")[-300:]))
        return url
    return up


class RegenerationFailed(Exception):
    pass


def make_regenerate(character_image, *, save_dir, ledger_db, run_id, logical_key,
                    estimated_cost, card_receipt, adapter_path=None, runner=None,
                    state_store=None, uploader=None, model=REGEN_MODEL,
                    production_stage=None):
    """The default PAID regeneration for gate_picture(regenerate=...).

    gpt-image-2 image-to-image from the 3D character (`character_image`, a
    local file) with the prompt gate_picture hands in (REGEN_PROMPT). Goes
    through kie_dispatch.dispatch: it reserves `estimated_cost` against the
    author's cap in the spend ledger, runs under the card gate, and every KIE
    call rides load_governor.kie_request. Each call is a new attempt id. A
    non-ok envelope raises RegenerationFailed (gate_picture then refuses).
    Real execution also requires the actual production_stage (video-generation
    or qc-retakes); constructing a repair callback never grants authority."""
    n = [0]

    def regenerate(_current, prompt):
        if (runner is None or getattr(runner, "_s75_live_runner", False)
                or production_stage is not None):
            if production_stage not in ("video-generation", "qc-retakes"):
                raise RegenerationFailed("PRODUCTION_STAGE_REQUIRED: name the actual "
                                         "video-generation or qc-retakes stage before picture repair")
        D = _dispatch()
        n[0] += 1
        url = (uploader or adapter_uploader(adapter_path, runner))(character_image)
        req = {"input": {"prompt": prompt, "input_urls": [url], "aspect_ratio": "9:16"},
               "card_receipt": card_receipt,
               "request_kind": "lipsync-picture-regeneration"}
        if production_stage is not None:
            req["production_stage"] = production_stage
        env = D.dispatch(model=model, request=req, save_dir=save_dir,
                         ledger_db=ledger_db, run_id=run_id, logical_key=logical_key,
                         attempt_id="picture-regen-%d" % n[0],
                         estimated_cost=estimated_cost, prompt=prompt,
                         adapter_path=adapter_path, runner=runner,
                         state_store=state_store, stage=production_stage or "kie")
        saved = (env.get("evidence") or {}).get("saved_paths") or []
        if env.get("outcome") != "ok" or not saved:
            raise RegenerationFailed("%s %s: %s" % (
                env.get("outcome"), env.get("reason_code"), env.get("next_action")))
        return saved[0]
    return regenerate

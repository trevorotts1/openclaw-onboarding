#!/usr/bin/env python3
"""select_agnes_video_model.py — deterministic Agnes video model router (Skill 64).

PURE / OFFLINE. No API calls, no network, no secrets. Given one JSON request
descriptor on stdin or via --payload <file.json>, emits exactly one JSON verdict
on stdout. Same input -> byte-identical output (fixed key order in the dump).

VERDICT SHAPE (exit 0 for every routing outcome; validity lives in the JSON):

  {
    "model": "agnes-video-2.5-flash" | "agnes-video-v2.0" | "unsupported",
    "valid": true | false,
    "mode": "text" | "keyframe" | "reference" | "ti2vid" | "keyframes" | null,
    "reason": "<one sentence>",
    "warnings": ["..."],
    "handoff": null | {"provider": "kie", "model_hint": null}
  }

EXIT CODES (documented contract):
  0  verdict emitted (valid may be true OR false — validity is data, not status)
  2  usage/input error (missing --payload file, empty stdin, unparseable JSON)
  3  internal error (determinism guard in --self-test only)

INPUT FIELDS (all optional; unknown/extra fields are ignored):
  explicit_model      "agnes-video-2.5-flash" | "agnes-video-v2.0" | other
  requested_seconds   int, str, or integer float ("5" / 5 / 5.0). Flash
                      seconds are vendor STRINGS "4"-"12"; V2.0 duration is
                      frame/fps-driven. Sub-4s or non-numeric values are
                      rejected (no approved model honors them as given).
  size / resolution   "720P"/"720p"/"480p"/"1080p"/"1080P" (case-insensitive)
  aspect_ratio        e.g. "16:9"
  width, height       ints — a V2.0 contract when explicit
  frame_rate          int 1-60 (V2.0)
  num_frames          int (V2.0; <=441 and 8n+1)
  negative_prompt     string (V2.0-only field)
  inference_steps     int (V2.0 num_inference_steps)
  seed                int — BOTH models accept it; never forces V2.0
  first_frame, last_frame  keyframe frame URLs (Flash keyframe mode)
  image_refs          count (int) or list of URLs — reference images
  audio_refs          count (int) or list of URLs — reference audios
  video_refs          count (int) or list of URLs — reference videos
  mode / intent       "text" | "keyframe" | "reference" | "ti2vid" | "keyframes"
  allow_kie_handoff   true | false — video-reference input hands off to KIE
                      Video (Skill 67) ONLY when this flag is true

DECISION ORDER (spec 11.4, verbatim sequence):
 1. explicit Flash  -> validate Flash; incompatible => valid=false, model STAYS
                       Flash (never a silent switch to V2.0)
 2. explicit V2.0   -> validate V2.0; incompatible => valid=false, explain
 3. video refs      -> unsupported by both Agnes models => valid=false
                       (handoff to KIE only when allow_kie_handoff=true);
                       never silently converted into image references
 4. 480p / 1080p    -> V2.0
 5. width/height    -> V2.0
 6. num_frames / frame_rate / negative_prompt / inference_steps -> V2.0
 7. requested >12s  -> V2.0 only if derivable frames <=441 on the 8n+1 grid;
                       otherwise explain tradeoff (split clips);
                       sub-4s / non-numeric seconds -> rejected (no model
                       honors the value as given)
 8. 4-12s 720P plain text -> Flash, mode "text"
 9. first/last frame 4-12s 720P -> Flash, mode "keyframe"
10. audio refs (valid Flash size/seconds) -> Flash, mode "reference"
11. up to 5 true image refs (valid Flash) -> Flash, mode "reference"
12. seed alone -> does NOT force V2.0; Flash default (warn)
13. both valid, no explicit model -> Flash default (tiebreak)

SEMANTIC GUARD: a 6-image reference request is NEVER reinterpreted as a V2.0
keyframe job (reference vs keyframe are different semantics): valid=false with
an explanatory reason. EXCEPTION: if the request EXPLICITLY states mode
keyframes/keyframe and the request fits V2.0's contract, the explicit-keyframe
path governs (equivalent to an explicit V2.0 intent).

LONG-CLIP DERIVATION (rule 7): frames = smallest 8n+1 >= requested_seconds *
frame_rate (frame_rate default 24). 18s @ 24fps = 432 raw -> 433 (8*54+1,
18.04s); 13s @ 24fps = 312 -> 313 (13.04s). If raw > 441: not achievable in one
clip (e.g. 20s @ 24fps = 480) -> valid=false; split clips or lower frame_rate.

MODEL FACTS (first-party, verified 2026-08-26; machine-readable copy in
models.json):
  Flash  agnes-video-2.5-flash — seconds STRING "4"-"12" default "5"; size ONLY
         "720P" (else HTTP 400 "size must be 720P"); aspect ratios
         [21:9,16:9,4:3,1:1,3:4,9:16]; modes text/keyframe/reference; keyframe
         = first_frame and/or last_frame only; reference = >=1 images or
         audios; images max 5 ("images length must not exceed 5"); videos NOT
         supported ("videos is not supported"); n only 1; width/height/
         num_frames/frame_rate/negative_prompt/inference_steps are NOT Flash
         fields.
  V2.0   agnes-video-v2.0 — width default 1152, height default 768;
         num_frames <=441 and 8n+1; frame_rate 1-60; num_inference_steps int;
         seed int; negative_prompt str; image single URL (i2v) or
         extra_body.image[] + extra_body.mode=keyframes; tiers 480p/720p/1080p;
         ratios [16:9,9:16,1:1,4:3,3:4]; seconds = num_frames/frame_rate.

--self-test: runs the fixture suite (spec 18.5 + semantic guards), prints one
line per fixture, exits 0 only if ALL pass.
"""

import json
import os
import sys

FLASH = "agnes-video-2.5-flash"
V20 = "agnes-video-v2.0"
UNSUPPORTED = "unsupported"

FLASH_SECONDS = {"4", "5", "6", "7", "8", "9", "10", "11", "12"}
FLASH_RATIOS = ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
V20_SIZES = {"480p", "720p", "1080p"}
V20_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4"]
V20_MAX_FRAMES = 441
DEFAULT_FPS = 24


class Verdict(object):
    """Verdict collector. to_json() is deterministic: fixed key order."""

    def __init__(self):
        self.model = None
        self.valid = None
        self.mode = None
        self.reason = None
        self.warnings = []
        self.handoff = None

    def to_json(self):
        return json.dumps({
            "model": self.model,
            "valid": self.valid,
            "mode": self.mode,
            "reason": self.reason,
            "warnings": self.warnings,
            "handoff": self.handoff,
        })


# ── input coercion helpers ────────────────────────────────────────────────

def as_int(value):
    """int(value) or None on parse failure. Bools rejected (True is not a count)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return int(s)
        return None
    return None


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def count_refs(value):
    """Reference count from an int, or the non-empty length of a list of URLs."""
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, (list, tuple)):
        return len([u for u in value if u is not None and str(u).strip() != ""])
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return int(s)
        if s.startswith("http"):
            return 1
        return 0
    return 0


def norm_size(raw):
    """Normalize size/resolution case-insensitively to a canonical token."""
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip().upper()
        if s in ("720P", "720"):
            return "720P"
        if s in ("480P", "480"):
            return "480p"
        if s in ("1080P", "1080"):
            return "1080p"
        return raw.strip()
    return raw


def norm_seconds(raw):
    """Flash seconds are vendor STRINGS "4"-"12". Accept int/str/integer float;
    return canonical digit string, or None when not numeric."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        s = raw.strip()
        return s if s.isdigit() else None
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return None


def seconds_tuple(raw):
    """(sec_str, sec_int) or (None, None). Single numerical source of truth for
    requested_seconds: the canonical digit string plus its int value."""
    sec_str = norm_seconds(raw)
    if sec_str is None:
        return None, None
    return sec_str, int(sec_str)


def grid_ceiling(raw_frames):
    """Smallest num_frames on the 8n+1 grid >= raw_frames, or None if > 441."""
    if raw_frames is None:
        return None
    if raw_frames > V20_MAX_FRAMES:
        return None
    if (raw_frames - 1) % 8 == 0:
        return raw_frames
    return ((raw_frames + 7) // 8) * 8 + 1


# ── Flash validation (decision step 1) ────────────────────────────────────

def validate_flash(p, v):
    """Explicit Flash request. On ANY incompatibility: v.model STAYS Flash and
    v.valid=False (spec: never silently switch to V2.0)."""

    def fail(reason):
        v.model = FLASH
        v.valid = False
        v.reason = reason
        return v

    size = norm_size(p.get("size") or p.get("resolution") or None)
    if size is not None and size != "720P":
        return fail(
            "explicit_model agnes-video-2.5-flash is incompatible with size %s: "
            "Flash takes size 720P only (480p/1080p are V2.0 tiers) — explicit "
            "model wins over auto-correction" % size)

    sec = norm_seconds(p.get("requested_seconds"))
    if sec is not None and sec not in FLASH_SECONDS:
        return fail(
            "explicit_model agnes-video-2.5-flash is incompatible with seconds "
            "%s: Flash seconds are the string range 4-12 — no silent switch" % sec)

    ar = p.get("aspect_ratio")
    if ar is not None and ar not in FLASH_RATIOS:
        return fail(
            "explicit_model agnes-video-2.5-flash is incompatible with "
            "aspect_ratio %s: Flash ratios are [21:9,16:9,4:3,1:1,3:4,9:16]" % ar)

    for field in ("num_frames", "frame_rate", "inference_steps", "negative_prompt"):
        if p.get(field) is not None:
            return fail(
                "explicit_model agnes-video-2.5-flash is incompatible: %s is "
                "not a Flash field (Flash takes seconds/size/aspect_ratio/seed/"
                "n/first_frame/last_frame/images/audios) — no silent switch"
                % field)
    if p.get("width") is not None or p.get("height") is not None:
        return fail(
            "explicit_model agnes-video-2.5-flash is incompatible: width/height "
            "are not Flash fields (Flash is size 720P only) — no silent switch")

    first = p.get("first_frame")
    last = p.get("last_frame")
    img_count = count_refs(p.get("image_refs"))
    aud_count = count_refs(p.get("audio_refs"))
    vid_count = count_refs(p.get("video_refs"))
    mode = str(p.get("mode") or p.get("intent") or "").lower()

    has_frames = bool(first or last)
    has_refs_img = img_count > 0
    has_refs_aud = aud_count > 0

    if vid_count > 0:
        return fail(
            "explicit_model agnes-video-2.5-flash is incompatible: videos is "
            "not supported by Flash (vendor HTTP 400) — no silent switch")

    if has_frames and (has_refs_img or has_refs_aud):
        return fail(
            "explicit_model agnes-video-2.5-flash is incompatible: keyframe "
            "mode may not combine first_frame/last_frame with images or audios")

    if not has_frames and not has_refs_img and not has_refs_aud \
            and mode not in ("text", ""):
        return fail(
            "explicit_model agnes-video-2.5-flash is incompatible with mode "
            "%s: text mode takes no frames/images/audios/videos" % mode)

    if img_count > 5:
        return fail(
            "explicit_model agnes-video-2.5-flash is incompatible: %d image refs "
            "exceed Flash max 5 (vendor HTTP 400 'images length must not exceed "
            "5')" % img_count)

    v.model = FLASH
    v.valid = True
    if has_frames:
        v.mode = "keyframe"
        v.reason = "explicit Flash: 720P keyframe request (first_frame or last_frame) is Flash-compatible"
    elif has_refs_img or has_refs_aud:
        v.mode = "reference"
        v.reason = ("explicit Flash: 720P reference request (%s) is Flash-compatible"
                    % ("images" if has_refs_img else "audios"))
    else:
        v.mode = "text"
        v.reason = "explicit Flash: 720P text request is Flash-compatible"
    return v


# ── V2.0 validation and routing (decision steps 2, 4, 5, 6, 7) ────────────

def route_v20(p, v, via_step):
    """V2.0 path used by explicit V2.0 and by auto-routes (rules 4-7).
    Derives num_frames when seconds > 12 (rule 7); validates otherwise."""
    sec_str, sec = seconds_tuple(p.get("requested_seconds"))
    has_num_frames = p.get("num_frames") is not None
    explicit = str(p.get("explicit_model", "") or "").strip() == V20

    # Rule 7 derivation: seconds > 12 with no explicit num_frames.
    if sec is not None and sec > 12 and not has_num_frames:
        fps = as_int(p.get("frame_rate")) or DEFAULT_FPS
        # fps may be given as a V2.0 field (rule 6) and must be in 1-60.
        if not 1 <= fps <= 60:
            v.model = V20
            v.valid = False
            v.reason = ("%s: frame_rate %r invalid — V2.0 range is 1-60"
                        % (via_step, p.get("frame_rate")))
            return v
        raw = sec * fps
        frames = grid_ceiling(raw)
        if frames is None:
            v.model = UNSUPPORTED
            v.valid = False
            v.reason = ("requested_seconds %d at frame_rate %d needs %d frames, "
                        "above the V2.0 cap of %d — not achievable in one clip; "
                        "split into multiple clips or lower frame_rate"
                        % (sec, fps, int(raw), V20_MAX_FRAMES))
            return v
        actual = frames / float(fps)
        p = dict(p)
        p["num_frames"] = frames
        p["frame_rate"] = fps
        v.model = V20
        v.valid = True
        v.mode = "ti2vid"
        v.reason = ("requested_seconds %d exceeds Flash max 12 — V2.0 with "
                    "derived num_frames %d at frame_rate %d (%.2fs) within the "
                    "%d-frame cap on the 8n+1 grid" % (sec, frames, fps, actual,
                                                       V20_MAX_FRAMES))
        if actual < sec - 0.01:
            v.warnings.append(
                "derived %d frames at %d fps yields %.2fs, slightly under "
                "requested %ds — request a longer clip or split" % (frames, fps,
                                                                    actual, sec))
        return v

    # Non-derived path: validate the V2.0 contract.
    v.model = V20
    v.valid = True

    w = p.get("width")
    h = p.get("height")
    if w is not None and (as_int(w) is None or w <= 0):
        v.valid = False
        v.reason = "%s: width %r invalid (positive integer expected; vendor default 1152)" % (via_step, w)
        return v
    if h is not None and (as_int(h) is None or h <= 0):
        v.valid = False
        v.reason = "%s: height %r invalid (positive integer expected; vendor default 768)" % (via_step, h)
        return v

    nf = as_int(p.get("num_frames"))
    if p.get("num_frames") is not None and nf is None:
        v.valid = False
        v.reason = "%s: num_frames %r is not an integer" % (via_step, p.get("num_frames"))
        return v
    if nf is not None and (nf > V20_MAX_FRAMES or nf % 8 != 1):
        v.valid = False
        v.reason = ("%s: num_frames %d invalid — must be <= %d AND on the 8n+1 "
                    "grid (e.g. 81, 121, 241, 441)" % (via_step, nf, V20_MAX_FRAMES))
        return v

    fr = as_int(p.get("frame_rate"))
    if p.get("frame_rate") is not None and (fr is None or not 1 <= fr <= 60):
        v.valid = False
        v.reason = "%s: frame_rate %r invalid — V2.0 range is 1-60" % (via_step, p.get("frame_rate"))
        return v

    steps = p.get("inference_steps")
    if steps is not None and as_int(steps) is None:
        v.valid = False
        v.reason = "%s: inference_steps %r is not an integer" % (via_step, steps)
        return v

    seed = p.get("seed")
    if seed is not None and as_int(seed) is None:
        v.valid = False
        v.reason = "%s: seed %r is not an integer" % (via_step, seed)
        return v

    size = norm_size(p.get("size") or p.get("resolution") or None)
    # norm_size canonicalizes 720p/720P -> "720P" (the Flash spelling); V2.0's
    # tier spelling is "720p" — same tier, map before the membership check.
    if size == "720P":
        size = "720p"
    if size is not None and size not in V20_SIZES:
        v.valid = False
        v.reason = "%s: size %s invalid — V2.0 tiers are 480p/720p/1080p" % (via_step, size)
        return v

    ar = p.get("aspect_ratio")
    if ar is not None and ar not in V20_RATIOS:
        v.valid = False
        v.reason = "%s: aspect_ratio %s not in V2.0's [16:9,9:16,1:1,4:3,3:4]" % (via_step, ar)
        return v

    # V2.0 has no seconds enum. Explicit V2.0 with a bare seconds value and no
    # num_frames cannot honor the requested duration deterministically: explain
    # (rule: no silent switch, no fabricated frames). Auto-routes
    # (size/fields-led) accept the vendor's normalization path with a warning.
    if sec is not None and nf is None and explicit:
        v.valid = False
        v.reason = ("explicit V2.0: requested_seconds %s without num_frames — "
                    "V2.0 duration is frame/fps-driven; provide num_frames "
                    "(<= %d, 8n+1)" % (sec, V20_MAX_FRAMES))
        return v

    mode = str(p.get("mode") or p.get("intent") or "").lower()
    if mode in ("keyframe", "keyframes"):
        v.mode = "keyframes"
    elif mode in ("text", "ti2vid", "i2v", "image-to-video"):
        v.mode = "ti2vid"
    else:
        v.mode = "ti2vid"
    v.reason = "%s: V2.0 request validated" % via_step
    if nf is not None and fr is not None:
        v.reason += " (num_frames %d, frame_rate %d)" % (nf, fr)
    elif nf is not None:
        v.reason += " (num_frames %d)" % nf
    if sec is not None and nf is None and not explicit:
        v.warnings.append(
            "no num_frames: V2.0 duration is frame/fps-driven and will be "
            "normalized by the service — read returned seconds/size_mapping")
    return v


# ── main router ───────────────────────────────────────────────────────────

def route(p, v):
    explicit = str(p.get("explicit_model", "") or "").strip()

    # STEP 1: explicit Flash — validate; model STAYS Flash on incompatibility.
    if explicit == FLASH:
        return validate_flash(p, v)

    # STEP 2: explicit V2.0 — validate; explain on incompatibility.
    if explicit == V20:
        return route_v20(p, v, "explicit V2.0")

    if explicit and explicit not in (FLASH, V20):
        v.model = UNSUPPORTED
        v.valid = False
        v.reason = ("explicit_model %s is not an approved Agnes video model "
                    "(approved: agnes-video-2.5-flash, agnes-video-v2.0) — "
                    "never auto-select full agnes-video-2.5" % explicit)
        return v

    vid_count = count_refs(p.get("video_refs"))
    img_count = count_refs(p.get("image_refs"))
    aud_count = count_refs(p.get("audio_refs"))
    mode = str(p.get("mode") or p.get("intent") or "").lower()

    # STEP 3: video-reference input — neither Agnes model supports it.
    if vid_count > 0:
        v.model = UNSUPPORTED
        v.valid = False
        v.mode = None
        if as_bool(p.get("allow_kie_handoff")):
            v.handoff = {"provider": "kie", "model_hint": None}
            v.reason = ("%d video reference(s): neither agnes video model "
                        "supports video references — handed off to KIE Video; "
                        "video refs are never silently converted to image refs"
                        % vid_count)
        else:
            v.reason = ("%d video reference(s): neither agnes-video-2.5-flash "
                        "nor agnes-video-v2.0 supports video references (vendor "
                        "HTTP 400 'videos is not supported') — use KIE Video; "
                        "not silently converted to image references" % vid_count)
        return v

    # SEMANTIC GUARD: 6+ image refs must not become a V2.0 keyframe job unless
    # the request itself explicitly asks for keyframes (then V2.0 governs).
    if img_count > 5 and mode not in ("keyframe", "keyframes"):
        v.model = UNSUPPORTED
        v.valid = False
        v.mode = None
        v.reason = ("%d image refs exceed Flash max 5; choosing V2.0 keyframes "
                    "would change the semantics (reference vs keyframe) — do "
                    "not silently convert; re-ask or use KIE Video" % img_count)
        return v
    if img_count > 5 and mode in ("keyframe", "keyframes"):
        return route_v20(p, v, "explicit keyframes request")

    size = norm_size(p.get("size") or p.get("resolution") or None)

    # STEP 4: 480p / 1080p -> V2.0
    if size in ("480p", "1080p"):
        return route_v20(p, v, "480p/1080p requirement")

    # STEP 5: explicit width/height -> V2.0
    if p.get("width") is not None or p.get("height") is not None:
        return route_v20(p, v, "explicit width/height")

    # STEP 6 + 7: V2.0-only fields, or seconds > 12 (derivation inside).
    has_v20_field = (p.get("num_frames") is not None or p.get("frame_rate") is not None
                     or p.get("negative_prompt") is not None
                     or p.get("inference_steps") is not None)
    # Numerical source of truth: canonical string + int for requested_seconds.
    sec_str, sec = seconds_tuple(p.get("requested_seconds"))
    if has_v20_field or (sec is not None and sec > 12):
        step_label = "V2.0-only field present" if has_v20_field else "requested > 12s"
        return route_v20(p, v, step_label)

    has_frames = bool(p.get("first_frame") or p.get("last_frame"))
    sec_str = norm_seconds(p.get("requested_seconds"))
    # Seconds guard: a numeric requested_seconds is a Flash enum value ("4"-"12")
    # or a >12s value routed to V2.0 derivation above. Anything else (sub-4s,
    # non-numeric) is honored by NO approved model as given — reject, do not
    # silently fall back to the Flash default seconds.
    if p.get("requested_seconds") is not None and sec_str is None:
        v.model = UNSUPPORTED
        v.valid = False
        v.reason = ("requested_seconds %r is not a number — Flash seconds "
                    "are the string range 4-12; V2.0 duration is "
                    "frame/fps-driven" % p.get("requested_seconds"))
        return v
    if p.get("requested_seconds") is not None and int(sec_str) < 4:
        v.model = UNSUPPORTED
        v.valid = False
        v.reason = ("requested_seconds %s below Flash minimum 4 — Flash "
                    "seconds are the string range 4-12; V2.0 duration is "
                    "frame/fps-driven (num_frames/frame_rate)" % sec_str)
        return v
    flash_sec_ok = sec_str is None or sec_str in FLASH_SECONDS
    size_ok_720 = size is None or size == "720P"

    # STEP 8: 4-12s 720P ordinary text -> Flash
    if flash_sec_ok and size_ok_720 and not has_frames \
            and img_count == 0 and aud_count == 0:
        v.model = FLASH
        v.valid = True
        v.mode = "text"
        v.reason = ("4-12s 720P ordinary text request is Flash-compatible "
                    "(Flash default)")
        if sec_str is None:
            v.warnings.append('no requested_seconds — Flash default seconds is "5"')
        if p.get("seed") is not None:
            # spec 11.4 rule 12: seed alone never forces V2.0 — warn
            v.warnings.append("seed with no explicit model — Flash default "
                              "applied (both models accept seed; it does not "
                              "force V2.0)")
        return v

    # STEP 9: first/last frame 4-12s 720P -> Flash keyframe
    if has_frames and flash_sec_ok and size_ok_720 and img_count == 0 and aud_count == 0:
        v.model = FLASH
        v.valid = True
        v.mode = "keyframe"
        v.reason = ("first_frame/last_frame with 4-12s 720P is Flash keyframe "
                    "compatible")
        return v

    # STEP 10: audio refs -> Flash reference
    if aud_count > 0 and img_count == 0 and flash_sec_ok and size_ok_720:
        v.model = FLASH
        v.valid = True
        v.mode = "reference"
        v.reason = ("audio reference request (4-12s/720P compatible) is Flash "
                    "reference mode")
        return v

    # STEP 11: up to 5 true image refs -> Flash reference
    if 0 < img_count <= 5 and flash_sec_ok and size_ok_720:
        v.model = FLASH
        v.valid = True
        v.mode = "reference"
        v.reason = ("%d image reference(s) with Flash-compatible size/seconds "
                    "-> Flash reference mode" % img_count)
        return v

    # STEP 12: seed ALONE -> does not force V2.0; Flash default (warn)
    if p.get("seed") is not None:
        v.model = FLASH
        v.valid = True
        v.mode = "text"
        v.reason = ("seed-only request: both models accept seed, no V2.0-only "
                    "field present — Flash default applied")
        v.warnings.append("seed with no explicit model — Flash default applied "
                          "(seed does not force V2.0)")
        return v

    # STEP 13: both valid, no explicit model -> Flash default (tiebreak)
    v.model = FLASH
    v.valid = True
    v.mode = "text"
    v.reason = ("no explicit model and no V2.0-only field: Flash default "
                "(tiebreak when both models are valid)")
    return v


# ── self-test fixture suite (spec 18.5 + semantic guards) ─────────────────

GOLDEN = [
    # spec 18.5 fixtures
    ({"requested_seconds": "5", "size": "720P", "intent": "text"},
     FLASH, True, "text", "Flash-compatible", None),
    ({"requested_seconds": "10", "size": "720P", "first_frame": "https://x/a.jpg"},
     FLASH, True, "keyframe", "keyframe", None),
    ({"requested_seconds": "5", "size": "720P", "audio_refs": 1},
     FLASH, True, "reference", "audio", None),
    ({"size": "1080p", "intent": "text"},
     V20, True, "ti2vid", "1080p", None),
    ({"num_frames": 121, "frame_rate": 24},
     V20, True, "ti2vid", "V2.0-only field", None),
    ({"requested_seconds": 18, "frame_rate": 24, "size": "1080p"},
     V20, True, "ti2vid", "441", None),
    ({"video_refs": 1},
     UNSUPPORTED, False, None, "video reference", None),
    ({"explicit_model": "agnes-video-2.5-flash", "size": "1080p"},
     FLASH, False, None, "explicit model wins over auto-correction", None),
    # semantic guard: 6 images is NOT auto-reinterpreted as V2.0 keyframes
    ({"requested_seconds": "5", "size": "720P", "image_refs": 6},
     UNSUPPORTED, False, None, "semantics", None),
    # explicit keyframes + V2.0-legal frames: explicit mode governs
    ({"num_frames": 121, "image_refs": 6, "mode": "keyframes"},
     V20, True, "keyframes", "keyframes", None),
    # 13s -> V2.0 derivation attempt
    ({"requested_seconds": 13, "size": "720P"},
     V20, True, "ti2vid", "derived", None),
    # derivation impossible: 20s @ 24fps = 480 > 441
    ({"requested_seconds": 20, "frame_rate": 24, "size": "720P"},
     UNSUPPORTED, False, None, "split", None),
    # seed alone -> Flash default with warning (rule 12: seed never forces V2.0)
    ({"requested_seconds": "7", "size": "720P", "seed": 42},
     FLASH, True, "text", "Flash default", "seed with no explicit model"),
    # explicit V2.0 + negative_prompt -> V2.0 valid
    ({"explicit_model": "agnes-video-v2.0", "negative_prompt": "blurry",
      "num_frames": 121, "frame_rate": 24},
     V20, True, "ti2vid", "validated", None),
    # explicit Flash + num_frames -> invalid, model STAYS Flash
    ({"explicit_model": "agnes-video-2.5-flash", "num_frames": 121},
     FLASH, False, None, "not a Flash field", None),
    # video ref handoff only when permitted
    ({"video_refs": 1, "allow_kie_handoff": True},
     UNSUPPORTED, False, None, "handed off to KIE", None),
    # Flash seconds enum: 13 invalid under explicit Flash
    ({"explicit_model": "agnes-video-2.5-flash", "requested_seconds": "13"},
     FLASH, False, None, "4-12", None),
    # V2.0 off-grid num_frames invalid under explicit V2.0
    ({"explicit_model": "agnes-video-v2.0", "num_frames": 120},
     V20, False, None, "8n+1", None),
    # V2.0 at max frames valid
    ({"num_frames": 441, "frame_rate": 24},
     V20, True, "ti2vid", "validated", None),
    # exactly 5 true image refs valid Flash
    ({"requested_seconds": "6", "size": "720P", "image_refs": 5},
     FLASH, True, "reference", "5 image reference", None),
    # unknown explicit model: never auto-selects full paid agnes-video-2.5
    ({"explicit_model": "agnes-video-2.5"},
     UNSUPPORTED, False, None, "approved", None),
    # regression: V2.0 accepts size 720p (case-insensitive tier spelling)
    ({"num_frames": 81, "frame_rate": 24, "size": "720p"},
     V20, True, "ti2vid", "validated", None),
    ({"num_frames": 81, "frame_rate": 24, "size": "720P"},
     V20, True, "ti2vid", "validated", None),
    # regression: explicit V2.0 + bare seconds (no num_frames) is invalid —
    # V2.0 has no seconds enum; never silently fabricate frames
    ({"explicit_model": "agnes-video-v2.0", "requested_seconds": "5", "size": "720P"},
     V20, False, None, "frame/fps-driven", None),
    # regression: sub-4s seconds is below Flash minimum — reject, do not
    # silently fall back to the Flash default seconds "5"
    ({"requested_seconds": 3},
     UNSUPPORTED, False, None, "below Flash minimum", None),
    # regression: non-numeric seconds is honored by no approved model
    ({"requested_seconds": "five", "size": "720P"},
     UNSUPPORTED, False, None, "not a number", None),
    # regression: integer-float seconds equals its int form (5.0 == "5" -> Flash)
    ({"requested_seconds": 5.0, "size": "720P"},
     FLASH, True, "text", "Flash-compatible", None),
    # regression: integer-float >12s drives V2.0 derivation (18.0 == 18)
    ({"requested_seconds": 18.0, "frame_rate": 24},
     V20, True, "ti2vid", "derived", None),
]


def _route_payload(payload):
    v = Verdict()
    try:
        route(payload, v)
    except Exception as exc:  # determinism guard; should never fire
        v.model = UNSUPPORTED
        v.valid = False
        v.reason = "internal router error: %s" % exc
    if v.reason is None:
        v.reason = "no decision rule matched"
    return v.to_json(), v


def run_self_test():
    failures = []
    for idx, (payload, model, valid, mode, substr, warn_sub) in enumerate(GOLDEN, 1):
        out, v = _route_payload(payload)
        problems = []
        if v.model != model:
            problems.append("model %r != %r" % (v.model, model))
        if v.valid != valid:
            problems.append("valid %r != %r" % (v.valid, valid))
        if mode is not None and v.mode != mode:
            problems.append("mode %r != %r" % (v.mode, mode))
        if substr and substr.lower() not in v.reason.lower():
            problems.append("reason %r missing %r" % (v.reason, substr))
        if warn_sub and not any(warn_sub.lower() in w.lower() for w in v.warnings):
            problems.append("warnings %r missing %r" % (v.warnings, warn_sub))
        # determinism: same payload twice -> byte-identical JSON
        out2, _ = _route_payload(payload)
        if out != out2:
            problems.append("non-deterministic output")
        if problems:
            failures.append(idx)
            print("  FAIL #%d %s -> %s" % (idx, json.dumps(payload), "; ".join(problems)))
        else:
            print("  PASS #%d %s -> %s" % (idx, json.dumps(payload), out))
    if failures:
        print("self-test: %d/%d failed" % (len(failures), len(GOLDEN)))
        return 1
    print("self-test: %d/%d passed" % (len(GOLDEN), len(GOLDEN)))
    return 0


def main(argv):
    payload_raw = None
    if "--self-test" in argv:
        return run_self_test()
    if "--payload" in argv:
        if "--self-test" in argv:
            return 2
        i = argv.index("--payload")
        if i + 1 >= len(argv):
            print("usage: select_agnes_video_model.py [--payload <file.json> | reads stdin]",
                  file=sys.stderr)
            return 2
        path = argv[i + 1]
        if not os.path.isfile(path):
            print("error: --payload file not found: %s" % path, file=sys.stderr)
            return 2
        with open(path, "r", encoding="utf-8") as fh:
            payload_raw = fh.read()
    else:
        payload_raw = sys.stdin.read()
    payload_raw = (payload_raw or "").strip()
    if not payload_raw:
        print("error: no input JSON (pass --payload <file.json> or pipe stdin)",
              file=sys.stderr)
        return 2
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError as exc:
        print("error: unparseable JSON: %s" % exc, file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("error: payload must be a JSON object", file=sys.stderr)
        return 2
    out, _ = _route_payload(payload)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

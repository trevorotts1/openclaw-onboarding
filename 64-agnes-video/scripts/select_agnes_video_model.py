#!/usr/bin/env python3
"""select_agnes_video_model.py — deterministic Agnes video model router (Skill 64).

PURE / OFFLINE. No API calls, no network, no secrets. Given one JSON request
descriptor on stdin or via --payload <file.json>, emits exactly one JSON verdict
on stdout. Same input -> byte-identical output (fixed key order in the dump).

VERDICT SHAPE (exit 0 for every routing outcome; validity lives in the JSON):

  {
    "model": "agnes-video-2.5-flash" | "unsupported",
    "valid": true | false,
    "mode": "text" | "keyframe" | "reference" | null,
    "reason": "<one sentence>",
    "warnings": ["..."],
    "handoff": null | {"provider": "kie", "model_hint": null}
  }

EXIT CODES (documented contract):
  0  verdict emitted (valid may be true OR false — validity is data, not status)
  2  usage/input error (missing --payload file, empty stdin, unparseable JSON)
  3  internal error (determinism guard in --self-test only)

INPUT FIELDS (all optional; unknown/extra fields are ignored):
  explicit_model      "agnes-video-2.5-flash" | "agnes-video-v2.0" (RETIRED —
                      always refused) | anything else (refused)
  requested_seconds   int, str, or integer float ("5" / 5 / 5.0). Flash
                      seconds are vendor STRINGS "4"-"12"; over 12 s is
                      refused with "split into clips of 12 s or less" (the
                      only Agnes model that took longer clips, v2.0, was
                      retired 2026-09-25). Sub-4s or non-numeric values are
                      rejected (no approved model honors them as given).
  size / resolution   "720P"/"720p" only; "480p"/"1080p" are refused (they
                      were V2.0 tiers — V2.0 retired 2026-09-25)
  aspect_ratio        e.g. "16:9"
  width, height       V2.0-only contract — refused (Flash is size 720P only)
  frame_rate          V2.0-only — refused
  num_frames          V2.0-only — refused
  negative_prompt     V2.0-only — refused
  inference_steps     V2.0-only — refused
  seed                int — accepted; never forces a V2.0 route
  first_frame, last_frame  keyframe frame URLs (Flash keyframe mode)
  image_refs          count (int) or list of URLs — reference images
  audio_refs          count (int) or list of URLs — reference audios
  video_refs          count (int) or list of URLs — reference videos
  mode / intent       "text" | "keyframe" | "reference" ("ti2vid" and
                      "keyframes" were V2.0 modes — V2.0 is retired, so they
                      no longer route anywhere)
  allow_kie_handoff   true | false — video-reference input hands off to KIE
                      Video (Skill 67) ONLY when this flag is true

DECISION ORDER (spec 11.4 sequence; v2.0 retired by the vendor 2026-09-25):
 1. explicit Flash  -> validate Flash; incompatible => valid=false, model STAYS
                       Flash (never a silent switch to another model)
 2. explicit v2.0   -> valid=false: the vendor retired it 2026-09-25
 3. any other name  -> valid=false (the full paid agnes-video-2.5 is never
                       auto-selected either)
 4. video refs      -> unsupported by Agnes => valid=false
                       (handoff to KIE only when allow_kie_handoff=true);
                       never silently converted into image references
 5. more than 5 image refs -> valid=false (Flash max 5; the old V2.0-keyframe
                       fallback is gone with V2.0 — reference vs keyframe are
                       different semantics anyway)
 6. requested >12s  -> valid=false, "split into clips of 12 s or less"
                       (sub-4s / non-numeric seconds -> rejected: no model
                       honors the value as given)
 7. 480p / 1080p, width/height, num_frames / frame_rate / negative_prompt /
    inference_steps -> valid=false (V2.0-only surface; V2.0 retired 2026-09-25)
 8. 4-12s 720P plain text -> Flash, mode "text"
 9. first/last frame 4-12s 720P -> Flash, mode "keyframe"
10. audio refs (valid Flash size/seconds) -> Flash, mode "reference"
11. up to 5 true image refs (valid Flash) -> Flash, mode "reference"
12. seed alone -> Flash default (warn; seed never forces another model)
13. nothing else said, no explicit model -> Flash default (tiebreak)

SEMANTIC GUARD: a 6-image reference request is NEVER reinterpreted as a
keyframe job (reference vs keyframe are different semantics): valid=false with
an explanatory reason. The former exception — an explicit mode keyframes
request falling through to V2.0 — no longer applies: V2.0 was retired
2026-09-25, so no approved Agnes video model takes more than 5 image refs.

RETIRED MODEL: agnes-video-v2.0 was retired by the vendor on 2026-09-25
23:59:59 (UTC+8) — "Migrate to the Agnes Video 2.5 series"
(https://wiki.agnes-ai.com/en/docs/agnes-video-v20.md). The router never
selects it: an explicit v2.0 name, a v2.0-only request surface, or any
requested_seconds over 12 all return valid=false. The only approved Agnes
video model is agnes-video-2.5-flash (720P, seconds "4"-"12").

MODEL FACTS (first-party: Flash verified 2026-08-26, registry refreshed
2026-10-15; machine-readable copy in models.json):
  Flash  agnes-video-2.5-flash — seconds STRING "4"-"12" default "5"; size ONLY
         "720P" (else HTTP 400 "size must be 720P"); aspect ratios
         [21:9,16:9,4:3,1:1,3:4,9:16]; modes text/keyframe/reference; keyframe
         = first_frame and/or last_frame only; reference = >=1 images or
         audios; images max 5 ("images length must not exceed 5"); videos NOT
         supported ("videos is not supported"); n only 1; width/height/
         num_frames/frame_rate/negative_prompt/inference_steps are NOT Flash
         fields.
  V2.0   agnes-video-v2.0 — RETIRED by the vendor 2026-09-25 23:59:59 (UTC+8).
         Its surface (width/height, num_frames 8n+1 <= 441, frame_rate 1-60,
         inference_steps, negative_prompt, 480p/720p/1080p tiers,
         seconds = num_frames/frame_rate) is kept here only so the router can
         NAME and refuse it; nothing routes to it and nothing selects it.

--self-test: runs the fixture suite (spec 18.5 + semantic guards), prints one
line per fixture, exits 0 only if ALL pass.
"""

import json
import os
import sys

FLASH = "agnes-video-2.5-flash"
V20 = "agnes-video-v2.0"          # RETIRED — named only so the router can refuse it
UNSUPPORTED = "unsupported"

FLASH_SECONDS = {"4", "5", "6", "7", "8", "9", "10", "11", "12"}
FLASH_RATIOS = ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
V20_RETIRED_ON = "2026-09-25"
V20_RETIRED_URL = "https://wiki.agnes-ai.com/en/docs/agnes-video-v20.md"
SPLIT_ADVICE = "split into clips of 12 s or less"


def v20_refusal(detail):
    """One sentence: what the request asked for, and why no approved model gives it."""
    return ("%s; agnes-video-v2.0 — the only Agnes video model with that "
            "surface — was retired by the vendor on %s 23:59:59 (UTC+8), so "
            "the only approved model is %s (size 720P, seconds \"4\"-\"12\") [%s]"
            % (detail, V20_RETIRED_ON, FLASH, V20_RETIRED_URL))


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


# ── Flash validation (decision step 1) ────────────────────────────────────

def validate_flash(p, v):
    """Explicit Flash request. On ANY incompatibility: v.model STAYS Flash and
    v.valid=False (spec: never silently switch to another model)."""

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
        advice = ("%s" % SPLIT_ADVICE) if int(sec) > 12 else \
            "no approved model honors that value as given"
        return fail(
            "explicit_model agnes-video-2.5-flash is incompatible with seconds "
            "%s: Flash seconds are the string range 4-12 — no silent switch; "
            "%s" % (sec, advice))

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


# ── the retired model's request surface (decision steps 2, 4-7) ──


def refuse_v20(p, v, detail):
    """A v2.0-only request surface: no approved model serves it any more."""
    v.model = UNSUPPORTED
    v.valid = False
    v.mode = None
    v.reason = v20_refusal(detail)
    return v


# ── main router ───────────────────────────────────────────────────────────

def route(p, v):
    explicit = str(p.get("explicit_model", "") or "").strip()

    # STEP 1: explicit Flash — validate; model STAYS Flash on incompatibility.
    if explicit == FLASH:
        return validate_flash(p, v)

    # STEP 2: explicit v2.0 — retired by the vendor 2026-09-25; always refused.
    if explicit == V20:
        v.model = UNSUPPORTED
        v.valid = False
        v.mode = None
        v.reason = v20_refusal("explicit_model agnes-video-v2.0 is no longer available")
        return v

    if explicit:
        v.model = UNSUPPORTED
        v.valid = False
        v.reason = ("explicit_model %s is not an approved Agnes video model "
                    "(the only approved model is agnes-video-2.5-flash; "
                    "agnes-video-v2.0 was retired on %s) — never auto-select "
                    "full agnes-video-2.5" % (explicit, V20_RETIRED_ON))
        return v

    vid_count = count_refs(p.get("video_refs"))
    img_count = count_refs(p.get("image_refs"))
    aud_count = count_refs(p.get("audio_refs"))

    # STEP 4: video-reference input — no Agnes model supports it.
    if vid_count > 0:
        v.model = UNSUPPORTED
        v.valid = False
        v.mode = None
        if as_bool(p.get("allow_kie_handoff")):
            v.handoff = {"provider": "kie", "model_hint": None}
            v.reason = ("%d video reference(s): no Agnes video model "
                        "supports video references — handed off to KIE Video; "
                        "video refs are never silently converted to image refs"
                        % vid_count)
        else:
            v.reason = ("%d video reference(s): no approved Agnes video model "
                        "supports video references (vendor HTTP 400 'videos is "
                        "not supported') — use KIE Video; not silently "
                        "converted to image references" % vid_count)
        return v

    # STEP 5: SEMANTIC GUARD — 6+ image refs are never reinterpreted as a
    # keyframe job (reference vs keyframe are different semantics), and with
    # v2.0 retired no approved model takes more than 5 image refs at all.
    if img_count > 5:
        v.model = UNSUPPORTED
        v.valid = False
        v.mode = None
        v.reason = ("%d image refs exceed Flash max 5 (vendor HTTP 400 'images "
                    "length must not exceed 5'); re-reading them as keyframes "
                    "would change the semantics (reference vs keyframe) and the "
                    "only model that did that, agnes-video-v2.0, was retired on "
                    "%s — use at most 5 image refs, or use KIE Video"
                    % (img_count, V20_RETIRED_ON))
        return v

    size = norm_size(p.get("size") or p.get("resolution") or None)
    # Numerical source of truth: canonical string + int for requested_seconds.
    sec_str, sec = seconds_tuple(p.get("requested_seconds"))

    # STEP 6: requested_seconds > 12 — no approved model takes a longer clip.
    if sec is not None and sec > 12:
        v.model = UNSUPPORTED
        v.valid = False
        v.mode = None
        v.reason = ("requested_seconds %d exceeds the Flash maximum of 12 s, "
                    "and agnes-video-v2.0 — the only Agnes model that took a "
                    "longer clip — was retired by the vendor on %s — %s"
                    % (sec, V20_RETIRED_ON, SPLIT_ADVICE))
        return v

    # STEP 7: the v2.0-only request surface.
    if size in ("480p", "1080p"):
        return refuse_v20(p, v, "size %s is a V2.0 tier and Flash takes 720P only" % size)
    if p.get("width") is not None or p.get("height") is not None:
        return refuse_v20(p, v, "width/height are V2.0-only fields and Flash takes size 720P only")
    for field in ("num_frames", "frame_rate", "negative_prompt", "inference_steps"):
        if p.get(field) is not None:
            return refuse_v20(p, v, "%s is a V2.0-only field" % field)

    has_frames = bool(p.get("first_frame") or p.get("last_frame"))
    # Seconds guard: a numeric requested_seconds is a Flash enum value ("4"-
    # "12"); anything else (sub-4s, non-numeric) is honored by NO approved
    # model as given — reject, do not silently fall back to the Flash default.
    if p.get("requested_seconds") is not None and sec_str is None:
        v.model = UNSUPPORTED
        v.valid = False
        v.reason = ("requested_seconds %r is not a number — Flash seconds "
                    "are the string range 4-12" % p.get("requested_seconds"))
        return v
    if p.get("requested_seconds") is not None and int(sec_str) < 4:
        v.model = UNSUPPORTED
        v.valid = False
        v.reason = ("requested_seconds %s below Flash minimum 4 — Flash "
                    "seconds are the string range 4-12" % sec_str)
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
            # spec 11.4 rule 12: seed alone never forces another model — warn
            v.warnings.append("seed with no explicit model — Flash default "
                              "applied (seed does not force another model)")
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

    # STEP 12: seed ALONE -> Flash default (warn)
    if p.get("seed") is not None:
        v.model = FLASH
        v.valid = True
        v.mode = "text"
        v.reason = ("seed-only request: no V2.0-only field present — Flash "
                    "default applied")
        v.warnings.append("seed with no explicit model — Flash default applied "
                          "(seed does not force another model)")
        return v

    # STEP 13: no explicit model -> Flash default (the only approved model)
    v.model = FLASH
    v.valid = True
    v.mode = "text"
    v.reason = ("no explicit model and no V2.0-only field: Flash default "
                "(the only approved Agnes video model)")
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
    # 480p/1080p were V2.0 tiers; V2.0 retired 2026-09-25 -> refused
    ({"size": "1080p", "intent": "text"},
     UNSUPPORTED, False, None, "720P only", None),
    ({"num_frames": 121, "frame_rate": 24},
     UNSUPPORTED, False, None, "V2.0-only field", None),
    # any request over 12 s -> refused with the split advice
    ({"requested_seconds": 18, "frame_rate": 24, "size": "1080p"},
     UNSUPPORTED, False, None, SPLIT_ADVICE, None),
    ({"video_refs": 1},
     UNSUPPORTED, False, None, "video reference", None),
    ({"explicit_model": "agnes-video-2.5-flash", "size": "1080p"},
     FLASH, False, None, "explicit model wins over auto-correction", None),
    # semantic guard: 6 images are NEVER reinterpreted as keyframes
    ({"requested_seconds": "5", "size": "720P", "image_refs": 6},
     UNSUPPORTED, False, None, "semantics", None),
    # ...not even when the request says mode keyframes (V2.0 is gone)
    ({"num_frames": 121, "image_refs": 6, "mode": "keyframes"},
     UNSUPPORTED, False, None, "semantics", None),
    # 13s / 15s / 18s / 20s -> split into clips of 12 s or less
    ({"requested_seconds": 13, "size": "720P"},
     UNSUPPORTED, False, None, SPLIT_ADVICE, None),
    ({"requested_seconds": 20, "frame_rate": 24, "size": "720P"},
     UNSUPPORTED, False, None, SPLIT_ADVICE, None),
    ({"requested_seconds": "15"},
     UNSUPPORTED, False, None, SPLIT_ADVICE, None),
    # seed alone -> Flash default with warning (rule 12: seed forces nothing)
    ({"requested_seconds": "7", "size": "720P", "seed": 42},
     FLASH, True, "text", "Flash default", "seed with no explicit model"),
    # explicit V2.0 -> refused: retired by the vendor 2026-09-25
    ({"explicit_model": "agnes-video-v2.0", "negative_prompt": "blurry",
      "num_frames": 121, "frame_rate": 24},
     UNSUPPORTED, False, None, "retired by the vendor", None),
    # explicit Flash + num_frames -> invalid, model STAYS Flash
    ({"explicit_model": "agnes-video-2.5-flash", "num_frames": 121},
     FLASH, False, None, "not a Flash field", None),
    # video ref handoff only when permitted
    ({"video_refs": 1, "allow_kie_handoff": True},
     UNSUPPORTED, False, None, "handed off to KIE", None),
    # Flash seconds enum: 13 invalid under explicit Flash
    ({"explicit_model": "agnes-video-2.5-flash", "requested_seconds": "13"},
     FLASH, False, None, "4-12", None),
    # explicit V2.0 with off-grid frames: refused for the retirement reason
    ({"explicit_model": "agnes-video-v2.0", "num_frames": 120},
     UNSUPPORTED, False, None, "retired by the vendor", None),
    # the whole V2.0 surface is refused, however well formed
    ({"num_frames": 441, "frame_rate": 24},
     UNSUPPORTED, False, None, "V2.0-only field", None),
    # exactly 5 true image refs valid Flash
    ({"requested_seconds": "6", "size": "720P", "image_refs": 5},
     FLASH, True, "reference", "5 image reference", None),
    # unknown explicit model: never auto-selects full paid agnes-video-2.5
    ({"explicit_model": "agnes-video-2.5"},
     UNSUPPORTED, False, None, "approved", None),
    # V2.0-only fields refuse before the size they came with
    ({"num_frames": 81, "frame_rate": 24, "size": "720p"},
     UNSUPPORTED, False, None, "V2.0-only field", None),
    ({"num_frames": 81, "frame_rate": 24, "size": "720P"},
     UNSUPPORTED, False, None, "V2.0-only field", None),
    # regression: explicit V2.0 + bare seconds is refused, never fabricated
    ({"explicit_model": "agnes-video-v2.0", "requested_seconds": "5", "size": "720P"},
     UNSUPPORTED, False, None, "retired by the vendor", None),
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
    # regression: integer-float over 12s is refused the same way (18.0 == 18)
    ({"requested_seconds": 18.0, "frame_rate": 24},
     UNSUPPORTED, False, None, SPLIT_ADVICE, None),
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

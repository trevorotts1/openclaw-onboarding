#!/usr/bin/env python3
"""Prompt limits (FU-U6 + FU-U7, plan E.1-E.3): one table, fail closed, measured LAST. Stdlib only.

The caps come from the skills' own catalogs, never copied here:
  * Skill 68 (68-kie-audio/models.json, entry "suno-generate") for the Suno
    generate fields: lyrics, style (per model version), title, duration.
  * Skill 67 (67-kie-video/models.json) for video/avatar: vendor_hard_cap_chars
    per model, and negative_prompt only where the entry declares it.
  * A small Skill-75 override table for what the catalogs do not hold, each
    entry carrying the source URL, the cap status and the free confirm step.
    FU-U7 adds: Hailuo 02 / 2.3 / 2.3 Fast prompt 2,000 (the catalog carries
    no hailuo entry at all - the whole family prefix is held there, and H3
    keeps the catalog's 7,000); Kling 2.6 i2v 2,500; and the Kling 2.5 Turbo
    negative_prompt cap of 2,500 (the catalog verifies the prompt cap but does
    not declare the field).

check_request(model, request) measures EVERY text field of the FINAL payload.
Over the cap is a refusal (PROMPT_OVER_CAP: field, characters, cap, source,
status). It NEVER truncates.

kie_dispatch.dispatch runs check_request on the final payload - after every
mutation, before any spend - so a refused prompt reserves nothing and sends
nothing; the refusal names the field, the characters, the cap, the source and
the status, and the receipt carries the same row.

Duration (10-360 s, VERIFIED) is not a text field and stays enforced by
song_dispatch.validate_request; this module does not restate it.

Rule 12 seam: the numbers stay in the catalogs and in the declared override
table; the shared enforcer is called ceiling-only (kind="verbatim") so the
audit trail is kept, exactly as product_style_bible/bible.py does. The 80
percent floor must NOT be applied here: the 67 house floor (5000) sits above
Kling's 2500 hard cap and H3's 7000 cap, and the floor would ban short
professional prompts (the One-Check style is 770 chars, an avatar prompt is
about 150).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TOOL_NAME = "prompt_limits"
TOOL_VERSION = "1.1.0"

#: Skill-75 overrides for what the catalogs do not hold. UNVERIFIED entries.
OVERRIDES = {
    "negative_tags": {
        "cap": 1000, "status": "UNVERIFIED",
        "source_url": "https://docs.kie.ai/suno-api/generate-music/",
        "source": "skill-75 override (file 17 citing docs [1][6]); 68 catalog holds no "
                  "negativeTags cap for generate (200 applies to add-vocals/add-instrumental only)",
        "confirm": "re-read the generate-music schema on docs.kie.ai (free), record the "
                   "negativeTags maxLength; no paid probe",
    },
    "kling/ai-avatar-standard": {
        "cap": 2500, "status": "UNVERIFIED",
        "source_url": "https://docs.kie.ai/market/kling/ai-avatar-standard",
        "source": "skill-75 override (file 17: the KIE page states no exact maximum; "
                  "2500 is the Kling Avatar API guidance)",
        "confirm": "read the ai-avatar-standard page on docs.kie.ai (free); no paid probe",
    },
    "kling-2.6/image-to-video": {
        "cap": 2500, "status": "VERIFIED",
        "source_url": "https://docs.kie.ai/market/kling/",
        "source": "skill-75 override (file 17: Kling 2.6 i2v prompt 2,500; 67 "
                  "catalog carries the sibling kling-2.6/motion-control at 2,500 "
                  "VERIFIED but holds no i2v entry)",
        "confirm": "re-read the Kling 2.6 i2v page on docs.kie.ai (free); no paid probe",
    },
}

#: FU-U7 (plan E.1, file 17): Hailuo 02 / 2.3 / 2.3 Fast prompt 2,000,
#: VERIFIED for those models and NOT H3 (the catalog carries MiniMax H3 at
#: 7,000). The 67 catalog has no hailuo entry at all, so the whole family
#: prefix is held at 2,000 - a new hailuo variant cannot slip past unmeasured.
HAILUO_PREFIX = "hailuo/"
HAILUO = {
    "cap": 2000, "status": "VERIFIED",
    "source_url": "https://docs.kie.ai/market/hailuo/2-3-image-to-video-pro",
    "source": "skill-75 override (file 17: Hailuo 02 / 2.3 / 2.3 Fast prompt "
              "2,000, VERIFIED for those models, not H3; 07-kie-setup re-read)",
}

#: Kling 2.5 Turbo: file 17 holds prompt AND negative_prompt to 2,500 each.
#: The 67 catalog verifies the prompt cap but declares no negative_prompt
#: control field for these models, so the negative cap is added here at the
#: same, file-17-verified number. Hailuo/H3 have no documented negative field
#: at all (negatives go inside the prompt, short) so nothing is invented.
KLING25_NEG_TABLE = {
    "kling/v2-5-turbo-text-to-video-pro": 2500,
    "kling/v2-5-turbo-image-to-video-pro": 2500,
}
NEGATIVE_PROMPT_SOURCE = ("file 17 + 67-kie-video/models.json (the same 2,500 the "
                          "catalog verifies for these Kling prompts), VERIFIED")

#: The numbers the 68 catalog holds for suno-generate (VERIFIED 2026-10-06). Used
#: ONLY when that catalog is unreachable from this install, so the guard stays armed.
SUNO_FALLBACK = {"lyrics": 5000, "style": 1000, "title": 80,
                 "source": "68-kie-audio/models.json suno-generate caps (VERIFIED 2026-10-06)",
                 "status": "VERIFIED"}


class PromptLimitError(ValueError):
    """A final-payload text field is over its cap. Never truncates."""

    def __init__(self, code, field, chars, cap, source, status, message=None):
        super().__init__(message or ("%s: field %r, chars %d, cap %d, source %s, status %s"
                                     % (code, field, chars, cap, source, status)))
        self.code = code
        self.field = field
        self.chars = chars
        self.cap = cap
        self.source = source
        self.status = status


# ---------------------------------------------------------------------------
# Catalog readers.

def find_catalogs():
    """(68 audio models.json, 67 video models.json) from this file's position.

    Same ancestor walk as kie_dispatch.resolve_adapter: the repo-root
    distribution layout (68-kie-audio/ next to this skill, or under
    onboarding/), then the 999-setup installer layout
    (installer-registration/helpers/67-kie-video/, the tracked copy in that
    distribution). Missing entries stay None.
    """
    audio = video = None
    for anc in Path(__file__).resolve().parents:
        for cand in (anc, anc / "onboarding",
                     anc / "installer-registration" / "helpers"):
            if audio is None and (cand / "68-kie-audio" / "models.json").is_file():
                audio = cand / "68-kie-audio" / "models.json"
            if video is None and (cand / "67-kie-video" / "models.json").is_file():
                video = cand / "67-kie-video" / "models.json"
    return audio, video


def _entry(path, canonical_id):
    if not path:
        return None
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for e in doc.get("entries") or doc.get("models") or []:
        if e.get("canonical_model_id") == canonical_id:
            return e
    return None


def suno_caps(version=None, models_path=None):
    """{lyrics, style, title, duration, source, status} for a Suno generate version."""
    entry = _entry(models_path if models_path is not None else find_catalogs()[0], "suno-generate")
    if entry is None:
        return dict(SUNO_FALLBACK, duration={"min_seconds": 10, "max_seconds": 360}, version=version or "V6")
    caps = entry.get("caps") or {}
    ver = version or entry.get("model_default") or "V6"
    style = caps.get("custom_style_max_chars") or {}
    dur = caps.get("duration") or {}
    path = models_path if models_path is not None else find_catalogs()[0]
    return {"lyrics": caps.get("lyrics_max_chars"), "style": style.get(ver),
            "title": caps.get("title_max_chars"), "version": ver,
            "duration": {"min_seconds": dur.get("min_seconds"), "max_seconds": dur.get("max_seconds")},
            "source": ("%s suno-generate caps, source %s, VERIFIED %s"
                       % (Path(path).name if path else "skill-75 fallback table",
                          entry.get("source_url", OVERRIDES["negative_tags"]["source_url"]),
                          entry.get("last_verified_at", "2026-10-06"))),
            "status": entry.get("cap_status", "VERIFIED")}


def video_caps(model, models_path=None):
    """{prompt: cap, negative_prompt: cap-or-None, source, status} for a 67 model or override.

    A missing catalog or a missing entry raises PromptLimitError (fail closed);
    a model the catalog carries with no published cap returns cap None and the
    caller reports the status. Hailuo models are held at the file-17 cap of
    2,000 even though the catalog carries no hailuo entry at all.
    """
    if model in OVERRIDES:
        o = OVERRIDES[model]
        return {"prompt": o["cap"], "negative_prompt": o["cap"], "status": o["status"],
                "source": "%s; %s" % (o["source_url"], o["source"])}
    if str(model).startswith(HAILUO_PREFIX):
        return {"prompt": HAILUO["cap"], "negative_prompt": None,
                "status": HAILUO["status"],
                "source": "%s; %s" % (HAILUO["source_url"], HAILUO["source"])}
    path = models_path if models_path is not None else find_catalogs()[1]
    entry = _entry(path, model)
    if entry is None:
        raise PromptLimitError("PROMPT_LIMIT_NO_CATALOG", model, 0, 0,
                               "67-kie-video/models.json (%s)" % (path or "not found"),
                               "UNKNOWN",
                               "PROMPT_LIMIT_NO_CATALOG: field %r, chars 0, cap 0, source 67-kie-video/"
                               "models.json (%s), status UNKNOWN: refusing (pass models_path)"
                               % (model, path or "not found"))
    cap = entry.get("vendor_hard_cap_chars")
    neg = cap if "negative_prompt" in (entry.get("control_fields") or []) else None
    if neg is None and model in KLING25_NEG_TABLE:
        neg = KLING25_NEG_TABLE[model]
    return {"prompt": cap, "negative_prompt": neg,
            "status": entry.get("cap_status", "UNKNOWN"),
            "source": "%s %s, source %s, VERIFIED %s%s" % (
                Path(path).name, model, entry.get("source_url", ""),
                entry.get("last_verified_at", ""),
                ("; negative_prompt %s" % NEGATIVE_PROMPT_SOURCE)
                if neg is not None and "negative_prompt" not in (entry.get("control_fields") or [])
                else "")}


# ---------------------------------------------------------------------------
# The gate.

def _is_suno(body):
    return any(k in body for k in ("lyrics", "custom_mode", "negative_tags", "style"))


def check_request(model, request, models_path=None):
    """Measure EVERY text field of the FINAL payload. Raises PromptLimitError.

    ``request`` is the whole envelope; the fields are read from request["input"]
    when that is a dict (the Skill 68 createTask shape), else from request.
    Nothing is truncated; a passing field comes back with its measured row.
    """
    if not isinstance(request, dict):
        return {"ok": True, "measured": []}
    body = request.get("input") if isinstance(request.get("input"), dict) else request
    measured, spec = [], []
    if _is_suno(body) or str(model).startswith(("suno", "ai-music-api")):
        caps = suno_caps(body.get("model") if isinstance(body.get("model"), str) else None, models_path)
        spec = [("lyrics", caps["lyrics"], caps["source"], caps["status"]),
                ("style", caps["style"], caps["source"], caps["status"]),
                ("title", caps["title"], caps["source"], caps["status"]),
                ("negative_tags", OVERRIDES["negative_tags"]["cap"],
                 OVERRIDES["negative_tags"]["source_url"] + "; " + OVERRIDES["negative_tags"]["source"],
                 OVERRIDES["negative_tags"]["status"])]
    else:
        caps = video_caps(model, models_path)
        spec = [("prompt", caps["prompt"], caps["source"], caps["status"]),
                ("negative_prompt", caps["negative_prompt"], caps["source"], caps["status"])]
    for field, cap, source, status in spec:
        text = body.get(field)
        if not isinstance(text, str):
            continue
        if cap is not None and len(text) > cap:
            raise PromptLimitError("PROMPT_OVER_CAP", field, len(text), cap, source, status)
        measured.append({"field": field, "chars": len(text), "cap": cap,
                         "source": source, "status": status})
    _enforcer_trail(model, measured)
    return {"ok": True, "measured": measured}


_TRAIL_DONE = False  # the seam is invoked once per process; the catalogs stay the numbers


def _enforcer_trail(model, measured):
    """Rule 12 audit trail, ceiling only, when the shared enforcer is reachable.

    Advisory: the refusal above is the gate; the numbers stay in the catalogs
    and OVERRIDES, and the enforcer is told the field's cap as its fallback_max
    (the bible.enforce_prompt pattern). Called once per process so a render
    fan-out does not spawn the Skill 74 adapter per payload.
    """
    global _TRAIL_DONE
    if _TRAIL_DONE:
        return
    row = next((m for m in measured if m["cap"]), None)
    if row is None:
        return
    _TRAIL_DONE = True
    try:
        dirs = [p / "shared-utils" for p in Path(__file__).resolve().parents]
        envd = os.environ.get("OPENCLAW_SKILLS_DIR")
        if envd:
            dirs.append(Path(envd) / "shared-utils")
        dirs += [Path.home() / ".openclaw" / "skills" / "shared-utils",
                 Path("/data/.openclaw/skills/shared-utils")]
        for d in dirs:
            if (d / "kie_prompt_enforcer.py").is_file():
                if str(d) not in sys.path:
                    sys.path.insert(0, str(d))
                import kie_prompt_enforcer as KPE
                KPE.check(model, "x" * row["chars"], kind="verbatim", fallback_max=row["cap"])
                return
    except Exception:
        return  # the trail is advisory; check_request already refused what is over cap

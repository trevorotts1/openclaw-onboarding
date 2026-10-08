#!/usr/bin/env python3
"""F4 no automatic Suno sound effects: default run plans ZERO sfx jobs.

Owner order 2026-10-08, manual Part F item F4 (Medium, ADDENDUM 3), PASTE
ADDENDUM 3+4+5. stdlib only, zero paid calls.

Audit finding (2026-10-08, this unit): nothing under ``scripts/core`` auto-
queues a Suno sound-effect job -- the greps the owner order names (sfx /
sound effect / sound_effect) return zero hits in skill 75's code on main,
the intake/preflight defaults carry no sound-effects field and the batch
stage list has no sound-effects stage. SFX was still a live hole through
three seams this module pins shut, fail-closed:

1. ``skill68_auto_job()`` -- Skill 68's catalog ships ``suno-sounds``
   (`ai-music-api/sounds`, tasks: ``sound-effects``). A generic catalog
   sweep could auto-queue it. The factory job planner must never derive a
   sound-effects job from the catalog: the ONLY accepted origin is the
   run's own config line (``sound_effects: ["..."]`` written by an explicit
   manual order). Everything else refuses.
2. Prompt leakage -- a Suno song or sounds prompt can *ask* Suno for
   effects ("thunder", "gunshot", "sirens" inside style/lyrics). The song
   request builder stamps ``no_sound_effects: true`` against any such text
   in the run's config: if the run config carries words on
   ``SFX_PROMPT_BAN`` and the config did not explicitly order sound
   effects, the stamp refuses (fail-closed, never silently cleaned).
3. Receipt honesty -- ``verify_run_jobs`` counts every job in a run's job
   list whose model, route, task set or endpoint points at Skill 68's
   sounds surface; any such job without the explicit-order flag fails. A
   default run (no sound_effects line) must therefore prove zero sfx jobs.

"Explicit manual order" shape: the run config (the batch card's settings
or the brief's config block) carries ``sound_effects: [...]`` with a
non-empty list of prompt strings. Nothing else counts -- not a style word,
not a catalog default, not an orchestrator's note.

Run: python3 core/audio_c3/test_sfx_off_f4.py
"""
from __future__ import annotations

SCHEMA_VERSION = "blackceo.audio-c3/sfx-off/v1"
TOOL_VERSION = "0.1.0"
EXIT = {"ok": 0, "error": 1, "rejected": 4}

#: Skill 68 catalog row (68-kie-audio/models.json, canonical_model_id
#: ``suno-sounds``) -- the ONLY sound-effects surface the factory could
#: ever queue, named here so a job list is checked against the real ids.
SFX_CATALOG_ID = "suno-sounds"
SFX_ROUTE_CURRENT = "ai-music-api/sounds"
SFX_ENDPOINTS = ("/api/v1/generate/sounds", "/api/v1/jobs/createTask")
SFX_TASK_TAG = "sound-effects"

#: Model ids the sounds route accepts (catalog model_enum). A job listing
#: one of these on a sounds route/endpoint is an sfx job.
SFX_MODELS = frozenset(("V5", "V5_5", "V6", "V6_MINI", "V6_WILD"))

#: Job-list keys this module treats as a "default run": any dict with a
#: ``jobs`` list (receipt shape) or a bare list of job dicts, plus the
#: run-config gate that decides whether ANY sfx job may exist.
RUN_CONFIG_SFX_KEY = "sound_effects"

#: Text seams where Suno could be *asked* for effects inside a prompt.
#: Checked only on the run's own config strings (style prompt, lyrics):
#: the module never invents or rewrites prompt text, it refuses it.
SFX_PROMPT_BAN = (
    "sound effect", "sound effects", "sound-effect", "sfx", "foley",
    "siren", "sirens", "gunshot", "explosion", "thunder", "doorbell",
    "applause", "whistle effect", "crowd chant",
)

# --- the config gate --------------------------------------------------------

def _config_words(cfg):
    """Lowered config text joined across the string/list fields we check."""
    if not isinstance(cfg, dict):
        return ""
    parts = [jsonable_text(v) for k, v in sorted(cfg.items())
             if k not in (RUN_CONFIG_SFX_KEY,)]
    return " ".join(p for p in parts if p).lower()

def jsonable_text(v):
    """Recursively collect string content (dict/list/str leaf join)."""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return " ".join((jsonable_text(k) + " " + jsonable_text(val))
                        for k, val in sorted(v.items())
                        if k != RUN_CONFIG_SFX_KEY)
    if isinstance(v, (list, tuple)):
        return " ".join(jsonable_text(x) for x in v)
    return ""

def sfx_ordered(cfg):
    """True only when the run's own config explicitly orders sound effects.

    ``sound_effects`` (case-insensitive key) holding a non-empty list of
    non-empty strings. Any other shape counts as not ordered: an empty
    list, a bare string, a bool, None, an absent key.
    """
    if not isinstance(cfg, dict):
        return False
    for k, v in cfg.items():
        if isinstance(k, str) and k.strip().lower() == RUN_CONFIG_SFX_KEY:
            if isinstance(v, list) and v and all(
                    isinstance(x, str) and x.strip() for x in v):
                return True
    return False

def sfx_error_codes(cfg, cfg_source="run-config"):
    """Errors a run config earns for sfx content it never ordered.

    Fail-closed: sfx-asking words in ANY other config field refuse even
    though the prompt is built elsewhere -- the config is the only surface
    this unit owns, so an asking word here means the plan would leak an
    sfx request downstream.
    """
    errs = []
    if not isinstance(cfg, dict):
        return ["CONFIG_INVALID:not a dict"]
    if sfx_ordered(cfg):
        return errs
    words = _config_words(cfg)
    for phrase in SFX_PROMPT_BAN:
        if phrase in words:
            errs.append(
                "SFX_NOT_ORDERED_LEAK:%s (config %r says %r; add "
                "`sound_effects: [...]` to the run config for an explicit "
                "manual order -- F4)" % (cfg_source, cfg_source, phrase))
    return errs

# --- the job-list gate ------------------------------------------------------

def _is_sfx_job(job):
    """Job dict points at Skill 68's Suno sound-effects surface?"""
    if not isinstance(job, dict):
        return False
    model = str(job.get("model") or job.get("catalog_model") or "")
    route = str(job.get("route") or "")
    endpoint = str(job.get("endpoint") or "")
    tasks = job.get("tasks") or job.get("task_types") or []
    if isinstance(tasks, str):
        tasks = [tasks]
    tags = " ".join(str(t) for t in tasks if isinstance(t, str))
    model_l = model.lower()
    route_l = route.lower()
    if model_l == SFX_CATALOG_ID or SFX_CATALOG_ID in route_l:
        return True
    if SFX_ROUTE_CURRENT in route_l:
        return True
    if "generate/sounds" in endpoint.lower():
        return True
    if SFX_TASK_TAG in tags.lower() and SFX_ROUTE_CURRENT in route_l:
        return True
    # a song-generation model used on the sounds route is still an sfx job
    if (route_l == SFX_ROUTE_CURRENT or "generate/sounds" in endpoint.lower()) \
            and model.upper() in SFX_MODELS:
        return True
    return False

def verify_run_jobs(receipt, cfg=None):
    """Error list for a run's job list. Empty = F4 provable for this run.

    ``receipt`` holds ``jobs`` (list of job dicts) -- the shape receipt /
    state-store records keep. With no config ordering sound effects, ANY
    sfx job fails. With an explicit order, the count may only equal the
    order's list length (one job per ordered prompt; surplus sfx jobs
    fail). The order list does NOT appear in jobs on a default run: the
    default is zero.
    """
    if not isinstance(receipt, dict):
        return ["RECEIPT_INVALID:not a dict"]
    jobs = receipt.get("jobs")
    if jobs is None:
        jobs = receipt.get("audio_jobs")
    if jobs is None:
        return []
    if not isinstance(jobs, list):
        return ["JOB_LIST_INVALID:not a list"]
    ordered = sfx_ordered(cfg or {})
    errs = []
    allow = 0
    if ordered:
        for k, v in (cfg or {}).items():
            if isinstance(k, str) and k.strip().lower() == RUN_CONFIG_SFX_KEY:
                allow = len(v)
    sfx_rows = [j for j in jobs if _is_sfx_job(j)]
    if not ordered and sfx_rows:
        errs.append("SFX_JOB_NOT_ORDERED:%d (default run makes zero "
                    "sound-effect jobs -- F4)"
                    % len(sfx_rows))
    elif ordered and len(sfx_rows) > allow:
        errs.append("SFX_JOB_SURPLUS:%d ordered >%d found"
                    % (allow, len(sfx_rows)))
    return errs

def default_run_job_audit(receipts, cfg=None):
    """The guard the test asserts: default runs prove zero sfx jobs.

    ``receipts`` is a list of run receipt dicts (or one dict). Returns the
    error list across them; a default run must come back empty with zero
    sfx jobs. The explicit-order allowance counts ACROSS all receipts (the
    order is one manual order for the run, not one per receipt) -- surplus
    sfx jobs over the ordered count fail.
    """
    if isinstance(receipts, dict):
        receipts = [receipts]
    if not isinstance(receipts, list):
        return ["RECEIPTS_INVALID:not a list"]
    errs = []
    allow = 0
    ordered = sfx_ordered(cfg or {})
    if ordered:
        for k, v in (cfg or {}).items():
            if isinstance(k, str) and k.strip().lower() == RUN_CONFIG_SFX_KEY:
                allow = len(v)
    total_sfx = 0
    for i, r in enumerate(receipts):
        if not isinstance(r, dict):
            errs.append("receipt[%d]: RECEIPT_INVALID:not a dict" % i)
            continue
        jobs = r.get("jobs")
        if jobs is None:
            jobs = r.get("audio_jobs")
        if jobs is None:
            continue
        if not isinstance(jobs, list):
            errs.append("receipt[%d]: JOB_LIST_INVALID:not a list" % i)
            continue
        rows = [j for j in jobs if _is_sfx_job(j)]
        total_sfx += len(rows)
    if not ordered and total_sfx:
        errs.append("SFX_JOB_NOT_ORDERED:%d (default run makes zero "
                    "sound-effect jobs -- F4)" % total_sfx)
    elif ordered and total_sfx > allow:
        errs.append("SFX_JOB_SURPLUS:%d ordered vs %d found"
                    % (allow, total_sfx))
    return errs

__all__ = [
    "EXIT", "RUN_CONFIG_SFX_KEY", "SCHEMA_VERSION", "SFX_CATALOG_ID",
    "SFX_ENDPOINTS", "SFX_MODELS", "SFX_PROMPT_BAN", "SFX_ROUTE_CURRENT",
    "SFX_TASK_TAG", "TOOL_VERSION",
    "default_run_job_audit", "sfx_error_codes", "sfx_ordered",
    "verify_run_jobs",
]
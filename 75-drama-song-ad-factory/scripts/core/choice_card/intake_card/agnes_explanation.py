"""Supplementary explanation for the two existing AGNES choices.

The question and its option identities stay in intake_card._agnes_q.  This
module only supplies read-only text after that menu; it neither parses an
answer nor selects a route, checks a key, or makes a provider request.

Sources checked 2026-10-24:
- https://wiki.agnes-ai.com/en/docs/tokenplan (paid Token Plan API key,
  shared daily quotas; vendor limits can change).
- agnes_quota.limits / AGNES_MAX_DELIVERED_S (this installation's planner).
- agnes_dispatch VIDEO_SIZE / VIDEO_SECONDS (720P, fixed 10-second clips).
- catalog_calculator.agnes_price (song and lip-sync remain paid KIE work).
- intake_card._model_question (the client's later KIE model choice).
- SKILL.md Provider policy (pictures/video through KIE; Suno and Kling).

No credential presence or provider availability is inferred from this text.
"""
from __future__ import annotations

import math
import os


def lines(env=None):
    """Both choices in plain language, using the local quota configuration.

    Only non-secret quota overrides are read.  Unreadable quota settings fail
    loudly through the existing quota reader rather than inventing capacity.
    The displayed totals are planning limits, never a remaining-balance claim.
    """
    from agnes_quota import agnes_quota as quota

    limits = quota.limits(os.environ if env is None else env)
    minutes = math.ceil(quota.AGNES_MAX_DELIVERED_S / 60)
    return [
        "Option 1 - Agnes: You need a paid Agnes plan and working subscription "
        "API access. It makes the pictures and 720p motion clips using your "
        "remaining plan quota. The clips are %d seconds each; this skill "
        "supports selected lengths up to %d minutes on Agnes."
        % (quota.CLIP_SECONDS, minutes),
        "The daily planning limits here are %s video seconds and %s images, "
        "shared across keys of the same type. Remaining quota and provider "
        "limits still apply; the whole video must fit that day."
        % (format(limits["video"], ","), format(limits["image"], ",")),
        "Option 2 - KIE.ai: Use KIE.ai's video models, including premium "
        "options. You'll choose the model next, see the estimated cost, and "
        "approve it before generation. KIE.ai also supplies the pictures; "
        "image and video usage is billed against your KIE.ai credits.",
        "With either choice, the Suno song and Kling talking close-ups still "
        "use KIE.ai and are billed separately. Those charges are included in "
        "the estimate and must stay within your approved spending limit. "
        "Choosing Agnes does not make the whole production free.",
        "Neither option is selected for you; choose 1 or 2.",
    ]

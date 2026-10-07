#!/usr/bin/env python3
"""creative_fidelity.py: Resilia-style creative-fidelity gate, Plan 9.3. stdlib only.

The V2 addition version 1 never had: an animated Resilia-style check that
runs before song generation, covering exactly the three properties plan 9.3
names:

1. the Style Bible is injected in EVERY visual prompt (directive 13.3:
   compiler output only -- a hand-typed prompt with no [compiled:style=
   mark means the default animated look was never applied);
2. the twelve-beat arc is present (reuses core.story_arc, the directive
   11.1 validator -- identity, order, no duplicates, reveal in range);
3. the product reveal lands after the mentor (mentor is beat 7, product
   intro is beat 8; story_arc enforces reveal >= 8, and the mentor order
   is re-checked here so the creative gate does not depend on that alone).

Fail-closed: a missing story, a missing prompt list, one uncompiled prompt
or one missing beat all block. UNAVAILABLE never counts as PASS.
"""
from __future__ import annotations

try:
    from story_arc import BEATS, validate_story
except ImportError as _e:  # imported as core.qc.creative_fidelity
    if "story_arc" not in str(_e):
        raise
    from ..story_arc import BEATS, validate_story

try:
    from style_bible_integration import assert_compiled
except ImportError as _e:
    if "style_bible_integration" not in str(_e):
        raise
    from ..style_bible_integration import assert_compiled

PASS = "PASS"
FAIL = "FAIL"
UNAVAILABLE = "UNAVAILABLE"

MENTOR_BEAT = "mentor"
PRODUCT_REVEAL_BEAT = 8  # Gift / Mechanism / Product Introduction


class CreativeError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _fail(failures, code, detail):
    failures.append({"code": code, "detail": detail, "verdict": FAIL})


def check_creative(payload):
    """Validate creative fidelity. Returns verdict/code/failures."""
    if not isinstance(payload, dict):
        raise CreativeError("BAD_PAYLOAD", "creative payload must be an object")
    failures = []

    story = payload.get("story")
    if not isinstance(story, dict):
        _fail(failures, "CREATIVE_STORY_MISSING",
              "no story record bound to this variant")
        story_res = None
    else:
        story_res = validate_story(story)
        if story_res.get("outcome") != "ok":
            _fail(failures, "CREATIVE_STORY_ARC",
                  "twelve-beat arc rejected: %s" % story_res.get("reason_code"))
        else:
            # Defence in depth: the product reveal must land after the
            # mentor, whatever story_arc's numeric floor says.
            beats = story_res.get("beats") or []
            reveal = story_res.get("product_reveal")
            if MENTOR_BEAT in beats and isinstance(reveal, int) and \
                    reveal <= beats.index(MENTOR_BEAT):
                _fail(failures, "CREATIVE_REVEAL_BEFORE_MENTOR",
                      "product_reveal %d is not after the mentor (beat %d)"
                      % (reveal, beats.index(MENTOR_BEAT) + 1))

    prompts = payload.get("visual_prompts")
    if not isinstance(prompts, list) or not prompts:
        _fail(failures, "CREATIVE_NO_PROMPTS",
              "visual_prompts must be a non-empty list for a visual stage")
    else:
        uncompiled = [i for i, p in enumerate(prompts)
                      if not assert_compiled(p)]
        if uncompiled:
            _fail(failures, "STYLE_NOT_INJECTED",
                  "%d of %d visual prompts lack the compiled style mark "
                  "(indices %s)" % (len(uncompiled), len(prompts),
                                    uncompiled[:8]))

    if not failures:
        return {"verdict": PASS, "code": None, "failures": [],
                "beats": (story_res or {}).get("beats", []),
                "product_reveal": (story_res or {}).get("product_reveal")}
    verdict = UNAVAILABLE if all(f["verdict"] == UNAVAILABLE
                                 for f in failures) else FAIL
    return {"verdict": verdict, "code": failures[0]["code"],
            "failures": failures,
            "beats": (story_res or {}).get("beats", []),
            "product_reveal": (story_res or {}).get("product_reveal")}

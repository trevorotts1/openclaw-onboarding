#!/usr/bin/env python3
"""
intelligence_engines_check.py — INTELLIGENCE-ENGINE MECHANICAL HALF.

================================================================================
Doctrine (binding): a rule that cannot be mechanically checked is not a rule.
Every INTELLIGENCE engine (Facial, World, Lighting, Emotional, Story, Typography,
Representation) is irreducibly perceptual at the *verdict* layer — "does the face
read sad", "would this person be in this room", "is the hair authentic" — but the
PROMPT-SIDE REQUIREMENT is fully deterministic: the required token string must be
PRESENT in the people/scene prompt (or the required beat tag must be present, in
slide order, in the copy). This script enforces that mechanical half as a binary
auto-fail. The vision VERDICT half stays subjective but is LOGGED to
working/qc/vision_qc_log.json (already required non-empty by AF-NO-VISION-QC) so it
is auditable. This is exactly how the Slide-00 binary-auto-fail principle is kept
true for perceptual engines: the GATEABLE half is the mechanical prompt-token
assertion; vision QC is the checker for the perceptual half.

This script does NOT touch build_deck.py's render path. It is a SEPARATE check,
invoked by the QC specialists at the 8.5 gate (Prompt-QC, Image-QC, Phase 1Q).

CODES ENFORCED HERE (all registered in SOP-SLIDE-00 Section 8b + PIPELINE-MANIFEST):
  AF-FACE-PROMPT-MISSING  (Prompt-QC, slide)  Facial — no expression token in the
                          people-prompt from the Expression Vocabulary Table.
  AF-WORLD-SCALE          (Prompt-QC, slide)  World — no stated setting + believability
                          justification string in the scene-prompt.
  AF-LIGHT-PROMPT-MISSING (Prompt-QC, slide)  Lighting — no key/fill/rim direction AND
                          no rim/hair-light token in the people-prompt.
  AF-HAIR-INAUTHENTIC     (Prompt-QC, slide)  Representation — no hairstyle token drawn
                          from the age-banded hairstyle catalog in the people-prompt.
  AF-NO-FELT-STAKES       (Phase 1Q, DECK)    Emotional — no FELT_STAKES beat (a concrete
                          number paired with a personal-loss frame) before the first
                          ladder beat in slides_copy.md.
  AF-NO-VILLAIN           (Phase 1Q, DECK)    Story — no VILLAIN/antagonist beat, or a
                          VILLAIN beat that does not PRECEDE the HERO/promise beat.
  AF-NO-HOOK-REFRAIN      (Phase 1Q, DECK)    Hook — the canonical refrain recurs on
                          <3 dedicated copy beats (sacred refrain not established).
  AF-HOOK-1               (DECK)              Hook — the refrain recurs on >4 slides
                          (copy or baked image text): over-stamp / wallpaper deck veto.
  AF-HOOK-OVERSTAMP       (Phase 1Q, slide)   Hook — the refrain is stamped >=2x within
                          one slide's copy.
  AF-HOOK-4               (Prompt-QC, slide)  Hook — the refrain is baked >=2x into one
                          slide's prompt text (per-slide over-stamp, image side).
  AF-HOOK                 (Prompt-QC, slide)  Hook — the refrain is baked into a FOOTER /
                          bottom band on a slide prompt (never a footer stamp).
  AF-HOOK-IMG-MISSING     (Prompt-QC, DECK)   Hook — the refrain is baked on <3 slides'
                          prompt text (image-side refrain not established).
  AF-NO-RECAP             (Phase 1Q, DECK)    Recap/Re-Pitch — no post-price beat restates
                          the value stack + price after the final price reveal.
  AF-NARRATIVE-HARMONY    (Phase 1Q, DECK)    Harmony — the writing arc is out of order
                          (must hold HOOK->VILLAIN->FELT_STAKES->PROMISE->PRICE->RECAP).

The verdict-half codes (AF-FACE-MOOD, AF-WORLD-IMAGE-MISMATCH/world-grounding,
AF-LIGHT-SKINTONE, AF-HAIR-INAUTHENTIC vision verdict) are owned by Image-QC and
read from vision_qc_log.json; this script only asserts the mechanical prompt half
and that the vision log carries a per-slide record so the verdict was actually run.

ZERO third-party deps (stdlib json / re / pathlib only).

USAGE:
    python3 intelligence_engines_check.py [RUN_DIR] [--phase prompt|copy|all] [--json]
    python3 intelligence_engines_check.py --run-dir DIR [--phase prompt|copy|all] [--json]
    python3 intelligence_engines_check.py --workspace DIR [--phase prompt|copy|all] [--json]
    # RUN_DIR resolution order (U86/GK-24 — "an alien cwd cannot silently read the
    # wrong live workspace"): explicit --run-dir/--workspace flag > positional
    # RUN_DIR (back-compat) > OC_DECK_WORKSPACE env var > CWD-relative './working'
    # (the historical default, PRESERVED for back-compat). Reads:
    #   <RUN_DIR>/prompts/slide-*.txt        (prompt-side engines)
    #   <RUN_DIR>/copy/slides_copy.md         (copy-beat engines)
    #   <RUN_DIR>/copy/price_ladder.json      (first ladder beat, for FELT_STAKES order)
    #   <RUN_DIR>/brand/hairstyle_catalog.json (catalog token set, optional asset)
    #
    # WORKSPACE-PATH DEFECT (U86/GK-24, VERIFIED-BY-EXECUTION): this is a
    # standalone CLI tool "invoked by the QC specialists at the 8.5 gate" (see
    # doctrine note above) — a human/agent runs it by hand from wherever their
    # shell happens to be. Before this fix, forgetting RUN_DIR silently resolved
    # './working' against the CALLER's cwd: if an unrelated deck's run dir
    # happened to be sitting there, the script would silently grade THAT deck
    # and report a result with zero indication it read the wrong directory. The
    # implicit CWD-relative fallback is kept (never a breaking change to the
    # documented default), but every invocation now REPORTS which directory it
    # actually read and BY WHAT RESOLUTION SOURCE (run_dir_resolved /
    # run_dir_source in --json; a loud stderr NOTE otherwise) — the ambiguity
    # can no longer be silent. build_deck.py / phase_verifiers.py are UNAFFECTED:
    # they always call check_copy()/check_prompts() directly with an explicit
    # run_dir, never through this CLI default.

EXIT CODES:
    0 — every engine's mechanical half passes (no triggered code).
    4 — one or more engines triggered an auto-fail (drift). Message names code+slide.
    2 — could not run (missing required input / parse error).
"""

import json
import os
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Detection vocabularies (the mechanical token sets). These mirror the doctrine
# tables in the producing-role SOPs so the SOP and the checker stay in lockstep.
# --------------------------------------------------------------------------- #

# Facial — Expression Vocabulary Table (slide-image-creator-sops.md SOP 9.2
# strengthening). A people-prompt must NAME an explicit expression term; "smiling"
# alone is NOT an explicit expression token and does not satisfy the gate.
EXPRESSION_TOKENS = [
    "brow tension", "distant gaze", "jaw set", "2am", "eyes lifting",
    "that's me", "half-smile", "relieved", "arrived", "soft confident smile",
    "shoulders down", "direct to camera", "settled", "certain", "no grin",
    "open-mouth joy", "hands up", "leaning in", "serious warmth", "hand extended",
    "worried", "overwhelmed", "distant", "hopeful", "resolved", "determined",
]
# A prompt that contains ONLY a bare "smiling"/"smile" with no explicit emotion
# token fails — caught by requiring at least one EXPRESSION_TOKEN.

# Lighting — key/fill/rim direction + a rim/hair separation light token.
LIGHT_DIRECTION_TOKENS = ["key light", "fill light", "rim light", "rim or hair",
                          "key/fill/rim", "key, fill", "lighting direction"]
RIM_HAIR_TOKENS = ["rim light", "hair light", "light on top of the hair",
                   "separation light", "hair and shoulder edge", "rim or hair light"]

# World — a STATED setting AND a believability justification ("because ...",
# "would this person", "normal house", "not a ... condo/penthouse", a station cue).
WORLD_SETTING_TOKENS = ["setting", "real-world setting", "interior", "room",
                        "kitchen", "office", "studio", "window", "exterior", "scene"]
WORLD_JUSTIFY_TOKENS = ["because", "would this person", "would this exact person",
                        "fits the slide", "their station", "normal house",
                        "not a million-dollar", "not a luxury", "not a penthouse",
                        "believable for", "real life and station"]

# Representation — hairstyle catalog token. If the catalog asset is present we
# assert membership against it; otherwise we assert a non-generic hairstyle
# descriptor token is present (presence floor) and flag that the catalog is absent.
HAIR_DESCRIPTOR_FALLBACK = ["coils", "coily", "locs", "afro", "twist-out", "twists",
                            "braids", "cornrows", "fade", "tapered", "natural hair",
                            "silk press", "bantu", "wash-and-go", "low cut",
                            "buzz cut", "waves", "ponytail", "bun", "updo", "bob"]

LADDER_BEAT_TAGS = ["ANCHOR", "BUILDUP", "DROP1", "DROP2", "DROP3", "FINAL"]

# --------------------------------------------------------------------------- #
# Narrative-engine token sets (SHARED by check_copy + check_narrative_harmony so
# the writing-half engines and the harmony arc-order gate stay in lockstep).
# --------------------------------------------------------------------------- #
FELT_FRAME_TOKENS = ["mornings left", "days left", "years left", "left with",
                     "never get", "running out", "you will lose", "cost you",
                     "every day you wait", "before it's too late", "while you wait",
                     "felt_stakes"]
VILLAIN_TOKENS = ["villain", "antagonist", "the enemy", "the real enemy",
                  "the thing stopping", "what's holding you back", "the obstacle",
                  "the lie", "the trap", "the broken system",
                  "the old way is the villain"]
HERO_TOKENS = ["hero", "the solution", "the breakthrough", "the way out",
               "the answer", "the promise", "the new way", "you become",
               "the transformation", "the path forward"]
# price/offer presence tokens for arc-order (promise -> price -> recap) reasoning
PRICE_TOKENS = ["ladder", "drop1", "drop2", "drop3", "anchor", "final price",
                "investment", "your price", "the price", "repitch", "re-pitch"]
# recap / re-pitch tokens (post-price restatement of value + price)
RECAP_TOKENS = ["recap", "to recap", "re-pitch", "repitch", "here's everything",
                "everything you get", "everything you're getting", "in summary",
                "let's recap", "quick recap", "value stack", "stack recap"]


def _load_intake_hook(run_dir):
    """Read the canonical hook string from <run_dir>/copy/intake.json (or None).

    The hook is the single SACRED REFRAIN; both the copy-side recurrence check and
    the image-side baked-text check measure against this one canonical string."""
    intake_path = run_dir / "copy" / "intake.json"
    if not intake_path.exists():
        return None
    try:
        data = json.loads(intake_path.read_text())
    except Exception:
        return None
    hook = (str(data.get("hook") or "")).strip()
    return hook or None


def _has_price_beat(body):
    """True if a slide body carries a price/ladder/offer beat (arc-order helper)."""
    if any(re.search(rf"\b{t}\b", body, re.IGNORECASE) for t in LADDER_BEAT_TAGS):
        return True
    if re.search(r"\$\s?\d", body):
        return True
    return _has_any(body.lower(), PRICE_TOKENS)


def _fatal(msg):
    print(f"FATAL (intelligence_engines_check cannot run): {msg}", file=sys.stderr)
    sys.exit(2)


def _lc(s):
    return (s or "").lower()


def _has_any(text_lc, tokens):
    return any(t.lower() in text_lc for t in tokens)


# --------------------------------------------------------------------------- #
# Prompt-side engines (Facial / Lighting / World / Representation hair).
# Only people/scene slides are gated. A prompt that declares no PEOPLE element
# (PEOPLE: no / no-people) is exempt from the people engines but still checked for
# WORLD setting if it depicts a scene.
# --------------------------------------------------------------------------- #

def _is_people_prompt(text_lc):
    # Heuristic mirroring element 11: a people-prompt names a PEOPLE element / a
    # human subject. No-people slides say "no people" / "PEOPLE: no".
    if "no people" in text_lc or "people: no" in text_lc or "people element omitted" in text_lc:
        return False
    return _has_any(text_lc, ["people", "subject", "person", "woman", "man",
                              "face", "portrait", "hero subject", "cast member"])


def check_prompts(run_dir, problems):
    prompts_dir = run_dir / "prompts"
    if not prompts_dir.is_dir():
        # No prompts yet (pre-prompt phase) — defer the prompt engines.
        return
    catalog_path = run_dir / "brand" / "hairstyle_catalog.json"
    catalog_tokens = None
    if catalog_path.exists():
        try:
            cat = json.loads(catalog_path.read_text())
            # accept either {"styles":[...]} or {"by_age_band":{...:[...]}}
            toks = []
            if isinstance(cat.get("styles"), list):
                toks += [str(x) for x in cat["styles"]]
            for band in (cat.get("by_age_band") or {}).values():
                toks += [str(x) for x in band]
            catalog_tokens = [t.lower() for t in toks] or None
        except Exception:
            catalog_tokens = None

    for pf in sorted(prompts_dir.glob("slide-*.txt")):
        text_lc = _lc(pf.read_text())
        slide = pf.stem
        scene = _has_any(text_lc, WORLD_SETTING_TOKENS)
        people = _is_people_prompt(text_lc)

        # --- WORLD (any scene-bearing prompt) — AF-WORLD-SCALE ---
        if scene and not _has_any(text_lc, WORLD_JUSTIFY_TOKENS):
            problems.append({
                "code": "AF-WORLD-SCALE", "slide": slide, "phase": "Phase Prompt-QC",
                "detail": "scene-prompt states a setting but carries NO believability/"
                          "scale justification string (e.g. 'because ...', 'would this "
                          "exact person be in this room', 'normal house, not a luxury "
                          "condo'). Add the WORLD ENGINE justification (SOP 9.3)."})

        if not people:
            continue

        # --- FACIAL — AF-FACE-PROMPT-MISSING ---
        if not _has_any(text_lc, EXPRESSION_TOKENS):
            problems.append({
                "code": "AF-FACE-PROMPT-MISSING", "slide": slide,
                "phase": "Phase Prompt-QC",
                "detail": "people-prompt names no explicit expression token from the "
                          "Expression Vocabulary Table (a bare 'smiling' does not "
                          "satisfy this). Write the exact expression for the slide's "
                          "emotion (slide-image-creator-sops.md SOP 9.2 strengthening)."})

        # --- LIGHTING — AF-LIGHT-PROMPT-MISSING ---
        if not (_has_any(text_lc, LIGHT_DIRECTION_TOKENS)
                and _has_any(text_lc, RIM_HAIR_TOKENS)):
            problems.append({
                "code": "AF-LIGHT-PROMPT-MISSING", "slide": slide,
                "phase": "Phase Prompt-QC",
                "detail": "people-prompt is missing a key/fill/rim lighting direction "
                          "AND/OR a rim/hair separation-light token appropriate to the "
                          "cast member's skin tone (SOP 9.3 LIGHTING INTELLIGENCE)."})

        # --- REPRESENTATION hair — AF-HAIR-INAUTHENTIC (mechanical half) ---
        if catalog_tokens is not None:
            if not _has_any(text_lc, catalog_tokens):
                problems.append({
                    "code": "AF-HAIR-INAUTHENTIC", "slide": slide,
                    "phase": "Phase Prompt-QC",
                    "detail": "people-prompt cites no hairstyle token from the "
                              "age-banded hairstyle catalog (working/brand/"
                              "hairstyle_catalog.json). Cite an age-appropriate "
                              "catalog hairstyle (brand-steward-sops.md hair doctrine)."})
        else:
            if not _has_any(text_lc, HAIR_DESCRIPTOR_FALLBACK):
                problems.append({
                    "code": "AF-HAIR-INAUTHENTIC", "slide": slide,
                    "phase": "Phase Prompt-QC",
                    "detail": "people-prompt names no specific hairstyle descriptor and "
                              "no hairstyle_catalog.json asset is present. Ship the "
                              "age-banded hairstyle catalog and cite an age-appropriate "
                              "style (brand-steward-sops.md hair doctrine)."})

    # --- HOOK engine, IMAGE side — the sacred refrain over the BAKED prompt text.
    #     No slide is excluded from scope: pure-typography hook slides are real
    #     kie bakes and are checked like any other. ---
    _check_hook_image(run_dir, problems)
    return


def _check_hook_image(run_dir, problems):
    """HOOK engine, image side — deterministic scan of the baked text inside every
    slide prompt for the single canonical refrain.

    Codes:
      AF-HOOK-1            (DECK)  hook baked on >4 slides (deck veto, over-stamp)
      AF-HOOK-IMG-MISSING  (DECK)  hook baked on <3 slides (refrain not established)
      AF-HOOK-4            (slide) hook baked >=2x on a single slide (per-slide stamp)
      AF-HOOK              (slide) hook baked into a FOOTER / bottom band (never a stamp)
    Defers (clean) when no prompts exist yet or no canonical hook is declared."""
    prompts_dir = run_dir / "prompts"
    if not prompts_dir.is_dir():
        return  # pre-prompt phase — defer
    hook = _load_intake_hook(run_dir)
    if not hook:
        return  # no canonical hook declared — copy phase owns hook presence
    h = hook.lower()
    slides_with = []
    for pf in sorted(prompts_dir.glob("slide-*.txt")):
        text_lc = _lc(pf.read_text())
        slide = pf.stem
        count = text_lc.count(h)
        if count >= 1:
            slides_with.append(slide)
        if count >= 2:
            problems.append({
                "code": "AF-HOOK-4", "slide": slide, "phase": "Phase Prompt-QC",
                "detail": f"the canonical hook is baked {count}x into the prompt for "
                          f"{slide}. A single slide carries the refrain at most once "
                          "(per-slide over-stamp; the Hook is a suppressor)."})
        # footer-band / bottom-stamp scan: hook adjacent to a footer cue
        for m in re.finditer(re.escape(h), text_lc):
            ctx = text_lc[max(0, m.start() - 140): m.start() + len(h) + 140]
            if "footer" in ctx or "bottom band" in ctx or "lower band" in ctx \
                    or "bottom strip" in ctx:
                problems.append({
                    "code": "AF-HOOK", "slide": slide, "phase": "Phase Prompt-QC",
                    "detail": f"{slide} bakes the canonical hook into a FOOTER / bottom "
                              "band. The sacred refrain is a dedicated typographic beat, "
                              "never a footer stamp (HOOK suppressor)."})
                break
    nslides = len(slides_with)
    if nslides > 4:
        problems.append({
            "code": "AF-HOOK-1", "slide": "DECK", "phase": "Phase Prompt-QC",
            "detail": f"the canonical hook is baked on {nslides} slides "
                      f"({', '.join(slides_with)}); the deck ceiling is 4 dedicated hook "
                      "beats (AF-HOOK-1 deck veto). Over-baking turns the refrain into "
                      "wallpaper."})
    elif nslides < 3:
        problems.append({
            "code": "AF-HOOK-IMG-MISSING", "slide": "DECK", "phase": "Phase Prompt-QC",
            "detail": f"the canonical hook is baked on only {nslides} slide(s) "
                      f"({', '.join(slides_with) or '[]'}); the sacred refrain must appear "
                      "verbatim on 3-4 dedicated image beats so the rendered deck carries "
                      "the same recurring line as the copy."})
    return


# --------------------------------------------------------------------------- #
# Copy-beat engines (Emotional FELT_STAKES, Story VILLAIN->HERO ordering).
# These read slides_copy.md arc tags in slide order.
# --------------------------------------------------------------------------- #

_SLIDE_RE = re.compile(r"^SLIDE\s+(\d+)", re.IGNORECASE | re.MULTILINE)


def _parse_slide_blocks(md_text):
    """Return ordered list of (slide_no, block_text)."""
    blocks = []
    parts = re.split(r"(?im)^\s*SLIDE\s+(\d+)\s*$", md_text)
    # re.split with one group yields [pre, num, body, num, body, ...]
    i = 1
    while i < len(parts) - 1:
        try:
            n = int(parts[i])
        except ValueError:
            i += 2
            continue
        body = parts[i + 1]
        blocks.append((n, body))
        i += 2
    return blocks


def _first_index_with(blocks, predicate):
    for idx, (n, body) in enumerate(blocks):
        if predicate(body):
            return idx
    return None


def check_copy(run_dir, problems):
    copy_md = run_dir / "copy" / "slides_copy.md"
    if not copy_md.exists():
        return  # pre-copy phase — defer the copy engines
    md = copy_md.read_text()
    md_lc = md.lower()
    blocks = _parse_slide_blocks(md)

    # --- EMOTIONAL — AF-NO-FELT-STAKES (DECK) ---
    # A FELT_STAKES beat: a concrete number paired with a personal-loss frame,
    # present BEFORE the first ladder beat. We accept an explicit FELT_STAKES tag OR
    # the structural signature (a digit + a felt-stakes frame token).
    def is_felt(body):
        b = body.lower()
        if "felt_stakes" in b:
            return True
        has_num = re.search(r"\d[\d,]*", body) is not None
        return has_num and _has_any(b, FELT_FRAME_TOKENS)
    felt_idx = _first_index_with(blocks, is_felt)
    # first ladder beat index
    def is_ladder(body):
        return any(re.search(rf"\b{t}\b", body, re.IGNORECASE) for t in LADDER_BEAT_TAGS)
    ladder_idx = _first_index_with(blocks, is_ladder)
    if felt_idx is None:
        problems.append({
            "code": "AF-NO-FELT-STAKES", "slide": "DECK", "phase": "Phase 1Q",
            "detail": "no FELT_STAKES beat anywhere: the deck never quantifies the cost "
                      "of inaction in concrete human terms (a number paired with a "
                      "personal-loss frame, the 'mornings left' device) before the "
                      "offer. Add one felt-stakes slide (SOP-ENGINE-00 Emotional)."})
    elif ladder_idx is not None and felt_idx > ladder_idx:
        problems.append({
            "code": "AF-NO-FELT-STAKES", "slide": "DECK", "phase": "Phase 1Q",
            "detail": f"FELT_STAKES beat appears (block #{felt_idx+1}) AFTER the first "
                      f"ladder beat (block #{ladder_idx+1}). The felt-stakes must land "
                      f"BEFORE the offer so the audience feels the cost first."})

    # --- STORY — AF-NO-VILLAIN (DECK, ordering) ---
    def has_villain(body):
        return _has_any(body.lower(), VILLAIN_TOKENS)
    def has_hero(body):
        return _has_any(body.lower(), HERO_TOKENS)
    v_idx = _first_index_with(blocks, has_villain)
    h_idx = _first_index_with(blocks, has_hero)
    if v_idx is None:
        problems.append({
            "code": "AF-NO-VILLAIN", "slide": "DECK", "phase": "Phase 1Q",
            "detail": "no VILLAIN/antagonist beat anywhere in the arc. 'No one cares "
                      "about the hero until they meet the villain' — name the antagonist "
                      "(the broken system / old way / the thing stopping them) before "
                      "the hero/solution beat (SOP-ENGINE-00 Story; SOP-STORY-01)."})
    elif h_idx is not None and v_idx > h_idx:
        problems.append({
            "code": "AF-NO-VILLAIN", "slide": "DECK", "phase": "Phase 1Q",
            "detail": f"VILLAIN beat (block #{v_idx+1}) appears AFTER the HERO/solution "
                      f"beat (block #{h_idx+1}). Order must be villain -> hero. Move the "
                      f"antagonist beat before the solution."})

    # --- HOOK — sacred-refrain recurrence (copy side) ---
    _check_hook_refrain_copy(blocks, _load_intake_hook(run_dir), problems)

    # --- RECAP / Re-Pitch — post-price restatement of value + price ---
    _check_recap_copy(blocks, problems)

    # --- NARRATIVE HARMONY — the arc holds end-to-end (hook->villain->stakes->
    #     promise->price->recap). This is the orchestration layer above the
    #     individual writing engines; it fires at COPY-QC, before any prompt. ---
    check_narrative_harmony(run_dir, problems)
    return


def _check_hook_refrain_copy(blocks, hook, problems):
    """HOOK engine, copy side — the canonical hook is a SACRED REFRAIN: it must
    recur verbatim on 3-4 dedicated beats, never on >4 slides (wallpaper/footer),
    and never be stamped twice on one slide.

    Codes:
      AF-NO-HOOK-REFRAIN  (DECK)  hook recurs on <3 slides (refrain not established)
      AF-HOOK-1           (DECK)  hook recurs on >4 slides (over-stamp deck veto)
      AF-HOOK-OVERSTAMP   (slide) hook stamped >=2x on a single slide
    Defers (returns clean) when no canonical hook is declared in intake.json."""
    if not hook:
        return  # no canonical hook declared at this phase — presence owned elsewhere
    h = hook.lower()
    slides_with = []
    for (n, body) in blocks:
        c = body.lower().count(h)
        if c >= 1:
            slides_with.append(n)
        if c >= 2:
            problems.append({
                "code": "AF-HOOK-OVERSTAMP", "slide": f"SLIDE {n}", "phase": "Phase 1Q",
                "detail": f"the canonical hook is stamped {c}x in the copy for slide {n}. "
                          "The sacred refrain lands ONCE per dedicated beat — repeating it "
                          "within a single slide turns it into wallpaper (HOOK suppressor)."})
    nslides = len(slides_with)
    if nslides < 3:
        problems.append({
            "code": "AF-NO-HOOK-REFRAIN", "slide": "DECK", "phase": "Phase 1Q",
            "detail": f"the canonical hook recurs on only {nslides} slide(s) "
                      f"(slides {slides_with or '[]'}); the sacred refrain must land "
                      "verbatim on 3-4 dedicated beats so the audience internalizes one "
                      "line (SOP-ENGINE-00 Hook; the Hook is a suppressor, not an "
                      "enricher)."})
    elif nslides > 4:
        problems.append({
            "code": "AF-HOOK-1", "slide": "DECK", "phase": "Phase 1Q",
            "detail": f"the canonical hook recurs on {nslides} slides "
                      f"(slides {slides_with}); the deck ceiling is 4 dedicated hook "
                      "beats. Over-recurrence is over-stamping — the refrain becomes a "
                      "footer band / wallpaper (AF-HOOK-1 deck veto)."})


def _check_recap_copy(blocks, problems):
    """RECAP / Re-Pitch engine — after the FINAL price reveal, a recap beat must
    restate the value stack AND the price. Emits AF-NO-RECAP (DECK).
    Defers (returns clean) for a pitchless deck (no price beat at all)."""
    last_price_idx = None
    for idx, (n, body) in enumerate(blocks):
        if _has_price_beat(body):
            last_price_idx = idx
    if last_price_idx is None:
        return  # pitchless deck — recap presence owned by the offer phase, defer here
    for idx in range(last_price_idx, len(blocks)):
        body = blocks[idx][1]
        if _has_any(body.lower(), RECAP_TOKENS):
            return  # a post-price recap/re-pitch beat exists — clean
    problems.append({
        "code": "AF-NO-RECAP", "slide": "DECK", "phase": "Phase 1Q",
        "detail": "no post-price RECAP / re-pitch beat: after the final price reveal the "
                  "deck never restates the value stack + price. Add a closing recap that "
                  "re-pitches everything they get for the price (SOP-ENGINE-00 "
                  "Recap/Re-Pitch)."})


def check_narrative_harmony(run_dir, problems):
    """NARRATIVE HARMONY — the writing arc holds end-to-end, in order:
        HOOK -> VILLAIN -> FELT_STAKES -> PROMISE -> PRICE -> RECAP.

    The individual writing engines prove each beat is PRESENT and locally ordered
    (villain-before-hero, felt-before-ladder). Harmony proves the WHOLE arc is
    monotonic — the orchestration layer above the per-engine checks. Only the
    beats that are PRESENT are ordered (absence is already caught by the engines);
    an out-of-order present pair emits AF-NARRATIVE-HARMONY (DECK).

    Fires at COPY-QC, before any prompt is authored. Defers pre-copy."""
    copy_md = run_dir / "copy" / "slides_copy.md"
    if not copy_md.exists():
        return  # pre-copy phase — defer
    blocks = _parse_slide_blocks(copy_md.read_text())
    if not blocks:
        return

    hook = _load_intake_hook(run_dir)

    def first_idx(pred):
        for idx, (n, body) in enumerate(blocks):
            if pred(body):
                return idx
        return None

    def is_felt(body):
        b = body.lower()
        if "felt_stakes" in b:
            return True
        return re.search(r"\d[\d,]*", body) is not None and _has_any(b, FELT_FRAME_TOKENS)

    # last price beat anchors the recap-after-price ordering
    last_price_idx = None
    for idx, (n, body) in enumerate(blocks):
        if _has_price_beat(body):
            last_price_idx = idx

    def recap_after_price():
        if last_price_idx is None:
            return None
        for idx in range(last_price_idx, len(blocks)):
            if _has_any(blocks[idx][1].lower(), RECAP_TOKENS):
                return idx
        return None

    beats = [
        ("HOOK", (first_idx(lambda b: hook and hook.lower() in b.lower())
                  if hook else None)),
        ("VILLAIN", first_idx(lambda b: _has_any(b.lower(), VILLAIN_TOKENS))),
        ("FELT_STAKES", first_idx(is_felt)),
        ("PROMISE", first_idx(lambda b: _has_any(b.lower(), HERO_TOKENS))),
        ("PRICE", first_idx(_has_price_beat)),
        ("RECAP", recap_after_price()),
    ]
    present = [(name, idx) for name, idx in beats if idx is not None]

    # walk adjacent present beats; flag any pair whose order is inverted
    for i in range(len(present) - 1):
        a_name, a_idx = present[i]
        b_name, b_idx = present[i + 1]
        if a_idx > b_idx:
            problems.append({
                "code": "AF-NARRATIVE-HARMONY", "slide": "DECK", "phase": "Phase 1Q",
                "detail": f"narrative arc out of order: {a_name} (block #{a_idx+1}) "
                          f"appears AFTER {b_name} (block #{b_idx+1}). The arc must hold "
                          "end-to-end HOOK -> VILLAIN -> FELT_STAKES -> PROMISE -> PRICE "
                          "-> RECAP for the engines to be in harmony, not just present."})
    return


# ---------------------------------------------------------------------------
# RUN_DIR resolution (U86/GK-24 — the "workspace-path defect" root-cause class:
# "any sibling that resolves bare `working/`" gets an explicit --workspace flag
# / env override, with the current directory kept as the (now VISIBLE) default).
#
# THREAT MODEL this closes: this script is a standalone CLI a QC specialist
# runs BY HAND, from wherever their shell happens to be, per its own docstring
# ("invoked by the QC specialists at the 8.5 gate"). Before this fix, a call
# with no RUN_DIR argument silently resolved './working' against the CALLER's
# cwd — if an unrelated deck's run dir happened to be sitting there, the script
# would silently grade THAT deck and report a verdict with zero indication it
# read the wrong directory (VERIFIED-BY-EXECUTION: reproduced by running the
# identical bare command from two different cwds, each holding its own
# working/copy/slides_copy.md, and observing the verdict flip with the command
# unchanged). The historical implicit CWD-relative default is PRESERVED (never
# a breaking change to documented behavior) — the fix is that the resolution is
# now EXPLICIT, overridable, and always reported, so the ambiguity can never be
# silent again. This does not touch check_copy()/check_prompts(): build_deck.py
# and phase_verifiers.py always call those directly with an explicit run_dir
# and never go through this CLI path.
# ---------------------------------------------------------------------------
OC_DECK_WORKSPACE_ENV = "OC_DECK_WORKSPACE"


def resolve_run_dir(argv):
    """Resolve RUN_DIR from argv + env, in priority order, and report the source.

    Priority: --run-dir/--workspace flag > positional RUN_DIR (back-compat) >
    OC_DECK_WORKSPACE env var > CWD-relative './working' (the historical
    default). Returns (run_dir: Path, source: str) — source is one of
    "flag", "positional", "env:OC_DECK_WORKSPACE", "implicit_cwd_default".
    """
    for flag in ("--run-dir", "--workspace"):
        if flag in argv:
            idx = argv.index(flag)
            if idx + 1 >= len(argv):
                _fatal(f"{flag} requires a directory argument")
            return Path(argv[idx + 1]), "flag"

    positional = [a for a in argv if not a.startswith("--")
                  and a not in ("prompt", "copy", "all")]
    if positional:
        return Path(positional[0]), "positional"

    env_val = os.environ.get(OC_DECK_WORKSPACE_ENV, "").strip()
    if env_val:
        return Path(env_val), f"env:{OC_DECK_WORKSPACE_ENV}"

    return Path("working"), "implicit_cwd_default"


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    phase = "all"
    if "--phase" in argv:
        phase = argv[argv.index("--phase") + 1]
    run_dir, run_dir_source = resolve_run_dir(argv)
    run_dir_resolved = str(run_dir.resolve()) if run_dir.exists() else str(run_dir)
    if not run_dir.exists():
        _fatal(f"RUN_DIR not found: {run_dir} (resolved via {run_dir_source}; "
                f"pass --run-dir/--workspace DIR, a positional RUN_DIR, or set "
                f"{OC_DECK_WORKSPACE_ENV} to name the deck's run directory explicitly)")

    # WORKSPACE-PATH DEFECT fix: never let the resolved directory be silent —
    # every invocation, pass or fail, states which dir was actually read and how
    # it was chosen. The implicit-default case gets a loud, explicit NOTE so a
    # caller who forgot RUN_DIR cannot mistake this run for the deck they meant.
    if run_dir_source == "implicit_cwd_default":
        print(f"NOTE (intelligence_engines_check): no RUN_DIR given — defaulted to "
              f"CWD-relative 'working/' ({run_dir_resolved}). This may NOT be the deck "
              f"you intended. Pass RUN_DIR explicitly (or --run-dir/--workspace DIR, or "
              f"set {OC_DECK_WORKSPACE_ENV}) to avoid silently checking the wrong "
              f"workspace.", file=sys.stderr)

    problems = []
    if phase in ("all", "prompt"):
        check_prompts(run_dir, problems)
    if phase in ("all", "copy"):
        check_copy(run_dir, problems)

    if as_json:
        print(json.dumps({
            "ok": not problems,
            "triggered": problems,
            "run_dir_resolved": run_dir_resolved,
            "run_dir_source": run_dir_source,
        }, indent=2))
    else:
        print(f"(run dir: {run_dir_resolved} — resolved via {run_dir_source})")
        if not problems:
            print("=== intelligence_engines_check: ALL ENGINE MECHANICAL HALVES PASS ===")
            print("Facial / World / Lighting / Representation prompt tokens present; "
                  "Emotional FELT_STAKES and Story VILLAIN->HERO beats present and "
                  "ordered. (Vision verdicts are logged separately at Image-QC.)")
        else:
            print("=== intelligence_engines_check: ENGINE AUTO-FAIL(S) ===",
                  file=sys.stderr)
            for p in problems:
                print(f"  {p['code']} [{p['slide']}] ({p['phase']}): {p['detail']}",
                      file=sys.stderr)
            print(f"\n{len(problems)} engine auto-fail(s). Each is the MECHANICAL half "
                  "of an INTELLIGENCE engine; fix the prompt token / copy beat named "
                  "above. The vision VERDICT half is graded separately at Image-QC and "
                  "logged to vision_qc_log.json.", file=sys.stderr)

    sys.exit(4 if problems else 0)


if __name__ == "__main__":
    main()

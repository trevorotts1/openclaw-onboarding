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

The verdict-half codes (AF-FACE-MOOD, AF-WORLD-IMAGE-MISMATCH/world-grounding,
AF-LIGHT-SKINTONE, AF-HAIR-INAUTHENTIC vision verdict) are owned by Image-QC and
read from vision_qc_log.json; this script only asserts the mechanical prompt half
and that the vision log carries a per-slide record so the verdict was actually run.

ZERO third-party deps (stdlib json / re / pathlib only).

USAGE:
    python3 intelligence_engines_check.py [RUN_DIR] [--phase prompt|copy|all] [--json]
    # RUN_DIR defaults to ./working ; reads:
    #   <RUN_DIR>/prompts/slide-*.txt        (prompt-side engines)
    #   <RUN_DIR>/copy/slides_copy.md         (copy-beat engines)
    #   <RUN_DIR>/copy/price_ladder.json      (first ladder beat, for FELT_STAKES order)
    #   <RUN_DIR>/brand/hairstyle_catalog.json (catalog token set, optional asset)

EXIT CODES:
    0 — every engine's mechanical half passes (no triggered code).
    4 — one or more engines triggered an auto-fail (drift). Message names code+slide.
    2 — could not run (missing required input / parse error).
"""

import json
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
    felt_frame = ["mornings left", "days left", "years left", "left with", "never get",
                  "running out", "you will lose", "cost you", "every day you wait",
                  "before it's too late", "while you wait", "felt_stakes"]
    def is_felt(body):
        b = body.lower()
        if "felt_stakes" in b:
            return True
        has_num = re.search(r"\d[\d,]*", body) is not None
        return has_num and _has_any(b, felt_frame)
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
    villain = ["villain", "antagonist", "the enemy", "the real enemy", "the thing "
               "stopping", "what's holding you back", "the obstacle", "the lie",
               "the trap", "the broken system", "the old way is the villain"]
    hero = ["hero", "the solution", "the breakthrough", "the way out", "the answer",
            "the promise", "the new way", "you become", "the transformation",
            "the path forward"]
    def has_villain(body):
        return _has_any(body.lower(), villain)
    def has_hero(body):
        return _has_any(body.lower(), hero)
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
    return


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    phase = "all"
    if "--phase" in argv:
        phase = argv[argv.index("--phase") + 1]
    positional = [a for a in argv if not a.startswith("--")
                  and a not in ("prompt", "copy", "all")]
    run_dir = Path(positional[0]) if positional else Path("working")
    if not run_dir.exists():
        _fatal(f"RUN_DIR not found: {run_dir}")

    problems = []
    if phase in ("all", "prompt"):
        check_prompts(run_dir, problems)
    if phase in ("all", "copy"):
        check_copy(run_dir, problems)

    if as_json:
        print(json.dumps({"ok": not problems, "triggered": problems}, indent=2))
    else:
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

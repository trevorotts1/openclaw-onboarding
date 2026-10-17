#!/usr/bin/env python3
"""Validate BlackCEO production prompts (Skill 71, Item 10 as rebuilt by
FIX-PLAN Amendment 6, Parts B and C; length doctrine superseded by owner
Decision 1, 2026-10-15).

WHAT GOVERNS NOW:

- Element completeness governs acceptance: the guide's ten element jobs
  are present and fully expressed. A missing element is an automatic
  failure. (Counting convention, per the guide: NFC-normalized, trimmed,
  Unicode code points; the prompt's SHA-256 is recorded in telemetry.)
- Length is governed by the KIE rule 12 band, adopted as this skill's
  native authoring target by owner Decision 1 (2026-10-15): author each
  prompt to 95 to 100 percent of the model's live prompt field maximum,
  never below the 80 percent floor, by genuine specification only.
  This validator renders the band verdict per prompt at the prompt
  stage; the numbers come from band_numbers(), which calls the shared
  enforcer's budget() (shared-utils/kie_prompt_enforcer.py) so this
  skill and the transport can never drift apart. Below the floor FAILS
  (budget exit 3, naming the exact characters to ADD and the count to
  the 95 percent target); above the maximum FAILS (budget exit 4,
  naming the exact characters to CUT); floor-to-target passes with a
  below-target warning; in band passes. Characters, percent of the
  maximum, and the full budget block land in the prompt's telemetry,
  and the prompt stage gate records the budget block on the item close
  entry. The policy layer (references/prompt-budget-policy.json)
  records each model's maximum; cap_status survives there as
  provenance only and no longer carries overflow semantics. Verbatim
  fields (text a model speaks or sings exactly) are exempt from the
  floor; this validator only ever receives the descriptive field.
- The requested aspect ratio is confirmed at validate time against
  the model's aspect-ratio enum in Skill 74's registry snapshot
  (74-kie-live-adapter/references/kie-model-registry.json) and the
  answer is recorded in telemetry (ratio_confirmation): confirmed;
  not_in_enum (fails at validate time by name); unverified (enum
  unreadable; recorded, never reported as confirmed); not_recorded.
- Where NO maximum is recorded for a model, no band verdict is
  rendered (budget status UNKNOWN, percent_of_max null) and the
  retained 2,000-character TRIPWIRE is the operative short-prompt
  flag: a complete prompt under it is flagged for manual element
  re-inspection by the reviewer, recorded, never auto-failed.
  Token-limited models are checked in tokens, never converted to a
  fake character cap; this validator has no tokenizer, so it records
  character telemetry and renders no character verdict for them.
- Padding detection is a hard fail at close (Part C-rule 4, retained): repeated
  n-gram blocks beyond what the verbatim blocks and locks explain,
  boilerplate not traceable to the Page Visual Bible, the selected
  style's extraction file, or the image's inventory entry, and element
  sections that do not reference the image's specific subject.
- Style fidelity is checked against the run's SELECTION RECORD
  (image-inventory-prompts/style-selection.json; references/style-selection.md)
  and the checked-in trait EXTRACTION for the selected style only
  (references/style-traits/*.json): lock/anchor/trait expression by the
  extraction's designer-specified checkable tokens (a lock with no
  tokens is UNCHECKABLE-BY-DESIGN, reported, never silently passed);
  the recorded 3x3 subject zone expressed in Element C; verbatim ONLY
  where the guide mandates it (Signature Grade Block STARTING Element F
  on SECRET_SAUCE_ONLY pages, the no-text sentence, the spelling-lock
  pattern per authorized string, the style-reference directive, a
  supplied Identity Lock Block); the human-only denylist screen (the
  denylist is validator-only data and is never echoed beyond its class);
  the Avoid screen scoped to the generation instruction (never the
  anti-drift/negative block that legitimately quotes it); contamination
  redefined (undeclared foreign style fails; a declared Cinematic rule D
  blend passes ONLY with recorded owner authorization, FIX-PLAN
  conflict N2; the Visual Artists exactly-one-system rule, with the
  selected system's branded name REQUIRED present); Element G
  representation specificity for Black and African-descended subjects.
- The negative block is checked by DEFECT-CLASS COVERAGE (image guide
  section 11): specific "Do not..." statements covering at least six of
  the repository's eight classes, not by one fixed string.

RETIRED HERE (withdrawn designs, do not reintroduce): Amendment 6
Part C's length position (element completeness alone governs length;
length as telemetry only; a hard ceiling only where a VERIFIED cap
exists; cap-status overflow semantics with warn-only overflow for
NOT_PUBLISHED and OWNER_CONFIRMED caps) — withdrawn by owner
Decision 1 (2026-10-15), which adopted the rule 12 band as the
native authoring target and supersedes Part C wherever the two
conflict; the verbatim style_block paste check; the
composition-phrase quota; the index-heading contamination screen;
the single fixed negative-block string as the coverage test.

CLI (contract shape kept: the stage contract calls
`validate_prompt.py {file} {sauce}`):
  validate_prompt.py <prompt-file> [--model ID] [--sauce-only] [--json]
      [--selection PATH] [--inventory PATH] [--image-id ID]
      [--bible PATH] [--policy PATH] [--traits-dir PATH]
      [--require-selection] [--strict-runtime]
When the prompt file lives in a run layout
(<run>/image-inventory-prompts/IMG-*.txt), the selection record, the
desktop-wireframe inventory, and the visual-mockup bible are
auto-discovered from the run folder unless flags override them.

Exit codes: 0 pass, 1 fail, 2 unreadable input.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path


def _load_kie_prompt_enforcer():
    """Best-effort import of shared-utils/kie_prompt_enforcer.py.

    Since owner Decision 1 (2026-10-15) the enforcer DOES render the
    length verdict inside Skill 71: band_numbers() calls its budget()
    for the band math. Absence is not an error: band_numbers() then
    falls back to identical arithmetic.
    """
    try:
        envd = os.environ.get("OPENCLAW_SKILLS_DIR")
        dirs = [p / "shared-utils" for p in Path(__file__).resolve().parents]
        dirs += ([Path(envd) / "shared-utils"] if envd else []) + [
            Path.home() / ".openclaw" / "skills" / "shared-utils",
            Path("/data/.openclaw/skills/shared-utils")]
        for d in dirs:
            if (d / "kie_prompt_enforcer.py").is_file():
                if str(d) not in sys.path:
                    sys.path.insert(0, str(d))
                import kie_prompt_enforcer
                return kie_prompt_enforcer
    except Exception:
        return None
    return None


KPE = _load_kie_prompt_enforcer()

SKILL_ROOT = Path(__file__).resolve().parent.parent
GRADE_BLOCK_FILE = SKILL_ROOT / "assets" / "brand" / "signature-grade-block.txt"
POLICY_FILE = SKILL_ROOT / "references" / "prompt-budget-policy.json"
TRAITS_DIR = SKILL_ROOT / "references" / "style-traits"

IMAGE_MODEL_DEFAULT = "gpt-image-2-5-sunburst-text-to-image"  # Skill 66 registry id; override with --model

# Verbatim texts mandated by Image Guide v5 (see full-read notes R1):
NO_TEXT_SENTENCE = "No text, no letters, no words anywhere in the image."
STYLE_REFERENCE_DIRECTIVE = (
    "Use the attached images only as style reference for color grading, "
    "lighting, and composition -- do not copy their subjects, faces, or text.")
SPELLING_LOCK_TEMPLATE = (
    "Render this exact string, letter-for-letter, correctly spelled, with "
    "no added, dropped, doubled, or substituted characters: '{string}'.")

# The nine named subject zones of the guide's 3x3 grid (section 6D).
ZONES = ["upper-left", "upper-center", "upper-right",
         "middle-left", "center", "middle-right",
         "lower-left", "lower-center", "lower-right"]

# The repository's eight negative-block defect classes (guide section 11)
# with mechanical matchers. Class coverage, not a fixed string, is the
# checkable rule (FIX-PLAN C3(b)).
DEFECT_CLASSES = {
    "text errors": [r"misspell", r"garbled", r"text errors?", r"wrong letters?",
                    r"typos?", r"render any text", r"invented text", r"gibberish",
                    r"no text, no letters"],
    "logo mutation": [r"logo"],
    "anatomy": [r"anatom", r"fingers?", r"distort\w* (hands|eyes|teeth|faces?|limbs?)",
                r"extra (hands?|fingers?|limbs?|digits?)",
                r"introduc\w* (hands?|faces?)", r"impossible (object )?construction"],
    "contrast/legibility": [r"low[- ]contrast", r"contrast", r"legib", r"readab",
                            r"unreadable"],
    "placeholder tokens": [r"placeholder", r"lorem", r"dummy (graphic|image|text)",
                           r"bracketed (token|marker|placeholder)"],
    "demographic defaults/skin fidelity": [r"skin", r"bleach", r"melanin",
                                           r"undertone", r"demographic",
                                           r"lighten\w* (her|his|their|the) skin"],
    "watermarks": [r"watermark", r"corner tag", r"caption", r"badge",
                   r"footer", r"production (label|tag|identifier)"],
    "style drift": [r"flat, muted", r"pastel", r"desaturated", r"style drift",
                    r"off-style", r"generic stock", r"washed-out", r"dull colors?"],
}
LOGO_MUTATION_VERBS = r"(mutat|distort|invent|approximat|redraw|alter|fabricat)"

# Guide section 7 vocabulary for the legacy (no inventory entry)
# representation presence screen. Mechanical approximation, labeled as
# such: the entry-bound check is the strict one.
SKIN_SPECIFICITY_TOKENS = ["deep brown", "rich brown", "dark brown", "medium brown",
                           "light brown", "undertone", "melanin", "skin tone",
                           "complexion", "ebony", "mahogany", "chestnut skin",
                           "golden undertone", "neutral-red", "warm undertone",
                           "cool undertone", "olive undertone"]
HAIR_SPECIFICITY_TOKENS = ["coil", "locs", "braids", "braided", "twists", "cornrows",
                           "afro", "tapered", "fade", "waves", "curls", "curly",
                           "natural cut", "hairstyle", "hair construction",
                           "silk press", "bantu", "finger coils", "wash-and-go"]

CANONICAL_ELEMENTS = [
    ("Asset class band", r"ASSET\s*:.*\|\s*BAND\s*:|ASSET\s+CLASS\s+BAND"),
    ("Subject and scene", r"SUBJECT\s*\+\s*SCENE|SUBJECT\s+AND\s+SCENE"),
    ("Composition grid", r"COMPOSITION\s+GRID"),
    ("Locked style block", r"STYLE\s+BLOCK"),
    ("Typography verbatim copy",
     r"TYPOGRAPHY\s*\+\s*VERBATIM\s+COPY|TYPOGRAPHY\s+AND\s+VERBATIM\s+COPY|TYPOGRAPHY\s+VERBATIM\s+COPY"),
    ("Lighting and color grade",
     r"LIGHTING\s*\+\s*COLOR\s+GRADE|LIGHTING\s+AND\s+COLOR\s+GRADE"),
    ("People/representation", r"PEOPLE\s*/\s*REPRESENTATION|PEOPLE\s+AND\s+REPRESENTATION"),
    ("Logo/reference direction", r"LOGO\s*/\s*REFERENCE(?:\s+DIRECTIVE)?|LOGO\s+AND\s+REFERENCE(?:\s+DIRECTION)?"),
    ("Technical", r"\bTECHNICAL\b"),
    ("Negative block", r"NEGATIVE\s+BLOCK"),
]
ELEMENT_INDEX = {name: i for i, (name, _p) in enumerate(CANONICAL_ELEMENTS)}

PLACEHOLDER_PATTERNS = [
    re.compile(r"\[\s*TODO\s*\]", re.I),
    re.compile(r"\{\{[^{}]+\}\}"),
    re.compile(r"<\s*(insert|replace|placeholder)[^>]*>", re.I),
    re.compile(r"\[\s*placeholder\s*\]", re.I),
    re.compile(r"\bPLACEHOLDER\b"),
]

DECLARED_TRAITS = {"centered composition", "spacious framing",
                   "sparse negative space", "uniform ratio"}
DECLARATION_FIELDS = ["era", "social_world", "character", "tone", "set",
                      "camera_language", "styling_logic", "beauty_logic",
                      "color_logic"]
SUBJECT_ELEMENTS = {"Subject and scene", "Composition grid", "People/representation"}


def norm_ws(text):
    return re.sub(r"\s+", " ", text).strip()


def norm_dashes(text):
    return text.replace("\u2014", "--").replace("\u2013", "--").replace("\u2011", "-")


def _heading_like(text, start):
    """A canonical-heading match is heading-like when only an optional
    element number precedes it on its line (so a prose mention of the
    word TECHNICAL inside another element is not taken as a heading)."""
    line_start = text.rfind("\n", 0, start) + 1
    prefix = text[line_start:start]
    return re.fullmatch(r"\s*(\d{1,2}\.)?\s*", prefix) is not None


def split_elements(text):
    """Split a prompt into its canonical element sections.

    Returns {element_name: body_text} using the guide's canonical
    ten-element headings; a body runs to the next element's heading.
    Heading-like matches win over prose mentions of the same words.
    """
    found = []
    for name, pattern in CANONICAL_ELEMENTS:
        matches = list(re.finditer(pattern, text, re.I))
        if not matches:
            continue
        chosen = next((m for m in matches if _heading_like(text, m.start())),
                      matches[0])
        found.append((chosen.start(), chosen.end(), name))
    found.sort()
    sections = {}
    for i, (start, end, name) in enumerate(found):
        stop = found[i + 1][0] if i + 1 < len(found) else len(text)
        sections[name] = text[end:stop]
    return sections


def load_grade_block():
    if not GRADE_BLOCK_FILE.exists():
        return None
    return GRADE_BLOCK_FILE.read_text(encoding="utf-8").rstrip("\n")


def load_policy(path=None):
    p = Path(path) if path else POLICY_FILE
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"models": [], "default": {"max_chars": None, "cap_status": "UNKNOWN",
                                          "unit": "chars"},
                "tripwire_chars": 2000}


def cap_for_model(model, policy):
    """Resolve the policy entry for a model id (longest prefix wins)."""
    best = None
    for entry in policy.get("models", []):
        match = entry.get("match", "")
        if model == match or model.startswith(match):
            if best is None or len(match) > len(best.get("match", "")):
                best = entry
    if best is not None:
        return best
    return policy.get("default", {"max_chars": None, "cap_status": "UNKNOWN",
                                   "unit": "chars"})


# ------------------------------------------------------- rule 12 band

FLOOR_PCT, TARGET_PCT = 80, 95  # KIE rule 12, adopted by Decision 1


def band_numbers(max_chars):
    """The rule 12 band for a recorded maximum:
    {"max", "floor", "target_min", "target_max"}.

    Calls the shared enforcer's budget() so this skill and the
    transport compute one set of numbers from one implementation.
    The fallback repeats the enforcer's integer math exactly (ceiling
    of 80 and 95 percent) for the case where the enforcer cannot be
    imported; it is character-identical arithmetic, not a second
    implementation that can drift.
    """
    m = int(max_chars)
    if KPE is not None:
        try:
            return KPE.budget(m)
        except Exception:
            pass
    return {"max": m, "floor": -(-m * FLOOR_PCT // 100),
            "target_min": -(-m * TARGET_PCT // 100), "target_max": m}


def _registry_path():
    """Skill 74's model registry snapshot (kie-model-registry.json)."""
    envd = os.environ.get("OPENCLAW_SKILLS_DIR")
    roots = list(Path(__file__).resolve().parents)
    if envd:
        roots.append(Path(envd))
    roots += [Path.home() / ".openclaw" / "skills",
              Path("/data/.openclaw/skills")]
    for root in roots:
        candidate = root / "74-kie-live-adapter" / "references" \
            / "kie-model-registry.json"
        if candidate.is_file():
            return candidate
    return None


def model_ratio_enum(model):
    """The model's aspect-ratio enum from the Skill 74 registry
    snapshot. Returns (enum, source) or (None, None) when the enum
    cannot be read (snapshot missing/unreadable, model absent, or no
    enum recorded): the caller records that as unverified, never as
    confirmed."""
    path = _registry_path()
    if path is None:
        return None, None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    for entry in doc.get("models") or []:
        if isinstance(entry, dict) and entry.get("id") == model:
            enum = ((entry.get("input_fields") or {})
                    .get("aspect_ratio") or {}).get("enum")
            if isinstance(enum, list) and enum:
                return [str(x) for x in enum], str(path)
            return None, None
    return None, None


def requested_ratio_of(entry):
    """The requested aspect ratio recorded on an inventory entry
    (requested_ratio, then aspect_ratio, then ratio), or None."""
    if not isinstance(entry, dict):
        return None
    for key in ("requested_ratio", "aspect_ratio", "ratio"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def ratio_confirmation(model, entry, errors, notes):
    """Confirm the entry's requested ratio against the model's enum
    (Item 4 part 3): the 21:9 class of question is settled at
    validate time, not discovered at generation. The record lands in
    telemetry["ratio_confirmation"] in one of four states."""
    requested = requested_ratio_of(entry)
    if requested is None:
        return {"status": "not_recorded", "requested_ratio": None,
                "model": model}
    enum, source = model_ratio_enum(model)
    if enum is None:
        notes.append(
            f"Ratio confirmation unverified: the aspect-ratio enum for "
            f"{model} could not be read from the Skill 74 registry "
            f"snapshot; requested ratio {requested!r} is recorded, not "
            "confirmed.")
        return {"status": "unverified", "requested_ratio": requested,
                "model": model}
    if requested in enum:
        notes.append(
            f"Ratio confirmed: requested ratio {requested} is in the "
            f"aspect-ratio enum for {model} (Skill 74 registry "
            "snapshot).")
        return {"status": "confirmed", "requested_ratio": requested,
                "model": model, "enum_source": source}
    errors.append(
        f"Requested ratio {requested!r} is not in the aspect-ratio "
        f"enum for {model} ({', '.join(enum)}); author the prompt to "
        "a supported ratio or correct the inventory entry (Item 4 "
        "part 3).")
    return {"status": "not_in_enum", "requested_ratio": requested,
            "model": model, "enum_source": source}


def load_json_file(path, label, errors):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Could not read {label} at {path}: {exc}")
        return None


# ---------------------------------------------------------------- padding

def padding_errors(stripped, words, masked_regions=()):
    """Part C-rule 4 mechanical padding screens.

    (a) repeated n-gram blocks beyond what the verbatim blocks and locks
    explain (verbatim regions are masked before counting); plus the
    legacy bulk screens (unique-word ratio, repeated 60-char substring).
    """
    errors = []
    if words and len(words) >= 50:
        unique = {w.lower() for w in words}
        ratio = len(unique) / len(words)
        if ratio < 0.25:
            errors.append(
                f"Padding detected: unique-word ratio {ratio:.2f} is below 0.25 "
                f"({len(unique)} unique of {len(words)} words).")
    window = 60
    if len(stripped) >= window:
        counts = {}
        for i in range(len(stripped) - window + 1):
            sub = stripped[i:i + window]
            counts[sub] = counts.get(sub, 0) + 1
        worst_sub, worst_count = max(counts.items(), key=lambda kv: kv[1])
        if worst_count > 3:
            errors.append(
                f"Padding detected: a {window}-character substring occurs {worst_count} times "
                f"(maximum 3): {worst_sub[:60]!r}.")

    # Word 8-gram repetition outside the verbatim/lock regions.
    masked = stripped
    for region in masked_regions:
        if region:
            masked = masked.replace(region, " ")
    tokens = re.findall(r"\S+", masked)
    n = 8
    if len(tokens) >= n * 3:
        shingles = {}
        for i in range(len(tokens) - n + 1):
            gram = " ".join(w.lower() for w in tokens[i:i + n])
            shingles[gram] = shingles.get(gram, 0) + 1
        repeated = {g: c for g, c in shingles.items() if c >= 3}
        if repeated:
            worst = max(repeated.items(), key=lambda kv: kv[1])
            errors.append(
                f"Padding detected: an 8-word sequence repeats {worst[1]} times outside the "
                f"verbatim blocks and locks ({worst[0][:80]!r}...); repeated n-gram blocks are "
                "padding under Part C-rule 4(a), however they are phrased.")
        covered = sum(c * n for c in shingles.values() if c >= 2)
        if covered > 0.5 * len(tokens):
            errors.append(
                f"Padding detected: repeated 8-word sequences cover {covered} of {len(tokens)} "
                "words; the prompt is mostly repetition (Part C-rule 4(a)).")
    return errors


def traceability_errors(sections, vocab, subject_vocab, image_id, masked=()):
    """Part C-rule 4(b)/(c): boilerplate and generic-filler screens.

    Runs only when run context exists (bible / extraction / inventory
    vocabulary supplied). An element section with substantial content
    sharing NO vocabulary with the bible, the selected style's
    extraction, and the inventory entry is untraceable boilerplate.
    Subject-bearing elements must additionally reference the image's
    specific subject. Two principled exclusions: the Negative block is
    a compliance artifact screened by the defect-class coverage rule,
    not art direction; and verbatim-mandated spans (the Signature
    Grade Block and the other B3(iii) blocks) trace to the sauce and
    the guide, which are themselves concrete run artifacts under rule
    4(b)'s wording, so they are masked before the screen runs.
    """
    errors = []
    who = f" for {image_id}" if image_id else ""
    for name, body in sections.items():
        if name == "Negative block":
            continue
        for span in masked:
            if span:
                body = body.replace(span, " ")
        words = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-']{3,}", body)}
        if len(words) < 40:
            continue
        if vocab and not (words & vocab):
            errors.append(
                f"Padding detected{who}: element '{name}' shares no vocabulary with the Page "
                "Visual Bible, the selected style's extraction, or the image's inventory entry; "
                "untraceable boilerplate fails Part C-rule 4(b).")
        if name in SUBJECT_ELEMENTS and subject_vocab and not (words & subject_vocab):
            errors.append(
                f"Padding detected{who}: element '{name}' does not reference the image's "
                "specific subject at all; an element that could be pasted unchanged into any "
                "other image's prompt is generic filler (Part C-rule 4(c)).")
    return errors


def vocabulary_of(*texts):
    words = set()
    for text in texts:
        if text:
            words |= {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-']{3,}", text)}
    return words


# ------------------------------------------------------- negative block

def negative_block_coverage(section_body):
    """Return (covered_classes, statements) for Element J's body.

    Only specific prohibition statements (containing 'do not' or starting
    with 'never') count as coverage evidence, per guide section 11.
    """
    statements = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", section_body)
                  if s.strip()]
    prohibitions = [s for s in statements
                    if re.search(r"\bdo not\b", s, re.I) or re.match(r"(?i)never\b", s)]
    covered = set()
    for stmt in prohibitions:
        low = stmt.lower()
        for cls, matchers in DEFECT_CLASSES.items():
            if cls in covered:
                continue
            if cls == "logo mutation":
                if re.search(r"logo", low) and re.search(LOGO_MUTATION_VERBS, low):
                    covered.add(cls)
                continue
            if any(re.search(m, low) for m in matchers):
                covered.add(cls)
    return covered, prohibitions


# ------------------------------------------------------- run context

def normalize_image_id(value):
    text = str(value).strip().upper()
    if text.startswith("IMAGE-"):
        text = "IMG-" + text[len("IMAGE-"):]
    return text


def load_inventory_entries(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict):
        items = data.get("images") or data.get("items") or data.get("inventory")
    else:
        items = data
    if not isinstance(items, list):
        return {}
    out = {}
    for item in items:
        if isinstance(item, dict) and item.get("id") is not None:
            out[normalize_image_id(item["id"])] = item
    return out


def is_supplied_entry(entry):
    """A run-context inventory entry is a supplied asset when its source
    begins with "supplied" (e.g. "supplied-logo", "supplied-founder-photo"):
    the asset already exists and no generation is performed for it
    (Item 3 supplied-asset path)."""
    if not isinstance(entry, dict):
        return False
    source = entry.get("source")
    return isinstance(source, str) and source.strip().lower().startswith("supplied")


def inventory_entry_ratio(entry):
    """The aspect ratio recorded on an inventory entry, under any of the
    keys the run records use, or None."""
    if not isinstance(entry, dict):
        return None
    for key in ("requested_ratio", "aspect_ratio", "ratio"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def validate_supplied_record(text, entry, image_id):
    """Validate a stage file as a supplied-asset record (Item 3): the
    record must name the image id, carry the asset sha256 recorded on
    the inventory entry, carry the inventory aspect ratio, declare
    itself supplied, and carry an explicit no-generation declaration.
    Every missing or mismatched field fails by name. Returns errors."""
    errors = []
    who = image_id or "this image"
    upper = text.upper()
    if image_id is None or normalize_image_id(image_id) not in upper:
        errors.append(f"supplied-asset record does not name its image id "
                      f"({who}); a supplied-asset record must name the image "
                      "it stands in for")
    sha = entry.get("sha256")
    if not isinstance(sha, str) or not sha.strip():
        errors.append(f"inventory entry for {who} records no sha256 for "
                      "the supplied asset; a supplied-asset record cannot "
                      "be verified without the inventory sha256")
    elif sha.strip().lower() not in text.lower():
        errors.append(f"supplied-asset record for {who} does not carry "
                      f"the asset sha256 recorded on the inventory entry "
                      f"({sha.strip()})")
    ratio = inventory_entry_ratio(entry)
    if ratio is None:
        errors.append(f"inventory entry for {who} records no aspect "
                      "ratio; a supplied-asset record must carry the "
                      "inventory aspect ratio")
    elif ratio not in text:
        errors.append(f"supplied-asset record for {who} does not carry "
                      f"the inventory aspect ratio ({ratio})")
    if not re.search(r"\bsupplied\b", text, re.IGNORECASE):
        errors.append(f"supplied-asset record for {who} does not declare "
                      "itself supplied")
    if not re.search(r"no generation|not generated|never generated",
                     text, re.IGNORECASE):
        errors.append(f"supplied-asset record for {who} carries no "
                      "explicit no-generation declaration")
    return errors


def selection_record_for(selection_doc, image_id):
    """The record governing image_id (later records win), or None."""
    if not isinstance(selection_doc, dict):
        return None
    records = selection_doc.get("selections")
    if not isinstance(records, list):
        return None
    chosen = None
    for record in records:
        if not isinstance(record, dict):
            continue
        applies = record.get("applies_to")
        if applies == "all":
            chosen = record
        elif isinstance(applies, list) and image_id is not None:
            if normalize_image_id(image_id) in {normalize_image_id(x) for x in applies}:
                chosen = record
    return chosen


def load_extraction(record, errors, who):
    """Load and hash-verify the extraction entry for a selection record."""
    ref = record.get("extraction_ref")
    if ref is None:
        return None, None
    if not isinstance(ref, dict) or not ref.get("path"):
        errors.append(f"{who}: extraction_ref is malformed; the selection record must name "
                      "the extraction file and its sha256 (Part B1).")
        return None, None
    path = SKILL_ROOT / ref["path"]
    if not path.is_file():
        errors.append(f"{who}: extraction file named by the selection record does not exist: "
                      f"{ref['path']}.")
        return None, None
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if ref.get("sha256") and ref["sha256"] != digest:
        errors.append(f"{who}: extraction_ref sha256 mismatch for {ref['path']}: the record "
                      "was authored against a different extraction than the checked-in file; "
                      "re-author the selection record against the current extraction.")
        return None, None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        errors.append(f"{who}: extraction file {ref['path']} is unreadable: {exc}")
        return None, None
    entries = doc.get("entries") if isinstance(doc, dict) else None
    entry = entries.get(record.get("style_id")) if isinstance(entries, dict) else None
    if entry is None:
        errors.append(f"{who}: style_id {record.get('style_id')!r} is not in the extraction "
                      f"{ref['path']}; the selection names a style the checked-in extraction "
                      "does not cover.")
    return doc, entry


def load_denylist(library, traits_dir):
    path = Path(traits_dir) / f"denylist-{library}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def style_index(traits_dir):
    """All (style_id, branded_name, library) across the extraction files."""
    out = []
    for library in ("photographers", "cinematic", "visual-artists"):
        path = Path(traits_dir) / f"{library}.json"
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for style_id, entry in (doc.get("entries") or {}).items():
            out.append((style_id, entry.get("branded_name"), library))
    return out


def token_present(token, haystack_low):
    return token.lower() in haystack_low


def check_tokens_of(item):
    tokens = item.get("check_tokens")
    return [t for t in tokens if isinstance(t, str) and t.strip()] if isinstance(tokens, list) else []


# ------------------------------------------------------- style checks

def entry_text(entry):
    """Flatten an inventory entry for phrase searches."""
    return json.dumps(entry, ensure_ascii=False) if isinstance(entry, dict) else ""


def recorded_zone(entry):
    """The 3x3 subject zone recorded on an inventory entry, or None.

    Accepts a structured subject_zone field, a named zone inside the
    composition/positioning text, or the coordinate style of the guide's
    own examples (x=61%, y=31%).
    """
    if not isinstance(entry, dict):
        return None
    for key in ("subject_zone", "zone"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip().lower() in ZONES:
            return ("named", value.strip().lower())
    comp = ""
    for key in ("composition", "composition_positioning", "Composition/positioning"):
        if isinstance(entry.get(key), str):
            comp = entry[key]
            break
    if not comp:
        comp = entry_text(entry)
    low = comp.lower()
    coords = re.search(r"x\s*=\s*(\d{1,3})\s*%\s*,?\s*y\s*=\s*(\d{1,3})\s*%", low)
    if coords:
        return ("coords", (coords.group(1), coords.group(2)))
    for zone in sorted(ZONES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(zone)}\b", low):
            return ("named", zone)
    return None


def zone_expressed(zone, element_c_low):
    if zone is None:
        return True
    kind, value = zone
    if kind == "named":
        return re.search(rf"\b{re.escape(value)}\b", element_c_low) is not None
    x, y = value
    return re.search(rf"x\s*=\s*{x}\s*%\s*,?\s*y\s*=\s*{y}\s*%", element_c_low) is not None


def generation_scope(text, sections):
    """The text the Avoid screen runs against (Part B3(v)).

    A GENERATION INSTRUCTION section, when present, is the whole scope.
    Otherwise the scope is the prompt minus the negative block and any
    anti-drift section: compiled prompts legitimately quote the Avoid
    list there.
    """
    # A compiled prompt's FINAL GENERATION INSTRUCTION field (Cinematic
    # section 0A schema) is the generation instruction, whole and only.
    fin = re.search(r"(?im)^[^\n]*FINAL GENERATION INSTRUCTION[^\n]*$", text)
    if fin:
        return text[fin.end():]
    for name, body in sections.items():
        if "GENERATION" in name.upper():
            return body
    scope = text
    for name, body in sections.items():
        if name == "Negative block":
            scope = scope.replace(body, " ")
    # Drop any anti-drift block: from its heading line to the next
    # canonical element heading (compiled prompts quote the Avoid list
    # there legitimately).
    for m in list(re.finditer(r"(?im)^[^\n]*ANTI[- ]DRIFT[^\n]*$", scope)):
        stops = [mm.start() for _n, pat in CANONICAL_ELEMENTS
                 for mm in re.finditer(pat, scope[m.end():], re.I)]
        stop = m.end() + min(stops) if stops else len(scope)
        scope = scope[:m.start()] + " " + scope[stop:]
    return scope


NEGATION_BEFORE = re.compile(r"\b(no|not|never|avoid|without|do not|don't)\b[^.]{0,40}$", re.I)


def avoid_hit(tokens, scope_low):
    """True when every token of an avoid item is instructed in scope.

    Tokens match on word boundaries (the token 'clutter' must not fire
    inside 'uncluttered'). A match immediately governed by a negation is
    a prohibition being stated, not the forbidden thing being
    instructed.
    """
    for token in tokens:
        pattern = re.compile(rf"(?<!\w){re.escape(token.lower())}(?!\w)")
        match = pattern.search(scope_low)
        if not match:
            return False
        idx = match.start()
        window_start = max(0, scope_low.rfind(".", 0, idx))
        prefix = scope_low[window_start:idx]
        if NEGATION_BEFORE.search(prefix + " "):
            return False
    return True


def expression_items(library, entry):
    """Yield (label, check_tokens) expression obligations for an entry."""
    if library == "photographers":
        locks = entry.get("locks")
        if entry.get("modes"):
            return  # handled by caller per selected mode
        if isinstance(locks, dict):
            for cat, lock in locks.items():
                if isinstance(lock, dict):
                    yield (f"lock '{cat}'", check_tokens_of(lock))
    elif library == "cinematic":
        for anchor in entry.get("anchors") or []:
            if isinstance(anchor, dict):
                yield (f"anchor '{anchor.get('name')}'", check_tokens_of(anchor))
    elif library == "visual-artists":
        for trait in entry.get("mandatory_traits") or []:
            if isinstance(trait, dict):
                label = (trait.get("text") or "trait")[:60]
                yield (f"mandatory trait '{label}'", check_tokens_of(trait))


def style_checks(text, sections, ctx, errors, warnings, notes):
    """Part B3 checks. ctx carries selection record, extraction entry,
    inventory entry, image_id, traits_dir."""
    record = ctx["record"]
    entry = ctx["inventory_entry"]
    image_id = ctx.get("image_id") or "this image"
    who = f"{image_id}:"
    library = record.get("source_library")
    text_low = text.lower()
    extraction = ctx.get("extraction_entry")

    if library == "image-guide-sauce-only":
        notes.append(f"{who} sauce-only selection; style checks are the guide's own "
                     "(grade-block position, verbatim blocks, contamination screen).")
    elif extraction is None:
        errors.append(f"{who} selection record names library {library!r} but no extraction "
                      "entry could be loaded; style fidelity cannot be verified.")
        return

    # -- B3(i) lock / anchor / trait expression (or B3(vii) procedural)
    uncheckable = []
    if extraction is not None and extraction.get("class") == "procedural":
        block = record.get("declaration_block")
        if not isinstance(block, dict):
            errors.append(f"{who} procedural-class style {record.get('style_id')} requires a "
                          "declaration_block in the selection record (era, social world, "
                          "character, tone, set, camera language, styling logic, beauty "
                          "logic, color logic); none is recorded (Part B3(vii)).")
        else:
            missing = [f for f in DECLARATION_FIELDS
                       if not (isinstance(block.get(f), str) and block.get(f).strip())]
            if missing:
                errors.append(f"{who} declaration_block for procedural style "
                              f"{record.get('style_id')} is incomplete; missing or empty "
                              f"field(s): {', '.join(missing)} (Part B3(vii)).")
            consistency = extraction.get("consistency_tokens")
            for token in consistency if isinstance(consistency, list) else []:
                if isinstance(token, str) and not token_present(token, text_low):
                    errors.append(f"{who} prompt is inconsistent with the declaration block: "
                                  f"the extraction's consistency token {token!r} is absent "
                                  "(Part B3(vii)).")
            notes.append(f"{who} procedural-class style: trait checks replaced by the "
                         "declaration-block check; coherence among the declarations is "
                         "reviewer judgment (Part B6).")
    elif extraction is not None:
        obligations = []
        va_modes = extraction.get("modes")
        if library == "visual-artists" and isinstance(va_modes, list) and va_modes:
            mode = record.get("mode")
            if not mode:
                errors.append(f"{who} style {record.get('style_id')} is multi-mode and the "
                              "selection record names no mode (Part B1).")
            elif mode not in va_modes:
                errors.append(f"{who} selection record mode {mode!r} is not one of the "
                              f"extraction's modes for {record.get('style_id')}: "
                              f"{', '.join(va_modes)}.")
        if library == "photographers" and extraction.get("modes"):
            mode = record.get("mode")
            modes = extraction["modes"]
            if not mode:
                errors.append(f"{who} style {record.get('style_id')} is multi-mode and the "
                              "selection record names no mode; no single lock set exists "
                              "until a mode is chosen (Part B1).")
            elif mode not in modes:
                errors.append(f"{who} selection record mode {mode!r} is not one of the "
                              f"extraction's modes for {record.get('style_id')}: "
                              f"{', '.join(sorted(modes))}.")
            else:
                locks = (modes[mode] or {}).get("locks") or {}
                for cat, lock in locks.items():
                    if isinstance(lock, dict):
                        obligations.append((f"lock '{cat}' (mode {mode})",
                                            check_tokens_of(lock)))
        else:
            obligations = list(expression_items(library, extraction))
        for label, tokens in obligations:
            if not tokens:
                uncheckable.append(label)
                continue
            missing = [t for t in tokens if not token_present(t, text_low)]
            if missing:
                errors.append(f"{who} the selected style's {label} is not expressed in the "
                              f"prompt's descriptive language; missing token(s): "
                              f"{', '.join(repr(t) for t in missing)}. Token expression is "
                              "the mechanical approximation of the guide's test that the "
                              "prompt communicates the grammar with the style name deleted "
                              "(Part B3(i)).")
        for item in extraction.get("uncheckable_by_design") or []:
            label = item.get("lock") or item.get("anchor") or item.get("trait") \
                if isinstance(item, dict) else str(item)
            if not any(str(label) in seen for seen in uncheckable):
                uncheckable.append(str(label))
    for label in uncheckable:
        notes.append(f"UNCHECKABLE-BY-DESIGN{who} {label} has no checkable tokens in the "
                     "extraction; reported, never silently passed (Part B3(i)). Its "
                     "expression is reviewer judgment at the extraction's acceptance gate "
                     "and in the item review.")

    # Style stated in Element D (guide L2046): family + branded style/ID.
    if extraction is not None:
        style_section = sections.get("Locked style block", "")
        stated = (record.get("style_id", "") in style_section
                  or (record.get("branded_name") or "") in style_section)
        if not stated:
            errors.append(f"{who} Element D (locked style block) states neither the selected "
                          f"style_id {record.get('style_id')!r} nor its branded name "
                          f"{record.get('branded_name')!r}; the guide requires Element D to "
                          "state the family and branded style and encode its locks in "
                          "descriptive language.")

    # -- B3(ii) 3x3 subject zone in Element C
    zone = recorded_zone(entry)
    element_c = sections.get("Composition grid", "")
    if zone is not None:
        if not zone_expressed(zone, element_c.lower()):
            errors.append(f"{who} the inventory entry records subject zone "
                          f"{zone[1]!r} but Element C does not express it; the recorded "
                          "3x3 zone must appear in Element C (Part B3(ii)).")
        entry_low = entry_text(entry).lower()
        if "text-safe" in entry_low and "text-safe" not in element_c.lower():
            errors.append(f"{who} the inventory entry records a text-safe zone but "
                          "Element C does not name one (Part B3(ii)).")
        if "margin" in entry_low and "margin" not in element_c.lower():
            errors.append(f"{who} the inventory entry records crop-safe margins but "
                          "Element C does not state margins (Part B3(ii)).")

    # -- B3(iv) denylist screen (validator-only data; class named, name withheld)
    denylist = load_denylist(library, ctx["traits_dir"]) if library else None
    if denylist:
        for name in denylist.get("names") or []:
            if re.search(rf"(?i)\b{re.escape(name)}\b", text):
                errors.append(f"{who} denylist hit: the prompt contains a {library} "
                              "human-only source name (class: human source name; the name "
                              "itself is withheld from this report per Part B3(iv)). Human "
                              "source names never reach a prompt.")
        for title in denylist.get("source_work_titles") or []:
            if re.search(rf"(?i)\b{re.escape(title)}\b", text):
                errors.append(f"{who} denylist hit: the prompt contains a {library} "
                              "source-work title (class: source-work title; withheld per "
                              "Part B3(iv)).")
        for phrase in denylist.get("constructions") or []:
            if phrase.lower() in text_low:
                errors.append(f"{who} denylist hit: the prompt uses the prohibited "
                              f"construction class {phrase!r} (Part B3(iv)); styles are "
                              "encoded as descriptive language, never attributed to a "
                              "human source.")

    # -- B3(v) Avoid screen, generation-instruction scope only
    if extraction is not None:
        scope_low = generation_scope(text, sections).lower()
        for item in extraction.get("avoid") or []:
            if not isinstance(item, dict) or item.get("judgment_only"):
                continue
            tokens = check_tokens_of(item)
            if tokens and avoid_hit(tokens, scope_low):
                errors.append(f"{who} the generation instruction instructs content the "
                              f"selected style's Avoid list prohibits: "
                              f"{(item.get('text') or '')[:80]!r} (Part B3(v)).")

    # -- B3(vi) contamination, redefined
    allowed_ids = {record.get("style_id")}
    allowed_names = {record.get("branded_name")}
    blend = record.get("blend")
    if library == "cinematic" and isinstance(blend, dict):
        if blend.get("owner_authorized") is not True:
            errors.append(f"{who} the selection record declares a Cinematic rule D blend "
                          f"({blend.get('primary_style_id')} + "
                          f"{blend.get('secondary_style_id')}) without recorded owner "
                          "authorization; a declared blend passes ONLY with "
                          "owner_authorized: true (FIX-PLAN conflict N2).")
        else:
            allowed_ids.add(blend.get("secondary_style_id"))
            traits = blend.get("secondary_traits") or []
            if not (1 <= len(traits) <= 3):
                errors.append(f"{who} the declared blend must name 1 to 3 secondary "
                              f"traits; it names {len(traits)} (rule D).")
            for trait in traits:
                if isinstance(trait, str) and trait.lower() not in text_low:
                    errors.append(f"{who} declared blend trait {trait!r} is recorded in "
                                  "the selection record but not expressed in the prompt.")
    hybrid_ok = (library == "visual-artists" and record.get("hybrid_flag") is True
                 and record.get("hybrid_requested_by_user") is True)
    for style_id, branded, lib in style_index(ctx["traits_dir"]):
        if style_id in allowed_ids or (branded and branded in allowed_names):
            continue
        hit = None
        if style_id and re.search(rf"\b{re.escape(style_id)}\b", text):
            hit = f"style id {style_id}"
        elif branded and branded.lower() in text_low:
            hit = f"branded system {branded!r}"
        if hit:
            if hybrid_ok and lib == "visual-artists":
                notes.append(f"{who} second Visual Artists system present ({hit}) under a "
                             "recorded user-requested hybrid (hybrid_flag).")
                continue
            errors.append(f"{who} contamination: the prompt carries undeclared foreign "
                          f"style material ({hit}, {lib}); exactly one system governs an "
                          "image unless a blend or hybrid is declared in the selection "
                          "record (Part B3(vi)).")
    if library == "visual-artists":
        branded = record.get("branded_name") or ""
        if branded and branded.lower() not in text_low:
            errors.append(f"{who} the prompt does not carry the selected Visual Artists "
                          f"system's branded name {branded!r}; a compliant prompt carries "
                          "it at assembly slot 1 (Part B3(vi)).")

    # -- B3(vi) representation specificity (Element G)
    representation_checks(text, sections, entry, who, errors)


def representation_checks(text, sections, entry, who, errors):
    element_g = sections.get("People/representation", "")
    g_declares_black = bool(re.search(
        r"\bblack\b|african[- ]descended", element_g, re.I))
    subjects, rep = [], {}
    entry_declares_black = False
    if isinstance(entry, dict) and entry:
        entry_low = entry_text(entry).lower()
        entry_declares_black = bool(re.search(
            r"\bblack\b|african[- ]descended|african american", entry_low))
        for key in ("people", "subjects", "casting"):
            value = entry.get(key)
            if isinstance(value, list):
                subjects = [s for s in value if isinstance(s, dict)]
        if isinstance(entry.get("representation"), dict):
            rep = entry["representation"]
    if subjects or rep:
        # The entry carries representation records: any recorded
        # specificity strings must be expressed in Element G, and an
        # entry that declares Black subjects must record them.
        skin = rep.get("skin_tone") or next(
            (s.get("skin_tone") for s in subjects if s.get("skin_tone")), None)
        hair = rep.get("hair") or next(
            (s.get("hair") for s in subjects if s.get("hair")), None)
        facial = rep.get("facial_hair") or next(
            (s.get("facial_hair") for s in subjects if s.get("facial_hair")), None)
        if entry_declares_black and (not skin or not hair):
            errors.append(f"{who} the inventory entry records Black or African-descended "
                          "subjects without the representation specificity the guide "
                          "requires (a recorded skin tone and hair construction per "
                          "subject); generic description of a Black subject is an "
                          "auto-fail in the guide (Part B3(vi)).")
            return
        g_low = element_g.lower()
        if skin and skin.lower() not in g_low:
            errors.append(f"{who} Element G does not carry the entry's recorded skin "
                          f"tone {skin!r} (Part B3(vi)).")
        if hair and hair.lower() not in g_low:
            errors.append(f"{who} Element G does not carry the entry's recorded hair "
                          f"construction {hair!r} (Part B3(vi)).")
        if facial and facial.lower() not in g_low:
            errors.append(f"{who} Element G does not carry the entry's recorded facial "
                          f"hair state {facial!r} (Part B3(vi)).")
        return
    if entry_declares_black:
        # The entry declares Black subjects in its own text but records
        # no representation data at all: the B3(vi) data gap.
        errors.append(f"{who} the inventory entry records Black or African-descended "
                      "subjects without the representation specificity the guide "
                      "requires (a recorded skin tone and hair construction per "
                      "subject); generic description of a Black subject is an "
                      "auto-fail in the guide (Part B3(vi)).")
        return
    if g_declares_black:
        # No entry data governs representation: the guide section 7
        # presence screen over the prompt's own text.
        whole_low = text.lower()
        if not any(t in whole_low for t in SKIN_SPECIFICITY_TOKENS):
            errors.append(f"{who} the prompt describes a Black subject with no skin "
                          "specificity anywhere (no skin tone, undertone, or complexion "
                          "language); the guide makes a generically described Black "
                          "subject an auto-fail (Part B3(vi), guide section 7).")
        if not any(t in whole_low for t in HAIR_SPECIFICITY_TOKENS):
            errors.append(f"{who} the prompt describes a Black subject with no hair "
                          "specificity anywhere (no hair construction language); see "
                          "guide section 7 (Part B3(vi)).")


# ------------------------------------------------------- verbatim checks

def verbatim_checks(text, sections, ctx, errors, notes):
    """Part B3(iii): verbatim ONLY where the guide mandates it."""
    entry = ctx.get("inventory_entry") if ctx else None
    who = f"{ctx.get('image_id')}:" if ctx and ctx.get("image_id") else ""
    sauce = bool(ctx and ctx.get("sauce_only"))

    # (a) Signature Grade Block STARTS Element F, sauce-only only.
    if sauce:
        block = load_grade_block()
        if block is None:
            errors.append("FAIL: Signature Grade Block file is missing "
                          f"({GRADE_BLOCK_FILE}); cannot verify --sauce-only.")
        else:
            body = sections.get("Lighting and color grade")
            if body is None:
                errors.append("Missing Signature Grade Block placement: with --sauce-only, Element F "
                              "(lighting and color grade) must START with the Signature "
                              "Grade Block verbatim, but the element is absent.")
            else:
                lead = body.lstrip(" \t\r\n:-\u2013\u2014")
                if not norm_ws(lead).startswith(norm_ws(block)):
                    errors.append(
                        "Missing Signature Grade Block at the mandated position: with --sauce-only "
                        "the Signature Grade Block from assets/brand/"
                        "signature-grade-block.txt must appear verbatim at the START of "
                        "Element F (lighting and color grade), not merely somewhere in "
                        "the prompt (Image Guide v5 L2388; Part B3(iii)(a)).")

    entry_low = entry_text(entry).lower() if entry else ""
    text_mode = None
    if isinstance(entry, dict):
        text_mode = str(entry.get("text_mode") or "").strip().lower()
    element_e = sections.get("Typography verbatim copy", "")

    # (b) No-text sentence, verbatim, for visual-only images. Triggered by
    # the entry's text mode or Element E's own no-text declaration.
    visual_only = text_mode in ("none", "visual-only", "visual_only") or \
        bool(re.search(r"\bno text\b", element_e, re.I))
    if visual_only:
        stem = NO_TEXT_SENTENCE.rstrip(".")
        if not re.search(re.escape(stem) + r"\s*[.;]", text):
            errors.append(f"{who}visual-only image is missing the mandated no-text "
                          f"sentence verbatim: {NO_TEXT_SENTENCE!r} (Part B3(iii)(b)).")

    # (c) Spelling-lock pattern per authorized string.
    strings = []
    if isinstance(entry, dict):
        for key in ("authorized_strings", "verbatim_strings", "approved_strings"):
            value = entry.get(key)
            if isinstance(value, list):
                strings += [s for s in value if isinstance(s, str) and s.strip()]
        single = entry.get("authorized_string")
        if isinstance(single, str) and single.strip():
            strings.append(single)
    for s in strings:
        lock = SPELLING_LOCK_TEMPLATE.format(string=s)
        if lock not in text:
            errors.append(f"{who}authorized string {s!r} lacks its spelling lock; the "
                          f"prompt must contain verbatim: {lock!r} (Part B3(iii)(c)).")

    # Text-bearing contrast statement (guide L2481-2488): when the entry
    # records the text and background colors, Element E must state both.
    if isinstance(entry, dict):
        text_color = entry.get("text_color")
        bg_color = entry.get("background_color") or entry.get("surface_color")
        if text_color and text_color.lower() not in element_e.lower():
            errors.append(f"{who}Element E does not state the entry's recorded text "
                          f"color {text_color!r}; text-bearing images must state both "
                          "the text color and the exact background/surface color "
                          "(guide section 12C criterion 10).")
        if bg_color and bg_color.lower() not in element_e.lower():
            errors.append(f"{who}Element E does not state the entry's recorded "
                          f"background/surface color {bg_color!r} (guide section 12C "
                          "criterion 10).")

    # (d) Style-reference directive, bound to style-reference files only.
    has_style_ref = False
    if isinstance(entry, dict):
        refs = entry.get("references")
        if isinstance(refs, list):
            has_style_ref = any(isinstance(r, dict)
                                and str(r.get("role", "")).lower() == "style"
                                for r in refs)
        elif isinstance(refs, dict):
            has_style_ref = str(refs.get("role", "")).lower() == "style"
    if has_style_ref:
        if norm_dashes(STYLE_REFERENCE_DIRECTIVE) not in norm_dashes(text):
            errors.append(f"{who}the entry attaches style-only references but the prompt "
                          f"lacks the style-reference directive verbatim: "
                          f"{STYLE_REFERENCE_DIRECTIVE!r} (Part B3(iii)(d)).")

    # (e) A supplied Identity Lock Block, verbatim.
    if isinstance(entry, dict):
        block = entry.get("identity_lock_block")
        if isinstance(block, str) and block.strip():
            if block.strip() not in text:
                errors.append(f"{who}the entry supplies an Identity Lock Block but the "
                              "prompt does not carry it verbatim (Part B3(iii)(e)).")


# ------------------------------------------------------- inspect / main

def inspect(text, model=IMAGE_MODEL_DEFAULT, sauce_only=False, ctx=None,
            policy=None):
    text = unicodedata.normalize("NFC", text)
    stripped = text.strip()
    chars = len(stripped)  # guide convention: NFC, trimmed, code points (N3)
    words = re.findall(r"\S+", stripped)
    errors, warnings, notes = [], [], []
    policy = policy or load_policy()
    sections = split_elements(stripped)

    # --- telemetry + budget (Decision 1: the rule 12 band governs length)
    cap = cap_for_model(model, policy)
    percent = None
    if cap.get("unit") == "chars" and cap.get("max_chars"):
        percent = round(100.0 * chars / cap["max_chars"], 2)
    telemetry = {
        "characters": chars,
        "sha256": hashlib.sha256(stripped.encode("utf-8")).hexdigest(),
        "model": model,
        "cap_status": cap.get("cap_status", "UNKNOWN"),
        "cap_unit": cap.get("unit", "chars"),
        "model_max_chars": cap.get("max_chars"),
        "percent_of_max": percent,
    }
    budget = {"status": "UNKNOWN", "budget_exit": 0, "max": None,
              "floor": None, "target_min": None, "target_max": None,
              "add_chars": 0, "add_to_target_chars": 0, "cut_chars": 0,
              "cap_status": cap.get("cap_status", "UNKNOWN")}
    if cap.get("unit") == "tokens":
        notes.append("Token-limited model: the ceiling is denominated in tokens and is "
                     "not converted to a character cap; character telemetry is recorded "
                     "and no character band verdict is rendered by this validator.")
    elif cap.get("max_chars"):
        band = band_numbers(cap["max_chars"])
        budget.update(band)
        pct = 100.0 * chars / band["max"]
        if chars > band["max"]:
            budget["status"] = "ABOVE_MAX"
            budget["budget_exit"] = 4
            budget["cut_chars"] = chars - band["max"]
            errors.append(
                f"prompt is {chars} chars; max is {band['max']}; CUT exactly "
                f"{budget['cut_chars']} chars (cap status "
                f"{cap.get('cap_status', 'UNKNOWN')}; budget exit 4).")
        elif chars < band["floor"]:
            budget["status"] = "BELOW_FLOOR"
            budget["budget_exit"] = 3
            budget["add_chars"] = band["floor"] - chars
            budget["add_to_target_chars"] = band["target_min"] - chars
            errors.append(
                f"prompt is {chars} chars ({pct:.1f}% of max {band['max']}); floor is "
                f"{band['floor']}: ADD at least {budget['add_chars']} chars "
                f"({budget['add_to_target_chars']} to reach the 95 percent target of "
                f"{band['target_min']}) of genuine specification (budget exit 3).")
        elif chars < band["target_min"]:
            budget["status"] = "BELOW_TARGET"
            budget["add_to_target_chars"] = band["target_min"] - chars
            warnings.append(
                f"prompt is {chars} chars ({pct:.1f}% of max {band['max']}); in the "
                f"band but below the 95 percent target of {band['target_min']}: ADD "
                f"{budget['add_to_target_chars']} chars of genuine specification to "
                "reach the target (budget exit 0).")
        else:
            budget["status"] = "OK"
            notes.append(f"prompt is {chars} chars ({pct:.1f}% of max {band['max']}); "
                         "in band, budget exit 0.")
    else:
        notes.append("Model cap UNKNOWN: percent_of_max is null and no band verdict is "
                     "rendered; the tripwire below is the operative short-prompt flag "
                     "for this model.")
    telemetry["budget"] = budget

    # --- ratio confirmation (Item 4 part 3)
    ratio_entry = ctx.get("inventory_entry") if isinstance(ctx, dict) else None
    telemetry["ratio_confirmation"] = ratio_confirmation(model, ratio_entry,
                                                         errors, notes)

    tripwire = policy.get("tripwire_chars", 2000)
    if chars < tripwire:
        warnings.append(f"TRIPWIRE: complete prompt is {chars} characters, under the "
                        f"{tripwire}-character smell-test tripwire; the reviewer must "
                        "manually re-inspect every element for completeness and record "
                        "that re-inspection in the review file. This is NOT an "
                        "automatic failure (the tripwire is retained for models with "
                        "no recorded maximum; Decision 1).")

    # --- placeholders (unchanged legacy screen)
    for pattern in PLACEHOLDER_PATTERNS:
        match = pattern.search(stripped)
        if match:
            errors.append(f"Unresolved placeholder detected: {match.group(0)!r}.")

    # --- element completeness (Part C-rule 1(a)/(b))
    missing_elements = [name for name, _p in CANONICAL_ELEMENTS if name not in sections]
    if missing_elements:
        errors.append(
            "Missing canonical element heading(s) from the ten-element prompt anatomy: "
            + ", ".join(missing_elements) + ". A missing element is an automatic "
            "failure under element completeness (Part C-rule 1(a)).")
    for name, body in sections.items():
        if len(norm_ws(body)) < 10:
            errors.append(f"Element '{name}' is present but empty of descriptive "
                          "content; an element that carries none of the substance its "
                          "job requires fails element completeness (Part C-rule 1(b)).")

    # --- negative block: defect-class coverage (guide section 11)
    neg_body = sections.get("Negative block")
    if neg_body is not None:
        covered, _prohibitions = negative_block_coverage(neg_body)
        if len(covered) < 6:
            errors.append(
                "Negative block defect-class coverage too low: the negative block "
                f"covers {len(covered)} of the repository's 8 defect classes "
                f"({', '.join(sorted(covered)) or 'none'}); at least 6 are required, "
                "written as specific Do not statements naming the actual risk "
                "(Image Guide v5 section 11).")

    # --- padding (Part C-rule 4)
    grade_block = load_grade_block()
    masked = [grade_block] if grade_block else []
    errors.extend(padding_errors(stripped, words, masked))

    # --- run context: selection record + style checks (Part B)
    if ctx:
        ctx.setdefault("traits_dir", TRAITS_DIR)
        if ctx.get("record") is not None:
            style_checks(stripped, sections, ctx, errors, warnings, notes)
        elif isinstance(ctx.get("inventory_entry"), dict):
            # No selection governs this image (a Part B1 gap the gate
            # change requests address), but the entry-bound
            # representation rules still apply to the prompt.
            representation_checks(stripped, sections, ctx["inventory_entry"],
                                  f"{ctx.get('image_id')}:", errors)
        eff_sauce = sauce_only or \
            (ctx.get("record") or {}).get("source_library") == "image-guide-sauce-only"
        verbatim_checks(stripped, sections, dict(ctx, sauce_only=eff_sauce),
                        errors, notes)
        # Traceability / generic-filler screens (need run vocabulary).
        vocab_texts = []
        bible_path = ctx.get("bible_path")
        if bible_path and Path(bible_path).is_file():
            vocab_texts.append(Path(bible_path).read_text(encoding="utf-8"))
        if ctx.get("extraction_entry") is not None:
            vocab_texts.append(json.dumps(ctx["extraction_entry"], ensure_ascii=False))
        entry = ctx.get("inventory_entry")
        if isinstance(entry, dict):
            vocab_texts.append(entry_text(entry))
        vocab = vocabulary_of(*vocab_texts)
        subject_vocab = vocabulary_of(entry_text(entry)) if isinstance(entry, dict) else set()
        if vocab:
            errors.extend(traceability_errors(sections, vocab, subject_vocab,
                                              ctx.get("image_id"),
                                              masked=masked))
    else:
        # Legacy path: verbatim checks that need no run context.
        if sauce_only:
            verbatim_checks(stripped, sections,
                            {"sauce_only": True, "inventory_entry": None,
                             "image_id": None}, errors, notes)
        # Representation presence screen from the prompt's own text.
        representation_checks(stripped, sections, None, "", errors)

    return {"characters": chars, "words": len(words), "telemetry": telemetry,
            "errors": errors, "warnings": warnings, "notes": notes}


def discover_context(prompt_file, args):
    """Assemble run context from flags and run-layout auto-discovery."""
    prompt_path = Path(prompt_file)
    image_id = args.image_id or normalize_image_id(prompt_path.stem) \
        if prompt_path.stem.upper().startswith(("IMG-", "IMAGE-")) else args.image_id
    run_dir = None
    if prompt_path.parent.name == "image-inventory-prompts":
        run_dir = prompt_path.parent.parent
    selection_path = args.selection
    if selection_path is None and run_dir is not None:
        candidate = run_dir / "image-inventory-prompts" / "style-selection.json"
        if candidate.is_file():
            selection_path = candidate
    inventory_path = args.inventory
    if inventory_path is None and run_dir is not None:
        candidate = run_dir / "desktop-wireframe" / "image-inventory.json"
        if candidate.is_file():
            inventory_path = candidate
    bible_path = args.bible
    if bible_path is None and run_dir is not None:
        candidate = run_dir / "visual-mockup" / "page-visual-bible.json"
        if candidate.is_file():
            bible_path = candidate

    errors = []
    record = None
    extraction_entry = None
    # The inventory entry is loaded before selection governance: a
    # supplied entry (source begins with "supplied") is exempt from
    # style-selection governance and takes the supplied-asset record
    # path in main() instead of the prompt pipeline (Item 3).
    entry = None
    if inventory_path is not None and image_id is not None:
        entry = load_inventory_entries(inventory_path).get(normalize_image_id(image_id))
    supplied = is_supplied_entry(entry)
    if selection_path is not None:
        doc = load_json_file(selection_path, "selection record", errors)
        if doc is not None:
            if image_id is None:
                records = doc.get("selections") or []
                record = records[0] if len(records) == 1 else None
                if record is None and records:
                    errors.append("The selection record carries multiple selections and "
                                  "no --image-id was given; cannot determine which "
                                  "selection governs this prompt.")
            else:
                record = selection_record_for(doc, image_id)
            if record is None and image_id is not None and not errors and not supplied:
                errors.append(f"The selection record at {selection_path} carries no "
                              f"selection governing {image_id}; every image must be "
                              "governed by a selection record before its prompt is "
                              "authored (Part B1).")
            if record is not None and not errors and not supplied:
                _doc, extraction_entry = load_extraction(record, errors,
                                                         image_id or "this image")
    elif args.require_selection and not supplied:
        errors.append("No selection record found for this prompt (looked for "
                      "image-inventory-prompts/style-selection.json in the run layout); "
                      "a run with no selection record cannot close "
                      "image-inventory-prompts (Part B1).")

    if record is None and entry is None and bible_path is None and not errors:
        return None, []
    ctx = {"record": record, "extraction_entry": extraction_entry,
           "inventory_entry": entry, "image_id": image_id,
           "supplied_entry": entry if supplied else None,
           "bible_path": bible_path, "traits_dir": args.traits_dir,
           "sauce_only": args.sauce_only}
    return ctx, errors


def main():
    parser = argparse.ArgumentParser(
        description="Validate a production prompt: element completeness, the rule 12 "
                    "prompt budget band (Decision 1), style fidelity against the "
                    "selection record and trait extraction (Part B), padding, "
                    "placeholders, verbatim blocks.")
    parser.add_argument("prompt_file", type=Path)
    parser.add_argument("--model", default=IMAGE_MODEL_DEFAULT,
                        help="KIE image model id (band policy + ratio enum; "
                             "default %(default)s).")
    parser.add_argument("--runtime-max", type=int, default=None,
                        help="DEPRECATED and ignored: length verdicts follow the "
                             "rule 12 band (Decision 1), not a runtime max.")
    parser.add_argument("--strict-runtime", action="store_true",
                        help="Treat warnings (including tripwire and below-target "
                             "band warnings) as failures.")
    parser.add_argument("--sauce-only", action="store_true",
                        help="SECRET_SAUCE_ONLY page: the Signature Grade Block must "
                             "START Element F verbatim.")
    parser.add_argument("--selection", type=Path, default=None,
                        help="Path to the run's style-selection.json.")
    parser.add_argument("--inventory", type=Path, default=None,
                        help="Path to desktop-wireframe/image-inventory.json.")
    parser.add_argument("--image-id", default=None,
                        help="Inventory id of the image this prompt authors (e.g. IMG-001).")
    parser.add_argument("--bible", type=Path, default=None,
                        help="Path to visual-mockup/page-visual-bible.json.")
    parser.add_argument("--policy", type=Path, default=None,
                        help="Prompt-budget policy JSON (default references/"
                             "prompt-budget-policy.json).")
    parser.add_argument("--traits-dir", type=Path, default=TRAITS_DIR,
                        help="Directory holding the style-traits extraction and "
                             "denylist files.")
    parser.add_argument("--require-selection", action="store_true",
                        help="Fail when no selection record governs this prompt.")
    parser.add_argument("--json", action="store_true", help="Emit JSON result.")
    args = parser.parse_args()

    try:
        text = args.prompt_file.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"FAIL: could not read prompt: {exc}")
        return 2

    policy = load_policy(args.policy)
    ctx, ctx_errors = discover_context(args.prompt_file, args)
    if ctx is not None and ctx.get("supplied_entry") is not None:
        # Item 3 supplied-asset path: the inventory entry for this file's
        # image records a source beginning with "supplied", so the stage
        # file is validated as a supplied-asset record and stops here;
        # no prompt validation is performed on it.
        entry = ctx["supplied_entry"]
        image_id = ctx.get("image_id")
        errors = ctx_errors + validate_supplied_record(text, entry, image_id)
        source = entry.get("source")
        if args.json:
            print(json.dumps({"supplied_asset": True, "image_id": image_id,
                              "source": source, "characters": len(text),
                              "words": len(text.split()), "errors": errors,
                              "warnings": [], "notes": []}, indent=2))
        elif errors:
            print(f"FAIL: {image_id} supplied-asset record (source: {source}) "
                  "does not validate.")
            for item in errors:
                print(f"ERROR: {item}")
        else:
            print(f"PASS: {image_id} is a supplied asset (source: {source}); "
                  "validated as a supplied-asset record; no prompt "
                  "validation performed.")
        return 1 if errors else 0
    result = inspect(text, args.model, sauce_only=args.sauce_only, ctx=ctx,
                     policy=policy)
    result["errors"] = ctx_errors + result["errors"]
    if args.strict_runtime and result["warnings"]:
        result["errors"].extend(result["warnings"])
        result["warnings"] = []

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "FAIL" if result["errors"] else "PASS"
        print(f"{status}: {result['characters']} characters, {result['words']} words.")
        for item in result["notes"]:
            print(f"NOTE: {item}")
        for item in result["warnings"]:
            print(f"WARNING: {item}")
        for item in result["errors"]:
            print(f"ERROR: {item}")

    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())

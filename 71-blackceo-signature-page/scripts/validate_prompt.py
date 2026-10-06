#!/usr/bin/env python3
"""Validate BlackCEO production prompts: length, placeholders, canonical
ten-element anatomy, negative block, padding, and (with --sauce-only) the
Signature Grade Block.

1.0.3 enforcement additions (order C4):
- NFC normalization before every count
- each of the ten canonical element headings (image guide v5 section 4)
  must be present
- required negative-block wording: "Do not produce flat, muted, pastel, desaturated"
- padding rejection: unique-word ratio < 0.25, or any 60-character substring
  occurring more than 3 times
- --sauce-only: the exact contents of assets/brand/signature-grade-block.txt
  must appear as a substring
- the 5,000-20,000 house band and the 19,000 runtime warning are RETIRED: prompt length is KIE prompt rule 12
  (owner order 2026-10-05), measured by the shared enforcer shared-utils/kie_prompt_enforcer.py from the live
  Skill 74 prompt-budget limit of the image model (95 to 100 percent of the maxLength, hard floor 80 percent,
  hard ceiling 100 percent; the message names the exact characters to add or cut).
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

def _load_kie_prompt_enforcer():
    """Find shared-utils/kie_prompt_enforcer.py (repo checkout or installed skills tree) and import it."""
    envd = os.environ.get("OPENCLAW_SKILLS_DIR")
    dirs = [p / "shared-utils" for p in Path(__file__).resolve().parents]
    dirs += ([Path(envd) / "shared-utils"] if envd else []) + [
        Path.home() / ".openclaw" / "skills" / "shared-utils", Path("/data/.openclaw/skills/shared-utils")]
    for d in dirs:
        if (d / "kie_prompt_enforcer.py").is_file():
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))
            import kie_prompt_enforcer
            return kie_prompt_enforcer
    raise ImportError("shared-utils/kie_prompt_enforcer.py not found; install or update the onboarding skills")


KPE = _load_kie_prompt_enforcer()

SKILL_ROOT = Path(__file__).resolve().parent.parent
GRADE_BLOCK_FILE = SKILL_ROOT / "assets" / "brand" / "signature-grade-block.txt"

IMAGE_MODEL_DEFAULT = "gpt-image-2-5-sunburst-text-to-image"  # Skill 66 registry id; override with --model

# Canonical ten-element prompt anatomy — names copied from the image guide v5,
# section 4 ("canonical ten-element prompt anatomy") and the production heading
# spellings used in the guide's own teaching prompts. Do not invent new names.
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

NEGATIVE_BLOCK_REQUIRED = "Do not produce flat, muted, pastel, desaturated"

PLACEHOLDER_PATTERNS = [
    re.compile(r"\[\s*TODO\s*\]", re.I),
    re.compile(r"\{\{[^{}]+\}\}"),
    re.compile(r"<\s*(insert|replace|placeholder)[^>]*>", re.I),
    re.compile(r"\[\s*placeholder\s*\]", re.I),
    # Bare marker only in its authored uppercase form: the ordinary lowercase English
    # word in a normal sentence (for example a negative-block instruction about not
    # rendering the word "placeholder") is not an unresolved placeholder.
    re.compile(r"\bPLACEHOLDER\b"),
]


def load_grade_block():
    if not GRADE_BLOCK_FILE.exists():
        return None
    return GRADE_BLOCK_FILE.read_text(encoding="utf-8").rstrip("\n")


def padding_errors(stripped, words):
    errors = []
    if words:
        ratio = len({w.lower() for w in words}) / len(words)
        if ratio < 0.25:
            errors.append(
                f"Padding detected: unique-word ratio {ratio:.2f} is below 0.25 "
                f"({len(set(w.lower() for w in words))} unique of {len(words)} words).")
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
    return errors


def inspect(text, model=IMAGE_MODEL_DEFAULT, sauce_only=False):
    text = unicodedata.normalize("NFC", text)
    stripped = text.strip()
    chars = len(stripped)
    words = re.findall(r"\S+", stripped)
    errors = []
    warnings = []

    verdict = KPE.check(model, stripped)
    if not verdict["ok"]:
        errors.append(verdict["message"] + ".")
    warnings.extend(verdict["warnings"])

    for pattern in PLACEHOLDER_PATTERNS:
        match = pattern.search(stripped)
        if match:
            errors.append(f"Unresolved placeholder detected: {match.group(0)!r}.")

    missing_elements = [name for name, pattern in CANONICAL_ELEMENTS
                        if not re.search(pattern, stripped, re.I)]
    if missing_elements:
        errors.append(
            "Missing canonical element heading(s) from the ten-element prompt anatomy: "
            + ", ".join(missing_elements) + ".")

    negative_pattern = r"\s+".join(re.escape(w) for w in NEGATIVE_BLOCK_REQUIRED.split())
    if not re.search(negative_pattern, stripped, re.I):
        errors.append(
            "Missing negative block: the prompt must contain "
            f"{NEGATIVE_BLOCK_REQUIRED!r} (archived negative block wording).")

    errors.extend(padding_errors(stripped, words))

    if sauce_only:
        grade_block = load_grade_block()
        if grade_block is None:
            errors.append(
                "FAIL: Signature Grade Block file is missing "
                f"({GRADE_BLOCK_FILE}); cannot verify --sauce-only.")
        elif grade_block not in stripped:
            errors.append(
                "Missing Signature Grade Block: with --sauce-only the prompt must contain the exact "
                "contents of assets/brand/signature-grade-block.txt verbatim.")

    return {"characters": chars, "words": len(words), "errors": errors, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(
        description="Validate BlackCEO production prompt anatomy, length, placeholders, padding, and grade block.")
    parser.add_argument("prompt_file", type=Path)
    parser.add_argument("--model", default=IMAGE_MODEL_DEFAULT,
                        help="KIE image model id whose maxLength sets the rule 12 band (default %(default)s).")
    parser.add_argument("--runtime-max", type=int, default=None,
                        help="DEPRECATED and ignored: the length band is KIE prompt rule 12 for --model.")
    parser.add_argument("--strict-runtime", action="store_true", help="Treat length warnings (below the 95 percent target) as failures.")
    parser.add_argument("--sauce-only", action="store_true",
                        help="Require the exact Signature Grade Block substring (SECRET_SAUCE_ONLY pages).")
    parser.add_argument("--json", action="store_true", help="Emit JSON result.")
    args = parser.parse_args()

    try:
        text = args.prompt_file.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"FAIL: could not read prompt: {exc}")
        return 2

    result = inspect(text, args.model, sauce_only=args.sauce_only)
    if args.strict_runtime and result["warnings"]:
        result["errors"].extend(result["warnings"])
        result["warnings"] = []

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "FAIL" if result["errors"] else "PASS"
        print(f"{status}: {result['characters']} characters, {result['words']} words.")
        for item in result["warnings"]:
            print(f"WARNING: {item}")
        for item in result["errors"]:
            print(f"ERROR: {item}")

    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

HOUSE_MIN = 5000
HOUSE_MAX = 20000
DEFAULT_RUNTIME_MAX = 19000
PLACEHOLDER_PATTERNS = [
    re.compile(r"\[\s*TODO\s*\]", re.I),
    re.compile(r"\{\{[^{}]+\}\}"),
    re.compile(r"<\s*(insert|replace|placeholder)[^>]*>", re.I),
    re.compile(r"\bPLACEHOLDER\b", re.I),
]


def inspect(text, runtime_max):
    stripped = text.strip()
    chars = len(stripped)
    words = len(re.findall(r"\S+", stripped))
    errors = []
    warnings = []

    if chars < HOUSE_MIN:
        errors.append(f"Prompt is {chars} characters; house minimum is {HOUSE_MIN}.")
    if chars > HOUSE_MAX:
        errors.append(f"Prompt is {chars} characters; house maximum is {HOUSE_MAX}.")
    if runtime_max and chars > runtime_max and chars <= HOUSE_MAX:
        warnings.append(
            f"Prompt is house-compliant but exceeds the configured runtime ceiling of {runtime_max}; re-author efficiently before dispatch."
        )

    for pattern in PLACEHOLDER_PATTERNS:
        match = pattern.search(stripped)
        if match:
            errors.append(f"Unresolved placeholder detected: {match.group(0)!r}.")

    return {"characters": chars, "words": words, "errors": errors, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description="Validate BlackCEO production prompt length and obvious unresolved placeholders.")
    parser.add_argument("prompt_file", type=Path)
    parser.add_argument("--runtime-max", type=int, default=DEFAULT_RUNTIME_MAX)
    parser.add_argument("--strict-runtime", action="store_true", help="Treat runtime-max warning as failure.")
    parser.add_argument("--json", action="store_true", help="Emit JSON result.")
    args = parser.parse_args()

    try:
        text = args.prompt_file.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"FAIL: could not read prompt: {exc}")
        return 2

    result = inspect(text, args.runtime_max)
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

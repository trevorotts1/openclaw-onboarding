#!/usr/bin/env python3
"""fix-installer-json-blocks.py — U103.

Makes every ```json config-merge block in the installer docs parseable, so the
agent can merge the documented config instead of failing or improvising.

Two repairs (both preserve the documented intent):
  1. BARE FRAGMENT: a block that starts with `"key":` (no outer braces) is a
     config fragment meant to be merged into a larger object. Wrap it in `{ }`
     so it is valid standalone JSON the agent can parse and merge.
  2. ELLIPSIS PLACEHOLDER: a `{...}` inside a block is a "detail omitted"
     placeholder that is not valid JSON. Replace it with {"_detail": "omitted"}
     so the block parses while still signalling the omission.

Idempotent: a block that already parses is left untouched.

USAGE
-----
  scripts/fix-installer-json-blocks.py            # apply the repairs
  scripts/fix-installer-json-blocks.py --check    # report which blocks would be
                                                  # repaired (no writes); exit 1 if
                                                  # any block is unparseable
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

INSTALLER_DOCS = (
    "12-openrouter-setup/INSTALL.md",
    "31-upgraded-memory-system/INSTALL.md",
    "23-ai-workforce-blueprint/INSTALL.md",
)

# A fenced ```json ... ``` block, capturing the inner content.
JSON_BLOCK_RE = re.compile(r"(```json\s*\n)(.*?)(```)", re.DOTALL)
# A `{...}` ellipsis placeholder (detail omitted).
ELLIPSIS_RE = re.compile(r"\{\s*\.\.\.\s*\}")


def _parses(content: str) -> bool:
    try:
        json.loads(content)
        return True
    except json.JSONDecodeError:
        return False


def repair_block(content: str) -> tuple[str, bool]:
    """Return (repaired_content, changed)."""
    original = content

    # Repair 2 first: replace `{...}` ellipsis placeholders with a parseable
    # marker, so the subsequent parse check sees valid JSON.
    content = ELLIPSIS_RE.sub('{"_detail": "omitted"}', content)

    # Does it parse now?
    if _parses(content):
        return content, content != original

    # Repair 1: a bare fragment. If the stripped content begins with a quoted key
    # (`"..." :`) and is not already an object/array, wrap it in braces.
    stripped = content.strip()
    if stripped and not (stripped.startswith("{") or stripped.startswith("[")):
        if re.match(r'^"[^"]*"\s*:', stripped):
            content = "{\n" + content.rstrip("\n") + "\n}\n"

    return content, content != original


def fix_file(path: pathlib.Path, check_only: bool) -> tuple[int, int]:
    """Return (repaired_count, still_invalid_count)."""
    text = path.read_text(encoding="utf-8")
    repaired = 0
    still_invalid = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal repaired, still_invalid
        open_fence, content, close_fence = m.group(1), m.group(2), m.group(3)
        new_content, changed = repair_block(content)
        if _parses(new_content):
            if changed:
                repaired += 1
            return open_fence + new_content + close_fence
        # Still invalid after repair — leave as-is and report.
        still_invalid += 1
        return m.group(0)

    new_text = JSON_BLOCK_RE.sub(repl, text)

    if not check_only and new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return repaired, still_invalid


def main() -> int:
    check_only = "--check" in sys.argv[1:]
    total_repaired = 0
    total_invalid = 0
    for rel in INSTALLER_DOCS:
        p = REPO_ROOT / rel
        if not p.is_file():
            print(f"  · skip (missing): {rel}")
            continue
        repaired, still_invalid = fix_file(p, check_only)
        total_repaired += repaired
        total_invalid += still_invalid
        verb = "would repair" if check_only else "repaired"
        print(f"  · {rel}: {verb} {repaired} block(s)"
              + (f", {still_invalid} still invalid" if still_invalid else ""))

    print(f"\n{'[check] ' if check_only else ''}repaired={total_repaired} "
          f"still_invalid={total_invalid}")
    if check_only and total_invalid:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# qc-23-key-bodies.sh — machine-enforce the 23-key GHL RAW BODY rule.
#
# Scans every GHL Custom Webhook RAW BODY example (object A) embedded in this
# skill's references/, templates/, and scripts/ and ASSERTS, for each:
#   1. It is valid JSON (after neutralizing GHL `{{merge}}` tokens and
#      `<TEMPLATE_PLACEHOLDER>` substitution markers).
#   2. It is FLAT — no nested objects, no nested arrays-of-objects.
#   3. It has EXACTLY 23 top-level keys (23 = the mandated minimum AND the
#      canonical shape; a sub-23 body is a stripped body, the exact failure
#      §14 of GHL-INBOUND-AND-PLAYBOOKS.md was written to kill).
#   4. Its `messageTemplate` value is PLACEHOLDER-FREE (no `{{…}}`), or GHL
#      throws "Error while parsing the object to JSON" and Skips the webhook.
#   5. No literal "\n" sequence inside the JSON (single-line JSON values only).
#
# WHAT COUNTS AS AN OBJECT-A BODY: a fenced ```json / ```text block whose JSON
# object contains the snake_case key "agent_id". The OpenClaw server
# `hooks.mappings` entry (object B) uses camelCase "agentId" + a NESTED
# "match": { "path": ... } + a TEMPLATED messageTemplate, and is intentionally
# NOT a 23-key flat body — those are skipped by the agent_id discriminator.
#
# DELIBERATE EXCLUSION: references/v6.0-source-playbook.md is the VERBATIM
# historical source extract ("Do not summarize"); §14 of GHL-INBOUND explicitly
# SUPERSEDES its older nested/stripped bodies. Linting it would flag history
# that is preserved on purpose, so it is excluded by name (logged, not silent).
#
# Exit codes: 0 = all bodies pass; 1 = one or more violations; 2 = no bodies
# found (treated as failure — the scan target moved and the linter went blind).
#
# Usage:
#   bash scripts/qc-23-key-bodies.sh           # human output
#   bash scripts/qc-23-key-bodies.sh --json    # machine output
#   bash scripts/qc-23-key-bodies.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
JSON_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

export SKILL_DIR JSON_MODE

python3 - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(os.environ["SKILL_DIR"])
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"

# Directories to scan (relative to the skill root).
SCAN_DIRS = ["references", "templates", "scripts"]

# Files excluded by name — verbatim historical archives superseded by §14.
EXCLUDE_NAMES = {"v6.0-source-playbook.md"}

EXPECTED_KEYS = [
    "id", "match", "action", "agent_id", "model", "wakeMode", "name",
    "session_key", "messageTemplate", "deliver", "timeoutSeconds", "channel",
    "to", "thinking", "contact_id", "first_name", "last_name", "email",
    "phone", "subject", "message_body", "location_id", "location_name",
]
EXPECTED_SET = set(EXPECTED_KEYS)

FENCE_RE = re.compile(r"```(?:json|text)?[ \t]*\n(.*?)```", re.DOTALL)
# GHL merge token like {{contact.id}} or template marker like <HOOK_NAME>.
MERGE_RE = re.compile(r"\{\{[^}]*\}\}")
PLACEHOLDER_RE = re.compile(r"<[A-Za-z0-9_./:-]+>")


def _extract_balanced_object(body, anchor):
    """Given a fence body and the index of the "agent_id" key, walk LEFT to the
    nearest unmatched '{' that opens the object containing the anchor, then walk
    RIGHT with brace-counting to its matching '}'. Returns the exact JSON object
    substring. This isolates the body even when the fence also contains prose
    (the SMS template wraps the JSON in a CONTEXT/TRIGGER/ACTIONS prompt)."""
    # Walk left: find the '{' that, counting braces, is still open at `anchor`.
    depth = 0
    start = None
    for i in range(anchor, -1, -1):
        c = body[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                start = i
                break
            depth -= 1
    if start is None:
        return None
    # Walk right from start, brace-counting (skip braces inside strings).
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(body)):
        c = body[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return body[start:j + 1]
    return None


def find_object_a_blocks(text):
    """Yield the JSON object text for fenced blocks that look like object-A GHL
    bodies (contain the snake_case key "agent_id"). Object-B server mappings use
    camelCase "agentId" and are skipped by the discriminator."""
    for m in FENCE_RE.finditer(text):
        body = m.group(1)
        idx = body.find('"agent_id"')
        if idx == -1:
            continue
        obj = _extract_balanced_object(body, idx)
        if obj:
            yield obj


def neutralize(raw):
    """Replace GHL {{merge}} tokens and <PLACEHOLDER> markers with quoted dummy
    strings so the example parses as strict JSON. We track whether the ORIGINAL
    messageTemplate value contained a {{…}} token BEFORE neutralizing."""
    s = MERGE_RE.sub("X", raw)
    s = PLACEHOLDER_RE.sub("X", s)
    return s


def lint_block(raw):
    """Return list of violation strings ([] == pass)."""
    violations = []

    # Rule 5: no literal backslash-n inside the JSON.
    if "\\n" in raw:
        violations.append("contains literal \\n inside JSON (single-line values only)")

    # Rule 4 (pre-parse): messageTemplate must be placeholder-free.
    mt = re.search(r'"messageTemplate"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if mt and "{{" in mt.group(1):
        violations.append('messageTemplate contains a {{…}} placeholder (must be placeholder-free)')

    neutral = neutralize(raw)
    try:
        obj = json.loads(neutral)
    except json.JSONDecodeError as e:
        violations.append(f"not valid JSON after neutralizing tokens: {e}")
        return violations

    if not isinstance(obj, dict):
        violations.append("top-level JSON is not an object")
        return violations

    # Rule 2: FLAT — no nested objects / arrays.
    for k, v in obj.items():
        if isinstance(v, (dict, list)):
            violations.append(f"key '{k}' has a nested {type(v).__name__} (body must be flat)")

    # Rule 3: exactly 23 keys, and they must be the canonical 23.
    keys = list(obj.keys())
    if len(keys) != 23:
        violations.append(f"has {len(keys)} keys, expected exactly 23")
    missing = EXPECTED_SET - set(keys)
    extra = set(keys) - EXPECTED_SET
    if missing:
        violations.append(f"missing key(s): {sorted(missing)}")
    if extra:
        violations.append(f"unexpected key(s): {sorted(extra)}")

    return violations


results = []
total_blocks = 0
total_files = 0
excluded = []

for sub in SCAN_DIRS:
    d = SKILL_DIR / sub
    if not d.is_dir():
        continue
    for f in sorted(d.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix not in (".md", ".sh", ".txt"):
            continue
        if f.name in EXCLUDE_NAMES:
            excluded.append(str(f.relative_to(SKILL_DIR)))
            continue
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        blocks = list(find_object_a_blocks(text))
        if not blocks:
            continue
        total_files += 1
        for i, raw in enumerate(blocks):
            total_blocks += 1
            v = lint_block(raw)
            results.append({
                "file": str(f.relative_to(SKILL_DIR)),
                "block": i,
                "violations": v,
            })

failures = [r for r in results if r["violations"]]

if JSON_MODE:
    print(json.dumps({
        "scanned_files": total_files,
        "scanned_bodies": total_blocks,
        "excluded_files": excluded,
        "failures": failures,
        "verdict": "PASS" if (not failures and total_blocks > 0) else
                   ("NO_BODIES" if total_blocks == 0 else "FAIL"),
    }, indent=2))
else:
    print("=== qc-23-key-bodies: GHL RAW BODY 23-key linter ===")
    print(f"skill_dir : {SKILL_DIR}")
    print(f"scanned   : {total_blocks} object-A bodies across {total_files} files")
    if excluded:
        print(f"excluded  : {', '.join(excluded)} (verbatim historical archive — superseded by §14)")
    print("")
    for r in results:
        tag = "PASS" if not r["violations"] else "FAIL"
        print(f"  [{tag}] {r['file']} (body #{r['block']})")
        for vio in r["violations"]:
            print(f"          - {vio}")
    print("")
    if total_blocks == 0:
        print("RESULT: NO BODIES FOUND — the scan target moved; the linter is blind. Treating as FAIL.")
    elif failures:
        print(f"RESULT: FAIL — {len(failures)} body/bodies violate the 23-key rule.")
    else:
        print(f"RESULT: PASS — all {total_blocks} GHL RAW BODY examples are 23-key, flat, placeholder-free.")

if total_blocks == 0:
    sys.exit(2)
sys.exit(1 if failures else 0)
PYEOF

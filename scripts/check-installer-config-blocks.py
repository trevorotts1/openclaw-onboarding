#!/usr/bin/env python3
"""check-installer-config-blocks.py — T2-22 / A46.

WHY THIS EXISTS
---------------
`12-openrouter-setup/INSTALL.md` told the agent to merge a JSON block into the
LIVE configuration file. Extracting that block and parsing it produced
"Illegal trailing comma before end of object"; it also contained an empty
`"models": {` body followed by six bare closing braces. The instruction is
executed by an agent against a real configuration, so a merge attempt either
fails outright or — worse — is repaired by the agent improvising, producing a
configuration nobody wrote and nobody reviewed.

The same document's `NEW_MODELS='{ … }'` shell block, which is fed straight to
`jq --argjson`, carried the same trailing-comma defect.

WHAT IT CHECKS
--------------
Every ```json fenced block in every installer document, and every
`NEW_MODELS='{...}'` style single-quoted JSON assignment, must parse.

Blocks are SKIPPED only when they are explicitly not a document: a fragment
marked with a `// …` or `# …` ellipsis comment, or a block whose fence is
tagged `jsonc`/`json5`. Every skip is COUNTED AND PRINTED, so a check that
silently stopped inspecting anything is visible in its own output rather than
looking like a clean pass.

EXIT
----
0 → every block that could be parsed, parsed.
1 → at least one block does not parse.
2 → the check could not run (no installer documents found).

USAGE
-----
  scripts/check-installer-config-blocks.py             # blocking check
  scripts/check-installer-config-blocks.py --report    # list every block, never fail
  scripts/check-installer-config-blocks.py --self-test # prove both directions
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

FENCE_RE = re.compile(r"^```(json[5c]?|jsonc)\s*$", re.IGNORECASE)
CLOSE_RE = re.compile(r"^```\s*$")
SHELL_JSON_RE = re.compile(r"^([A-Z_][A-Z0-9_]*)='(\{.*?\})'", re.DOTALL | re.MULTILINE)
ELLIPSIS_RE = re.compile(r"^\s*(//|#)\s*\.\.\.|\.\.\.\s*$|^\s*\.\.\.\s*,?\s*$", re.MULTILINE)

Block = tuple[str, int, str, str]  # (relpath, line, kind, text)


def installer_docs(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in root.glob("*/INSTALL.md") if p.is_file())


def extract_blocks(path: pathlib.Path, root: pathlib.Path) -> list[Block]:
    rel = str(path.relative_to(root))
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks: list[Block] = []

    i = 0
    while i < len(lines):
        m = FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        tag = m.group(1).lower()
        start = i + 1
        j = start
        while j < len(lines) and not CLOSE_RE.match(lines[j]):
            j += 1
        body = "\n".join(lines[start:j])
        kind = "fenced-json" if tag == "json" else f"fenced-{tag}"
        blocks.append((rel, start + 1, kind, body))
        i = j + 1

    for m in SHELL_JSON_RE.finditer(text):
        line = text[: m.start()].count("\n") + 1
        blocks.append((rel, line, f"shell-assignment ${m.group(1)}", m.group(2)))

    return blocks


def classify(block: Block) -> tuple[str, str]:
    """Return (verdict, detail). verdict is one of: ok, skip, fail.

    An installer block is legitimately either a WHOLE JSON document (merge this
    into the config) or a FRAGMENT (add these keys to that section) — the
    memory-system and OpenRouter installers use both shapes on purpose. A
    fragment is checked by wrapping it in braces and parsing that, so a real
    syntax defect is still caught while a valid fragment is not miscalled.
    A block that parses as NEITHER is the defect this check exists for.
    """
    _rel, _line, kind, body = block
    if not body.strip():
        return "skip", "empty block"
    if kind.startswith("fenced-json5") or kind.startswith("fenced-jsonc"):
        return "skip", f"fence tagged {kind.split('-', 1)[1]} — not strict JSON by declaration"
    if ELLIPSIS_RE.search(body) or "{...}" in body or "{ ... }" in body:
        return "skip", "illustrative example containing an ellipsis placeholder"

    try:
        json.loads(body)
        return "ok", ""
    except json.JSONDecodeError as exc:
        document_error = str(exc)

    stripped = body.strip().rstrip(",")
    try:
        json.loads("{" + stripped + "}")
        return "ok", ""
    except json.JSONDecodeError:
        return "fail", f"parses neither as a document ({document_error}) nor as a fragment"


def run(root: pathlib.Path) -> tuple[int, list[str], dict[str, int]]:
    docs = installer_docs(root)
    if not docs:
        return 2, ["CANNOT RUN: no */INSTALL.md documents found"], {}

    tally = {"ok": 0, "skip": 0, "fail": 0, "documents": len(docs)}
    lines: list[str] = []
    failures: list[str] = []
    for doc in docs:
        for block in extract_blocks(doc, root):
            rel, line, kind, _ = block
            verdict, detail = classify(block)
            tally[verdict] += 1
            if verdict == "fail":
                failures.append(f"{rel}:{line} [{kind}] PARSE ERROR: {detail}")
            elif verdict == "skip":
                lines.append(f"{rel}:{line} [{kind}] skipped — {detail}")
    return (1 if failures else 0), failures + lines, tally


def self_test() -> int:
    """Prove the check fails on a real defect and passes on a valid document."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        good = root / "99-good-skill"
        good.mkdir()
        (good / "INSTALL.md").write_text(
            '# good\n\n```json\n{\n  "a": 1,\n  "b": {"c": 2}\n}\n```\n'
            "\nNEW_MODELS='{\n  \"x\": {\"y\": 1}\n}'\n",
            encoding="utf-8",
        )
        code, problems, tally = run(root)
        if code != 0:
            failures.append(f"clean document should PASS, got exit {code}: {problems}")
        elif tally["ok"] != 2:
            failures.append(f"expected 2 parsed blocks, counted {tally['ok']}")
        else:
            print("  ok direction 1 — a valid fenced block and a valid shell assignment both parse")

        # Mutation A: the exact defect found in the openrouter installer.
        bad = root / "98-trailing-comma"
        bad.mkdir()
        (bad / "INSTALL.md").write_text(
            '# bad\n\n```json\n{\n  "a": 1,\n}\n```\n', encoding="utf-8"
        )
        code, problems, _ = run(root)
        if code != 1 or not any("98-trailing-comma" in p for p in problems):
            failures.append(f"trailing comma should FAIL, got exit {code}: {problems}")
        else:
            print(f"  ok direction 2 — trailing comma fails: {problems[0]}")

        # Mutation B: the bare-closing-brace run.
        (bad / "INSTALL.md").write_text(
            '# bad\n\n```json\n{\n  "models": {\n    },\n    },\n}\n```\n', encoding="utf-8"
        )
        code, problems, _ = run(root)
        if code != 1:
            failures.append(f"bare closing braces should FAIL, got exit {code}")
        else:
            print(f"  ok direction 3 — bare closing braces fail: {problems[0]}")

        # Mutation C: a broken shell-assignment block fed to jq --argjson.
        (bad / "INSTALL.md").write_text(
            "# bad\n\nNEW_MODELS='{\n  \"x\": {\"y\": 1},\n}'\n", encoding="utf-8"
        )
        code, problems, _ = run(root)
        if code != 1 or not any("shell-assignment" in p for p in problems):
            failures.append(f"broken shell assignment should FAIL, got exit {code}: {problems}")
        else:
            print(f"  ok direction 4 — broken shell assignment fails: {problems[0]}")

        # Direction 5: an empty tree must report CANNOT RUN, never a pass.
        empty = pathlib.Path(tempfile.mkdtemp())
        code, problems, _ = run(empty)
        if code != 2:
            failures.append(f"empty tree should report CANNOT RUN (2), got {code}")
        else:
            print("  ok direction 5 — no installers reports CANNOT RUN (exit 2)")

    if failures:
        print("\nSELF-TEST FAILED")
        for f in failures:
            print(f"  x {f}")
        return 1
    print("\nSELF-TEST PASSED (5 directions)")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if "--self-test" in argv:
        return self_test()

    code, problems, tally = run(REPO_ROOT)
    print("installer configuration-block parse check (T2-22 / A46)")
    if tally:
        print(
            f"  · {tally['documents']} installer documents · "
            f"{tally['ok']} blocks parsed · {tally['skip']} skipped · {tally['fail']} failed"
        )
    for problem in problems:
        marker = "x" if "PARSE ERROR" in problem or problem.startswith("CANNOT RUN") else "-"
        print(f"  {marker} {problem}")

    if "--report" in argv:
        print("\n(--report: findings listed, exit forced to 0)")
        return 0
    if code == 0:
        print("OK every configuration block an installer tells an agent to merge parses")
    elif code == 2:
        print("FAIL CHECK COULD NOT RUN — reported as a failure, never as a pass")
    else:
        print("FAIL a configuration block an installer tells an agent to merge does not parse")
    return code


if __name__ == "__main__":
    sys.exit(main())

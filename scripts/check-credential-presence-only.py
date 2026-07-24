#!/usr/bin/env python3
"""check-credential-presence-only.py — U074 / SYS-2.

WHY THIS EXISTS
---------------
Seven skills' install/QC documentation printed credential VALUES (or prefixes)
in their verification commands — `echo $KIE_API_KEY | head -c 10`,
`grep GOOGLE_API_KEY secrets/.env` (prints the matching line), `printenv
NOTION_API_TOKEN | head -c 8`, `echo "GOOGLE_API_KEY length: ${#...}"`, etc.
Terminal transcripts, agent logs, and shell history retain those characters, so
a "verify your key" step leaked the very secret it was checking.

WHAT IT ENFORCES
----------------
No verification command in the seven affected skills may EMIT a credential
value or prefix. The only sanctioned check is PRESENCE-ONLY — report SET /
NOT-SET (or `[ -n "$VAR" ]`) and emit no character of the key. This guard scans
the seven skills' .md and .sh files for the known value-emitting shapes and
fails if any reappear.

FAIL-VISIBLY CONTRACT
---------------------
Exit 0  → scan RAN and found NO value-emitting credential pattern.
Exit 1  → scan ran and FOUND one or more value-emitting patterns (listed).
Exit 2  → scan COULD NOT RUN (a skill directory is missing). Never a pass.

USAGE
-----
  scripts/check-credential-presence-only.py             # scan the seven skills
  scripts/check-credential-presence-only.py --self-test  # prove both directions
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# The seven skills the finding covers.
SKILLS = (
    "05-ghl-setup",
    "07-kie-setup",
    "16-summarize-youtube",
    "22-book-to-persona-coaching-leadership-system",
    "31-upgraded-memory-system",
    "37-zhc-closeout",
    "45-design-intelligence-library",
)

# Value-emitting shapes. Each is a (compiled regex, human description). A match
# means a verification command would print credential characters. The presence-
# only pattern (`[ -n "$VAR" ] && echo "...SET"`) does NOT match any of these.
_CRED = r"[A-Z][A-Z0-9_]*(?:API_KEY|API_TOKEN|TOKEN|SECRET|PIT|KEY)"
VALUE_EMITTING_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"echo\s+\${_CRED}"), "echo $CREDENTIAL (prints the value)"),
    (re.compile(rf'echo\s+"\$\(?echo\s+\${_CRED}'), "echo \"$(echo $CREDENTIAL ...)\" (prints a prefix)"),
    (re.compile(rf"\${_CRED}\s*\|\s*head\s+-c"), "$CREDENTIAL | head -c N (prints a prefix)"),
    (re.compile(rf"printenv\s+{_CRED}\s*\|\s*head\s+-c"), "printenv CREDENTIAL | head -c N (prints a prefix)"),
    (re.compile(rf"\${_CRED}\s*\|\s*cut\s+-c"), "$CREDENTIAL | cut -c (prints a prefix)"),
    (re.compile(rf"echo\s+\${{#{_CRED}}}"), "echo ${#CREDENTIAL} (prints the length)"),
    (re.compile(rf"grep\s+{_CRED}\s+[^\n|]*secrets/\.env"), "grep CREDENTIAL secrets/.env (prints the matching line)"),
    (re.compile(rf"grep\s+\"?{_CRED}\"?\s+[^\n|]*\.env"), "grep CREDENTIAL .env (prints the matching line)"),
)


def scan_file(path: pathlib.Path) -> list[str]:
    """Return the list of value-emitting problems in one file."""
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{path}: CANNOT READ ({exc})"]
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # Skip pure comment lines.
        if stripped.startswith("#"):
            continue
        for pattern, desc in VALUE_EMITTING_PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            # The grep-the-secrets-file shape is only a DEFECT when it PRINTS the
            # matching line to the terminal. When the grep is the source of a
            # command substitution (`VAR="$(grep KEY secrets/.env | cut -d= -f2)"`
            # or `Bearer $(grep KEY ...)`), the value is captured to be USED (e.g.
            # in an Authorization header), not printed — that is not the leak this
            # guard targets. Skip those.
            if "grep" in desc and "$(" in line:
                continue
            problems.append(f"{path}:{lineno}: {desc} -> {stripped[:90]}")
    return problems


def run_scan(root: pathlib.Path) -> tuple[int, list[str], list[str]]:
    """Scan the seven skills. Returns (exit_code, problems, notes)."""
    problems: list[str] = []
    blockers: list[str] = []
    notes: list[str] = []

    scanned = 0
    for skill in SKILLS:
        skill_dir = root / skill
        if not skill_dir.is_dir():
            blockers.append(f"CANNOT RUN: skill directory missing: {skill}")
            continue
        scanned += 1
        for path in sorted(skill_dir.rglob("*")):
            if path.suffix not in (".md", ".sh"):
                continue
            problems.extend(scan_file(path))
    notes.append(f"skills scanned: {scanned}/{len(SKILLS)}")

    if blockers:
        return 2, blockers + problems, notes
    if problems:
        return 1, problems, notes
    return 0, [], notes


def self_test() -> int:
    """Prove the guard fails on a reintroduced value-emitting pattern and passes
    on the clean tree (mutation proof)."""
    script = pathlib.Path(__file__).resolve()
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        clean = pathlib.Path(tmp)
        # Copy just the seven skills (small, hermetic).
        for skill in SKILLS:
            src = REPO_ROOT / skill
            if src.is_dir():
                shutil.copytree(src, clean / skill)

        code, problems, _ = run_scan(clean)
        if code != 0:
            failures.append(
                f"DIRECTION 1 (clean tree must PASS) got exit {code}: {problems[:3]}"
            )
        else:
            print("  ✓ direction 1 — clean tree passes (exit 0)")

        # Mutation: reintroduce a value-emitting pattern into one doc.
        victim = clean / "07-kie-setup" / "kie-setup-full.md"
        if victim.is_file():
            victim.write_text(
                victim.read_text(encoding="utf-8")
                + "\nTEST: echo $KIE_API_KEY | head -c 10\n",
                encoding="utf-8",
            )
        code, problems, _ = run_scan(clean)
        if code != 1 or not any("head -c" in p for p in problems):
            failures.append(
                f"DIRECTION 2 (reintroduced value-emitting pattern must FAIL) got "
                f"exit {code}, problems={problems[:3]}"
            )
        else:
            print(f"  ✓ direction 2 — reintroduced value-emitting pattern fails (exit 1): {problems[0]}")

    # The script must also pass end-to-end against the real repo.
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    if proc.returncode != 0:
        failures.append(
            f"DIRECTION 3 (real repo must PASS) exit {proc.returncode}:\n{proc.stdout}{proc.stderr}"
        )
    else:
        print("  ✓ direction 3 — the real repository passes (exit 0)")

    if failures:
        print("\nSELF-TEST FAILED")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("\nSELF-TEST PASSED (3 directions)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()

    code, problems, notes = run_scan(REPO_ROOT)
    print("credential presence-only guard (U074 / SYS-2)")
    for note in notes:
        print(f"  · {note}")
    if code == 0:
        print("✅ no verification command in the seven skills emits a credential value")
        print("   (all credential checks are presence-only: SET / NOT-SET)")
        return 0
    header = (
        "❌ GUARD COULD NOT RUN — reporting as a failure, never as a pass"
        if code == 2
        else "❌ value-emitting credential check present"
    )
    print(header)
    for problem in problems:
        print(f"  ✗ {problem}")
    return code


if __name__ == "__main__":
    sys.exit(main())

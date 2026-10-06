"""FIX 77 — role-number uniqueness and roster lockstep.

Spec (QC.md FIX 77): "register-library-additions.py --check exit 0; a roster
uniqueness test passes; no two files claim the same ROLE number."
Source: MASTER-ASSESSMENT-AND-FIX-PLAN.md FIX 77 (R6 §J4).

Before this test the roster in 00-START-HERE.md claimed ROLE-20 twice (the
Presenter's Speech Writer AND the Audio Demonstration Specialist) and the
Fish Audio template claimed ROLE-21 alongside the Audio Demonstration
Specialist it had been split from. Four roles (signature QC, signature
architect, representation casting, image grounding) claimed no number at all.

Five legs, all failing LOUDLY on drift:

  1. UNIQUENESS — no two role files in the department claim the same
     ROLE number in their `**Role number:**` header. (The literal FIX 77
     demand: no two files CLAIM the same number; the fourteen pre-v12.17
     legacy roles — ROLE-01..17 minus the ones already stamped — claim
     nothing, so they cannot collide.)
  2. ROSTER LOCKSTEP — every roster row whose file carries a number
     matches the number the file itself claims (the roster is copied
     FROM the headers, never the other way around).
  3. ROSTER COMPLETENESS — every file that claims a ROLE number appears
     in the roster exactly once.
  4. NO DUPLICATE ROSTER ROWS — the roster table itself repeats neither
     a file nor a number (the ROLE-20/ROLE-20 disease).
  5. ROSTER EXISTENCE — every roster row names a file that exists on disk.

Infra docs (00-START-HERE, BUILDER-PROMPT, SOUL/TOOLS/IDENTITY, how-to,
DEPARTMENT-COUNTS, retired-doctrine-patterns.json) are not roles and carry
no Role number; they are skipped by the same stem set
register-library-additions.py uses.
"""
from __future__ import annotations

import re
from pathlib import Path

DEPT = Path(__file__).resolve().parent.parent.parent  # .../role-library/presentations

ROLE_NUMBER_RE = re.compile(r"^\*\*Role number:\*\*\s*(\S+)\s*$", re.MULTILINE)
ROSTER_ROW_RE = re.compile(
    r"^\|\s*(ROLE-\S+)\s*\|\s*([a-z0-9-]+)\s*\|\s*[^|]+\|\s*([A-Za-z0-9._-]+\.md)\s*\|",
    re.MULTILINE,
)

# Same identity set register-library-additions.py uses: files under <dept>/ that
# are department infra, never roles (no Role number header, no roster row).
INFRA_STEMS = {
    "00-START-HERE",
    "BUILDER-PROMPT",
    "DEPARTMENT-COUNTS-CANONICAL",
    "IDENTITY",
    "SOUL",
    "TOOLS",
    "how-to-use-this-department",
}


def _role_files() -> list[Path]:
    return sorted(
        p
        for p in DEPT.glob("*.md")
        if p.stem not in INFRA_STEMS
    )


def _header_number(path: Path) -> str | None:
    m = ROLE_NUMBER_RE.search(path.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def _roster_rows() -> list[tuple[str, str, str]]:
    start = DEPT / "00-START-HERE.md"
    return ROSTER_ROW_RE.findall(start.read_text(encoding="utf-8"))


def test_fix77_no_two_files_claim_the_same_role_number():
    claims: dict[str, list[str]] = {}
    for p in _role_files():
        n = _header_number(p)
        if n:
            claims.setdefault(n, []).append(p.name)
    dupes = {n: files for n, files in claims.items() if len(files) > 1}
    assert not dupes, (
        "FIX 77 violated: two or more role files claim the same ROLE number: "
        + "; ".join(f"{n} -> {files}" for n, files in sorted(dupes.items()))
    )


def test_fix77_roster_rows_match_file_headers():
    bad: list[str] = []
    for number, slug, fname in _roster_rows():
        p = DEPT / fname
        header = _header_number(p) if p.is_file() else None
        # Legacy roles (ROLE-01..17 family) predate the header convention and
        # claim nothing; the roster is the sole authority for their number and
        # they are allowed to stay header-less. Any file that DOES claim a
        # number must agree with its roster row.
        if header is not None and header != number:
            bad.append(
                f"roster says {number} for {fname} but the file header says "
                f"{header}"
            )
    assert not bad, (
        "FIX 77 violated: roster/file header disagreement (roster must be "
        "copied FROM the file headers): " + "; ".join(bad)
    )


def test_fix77_every_numbered_file_appears_in_roster():
    roster_files = {fname for _, _, fname in _roster_rows()}
    missing = [
        p.name
        for p in _role_files()
        if _header_number(p) is not None and p.name not in roster_files
    ]
    assert not missing, (
        "FIX 77 violated: role files claiming a number but absent from the "
        f"00-START-HERE roster: {missing}"
    )


def test_fix77_no_duplicate_roster_rows():
    rows = _roster_rows()
    seen: dict[str, list[str]] = {}
    for number, _slug, fname in rows:
        seen.setdefault(fname, []).append(number)
    dupes = {f: nums for f, nums in seen.items() if len(nums) > 1}
    dup_nums: dict[str, list[str]] = {}
    for number, _slug, fname in rows:
        dup_nums.setdefault(number, []).append(fname)
    dupes_n = {n: fs for n, fs in dup_nums.items() if len(fs) > 1}
    assert not dupes and not dupes_n, (
        "FIX 77 violated: roster repeats a file row or a number: "
        f"file dupes={dupes} number dupes={dupes_n}"
    )


def test_fix77_roster_files_exist():
    gone = [
        fname
        for _, _, fname in _roster_rows()
        if not (DEPT / fname).is_file()
    ]
    assert not gone, f"FIX 77 violated: roster rows naming missing files: {gone}"

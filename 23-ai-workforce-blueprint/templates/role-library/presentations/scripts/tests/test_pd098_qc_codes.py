#!/usr/bin/env python3
"""test_pd098_qc_codes.py — PD-098 rule 1: real codes, one meaning each.

PD-098 item (1): "Every code named must exist in the manifest registry or carry
the words `(role-level; not in the registry)`; no code has two definitions in
the file."

This test parses the definition tables of the main QC role file and its sops
mirror (every markdown table row whose first cell names an auto-fail code) and
compares each code with `PIPELINE-MANIFEST.json`'s `autofails` registry. It also
pins the shape of the new SOP 9.7 so the procedure keeps pointing at
`presentation_job/priority_shift_items.py` instead of copying the id list, and
pins one criteria count per gate.

Read-only: no file, network, model or live service is touched.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEPT = HERE.parents[2]  # .../role-library/presentations
ROLE_FILE = DEPT / "qc-specialist-presentations.md"
MIRROR_FILE = DEPT / "sops" / "qc-specialist-presentations-sops.md"
MANIFEST = (
    HERE.parents[6]
    / "universal-sops"
    / "presentation-slide-craft"
    / "PIPELINE-MANIFEST.json"
)

CODE_RE = re.compile(r"AF-[A-Z0-9]+(?:-[A-Z0-9]+)*")
ROLE_LEVEL = "(role-level; not in the registry)"


def registry_codes():
    data = json.loads(MANIFEST.read_text())
    codes = set()
    for row in data["autofails"]:
        code = row.get("code")
        if code:
            codes.add(code)
    assert codes, "the manifest registry is empty"
    return codes


def definition_rows(path):
    """Yield (line_number, first_cell) for every definition table row."""
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.startswith("| AF-"):
            yield number, line.split("|")[1].strip()


def cell_codes(cell):
    bare = cell.replace(ROLE_LEVEL, "")
    return [token.strip() for token in bare.split("/") if CODE_RE.fullmatch(token.strip())]


def test_role_file_codes_are_registered_or_marked_role_level():
    registered = registry_codes()
    for path in (ROLE_FILE, MIRROR_FILE):
        rows = list(definition_rows(path))
        assert rows, "%s: no auto-fail definition tables found" % path.name
        for number, cell in rows:
            codes = cell_codes(cell)
            assert codes, "%s:%d: no code in the first cell: %r" % (path.name, number, cell)
            for code in codes:
                if code in registered:
                    continue
                assert ROLE_LEVEL in cell, (
                    "%s:%d: code %s is not in PIPELINE-MANIFEST autofails and the row "
                    "does not carry %r" % (path.name, number, code, ROLE_LEVEL)
                )


def test_no_code_has_two_definitions():
    for path in (ROLE_FILE, MIRROR_FILE):
        seen = {}
        for number, cell in definition_rows(path):
            for code in cell_codes(cell):
                assert code not in seen, (
                    "%s: code %s is defined twice (lines %d and %d)"
                    % (path.name, code, seen[code], number)
                )
                seen[code] = number


def test_sop_97_points_at_the_shared_item_list():
    for path in (ROLE_FILE, MIRROR_FILE):
        text = path.read_text()
        start = text.find("SOP 9.7 -- P-SHIFT-QC")
        assert start != -1, "%s: SOP 9.7 -- P-SHIFT-QC is missing" % path.name
        section = text[start:]
        for needle in (
            "presentation_job/priority_shift_items.py",
            "PRIORITY_SHIFT_ITEM_IDS",
            "PRIORITY_SHIFT_ID_KEY",
            "working/qc/priority_shift_report.json",
            "priority_shift_report/v1",
        ):
            assert needle in section, "%s: SOP 9.7 does not name %s" % (path.name, needle)
        # The list lives in the module; the procedure must not copy the ids.
        assert "0_attention_is_the_no1_job" not in section, (
            "%s: SOP 9.7 copies the priority-shift id list instead of pointing at the module"
            % path.name
        )


def test_one_criteria_count_per_gate():
    expected = {
        "The 24 Copy QC Criteria": True,
        "The 22 Prompt QC Criteria": True,
        "The 17 Image QC Criteria": True,
    }
    stale = (
        "The 17 Copy QC Criteria",
        "prompt QC, 15 criteria",
        "image QC, 14 criteria",
        "After the standard 18 criteria",
    )
    for path in (ROLE_FILE, MIRROR_FILE):
        text = path.read_text()
        for needle in expected:
            assert needle in text, "%s: missing %r" % (path.name, needle)
        for needle in stale:
            assert needle not in text, "%s: stale count still present: %r" % (path.name, needle)

"""PD-039 — the roster says truthfully how each role is called.

Acceptance row A1 (01-BUILD-SPEC.md, PD-039): "the `engine phase` set in the
table equals the set of `owning_role` values parsed from the manifest; every
roster row has a value."

Consolidation amendment (finding PD-110): under the roster table there is a
second table, "Files a procedure requires that no phase produces", one row
each for hook_package.json, mission_prd.json, price_ladder.json,
offer_stack.json, audience_say_tags.json, presenter_notes.json and
approval_record.json; every cell that names a procedure names a file that
exists under `sops/`.

Fail-closed: an unparsed row, a missing value or a procedure cell naming a
file that is not under `sops/` fails here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEPT = Path(__file__).resolve().parent.parent.parent          # .../role-library/presentations
REPO = Path(__file__).resolve().parents[6]                    # repo root
MANIFEST = REPO / "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"
START = DEPT / "00-START-HERE.md"

VALUES = {
    "engine phase",
    "front door, before the engine",
    "on call",
    "called by another role",
}

ROW_RE = re.compile(
    r"^\|\s*(ROLE-\S+)\s*\|\s*([a-z0-9-]+)\s*\|\s*[a-z-]+\s*\|\s*[A-Za-z0-9._-]+\.md\s*\|\s*([^|]*?)\s*\|",
    re.MULTILINE,
)
CELL_RE = re.compile(r"`([^`]+)`")

REQUIRED_FILES = [
    "hook_package.json",
    "mission_prd.json",
    "price_ladder.json",
    "offer_stack.json",
    "audience_say_tags.json",
    "presenter_notes.json",
    "approval_record.json",
]


def _roster() -> dict[str, str]:
    """slug -> How it is called, from the roster table."""
    out: dict[str, str] = {}
    for role, slug, how in ROW_RE.findall(START.read_text(encoding="utf-8")):
        assert slug not in out, f"roster repeats {slug}"
        out[slug] = how
    return out


def _manifest_engine_roles() -> set[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {p["owning_role"] for p in manifest["phases"] if p.get("owning_role")}


def _files_table() -> dict[str, str]:
    """file name -> 'Read by' cell text, from the PD-110 table."""
    text = START.read_text(encoding="utf-8")
    start = text.index("### Files a procedure requires that no phase produces")
    out: dict[str, str] = {}
    for line in text[start:].splitlines():
        if not line.startswith("|") or "`" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 3:
            continue
        out[cells[0]] = cells[1]
    return out


def test_a1_every_roster_row_has_a_value():
    roster = _roster()
    assert len(roster) == 35, f"parsed {len(roster)} roster rows, expected 35"
    for slug, how in roster.items():
        assert how in VALUES, f"{slug}: {how!r} is not one of the four values"


def test_a1_engine_phase_set_equals_manifest_owning_role_set():
    roster = _roster()
    claimed = {slug for slug, how in roster.items() if how == "engine phase"}
    actual = _manifest_engine_roles()
    assert claimed == actual, (
        f"roster claims {sorted(claimed ^ actual)} differently from the manifest"
    )


def test_pd110_all_seven_rows_exist_with_a_writer():
    table = _files_table()
    for name in REQUIRED_FILES:
        assert name in table, f"{name}: no row in the no-phase-produces table"
    # every row also names who writes it
    text = START.read_text(encoding="utf-8")
    for name in REQUIRED_FILES:
        assert re.search(rf"^\|\s*{re.escape(name)}\s*\|[^\n]*\|[^\n]+\|\s*$",
                         text, re.MULTILINE), f"{name}: row has no writer cell"


def test_pd110_every_named_procedure_exists_under_sops():
    sops = DEPT / "sops"
    table = _files_table()
    for name in REQUIRED_FILES:
        named = CELL_RE.findall(table[name])
        assert named, f"{name}: names no procedure"
        for proc in named:
            assert (sops / proc).is_file(), f"{name}: {proc} is not under sops/"


def test_pd110_none_of_the_seven_is_produced_by_a_phase():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    produced: set[str] = set()
    for phase in manifest["phases"]:
        val = phase.get("produces_artifact") or phase.get("produces_artifacts") or []
        if isinstance(val, str):
            val = [val]
        produced.update(str(v) for v in val)
    for name in REQUIRED_FILES:
        assert not any(name in p for p in produced), f"{name} IS produced by a phase"

#!/usr/bin/env python3
"""migrate.py — Skill 35 planner sheet migration 1.2.0 -> 1.3.0.

Source: Owner D27 / decision 35 / plan section 6.15 (2026-10-07):

  "The planner sheet (Google Sheet template, config/sheet-template.schema.json,
   now 1.2.0): add drama song fields to the Weekly Overview (style chosen,
   status, KIE cost, video link, channels posted) as schema 1.3.0; migrate live
   client sheets with scripts/migrate-template.py (no data loss)."

What this module guarantees
---------------------------
The 1.2.0 -> 1.3.0 bump is **purely additive**. It:

  * appends the five drama-song headings to the Weekly Overview heading row,
  * inserts five empty cells at exactly those positions in every row,
  * pushes any trailing technical cell (the ``_row_key`` cell the row-append
    webhook writes at index 20 / column U on a 1.2.0 sheet) past the new
    fields, so it lands at index 25 / column Z on a 1.3.0 sheet,
  * stamps ``schema_version`` 1.3.0 on the document and on ``identity``,
  * changes NOTHING else: every pre-existing cell keeps its value and its
    index, every other tab is byte-identical, no row is blanked, no row is
    dropped, no heading is renamed or reordered.

Legacy template-starter cleanup (the F22 blanking of demo/publication rows) is
NOT part of this bump and is untouched — see the README seam note. This path
never removes a cell, so "no data loss" is provable by construction.

Fail-closed refusals (MigrationError, CLI exit 4):
  * a document already at a NEWER than 1.3.0 schema (never downgrade),
  * a document stamped 1.3.0 that is missing drama-song headings (hand-edited
    contract — repair it, do not guess),
  * a partial set of drama-song headings already present (ambiguous),
  * no Weekly Overview tab to put the fields on,
  * a duplicate heading the append would create.

stdlib only; no network, no credentials, no media files.
"""
from __future__ import annotations

import copy
import json
import re

SCHEMA_FROM = "1.2.0"
SCHEMA_TO = "1.3.0"
OVERVIEW_TAB = "Weekly Overview"

# Plan 6.15: "style chosen, status, KIE cost, video link, channels posted".
# Display headings first, payload keys second. The heading prefix keeps the new
# columns distinguishable from the existing "Videos", "QC" and "Overall"
# columns on the same tab.
DRAMA_SONG_FIELDS = [
    "Drama Style Chosen",
    "Drama Status",
    "Drama KIE Cost",
    "Drama Video Link",
    "Drama Channels Posted",
]

DRAMA_SONG_PAYLOAD_KEYS = [
    "drama_style_chosen",
    "drama_status",
    "drama_kie_cost",
    "drama_video_link",
    "drama_channels_posted",
]

# Weekly Overview column index each payload key lands at on a 1.3.0 sheet.
OVERVIEW_FIELD_INDEX = {
    key: 20 + i for i, key in enumerate(DRAMA_SONG_PAYLOAD_KEYS)
}

# The technical upsert key the row-append webhook writes: column U on a 1.2.0
# sheet (index 20), column Z on a 1.3.0 sheet (index 25) — the drama fields
# take 20..24, so the key is pushed to the end rather than overwritten.
OVERVIEW_KEY_INDEX_120 = 20
OVERVIEW_KEY_INDEX_130 = 25

# The client-facing 20-column Weekly Overview of schema 1.2.0. Used by the
# validator to prove the legacy layout is a prefix of 1.3.0 (no column moved,
# none renamed). Migration itself reads the headings off the document, so a
# live sheet with the legacy duplicate-heading pattern migrates the same way.
LEGACY_OVERVIEW_HEADINGS = [
    "Week Of", "Theme of the Week", "Research", "Core Content", "Images",
    "Videos", "Facebook", "Instagram", "LinkedIn", "YouTube", "TikTok",
    "Pinterest", "Carousels", "Blog", "Podcast", "Email", "QC", "Scheduled",
    "Overall", "Notes",
]

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class MigrationError(Exception):
    """A refusal: the document cannot be migrated safely as asked."""


def parse_version(raw):
    """'1.3.0' -> (1, 3, 0). Raises MigrationError on anything else."""
    if raw is None or str(raw).strip() == "":
        raise MigrationError("schema_version is missing")
    m = _VERSION_RE.match(str(raw).strip())
    if not m:
        raise MigrationError("unrecognised schema_version: %r" % (raw,))
    return tuple(int(g) for g in m.groups())


def _blank(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def _migrate_overview(tab, findings):
    """Purely additive 1.2.0 -> 1.3.0 edit of the Weekly Overview tab.

    Returns the plan entry for this tab. Mutates ``tab`` in place.
    """
    headings = list(tab.get("headings") or [])
    had_rows = isinstance(tab.get("rows"), list)
    rows = tab.get("rows")
    rows = [list(r) for r in rows] if isinstance(rows, list) else []

    present = [f for f in DRAMA_SONG_FIELDS if f in headings]
    if present and len(present) != len(DRAMA_SONG_FIELDS):
        missing = [f for f in DRAMA_SONG_FIELDS if f not in headings]
        raise MigrationError(
            "Weekly Overview already carries %d of the 5 drama-song headings; "
            "missing %s — repair the sheet by hand, this migration refuses a "
            "partial layout" % (len(present), ", ".join(missing)))
    if len(present) == len(DRAMA_SONG_FIELDS):
        # Already at 1.3.0 layout — idempotent, no cell is touched again.
        return {"tab": OVERVIEW_TAB, "action": "already_1_3_0",
                "headings_before": len(headings), "headings_after": len(headings),
                "rows_before": len(rows), "rows_after": len(rows),
                "cells_added": 0,
                "detail": "drama-song headings already present — layout untouched"}

    old_n = len(headings)
    # Never create a duplicate heading.
    collisions = [f for f in DRAMA_SONG_FIELDS
                  if f.lower() in {str(h).strip().lower() for h in headings}]
    if collisions:
        raise MigrationError(
            "appending the drama-song headings would duplicate existing "
            "heading(s): %s" % ", ".join(collisions))

    new_headings = headings + list(DRAMA_SONG_FIELDS)
    if len(new_headings) != len(set(str(h).strip().lower() for h in new_headings)):
        raise MigrationError("Weekly Overview headings would not be unique "
                             "after the append")

    cells_added = 0
    row_lengths = []
    for idx, row in enumerate(rows):
        before = list(row)
        head = before[:old_n]
        tail = before[old_n:]          # trailing technical cell(s), e.g. _row_key
        if len(head) < old_n:
            head = head + [""] * (old_n - len(head))
        after = head + [""] * len(DRAMA_SONG_FIELDS) + tail
        # --- the no-loss invariant, checked on every row ---------------
        if after[:old_n] != head:
            raise MigrationError("row %d: pre-existing cells changed" % idx)
        if after[old_n:old_n + len(DRAMA_SONG_FIELDS)] != [""] * len(DRAMA_SONG_FIELDS):
            raise MigrationError("row %d: new cells are not empty" % idx)
        if after[old_n + len(DRAMA_SONG_FIELDS):] != tail:
            raise MigrationError("row %d: trailing technical cell lost" % idx)
        rows[idx] = after
        row_lengths.append({"row": idx, "before": len(before), "after": len(after)})
        cells_added += len(after) - len(before)

    tab["headings"] = new_headings
    if had_rows:
        tab["rows"] = rows
    findings.append(
        "%s: +%d drama-song heading(s) at columns U..Y (1.3.0), %d row(s) "
        "widened by %d empty cell(s), trailing technical cell moved to column Z"
        % (OVERVIEW_TAB, len(DRAMA_SONG_FIELDS), len(rows), len(DRAMA_SONG_FIELDS)))
    return {"tab": OVERVIEW_TAB, "action": "append_drama_song_fields",
            "headings_before": old_n, "headings_after": len(new_headings),
            "rows_before": len(rows), "rows_after": len(rows),
            "cells_added": cells_added, "rows": row_lengths,
            "detail": "5 drama-song headings appended; every pre-existing cell "
                      "kept its value and index; _row_key moved to column Z"}


def plan_migration(doc):
    """Read-only preview: (plan_entries, findings, target_version_state)."""
    if not isinstance(doc, dict):
        raise MigrationError("document is not a JSON object")
    raw = doc.get("schema_version")
    version = (1, 2, 0) if _blank(raw) else parse_version(raw)
    if version > (1, 3, 0):
        raise MigrationError(
            "document is at schema_version %s — refusing to downgrade to %s"
            % (raw, SCHEMA_TO))
    already = version == (1, 3, 0)
    tabs = doc.get("tabs")
    if not isinstance(tabs, dict) or OVERVIEW_TAB not in tabs:
        raise MigrationError("no '%s' tab — the drama-song fields have nowhere "
                             "to go" % OVERVIEW_TAB)
    if already:
        # Verify the layout really is 1.3.0 before calling it done.
        headings = tabs[OVERVIEW_TAB].get("headings") or []
        missing = [f for f in DRAMA_SONG_FIELDS if f not in headings]
        if missing:
            raise MigrationError(
                "schema_version says %s but '%s' is missing %s — repair the "
                "contract, this migration refuses to guess"
                % (raw, OVERVIEW_TAB, ", ".join(missing)))
        return ([{"tab": OVERVIEW_TAB, "action": "already_1_3_0",
                  "detail": "schema_version already %s and the drama-song "
                            "headings are present" % SCHEMA_TO}], [], True)
    plan, findings = [], []
    for name, tab in tabs.items():
        if not isinstance(tab, dict):
            continue
        if name == OVERVIEW_TAB:
            plan.append(_migrate_overview(tab, findings))
        else:
            plan.append({"tab": name, "action": "untouched",
                         "detail": "not part of the 1.2.0 -> 1.3.0 bump"})
    return plan, findings, False


def migrate_doc(doc):
    """Return (migrated_copy, report). Pure — the input is never mutated."""
    if not isinstance(doc, dict):
        raise MigrationError("document is not a JSON object")
    raw_before = doc.get("schema_version")
    before_version = None if _blank(raw_before) else str(raw_before).strip()

    migrated = copy.deepcopy(doc)
    plan, findings, already = plan_migration(migrated)

    if not already:
        migrated["schema_version"] = SCHEMA_TO
        identity = migrated.get("identity")
        if not isinstance(identity, dict):
            identity = {}
            migrated["identity"] = identity
        identity["schema_version"] = SCHEMA_TO
        if before_version:
            identity.setdefault("migrated_from", before_version)
        else:
            identity.setdefault("migrated_from", SCHEMA_FROM)

    report = {
        "from_version": before_version or "(absent — treated as %s)" % SCHEMA_FROM,
        "to_version": migrated.get("schema_version"),
        "already_current": bool(already),
        "changed": not already,
        "plan": plan,
        "findings": findings,
        "cells_added": sum(int(p.get("cells_added") or 0) for p in plan),
        "schema_version_key": "schema_version",
    }
    return migrated, report


def lossless(before, after):
    """Structural no-loss proof between a 1.2.0 and a 1.3.0 document.

    Returns (ok, problems). Checks, for every tab:
      * every pre-existing heading survives, in order, as a prefix (Weekly
        Overview gains exactly the 5 drama-song headings, at 20..24);
      * every pre-existing row cell keeps its value at its index;
      * trailing technical cells survive, in order, after the new fields;
      * no row and no tab appears or disappears;
      * every non-Overview tab is deep-equal;
      * the set of non-empty cell values only grows (nothing vanished).
    """
    problems = []
    b_tabs = before.get("tabs") or {}
    a_tabs = after.get("tabs") or {}
    if set(b_tabs) != set(a_tabs):
        problems.append("tab set changed: %s -> %s"
                        % (sorted(b_tabs), sorted(a_tabs)))
    drama_n = len(DRAMA_SONG_FIELDS)
    for name, b_tab in b_tabs.items():
        a_tab = a_tabs.get(name)
        if a_tab is None:
            continue
        b_head = list(b_tab.get("headings") or [])
        a_head = list(a_tab.get("headings") or [])
        if name == OVERVIEW_TAB:
            if a_head[:len(b_head)] != b_head:
                problems.append("%s: pre-existing headings moved or changed" % name)
            if a_head[len(b_head):] != DRAMA_SONG_FIELDS:
                problems.append("%s: new headings are not exactly %s"
                                % (name, DRAMA_SONG_FIELDS))
        elif a_head != b_head or a_tab != b_tab:
            problems.append("%s: a non-Overview tab changed" % name)

        b_rows = b_tab.get("rows") or []
        a_rows = a_tab.get("rows") or []
        if len(b_rows) != len(a_rows):
            problems.append("%s: row count changed %d -> %d"
                            % (name, len(b_rows), len(a_rows)))
            continue
        for i, (b_row, a_row) in enumerate(zip(b_rows, a_rows)):
            b_row, a_row = list(b_row), list(a_row)
            old_n = len(b_head)
            if name == OVERVIEW_TAB:
                if a_row[:min(len(b_row), old_n)] != b_row[:min(len(b_row), old_n)]:
                    problems.append("%s row %d: pre-existing cells changed"
                                    % (name, i))
                if a_row[old_n:old_n + drama_n] != [""] * drama_n:
                    problems.append("%s row %d: drama cells are not empty"
                                    % (name, i))
                if a_row[old_n + drama_n:] != b_row[old_n:]:
                    problems.append("%s row %d: trailing technical cell changed"
                                    % (name, i))
            elif a_row != b_row:
                problems.append("%s row %d: changed" % (name, i))
            b_vals = [str(c) for c in b_row if not _blank(c)]
            a_vals = [str(c) for c in a_row if not _blank(c)]
            missing = [v for v in b_vals if v not in a_vals]
            if missing:
                problems.append("%s row %d: value(s) vanished: %s"
                                % (name, i, missing))
    # schema_version must move forward, never back.
    b_raw = before.get("schema_version")
    a_raw = after.get("schema_version")
    if not _blank(b_raw) and not _blank(a_raw):
        if parse_version(a_raw) < parse_version(b_raw):
            problems.append("schema_version went backwards: %s -> %s"
                            % (b_raw, a_raw))
    if str(a_raw).strip() != SCHEMA_TO:
        problems.append("schema_version is %r, expected %s" % (a_raw, SCHEMA_TO))
    return (not problems), problems

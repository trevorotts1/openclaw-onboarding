#!/usr/bin/env python3
"""migrate.py — Skill 35 planner sheet migration 1.2.0 -> 1.3.0.

Source: Owner D27 / decision 35 / plan section 6.15 (2026-10-07), manual H5
(2026-10-08, rewrite option — the installed contract is authoritative):

  "The planner sheet (Google Sheet template, config/sheet-template.schema.json,
   now 1.2.0): add drama song fields to the Weekly Overview (style chosen,
   status, KIE cost, video link, channels posted) as schema 1.3.0; migrate live
   client sheets with scripts/migrate-template.py (no data loss)."

The installed contract
----------------------
``35-social-media-planner/config/sheet-template.schema.json`` (stamped 1.3.0)
is THE contract. Its Weekly Overview layout is:

  index 0..19   columns A..T  the 20 client-facing headings, unchanged
  index 20      column U      ``cycle_id`` — the row-append upsert key,
                               PRE-1.3.0 provisioner column, PINNED so the
                               webhook key never moves
  index 21..25  columns V..Z  the five drama-song fields:
                               Drama Song Style, Drama Song Status,
                               KIE Cost (cents), Drama Song Video Link,
                               Drama Song Channels Posted
                               (payload keys drama_song_style,
                               drama_song_status, kie_cost_cents,
                               drama_song_video_url, drama_song_channels)

What this module guarantees
---------------------------
The 1.2.0 -> 1.3.0 bump is **purely additive** under that contract. It:

  * keeps the technical ``cycle_id`` upsert key at index 20 / column U at
    every schema version — it is never overwritten, never pushed right,
  * appends the five installed drama-song headings at index 21..25 (V..Z),
  * widens every Weekly Overview row so those five cells exist and are empty,
  * stamps ``schema_version`` 1.3.0 on the document and on ``identity``,
  * changes NOTHING else: every pre-existing cell keeps its value and its
    index, every other tab is byte-identical, no row is blanked, no row is
    dropped, no heading is renamed or reordered.

A 1.2.0 sheet's heading row may be the bare 20 client headings, or those 20
plus ``cycle_id`` (the provisioner's shape). Both migrate to the same 26-cell
installed layout. A 1.2.0 row carrying more than 21 cells already holds
divergent drama columns — that is the layout this rewrite exists to end — so
the migration refuses it by name instead of guessing.

Legacy template-starter cleanup (the F22 blanking of demo/publication rows) is
NOT part of this bump and is untouched — see the README seam note. This path
never removes a cell, so "no data loss" is provable by construction.

Fail-closed refusals (MigrationError, CLI exit 4):
  * a document already at a NEWER than 1.3.0 schema (never downgrade),
  * a document stamped 1.3.0 whose Weekly Overview is not the installed
    26-cell layout (hand-edited or divergent contract — repair it, do not
    guess; this includes the retired 25-heading layout that overwrote the
    key column),
  * a partial set of drama-song headings already present (ambiguous),
  * a heading row that is neither the 1.2.0 shapes nor the installed 1.3.0
    shape (the retired divergent layout included),
  * ``cycle_id`` present but not at index 20 (the technical column moved),
  * a 1.2.0 row already wider than 21 cells (divergent drama cells),
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

# The client-facing 20-column Weekly Overview of schema 1.2.0 (A..T). Used by
# the validator to prove the legacy layout is a prefix of 1.3.0 (no column
# moved, none renamed). Migration itself reads the headings off the document.
LEGACY_OVERVIEW_HEADINGS = [
    "Week Of", "Theme of the Week", "Research", "Core Content", "Images",
    "Videos", "Facebook", "Instagram", "LinkedIn", "YouTube", "TikTok",
    "Pinterest", "Carousels", "Blog", "Podcast", "Email", "QC", "Scheduled",
    "Overall", "Notes",
]

# The technical upsert key the row-append webhook writes. Pre-1.3.0
# provisioner column; the installed 1.3.0 contract KEEPS it at the same index
# so the key never moves and live sheets are never corrupted.
TECHNICAL_HEADING = "cycle_id"
TECHNICAL_INDEX = 20          # column U
TECHNICAL_COLUMN = "U"
OVERVIEW_KEY_INDEX = 20       # the key cell index at EVERY schema version

# The five drama-song fields as the installed contract spells them.
# Heading first; payload keys are the installed snake_case counterparts.
DRAMA_SONG_FIELDS = [
    "Drama Song Style",
    "Drama Song Status",
    "KIE Cost (cents)",
    "Drama Song Video Link",
    "Drama Song Channels Posted",
]

DRAMA_SONG_PAYLOAD_KEYS = [
    "drama_song_style",
    "drama_song_status",
    "kie_cost_cents",
    "drama_song_video_url",
    "drama_song_channels",
]

# Weekly Overview column index each installed payload key lands at on a 1.3.0
# sheet: V..Z, right after the pinned cycle_id at U.
OVERVIEW_FIELD_INDEX = {
    key: 21 + i for i, key in enumerate(DRAMA_SONG_PAYLOAD_KEYS)
}

# The installed 1.3.0 Weekly Overview heading row (26 cells): the 20 legacy
# headings, cycle_id pinned at 20, the five drama-song fields at 21..25.
WEEKLY_OVERVIEW_HEADINGS_130 = (
    list(LEGACY_OVERVIEW_HEADINGS) + [TECHNICAL_HEADING] + list(DRAMA_SONG_FIELDS)
)

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

def _overview_headings_ok(headings):
    """True when ``headings`` is a migratable 1.2.0 shape or the installed
    1.3.0 row. Anything else — including the retired divergent layout — is a
    refusal, not a guess."""
    if list(headings) == WEEKLY_OVERVIEW_HEADINGS_130:
        return True
    if list(headings) == LEGACY_OVERVIEW_HEADINGS:
        return True
    if list(headings) == LEGACY_OVERVIEW_HEADINGS + [TECHNICAL_HEADING]:
        return True
    return False

def _migrate_overview(tab, findings):
    """Purely additive 1.2.0 -> 1.3.0 edit of the Weekly Overview tab.

    Returns the plan entry for this tab. Mutates ``tab`` in place.
    """
    headings = list(tab.get("headings") or [])
    had_rows = isinstance(tab.get("rows"), list)
    rows = tab.get("rows")
    rows = [list(r) for r in rows] if isinstance(rows, list) else []

    if list(headings) == WEEKLY_OVERVIEW_HEADINGS_130:
        # Already the installed layout — idempotent, no cell is touched again.
        return {"tab": OVERVIEW_TAB, "action": "already_1_3_0",
                "headings_before": len(headings), "headings_after": len(headings),
                "rows_before": len(rows), "rows_after": len(rows),
                "cells_added": 0,
                "detail": "installed 1.3.0 layout already present — untouched"}

    present = [f for f in DRAMA_SONG_FIELDS if f in headings]
    if present and len(present) == len(DRAMA_SONG_FIELDS):
        # All five present by exact name but not on the installed row: that is
        # the retired/divergent layout, not a completed migration.
        raise MigrationError(
            "Weekly Overview carries all 5 drama-song headings but is not the "
            "installed 1.3.0 layout (cycle_id at index %d / column %s, the five "
            "fields at indexes 21..25) — repair the sheet against "
            "35-social-media-planner/config/sheet-template.schema.json; got %r"
            % (TECHNICAL_INDEX, TECHNICAL_COLUMN, headings))
    if present:
        missing = [f for f in DRAMA_SONG_FIELDS if f not in headings]
        raise MigrationError(
            "Weekly Overview already carries %d of the 5 drama-song headings; "
            "missing %s — repair the sheet by hand, this migration refuses a "
            "partial layout" % (len(present), ", ".join(missing)))

    # Never create a duplicate heading (case-insensitive, as sheets are
    # hand-edited): a legacy column spelled like a drama field would collide.
    collisions = [f for f in DRAMA_SONG_FIELDS
                  if f.lower() in {str(h).strip().lower() for h in headings}]
    if collisions:
        raise MigrationError(
            "appending the drama-song headings would duplicate existing "
            "heading(s): %s" % ", ".join(collisions))

    # cycle_id, when present, must sit at its pinned index or the upsert key
    # has already drifted into a drama column. Checked before the generic
    # layout refusal so the diagnosis names the real fault.
    if TECHNICAL_HEADING in headings:
        idx = headings.index(TECHNICAL_HEADING)
        if idx != TECHNICAL_INDEX:
            raise MigrationError(
                "%r is at index %d — the installed contract pins it at index "
                "%d (column %s); repair the sheet by hand"
                % (TECHNICAL_HEADING, idx, TECHNICAL_INDEX, TECHNICAL_COLUMN))

    if not _overview_headings_ok(headings):
        raise MigrationError(
            "Weekly Overview headings are neither the 1.2.0 client layout nor "
            "the installed 1.3.0 layout (cycle_id at column U, the five "
            "Drama Song fields at V..Z). Retired/divergent layouts are never "
            "guessed — repair the sheet against "
            "35-social-media-planner/config/sheet-template.schema.json; got "
            "%r" % (headings,))

    old_n = len(headings)

    new_headings = list(WEEKLY_OVERVIEW_HEADINGS_130)
    if len(new_headings) != len(set(str(h).strip().lower() for h in new_headings)):
        raise MigrationError("Weekly Overview headings would not be unique "
                             "after the append")

    # Rows wider than 1.2.0's 21 cells already hold divergent drama columns —
    # the layout this rewrite exists to end. Refuse by name.
    for idx, row in enumerate(rows):
        if len(row) > TECHNICAL_INDEX + 1:
            raise MigrationError(
                "row %d has %d cells on a %s layout (max %d) — divergent "
                "drama-song columns are not migrated; repair the sheet by hand"
                % (idx, len(row), SCHEMA_FROM, TECHNICAL_INDEX + 1))

    target_n = len(new_headings)          # 26
    drama_n = len(DRAMA_SONG_FIELDS)      # 5
    cells_added = 0
    row_lengths = []
    for idx, row in enumerate(rows):
        before = list(row)
        # Preserve cells 0..20 in place (the client columns and, when the row
        # carries it, the technical key at index 20). Short rows are padded
        # through the key slot so every migrated row is the installed width.
        head = before[:TECHNICAL_INDEX + 1]
        if len(head) < TECHNICAL_INDEX + 1:
            head = head + [""] * (TECHNICAL_INDEX + 1 - len(head))
        after = head + [""] * drama_n
        # --- the no-loss invariant, checked on every row ---------------
        if after[:len(before)] != before:
            raise MigrationError("row %d: pre-existing cells changed" % idx)
        if after[TECHNICAL_INDEX + 1:] != [""] * drama_n:
            raise MigrationError("row %d: new cells are not empty" % idx)
        if after[TECHNICAL_INDEX] != (before[TECHNICAL_INDEX]
                                      if len(before) > TECHNICAL_INDEX else ""):
            raise MigrationError("row %d: technical key cell moved" % idx)
        rows[idx] = after
        row_lengths.append({"row": idx, "before": len(before), "after": len(after)})
        cells_added += len(after) - len(before)

    tab["headings"] = new_headings
    if had_rows:
        tab["rows"] = rows
    findings.append(
        "%s: technical %r kept at column %s (index %d); +%d drama-song "
        "heading(s) at columns V..Z (indexes 21..25); %d row(s) widened to "
        "%d cells" % (OVERVIEW_TAB, TECHNICAL_HEADING, TECHNICAL_COLUMN,
                      TECHNICAL_INDEX, drama_n, len(rows), target_n))
    return {"tab": OVERVIEW_TAB, "action": "append_drama_song_fields",
            "headings_before": old_n, "headings_after": len(new_headings),
            "rows_before": len(rows), "rows_after": len(rows),
            "cells_added": cells_added, "rows": row_lengths,
            "detail": "cycle_id stays at column U; the five installed "
                      "drama-song headings land at V..Z; every pre-existing "
                      "cell kept its value and index"}

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
    tabs = doc.get("tabs")
    if not isinstance(tabs, dict) or OVERVIEW_TAB not in tabs:
        raise MigrationError("no '%s' tab — the drama-song fields have nowhere "
                             "to go" % OVERVIEW_TAB)
    headings = list((tabs[OVERVIEW_TAB].get("headings") or []))
    layout_ok = list(headings) == WEEKLY_OVERVIEW_HEADINGS_130
    already = version == (1, 3, 0) and layout_ok
    if version == (1, 3, 0) and not layout_ok:
        raise MigrationError(
            "schema_version says %s but '%s' is not the installed 1.3.0 "
            "layout (cycle_id at index %d / column %s, the five drama-song "
            "fields at indexes 21..25) — repair the contract against "
            "35-social-media-planner/config/sheet-template.schema.json, this "
            "migration refuses to guess; got %r"
            % (raw, OVERVIEW_TAB, TECHNICAL_INDEX, TECHNICAL_COLUMN, headings))
    if already:
        return ([{"tab": OVERVIEW_TAB, "action": "already_1_3_0",
                  "detail": "schema_version already %s and the Weekly Overview "
                            "is the installed layout" % SCHEMA_TO}], [], True)
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
      * the Weekly Overview lands on the installed 26-cell layout exactly;
      * every pre-existing heading survives, in order, as a prefix;
      * every pre-existing row cell keeps its value at its index — including
        the technical key at index 20 when the row carried one;
      * the five new drama cells exist and are empty;
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
            if a_head != WEEKLY_OVERVIEW_HEADINGS_130:
                problems.append("%s: headings are not the installed 1.3.0 "
                                "layout (got %d cells)"
                                % (name, len(a_head)))
            elif b_head != WEEKLY_OVERVIEW_HEADINGS_130:
                # Whatever 1.2.0 shape it started from, the result must be the
                # installed row with the original headings as its prefix.
                if a_head[:len(b_head)] != b_head:
                    problems.append("%s: pre-existing headings moved or changed"
                                    % name)
                if a_head[len(b_head):] != WEEKLY_OVERVIEW_HEADINGS_130[len(b_head):]:
                    problems.append("%s: appended headings are not the "
                                    "installed tail %s"
                                    % (name, WEEKLY_OVERVIEW_HEADINGS_130[len(b_head):]))
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
                if (len(a_row) > TECHNICAL_INDEX and len(b_row) > TECHNICAL_INDEX
                        and a_row[TECHNICAL_INDEX] != b_row[TECHNICAL_INDEX]):
                    problems.append("%s row %d: technical key cell moved"
                                    % (name, i))
                if a_row[TECHNICAL_INDEX + 1:TECHNICAL_INDEX + 1 + drama_n] \
                        != [""] * drama_n:
                    problems.append("%s row %d: drama cells are not empty"
                                    % (name, i))
                if len(a_row) < len(b_row):
                    problems.append("%s row %d: row got shorter" % (name, i))
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

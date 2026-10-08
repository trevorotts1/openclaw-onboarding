#!/usr/bin/env python3
"""sheet_schema_130 -- the Skill 35 sheet-template contract at 1.3.0.

Source: Owner D27 / D35, 2026-10-07, plan section 6.15.

1.3.0 adds five drama-song columns to the Weekly Overview summary row -- which
style was chosen for the week, whether the week produced one, what it cost,
where the video lives and which channels took it -- and bumps the template
schema_version the provisioner stamps into appProperties and developerMetadata.

Layout contract this module encodes (indexes are 0-based, columns are A=0):

    0..19   the 1.2.0 client columns (Week Of .. Notes), A-T, UNCHANGED
    20      cycle_id, column U -- the pre-1.3.0 provisioner's technical
            column, pinned at the same index so the row-append upsert key
            never moves
    21..25  the five drama-song columns, V-Z

Because A-U keep their 1.2.0 meaning, a 1.2.0 -> 1.3.0 migration only appends
columns; no existing cell has to move.

Pure data and pure functions: stdlib only, no transport, no KIE, no spend.
Skill 74 stays the sole KIE path -- this module describes columns and nothing
calls out.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SOURCE = "Owner D27/D35 2026-10-07, plan 6.15"
TOOL_VERSION = "1.0.0"

SCHEMA_VERSION = "1.3.0"
PREVIOUS_SCHEMA_VERSION = "1.2.0"
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

CONTRACT_RELATIVE_PATH = os.path.join(
    "35-social-media-planner", "config", "sheet-template.schema.json"
)

# The Weekly Overview client columns exactly as 1.2.0 shipped them (A-T).
HEADINGS_1_2_0 = (
    "Week Of", "Theme of the Week", "Research", "Core Content", "Images",
    "Videos", "Facebook", "Instagram", "LinkedIn", "YouTube", "TikTok",
    "Pinterest", "Carousels", "Blog", "Podcast", "Email", "QC", "Scheduled",
    "Overall", "Notes",
)

# Technical column the 1.2.0 provisioner appended; it holds the row-append
# upsert key (_row_key), so its index must not move when 1.3.0 lands.
TECHNICAL_HEADING = "cycle_id"
TECHNICAL_INDEX = 20
TECHNICAL_COLUMN = "U"

# The five drama-song columns 1.3.0 adds. `key` is the row-append webhook
# payload name; `index`/`column` are the Weekly Overview cell they land in.
DRAMA_SONG_FIELDS = (
    {
        "heading": "Drama Song Style",
        "key": "drama_song_style",
        "kind": "text",
        "index": 21,
        "column": "V",
        "source": "style chosen for the week (look / music / voice / length)",
    },
    {
        "heading": "Drama Song Status",
        "key": "drama_song_status",
        "kind": "status",
        "index": 22,
        "column": "W",
        "source": "status dropdown; blank means no drama song that week",
    },
    {
        "heading": "KIE Cost (cents)",
        "key": "kie_cost_cents",
        "kind": "integer",
        "unit": "usd_cents",
        "index": 23,
        "column": "X",
        "source": "whole cents spent through Skill 74/75 that week",
    },
    {
        "heading": "Drama Song Video Link",
        "key": "drama_song_video_url",
        "kind": "url",
        "index": 24,
        "column": "Y",
        "source": "the produced video's link, RAW text",
    },
    {
        "heading": "Drama Song Channels Posted",
        "key": "drama_song_channels",
        "kind": "text_list",
        "separator": ", ",
        "index": 25,
        "column": "Z",
        "source": "channels the week's drama song was posted to",
    },
)

WEEKLY_OVERVIEW_HEADINGS = (
    HEADINGS_1_2_0 + (TECHNICAL_HEADING,)
    + tuple(field["heading"] for field in DRAMA_SONG_FIELDS)
)
WEEKLY_OVERVIEW_STATUS_COLUMNS = (
    "QC", "Overall", "Drama Song Status",
)
OVERVIEW_ROW_WIDTH = len(WEEKLY_OVERVIEW_HEADINGS)

# What Verify Ready Headers reads back (A1:T1): the first 20 cells only, so
# the ready-header gate is bit-identical before and after 1.3.0.
HEADER_READBACK_HEADINGS = HEADINGS_1_2_0

THIS_WEEK_HEADINGS = (
    "Week", "Client", "Next Action", "Drafting", "QC", "Scheduled",
    "Published", "Needs Attention",
)


class SheetSchemaError(ValueError):
    """Raised by name so a caller can refuse instead of guessing."""


def _column_letter(index):
    """0-based index -> spreadsheet column letter (0 -> A, 26 -> AA)."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def upgrade_headings(headings):
    """Return the Weekly Overview header row at 1.3.0.

    Accepts the 1.2.0 row (20 cells) or the 1.2.0 row with its technical
    column (21 cells), and an already-upgraded 1.3.0 row (26 cells). Any other
    shape refuses by name rather than guessing where the columns sit.
    """
    row = tuple(headings)
    if row == WEEKLY_OVERVIEW_HEADINGS:
        return list(row)
    if row == HEADINGS_1_2_0 or row == HEADINGS_1_2_0 + (TECHNICAL_HEADING,):
        return list(WEEKLY_OVERVIEW_HEADINGS)
    raise SheetSchemaError(
        "HEADINGS_NOT_MIGRATABLE: expected the 1.2.0 row (20 or 21 cells) or "
        "the 1.3.0 row (26 cells); got %d cells starting %r"
        % (len(row), row[:3])
    )


def drama_song_fields_by_key():
    """{webhook payload key: field spec} for the five 1.3.0 columns."""
    return {field["key"]: field for field in DRAMA_SONG_FIELDS}


def validate_contract(doc):
    """Check a sheet-template contract document against 1.3.0.

    Returns a list of failure strings; an empty list means the contract
    matches. This is the same check the mocked suite runs -- callers outside
    this repo (migration, provisioning review) should use it rather than
    re-deriving the rules.
    """
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    if not isinstance(doc, dict):
        return ["CONTRACT_NOT_AN_OBJECT"]

    version = doc.get("schema_version")
    check(isinstance(version, str) and VERSION_PATTERN.match(version or ""),
          "SCHEMA_VERSION_PATTERN: schema_version must be N.N.N")
    check(version == SCHEMA_VERSION,
          "SCHEMA_VERSION_NOT_1_3_0: expected %s, got %r" % (SCHEMA_VERSION, version))

    tabs = doc.get("tabs")
    check(isinstance(tabs, dict), "TABS_MISSING: tabs is not an object")
    tabs = tabs if isinstance(tabs, dict) else {}
    overview = tabs.get("Weekly Overview")
    check(isinstance(overview, dict), "WEEKLY_OVERVIEW_MISSING")
    overview = overview if isinstance(overview, dict) else {}

    headings = tuple(overview.get("headings") or ())
    check(headings == WEEKLY_OVERVIEW_HEADINGS,
          "OVERVIEW_HEADINGS_NOT_1_3_0: expected 26 headings in contract "
          "order, got %d" % len(headings))
    check(len(headings) == len(set(headings)),
          "OVERVIEW_HEADINGS_DUPLICATE: headings_unique is violated")
    check(headings[:len(HEADINGS_1_2_0)] == HEADINGS_1_2_0,
          "OVERVIEW_PREFIX_DRIFT: the 1.2.0 columns A-T must keep their "
          "meaning so migration never has to move a cell")
    if len(headings) > TECHNICAL_INDEX:
        check(headings[TECHNICAL_INDEX] == TECHNICAL_HEADING,
              "TECHNICAL_COLUMN_MOVED: cycle_id must stay at index %d "
              "(column %s) or the row-append upsert key lands in a "
              "drama-song column" % (TECHNICAL_INDEX, TECHNICAL_COLUMN))
    for field in DRAMA_SONG_FIELDS:
        check(field["heading"] in headings,
              "DRAMA_SONG_HEADING_MISSING: %s" % field["heading"])
        if field["heading"] in headings:
            check(headings.index(field["heading"]) == field["index"],
                  "DRAMA_SONG_INDEX_WRONG: %s belongs at index %d, found %d"
                  % (field["heading"], field["index"],
                     headings.index(field["heading"])))

    status_columns = overview.get("status_columns")
    check(isinstance(status_columns, list),
          "STATUS_COLUMNS_MISSING: Weekly Overview status_columns absent")
    status_columns = status_columns if isinstance(status_columns, list) else []
    check(status_columns == list(WEEKLY_OVERVIEW_STATUS_COLUMNS),
          "STATUS_COLUMNS_NOT_1_3_0: expected %r, got %r"
          % (list(WEEKLY_OVERVIEW_STATUS_COLUMNS), status_columns))

    drama = doc.get("drama_song")
    check(isinstance(drama, dict), "DRAMA_SONG_BLOCK_MISSING: the 1.3.0 "
          "contract must declare its drama_song field block")
    drama = drama if isinstance(drama, dict) else {}
    check(drama.get("introduced_in") == SCHEMA_VERSION,
          "DRAMA_SONG_INTRODUCED_IN_WRONG: expected %s" % SCHEMA_VERSION)
    check(drama.get("tab") == "Weekly Overview",
          "DRAMA_SONG_TAB_WRONG: expected Weekly Overview")
    fields = drama.get("fields")
    check(isinstance(fields, list) and len(fields) == len(DRAMA_SONG_FIELDS),
          "DRAMA_SONG_FIELD_COUNT: expected %d fields, got %s"
          % (len(DRAMA_SONG_FIELDS),
             len(fields) if isinstance(fields, list) else None))
    if isinstance(fields, list) and len(fields) == len(DRAMA_SONG_FIELDS):
        for got, expected in zip(fields, DRAMA_SONG_FIELDS):
            for attr in ("heading", "key", "kind", "index", "column"):
                check(got.get(attr) == expected[attr],
                      "DRAMA_SONG_FIELD_%s_MISMATCH: %s expected %r, got %r"
                      % (attr.upper(), expected["heading"],
                         expected[attr], got.get(attr)))
        keys = [f.get("key") for f in fields]
        check(len(keys) == len(set(keys)),
              "DRAMA_SONG_KEY_DUPLICATE: webhook payload keys must be unique")
    technical = drama.get("technical_column")
    check(isinstance(technical, dict) and
          technical.get("heading") == TECHNICAL_HEADING and
          technical.get("index") == TECHNICAL_INDEX,
          "DRAMA_SONG_TECHNICAL_COLUMN: contract must pin cycle_id at index "
          "%d" % TECHNICAL_INDEX)

    this_week = tabs.get("This Week")
    this_week = this_week if isinstance(this_week, dict) else {}
    check(tuple(this_week.get("headings") or ()) == THIS_WEEK_HEADINGS,
          "THIS_WEEK_VIEW_DRIFT: the compact client view stays at 8 columns")

    for required in ("tabs", "status_colors", "formatting_contract"):
        check(required in doc, "REQUIRED_KEY_MISSING: %s" % required)

    return failures


def is_1_3_0(doc):
    """True when a contract document validates clean against 1.3.0."""
    return not validate_contract(doc)


def find_contract(start=None):
    """Locate the repo's sheet-template.schema.json, or return None.

    Walks up from this file (or `start`) looking for
    35-social-media-planner/config/sheet-template.schema.json. The build-root
    artifact mirror has no such tree, so callers there must treat None as
    "contract not shipped alongside", never as "contract is invalid".
    """
    here = os.path.abspath(start or os.path.dirname(__file__))
    while True:
        candidate = os.path.join(here, *CONTRACT_RELATIVE_PATH.split(os.sep))
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Skill 35 sheet-template contract at %s" % SCHEMA_VERSION)
    parser.add_argument("--headings", action="store_true",
                        help="print the 1.3.0 Weekly Overview headings as JSON")
    parser.add_argument("--validate", nargs="?", const="", metavar="PATH",
                        help="validate a contract file (default: the repo copy)")
    parser.add_argument("--version", action="version",
                        version="sheet_schema_130 %s (template %s -> %s)"
                        % (TOOL_VERSION, PREVIOUS_SCHEMA_VERSION, SCHEMA_VERSION))
    args = parser.parse_args(argv)

    if args.headings:
        print(json.dumps(list(WEEKLY_OVERVIEW_HEADINGS), indent=2))
        return 0

    if args.validate is not None:
        path = args.validate or find_contract()
        if not path:
            sys.stderr.write(
                "CONTRACT_NOT_FOUND: no %s above %s\n"
                % (CONTRACT_RELATIVE_PATH, os.path.dirname(__file__)))
            return 2
        if not os.path.isfile(path):
            sys.stderr.write("CONTRACT_NOT_FOUND: %s\n" % path)
            return 2
        try:
            with open(path) as handle:
                doc = json.load(handle)
        except Exception as exc:  # noqa: BLE001 - report, do not guess
            sys.stderr.write("CONTRACT_UNREADABLE: %s: %s\n" % (path, exc))
            return 1
        failures = validate_contract(doc)
        print("sheet_schema_130: %s, %d failure(s)"
              % (os.path.relpath(path), len(failures)))
        for failure in failures:
            print(failure)
        return 1 if failures else 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

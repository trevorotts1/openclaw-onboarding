"""sheet_schema_130 package: the Skill 35 sheet-template contract at 1.3.0
(Owner D27 / D35, plan section 6.15, 2026-10-07).

Bumps schema_version 1.2.0 -> 1.3.0 and declares the five drama-song columns
1.3.0 adds to the Weekly Overview summary row: style chosen, status, KIE cost,
video link, channels posted. Columns A-U keep their 1.2.0 meaning (the
provisioner's technical cycle_id key stays at index 20 / column U), so a
migration only appends V-Z and moves no existing cell.

Column description, heading upgrade and contract validation only -- no KIE, no
network, no spend; Skill 74 stays the sole KIE path. stdlib only.
"""
from .sheet_schema_130 import (
    CONTRACT_RELATIVE_PATH,
    DRAMA_SONG_FIELDS,
    HEADER_READBACK_HEADINGS,
    HEADINGS_1_2_0,
    OVERVIEW_ROW_WIDTH,
    PREVIOUS_SCHEMA_VERSION,
    SCHEMA_VERSION,
    SOURCE,
    TECHNICAL_COLUMN,
    TECHNICAL_HEADING,
    TECHNICAL_INDEX,
    THIS_WEEK_HEADINGS,
    TOOL_VERSION,
    VERSION_PATTERN,
    WEEKLY_OVERVIEW_HEADINGS,
    WEEKLY_OVERVIEW_STATUS_COLUMNS,
    SheetSchemaError,
    drama_song_fields_by_key,
    find_contract,
    is_1_3_0,
    main,
    upgrade_headings,
    validate_contract,
)

__all__ = [
    "CONTRACT_RELATIVE_PATH",
    "DRAMA_SONG_FIELDS",
    "HEADER_READBACK_HEADINGS",
    "HEADINGS_1_2_0",
    "OVERVIEW_ROW_WIDTH",
    "PREVIOUS_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "SOURCE",
    "TECHNICAL_COLUMN",
    "TECHNICAL_HEADING",
    "TECHNICAL_INDEX",
    "THIS_WEEK_HEADINGS",
    "TOOL_VERSION",
    "VERSION_PATTERN",
    "WEEKLY_OVERVIEW_HEADINGS",
    "WEEKLY_OVERVIEW_STATUS_COLUMNS",
    "SheetSchemaError",
    "drama_song_fields_by_key",
    "find_contract",
    "is_1_3_0",
    "main",
    "upgrade_headings",
    "validate_contract",
]

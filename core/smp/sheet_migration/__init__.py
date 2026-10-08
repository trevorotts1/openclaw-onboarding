"""core/smp/sheet_migration — live-sheet migration 1.2.0 -> 1.3.0 for the
Skill 35 social media planner template (Owner D27 / decision 35 / plan 6.15).

Ships three things: scripts/migrate-template.py (additive, no data loss), the
row-append webhook payload carrying the five new fields, and
config/validate-sheet-format.py (validates 1.3.0 and its export wiring).
"""
from .migrate import (
    DRAMA_SONG_FIELDS,
    DRAMA_SONG_PAYLOAD_KEYS,
    LEGACY_OVERVIEW_HEADINGS,
    OVERVIEW_FIELD_INDEX,
    OVERVIEW_KEY_INDEX_120,
    OVERVIEW_KEY_INDEX_130,
    OVERVIEW_TAB,
    SCHEMA_FROM,
    SCHEMA_TO,
    MigrationError,
    lossless,
    migrate_doc,
    parse_version,
    plan_migration,
)

__all__ = [
    "DRAMA_SONG_FIELDS",
    "DRAMA_SONG_PAYLOAD_KEYS",
    "LEGACY_OVERVIEW_HEADINGS",
    "OVERVIEW_FIELD_INDEX",
    "OVERVIEW_KEY_INDEX_120",
    "OVERVIEW_KEY_INDEX_130",
    "OVERVIEW_TAB",
    "SCHEMA_FROM",
    "SCHEMA_TO",
    "MigrationError",
    "lossless",
    "migrate_doc",
    "parse_version",
    "plan_migration",
]

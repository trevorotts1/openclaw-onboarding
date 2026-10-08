"""core/smp/sheet_migration — live-sheet migration 1.2.0 -> 1.3.0 for the
Skill 35 social media planner template (Owner D27 / decision 35 / plan 6.15;
manual H5 rewrite 2026-10-08).

The installed contract
``35-social-media-planner/config/sheet-template.schema.json`` is
authoritative: the row-append upsert key ``cycle_id`` stays at column U
(index 20) and the five drama-song fields land at V..Z (indexes 21..25)
under their installed payload keys. Ships three things:
scripts/migrate-template.py (additive, no data loss), the row-append webhook
payload carrying the five new fields, and config/validate-sheet-format.py
(validates 1.3.0 and its export wiring).
"""
from .migrate import (
    DRAMA_SONG_FIELDS,
    DRAMA_SONG_PAYLOAD_KEYS,
    LEGACY_OVERVIEW_HEADINGS,
    OVERVIEW_FIELD_INDEX,
    OVERVIEW_KEY_INDEX,
    OVERVIEW_TAB,
    SCHEMA_FROM,
    SCHEMA_TO,
    TECHNICAL_COLUMN,
    TECHNICAL_HEADING,
    TECHNICAL_INDEX,
    WEEKLY_OVERVIEW_HEADINGS_130,
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
    "OVERVIEW_KEY_INDEX",
    "OVERVIEW_TAB",
    "SCHEMA_FROM",
    "SCHEMA_TO",
    "TECHNICAL_COLUMN",
    "TECHNICAL_HEADING",
    "TECHNICAL_INDEX",
    "WEEKLY_OVERVIEW_HEADINGS_130",
    "MigrationError",
    "lossless",
    "migrate_doc",
    "parse_version",
    "plan_migration",
]

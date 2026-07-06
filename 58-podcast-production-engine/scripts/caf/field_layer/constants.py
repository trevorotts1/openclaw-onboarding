#!/usr/bin/env python3
"""
Podcast Production Engine, Convert and Flow field layer: constants.

Client-visible name is always "Convert and Flow". The abbreviation GHL is used
only in internal code and comments for brevity (per design/ghl-design.md naming
rule). Never emit "GoHighLevel" or "GHL" on any client-visible surface.

Sources: design/ghl-design.md Sections 2 to 5. Exact field keys are verbatim
from the companion document custom_field_map and must never be guessed, renamed,
or invented.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Transport endpoints (Tier 3 REST). Tier 0 is the caf command line interface.
# ---------------------------------------------------------------------------
LEADCONNECTOR_BASE_URL = "https://services.leadconnectorhq.com"

# design/ghl-design.md Section 3.2 states the contacts calls carry
# Version: 2021-07-28. The 29-ghl-convert-and-flow reference documents
# 2021-04-15 for some endpoints. This is a canary LIVE-VERIFY item: the header
# is resolved from PODCAST_GHL_API_VERSION when set, else the design default.
# Keeping it a single named constant means one place to correct after the
# operator-box canary confirms the accepted value against a live response.
GHL_API_VERSION = os.environ.get("PODCAST_GHL_API_VERSION", "2021-07-28")

# Per-location Private Integration Token prefix (design Section 2.1).
PIT_PREFIX = "pit-"

# ---------------------------------------------------------------------------
# Credential resolution alias sets (design Section 2.2).
#
# LOCATION Private Integration Token aliases ONLY. The Agency PIT and the
# Firebase refresh token are DIFFERENT credentials and are deliberately absent
# here: they must never be substituted for a Location PIT (design Section 2.1,
# isolation doctrine). The shared fleet resolver is expanding to carry the
# CONVERTFLOW family; the field layer names the full expected set locally so it
# never falsely reports a client key missing while that shared change lands.
# ---------------------------------------------------------------------------
LOCATION_PIT_ALIASES = (
    "GOHIGHLEVEL_API_KEY",          # canonical
    "GHL_API_KEY",
    "GHL_PIT",
    "GHL_TOKEN",
    "GHL_PRIVATE_INTEGRATION_TOKEN",
    "PRIVATE_INTEGRATION_TOKEN",
    "GHL_PRIVATE_TOKEN",
    "PIT_TOKEN",
    "GHL_PIT_TOKEN",
    "GOHIGHLEVEL_LOCATION_PIT",
    "GHL_LOCATION_PIT",
    # Convert and Flow branded additions (design Section 2.2 recommendation).
    "CONVERTFLOW_API_KEY",
    "CONVERTANDFLOW_API_KEY",
    "CONVERT_AND_FLOW_API_KEY",
    "CONVERTFLOW_PIT",
    "CONVERTANDFLOW_PIT",
)

# Aliases that must NEVER resolve a Location PIT (isolation guard).
FORBIDDEN_PIT_ALIASES = (
    "GOHIGHLEVEL_AGENCY_PIT",
    "GHL_AGENCY_PIT",
    "AGENCY_PIT",
    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
)

LOCATION_ID_ALIASES = (
    "GHL_LOCATION_ID",              # canonical for this alias set
    "GOHIGHLEVEL_LOCATION_ID",
    "LOCATION_ID",
    "CONVERTANDFLOW_LOCATION_ID",
    "CONVERTFLOW_LOCATION_ID",
)

# ---------------------------------------------------------------------------
# Custom field keys (verbatim, design Sections 3.2 and 3.3).
# ---------------------------------------------------------------------------

# The single field whose change fires the client account workflow
# "04-Podcast is Completed". It is written ALONE and LAST (design Section 3.4).
EPISODE_URL_KEY = "contact.podcast_survey_episode_url"

# WRITE fields carried in the first batch call (everything except the URL key).
# title, description, Episode Package doc link, Speech Script doc link.
BATCH_REQUIRED_WRITE_KEYS = (
    "contact.podcast_survey_episode_title",
    "contact.podcast_survey_episode_description",
    "contact.finish_podcast_google_doc_link",
    "contact.podcast_transcript_link",
)

# Optional WRITE fields, included in the batch only when a value is supplied
# and (for book_teaser) only when the field exists in the account.
FULL_TRANSCRIPT_KEY = "contact.podcast_full_transcript"   # optional text store
BOOK_TEASER_KEY = "contact.book_teaser"                   # Interview mode only

# The full ordered set of five required link-back keys (design Section 3.4:
# "Write LAST among the five"). URL is intentionally last.
REQUIRED_WRITE_KEYS = BATCH_REQUIRED_WRITE_KEYS + (EPISODE_URL_KEY,)

# READ fields (input side, design Section 3.2). Exact keys only.
# The double underscore in podcast_survey__additional_info is deliberate and
# must never be normalized to a single underscore variant.
ADDITIONAL_INFO_DOUBLE_UNDERSCORE_KEY = "contact.podcast_survey__additional_info"

READ_KEYS = (
    "contact.podcast_survey_writing_style",
    "contact.select_your_presentation_style_personal_podcast",
    "contact.my_preferred_pronoun",
    "contact.podcast_interview_smiq",
    "contact.smiq_answers",
    "contact.smiq_history",
    "contact.my_client_smiq_answers",
    "contact.my_client_smiq_history",
    ADDITIONAL_INFO_DOUBLE_UNDERSCORE_KEY,
    "contact.date_for_release",
)

# All keys the field-map cache resolves (read side plus write side, deduped,
# order preserved for a stable audit).
def all_field_keys() -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for key in (*READ_KEYS, *REQUIRED_WRITE_KEYS, FULL_TRANSCRIPT_KEY, BOOK_TEASER_KEY):
        seen.setdefault(key, None)
    return tuple(seen.keys())


# ---------------------------------------------------------------------------
# Value hygiene (design Section 3.4).
# ---------------------------------------------------------------------------
# Forbidden characters expressed as escapes so no literal em dash byte or fence
# sequence appears in this source file (keeps naive byte scanners quiet).
EM_DASH_CHARS = ("\u2014", "\u2015")  # em dash, horizontal bar (both forbidden)
TRIPLE_BACKTICK = "`" * 3

# Keys whose values are bare URLs (no markdown, no surrounding quotes). The
# book_teaser field carries the teaser PDF link, so it is URL-hygiene checked.
URL_WRITE_KEYS = (
    EPISODE_URL_KEY,
    "contact.finish_podcast_google_doc_link",
    "contact.podcast_transcript_link",
    BOOK_TEASER_KEY,
)


# ---------------------------------------------------------------------------
# State file (design Section 8). No secret material is ever stored here.
# ---------------------------------------------------------------------------
STATE_FILE_NAME = "ghl-state.json"


def default_state_dir() -> str:
    """Per-client state directory, override with PODCAST_ENGINE_STATE_DIR."""
    override = os.environ.get("PODCAST_ENGINE_STATE_DIR")
    if override:
        return override
    return os.path.expanduser("~/.openclaw/podcast-engine/state")

"""Canonical submission and job-key computation.

Implements design/webhook-design.md Section 3.1 exactly:

    job_key = "pd-" + <contact_id> + "-" + first16hex( sha256( canonical_submission ) )

canonical_submission is built from canonical fields ONLY, AFTER meaning-mapping,
so the same submission arriving via Make.com and via a Convert and Flow webhook
(different field spellings, same meaning) hashes identically. Volatile transport
fields (delivery timestamps, event ids, execution ids, signatures, retry counters,
_test flags, and anything not in the canonical hash list) are excluded so they
cannot defeat dedup.
"""

from __future__ import annotations

import hashlib
import re

# Section 3.1 step 1: exactly these canonical fields participate in the hash.
# NOTE: writing_model, web_research_tool, workflow_trigger, retry, and _test are
# canonical fields the mapper carries, but they are intentionally NOT in this list,
# so they never affect the job key. preset is also a canonical field (OPTION A,
# rem-5) but is hash-excluded (see payload-schema.json x-canonical-hash-note),
# so an intake-supplied preset change never defeats dedup.
# transparency_answer IS hashed: the mapper maps podcast_interview_smiq/smiq to a
# DISTINCT transparency_answer canonical field, and two submissions differing
# ONLY in that answer are genuinely different episodes that MUST produce
# different job keys; excluding it would let the second be deduped as a false
# duplicate. This list is synced to the production job_key.HASH_FIELDS
# (scripts/webhook/job_key.py) and to payload-schema.json x-canonical-hash-fields
# (enforced by tests/webhook/test_r09_schema_hash_fields.py).
HASH_FIELDS = [
    "mode",
    "style",
    "show_name",
    "host_name",
    "first_name",
    "last_name",
    "preferred_pronoun",
    "q1_answer",
    "q2_answer",
    "q3_answer",
    "q4_answer",
    "q5_answer",
    "q6_answer",
    "q7_answer",
    "transparency_answer",
    "additional_info",
    "target_runtime",
    "tts_model",
    "podcast_id",
    "location_id",
    "contact_id",
    "publish_timestamp",
    "episode_type",
    "explicit",
]

# Enum-shaped fields are lowercased during hash normalization (Section 3.1 step 3).
# Free-text answers and names keep their case; only whitespace is normalized.
# Synced to the production job_key.ENUM_HASH_FIELDS (scripts/webhook/job_key.py):
# mode, style, episode_type, explicit. preferred_pronoun and tts_model are NOT
# enum-lowercased in the production hash (preferred_pronoun keeps its case;
# tts_model is a model id, not an enum token), so they are excluded here to match.
ENUM_HASH_FIELDS = {"mode", "style", "episode_type", "explicit"}

_WHITESPACE = re.compile(r"\s+")


def _normalize_value(field: str, value) -> str:
    """Section 3.1 step 3 normalization applied per field."""
    text = "" if value is None else str(value)
    # trim, then collapse internal runs of whitespace to a single space
    text = _WHITESPACE.sub(" ", text).strip()
    if field in ENUM_HASH_FIELDS:
        text = text.lower()
    return text


def canonical_submission(canonical: dict) -> str:
    """Serialize the hash fields as sorted key=value lines joined with newlines.

    Empty and null fields are dropped (Section 3.1 step 3). The mapper's own
    normalization is deliberately re-applied here so the hash is defined purely on
    canonical field values and is independent of any upstream normalization pass.
    """
    lines = []
    for field in sorted(HASH_FIELDS):
        if field not in canonical:
            continue
        normalized = _normalize_value(field, canonical.get(field))
        if normalized == "":
            continue
        lines.append(field + "=" + normalized)
    return "\n".join(lines)


def first16hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def compute_job_key(canonical: dict) -> str:
    """Return the deterministic job key for a canonical submission.

    Requires contact_id: the key is anchored to the person. A submission with no
    contact_id cannot be deduplicated and must be handled as needs_input upstream
    (see mapper required-field gate), never assigned a guessed key.
    """
    contact_id = _normalize_value("contact_id", canonical.get("contact_id"))
    if contact_id == "":
        raise ValueError("cannot compute job_key without contact_id")
    digest = first16hex(canonical_submission(canonical))
    return "pd-" + contact_id + "-" + digest

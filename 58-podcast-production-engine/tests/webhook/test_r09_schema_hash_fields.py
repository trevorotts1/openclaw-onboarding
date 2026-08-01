"""R-09 cross-check: payload-schema.json x-canonical-hash-fields == job_key.HASH_FIELDS.

The canonical submission hash (job_key.py, design/webhook-design.md Section 3.1)
and the static intake schema (config/payload-schema.json) are TWO declarations of
the same contract: exactly which canonical fields participate in the dedup hash.
If they drift, a field the schema promises is hashed could silently drop out of
the job key (a false duplicate), or a field the schema excludes could leak into
the hash (a redelivery falsely diverging). This test imports the PRODUCTION
job_key module (scripts/webhook/job_key.py), not the spec_reference oracle, so it
provably checks the shipped hash contract against the shipped schema. The oracle
is a frozen executable spec of the webhook-design.md contract; the schema and the
production module are the two production declarations that must agree.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

# Import the PRODUCTION job_key module (not the spec_reference oracle) so this
# cross-check is against the shipped hash contract, not the frozen spec encoding.
_HERE = os.path.dirname(os.path.abspath(__file__))
_WEBHOOK_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "scripts", "webhook"))
if _WEBHOOK_DIR not in sys.path:
    sys.path.insert(0, _WEBHOOK_DIR)

import job_key as _prod_job_key  # noqa: E402

_SCHEMA_PATH = os.path.normpath(os.path.join(_HERE, "..", "..", "config", "payload-schema.json"))


def _load_schema():
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def test_schema_hash_fields_equal_production_hash_fields():
    """The schema's x-canonical-hash-fields list and job_key.HASH_FIELDS must be
    the same set of fields. Order is irrelevant (the hash sorts by key), so the
    comparison is set-based; a difference is a contract drift that breaks dedup."""
    schema = _load_schema()
    schema_fields = set(schema["x-canonical-hash-fields"])
    prod_fields = set(_prod_job_key.HASH_FIELDS)
    missing_in_prod = schema_fields - prod_fields
    extra_in_prod = prod_fields - schema_fields
    assert not missing_in_prod, (
        "schema x-canonical-hash-fields has fields NOT in job_key.HASH_FIELDS "
        "(these would be silently dropped from the hash): "
        + ", ".join(sorted(missing_in_prod))
    )
    assert not extra_in_prod, (
        "job_key.HASH_FIELDS has fields NOT in schema x-canonical-hash-fields "
        "(these would be hashed without a schema declaration): "
        + ", ".join(sorted(extra_in_prod))
    )
    assert schema_fields == prod_fields, (
        "schema and production hash field sets differ"
    )


def test_schema_hash_fields_match_production_count_and_no_duplicates():
    """The schema list must not carry duplicate entries and must have the same
    cardinality as job_key.HASH_FIELDS (a set-equality guard against a silent
    dup inflating the schema list while the set still matches)."""
    schema = _load_schema()
    schema_list = schema["x-canonical-hash-fields"]
    assert len(schema_list) == len(set(schema_list)), (
        "schema x-canonical-hash-fields has duplicate entries: "
        + ", ".join(sorted(set([f for f in schema_list if schema_list.count(f) > 1])))
    )
    assert len(schema_list) == len(_prod_job_key.HASH_FIELDS), (
        "schema x-canonical-hash-fields count (%d) != job_key.HASH_FIELDS count (%d)"
        % (len(schema_list), len(_prod_job_key.HASH_FIELDS))
    )


def test_preset_is_excluded_from_hash_fields():
    """preset is a real canonical field (OPTION A) but is hash-EXCLUDED, like
    retry and _test, so an intake-supplied preset change never defeats dedup.
    The schema's x-canonical-hash-note names preset explicitly as excluded; this
    asserts the field lists honor that (preset appears in neither hash list)."""
    schema = _load_schema()
    schema_fields = set(schema["x-canonical-hash-fields"])
    prod_fields = set(_prod_job_key.HASH_FIELDS)
    assert "preset" not in schema_fields, (
        "preset must be hash-excluded but appears in schema x-canonical-hash-fields"
    )
    assert "preset" not in prod_fields, (
        "preset must be hash-excluded but appears in job_key.HASH_FIELDS"
    )


def test_transparency_answer_is_in_hash_fields():
    """transparency_answer is a contact-authored survey answer that the mapper
    maps to its own canonical field (podcast_interview_smiq/smiq). Two
    submissions differing ONLY in that answer are genuinely distinct episodes,
    so it MUST be in both hash declarations (the dedup hole it closes)."""
    schema = _load_schema()
    schema_fields = set(schema["x-canonical-hash-fields"])
    prod_fields = set(_prod_job_key.HASH_FIELDS)
    assert "transparency_answer" in schema_fields, (
        "transparency_answer must be hashed but is missing from schema "
        "x-canonical-hash-fields"
    )
    assert "transparency_answer" in prod_fields, (
        "transparency_answer must be hashed but is missing from job_key.HASH_FIELDS"
    )
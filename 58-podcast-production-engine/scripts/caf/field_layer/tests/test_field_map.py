#!/usr/bin/env python3
"""Field-map tests: required keys, double-underscore assertion, book_teaser, cache."""
from __future__ import annotations

import pytest

from field_layer import constants
from field_layer.field_map import (
    MissingRequiredFieldError,
    build_field_map,
    get_or_build_field_map,
)
from field_layer.state import GhlState


def test_all_required_write_keys_resolve(dataplane):
    result = build_field_map(dataplane)
    for key in constants.REQUIRED_WRITE_KEYS:
        assert key in result.field_map


def test_missing_required_key_raises(custom_fields, fake_dataplane_cls):
    trimmed = [f for f in custom_fields
               if f["fieldKey"] != "contact.podcast_transcript_link"]
    dp = fake_dataplane_cls(trimmed)
    with pytest.raises(MissingRequiredFieldError) as exc:
        build_field_map(dp)
    assert "contact.podcast_transcript_link" in exc.value.missing


def test_double_underscore_key_is_exact_never_single(custom_fields, fake_dataplane_cls):
    # Replace the double-underscore key with the single-underscore variant only.
    single = constants.ADDITIONAL_INFO_DOUBLE_UNDERSCORE_KEY.replace(
        "survey__additional", "survey_additional")
    swapped = []
    for f in custom_fields:
        if f["fieldKey"] == constants.ADDITIONAL_INFO_DOUBLE_UNDERSCORE_KEY:
            swapped.append({**f, "fieldKey": single})
        else:
            swapped.append(f)
    dp = fake_dataplane_cls(swapped)
    result = build_field_map(dp)
    # The layer must NOT map the single variant to the double key.
    assert constants.ADDITIONAL_INFO_DOUBLE_UNDERSCORE_KEY not in result.field_map
    assert result.additional_info_double_underscore_present is False
    assert result.additional_info_single_underscore_seen is True


def test_book_teaser_absent_by_default(dataplane):
    result = build_field_map(dataplane)
    assert result.book_teaser_present is False
    assert constants.BOOK_TEASER_KEY not in result.field_map


def test_book_teaser_present_when_field_exists(custom_fields, fake_dataplane_cls):
    custom_fields.append({"id": "fid_bt", "fieldKey": constants.BOOK_TEASER_KEY})
    dp = fake_dataplane_cls(custom_fields)
    result = build_field_map(dp)
    assert result.book_teaser_present is True
    assert result.field_map[constants.BOOK_TEASER_KEY] == "fid_bt"


def test_cache_reuse_avoids_relisting(dataplane, tmp_path):
    state = GhlState(str(tmp_path))
    first = get_or_build_field_map(dataplane, state)
    assert first.from_cache is False
    assert dataplane.list_count == 1
    # Second call reads the cache and does not list the account again.
    second = get_or_build_field_map(dataplane, state)
    assert second.from_cache is True
    assert second.field_map == first.field_map
    assert dataplane.list_count == 1

    # A forced refresh does re-list.
    third = get_or_build_field_map(dataplane, state, refresh=True)
    assert third.from_cache is False
    assert dataplane.list_count == 2


def test_prefix_tolerant_lookup_handles_bare_keys(custom_fields, fake_dataplane_cls):
    # Some API versions return fieldKey without the contact. prefix.
    bare = []
    for f in custom_fields:
        bare.append({**f, "fieldKey": f["fieldKey"].replace("contact.", "")})
    dp = fake_dataplane_cls(bare)
    result = build_field_map(dp)
    for key in constants.REQUIRED_WRITE_KEYS:
        assert key in result.field_map

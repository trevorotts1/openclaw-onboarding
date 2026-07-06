#!/usr/bin/env python3
"""Writer tests: batch-then-URL-last ordering, read-back, retry, hygiene."""
from __future__ import annotations

import pytest

from field_layer import constants
from field_layer.field_map import build_field_map
from field_layer.writer import (
    ReadBackMismatch,
    ValueHygieneError,
    verify_read_back,
    write_link_back,
)

URL_ID = "fid_0"
TITLE_ID = "fid_1"
DESC_ID = "fid_2"
PKG_ID = "fid_3"
SCRIPT_ID = "fid_4"


def _field_result(dataplane):
    return build_field_map(dataplane)


def test_url_is_written_alone_and_last(dataplane, valid_values):
    fr = _field_result(dataplane)
    result = write_link_back(dataplane, "c1", valid_values, fr)

    # Exactly two write calls: the batch, then the URL alone.
    assert len(dataplane.write_calls) == 2
    batch_call, url_call = dataplane.write_calls
    assert URL_ID not in batch_call, "URL must never ride in the batch call"
    assert batch_call == [TITLE_ID, DESC_ID, PKG_ID, SCRIPT_ID]
    assert url_call == [URL_ID], "URL must be written alone and last"
    assert result.url_written is True
    assert result.read_back_pass is True
    assert result.public_summary()["save_confirmed"] is True


def test_read_back_matches_byte_for_byte(dataplane, valid_values):
    fr = _field_result(dataplane)
    write_link_back(dataplane, "c1", valid_values, fr)
    ok, mismatched = verify_read_back(dataplane, "c1", fr.field_map, valid_values)
    assert ok is True and mismatched == []


def test_optional_full_transcript_rides_in_batch(dataplane, valid_values):
    fr = _field_result(dataplane)
    values = dict(valid_values)
    values[constants.FULL_TRANSCRIPT_KEY] = "full spoken transcript text"
    write_link_back(dataplane, "c1", values, fr)
    batch_call = dataplane.write_calls[0]
    assert "fid_5" in batch_call and URL_ID not in batch_call


def test_book_teaser_absent_is_a_note_not_a_failure(dataplane, valid_values):
    fr = _field_result(dataplane)  # conftest omits book_teaser by default
    values = dict(valid_values)
    values[constants.BOOK_TEASER_KEY] = "https://media.example.com/teaser.pdf"
    result = write_link_back(dataplane, "c1", values, fr)
    assert result.book_teaser_note is not None
    assert "book_teaser" in result.book_teaser_note
    # Never written, never failed.
    assert all("fid_bt" not in call for call in dataplane.write_calls)
    assert result.read_back_pass is True


def test_book_teaser_present_rides_in_batch(custom_fields, valid_values, fake_dataplane_cls):
    custom_fields.append({"id": "fid_bt", "fieldKey": constants.BOOK_TEASER_KEY,
                          "dataType": "TEXT"})
    dataplane = fake_dataplane_cls(custom_fields)
    fr = build_field_map(dataplane)
    assert fr.book_teaser_present is True
    values = dict(valid_values)
    values[constants.BOOK_TEASER_KEY] = "https://media.example.com/teaser.pdf"
    write_link_back(dataplane, "c1", values, fr)
    assert "fid_bt" in dataplane.write_calls[0]


def test_mismatch_retries_once_then_passes(dataplane, valid_values):
    dataplane.drop_once.add(URL_ID)  # first URL write does not land
    fr = _field_result(dataplane)
    result = write_link_back(dataplane, "c1", valid_values, fr)
    assert result.retried is True
    assert result.read_back_pass is True
    # batch, url(dropped), retry url = 3 calls
    assert len(dataplane.write_calls) == 3
    assert dataplane.write_calls[-1] == [URL_ID]


def test_permanent_mismatch_raises_after_one_retry(dataplane, valid_values):
    dataplane.drop_always.add(URL_ID)
    fr = _field_result(dataplane)
    with pytest.raises(ReadBackMismatch) as exc:
        write_link_back(dataplane, "c1", valid_values, fr)
    assert constants.EPISODE_URL_KEY in exc.value.mismatched_keys


def test_em_dash_in_title_is_rejected(dataplane, valid_values):
    fr = _field_result(dataplane)
    values = dict(valid_values)
    values["contact.podcast_survey_episode_title"] = "Quiet Founders \u2014 Win"
    with pytest.raises(ValueHygieneError):
        write_link_back(dataplane, "c1", values, fr)


def test_triple_backtick_in_description_is_rejected(dataplane, valid_values):
    fr = _field_result(dataplane)
    values = dict(valid_values)
    values["contact.podcast_survey_episode_description"] = "text " + ("`" * 3) + " fence"
    with pytest.raises(ValueHygieneError):
        write_link_back(dataplane, "c1", values, fr)


def test_markdown_url_is_rejected(dataplane, valid_values):
    fr = _field_result(dataplane)
    values = dict(valid_values)
    values[constants.EPISODE_URL_KEY] = "[link](https://x.com/e/1)"
    with pytest.raises(ValueHygieneError):
        write_link_back(dataplane, "c1", values, fr)


def test_quoted_url_is_stripped_to_bare(dataplane, valid_values):
    fr = _field_result(dataplane)
    values = dict(valid_values)
    values[constants.EPISODE_URL_KEY] = '"https://client.podbean.com/e/ep-9"'
    result = write_link_back(dataplane, "c1", values, fr)
    stored = dataplane.get_contact("c1")["customFields"]
    url_stored = next(f["value"] for f in stored if f["id"] == URL_ID)
    assert url_stored == "https://client.podbean.com/e/ep-9"
    assert result.read_back_pass is True


def test_missing_required_value_is_rejected(dataplane, valid_values):
    fr = _field_result(dataplane)
    values = dict(valid_values)
    del values["contact.podcast_transcript_link"]
    with pytest.raises(ValueHygieneError):
        write_link_back(dataplane, "c1", values, fr)

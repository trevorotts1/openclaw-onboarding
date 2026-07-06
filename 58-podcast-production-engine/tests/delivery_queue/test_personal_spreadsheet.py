"""Tests for the Personal-mode running spreadsheet (W1.28, PRD Step 17 / Section 8)."""

from __future__ import annotations

import csv
import os

import pytest

import personal_spreadsheet as ps


def _record():
    return {
        "episode_number": 3,
        "publish_date": "2026-07-06",
        "episode_title": "Say the Quiet Part",
        "style": "vulnerable",
        "runtime_minutes": 9.8,
        "spoken_word_count": 1370,
        "podbean_permalink": "https://acme.podbean.com/e/ep3",
        "episode_package_url": "https://docs.example.com/pkg3",
        "speech_script_url": "https://docs.example.com/script3",
        "cover_image_url": "https://media.example.com/ep3.jpg",
        "mp3_media_url": "https://media.example.com/ep3.mp3",
        "submitter": {"first_name": "Dana", "last_name": "Reed"},
        "status": "complete",
    }


# --- mode guard --------------------------------------------------------------


def test_append_refuses_interview_mode(tmp_path):
    backend = ps.CsvBackend(str(tmp_path))
    ref = ps.create_at_setup("acme", backend, str(tmp_path))
    with pytest.raises(ValueError):
        ps.append_episode(ref, backend, _record(), "interview_style_podcast")


def test_assert_personal_mode_accepts_personal_variants():
    ps.assert_personal_mode("personal_podcast_style")
    ps.assert_personal_mode("Personal")
    with pytest.raises(ValueError):
        ps.assert_personal_mode("interview_style_podcast")


# --- create at setup, idempotent --------------------------------------------


def test_create_at_setup_writes_header_and_is_idempotent(tmp_path):
    backend = ps.CsvBackend(str(tmp_path))
    ref1 = ps.create_at_setup("acme", backend, str(tmp_path))
    assert ref1.backend == "csv"
    assert backend.header(ref1) == ps.COLUMNS
    # second call reuses, does not duplicate or overwrite
    ref2 = ps.create_at_setup("acme", backend, str(tmp_path))
    assert ref2.sheet_id == ref1.sheet_id
    files = [f for f in os.listdir(tmp_path) if f.endswith(".csv")]
    assert len(files) == 1


def test_create_at_setup_reuses_existing_sheet_by_title(tmp_path):
    backend = ps.CsvBackend(str(tmp_path))
    # a sheet already exists on the box with the default title
    pre = backend.create(ps.default_title("acme"), ps.COLUMNS)
    ref = ps.create_at_setup("acme", backend, str(tmp_path))
    assert ref.sheet_id == pre.sheet_id  # reused, never duplicated


# --- append per episode ------------------------------------------------------


def test_append_episode_writes_a_row(tmp_path):
    backend = ps.CsvBackend(str(tmp_path))
    ref = ps.create_at_setup("acme", backend, str(tmp_path))
    ps.append_episode(ref, backend, _record(), "personal_podcast_style")
    with open(ref.sheet_id, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ps.COLUMNS
    assert rows[1][0] == "3"
    assert rows[1][2] == "Say the Quiet Part"
    assert rows[1][11] == "Dana Reed"  # submitter column
    assert rows[1][6] == "https://acme.podbean.com/e/ep3"


def test_row_rejects_em_dash_in_a_cell():
    bad = _record()
    bad["episode_title"] = "Before" + "\u2014" + "After"
    with pytest.raises(ValueError):
        ps.row_from_record(bad)


# --- custom-field link storage ----------------------------------------------


def test_store_spreadsheet_link_writes_state_and_custom_field(tmp_path):
    backend = ps.CsvBackend(str(tmp_path))
    written = {}

    def field_writer(field_key, url):
        written[field_key] = url

    ref = ps.create_at_setup(
        "acme",
        backend,
        str(tmp_path),
        field_writer=field_writer,
        field_key="contact.podcast_running_spreadsheet",
    )
    state = ps.load_state(str(tmp_path))
    assert state["url"] == ref.url
    assert state["client_id"] == "acme"
    assert state["custom_field_key"] == "contact.podcast_running_spreadsheet"
    assert written["contact.podcast_running_spreadsheet"] == ref.url


def test_store_link_without_writer_stays_state_only(tmp_path):
    backend = ps.CsvBackend(str(tmp_path))
    ps.create_at_setup("acme", backend, str(tmp_path))
    state = ps.load_state(str(tmp_path))
    assert "custom_field_written" not in state


# --- backend selection -------------------------------------------------------


def test_detect_backend_prefers_google_then_notion_then_csv(tmp_path):
    class FakeClient:
        pass

    g = ps.detect_backend(str(tmp_path), google_client=FakeClient())
    assert isinstance(g, ps.GoogleSheetsBackend)
    n = ps.detect_backend(str(tmp_path), notion_client=FakeClient())
    assert isinstance(n, ps.NotionBackend)
    c = ps.detect_backend(str(tmp_path))
    assert isinstance(c, ps.CsvBackend)


def test_injected_backend_without_client_raises_not_silent():
    backend = ps.GoogleSheetsBackend(client=None)
    with pytest.raises(NotImplementedError):
        backend.create("x", ps.COLUMNS)

"""Tests for idempotent page create: page_list + find_page_by_name.

Covers:
- page_list() step-emitter shape
- find_page_by_name() across all supported response shapes
- ID fallback chain (_id / id / pageId)
- Case-insensitive / strip name matching
- Guard clauses (wrong types, blank name)
- Integration flow: list -> find -> update-in-place vs create
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import browser_manager  # needed for session context in argv tests
from ghl_rest_canvas import (
    page_list,
    find_page_by_name,
    page_autosave,
    step_create,
    GHL_BACKEND_ORIGIN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(name: str, _id: str = "abc123", page_version: int = 3) -> dict:
    return {"_id": _id, "name": name, "pageVersion": page_version}


# ---------------------------------------------------------------------------
# TestPageListEmitter
# ---------------------------------------------------------------------------

class TestPageListEmitter:
    def test_returns_dict(self):
        step = page_list("f1", "loc1")
        assert isinstance(step, dict)

    def test_method_is_get(self):
        step = page_list("f1", "loc1")
        assert step["method"] == "GET"

    def test_path_contains_funnel_id(self):
        step = page_list("FUNNEL_XYZ", "loc1")
        assert "FUNNEL_XYZ" in step["path"]

    def test_path_contains_location_id(self):
        step = page_list("f1", "LOC_ABC")
        assert "LOC_ABC" in step["path"]

    def test_url_starts_with_backend_origin(self):
        step = page_list("f1", "loc1")
        assert step["url"].startswith(GHL_BACKEND_ORIGIN.rstrip("/"))

    def test_eval_field_present_and_nonempty(self):
        step = page_list("f1", "loc1")
        assert step.get("eval") and len(step["eval"]) > 10

    def test_argv_absent_without_session(self):
        step = page_list("f1", "loc1")
        assert "argv" not in step

    def test_argv_present_with_session(self):
        with browser_manager.browser_session("sess-fake"):
            step = page_list("f1", "loc1", session="sess-fake")
        assert "argv" in step


# ---------------------------------------------------------------------------
# TestFindPageByName -- happy-path with funnelPages top-level key
# ---------------------------------------------------------------------------

class TestFindPageByName:
    def test_finds_exact_match(self):
        body = {"funnelPages": [_make_page("ZHC Sales Page")]}
        result = find_page_by_name(body, "ZHC Sales Page")
        assert result is not None
        assert result["name"] == "ZHC Sales Page"
        assert result["page_id"] == "abc123"
        assert result["page_version"] == 3

    def test_case_insensitive_match(self):
        body = {"funnelPages": [_make_page("ZHC Sales Page")]}
        assert find_page_by_name(body, "zhc sales page") is not None

    def test_strips_whitespace_in_query(self):
        body = {"funnelPages": [_make_page("ZHC Opt-In")]}
        assert find_page_by_name(body, "  ZHC Opt-In  ") is not None

    def test_strips_whitespace_in_stored_name(self):
        body = {"funnelPages": [{"_id": "x1", "name": "  ZHC Opt-In  ", "pageVersion": 1}]}
        assert find_page_by_name(body, "ZHC Opt-In") is not None

    def test_returns_none_when_no_match(self):
        body = {"funnelPages": [_make_page("ZHC Sales Page")]}
        assert find_page_by_name(body, "ZHC Thank You") is None

    def test_returns_none_for_empty_list(self):
        body = {"funnelPages": []}
        assert find_page_by_name(body, "ZHC Sales Page") is None

    def test_returns_none_for_missing_key(self):
        body = {}
        assert find_page_by_name(body, "ZHC Sales Page") is None


# ---------------------------------------------------------------------------
# TestFindPageByNameIdFallback
# ---------------------------------------------------------------------------

class TestFindPageByNameIdFallback:
    @pytest.mark.parametrize("id_key,id_val", [
        ("_id", "id_underscore"),
        ("id", "id_plain"),
        ("pageId", "id_pageid"),
    ])
    def test_id_fallback(self, id_key, id_val):
        page = {"name": "ZHC Funnel", id_key: id_val, "pageVersion": 1}
        body = {"funnelPages": [page]}
        result = find_page_by_name(body, "ZHC Funnel")
        assert result is not None
        assert result["page_id"] == id_val

    def test_skips_page_with_no_id(self):
        page_no_id = {"name": "ZHC Funnel", "pageVersion": 1}
        page_with_id = {"name": "ZHC Funnel", "_id": "valid_id", "pageVersion": 2}
        body = {"funnelPages": [page_no_id, page_with_id]}
        result = find_page_by_name(body, "ZHC Funnel")
        assert result is not None
        assert result["page_id"] == "valid_id"


# ---------------------------------------------------------------------------
# TestFindPageByNameShapeResilience
# ---------------------------------------------------------------------------

class TestFindPageByNameShapeResilience:
    @pytest.mark.parametrize("top_key", ["funnelPages", "pages", "data", "steps"])
    def test_top_level_keys(self, top_key):
        body = {top_key: [_make_page("ZHC Test")]}
        assert find_page_by_name(body, "ZHC Test") is not None

    def test_nested_funnel_funnelpages(self):
        body = {"funnel": {"funnelPages": [_make_page("ZHC Nested")]}}
        assert find_page_by_name(body, "ZHC Nested") is not None

    def test_nested_funnel_pages(self):
        body = {"funnel": {"pages": [_make_page("ZHC Nested Pages")]}}
        assert find_page_by_name(body, "ZHC Nested Pages") is not None

    def test_nested_funnel_steps(self):
        body = {"funnel": {"steps": [_make_page("ZHC Nested Steps")]}}
        assert find_page_by_name(body, "ZHC Nested Steps") is not None

    def test_page_version_defaults_to_zero_on_missing(self):
        page = {"_id": "p1", "name": "ZHC No Ver"}
        body = {"funnelPages": [page]}
        result = find_page_by_name(body, "ZHC No Ver")
        assert result["page_version"] == 0

    def test_page_version_defaults_to_zero_on_bad_value(self):
        page = {"_id": "p1", "name": "ZHC Bad Ver", "pageVersion": "bad"}
        body = {"funnelPages": [page]}
        result = find_page_by_name(body, "ZHC Bad Ver")
        assert result["page_version"] == 0

    def test_skips_non_dict_entries(self):
        body = {"funnelPages": ["not-a-dict", None, _make_page("ZHC Real")]}
        assert find_page_by_name(body, "ZHC Real") is not None


# ---------------------------------------------------------------------------
# TestFindPageByNameGuards
# ---------------------------------------------------------------------------

class TestFindPageByNameGuards:
    def test_raises_type_error_for_non_dict_body(self):
        with pytest.raises(TypeError, match="page_list_body must be a dict"):
            find_page_by_name(["not", "a", "dict"], "ZHC Page")

    def test_raises_type_error_for_non_str_name(self):
        with pytest.raises(TypeError, match="name must be a str"):
            find_page_by_name({}, 123)

    def test_raises_value_error_for_blank_name(self):
        with pytest.raises(ValueError, match="name must not be blank"):
            find_page_by_name({}, "")

    def test_raises_value_error_for_whitespace_only_name(self):
        with pytest.raises(ValueError, match="name must not be blank"):
            find_page_by_name({}, "   ")


# ---------------------------------------------------------------------------
# TestIdempotentPageCreateFlow -- integration pattern
# ---------------------------------------------------------------------------

class TestIdempotentPageCreateFlow:
    """Verify the update-in-place vs create branch using mocked API responses."""

    def test_update_in_place_when_page_exists(self):
        """When find_page_by_name returns a hit, page_autosave should be used
        instead of step_create to avoid duplicates."""
        existing_page_id = "existing_page_abc"
        existing_version = 5
        fake_list_response = {
            "funnelPages": [
                {"_id": existing_page_id, "name": "ZHC Sales Page", "pageVersion": existing_version}
            ]
        }

        hit = find_page_by_name(fake_list_response, "ZHC Sales Page")
        assert hit is not None, "Should find existing page"
        assert hit["page_id"] == existing_page_id
        assert hit["page_version"] == existing_version

        # Build loop uses page_autosave with existing IDs (no step_create)
        save_step = page_autosave(existing_page_id, {}, funnel_id="f1",
                                  page_version=existing_version + 1)
        assert save_step["method"] == "POST"
        assert existing_page_id in save_step["path"]

    def test_creates_new_when_page_absent(self):
        """When find_page_by_name returns None, step_create is used."""
        fake_list_response = {"funnelPages": []}

        hit = find_page_by_name(fake_list_response, "ZHC Sales Page")
        assert hit is None, "Should not find absent page"

        # Build loop falls through to step_create
        create_step = step_create("funnel1", "ZHC Sales Page", "zhc-sales-page")
        assert create_step["method"] == "POST"

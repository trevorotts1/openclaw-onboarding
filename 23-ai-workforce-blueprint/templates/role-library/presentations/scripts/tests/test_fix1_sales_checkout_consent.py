#!/usr/bin/env python3
"""Fix 1 sales checkout page consent (sales_checkout_builder.py), as
amended by the owner ruling of 2026-10-13.

MUST-TEST: any type="tel" input means both consent boxes are present,
unchecked and REQUIRED. The offline checkout page form carries the two
SMS consent checkboxes (transactional + marketing); neither is checked by
default, and the submit is gated until every box is checked (owner ruling
2026-10-13, superseding the 2026-09-27 D3 optional posture), with a branded
error and a "Check here" tag on each unchecked box.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import sales_checkout_builder as scb  # noqa: E402


def _html():
    brand = {"primary": "#111111", "secondary": "#222222",
             "accent": "#333333", "base": "#ffffff", "ink": "#000000"}
    fields = {"headline": "H", "subhead": "S", "cta": "Buy",
              "order_line": "O", "reassurance": "R"}
    return scb.build_page_html(page_role="checkout", brand=brand,
                               client_name="Acme Co", fields=fields,
                               hero_image_src=None, marker="T",
                               deck_slug="t")


def _input_tag(html: str, name: str) -> str:
    m = re.search(r"<input[^>]*name=\"%s\"[^>]*>" % re.escape(name), html)
    assert m, "missing consent checkbox %s" % name
    return m.group(0)


def test_tel_input_carries_both_consent_boxes():
    html = _html()
    assert "type=\"tel\"" in html
    for name in ("consent_transactional", "consent_marketing"):
        tag = _input_tag(html, name)
        assert "type=\"checkbox\"" in tag
        assert "checked" not in tag
        assert "required" in tag


def test_checkout_submit_is_gated_on_consent():
    html = _html()
    # the branded gate: error element + per-box "Check here" tags + the JS
    # handlers that block the submit while any consent box is unchecked.
    assert "id=\"checkout-consent-error\"" in html
    assert "Check here" in html
    assert "consent-box" in html
    assert "addEventListener('invalid'" in html
    assert "addEventListener('submit'" in html


def test_consent_boxes_carry_wording_not_placeholders():
    html = _html()
    assert "Message and data rates may apply" in html
    assert "Reply STOP to opt out" in html
    assert "[BUSINESS NAME]" not in html
    assert "[USE_CASE_FROM_CAMPAIGN_DESCRIPTION]" not in html

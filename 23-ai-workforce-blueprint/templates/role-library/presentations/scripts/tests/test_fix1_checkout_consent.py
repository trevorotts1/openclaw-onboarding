#!/usr/bin/env python3
"""Fix 1 (D3) -- checkout form consent (checkout_form_builder.py).

MUST-TEST: any type="tel" input means both consent boxes are present,
unchecked and not required. The Skill44 contract keeps GHL's
"Terms & Conditions" element (never deletes it) and carries the two SMS
consent wordings (transactional + marketing); the wording never ships
GHL's seeded placeholders.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import checkout_form_builder as cfb  # noqa: E402


def _contract(**kw):
    offer = {"name": "Test Offer", "price_display": "$1", "amount_minor": 100,
             "currency": "USD", "price_mode": "one_time"}
    scope = {"deck_slug": "t", "run_id": "r", "location_id": "loc",
             "location_bound": False}
    fields = cfb.build_form_schema(offer=offer, intent="lead_capture",
                                   deck_slug="t")
    return cfb.build_skill44_contract(offer=offer, intent="lead_capture",
                                      scope=scope, fields=fields, **kw)


def test_terms_and_conditions_kept_not_deleted():
    contract = _contract(
        consent=cfb.resolve_consent_copy({"company": "Acme Co"}, {}))
    assert ("Terms & Conditions"
            not in contract["form"]["default_fields_delete"])


def test_tel_field_means_both_consent_boxes_unchecked_optional():
    contract = _contract(
        consent=cfb.resolve_consent_copy({"company": "Acme Co"}, {}))
    form = contract["form"]
    # the form collects a phone number (the type="tel" input)
    assert any(f.get("element") == "Phone" for f in form["fields"])
    boxes = {b["kind"]: b for b in form["consent"]["boxes"]}
    assert {"transactional_sms", "marketing_sms"} <= set(boxes)
    for box in boxes.values():
        assert box["default_unchecked"] is True
        assert box["required"] is False


def test_consent_copy_from_intake_never_placeholders():
    copy = cfb.resolve_consent_copy({"company": "Acme Co"}, {})
    assert copy["source"] == "intake"
    for box in copy["boxes"]:
        assert "Acme Co" in box["text"]
        assert "[BUSINESS NAME]" not in box["text"]
        assert "[USE_CASE_FROM_CAMPAIGN_DESCRIPTION]" not in box["text"]


def test_consent_copy_default_template_never_placeholders():
    copy = cfb.resolve_consent_copy({}, {})
    assert copy["source"] == "default_template"
    for box in copy["boxes"]:
        assert "[BUSINESS NAME]" not in box["text"]
        assert "[USE_CASE_FROM_CAMPAIGN_DESCRIPTION]" not in box["text"]
        assert "Message and data rates may apply" in box["text"]
        assert "Reply STOP to opt out" in box["text"]
        assert box["default_unchecked"] is True
        assert box["required"] is False

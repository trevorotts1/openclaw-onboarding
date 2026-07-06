#!/usr/bin/env python3
"""Redaction and secrecy tests (design Section 7.3)."""
from __future__ import annotations

from field_layer import redact


def test_registered_secret_is_scrubbed():
    r = redact.Redactor()
    r.register("pit-superSecretToken123")
    out = r.redact("failed with pit-superSecretToken123 in the body")
    assert "pit-superSecretToken123" not in out
    assert "[REDACTED]" in out


def test_short_values_not_registered():
    r = redact.Redactor()
    r.register("abc")  # too short to register
    assert r.redact("abc def") == "abc def"


def test_authorization_header_is_masked():
    r = redact.Redactor()
    r.register("pit-token-value-abcdef")
    safe = r.scrub_headers({
        "Authorization": "Bearer pit-token-value-abcdef",
        "Version": "2021-07-28",
    })
    assert safe["Authorization"] == "Bearer [REDACTED]"
    assert safe["Version"] == "2021-07-28"


def test_prefix_ok_and_safe_len():
    assert redact.prefix_ok("pit-abc") is True
    assert redact.prefix_ok("nope-abc") is False
    assert redact.prefix_ok(None) is False
    assert redact.safe_len("pit-abcdef") == 10
    assert redact.safe_len(None) == 0


def test_build_auth_header_shape():
    header = redact.build_auth_header("pit-xyz")
    assert header["Authorization"] == "Bearer pit-xyz"
    assert "Version" in header and "Content-Type" in header

"""Deterministic L1 tests for the interest popup (doc 16 s.1, doc 07 s.4)."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN = os.path.abspath(os.path.join(HERE, "..", ".."))
POPUP_DIR = os.path.join(DESIGN, "interest_popup")


def _load(name, *relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(DESIGN, *relpath))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


popup = _load("sl_interest_popup", "interest_popup", "interest_popup.py")

CONSENT = [
    {"id": "email", "text": "Email me the details.", "required": True},
    {"id": "sms", "text": "Text me the details.", "required": True},
]
CONFIG = {"heading": "Save your seat", "consent_statements": CONSENT}
CARD_TOKENS = (
    "card_number", "cardnumber", "ccnum", "cc_number", "cvc", "cvv",
    "credit_card", "creditcard", "exp_month", "exp_year",
)


def _input_names(html_text):
    return re.findall(r'<input[^>]* name="([^"]+)"', html_text)


class RenderedFieldSet(unittest.TestCase):
    def setUp(self):
        self.html = popup.render_interest_popup(CONFIG)

    def test_field_set_is_exactly_the_four_fields(self):
        names = _input_names(self.html)
        visitor = [n for n in names if not n.startswith("consent_")]
        self.assertEqual(
            visitor, ["first_name", "last_name", "email", "phone"]
        )
        self.assertEqual(set(popup.POPUP_FIELDS), set(visitor))

    def test_no_card_fields_anywhere(self):
        with open(os.path.join(POPUP_DIR, "interest_popup.js"), encoding="utf-8") as fh:
            js = fh.read()
        for token in CARD_TOKENS:
            self.assertNotIn(token, self.html.lower())
            self.assertNotIn(token, js.lower())
        # No input carries a payment-flavored name or type either.
        for name in _input_names(self.html):
            self.assertNotIn("card", name)
            self.assertNotIn("pay", name)

    def test_labels_autocomplete_and_close_control(self):
        for field, autocomplete in (
            ("first_name", "given-name"),
            ("last_name", "family-name"),
            ("email", "email"),
            ("phone", "tel"),
        ):
            self.assertIn('name="%s"' % field, self.html)
            self.assertIn('autocomplete="%s"' % autocomplete, self.html)
            self.assertIn('for="sl-interest-%s"' % field, self.html)
        self.assertIn("data-sl-popup-close", self.html)
        self.assertIn('aria-label="Close"', self.html)
        self.assertIn('role="dialog"', self.html)

    def test_consent_boxes_unchecked_and_required(self):
        self.assertNotIn("checked", self.html)
        consent_inputs = [
            tag for tag in re.findall(r"<input[^>]*>", self.html)
            if 'name="consent_' in tag
        ]
        self.assertEqual(len(consent_inputs), 2)
        for tag in consent_inputs:
            self.assertIn("required", tag)
        # The statement text IS the checkbox label text.
        self.assertIn("Email me the details.", self.html)


class CaptureContract(unittest.TestCase):
    def test_valid_capture_shape(self):
        payload = popup.build_interest_capture(
            {
                "first_name": "Ada",
                "last_name": "Example",
                "email": "ada@example.com",
                "phone": "+15551234567",
            },
            {"email": True, "sms": True},
            CONSENT,
        )
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["validation_errors"], [])
        self.assertEqual(
            payload["fields"],
            {
                "first_name": "Ada",
                "last_name": "Example",
                "email": "ada@example.com",
                "phone": "+15551234567",
            },
        )
        self.assertEqual(
            payload["native_field_map"],
            {
                "first_name": "first_name",
                "last_name": "last_name",
                "email": "email",
                "phone": "phone",
            },
        )
        self.assertEqual(payload["consent"], {"email": True, "sms": True})

    def test_missing_field_and_unchecked_consent_are_invalid(self):
        payload = popup.build_interest_capture(
            {"first_name": "Ada", "last_name": "", "email": "ada@example.com",
             "phone": ""},
            {"email": True, "sms": False},
            CONSENT,
        )
        self.assertFalse(payload["valid"])
        self.assertTrue(any("Last name" in e for e in payload["validation_errors"]))
        self.assertTrue(any("Phone" in e for e in payload["validation_errors"]))
        self.assertTrue(any("sms" in e for e in payload["validation_errors"]))

    def test_bad_email_is_invalid(self):
        payload = popup.build_interest_capture(
            {"first_name": "A", "last_name": "B", "email": "not-an-email",
             "phone": "123"},
            {"email": True, "sms": True},
            CONSENT,
        )
        self.assertFalse(payload["valid"])

    def test_trailing_or_leading_at_email_is_invalid(self):
        # The canonical rule the JS must mirror exactly: a present
        # email with no "@", a leading "@", or a trailing "@" is
        # invalid. ("a@" passed the old JS check; it must not pass.)
        for bad in ("a@", "@example.com", "not-an-email"):
            payload = popup.build_interest_capture(
                {"first_name": "A", "last_name": "B", "email": bad,
                 "phone": "123"},
                {"email": True, "sms": True},
                CONSENT,
            )
            self.assertFalse(payload["valid"], bad)
            self.assertTrue(
                any("email" in e.lower() for e in payload["validation_errors"]),
                bad,
            )

    def test_minimal_email_shape_is_accepted(self):
        payload = popup.build_interest_capture(
            {"first_name": "A", "last_name": "B", "email": "a@b",
             "phone": "123"},
            {"email": True, "sms": True},
            CONSENT,
        )
        self.assertTrue(payload["valid"])


class EscapingAndSeam(unittest.TestCase):
    def test_interpolated_copy_is_escaped(self):
        html_text = popup.render_interest_popup(
            {"heading": "<script>alert(1)</script>", "consent_statements": []}
        )
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_text)
        self.assertNotIn("<script>alert(1)</script>", html_text)

    def test_js_emits_event_and_invents_no_endpoint(self):
        with open(os.path.join(POPUP_DIR, "interest_popup.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("sl:interest-capture", js)
        self.assertIn("markVerified", js)
        self.assertIn("markFailed", js)
        self.assertNotIn("fetch(", js)
        self.assertNotIn("XMLHttpRequest", js)
        self.assertNotIn("http://", js)
        self.assertNotIn("https://", js)


def _js_source():
    with open(os.path.join(POPUP_DIR, "interest_popup.js"), encoding="utf-8") as fh:
        return fh.read()


def _js_payload_top_level_keys(js):
    """Top-level keys of the `var payload = { ... }` object literal."""
    start = js.index("var payload = {")
    i = js.index("{", start)
    depth = 0
    keys = []
    j = i
    while j < len(js):
        ch = js[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        elif depth == 1 and (ch.isalpha() or ch == "_"):
            m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", js[j:])
            if m:
                keys.append(m.group(1))
                j += m.end()
                continue
        j += 1
    return keys


class JsContractParity(unittest.TestCase):
    """The JS is the browser twin of the canonical Python contract;
    these tests pin the two to the same shape (review defect D1)."""

    def test_js_payload_field_set_equals_python_payload(self):
        python_payload = popup.build_interest_capture(
            {"first_name": "Ada", "last_name": "Example",
             "email": "ada@example.com", "phone": "+15551234567"},
            {"email": True, "sms": True},
            CONSENT,
        )
        js_keys = _js_payload_top_level_keys(_js_source())
        self.assertEqual(set(js_keys), set(python_payload.keys()))
        self.assertIn("component_version", js_keys)

    def test_js_field_list_equals_python_fields(self):
        m = re.search(r"var FIELDS = \[([^\]]*)\]", _js_source())
        self.assertIsNotNone(m)
        js_fields = re.findall(r'"([^"]+)"', m.group(1))
        self.assertEqual(js_fields, list(popup.POPUP_FIELDS))

    def test_js_version_constant_matches_python(self):
        js = _js_source()
        m = re.search(r'var COMPONENT_VERSION = "([^"]+)"', js)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), popup.COMPONENT_VERSION)


@unittest.skipUnless(shutil.which("node"), "node executable not available")
class JsBehaviorWithNode(unittest.TestCase):
    """Executes the real interest_popup.js under Node against a DOM
    stub (tests/js_harness.js): payload shape incl. component_version,
    trailing-@ rejection, validation-vs-send error copy, and the
    duplicate-submit guard. Skipped where Node is unavailable; the
    structural parity tests above still run."""

    def test_js_behavior_end_to_end(self):
        proc = subprocess.run(
            [
                shutil.which("node"),
                os.path.join(POPUP_DIR, "tests", "js_harness.js"),
                os.path.join(POPUP_DIR, "interest_popup.js"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        results = json.loads(proc.stdout.strip().splitlines()[-1])
        failed = [name for name, ok in results["checks"].items() if not ok]
        self.assertEqual(failed, [], results)


class SharedStyles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(DESIGN, "design.css"), encoding="utf-8") as fh:
            cls.css = fh.read()

    def test_focus_state_is_styled_with_accent_token(self):
        # Doc 16 s.5 names the focus state (review defect D3).
        self.assertRegex(
            self.css,
            r":focus[^{]*\{[^}]*outline:[^;}]*var\(--sl-color-accent",
        )

    def test_error_color_is_token_driven(self):
        # Review defect D5: literal allowed only as the var() fallback.
        self.assertRegex(
            self.css,
            r"\.sl-popup-error\s*\{[^}]*color:\s*var\(--sl-color-error,\s*#b00020\)",
        )

    def test_scrim_is_token_driven(self):
        self.assertRegex(
            self.css,
            r"\.sl-popup-overlay\s*\{[^}]*background:\s*var\(--sl-color-scrim,\s*rgba\(0, 0, 0, 0\.55\)\)",
        )


if __name__ == "__main__":
    unittest.main()

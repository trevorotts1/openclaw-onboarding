"""Tests for the S82-09 semantic pitch PRE-SCREEN (scripts/semantic_scan.py).

Two required cases:

1. The honest fixture render (scripts/render_thank_you.py output on
   fixtures/test-only-order-view.json with the TEST ONLY brand) must
   produce NO flags and exit 0 — purchased names, amounts, and totals
   inside the order summary are required content, not a pitch.
2. A tampered render carrying an upsell paragraph (urgency, "one more
   thing", "upgrade", percentage-off, price pressure, "don't miss")
   must be flagged with named reasons and exit 1.

The scanner is a pre-screen for the independent semantic review
(references/semantic-review-protocol.md); these tests prove the
pre-screen's behavior, not the review itself.

Stdlib unittest only. All data is TEST ONLY.
"""

import json
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from render_thank_you import render_thank_you  # noqa: E402
from semantic_scan import main as scan_main, scan_text  # noqa: E402


def _load_fixture(name):
    return json.loads((SKILL_DIR / "fixtures" / name).read_text())


def honest_render():
    view = _load_fixture("test-only-order-view.json")
    brand = _load_fixture("test-only-brand.json")
    return render_thank_you(view, brand)


UPSELL_PARAGRAPH = (
    "<p>One more thing before you go: upgrade to the VIP package today "
    "and save 50% off — only $49! Don't miss this limited time offer. "
    "Act now, before it's gone!</p>"
)


def tampered_render():
    html_out = honest_render()
    marker = "</section>"
    idx = html_out.rfind(marker)
    return html_out[:idx] + UPSELL_PARAGRAPH + html_out[idx:]


class SemanticScanTest(unittest.TestCase):
    def test_honest_fixture_render_is_clean(self):
        html_out = honest_render()
        # Sanity: the render really carries purchased amounts inside
        # the order summary — the scanner must not treat them (or the
        # word "only" in access copy) as pitch pressure.
        self.assertIn("$97.00", html_out)
        self.assertIn("only what you purchased", html_out)
        self.assertEqual(scan_text(html_out), [])

    def test_honest_render_cli_exit_0(self):
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(
                "w", suffix=".html", delete=False) as fh:
            fh.write(honest_render())
            path = fh.name
        try:
            self.assertEqual(scan_main([path]), 0)
        finally:
            os.unlink(path)

    def test_tampered_render_with_upsell_paragraph_is_flagged(self):
        findings = scan_text(tampered_render())
        self.assertTrue(findings, "tampered render produced no flags")
        reasons = {f["reason"] for f in findings}
        self.assertIn("one_more_thing", reasons)
        self.assertIn("pitch_verb", reasons)          # upgrade / don't miss
        self.assertIn("percentage_off", reasons)      # save 50% off
        self.assertIn("urgency_scarcity", reasons)    # limited time / act now
        self.assertIn("price_pressure_outside_summary", reasons)  # only $49
        for finding in findings:
            self.assertTrue(finding["excerpt"])
            self.assertGreaterEqual(finding["line"], 1)

    def test_tampered_render_cli_exit_1(self):
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(
                "w", suffix=".html", delete=False) as fh:
            fh.write(tampered_render())
            path = fh.name
        try:
            self.assertEqual(scan_main([path]), 1)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()

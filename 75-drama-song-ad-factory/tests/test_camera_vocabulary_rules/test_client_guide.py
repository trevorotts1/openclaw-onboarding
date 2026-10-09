"""DEL-16 client-guide line and the client-facing text hygiene gates.

Three gates, all on the text this unit ships to a client:
  * the exact line is in the client guide;
  * that line is English and names no model and no tool;
  * client-facing documents render at twelve point or larger.

Run:  python3 tests/test_camera_vocabulary_rules/test_client_guide.py
stdlib only.
"""
import re
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "scripts"))

from camera_signatures.rules import (  # noqa: E402
    CLIENT_GUIDE_DRONE_LINE,
    MIN_CLIENT_PDF_POINT_SIZE,
)

GUIDE = SKILL / "references" / "CLIENT-GUIDE.md"

# Model names and tool names. A client-facing sentence may name none of
# them. Word-boundary matched, so "reveal" never trips on "veo".
MODEL_OR_TOOL_NAMES = (
    r"kling", r"veo", r"minimax", r"seedance", r"runway", r"sora",
    r"luma", r"openrouter", r"ollama", r"kie\.ai", r"claude", r"opus",
    r"sonnet", r"haiku", r"fable", r"deepseek", r"gemini", r"gpt",
    r"anthropic", r"openclaw", r"perplexity", r"ffmpeg", r"reportlab",
    r"python", r"pytest", r"github", r"curl", r"docker",
)
MODEL_TOOL_RE = re.compile(
    r"\b(?:%s)\b" % "|".join(MODEL_OR_TOOL_NAMES), re.IGNORECASE)

# Font sizes that appear in this guide as a rendered size. Below twelve
# point is a fail.
PT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*pt\b", re.IGNORECASE)
FONT_SIZE_RE = re.compile(
    r"font-?size\s*[:=]\s*[\"']?(\d+(?:\.\d+)?)", re.IGNORECASE)


class TheExactLine(unittest.TestCase):
    def test_the_constant_is_the_ordered_sentence(self):
        self.assertEqual(
            CLIENT_GUIDE_DRONE_LINE,
            "Your video can open with a sweeping drone fly-in.")

    def test_the_client_guide_contains_that_exact_line(self):
        text = GUIDE.read_text(encoding="utf-8")
        self.assertIn(CLIENT_GUIDE_DRONE_LINE, text)

    def test_the_line_stands_as_its_own_line(self):
        lines = GUIDE.read_text(encoding="utf-8").splitlines()
        self.assertIn(CLIENT_GUIDE_DRONE_LINE, lines)

    def test_the_line_appears_exactly_once(self):
        text = GUIDE.read_text(encoding="utf-8")
        self.assertEqual(text.count(CLIENT_GUIDE_DRONE_LINE), 1)

    def test_the_line_ends_with_a_full_stop(self):
        self.assertTrue(CLIENT_GUIDE_DRONE_LINE.endswith("."))


class EnglishOnly(unittest.TestCase):
    def test_the_line_is_ascii_english(self):
        self.assertTrue(CLIENT_GUIDE_DRONE_LINE.isascii())
        self.assertTrue(
            all(ord(c) < 128 for c in CLIENT_GUIDE_DRONE_LINE))

    def test_the_line_has_no_cjk_or_fullwidth_characters(self):
        for c in CLIENT_GUIDE_DRONE_LINE:
            code = ord(c)
            self.assertFalse(0x3000 <= code <= 0x9FFF, repr(c))
            self.assertFalse(0xFF00 <= code <= 0xFFEF, repr(c))

    def test_the_line_is_a_sentence_not_a_slug(self):
        self.assertIn(" ", CLIENT_GUIDE_DRONE_LINE)
        self.assertNotIn("_", CLIENT_GUIDE_DRONE_LINE)


class NoModelOrToolNames(unittest.TestCase):
    def test_the_line_names_no_model_and_no_tool(self):
        hit = MODEL_TOOL_RE.search(CLIENT_GUIDE_DRONE_LINE)
        self.assertIsNone(hit, hit.group(0) if hit else "")

    def test_the_deny_list_is_not_empty(self):
        self.assertTrue(MODEL_OR_TOOL_NAMES)
        # control: the matcher must actually bite
        self.assertIsNotNone(MODEL_TOOL_RE.search("built with Kling"))
        self.assertIsNotNone(MODEL_TOOL_RE.search("on Veo"))
        # and must not bite on an ordinary English word
        self.assertIsNone(MODEL_TOOL_RE.search("a wide reveal of the street"))

    def test_the_line_has_no_model_or_tool_name_anywhere_in_it(self):
        # control pair: the matcher bites on a vendor word and stays quiet
        # on an ordinary English word that merely looks like one
        self.assertIsNotNone(MODEL_TOOL_RE.search(CLIENT_GUIDE_DRONE_LINE
                                                 .replace("drone", "kling")))
        self.assertIsNone(MODEL_TOOL_RE.search(CLIENT_GUIDE_DRONE_LINE))


class TwelvePointFloor(unittest.TestCase):
    def test_the_floor_constant_is_twelve(self):
        self.assertEqual(MIN_CLIENT_PDF_POINT_SIZE, 12)
        self.assertGreaterEqual(MIN_CLIENT_PDF_POINT_SIZE, 12)

    def test_no_smaller_point_size_is_declared_in_the_client_guide(self):
        text = GUIDE.read_text(encoding="utf-8")
        for rx, label in ((PT_RE, "pt"), (FONT_SIZE_RE, "font-size")):
            for m in rx.finditer(text):
                self.assertGreaterEqual(
                    float(m.group(1)), MIN_CLIENT_PDF_POINT_SIZE,
                    "%s %s below the twelve point floor"
                    % (m.group(1), label))

    def test_the_control_size_would_be_judged(self):
        # control: the scanner really sees a declared point size, and the
        # floor -- not a silent pattern miss -- is what rejects a small one
        nine = PT_RE.search("body { font-size: 9pt }")
        self.assertIsNotNone(nine)
        self.assertLess(float(nine.group(1)), MIN_CLIENT_PDF_POINT_SIZE)
        twelve = PT_RE.search("body { font-size: 12pt }")
        self.assertIsNotNone(twelve)
        self.assertGreaterEqual(
            float(twelve.group(1)), MIN_CLIENT_PDF_POINT_SIZE)
        self.assertGreaterEqual(
            float(FONT_SIZE_RE.search("body { font-size: 14 }").group(1)),
            MIN_CLIENT_PDF_POINT_SIZE)


if __name__ == "__main__":
    unittest.main()

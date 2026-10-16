"""Authoring-model freedom policy gate (MG-002 policy, MG-043 test).

Directive T02 requires two things: renders succeed locally with no LLM
credential, and no document mandates an authoring vendor. The first half
is exercised continuously by the render suites (T04/T05 run in this
environment with no authoring-model credential present). This test
guards the second half mechanically:

- SKILL.md and INSTRUCTIONS.md carry the freedom rule: the client
  selects the model or their configured default applies, and a
  recommendation is guidance only, never a hidden prescription.
- None of the governing documents (SKILL.md, INSTRUCTIONS.md,
  references/renderer-routing.md) contains mandate language: a required,
  prescribed, or banned authoring model or vendor.

The mandate predicate is deliberately narrow and is proven below against
synthetic good and bad text, so the gate's own behavior is tested, not
just the documents' current wording.

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]

GOVERNING_DOCS = [
    SKILL_ROOT / "SKILL.md",
    SKILL_ROOT / "INSTRUCTIONS.md",
    SKILL_ROOT / "references" / "renderer-routing.md",
]

FREEDOM_MARKERS = [
    "configured default",
    "guidance only",
]

VENDOR_WORDS = (
    r"(?:claude|gpt|gemini|sonnet|opus|haiku|deepseek|llama|mistral|"
    r"openai|anthropic|google|openrouter|ollama)"
)

MANDATE_PATTERNS = [
    re.compile(r"authoring model\s+(?:must|shall|is required)", re.IGNORECASE),
    re.compile(r"(?:must|shall|always)\s+(?:use|author\s+with)\s+(?:the\s+)?" + VENDOR_WORDS, re.IGNORECASE),
    re.compile(r"required\s+(?:authoring\s+)?model\s*[:=]", re.IGNORECASE),
    re.compile(r"prescribed\s+model\s*[:=]", re.IGNORECASE),
    re.compile(r"default\s+(?:authoring\s+)?model\s+is\s+(?:the\s+)?" + VENDOR_WORDS, re.IGNORECASE),
    re.compile(VENDOR_WORDS + r"\s+is\s+(?:banned|forbidden|prohibited)", re.IGNORECASE),
]

NEGATION_PATTERN = re.compile(
    r"(?:never|no\s+model\s+vendor|none\s+is|not\s+(?:banned|required|prescribed)|"
    r"is\s+banned\s+or\s+required|banned\s+or\s+required)",
    re.IGNORECASE,
)


def find_mandates(text: str) -> list[str]:
    """Return the lines of text that mandate an authoring model/vendor."""
    hits: list[str] = []
    for line in text.splitlines():
        if NEGATION_PATTERN.search(line):
            continue
        for pattern in MANDATE_PATTERNS:
            if pattern.search(line):
                hits.append(line.strip())
                break
    return hits


class MandatePredicateTests(unittest.TestCase):
    def test_flags_a_required_vendor(self):
        bad = "All scene code must use Claude for authoring.\n"
        self.assertEqual(len(find_mandates(bad)), 1)

    def test_flags_a_required_authoring_model(self):
        bad = "The authoring model must be set before intake.\n"
        self.assertEqual(len(find_mandates(bad)), 1)

    def test_flags_a_banned_vendor(self):
        bad = "Anthropic is banned for scene authoring.\n"
        self.assertEqual(len(find_mandates(bad)), 1)

    def test_accepts_freedom_language(self):
        good = (
            "This skill never prescribes which model writes the animation code, and no\n"
            "model vendor is banned or required. The client selected the model or their\n"
            "configured default applies; a recommendation is guidance only.\n"
        )
        self.assertEqual(find_mandates(good), [])


class GoverningDocumentTests(unittest.TestCase):
    def test_freedom_rule_present_in_skill_and_instructions(self):
        for doc in (SKILL_ROOT / "SKILL.md", SKILL_ROOT / "INSTRUCTIONS.md"):
            # Whitespace-normalized: the rule's wording may wrap lines.
            text = re.sub(r"\s+", " ", doc.read_text(encoding="utf-8"))
            for marker in FREEDOM_MARKERS:
                self.assertIn(
                    marker,
                    text,
                    f"{doc.name} must carry the authoring-model freedom marker {marker!r}",
                )

    def test_no_mandate_language_in_governing_documents(self):
        for doc in GOVERNING_DOCS:
            hits = find_mandates(doc.read_text(encoding="utf-8"))
            self.assertEqual(hits, [], f"{doc.name} contains mandate language: {hits}")


if __name__ == "__main__":
    unittest.main()

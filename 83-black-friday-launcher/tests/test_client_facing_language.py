"""The words the client reads stay plain, warm and free of the launcher's inside vocabulary.

A client's agent once described this skill as "validates the intake behind an entitlement gate, builds the
route graph, maps the checkout contract ...". The client is a non-technical business owner. SKILL.md now
carries the opening and the other client moments between CLIENT-TEXT markers, and the list of banned words
between BANNED-WORDS markers. This guard fails when any banned word (or a version number) appears in the
client text, in the description the skill list shows, in the client summary, or in skill.json's description.

Stdlib only: python3 -m unittest.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT))

SKILL_MD = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

# The least the list in SKILL.md must always ban (the owner's own list). SKILL.md may ban more.
MUST_BAN = ("route graph", "entitlement", "gate", "gated", "intake", "validate", "contract", "manifest", "dispatch",
            "schema", "jsonschema", "python", "prereq", "exit code", "completeness check",
            "Council planning step", "7FigurePreneur shape", "hashed", "receipt")
VERSION_NUMBER = re.compile(r"\bv\d+(\.\d+)+\b|\b\d+\.\d+\.\d+\b", re.IGNORECASE)
REQUIRED_MOMENTS = ("opening", "missing-offer", "missing-price", "missing-product", "advisors",
                    "plan-review", "finished", "ready", "technical-problem")


def banned_words(text: str) -> list:
    block = re.search(r"<!-- BANNED-WORDS:BEGIN -->(.*?)<!-- BANNED-WORDS:END -->", text, re.S)
    assert block, "SKILL.md has no BANNED-WORDS block"
    return [line[2:].strip() for line in block.group(1).splitlines() if line.startswith("- ")]


def client_text(text: str) -> dict:
    return {name: body.strip() for name, body in
            re.findall(r"<!-- CLIENT-TEXT:BEGIN ([\w-]+) -->(.*?)<!-- CLIENT-TEXT:END -->", text, re.S)}


def _pattern(term: str) -> re.Pattern:
    """A word, a plural or a longer form of it: 'validate' also catches validates and validation."""
    *head, last = term.split()
    if len(last) <= 4:                       # gate, pip, hash: only the word or its plural
        tail = re.escape(last) + r"(?:s|es)?\b"
    else:                                    # intake, dispatch, dependency: any longer form
        tail = re.escape(last[:-1] if last[-1] in "ey" and len(last) > 6 else last) + r"\w*"
    return re.compile(r"\b" + r"\s+".join([re.escape(w) for w in head] + [tail]), re.IGNORECASE)


def violations(text: str, terms: list) -> list:
    found = [t for t in terms if _pattern(t).search(text)]
    if VERSION_NUMBER.search(text):
        found.append("a version number")
    return found


# Where else an agent reads about this skill and repeats it to the client: the funnel-engine registry summary
# (06-ghl-install-pages) and the department map description, whose first sentence
# 23-ai-workforce-blueprint/scripts/stamp-dept-skill-guides.py stamps into the owner-facing
# how-to-use-this-department.md guides.
REGISTRY = REPO_ROOT / "06-ghl-install-pages" / "funnel-engines" / "registry.json"
DEPT_MAP = REPO_ROOT / "23-ai-workforce-blueprint" / "skill-department-map.json"
DEPT_MAP_ENTRY = SKILL_ROOT / "repo-integration" / "skill-department-map-entry.json"
STAMPER = REPO_ROOT / "23-ai-workforce-blueprint" / "scripts" / "stamp-dept-skill-guides.py"
GUIDES = tuple(REPO_ROOT / "23-ai-workforce-blueprint" / "templates" / "role-library" / dept / "how-to-use-this-department.md"
               for dept in ("marketing", "web-development", "funnels"))
TRIGGER = '"build my black friday launch"'


def registry_summary(registry_path: Path = REGISTRY) -> str:
    engines = json.loads(registry_path.read_text(encoding="utf-8"))["engines"]
    return next(e for e in engines if e["id"] == "black-friday-launcher")["summary"]


def first_sentence(description: str) -> str:
    """The text the guide stamper keeps from a map description (its own function, so the guard cannot drift)."""
    spec = importlib.util.spec_from_file_location("stamp_dept_skill_guides", STAMPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._first_sentence(description)


def map_description(map_path: Path) -> str:
    data = json.loads(map_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("slug") == "black-friday-launcher":
        return data["description"]
    return next(e for e in data["skills"] if e.get("slug") == "black-friday-launcher")["description"]


def frontmatter(text: str) -> dict:
    block = re.match(r"---\n(.*?)\n---\n", text, re.S).group(1)
    return {m.group(1): json.loads(m.group(2)) for m in re.finditer(r'^(description|client_summary): ("(?:[^"\\]|\\.)*")$',
                                                                   block, re.M)}


class ClientFacingLanguage(unittest.TestCase):
    def test_the_banned_list_covers_the_owners_list(self):
        listed = {t.lower() for t in banned_words(SKILL_MD)}
        self.assertEqual([t for t in MUST_BAN if t.lower() not in listed], [])

    def test_every_client_moment_is_present_and_free_of_banned_words(self):
        moments, terms = client_text(SKILL_MD), banned_words(SKILL_MD)
        self.assertEqual([m for m in REQUIRED_MOMENTS if m not in moments], [])
        for name, body in moments.items():
            self.assertEqual(violations(body, terms), [], f"client text '{name}'")

    def test_the_opening_is_the_warm_guide_the_owner_asked_for(self):
        opening = client_text(SKILL_MD)["opening"]
        for needed in ("I'm so glad you're here", "sales page", "order form", "add-on", "one-time offers",
                       "thank-you page", "launch emails and text messages", "look over",
                       "one at a time", "no wrong answers", "just tell me and I'll help you figure it out",
                       "sit back and relax", "What would you like to sell this Black Friday?"):
            self.assertIn(needed, opening)
        self.assertEqual(opening.count("?"), 1, "the opening ends with exactly one question")
        self.assertTrue(opening.endswith("What would you like to sell this Black Friday?"))

    def test_the_missing_offer_line_asks_kindly_and_never_says_no_records(self):
        moments = client_text(SKILL_MD)
        self.assertIn("what you'd like to sell and the price", moments["missing-offer"])
        for body in moments.values():
            self.assertNotIn("records on file", body.lower())

    def test_the_text_the_skill_list_and_agents_repeat_is_plain(self):
        terms = banned_words(SKILL_MD)
        front = frontmatter(SKILL_MD)
        self.assertEqual(sorted(front), ["client_summary", "description"])
        skill_json = json.loads((SKILL_ROOT / "skill.json").read_text(encoding="utf-8"))
        for where, text in (("SKILL.md description", front["description"]),
                            ("SKILL.md client_summary", front["client_summary"]),
                            ("skill.json description", skill_json["description"])):
            self.assertEqual(violations(text, terms), [], where)

    def test_the_technical_description_lives_only_in_the_operator_section(self):
        head, _, tail = SKILL_MD.partition("## Operator reference (NEVER read")
        self.assertTrue(tail, "SKILL.md has no operator-only section")
        self.assertIn("route graph", tail)
        self.assertNotIn("Technical description (operator only)", head)

    def test_the_banned_list_names_the_forms_a_word_stem_misses(self):
        listed = {t.lower() for t in banned_words(SKILL_MD)}
        self.assertLessEqual({"gated", "hashed"}, listed)
        terms = banned_words(SKILL_MD)
        for bad in ("The order form is gated behind a test.", "Every file is hashed first."):
            self.assertTrue(violations(bad, terms), bad)

    def test_the_funnel_registry_summary_is_plain_and_does_not_promise_a_live_order_form(self):
        if not REGISTRY.is_file():
            self.skipTest("Skill 06 is not beside this skill (vendored copy)")
        terms = banned_words(SKILL_MD)
        summary = registry_summary()
        self.assertEqual(violations(summary, terms), [], "funnel-engines/registry.json summary")
        # Skill 06 cannot put the order form and one-click offers live before the live capture (CHK-19):
        # the summary must say drafts, never promise them delivered.
        self.assertIn("drafts", summary)
        self.assertIn("not happened yet", summary)
        engine = next(e for e in json.loads(REGISTRY.read_text(encoding="utf-8"))["engines"]
                      if e["id"] == "black-friday-launcher")
        self.assertIn("CHK-19", engine["delivery_delegation"])
        self.assertIn("CHK-19", engine["entry_contract"])
        readme = (REGISTRY.parent / "README.md").read_text(encoding="utf-8")
        row = next(line for line in readme.splitlines() if line.startswith("| `black-friday-launcher` |"))
        self.assertEqual(violations(row.split("|")[3], terms), [], "funnel-engines/README.md row")
        self.assertIn("CHK-19", row)

    def test_the_department_map_sentence_the_owner_guides_repeat_is_plain(self):
        if not STAMPER.is_file():
            self.skipTest("the department guide stamper is not beside this skill (vendored copy)")
        terms = banned_words(SKILL_MD)
        for where, path in (("skill-department-map.json", DEPT_MAP), ("skill-department-map-entry.json", DEPT_MAP_ENTRY)):
            sentence = first_sentence(map_description(path))
            self.assertEqual(violations(sentence, terms), [], where)
            self.assertIn("Black Friday", sentence)
            self.assertGreater(len(sentence.split()), 12, f"{where}: the stamper cut the sentence short: {sentence!r}")
            # Issue 75: the operator-detail sentences after the first are read by agents too, so every
            # sentence is held to the same banned words, not only the one the stamper keeps.
            for each in re.split(r"(?<=[.!?])\s+", map_description(path)):
                self.assertEqual(violations(each, terms), [], f"{where}: {each[:80]!r}")
        self.assertEqual(map_description(DEPT_MAP), map_description(DEPT_MAP_ENTRY), "the entry mirrors the map")
        stamped = 0
        for guide in GUIDES:
            for line in guide.read_text(encoding="utf-8").splitlines():
                if TRIGGER in line:
                    stamped += 1
                    self.assertEqual(violations(line.split("|")[2], terms), [], str(guide.relative_to(REPO_ROOT)))
        self.assertEqual(stamped, len(GUIDES), "each department guide carries the Skill 83 row")

    def test_no_copy_of_the_stale_department_map_description_survives_in_the_root_readme(self):
        # Issue 75: README.md repeats the map description; a stale copy anywhere in it must fail.
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        stale = [p for p in ("entitlement attestation", "entitlement gate", "School of AI alone does not",
                             "delivery-blocked until Skill 79")
                 if p.lower() in readme.lower()]
        self.assertEqual(stale, [], "README.md still carries the old Skill 83 description")
        row = next(line for line in readme.splitlines() if line.startswith("| 83-black-friday-launcher |"))
        self.assertIn("no membership question", row)
        self.assertIn("checkout mode is resolved", row)
        self.assertIn("no membership question", map_description(DEPT_MAP))

    def test_the_detector_catches_what_it_is_for(self):  # control: the guard is not always green
        terms = banned_words(SKILL_MD)
        for bad in ("I will validate your intake first.", "We build the route graph.",
                    "Your python needs a package.", "Version v0.2.14 is ready.", "It passed with exit code 0.",
                    "Running the completeness checks now.", "The 7FigurePreneur shape is ready.",
                    "Composes the separate page skills into one runtime walk behind an entitlement gate.",
                    "An assembled package with a manifest and receipt.", "The route graph and Council planning step."):
            self.assertTrue(violations(bad, terms), bad)
        self.assertEqual(violations("Hi! What would you like to sell this Black Friday?", terms), [])


if __name__ == "__main__":
    unittest.main()

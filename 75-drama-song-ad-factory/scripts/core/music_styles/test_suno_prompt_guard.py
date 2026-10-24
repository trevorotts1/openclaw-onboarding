#!/usr/bin/env python3
"""S75-T41 / S75-A41: the outgoing-prompt guard, proved on all eighteen styles.

Dual-mode:  python3 scripts/core/music_styles/test_suno_prompt_guard.py
            python3 -m pytest scripts/core/music_styles/test_suno_prompt_guard.py

Zero provider calls, zero network, zero credential reads: every payload here is
a synthetic createTask envelope and every "send" is a local dict.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from music_styles import prompt_compiler as PC          # noqa: E402
from music_styles import suno_prompt_guard as G          # noqa: E402

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
FIXTURE = os.path.join(SKILL_ROOT, "tests", "fixtures",
                       "suno_artist_reference_guard.json")

STYLE_IDS = (
    "soul-ballad", "rnb-flow", "soul-rise", "acoustic-pop",
    "folk-storytelling", "country-pop", "melodic-rap", "trap-rap",
    "pop-rap", "pop-rock", "reggaeton", "cinematic-orchestral-song",
    "musical-theater", "contemporary-gospel", "urban-gospel",
    "alternative-rnb", "afro-soul", "country-rap",
)

APPROVED_LYRICS = (
    "[Spoken] The shop lights go down.\n"
    "[Sung] One honest call is all I need to make."
)


def load_catalog():
    with open(FIXTURE, encoding="utf-8") as handle:
        return json.load(handle)


def style_field(catalog, style_id):
    return PC.compile_from_catalog(catalog, style_id)


def envelope(catalog, style_id, **overrides):
    """A synthetic createTask envelope -- exactly the fields the adapter sends."""
    inp = {
        "custom_mode": True,
        "instrumental": False,
        "model": "V6",
        "title": "One Honest Call",
        "style": style_field(catalog, style_id),
        "lyrics": APPROVED_LYRICS,
        "negative_tags": ["reverb", "echo", "choir"],
        "duration": 120,
    }
    inp.update(overrides)
    inp = {k: v for k, v in inp.items() if v is not None}
    return {
        "endpoint": "/api/v1/jobs/createTask",
        "model": "ai-music-api/generate",
        "callBackUrl": "https://example.invalid/cb",
        "input": inp,
    }


def references(catalog):
    """Every display reference string in the catalog."""
    out = []
    for record in PC.catalog_records(catalog):
        refs = record.get("client_references") or {}
        out.extend(refs.get("artists") or [])
        out.extend(refs.get("reference_songs") or [])
        aliases = refs.get("aliases")
        if isinstance(aliases, dict):
            for artist, extra in aliases.items():
                out.append(artist)
                out.extend(extra or [])
        else:
            out.extend(aliases or [])
    return sorted(set(out))


def variants(name):
    """Case, apostrophe and punctuation spellings of one reference."""
    return [
        name,
        name.upper(),
        name.lower(),
        name + ".",
        name + "’s",
        name.replace(" ", "-"),
    ]


class CompilerContract(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()

    def test_catalog_has_exactly_eighteen_styles(self):
        ids = [r["style_id"] for r in PC.catalog_records(self.catalog)]
        self.assertEqual(sorted(ids), sorted(STYLE_IDS))

    def test_every_style_compiles_from_traits_only(self):
        aliases = G.alias_set(self.catalog)
        for style_id in STYLE_IDS:
            text = style_field(self.catalog, style_id)
            self.assertTrue(text.strip(), style_id)
            self.assertEqual(G.find_matches(text, aliases), [], style_id)

    def test_display_metadata_never_reaches_the_compiled_field(self):
        record = {
            "style_id": "x",
            "client_references": {"artists": ["Imaginary Leak Artist"]},
            "production_traits": {"instruments": "warm piano",
                                  "tempo": "70 bpm"},
        }
        compiled = PC.compile_style_field(record)
        self.assertEqual(compiled, "warm piano, 70 bpm")
        self.assertNotIn("Imaginary", compiled)
        self.assertEqual(PC.display_metadata(record),
                         {"artists": ["Imaginary Leak Artist"]})

    def test_missing_traits_fail_closed_and_never_fall_back_to_an_artist(self):
        record = {"style_id": "x",
                  "client_references": {"artists": ["Some Artist"]}}
        with self.assertRaises(PC.PromptCompileError) as ctx:
            PC.compile_style_field(record)
        self.assertEqual(ctx.exception.code, "MISSING_PRODUCTION_TRAITS")

    def test_reference_metadata_inside_traits_is_refused_not_filtered(self):
        record = {"style_id": "x",
                  "production_traits": {"instruments": "guitar",
                                        "artists": ["Some Artist"]}}
        with self.assertRaises(PC.PromptCompileError) as ctx:
            PC.compile_style_field(record)
        self.assertEqual(ctx.exception.code, "REFERENCE_IN_TRAITS")


class GuardContract(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.aliases = G.alias_set(self.catalog)

    def test_clean_payload_passes_byte_identical(self):
        payload = envelope(self.catalog, "soul-ballad")
        before = copy.deepcopy(payload)
        receipt = G.guard(payload, self.catalog)
        self.assertEqual(receipt["decision"], "PASS")
        self.assertTrue(receipt["sendable"])
        self.assertEqual(receipt["payload"], before)
        self.assertEqual(receipt["provider_calls"], 0)

    def test_client_metadata_key_in_payload_is_a_hard_block(self):
        payload = envelope(self.catalog, "pop-rap")
        payload["input"]["client_references"] = {
            "artists": ["Puff Daddy"]}
        receipt = G.guard(payload, self.catalog)
        self.assertEqual(receipt["decision"], "BLOCKED")
        self.assertFalse(receipt["sendable"])
        self.assertIsNone(receipt["payload"])
        self.assertEqual(receipt["blocked"][0]["reason"],
                         "CLIENT_METADATA_SERIALIZED")
        self.assertIn("input.client_references",
                      receipt["blocked"][0]["field"])

    def test_every_reference_is_removed_from_every_instruction_field(self):
        started = 0
        for style_id in STYLE_IDS:
            for name in references(self.catalog):
                for variant in variants(name):
                    for field in ("style", "title", "prompt"):
                        started += 1
                        payload = envelope(self.catalog, style_id)
                        payload["input"][field] = (
                            "%s, %s" % (payload["input"].get(field, "kept"),
                                        variant))
                        receipt = G.guard(payload, self.catalog)
                        self.assertTrue(
                            receipt["sendable"] or
                            any(b["reason"] == "MISSING_TRAITS"
                                for b in receipt["blocked"]),
                            (style_id, field, variant, receipt["blocked"]))
                        if receipt["sendable"]:
                            self.assertEqual(
                                G.find_matches(
                                    receipt["payload"]["input"][field],
                                    self.aliases), [],
                                (style_id, field, variant))
                            self.assertIn("input." + field,
                                          receipt["sanitized_fields"])
                        else:
                            self.assertEqual(receipt["provider_calls"], 0)
                            self.assertIsNone(receipt["payload"])
        self.assertGreater(started, 18 * len(references(self.catalog)))

    def test_every_reference_in_every_negative_tag_position_is_removed(self):
        for name in references(self.catalog):
            for variant in variants(name):
                payload = envelope(self.catalog, "trap-rap")
                payload["input"]["negative_tags"] = [
                    "reverb", variant, "echo"]
                receipt = G.guard(payload, self.catalog)
                self.assertTrue(receipt["sendable"], (name, receipt["blocked"]))
                self.assertEqual(receipt["payload"]["input"]["negative_tags"],
                                 ["reverb", "echo"])

    def test_every_reference_in_approved_lyrics_blocks_by_name(self):
        for style_id in STYLE_IDS:
            for name in references(self.catalog):
                payload = envelope(self.catalog, style_id)
                payload["input"]["lyrics"] = (
                    APPROVED_LYRICS + "\n[Sung] " + name)
                receipt = G.guard(payload, self.catalog)
                self.assertEqual(receipt["decision"], "BLOCKED",
                                 (style_id, name))
                self.assertFalse(receipt["sendable"])
                self.assertIsNone(receipt["payload"])
                self.assertEqual(receipt["provider_calls"], 0)
                fields = [b["field"] for b in receipt["blocked"]]
                self.assertIn("input.lyrics", fields)
                self.assertEqual(
                    [b["reason"] for b in receipt["blocked"]
                     if b["field"] == "input.lyrics"],
                    ["APPROVED_CONTENT_COLLISION"])

    def test_negative_reference_is_rewritten_into_the_remaining_traits(self):
        payload = envelope(self.catalog, "country-rap")
        payload["input"]["style"] = (
            payload["input"]["style"]
            + ", do not sound like Jelly Roll, keep the gritty soulful chorus")
        receipt = G.guard(payload, self.catalog)
        self.assertEqual(receipt["decision"], "SANITIZED")
        self.assertTrue(receipt["sendable"])
        style = receipt["payload"]["input"]["style"]
        self.assertNotIn("jelly", style.lower())
        self.assertIn("gritty soulful chorus", style)
        self.assertEqual(G.find_matches(style, self.aliases), [])

    def test_common_word_alias_in_approved_creative_content_blocks_untouched(self):
        lyrics = APPROVED_LYRICS + "\n[Spoken] The Future is not written yet."
        payload = envelope(self.catalog, "rnb-flow", lyrics=lyrics)
        receipt = G.guard(payload, self.catalog)
        self.assertEqual(receipt["decision"], "BLOCKED")
        self.assertIsNone(receipt["payload"])
        self.assertEqual(receipt["provider_calls"], 0)
        blocked = [b for b in receipt["blocked"]
                   if b["field"] == "input.lyrics"][0]
        self.assertIn("future", blocked["match"])
        self.assertEqual(blocked["reason"], "APPROVED_CONTENT_COLLISION")
        self.assertIn("review", blocked["resolution_owner"])
        self.assertEqual(
            receipt["preserved_approved_content_digest"]["fields"],
            {"input.lyrics": __import__("hashlib").sha256(
                lyrics.encode("utf-8")).hexdigest()})

    def test_case_unicode_and_punctuation_spellings_all_hit(self):
        spellings = (
            "CÉLINE DION",
            "Celine Dion’s",
            "celine dion.",
            "P. Diddy",
            "diddy",
            "JellyRoll",
            "jelly-roll",
            "ADELE’S",
            "Maroon 5",
            "missy elliott",
        )
        for spelling in spellings:
            payload = envelope(self.catalog, "cinematic-orchestral-song")
            payload["input"]["style"] = (
                payload["input"]["style"] + ", in the style of " + spelling)
            receipt = G.guard(payload, self.catalog)
            self.assertTrue(receipt["sendable"], spelling)
            self.assertEqual(
                G.find_matches(receipt["payload"]["input"]["style"],
                               self.aliases), [], spelling)

    def test_reference_song_titles_are_guarded_too(self):
        for song in ("Skyfall", "My Heart Will Go On"):
            payload = envelope(self.catalog, "cinematic-orchestral-song")
            payload["input"]["title"] = song
            receipt = G.guard(payload, self.catalog)
            self.assertTrue(receipt["sendable"], song)
            self.assertEqual(receipt["payload"]["input"]["title"], "")

    def test_nested_unknown_fields_are_traversed(self):
        payload = envelope(self.catalog, "pop-rap")
        payload["input"]["experimental"] = {"outer": {"style": "Puff Daddy"}}
        receipt = G.guard(payload, self.catalog)
        self.assertEqual(receipt["decision"], "SANITIZED")
        self.assertIn("input.experimental.outer.style",
                      receipt["sanitized_fields"])
        self.assertEqual(receipt["payload"]["input"]["experimental"],
                         {"outer": {"style": ""}})

    def test_receipt_binds_fields_alias_revision_and_digest(self):
        payload = envelope(self.catalog, "afro-soul")
        receipt = G.guard(payload, self.catalog)
        for field in ("input.style", "input.lyrics", "input.negative_tags.0",
                      "input.negative_tags.1", "input.negative_tags.2",
                      "input.title"):
            self.assertIn(field, receipt["inspected_fields"])
        self.assertEqual(len(receipt["alias_revision"]), 64)
        self.assertEqual(len(receipt["payload_digest"]), 64)
        self.assertEqual(receipt["alias_scope"].split(";")[0],
                         "catalog display references and their recorded aliases only")

    def test_sanitized_payload_keeps_approved_content_digest(self):
        clean = G.guard(envelope(self.catalog, "soul-rise"), self.catalog)
        payload = envelope(self.catalog, "soul-rise")
        payload["input"]["style"] += ", avoid Bill Withers phrasing"
        dirty = G.guard(payload, self.catalog)
        self.assertEqual(dirty["decision"], "SANITIZED")
        self.assertEqual(dirty["preserved_approved_content_digest"],
                         clean["preserved_approved_content_digest"])

    def test_guard_or_raise_names_field_and_match(self):
        payload = envelope(self.catalog, "country-rap",
                           lyrics=APPROVED_LYRICS + "\n[Sung] Jelly Roll")
        with self.assertRaises(G.PromptGuardError) as ctx:
            G.guard_or_raise(payload, self.catalog)
        self.assertEqual(ctx.exception.code, "OUTGOING_REFERENCE_BLOCKED")
        self.assertIn("input.lyrics", str(ctx.exception))
        self.assertIn("jelly roll", str(ctx.exception))

    def test_retry_reruns_the_guard_on_the_exact_final_payload(self):
        payload = envelope(self.catalog, "melodic-rap")
        first = G.guard(payload, self.catalog)
        again = G.guard(copy.deepcopy(payload), self.catalog)
        self.assertEqual(first["payload_digest"], again["payload_digest"])
        changed = copy.deepcopy(payload)
        changed["input"]["style"] += ", like Drake"
        third = G.guard(changed, self.catalog)
        self.assertEqual(third["decision"], "SANITIZED")
        self.assertNotEqual(third["payload_digest"], first["payload_digest"])

    def test_bare_reference_style_cannot_leave_an_empty_prompt(self):
        payload = envelope(self.catalog, "soul-ballad")
        payload["input"]["style"] = "Whitney Houston"
        receipt = G.guard(payload, self.catalog)
        self.assertEqual(receipt["decision"], "BLOCKED")
        self.assertEqual(receipt["blocked"][0]["reason"], "MISSING_TRAITS")
        self.assertIsNone(receipt["payload"])

    def test_guarded_send_makes_a_blocked_submission_zero_calls(self):
        sent = []

        def fake_send(text):
            sent.append(text)
            return "job-1"

        blocked = envelope(self.catalog, "musical-theater",
                           lyrics=APPROVED_LYRICS + "\n[Sung] Idina Menzel")
        with self.assertRaises(G.PromptGuardError):
            G.guarded_send(blocked, self.catalog, fake_send)
        self.assertEqual(sent, [])

        clean = envelope(self.catalog, "musical-theater")
        _, receipt = G.guarded_send(clean, self.catalog, fake_send)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0], clean)
        self.assertEqual(receipt["submitted_payload_digest"],
                         receipt["payload_digest"])


class Hygiene(unittest.TestCase):
    def test_modules_are_stdlib_only_and_never_touch_a_provider(self):
        forbidden = ("socket", "urllib", "requests", "http.client",
                     "subprocess", "api_key", "API_KEY", "Authorization",
                     "Bearer")
        for name in ("prompt_compiler.py", "suno_prompt_guard.py"):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                name)
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            for token in forbidden:
                self.assertNotIn(token, source, (name, token))


if __name__ == "__main__":
    unittest.main(verbosity=2)

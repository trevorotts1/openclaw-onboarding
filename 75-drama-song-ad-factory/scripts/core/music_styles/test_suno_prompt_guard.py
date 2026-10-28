#!/usr/bin/env python3
"""S75-T41 / S75-A41: the outgoing-prompt guard, proved on all eighteen styles.

Dual-mode:  python3 scripts/core/music_styles/test_suno_prompt_guard.py
            python3 -m pytest scripts/core/music_styles/test_suno_prompt_guard.py

Zero provider calls, zero network, zero credential reads: every payload here is
a synthetic createTask envelope and every "send" is a local dict.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
import unittest

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from music_styles import prompt_compiler as PC          # noqa: E402
from music_styles import suno_prompt_guard as G          # noqa: E402
from music_styles import catalog as C                    # noqa: E402
from suno_recipe import suno_recipe as R                 # noqa: E402

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

#: S75-T41 r8: a display block under the spellings a seventh writer would use.
RENAMED_DISPLAY_KEYS = (
    "artistReferences", "artist_references_v2", "Artist_References",
    "client_references_extra", "recognition_ref", "artist_names",
    "displayReference", "artist_reference",
)
DISPLAY_BLOCK = {"display_value": "Marisol Ferrer",
                 "display_note": "client asked for this exact sound"}

#: Approved sheets that carry an alias's WORDS with other material between
#: them.  They are prose, not references, and must dispatch byte-identical.
PROSE_SHEETS = (
    "the band was bad that night but the bunny hop encore stole the show",
    "the jelly sits on the plate while the whole room waits for it to roll",
    "my heart will always search for the one who will go on loving me",
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


def deep_merge(base, extra):
    """Overlay one fixture injection onto an envelope: dicts merge, rest replaces."""
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base

def approved_hashes(payload):
    """sha256 of every approved creative field, by path -- a hash, not a claim."""
    out = {}
    for path, text in G._walk_text(payload):
        if G.is_protected(path, G.DEFAULT_PROTECTED_PATHS):
            out[G._dot(path)] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return out

def references_left(payload, aliases):
    """Aliases still present anywhere in a payload: values AND keys, any depth."""
    found = {}
    for path, text in G._walk_text(payload):
        hits = G.find_matches(text, aliases)
        if hits:
            found[G._dot(path)] = hits
    for path, key in G._walk_keys(payload):
        hits = G.find_matches(str(key), aliases)
        if hits:
            found[G._dot(path)] = hits
    return found

class FixtureCases(unittest.TestCase):
    """The fixture's guard_cases, proved on all eighteen styles."""

    #: Clause 0 names these coverage dimensions.  A dimension is counted only
    #: when a case's INJECTED BYTES witness it; an id is a claim and is never
    #: the oracle.  A fixture whose cases are named but empty witnesses none.
    REQUIRED_DIMENSIONS = (
        "case-variant", "punctuation-variant",
        "key-position", "list-value", "instruction-value", "nested-position",
        "negative-key", "negative-list-value", "negative-instruction",
        "approved-content",
    )

    #: Words that make a scalar instruction a NEGATIVE reference, not a trait.
    NEGATION = re.compile(
        r"\b(?:do not|don't|does not|no|never|avoid|exclude|not in the style)\b",
        re.IGNORECASE)

    def setUp(self):
        self.catalog = load_catalog()
        self.aliases = G.alias_set(self.catalog)
        self.cases = self.catalog.get("guard_cases") or []

    def _forms_in(self, text):
        """The case and punctuation spellings actually written in one text.

        Derived from the catalogue's own display names, so a case that claims
        "case-variant" but injects the canonical spelling witnesses nothing.
        """
        case_variants, punctuation_variants = set(), set()
        for name in references(self.catalog):
            upper = name.upper()
            if upper != name and upper in text:
                case_variants.add(name)
            for spelling in (name + "’s", name + "'s",
                             name.replace(" ", "-"),
                             name.replace(" ", "")):
                if spelling != name and spelling in text:
                    punctuation_variants.add(name)
        return case_variants, punctuation_variants

    def _witnessed(self, payload):
        """Dimensions this payload's bytes witness, read from the bytes."""
        found = set()
        for path, text in G._walk_text(payload):
            if not G.find_matches(str(text), self.aliases):
                continue
            dot = G._dot(path)
            in_list = isinstance(G._get(payload, path[:-1]), list)
            case_variants, punctuation_variants = self._forms_in(str(text))
            if case_variants:
                found.add("case-variant")
            if punctuation_variants:
                found.add("punctuation-variant")
            if len(path) >= 4:
                found.add("nested-position")
            if G.is_protected(path, G.DEFAULT_PROTECTED_PATHS):
                found.add("approved-content")
                continue
            if in_list:
                found.add("list-value")
                if "negative" in dot:
                    found.add("negative-list-value")
            else:
                found.add("instruction-value")
                if "negative" in dot or self.NEGATION.search(str(text)):
                    found.add("negative-instruction")
        for path, key in G._walk_keys(payload):
            if not G.find_matches(str(key), self.aliases):
                continue
            dot = G._dot(path)
            case_variants, punctuation_variants = self._forms_in(str(key))
            found.add("key-position")
            if case_variants:
                found.add("case-variant")
            if punctuation_variants:
                found.add("punctuation-variant")
            if len(path) >= 4:
                found.add("nested-position")
            if "negative" in dot:
                found.add("negative-key")
        return found

    def test_fixture_covers_the_whole_class(self):
        """Clause 0 coverage, measured on the injected bytes and never on ids.

        Each required dimension must be witnessed by what a case actually puts
        into the payload, and an id that names a dimension the bytes do not
        show is a failure.  This is the property; the previous version asserted
        a list of ids the test itself declared, which is the receipt's claim.
        """
        self.assertTrue(self.cases, "the fixture carries no guard_cases")
        witnessed = set()
        per_case = {}
        for case in self.cases:
            payload = deep_merge(envelope(self.catalog, STYLE_IDS[0]),
                                 case["inject"])
            dimensions = self._witnessed(payload)
            per_case[case["id"]] = dimensions
            witnessed |= dimensions
        missing = sorted(set(self.REQUIRED_DIMENSIONS) - witnessed)
        self.assertEqual(missing, [],
                         "no case actually injects: %r" % (missing,))
        for case_id, dimensions in per_case.items():
            if "key" in case_id:
                self.assertIn("key-position", dimensions, case_id)
            if "case-variant" in case_id:
                self.assertIn("case-variant", dimensions, case_id)
            if "punctuation-variant" in case_id:
                self.assertIn("punctuation-variant", dimensions, case_id)
            if "negative" in case_id:
                self.assertTrue(
                    dimensions & {"negative-key", "negative-list-value",
                                  "negative-instruction"},
                    "%s claims a negative reference the bytes do not show"
                    % case_id)
            if "collision" in case_id:
                self.assertIn("approved-content", dimensions, case_id)

    def test_every_case_holds_on_every_style(self):
        self.assertTrue(self.cases)
        for case in self.cases:
            expect = case["expect"]
            for style_id in STYLE_IDS:
                payload = deep_merge(envelope(self.catalog, style_id),
                                     case["inject"])
                approved_before = approved_hashes(payload)
                receipt = G.guard(payload, self.catalog)
                label = (case["id"], style_id)
                self.assertEqual(receipt["decision"], expect["decision"], label)
                self.assertEqual(receipt["sendable"], expect["sendable"], label)
                self.assertEqual(sorted(receipt["sanitized_fields"]),
                                 sorted(expect["sanitized_fields"]), label)
                self.assertEqual(receipt["provider_calls"], 0, label)
                # the caller's payload, approved bytes included, is untouched
                self.assertEqual(approved_hashes(payload), approved_before,
                                 label)
                self.assertEqual(
                    receipt["preserved_approved_content_digest"]["fields"],
                    approved_before, label)
                if expect["blocked_reason"] is None:
                    self.assertEqual(receipt["blocked"], [], label)
                    self.assertEqual(
                        references_left(receipt["payload"], self.aliases),
                        {}, label)
                else:
                    self.assertEqual([b["reason"] for b in receipt["blocked"]],
                                     [expect["blocked_reason"]], label)
                    self.assertEqual([b["field"] for b in receipt["blocked"]],
                                     [expect["blocked_field"]], label)
                    self.assertIsNone(receipt["payload"], label)

    def test_collision_hold_is_hash_proven_and_holds_only_that_submission(self):
        held = deep_merge(envelope(self.catalog, "soul-ballad"),
                          {"input": {"lyrics": APPROVED_LYRICS +
                                     "\n[Sung] Whitney Houston"}})
        before = hashlib.sha256(
            held["input"]["lyrics"].encode("utf-8")).hexdigest()
        receipt = G.guard(held, self.catalog)
        after = hashlib.sha256(
            held["input"]["lyrics"].encode("utf-8")).hexdigest()
        self.assertEqual(before, after)                 # hash, not a claim
        self.assertEqual(
            receipt["preserved_approved_content_digest"]["fields"],
            {"input.lyrics": before})
        self.assertEqual(receipt["decision"], "BLOCKED")
        self.assertEqual(receipt["blocked"][0]["match"], ["whitney houston"])
        self.assertIn("review", receipt["blocked"][0]["resolution_owner"])
        # only that submission is held; the next clean one goes untouched
        clean = G.guard(envelope(self.catalog, "soul-ballad"), self.catalog)
        self.assertEqual(clean["decision"], "PASS")
        self.assertTrue(clean["sendable"])

    def test_inspected_fields_cover_every_text_and_key_position(self):
        payload = envelope(self.catalog, "afro-soul",
                           mix={"outer": {"inner": "clean"}})
        receipt = G.guard(payload, self.catalog)
        expect = set()
        for path, _text in G._walk_text(payload):
            expect.add(G._dot(path))
        for path, _key in G._walk_keys(payload):
            expect.add(G._dot(path))
        self.assertEqual(set(receipt["inspected_fields"]), expect)
        self.assertIn("input.mix.outer.inner", expect)
        self.assertIn("input.mix.outer", expect)

class DisplayMetadataBoundary(unittest.TestCase):
    """Display metadata is structurally unable to reach a provider payload."""

    def setUp(self):
        self.catalog = load_catalog()
        self.aliases = G.alias_set(self.catalog)
        self.record = {
            "style_id": "x",
            "client_references": {"artists": ["Whitney Houston"],
                                  "aliases": ["Whitney"]},
            "production_traits": {"instruments": "warm piano",
                                  "tempo": "70 bpm"},
        }

    def test_display_metadata_cannot_serialise_into_a_payload(self):
        block = PC.display_metadata(self.record)
        self.assertEqual(block, {"artists": ["Whitney Houston"],
                                 "aliases": ["Whitney"]})
        with self.assertRaises(TypeError):
            json.dumps({"input": {"mix": block}})

    def test_display_metadata_in_a_payload_is_refused_at_the_boundary(self):
        payload = envelope(self.catalog, "soul-ballad")
        payload["input"]["mix"] = PC.display_metadata(self.record)
        receipt = G.guard(payload, self.catalog)
        self.assertEqual(receipt["decision"], "BLOCKED")
        self.assertFalse(receipt["sendable"])
        self.assertIsNone(receipt["payload"])
        self.assertEqual([b["reason"] for b in receipt["blocked"]],
                         ["DISPLAY_METADATA_NOT_SERIALIZABLE"])
        self.assertIn("input.mix", receipt["blocked"][0]["field"])

    def test_a_compiled_payload_serialises_with_zero_references(self):
        payload = envelope(self.catalog, "soul-ballad",
                           style=PC.compile_style_field(self.record))
        wire = json.dumps(payload, sort_keys=True)
        self.assertEqual(references_left(payload, self.aliases), {})
        self.assertNotIn("Whitney", wire)
        self.assertEqual(G.find_matches(wire, self.aliases), [])

    def test_display_block_under_every_renamed_key_never_reaches_the_transport(
            self):
        # S75-T41 r8: a seventh spelling of a display-only key is the SAME
        # container.  Every renamed spelling is refused at the send boundary --
        # the transport sees nothing at all -- and the display payload itself
        # never reaches the serialized request.
        sent = []

        def fake_send(payload):
            sent.append(payload)
            return "job-1"

        for key in RENAMED_DISPLAY_KEYS:
            payload = envelope(self.catalog, "soul-ballad")
            payload["input"]["mix"] = {key: copy.deepcopy(DISPLAY_BLOCK)}
            with self.assertRaises(G.PromptGuardError) as ctx:
                G.guarded_send(payload, self.catalog, fake_send)
            self.assertIn("OUTGOING_REFERENCE_BLOCKED", str(ctx.exception), key)
            self.assertEqual(sent, [], key)
            receipt = G.guard(payload, self.catalog)
            self.assertEqual(receipt["decision"], "BLOCKED", key)
            self.assertFalse(receipt["sendable"], key)
            self.assertIsNone(receipt["payload"], key)
            self.assertEqual(receipt["provider_calls"], 0, key)
            self.assertTrue(
                any(b["reason"] == "CLIENT_METADATA_SERIALIZED"
                    and b["field"].endswith(key) for b in receipt["blocked"]),
                (key, receipt["blocked"]))
        self.assertEqual(sent, [])

    def test_a_display_block_cannot_hide_under_a_key_nobody_named_yet(self):
        # the block keys live INSIDE the block: display_value / display_note are
        # display-metadata names at any depth, under any outer key.
        for key in ("totally_new_key", "mix", "zzz"):
            payload = envelope(self.catalog, "soul-ballad")
            payload["input"]["mix"] = {key: copy.deepcopy(DISPLAY_BLOCK)}
            receipt = G.guard(payload, self.catalog)
            self.assertEqual(receipt["decision"], "BLOCKED", key)
            self.assertIsNone(receipt["payload"], key)
            self.assertEqual(receipt["provider_calls"], 0, key)

    def test_the_six_canonical_client_metadata_keys_keep_their_hard_block(self):
        for key in sorted(G.CLIENT_METADATA_KEYS):
            payload = envelope(self.catalog, "soul-ballad")
            payload["input"][key] = copy.deepcopy(DISPLAY_BLOCK)
            receipt = G.guard(payload, self.catalog)
            self.assertEqual(receipt["decision"], "BLOCKED", key)
            self.assertEqual([b["reason"] for b in receipt["blocked"]
                              if b["field"] == "input." + key],
                             ["CLIENT_METADATA_SERIALIZED"], key)
            self.assertIsNone(receipt["payload"], key)
            self.assertEqual(receipt["provider_calls"], 0, key)

    def test_displayonly_type_is_still_refused_under_any_key(self):
        for key in ("brand_new_key", "artistReferences", "mix"):
            payload = envelope(self.catalog, "soul-ballad")
            payload["input"]["mix"] = {key: PC.display_metadata(self.record)}
            receipt = G.guard(payload, self.catalog)
            self.assertEqual(receipt["decision"], "BLOCKED", key)
            self.assertIsNone(receipt["payload"], key)
            self.assertIn("DISPLAY_METADATA_NOT_SERIALIZABLE",
                          [b["reason"] for b in receipt["blocked"]], key)

    def test_digit_glued_and_allcaps_prefix_spellings_are_refused(self):
        # S75-T41 r9 defect D-1: the namespace is CLOSED.  A digit glued to the
        # container name and an all-caps prefix are the same container, so each
        # of these escapes everything the shape rule knew at r8.
        escapes = ("artistNames2", "artistReferences2", "displayMetadata2",
                   "artist_names2", "ARTISTReferences", "ARTISTNames",
                   "DISPLAYMetadata2", "CLIENTNames2")
        for key in escapes:
            payload = envelope(self.catalog, "soul-ballad")
            payload["input"][key] = {"artists": ["Whitney Houston"]}
            receipt = G.guard(payload, self.catalog)
            self.assertEqual(receipt["decision"], "BLOCKED", key)
            self.assertIsNone(receipt["payload"], key)
            self.assertIn("CLIENT_METADATA_SERIALIZED",
                          [b["reason"] for b in receipt["blocked"]], key)

    def test_plural_value_and_text_qualifiers_are_refused(self):
        # S75-T41 r9 defect D-2: the qualifier set carried value and text but
        # not values or texts, so a display subject with a plural qualifier
        # slipped the shape rule.
        escapes = ("recognition_values", "display_values", "artist_texts",
                   "recognition_texts", "client_values", "song_texts")
        for key in escapes:
            payload = envelope(self.catalog, "soul-ballad")
            payload["input"][key] = ["witney"]
            receipt = G.guard(payload, self.catalog)
            self.assertEqual(receipt["decision"], "BLOCKED", key)
            self.assertIn("CLIENT_METADATA_SERIALIZED",
                          [b["reason"] for b in receipt["blocked"]], key)

    def test_a_scalar_note_or_count_is_not_refused_as_display_metadata(self):
        # S75-T41 r9 defect D-3: the r8 shape rule refused keys that are not
        # containers at all.  A note and a count are scalars, and ONE token can
        # never be both halves of a container name.
        for key in ("displayNote", "referenceCount", "reference_count"):
            payload = envelope(self.catalog, "soul-ballad")
            payload["input"][key] = 3
            receipt = G.guard(payload, self.catalog)
            self.assertNotIn("CLIENT_METADATA_SERIALIZED",
                             [b["reason"] for b in receipt["blocked"]], key)
            self.assertEqual(receipt["decision"], "PASS", key)

    def test_a_bare_container_word_is_the_namespace_not_a_scalar(self):
        # S75-T41 r10: the r9 two-token rule ("the halves must be TWO tokens")
        # reads a key that is BOTH halves on its own as one scalar, so
        # ``references`` and its three spellings rode out where r8 refused
        # them.  A lone container word is the display namespace itself.
        for key in ("reference", "references", "ref", "refs"):
            payload = envelope(self.catalog, "soul-ballad")
            payload["input"][key] = ["Whitney Houston"]
            receipt = G.guard(payload, self.catalog)
            self.assertEqual(receipt["decision"], "BLOCKED", key)
            self.assertIsNone(receipt["payload"], key)
            self.assertEqual(receipt["provider_calls"], 0, key)
            self.assertIn("CLIENT_METADATA_SERIALIZED",
                          [b["reason"] for b in receipt["blocked"]
                           if b["field"] == "input." + key], key)

    def test_the_envelope_refuses_an_input_key_it_never_named(self):
        # S75-T41 r9 defect D-5: check_envelope allowlists the input keys, so a
        # spelling the shape rule never learned cannot legally ride out.
        clean = envelope(self.catalog, "soul-ballad")
        self.assertEqual(R.check_envelope(clean), [])
        for key in ("artistReferences2", "artistNames2", "displayMetadata2",
                    "ARTISTReferences", "recognition_values"):
            leaky = copy.deepcopy(clean)
            leaky["input"][key] = "x"
            errs = R.check_envelope(leaky)
            self.assertTrue(
                any(e.startswith("UNKNOWN_INPUT_KEY") and key in e
                    for e in errs), (key, errs))

class SquashedSpellings(unittest.TestCase):
    """S75-T41 defect 1: a squashed / hyphenated / punctuation-stripped
    spelling of a catalog reference is the SAME reference, in BOTH directions
    -- the leak is caught on both createTask directions (``input.style`` and
    ``input.negative_tags``), and a word that merely CONTAINS a squashed alias
    is not one."""

    LEAKS = (
        ("soul-rise", "negative_tags", "andraday beat"),
        ("acoustic-pop", "style", "warm strings, EdSheeran groove"),
        ("soul-ballad", "style", "warm strings, avoid LutherVandross tone"),
        # a JOIN between words is the same reference: underscore-joined and
        # apostrophe-joined spellings used to dispatch verbatim (S75-T41 r5)
        ("pop-rap", "style", "warm strings, Maroon_5 groove"),
        ("reggaeton", "negative_tags", "do not sound like Cardi_B"),
        ("trap-rap", "style_suffix", "avoid Jelly'Roll grit"),
        ("country-pop", "mix", "avoid Bad_Bunny grit"),
        # a NUMBER may not carry that join either.  NFKD decomposes the circled
        # digit to "1" and the Roman numeral to "I", which used to leave one
        # word no alias form could reach: ``bad1bunny`` / ``badibunny``.
        # (S75-T41 r6)
        ("pop-rap", "style", "warm strings, Maroon\u2460 5 groove"),
        ("trap-rap", "negative_tags", "do not sound like Bad\u2460Bunny"),
        ("reggaeton", "style_suffix", "avoid Cardi\u2460B grit"),
        ("acoustic-pop", "style", "warm strings, Jelly\u2460Roll groove"),
        ("country-pop", "mix", "avoid Celine\u2160Dion grit"),
        ("soul-rise", "style", "warm strings, avoid Bad\u2160Bunny tone"),
        ("soul-ballad", "negative_tags", "do not sound like Maroon\u21605"),
        ("pop-rap", "style", "warm strings, Maroon15 groove"),
    )

    def setUp(self):
        self.catalog = load_catalog()
        self.aliases = G.alias_set(self.catalog)

    def test_every_spelling_form_is_generated_per_alias(self):
        forms = G._alias_forms("Ed Sheeran")
        for form in ("ed sheeran", "edsheeran", "ed-sheeran",
                     "ed_sheeran", "ed'sheeran"):
            self.assertIn(form, forms)
        self.assertIn("pdiddy", G._alias_forms("P. Diddy"))
        self.assertIn("dangelo", G._alias_forms("D’Angelo"))
        self.assertIn("bad_bunny", G._alias_forms("Bad Bunny"))

    def test_squashed_leaks_are_caught_and_never_dispatched(self):
        for style_id, field, text in self.LEAKS:
            payload = envelope(self.catalog, style_id, **{field: text})
            self.assertTrue(G.find_matches(text, self.aliases), text)
            receipt = G.guard(payload, self.catalog)
            self.assertIn(receipt["decision"], ("SANITIZED", "BLOCKED"), text)
            self.assertNotEqual(receipt["decision"], "PASS", text)
            if receipt["sendable"]:
                wire = json.dumps(receipt["payload"], ensure_ascii=False)
                self.assertNotIn(text, wire, (field, text))
                self.assertEqual(G.find_matches(wire, self.aliases), [],
                                 (field, text))

    def test_squashed_hit_is_alias_shaped_never_a_substring(self):
        for text in ("andradaybeat drums", "bandraday groove",
                     "luthervandrossville tone", "bedsheeran groove",
                     "the day beat", "the_day_beat", "warm piano and strings"):
            self.assertEqual(G.find_matches(text, self.aliases), [], text)
        for text in ("andraday beat", "andraday_beat", "ANDRA-DAY beat",
                     "EdSheeran groove", "avoid LutherVandross tone",
                     "Luther-Vandross tone", "PDiddy groove",
                     "CÉLINE DION", "jelly-roll",
                     "Bad_Bunny groove", "Jelly_Roll groove",
                     "Maroon_5 groove", "Cardi_B groove", "Celine_Dion groove",
                     "Jelly'Roll groove", "Bad’Bunny groove",
                     "Bad__Bunny groove", "Puff_Daddy groove",
                     "Bad\u2460Bunny groove", "Bad\u2160Bunny groove",
                     "Bad1Bunny groove", "Maroon15 groove",
                     "Maroon\u2460 5 groove", "My\u2460Heart\u2460Will"
                     "\u2460Go\u2460On"):
            self.assertTrue(G.find_matches(text, self.aliases), text)

    def test_a_number_is_a_join_and_a_word_is_not(self):
        # The compatibility character is a SEPARATOR in its own right, whatever
        # NFKD would have made of it -- the two families S75-T41 r6 closes.
        for text in ("Bad\u2460Bunny", "Bad\u2160Bunny", "Bad\u2461Bunny",
                     "Bad\u00b2Bunny", "Bad\u2081Bunny", "Bad\u00bdBunny",
                     "Bad\u24ffBunny"):
            self.assertEqual(G.normalize(text), "bad bunny", text)
            self.assertTrue(G.find_matches(text, self.aliases), text)
        # a digit between the words is one join, whatever carries it
        for text in ("Bad1Bunny", "Bad\u0661Bunny", "Maroon15", "Cardi1B"):
            self.assertTrue(G.find_matches(text, self.aliases), text)
        # and it did NOT become a rule that any character is a separator:
        # an accent still folds, and a DIFFERENT WORD in an alias's place is
        # not that alias (``bead bunny`` is not ``bad bunny`` -- matching those
        # would be a fuzzy match on the words, which this never draws).  What is
        # a join is any material AT the word join -- see
        # ``test_a_join_unit_carries_any_characters_and_still_names_the_reference``.
        self.assertEqual(G.normalize("C\u00e9line Dion"), "celine dion")
        self.assertTrue(G.find_matches("C\u00c9LINE DION", self.aliases))
        for text in ("bead bunny drums", "brad bunny groove",
                     "maroon5paint", "maroon5paint set", "jellyrollpan"):
            self.assertEqual(G.find_matches(text, self.aliases), [], text)

    def test_a_join_unit_carries_any_characters_and_still_names_the_reference(
            self):
        # S75-T41 r7: the material sitting at an alias's word join may carry
        # ANY characters -- one letter, two, a digit, a digit run, punctuation,
        # a mix of all of them -- and the WORDS still name the reference.
        # Round 6 left nine of these dispatching verbatim: only the digit family
        # had been closed, and the two-letter join, the space-padded join and
        # the mixed join runs were still open.
        for text in ("BadxyBunny", "Bad 1 Bunny", "Bad'1'Bunny",
                     "Bad-1-Bunny", "Bad.x.Bunny", "Bad1_1Bunny",
                     "Bad_1'Bunny", "Bad_1_Bunny", "Bad__1__Bunny",
                     "BadxyzBunny", "BadabcdBunny", "Bad  x  Bunny",
                     "Bad 1 2 Bunny", "Bad___1___Bunny", "P.xDiddy"):
            self.assertTrue(G.find_matches(text, self.aliases), text)
        # the words are still what names it: a different word in an alias's
        # place is not the alias, and a squashed alias is never a substring of
        # a longer word.
        for text in ("bead bunny drums", "brad bunny groove",
                     "andradaybeat drums", "bedsheeran groove",
                     "jellyrollpan", "maroon5paint set"):
            self.assertEqual(G.find_matches(text, self.aliases), [], text)

    def test_no_alias_set_matches_nothing(self):
        self.assertEqual(G.find_matches("andraday beat", {}), [])
        receipt = G.guard(envelope(self.catalog, "soul-rise"), {"styles": {}})
        self.assertEqual(receipt["decision"], "PASS")

class JoinBoundaryRegression(unittest.TestCase):
    """S75-T41 r8: the join is one UNIT at the word boundary, never a WORD.

    Round 7 closed the join class with an UNBOUNDED gap, which turned ordinary
    prose into catalog collisions -- a 55-character English clause presented to
    the client as a reference.  The join stays open to any material AT the
    boundary and closed to a whole word between an alias's words.
    """

    def setUp(self):
        self.catalog = load_catalog()
        self.aliases = G.alias_set(self.catalog)

    def test_prose_carrying_an_aliass_words_with_material_between_dispatches(
            self):
        # the three sheets round 7 blocked as APPROVED_CONTENT_COLLISION: they
        # carry an alias's words with prose between them and must dispatch
        # byte-identical, at the guard and at the send boundary.
        sent = []

        def fake_send(payload):
            sent.append(payload)
            return "job-1"

        for sheet in PROSE_SHEETS:
            self.assertEqual(G.find_matches(sheet, self.aliases), [], sheet)
            payload = envelope(self.catalog, "soul-ballad", lyrics=sheet)
            before = hashlib.sha256(sheet.encode("utf-8")).hexdigest()
            receipt = G.guard(payload, self.catalog)
            self.assertEqual(receipt["decision"], "PASS", sheet)
            self.assertTrue(receipt["sendable"], sheet)
            self.assertEqual(receipt["payload"]["input"]["lyrics"], sheet)
            self.assertEqual(
                receipt["preserved_approved_content_digest"]["fields"],
                {"input.lyrics": before}, sheet)
            _, sent_receipt = G.guarded_send(
                envelope(self.catalog, "soul-ballad", lyrics=sheet),
                self.catalog, fake_send)
            wire = json.dumps(sent[-1], ensure_ascii=False)
            self.assertEqual(sent[-1]["input"]["lyrics"], sheet, sheet)
            self.assertNotIn("display_value", wire)
        self.assertEqual(len(sent), len(PROSE_SHEETS))

    def test_hyphenated_prose_never_collides_on_an_aliass_words(self):
        # S75-T41 r9 defect D-4: a hyphen is a WORD SEPARATOR, so a hyphenated
        # compound of an alias's words is prose, never a reference.
        sheet = "the bad-boy-bunny hops"
        self.assertEqual(G.find_matches(sheet, self.aliases), [])
        payload = envelope(self.catalog, "soul-ballad", lyrics=sheet)
        receipt = G.guard(payload, self.catalog)
        self.assertEqual(receipt["decision"], "PASS")
        self.assertEqual(receipt["payload"]["input"]["lyrics"], sheet)

    def test_the_ten_named_carriers_never_reach_any_wire_position(self):
        # the ten carriers the round-6 verdict named, at all four wire
        # positions (style, negative tags, style suffix and an outbound map
        # key): the literal spelling must never appear in what the transport
        # was handed.
        spellings = ("BadXYBunny", "BadXYZBunny", "Bad_1_Bunny",
                     "Bad__1__Bunny", "Bad_1'Bunny", "Bad'1_Bunny",
                     "Bad-1-Bunny", "Bad.x.Bunny", "Bad 1 Bunny",
                     "Bad1_1Bunny")
        for text in spellings:
            for position in ("style", "negative_tags", "style_suffix",
                             "mix_key"):
                payload = envelope(self.catalog, "trap-rap")
                if position == "mix_key":
                    payload["input"]["mix"] = {text: "clean"}
                else:
                    payload["input"][position] = {
                        "style": "warm strings, %s groove" % text,
                        "negative_tags": "do not sound like %s" % text,
                        "style_suffix": "avoid %s grit" % text,
                    }[position]
                sent = []

                def fake_send(request):
                    sent.append(request)
                    return "job-1"

                try:
                    G.guarded_send(payload, self.catalog, fake_send)
                except G.PromptGuardError:
                    pass
                wire = "".join(json.dumps(request, ensure_ascii=False)
                               for request in sent)
                self.assertNotIn(text, wire, (position, text))
                self.assertEqual(G.find_matches(wire, self.aliases), [],
                                 (position, text))

    def test_the_boundary_controls_the_round_named_match_nothing(self):
        for text in ("bad boy bunny groove", "bad moon bunny groove",
                     "cardigan b"):
            self.assertEqual(G.find_matches(text, self.aliases), [], text)
            payload = envelope(self.catalog, "trap-rap", lyrics=text)
            receipt = G.guard(payload, self.catalog)
            self.assertEqual(receipt["decision"], "PASS", text)

    def test_the_join_is_still_open_to_any_material_at_the_boundary(self):
        # one join UNIT at one word boundary: letters, digits, punctuation,
        # runs of them, mixed, doubled, padded -- the same reference.
        for text in ("BadxyBunny", "BadabcdBunny", "BadxyzzyxqBunny",
                     "Bad 1 Bunny", "Bad 1 2 Bunny", "Bad'1'Bunny",
                     "Bad-1-Bunny", "Bad.x.Bunny", "Bad1_1Bunny",
                     "Bad_1'Bunny", "Bad_1_Bunny", "Bad__1__Bunny",
                     "Bad___1___Bunny", "Bad1234Bunny", "P.xDiddy"):
            self.assertTrue(G.find_matches(text, self.aliases), text)
            payload = envelope(self.catalog, "trap-rap", style=text)
            receipt = G.guard(payload, self.catalog)
            self.assertIn(receipt["decision"], ("SANITIZED", "BLOCKED"), text)
            self.assertNotEqual(receipt["decision"], "PASS", text)

    def test_a_whole_word_between_the_alias_words_is_not_that_alias(self):
        for text in ("bad boy bunny groove", "bad moon bunny groove",
                     "bad that night but the bunny", "bead bunny drums",
                     "brad bunny groove", "the jelly sits on the plate",
                     "my heart will always search for the one"):
            self.assertEqual(G.find_matches(text, self.aliases), [], text)

class DispatchSeam(unittest.TestCase):
    """S75-T41 defect 2: the guard runs at the REAL outbound seam --
    ``song_dispatch.run_takes``, the one funnel every createTask payload goes
    through -- so a leaking payload is refused there and NEVER reaches the
    transport (zero provider calls)."""

    CLIENT = "I am not small. I never was. One seed of truth made me strong."
    HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
    SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
             {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
             {"tag": "Verse", "delivery": "sung",
              "lines": ["One seed of truth made me stro-o-ong,"]},
             {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
             {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
             {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
             {"tag": "Outro", "delivery": "spoken",
              "lines": ["Get the book. Link below."]}]
    HOOK_PLAN = {"true_at_beat": "the_world"}
    PACE_ORDER = {"drop": "half-time drop, thin drums",
                  "return": "turn and rise back to the groove",
                  "boundary_s": 15.0, "return_boundary_s": 38.0}
    STYLE_ID = "soul-ballad"

    def setUp(self):
        self.catalog = load_catalog()
        self.aliases = G.alias_set(self.catalog)

    def _dispatch(self, mutate=None):
        """(requests the transport received, seam error or None)."""
        import length_formula as LF
        import song_dispatch as SD
        import suno_recipe as R
        sent = []

        def transport(request):
            sent.append(request)
            return []

        plan = dict(LF.plan(60, (15, 20)), style_id=self.STYLE_ID,
                    hook_plan=self.HOOK_PLAN, pace_change=self.PACE_ORDER)
        req = R.build_request(self.STYLE_ID, self.SHEET, self.CLIENT, "T",
                              plan["delivered_s"], hook_plan=self.HOOK_PLAN,
                              pace_plan=self.PACE_ORDER)
        req["input"]["duration"] = plan["delivered_s"]
        if mutate:
            mutate(req["input"])
        try:
            SD.run_takes(req, plan, transport, lambda t: {}, lambda t, r: None,
                         "One closed door. Get the book.", " ".join(self.HOOK),
                         (15, 20), kie=lambda fn, lbl, generation=False: fn(),
                         style_id=self.STYLE_ID, cap_cents=6,
                         alias_catalog=self.catalog)
        except Exception as exc:                      # noqa: BLE001 - the seam's own refusal
            return sent, exc
        return sent, None

    def test_leaking_payload_is_refused_at_the_seam_and_never_dispatched(self):
        for field, text in (("lyrics", APPROVED_LYRICS + "\n[Sung] Jelly Roll"),
                            ("style", "EdSheeran groove"),
                            ("style", "avoid LutherVandross tone"),
                            ("style", "avoid Puff_Daddy tone"),
                            ("style", "avoid Bad_Bunny tone")):
            def mutate(inp, field=field, text=text):
                inp[field] = text
            sent, err = self._dispatch(mutate)
            self.assertEqual(sent, [], (field, text))
            self.assertIsNotNone(err, (field, text))
            self.assertIn("OUTGOING_REFERENCE_BLOCKED", str(err), (field, text))

    def test_join_carriers_are_refused_at_every_wire_position(self):
        # S75-T41 r7: the join class is closed at the REAL seam -- the same nine
        # spellings round 6 measured reaching the transport, in every position
        # that goes on the wire (style, negative tags, style suffix and an
        # outbound map key).  The criterion is the round-6 one: the literal
        # spelling must never appear in anything the transport was handed.
        spellings = ("BadxyBunny", "Bad 1 Bunny", "Bad'1'Bunny",
                     "Bad-1-Bunny", "Bad.x.Bunny", "Bad1_1Bunny",
                     "Bad_1'Bunny", "Bad_1_Bunny", "Bad__1__Bunny")
        for text in spellings:
            self.assertTrue(G.find_matches(text, self.aliases), text)
            for position in ("style", "negative_tags", "style_suffix",
                             "mix_key"):
                def mutate(inp, position=position, text=text):
                    if position == "mix_key":
                        inp["mix"] = {text: "clean"}
                    else:
                        inp[position] = {
                            "style": "warm strings, %s groove" % text,
                            "negative_tags": "do not sound like %s" % text,
                            "style_suffix": "avoid %s grit" % text,
                        }[position]
                sent, _err = self._dispatch(mutate)
                wire = "".join(json.dumps(request, ensure_ascii=False)
                               for request in sent)
                self.assertNotIn(text, wire, (position, text))
                self.assertEqual(G.find_matches(wire, self.aliases), [],
                                 (position, text))

    def test_squashed_leak_dispatches_only_approved_traits(self):
        def mutate(inp):
            inp["style"] = inp["style"] + ", warm strings, EdSheeran groove"
            inp["negative_tags"] = "andraday beat"
        sent, err = self._dispatch(mutate)
        self.assertIsNone(err, err)
        self.assertEqual(len(sent), 1)
        wire = json.dumps(sent[0], ensure_ascii=False)
        self.assertNotIn("EdSheeran groove", wire)
        self.assertNotIn("andraday beat", wire)
        self.assertEqual(G.find_matches(wire, self.aliases), [], wire)

    def test_clean_payload_still_reaches_the_transport(self):
        sent, err = self._dispatch()
        self.assertIsNone(err, err)
        self.assertEqual(len(sent), 1)
        self.assertEqual(G.find_matches(json.dumps(sent[0], ensure_ascii=False),
                                        self.aliases), [])


class ShippedCatalogFailClosed(unittest.TestCase):
    """S75-A41 fail-closed (S75-T41-alias): the dispatch seam guards with the
    SHIPPED 18-style catalog even when the caller omits ``alias_catalog`` and
    the request carries no ``_alias_catalog`` -- the sweep can no longer be
    silently skipped by leaving the catalog out.  No fixture catalog is
    injected anywhere in this class: the shipped module is the only source."""

    CLIENT = DispatchSeam.CLIENT
    HOOK = DispatchSeam.HOOK
    SHEET = DispatchSeam.SHEET
    HOOK_PLAN = DispatchSeam.HOOK_PLAN
    PACE_ORDER = DispatchSeam.PACE_ORDER
    STYLE_ID = DispatchSeam.STYLE_ID

    def _dispatch_no_catalog(self, mutate=None):
        """(requests the transport received, seam error or None).

        Identical to DispatchSeam._dispatch except ``alias_catalog`` is never
        passed and no ``_alias_catalog`` rides the request: the SHIPPED path.
        """
        import length_formula as LF
        import song_dispatch as SD
        import suno_recipe as R
        sent = []

        def transport(request):
            sent.append(request)
            return []

        plan = dict(LF.plan(60, (15, 20)), style_id=self.STYLE_ID,
                    hook_plan=self.HOOK_PLAN, pace_change=self.PACE_ORDER)
        req = R.build_request(self.STYLE_ID, self.SHEET, self.CLIENT, "T",
                              plan["delivered_s"], hook_plan=self.HOOK_PLAN,
                              pace_plan=self.PACE_ORDER)
        req["input"]["duration"] = plan["delivered_s"]
        self.assertNotIn("_alias_catalog", req)
        if mutate:
            mutate(req["input"])
        try:
            SD.run_takes(req, plan, transport, lambda t: {}, lambda t, r: None,
                         "One closed door. Get the book.", " ".join(self.HOOK),
                         (15, 20), kie=lambda fn, lbl, generation=False: fn(),
                         style_id=self.STYLE_ID, cap_cents=6)
        except Exception as exc:                      # noqa: BLE001 - the seam's own refusal
            return sent, exc
        return sent, None

    def test_omitted_catalog_still_strips_a_real_artist_name(self):
        def mutate(inp):
            inp["style"] = (inp["style"]
                            + ", in the style of Whitney Houston")
        sent, err = self._dispatch_no_catalog(mutate)
        self.assertIsNone(err, err)
        self.assertEqual(len(sent), 1)
        wire = json.dumps(sent[0], ensure_ascii=False)
        self.assertNotIn("Whitney Houston", wire)
        probe = G.alias_set({"styles": {
            "<run>": {"client_references": {
                "artists": ["Whitney Houston"]}}}})
        self.assertEqual(G.find_matches(wire, probe), [])

    def test_omitted_catalog_still_blocks_an_unrewritable_reference(self):
        def mutate(inp):
            inp["style"] = "Whitney Houston"
        sent, err = self._dispatch_no_catalog(mutate)
        self.assertEqual(sent, [])
        self.assertIsNotNone(err)
        self.assertIn("OUTGOING_REFERENCE_BLOCKED", str(err))

    def test_omitted_catalog_clean_payload_still_reaches_the_transport(self):
        sent, err = self._dispatch_no_catalog()
        self.assertIsNone(err, err)
        self.assertEqual(len(sent), 1)

    def test_shipped_catalog_covers_all_eighteen_styles(self):
        import song_dispatch.song_dispatch as SDM
        shipped = SDM._shipped_alias_catalog()
        self.assertEqual(len(shipped.get("styles", {})), 18)
        aliases = G.alias_set(shipped)
        self.assertTrue(aliases)
        for sid in C.style_ids():
            for ref in C.client_references(sid):
                self.assertTrue(G.find_matches(ref, aliases),
                                (sid, ref))

    def test_unreadable_shipped_catalog_with_partial_caller_catalog_refuses(self):
        # S75-T41-alias r3: shipped unreadable + PARTIAL caller catalog must
        # refuse (MISSING_ALIAS_CATALOG), never union caller-only refs and send
        # a raw artist name. Written against the leaking code this FAILS: one
        # send carrying "Whitney Houston" reaches the transport.
        import length_formula as LF
        import song_dispatch as SD
        import song_dispatch.song_dispatch as SDM
        import suno_recipe as R
        real = SDM._shipped_alias_catalog
        SDM._shipped_alias_catalog = lambda: {}
        try:
            partial = {"styles": {"<run>": {
                "style_id": "<run>",
                "client_references": {"artists": ["Imaginary Leak Artist"],
                                      "aliases": [], "reference_songs": []}}}}
            sent = []

            def transport(request):
                sent.append(request)
                return []

            plan = dict(LF.plan(60, (15, 20)), style_id=self.STYLE_ID,
                        hook_plan=self.HOOK_PLAN, pace_change=self.PACE_ORDER)
            req = R.build_request(self.STYLE_ID, self.SHEET, self.CLIENT,
                                  "T", plan["delivered_s"],
                                  hook_plan=self.HOOK_PLAN,
                                  pace_plan=self.PACE_ORDER)
            req["input"]["duration"] = plan["delivered_s"]
            req["input"]["style"] = (req["input"]["style"]
                                     + ", in the style of Whitney Houston")
            try:
                SD.run_takes(req, plan, transport, lambda t: {},
                             lambda t, r: None,
                             "One closed door. Get the book.",
                             " ".join(self.HOOK), (15, 20),
                             kie=lambda fn, lbl, generation=False: fn(),
                             style_id=self.STYLE_ID, cap_cents=6,
                             alias_catalog=partial)
            except Exception as exc:  # noqa: BLE001 - the seam's own refusal
                err = exc
            else:
                err = None
            self.assertEqual(sent, [])
            self.assertIsNotNone(err)
            self.assertIn("MISSING_ALIAS_CATALOG", str(err))
            wire = "".join(json.dumps(request, ensure_ascii=False)
                           for request in sent)
            self.assertNotIn("Whitney Houston", wire)
        finally:
            SDM._shipped_alias_catalog = real

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

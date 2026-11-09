#!/usr/bin/env python3
"""S75-T41 runnable self-check: artist references never reach generation.

No framework: stdlib ``unittest`` only, runnable two ways --
    python3 core/music_styles/test_suno_prompt_guard_s75t41.py
    python3 -m pytest core/music_styles/test_suno_prompt_guard_s75t41.py

Exit 0 = all pass, 1 = failures, 2 = tooling failure.

The adversarial block at the bottom is the point of this file. It includes
cases the guard deliberately does NOT catch; those are asserted as uncaught
and printed by name, so the limitation is measured, never assumed.
"""
from __future__ import annotations

import hashlib
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import catalog as C                                # noqa: E402
import suno_prompt_compiler as P                  # noqa: E402
import suno_prompt_guard as G                     # noqa: E402

#: Cases this self-check proves are NOT caught. Reported, not hidden.
UNCAUGHT = []

LYRICS = "[Spoken] the sign turns to closed\n[Sung] I ask for the help I need"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CompilerContract(unittest.TestCase):

    def test_all_eighteen_compile_clean_and_within_cap(self):
        for sid in C.style_ids():
            out = P.compile_outgoing(sid, {"lyrics": LYRICS})
            self.assertLessEqual(len(out["style"]), P.STYLE_FIELD_MAX, sid)
            self.assertTrue(out["negative_tags"].strip(), sid)
            for dry in P.DRY_NEGATIVES:
                self.assertIn(dry, out["negative_tags"].lower(), sid)
            receipt = G.guard(out, approved_lyrics=LYRICS,
                              approved_character_names=())
            self.assertEqual("PASS", receipt["verdict"],
                             "%s: %r" % (sid, receipt["matches"]))
            self.assertGreaterEqual(len(receipt["scanned_fields"]), 4, sid)
            self.assertEqual(sha(LYRICS), out["_lyrics_sha256"], sid)

    def test_every_outgoing_field_is_enumerated(self):
        out = P.compile_outgoing("pop-rock", {"lyrics": LYRICS, "title": "T",
                                              "duration_s": 60,
                                              "character_names": ("Mara",)})
        receipt = G.guard(out, approved_lyrics=LYRICS)
        fields = set(receipt["scanned_fields"])
        for required in ("style", "negative_tags", "title"):
            self.assertTrue(any(f == required or f.endswith("." + required)
                                for f in receipt["scanned_fields"]),
                            "%s not enumerated: %r" % (required, fields))
        self.assertIn("lyrics", receipt["protected_fields"])
        self.assertIn("character_names", receipt["protected_fields"])

    def test_display_path_is_separate_from_provider_path(self):
        for sid in C.style_ids():
            display = P.client_display(sid)
            outgoing = P.compile_outgoing(sid, {"lyrics": LYRICS})
            self.assertTrue(display["client_references"], sid)
            self.assertTrue(display["display_only"], sid)
            self.assertNotIn("client_references", P.outgoing_field_names(outgoing))
            blob = repr(outgoing).casefold()
            for ref in display["client_references"]:
                self.assertNotIn(G.normalize(ref), G.normalize(blob), sid)

    def test_compiler_never_reads_client_references(self):
        rec = C.style("country-rap")
        stripped = {k: v for k, v in rec.items() if k != "client_references"}
        with_refs = P.compile_outgoing(rec, {"lyrics": LYRICS})
        without = P.compile_outgoing(stripped, {"lyrics": LYRICS})
        self.assertEqual(with_refs["style"], without["style"])
        self.assertEqual(with_refs["negative_tags"], without["negative_tags"])

    def test_approved_bytes_pass_through_untouched(self):
        lyrics = "[Spoken] Drake opens the door\n[Sung] Drake stays anyway"
        names = ("Drake", "Mara")
        out = P.compile_outgoing("melodic-rap",
                                 {"lyrics": lyrics, "character_names": names})
        self.assertEqual(lyrics, out["lyrics"])
        self.assertEqual(names, out["character_names"])
        receipt = G.guard(out, approved_lyrics=lyrics,
                          approved_character_names=names)
        self.assertEqual("PASS", receipt["verdict"], receipt["matches"])
        self.assertEqual(sha(lyrics), receipt["lyrics_sha256"])

    def test_unknown_style_and_trait_namespace_are_refused(self):
        with self.assertRaises(P.CompileError) as exc:
            P.compile_outgoing("not-a-style", {"lyrics": ""})
        self.assertEqual("UNKNOWN_STYLE", exc.exception.code)
        rec = C.style("pop-rock")
        rec["production_traits"]["client_references"] = ("Maroon 5",)
        with self.assertRaises(P.CompileError) as exc:
            P.compile_outgoing(rec, {"lyrics": ""})
        self.assertEqual("DISPLAY_KEY_IN_TRAITS", exc.exception.code)
        with self.assertRaises(P.CompileError) as exc:
            P.compile_outgoing("pop-rock", {"lyrics": "", "duration_s": 61})
        self.assertEqual("BAD_CHOICE", exc.exception.code)
        with self.assertRaises(P.CompileError) as exc:
            P.compile_outgoing("soul-ballad",
                               {"lyrics": "", "deliveries": ("rap",)})
        self.assertEqual("BAD_CHOICE", exc.exception.code)


class AdversarialSeparation(unittest.TestCase):

    def _blocked(self, payload, token, field_hint=None):
        receipt = G.guard(payload)
        self.assertEqual("BLOCKED", receipt["verdict"], receipt)
        tokens = {m["token"] for m in receipt["matches"]}
        self.assertIn(token, tokens, receipt["matches"])
        if field_hint:
            self.assertTrue(
                any(field_hint in m["field"] for m in receipt["matches"]),
                receipt["matches"])
        return receipt

    def _payload(self, **overrides):
        payload = P.compile_outgoing("pop-rap", {"lyrics": LYRICS})
        payload.update(overrides)
        return payload

    def test_alias_instead_of_full_name(self):
        self._blocked(self._payload(style="drizzy bounce over bright bass"),
                      "Drizzy", "style")

    def test_artist_inside_longer_descriptive_phrase(self):
        self._blocked(
            self._payload(style="warm acoustic guitar in the spirit of "
                                "Ed Sheeran and friends"),
            "Ed Sheeran", "style")

    def test_artist_only_in_negative_field(self):
        self._blocked(
            self._payload(negative_tags="dry mix, not in the style of "
                                       "P. Diddy, no reverb"),
            "P. Diddy", "negative_tags")

    def test_alias_spellings_punctuation_case_and_squash(self):
        for spelling, token in (
                ("CÉLINE-DION", "Celine Dion"),
                ("P Diddy", "P. Diddy"),
                ("pdiddy", "P. Diddy"),
                ("DRAKE’S bounce", "Drake")):
            self._blocked(self._payload(style="a %s lift" % spelling), token)

    def test_style_trait_word_is_an_artist_name(self):
        rec = C.style("trap-rap")
        rec["production_traits"]["musical_identity"] = (
            "future bass low end under rolling hats")
        out = P.compile_outgoing(rec, {"lyrics": LYRICS})
        self.assertIn("future bass", out["style"])
        self._blocked(out, "Future", "style")

    def test_character_name_equal_to_artist_name_inside_lyrics_is_kept(self):
        lyrics = "[Spoken] Drake signs the letter\n[Sung] Drake keeps the name"
        out = P.compile_outgoing("rnb-flow",
                                 {"lyrics": lyrics,
                                  "character_names": ("Drake",)})
        receipt = G.guard(out, approved_lyrics=lyrics,
                          approved_character_names=("Drake",))
        self.assertEqual("PASS", receipt["verdict"], receipt["matches"])
        self.assertEqual(lyrics, out["lyrics"])
        self.assertEqual(sha(lyrics), receipt["lyrics_sha256"])

    def test_character_name_in_instruction_field_is_blocked(self):
        out = P.compile_outgoing("rnb-flow",
                                 {"lyrics": "[Spoken] Drake signs\n[Sung] no",
                                  "character_names": ("Drake",)})
        out["style"] = out["style"] + " and Drake on the hook"
        self._blocked(out, "Drake", "style")

    def test_display_metadata_key_in_provider_payload(self):
        out = self._payload()
        out["client_references"] = ("Nelly",)
        receipt = self._blocked(out, "client_references")
        self.assertTrue(any(m["kind"] == "display-metadata-key"
                            for m in receipt["matches"]))
        camel = self._payload()
        camel["clientReferences"] = ("Nelly",)
        self._blocked(camel, "clientReferences")

    def test_squashed_full_name_is_caught(self):
        self._blocked(self._payload(style="an edsheeran lift"), "Ed Sheeran")

    def test_object_key_is_outbound_text(self):
        out = self._payload()
        out["Drake"] = "warm"
        self._blocked(out, "Drake")

    def test_mutated_lyrics_are_blocked_not_rewritten(self):
        out = P.compile_outgoing("pop-rock", {"lyrics": LYRICS})
        mutated = out["lyrics"].replace("help", "aid")
        out["lyrics"] = mutated
        receipt = G.guard(out, approved_lyrics=LYRICS)
        self.assertEqual("BLOCKED", receipt["verdict"])
        self.assertTrue(any(m["kind"] == "approved-lyrics-mutated"
                            for m in receipt["matches"]))
        # The guard read the bytes; it did not repair them.
        self.assertEqual(mutated, out["lyrics"])

    def test_mutated_character_names_are_blocked(self):
        out = P.compile_outgoing("pop-rock",
                                 {"lyrics": LYRICS,
                                  "character_names": ("Mara", "Drake")})
        out["character_names"] = ("Mara",)
        receipt = G.guard(out, approved_lyrics=LYRICS,
                          approved_character_names=("Mara", "Drake"))
        self.assertEqual("BLOCKED", receipt["verdict"])
        self.assertTrue(any(m["kind"] == "approved-characters-mutated"
                            for m in receipt["matches"]))


class KnownUncaught(unittest.TestCase):
    """Measured limits. Each PASS here is a case the guard cannot catch."""

    def test_unrecorded_nickname_passes(self):
        # "Wheelchair Jimmy" is a real Drake alias the alias table omits.
        receipt = G.guard({"style": "a wheelchair jimmy bounce"})
        self.assertEqual("PASS", receipt["verdict"])
        UNCAUGHT.append("unrecorded nickname: 'Wheelchair Jimmy'")

    def test_homoglyph_passes(self):
        # Cyrillic 'а' in "Drаke" is not folded to Latin 'a'.
        receipt = G.guard({"style": "a Drаke bounce"})
        self.assertEqual("PASS", receipt["verdict"])
        UNCAUGHT.append("homoglyph spelling: 'Dr\\u0430ke'")

    def test_artist_missing_from_catalog_passes(self):
        receipt = G.guard({"style": "a Beatles-style bounce"})
        self.assertEqual("PASS", receipt["verdict"])
        UNCAUGHT.append("artist absent from the 18-style catalog: 'Beatles'")


def main():
    try:
        result = unittest.main(exit=False, verbosity=2).result
    except Exception as exc:                        # tooling, not a verdict
        print("TOOLING FAILURE: %r" % (exc,))
        return 2
    print("\nKNOWN UNCAUGHT BY THIS GUARD (%d):" % len(UNCAUGHT))
    for case in UNCAUGHT:
        print("  - %s" % case)
    print("ALIAS SCOPE: %d catalog references, %d distinct alias forms; "
          "not a global blacklist" % (len(G.catalog_references()),
                                      len({f for _t, f in
                                           G.forbidden_tokens()})))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

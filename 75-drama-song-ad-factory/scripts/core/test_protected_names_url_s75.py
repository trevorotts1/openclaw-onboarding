#!/usr/bin/env python3
"""U6/S75: a site given as ``url`` or ``cta_url`` is a protected name.

Failure this prevents: a brief carried the client's site under ``url`` or
``cta_url`` instead of ``website``, so the site's own words ("Bright Future
Now") were refused by the lyric spelling gate and the site never reached the
protected list. Zero paid calls; stdlib only.

    python3 test_protected_names_url_s75.py
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import protected_names as P  # noqa: E402  module under test

LINE = "Go to brightfuturenow dot org."

class SiteKeysAreProtected(unittest.TestCase):
    def test_url_protects_the_site(self):
        self.assertEqual(
            P.check_lyrics_spelling(LINE, P.protected_list({"url": "brightfuturenow.org"})),
            [])

    def test_cta_url_protects_the_site(self):
        self.assertEqual(
            P.check_lyrics_spelling(LINE, P.protected_list({"cta_url": "brightfuturenow.org"})),
            [])

    def test_empty_brief_still_refuses_the_site(self):
        errs = P.check_lyrics_spelling(LINE, P.protected_list({}))
        self.assertTrue(any("brightfuturenow" in e for e in errs), errs)

    def test_website_is_unchanged(self):
        self.assertEqual(P.protected_list({"website": "brightfuturenow.org"}),
                         ["brightfuturenow.org"])

    def test_both_site_keys_dedupe(self):
        self.assertEqual(
            P.protected_list({"website": "brightfuturenow.org",
                              "url": "brightfuturenow.org",
                              "cta_url": "brightfuturenow.org"}),
            ["brightfuturenow.org"])

if __name__ == "__main__":
    unittest.main(verbosity=2)

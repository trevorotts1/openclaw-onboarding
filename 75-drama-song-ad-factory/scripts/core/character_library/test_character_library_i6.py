#!/usr/bin/env python3
"""I6: save + reuse round trip. Run: python3 test_character_library_i6.py"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:                                   # pytest imports the character_library
    from character_library import character_library as CL  # noqa: E402
except ImportError:                    # PACKAGE (dir has __init__.py) first;
    import character_library as CL     # a script run gets the module file


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.client = os.path.join(self.t, "client-a")
        self.img = os.path.join(self.t, "face.png")
        with open(self.img, "wb") as f:
            f.write(b"\x89PNG-fake-bytes")

    def test_save_then_reuse_in_a_fresh_process(self):
        self.assertIsNone(CL.saved_character_question(self.client))
        self.assertIn("reuse them in future ads", CL.save_question("Maya"))
        CL.save_character(self.client, "Maya Lee", "Warm, 40s, silver braids.",
                          [self.img], "Low, calm alto")
        out = subprocess.run(
            [sys.executable, os.path.join(HERE, "character_library.py"),
             "--client-dir", self.client, "use", "--name", "maya lee"],
            capture_output=True, text=True, check=True).stdout
        self.assertIn("silver braids", out)
        rec = CL.get_character(self.client, "Maya Lee")
        with open(rec["reference_paths"][0], "rb") as f:
            self.assertEqual(f.read(), b"\x89PNG-fake-bytes")
        self.assertEqual(CL.brief_fields(rec)["character_voice_notes"], "Low, calm alto")
        q = CL.saved_character_question(self.client)
        self.assertTrue(q["ask"].endswith("?"))
        self.assertEqual(q["options"][0][0], "Create a new character")
        self.assertEqual(q["options"][1][0], "Use Maya Lee")

    def test_clients_are_separate_and_refusals(self):
        CL.save_character(self.client, "Maya", "d", [self.img])
        self.assertEqual(CL.list_characters(os.path.join(self.t, "client-b")), [])
        for bad in (lambda: CL.save_character(self.client, "Maya", "d", [self.img]),
                    lambda: CL.save_character(self.client, "Zed", "d", []),
                    lambda: CL.save_character(self.client, "Zed", "", [self.img]),
                    lambda: CL.save_character(self.client, "!!", "d", [self.img]),
                    lambda: CL.save_character(self.client, "Zed", "d", [self.img + ".nope"])):
            with self.assertRaises(CL.LibraryError):
                bad()
        CL.save_character(self.client, "Maya", "new", [self.img], overwrite=True)
        self.assertEqual(CL.get_character(self.client, "Maya")["description"], "new")

    def test_factory_cli_and_card(self):
        factory = os.path.join(HERE, "..", "intake_preflight", "factory.py")
        run = lambda *a: subprocess.run([sys.executable, factory] + list(a),
                                        capture_output=True, text=True)
        r = run("character", "--client-dir", self.client, "save", "--name", "Maya",
                "--description", "Warm, 40s", "--image", self.img)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Maya", run("character", "--client-dir", self.client, "list").stdout)
        self.assertIn("Use Maya",
                      run("character", "--client-dir", self.client, "card").stdout)
        out = run("card", "--client-dir", self.client).stdout  # factory card passes --client-dir (I6)
        self.assertIn("saved with us", out)
        self.assertNotIn("saved with us", run("card").stdout)
        card = os.path.join(HERE, "..", "choice_card", "intake_card", "intake_card.py")
        if os.path.exists(card):  # H9 card present in this tree
            out = subprocess.run([sys.executable, card, "--client-dir", self.client],
                                 capture_output=True, text=True, check=True).stdout
            self.assertIn("saved with us", out)
            self.assertIn("Question 1 of 7", out)


if __name__ == "__main__":
    unittest.main()

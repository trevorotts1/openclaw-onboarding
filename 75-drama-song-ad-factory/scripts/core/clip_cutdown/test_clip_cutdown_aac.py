"""FU-AAC-FINAL-MUX: clip cutdowns are AAC 48 kHz + faststart."""
import os
import sys
import unittest

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)
from clip_cutdown import clip_cutdown as C  # noqa: E402


class T(unittest.TestCase):
    def test_argv(self):
        a = C.build_argv("m.mp4", {"start_s": 0, "duration_s": 10, "name": "c"}, "o")
        self.assertEqual(a[a.index("-c:a") + 1], "aac")
        self.assertEqual(a[a.index("-ar") + 1], "48000")
        self.assertEqual(a[a.index("-movflags") + 1], "+faststart")


if __name__ == "__main__":
    unittest.main()

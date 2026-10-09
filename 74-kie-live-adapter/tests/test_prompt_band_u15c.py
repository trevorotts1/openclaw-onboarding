#!/usr/bin/env python3
"""U15c: prompt_band_chars over the 80/95 rule, ceiling-only fields.

Fail-first for the Skill 74 half of U15c (design 20-OPUS-PROMPT-TEMPLATE-SYSTEM,
section 8 "Conflict to fix first"). On the base tree every one of these fails:
the 80/95 rule (FLOOR_PCT, TARGET_PCT = 80, 95) floors a 5,200-char H3 prompt at
5,600 (exit 3), passes a 6,900-char H3 prompt as OK, floors a 300-char Suno style
at 800, and floors a 280-char Kling avatar prompt when a max is known.

  (a) 5,200-char H3 prompt -> exit 0 (band floor 5,000)
  (b) 6,900-char H3 prompt -> TRIM warning, never a pass-as-target
  (c) 300-char Suno style -> never BELOW_FLOOR (ceiling only)
  (d) 280-char avatar prompt -> never floored even when a max is known
  (e) the band lives in the 67 catalog rows for minimax-h3/* (Trevor 2026-10-08)

Offline: fake transport, no key, no network, no spend. stdlib only.
Run: (cd tests && HOME="$(mktemp -d)" python3 -m unittest test_prompt_band_u15c -v)
"""
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                  # fakes
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # kie_live_adapter
from fakes import K, make  # noqa: E402

#: The repo's own catalog tree. ONB: <repo>/67-kie-video/models.json.
#: 999: <repo>/installer-registration/helpers/67-kie-video/models.json.
POLICY_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

H3 = "minimax-h3/image-to-video"
H3_ROWS = ("text-to-video", "image-to-video", "reference-to-video")
SUNO = "ai-music-api/generate"
AVATAR = "kling/ai-avatar-standard"
PLAIN = "gpt-image-2-5-sunburst-text-to-image"

BAND = {"floor": 5000, "target_min": 5000, "target_max": 6800, "hard_max": 7000,
        "owner": "Trevor 2026-10-08", "below_floor": "FLAG_AND_EXPAND",
        "above_target": "TRIM", "above_hard_max": "REFUSE"}


def schema(props, required=None):
    """One openapi schema body with the caller's input properties."""
    body = {"type": "object", "required": ["model", "input"], "properties": {
        "model": {"type": "string"},
        "input": {"type": "object", "required": required or ["prompt"],
                  "properties": props}}}
    doc = {"paths": {K.JOB_PATH: {"post": {"requestBody": {"content": {
        "application/json": {"schema": body}}}}}}}
    return (200, {"code": 200, "data": {"model": "x", "openapi": doc}})


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.addCleanup(self._t.cleanup)
        self.empty = os.path.join(self.tmp, "none.json")
        self._old = os.environ.get("KIE_POLICY_ROOT")
        self.addCleanup(self._restore)
        self.policy(os.path.join(self.tmp, "skills"))     # none by default

    def _restore(self):
        if self._old is None:
            os.environ.pop("KIE_POLICY_ROOT", None)
        else:
            os.environ["KIE_POLICY_ROOT"] = self._old

    def policy(self, root):
        os.environ["KIE_POLICY_ROOT"] = root

    def adapter(self, routes, env=None):
        e = {"KIE_LIVE_REGISTRY": self.empty,
             "OPENCLAW_SKILLS_DIR": os.path.join(self.tmp, "skills")}
        e.update(env or {})
        return make(self.tmp, routes, extra_env=e)

    def check(self, a, model, text):
        f = os.path.join(self.tmp, "p.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(text)
        out = io.StringIO()
        rc = K.main(["prompt-budget", "--model", model, "--check",
                     "--prompt-file", f], adapter=a, out=out)
        return rc, json.loads(out.getvalue())

    def budget(self, a, model):
        out = io.StringIO()
        K.main(["prompt-budget", "--model", model], adapter=a, out=out)
        return json.loads(out.getvalue())


class BandData(Base):
    """(e) the band is data in the 67 catalog, not code."""

    def test_band_block_on_every_h3_row(self):
        with open(os.path.join(POLICY_ROOT, "67-kie-video", "models.json"),
                  encoding="utf-8") as f:
            models = json.load(f)["models"]
        rows = [m for m in models if m["family"] == "minimax-h3"]
        self.assertEqual(sorted(m["canonical_model_id"] for m in rows),
                         sorted("minimax-h3/" + t for t in H3_ROWS))
        for m in rows:
            self.assertEqual(m.get("prompt_band_chars"), BAND,
                             m["canonical_model_id"])


class H3Band(Base):
    """(a), (b): Trevor's 5,000-6,800 band overrides the 80/95 rule for H3."""

    def routes(self):
        return [["GET", "/schema", [schema({"prompt": {"type": "string",
                                                       "maxLength": 7000}})]]]

    def test_a_5200_chars_is_in_band_exit_0(self):
        self.policy(POLICY_ROOT)
        a, tr, c = self.adapter(self.routes())
        rc, r = self.check(a, H3, "a" * 5200)
        self.assertEqual((rc, r["data"]["status"]), (0, "OK"), r["warnings"])
        self.assertEqual((r["data"]["floor"], r["data"]["target_min"],
                          r["data"]["target_max"], r["data"]["max"]),
                         (5000, 5000, 6800, 7000))
        self.assertEqual(r["data"]["chars"], 5200)

    def test_b_6900_chars_warns_trim_never_a_pass_as_target(self):
        self.policy(POLICY_ROOT)
        a, tr, c = self.adapter(self.routes())
        rc, r = self.check(a, H3, "a" * 6900)
        self.assertEqual(rc, 0)
        self.assertEqual(r["data"]["status"], "TRIM")
        self.assertNotEqual(r["data"]["status"], "OK")
        self.assertTrue(any("TRIM" in w and "6800" in w for w in r["warnings"]),
                        r["warnings"])

    def test_band_floor_still_refuses_below_5000(self):
        self.policy(POLICY_ROOT)
        a, tr, c = self.adapter(self.routes())
        rc, r = self.check(a, H3, "a" * 4900)
        self.assertEqual((rc, r["data"]["status"]), (3, "BELOW_FLOOR"))
        self.assertEqual(r["data"]["floor"], 5000)
        self.assertEqual(r["error"]["code"], "prompt_below_floor")
        self.assertIn("FLAG_AND_EXPAND", r["error"]["msg"])
        # the band's own floor is the target minimum: 5,000 chars is in band
        rc, r = self.check(a, H3, "a" * 5000)
        self.assertEqual((rc, r["data"]["status"]), (0, "OK"))

    def test_hard_max_still_refuses(self):
        self.policy(POLICY_ROOT)
        a, tr, c = self.adapter(self.routes())
        rc, r = self.check(a, H3, "a" * 7001)
        self.assertEqual((rc, r["data"]["status"]), (4, "ABOVE_MAX"))
        self.assertEqual(r["data"]["max"], 7000)
        self.assertEqual(r["data"]["cut"], 1)

    def test_band_is_per_model_never_global(self):
        """A model without a band keeps the 80/95 rule (control)."""
        a, tr, c = self.adapter([["GET", "/schema", [schema({"prompt": {"type": "string",
                                                                       "maxLength": 1000}})]]])
        rc, r = self.check(a, PLAIN, "a" * 800)
        self.assertEqual((rc, r["data"]["status"]), (0, "BELOW_TARGET"))
        rc, r = self.check(a, PLAIN, "a" * 799)
        self.assertEqual((rc, r["data"]["status"]), (3, "BELOW_FLOOR"))
        # ...while H3 in the same test uses the band
        self.policy(POLICY_ROOT)
        a, tr, c = self.adapter(self.routes())
        rc, r = self.check(a, H3, "a" * 5200)
        self.assertEqual((rc, r["data"]["status"]), (0, "OK"))


class CeilingOnly(Base):
    """(c), (d): the Suno style and the Kling avatar prompt are never floored."""

    def test_c_suno_style_300_chars_not_below_floor(self):
        a, tr, c = self.adapter([["GET", "/schema", [schema(
            {"style": {"type": "string", "maxLength": 1000, "description": "Music style."},
             "lyrics": {"type": "string", "maxLength": 5000},
             "prompt": {"type": "string", "maxLength": 5000}})]]])
        rc, r = self.check(a, SUNO, "a" * 300)
        self.assertEqual(rc, 0, r.get("error"))
        self.assertEqual(r["data"]["field"], "style")
        self.assertIn(r["data"]["status"], ("CEILING_ONLY", "OK"))
        self.assertIsNone(r["data"]["floor"])
        self.assertFalse(any("BELOW_FLOOR" in w for w in r["warnings"]), r["warnings"])
        self.assertEqual((r["data"]["max"], r["data"]["chars"]), (1000, 300))
        # the ceiling itself is still enforced
        rc, r = self.check(a, SUNO, "a" * 1001)
        self.assertEqual((rc, r["data"]["status"]), (4, "ABOVE_MAX"))

    def test_d_avatar_prompt_never_floored_even_with_a_known_max(self):
        a, tr, c = self.adapter([["GET", "/schema", [schema(
            {"prompt": {"type": "string", "maxLength": 2500}})]]])
        rc, r = self.check(a, AVATAR, "a" * 280)
        self.assertEqual(rc, 0, r.get("error"))
        self.assertEqual(r["data"]["status"], "CEILING_ONLY")
        self.assertIsNone(r["data"]["floor"])
        self.assertEqual(r["data"]["max"], 2500)
        # a published 2,500 max must not create a 2,000 floor
        rc, r = self.check(a, AVATAR, "a" * 1999)
        self.assertEqual(rc, 0, r.get("error"))
        self.assertNotEqual(r["data"]["status"], "BELOW_FLOOR")


if __name__ == "__main__":
    unittest.main(verbosity=2)

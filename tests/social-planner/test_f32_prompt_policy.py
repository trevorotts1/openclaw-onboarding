#!/usr/bin/env python3
"""
test_f32_prompt_policy.py — F32 social-planner prompt structure + length policy
(QC-F32).

Covers:
  - The count rule: len(unicodedata.normalize("NFC", final).strip()) with
    8,999 / 9,000 / 19,000 / 19,001 NFC boundaries (8999+19001 fail; 9000+19000
    pass length but still require semantic QC);
  - Python/TS parity for the counting rule (TS mirror: Array.from(normalized
    .trim()).length) via a shared fixture JSON both implementations agree on;
  - padding rejection (repeated sentences / duplicated n-grams) BEFORE spend;
  - the corrected Agnes logo conflict: identity/logo reference PRESERVES the
    approved mark; style-only reference must not copy subject/text —
    per-reference instructions, never global;
  - policy + spend receipt: hash + count + policy version + provider/model +
    capability source recorded; house band distinct from vendor caps;
  - the pregen gate enforces the band and capability-metadata routing (GPT
    Image 2 + Agnes eligible through verified adapters; Ideogram allowlist gone).

Run:  python3 -m unittest discover -s tests/social-planner -p 'test_f*.py'
"""

import json
import os
import subprocess
import sys
import unittest
import unicodedata

_ONB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED = os.path.join(_ONB_ROOT, "shared-utils")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import social_prompt_compiler as spc  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_GATE = os.path.join(_ONB_ROOT, "35-social-media-planner", "scripts", "pregen_prompt_gate.py")
_FIXTURE = os.path.join(_HERE, "fixtures", "f32_count_parity.json")
_TS_MIRROR = os.path.join(_HERE, "fixtures", "f32_count_mirror.js")
_POLICY = os.path.join(_SHARED, "social_prompt_policy.json")

BRIEF_OK = {
    "objective": "a weekly campaign image",
    "audience": "small business owners",
    "theme": "pipeline confidence",
    "brand_palette": {"primary": "#0B3D2E", "accent": "#C9A24B"},
    "copy": {"on_image_text": "Grow With Confidence"},
    "destination_dimensions": {"platform": "instagram", "ratio": "4:5", "pixels": "1080x1350"},
}


def count(final: str) -> int:
    """THE contract rule."""
    return len(unicodedata.normalize("NFC", final).strip())


def sized(n: int) -> str:
    """A payload of EXACTLY n stripped Unicode chars carrying the mandatory
    brand-safety clause (so only the length rule is under test)."""
    base = "A useful visual decision sentence for the scene. "   # 49 chars
    suffix = " brand-appropriate, appropriate for the client's audience, no suggestive content."
    body = base + "x" * (n - len(base) - len(suffix)) + suffix
    return body


class TestCountRuleBoundaries(unittest.TestCase):
    """8,999 and 19,001 fail; 9,000 and 19,000 pass length (semantic QC still
    required). Measured on NFC-normalized, stripped payloads."""

    def test_count_rule_is_the_contract(self):
        self.assertEqual(count("  Hello  "), 5)
        self.assertEqual(count("🦄🦄"), 2)  # code points, not UTF-16 units
        self.assertEqual(count("café  "), 4)  # NFD pair -> NFC composed

    def test_8999_fails_validate_final(self):
        v = spc.validate_final(sized(8999))
        self.assertFalse(v["ok"])
        self.assertTrue(any("AF-PROMPT-LENGTH" in p and "below" in p for p in v["problems"]),
                        v["problems"])
        self.assertEqual(v["count"], 8999)

    def test_9000_passes_length(self):
        v = spc.validate_final(sized(9000))
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual(v["count"], 9000)
        self.assertEqual(v["house_band"], {"min": 9000, "max": 19000})

    def test_19000_passes_length(self):
        v = spc.validate_final(sized(19000))
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual(v["count"], 19000)

    def test_19001_fails_validate_final(self):
        v = spc.validate_final(sized(19001))
        self.assertFalse(v["ok"])
        self.assertTrue(any("AF-PROMPT-LENGTH" in p and "above" in p for p in v["problems"]),
                        v["problems"])
        self.assertEqual(v["count"], 19001)

    def test_astral_chars_count_as_code_points(self):
        # 4500 unicorn emoji = 4500 code points (9000 UTF-16 units) — must be
        # BELOW the floor when counted as code points.
        v = spc.validate_final("🦄" * 4500)
        self.assertFalse(v["ok"])
        self.assertEqual(v["count"], 4500)


class TestPythonTSParity(unittest.TestCase):
    """Both implementations agree on the shared fixture (contract: Array.from(
    normalized.trim()).length in TypeScript)."""

    def test_fixture_agrees_python(self):
        with open(_FIXTURE, encoding="utf-8") as f:
            fx = json.load(f)
        for case in fx["fixtures"]:
            inp = "x" * case["count"] if case.get("input_kind") == "repeat_x" else case["input"]
            self.assertEqual(count(inp), case["expected"],
                             f"python disagrees on fixture {case['name']}")

    def test_ts_mirror_agrees(self):
        if not os.path.exists(_TS_MIRROR):
            self.skipTest("node mirror fixture not shipped")
        try:
            proc = subprocess.run(["node", _TS_MIRROR, _FIXTURE],
                                  capture_output=True, text=True, timeout=30)
        except FileNotFoundError:
            self.skipTest("node not available on this host")
        self.assertEqual(proc.returncode, 0, f"TS mirror failures:\n{proc.stdout}\n{proc.stderr}")
        lines = [json.loads(l) for l in proc.stdout.strip().splitlines() if l.strip()]
        self.assertTrue(lines)
        for row in lines:
            self.assertTrue(row["ok"], f"TS mirror disagrees on {row['name']}: {row}")


class TestPaddingRejected(unittest.TestCase):
    """Repeated filler is rejected BEFORE spend — expansion adds useful visual
    decisions, never repetitive padding."""

    def test_repeated_sentence_rejected(self):
        padded = ("A unique scene sentence one. " * 200)
        problems = spc.find_padding(padded)
        self.assertTrue(any("AF-PROMPT-PADDING" in p for p in problems), problems)

    def test_duplicated_ngram_ratio_rejected(self):
        padded = "the quick brown fox jumps over the lazy dog. " * 200
        problems = spc.find_padding(padded)
        self.assertTrue(any("AF-PROMPT-PADDING" in p for p in problems), problems)

    def test_genuine_expansion_not_flagged(self):
        r = spc.compile_prompt(dict(BRIEF_OK), "kie", "gpt-image-2-5-sunburst-text-to-image")
        self.assertFalse(any("AF-PROMPT-PADDING" in p for p in r["problems"]),
                         r["problems"])

    def test_short_brief_expands_into_band_without_padding(self):
        # The client supplies one short sentence; the compiler produces the
        # full in-band brief.
        r = spc.compile_prompt({"audience": "dental patients", "theme": "brighter smile"},
                               "agnes", "agnes-image-2.1-flash")
        self.assertTrue(r["ok"], r["problems"])
        self.assertTrue(9000 <= r["count"] <= 19000, r["count"])
        self.assertLess(r["token_estimate"], 19000 // 2)


class TestLogoVsStyleConflict(unittest.TestCase):
    """Corrected Agnes logo rule: identity/logo reference PRESERVES the approved
    mark; style-only reference must not copy subject/text — per-reference."""

    def test_identity_ref_with_style_only_directive_rejected(self):
        brief = {"logo_rules": {"references": [
            {"role": "identity", "name": "client logo",
             "instruction": "use as style reference only, do not copy subjects or text"}]}}
        problems = spc.find_contradictions(brief)
        self.assertTrue(any("AF-PROMPT-CONFLICT" in p for p in problems), problems)

    def test_style_ref_with_preserve_directive_rejected(self):
        brief = {"logo_rules": {"references": [
            {"role": "style", "name": "mood board",
             "instruction": "preserve the approved mark exactly"}]}}
        problems = spc.find_contradictions(brief)
        self.assertTrue(any("AF-PROMPT-CONFLICT" in p for p in problems), problems)

    def test_correct_roles_pass(self):
        brief = {"logo_rules": {"references": [
            {"role": "identity", "name": "client logo",
             "instruction": "reproduce exactly; preserve geometry, colors and wordmark spelling"},
            {"role": "style", "name": "mood board",
             "instruction": "style only for color grading and lighting; do not copy subjects, faces, or text"}]}}
        self.assertEqual(spc.find_contradictions(brief), [])
        blocks = spc.reference_instruction_blocks(brief)
        self.assertEqual(len(blocks), 2)
        self.assertIn("REPRODUCE", blocks[0])
        self.assertIn("do not copy", blocks[1])

    def test_compile_rejects_conflicting_brief_before_spend(self):
        brief = dict(BRIEF_OK)
        brief["logo_rules"] = {"references": [
            {"role": "identity", "name": "logo", "instruction": "treat as style only, do not copy text"}]}
        r = spc.compile_prompt(brief, "agnes", "agnes-image-2.1-flash")
        self.assertFalse(r["ok"])
        self.assertTrue(any("AF-PROMPT-CONFLICT" in p for p in r["problems"]), r["problems"])
        self.assertEqual(r["final_prompt"], "")  # nothing assembled toward spend


class TestPolicyAndReceipt(unittest.TestCase):
    """Policy version, hash, count, provider/model, capability source recorded;
    house band distinct from vendor caps; token budget cannot silently truncate."""

    def test_policy_file_scope_and_band(self):
        with open(_POLICY, encoding="utf-8") as f:
            pol = json.load(f)
        self.assertEqual(pol["house_band"]["min_chars"], 9000)
        self.assertEqual(pol["house_band"]["max_chars"], 19000)
        self.assertIn("SOCIAL PLANNER ONLY", pol["scope"])
        kie = pol["providers"]["kie-gpt-image-2-5"]
        self.assertEqual(kie["vendor_cap_chars"], 20000)  # published schema cap
        agnes = pol["providers"]["agnes-image-2.1-flash"]
        self.assertIsNone(agnes["vendor_cap_chars"])
        self.assertEqual(agnes["cap_status"], "NOT_PUBLISHED")
        self.assertIn("uncertainty", agnes["uncertainty_note"].lower())

    def test_compile_receipt_fields(self):
        r = spc.compile_prompt(dict(BRIEF_OK), "kie", "gpt-image-2-5-sunburst-text-to-image")
        self.assertTrue(r["ok"], r["problems"])
        for field in ("hash", "count", "policy_version", "provider", "model",
                      "capability_source", "token_estimate", "vendor_cap_chars",
                      "vendor_cap_source"):
            self.assertIn(field, r, field)
        self.assertEqual(r["count"], count(r["final_prompt"]))
        self.assertEqual(r["vendor_cap_chars"], 20000)
        self.assertGreater(len(r["hash"]), 0)

    def test_hash_is_stable_and_payload_exact(self):
        v1 = spc.validate_final(sized(9000))
        v2 = spc.validate_final(sized(9000))
        self.assertEqual(v1["hash"], v2["hash"])
        normalized = unicodedata.normalize("NFC", sized(9000)).strip()
        import hashlib
        self.assertEqual(v1["hash"], hashlib.sha256(normalized.encode("utf-8")).hexdigest())

    def test_unrelated_bands_untouched(self):
        bands_path = os.path.join(_ONB_ROOT, "45-design-intelligence-library",
                                  "library", "_system", "prompt-bands.json")
        with open(bands_path, encoding="utf-8") as f:
            bands = json.load(f)
        # pre-existing GIP bands keep their numbers (scoped override only adds)
        self.assertEqual(bands["bands"]["text_bearing_medium"]["min"], 1600)
        self.assertEqual(bands["bands"]["text_bearing_medium"]["max"], 4500)
        self.assertEqual(bands["bands"]["medium"]["min"], 800)
        scoped = bands["bands"]["social_planner_image_scoped_override"]
        self.assertEqual((scoped["min"], scoped["max"]), (9000, 19000))
        self.assertTrue(scoped["hard_fail_closed"])


class TestPregenGateF32(unittest.TestCase):
    """The Skill 35 gate enforces the band boundaries + capability routing."""

    def _run_gate(self, prompt: str, model: str, text_overlay=None):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write(prompt)
            path = f.name
        try:
            # gate requires --avoid-list-file; write one
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                             encoding="utf-8") as af:
                af.write("avoid junk")
                avoid = af.name
            cmd = [sys.executable, _GATE, "check", "--prompt-file", path,
                   "--model", model, "--ratio", "4:5", "--pixels", "1080x1350",
                   "--brand-colors", "#0B3D2E", "--avoid-list-file", avoid]
            if text_overlay:
                cmd += ["--text-overlay", text_overlay]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return proc
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def test_gate_8999_fails_9000_passes(self):
        proc = self._run_gate(sized(8999), "gpt-image-2-5-sunburst-text-to-image")
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("AF-PROMPT-LENGTH", proc.stderr)
        proc = self._run_gate(sized(9000), "gpt-image-2-5-sunburst-text-to-image")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_gate_19000_passes_19001_fails(self):
        proc = self._run_gate(sized(19000), "agnes-image-2.1-flash")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = self._run_gate(sized(19001), "agnes-image-2.1-flash")
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("AF-PROMPT-LENGTH", proc.stderr)

    def test_gate_capability_routing_admits_gpt_image25_and_agnes(self):
        for model in ("gpt-image-2-5-sunburst-text-to-image", "agnes-image-2.1-flash",
                      "ideogram-v3-design"):
            proc = self._run_gate(sized(9000), model)
            self.assertEqual(proc.returncode, 0,
                             f"{model} refused: {proc.stderr}")

    def test_gate_capability_routing_refuses_nano_banana_for_text(self):
        prompt = sized(9000).rstrip() + ' On-image text reads exactly: "Headline Here".'
        proc = self._run_gate(prompt, "nano-banana-2", text_overlay="Headline Here")
        self.assertEqual(proc.returncode, 6, proc.stderr)
        self.assertIn("AF-SM-MODEL-ROUTING", proc.stderr)


if __name__ == "__main__":
    unittest.main()
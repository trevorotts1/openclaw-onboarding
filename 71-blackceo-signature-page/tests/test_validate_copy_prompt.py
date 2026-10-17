#!/usr/bin/env python3
"""Order C3 + C4 tests: validate_public_copy.py leak patterns and
validate_prompt.py anatomy/padding/grade-block enforcement.

C3 probe (from skill-audit §5): a file carrying data-section="Section 2 / P01",
aria-label="Big Bold Pain 1", <h2>The Big Bold Claim</h2>,
<!-- HANDOFF NOTE - NOT FOR PUBLICATION -->, alt="IMG-07 hero", [EVENT_DATE]
must FAIL naming every reason; plain public copy must PASS.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
COPY_SCRIPT = os.path.join(SKILL_ROOT, "scripts", "validate_public_copy.py")
PROMPT_SCRIPT = os.path.join(SKILL_ROOT, "scripts", "validate_prompt.py")
GOOD_PROMPT = os.path.join(HERE, "fixtures", "prompt_good.txt")
GRADE_BLOCK = os.path.join(SKILL_ROOT, "assets", "brand", "signature-grade-block.txt")


def run(script, *args):
    return subprocess.run([sys.executable, script, *args],
                          capture_output=True, text=True, timeout=60)


sys.path.insert(0, HERE)
import fit_prompt  # noqa: E402


C3_PROBE = """<html><body>
<div data-section="Section 2 / P01">
<h2>The Big Bold Claim</h2>
<p aria-label="Big Bold Pain 1">Your mornings disappear.</p>
<!-- HANDOFF NOTE - NOT FOR PUBLICATION -->
<img src="hero.jpg" alt="IMG-07 hero">
<p>Register by [EVENT_DATE].</p>
</div></body></html>
"""

PLAIN_COPY = """<html><body>
<h1>Own Your Week</h1>
<p>Your mornings disappear into other people's fires.</p>
<p>Register now and give your plans a place.</p>
<a href="/register">Apply Now</a>
</body></html>
"""


class TestPublicCopyLeaks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="c3-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_probe_fails_with_every_reason(self):
        probe = self.tmp / "probe.html"
        probe.write_text(C3_PROBE, encoding="utf-8")
        proc = run(COPY_SCRIPT, str(probe))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = proc.stdout
        # Each probe line must produce its own reason.
        self.assertIn("data-section", out)
        self.assertIn("Big Bold Pain 1", out)          # private label in aria-label
        self.assertIn("Big Bold Claim", out)           # private label in visible text
        self.assertIn("HANDOFF", out)                  # note/handoff comment
        self.assertIn("IMG-07", out)                   # image prompt ID in alt
        self.assertIn("[EVENT_DATE]", out)             # bracket placeholder

    def test_bracket_placeholder_is_warn_only_with_test_run(self):
        probe = self.tmp / "probe.html"
        probe.write_text(C3_PROBE, encoding="utf-8")
        proc = run(COPY_SCRIPT, "--test-run", str(probe))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("WARNING", proc.stdout)
        self.assertIn("[EVENT_DATE]", proc.stdout)
        # The bracket placeholder must no longer be a FAIL reason line.
        fail_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("- ")]
        self.assertFalse(any("[EVENT_DATE]" in ln for ln in fail_lines),
                         "bracket placeholder still a FAIL line with --test-run")

    def test_plain_public_copy_passes(self):
        plain = self.tmp / "plain.html"
        plain.write_text(PLAIN_COPY, encoding="utf-8")
        proc = run(COPY_SCRIPT, str(plain))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)


def a_flood(path, count=5000):
    Path(path).write_text("a" * count, encoding="utf-8")
    return str(path)


REPEATED_SENTENCE = "Detailed production prompt control sentence. " * 150


def build_no_grade_prompt(tmpdir, source=GOOD_PROMPT):
    """The source prompt with the Signature Grade Block removed."""
    good = Path(source).read_text(encoding="utf-8")
    grade = Path(GRADE_BLOCK).read_text(encoding="utf-8").rstrip("\n")
    assert grade in good
    out = Path(tmpdir) / "prompt_no_grade.txt"
    out.write_text(good.replace(grade, ""), encoding="utf-8")
    return str(out), grade


def build_no_negative_prompt(tmpdir, source=GOOD_PROMPT):
    """The source prompt with its Do-not statements replaced by two vague lines."""
    good = Path(source).read_text(encoding="utf-8")
    cut = good.index("\nDo not produce flat")
    out = Path(tmpdir) / "prompt_no_negative.txt"
    out.write_text(good[:cut] + "\nAvoid dull colors. Keep it vivid.\n",
                   encoding="utf-8")
    return str(out)


class TestPromptValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="c4-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # The raw fixture is teaching-size (7,591 characters) and cannot
        # pass under the adopted band; the passing form is the FITTED
        # fixture, grown into the band by tests/fit_prompt.py — the
        # suite's standing convention (test_stage_gate.py, verify.sh).
        self.good = fit_prompt.fit_file(GOOD_PROMPT,
                                        self.tmp / "prompt_good_fitted.txt")

    def test_letter_a_flood_fails(self):
        proc = run(PROMPT_SCRIPT, a_flood(self.tmp / "aaaa.txt"))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Padding detected", proc.stdout)
        self.assertIn("Missing canonical element", proc.stdout)

    def test_repeated_sentence_fails(self):
        p = self.tmp / "repeat.txt"
        p.write_text(REPEATED_SENTENCE, encoding="utf-8")
        proc = run(PROMPT_SCRIPT, str(p))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Padding detected", proc.stdout)

    def test_good_fixture_passes(self):
        self.assertTrue(Path(GOOD_PROMPT).exists(), "tests/fixtures/prompt_good.txt missing")
        proc = run(PROMPT_SCRIPT, self.good)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)

    def test_good_fixture_passes_sauce_only(self):
        proc = run(PROMPT_SCRIPT, "--sauce-only", self.good)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)

    def test_missing_grade_block_fails_sauce_only(self):
        no_grade, grade = build_no_grade_prompt(self.tmp, self.good)
        self.assertNotIn(grade, Path(no_grade).read_text(encoding="utf-8"))
        proc = run(PROMPT_SCRIPT, "--sauce-only", no_grade)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Grade Block", proc.stdout)

    def test_missing_negative_block_fails(self):
        proc = run(PROMPT_SCRIPT, build_no_negative_prompt(self.tmp, self.good))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("negative block", proc.stdout)


_SYL = ["ba", "ko", "ri", "mu", "te", "sa", "no", "vi",
        "la", "pe", "do", "xu", "fi", "ga", "hu", "ze"]


def _gword(n):
    a, b, c = n % 16, (n // 16) % 16, (n // 256) % 16
    return _SYL[a] + _SYL[b] + _SYL[c] + "n"


def grow_to(text, target_chars):
    """Insert distinct art-direction sentences into Element J's prose,
    before its Do-not statements, until the text measures exactly
    target_chars under the validator's counting convention
    (NFC-normalized, trimmed). Every sentence carries unique generated
    words, so no 8-word sequence, 60-character substring, or
    vocabulary pattern repeats and the padding screens stay silent.
    The final filler line is trimmed to land on the target to the
    character, because the band tests assert the exact ADD and CUT
    counts the validator reports."""
    anchor = "\nDo not produce flat"
    head, tail = text.split(anchor, 1)
    raw_target = target_chars + (len(text) - len(text.strip()))
    i = 0
    while len(head) + len(anchor) + len(tail) < raw_target:
        ws = [_gword(i * 10 + k) for k in range(10)]
        sentence = (f"Beat {i}: the {ws[0]} {ws[1]} beside the {ws[2]} keeps "
                    f"the {ws[3]} light specific to scene {i}, with {ws[4]} "
                    f"shadow, {ws[5]} air, {ws[6]} texture on the {ws[7]} "
                    f"wall, and {ws[8]} {ws[9]} detail.\n")
        room = raw_target - (len(head) + len(anchor) + len(tail))
        if len(sentence) > room:
            filler = (f"Beat {i}: " + " ".join(_gword(i * 10 + k)
                                               for k in range(60)))
            head += (filler[:room - 1] + "\n") if room > 1 else filler[:room]
            break
        head += sentence
        i += 1
    return head + anchor + tail


SMALL_COMPLETE = """ASSET: editorial photograph | BAND: visual_long. One standalone scene image for the page.
SUBJECT + SCENE: One woman at one dining table at one interrupted moment, the room lived-in and plausible.
COMPOSITION GRID: Subject in the middle-right zone; text-safe zone upper-left; crop-safe margins of 5-10 percent.
STYLE BLOCK: One locked creative direction governs this page and no second family is imported anywhere.
TYPOGRAPHY + VERBATIM COPY: No text, no letters, no words anywhere in the image.
LIGHTING + COLOR GRADE: One motivated window key, gentle fill, protected highlights, deliberate grade.
PEOPLE / REPRESENTATION: One fictional adult, believable hands, natural unperformed expression, honest posture.
LOGO / REFERENCE DIRECTIVE: No logo is approximated on any surface; references are style-only here.
TECHNICAL: One independent master image; save the unmodified master file under its recorded name.
NEGATIVE BLOCK:
Do not produce flat, muted, pastel, desaturated, or low-contrast color.
Do not distort hands, eyes, or teeth.
Do not render any text, letters, or words anywhere in the image.
Do not invent or mutate any brand logo.
Do not render placeholder blocks or lorem text.
Do not add any watermark, caption, or badge.
"""


class TestPartCBudget(unittest.TestCase):
    """Amendment 6 Part C as superseded by owner Decision 1
    (2026-10-15): the KIE rule 12 band (95 to 100 percent target,
    80 percent floor) is the skill's native authoring target and
    governs length; element completeness still governs acceptance;
    cap_status survives as provenance only; the 2,000-character
    tripwire is retained for models with no recorded maximum. (The
    Part C no-floor tests this class used to carry encoded the
    withdrawn length position and are re-pinned to the band at equal
    or greater strength.)"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="partc-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.base = Path(GOOD_PROMPT).read_text(encoding="utf-8")

    def _write(self, name, text):
        p = self.tmp / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_below_floor_fails(self):
        path = self._write("p75.txt", grow_to(self.base, 15000))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("ADD at least 1000 chars", proc.stdout)
        self.assertIn("budget exit 3", proc.stdout)

    def test_above_max_fails_with_cut_count(self):
        path = self._write("p103.txt", grow_to(self.base, 20600))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("CUT exactly 600 chars", proc.stdout)
        self.assertIn("budget exit 4", proc.stdout)

    def test_in_band_prompt_passes(self):
        path = self._write("p97.txt", grow_to(self.base, 19400))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("in band, budget exit 0", proc.stdout)

    def test_below_target_warns_but_passes(self):
        path = self._write("p85.txt", grow_to(self.base, 17000))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("below the 95 percent target", proc.stdout)

    def test_verified_cap_fails_closed(self):
        policy = {"models": [{"match": "gpt-image-2-5", "max_chars": 5000,
                              "cap_status": "VERIFIED", "unit": "chars"}],
                  "default": {"max_chars": None, "cap_status": "UNKNOWN",
                              "unit": "chars"},
                  "tripwire_chars": 2000}
        policy_path = self._write("policy.json", json.dumps(policy))
        proc = run(PROMPT_SCRIPT, "--policy", policy_path, GOOD_PROMPT)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("VERIFIED", proc.stdout)

    def test_tripwire_flags_short_complete_prompt_without_failing(self):
        # Re-pinned under Decision 1: the tripwire is the operative
        # short-prompt flag only where NO maximum is recorded, so
        # this runs against an explicit UNKNOWN-maximum policy.
        policy = {"models": [],
                  "default": {"max_chars": None, "cap_status": "UNKNOWN",
                              "unit": "chars"},
                  "tripwire_chars": 2000}
        policy_path = self._write("policy_unknown.json", json.dumps(policy))
        path = self._write("small.txt", SMALL_COMPLETE)
        proc = run(PROMPT_SCRIPT, "--policy", policy_path, path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("TRIPWIRE", proc.stdout)

    def test_9500_char_complete_prompt_fails_below_floor_with_telemetry(self):
        path = self._write("p9500.txt", grow_to(self.base, 9500))
        proc = run(PROMPT_SCRIPT, "--json", path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(any("ADD at least" in e for e in data["errors"]),
                        data["errors"])
        self.assertEqual(data["telemetry"]["characters"], 9500)
        self.assertEqual(data["telemetry"]["percent_of_max"], 47.5)
        budget = data["telemetry"]["budget"]
        self.assertEqual(budget["status"], "BELOW_FLOOR")
        self.assertEqual(budget["budget_exit"], 3)
        self.assertEqual(budget["floor"], 16000)
        self.assertEqual(budget["target_min"], 19000)
        self.assertEqual(budget["add_chars"], 6500)

    def test_padded_prompt_fails_on_padding_not_length(self):
        anchor = "\nDo not produce flat"
        head, tail = self.base.split(anchor, 1)
        padded = head + ("The same generic sentence about beautiful light "
                         "and nice colors repeated without any new "
                         "direction. " * 120) + anchor + tail
        path = self._write("padded.txt", padded)
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Padding detected", proc.stdout)


class TestRatioConfirmation(unittest.TestCase):
    """Item 4 part 3: the requested aspect ratio is confirmed at
    validate time against the model's aspect-ratio enum in Skill
    74's registry snapshot. The live default model's enum carries
    21:9 and 16:9; 7:3 is not in it."""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("vp_ratio",
                                                      PROMPT_SCRIPT)
        self.vp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.vp)
        base = Path(GOOD_PROMPT).read_text(encoding="utf-8")
        self.text = grow_to(base, 19400)  # in band: no budget noise

    def _ctx(self, entry):
        return {"inventory_entry": entry, "image_id": "IMG-001"}

    def test_ratio_in_enum_confirmed(self):
        result = self.vp.inspect(
            self.text, ctx=self._ctx({"requested_ratio": "21:9"}))
        record = result["telemetry"]["ratio_confirmation"]
        self.assertEqual(record["status"], "confirmed")
        self.assertEqual(record["requested_ratio"], "21:9")
        self.assertEqual(result["errors"], [], result["errors"])

    def test_ratio_not_in_enum_fails_by_name(self):
        result = self.vp.inspect(
            self.text, ctx=self._ctx({"requested_ratio": "7:3"}))
        record = result["telemetry"]["ratio_confirmation"]
        self.assertEqual(record["status"], "not_in_enum")
        self.assertTrue(
            any("7:3" in e and "aspect-ratio enum" in e
                for e in result["errors"]), result["errors"])

    def test_ratio_not_recorded(self):
        result = self.vp.inspect(self.text, ctx=self._ctx({}))
        record = result["telemetry"]["ratio_confirmation"]
        self.assertEqual(record["status"], "not_recorded")
        self.assertEqual(result["errors"], [], result["errors"])

    def test_ratio_unverified_for_unknown_model(self):
        result = self.vp.inspect(
            self.text, model="no-such-model-xyz",
            ctx=self._ctx({"requested_ratio": "21:9"}))
        record = result["telemetry"]["ratio_confirmation"]
        self.assertEqual(record["status"], "unverified")
        self.assertEqual(result["errors"], [], result["errors"])
LOGO_SHA = "a" * 64
PHOTO_SHA = "b" * 64


def supplied_record(image_id, sha, ratio_value, **overrides):
    """A canonical supplied-asset record (references/artifact-contracts.md)."""
    lines = {
        "heading": "SUPPLIED ASSET RECORD",
        "image": f"Image: {image_id}",
        "source": "Source: supplied",
        "sha": f"SHA-256: {sha}",
        "ratio": f"Aspect ratio: {ratio_value}",
        "declaration": "This asset is supplied by the owner as an existing "
                       "asset; it is not a generation prompt.",
        "generation": "Generation: NONE. No generation was performed for "
                      "this asset, and none is permitted; the supplied "
                      "asset is never generated and never substituted.",
    }
    lines.update(overrides)
    return "\n".join(lines.values()) + "\n"


class TestSuppliedAssetRecords(unittest.TestCase):
    """Item 3 supplied-asset path in validate_prompt.py: an inventory
    entry whose source begins with "supplied" makes the stage file a
    supplied-asset record, validated against the inventory entry and
    exempt from style-selection governance and the prompt pipeline."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="supplied-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_dir = self.tmp / "run"
        inv = {"images": [
            {"id": "IMG-001", "source": "supplied-logo",
             "sha256": LOGO_SHA, "requested_ratio": "1:1"},
            {"id": "IMG-002"},
            {"id": "IMG-012", "source": "supplied-founder-photo",
             "sha256": PHOTO_SHA, "requested_ratio": "4:5"},
        ]}
        p = self.run_dir / "desktop-wireframe" / "image-inventory.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(inv), encoding="utf-8")
        # The selection governs ONLY the generated entry; the supplied
        # entries are deliberately ungoverned.
        sel = {"schema_version": 1, "selections": [
            {"applies_to": ["IMG-002"], "source_library": "photographers",
             "style_id": "some-style", "branded_name": "Some Style"}]}
        p = self.run_dir / "image-inventory-prompts" / "style-selection.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(sel), encoding="utf-8")

    def stage_file(self, name, text):
        p = self.run_dir / "image-inventory-prompts" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_supplied_logo_record_passes_naming_the_exception(self):
        path = self.stage_file("IMG-001.txt",
                               supplied_record("IMG-001", LOGO_SHA, "1:1"))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)
        self.assertIn("supplied asset", proc.stdout)
        self.assertIn("IMG-001", proc.stdout)
        self.assertIn("supplied-logo", proc.stdout)

    def test_supplied_founder_photo_record_passes(self):
        path = self.stage_file("IMG-012.txt",
                               supplied_record("IMG-012", PHOTO_SHA, "4:5"))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("supplied-founder-photo", proc.stdout)

    def test_supplied_record_json_marks_supplied_asset(self):
        path = self.stage_file("IMG-001.txt",
                               supplied_record("IMG-001", LOGO_SHA, "1:1"))
        proc = run(PROMPT_SCRIPT, "--json", path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["supplied_asset"])
        self.assertEqual(data["errors"], [])

    def test_wrong_sha_fails_by_name(self):
        path = self.stage_file("IMG-001.txt",
                               supplied_record("IMG-001", "c" * 64, "1:1"))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("sha256", proc.stdout)
        self.assertIn(LOGO_SHA, proc.stdout)

    def test_missing_no_generation_declaration_fails_by_name(self):
        path = self.stage_file(
            "IMG-001.txt",
            supplied_record("IMG-001", LOGO_SHA, "1:1",
                            generation="Generation: handled upstream."))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("no-generation declaration", proc.stdout)

    def test_missing_aspect_ratio_fails_by_name(self):
        path = self.stage_file(
            "IMG-001.txt",
            supplied_record("IMG-001", LOGO_SHA, "1:1", ratio="Filed at "
                            "whatever size the owner sent."))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("aspect ratio", proc.stdout)

    def test_record_naming_another_image_fails_by_name(self):
        path = self.stage_file("IMG-001.txt",
                               supplied_record("IMG-009", LOGO_SHA, "1:1"))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("image id", proc.stdout)

    def test_record_without_supplied_declaration_fails_by_name(self):
        # Every line scrubbed of the word "supplied": the sha, ratio and
        # no-generation lines stay valid, so the only failure is the
        # missing supplied declaration itself.
        path = self.stage_file(
            "IMG-001.txt",
            supplied_record("IMG-001", LOGO_SHA, "1:1",
                            heading="ASSET RECORD",
                            source="Source: owner files",
                            declaration="This asset is on file with the "
                                        "owner and is not a generation "
                                        "prompt.",
                            generation="Generation: NONE. No generation "
                                       "was performed for this asset."))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("declare", proc.stdout)

    def test_inventory_entry_without_sha_cannot_validate(self):
        inv_path = self.run_dir / "desktop-wireframe" / "image-inventory.json"
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        inv["images"].append({"id": "IMG-020", "source": "supplied-photo",
                              "requested_ratio": "3:2"})
        inv_path.write_text(json.dumps(inv), encoding="utf-8")
        path = self.stage_file("IMG-020.txt",
                               supplied_record("IMG-020", "d" * 64, "3:2"))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("records no sha256", proc.stdout)

    def test_generated_entry_record_shape_does_not_take_supplied_path(self):
        # IMG-002 has no supplied source: a record-shaped file for it
        # still goes through the prompt pipeline and fails there.
        path = self.stage_file("IMG-002.txt",
                               supplied_record("IMG-002", LOGO_SHA, "1:1"))
        proc = run(PROMPT_SCRIPT, path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("is a supplied asset", proc.stdout)


if __name__ == "__main__":
    unittest.main()

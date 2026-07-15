#!/usr/bin/env python3
"""
test_pregen_prompt_gate.py — proves pregen_prompt_gate.py (P3-05 steps 4i/8/9) THROUGH THE
REAL CLI (subprocess), fail-first: every REFUSAL case is also proven to PASS once the single
defect it targets is fixed, so a broken/no-op gate cannot silently keep the test green.

Cases (mirror the P3-05 (e) QC break-it probes verbatim):
  1. A prompt missing its pixel spec / avoid-list -> refused (exit 3, AF-SM-PROMPT-FORM),
     no generation call implied (the script never touches a network).
  2. A Section-18 text-overlay prompt routed to Nano Banana -> now IMPOSSIBLE (exit 6,
     AF-SM-MODEL-ROUTING) — the exact §8 model-table gap the P3-05 root cause names.
  3. The SAME text-overlay prompt routed to Ideogram V3 DESIGN with every FORM field
     present -> PASSES (exit 0) — proves case 2 was really about routing, not a fluke.
  4. An "ungated" graphics-department asset (no QC receipt) -> refused (exit 6,
     AF-SM-INPUT-QC-GATE); the SAME asset with a >=8.5 SOP-GIP-02 receipt -> passes.
  5. A non-text (no --text-overlay) prompt on Nano Banana 2 -> passes (routing rule only
     applies to text-overlay deliverables — Nano Banana stays legitimate for photoreal work).
  6. GK-20 (band<->routing reconciliation, 2026-07-15): a text-overlay prompt SIZED TO the
     Graphics department's `text_bearing_medium` GIP band floor (prompt-bands.json, the
     ONLY text-bearing band naming an Ideogram endpoint) routed to `ideogram-v3-design`
     -> PASSES this gate too (exit 0) -- proves the BINARY acceptance criterion that the
     SAME reconciled-band prompt clears BOTH `diu_validator.py prompt-band` (see
     test_prompt_band_cli.py case 5) AND `pregen_prompt_gate.py check`, not just one.

Run:  python3 test_pregen_prompt_gate.py
Exit: 0 = every assertion passed; 1 = a case failed.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE / "pregen_prompt_gate.py"

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS: {label}")
    else:
        print(f"  FAIL: {label}" + (f" — {detail}" if detail else ""))
        FAILURES.append(label)


def _write(tmpdir: Path, name: str, content: str) -> Path:
    p = tmpdir / name
    p.write_text(content, encoding="utf-8")
    return p


def run_gate(*extra_args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(GATE), "check", *extra_args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


_COMPLIANT_PROMPT_BODY = (
    "A warm editorial photo of a confident founder at a walnut desk, brand-appropriate, "
    "appropriate for the client's audience, no suggestive content. On-image text reads "
    "exactly: \"Three Moves That Doubled Our Pipeline\"."
)
_AVOID_LIST = (
    "Do not render misspelled text. Do not distort the logo. Do not add extra fingers. "
    "Do not cover the subject's face with text."
)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        print("=== 1. missing pixel spec + missing avoid-list -> exit 3, AF-SM-PROMPT-FORM ===")
        p1 = _write(tmp, "p1.txt", _COMPLIANT_PROMPT_BODY)
        r1 = run_gate(
            "--prompt-file", str(p1), "--model", "ideogram-v3-design",
            "--ratio", "4:5", "--brand-colors", "#0B3D2E,#F5EFE0",
            "--text-overlay", "Three Moves That Doubled Our Pipeline",
            # deliberately NO --pixels, NO --avoid-list-file
        )
        check("exit code is 3", r1.returncode == 3, f"got {r1.returncode}, stderr={r1.stderr!r}")
        check("stderr names AF-SM-PROMPT-FORM", "AF-SM-PROMPT-FORM" in r1.stderr, r1.stderr)
        check("stderr flags the missing pixel spec", "--pixels" in r1.stderr, r1.stderr)
        check("stderr flags the missing avoid-list", "avoid-list" in r1.stderr, r1.stderr)
        check("stdout carries no OK: (nothing implied as ready to generate)",
              "OK:" not in r1.stdout, r1.stdout)

        print("\n=== 2. text-overlay prompt routed to Nano Banana 2 -> exit 6, AF-SM-MODEL-ROUTING (now IMPOSSIBLE) ===")
        p2 = _write(tmp, "p2.txt", _COMPLIANT_PROMPT_BODY)
        avoid_file = _write(tmp, "avoid.txt", _AVOID_LIST)
        r2 = run_gate(
            "--prompt-file", str(p2), "--model", "nano-banana-2",
            "--ratio", "4:5", "--pixels", "1080x1350",
            "--brand-colors", "#0B3D2E,#F5EFE0",
            "--text-overlay", "Three Moves That Doubled Our Pipeline",
            "--avoid-list-file", str(avoid_file),
        )
        check("exit code is 6", r2.returncode == 6, f"got {r2.returncode}, stderr={r2.stderr!r}")
        check("stderr names AF-SM-MODEL-ROUTING", "AF-SM-MODEL-ROUTING" in r2.stderr, r2.stderr)
        check("stderr names Ideogram V3 DESIGN as the required route",
              "Ideogram V3 DESIGN" in r2.stderr, r2.stderr)

        print("\n=== 3. SAME text-overlay prompt routed to Ideogram V3 DESIGN, all FORM fields present -> exit 0 ===")
        r3 = run_gate(
            "--prompt-file", str(p2), "--model", "ideogram-v3-design",
            "--ratio", "4:5", "--pixels", "1080x1350",
            "--brand-colors", "#0B3D2E,#F5EFE0",
            "--text-overlay", "Three Moves That Doubled Our Pipeline",
            "--avoid-list-file", str(avoid_file),
        )
        check("exit code is 0", r3.returncode == 0, f"got {r3.returncode}, stderr={r3.stderr!r}")
        check("stdout confirms OK", r3.stdout.strip().startswith("OK:"), r3.stdout)

        print("\n=== 4a. graphics-department asset with NO QC receipt -> exit 6, AF-SM-INPUT-QC-GATE ===")
        r4a = run_gate(
            "--prompt-file", str(p2), "--model", "ideogram-v3-design",
            "--ratio", "4:5", "--pixels", "1080x1350",
            "--brand-colors", "#0B3D2E,#F5EFE0",
            "--text-overlay", "Three Moves That Doubled Our Pipeline",
            "--avoid-list-file", str(avoid_file),
            "--asset-source", "graphics-department",
        )
        check("exit code is 6", r4a.returncode == 6, f"got {r4a.returncode}")
        check("stderr names AF-SM-INPUT-QC-GATE", "AF-SM-INPUT-QC-GATE" in r4a.stderr, r4a.stderr)

        print("=== 4b. SAME asset with a low-score receipt (7.0) -> still refused ===")
        low_receipt = _write(tmp, "low_receipt.json", json.dumps({"pass": True, "average": 7.0}))
        r4b = run_gate(
            "--prompt-file", str(p2), "--model", "ideogram-v3-design",
            "--ratio", "4:5", "--pixels", "1080x1350",
            "--brand-colors", "#0B3D2E,#F5EFE0",
            "--text-overlay", "Three Moves That Doubled Our Pipeline",
            "--avoid-list-file", str(avoid_file),
            "--asset-source", "graphics-department",
            "--qc-receipt-file", str(low_receipt),
        )
        check("low-score (7.0 < 8.5) receipt still refused (exit 6)", r4b.returncode == 6,
              f"got {r4b.returncode}")

        print("=== 4c. SAME asset with a >=8.5 passing receipt -> exit 0 ===")
        good_receipt = _write(tmp, "good_receipt.json", json.dumps({"pass": True, "average": 8.9}))
        r4c = run_gate(
            "--prompt-file", str(p2), "--model", "ideogram-v3-design",
            "--ratio", "4:5", "--pixels", "1080x1350",
            "--brand-colors", "#0B3D2E,#F5EFE0",
            "--text-overlay", "Three Moves That Doubled Our Pipeline",
            "--avoid-list-file", str(avoid_file),
            "--asset-source", "graphics-department",
            "--qc-receipt-file", str(good_receipt),
        )
        check("passing (8.9 >= 8.5) receipt clears the gate (exit 0)", r4c.returncode == 0,
              f"got {r4c.returncode}, stderr={r4c.stderr!r}")

        print("\n=== 5. non-text prompt on Nano Banana 2 -> passes (routing rule is text-overlay-only) ===")
        p5 = _write(tmp, "p5.txt",
                    "A photoreal lifestyle photo of a team collaborating, brand-appropriate, "
                    "appropriate for the client's audience, no suggestive content. No on-image "
                    "text.")
        r5 = run_gate(
            "--prompt-file", str(p5), "--model", "nano-banana-2",
            "--ratio", "9:16", "--pixels", "1080x1920",
            "--brand-colors", "#0B3D2E,#F5EFE0",
            "--avoid-list-file", str(avoid_file),
            # no --text-overlay
        )
        check("exit code is 0 (no text overlay -> Nano Banana stays legitimate)",
              r5.returncode == 0, f"got {r5.returncode}, stderr={r5.stderr!r}")

        print("\n=== 6. GK-20: text_bearing_medium-band-floor-sized prompt, routed to Ideogram V3 DESIGN -> exit 0 ===")
        # A genuinely rich body (>=1,600 chars to clear the Graphics text_bearing_medium GIP
        # floor) carrying the SAME baked headline this gate checks for, plus the mandatory
        # FORM fields and brand-safety clause -- proving the reconciled band and this gate
        # agree on the identical asset, not two independently-tuned thresholds.
        p6_body = (
            "A quote-card graphic for a mid-market services brand, brand-appropriate, "
            "appropriate for the client's audience, no suggestive content. Centered "
            "headline composition with generous negative space reserved for the text "
            "zone; deep forest green and warm cream palette matching the locked brand "
            "style block; brass accent detailing; clean editorial background with no "
            "competing visual elements. On-image text reads exactly: "
            "\"Three Moves That Doubled Our Pipeline\". Spelling lock: render this exact "
            "string, letter-for-letter, correctly spelled, with no added, dropped, "
            "doubled, or substituted characters. Typography set bold serif, centered, "
            "96pt weight 700, generous line height for mobile legibility. Platform crop "
            "safety: the headline sits fully inside the safe zone for a 4:5 crop so no "
            "letterform is clipped on a narrower feed slot. Style reference only: any "
            "attached reference image guides style and mood alone; do not copy "
            "composition or literal content from the reference. Negative block: do not "
            "render any misspelled or garbled text; do not redraw, recolor, or "
            "reinterpret the logo or tagline lockup; do not produce anatomical "
            "artifacts such as a fused hand or extra limb; do not let a cluttered "
            "background compete behind the text zone; do not lighten or desaturate any "
            "deep skin tone; do not add a watermark, emoji, or system default font; do "
            "not drift off-brand or off-palette. Final check: the composition resolves "
            "to one coherent quote-card graphic with no collage or split-frame layout, "
            "and every visible material renders with photographic plausibility rather "
            "than a flat, illustrated look, matching the client's established "
            "photographic house style across the last six months of campaign creative."
        )
        assert len(p6_body.strip()) >= 1600, "fixture must clear the text_bearing_medium GIP floor"
        p6 = _write(tmp, "p6.txt", p6_body)
        r6 = run_gate(
            "--prompt-file", str(p6), "--model", "ideogram-v3-design",
            "--ratio", "4:5", "--pixels", "1080x1350",
            "--brand-colors", "#0B3D2E,#F5EFE0,#C9A24B",
            "--text-overlay", "Three Moves That Doubled Our Pipeline",
            "--avoid-list-file", str(avoid_file),
        )
        check("exit code is 0", r6.returncode == 0, f"got {r6.returncode}, stderr={r6.stderr!r}")
        check("stdout confirms OK", r6.stdout.strip().startswith("OK:"), r6.stdout)

    print()
    if FAILURES:
        print(f"test_pregen_prompt_gate: {len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("test_pregen_prompt_gate: ALL CASES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

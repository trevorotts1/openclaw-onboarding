#!/usr/bin/env python3
"""
test_prompt_band_cli.py — proves the GIP prompt-band gate (diu_validator.py
`prompt-band`) refuses under-floor and under-quality prompts THROUGH THE REAL CLI
(subprocess, no internal-function shortcuts), and passes a genuinely compliant one.

This is the P3-05 (e) QC break-it probe set, run as an actual fail-first test
rather than only described in a QC report. Length is KIE prompt rule 12 (owner order
2026-10-05): 95 to 100 percent of the model maxLength, hard floor 80 percent, hard
ceiling 100 percent, from the shared enforcer (Skill 74 prompt-budget). The real adapter
runs against its registry snapshot (hermetic HOME, no key): GPT Image 2.5 max 20,000.
  1. A 300-char "logo pls" prompt through the `medium` band -> refused, exit 3,
     AF-GIP-PROMPT-FLOOR quoted in stderr with the exact characters to ADD.
  2. A prompt built almost entirely from ONE repeated word, sized INSIDE the length band
     (so only the density tooth can fail it) -> refused, exit 6, AF-GIP-PROMPT-QUALITY.
  3. A genuinely rich, fully-compliant `text_bearing_long` prompt at 97 percent of the max
     (every quality tooth satisfied) -> PASSES, exit 0.
  4. FAIL-FIRST PROOF: case 2 against a deliberately permissive fixture bands file loses
     its density complaint; the length gate does NOT move with the bands file (it is the
     model's, not the band's); and the SAME prompt resized into the band flips from
     refused to PASS, so the refusals are caused by the length rule and nothing else.
  5. Rule 12 boundaries through the real CLI: 79 percent -> exit 3 naming the chars to
     ADD; 101 percent -> exit 3 naming the chars to CUT; 95 and 100 percent length-clear.
  6. The text_bearing_medium Ideogram social band no longer exists (unknown band, exit 2).
  7. `prompt-caps` is ceiling-only (verbatim-style exemption from the floor): a short
     prompt passes, 20,001 characters on GPT Image 2.5 is refused.

Run:  python3 test_prompt_band_cli.py
Exit: 0 = every assertion passed; 1 = a case failed (prints which one).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "diu_validator.py"
sys.path.insert(0, str(HERE))
import prove_gip_prompt_floor as pg  # noqa: E402  (fixture builders sized by percentage of the model max)

MAX = 20000  # GPT Image 2.5 maxLength, the first endpoint of text_bearing_long

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS: {label}")
    else:
        msg = f"  FAIL: {label}" + (f" — {detail}" if detail else "")
        print(msg)
        FAILURES.append(label)


def run_prompt_band(band: str, prompt: str, *, copy: list[str] | None = None,
                     style_ref: bool = False, bands_file: Path | None = None) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(prompt)
        prompt_path = fh.name
    cmd = [sys.executable, str(VALIDATOR), "prompt-band", "--band", band,
           "--prompt-file", prompt_path]
    for c in (copy or []):
        cmd += ["--copy", c]
    if style_ref:
        cmd.append("--style-ref")
    if bands_file:
        cmd += ["--bands-file", str(bands_file)]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    finally:
        Path(prompt_path).unlink(missing_ok=True)


def run_prompt_caps(prompt: str, model: str = "gpt-image-2-5-sunburst-text-to-image") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(VALIDATOR), "prompt-caps", "--model", model, "--prompt", prompt],
                          capture_output=True, text=True, timeout=60)


def main() -> int:
    os.environ["HOME"] = tempfile.mkdtemp()  # hermetic: no key, no cache, the adapter answers from its registry
    os.environ.pop("KIE_API_KEY", None)

    print("=== 1. under-floor: 300-char \"logo pls\" through the `medium` band -> exit 3 ===")
    stub = ("logo pls, make it look nice, modern branding, " * 6)[:300]
    r1 = run_prompt_band("medium", stub)
    check("exit code is 3 (AF-GIP-PROMPT-FLOOR)", r1.returncode == 3, f"got {r1.returncode}, stderr={r1.stderr!r}")
    check("stderr names AF-GIP-PROMPT-FLOOR", "AF-GIP-PROMPT-FLOOR" in r1.stderr, r1.stderr)
    check("stderr names the exact characters to ADD (3000-char Seedream max, floor 2400)",
          f"ADD at least {2400 - len(stub.strip())}" in r1.stderr, r1.stderr)
    check("stub is NOT submitted (stdout carries no OK:)", "OK:" not in r1.stdout, r1.stdout)

    print("\n=== 2. under-density: in-band length, <150 distinct words -> exit 6 ===")
    padded = ("brand image concept " * 1000)[:MAX * 97 // 100].strip()
    r2 = run_prompt_band("text_bearing_long", padded)
    check("exit code is 6 (AF-GIP-PROMPT-QUALITY)", r2.returncode == 6, f"got {r2.returncode}, stderr={r2.stderr!r}")
    check("stderr names AF-GIP-PROMPT-QUALITY", "AF-GIP-PROMPT-QUALITY" in r2.stderr, r2.stderr)
    check("stderr specifically cites the distinct-word density defect",
          "distinct words" in r2.stderr and "band floor 150" in r2.stderr, r2.stderr)
    check("the length gate did NOT fire (the prompt is inside the rule 12 band)",
          "AF-GIP-PROMPT-FLOOR" not in r2.stderr and "AF-DIU-PROMPT-CAP" not in r2.stderr, r2.stderr)

    print("\n=== 3. genuinely compliant text_bearing_long prompt at 97 percent of the max -> exit 0 ===")
    rich = pg.rich_text_bearing(chars=MAX * 97 // 100)
    r3 = run_prompt_band("text_bearing_long", rich, copy=["Stop Guessing. Start Closing."], style_ref=True)
    check("exit code is 0", r3.returncode == 0, f"got {r3.returncode}, stdout={r3.stdout!r}, stderr={r3.stderr!r}")
    check("stdout confirms OK", r3.stdout.strip().startswith("OK:"), r3.stdout)

    print("\n=== 4. fail-first proof: each refusal is caused by the one thing it targets ===")
    permissive = {"bands": {
        "medium": {"min_distinct_words": 0, "text_bearing": False},
        "text_bearing_long": {"min_distinct_words": 0, "text_bearing": True, "endpoints": ["gpt-image-2-5-sunburst-text-to-image"]},
    }}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(permissive, fh)
        permissive_path = Path(fh.name)
    try:
        r2p = run_prompt_band("text_bearing_long", padded, bands_file=permissive_path)
        check("under-density prompt: the density complaint disappears once the fixture's "
              "min_distinct_words is 0", "distinct words" not in r2p.stderr, r2p.stderr)
        r1p = run_prompt_band("medium", stub, bands_file=permissive_path)
        check("under-floor stub: a permissive bands file does NOT relax the length gate "
              "(rule 12 belongs to the model, not the band)", r1p.returncode == 3 and "AF-GIP-PROMPT-FLOOR" in r1p.stderr,
              f"got {r1p.returncode}, stderr={r1p.stderr!r}")
    finally:
        permissive_path.unlink(missing_ok=True)
    over = pg.rich_text_bearing(chars=MAX * 101 // 100)
    r4o = run_prompt_band("text_bearing_long", over, copy=["Stop Guessing. Start Closing."], style_ref=True)
    check("the 101 percent twin of the passing prompt is refused (exit 3)", r4o.returncode == 3, f"got {r4o.returncode}")

    print("\n=== 5. rule 12 boundaries through the real CLI ===")
    low = pg.rich_text_bearing(chars=MAX * 79 // 100)
    r5l = run_prompt_band("text_bearing_long", low, copy=["Stop Guessing. Start Closing."], style_ref=True)
    check("79 percent: exit 3 AF-GIP-PROMPT-FLOOR", r5l.returncode == 3 and "AF-GIP-PROMPT-FLOOR" in r5l.stderr,
          f"got {r5l.returncode}, stderr={r5l.stderr[:300]!r}")
    check("79 percent: names the exact characters to ADD (200)", "ADD at least 200" in r5l.stderr, r5l.stderr)
    check("101 percent: names the exact characters to CUT (200) and AF-DIU-PROMPT-CAP",
          "CUT exactly 200" in r4o.stderr and "AF-DIU-PROMPT-CAP" in r4o.stderr, r4o.stderr)
    for pct in (95, 100):
        rp = run_prompt_band("text_bearing_long", pg.rich_text_bearing(chars=MAX * pct // 100),
                             copy=["Stop Guessing. Start Closing."], style_ref=True)
        check(f"{pct} percent passes (exit 0)", rp.returncode == 0, f"got {rp.returncode}, stderr={rp.stderr[:300]!r}")
    r5old = run_prompt_band("text_bearing_long", pg.rich_text_bearing(chars=9000),
                            copy=["Stop Guessing. Start Closing."], style_ref=True)
    check("the retired 5,000-19,000 band: a 9,000-char prompt is now refused (exit 3)", r5old.returncode == 3,
          f"got {r5old.returncode}")

    print("\n=== 6. the text_bearing_medium Ideogram social band no longer exists ===")
    r6 = run_prompt_band("text_bearing_medium", "x" * 3000)
    check("unknown band -> exit 2", r6.returncode == 2, f"got {r6.returncode}, stderr={r6.stderr!r}")

    print("\n=== 7. prompt-caps is ceiling-only: a short prompt passes, 20,001 chars is refused ===")
    r7a = run_prompt_caps("a short descriptive prompt")
    check("short prompt: exit 0 (no floor on the caps command)", r7a.returncode == 0, f"got {r7a.returncode}, {r7a.stderr!r}")
    r7b = run_prompt_caps("x" * 20001)
    check("20,001 chars: exit 3 AF-DIU-PROMPT-CAP naming the chars to cut",
          r7b.returncode == 3 and "AF-DIU-PROMPT-CAP" in r7b.stderr and "CUT exactly 1" in r7b.stderr, r7b.stderr)

    print()
    if FAILURES:
        print(f"test_prompt_band_cli: {len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("test_prompt_band_cli: ALL CASES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

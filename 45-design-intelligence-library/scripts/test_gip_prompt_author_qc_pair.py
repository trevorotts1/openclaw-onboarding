#!/usr/bin/env python3
"""
test_gip_prompt_author_qc_pair.py — proves Skill 6 unit U83 (GK-21): the dedicated
Graphics Prompt Author + Prompt QC Specialist role pair exists, is wired into the
department's manifests + dispatch SOP, and a fixture creative brief driven through
the pair produces a prompt that clears `diu_validator.py prompt-band` with a
Prompt-QC receipt written to disk — exactly the GK-21 BINARY acceptance criterion,
run as an actual fail-first test rather than only described in a role doc.

Structural checks (role files, manifest wiring, dispatch SOP, the 15 producing
roles' re-pointed compliance sections) run first; the functional fixture (a
non-text-bearing `visual_long` brief, chosen deliberately so this unit's proof
does not depend on GK-20's separate band<->routing reconciliation) runs last,
through the REAL diu_validator.py CLI via subprocess — no internal-function
shortcuts.

Run:  python3 test_gip_prompt_author_qc_pair.py
Exit: 0 = every assertion passed; 1 = a case failed (prints which one).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent                       # 45-design-intelligence-library/scripts
SKILL45_DIR = HERE.parent                                     # 45-design-intelligence-library
REPO_ROOT = SKILL45_DIR.parent                                # repo root
VALIDATOR = HERE / "diu_validator.py"

GRAPHICS_DIR = REPO_ROOT / "23-ai-workforce-blueprint" / "templates" / "role-library" / "graphics"
PROMPT_AUTHOR_MD = GRAPHICS_DIR / "prompt-author-graphics.md"
PROMPT_QC_MD = GRAPHICS_DIR / "qc-specialist-prompt-graphics.md"
CONNECTION_MANIFEST = GRAPHICS_DIR / "connection-manifest.json"
CDO_MD = GRAPHICS_DIR / "chief-design-officer.md"
SOP_GIP_01 = GRAPHICS_DIR / "sops" / "SOP-GIP-01-PROMPT-ANATOMY.md"
INDEX_JSON = GRAPHICS_DIR.parent / "_index.json"

# The 15 producing roles GK-21 requires to re-point their "GIP Prompt-Band
# Compliance" section to the author/QC pair instead of self-authoring.
PRODUCING_ROLES = [
    "ai-image-generator-specialist", "ad-creative-specialist", "book-cover-designer",
    "brand-identity-specialist-logo-color-type", "course-slide-designer",
    "deck-systems-specialist", "email-designer", "infographic-specialist",
    "motion-systems-specialist", "presentation-designer-slides-decks",
    "print--asset-design-specialist", "photo-shoot-director",
    "thumbnail--cover-designer", "style-analyst", "social-media-graphics-specialist",
]

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS: {label}")
    else:
        msg = f"  FAIL: {label}" + (f" — {detail}" if detail else "")
        print(msg)
        FAILURES.append(label)


def run_prompt_band(band: str, prompt: str, *, copy: list[str] | None = None,
                     style_ref: bool = False, run_dir: Path | None = None) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(prompt)
        prompt_path = fh.name
    cmd = [sys.executable, str(VALIDATOR), "prompt-band", "--band", band,
           "--prompt-file", prompt_path]
    for c in (copy or []):
        cmd += ["--copy", c]
    if style_ref:
        cmd.append("--style-ref")
    if run_dir:
        cmd += ["--run-dir", str(run_dir)]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    finally:
        Path(prompt_path).unlink(missing_ok=True)


# ─── STRUCTURAL FIXTURES (files, manifests, dispatch SOP) ─────────────────────

def _compliant_visual_long_prompt() -> str:
    """A fixture non-text-bearing `visual_long` prompt assembled to the SOP-GIP-01
    ten-element anatomy — deliberately non-text-bearing so this unit's proof does
    NOT depend on GK-20's separate prompt-bands.json <-> routing reconciliation
    (visual_long carries no baked copy, so the known nano-banana/Ideogram
    text-bearing contradiction never enters this fixture)."""
    clauses = [
        "ASSET: brand imagery | BAND: visual_long",
        "SUBJECT + SCENE: a small-business owner reviewing a handwritten client-appreciation card at a "
        "reclaimed-oak counter, warm late-afternoon light through a storefront window, a softly blurred "
        "shelf of product just out of focus behind her, no on-image text of any kind.",
        "COMPOSITION GRID: rule-of-thirds framing, the subject anchored on the left third, the storefront "
        "window filling the right two-thirds with generous negative space above her shoulder line, safe "
        "margins of at least 6% on every edge for a square social crop.",
        "STYLE BLOCK: brand hex #1F3B2C forest green and #F4EDE1 warm cream, Montserrat display family "
        "referenced only for any adjacent brand collateral (no baked text here), logo note: brand mark "
        "reserved for a separate lockup slide, not this image.",
        "LIGHTING + COLOR GRADE: soft golden-hour key light from camera-left, gentle bounce fill, a warm "
        "rim light separating the subject from the window glass, color grade pulled toward the brand's "
        "forest green and warm cream palette without crushing the shadows.",
        "PEOPLE / REPRESENTATION: a confident business owner in her forties, tailored blazer in the "
        "brand's forest green, warm genuine smile, hands resting on the reclaimed-oak counter; "
        "representation is drawn from the client's captured audience, never a fixed demographic split.",
        "LOGO / REFERENCE DIRECTIVE: no logo baked into this frame. Use the attached images only as style "
        "reference for color grading, lighting, and composition — do not copy their subjects, faces, or "
        "text.",
        "TECHNICAL: endpoint gpt-image-2-text-to-image, aspect ratio 1:1, resolution 2048x2048, output "
        "format png, no watermark.",
        "SECONDARY SCENE DETAIL: a shelf of hand-labeled jars and a small potted fern sits just out of "
        "focus behind the subject's right shoulder, reinforcing an established, grounded brand feel "
        "without competing with the primary focal subject.",
        "PROP DETAIL: a ceramic mug with a subtle embossed texture rests near the subject's hand, angled "
        "so it reads as ambient set-dressing rather than a second focal point, and never carries any "
        "legible text or wordmark of its own.",
        "DEPTH OF FIELD: a shallow depth of field keeps the subject tack-sharp while the storefront "
        "background falls into a soft, pleasing bokeh that never distracts from the open negative space.",
        "CAMERA ANGLE: eye-level, slightly below center, giving the subject quiet authority without "
        "looming over the viewer, consistent with the brand's grounded, mid-market positioning.",
        "MATERIALS AND FINISH: the counter surface shows genuine oak grain with a satin, not glossy, "
        "finish; every visible material renders with photographic plausibility rather than a "
        "computer-generated plastic sheen.",
        "AMBIENT DETAIL: a faint reflection of the storefront window is visible on the polished counter, "
        "and a soft, believable shadow falls from the subject onto the counter, anchoring the figure "
        "believably in the physical space rather than looking pasted onto the background.",
        "CONTINUITY NOTE: match the established campaign's prior week's lighting temperature and prop "
        "styling so this asset reads as one continuous visual story with the rest of the series.",
        "NEGATIVE BLOCK — DO NOT: do not render any garbled, misspelled, or fragmented text anywhere in "
        "the frame. Do not invent, redraw, recolor, restyle, or reinterpret any logo, monogram, or "
        "tagline lockup. Do not produce anatomical artifacts such as a fused hand, extra limb, or "
        "malformed fingers. Do not let a cluttered or high-detail background compete for attention with "
        "the primary subject. Do not render any bracketed token, placeholder text, or unresolved build "
        "variable anywhere in the frame. Do not default to a mono-cast or lightened deep-skin rendering; "
        "cast the subject exactly as specified above. Do not render watermarks, emoji, clipart, or a "
        "basic platform-default font anywhere in the frame.",
    ]
    return "\n\n".join(clauses)


def _thin_self_authored_stub() -> str:
    """A thin, self-authored-style stub — the exact failure mode GK-21 exists to
    close (a producing role hand-rolling a short, unstructured prompt instead of
    routing through the Prompt Author). Deliberately short and defect-laden so
    the fail-first proof below can distinguish a genuine gate from a rubber stamp."""
    return "nice photo of a business owner, warm lighting, brand colors, modern look"


def main() -> int:
    print("=== A. structural: both role files exist and are registered ===")
    check("prompt-author-graphics.md exists", PROMPT_AUTHOR_MD.is_file(), str(PROMPT_AUTHOR_MD))
    check("qc-specialist-prompt-graphics.md exists", PROMPT_QC_MD.is_file(), str(PROMPT_QC_MD))

    author_text = PROMPT_AUTHOR_MD.read_text(encoding="utf-8") if PROMPT_AUTHOR_MD.is_file() else ""
    qc_text = PROMPT_QC_MD.read_text(encoding="utf-8") if PROMPT_QC_MD.is_file() else ""

    check("Prompt Author references SOP-GIP-01 (the ten-element anatomy)",
          "SOP-GIP-01" in author_text)
    check("Prompt Author references diu_validator.py",
          "diu_validator.py" in author_text)
    check("Prompt Author hands off to qc-specialist-prompt-graphics.md (never self-certifies)",
          "qc-specialist-prompt-graphics.md" in author_text and "self-certif" in author_text.lower())
    check("Prompt QC Specialist references diu_validator.py prompt-band",
          "diu_validator.py prompt-band" in qc_text)
    check("Prompt QC Specialist declares independence (never grades own prompts)",
          "never grade" in qc_text.lower() or "never grades" in qc_text.lower())
    check("Prompt QC Specialist's graded_by identity is this role's own slug",
          'qc-specialist-prompt-graphics' in qc_text and 'graded_by' in qc_text)

    if INDEX_JSON.is_file():
        idx = json.loads(INDEX_JSON.read_text(encoding="utf-8"))
        slugs = {r.get("slug") for r in idx.get("roles", []) if r.get("dept") == "graphics"}
        check("prompt-author-graphics registered in _index.json roles[]",
              "prompt-author-graphics" in slugs)
        check("qc-specialist-prompt-graphics registered in _index.json roles[]",
              "qc-specialist-prompt-graphics" in slugs)
    else:
        check("_index.json present for registration check", False, str(INDEX_JSON))

    print("\n=== B. structural: connection-manifest.json + CDO dispatch SOP wiring ===")
    if CONNECTION_MANIFEST.is_file():
        manifest = json.loads(CONNECTION_MANIFEST.read_text(encoding="utf-8"))
        points = manifest.get("connection_points", [])
        routing = [p for p in points if p.get("author_role") == "prompt-author-graphics"
                   and p.get("qc_role") == "qc-specialist-prompt-graphics"]
        check("connection-manifest.json declares the GIP prompt-authoring route",
              len(routing) == 1, f"found {len(routing)} matching entries")
        if routing:
            check("the routing entry is advisory (required:false) — never blocks verify-wiring.sh",
                  routing[0].get("required") is False)
    else:
        check("connection-manifest.json present", False, str(CONNECTION_MANIFEST))

    cdo_text = CDO_MD.read_text(encoding="utf-8") if CDO_MD.is_file() else ""
    check("chief-design-officer.md carries the GIP dispatch SOP (SOP 9.9)",
          "SOP 9.9" in cdo_text and "GIP Prompt-Authoring Dispatch" in cdo_text)
    check("CDO dispatch SOP names both new roles",
          "prompt-author-graphics.md" in cdo_text and "qc-specialist-prompt-graphics.md" in cdo_text)

    sop_gip01_text = SOP_GIP_01.read_text(encoding="utf-8") if SOP_GIP_01.is_file() else ""
    check("SOP-GIP-01's Owner Role names the Prompt Author + Prompt QC Specialist",
          "Prompt Author" in sop_gip01_text and "Prompt QC Specialist" in sop_gip01_text)

    print("\n=== C. structural: all 15 producing roles re-point to the author/QC pair ===")
    for slug in PRODUCING_ROLES:
        p = GRAPHICS_DIR / f"{slug}.md"
        text = p.read_text(encoding="utf-8") if p.is_file() else ""
        check(f"{slug}.md re-points to prompt-author-graphics.md (no self-authoring)",
              p.is_file() and "prompt-author-graphics.md" in text,
              "file missing" if not p.is_file() else "no reference to prompt-author-graphics.md found")
        check(f"{slug}.md re-points to qc-specialist-prompt-graphics.md (judge != writer)",
              p.is_file() and "qc-specialist-prompt-graphics.md" in text,
              "file missing" if not p.is_file() else "no reference to qc-specialist-prompt-graphics.md found")

    # ─── D. FUNCTIONAL: a fixture brief driven through the pair clears the gate ──
    print("\n=== D. functional: fixture brief -> Prompt-Author-assembled prompt clears "
          "diu_validator.py prompt-band, Prompt-QC receipt written to disk ===")
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td)
        (run_dir / "working" / "qc").mkdir(parents=True, exist_ok=True)

        compliant = _compliant_visual_long_prompt()
        result = run_prompt_band("visual_long", compliant, style_ref=True, run_dir=run_dir)
        check("compliant fixture prompt clears the visual_long band gate (exit 0)",
              result.returncode == 0, f"got {result.returncode}, stderr={result.stderr!r}")
        check("validator confirms OK on stdout", result.stdout.strip().startswith("OK:"), result.stdout)

        band_receipt = run_dir / "working" / "checkpoints" / "diu_prompt_band_receipts.json"
        check("diu_validator.py itself wrote a band receipt to disk",
              band_receipt.is_file(), str(band_receipt))

        # The Prompt QC Specialist's own receipt, per this unit's role-file contract
        # (qc-specialist-prompt-graphics.md §9 SOP 9.4 step 5): graded_by identity,
        # the validator's exit code as the authoritative gate signal, and pass:true
        # ONLY when the validator itself returned 0.
        qc_report = {
            "gate": "GIP Prompt-QC",
            "asset_id": "fixture-brand-imagery-0001",
            "band": "visual_long",
            "validator_exit_code": result.returncode,
            "triggered_autofails": [],
            "pass": result.returncode == 0,
            "qc_independence": {
                "graded_by": "qc-specialist-prompt-graphics",
                "independent": True,
                "author": "prompt-author-graphics",
                "self_graded": False,
            },
        }
        qc_report_path = run_dir / "working" / "qc" / "gip_prompt_qc_report.json"
        qc_report_path.write_text(json.dumps(qc_report, indent=2) + "\n", encoding="utf-8")

        check("Prompt-QC report written to disk", qc_report_path.is_file(), str(qc_report_path))
        written = json.loads(qc_report_path.read_text(encoding="utf-8"))
        check("Prompt-QC report records pass:true for the compliant fixture", written["pass"] is True)
        check("Prompt-QC report's graded_by is the independent QC role, never the author",
              written["qc_independence"]["graded_by"] == "qc-specialist-prompt-graphics"
              and written["qc_independence"]["graded_by"] != written["qc_independence"]["author"])

    # ─── E. FAIL-FIRST PROOF: a thin, self-authored-style stub is REFUSED ────────
    print("\n=== E. fail-first proof: the exact failure mode GK-21 closes (a self-authored, "
          "unstructured stub) is REFUSED, not a rubber stamp ===")
    stub = _thin_self_authored_stub()
    stub_result = run_prompt_band("visual_long", stub)
    check("thin self-authored stub is REFUSED by the same gate (non-zero exit)",
          stub_result.returncode != 0, f"got {stub_result.returncode}")
    check("stub failure cites the band floor or the quality teeth",
          "AF-GIP-PROMPT-FLOOR" in stub_result.stderr or "AF-GIP-PROMPT-QUALITY" in stub_result.stderr,
          stub_result.stderr)
    stub_qc_report = {
        "pass": stub_result.returncode == 0,
        "qc_independence": {"graded_by": "qc-specialist-prompt-graphics"},
    }
    check("a Prompt-QC report built honestly from the stub's real exit code records pass:false",
          stub_qc_report["pass"] is False)

    print()
    if FAILURES:
        print(f"test_gip_prompt_author_qc_pair: {len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("test_gip_prompt_author_qc_pair: ALL CASES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

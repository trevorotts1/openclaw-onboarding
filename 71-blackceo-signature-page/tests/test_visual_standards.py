#!/usr/bin/env python3
"""Item 14: Trevor's example folders are the skill's visual standard set.

Pins four things:
1. The bundled set exists under assets/visual-standards/ and every
   file matches manifest.json byte-for-byte (size + SHA-256) and in
   pixel dimensions, so the set a reviewer opens is provably the set
   Trevor supplied, not a re-render or a resize.
2. The trait lists (W1-W7, M1-M5, H1-H2) are encoded in
   references/qc-contract.md, the wireframe/mockup review criteria
   name them, and the stages whose artifacts a trait list governs
   read the set's README (desktop-wireframe, mobile-tablet,
   visual-mockup, final-mockups). visual-mockup reads it because
   Fix 7 (spec signature-page-fixes, task 2.1) puts the set in front
   of the layout-proof stage as well; the mockup trait list itself
   still binds at final-mockups only (see 3).
3. The reconcile cure's scoping holds: mockup_trait_fidelity applies
   to final-mockups ONLY, so a layout proof with solid-block image
   slots at visual-mockup is not failed by the mockup trait list,
   while the same content at final-mockups is scored and fails
   naming M1.
4. The plan's deficient fixtures fail review on named traits: a
   trait-check record for an unannotated wireframe is rejected
   naming W1, and one for a mockup with a placeholder slot is
   rejected naming M1. Trait evaluation here is the review-record
   rule stated in qc-contract.md; deterministic gate enforcement of
   the traits is Item 15 and is deliberately not claimed here.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SET_DIR = ROOT / "assets" / "visual-standards"

WIREFRAME_TRAITS = ["W1", "W2", "W3", "W4", "W5", "W6", "W7"]
MOCKUP_TRAITS = ["M1", "M2", "M3", "M4", "M5"]
HYBRID_TRAITS = ["H1", "H2"]
ALL_TRAITS = WIREFRAME_TRAITS + MOCKUP_TRAITS + HYBRID_TRAITS


def png_dims(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def trait_failures(record, required):
    """A trait-check record passes only when every required trait is
    recorded 'pass'; failures are returned by trait ID (qc-contract.md,
    'Visual standard set traits')."""
    verdicts = record.get("traits", {})
    return [t for t in required if verdicts.get(t) != "pass"]


def main():
    failures = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail and not ok else ""))
        if not ok:
            failures.append(name)

    # 1. The bundled set, verified against its manifest.
    manifest_path = SET_DIR / "manifest.json"
    check("manifest exists", manifest_path.is_file())
    manifest = json.loads(manifest_path.read_text())
    check("manifest schema", manifest.get("schema") == "skill71-visual-standards/v1")
    check("manifest standard_for names all three artifact kinds",
          manifest.get("standard_for") == ["wireframe", "mockup", "hybrid-board"])
    entries = manifest.get("files", [])
    check("manifest file_count matches entries",
          manifest.get("file_count") == len(entries) and len(entries) == 44,
          f"file_count={manifest.get('file_count')} entries={len(entries)}")
    kinds = {e["kind"] for e in entries}
    check("set covers wireframes, mockups, and the hybrid board",
          any(k.startswith("wireframe") for k in kinds)
          and any(k.startswith("mockup") for k in kinds)
          and "hybrid-board" in kinds, f"kinds={sorted(kinds)}")
    bad = []
    for e in entries:
        f = SET_DIR / e["file"]
        if not f.is_file():
            bad.append(e["file"] + ": missing")
            continue
        data = f.read_bytes()
        if len(data) != e["bytes"]:
            bad.append(e["file"] + ": size drift")
        elif hashlib.sha256(data).hexdigest() != e["sha256"]:
            bad.append(e["file"] + ": sha256 drift")
        elif png_dims(f) != (e["width_px"], e["height_px"]):
            bad.append(e["file"] + ": dimension drift")
    check("every bundled file matches the manifest (bytes, sha256, dimensions)",
          not bad, "; ".join(bad[:5]))
    on_disk = sorted(str(p.relative_to(SET_DIR)) for p in SET_DIR.rglob("*.png"))
    check("no unmanifested PNG files in the set",
          on_disk == sorted(e["file"] for e in entries),
          f"disk={len(on_disk)} manifest={len(entries)}")
    check("set README names the set the standard for the three artifact kinds",
          (SET_DIR / "README.md").is_file()
          and "visual standard" in (SET_DIR / "README.md").read_text().lower())
    check("ANALYSIS.md bundled with the set", (SET_DIR / "ANALYSIS.md").is_file())

    # 2. Traits encoded in the QC contract and review criteria; stages read the set.
    qc = (ROOT / "references" / "qc-contract.md").read_text()
    check("qc-contract has the Visual standard set traits section",
          "## Visual standard set traits (Item 14)" in qc)
    missing = [t for t in ALL_TRAITS if f"- {t}:" not in qc]
    check("qc-contract encodes every trait by ID", not missing,
          "missing: " + ", ".join(missing))
    check("wireframe review criteria name the trait criterion",
          "wireframe_trait_completeness" in qc)
    check("mockup review criteria name the trait criterion",
          "mockup_trait_fidelity" in qc)
    contract = json.loads((ROOT / "references" / "stage-contract.json").read_text())
    for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup", "final-mockups"):
        reads = contract["stages"][stage].get("reads", [])
        check(f"stage {stage} reads the visual standard set",
              any("assets/visual-standards/README.md" in r for r in reads))

    # 2b. Reconcile cure R1: mockup_trait_fidelity is scoped to
    # final-mockups only, as the qc-contract's criterion blocks state.
    def criteria_named(block):
        names = []
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("- `") and "`" in stripped[3:]:
                names.append(stripped[3:stripped.index("`", 3)])
        return names

    shared_block = qc.split("Visual design stages (`visual-mockup`, `final-mockups`)")[1] \
        .split("Final-mockups stage (`final-mockups`) only")[0]
    final_block = qc.split("Final-mockups stage (`final-mockups`) only")[1] \
        .split("Generated images (`image-generation-qc`)")[0]
    shared_criteria = criteria_named(shared_block)
    final_criteria = criteria_named(final_block)

    def criteria_for(stage):
        names = list(shared_criteria)
        if stage == "final-mockups":
            names += final_criteria
        return names

    check("mockup trait criterion appears in exactly one criterion block",
          qc.count("`mockup_trait_fidelity`") == 1
          and "mockup_trait_fidelity" in final_criteria
          and "mockup_trait_fidelity" not in shared_criteria)
    check("mockup_trait_fidelity stage scope is exactly final-mockups (cure R1)",
          "mockup_trait_fidelity" in criteria_for("final-mockups")
          and "mockup_trait_fidelity" not in criteria_for("visual-mockup"))

    def mockup_trait_failures_at(stage, record):
        """Failures the mockup trait list records against a review at a
        stage: the list binds only where mockup_trait_fidelity applies."""
        if "mockup_trait_fidelity" not in criteria_for(stage):
            return []
        return trait_failures(record, MOCKUP_TRAITS)

    layout_proof = {"artifact": "layout proof, solid-block image slots", "traits": {
        "M1": "fail", "M2": "pass", "M3": "pass", "M4": "pass", "M5": "pass"}}
    check("layout proof with solid-block slots at visual-mockup is NOT failed "
          "by the mockup trait list (cure R1)",
          mockup_trait_failures_at("visual-mockup", layout_proof) == [])
    check("the same solid-block content at final-mockups IS scored and fails "
          "naming M1 (cure R1)",
          mockup_trait_failures_at("final-mockups", layout_proof) == ["M1"])

    # 4. Deficient fixtures fail review on named traits.
    unannotated = {"artifact": "wireframe", "traits": {
        "W1": "fail", "W2": "fail", "W3": "pass", "W4": "pass",
        "W5": "fail", "W6": "fail", "W7": "pass"}}
    fails = trait_failures(unannotated, WIREFRAME_TRAITS)
    check("unannotated wireframe fixture fails review naming W1",
          "W1" in fails, f"failures={fails}")
    placeholder_mockup = {"artifact": "mockup", "traits": {
        "M1": "fail", "M2": "pass", "M3": "pass", "M4": "pass", "M5": "pass"}}
    fails = trait_failures(placeholder_mockup, MOCKUP_TRAITS)
    check("placeholder-slot mockup fixture fails review naming M1 (and only M1)",
          fails == ["M1"], f"failures={fails}")
    compliant = {"artifact": "wireframe", "traits": {t: "pass" for t in WIREFRAME_TRAITS}}
    check("fully compliant wireframe record passes the trait rule",
          trait_failures(compliant, WIREFRAME_TRAITS) == [])

    if failures:
        print(f"VISUAL STANDARDS TESTS FAILED: {len(failures)}")
        return 1
    print("ALL PASS: visual standard set (Item 14)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

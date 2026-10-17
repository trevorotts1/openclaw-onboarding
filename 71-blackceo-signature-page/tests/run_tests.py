#!/usr/bin/env python3
"""Run every Skill 71 test module. Exit 0 when all pass; exit 1 on any failure.

Includes the deterministic smoke tests (tests/test_scripts.py) and the
enforcement-order test modules. Playwright-dependent tests self-skip when
Playwright/Chromium is unavailable, so this runner is safe in any environment.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

MODULES = [
    "test_scripts.py",
    "test_validate_visual_direction.py",
    "test_validate_manifest_grade.py",
    "test_stage_gate.py",
    "test_stage_model.py",
    "test_validate_copy_prompt.py",
    "test_render_compare.py",
    "test_validate_page.py",
    # Stream modules registered at integration (S8 assembly, Item 29):
    "test_review_v2.py",
    "test_image_grade_extended.py",
    "test_item10_style_fidelity.py",
    "test_layout_metrics.py",
    "test_validate_copy_structure.py",
    "test_delivery_funnel.py",
    "test_automation_handoff.py",
    "test_automation_receipt.py",
    "test_r71h_fixture.py",
    "test_handoff_contract.py",
    "test_item_gate.py",
    "test_supplied_size_check.py",
    "test_swarm_runner.py",
    "test_browser_hygiene.py",
    "test_shipper.py",
    "test_suppress_fixture.py",
    "test_assembly_integration.py",
    # S71-03 no-offer-pricing gate (packet doc 07 section 3; A06 L1):
    "test_no_offer_pricing.py",
    # Signature Launch S71-05: page-result / page-handoff emission.
    "test_page_result.py",
    "test_launch_profile.py",
    "test_wave1_items_678.py",
    # Update Plan Item 5: stage architecture pins (mockup stage form).
    "test_item5_stage_architecture.py",
    "test_visual_standards.py",
    "test_item11_wireframe_artifact.py",
    "test_item13_production_method.py",
    "test_item12_hybrid_board.py",
    "test_item15_trait_gates.py",
    "test_item25_part_naming.py",
    "test_item16_parity_gate.py",
    "test_item26_delivered_filename.py",
    "test_item20_21_governing_docs.py",
    "test_wave6_items22_24_28.py",
    "test_sync_allowlist.py",
    # Signature Launch S71 A23: per-provider image-generation-qc gate.
    "test_provider_gate_a23.py",
]

def main():
    failures = []
    for mod in MODULES:
        proc = subprocess.run([sys.executable, str(HERE / mod)], text=True)
        if proc.returncode != 0:
            failures.append(mod)
            print(f"FAIL {mod}")
        else:
            print(f"PASS {mod}")
    if failures:
        print(f"TESTS FAILED: {', '.join(failures)}")
        return 1
    print(f"ALL PASS: {len(MODULES)} test modules")
    return 0

if __name__ == "__main__":
    sys.exit(main())

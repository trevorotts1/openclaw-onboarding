# Golden Momentum — Sales Page Assets regression sample

A reusable **golden regression sample** for the Skill 56 Sales Page Assets pipeline (the
Direct-Response sibling of Skill 49): a complete, methodology-faithful DR asset bundle that
PASSES all seven Skill-56 provers and drives the canonical no-skip orchestrator to a signed
`PROCESS-CERTIFICATE.json`.

- **Fictional client:** *The Momentum Engine* by **Marcus Vale** — a self-paced operating-system
  course archetype for solo operators. No real names, brands, URLs, PII, or secrets ship.
  Method attribution: the **Trevor Otts Direct-Response method** (owner attribution only).
- **Asset stack (`copy_ledger.json`):** the 8-section main page in **both A/B variants** (with the
  mandated countdown timer), the Trevor Otts **9-section upsell** in both A/B personas (variant a =
  conversion-copywriter, variant b = emotional-hijacking), a **9-section downsell** recovery page
  (graceful-concession frame), the **Sovereign Architect high-ticket** long-form page (**6,727
  stripped words**, inside the 6,500–7,100 band), and the **40–80-word bump** copy (58 body words)
  ending with the checkbox close.
- **Image plan (`image_plan.json`):** 12 genuinely-authored, distinct prompts, one contiguous
  index set, with every funnel stage slice filled (main / upsell-1 / downsell-1 / high-ticket) —
  the fix for the legacy default-4 slice bug.
- **Provenance (`media_ledger.json`):** every image carries a task id + a GHL-media-host URL; the
  bundle routes the bump to the Skill 44 order-bump seam and terminates on a thank-you step.
- **Delegation seams (attested, never forked here):** image generation → Skill 47 / the client's
  own image provider; GHL media folder/upload + funnel/page build → Skill 6; bump order-form →
  Skill 44. The orchestrator attests those phases in order.

## Content authenticity (systemic fix #8)

Every band is filled with **real, authored persuasive copy** — no repeated filler, no vocabulary
padding, no mid-phrase cutoffs. `build_golden.py --content-check` enforces this in the reproducer
itself: it asserts the high-ticket + bump word bands **and** that no 6-word phrase repeats more
than three times across all authored copy, and that no section body ends on a dangling connective.

## Files

| File | Purpose |
|---|---|
| `brief.json` | Locked, provenance-gated 12-field runtime intake brief (`funnel_type=sales_page_assets`) |
| `image_plan.json` | 12-prompt image plan with full stage-slice coverage |
| `copy_ledger.json` | The 7 copy assets (main a/b, upsell a/b, downsell, high-ticket, bump) with authored copy |
| `media_ledger.json` | Image provenance records (task id + GHL-media host) |
| `funnel-manifest.json` | The Track-2 build bundle Skill 6 reads (labels, ZHC, SEO, fragments, bump route, thank-you) |
| `build_golden.py` | Deterministic reproducer — regenerates every ledger, proves each gate, mints the cert, writes the broken variants + rejection results |
| `working/prover_results.json` | Captured PASS output of the seven Skill-56 provers |
| `delivery/golden-momentum-FINAL/PROCESS-CERTIFICATE.{json,md}` | Issued, signed process certificate (specimen; nonce `golden-momentum-nonce-v1`) |
| `broken-variants/` | Six one-mutation broken variants + `REJECTION-RESULTS.json` proving each fails closed on a DISTINCT autofail |

## Reproduce

```bash
S=56-sales-page-assets
python3 $S/scripts/prove_sp_intake.py           $S/examples/golden-momentum/brief.json                 # PASS (0)
python3 $S/scripts/prove_sp_image_plan.py --plan $S/examples/golden-momentum/image_plan.json            # PASS (0)
python3 $S/scripts/prove_sp_main_structure.py   --ledger $S/examples/golden-momentum/copy_ledger.json   # PASS (0)
python3 $S/scripts/prove_sp_upsell_structure.py --ledger $S/examples/golden-momentum/copy_ledger.json   # PASS (0)
python3 $S/scripts/prove_sp_highticket_band.py  --ledger $S/examples/golden-momentum/copy_ledger.json   # PASS (0)
python3 $S/scripts/prove_sp_bump_band.py        --ledger $S/examples/golden-momentum/copy_ledger.json   # PASS (0)
python3 $S/scripts/prove_sp_bundle.py --manifest $S/examples/golden-momentum/funnel-manifest.json       # PASS (0)

# full deterministic reproduce (regenerate + prove + orchestrate + broken variants):
python3 $S/examples/golden-momentum/build_golden.py                                                     # PASS (0)

# or verify everything (self-tests + golden reproduce + broken rejections) from one gate:
bash $S/verify.sh                                                                                       # PASS (0)
```

`run_method`: **canonical-orchestrator.** `verify.sh` copies the five golden ledgers into a
throwaway run-dir, writes a fresh run-scoped `.spa_run_nonce`, and runs
`run_sales_page_assets.py --run-dir … --nonce …` — the no-skip state machine — which emits a
signed certificate only on all-phases-pass. The delegated P2/P4/P5/P6/P8/P9 phases (image
generation via Skill 47 / the client provider + all GHL media/build via Skill 6 + the Skill 44
bump seam) are attested seams in this repo-only reproduce; their live adapters run on a
provisioned box.

## Broken variants (fail-closed proof)

Each variant is the golden with **one** mutation and trips a **distinct** fail-closed autofail:

| Variant | Defect | Gate | Verdict |
|---|---|---|---|
| A `out_of_band_section` | main variant b sections swapped out of canonical order | `prove_sp_main_structure` | rejected — `AF-SP56-MAIN-SECTION-ORDER` (exit 2) |
| B `high_ticket_word_floor` | high-ticket truncated well under the 6,500-word floor | `prove_sp_highticket_band` | rejected — `AF-SP56-HIGHTICKET-FLOOR` (exit 2) |
| C `bump_out_of_band` | bump body cut under the 40-word floor (checkbox intact) | `prove_sp_bump_band` | rejected — `AF-SP56-BUMP-FLOOR` (exit 2) |
| D `image_slice` | image plan dropped to the legacy default of 4 prompts | `prove_sp_image_plan` | rejected — `AF-SP56-IMGPLAN-SLICE-EMPTY` (exit 2) |
| E `missing_provenance` | run-dir omits `media_ledger.json` (image provenance artifact) | orchestrator P2 seam | rejected — **no certificate** (P2-IMAGES delegated artifact absent) |
| F `unapproved` | brief never locked (human approval withheld) | `prove_sp_intake` | rejected — `AF-SP56-INTAKE-UNLOCKED` (exit 2); through the orchestrator: **no certificate** (P0 abort) |

`broken-variants/REJECTION-RESULTS.json` records each variant's return code, the autofail it
carries, and (for E + F) the orchestrator's fail-closed abort with no certificate.

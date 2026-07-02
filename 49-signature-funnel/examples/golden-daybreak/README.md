# Golden Daybreak — Signature Funnel regression sample

A reusable **golden regression sample** for the Skill 49 Signature Funnel pipeline: a
complete, methodology-faithful **7-step** funnel that PASSES all four Signature-Funnel
provers and drives the canonical no-skip orchestrator to a signed
`PROCESS-CERTIFICATE.json`.

- **Fictional client:** *The Daybreak Method* — a 30-day morning-discipline course
  archetype. No real names, brands, URLs, PII, or secrets ship. Method attribution:
  the Trevor Otts Signature Funnel method (owner attribution only).
- **Funnel size:** **7-step** — the worst case, so the copy gate exercises every page
  profile: `main` → `checkout` (microcopy-only) → `upsell` (OTO1) → `downsell` →
  `upsell-2` (OTO2) → `downsell-2` → `thank-you`.
- **SACRED copy (`copy_ledger.json`):** the full 12-section Trevor Otts Hero on the main
  page (every char/word band in `structure/funnel_structure.json`), Sections 1–7 + the
  renumbered Section-8 replacement on each derived page ("7 Reasons To Commit To Your
  ____ Future" on the two upsells, "When Time Runs Out" on the two downsells, each
  exactly 7 items), and the three-part Thank-You (TY-1 120–180, TY-2 4–6 steps of
  89–116 chars, TY-3 ≤170).
- **Image prompts (`prompt_ledger.json`):** 14 prompts, each 5,000–19,000 stripped
  chars, each carrying the Signature Grade Block fingerprint, a `Do not …` negative
  block, ≥220 distinct words, no em/en dashes; Section 11 is typography-as-art with a
  spelling-lock directive over three baked words (`DECIDE` / `COMMIT` / `RISE`).
- **Provenance + no-pitch (`media_ledger.json`):** every image carries a real Kie
  `taskId` and a GHL-media-host URL; the Thank-You page carries only utility buttons
  (Join The Community / Share With A Friend / Add To Calendar) — no offer name, no
  price, no sale CTA.
- **Delegation seams (attested, never forked here):** image generation → Skill 47
  (`kie_image.py`); GHL media folder/upload + funnel/page build → Skill 6. The
  orchestrator attests those phases in order; provenance is enforced at P9.

## Files

| File | Purpose |
|---|---|
| `brief.json` | Locked, provenance-gated runtime intake brief (7-step; Q1–Q17 answers + truth gate + offer ledger) |
| `copy_ledger.json` | Per-page 12-section SACRED copy ledger (main + checkout + U1/D1/U2/D2 + thank-you) |
| `prompt_ledger.json` | Image-prompt ledger (14 prompts, 5k–19k band) |
| `media_ledger.json` | Image records (Kie taskId + GHL host) + thank-you page (no-pitch gate input) |
| `build_golden.py` | Deterministic reproducer — regenerates every ledger, proves each gate, mints the cert, and writes the broken variants + rejection results |
| `working/prover_results.json` | Captured PASS output of the four Signature-Funnel provers |
| `delivery/golden-daybreak-FINAL/PROCESS-CERTIFICATE.{json,md}` | Issued, signed process certificate (specimen; nonce `golden-daybreak-nonce-v1`) |
| `broken-variants/` | Five one-mutation broken variants + `REJECTION-RESULTS.json` proving each fails closed on a DISTINCT AF-FUN-* |

## Reproduce

```bash
SF=49-signature-funnel
python3 $SF/scripts/prove_sf_intake.py        $SF/examples/golden-daybreak/brief.json          # PASS (0)
python3 $SF/scripts/prove_sf_copy.py   --ledger $SF/examples/golden-daybreak/copy_ledger.json   # PASS (0)
python3 $SF/scripts/prove_sf_prompt_floor.py --ledger $SF/examples/golden-daybreak/prompt_ledger.json  # PASS (0)
python3 $SF/scripts/prove_sf_no_pitch.py --ledger $SF/examples/golden-daybreak/media_ledger.json # PASS (0)

# full deterministic reproduce (regenerate + prove + orchestrate + broken variants):
python3 $SF/examples/golden-daybreak/build_golden.py                                             # PASS (0)

# or verify everything (self-tests + golden reproduce + broken rejections) from one gate:
bash $SF/verify.sh                                                                               # PASS (0)
```

`run_method`: **canonical-orchestrator.** `verify.sh` copies the four golden ledgers
into a throwaway run-dir, writes a fresh run-scoped `.sf_run_nonce`, and runs
`run_signature_funnel.py --run-dir … --nonce …` — the no-skip state machine — which
emits a signed certificate only on all-phases-pass. The delegated P3/P4/P5/P6/P7/P8
phases (Kie image generation + all GHL media/build via Skills 47 and 6) are attested
seams in this repo-only reproduce; their live adapters run on a provisioned box.

## Broken variants (fail-closed proof)

Each variant is the golden with **one** mutation and trips a **distinct** AF code:

| Variant | Defect | Prover | Verdict |
|---|---|---|---|
| A `wrong_section_count` | main page missing Section 3 | `prove_sf_copy` | rejected — `AF-FUN-SECTION-MISSING` (exit 2) |
| B `out_of_band_copy` | Section 1 = 20 chars (under 180) | `prove_sf_copy` | rejected — `AF-FUN-SEC1-CHARBAND` (exit 2) |
| C `image_prompt_too_short` | a prompt under the 5,000-char floor | `prove_sf_prompt_floor` | rejected — `AF-FUN-PROMPT-FLOOR` (exit 2) |
| D `missing_provenance` | an image with a placeholder Kie taskId | `prove_sf_no_pitch` | rejected — `AF-FUN-IMG-PROVENANCE` (exit 2) |
| E `unapproved` | brief never locked (human approval withheld) | `prove_sf_intake` | rejected — `AF-FUN-INTAKE-UNLOCKED` (exit 2); through the orchestrator: **no certificate** (P0 abort) |

`broken-variants/REJECTION-RESULTS.json` records each variant's return code, the AF
code carried, and (for E) the orchestrator's fail-closed abort with no certificate.

# Golden Lumen Rise — Avatar-Alchemist BRAND regression sample

A reusable **golden regression sample** for the Skill 52 Avatar-Alchemist BRAND
pipeline: one complete, methodology-faithful BRAND run that PASSES every
fail-closed prover and drives `aa_delivery_gate.py` to a signed process
certificate — plus five deliberately-broken variants that each fail closed.

- **Fictional client (100% invented, zero PII):** brand *Lumen Rise Collective*,
  founder *Amara Vale*, offer *The Visible Founder Accelerator* — visibility and
  authority coaching for women founders who feel invisible. No real names, brands,
  URLs, or private data ship. (The product's own "Trevor Otts" method attribution
  is the only permitted real name and is not used here.)
- **Version:** `brand` (this skill's 40-stage pipeline). A `book` run does **not**
  run here — it routes to the separate Book skill (53) or parks fail-closed
  `book-skill-not-available` (broken variant 04 proves it).
- **CLIENT-path models only** — `ollama-cloud/*` (TIER-A), `openrouter/deepseek-*`
  (TIER-B), `openrouter/perplexity-sonar` (SEARCH). **Zero Anthropic ids**
  (`G-NOANTHROPIC` / `AF-AV-NOANTHROPIC`).

## Every subsystem is exercised (representative coverage, all 40 stages present)

Every numeric floor/band below is the one in `AA-PIPELINE-MANIFEST.json` `stages[].floors`
(aligned to `MASTERDOC.md`, the single numeric source). This table names WHICH invariant each
subsystem clears, never restated numbers — see the manifest for the exact values.

| Subsystem | Proven by (stage) | Sacred invariant cleared |
|---|---|---|
| avatar-core | `01` Q1-30, `02` Q31-32 search, `03` rewrite, `38` questionnaire | `01`/`03` stripped-word floors (manifest) + Q1-30 header relevance |
| tone (via the shared tone/writing core) | `04`-`07` tone styles → `08` blended tone | `08` stripped-word floor (manifest; R1 fuses the 4 styles) |
| awareness | `09`/`11`/`13` pt1 + `10`/`12`/`14` pt2 | pt1 + pt2 stripped-word floors (manifest) + five-list relevance |
| bios | `16` brand bio, `17` product bio | stripped-word floors (manifest) + labeled `[Section]` format |
| facebook-ads | `15` targeting, `22`-`34` **13 ad sets**, `35` top-39, `37` headline copy | `15` floor (manifest); 13 restored R4 categories; top-39 = 3×13; headline = 12+12+12 |
| booking-bots | `18` prep, `19` booking, `20` post, `21` reschedule | `19` stripped-word floor + per-message stripped-char cap (manifest); H1 `# … Section` + XML labels + `{{contact.*}}` merge tags |
| landing-hero | `39` hero page, `36` + `40` image prompts | hero = 12 sections; image-prompt char band + unique artist per prompt (manifest) |

## Files

| Path | Purpose |
|---|---|
| `build_golden.py` | Deterministic generator: imports the real provers, self-verifies, writes the run + delivery |
| `run/intake.json` | Normalized BRAND intake (version selector + full brand payload) |
| `run/artifacts/<stage>.md` ×40 | The 40 generated stage artifacts |
| `run/receipts/G-STAGE-<stage>.json` ×40 | Foreman receipts (sha256 of each artifact) |
| `run/RUN-LEDGER.json` | Per-stage ledger (status/model/sha256/words) — client models only |
| `delivery/Amara_Vale-FINAL/` | The **16 named deliverables** + `00-INDEX.md` + `MANIFEST.json` + `PROCESS-CERTIFICATE.{json,md}` |
| `broken-variants/make_broken.py` | Applies 5 single-defect mutations, asserts each fails closed |
| `broken-variants/REJECTION-RESULTS.json` | Recorded rejection evidence (rc + AF code + output per variant) |
| `broken-variants/book_intake.json` | Standalone BOOK-version intake fixture (variant 04) |

## Reproduce

```bash
SK=52-avatar-alchemist
GD=$SK/examples/golden-lumen-rise

# 1) regenerate + self-verify the whole golden run (deterministic)
python3 $GD/build_golden.py --self-test

# 2) content prover on the checked-in run-dir  -> PASS (exit 0)
python3 $SK/scripts/aa_build_check.py --run $GD/run

# 3) intake + version gate on the BRAND intake -> PASS (exit 0)
python3 $SK/scripts/aa_intake_gate.py --intake $GD/run/intake.json

# 4) the five broken variants all fail closed  -> exit 0 (all rejected)
python3 $GD/broken-variants/make_broken.py

# everything above is wrapped, idempotent + read-only, by:  bash $SK/verify.sh
```

The certificate in `delivery/Amara_Vale-FINAL/PROCESS-CERTIFICATE.json` is issued by
`aa_delivery_gate.py`: 40/40 receipts whose sha256 matches the artifact bytes,
content gate PASS, independent QC 9.2 (≥ 8.5, verifier ≠ author).

## Broken variants (fail-closed proof)

| # | Variant | Defect | Prover | Verdict |
|---|---|---|---|---|
| 01 | missing-generator | `16-brand-bio` produced nothing | `aa_build_check` | rejected — `AF-AV-STAGE-MISSING` (exit 2) |
| 02 | out-of-band-copy | ad-set-7 category drifts `5 → 2` | `aa_build_check` | rejected — `AF-AV-ADSET-CAT` (exit 2) |
| 03 | image-prompt-too-short | landing image prompts under the 5000-char band | `aa_build_check` | rejected — `AF-AV-IMG-BAND` (exit 2) |
| 04 | book-version-not-routed | `version=book`, no Book skill on box | `aa_intake_gate` | rejected — `AF-AV-BOOK-SKILL-MISSING` (parks `book-skill-not-available`, exit 2) |
| 05 | missing-provenance | artifact edited after its receipt sha256 | `aa_delivery_gate` | **no certificate** — `AF-AV-PROVENANCE` (exit 2) |

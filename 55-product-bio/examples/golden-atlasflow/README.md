# Golden AtlasFlow — Product Bio regression sample

A reusable **golden regression sample** for the Skill 55 Product Bio engine: a
complete, methodology-faithful **master-brain product bio** that PASSES all five
fail-closed provers and drives `product-bio-entry.sh` → `run_product_bio.py` to a
signed process certificate.

- **Fictional subject:** *AtlasFlow* — "the operating system for momentum," a
  workflow-clarity product archetype. **No real client names, brands, URLs, emails,
  or private details ship** (persona *Jordan Rivera*, `ops@example.com`,
  `+1-555-0100` are all invented). Method attribution: the Trevor Otts "Guru-Level
  Product Bio Architect" prompt (own-brand IP, `assets/prompts/01`).
- **Shape (the SACRED contract):** 10 mandatory sections in order · **24** named
  signature-close styles (the tracker's 24 — the prompt teaches 20, PRD O3 enforces
  24) · per-section floors met (10 intros, 15–20 adjectives, 8–10 objections, 10–12
  FAQs, 8–10 social-proof, all 7 StoryBrand beats) · a `COMPLETION VERIFICATION`
  block present.
- **Measured word count: 6,105** (stripped) — inside the 6,000–7,000 band. Note the
  bio's *self-reported* "6500 words" line is **ignored**; the gate measures the real
  stripped words, which is why a whitespace-padding attack cannot fool the floor.
- **HTML:** starts EXACTLY `<!DOCTYPE html>`, ends EXACTLY `</html>`, exactly one
  `<h1>`, no CSS beyond `page-break-after`, 100% content coverage vs the bio.
- **Runtime:** local-only — **zero** n8n / Google Drive / Slack / Gmail. The client's
  own model providers author the two artifacts upstream (NEVER Anthropic on the
  client path); this engine measures + certifies them.

## Files

| File | Purpose |
|---|---|
| `intake.json` | The 4-field intake record (+ optional handoff fields) |
| `product-bio.md` | The master-brain bio (chain-1 artifact) |
| `product-bio.html` | The Google-Docs-importable HTML (chain-2 artifact) |
| `working/{intake.json,product-bio.md,product-bio.html}` | Run-dir artifacts consumed by `run_product_bio.py --run-dir .` |
| `working/prover_results.json` | Captured PASS output of the five provers on this bundle |
| `working/checkpoints/process_manifest.json` | Governed run record (7 phases, all passed) |
| `delivery/PROCESS-CERTIFICATE.{json,md}` | The issued signed certificate (deterministic sha over slug + measured counts + phase chain) |
| `broken-variants/` | Deliberately-broken artifacts + `REJECTION-RESULTS.json` proving each trips a distinct AF, fail-closed |

- **Certificate SHA:** `5311779354e4febb6b4d1d242e258561386c9db163ae260d5e01f7478f4b8470`
  (`measured_word_count` 6105 · `measured_signature_closes` 24 · all 7 phases pass).
  The sha is computed over the slug + measured counts + ordered phase steps (never
  the wall clock), so re-running the same passing artifacts reproduces it exactly.

## Reproduce

```bash
cd 55-product-bio
# Full pipeline through the ONE sanctioned entry (mints a run-scoped nonce, runs the
# 3 entry gates, then the 7-phase machine; issues the certificate on a full pass):
bash product-bio-entry.sh --run-dir examples/golden-atlasflow      # exit 0, cert issued

# Or drive the five provers directly:
S=scripts; EX=examples/golden-atlasflow/working
python3 $S/prove_pb_intake.py    $EX/intake.json                          # PASS (0)
python3 $S/prove_pb_fidelity.py                                           # PASS (0)
python3 $S/prove_pb_wordcount.py $EX/product-bio.md                       # PASS (0)
python3 $S/prove_pb_sections.py  $EX/product-bio.md                       # PASS (0)
python3 $S/prove_pb_html.py      $EX/product-bio.html --source-bio $EX/product-bio.md  # PASS (0)
```

`run_method`: **entry → orchestrator (full pipeline).** Unlike a rendered deck,
the Product Bio pipeline has **no paid/external step** — the two authoring calls run
upstream on the client's own chain and drop `working/product-bio.{md,html}` into the
run dir, so the sanctioned entry runs every phase (P0→P6) cleanly in-environment and
reaches the certificate. `verify.sh` re-proves this bundle in a throwaway temp
run-dir (read-only; it never mutates the shipped example).

## Broken variants (fail-closed proof)

Each file below trips a **distinct** AutoFail code (exit 2); `REJECTION-RESULTS.json`
captures the real prover verdict for every one. The two mandated adversarial vectors
are present: a **whitespace-padding attack** and a **sha-mismatch on the prompt asset**.

| Variant | Defect | Prover | Verdict |
|---|---|---|---|
| `intake_missing.json` | `last_name` is whitespace-only | `prove_pb_intake` | `AF-PB-INTAKE-MISSING` (exit 2) |
| `drifted-prompts/` | 1-byte drift in a baked prompt asset (**sha-mismatch**) | `prove_pb_fidelity` | `AF-PB-PROMPT-DRIFT` (exit 2) |
| `wordcount_short.md` | 2,684-word bio (below the 6,000 floor) | `prove_pb_wordcount` | `AF-PB-WORDCOUNT` (exit 2) |
| `wordcount_whitespace_pad.md` | same 2,684 words padded with blank lines + trailing spaces to look book-length (**whitespace attack**) | `prove_pb_wordcount` | `AF-PB-WORDCOUNT` (exit 2) — stripped measurement defeats it |
| `verify_block_missing.md` | in-band 6,765 words but no `COMPLETION VERIFICATION` block | `prove_pb_wordcount` | `AF-PB-VERIFY-BLOCK` (exit 2) |
| `section_missing.md` | a mandatory section dropped | `prove_pb_sections` | `AF-PB-SECTION` (exit 2) |
| `closes_23.md` | only 23 of the 24 signature closes | `prove_pb_sections` | `AF-PB-CLOSES` (exit 2) |
| `counts_short.md` | a per-section enumerated floor missed | `prove_pb_sections` | `AF-PB-COUNTS` (exit 2) |
| `html_envelope.html` | commentary before `<!DOCTYPE html>` | `prove_pb_html` | `AF-PB-HTML-ENVELOPE` (exit 2) |
| `html_two_h1.html` | two `<h1>` elements | `prove_pb_html` | `AF-PB-HTML-H1` (exit 2) |
| `html_css.html` | custom CSS beyond `page-break-after` | `prove_pb_html` | `AF-PB-HTML-CSS` (exit 2) |
| `html_loss.html` | ~half the bio content lost in conversion | `prove_pb_html` | `AF-PB-HTML-LOSS` (exit 2) |
| `E2E_no_certificate` (in `REJECTION-RESULTS.json`) | a short bio fed to the full runner | `run_product_bio` | **no certificate** — BLOCKED at `P3-BIO-QC` (exit 2) |

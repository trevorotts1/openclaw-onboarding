# Golden worked example — "Unbroken Ground" / contributor Marcus Bell

A complete, real, gated anthology chapter run for a **fictional** anthology
(*Unbroken Ground: Voices from the Second Start*) and a **fictional** contributor
(Marcus Bell). No real client, brand, or person appears anywhere — this is a
regression fixture, not a deliverable.

## What's here
- `working/` — the authored artifacts the pipeline consumes: `intake.json`,
  `tone-doc.md` (the 3,058-word "The Marcus Bell Tone", built from 4 influence
  analyses), `title.json` (the locked title/subtitle), `outline.md`, `chapter.md`
  (a real 2,118-word chapter, "The Weight of the Keys"), and `RUN-LEDGER.json`
  (every resolved model id NON-Anthropic).
- `delivery/PROCESS-CERTIFICATE.json` / `.md` — the signed certificate issued by
  a full P0→P7 pass through `anthology-entry.sh`. Its `certificate_sha` is
  deterministic: re-running the same artifacts reproduces it exactly (this is how
  `verify.sh` proves idempotency).
- `broken-variants/` — one seeded defect per `AF-AW-*` code, plus
  `REJECTION-RESULTS.json` recording that each is rejected (exit 2) with its
  distinct code, and an `E2E_no_certificate` entry proving the orchestrator
  refuses a certificate when a short chapter is seeded.

## Reproduce
```
bash 54-anthology-writer/anthology-entry.sh --run-dir 54-anthology-writer/examples/golden-unbroken-ground
```
(Or run the whole self-verify gate: `bash 54-anthology-writer/verify.sh`.)

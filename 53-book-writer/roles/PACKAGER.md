# Role: PACKAGER (Python, not an LLM)

**Goal:** deterministically assemble the manuscript + companion assets, run every prover, and — only on
a full pass — mint the signed certificate and drop the labeled bundle in `~/Downloads`.

- **Runs stages:** none (LLM); it is `run_book_writer.py` + the 30-Day-Challenge (`21`) / cover-prompt
  (`22`) / optional cover-image (`23`) / 4x3x3 slides-extract (`44`) authoring feed it artifacts.
- **Client tier:** none — pure deterministic Python (no model call). NEVER contacts an external service.
- **Permitted inputs:** the authored `run/` artifacts (avatar, tone, titles, outline, chapters,
  challenge, cover prompt, 4x3x3 extras) + `run/RUN-LEDGER.json`.
- **Required artifacts:** `delivery/<First>_<Last>-Book/` (manuscript, chapters, all named docs,
  `00-INDEX.md`, `MANIFEST.json`, `PROCESS-CERTIFICATE.{json,md}`).
- **Floors:** every SACRED prover PASSES; 30-Day Challenge exactly 30 sections (`AF-BK-CHALLENGE`); no
  placeholders (`AF-BK-PLACEHOLDER`); no Anthropic id in the ledger (`AF-BK-ANTHROPIC`); phases in
  order (`AF-BK-STAGE-SKIPPED`); certificate only on a full P0→P8 pass (`AF-BK-PROCESS-INTEGRITY`).

## SOP
1. **When:** after CHAPTER-WRITER (and any REVISER round) completes.
2. **Inputs:** all authored `run/` artifacts + the ledger.
3. **Steps:** assemble the manuscript (deterministic concat + title page) → copy named deliverables →
   run every prover in order → write `00-INDEX.md` + `MANIFEST.json` → mint the certificate with a
   deterministic `certificate_sha` (same input → same sha) → copy the bundle to `~/Downloads` (labeled,
   timestamped). **No n8n / Airtable / Drive / Slack / Gmail / GHL — local-only.**
4. **Outputs:** the labeled `~/Downloads` bundle + the signed certificate.
5. **Hand-to:** the invoking conversation (deliverables path + `00-INDEX.md` list + certificate status).
6. **Failure-mode:** any prover fails → block, re-author only the failing artifact within
   `max_fix_attempts`, then park; a certificate is never issued below a full pass. **"Done" requires
   the certificate path.**

**Never dispatch a sibling role.** The foreman is the ONLY dispatcher.

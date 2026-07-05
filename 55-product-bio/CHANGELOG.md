# Changelog — Product Bio Engine (Skill 55)

## 1.0.5 — client-exact overrides, labeled Downloads bundle, real department (T-55-product-bio)
- **FIX-XC-12c — client-exact override channel (mirror Skill 57).** The 6,000–7,000
  word band and the per-section enumerated COUNT_BANDS are now DEFAULT floors: a
  client-exact target LOGGED in the locked brief (`word_count_override` /
  `section_count_overrides`) wins verbatim and is recorded on the certificate —
  never floored, capped, or substituted. `prove_pb_wordcount.py` /
  `prove_pb_sections.py` read the logged channel via `--intake`; an override
  *applied* on the command line that is not present-and-equal in the locked brief
  is fail-closed (`AF-PB-OVERRIDE-UNLOGGED`). An exact 5,500- or 8,000-word bio is
  no longer rejected. The SACRED STRUCTURE (10 sections, order, 24 named closes, 7
  StoryBrand beats) has NO override channel. Resolver lives in `_pb_common.py`
  (`parse_band` / `resolve_band` / `resolved_word_band`); the orchestrator threads
  `--intake` at P3-BIO-QC; the certificate records `word_band` + `word_band_source`.
- **FIX-S36-57 — labeled ~/Downloads bundle + DELIVERY-NOTE + handoff + card
  pointer.** After the full P0→P5 pass certifies, `run_product_bio.py` assembles
  the client-facing `~/Downloads/Product-Bio-<slug>-<MM-DD-YYYY>/` bundle (bio,
  HTML, `DELIVERY-NOTE.md`, `handoff.json`, `PROCESS-CERTIFICATE.json`/`.md`),
  byte-copied from the P3/P5-proven working copies. The Downloads root is
  overridable via `PRODUCT_BIO_DELIVERY_ROOT` (state-path discipline — a test /
  `verify.sh` redirects it into a throwaway dir; it never touches the real
  `~/Downloads`). The Command Center card's terminal note now carries the
  deliverable pointer (bundle path + certificate sha).
- **FIX-XC-11g — registered role recipe + real fleet department.** Added
  `roles/product-bio-specialist.role.md` (slug `product-bio-specialist`) and
  aligned the CC card's `department_slug` from the non-existent `product-bio` to
  the REAL `marketing` fleet department (verified against the role-library / live
  board — it owns the sibling brand-positioning / signature-funnel /
  sales-page-assets specialists). Cards no longer strand unrouted.
- Manifest: added `AF-PB-OVERRIDE-UNLOGGED` to the P3 gate codes + autofail table;
  updated the P6 delivery label to the certified-then-bundle flow. `verify.sh`
  redirects the deliverable root into a throwaway dir. `ENGINE-PIN.sha256`
  re-stamped over the edited enforcement set.

## 1.0.4 — prior governed build
- Enforcement core: `PRODUCT-BIO-MANIFEST.json` (P0→P6 phase machine + AF-PB-*
  autofail table), the five fail-closed model-free provers (`prove_pb_intake`,
  `prove_pb_fidelity`, `prove_pb_wordcount`, `prove_pb_sections`, `prove_pb_html`)
  over a shared `_pb_common.py`, each with a `--self-test`.
- Baked IP prompts (`assets/prompts/01`, `02`), sha256-pinned in the manifest;
  the 25-node n8n / Google Drive / Slack / Gmail workflow retired for a local-only
  pipeline on the client's own NON-Anthropic providers.
- Canonical front door `product-bio-entry.sh` (deps → bypass-scan → hash-pin →
  nonce) + deterministic orchestrator `run_product_bio.py` (signed certificate on
  a full pass, deterministic sha ⇒ idempotent).
- Golden worked example `examples/golden-atlasflow/` (6,105-word bio +
  envelope-clean HTML) + one broken-variant per AF-PB-* code; `verify.sh` green.

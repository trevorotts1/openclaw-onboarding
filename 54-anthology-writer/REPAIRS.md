# Anthology Writer — REPAIRS register (KEEP / REPAIR / DROP)

The faithful-or-repaired defect register for the source anthology workflow. Each
row records how a source behavior was carried forward (KEEP), corrected (REPAIR),
or removed (DROP), and which gate now enforces it.

| # | Source behavior | Disposition | Enforced by |
|---|---|---|---|
| D1 | Every extracted call pinned to an Anthropic model id + "OpenRouter primary" chain | **REPAIR** — treated as capability tiers; resolved per box to the client's strongest NON-Anthropic model; no id baked | `aw_build_check.py` (AF-AW-ANTHROPIC) + `preflight.sh` + verify.sh scan |
| D2 | Five HTML-formatter LLM calls (source 06/08/11/13/15) | **DROP** — formatting is deterministic Python; no formatter model tier | `prompts/_retired-html-formatters/README.md` + no FORMATTER tier |
| D3 | Chapter length governed by prose + a self-reported word count | **REPAIR** — measured on stripped text; self-report ignored; padding inert | `prove_aw_chapter.py` (AF-AW-CHAP-LEN) |
| D4 | Title/subtitle could drift between outline, chapter, and rewrite | **REPAIR** — locked title/subtitle carried byte-exact; rewrite cannot change them | `prove_aw_chapter.py` (AF-AW-TITLE-LOCK) |
| D5 | Personal stories could be dropped silently in the chapter | **REPAIR** — every non-N/A anchor provably placed in outline AND chapter | `prove_aw_chapter.py` (AF-AW-STORIES) |
| D6 | Blended tone assembled from an unfixed number of influences | **REPAIR** — exactly 4 influence analyses + a ≥3,000-word floor | `prove_aw_tone.py` (AF-AW-TONE-4 / -FLOOR) |
| D7 | Client API key passed per-run in the trigger webhook payload | **REPAIR** — keys resolved per box from the client's own config; credential-shaped intake keys rejected | `prove_aw_intake.py` (AF-AW-INTAKE-CREDENTIAL) |
| D8 | n8n / Airtable / Google Docs / Slack / Gmail plumbing | **DROP** — replaced by a local artifact store + a labeled `~/Downloads` bundle | `anthology-entry.sh` bypass-scan (AF-AW-ENTRY-BYPASS) |
| D9 | Unbounded rework | **REPAIR** — bounded to 2 rewrites per contributor | `aw_build_check.py` (AF-AW-REWRITE-BUDGET) |
| D10 | "Done" claimed without proof | **REPAIR** — a signed process certificate requires a full P0→P6 pass | `run_anthology.py` (AF-AW-PROCESS-INTEGRITY) |

## Source gaps carried forward (recorded, not invented)

- **G1 — Avatar/tone-influence export:** the anthology's tone stages consume the
  avatar's 32 answers via the shared tone core (04..08). Where a contributor
  supplies fewer than 4 named influences, the tone stage auto-picks a real,
  well-known figure in harmony with the avatar answers (tone-core R3). Nothing is
  fabricated about the contributor.
- **G2 — Cover generation:** optional; if the client configured no image
  provider, the run records `degraded:image` and ships the cover PROMPT doc only.
- **G3 — Research grounding:** optional; absent a client search tool the run
  records `degraded:search` and never fabricates external facts.

Editing any gate is a four-step change: add the gate + AF code to
`ANTHOLOGY-MANIFEST.json`, add/adjust the prover, add a golden + attack fixture,
and record the disposition here.

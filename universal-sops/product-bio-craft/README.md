# Product-Bio-Craft SOP Cluster (`universal-sops/product-bio-craft/`)

The SHARED, cross-department procedure for how any department discovers and drives the **Product Bio
Engine (Skill 55)** end to end: 4-field intake -> prompt-fidelity -> bio authoring -> bio QC -> HTML
conversion -> HTML QC -> local labeled delivery + signed certificate.

This cluster is the `universal-sops` face of the capability. It does NOT re-implement the engine. The
authoritative machine spine lives in the skill:

- `55-product-bio/PRODUCT-BIO-MANIFEST.json` — the P0..P6 phase spine + every `AF-PB-*` gate code
  (SINGLE SOURCE OF TRUTH; editing it is step (i) of any Product Bio change).
- `55-product-bio/scripts/prove_pb_intake.py`, `prove_pb_fidelity.py`, `prove_pb_wordcount.py`,
  `prove_pb_sections.py`, `prove_pb_html.py` — the five fail-closed, model-free, stdlib-only floor
  provers (each with a built-in `--self-test` + golden/attack fixtures). They MEASURE the stripped
  text; a model's self-reported word/close count is NEVER trusted.
- `55-product-bio/run_product_bio.py` — the deterministic no-skip orchestrator (front-door-nonce
  gated by `product-bio-entry.sh`); issues the signed PROCESS-CERTIFICATE only on a full P0->P5 pass.
- `55-product-bio/product-bio-entry.sh` — the ONE sanctioned entry (DEPS -> BYPASS-SCAN ->
  VERSION/HASH-PIN gates, run-scoped nonce), fail-closed.
- `55-product-bio/MASTERDOC.md` — the SACRED IP + every rule tied to its `AF-PB-*` code.
- `55-product-bio/assets/prompts/01-product-bio-writer.md` + `02-google-doc-html-writer.md` — the two
  verbatim IP system prompts, baked byte-identical and sha256-pinned (fidelity is gated, not assumed).
- `55-product-bio/assets/intake-schema.json` — the locked 4-field intake contract.

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/product-bio-craft/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **55** product-bio | "write my product bio" · "a master brain for my product" · "a product sales knowledge base" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->

## The ONE way in

A Product Bio is built by running, and ONLY by running, the canonical fail-closed entry shell:

```
bash 55-product-bio/product-bio-entry.sh --run-dir <RUN_DIR> [--upto PHASE] [--plan]
```

Writing and running a hand-rolled uploader/notifier (a Google Drive upload, a Slack post, a
Gmail/SMTP send, an n8n webhook) is the ungoverned path and is refused (`AF-PB-ENTRY-BYPASS`).
Delivery is a labeled LOCAL bundle in `~/Downloads/`. A gate may be skipped ONLY by a logged owner
approval token in `<run-dir>/working/checkpoints/process_manifest.json` — never silently.

## Files

| File | What it governs |
|---|---|
| `SOP-PRODBIO-01-MASTER-BRAIN-BIO.md` | What the master-brain Product Bio is, when to build it, the 4-field intake, and the full gate contract (P0->P6 + every `AF-PB-*`). |

The auto-fail ruleset and phase manifest are NOT duplicated here — they live authoritatively in
`55-product-bio/PRODUCT-BIO-MANIFEST.json` (the phase spine + the `autofails` table). This SOP points
at them so there is exactly one source of truth.

## SACRED law (from `55-product-bio/MASTERDOC.md`)

- The 10 mandatory sections, their ORDER, and every count are SACRED — never floored, reordered,
  renamed, or reinterpreted. Every rule is machine-enforced by a fail-closed prover, never advisory.
- **Word band:** the bio measures 6,000–7,000 stripped words (`AF-PB-WORDCOUNT`); the mandatory
  `COMPLETION VERIFICATION` block is present (`AF-PB-VERIFY-BLOCK`). The model's self-reported count is
  IGNORED — the prover MEASURES; whitespace padding is inert.
- **Sections + closes:** the 10 sections present and in order (`AF-PB-SECTION`); exactly **24** distinct
  named signature-close styles (`AF-PB-CLOSES`, PRD O3 — the tracker's 24, not the 20 taught).
- **Per-section floors** (`AF-PB-COUNTS`): 10 intros / 15–20 power adjectives / 8–10 objections /
  10–12 FAQs / 8–10 social-proof / all 7 StoryBrand beats.
- **HTML envelope:** starts EXACTLY `<!DOCTYPE html>`, ends EXACTLY `</html>` after the one logged
  auto-trim (`AF-PB-HTML-ENVELOPE`); exactly one `<h1>` (`AF-PB-HTML-H1`); no CSS beyond
  `page-break-after` (`AF-PB-HTML-CSS`); >= 90% normalized-token coverage vs the source bio
  (`AF-PB-HTML-LOSS`).
- **Process integrity:** a signed certificate requires a full P0->P5 pass with no phase skips
  (`AF-PB-STAGE-SKIPPED` / `AF-PB-PROCESS-INTEGRITY`).
- **Client-exact overrides win:** a client-stated exact word target is honored verbatim and logged on
  the certificate — never floored, capped, or substituted (fleet-wide absolute law).

## Relationship to Avatar Alchemist (Skill 52) — cross-linked, NEVER merged

Skill 52 (Avatar Alchemist) carries a DIFFERENT "Product Bio" prompt (a strategic product messaging
specialist inside its brand-intelligence pipeline). Skill 55 is the STANDALONE master-brain generator.
**Do not merge or deduplicate the two prompts.** A change to either product-bio prompt MUST flag the
sibling skill for review. Routing: a standalone master-brain bio -> Skill 55; a brand-intelligence
package (its embedded bio ships with it) -> Skill 52. (The reciprocal note is a forward-ref TODO on the
Skill-52 `SKILL.md`, to be added when Skill 52 lands on `main`.)

## Command Center registration (operator action)

The Command Center surfaces this capability as ONE `sops` row so the Triad Rule auto-resolves a
"product bio" request to it. NO schema change (a job is a `tasks` row). Because the mission-control
repo is a separate submodule not reachable from the skill worktree, inserting/refreshing the row is an
OPERATOR action at CC install/update time — via `32-command-center-setup/scripts/add-sop.sh` (or the
dashboard `POST /api/sops/import-role-library`). Suggested row:

- `slug`: `product-bio-master-brain-bio`
- `name`: `Product Bio: build the master-brain sales knowledge base`
- `department`: `marketing`
- `task_keywords`: `product bio, master brain, sales knowledge base, 10 sections, signature closes,
  storybrand, google doc html, objections, faqs, social proof`
- `success_criteria`: signed `PROCESS-CERTIFICATE.json` present (full P0->P6 pass); measured
  6,000–7,000-word bio; 10 sections in order; 24 closes; HTML envelope battery clean; labeled local
  bundle in `~/Downloads/`.

## Flexibility = guide-not-rule

The engine is a GUIDE and a RESOURCE for how a department fulfils a product-bio request; honor an
explicit owner choice (e.g. an exact word target, logged on the certificate). But the SACRED bands
above are enforced by the provers and are not opinions — a violation is a hard, named `AF-PB-*`
auto-fail.

## Client-runtime rule (binding)

The shipped engine on a client box NEVER uses Anthropic / `claude-*` models or operator keys. The two
LLM calls (bio authoring + HTML conversion) run on the CLIENT's own configured provider chain
(`55-product-bio/assets/model-map.template.json`, resolved per box: a long-output tier for the bio, a
cheaper tier permitted for the HTML). The deterministic gates (`prove_pb_*.py`) are provider-neutral
Python and run identically everywhere; `55-product-bio/verify.sh` includes a no-Anthropic scan
(`AF-PB-ANTHROPIC`) over the shipped skill + the resolved model map.

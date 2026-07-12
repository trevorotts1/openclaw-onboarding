---
name: product-bio
description: The Product Bio Engine — a governed skill that turns a 4-field intake into the master-brain product bio: a 6,000-7,000-word, 10-section sales knowledge base (10 intros, 15-20 power adjectives, ICP, description, positioning, 8-10 objections, 10-12 FAQs, 8-10 social proof, StoryBrand 2.0, 24 named signature closes + a completion-verification block) AND its Google-Docs-importable HTML. It bakes Trevor Otts's two verbatim system prompts (sha256-pinned), replaces the 25-node n8n / Google Drive / Slack / Gmail workflow with a local-only pipeline on the CLIENT's own model providers, and gates every SACRED count with fail-closed, model-free Python provers that MEASURE the stripped text (self-reported counts are ignored). Runs P0 INTAKE -> P1 FIDELITY -> P2 BIO -> P3 BIO-QC -> P4 HTML -> P5 HTML-QC -> P6 DELIVER through one canonical entry (product-bio-entry.sh) with a deps/bypass/hash-pin/nonce gate; a signed process certificate is issued only on a full pass. Cross-linked with (never merged into) Skill 52 Avatar Alchemist.
version: 1.0.11
---

# Product Bio Engine (Skill 55)

The methodology + enforcement layer for the Trevor Otts **"master brain" product
bio** — the 6,000–7,000-word, 10-section sales knowledge base that powers AI
chatbots and human sales teams. This skill owns the **IP and the gates**; it
authors two artifacts (the bio text + the Google-Docs-importable HTML) as a
labeled local deliverable, then hands off — it touches **no n8n, no Google Drive,
no Slack, no Gmail, no Airtable** at runtime.

> The structures, counts, names, and envelope rules captured in `MASTERDOC.md`
> (and baked verbatim into `assets/prompts/`) are **SACRED** — never floored,
> reordered, renamed, or reinterpreted. Every rule is machine-enforced by a
> fail-closed prover, never advisory. **Enforcement, not description.** The
> model's self-reported word/close count is IGNORED — the provers MEASURE.

## What this skill produces / owns

- `assets/prompts/01-product-bio-writer.md` + `02-google-doc-html-writer.md` —
  the two IP system prompts, baked **byte-identical** and **sha256-pinned**
  (`82b52e01…` / `f015392a…`). Provider-agnostic; no Anthropic ids.
- `PRODUCT-BIO-MANIFEST.json` — the phase machine (P0-INTAKE → P6-DELIVER), each
  phase's `produces_artifact`, `_chk_*` preflight symbol, and the `AF-PB-*`
  autofail table with documented triggers.
- `intake/product-bio-intake.json` + `assets/intake-schema.json` — the ONE-block
  intake spec + locked contract (`product_name`, `product_description`,
  `first_name`, `last_name` required; `client_folder_name`/`email`/`phone`
  optional, captured for handoff parity only).
- `scripts/` — the five fail-closed, model-free, stdlib-only provers (each with a
  built-in `--self-test` and golden+attack fixtures):
  - `prove_pb_intake.py` — AF-PB-INTAKE-MISSING.
  - `prove_pb_fidelity.py` — AF-PB-PROMPT-DRIFT (sha-pins the baked IP).
  - `prove_pb_wordcount.py` — AF-PB-WORDCOUNT (measured band) + AF-PB-VERIFY-BLOCK.
  - `prove_pb_sections.py` — AF-PB-SECTION (10 in order) + AF-PB-CLOSES (24) +
    AF-PB-COUNTS (per-section floors + StoryBrand beats).
  - `prove_pb_html.py` — AF-PB-HTML-ENVELOPE / -H1 / -CSS / -LOSS.
- `assets/model-map.template.json` — the CLIENT-PATH model map, resolved per box
  against the client's own providers/keys (long-output tier for the bio, cheaper
  tier permitted for the HTML). NEVER `claude-*`/`anthropic/*`.
- `MASTERDOC.md` — the SACRED IP + every rule tied to its `AF-PB-*` code.
- `REPAIRS.md` — the faithful-or-repaired defect register (KEEP/REPAIR/DROP).
- `test-fixtures/golden/` + `test-fixtures/attack/` — a golden PASS bundle
  (6,105-word bio + envelope-clean HTML + intake) and one attack fixture per AF
  code, including a **whitespace-padding attack** (a short bio padded to book
  length that the stripped measurement still rejects).
- `product-bio-entry.sh` — the ONE sanctioned command (deps / bypass-scan /
  hash-pin / nonce, fail-closed).
- `run_product_bio.py` — the deterministic state machine over the manifest
  (P0→P6, no phase skips, front-door nonce, signed certificate on a full pass).
- `roles/product-bio-specialist.role.md` — the **registered role recipe** (slug
  `product-bio-specialist`, department **`marketing`**): trigger phrases, success
  criteria, and the provider rule. Its Command Center card lands in the real
  `marketing` fleet department (the one that owns the brand-positioning /
  signature-funnel / sales-page-assets specialists) — never a non-existent
  `product-bio` department that would strand the card unrouted.
- `verify.sh` — the READ-ONLY self-verify gate.

## The SACRED invariants the provers enforce

| Invariant | Rule | Code |
|---|---|---|
| Intake | the 4 required fields present + non-whitespace | AF-PB-INTAKE-MISSING |
| Prompt fidelity | sha256 of each baked prompt == its recorded pin | AF-PB-PROMPT-DRIFT |
| Word band | MEASURED stripped word count 6,000–7,000 (self-report ignored; padding inert) | AF-PB-WORDCOUNT |
| Completion block | the `COMPLETION VERIFICATION` block is present | AF-PB-VERIFY-BLOCK |
| Sections | the 10 mandatory sections present and in order | AF-PB-SECTION |
| Closes | exactly 24 distinct named signature-close styles (PRD O3) | AF-PB-CLOSES |
| Per-section floors | 10 intros / 15–20 adjectives / 8–10 objections / 10–12 FAQs / 8–10 social proof / all 7 StoryBrand beats | AF-PB-COUNTS |
| HTML envelope | starts EXACTLY `<!DOCTYPE html>`, ends EXACTLY `</html>` (after the one logged auto-trim) | AF-PB-HTML-ENVELOPE |
| One H1 | exactly one `<h1>` | AF-PB-HTML-H1 |
| No custom CSS | nothing beyond `page-break-after` | AF-PB-HTML-CSS |
| No content loss | ≥ 90% normalized-token coverage vs the source bio | AF-PB-HTML-LOSS |
| Process integrity | a signed certificate requires a full P0→P5 pass; no phase skips | AF-PB-PROCESS-INTEGRITY / AF-PB-STAGE-SKIPPED |
| Override discipline | a client-exact word/section override is honored ONLY when logged in the locked brief; an applied-but-unlogged override is fail-closed | AF-PB-OVERRIDE-UNLOGGED |

**Client-exact overrides win.** The 6,000–7,000 band is the DEFAULT floor; a
client-stated exact word target is honored verbatim and logged on the
certificate, never floored, capped, or substituted (fleet-wide absolute law).
The channel is the **locked brief** (`working/intake.json`): a `word_count_override`
(band / exact / `{min,max}`) or a per-section `section_count_overrides` map is
read via `--intake` and wins over the default band; an override *applied* on the
command line that is **not** present-and-equal in the locked brief is rejected
(`AF-PB-OVERRIDE-UNLOGGED`), so a SACRED floor can never be relaxed by an unlogged
value. The **SACRED STRUCTURE never overrides** — the 10 sections, their order,
the 24 named signature closes, and the 7 StoryBrand beats have no override
channel. (Mirrors Skill 57's logged-override-wins-and-is-recorded pattern.)

## How it runs — THROUGH one canonical entry

```
bash 55-product-bio/product-bio-entry.sh --run-dir <RUN_DIR> [--upto PHASE] [--plan]
```

The entry runs three fail-closed gates (DEPS → BYPASS-SCAN → VERSION/HASH-PIN),
mints a run-scoped nonce, and dispatches the deterministic orchestrator
`run_product_bio.py`, which walks the manifest P0 → P6 with no phase skips. The QC
phases shell out to the provers and refuse to advance on any `AF-PB-*` violation.
Writing and running a hand-rolled external uploader/notifier (a Google Drive
upload, a Slack post, a Gmail/SMTP send, an n8n webhook) is the **ungoverned path
and is FORBIDDEN** (`AF-PB-ENTRY-BYPASS`) — delivery is a labeled LOCAL bundle in
`~/Downloads`. A gate may be skipped ONLY by a logged owner approval token in
`<run-dir>/working/checkpoints/process_manifest.json` — never silently.

## Delivery is local-only

After a full P0→P5 pass issues the signed certificate, the client-facing bundle
is assembled at `~/Downloads/Product-Bio-<slug>-<MM-DD-YYYY>/`:
`Product-Bio-<slug>.md`, `Product-Bio-<slug>.html` (Google-Docs-importable),
`DELIVERY-NOTE.md`, `handoff.json`, and `PROCESS-CERTIFICATE.json`/`.md` — each
copied byte-for-byte from the P3/P5-proven working copies. The Downloads root is
overridable via `PRODUCT_BIO_DELIVERY_ROOT` (state-path discipline: a test / a
`verify.sh` run redirects it into a throwaway dir and never touches the real
`~/Downloads`). The Command Center card carries the **deliverable pointer** — the
bundle path + certificate sha — in its terminal note. No n8n / Drive / Slack /
Gmail / Airtable. Any push notification is per-client config through the client's
own OpenClaw gateway (never bypassed), client-silent by default.

## Relationship to Avatar Alchemist (Skill 52) — cross-linked, NEVER merged

Skill 52 (Avatar Alchemist) carries a **different** "Product Bio" prompt — a
"strategic product messaging specialist" persona inside its brand-intelligence
pipeline. This skill (55) is the STANDALONE master-brain generator (10 sections /
6,000–7,000 words / 24 closes). **Do not merge or deduplicate the two prompts.**
A change to either product-bio prompt MUST flag the sibling skill for review.
Routing disambiguation: a standalone master-brain bio → **Skill 55**; a
brand-intelligence package (its embedded bio ships with it) → **Skill 52**.
(PRD §5, G6, O8.) **Reciprocal cross-ref (LIVE):** Skill 52 (Avatar Alchemist) is
on `main`, and its `52-avatar-alchemist/SKILL.md` carries the matching "never
merge; a change to either product-bio prompt flags the sibling" note ("Relationship
to Product Bio (Skill 55) — cross-linked, NEVER merged"). The cross-ref is now
two-way, so a fleet update to one can never silently strand the other.

## Client-provider rule (binding)

On a client box this skill uses the **client's own configured providers and
keys** — never the operator's, never Anthropic / `claude-*` model ids. The source
workflow pinned both chains to `google/gemini-2.5-pro` (via OpenRouter) — already
non-Anthropic; kept only if the client configured that provider, else the
client's own capability-tested tier (long-output for the bio, cheaper for the
HTML). The deterministic gates are model-free Python that run identically
everywhere. `verify.sh` includes a no-Anthropic scan (`AF-PB-ANTHROPIC`) over the
shipped skill + the resolved model map. This skill is provider-neutral by
construction.

## Verify

`bash 55-product-bio/verify.sh` is the self-verify gate: it runs each prover's
`--self-test` (built-in golden + attack fixtures), reproduces the golden bundle
end-to-end, proves each attack fixture is rejected with its distinct AF code,
re-checks the prompt-fidelity pins, and runs the no-Anthropic scan — exiting
nonzero on any regression, so it can gate a merge / CI / a post-install check. It
is idempotent and read-only.

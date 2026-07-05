---
name: anthology-writer
description: The Anthology Writer — a governed skill that turns one contributor intake (anthology title, contributor name, chapter premise, and real personal stories) into a finished, gated anthology chapter (2,000-3,500 words) in that contributor's blended signature voice, plus the supporting blended tone doc, locked title/subtitle, blurb, and outline, delivered as a labeled LOCAL bundle. It bakes the anthology authoring IP as sha256-pinned prompt assets, references the shared tone-writing-core (04..08) in lockstep, replaces the source n8n / Airtable / Google Docs / Slack / Gmail workflow with a local-only pipeline on the CLIENT's own model providers, and gates every SACRED floor with fail-closed, model-free Python provers that MEASURE the stripped text (self-reported counts are ignored). Runs P0 INTAKE -> P1 FIDELITY -> P2 TONE -> P3 TONE-QC -> P4 TITLE-LOCK -> P5 CHAPTER -> P6 CHAPTER-QC -> P7 DELIVER through one canonical entry (anthology-entry.sh) with a deps/bypass/hash-pin/nonce gate; a signed process certificate is issued only on a full pass. SEPARATE skill, sibling of Skill 53 Book Writer — they share the ONE tone core, never merged. Client runtime is NEVER Anthropic: every source Anthropic-model / "OpenRouter primary" tier is resolved to the client's strongest NON-Anthropic model. Trigger with "run anthology writer", "start my anthology", "anthology chapter for <contributor>", "add a contributor to book <id>", or "anthology status".
version: 1.1.0
---

# Anthology Writer (Skill 54)

The methodology + enforcement layer for a **multi-contributor anthology**: one
finished chapter per contributor, authored in that contributor's blended
signature voice, gated so nothing ships that missed a SACRED floor. This skill
owns the **IP and the gates**; it authors the chapter and its supporting
artifacts (tone doc, locked title/subtitle, blurb, outline) as a labeled LOCAL
deliverable, then hands off — it touches **no n8n, no Airtable, no Google
Docs/Drive, no Slack, no Gmail, no Go High Level** at runtime, and **no git/gh**
in any skill script or sub-agent prompt.

> The floors, counts, and lock rules captured in `MASTERDOC.md` (and baked into
> `assets/prompts/` + the shared tone core) are **SACRED** — never floored,
> reordered, renamed, or reinterpreted. Every rule is machine-enforced by a
> fail-closed prover, never advisory. **Enforcement, not description.** The
> model's self-reported word count is IGNORED — the provers MEASURE.

## What this skill produces / owns

- `assets/prompts/06-suggested-titles.md` · `07-book-blurb.md` ·
  `08-create-outline.md` · `09-write-chapter.md` · `10-chapter-rewrite.md` — the
  baked anthology authoring IP, **sha256-pinned** in `ANTHOLOGY-MANIFEST.json`.
  Provider-agnostic; **no concrete model id** in any prompt body.
- `prompts/04-tone-style-1 … 08-blended-tone/` — a **lockstep copy** of the
  shared `shared-utils/tone-writing-core` tone stages, proven byte-identical by
  `scripts/verify_tone_core_sync.py` (AF-AW-TONE-DRIFT). The tone IP lives in ONE
  place; this skill references it, never re-authors it.
- `prompts/_retired-html-formatters/` — provenance note for the five source
  HTML-formatter LLM calls (06/08/11/13/15), **retired**: all formatting is
  deterministic Python, so there is no formatter model tier.
- `ANTHOLOGY-MANIFEST.json` — the phase machine (P0-INTAKE → P7-DELIVER), each
  phase's `produces_artifact`, `_chk_*` preflight symbol, and the `AF-AW-*`
  autofail table with documented triggers, plus `shared_tone_core`.
- `intake/aw-intake-schema.json` + `aw-intake-template.md` — the locked intake
  contract (`anthology_title`, `first_name`, `last_name`, `chapter_premise`
  required; `personal_stories` may be `N/A`). **No credential-shaped fields.**
- `scripts/` — the fail-closed, model-free, stdlib-only provers (each with a
  built-in `--self-test` and golden+attack fixtures):
  - `prove_aw_intake.py` — AF-AW-INTAKE-MISSING / AF-AW-INTAKE-CREDENTIAL.
  - `prove_aw_fidelity.py` — AF-AW-PROMPT-DRIFT (sha-pins the baked IP).
  - `verify_tone_core_sync.py` — AF-AW-TONE-DRIFT (tone-core lockstep).
  - `prove_aw_tone.py` — AF-AW-TONE-4 (exactly 4 influences) + AF-AW-TONE-FLOOR.
  - `prove_aw_chapter.py` — AF-AW-CHAP-LEN + AF-AW-VERIFY-BLOCK + AF-AW-PLACEHOLDER
    + AF-AW-TITLE-LOCK + AF-AW-STORIES (chapter AND outline placement).
  - `aw_build_check.py` — AF-AW-ANTHROPIC (G-NOANTHROPIC over the run ledger) +
    AF-AW-REWRITE-BUDGET.
- `assets/model-map.template.json` — the CLIENT-PATH tier map (HEAVY-WRITER /
  MID-WRITER / RESEARCHER / IMAGE), resolved per box against the client's own
  providers/keys. NEVER `claude-*` / `anthropic/*`.
- `run_anthology.py` — the deterministic state machine over the manifest
  (P0→P7, no phase skips, front-door nonce, signed certificate on a full pass).
- `anthology-entry.sh` — the ONE sanctioned command (deps / model-map pre-gate /
  bypass-scan / hash-pin / nonce, fail-closed).
- `ENGINE-PIN.sha256` — the pinned content hash of the enforcement set
  (`run_anthology.py` + the provers + `_aw_common.py` + `verify_tone_core_sync.py`).
  `anthology-entry.sh` GATE 3 recomputes it and refuses to run on any drift
  (`AF-AW-HASH-PIN`), so a silently-edited gate can never disarm itself.
- `roles/anthology-writer.role.md` — the registered role recipe (department
  **Content / Publishing**, role slug `anthology-chapter-author`) with trigger
  phrases and duties; this is the skill's role IP referenced by the SKILL, not
  dead weight.
- `verify.sh` — the READ-ONLY, idempotent self-verify gate.

## The SACRED invariants the provers enforce

| Invariant | Rule | Code |
|---|---|---|
| Intake | the 4 required fields present + non-whitespace | AF-AW-INTAKE-MISSING |
| No keys in intake | no credential-shaped intake key (provider keys ride the client's own config) | AF-AW-INTAKE-CREDENTIAL |
| Prompt fidelity | sha256 of each baked authoring prompt == its manifest pin | AF-AW-PROMPT-DRIFT |
| Tone-core lockstep | baked tone stages byte-identical to `shared-utils/tone-writing-core` | AF-AW-TONE-DRIFT |
| Blended tone influences | exactly 4 distinct tone-style influence analyses | AF-AW-TONE-4 |
| Tone floor | MEASURED tone-doc stripped words ≥ 3,000 (tone-core R7) | AF-AW-TONE-FLOOR |
| Title lock | working/title.json has a non-empty title + subtitle | AF-AW-TITLE-MISSING |
| Chapter band | MEASURED chapter stripped words 2,000-3,500 (self-report ignored; padding inert) | AF-AW-CHAP-LEN |
| Completion block | the `COMPLETION VERIFICATION` block is present | AF-AW-VERIFY-BLOCK |
| No placeholders | no unresolved `{{..}}` / `[[..]]` / `<ALLCAPS>` in a finalized artifact | AF-AW-PLACEHOLDER |
| Title carried | the locked title + subtitle appear byte-exact in the outline AND chapter | AF-AW-TITLE-LOCK |
| Stories placed | every non-`N/A` personal-story anchor appears in the outline AND chapter | AF-AW-STORIES |
| No Anthropic | every model id in `RUN-LEDGER.json` is NON-Anthropic; no operator key in env | AF-AW-ANTHROPIC |
| Model provenance | `RUN-LEDGER.json` is REQUIRED at P6 and records ≥1 resolved model id (fail-closed) | AF-AW-PROVENANCE-MISSING |
| Rewrite budget | at most 2 rewrites per contributor | AF-AW-REWRITE-BUDGET |
| Client-exact override | a band override is honored only through the LOGGED, brief-tied `working/overrides.json`; an unlogged override fails closed | AF-AW-OVERRIDE-UNLOGGED |
| Delivery integrity | the labeled bundle is assembled + byte-verified from the QC'd working copies; no swap-after-QC | AF-AW-STAGE-SKIPPED / AF-AW-DELIVER-MISMATCH |
| Process integrity | a signed certificate requires a full P0→P6 pass; no phase skips | AF-AW-PROCESS-INTEGRITY / AF-AW-STAGE-SKIPPED |
| Entry front-door | no hand-rolled external uploader/notifier in the run dir | AF-AW-ENTRY-BYPASS |
| Model-map resolved | a resolved run-dir `model-map.json` carries no `<CLIENT_*>` placeholder / Anthropic id | AF-AW-UNRESOLVED-MODELMAP |

**Client-exact overrides win.** The 2,000-3,500 chapter band and the 3,000-word
tone floor are DEFAULT floors; a client-stated exact word target is honored
verbatim, never floored, capped, or substituted (fleet-wide absolute law). It is
honored ONLY through the audited channel — a `working/overrides.json` that is
recorded, approved, reasoned, and cites the locked brief (`brief_ref`). The
provers read it via `--band-override` and an applied override is recorded on the
`PROCESS-CERTIFICATE` (`client_band_override`) and bound into the certificate
sha. An override applied WITHOUT that log fails closed (`AF-AW-OVERRIDE-UNLOGGED`)
— an exact ask is honored, but never as a silent floor-swap.

## How it runs — THROUGH one canonical entry

```
bash 54-anthology-writer/anthology-entry.sh --run-dir <RUN_DIR> [--upto PHASE] [--plan]
```

The entry runs its fail-closed gates (DEPS → MODEL-MAP PRE-GATE → BYPASS-SCAN →
VERSION/HASH-PIN), mints a run-scoped nonce, and dispatches `run_anthology.py`,
which walks the manifest P0 → P7 with no phase skips, one contributor at a time.
The MODEL-MAP PRE-GATE runs `preflight.sh --check`: a resolved run-dir
`model-map.json` that still carries `<CLIENT_*>` placeholders (installer not run)
or a banned Anthropic id is refused (`AF-AW-UNRESOLVED-MODELMAP`); a missing map
is a clean pass. The QC phases shell out to the provers and refuse to advance on
any `AF-AW-*` violation.
Writing/running a hand-rolled external uploader/notifier (a Google Drive upload,
a Slack post, a Gmail/SMTP send, an n8n webhook, an Airtable write) is the
**ungoverned path and is FORBIDDEN** (`AF-AW-ENTRY-BYPASS`) — delivery is a
labeled LOCAL bundle in `~/Downloads`. A gate may be skipped ONLY by a logged
owner approval token in `<run-dir>/working/checkpoints/process_manifest.json`.

## Delivery is local-only

The deliverable bundle is `~/Downloads/Anthology-<slug>-<MM-DD-YYYY>/`: the
chapter markdown, the tone doc, the outline, the blurb, `DELIVERY-NOTE.md`,
`handoff.json`, and `PROCESS-CERTIFICATE.json`. No n8n / Airtable / Drive / Slack
/ Gmail. Any push notification is per-client config through the client's own
OpenClaw gateway (never bypassed), client-silent by default.

## Client-provider rule (binding) — the NON-Anthropic build-fix

On a client box this skill uses the **client's own configured providers and
keys** — never the operator's, never `claude-*` / `anthropic/*` model ids. The
source workflow pinned every extracted call to an Anthropic model id "as shipped
in source" and routed through "the client's OpenRouter primary"; those ids are
**capability tiers, not prescriptions**. `preflight.sh` resolves each tier
(HEAVY-WRITER / MID-WRITER / RESEARCHER / IMAGE) per box to the client's
**strongest NON-Anthropic model** and writes `model-map.json`. `aw_build_check.py`
(G-NOANTHROPIC) hard-fails any run whose `RUN-LEDGER.json` shows an
`/anthropic|claude/i` id, and `verify.sh` runs a static no-Anthropic scan
(`AF-AW-ANTHROPIC`) over the shipped skill + the resolved map. This skill is
provider-neutral by construction.

## Relationship to Book Writer (Skill 53) — separate, sharing ONE tone core

Skill 54 (Anthology Writer) and Skill 53 (Book Writer) are **separate skills**
(Trevor's standing decision — never consolidated) that **share the ONE**
`shared-utils/tone-writing-core`. The anthology is many contributors, one chapter
each; the book is one author, many chapters. A change to the shared tone core
flags **both** siblings for review. Routing: a multi-contributor anthology →
**Skill 54**; a single-author book → **Skill 53**.

## Verify

`bash 54-anthology-writer/verify.sh` is the self-verify gate: it runs each
prover's `--self-test`, reproduces the golden bundle, proves each attack fixture
is rejected with its distinct AF code, re-checks the prompt-fidelity pins + the
tone-core lockstep, runs the no-Anthropic scan, drives the golden example
end-to-end through the entry (a full pass issues a certificate that reproduces
the SHIPPED `certificate_sha` — deterministic ⇒ idempotent), and proves a seeded
short chapter blocks the run with NO certificate. It exits nonzero on any
regression, so it can gate a merge / CI / a post-install check. Read-only and
idempotent.

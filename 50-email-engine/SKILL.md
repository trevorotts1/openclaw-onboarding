---
name: email-engine
description: The Email Engine — a governed skill + Email Superlibrary that SELECTS the right framework, GENERATES corpus-faithful email copy, QCs it against fail-closed provers, and hands a DRAFT-ONLY deploy plan to the Convert & Flow (GoHighLevel) operator. Owns the reusable IP — 13 email frameworks, 12 persona styles, the buyer-type -> email# -> framework map, the 4 sequence objectives, the 10-email landing-page promo sequence and the 12-email buyer-type / high-ticket-appointment sequences — and gates every one of those SACRED structures with a deterministic, model-free floor prover (prove-email.py). Runs P1 SELECT -> P2 GENERATE -> P3 QC -> P4 DEPLOY through one canonical entry (email-engine-entry.sh) with a deps/bypass/hash-pin/nonce gate; nothing is ever sent without explicit human approval.
version: 1.0.5
---

# Email Engine (Skill 50)

The methodology + enforcement layer for the Trevor Otts email system. This skill owns the
**IP and the gates**; it authors copy and a build plan, then hands off — it never sends an
email itself.

> The structures, counts, names, and rules captured in `MASTERDOC.md` (and mirrored from
> `SOURCE-EMAIL-CORPUS.md`) are **SACRED** — never floored, reordered, renamed, or
> reinterpreted. Every rule below is machine-enforced by a fail-closed prover, never advisory.
> **Enforcement, not description.**

## What this skill produces / owns

- `EMAIL-MANIFEST.json` — the phase machine (P1 SELECT -> P2 GENERATE -> P3 QC -> P4 DEPLOY),
  each phase's `produces_artifact`, `_chk_*` preflight symbols, and the `AF-EMAIL-*` autofail
  table with documented triggers.
- `intake/email-intake-questions.json` — the ONE-block intake spec (objective, buyer type,
  offer, brand voice, sequence position, founder name; optional high-ticket flag +
  persona style) with a `blocks_until_answered` provenance gate.
- `schema/email.schema.json` — the per-email input contract (`subjects[2]`, `previews`,
  `body`, `framework`, `objective`, `buyer_type?`, `ctas[]`, `persona_style?`, `founder_name`,
  `sequence_id`, `e_slot`).
- `tools/prove-email.py` — THE fail-closed floor prover. Deterministic, stdlib-only, no model
  judgement. Enforces every SACRED invariant (see below) with a named `AF-EMAIL-*` code, exits
  nonzero on any violation, and carries a built-in `--self-test` (VALID -> exit 0 /
  VIOLATION -> exit nonzero).
- `tools/email_matcher.py` + `email_matcher_cli.py` — the tags + embedding-reranker matcher
  (mirrors Skill 6's `funnel_matcher.py`): 3 flexibility modes, a confidence threshold, and an
  optional semantic `EmbeddingReranker` hook. Never blocks; the user's explicit desire always wins.
- `MASTERDOC.md` — the SACRED email IP verbatim (13 frameworks + structures, the
  buyer-type -> email# -> framework map, 12 persona styles, 4 objectives, and the
  three named sequences), each rule tied to its `AF-EMAIL-*` code.
- `email-library/` — THE Email Superlibrary: **36 entries** as paired `<id>.json`
  (machine `rules{}` spec) + `<id>.md` (how-to / example / tags) under
  `frameworks/ buyer-types/ objectives/ persona-styles/ sequences/`, plus the
  lexical `catalog-index.json` + built `catalog-built-index.json` and a
  `register.py --check` coverage gate.
- `schema/brief.schema.json` + `schema/build-plan.schema.json` — the locked intake
  brief contract and the Skill-44 DRAFT-ONLY deploy handoff contract.
- `tools/emit_build_plan.py` — deterministic P4 emitter: brief + approved copy ->
  a DRAFT-ONLY Skill-44 (Convert & Flow / GoHighLevel) workflow build plan (email +
  wait steps). Model-free; nothing sends.
- `index/` — the SEPARATE embed-once Gemini email index (`EMAIL-INDEX-MANIFEST.json`
  with model + dims PINNED, `build-and-publish.sh` operator-box HASH-SKIP delta,
  `provision-email-index.sh` -> `provision_email_index()` sha256-verified download,
  NEVER a per-box re-embed).
- `examples/golden-landing-10/` — the golden 10-email regression sample (PASSES
  end-to-end + issues a certificate) with `broken-variants/` proving fail-closed
  rejection.
- `verify.sh` — the READ-ONLY self-verify gate (self-tests + register check + golden
  reproduce + broken-variant rejection); nonzero on any failure.
- `email-engine-entry.sh` — the ONE sanctioned command. Deps / bypass-scan / hash-pin / nonce,
  fail-closed. Refuses any hand-rolled email sender in the run directory.
- `run_email_engine.py` — the deterministic state machine over the manifest (P1 -> P4, no phase skips).

## The SACRED invariants the prover enforces

All from `SOURCE-EMAIL-CORPUS.md`. Each is a deterministic measurer with a named `AF-EMAIL-*` code.

| Invariant | Rule | Code |
|---|---|---|
| Framework set | `framework` is one of the 13 canonical ids; if a structured `sections[]` is supplied it must match the framework's declared part count | `AF-EMAIL-FRAMEWORK-UNKNOWN` / `AF-EMAIL-FRAMEWORK-INCOMPLETE` |
| Buyer-type map (12-email) | E1-2 spontaneous (3-B, Star-Chain-Hook) / E3-6 methodical (F2B, 6 W's, ACCA, PASTOR-Solutions) / E7-9 humanistic (PASTOR-Story, Star-Story-Solution, PAS) / E10-12 competitive (AIDA, Million-Dollar-Sales, BAB) | `AF-EMAIL-BUYERTYPE-MAP` |
| Landing-page map (10-email) | E1-3 PASTOR-Solutions, E4 F2B, E5 6 W's, E6 BAB, E7 3-B, E8 Million-Dollar-Sales, E9 AIDA, E10 PAS | `AF-EMAIL-SEQUENCE-MAP` |
| Sequence length | landing-page = 10 emails; high-ticket / buyer-type = 12 emails; slots contiguous 1..N | `AF-EMAIL-SEQUENCE-LENGTH` |
| Objective validity | exactly one of promotional / abandoned-cart / upsell / downsell | `AF-EMAIL-OBJECTIVE-INVALID` |
| Persona-style validity | if set, one of the 12 canonical styles | `AF-EMAIL-PERSONA-INVALID` |
| Persona never named | NEVER name/quote the referenced person (tone only, 100% original) | `AF-EMAIL-PERSONA-NAMED` |
| Subject count | exactly 2 (A/B), both non-empty | `AF-EMAIL-SUBJECT-COUNT` |
| Preview count | Convert&Flow master = 1 line; high-ticket = 2 (the sequence declares which) | `AF-EMAIL-PREVIEW-COUNT` |
| Word band | 150-300 words, EXCEPT the 3-B Plan (< 150). A logged client-exact override wins over the default band | `AF-EMAIL-WORDBAND` |
| CTA count | >=1 per email; >=3 for the landing-page PASTOR emails (E1-3) | `AF-EMAIL-CTA-COUNT` |
| Subject char band | C&F: 8-12 words, no pricing token / high-ticket: 80-87 rendered chars, exactly ONE emoji | `AF-EMAIL-SUBJECT-CHARBAND` |
| First-name placement | `{{contact.first_name}}` in the first 40 chars of a subject (C&F) / present in a subject (HT) | `AF-EMAIL-FIRSTNAME-PLACEMENT` |
| Formatting | <=4 emojis in the body; never >3 sentences in a paragraph without a break | `AF-EMAIL-FORMAT` |
| Founder signature | the founder's ACTUAL name in the close, never a placeholder token | `AF-EMAIL-SIGNATURE-PLACEHOLDER` |
| Disruptive element (HT) | every high-ticket email carries >=1 disruptive element | `AF-EMAIL-DISRUPTIVE-MISSING` |
| Client-exact override | an override (`word_band_override` / `expected_preview_count` / `subject_mode`) is honored ONLY when echoed in the LOCKED brief; an unlogged override is refused and the SACRED default re-applies | `AF-EMAIL-OVERRIDE-UNLOGGED` |
| Process integrity | when the deploy artifact (`build-plan.json`) is present the REAL `PROCESS-CERTIFICATE.json` is required (`all_phases_pass` + a `certificate_sha` that recomputes); phases cannot be skipped | `AF-PROCESS-INTEGRITY` |
| Deploy-plan valid | a present `working/deploy/build-plan.json` validates against `schema/build-plan.schema.json`'s contract | `AF-EMAIL-DEPLOY-PLAN-INVALID` |
| Intake gate | brief comes from the turn-gated ledger (one block) — verified against an INDEPENDENT `conversation_ledger` export when present (authoritative), else from the self-attested one-block flags — the skill type matches, and all six brief fields are present | `AF-EMAIL-INTAKE-SPLIT` / `AF-EMAIL-TYPE-MISMATCH` / `AF-EMAIL-BRIEF-INCOMPLETE` |

**Client-exact overrides win.** The word band is the DEFAULT floor; when the client states an
exact per-email length it is honored verbatim, never floored, capped, or substituted. (Client-exact
is the fleet-wide absolute law.) The override is honored ONLY when it is **logged in the LOCKED
brief** (`locked_overrides.word_band_override` / `expected_preview_count` / `subject_mode`) — an
override that appears on the authoring-written `emails.json` but is NOT echoed in the locked brief
is refused (`AF-EMAIL-OVERRIDE-UNLOGGED`) and the SACRED default re-applies, so an override can never
silently loosen a gate. The honored override's source is recorded on the process certificate.

## How it runs — THROUGH one canonical entry

```
bash 50-email-engine/email-engine-entry.sh --run-dir <RUN_DIR> [--plan]
```

The entry runs three fail-closed gates (DEPS -> BYPASS-SCAN -> VERSION/HASH-PIN), mints a
run-scoped nonce, and dispatches the deterministic orchestrator `run_email_engine.py`, which
walks the manifest P1 -> P2 -> P3 -> P4 with no phase skips. **P3 QC shells out to
`prove-email.py` and refuses to advance on any `AF-EMAIL-*` violation.** Writing and running a
hand-rolled sender (`python3 working/*send*.py`, a direct GHL/SMTP send outside the sanctioned
handoff) is the **ungoverned path and is FORBIDDEN** (`AF-EMAIL-SEND-BYPASS`). A gate may be
skipped ONLY by a logged owner approval token in
`<run-dir>/working/checkpoints/process_manifest.json` — never silently, never by an agent's choice.

## Deploy is DRAFT-ONLY (P4)

P4 emits a Skill-44 (Convert & Flow / GoHighLevel) build plan as a **draft workflow** only.
Nothing sends. A human approves before any send, and the Skill-44 built-workflow QC gate
(`>= 8.5`) runs on the draft. Scope is workflow email steps only.

## Client-provider rule (binding)

On a client box this skill uses the **client's own configured providers and keys** — never the
operator's, never Anthropic / `claude-*` model ids. The deterministic gates
(`prove-email.py`, `email_matcher.py`, `run_email_engine.py`) are model-free Python that run
identically everywhere; the authoring/QC LLM tiers named for the client path are the client's
own provider chain. This skill is provider-neutral by construction.

## Verify

`bash 50-email-engine/verify.sh` is the self-verify gate: it runs `prove-email.py --self-test`
(built-in VALID + VIOLATION fixtures), `email_matcher_cli.py --selftest`,
`emit_build_plan.py --selftest`, `email-library/register.py --check`, the golden
reproduce, and the broken-variant rejection proof — and exits nonzero on any regression,
so it can gate a merge / CI / a post-install check.

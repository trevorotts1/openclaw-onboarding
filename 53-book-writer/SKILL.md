---
name: book-writer
description: Turns ONE completed book-intake interview into a tone-matched 12-chapter nonfiction book plus companion assets — avatar dossier, the blended "The {First} {Last} Tone", locked title/subtitle + approved outline, print-ready manuscript, a 30-Day Challenge, and an AI cover prompt — delivered as labeled files in ~/Downloads. Fully local at runtime — no n8n, no Airtable, no Google/Gmail/Slack/GHL — on the client's OWN model providers, never Anthropic. A Book/Brand version selector runs FIRST: version=book runs here; version=brand hands off to Skill 52 (avatar-alchemist). Modes full (flagship 12-chapter book) and 4x3x3 (offer book: 30 titles / 4 Transformational Outcomes / KP doc / 433_Deck_Data.json handed to Skill 51). Every SACRED count/floor is a fail-closed Python prover with a negative test; a run cannot claim "done" without a signed process certificate. Trigger with "write my book", "run book writer", "book version of avatar alchemist", "12-chapter book for <name>", or "4x3x3 book".
version: 1.1.6
---

# Book Writer — Ghostwriting Engine (Avatar Alchemist, BOOK version) (Skill 53)

The OpenClaw conversion of the 8-workflow n8n ghostwriting factory (the flagship 153-node
"Book Writer" + the 121-node "4x3x3 w Book Writer" + factored sub-agents) into a self-contained
skill: **baked versioned prompts + a local artifact store + in-chat checkpoint approvals + one
deterministic assembler/certifier + fail-closed provers + labeled deliverables in `~/Downloads`.**
**Zero n8n, Airtable, Google Drive/Docs/Slides, Gmail, Slack, or GHL at runtime — fully local +
the client's own model providers (never Anthropic).**

> The 12-chapter method captured in `MASTERDOC.md` is **SACRED** — never floored, reordered, or
> reinterpreted. Every rule below is machine-enforced by a fail-closed prover, never advisory.

## Authoring layer — SHIPPED vs. PENDING (truthful status)

> **Disclosure (no-false-done):** the sentence above about "baked versioned prompts" describes the
> intended full architecture. As of this version, the baked prompt triplets that actually SHIP are the
> **five shared-tone-core stages only** — `prompts/04-tone-style-1` … `prompts/08-blended-tone`, each a
> `{system.md, methodology.md, user.md}` triplet byte-identical to `shared-utils/tone-writing-core`. The
> full 12-chapter **authoring layer is PENDING** and is **deferred to a separate, scoped follow-up
> campaign** (repo-only; fleet rollout stays HELD).

- **Shipped now:** the intake + Book/Brand selector, `BOOK-WRITER-MANIFEST.json`, the deterministic
  assembler/certifier (`run_book_writer.py`), all twelve fail-closed provers + `verify_tone_core_sync.py`,
  the seven role SOPs under `roles/` (registered in `roles/_index.json`), and the **five tone-core baked
  prompt triplets (stages 04–08)**.
- **Pending (NOT yet shipped):** the baked prompt triplets for the **22 non-tone authoring stages** that
  `BOOK-WRITER-MANIFEST.json` `stages[]` references by `prompt_dir` but that are not present on disk —
  avatar (`01`–`03`), titles/blurb/chapter-titles/outline/extract (`10`–`14`), the four chapter batches
  (`15`–`18`), the two book rewrites (`19`–`20`), the 30-Day Challenge (`21`), cover prompt/image
  (`22`–`23`), and the 4x3x3 extras (`41`–`45`). Until those triplets ship, the corresponding stages are
  described by the `roles/` SOPs + `MASTERDOC.md` method rather than driven by a pinned baked prompt
  triplet, so a full end-to-end book has not yet been exercised through baked authoring prompts.
- **Unchanged by this disclosure:** every SACRED invariant below and its fail-closed prover still holds —
  the provers MEASURE any produced artifact regardless of how the stage was generated; nothing here
  weakens a gate. This section only corrects the over-claim that the *whole* stage graph already ships as
  baked prompts. Building out the pending triplets is the follow-up campaign's scope, not this fix.

## What this skill produces / owns

- `GOLDEN-BOOK-BIBLE.md` — the pinned contract for the golden regression sample (fictional author
  **Marcus Halloway**, *The Quiet Authority*).
- `BOOK-WRITER-MANIFEST.json` — the single source of truth: phases (P0→P8), the stage graph, the
  `AF-BK-*` autofail map, tiers, modes, and the `shared_tone_core` key.
- `prompts/<stage dirs>/{system.md, methodology.md, user.md}` — the baked generators. **Only stages
  04–08 (the shared tone core, byte-identical to `shared-utils/tone-writing-core`) ship today; the
  remaining authoring-stage prompt dirs referenced by the manifest are PENDING** — see "Authoring layer —
  SHIPPED vs. PENDING" above.
- `intake/{intake-schema.json, INTAKE-TEMPLATE.md}` — the Book/Brand selector (Q0) + the book intake.
- `scripts/` — the twelve fail-closed provers, `verify_tone_core_sync.py`, and the process guard.
- `run_book_writer.py` — the deterministic assembler/certifier.
- `book-writer-entry.sh` — the ONE sanctioned front door (deps → bypass-scan → hash-pin → nonce).
- `roles/` — the 7 dispatchable role SOPs (AVATAR-ANALYST · TONE-ANALYST · TITLE-STRATEGIST ·
  BOOK-ARCHITECT · CHAPTER-WRITER · PACKAGER · REVISER), registered with a canonical `content_sha` in
  `roles/_index.json` (re-stamp with `scripts/hash_role_index.py` after any role edit; `--check` gates it
  in `verify.sh`). The SOLE dispatcher (foreman) is the assembler `run_book_writer.py` — roles never
  invoke each other. `examples/golden-marcus-halloway/` — the worked example.

## Deliverables (labeled, local)

Avatar dossier · Tone doc ("The {First} {Last} Tone") · locked title/subtitle (`APPROVED-TITLE.txt`)
· blurb + 12 chapter titles · approved outline · manuscript (.md) · 30-Day Challenge · cover prompt
(+ optional cover PNG) · 4x3x3 extras (30 titles / outcomes / KP doc / `433_Deck_Data.json` → Skill
51) · `00-INDEX.md` + `MANIFEST.json` + signed `PROCESS-CERTIFICATE`.

## SACRED invariants (each is a fail-closed prover with a negative test)

| Invariant | Rule | Code |
|---|---|---|
| Version selector | `version` ∈ {book,brand} explicit; brand hands off to Skill 52, never runs here | `AF-BK-VERSION` |
| Complete intake | every required field present, non-boilerplate | `AF-BK-INTAKE-MISSING` |
| Locked title | title + subtitle byte-exact in blurb, outline, every chapter, cover prompt, manuscript | `AF-BK-TITLE-LOCK` |
| Story placement | each non-N/A personal story's key phrase in the outline AND manuscript | `AF-BK-STORIES` |
| 12 chapters | exactly 12, numbered 1..12 | `AF-BK-CHAP-COUNT` |
| Chapter length | each 2000–3500 **stripped** words (padding is inert) | `AF-BK-CHAP-LEN` |
| Batch continuity | batch N's receipt records the sha256 of every prior chapter embedded | `AF-BK-CONTINUITY` |
| Blended tone | ≥ 3000 stripped words (shared tone core) | `AF-BK-TONE-LEN` |
| 30-Day Challenge | exactly 30 day-sections | `AF-BK-CHALLENGE` |
| 4x3x3 counts | exactly 4 outcomes AND 30 titles | `AF-BK-433-COUNTS` |
| 4x3x3 map | 12 chapters = 4 phases × 3; deck-data schema-valid | `AF-BK-433-MAP` |
| No placeholders | no unresolved `{{…}}` / `$('…')` tokens | `AF-BK-PLACEHOLDER` |
| No Anthropic | no `/anthropic\|claude/i` model id in `RUN-LEDGER.json`; no operator creds in env | `AF-BK-ANTHROPIC` |
| Anonymization | no configured client-name token in files/metadata (fictional names only) | `AF-BK-ANON` |
| Process integrity | phases in order; certificate only on a full pass; enforcement hash pinned; run through the entry | `AF-BK-STAGE-SKIPPED` / `AF-BK-PROCESS-INTEGRITY` / `AF-BK-HASH-PIN` / `AF-BK-ENTRY-BYPASS` |

## How it runs — one governed path, never a second build path

```
bash 53-book-writer/book-writer-entry.sh --run-dir <RUN_DIR>   # deps → bypass-scan → hash-pin → nonce
python3 53-book-writer/run_book_writer.py --run-dir <RUN_DIR>  # deterministic assembler/certifier (nonce-gated)
```

1. **Gate 0** — `prove_bw_intake.py` proves the intake + Book/Brand selector. `version=brand` hands
   off to Skill 52 (or parks); `version=book` runs. `mode` ∈ {full, 4x3x3}.
2. **Phases P0→P8** — the assembler walks phases IN ORDER with NO skips: intake → avatar → tone →
   titles-gate → outline-gate → chapters (four STRICTLY-SEQUENTIAL batches, continuity proven) →
   package → QC → deliver. Human checkpoints (GATE-1 titles / GATE-2 outline / GATE-3 approval /
   GATE-4 second revision) are in-chat, receipted, in the exact source order — and the assembler
   REQUIRES the matching gate receipt (`approved:true` + `approved_by` + timestamp, in
   `run/checkpoints/gate-receipts.json`) before advancing (GATE-1/2 always; GATE-3/4 when a revision
   round ran). P8-DELIVER promotes the certified bundle to `delivery/`, copies it to a labeled,
   timestamped `~/Downloads` folder, and re-verifies every file's sha256 against `MANIFEST.json`; an
   uncertified bundle is quarantined and never sits in `delivery/`.
3. **Provers** — the twelve fail-closed provers MEASURE the stripped text and ignore self-reported
   counts; any `AF-BK-*` violation blocks the run.
4. **Certificate** — a full P0→P8 pass mints `PROCESS-CERTIFICATE.{json,md}` with a deterministic
   `certificate_sha`. **"Done" is claimed only with the certificate path (no-false-done).**

## The provers (fail-closed; `sys.exit(2)` on violation; each carries `--self-test`)

| Prover | Gates / AF codes |
|---|---|
| `prove_bw_intake.py` | AF-BK-INTAKE-MISSING / AF-BK-VERSION |
| `prove_bw_titlelock.py` | AF-BK-TITLE-LOCK |
| `prove_bw_stories.py` | AF-BK-STORIES |
| `prove_bw_chapters.py` | AF-BK-CHAP-COUNT / AF-BK-CHAP-LEN |
| `prove_bw_continuity.py` | AF-BK-CONTINUITY |
| `prove_bw_tone.py` | AF-BK-TONE-LEN |
| `prove_bw_challenge.py` | AF-BK-CHALLENGE |
| `prove_bw_433.py` | AF-BK-433-COUNTS / AF-BK-433-MAP |
| `prove_bw_placeholder.py` | AF-BK-PLACEHOLDER |
| `prove_bw_noanthropic.py` | AF-BK-ANTHROPIC |
| `prove_bw_anon.py` | AF-BK-ANON |
| `prove_bw_process.py` | AF-BK-STAGE-SKIPPED / PROCESS-INTEGRITY / HASH-PIN / ENTRY-BYPASS |
| `verify_tone_core_sync.py` | tone stages 04–08 byte-identical to `shared-utils/tone-writing-core` |

## Client-provider rule (binding)

On a client box the skill uses the **client's own configured providers and keys** — never the
operator's, never Anthropic model ids. `preflight.sh` REALLY probes the box (bounded `ollama list` +
provider-key NAMES, never values), preserves any operator-filled tiers, and **hard-fails (exit 7) when a
REQUIRED tier (HEAVY-WRITER / MID-WRITER / FORMATTER) is unresolved or resolves to an `/anthropic|claude/i`
id** — an unconfigured box never silently ships empty tiers. It writes `model-map.json`
(HEAVY-WRITER / MID-WRITER / FORMATTER / RESEARCHER / IMAGE tiers + `provider_caps` + a `probe` block) and,
with `--run-dir`, cross-checks the resolved tier→model map into `RUN-LEDGER.json` (so the no-Anthropic
gate re-scans the resolved ids). `AF-BK-ANTHROPIC`
hard-fails any run whose resolved model id matches `/anthropic\|claude/i`. The client's express model
choice is never substituted. Role files and SOPs name client-provider tiers, never `claude-*` ids.

## Downstream handoffs (see INSTRUCTIONS.md)

`433_Deck_Data.json` + deck outline → **Skill 51** (signature-presentation); avatar dossier + blended
tone ↔ **Skill 52** (both directions); `Book_Cover_Prompt.md` → any image provider; the manuscript →
**Skills 49/50** for launch assets.

## Relationship to Skill 52 (avatar-alchemist) — cross-linked, NEVER merged

Skill 52 is the **BRAND** version of the Avatar Alchemist; this skill (53) is the **BOOK** version.
The shared **Book/Brand selector (Q0)** routes `version=book` here and `version=brand` to Skill 52 —
an explicit, receipted hand-off, **never a silent cross-version fallback** in either direction. Both
skills bake a lockstep copy of the shared avatar/tone IP at `shared-utils/tone-writing-core/` and prove
it with `verify_tone_core_sync.py`; **a change to those shared prompts in either skill MUST flag the
sibling for review.** **Anthology is the SEPARATE sibling Skill 54 (anthology-writer)** — referenced
only as a sibling and never built or merged here. Do not merge the two skills.

## Prerequisites

- python3 (stdlib only — `verify-deps.sh` proves zero external runtime services).
- The client's own model providers configured on the box (Ollama / OpenRouter / etc.).
- Optional PDF toolchain (pandoc + weasyprint) if a print-ready PDF is wanted; the manuscript `.md`
  always delivers regardless.

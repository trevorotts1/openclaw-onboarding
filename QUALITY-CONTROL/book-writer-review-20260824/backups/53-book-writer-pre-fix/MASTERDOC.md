# Book Writer — MASTERDOC (anonymized IP overview)

The **BOOK version of the Avatar Alchemist**. It replaces an 8-workflow n8n ghostwriting factory
(flagship 153-node "Book Writer" + 121-node "4x3x3 w Book Writer" + five factored sub-agents) with a
self-contained skill. Everything that is not an LLM call — Airtable prompt fetches, Drive folder
scaffolding, HTML→Google-Doc chains, base64 nodes, Gmail forms, Slack posts, GHL stage updates — is
replaced by skill infrastructure. The engine is ~45 distinct LLM calls plus plumbing; the plumbing dies.

## The method (SACRED — machine-enforced, never advisory)

One completed book-intake interview → a tone-matched **12-chapter nonfiction book** + companion assets:

1. **Avatar** — 32-question avatar analysis (Phase B), rewritten niche/primary-goal.
2. **Tone** — four style analyses blended into **"The {First} {Last} Tone"** (≥3000 words). This is the
   shared tone/writing core (`shared-utils/tone-writing-core`), identical to Skills 52 (Brand) + 54
   (Anthology).
3. **Titles → GATE-1** — the client LOCKS a title + subtitle. From here they are IMMUTABLE and must
   appear byte-exact in every downstream artifact ("DO NOT CHANGE ABOVE TITLES" as code).
4. **Blurb → Chapter titles → Outline → GATE-2** — the outline places every non-N/A personal story
   verbatim ("we must use it for sure").
5. **Chapters** — exactly 12, each **2000–3500 stripped words**, written in **four STRICTLY-SEQUENTIAL
   batches** with **all prior chapters injected** (the continuity mechanism; never parallelized).
6. **Package** — deterministic manuscript assembly + a **30-Day Challenge** (exactly 30 days) + a cover
   prompt (+ optional cover image), then up to **two receipted revision rounds** (GATE-3 / GATE-4).
7. **Deliver** — a labeled local `~/Downloads` bundle + a signed `PROCESS-CERTIFICATE` (no-false-done).

## Modes

- **`full`** — the flagship 12-chapter book (source 153 nodes).
- **`4x3x3`** — the offer book: exactly **30 program titles**, exactly **4 Transformational Outcomes**,
  a KP document, and a schema-valid `433_Deck_Data.json` + deck outline handed to **Skill 51**. The 12
  chapters map **4 phases × 3 chapters**. Consumes an existing avatar dossier + tone doc.
- **Anthology** is the SEPARATE sibling **Skill 54** (multi-author). Referenced, never built here.

## Enforcement (the IP teeth)

Every SACRED rule is a fail-closed, model-free, stdlib-only prover in `scripts/` that MEASURES the
stripped text and ignores self-reported counts — see the `AF-BK-*` map in `BOOK-WRITER-MANIFEST.json`
and the invariants table in `SKILL.md`. The single sanctioned entry (`book-writer-entry.sh`) runs
deps → bypass-scan → hash-pin → nonce; the deterministic assembler (`run_book_writer.py`) walks phases
P0→P8 with no skips and mints the certificate only on a full pass.

## Runtime posture (binding)

Fully local. **No n8n / Airtable / Google / Gmail / Slack / GHL at runtime.** The client's OWN model
providers only — **never Anthropic**, never operator keys. Deliverables are labeled files in
`~/Downloads`; human gates are in-conversation checkpoints. We move in silence (operator-verbose,
client-silent). Fictional names only in fixtures/examples; the only permitted real name is the owner.

# Book-Writer-Craft SOP Cluster (`universal-sops/book-writer-craft/`)

The SHARED, cross-department procedure for how any department discovers and drives the **Book Writer
Engine (Skill 53 — the BOOK version of the Avatar Alchemist)** end to end: ONE completed book-intake
interview -> a Book/Brand version selector -> nine STRICTLY-ORDERED phases (P0->P8) -> a tone-matched
12-chapter nonfiction book plus companion assets -> a labeled LOCAL delivery bundle + a signed process
certificate.

This cluster is the `universal-sops` face of the capability (parallel to `avatar-craft/`,
`email-craft/`, `product-bio-craft/`, `funnel-craft/`). It does NOT re-implement the engine. The
authoritative machine spine lives in the skill:

- `53-book-writer/BOOK-WRITER-MANIFEST.json` — the SINGLE SOURCE OF TRUTH: the ordered phases
  (P0-INTAKE -> P8-DELIVER), the stage graph, tiers, both modes (`full`, `4x3x3`), the gate order,
  and the full `AF-BK-*` autofail map (each code's trigger + the prover that enforces it).
- `53-book-writer/scripts/prove_bw_*.py` — the twelve fail-closed, model-free, stdlib-only provers
  (each with a built-in `--self-test`). They MEASURE the STRIPPED text (markdown + whitespace removed)
  and the artifact bytes; a model's self-reported chapter/word count is NEVER trusted, so a
  whitespace-padding attack cannot fake a floor.
- `53-book-writer/run_book_writer.py` — the deterministic assembler/certifier. It walks the phases IN
  ORDER with NO skips, runs the provers, and — only on a full P0->P7 pass — mints the certificate with a
  deterministic `certificate_sha` over the MEASURED values (same authored input -> same sha).
- `53-book-writer/book-writer-entry.sh` — the ONE sanctioned front door (DEPS -> BYPASS-SCAN ->
  HASH-PIN -> NONCE), fail-closed; it mints the run-scoped nonce the assembler requires and dispatches
  it. Running the assembler by hand around the front door is refused (no valid nonce).
- `53-book-writer/roles/` — the 7 dispatchable role SOPs + their named-persona registry
  (`roles/PERSONAS.json`); `GOLDEN-BOOK-BIBLE.md` + `examples/golden-marcus-halloway/` — the pinned
  golden regression sample (fictional author, *The Quiet Authority*).
- `53-book-writer/intake/{intake-schema.json, INTAKE-TEMPLATE.md}` — the version selector (question 0)
  + the book intake.
- `53-book-writer/prompts/<stage dirs>/{system.md, methodology.md, user.md}` — the baked, provider-
  agnostic generators. Stages **04-08 are the shared tone core** (byte-identical to
  `shared-utils/tone-writing-core`, proved by `scripts/verify_tone_core_sync.py`).

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/book-writer-craft/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **53** book-writer | "write my book" · "a nonfiction book" · "turn my ideas into a book" |
| **54** anthology-writer | "my anthology chapter" · "write my contributor chapter" · "write my chapter for the anthology" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->

## The ONE way in

A book is built by running, and ONLY by running, the canonical fail-closed front door, which runs its
three gates, mints the one-time nonce the assembler requires, and dispatches it:

```
bash 53-book-writer/book-writer-entry.sh --run-dir <RUN_DIR>   # deps -> bypass-scan -> hash-pin -> nonce -> assembler
```

`--plan` prints the canonical phase plan (the gates still run). The authoring layers
(avatar / tone / titles / outline / chapters / challenge / cover) run UPSTREAM on the CLIENT's own
providers and drop their artifacts into `<RUN_DIR>/run/`; the assembler is model-free and only measures
and certifies them. Hand-rolling an Airtable/Drive/Slack/Gmail/n8n/GHL uploader in the run directory is
the UNGOVERNED path and is refused fail-closed (`AF-BK-ENTRY-BYPASS`). Delivery is a labeled LOCAL bundle
in `~/Downloads/`.

## Files

| File | What it governs |
|---|---|
| `SOP-BOOK-01-TWELVE-CHAPTER-BOOK.md` | What the book is, when to build it, the Book/Brand selector + the intake, the full **gate order (P0->P8)** + the **certificate contract**, the four in-chat human checkpoints, and local delivery. |

The autofail table and phase order are NOT duplicated here — they live authoritatively in
`53-book-writer/BOOK-WRITER-MANIFEST.json` (the `phases[]` order + the `AF-BK-*` table). This SOP points
at them so there is exactly one source of truth.

## SACRED law (from `53-book-writer/MASTERDOC.md`)

- The 12-chapter method, its ORDER, and every count/floor are SACRED — never floored, reordered, or
  reinterpreted. Every rule is machine-enforced by a fail-closed prover, never advisory.
- **Version selector runs FIRST:** question 0 is Book vs Brand (`AF-BK-VERSION`). `version=book` runs
  this pipeline; `version=brand` hands off to Skill 52 (avatar-alchemist) or PARKS fail-closed — it is
  NEVER served by the book pipeline. `mode` is `full` (the flagship 12-chapter book) or `4x3x3` (the
  offer book: 30 titles / 4 Transformational Outcomes / KP doc / `433_Deck_Data.json` -> Skill 51).
- **Measured counts (self-report ignored):** exactly 12 chapters numbered 1..12 (`AF-BK-CHAP-COUNT`);
  each chapter 2000-3500 stripped words (`AF-BK-CHAP-LEN`); the blended tone >= 3000 stripped words
  (`AF-BK-TONE-LEN`); exactly 30 day-sections in the 30-Day Challenge (`AF-BK-CHALLENGE`); in `4x3x3`,
  exactly 4 outcomes AND 30 titles, and 12 chapters mapping to 4 phases x 3 (`AF-BK-433-COUNTS` /
  `AF-BK-433-MAP`).
- **Locked title immutability:** the GATE-1 title + subtitle appear BYTE-EXACT in the blurb, outline,
  every chapter, the manuscript title page, and the cover prompt (`AF-BK-TITLE-LOCK`).
- **Verbatim personal stories:** each non-N/A personal story's key phrase is present in the approved
  outline AND the manuscript (`AF-BK-STORIES`).
- **Continuity by design:** the four chapter batches are STRICTLY SEQUENTIAL (no parallel flag); batch N
  embeds every prior chapter and its receipt records their sha256 (`AF-BK-CONTINUITY`).
- **Provenance:** phases in order with no skips (`AF-BK-STAGE-SKIPPED`); a signed process certificate
  issued only on a full P0->P7 pass (`AF-BK-PROCESS-INTEGRITY`); no unresolved `{{...}}` / `$('...')`
  tokens (`AF-BK-PLACEHOLDER`). **No signed certificate = not done.**
- **Client-exact overrides win:** a client-stated exact target is honored verbatim and logged — never
  floored, capped, or substituted (fleet-wide absolute law).

## Named personas (the 7 roles)

The engine's seven dispatchable roles carry named governing personas in
`53-book-writer/roles/PERSONAS.json` (metadata consumed by the standard Skill-22/23 persona selector;
LOCAL to the skill, not client personas, and not part of the Skill-22 persona SET / count triad): the
**Reader Cartographer** (avatar), the **Voice Alchemist** (tone), the **Title Locksmith** (GATE-1
titles), the **Outline Architect** (blurb/outline/GATE-2), the **Continuity Ghostwriter** (the four
sequential chapter batches), the **Faithful Reviser** (the two GATE-3/4 revision rounds), and the
**Provenance Binder** (the deterministic assembler/certifier). Roles never invoke each other — the
assembler (`run_book_writer.py`) is the ONLY dispatcher.

## Relationship to Skills 52 (Brand) + 54 (Anthology) — cross-linked, NEVER merged

Skill 52 is the BRAND version of the Avatar Alchemist; Skill 53 is the BOOK version; Skill 54
(anthology-writer) is the separate anthology sibling. The shared **Book/Brand selector (Q0)** routes
`version=book` here and `version=brand` to Skill 52 — an explicit, receipted hand-off, never a silent
cross-version fallback in either direction. All three bake a lockstep copy of the shared tone/writing IP
at `shared-utils/tone-writing-core/` and prove it with `verify_tone_core_sync.py`; **a change to those
shared prompts in any one skill MUST flag the siblings for review.** Do not merge the skills.

## Command Center registration (operator action)

The Command Center surfaces this capability as ONE `sops` row so the Triad Rule auto-resolves a "write
my book" / "book version of avatar alchemist" request to it. NO schema change (a job is a `tasks` row).
Because the mission-control repo is a separate submodule not reachable from the skill worktree,
inserting/refreshing the row is an OPERATOR action at CC install/update time — via
`32-command-center-setup/scripts/add-sop.sh` (or the dashboard `POST /api/sops/import-role-library`).
Suggested row:

- `slug`: `book-writer-twelve-chapter-book`
- `name`: `Book Writer: turn one book-intake into a 12-chapter book (+ 4x3x3 offer book)`
- `department`: `marketing`
- `task_keywords`: `write my book, book writer, book version of avatar alchemist, 12-chapter book,
  4x3x3 book, ghostwrite, manuscript, 30-day challenge, book cover prompt, book outline`
- `success_criteria`: signed `PROCESS-CERTIFICATE.json` present (full P0->P8 pass, deterministic
  `certificate_sha`); exactly 12 chapters on-band + >= 3000-word blended tone + exactly 30 challenge
  days + byte-exact locked title/subtitle; Book/Brand selector honored; labeled local bundle in
  `~/Downloads/<First>_<Last>-Book/`.

## Flexibility = guide-not-rule

The engine is a GUIDE and a RESOURCE for how a department fulfils a book request; honor an explicit owner
choice (logged on the certificate). But the SACRED counts/floors above are enforced by the provers and
are not opinions — a violation is a hard, named `AF-BK-*` auto-fail.

## Client-runtime rule (binding)

The shipped engine on a client box NEVER uses Anthropic / `claude-*` model ids or operator keys. The
authoring stages run on the CLIENT's own configured provider chain (`53-book-writer/preflight.sh` probes
the box and writes `model-map.json`: HEAVY-WRITER deep authoring / MID-WRITER structured /
FORMATTER fast-structured / RESEARCHER search + compose / IMAGE cover). A client's express model choice
is never substituted. The deterministic gates (`prove_bw_*.py`, `run_book_writer.py`) are provider-neutral
stdlib Python and run identically everywhere; `AF-BK-ANTHROPIC` hard-fails any run whose resolved model
id matches `/anthropic|claude/i`, and `AF-BK-ANON` hard-fails any configured client-name token in a
shipped file or deliverable. The tone subsystem (stages 04-08) is the canonical shared tone/writing core
at `shared-utils/tone-writing-core/`; the skill bakes a lockstep copy and proves it with
`scripts/verify_tone_core_sync.py`.

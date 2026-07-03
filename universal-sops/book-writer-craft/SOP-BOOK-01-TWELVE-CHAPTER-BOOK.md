# SOP-BOOK-01: BUILD THE 12-CHAPTER BOOK (gate order + certificate contract)

**Cluster:** Book-Writer-Craft Rules (`universal-sops/book-writer-craft/`)
**Master authority:** `53-book-writer/BOOK-WRITER-MANIFEST.json` (the ordered `phases[]` P0->P8 + the `AF-BK-*` table) + `53-book-writer/MASTERDOC.md` (the SACRED 12-chapter method)
**Owning department:** Marketing
**Owning roles:** the 7 named book personas (`53-book-writer/roles/PERSONAS.json`), dispatched by the assembler; routed by the Chief Marketing Officer
**Canonical entry:** `53-book-writer/book-writer-entry.sh` (which mints the nonce and dispatches `run_book_writer.py`)
**Gates this SOP satisfies:** AF-BK-INTAKE-MISSING, AF-BK-VERSION, AF-BK-TONE-LEN, AF-BK-TITLE-LOCK, AF-BK-STORIES, AF-BK-CHAP-COUNT, AF-BK-CHAP-LEN, AF-BK-CONTINUITY, AF-BK-CHALLENGE, AF-BK-433-COUNTS, AF-BK-433-MAP, AF-BK-PLACEHOLDER, AF-BK-ANTHROPIC, AF-BK-ANON, AF-BK-STAGE-SKIPPED, AF-BK-PROCESS-INTEGRITY, AF-BK-HASH-PIN, AF-BK-ENTRY-BYPASS

---

## 0. WHAT THIS ARTIFACT IS

The **book** is the full Book Writer output: from ONE completed book-intake interview, nine ordered
phases produce a tone-matched **12-chapter nonfiction book** plus companion assets — an avatar dossier,
the blended **"The {First} {Last} Tone"** (>= 3000 words), a locked title + subtitle, an approved
outline, the print-ready manuscript, a **30-Day Challenge** (exactly 30 day-sections), and an AI cover
prompt — delivered as labeled markdown in `~/Downloads/`. Two modes:

| Mode | What it produces |
|---|---|
| `full` | the flagship 12-chapter book + all companion assets. |
| `4x3x3` | the offer book: 30 program titles, 4 Transformational Outcomes, a KP doc, and a schema-valid `433_Deck_Data.json` + deck outline handed to **Skill 51** (signature-presentation). |

The manuscript and its receipts ship as a labeled LOCAL bundle in `~/Downloads/<First>_<Last>-Book/` with
a signed `PROCESS-CERTIFICATE.{json,md}`. The tone subsystem (stages 04-08) is the canonical shared
tone/writing core at `shared-utils/tone-writing-core/`; the skill bakes a lockstep copy proven by
`scripts/verify_tone_core_sync.py`.

## 1. WHEN TO BUILD IT

Build it when a client wants a full-length nonfiction book (or the `4x3x3` offer book) written in their
own blended voice off one completed book-intake interview. If the request is for the full BRAND
intelligence package (avatar, awareness levels, Facebook ad system, booking bots, hero page), that is
**Skill 52 (avatar-alchemist)**, not this skill. Routing disambiguation is the Book/Brand selector below:
`version=book` -> this pipeline; `version=brand` -> Skill 52. The anthology variant is the separate
sibling **Skill 54 (anthology-writer)** — referenced here only as a sibling and never merged.

## 2. THE INTAKE + BOOK/BRAND SELECTOR (P0-INTAKE, turn-gated)

Ask the intake in a SINGLE message, never one-question-per-turn. **Question 0 is the version selector:
Book or Brand.** The selected version determines which pipeline answers:

- `version=book` -> the book question set -> this P0->P8 pipeline. `mode` is `full` or `4x3x3`.
- `version=brand` -> hands off to Skill 52 (avatar-alchemist); if no brand route resolves, the run PARKS
  fail-closed — it is NEVER served by the book pipeline (`AF-BK-VERSION`).

`prove_bw_intake.py` proves the intake + selector: any required field
(`version, mode, first_name, last_name, ideal_avatar, niche, primary_goal, tone_style_1, tone_style_2,
book_about, book_stories, cover_description`) missing/empty/boilerplate is `AF-BK-INTAKE-MISSING`; a
version that is unset or not exactly `book|brand`, a mismatched question set, or a `mode` not in
`{full, 4x3x3}` is `AF-BK-VERSION`. Never fabricate an intake answer — client words only; return the gap
list and STOP if a required field is missing. A self-attested "intake complete" flag is never trusted:
the gate reads the actual fields. `book_stories` may be `N/A`; a non-N/A story is then enforced verbatim
downstream (`AF-BK-STORIES`).

## 3. THE GATE ORDER — P0 -> P8 (enforcement, not description)

The assembler `run_book_writer.py` walks the nine phases IN ORDER with **NO phase skips**. A phase that
fails BLOCKS the run fail-closed (`AF-BK-STAGE-SKIPPED`); the failing artifact is re-authored (verifier
!= author) and the WHOLE phase is re-proved. Bands are MEASURED on the STRIPPED text and the artifact
bytes; a model's self-reported count is never trusted.

| # | Phase | Produces | Gate codes (all measured) |
|---|---|---|---|
| P0 | INTAKE + Book/Brand selector | `run/intake.json` | `AF-BK-INTAKE-MISSING`, `AF-BK-VERSION` |
| P1 | AVATAR dossier (stages 01-03) | `run/artifacts/01-avatar.md` | (dossier present; primary goal echoed) |
| P2 | TONE — 4 style analyses + the blended **"The {First} {Last} Tone"** (shared tone core, stages 04-08) | `run/artifacts/08-blended-tone.md` | `AF-BK-TONE-LEN` (>= 3000 stripped words) |
| P3 | TITLES -> **GATE-1** (client LOCKS title + subtitle) | `run/artifacts/APPROVED-TITLE.txt` | `AF-BK-TITLE-LOCK` (byte-exact everywhere downstream) |
| P4 | OUTLINE — blurb -> 12 chapter titles -> outline -> **GATE-2** (client approves the outline); 4x3x3: 30 titles/outcomes -> **GATE-433** | `run/artifacts/13-outline.md` | `AF-BK-STORIES` (each non-N/A story key phrase in the outline) |
| P5 | CHAPTERS — four STRICTLY-SEQUENTIAL batches (1-3, 4-6, 7-9, 10-12) | `run/chapters/ch01..ch12.md` | `AF-BK-CHAP-COUNT` (exactly 12), `AF-BK-CHAP-LEN` (each 2000-3500), `AF-BK-CONTINUITY` (batch N embeds every prior chapter; receipt records their sha256), `AF-BK-STORIES` |
| P6 | PACKAGE — manuscript + 30-Day Challenge + cover prompt (+ optional **GATE-3** / **GATE-4** revision rounds) | `delivery/<First>_<Last>-Book/` | `AF-BK-CHALLENGE` (exactly 30 day-sections), `AF-BK-PLACEHOLDER` (no unresolved `{{...}}` / `$('...')`), `AF-BK-TITLE-LOCK` |
| P7 | QC battery | `run/qc/` | `AF-BK-ANTHROPIC` (no `/anthropic\|claude/i` model id; no operator cred in env), `AF-BK-ANON` (no configured client-name token), `AF-BK-433-COUNTS` + `AF-BK-433-MAP` (mode=4x3x3) |
| P8 | DELIVER — labeled local bundle + signed certificate | `delivery/<First>_<Last>-Book/PROCESS-CERTIFICATE.json` | `AF-BK-STAGE-SKIPPED`, `AF-BK-PROCESS-INTEGRITY` |

**The four in-chat human checkpoints (exact source order preserved).** These replace the source's
Gmail `sendAndWait` forms; each gate receipt records the human's actual reply text + timestamp, and
downstream stage receipts reference the gate-receipt hash they depended on (approvals cannot be
back-filled):

1. **GATE-1 (titles):** the client LOCKS one title + subtitle. Now IMMUTABLE — byte-exact in the blurb,
   outline, every chapter, the manuscript title page, and the cover prompt.
2. **GATE-2 (outline):** the client approves the outline before any chapter is written. Chapters cannot
   start earlier.
3. **GATE-3 (approval) + GATE-4 (second revision):** up to TWO receipted revision rounds applied to the
   affected chapters only, never touching the locked title/subtitle. A third round requested = a NEW run
   (source law).

Entry-set integrity is also enforced: `AF-BK-HASH-PIN` (the enforcement set — the orchestrator +
`_bw_common.py` + the twelve provers — must match its pin when present) and `AF-BK-ENTRY-BYPASS` (no
hand-rolled Drive/Slack/Gmail/n8n/Airtable/GHL uploader in the run dir; local-only delivery).

## 4. THE CERTIFICATE CONTRACT

`run_book_writer.py` mints `PROCESS-CERTIFICATE.{json,md}` **only** after a full P0->P8 pass
(`write_certificate` refuses otherwise -> `AF-BK-PROCESS-INTEGRITY`). The JSON certificate
(`schema: book-writer-process-certificate-v1`) carries the audit contract:

- **Identity:** `skill`, `author`, `book_slug`, `mode`, `locked_title`, `locked_subtitle`.
- **Measured provenance (self-report ignored):** `measured_chapter_count` (= 12),
  `measured_chapter_word_counts` (per chapter, each 2000-3500), `measured_tone_word_count` (>= 3000),
  `measured_challenge_sections` (= 30), `title_lock_ok`, `stories_placed`.
- **Ordered phase chain:** `declared_phases` (the nine P0->P8 ids), `verified_phases` (= 9),
  `all_phases_pass`, and a `steps[]` list with each `phase_id` + `ok`.
- **Runtime attestation:** `runtime = "local-only (no n8n / Airtable / Google / Gmail / Slack / GHL)"`.
- **`certificate_sha`:** a DETERMINISTIC sha256 over the MEASURED values (slug, mode, title/subtitle,
  the sorted per-chapter word counts, tone, challenge, title-lock, stories, and the ordered phase
  chain) — NOT the wall clock. **Same authored input -> same sha** (the idempotency contract `verify.sh`
  re-proves). `certified_at` is a separate wall-clock stamp and does NOT feed the sha.

**No-false-done:** "Done" may be claimed ONLY with the certificate path. No signed certificate = not
done. A phase failure returns the exact `AF-BK-*` code; after the bounded re-author attempts,
hard-escalate to the operator — never silent-pass, never waive a floor.

## 5. RUN IT — THROUGH THE ONE FRONT DOOR

```
bash 53-book-writer/book-writer-entry.sh --run-dir <RUN_DIR>
```

The front door runs three fail-closed gates (DEPS -> BYPASS-SCAN -> HASH-PIN), mints a run-scoped 0600
nonce under `<RUN_DIR>/run/checkpoints/`, and dispatches `run_book_writer.py`, which REFUSES to run
without that nonce (exit 4). The authoring layers (avatar / tone / titles / outline / chapters /
challenge / cover) run UPSTREAM on the CLIENT's own providers and drop artifacts into `<RUN_DIR>/run/`;
the assembler is model-free — it MEASURES and CERTIFIES only. `--plan` prints the canonical phase plan
(gates still run). Running the assembler by hand around the front door, or hand-rolling an external
uploader/notifier, is the UNGOVERNED path and is refused.

## 6. DELIVER (P8-DELIVER, local-only)

The deliverable bundle is a labeled folder `~/Downloads/<First>_<Last>-Book/` — the manuscript, the
chapters, the named companion docs (`Avatar_Document`, `Tone_Communication_Style_Analysis`,
`Suggested_Titles`, `APPROVED-TITLE.txt`, `APPROVED-OUTLINE.md`, `Book_Blurb_and_Chapter_Titles`,
`30_Day_Challenge`, `Book_Cover_Prompt.md`), the 4x3x3 extras when applicable, `00-INDEX.md`,
`MANIFEST.json`, and the signed `PROCESS-CERTIFICATE.{json,md}`. NO n8n / Airtable / Google Drive /
Gmail / Slack / GHL. Any owner notification is per-client config through the client's own OpenClaw
gateway (never bypassed), client-silent by default — we move in silence. Downstream handoffs:
`433_Deck_Data.json` + deck outline -> **Skill 51**; avatar dossier + blended tone <-> **Skill 52** (both
directions); `Book_Cover_Prompt.md` -> any image provider; the manuscript -> **Skills 49 / 50** for
launch assets.

## 7. VERIFY BEFORE CLAIMING DONE

End-to-end proof is from the CLIENT outcome, not the builder's claim: the bundle opens, every deliverable
is present and on-band, the locked title is byte-exact everywhere, and the certificate chain is intact.
Self-verify the skill with:

```
bash 53-book-writer/verify.sh
```

It runs each prover's `--self-test`, checks tone-core lockstep, reproduces the golden run's
`certificate_sha` (the idempotency contract), proves every broken variant fails closed with a DISTINCT
`AF-BK-*` code, proves `version=book` is accepted while `version=brand` parks/hands-off, and runs the
no-Anthropic + no-client-name scans — idempotent and read-only, and it must pass under both `bash` and
`zsh`. Any nonzero exit = fix and re-run; never guess a missing field or waive a floor.

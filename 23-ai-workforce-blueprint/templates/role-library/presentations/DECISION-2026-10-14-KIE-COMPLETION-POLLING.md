# DECISION 2026-10-14: KIE completion for Presentations decks is learned by polling, never by callback

**Status:** DECIDED (FIX-PLAN Item 33d). Recorded 2026-10-14.
**Scope:** Presentations deck runs, meaning the canonical engine shipped in this department home (`scripts/build_deck.py`, `scripts/kie_generate.py`, `scripts/kie_tasks.py`). This record does not change Skill 46's doctrine for the routes Skill 46 serves.

## The decision

One doctrine: a Presentations deck run learns that a KIE task finished by POLLING Kie's `recordInfo` endpoint through the department's shipped scripts. Deck runs never send `callBackUrl`, never use the Skill 46 callback relay (`46-kie-callback-relay`), and never dispatch through Skill 74. Skill 46 callbacks are not a Presentations dependency.

## Why the evidence allows only this decision

### 1. The engine polls, in code (read in full)

- `build_deck.py` `submit_task` builds the createTask payload as `{model, input{prompt, input_urls (only when a logo URL is passed), aspect_ratio, resolution}}`. There is no `callBackUrl` field. A search for "callback" across the whole file returns zero hits.
- `build_deck.py` `poll_task` polls `recordInfo` on a ladder (10s for the first 120s, 20s for the next 180s, 40s after, with a hard cap), and `render_slides_batch` submits every slide once, then polls every pending task on one shared 10s cadence, downloading and verifying each slide the moment its own task succeeds.
- `build_deck.py`'s header states the only-allowed recipe: createTask, then `recordInfo`, then `resultJson.resultUrls[0]`. Its HTTP helper refuses anything else in words: "This pipeline only uses /api/v1/jobs/createTask and /api/v1/jobs/recordInfo."
- `kie_generate.py` (the second renderer) builds the same callback-free payload, and its `poll_task_once` is a single `recordInfo` GET. It runs through `kie_tasks.py`, which round-robin polls every pending task (60s cadence, `KIE_DEADLINE_S` 6000s) and downloads and verifies each the moment it succeeds. SOP-IMG-01 section 3 describes exactly this lifecycle, and section 1A names these two scripts as the only renderers.

### 2. The callback route is barred from deck runs by doctrine and by enforcement

- SOP-IMG-01 section 1A: Skill 74 is never part of a deck run. None of its files is ever copied into, imported from, or run inside a deck run directory. The adapter may be used only from the Skill 74 folder, and only for read-only checks.
- Skill 46's production path requires that barred route: `46-kie-callback-relay/SKILL.md` and `SUBMITTER-SOP.md` route submission through Skill 74 (`kie_live_adapter.py submit --mode active`) with the relay's signed callback URL, above a slide-count threshold.
- Skill 74's own `SKILL.md` hard rule 6 bars copying `kie_live_adapter.py` into a Presentations deck run directory.
- `scripts/canonical_render_guard.py` blocks any run-directory `.py` that mentions `createTask`, `recordInfo`, or `api.kie.ai` outside the canonical scripts (AF-CANONICAL-RENDER-BYPASS), so a relay submitter cannot ride along inside a run.

### 3. The order to use callbacks for decks lived in Skill 07, and Skill 07's own canon already carried the exception

- `07-kie-setup/SKILL.md`, Critical Things to Know: "For production batch jobs and decks: Use Skill 46 (kie-callback-relay) callback architecture rather than polling sequentially." Its item 4 states the same preference without a department carve-out, and its Skill 74 paragraph states that production batches pass `--callback-url` of the Skill 46 relay.
- `07-kie-setup/references/kie-common-rules.md` rule 4 says in one breath "Production batches use Skill 46 callbacks" and that a department whose code implements a specific ladder (named example: Presentations `build_deck.py`) is authoritative for that department, and its SOPs must describe that code. Rule 1 puts department pins above skill policy owners. The flat first sentence and the department exception cannot both govern decks. The code and the exception agree, so the flat sentence is the text that gets conformed.

## B9's carried question, settled

The Cloudflare check (FIX-PLAN Item 29) carried one UNVERIFIED: whether any presentation code path depends on Skill 46's callback relay. Settling check performed 2026-10-14: search the whole Presentations tree for `kie-callback`, `callBackUrl`, `KIE_CALLBACK`, `KVREAD`, `kv-read`; read every hit in full. Exactly two hits:

1. `scripts/prompt_gate.py` line 14: a module docstring listing `46-kie-callback-relay/kie-slide-submitter.js` among the side-door image-API paths that carried no prompt-quality gate, which is why the shared prompt gate exists. It configures nothing, names no relay hostname or URL, and the JavaScript submitter cannot import the Python gate.
2. SOP-IMG-01 section 2A: `callBackUrl` semantics listed among the unchanged vendor API surface on both model routes. It describes the vendor parameter; it does not configure the engine.

A separate sweep for `Skill 46`, `callback-relay`, and `kie-callback` across the department home and the Skill 51 folder found one further mention: `scripts/workbook_builder.py` line 99 cites Skill 46 among the sources for its KIE endpoint constants, and the constants it defines are the createTask and recordInfo (poll) URLs. Every other "callback" occurrence in the department's scripts is an unrelated Python function callback (board dispatch, launcher ingest, a parser callback, one test).

VERIFIED: no presentation code path configures, references, or depends on the Skill 46 relay. The pipeline polls. The carried UNVERIFIED is closed as VERIFIED-negative.

## What this decision does not change

- Skill 46 remains the callback architecture for the routes that dispatch through Skill 74 (the modality skills 66, 67, 68 production route). Skill 46's own files are not edited by this decision; the conflict's presentations-facing order lived in Skill 07's texts.
- The vendor `callBackUrl` parameter still exists in KIE's API. The vendor reference `07-kie-setup/kie-setup-full.md` documents that API surface (its callback lines are per-model parameter documentation and transcribed vendor polling advice; it names no Skill 46, no decks, and no Presentations text) and is not conformed, because it orders nothing for decks.
- Generic either/or mentions elsewhere in Skill 07 (`INSTRUCTIONS.md`, `QC.md`, `CORE_UPDATES.md`: poll or callback, webhooks described as optional) state no deck order and are not conformed.
- Flag for Skill 46's owner, NOT actioned here: `46-kie-callback-relay/SKILL.md` frontmatter ("Applies to large decks (above configurable threshold)") and `SUBMITTER-SOP.md` ("applies to any role or agent that submits images to Kie.ai for slide decks") still claim slide-deck scope. Read against this record and SOP-IMG-01 section 1B, those claims do not govern Presentations deck runs. Harmonizing Skill 46's scope wording is Skill 46's owner's edit to make.

## Conforming edits made with this record

- This department: SOP-IMG-01 gains section 1B stating this doctrine in department doctrine.
- Skill 07, in its own version ceremony (v7.2.1 to v7.2.2): `SKILL.md` (the deck bullet in Critical Things to Know, item 4, the Skill 74 paragraph, the Skill 46 Companion scope) and `references/kie-common-rules.md` rule 4 are conformed so the callback preference names the route it governs and the Presentations exception is explicit.
- The engine is untouched: poll won, so no code changes.

# TOOLS.md — Presentations Builder Tools (DETERMINISTIC PIPELINE)

## SLICED READS FOR LARGE FILES (FIX-19 / D18 — READ THIS FIRST)

The department's SOP/role files are **25–125KB**. Reading one WHOLE into a tool
result is what fired `[tool-result-truncation]` **33 times** in the 2026-08-06
E2E (D18) — the harness truncated the giant result and you reasoned from
incomplete context. **Never read a SOP/role file whole.**

The engine ships ONE sliced-read tool: `scripts/read_slice.py`. Use it for any
file over ~32KB:

```
# 1. Find the section you need (cheap — headers + line numbers only):
python3 <SCRIPTS_DIR>/read_slice.py <sop-file.md> --index

# 2. Fetch exactly the slice you need:
python3 <SCRIPTS_DIR>/read_slice.py <sop-file.md> --lines 262-270
python3 <SCRIPTS_DIR>/read_slice.py <sop-file.md> --offset 1000 --length 2000
```

A bare filename resolves to the department `sops/` mirror (and the
universal-sops clusters) the same way the engine resolves `sop_refs`. The tool
prints the slice + the slice bounds + byte counts to stderr, and maintains a
truncation-event counter at
`working/checkpoints/read_slice_truncations.json`. A sliced build keeps that
counter at **0** — that is the FIX-19 QC gate.

The `--next` phase turn-gate emits each `sop_ref` with a `read_slice_hint`
(and marks `sliced_read_required: true` when the SOP exceeds the guard budget),
so follow the hint the runner gives you rather than doing a whole-file read.

---

## YOU HAVE EXACTLY ONE TOOL FOR DECKS: `presentation-canonical-entry.sh`

You do NOT generate images. You do NOT call KIE.ai. You do NOT assemble `.pptx` files.
There is exactly ONE tool that builds a deck, and it does all of those for you:

```
bash <SCRIPTS_DIR>/presentation-canonical-entry.sh \
    --run-dir <DIR> --slides slides.json --out out.pptx
```

`build_deck.py` is NEVER invoked directly. `presentation-canonical-entry.sh` is the
ONE sanctioned command; it runs the deps/bypass/version/interview gates and then
dispatches the canonical orchestrator (`run_signature_deck.py` → `build_deck.py`).
A direct `build_deck.py` or `working/*.py` call is blocked by the front-door guard
(AF-CANONICAL-RENDER-BYPASS).

`presentation-canonical-entry.sh`, `build_deck.py`, `run_signature_deck.py`,
`kie_generate.py`, and `slides.schema.json` ship in this repo's scripts and
render-template directories and are installed into the client's Presentations scripts
directory on a materialized box. Use the `SCRIPTS_DIR` your task message gives you.
The scripts directory defaults to the materialized department's `scripts/` folder;
`--scripts-dir` overrides it. The script refuses rather than searching or guessing.

**Your job is NOT just `slides.json`.** `slides.json` is the Layer-A structure ledger; the
render also requires the hand-authored rich per-slide prompt files
(`working/prompts/slide-NN.txt`, sized to the prompt budget of the pinned model (rule 12 of `07-kie-setup/references/kie-common-rules.md`: target 95 to 100 percent of the model maximum, hard floor 80 percent), read with `kie_live_adapter.py prompt-budget --check`; until the renderer gate (9,000 to 18,000 in `build_deck.py` and `prompt_gate.py`) is migrated to rule 12, write 16,000 to 18,000 characters so both pass) and every other upstream Layer-A artifact the manifest
requires before the render preflight will pass. The full two-layer procedure — walk
`run_signature_deck.py --next` phase by phase, THEN dispatch the canonical entry command
above — is in `BUILDER-PROMPT.md`; read it first on every deck task. Treat the mechanics
summary below as reference for what the render step itself does at P4-RENDER, not as a
shortcut past Layer A.

**FORBIDDEN (any one = immediate FAIL at QC, AF-I14):**
- The native `image_generate` tool, or any other image-generating tool, for a deck slide.
  You have no image tool. Do not call one.
- Writing your own inline KIE.ai HTTP call (curl / requests / urllib / fetch) from memory or
  otherwise. Only `build_deck.py` (or `kie_generate.py` for the reference image-to-image
  flow) ever talks to KIE.ai.
- Touching the dead endpoint `/api/v1/image/gpt-image` (HTTP 404).
- Hand-editing PNGs or substituting any image the script did not render. No placeholders.
- Assembling a `.pptx` yourself — `build_deck.py` does the assembly.

---

## Tool arguments are ALWAYS a JSON object (FIX-18 / Error 10)

A malformed tool call burns a full retry cycle and — repeated — trips the
`AF-TOOL-SCHEMA-LOOP` alert that stops a build. Two durable rules, enforced by
`tool_schema_validator.py` and stated here so the model reads the SAME rule the
validator enforces:

1. **`write` takes `path`, never `file`.** The `write` tool's arguments are
   `write(path: string, content: string)`. There is no `file` argument; calling
   `write` with `file:` and no `path` FAILS with "missing required parameter:
   path". The same holds for `read(path: string)` and `Edit(file_path: string,
   old_string: string, new_string: string)`.

2. **Tool args are a JSON object, never a string.** Every tool's arguments must
   be emitted as a JSON object literal (`{"key": "value", ...}`), not as a
   serialized string (`'{"key": "value"}'`) and never as a bare prose string.
   If you receive a validation error, read the normalized schema hint in the
   error, correct the args to an object, and do NOT re-emit the schema dump.

When a tool's malformed calls hit 5 CONSECUTIVE failures, the run records an
`AF-TOOL-SCHEMA-LOOP` event and the Phase-0 preflight stops the build — the
model is re-oriented, not silently re-run.

---

## What the canonical pipeline does (so you don't have to)

You hand `slides.json`, the pre-authored `working/prompts/slide-NN.txt` rich prompts, and
an output path to `presentation-canonical-entry.sh`. It runs three fail-closed gates
(deps / bypass-scan / version-hash-pin) and then dispatches `run_signature_deck.py` →
`build_deck.py`, which does EVERYTHING else, deterministically, with zero AI judgement at
runtime:

1. Validates `slides.json` (fails loud on bad JSON / missing fields / non-unique ordinals)
   AND preflights the full Layer-A artifact set — including the rich prompt files.
2. For each slide, renders the Layer-A-authored rich prompt **VERBATIM** — it does **not**
   compose a prompt from `scene` + `copy` (that claim is a retired residual pattern; see
   `BUILDER-PROMPT.md`). It appends the MANDATORY English/Latin-only pin if the authored
   prompt does not already carry it. No model decides wording at render time — the copy is
   whatever the Slide Copywriter / Slide Image Creator roles authored upstream. The pin
   appended to every prompt is, verbatim:
   > All text rendered in the image MUST be in English, Latin alphabet ONLY. NO Chinese/CJK
   > or non-Latin characters anywhere. Render the copy spelled correctly, letter-for-letter.
   > No garbled, misspelled, or invented text.
3. Calls KIE.ai at 16:9 / 2K resolution via the ONLY verified live recipe:
   `POST /api/v1/jobs/createTask` → `GET /api/v1/jobs/recordInfo?taskId=<id>` →
   parse `data.resultJson` (a JSON string) → `resultUrls[0]`. It refuses the dead endpoint.
   The model id is NEVER a literal here — `build_deck.py` resolves its render classes
   (`image.t2i`, and `image.i2i` for a URL-logo run, which the canonical command does not reach today)
   from the central versioned catalog per submit, so a catalog bump changes the next render without a code
   edit. The batch path submits every slide once, 0.6 seconds apart (the governor also paces
   the `kie` provider at 1.33 per second, at most 13 starts per rolling 10 seconds), then runs
   one poll pass over all pending tasks every 10 seconds and downloads each slide the moment
   its own task succeeds. A task still unfinished after 900 seconds is a terminal failure for
   that slide (never a silent hang); HTTP 429 on submit sleeps 20 seconds and retries, at most
   15 times in a row.
4. Downloads each result to `<renders_dir>/slide-NN.png` with the client's own key as the
   Bearer header plus a browser User-Agent (an unauthenticated GET of the KIE result URL
   returns 403), and VERIFIES PNG magic bytes + non-zero size, the 16:9 / 2K shape, and an
   OCR readback of the baked text against the approved copy. In the batch path a slide that
   fails (terminal KIE state, bad PNG, OCR mismatch, poll cap) is recorded as a failure, the
   run exits 1 with no `.pptx`, and re-running the same command reuses every slide already
   verified in `pending_tasks.json` and submits only the rest. The single-slide helper (used
   for the style-preview samples) re-submits a failing slide from scratch, up to 6 attempts
   by default (`BUILD_DECK_SLIDE_MAX_ATTEMPTS`) with exponential backoff (4 seconds doubling,
   capped at 90 seconds). A 401 or 403 is never retried on any path, and a poll timeout is
   never re-submitted. Before any render the script also proves the key with a one-shot auth
   check (a 401 aborts with exit 4) and checks the OCR engine and the credit balance.
5. Assembles all slide PNGs into a 16:9 `.pptx` (10 × 5.625 in), ONE full-bleed picture per
   slide, NO text boxes (the copy is baked into each image).
6. Writes the receipts below, prints a JSON summary and sets an exit code:
   ```json
   { "slidesRendered": N, "kieTaskIds": ["..."], "outputPath": ".../out.pptx", "failures": [] }
   ```

**Receipts (what proves a slide was really rendered):** `working/checkpoints/pending_tasks.json`
(the KIE task id is written before polling and replaced by the verified PNG's sha256 once
the slide is downloaded; a resumed run reuses only slides recorded complete there, so a
crash never re-bills a finished slide), `renders/slide-NN.ocr.json` (the OCR readback
record), the render record in `working/checkpoints/process_manifest.json`, and `kieTaskIds`
in the summary. Credits are checked once before any render by the runner's balance
preflight (`GET /api/v1/chat/credit`, abort `AF-KIE-BALANCE`, exit 4). The price authority
is `kie_live_adapter.py price` (rule 7 of kie-common-rules.md); the `unit_costs` in
`model_catalog.json` are a dated snapshot, not an authority.

**The image chain, end to end:** authored prompt -> prompt budget (above) -> model pin
(`model_catalog.json` aliases `image.t2i` and `image.i2i`, a department pin that outranks
Skill 74 and the `latest-family` default; a newer GPT Image generation is adopted by an
operator catalog bump, never silently) -> transport (this script only) -> receipts. Skill 74
(`74-kie-live-adapter`) is mechanics for other skills and is NEVER copied into or run from a
deck run directory: the render guard (`canonical_render_guard.py`) blocks any `*.py` there
that mentions `createTask`, `recordInfo` or `api.kie.ai` (`AF-CANONICAL-RENDER-BYPASS`).

**Exit codes (the contract you act on):**
- `0` — every slide rendered and the `.pptx` was written. `outputPath` is your deliverable.
- `1` — one or more slides failed (NO `.pptx` written), or assembly failed.
  Read `failures`. Fix `slides.json` if it was a content problem and re-run; otherwise
  report the failure. NEVER substitute an image.
- `2` — fatal config error (no `KIE_API_KEY`, bad `slides.json`, `python-pptx` missing).

**API key:** the script reads `KIE_API_KEY` itself, from env or the client's own env stores
(`~/.openclaw/workspace/.env`, `~/clawd/secrets/.env`, `~/.openclaw/secrets/.env`). It is
ALWAYS the CLIENT's own KIE.ai key — never the operator's, never shared. You never handle the
key and you never see the KIE traffic.

---

## `slides.json` — the input contract (this is what YOU write)

Authoritative schema: `slides.schema.json` (render-template directory). Each element:

```json
{
  "slide": 1,
  "scene": "A confident founder in a sunlit modern office, soft window light, warm neutral palette, shallow depth of field, 85mm, editorial photography.",
  "copy": ["Acme Co", "Three moves that doubled our pipeline in 90 days"],
  "logo": "ACME CO",
  "layout": "headline lower-left over a soft dark gradient, subhead beneath, logo wordmark top-right"
}
```

- `slide` — unique integer starting at 1, contiguous. Sets order AND filename.
- `scene` — describe a PHOTOGRAPH (subject, setting, light, mood, palette, framing). Do NOT
  put slide wording here.
- `copy` — the EXACT text to appear, in reading order. Index 0 = headline. **Spell every
  word correctly, letter-for-letter** — the script renders it verbatim; it will not fix
  spelling or reword. Keep lines short (slide copy, not paragraphs).
- `logo` — optional brand wordmark (rendered as text). Omit if none.
- `layout` — optional placement hint. Omit for a safe default.

The deterministic pipeline renders each slide as **text-to-image by default** — a slide
with no official logo is a plain t2i generation. The canonical command has NO `--logo`
option (the entry exits with "unknown argument"). When the deck has an OFFICIAL logo, set
`brand.logo_image_path` in `working/copy/intake.json` to a LOCAL PNG file (absolute, or relative
to the run directory; a URL there makes the renderer exit 2, so a logo that exists only as a hosted
URL is downloaded to a local PNG in the run directory first). The render stays t2i and
`assemble_pptx` places the exact PNG on every slide at assembly time (top-right, ~13% of slide
width, 0.25 inch margin). The URL image-to-image mode (`build_deck.py --logo <https URL>`, the logo
riding `input_urls`) exists in the renderer but is not forwarded by the entry or the runner, so it
is not available to a department agent until lane D plumbs it; never hand-run `build_deck.py` to
reach it (AF-CANONICAL-RENDER-BYPASS). You never pass logo image files into `slides.json` — its `logo` field is a TEXT wordmark only, and there is
no per-slide `mode` choice for a deck build. (The separate `kie_generate.py` helper runs
standalone i2i jobs for the full webinar pipeline per SOP-IMG-01, but it is OUT OF SCOPE
for `build_deck.py` and you do not invoke it for a standard deterministic deck build.)

---

## Mission Control (Command Center) — handled automatically

The build script (`build_deck.py` postflight via `cc_board.py`) registers the deliverable
and advances the Command Center card automatically. You do NOT make manual POST/PATCH calls.
When `presentation-canonical-entry.sh` exits 0, report TASK_COMPLETE — the registration
is already done.

## Artifact Directory

The task message always contains an `ARTIFACT_DIR` line. Use that exact path. Pass
`<ARTIFACT_DIR>/presentation.pptx` to `presentation-canonical-entry.sh` as `--out`; the renderer writes
the renders under `<ARTIFACT_DIR>/presentation/renders/` (or the `renders_dir` you pass).
`mkdir -p $ARTIFACT_DIR` first if it does not exist.

# TOOLS.md — Presentations Builder Tools (DETERMINISTIC PIPELINE)

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

**Your job is NOT just `slides.json`.** `slides.json` is the Layer-A structure ledger; the
render also requires the hand-authored 9,000–18,000-character rich per-slide prompt files
(`working/prompts/slide-NN.txt`) and every other upstream Layer-A artifact the manifest
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
3. Calls KIE.ai (`gpt-image-2-text-to-image`, 16:9, 2K) via the ONLY verified live recipe:
   `POST /api/v1/jobs/createTask` → `GET /api/v1/jobs/recordInfo?taskId=<id>` →
   parse `data.resultJson` (a JSON string) → `resultUrls[0]`. It refuses the dead endpoint.
4. Downloads each result UNAUTHENTICATED to `<renders_dir>/slide-NN.png` and VERIFIES PNG
   magic bytes + non-zero size. Retries a failing slide up to 3×.
5. Assembles all slide PNGs into a 16:9 `.pptx` (10 × 5.625 in), ONE full-bleed picture per
   slide, NO text boxes (the copy is baked into each image).
6. Prints a JSON summary and sets an exit code:
   ```json
   { "slidesRendered": N, "kieTaskIds": ["..."], "outputPath": ".../out.pptx", "failures": [] }
   ```

**Exit codes (the contract you act on):**
- `0` — every slide rendered and the `.pptx` was written. `outputPath` is your deliverable.
- `1` — one or more slides failed after retries (NO `.pptx` written), or assembly failed.
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

The deterministic pipeline uses `mode: "t2i"` only (text-to-image). The script does not pass
logo image files. (The separate `kie_generate.py` helper supports image-to-image logo
placement for the full webinar pipeline per SOP-IMG-01, but it is OUT OF SCOPE for
`build_deck.py` and you do not invoke it for a standard deterministic deck build.)

---

## Mission Control (Command Center) — handled automatically

The build script (`build_deck.py` postflight via `cc_board.py`) registers the deliverable
and advances the Command Center card automatically. You do NOT make manual POST/PATCH calls.
When `presentation-canonical-entry.sh` exits 0, report TASK_COMPLETE — the registration
is already done.

## Artifact Directory

The task message always contains an `ARTIFACT_DIR` line. Use that exact path. Pass
`<ARTIFACT_DIR>/presentation.pptx` to `build_deck.py` as the output path; the script writes
the renders under `<ARTIFACT_DIR>/presentation/renders/` (or the `renders_dir` you pass).
`mkdir -p $ARTIFACT_DIR` first if it does not exist.

# TOOLS.md — Presentations Builder Tools (DETERMINISTIC PIPELINE)

## YOU HAVE EXACTLY ONE TOOL FOR DECKS: `build_deck.py`

You do NOT generate images. You do NOT call KIE.ai. You do NOT assemble `.pptx` files.
There is exactly ONE tool that builds a deck, and it does all three of those for you:

```
python3 <SCRIPTS_DIR>/build_deck.py <slides.json> <out.pptx> [renders_dir]
```

`build_deck.py`, `kie_generate.py`, and `slides.schema.json` ship in this repo's
render-template directory `23-ai-workforce-blueprint/templates/presentation-render/` and
are installed into the client's Presentations scripts directory on a materialized box. Use
the `SCRIPTS_DIR` your task message gives you.

Your only job is to produce a correct `slides.json` (see `slides.schema.json`) and run that
command. The procedure is in `BUILDER-PROMPT.md`; read it first on every deck task.

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

## `build_deck.py` — what it does (so you don't have to)

You hand it `slides.json` and an output path. It does EVERYTHING else, deterministically,
with zero AI judgement at runtime:

1. Validates `slides.json` (fails loud on bad JSON / missing fields / non-unique ordinals).
2. For each slide, MECHANICALLY composes the KIE prompt = `scene` + your exact `copy`
   (verbatim) + optional `logo` wordmark + `layout` hint + a MANDATORY English/Latin-only
   pin. No model decides wording — the copy is whatever you wrote in `slides.json`. The pin
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

## Mission Control API (for registering the deliverable)

The task message includes the exact URLs. Standard pattern:
- Base URL: from the task message (`missionControlUrl`).
- Register the deliverable: `POST /api/tasks/{id}/deliverables` — register the EXACT
  `outputPath` from the `build_deck.py` summary (the `.pptx`), nothing else.
- Log activity: `POST /api/tasks/{id}/activities`.
- Update status: `PATCH /api/tasks/{id}` → `{"status": "review"}`.

Use curl or python requests for these API calls — both are available. (These are Mission
Control calls only; they are NOT image calls.)

## Artifact Directory

The task message always contains an `ARTIFACT_DIR` line. Use that exact path. Pass
`<ARTIFACT_DIR>/presentation.pptx` to `build_deck.py` as the output path; the script writes
the renders under `<ARTIFACT_DIR>/presentation/renders/` (or the `renders_dir` you pass).
`mkdir -p $ARTIFACT_DIR` first if it does not exist.

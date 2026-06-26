# SOP-PITCH-05: THE DELIVERABLE BUNDLE (PRESENTER GUIDE + SCRIPT + AUDIO + HYGIENE)

**Cluster:** Pitch-Craft Rules / Closeout
**Version:** v2.0.0 (2026-06-15)
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md; 30-fish-audio-api-reference/fish-audio-voice-sop.md
**Owning role at write time:** Presenters Guide Specialist (ROLE-19, SOP 9.2) for the Presenter Guide PDF; Presenters Speech Writer (ROLE-20, SOP 9.2) for the Word-for-Word Script PDF and audio render source
**Enforced at the gate by:** QC Specialist - Presentations (AF-DELIVER -- closeout hard gate)
**Purpose:** Guarantee every deck build produces all three required artifacts -- presenter guide PDF, word-for-word script PDF, and AUDIO rendition -- and that the gate blocks closeout until all three are verified on disk as non-empty files.

---

## 1. THE THREE REQUIRED ARTIFACTS

A deck build is NOT closed out until all three of the following artifacts exist on disk and are verified non-empty:

| Artifact | Format | Source file | Required |
|---------|--------|-------------|---------|
| Presenter Guide | PDF | `working/deliverables/PRESENTER-GUIDE.md` rendered to PDF | REQUIRED |
| Word-for-Word Script | PDF | `working/deliverables/PRESENTERS-SPEECH.md` rendered to PDF | REQUIRED |
| Audio Rendition | MP3 or M4A | Fish Audio S2 render of the word-for-word script | REQUIRED |

Missing any of these three triggers AF-DELIVER (closeout auto-fail). The deck cannot be delivered to the client until all three are present and non-empty.

---

## 2. PRESENTER GUIDE PDF (the visual reference)

The Presenters Guide Specialist (ROLE-19, SOP 9.2) authors `PRESENTER-GUIDE.md` -- a presenter-facing reference that shows each slide thumbnail or description alongside the key talking points and timing guidance. The Presenters Guide Specialist also renders it to PDF using the following method:

1. Confirm `working/deliverables/PRESENTER-GUIDE.md` exists and is non-empty (at least 2KB).
2. Render to PDF: `pandoc working/deliverables/PRESENTER-GUIDE.md -o working/deliverables/PRESENTER-GUIDE.pdf --pdf-engine=wkhtmltopdf` (or equivalent). If the toolchain is unavailable, use LibreOffice Writer as a fallback: `soffice --headless --convert-to pdf working/deliverables/PRESENTER-GUIDE.md`.
3. Verify the output PDF exists and is non-empty (> 10KB).
4. Record in `working/checkpoints/deliverable_bundle.json`: `{"artifact": "presenter_guide", "path": "working/deliverables/PRESENTER-GUIDE.pdf", "size_bytes": N, "status": "ready"}`.

---

## 3. WORD-FOR-WORD SCRIPT PDF (the oral rendition source)

The Presenters Speech Writer (ROLE-20, SOP 9.2) authors `PRESENTERS-SPEECH.md` -- the complete word-for-word spoken script, with slide-by-slide sections, timing, and expression cues. The Presenters Speech Writer also renders it to PDF using the same method as the guide (step 2 above, substitute PRESENTERS-SPEECH.md/pdf).

1. Confirm `working/deliverables/PRESENTERS-SPEECH.md` exists and is non-empty (at least 5KB -- a full webinar script is typically 5,000-15,000 words).
2. Render to PDF via pandoc or LibreOffice.
3. Verify the output PDF is non-empty (> 20KB).
4. Record in `deliverable_bundle.json`: `{"artifact": "script", "path": "working/deliverables/PRESENTERS-SPEECH.pdf", "size_bytes": N, "status": "ready"}`.

---

## 4. AUDIO RENDITION (the missing artifact -- new Fish Audio S2 stage)

The audio rendition is a FULL voiced reading of the presenter script, rendered via Fish Audio S2 (the expression-tag TTS engine). This stage did not exist in prior builds; its absence is the documented V10 gap and the trigger for AF-DELIVER.

### 4.1 Source

The source text is `working/deliverables/PRESENTERS-SPEECH.md`. The Presenters Speech Writer (ROLE-20) reads the script, chunks it by section (each `## Slide N` heading starts a new chunk), and adds Fish Audio S2 expression tags to each chunk for directed vocal performance.

### 4.2 Expression Tags (required -- not flat TTS)

Per `30-fish-audio-api-reference/fish-audio-voice-sop.md`, S2 supports expression tags that direct vocal performance. Every chunk must include at minimum:

- `[pause]` at natural breath points (between slide sections, after strong emotional statements).
- `[storytelling tone]` at narrative / story beats.
- `[voice lifts]` at climactic moments (a promise landed, a price reveal, the close).
- Paired physical+emotion tags where the script calls for them (e.g., `[warm, leaning in]` at the close section, `[grounded, certain]` at the authority section).

The Presenters Speech Writer (ROLE-20) adds these tags inline in the chunked script before submitting to the Fish Audio S2 API. Do not submit flat untagged text: flat TTS produces a monotone read that does not serve the presenter or the audience.

### 4.3 Voice Key Selection

- **If the client has a Fish Audio voice reference file or voice ID on file:** use it. Record the voice ID in `intake.json` as `fish_audio_voice_id`.
- **If no client voice ID exists:** render the audio using the operator key's default voice and note in `deliverable_bundle.json`: `"voice_source": "operator_key_sample -- client voice pending"`. Label the audio file `PRESENTER-AUDIO-operator-sample.mp3` so it is clearly distinguished from a client-voiced rendition.

### 4.4 Stitching with ffmpeg

Render each section chunk as a separate audio file, then stitch them into one continuous rendition:

1. Submit each chunk to the Fish Audio S2 API with expression tags. Save as `working/audio/chunk-NN.mp3` (zero-padded, matching the slide-section numbering).
2. Add silence between chunks at `[pause]` boundaries: generate a 0.5s silence file (`ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 0.5 -q:a 9 -acodec libmp3lame working/audio/pause.mp3`) and splice it between chunks.
3. Concatenate all chunks + pauses into one file: `ffmpeg -f concat -safe 0 -i working/audio/concat-list.txt -c copy working/deliverables/PRESENTER-AUDIO.mp3`.
4. Verify the output MP3 is non-empty (> 100KB for any real narration). A zero-byte or sub-100KB audio file for a full webinar script is a failed render.

### 4.5 Failure Mode

If the Fish Audio S2 API is unavailable or returns an error:

1. Retry once after a 30-second wait.
2. If still failing, try the next available TTS engine in the fallback chain (operator configured; document the fallback used in `deliverable_bundle.json`).
3. If no TTS engine is available, flag to the Director with the exact error. The audio artifact is required; a deck cannot close out without it. Do NOT close out with a placeholder or an empty file.

---

## 5. DELIVERABLE BUNDLE QC CHECK

The Presenters Guide Specialist (ROLE-19) records the guide artifact and the Presenters Speech Writer (ROLE-20) records the script and audio artifacts in `working/checkpoints/deliverable_bundle.json`, then either role sets `all_present: true` once both have confirmed their artifacts are ready:

```json
{
  "presenter_guide": {"path": "working/deliverables/PRESENTER-GUIDE.pdf", "size_bytes": N, "status": "ready"},
  "script": {"path": "working/deliverables/PRESENTERS-SPEECH.pdf", "size_bytes": N, "status": "ready"},
  "audio": {
    "path": "working/deliverables/PRESENTER-AUDIO.mp3",
    "size_bytes": N,
    "voice_source": "client_voice_id: <ID>" or "operator_key_sample -- client voice pending",
    "status": "ready"
  },
  "all_present": true
}
```

`all_present` is `true` ONLY when all three artifacts exist on disk with their paths, non-empty sizes, and `status: "ready"`. The QC Specialist reads this file as part of AF-DELIVER.

---

## 6. THE GATE: AF-DELIVER (closeout hard auto-fail)

AF-DELIVER is a closeout auto-fail in the QC gate (qc-specialist-presentations-sops.md). It fires when ANY of the following is true at closeout:

- `working/checkpoints/deliverable_bundle.json` is absent or `all_present` is not `true`.
- The presenter guide PDF does not exist or is empty on disk.
- The word-for-word script PDF does not exist or is empty on disk.
- The audio file does not exist, is empty (< 100KB for a full script), or is the stub silence file.

AF-DELIVER is checked independently of `final_deck_qc.json`. Both must pass (AF-F5 for the deck quality gate, AF-DELIVER for the bundle completeness gate) before any delivery action may proceed.

---

## 7. INTEGRATION NOTE

This SOP is owned jointly by the Presenters Guide Specialist (ROLE-19, SOP 9.2) and the Presenters Speech Writer (ROLE-20, SOP 9.2) -- there is no separate "Deliverable Producer" role. ROLE-19 owns the guide PDF; ROLE-20 owns the script PDF and the audio render. This SOP adds the audio render stage as a mandatory third artifact, the Fish Audio S2 expression-tag requirement, the ffmpeg stitch procedure, the `deliverable_bundle.json` manifest, and the AF-DELIVER closeout gate. Prior builds that shipped only the deck PPTX + the guide/script as markdown files are now incomplete. The three-artifact bundle is the minimum viable delivery.

---

## 8. THE CLIENT PACKAGE -- EXACT ALLOWED FILE SET (v2.0 -- Deliverable Hygiene)

**Two file sets, two counts (deliberate).** `build_deck.py` writes a NINE-file OPERATOR BUILD
bundle to `~/Downloads/<client-slug>-<deck-slug>/` (`<deck-slug>-FINAL.pptx`, `<deck-slug>-FINAL.pdf`,
`PRESENTER-GUIDE.pdf`, `PRESENTERS-SPEECH.md`, `PRESENTERS-SPEECH.pdf`, `PRESENTERS-SPEECH-FISH-TAGGED.md`,
`PRESENTER-AUDIO.mp3`, `infographic.png`, `presenter-teleprompter.html` -- the `build_bundle_files`
set). The Delivery Concierge SOP 9.0 then CURATES the FIVE-file CLIENT package (the
`client_package_files` set) from that build bundle. Nine build, five client -- the difference is
intentional (the `.md` sources, the fish-tagged script, the infographic, and the teleprompter HTML
are operator-side artifacts, not part of the clean client hand-off).

The client-deliverable package must contain EXACTLY these five files and NOTHING ELSE:

```
[DECK_SLUG]-FINAL/
  <deck-slug>-FINAL.pptx           # assembled deck (from output/[DECK_SLUG].pptx)
  <deck-slug>-FINAL.pdf            # portable-document export (from output/[DECK_SLUG].pdf)
  PRESENTER-GUIDE.pdf              # rendered from working/deliverables/PRESENTER-GUIDE.md
  PRESENTERS-SPEECH.pdf            # rendered from working/presenter-speech/PRESENTERS-SPEECH.md (locked plural name; matches build_deck.py)
  PRESENTER-AUDIO.mp3              # Fish Audio S2 render (from working/presenter-speech/audio/PRESENTER-AUDIO.mp3)
```

**Five files. Nothing else.** No scripts, logs, prompts, loose PNGs, JSON manifests, QC reports, or `.md` source files. `PRESENTER-GUIDE` and `PRESENTERS-SPEECH` ship as **PDF only** -- clients do not open markdown. (The `*-FINAL.pptx` / `*-FINAL.pdf` AF-DH1 whitelist patterns are unchanged.)

**Hygiene gate (AF-DH1):** Before any delivery action, the Delivery Concierge runs SOP 9.0 (Package Assembly and Hygiene Sweep) which creates a clean `delivery/[DECK_SLUG]-FINAL/` directory, copies only the five allowed files into it, and runs AF-DH1. Hard-stop on any AF-DH1 failure -- delivery cannot proceed.

---

## 9. BUILD WORKSPACE STRUCTURE (dev artifacts stay OUT of the client package)

The operator-side build workspace that the client NEVER receives:

```
~/webinar-decks/[client-slug]/[deck-slug]/[YYYY-MM-DD]/
  working/
    prompts/        # image prompts (.txt files -- never delivered)
    renders/        # raw generated images -- never delivered
    scripts/        # assembly + render scripts (assemble_pptx.py lives HERE, not at root)
    qc/             # QC reports, vision_qc_log.json, copy_qc_report.json -- never delivered
    checkpoints/    # run_ledger.json, model_manifest.json, delivery_plan.json
    deliverables/   # PRESENTER-GUIDE.md, PRESENTERS-SPEECH.md, PRESENTER-AUDIO.mp3 (source files)
    logs/           # all log files -- never delivered
    audio/          # chunk-NN.mp3 files before stitching
  output/
    [deck-slug].pptx    # assembled PPTX (the Delivery Concierge copies this to delivery/)
    [deck-slug].pdf     # portable-document export (copied to delivery/)
    pdf-pages/          # per-page PNGs for QC inspection -- never delivered
  images/               # QC-passed PNGs that fed assembly -- never delivered
  delivery/
    [DECK_SLUG]-FINAL/  # clean client package (the ONLY dir that goes to the client)
      [Deck-Title]-FINAL.pptx
      [Deck-Title]-FINAL.pdf
      PRESENTER-GUIDE.pdf
      PRESENTERS-SPEECH.pdf
      PRESENTER-AUDIO.mp3
```

**Hard rule for the PPTX Assembly Specialist:** The assembly script MUST write the PPTX to `output/[DECK_SLUG].pptx` and ALL intermediates under `working/`. The assembly script at `working/scripts/assemble_pptx.py` must NEVER hard-code the client delivery folder as `BUNDLE_DIR` or write to `~/Downloads/<DECK>` as its working directory. The delivery folder root (`~/Downloads/<DECK>`) as a build directory is the documented root cause of the forensic reference deck's dev-artifact leak. Dev artifacts must NEVER appear in `output/` or `delivery/` under any circumstance.

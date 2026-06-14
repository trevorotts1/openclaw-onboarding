# SOPs Mirror -- Presenters Speech Writer

**Source:** presentations/presenters-speech-writer.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Version:** 1.0

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Word-for-Word Draft

**When to run:** After Phase 6 final QC passes AND the Presenter Coach has produced talk_track.md, and only if DELIVERABLE_SET includes the speech.

**Inputs:**
- working/coach/talk_track.md (the timed talk track)
- working/copy/arc_allocation.json (section structure, time per section)
- working/copy/intake.json (DURATION_MIN, TONE, HOOK, OFFER_STACK)
- working/copy/hook_package.json (hook variants, scheduled hook beats)
- working/copy/price_ladder.json (drops, earned reasons, value added)

**Steps:**

1. Expand the talk track into a FULL word-for-word script keyed to each slide. For each slide write the complete spoken text the owner reads aloud, in the owner's TONE. The slide carries one big idea; the speech carries everything else (the spoken words live off the slide, here).

2. Sing the hook on its scheduled beats from hook_package.json (the Purple Rain rule): voice the hook line at the open verse, the mid reprise, the post-proof reprise, and the close reprise, using the placement-map variants. Do NOT pepper the hook into every slide's script; sing it where the placement map schedules it.

3. Write the drops with their EARNED REASONS and TIMED PAUSES: at each price-ladder drop, write the spoken reason the price moves (the value just added, the promise just earned) and mark a pause beat before the new number lands. The mechanic lines that must stay OFF the slide (for example "the lower the price, the greater the value") live HERE in the speech, not on the slide.

4. Write transitions between slides as spoken bridges so the read flows; the owner is never left guessing how to get from one slide to the next.

5. Enforce no em dashes. Use periods, commas, and short sentences for spoken rhythm. Never fabricate a number, a testimonial, or a client win; every concrete claim traces to intake.json (use placeholder discipline if real data has not arrived).

6. Write working/presenter-speech/presenters_speech.md: one block per slide, the full spoken text, the hook beats marked, the drop reasons and pause beats marked.

**Outputs:**
- working/presenter-speech/presenters_speech.md (the full word-for-word script, draft)

**Hand to:** SOP 9.2 (WPM Pacing Pass).

**Failure mode:** If talk_track.md is missing or incomplete, do NOT write the speech from the deck copy alone (the deck is not the script). Request the talk track from the Presenter Coach and block until it exists.

---

### SOP 9.2 -- WPM Pacing Pass

**When to run:** Immediately after SOP 9.1 produces the draft script.

**Inputs:**
- working/presenter-speech/presenters_speech.md (draft)
- working/copy/intake.json (DURATION_MIN, TONE)
- TARGET_WPM (default 140; 130 teach-heavy; 150 to 160 high-energy)

**Steps:**

1. Record TARGET_WPM EXPLICITLY in the script header. Default is 140. Select 130 only if the deck is teach-heavy, or 150 to 160 only if the deck is high-energy and the owner wants a faster pace. Record the chosen value and the reason. NEVER let it default silently to the repo TTS value of 150; 140 is the presentation-speech SOP constant.

2. Count total_words in the script. Compute expected runtime = total_words / TARGET_WPM (in minutes).

3. ASSERT: expected runtime is within plus-or-minus 10% of DURATION_MIN. If the script is too long, trim per-slide word budgets (cut filler, keep the beats); if too short, expand the proof and transition spoken bridges. Re-count and re-assert until within band.

4. Write a per-slide PACE MARKER on each slide block: per-slide spoken duration = (slide word count) / TARGET_WPM, in seconds. The owner sees how long each slide should take to say.

5. Record the pacing result in the script header: `{ "TARGET_WPM": 140, "wpm_reason": "...", "total_words": N, "expected_runtime_min": X, "duration_min": Y, "within_band": true|false }`.

**Outputs:**
- working/presenter-speech/presenters_speech.md (paced, with per-slide pace markers and the WPM header)

**Hand to:** SOP 9.3 (Designed PDF Render).

**Failure mode:** If the script cannot land within plus-or-minus 10% of DURATION_MIN even after trimming or expanding (for example the offer stack genuinely needs more time than DURATION_MIN allows), flag the duration conflict to the Director: either DURATION_MIN grows or the content is cut. Never ship a script that does not fit its time budget.

---

### SOP 9.3 -- Designed PDF Render (font-floor >=12 assert)

**When to run:** After the WPM pacing pass passes.

**Inputs:**
- working/presenter-speech/presenters_speech.md (paced)
- brand assets (logo, palette, font family) for the designed PDF

**Steps:**

1. Render the script to a DESIGNED PDF. Reuse the proven render path: the LibreOffice headless route (`soffice --headless --convert-to pdf`, as in pptx-assembly-specialist.md:262) via an intermediate styled document, or a Markdown-to-PDF path with a branded stylesheet. The speech PDF is laid out for reading aloud: generous line spacing, the hook beats and pause beats visually marked, the per-slide pace markers visible.

2. Enforce the FONT-FLOOR: no font below 12pt anywhere (the owner reads this aloud while presenting, so legibility is non-negotiable). This is a hard assert. If any element renders below 12pt, fix the stylesheet and re-render.

3. Verify the PDF was created, is non-empty, and opens. Confirm the font-floor by inspecting the smallest text element.

4. Name the file output/[DECK_SLUG]_presenters_speech.pdf.

**Outputs:**
- output/[DECK_SLUG]_presenters_speech.pdf (designed, no font below 12pt, marked for reading aloud)

**Hand to:** SOP 9.4 (Notion Publish + Verified Delivery).

**Failure mode:** If the render path fails, fall back to the alternate render path. If both fail, escalate to the Capacity and Reliability Engineer and the Director; never deliver a speech that renders below 12pt or did not render at all.

---

### SOP 9.4 -- Notion Publish + Verified Delivery via the Delivery Concierge

**When to run:** After the PDF renders and passes the font-floor assert.

**Inputs:**
- working/presenter-speech/presenters_speech.md
- output/[DECK_SLUG]_presenters_speech.pdf

**Steps:**

1. Publish the speech to Notion via the proven fallback chain, in order, stopping at the first that succeeds: PRIMARY Notion API; FALLBACK 1 Google Docs; FALLBACK 2 a hosted text / link to the PDF. On each leg, fetch the page back to confirm it exists before declaring that leg a success.

2. Hand both deliverables (PDF + Notion URL) to the Delivery Concierge (ROLE-13) using the standard dispatch contract, destinations resolved from intake.json (Mac Downloads / GHL / Drive per client box type).

3. The Delivery Concierge resolves destinations, uploads, sends the verified delivery notification via openclaw message send, and runs ground-truth verification (file hash + size). You do NOT upload or notify yourself.

4. Wait for the Delivery Concierge's verified-delivery confirmation (its delivery_complete ledger entry). Only then is the Presenters Speech considered shipped. Record the confirmation reference and notify the Director.

**Outputs:**
- A Notion (or fallback) URL for the speech and a verified-delivery confirmation from the Delivery Concierge

**Hand to:** Delivery Concierge (executes and verifies delivery); Director of Presentations (notified on verified delivery).

**Failure mode:** If all Notion legs fail, deliver the PDF and flag the outage. If the Delivery Concierge reports a delivery failure, do NOT self-report success; surface it to the Director and re-dispatch after the cause is fixed. An unverified delivery is not a delivery.

---

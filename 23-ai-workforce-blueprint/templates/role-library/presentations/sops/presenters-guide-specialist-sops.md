# SOPs Mirror -- Presenters Guide Specialist

**Source:** presentations/presenters-guide-specialist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Version:** 1.0

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Guide Assembly

**When to run:** After Phase 6 final QC passes AND the Presenter Coach has produced talk_track.md, and only if DELIVERABLE_SET includes the guide.

**Inputs:**
- working/coach/talk_track.md (the timed, slide-by-slide talk track)
- working/copy/arc_allocation.json (section banners, slide order, time allocation)
- output/pdf-pages/ (rendered slide thumbnails for the thumbnail references)

**Steps:**

1. Read the talk track and the arc allocation. Build the outline as one block per SECTION (a banner with the section name and its time budget) and within it one sub-block per SLIDE.

2. For each slide block, carry exactly these speaker cues (no more, to keep it at-a-glance):
   - **THUMBNAIL REF:** the slide number and a thumbnail reference (output/pdf-pages/slide-NN.png).
   - **ONE POINT TO DRIVE HOME:** the single takeaway for this slide, pulled from the talk track. One line. Never the full script.
   - **BEAT / TRANSITION:** how to move into the next slide (the transition sentence or gesture cue).
   - **TIME BUDGET:** the seconds or minutes allotted to this slide from the arc allocation.
   - **LADDER / HOOK CUE:** if this is a price-ladder drop slide or a dedicated hook slide, the cue (for example "DROP1 here: name the new value added" or "HOOK reprise: sing the line").

3. Keep the guide an OUTLINE. If a block grows past a few lines, it is drifting toward the Speech; trim it back to cues. The Guide is at-a-glance; the Speech is the full read.

4. Source every cue and one-point line from the talk track and the deck. Never fabricate a transition or a takeaway. If the talk track is silent on a slide, flag it back to the Presenter Coach rather than inventing.

5. Write working/presenter-guide/presenters_guide.md with a section-banner structure and the per-slide cue blocks.

**Outputs:**
- working/presenter-guide/presenters_guide.md (the speaker-facing outline source)

**Hand to:** SOP 9.2 (PDF Render).

**Failure mode:** If talk_track.md is missing or incomplete, do NOT write the guide from the deck copy alone (the deck is not the script). Request the talk track from the Presenter Coach and block until it exists.

---

### SOP 9.2 -- PDF Render (designed, branded, fonts >=12)

**When to run:** Immediately after SOP 9.1 produces presenters_guide.md.

**Inputs:**
- working/presenter-guide/presenters_guide.md
- brand assets (logo, palette, font family from the STYLE BLOCK) for the branded design

**Steps:**

1. Render presenters_guide.md to a DESIGNED, BRANDED PDF. Reuse the proven render path: either the LibreOffice headless route (`soffice --headless --convert-to pdf`, as in pptx-assembly-specialist.md:262) by way of an intermediate styled document, or a Markdown-to-PDF path with a branded stylesheet. Apply the brand logo, palette, and font family so the guide looks like a producer's run-of-show, not a plain dump.

2. Enforce the FONT-FLOOR: no font below 12pt anywhere in the rendered PDF (body, captions, footnotes, cues). This is a hard assert. If any element renders below 12pt, fix the stylesheet and re-render.

3. Verify the PDF was created, is non-empty, and opens. Confirm the font-floor by inspecting the smallest text element.

4. Name the file output/[DECK_SLUG]_presenters_guide.pdf.

**Outputs:**
- output/[DECK_SLUG]_presenters_guide.pdf (designed, branded, no font below 12pt)

**Hand to:** SOP 9.3 (Notion Publish).

**Failure mode:** If the render path fails (soffice unavailable, stylesheet error), fall back to the alternate render path (Markdown-to-PDF if soffice failed, or vice versa). If both fail, escalate to the Capacity and Reliability Engineer for the box environment and to the Director; never deliver a guide that renders below 12pt or did not render at all.

---

### SOP 9.3 -- Notion Publish (with fallback chain)

**When to run:** After the PDF renders and passes the font-floor assert.

**Inputs:**
- working/presenter-guide/presenters_guide.md
- output/[DECK_SLUG]_presenters_guide.pdf

**Steps:**

1. Publish the guide to Notion as a clean page via the proven fallback chain, in order, stopping at the first that succeeds:
   - PRIMARY: Notion API (create a page, render the outline as headings + blocks).
   - FALLBACK 1: Google Docs (create a doc from the markdown, share link).
   - FALLBACK 2: a hosted text / link to the PDF as the last resort.

2. On each leg, verify the page or doc actually exists (fetch it back) before declaring that leg a success. Do not trust a create call's return value alone.

3. Record which leg succeeded and the resulting URL in a publish record alongside the guide.

**Outputs:**
- A Notion page URL (or Google Docs / text fallback URL) for the Presenters Guide

**Hand to:** SOP 9.4 (Verified Delivery).

**Failure mode:** If all three legs fail, attach the PDF as the deliverable and flag the Notion outage to the Director; still proceed to verified delivery of the PDF so the owner is not left empty-handed. Never report "published" without fetching the page back.

---

### SOP 9.4 -- Verified Delivery via the Delivery Concierge

**When to run:** After the PDF and the Notion (or fallback) URL exist.

**Inputs:**
- output/[DECK_SLUG]_presenters_guide.pdf
- the Notion / Docs / text URL

**Steps:**

1. Hand both deliverables to the Delivery Concierge (ROLE-13) using the standard dispatch contract, with the destination set resolved from intake.json (Mac Downloads / GHL / Drive per the client box type).

2. The Delivery Concierge resolves destinations, uploads, sends the verified delivery notification via openclaw message send, and runs ground-truth verification (file hash + size). You do NOT upload or notify yourself; the last mile and the verification belong to the Concierge.

3. Wait for the Delivery Concierge's verified-delivery confirmation (its delivery_complete ledger entry). Only then is the Presenters Guide considered shipped.

4. Record the verified-delivery confirmation reference in the guide's publish record and notify the Director.

**Outputs:**
- A verified-delivery confirmation from the Delivery Concierge for the Presenters Guide PDF + Notion link

**Hand to:** Delivery Concierge (executes and verifies delivery); Director of Presentations (notified on verified delivery).

**Failure mode:** If the Delivery Concierge reports a delivery failure, do NOT self-report success. Surface the failure to the Director and re-dispatch after the cause is fixed. An unverified delivery is not a delivery.

---

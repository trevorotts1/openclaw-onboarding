# SOP-FBAD-08: HOST IN GOHIGHLEVEL, BUILD THE DOCS, APPROVE-TO-PUBLISH

**Cluster:** FB/IG Ad-Craft Rules
**Master authority:** `AD-PIPELINE-MANIFEST.json` + `MASTER-AD-QC-AUTOFAIL-RULESET.md` (Gate E)
**Owning roles:** Facebook Ads Specialist (+ Instagram Ads Specialist) for S7; Facebook & Instagram Ad-Run Producer for PUBLISH
**Stages:** S7-DELIVER (`depends_on: [S5-IMAGE-GEN, S6-TARGETING]`) → PUBLISH (`depends_on: [S7-DELIVER]`, **HUMAN GATE**)
**Produces:** S7 → `working/checkpoints/s7-deliver-receipt.json` + `working/s7-plai-brief.json` + the ad-text doc; PUBLISH → `working/checkpoints/approval-receipt.json`
**Gates:** S7 — AF-FBAD-FANOUT, AF-FBAD-GHL-URL, AF-FBAD-ADTEXT-DOC, AF-FBAD-PLAI-FIELDS, AF-FBAD-BOARD, AF-FBAD-PACKAGE-QC, AF-FBAD-QC-INDEPENDENCE; PUBLISH — AF-FBAD-APPROVE
**Helpers:** `ad_ghl_push.py` (+ `ghl_media.create_media_folder()`), `build_ad_text_doc.py`, `build_plai_brief.py`

---

## 0. WHY THIS SOP EXISTS

This is where the batch becomes a real, hand-off-able package: the 10 images hosted on
public, login-free links, a copy-paste-ready ad-text document, and a PLAI-ready brief —
then the second (and final) human pause. PLAI is the ONLY ad path; nothing here calls
Meta directly.

## 1. CHECK THE 1:1 FAN-OUT FIRST (AF-FBAD-FANOUT)

Before anything ships, confirm the counts line up: selection == bodies == headlines ==
prompts == images, all equal to the locked 10. A broken fan-out means an ad is missing
a piece — stop and fix before hosting.

## 2. HOST THE IMAGES IN GOHIGHLEVEL (AF-FBAD-GHL-URL)

Upload each approved image to the client's **own** GoHighLevel media library via
`ad_ghl_push.py` → `ghl_media.upload_media()` (`POST /medias/upload-file`, Bearer the
client's LOCATION Private Integration Token with `medias.write`, header
`Version: 2021-07-28`). Give the run its own folder via the NEW
`ghl_media.create_media_folder()` (`POST /medias/folder`, same Version header) with the
"upload to root with a name prefix" fallback. The response `url` is a public
`storage.googleapis.com/msgsndr/...` link — record it with its verified HTTP-200. A
fabricated/placeholder link is never accepted. Receipts are namespaced by the run-id so
a retry never re-uploads.

## 3. THE COPY-PASTE AD-TEXT DOCUMENT (AF-FBAD-ADTEXT-DOC)

`build_ad_text_doc.py` writes a copy-paste-ready document — into **Notion** if the
client has it, else a **Google Doc**, else **plain text**. Each of the 10 ads is shown
as **two separate copy-paste blocks: a Headline block and a Main Body block** — the
exact approved copy, verbatim, not a paraphrase. 10 Headline+Body pairs.

## 4. THE PLAI-READY BRIEF (AF-FBAD-PLAI-FIELDS)

`build_plai_brief.py` assembles `working/s7-plai-brief.json` carrying every field PLAI's
builder asks for: `campaign_name, objective, image_links, primary_texts, headlines,
targeting_groups, placements, destination_url` (the Group → Layer 1/2/3 targeting table
included), plus a human paste-guide. A missing field fails the gate.

## 5. ON THE BOARD (AF-FBAD-BOARD)

The campaign is one grouped campaign on the Command Center board; the `campaign_id`
(the receipt-number) is recorded. If the box's Command Center predates the endpoint,
degrade to ungrouped cards and log it (never silently drop the board).

## 6. GATE E — independent package QC + independence

The department's **Devil's Advocate** (not the Facebook Ads Specialist that assembled
it) grades the whole bundle: everything present, lines up 1:1, links actually work,
copy-paste-ready (Headline + Body as separate clean blocks), launch-complete. Pass =
8.5+ no category < 7 (AF-FBAD-PACKAGE-QC). Across ALL five gates, every scorecard must
be independent — grader ≠ maker, `independent: true` (AF-FBAD-QC-INDEPENDENCE).

## 7. APPROVE-TO-PUBLISH (the second human pause — non-skippable)

S7 attests; the card sits in **Review**. The owner is pinged with the images, copy, and
targeting brief, and approves. Approval is recorded (who + when + confirmed). Only then
does the PLAI handoff happen. This HUMAN GATE can never be skipped — no owner skip, no
`--adhoc`.

---

## 8. ATTESTATION APPEND (replaces any prose "do not skip")

`working/checkpoints/s7-deliver-receipt.json`:
```json
{
  "counts": { "selection": 10, "bodies": 10, "headlines": 10, "prompts": 10, "images": 10 },
  "delivered": [ { "image_url": "https://storage.googleapis.com/msgsndr/loc/ad0.png", "http_status": 200 } ],
  "adtext_block_pairs": 10,
  "adtext_matches_copy": true,
  "campaign_id": "<run-id>"
}
```
`working/s7-plai-brief.json` — all required PLAI fields.
`working/checkpoints/approval-receipt.json`:
```json
{ "approved_by": "<owner>", "approval_received_at": "2026-06-25T18:00:00-0400", "owner_confirmed": true }
```
`_chk_fanout` / `_chk_ghl_url` / `_chk_adtext_doc` / `_chk_plai_fields` / `_chk_board` /
`_chk_package_qc` / `_chk_qc_independence` validate S7; `_chk_approve` validates PUBLISH.

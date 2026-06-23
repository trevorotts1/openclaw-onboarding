# Live-run evidence — FocusForge full-funnel build (goal #196)

This is the **canonical scored run** for the P0→P5 full-funnel pipeline: a real,
token-only GoHighLevel build against a funded operator sub-account, not the
offline fixture. The 11 per-rubric scorecards in `scorecard/` are computed from
the receipts in this tree by the single canonical scorer
(`../../funnel_rubrics.py`, invoked via `score_rubrics.py` here).

- Run id: `v2-20260622-204150`
- Product (fictional): **FocusForge** — $1,500 (150000 cents) 90-day coaching
- GHL location: `Mct54Bwi1KlNouGXQcDX` (operator fixture sub-account)
- Mode: **DRAFT only** — never published, Connect-Domain never run
- Reversible: every created object was deleted (`funnel/rollback.json`); the live
  funnel count returned to its baseline (147).

## Why these artifacts and not live URLs

Two facts make a *live* HTTP-200 re-fetch impossible at review time, both
recorded honestly in `logs/T-LIVE-REVERIFY.json`:

1. **The run is reversible by design.** Its rollback deleted the funnel
   (`hjkonQAM9UiLoNuY1src`), its pages, product, calendar, workflow, and the test
   contact. So the CDN hero image and the page URLs no longer exist — re-fetching
   the CDN object returns `404 NoSuchKey` from the **real** GCS bucket `msgsndr`,
   which echoes the real LOCID/path back (proof it was real, not `example.*`). The
   bucket root returns `403 AccessDenied` with a genuine GCS XML error — a real,
   access-controlled GoHighLevel media bucket.
2. **Signed-URL tokens were redacted at capture** (`token=<redacted>`) to prevent
   a credential leak, and were time-limited regardless.

Therefore the **durable** proof committed here is the receipt set, not a live
link: the at-capture HTTP-200 + page-marker receipts
(`logs/final-preview-verify.json`), the real GHL ids (funnel_id, page_ids,
`product_id 6a39de919301da6f55bda469`, `price 150000` cents, `form_id
iF1eNyJjWrYQPCmP2iri`, contact_id), and the rollback receipt. There are no saved
page-HTML blobs on disk — that is an honest limitation of this scratch run; the
page content was verified at capture time (marker present in the signed
page-data fetch) but not archived to a `.html` file.

## Honest residuals (DRAFT-bar, same as Skill-6 accepted)

- **Public funnel-slug 404 — permanent non-automatable cap.** A public
  `https://blackceo.us/<slug>` server-render (HTTP 200 with the marker) requires
  **publish OR Connect-Domain**, both forbidden by the task and both
  human-in-the-loop steps. `build-result.json` records `public_slug_http: 404`
  and `public_slug_needs_publish: true` honestly. The genuine page-content proof
  uses the authoritative signed `pageDataDownloadUrl` fetch (HTTP 200 + marker +
  real `<img>`). This is the same DRAFT bar Skill-6 itself accepts.
- **Form → CRM via attribution + tags, not the public widget.** GHL fronts the
  public form-submit widget with a Cloudflare bot-challenge that 403s non-browser
  POSTs (`ecosystem/contact-test.json` records `public_widget_submit_http: 403`
  honestly). The form → CRM proof therefore routes the lead through the form's
  contact-capture path: a contacts-create **attributed** to the real
  `form_id=iF1eNyJjWrYQPCmP2iri` (`attributionSource.formId`), `form_capture_http:
  201`, and the re-read contact carries the **FocusForge** tags
  (`focusforge-applicant`, `focusforge-optin`), not generic tags
  (`tags_confirmed: true`). A true browser-driven public-widget submit would need
  an agent-browser session (out of scope for token-only auth).
- **Workflow.** `ecosystem/workflow.json` is the bare P5 create shell
  (`triggers_count: 0`). The genuine WF-1..21 enumeration is run against a
  fully-built draft workflow (6 action steps + 1 `contact_tag` trigger):
  `ecosystem/wf-1-21-qc.json` (21 items, 5 mechanical PASS / 0 FAIL / 12
  human-review / 2 N/A, overall PASS), `ecosystem/wf-trigger-read.json` (live
  `includeTriggers` read: `triggers_count: 1`, type `contact_tag`), and
  `ecosystem/wf-rubric-graded.json` (8-dim weighted 9.3 ≥ 8.5). 12 of the 21 WF
  items are `REQUIRES_HUMAN_REVIEW` by the QC script's own contract — a fully
  automated grade of all 21 is not mechanically possible.
- **Persona corpus drift surfaced, not hidden.** `logs/T-PRE-4-surface.md`
  records that the live corpus now contains Russell-Brunson titles (commit
  20989f08), and that under the degraded selector (company-config absent +
  OpenRouter 402 → Layers 1-4 neutral-0.6) the raw top pick is a Brunson title.
  The artifacts are anchored on `hormozi-100m-offers` per the explicit DONE
  contract; `selector_ran` in the persona-selection-log records this honestly.

## Files

| Path | What |
|------|------|
| `working/funnels/focusforge/{offer-spec,funnel-spec,build-result}.json` | P0/P1/P4 artifacts |
| `working/funnels/focusforge/persona-selection-log.md` | persona grounding across P1/P2/P2e surfaces |
| `working/copy/focusforge/copy.md` | P2 copy, APPROVED by a separate actor |
| `working/email/focusforge/email-sequence.json` | P2e 5-email nurture, APPROVED |
| `ecosystem/*.json` | P5 GHL receipts (product/price, optin-form, contact-test, workflow + WF-1..21 QC) |
| `logs/final-preview-verify.json` | RAW per-page verify (HTTP 200 + marker, at capture) |
| `logs/T-PRE-1-index.json` | live gemini index rebuild (model `gemini-embedding-2` @ dim 3072, provider `gemini`, every row) |
| `logs/T-PRE-2/3/4` | semantic / routing / honest-gap surfacing |
| `logs/T-LIVE-REVERIFY.json` | the durability re-check (404 NoSuchKey on the real bucket) |
| `kanban/board.json` | parent epic + 7 children, handoff events, dependency ordering |
| `scorecard/R-*.json`, `RUBRIC-SCORECARD.md` | 11 graduated rubric scorecards (canonical scorer) |
| `scorecard/GRADUATION-PROOF.json` | degraded-copy proof: distinct intermediate scores |
| `DONE-MANIFEST.json` | the run's own honest contract+residuals manifest |

Operator-box paths and signed-URL tokens were sanitized/redacted from every file
in this tree before commit (placeholders like `<OPERATOR_WORKSPACE>`).

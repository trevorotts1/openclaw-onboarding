# MASTER FUNNEL QC AUTO-FAIL RULESET (`universal-sops/funnel-craft/`)

The table every Signature Funnel page, image prompt, and certificate is measured against. Each code is a
hard, named `sys.exit(non-zero)` in a fail-closed prover or the orchestrator, never advisory, never an agent
self-score. This is the `universal-sops` mirror of the authoritative codes in
`49-signature-funnel/FUNNEL-MANIFEST.json` (`autofail_codes`); the provers are the source of truth.
SOP-LOCKED: this table lists every code in the manifest, one row each, and
`49-signature-funnel/scripts/test_sop_lockstep.py` fails if the two ever differ. To change it, edit the
manifest first, then regenerate the rows below from it (`python3 49-signature-funnel/scripts/test_sop_lockstep.py --print-rows`).
Triggers below are copied from the manifest verbatim.



## P0-INTAKE

| Code | Fires when |
|---|---|
| AF-FUN-INTAKE-TYPE | funnel_type != signature_funnel |
| AF-FUN-INTAKE-MISSING | a required intake answer (by funnel size) is missing/empty |
| AF-FUN-INTAKE-SIZE | funnel_size not in {3,5,7} |
| AF-FUN-INTAKE-OFFER | offer_token_ledger empty (Q1 offer not declared) |
| AF-FUN-INTAKE-REPRESENTATION | representation (Q8) not explicitly provided |
| AF-FUN-INTAKE-TRUTHGATE | community URL / bonus / founder-text not confirmed (Q16) |
| AF-FUN-INTAKE-UNLOCKED | brief not locked (provenance-gated) before generation |
| AF-FUN-INTAKE-PERSONA-LOG | persona-selection-log absent or names no registered persona slug (copywriter-persona Step-0 grounding); FIX-XC-02a fail-closed |

## P1-COPY

| Code | Fires when |
|---|---|
| AF-FUN-PROFILE-UNKNOWN | page_type not in the profiles map |
| AF-FUN-SECTION-MISSING | a required section for the page profile is absent, OR a page type the locked 3/5/7 funnel_matrix requires has no page in the copy ledger (main-only ledger; STR-19), OR the ledger contradicts the locked brief size / the size is unresolved (fail-closed) |
| AF-FUN-SECTION-EXTRA | a page carries a section not allowed by its profile |
| AF-FUN-SECTION-ORDER | sections duplicated / not ascending / bad id |
| AF-FUN-SEC1-CHARBAND | Section 1 outside 180-225 stripped chars |
| AF-FUN-SEC1-TITLE | Section 1 does not contain the product title |
| AF-FUN-SEC1-CTA | Section 1 missing a labeled CTA |
| AF-FUN-PAIN-CHARBAND | a pain section (2/3/4) outside 180-225 chars |
| AF-FUN-PAIN-QUESTION | a pain section is written in question format ('?') |
| AF-FUN-PAIN-2ND-PERSON | a pain section is not in 2nd person (no you/your) |
| AF-FUN-PAIN-CTA | a pain section missing a labeled CTA |
| AF-FUN-SEC5-WORDS | Section 5 outside 18-30 words (under-length is as much a hard miss as over-length) |
| AF-FUN-SEC5-LEAD | Section 5 does not start 'That's the reason why...' |
| AF-FUN-SEC5-CTA | Section 5 missing its motivational CTA |
| AF-FUN-SEC6-WORDS | Section 6 outside 18-30 words (under-length is as much a hard miss as over-length) |
| AF-FUN-SEC6-PERSONAS | Section 6 outside 3-6 personas |
| AF-FUN-SEC6-NO-CTA | Section 6 carries a CTA (forbidden) |
| AF-FUN-SEC7-WORDS | Section 7 outside 70-120 words |
| AF-FUN-SEC7-BULLETS | Section 7 outside 5-10 bullets |
| AF-FUN-BENEFIT-WORDS | a benefit section (8/9/10) outside 18-30 words (under-length is as much a hard miss as over-length) |
| AF-FUN-BENEFIT-NO-CTA | a benefit section (8/9) carries a CTA (forbidden) |
| AF-FUN-SEC10-CTA | Section 10 missing its inspirational CTA button |
| AF-FUN-SEC11-WORDS | Section 11 outside 100-150 words |
| AF-FUN-SEC11-NO-CTA-BUTTON | Section 11 carries a CTA button |
| AF-FUN-SEC11-STEPS | Section 11 outside 5-10 steps |
| AF-FUN-SEC11-STEPBAND | a Section 11 step 1-6 outside 89-116 chars |
| AF-FUN-SEC11-STEP7 | Section 11 step 7 (CTA) exceeds 170 chars |
| AF-FUN-SEC11-REQUIRED-STEPS | Section 11 missing share/email-bonus/founder-text/community step |
| AF-FUN-SEC12-WORDS | Section 12 outside 100-150 words |
| AF-FUN-SEC12-PARTS | Section 12 not exactly 6 labeled parts |
| AF-FUN-SEC12-STRUGGLE | Section 12 part 2 does not start 'I used to be just like you...' |
| AF-FUN-SEC8REPL-NAME | replacement Section 8 name mismatches the profile |
| AF-FUN-SEC8REPL-COUNT | replacement Section 8 not exactly 7 items |
| AF-FUN-TY1-CHARBAND | Thank-You TY-1 outside 120-180 chars |
| AF-FUN-TY1-TITLE | Thank-You TY-1 does not name the product title |
| AF-FUN-TY2-STEPS | Thank-You TY-2 outside 4-6 steps |
| AF-FUN-TY2-STEPBAND | a Thank-You TY-2 step outside 89-116 chars |
| AF-FUN-TY3-CHARBAND | Thank-You TY-3 exceeds 170 chars |

## P2-PROMPTS

| Code | Fires when |
|---|---|
| AF-FUN-PROMPT-FLOOR | image prompt under the KIE rule-12 floor (shared kie_prompt_enforcer) |
| AF-FUN-PROMPT-CEILING | image prompt over the KIE rule-12 ceiling (shared kie_prompt_enforcer) |
| AF-FUN-PROMPT-DENSITY | fewer than 220 distinct words (padding) |
| AF-FUN-PROMPT-GRADE | Signature Grade Block not embedded |
| AF-FUN-PROMPT-NEGATIVE | no negative block ('Do not ...') in the prompt |
| AF-FUN-PROMPT-EMDASH | an em/en dash present (model-safety rule) |
| AF-FUN-PROMPT-TYPO | text-bearing prompt lacks spelling-lock/words, or non-text prompt lacks 'no text' |
| AF-FUN-PROMPT-COVERAGE | prompt ledger is missing a required (page_type, section) image slot for the funnel size (partial ledger) |
| AF-FUN-PROMPT-STYLE-CARD | the intake names a Skill 45 style_card_id (Q18) but a prompt does not carry that card's LONG tier verbatim in block 8 ahead of the negatives, or the card cannot be read from the design library |

## P9-CERTIFY

| Code | Fires when |
|---|---|
| AF-FUN-IMG-COVERAGE | media ledger is missing a required (page_type, section) image slot for the funnel size (partial image set) |
| AF-FUN-P10-EMAILS | P10-EMAIL: the brief's email_offer is accepted but working/emails/emails.json is missing or carries no Skill 50 certificate sha (64-hex certificate_sha), or email_offer is neither accepted nor declined |
| AF-FUN-TY-PITCH | an offer/product NAME appears on the thank-you page |
| AF-FUN-TY-PRICE | a price/monetary token appears on the thank-you page |
| AF-FUN-TY-CTA | a sale/offer CTA (non-utility) on the thank-you page |
| AF-FUN-IMG-PROVENANCE | missing/placeholder/native Kie taskId |
| AF-FUN-IMG-HOST | media URL is not the hosted URL the P4 delivery-rail receipt recorded for that image (ledger-only: not a well-formed non-placeholder http(s) URL) |
| AF-FUN-OFFER-LEDGER-MISSING | no offer names to prove absent (fail-closed) |
| AF-FUN-TY-MISSING | no thank-you page (cannot prove no-pitch; fail-closed) |
| AF-FUN-IMG-EMPTY | no image records (cannot prove provenance; fail-closed) |
| AF-FUN-CERT-MISSING | certificate malformed / missing required field |
| AF-FUN-CERT-PHASE-GAP | phase orders not contiguous 0..N (a phase skipped) |
| AF-FUN-CERT-PHASE-FAIL | a phase status != pass / all_phases_pass not true |
| AF-FUN-CERT-SIGNATURE | HMAC signature invalid for the operator key (tamper/forgery) |
| AF-FUN-PROCESS-INTEGRITY | process certificate invalid -> funnel is NOT done |
| AF-FUN-MODEL-TIER | model-content-receipt absent or authoring tier is not an execution/content tier (client's own strongest model must write copy); FIX-XC-09e |

## P5-HTML

| Code | Fires when |
|---|---|
| AF-FUN-HTML-FRAGMENT | a pages/<profile>.fragment.html is missing/empty for a matrix page |

## P6-COMPOSE

| Code | Fires when |
|---|---|
| AF-FUN-GRAPH-SIZE | funnel_graph funnel_size absent / not in {3,5,7} |
| AF-FUN-GRAPH-TYPE | funnel_graph funnel_type != signature_funnel |
| AF-FUN-GRAPH-NODES | node id set does not match the MASTERDOC §3 matrix for the size |
| AF-FUN-GRAPH-EDGE | an edge references an unknown node or carries an illegal on-label |
| AF-FUN-GRAPH-TERMINAL | thank-you is not the unique terminal, or a non-terminal node is a dead end |
| AF-FUN-GRAPH-BRANCH | an upsell node is missing its accept or decline (one-click) edge |
| AF-FUN-GRAPH-REACH | a node is unreachable from main, or cannot reach thank-you |

## P7-BUILD

| Code | Fires when |
|---|---|
| AF-FUN-BUILD-FAB | the FAB scorecard build/fab-artifact.json is absent/unreadable or echoes no copy — the >=8.5 copy-substance gate cannot run (fail-closed; FIX-COPY-02) |
| AF-FUN-BUILD-MALFORMED | build_receipt.json absent/unreadable or carries no pages (fail-closed) |
| AF-FUN-BUILD-QC | build receipt qc_score missing/non-numeric or below the 8.5 floor |
| AF-FUN-BUILD-PREVIEW | a built page has no non-empty http(s) preview_url |
| AF-FUN-BUILD-TYPE | build receipt funnel_type != signature_funnel |
| AF-FUN-BUILD-PAGESET | the build receipt does not carry every page type the locked 3/5/7 funnel matrix requires (an under-sized receipt — a 7-step funnel with 3 pages — no longer certifies); A10/T0-11 |
| AF-FUN-BUILD-SIZE | the locked funnel size is unresolved (no brief size and no receipt funnel_size), so the required page set cannot be computed (fail-closed); A10/T0-11 |
| AF-FUN-BUILD-SIZE-MISMATCH | the build receipt declares a funnel_size that contradicts the locked brief size (the receipt does not describe this funnel); A10/T0-11 |
| AF-FUN-BUILD-PREVIEW-PLACEHOLDER | a page preview_url resolves to a placeholder/example/loopback host (a caller-authored stand-in is not a built preview); A10/T0-11 |
| AF-FUN-BUILD-QC-RECORD | no signed delivery-rail QC record: the P7-BUILD receipt lines are absent, unsigned, forged, for another run, authored by a certified module, break schema/delivery-rail-receipt.schema.json or miss a required page type; or the QC recomputed from the lines (10 x passing / total) is below the 8.5 floor, or the receipt qc_score is higher than the recomputed one (a receipt that only says 9.0 fails; STR-18/S06-08) |
| AF-FUN-BUILD-PREVIEW-UNBOUND | a receipt preview_url is not a URL that a passing delivery-rail P7 receipt line recorded (a real-looking host the rail never built; STR-18) |
| AF-FUN-BUILD-VISUAL | a page of the funnel has no wireframe/mockup set: page-images/page-images-receipt.json absent, or a page lacks its desktop-wireframe / mobile-tablet / visual-mockup stage-executor-record with images, or a record does not match the receipt sha256 (no certificate without visual direction; IMG-16) |

## P8-DERIVE

| Code | Fires when |
|---|---|
| AF-FUN-DERIVE-LEDGER | derived_pages.json absent/malformed, wrong derived set, or bad U1/D1/U2/D2/TY label |

## front-door

| Code | Fires when |
|---|---|
| AF-FUN-FRONT-DOOR | orchestrator called without the operator key, or with a caller-supplied nonce (refused; ENF-16) |
| AF-FUN-CANONICAL-BYPASS | run working files hand-roll GHL REST / mail sender / raw Kie createTask / a KIE client script (Skill 74 result files under receipts/kie74/ are allow-listed) |
| AF-FUN-HASH-PIN | enforcement-core sha256 does not match SF-PROVER-PIN.sha256 |

## P5-HTML/P7-BUILD

| Code | Fires when |
|---|---|
| AF-FUN-HTML-SECTIONS | a pages/<profile>.fragment.html lacks its root page marker, does not carry exactly the profile's data-section markers in order (12 for main, 8 for derived pages, TY-1..TY-3 for thank-you), or a section carries no real text (a fragment of 'x' fails; STR-18) |

## P3-IMAGES

| Code | Fires when |
|---|---|
| AF-FUN-DELEG-IMAGES | P3-IMAGES: media ledger carries no image records or an image has no real image-provider task id (file existence is no longer proof of delegated image generation); A10/T0-09 |

## P4-MEDIA

| Code | Fires when |
|---|---|
| AF-FUN-DELEG-MEDIA | P4-MEDIA: a ledger image carries a URL that differs from the hosted_url the delivery rail's signed receipt recorded for it, or the ledger is absent (an un-uploaded image is not a delegated upload); A10/T0-09 |

## P3-IMAGES/P4-MEDIA

| Code | Fires when |
|---|---|
| AF-FUN-DELEG-RECEIPT-SELF-AUTHORED | a delegated-phase provider receipt is present but SELF-AUTHORED by the certificate's own subject (the run stamped its own evidence) — the strongest A10/T0-09 protection; the same validator also rejects a non-2xx status, a placeholder response/remote id, and a ledger row no provider was called for (-STATUS / -ID / -COVERAGE / -MISSING-PHASE / -MALFORMED / -ABSENT) |
---

**Client-runtime note:** every prover is deterministic, stdlib-only, model-free; it runs identically on
a client box using no model at all. Generation (copy/prompts) runs on the CLIENT's own configured
provider chain, never Anthropic, never operator keys.

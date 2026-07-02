# MASTER FUNNEL QC AUTO-FAIL RULESET (`universal-sops/funnel-craft/`)

The table every Signature Funnel page, image prompt, and certificate is measured against. Each code is a
hard, named `sys.exit(non-zero)` in a fail-closed prover — never advisory, never an agent self-score.
This is the `universal-sops` mirror of the authoritative codes in
`49-signature-funnel/FUNNEL-MANIFEST.json`; the provers are the source of truth. SOP-LOCKED: keep this
table in lockstep with the manifest.

## P0-INTAKE — `prove_sf_intake.py`

| Code | Fires when |
|---|---|
| AF-FUN-INTAKE-TYPE | `funnel_type` is not `signature-funnel`. |
| AF-FUN-INTAKE-MISSING | A required intake answer is missing/empty. |
| AF-FUN-INTAKE-SIZE | `funnel_size` is not one of 3 / 5 / 7. |
| AF-FUN-INTAKE-OFFER | The size-gated offer ledger (OTO1/D1/OTO2/D2) is incomplete for the chosen size. |
| AF-FUN-INTAKE-REPRESENTATION | Audience representation percentages were assumed rather than captured. |
| AF-FUN-INTAKE-TRUTHGATE | A bonus / founder-text / community was not confirmed real. |
| AF-FUN-INTAKE-UNLOCKED | The brief was not locked before advancing. |

## P1-COPY / P8-DERIVE — `prove_sf_copy.py`

| Code | Fires when |
|---|---|
| AF-FUN-PROFILE-UNKNOWN | A page profile is not one of the six (+ checkout). |
| AF-FUN-SECTION-MISSING / -EXTRA / -ORDER | A section is missing, extra, or out of order. |
| AF-FUN-SEC1-CHARBAND / -TITLE / -CTA | Sec 1 out of 180–225 chars, missing the product title, or missing the labeled CTA. |
| AF-FUN-PAIN-CHARBAND / -QUESTION / -2ND-PERSON / -CTA | A pain section (2–4) out of band, phrased as a question, not 2nd person, or missing its CTA. |
| AF-FUN-SEC5-WORDS / -LEAD / -CTA | Sec 5 over 30 words, not starting "That's the reason why…", or missing the CTA. |
| AF-FUN-SEC6-WORDS / -PERSONAS / -NO-CTA | Sec 6 over 30 words, not 3–6 personas, or carrying a forbidden CTA. |
| AF-FUN-SEC7-WORDS / -BULLETS | Sec 7 out of 70–120 words or not 5–10 bullets. |
| AF-FUN-BENEFIT-WORDS / -NO-CTA | Sec 8/9 over 30 words or carrying a forbidden CTA button. |
| AF-FUN-SEC10-CTA | Sec 10 missing its inspirational CTA button. |
| AF-FUN-SEC11-WORDS / -NO-CTA-BUTTON / -STEPS / -STEPBAND / -STEP7 / -REQUIRED-STEPS | Sec 11 out of 100–150 words, carrying a button, wrong step count, a step out of 89–116, step 7 over 170, or missing a share / email-bonus / founder-text / community step. |
| AF-FUN-SEC12-WORDS / -PARTS / -STRUGGLE | Sec 12 out of 100–150 words, not exactly 6 labeled parts, or part 2 not starting "I used to be just like you…". |
| AF-FUN-SEC8REPL-NAME / -COUNT | A derived page's replacement Section 8 has the wrong name or not exactly 7 items. |
| AF-FUN-TY1-CHARBAND / -TITLE | TY-1 out of 120–180 chars or missing the product title. |
| AF-FUN-TY2-STEPS / -STEPBAND | TY-2 not 4–6 steps or a step out of 89–116 chars. |
| AF-FUN-TY3-CHARBAND | TY-3 over 170 chars. |

## P2-PROMPTS — `prove_sf_prompt_floor.py`

| Code | Fires when |
|---|---|
| AF-FUN-PROMPT-FLOOR / -CEILING | A prompt under 5,000 or over 19,000 stripped chars. |
| AF-FUN-PROMPT-DENSITY | Distinct-word density floor failed (padding attack). |
| AF-FUN-PROMPT-GRADE | The Signature Grade Block is absent/altered. |
| AF-FUN-PROMPT-NEGATIVE | The negative block is missing from the final paragraph. |
| AF-FUN-PROMPT-EMDASH | An em dash appears in an image prompt. |
| AF-FUN-PROMPT-TYPO | Sec 11 typography rule (three spelling-locked quoted words) violated. |

## P3-IMAGES / P4-MEDIA — provenance + host

| Code | Fires when |
|---|---|
| AF-FUN-IMG-PROVENANCE | An image lacks a real Kie taskId (native/placeholder). |
| AF-FUN-IMG-EMPTY | A page has no images. |
| AF-FUN-IMG-HOST | An `<img>` does not resolve to the GHL media host. |

## P9-CERTIFY — `prove_sf_no_pitch.py` + `prove_sf_cert.py`

| Code | Fires when |
|---|---|
| AF-FUN-TY-PITCH / -PRICE / -CTA | The Thank-You page names an offer, a price, or a sale CTA. |
| AF-FUN-TY-MISSING | No Thank-You page. |
| AF-FUN-OFFER-LEDGER-MISSING | The offer ledger is empty at certify time. |
| AF-FUN-CERT-MISSING | No certificate emitted. |
| AF-FUN-CERT-PHASE-GAP / -PHASE-FAIL | The phase ledger is non-contiguous or a phase failed. |
| AF-FUN-CERT-SIGNATURE | The certificate HMAC is invalid. |
| AF-FUN-PROCESS-INTEGRITY | The phase chain is broken / a phase was skipped. |

## Front door — `signature-funnel-entry.sh`

| Code | Fires when |
|---|---|
| AF-FUN-FRONT-DOOR | The orchestrator was called without the run-scoped 0600 nonce. |
| AF-FUN-CANONICAL-BYPASS | A hand-rolled GHL/Kie/mail driver was detected in the run dir. |
| AF-FUN-HASH-PIN | The deployed provers do not match the pinned hash (`scripts/SF-PROVER-PIN.sha256`). |

---

**Client-runtime note:** every prover is deterministic, stdlib-only, model-free — it runs identically on
a client box using no model at all. Generation (copy/prompts) runs on the CLIENT's own configured
provider chain, never Anthropic, never operator keys.
